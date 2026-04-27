"""Microbenchmark for `m lint` over a sample of VistA routines.

Run: ``.venv/bin/python scripts/lint_bench.py [N]``

Times a fresh lint pass over a deterministic sample of N routines from the
Kernel package (default 200). Reports total wall time and per-file mean.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from m_cli.lint.runner import lint_source, select_rules
from m_cli.parser import parse

ROOT = Path("/home/rafael/vista-meta/vista/vista-m-host/Packages/Kernel/Routines")


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    files = sorted(ROOT.rglob("*.m"))[:n]
    rules = select_rules("xindex")
    print(f"benchmark: {len(files)} files, {len(rules)} rules")

    # Skip files with parse errors so we measure rule-walk time, not parsing.
    src_paths = []
    for p in files:
        src = p.read_bytes()
        if not parse(src).root_node.has_error:
            src_paths.append((p, src))
    print(f"  {len(src_paths)} parseable")

    t0 = time.perf_counter()
    total_diags = 0
    for path, src in src_paths:
        diags = lint_source(path, src, rules)
        total_diags += len(diags)
    elapsed = time.perf_counter() - t0

    per_file_ms = (elapsed / len(src_paths)) * 1000.0
    print(
        f"\nTotal: {elapsed:.2f}s  "
        f"({per_file_ms:.2f} ms/file)  "
        f"{total_diags} findings"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
