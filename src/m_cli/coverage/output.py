"""Coverage result formatters: text (human), json (CI), lcov (tool-friendly)."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from m_cli.coverage.runner import CoverageResult, LineCoverage


def write_output(
    result: CoverageResult,
    *,
    fmt: str = "text",
    uncovered_only: bool = False,
    show_lines: bool = False,
    show_branches: bool = False,
) -> None:
    if fmt == "json":
        _write_json(result, show_branches=show_branches)
    elif fmt == "lcov":
        _write_lcov(result, show_branches=show_branches)
    elif fmt == "text":
        _write_text(
            result,
            uncovered_only=uncovered_only,
            show_lines=show_lines,
            show_branches=show_branches,
        )
    else:
        raise ValueError(f"unknown coverage output format: {fmt!r}")


def _write_json(result: CoverageResult, *, show_branches: bool = False) -> None:
    payload = {
        "total": result.total,
        "covered": result.covered,
        "percent": round(result.percent, 1),
        "total_lines": result.total_lines,
        "covered_lines": result.covered_lines,
        "line_percent": round(result.line_percent, 1),
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
        "lines": [
            {
                "routine": ln.routine,
                "label": ln.label,
                "path": str(ln.path),
                "line": ln.line,
                "hit_count": ln.hit_count,
            }
            for ln in result.lines
        ],
    }
    if show_branches and result.branches is not None:
        payload["total_branches"] = result.total_branches
        payload["reached_branches"] = result.reached_branches
        payload["branch_percent"] = round(result.branch_percent, 1)
        payload["branches"] = [
            {
                "routine": bc.point.routine,
                "label": bc.point.label,
                "path": str(bc.point.path),
                "line": bc.point.line,
                "column": bc.point.column,
                "kind": bc.point.kind,
                "reached": bc.reached,
            }
            for bc in result.branches
        ]
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")


def _write_lcov(result: CoverageResult, *, show_branches: bool = False) -> None:
    """Emit LCOV tracefile records.

    One ``SF:..`` block per source file, with a ``DA:line,count`` per
    executable line, ``LF:`` / ``LH:`` totals, and — when branch data
    was collected — one ``BRDA:line,block,branch,taken`` per branch
    point plus ``BRF:`` / ``BRH:`` totals. We use a single block id
    (0) and a per-line counter for ``branch`` since M's same-line
    gating doesn't expose multiple LLVM-style basic-block boundaries.
    """
    by_path: dict[Path, list[LineCoverage]] = defaultdict(list)
    for line in result.lines:
        by_path[line.path].append(line)
    branches_by_path: dict[Path, list] = defaultdict(list)
    if show_branches and result.branches is not None:
        for bc in result.branches:
            branches_by_path[bc.point.path].append(bc)
    out = sys.stdout
    out.write("TN:\n")
    for path in sorted(by_path):
        out.write(f"SF:{path}\n")
        lines = sorted(by_path[path], key=lambda lc: lc.line)
        hit_count = 0
        for lc in lines:
            out.write(f"DA:{lc.line},{lc.hit_count}\n")
            if lc.hit_count > 0:
                hit_count += 1
        if show_branches:
            file_branches = sorted(
                branches_by_path.get(path, []),
                key=lambda bc: (bc.point.line, bc.point.column),
            )
            per_line_counter: dict[int, int] = {}
            br_hit = 0
            for bc in file_branches:
                idx = per_line_counter.get(bc.point.line, 0)
                per_line_counter[bc.point.line] = idx + 1
                taken = "1" if bc.reached else "-"
                out.write(f"BRDA:{bc.point.line},0,{idx},{taken}\n")
                if bc.reached:
                    br_hit += 1
            out.write(f"BRF:{len(file_branches)}\n")
            out.write(f"BRH:{br_hit}\n")
        out.write(f"LF:{len(lines)}\n")
        out.write(f"LH:{hit_count}\n")
        out.write("end_of_record\n")


def _write_text(
    result: CoverageResult,
    *,
    uncovered_only: bool,
    show_lines: bool,
    show_branches: bool = False,
) -> None:
    if uncovered_only:
        uncovered_labels = [lab for lab in result.labels if not lab.covered]
        sys.stdout.write(
            f"Uncovered labels ({len(uncovered_labels)} of {result.total}):\n"
        )
        for lab in sorted(uncovered_labels, key=lambda x: (x.routine, x.label)):
            sys.stdout.write(f"  {lab.label}^{lab.routine}  ({lab.path}:{lab.line})\n")
        if show_lines:
            uncovered_lines = [ln for ln in result.lines if ln.hit_count == 0]
            sys.stdout.write(
                f"\nUncovered lines ({len(uncovered_lines)} of {result.total_lines}):\n"
            )
            for ln in sorted(uncovered_lines, key=lambda x: (x.routine, x.line)):
                sys.stdout.write(f"  {ln.path}:{ln.line}  ({ln.label}^{ln.routine})\n")
        return

    # Per-routine table.
    if show_lines:
        sys.stdout.write(
            f"{'Routine':<20} {'Labels':>15} {'Lines':>15}\n"
        )
        sys.stdout.write(f"{'-' * 20} {'-' * 15} {'-' * 15}\n")
        line_by_routine = _line_totals_by_routine(result)
        for routine, (cov, total) in sorted(result.by_routine.items()):
            label_pct = (100.0 * cov / total) if total else 0.0
            line_cov, line_total = line_by_routine.get(routine, (0, 0))
            line_pct = (100.0 * line_cov / line_total) if line_total else 0.0
            sys.stdout.write(
                f"{routine:<20} "
                f"{f'{cov}/{total} ({label_pct:.0f}%)':>15} "
                f"{f'{line_cov}/{line_total} ({line_pct:.0f}%)':>15}\n"
            )
        sys.stdout.write(f"{'-' * 20} {'-' * 15} {'-' * 15}\n")
        sys.stdout.write(
            f"{'Total':<20} "
            f"{f'{result.covered}/{result.total} ({result.percent:.1f}%)':>15} "
            f"{f'{result.covered_lines}/{result.total_lines} ({result.line_percent:.1f}%)':>15}\n"
        )
        return

    # Default: label-only table.
    sys.stdout.write(f"{'Routine':<20} {'Covered':>9} {'Total':>9} {'Percent':>9}\n")
    sys.stdout.write(f"{'-' * 20} {'-' * 9} {'-' * 9} {'-' * 9}\n")
    for routine, (cov, total) in sorted(result.by_routine.items()):
        pct = (100.0 * cov / total) if total else 0.0
        sys.stdout.write(f"{routine:<20} {cov:>9} {total:>9} {pct:>8.1f}%\n")
    sys.stdout.write(f"{'-' * 20} {'-' * 9} {'-' * 9} {'-' * 9}\n")
    sys.stdout.write(
        f"{'Total':<20} {result.covered:>9} {result.total:>9} {result.percent:>8.1f}%\n"
    )
    if show_branches and result.branches is not None:
        sys.stdout.write(
            f"\nBranches: {result.reached_branches}/{result.total_branches} "
            f"reached ({result.branch_percent:.1f}%)\n"
        )


def _line_totals_by_routine(result: CoverageResult) -> dict[str, tuple[int, int]]:
    """Aggregate hit / total line counts per routine for the --lines table."""
    out: dict[str, tuple[int, int]] = {}
    for ln in result.lines:
        cov, total = out.get(ln.routine, (0, 0))
        out[ln.routine] = (cov + (1 if ln.hit_count > 0 else 0), total + 1)
    return out


__all__ = ["write_output"]
