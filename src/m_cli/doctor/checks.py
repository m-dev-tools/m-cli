"""Environment-health checks for ``m doctor``.

Each ``check_*`` function is independent and returns a :class:`Check`.
``run_all_checks()`` runs them in a stable order and returns the list.
"""

from __future__ import annotations

import enum
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


class Status(enum.Enum):
    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    message: str
    hint: str | None = None


def check_ydb_dist() -> Check:
    """Check `$ydb_dist` env var: set, exists, contains a `ydb` binary."""
    val = os.environ.get("ydb_dist")
    if not val:
        return Check(
            name="ydb_dist",
            status=Status.WARN,
            message="not set",
            hint=(
                "Source your YottaDB env script (e.g. "
                "`source $ydb_dist/ydb_env_set`) or export "
                "`ydb_dist=/usr/local/lib/yottadb/r2.07`."
            ),
        )
    path = Path(val)
    if not path.exists():
        return Check(
            name="ydb_dist",
            status=Status.FAIL,
            message=f"missing directory: {val}",
            hint="Set $ydb_dist to a real YottaDB install directory.",
        )
    if not path.is_dir():
        return Check(
            name="ydb_dist",
            status=Status.FAIL,
            message=f"not a directory: {val}",
            hint="$ydb_dist must point at the YottaDB install directory.",
        )
    binary = path / "ydb"
    if not binary.exists():
        return Check(
            name="ydb_dist",
            status=Status.WARN,
            message=f"directory ok but no `ydb` binary inside ({val})",
            hint=(
                "Reinstall YottaDB or check the directory layout — the "
                "expected binary is `$ydb_dist/ydb`."
            ),
        )
    return Check(name="ydb_dist", status=Status.OK, message=val)


def check_ydb_routines() -> Check:
    """Check `$ydb_routines` is set (the routine search path)."""
    val = os.environ.get("ydb_routines")
    if not val:
        return Check(
            name="ydb_routines",
            status=Status.WARN,
            message="not set",
            hint=(
                "Export `ydb_routines` to your routine search path, "
                "typically containing your project's `routines/` and "
                "`$ydb_dist/libyottadbutil.so`."
            ),
        )
    return Check(name="ydb_routines", status=Status.OK, message=val)


def check_parser() -> Check:
    """Confirm tree-sitter-m parses a trivial routine."""
    try:
        from m_cli.parser import parse

        tree = parse(b"HELLO ;test\n Q\n")
        if tree.root_node is None:
            return Check(
                name="parser",
                status=Status.FAIL,
                message="parser returned no root node",
                hint="Reinstall tree-sitter-m: pip install -e ../tree-sitter-m",
            )
        return Check(
            name="parser",
            status=Status.OK,
            message="tree-sitter-m loaded",
        )
    except Exception as exc:  # pragma: no cover - import-error path
        return Check(
            name="parser",
            status=Status.FAIL,
            message=f"failed to parse: {exc.__class__.__name__}: {exc}",
            hint="Reinstall tree-sitter-m and verify the .so is present.",
        )


def check_keywords() -> Check:
    """Confirm m-standard keyword TSVs load."""
    try:
        from m_cli.lint._keywords import keyword_records

        records = keyword_records()
        n = len(records)
        if n == 0:
            return Check(
                name="keywords",
                status=Status.FAIL,
                message="m-standard returned 0 keyword records",
                hint="Check m-standard install — TSVs may be missing.",
            )
        return Check(
            name="keywords",
            status=Status.OK,
            message=f"{n} M language keywords loaded from m-standard",
        )
    except Exception as exc:  # pragma: no cover - import-error path
        return Check(
            name="keywords",
            status=Status.FAIL,
            message=f"keyword loader raised {exc.__class__.__name__}: {exc}",
            hint="Reinstall m-standard or verify its TSVs are reachable.",
        )


def check_ydb_binary() -> Check:
    """Locate the `ydb` binary via `$YDB`, `$ydb_dist/ydb`, or PATH."""
    explicit = os.environ.get("YDB")
    if explicit:
        path = Path(explicit)
        if path.exists() and os.access(path, os.X_OK):
            return Check(
                name="ydb_binary",
                status=Status.OK,
                message=f"$YDB → {path}",
            )
        return Check(
            name="ydb_binary",
            status=Status.FAIL,
            message=f"$YDB points at non-executable path: {explicit}",
            hint="Unset $YDB or fix it to point at a real ydb binary.",
        )
    dist = os.environ.get("ydb_dist")
    if dist:
        candidate = Path(dist) / "ydb"
        if candidate.exists() and os.access(candidate, os.X_OK):
            return Check(
                name="ydb_binary",
                status=Status.OK,
                message=f"$ydb_dist/ydb → {candidate}",
            )
    on_path = shutil.which("ydb")
    if on_path:
        return Check(
            name="ydb_binary",
            status=Status.OK,
            message=f"PATH → {on_path}",
        )
    return Check(
        name="ydb_binary",
        status=Status.WARN,
        message="no `ydb` binary found",
        hint=(
            "Install YottaDB or set $YDB to the binary path. "
            "`m test` and `m coverage` need a working ydb to run suites."
        ),
    )


_CHECKS: tuple[Callable[[], Check], ...] = (
    check_ydb_dist,
    check_ydb_routines,
    check_parser,
    check_keywords,
    check_ydb_binary,
)


def run_all_checks() -> list[Check]:
    """Run every registered check in order and return the results."""
    return [fn() for fn in _CHECKS]
