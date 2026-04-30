"""Project-level configuration for m-cli.

Loads settings from one of two locations, walked up from the start
directory toward the filesystem root (or the nearest ``.git`` boundary):

  1. ``.m-cli.toml`` — preferred, project-local file
  2. ``[tool.m-cli]`` table in ``pyproject.toml`` — for projects that
     already use Python packaging conventions

Settings layer like this: defaults → config file → CLI flag. CLI
flags always win. The config file is optional; an absent file
yields :func:`Config.empty()` and changes nothing.

Schema (TOML)::

    [lint]
    rules = "default"              # profile name or comma-list of rule IDs
                                   # — built-in profiles: default, xindex
                                   # (VA VistA Toolkit), sac, all. See
                                   # `m lint --list-profiles`.
    disable = ["M-XINDX-013"]      # rule ids to skip after selection
    target_engine = "any"          # "any" (default) | "yottadb" | "iris"
                                   # Used by engine-aware rules to choose
                                   # the right $Z*/Z-command allowlist.

    [lint.severity]
    "M-XINDX-019" = "warning"      # downgrade/upgrade per-rule severity

    [lint.thresholds]
    line_length = 200              # M-MOD-001 (replaces M-XINDX-019)
    code_line_length = 1000        # M-MOD-002 (replaces M-XINDX-058)
    routine_lines = 1000           # M-MOD-003 (replaces M-XINDX-035)
    label_lines = 50               # M-MOD-004
    # See `m_cli.lint.thresholds.KNOWN_THRESHOLDS` for the full list
    # of supported keys and their defaults.

    [fmt]
    rules = "identity"             # canonical, identity, or comma-list

The keys above are the only ones honored. Unknown keys are ignored
silently — that keeps forward compatibility cheap, but means a typo
won't be flagged. ``severity`` values must be one of the four
:class:`m_cli.lint.diagnostic.Severity` strings.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from m_cli.lint.diagnostic import Severity

CONFIG_FILENAME = ".m-cli.toml"
PYPROJECT_FILENAME = "pyproject.toml"
PYPROJECT_TABLE = "m-cli"  # nested under [tool.m-cli]


# Recognized values for `[lint] target_engine` / `--target-engine`.
# `any` (default) means engine-aware rules don't apply — the linter
# stays portable. The named engines unlock engine-specific allowlists
# (e.g. which $Z* ISVs are legitimate, which Z-commands ship with the
# engine).
KNOWN_ENGINES: tuple[str, ...] = ("any", "yottadb", "iris")


@dataclass(frozen=True)
class Config:
    """Resolved m-cli configuration.

    ``None`` for any field means "not configured" — the CLI / LSP
    falls back to its built-in default.
    """

    lint_rules: str | None = None
    lint_disable: tuple[str, ...] = ()
    lint_severity_overrides: dict[str, "Severity"] = field(default_factory=dict)
    lint_target_engine: str | None = None
    lint_thresholds: dict[str, int] = field(default_factory=dict)
    # [lint.taint] — controls Phase 9 taint analysis (M-MOD-036).
    # ``None`` for ``lint_taint_formals_tainted`` means "use the
    # built-in default" (which is True — public-label formals are
    # treated as untrusted attack surface).
    lint_taint_formals_tainted: bool | None = None
    lint_taint_extra_sanitizers: tuple[str, ...] = ()
    fmt_rules: str | None = None
    source_path: Path | None = None  # where this Config was loaded from, if any

    @staticmethod
    def empty() -> Config:
        return Config()


def find_config(start: Path) -> Path | None:
    """Walk up from ``start`` looking for an m-cli config file.

    Returns the first match: a ``.m-cli.toml`` is preferred over a
    ``pyproject.toml`` at the same level. Stops at the filesystem
    root or at a directory containing ``.git`` (whichever comes
    first) — that mirrors how ruff / black scope a project.
    """
    current = start.resolve() if start.exists() else start
    if current.is_file():
        current = current.parent
    while True:
        local = current / CONFIG_FILENAME
        if local.is_file():
            return local
        pyproject = current / PYPROJECT_FILENAME
        if pyproject.is_file() and _pyproject_has_m_cli_table(pyproject):
            return pyproject
        # Stop at git boundary (don't escape the project) or at /
        if (current / ".git").exists() or current.parent == current:
            return None
        current = current.parent


def load_config(start: Path) -> Config:
    """Load m-cli config starting from ``start``.

    Returns :func:`Config.empty` if no config file is found or the
    found file is unreadable / malformed. Errors are surfaced via
    ``ValueError`` only when a value is present but invalid (e.g. a
    bad severity name) — missing files don't raise.
    """
    path = find_config(start)
    if path is None:
        return Config.empty()
    try:
        data = path.read_bytes()
    except OSError:
        return Config.empty()
    try:
        parsed = tomllib.loads(data.decode("utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"{path}: invalid TOML: {e}") from e
    if path.name == PYPROJECT_FILENAME:
        section = parsed.get("tool", {}).get(PYPROJECT_TABLE, {})
    else:
        section = parsed
    return _from_dict(section, source=path)


def _pyproject_has_m_cli_table(path: Path) -> bool:
    try:
        parsed = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return False
    return PYPROJECT_TABLE in parsed.get("tool", {})


def _from_dict(section: dict, *, source: Path) -> Config:
    # Imported here (not at module top) to break a circular dep:
    # m_cli.lint.cli imports m_cli.config, and m_cli.lint.__init__
    # imports m_cli.lint.cli — pulling Severity at module load time
    # would form a cycle.
    from m_cli.lint.diagnostic import Severity

    lint = section.get("lint", {}) or {}
    fmt = section.get("fmt", {}) or {}
    lint_rules = lint.get("rules") if isinstance(lint.get("rules"), str) else None
    fmt_rules = fmt.get("rules") if isinstance(fmt.get("rules"), str) else None

    disable_raw = lint.get("disable", []) or []
    if not isinstance(disable_raw, list):
        raise ValueError(
            f"{source}: [lint] disable must be a list of rule ids, got {type(disable_raw).__name__}"
        )
    disable = tuple(str(item) for item in disable_raw if item)

    severity_raw = lint.get("severity", {}) or {}
    if not isinstance(severity_raw, dict):
        raise ValueError(f"{source}: [lint.severity] must be a table mapping rule id -> severity")
    overrides: dict[str, Severity] = {}
    valid_names = {sev.value: sev for sev in Severity}
    for rule_id, sev_name in severity_raw.items():
        if not isinstance(sev_name, str):
            type_name = type(sev_name).__name__
            raise ValueError(
                f"{source}: [lint.severity] {rule_id!r}: expected a string, got {type_name}"
            )
        sev = valid_names.get(sev_name.strip().lower())
        if sev is None:
            raise ValueError(
                f"{source}: [lint.severity] {rule_id!r}: unknown severity "
                f"{sev_name!r} (expected one of {sorted(valid_names)})"
            )
        overrides[rule_id] = sev

    thresholds_raw = lint.get("thresholds", {}) or {}
    if not isinstance(thresholds_raw, dict):
        raise ValueError(
            f"{source}: [lint.thresholds] must be a table mapping name -> "
            f"positive integer, got {type(thresholds_raw).__name__}"
        )
    # Validate against the m_cli.lint.thresholds allowlist. Imported here
    # to avoid a circular dep at module load time (m_cli.lint imports
    # m_cli.config via the lint CLI).
    from m_cli.lint.thresholds import validate as _validate_thresholds

    try:
        # _validate_thresholds returns the merged dict (defaults + overrides)
        # but Config stores ONLY the user-supplied overrides — defaults are
        # applied at LintContext-build time. Validating here just rejects
        # bad values early.
        _validate_thresholds({k: v for k, v in thresholds_raw.items()})
    except ValueError as e:
        raise ValueError(f"{source}: [lint.thresholds]: {e}") from e
    thresholds: dict[str, int] = {
        str(k): int(v) for k, v in thresholds_raw.items()
    }

    target_engine_raw = lint.get("target_engine")
    target_engine: str | None = None
    if target_engine_raw is not None:
        if not isinstance(target_engine_raw, str):
            type_name = type(target_engine_raw).__name__
            raise ValueError(f"{source}: [lint] target_engine must be a string, got {type_name}")
        normalized = target_engine_raw.strip().lower()
        if normalized not in KNOWN_ENGINES:
            raise ValueError(
                f"{source}: [lint] target_engine {target_engine_raw!r}: unknown "
                f"engine (expected one of {list(KNOWN_ENGINES)})"
            )
        target_engine = normalized

    taint_raw = lint.get("taint", {}) or {}
    if not isinstance(taint_raw, dict):
        raise ValueError(
            f"{source}: [lint.taint] must be a table, got "
            f"{type(taint_raw).__name__}"
        )
    taint_formals_tainted: bool | None = None
    if "formals_tainted" in taint_raw:
        ft = taint_raw["formals_tainted"]
        if not isinstance(ft, bool):
            raise ValueError(
                f"{source}: [lint.taint] formals_tainted must be a boolean, "
                f"got {type(ft).__name__}"
            )
        taint_formals_tainted = ft
    extra_san_raw = taint_raw.get("extra_sanitizers", []) or []
    if not isinstance(extra_san_raw, list):
        raise ValueError(
            f"{source}: [lint.taint] extra_sanitizers must be a list of "
            f"intrinsic-keyword strings, got {type(extra_san_raw).__name__}"
        )
    taint_extra_sanitizers = tuple(
        str(item).strip().upper() for item in extra_san_raw if item
    )

    return Config(
        lint_rules=lint_rules,
        lint_disable=disable,
        lint_severity_overrides=overrides,
        lint_target_engine=target_engine,
        lint_thresholds=thresholds,
        lint_taint_formals_tainted=taint_formals_tainted,
        lint_taint_extra_sanitizers=taint_extra_sanitizers,
        fmt_rules=fmt_rules,
        source_path=source,
    )


__all__ = [
    "CONFIG_FILENAME",
    "Config",
    "KNOWN_ENGINES",
    "PYPROJECT_FILENAME",
    "PYPROJECT_TABLE",
    "find_config",
    "load_config",
]
