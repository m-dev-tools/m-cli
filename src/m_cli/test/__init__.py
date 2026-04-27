"""m test — the M (MUMPS) test runner.

Tier 1, Step 3 of the M ecosystem gap-remediation plan
(see docs/m-tooling-tier1.md in the m-tools repo).

`m test` discovers test suites under one or more paths and runs them
against a YottaDB interpreter. Suites are `.m` files whose stem ends in
``TST`` and whose test labels follow the convention ``t<UpperCase>(pass,fail)``.

Discovery is parser-aware (tree-sitter-m AST) — labels and their formal
parameters are read from the parsed tree, not via regex. The runner is
YottaDB-specific (unlike `m fmt` and `m lint` which are engine-neutral).

Reference convention: VistA / m-tools `routines/tests/<NAME>TST.m`,
exercising the assertion library at ``^TESTRUN`` (see m-tools).
"""

from m_cli.test.cli import test_command
from m_cli.test.discovery import TestCase, TestSuite, discover, find_test_cases
from m_cli.test.runner import Outcome, RunResult, run_case, run_suite

__all__ = [
    "test_command",
    "TestCase",
    "TestSuite",
    "discover",
    "find_test_cases",
    "Outcome",
    "RunResult",
    "run_case",
    "run_suite",
]
