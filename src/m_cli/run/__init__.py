"""m run — thin wrapper around ``ydb -run ENTRYREF``.

Resolves the ydb binary, composes ``$ydb_routines`` (optionally
prepending project paths), and execs ``ydb -run`` with the given
entryref. Pass-through stdout/stderr; the subprocess returncode is
returned directly so M's exit codes flow back to the caller.
"""

from m_cli.run.cli import run_command
from m_cli.run.runner import (
    EntryrefError,
    build_command,
    build_env,
    parse_entryref,
    resolve_ydb_binary,
)

__all__ = [
    "run_command",
    "EntryrefError",
    "build_command",
    "build_env",
    "parse_entryref",
    "resolve_ydb_binary",
]
