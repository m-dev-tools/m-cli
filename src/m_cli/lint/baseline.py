"""Baseline-file support for ``m lint``.

A baseline freezes the *currently-known* findings in a project so the
linter can be set strict (`--rules=modern`, tight thresholds, low
`--error-on`) without flooding new noise on every run. After a
baseline is captured, only findings *not* in the baseline are
reported.

Format: a small JSON file with a stable schema. Each entry is keyed by
``(relative_path, line, rule_id)`` plus a short ``message_hash`` so a
finding that gets re-numbered (e.g. file edited above the diagnostic
site) reappears — the user has to confirm the new state by re-running
``m lint --update-baseline``.

Path normalisation:
- relative to the baseline file's directory (so the project moves cleanly)
- POSIX separators on every platform (so Windows / Linux baselines diff)

Match policy: a diagnostic is "in the baseline" if every key field
(path / line / rule_id / message_hash) matches an entry. Column is
omitted intentionally — it's stable enough but not load-bearing for
the suppression check.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from m_cli.lint.diagnostic import Diagnostic

DEFAULT_BASELINE_NAME = ".m-lint-baseline.json"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class BaselineEntry:
    """A single suppressed finding."""

    path: str  # POSIX-style, relative to baseline file's directory
    line: int
    rule_id: str
    message_hash: str  # short hash of the diagnostic message


def _hash_message(message: str) -> str:
    """Short stable hash of a diagnostic message — first 12 chars of sha1.

    Used as a tie-breaker so re-numbering or duplicates fan out cleanly.
    Truncated for readability in JSON; collisions on the same
    ``(path, line, rule_id)`` are vanishingly unlikely.
    """
    return hashlib.sha1(message.encode("utf-8")).hexdigest()[:12]


def find_baseline(start: Path, name: str = DEFAULT_BASELINE_NAME) -> Path | None:
    """Walk up from ``start`` looking for a baseline file.

    Stops at a ``.git`` boundary so a baseline in an unrelated parent
    project doesn't apply. Mirrors :func:`m_cli.config.find_config`.
    """
    cur = start.resolve()
    while True:
        candidate = cur / name
        if candidate.is_file():
            return candidate
        if (cur / ".git").exists():
            return None
        if cur.parent == cur:
            return None
        cur = cur.parent


def load_baseline(baseline_path: Path) -> list[BaselineEntry]:
    """Load entries from a baseline file. Missing file → empty list."""
    if not baseline_path.is_file():
        return []
    try:
        data = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(
            f"failed to read baseline at {baseline_path}: {e}"
        ) from e
    version = data.get("version")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported baseline schema version {version!r} "
            f"in {baseline_path} (expected {SCHEMA_VERSION})"
        )
    out: list[BaselineEntry] = []
    for raw in data.get("entries", []):
        try:
            out.append(
                BaselineEntry(
                    path=raw["path"],
                    line=int(raw["line"]),
                    rule_id=raw["rule_id"],
                    message_hash=raw["message_hash"],
                )
            )
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(
                f"malformed baseline entry in {baseline_path}: {raw!r} ({e})"
            ) from e
    return out


def write_baseline(
    baseline_path: Path, diags: list[Diagnostic], project_root: Path
) -> int:
    """Write ``diags`` as a fresh baseline file. Returns count written.

    Paths are stored relative to ``project_root`` (the baseline file's
    directory) using POSIX separators, so the file is portable across
    machines and OSes.
    """
    entries = []
    for d in diags:
        entries.append(
            {
                "path": _relative_posix(d.path, project_root),
                "line": d.line,
                "rule_id": d.rule_id,
                "message_hash": _hash_message(d.message),
            }
        )
    # Stable order — easy to diff across `--update-baseline` runs.
    entries.sort(key=lambda e: (e["path"], e["line"], e["rule_id"], e["message_hash"]))
    payload = {
        "version": SCHEMA_VERSION,
        "entries": entries,
    }
    baseline_path.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    return len(entries)


def filter_baselined(
    diags: list[Diagnostic], baseline: list[BaselineEntry], project_root: Path
) -> tuple[list[Diagnostic], int]:
    """Drop ``diags`` that match a baseline entry.

    Returns ``(remaining, suppressed_count)``. Match key is
    ``(relative-posix-path, line, rule_id, message_hash)``.
    """
    if not baseline:
        return diags, 0
    keys = {
        (e.path, e.line, e.rule_id, e.message_hash) for e in baseline
    }
    out: list[Diagnostic] = []
    suppressed = 0
    for d in diags:
        key = (
            _relative_posix(d.path, project_root),
            d.line,
            d.rule_id,
            _hash_message(d.message),
        )
        if key in keys:
            suppressed += 1
            continue
        out.append(d)
    return out, suppressed


def _relative_posix(path: Path, root: Path) -> str:
    """Return ``path`` relative to ``root``, using POSIX separators.

    If ``path`` is not under ``root`` (e.g. the user lints a file
    outside the project), fall back to the absolute POSIX form so
    the baseline still works — the entry just won't be portable.
    """
    try:
        rel = path.resolve().relative_to(root.resolve())
        return rel.as_posix()
    except ValueError:
        return path.resolve().as_posix()
