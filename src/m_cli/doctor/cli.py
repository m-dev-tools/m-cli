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

``--fix`` (Phase 2.4) delegates to ``m engine <verb>`` for every WARN
whose Fix carries ``engine_verb``. Non-engine fixes (e.g. ``sudo
systemctl start docker``) are never auto-run; ``--fix`` prints a
``manual:`` line instead, keeping the security surface bounded to the
engine driver's owned operations.
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

    if getattr(args, "fix", False):
        apply_fixes(checks, confirm=getattr(args, "confirm", False))
        # Re-check post-fix so the exit code reflects new state.
        checks = run_all_checks()
        if fmt != "json":
            print("\nafter --fix:")
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
                "engine_verb": c.fix.engine_verb,
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


# ── --fix surface ────────────────────────────────────────────────────


def apply_fixes(checks: list[Check], *, confirm: bool) -> int:
    """Walk WARN/FAIL checks and apply each whose Fix has ``engine_verb``.

    Returns the number of fixes that were actually invoked (non-zero
    when at least one ran). Non-engine fixes print a ``manual:`` hint
    so the user knows what to run by hand. Destructive engine verbs
    refuse to run without ``confirm=True``.
    """
    invoked = 0
    for c in checks:
        if c.status not in (Status.WARN, Status.FAIL):
            continue
        if c.fix is None:
            continue
        if _apply_one_fix(c, confirm=confirm):
            invoked += 1
    return invoked


def _apply_one_fix(check: Check, *, confirm: bool) -> bool:
    """Apply a single check's fix. Returns True iff the driver was called."""
    if check.fix is None:
        return False
    fix = check.fix

    if fix.engine_verb is None:
        # Outside the engine namespace — never auto-run. Print the
        # fix.command as a manual recipe and move on.
        print(
            f"  manual: {check.name}: run `{shlex.join(fix.command)}` to fix"
        )
        return False

    if fix.destructive and not confirm:
        print(
            f"  skipping {check.name}: destructive engine verb "
            f"`{fix.engine_verb}` requires --confirm"
        )
        return False

    # Resolve the engine driver lazily so test injection via
    # set_driver_factory takes effect.
    from m_cli.engine_cli import select_driver

    driver = select_driver()
    method = getattr(driver, fix.engine_verb, None)
    if method is None:
        print(
            f"  skipping {check.name}: driver has no verb "
            f"`{fix.engine_verb}` (driver={driver.name})"
        )
        return False

    print(f"  fixing {check.name}: m engine {fix.engine_verb}")
    if fix.engine_verb == "reset":
        rc = method(confirm=confirm)
    else:
        rc = method()
    if rc != 0:
        print(f"  warn: m engine {fix.engine_verb} returned rc={rc}")
    return True
