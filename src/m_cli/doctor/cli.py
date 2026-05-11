"""`m doctor` command — environment diagnostics.

Runs every registered check, prints a per-check line, and exits ``1``
if any check is FAIL (WARN/SKIPPED do not fail the run).

Output formats:

* ``text`` (default) — human-readable, one line per check; failing
  checks render ``hint:`` and ``fix:`` lines below.
* ``json`` — structured payload. Each entry includes ``name``,
  ``status``, ``message``, ``hint`` and (when the check provides one)
  ``fix.command`` + ``fix.destructive``. Agents walk failure → fix
  edges programmatically without re-parsing prose.
"""

from __future__ import annotations

import argparse
import json
import shlex

from m_cli.doctor.checks import Check, Status, run_all_checks

_MARKERS = {
    Status.OK: "✓",
    Status.WARN: "!",
    Status.FAIL: "x",
    Status.SKIPPED: "-",
}


def doctor_command(args: argparse.Namespace) -> int:
    checks = run_all_checks()
    fmt = getattr(args, "format", "text")
    if fmt == "json":
        print(json.dumps(_to_json(checks), indent=2))
    else:
        _write_text(checks)
    return 1 if any(c.status is Status.FAIL for c in checks) else 0


def _to_json(checks: list[Check]) -> list[dict]:
    out: list[dict] = []
    for c in checks:
        entry: dict = {
            "name": c.name,
            "status": c.status.value,
            "message": c.message,
            "hint": c.hint,
        }
        if c.fix is not None:
            entry["fix"] = {
                "command": list(c.fix.command),
                "destructive": c.fix.destructive,
            }
        else:
            entry["fix"] = None
        if c.prerequisites:
            entry["prerequisites"] = list(c.prerequisites)
        out.append(entry)
    return out


def _write_text(checks: list[Check]) -> None:
    width = max((len(c.name) for c in checks), default=0)
    for c in checks:
        label = c.status.value.ljust(7)
        marker = _MARKERS[c.status]
        print(f"  {marker} {label} {c.name.ljust(width)}  {c.message}")
        if c.status is Status.OK or c.status is Status.SKIPPED:
            continue
        if c.hint:
            print(f"        hint: {c.hint}")
        if c.fix is not None:
            print(f"        fix:  {shlex.join(c.fix.command)}")
    fails = sum(1 for c in checks if c.status is Status.FAIL)
    warns = sum(1 for c in checks if c.status is Status.WARN)
    oks = sum(1 for c in checks if c.status is Status.OK)
    skipped = sum(1 for c in checks if c.status is Status.SKIPPED)
    print(f"\n{oks} OK, {warns} warning, {fails} fail, {skipped} skipped")
