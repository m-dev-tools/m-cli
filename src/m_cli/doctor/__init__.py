"""m doctor — environment diagnostics.

Reports the health of the M development environment so a newcomer can
tell at a glance whether their shell is configured correctly. Each
check returns a :class:`Check` with status ``ok`` / ``warn`` / ``fail``,
a one-line message, and an optional hint for fixing failures.

Exit codes mirror the convention used by ``cargo --check`` and friends:
``0`` if no FAIL is recorded (WARN does not fail the run), ``1``
otherwise.
"""

from m_cli.doctor.checks import (
    Check,
    Status,
    check_keywords,
    check_parser,
    check_ydb_binary,
    check_ydb_dist,
    check_ydb_routines,
    run_all_checks,
)
from m_cli.doctor.cli import doctor_command

__all__ = [
    "Check",
    "Status",
    "check_keywords",
    "check_parser",
    "check_ydb_binary",
    "check_ydb_dist",
    "check_ydb_routines",
    "run_all_checks",
    "doctor_command",
]
