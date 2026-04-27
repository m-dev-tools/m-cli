"""Output formatters for `m test`: text, TAP, and JSON."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable

from m_cli.test.runner import Outcome, RunResult


def write_output(results: Iterable[RunResult], fmt: str) -> None:
    results = list(results)
    if fmt == "tap":
        _write_tap(results)
    elif fmt == "json":
        _write_json(results)
    else:
        _write_text(results)


def _write_text(results: list[RunResult]) -> None:
    for r in results:
        header = r.suite if r.label is None else f"{r.suite}::{r.label}"
        status = "ok" if r.ok else "FAIL"
        print(f"{status}  {header}  ({r.summary.passed}/{r.summary.total} passed)")
        if not r.ok:
            for a in r.summary.assertions:
                if a.outcome == Outcome.FAIL:
                    print(f"    - {a.description}")
                    if a.expected is not None:
                        print(f"        expected: {a.expected}")
                    if a.actual is not None:
                        print(f"        actual:   {a.actual}")


def _write_tap(results: list[RunResult]) -> None:
    print("TAP version 13")
    # Flatten across suites: each parsed assertion is one TAP point.
    n = sum(len(r.summary.assertions) for r in results)
    if n == 0:
        # Fall back to per-suite points if we can't introspect assertions.
        n = len(results)
        print(f"1..{n}")
        for i, r in enumerate(results, start=1):
            header = r.suite if r.label is None else f"{r.suite}::{r.label}"
            ok = "ok" if r.ok else "not ok"
            print(f"{ok} {i} - {header}")
        return
    print(f"1..{n}")
    i = 0
    for r in results:
        suite_label = r.suite if r.label is None else f"{r.suite}::{r.label}"
        for a in r.summary.assertions:
            i += 1
            ok = "ok" if a.outcome == Outcome.PASS else "not ok"
            print(f"{ok} {i} - {suite_label}: {a.description}")
            if a.outcome == Outcome.FAIL:
                print("  ---")
                if a.expected is not None:
                    print(f"  expected: {a.expected}")
                if a.actual is not None:
                    print(f"  actual:   {a.actual}")
                print("  ...")


def _write_json(results: list[RunResult]) -> None:
    payload = {
        "ok": all(r.ok for r in results),
        "suites": [
            {
                "name": r.suite,
                "label": r.label,
                "ok": r.ok,
                "passed": r.summary.passed,
                "failed": r.summary.failed,
                "total": r.summary.total,
                "returncode": r.returncode,
                "assertions": [
                    {
                        "outcome": a.outcome.value,
                        "description": a.description,
                        "expected": a.expected,
                        "actual": a.actual,
                    }
                    for a in r.summary.assertions
                ],
            }
            for r in results
        ],
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
