"""Output formatters for `m test`: text, TAP, JSON, and JUnit XML."""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterable

from m_cli.test.runner import Outcome, RunResult


def write_output(results: Iterable[RunResult], fmt: str) -> None:
    results = list(results)
    if fmt == "tap":
        _write_tap(results)
    elif fmt == "json":
        _write_json(results)
    elif fmt == "junit":
        _write_junit(results)
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


def _write_junit(results: list[RunResult]) -> None:
    """Emit Jenkins-style JUnit XML.

    Granularity mirrors TAP: one ``<testcase>`` per parsed assertion. If
    a suite emitted no assertion lines, fall back to a single
    ``<testcase>`` named after the suite so totals are non-zero.
    """
    root = ET.Element("testsuites", {"name": "m test"})
    total_tests = 0
    total_failures = 0
    for r in results:
        suite_el = ET.SubElement(root, "testsuite")
        suite_label = r.suite if r.label is None else f"{r.suite}::{r.label}"
        suite_tests = 0
        suite_failures = 0
        if r.summary.assertions:
            for a in r.summary.assertions:
                case_el = ET.SubElement(
                    suite_el,
                    "testcase",
                    {"classname": r.suite, "name": a.description},
                )
                suite_tests += 1
                if a.outcome != Outcome.PASS:
                    suite_failures += 1
                    body_lines = []
                    if a.expected is not None:
                        body_lines.append(f"expected: {a.expected}")
                    if a.actual is not None:
                        body_lines.append(f"actual:   {a.actual}")
                    failure_el = ET.SubElement(
                        case_el,
                        "failure",
                        {"message": "assertion failed"},
                    )
                    failure_el.text = "\n".join(body_lines) or "assertion failed"
        else:
            case_el = ET.SubElement(
                suite_el,
                "testcase",
                {"classname": r.suite, "name": suite_label},
            )
            suite_tests = 1
            if not r.ok:
                suite_failures = 1
                ET.SubElement(
                    case_el,
                    "failure",
                    {"message": "suite failed"},
                ).text = r.stdout or "suite failed with no output"
        suite_el.set("name", r.suite)
        suite_el.set("tests", str(suite_tests))
        suite_el.set("failures", str(suite_failures))
        suite_el.set("errors", "0")
        suite_el.set("time", "0")
        total_tests += suite_tests
        total_failures += suite_failures
    root.set("tests", str(total_tests))
    root.set("failures", str(total_failures))
    root.set("errors", "0")
    root.set("time", "0")
    ET.indent(root, space="  ")
    sys.stdout.write('<?xml version="1.0" encoding="utf-8"?>\n')
    sys.stdout.write(ET.tostring(root, encoding="unicode"))
    sys.stdout.write("\n")


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
