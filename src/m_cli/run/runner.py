"""Pure-logic helpers for ``m run``.

Kept free of subprocess and CLI concerns so the unit tests can verify
entryref parsing, env composition, and command composition without a
live ydb.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

_LABEL_RE = re.compile(r"^[A-Za-z%][A-Za-z0-9]*$")
_ROUTINE_MAX = 8  # M routine-name limit


class EntryrefError(ValueError):
    """Raised when an entryref string can't be parsed."""


def parse_entryref(text: str) -> tuple[str, str]:
    """Parse ``ROUTINE`` or ``LABEL^ROUTINE`` into ``(label, routine)``.

    The routine name is uppercased and truncated to 8 chars (M's
    routine-name limit). The label is uppercased but kept full-length
    (M label names are also typically ≤ 8 but ydb is permissive).
    Returns ``("", routine)`` for the bare-routine form.
    """
    s = (text or "").strip()
    if not s:
        raise EntryrefError("entryref must not be empty")

    if "^" in s:
        label, _, routine = s.partition("^")
        label = label.upper()
        routine = routine.upper()
    else:
        label = ""
        routine = s.upper()

    if label and not _LABEL_RE.match(label):
        raise EntryrefError(f"invalid label {label!r} in entryref {text!r}")
    if not routine or not _LABEL_RE.match(routine):
        raise EntryrefError(f"invalid routine {routine!r} in entryref {text!r}")
    if routine[0].isdigit():
        raise EntryrefError(f"routine {routine!r} starts with a digit")

    return label, routine[:_ROUTINE_MAX]


def resolve_ydb_binary() -> str | None:
    """Locate the ydb binary. Returns the path or ``None`` if missing.

    Order: ``$YDB`` → ``$ydb_dist/ydb`` → ``ydb`` on ``$PATH``.
    """
    explicit = os.environ.get("YDB")
    if explicit:
        p = Path(explicit)
        if p.exists() and os.access(p, os.X_OK):
            return str(p)
    dist = os.environ.get("ydb_dist")
    if dist:
        candidate = Path(dist) / "ydb"
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    on_path = shutil.which("ydb")
    return on_path


def build_env(routines: list[str] | None) -> dict[str, str]:
    """Compose the env for the ydb subprocess.

    Inherits the parent env. If ``routines`` is non-empty, prepends
    each path to ``$ydb_routines`` (space-separated, ydb's convention).
    """
    env = dict(os.environ)
    if routines:
        existing = env.get("ydb_routines", "")
        joined = " ".join(routines)
        if existing:
            env["ydb_routines"] = f"{joined} {existing}"
        else:
            env["ydb_routines"] = joined
    return env


def build_command(
    binary: str,
    label: str,
    routine: str,
    extra_args: list[str],
) -> list[str]:
    """Build the argv list for ``ydb -run``.

    ``extra_args`` are appended verbatim (passed through ydb to the M
    program via $ZCMDLINE).
    """
    entryref = f"{label}^{routine}" if label else f"^{routine}"
    return [binary, "-run", entryref, *extra_args]
