"""`m doctor` command — environment diagnostics.

Runs every registered check, prints a per-check line, and exits ``1``
if any check is FAIL (WARN does not fail the run).
"""

from __future__ import annotations

import argparse
import json

from m_cli.doctor.checks import Check, Status, run_all_checks


def doctor_command(args: argparse.Namespace) -> int:
    checks = run_all_checks()
    fmt = getattr(args, "format", "text")
    if fmt == "json":
        payload = [
            {
                "name": c.name,
                "status": c.status.value,
                "message": c.message,
                "hint": c.hint,
            }
            for c in checks
        ]
        print(json.dumps(payload, indent=2))
    else:
        _write_text(checks)
    return 1 if any(c.status is Status.FAIL for c in checks) else 0


def _write_text(checks: list[Check]) -> None:
    width = max((len(c.name) for c in checks), default=0)
    for c in checks:
        label = c.status.value.ljust(4)
        marker = {"OK": "✓", "WARN": "!", "FAIL": "x"}[c.status.value]
        print(f"  {marker} {label}  {c.name.ljust(width)}  {c.message}")
        if c.hint and c.status is not Status.OK:
            print(f"        hint: {c.hint}")
    fails = sum(1 for c in checks if c.status is Status.FAIL)
    warns = sum(1 for c in checks if c.status is Status.WARN)
    oks = sum(1 for c in checks if c.status is Status.OK)
    summary = f"\n{oks} OK, {warns} warning, {fails} fail"
    print(summary)
