"""Coverage result formatters: text (human), json (CI)."""

from __future__ import annotations

import json
import sys

from m_cli.coverage.runner import CoverageResult


def write_output(
    result: CoverageResult, *, fmt: str = "text", uncovered_only: bool = False
) -> None:
    if fmt == "json":
        _write_json(result)
    elif fmt == "text":
        _write_text(result, uncovered_only=uncovered_only)
    else:
        raise ValueError(f"unknown coverage output format: {fmt!r}")


def _write_json(result: CoverageResult) -> None:
    payload = {
        "total": result.total,
        "covered": result.covered,
        "percent": round(result.percent, 1),
        "returncode": result.returncode,
        "suites_run": result.suites_run,
        "by_routine": [
            {
                "routine": routine,
                "covered": cov,
                "total": total,
                "percent": round(100.0 * cov / total, 1) if total else 0.0,
            }
            for routine, (cov, total) in sorted(result.by_routine.items())
        ],
        "labels": [
            {
                "routine": lab.routine,
                "label": lab.label,
                "path": str(lab.path),
                "line": lab.line,
                "covered": lab.covered,
            }
            for lab in result.labels
        ],
    }
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")


def _write_text(result: CoverageResult, *, uncovered_only: bool) -> None:
    if uncovered_only:
        uncovered = [lab for lab in result.labels if not lab.covered]
        sys.stdout.write(
            f"Uncovered labels ({len(uncovered)} of {result.total}):\n"
        )
        for lab in sorted(uncovered, key=lambda x: (x.routine, x.label)):
            sys.stdout.write(f"  {lab.label}^{lab.routine}  ({lab.path}:{lab.line})\n")
        return

    # Per-routine table.
    sys.stdout.write(f"{'Routine':<20} {'Covered':>9} {'Total':>9} {'Percent':>9}\n")
    sys.stdout.write(f"{'-' * 20} {'-' * 9} {'-' * 9} {'-' * 9}\n")
    for routine, (cov, total) in sorted(result.by_routine.items()):
        pct = (100.0 * cov / total) if total else 0.0
        sys.stdout.write(f"{routine:<20} {cov:>9} {total:>9} {pct:>8.1f}%\n")
    sys.stdout.write(f"{'-' * 20} {'-' * 9} {'-' * 9} {'-' * 9}\n")
    sys.stdout.write(
        f"{'Total':<20} {result.covered:>9} {result.total:>9} {result.percent:>8.1f}%\n"
    )


__all__ = ["write_output"]
