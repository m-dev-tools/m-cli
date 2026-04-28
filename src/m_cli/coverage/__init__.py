"""`m coverage` — label-level coverage of M test suites.

First-slice scope: label coverage via YottaDB ZBREAK instrumentation.
For each non-suite label we emit a ZBREAK that writes ``^ycov(routine,
label)=1`` on entry; running every selected suite under the
instrumented direct-mode session populates ``^ycov`` with the labels
the tests actually exercised. We then diff against the discovered
label set to compute per-routine and overall coverage.

Line-level coverage via source instrumentation is a deliberate
follow-up. The ZBREAK approach mirrors the technique in m-tools'
``bin/ycover`` shell script and gives a useful first signal without
requiring a parser-rewrite pipeline.
"""

from m_cli.coverage.cli import coverage_command
from m_cli.coverage.runner import (
    CoverageResult,
    LabelCoverage,
    LineCoverage,
    run_coverage,
)

__all__ = [
    "coverage_command",
    "run_coverage",
    "CoverageResult",
    "LabelCoverage",
    "LineCoverage",
]
