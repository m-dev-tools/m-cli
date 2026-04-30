"""Tests for ``m_cli.lint.flow.transaction_state`` — path-sensitive
transaction nesting analyzer.

Forward MAY-analysis over the per-label CFG: at each block B, the
maximum transaction nesting depth on any path from entry to B.
Drives M-MOD-026 (TSTART leak across exit paths) — the path-
sensitive graduation of M-MOD-012.

Transfer functions:

  ``TSTART`` / ``TS``      →  depth + 1
  ``TCOMMIT`` / ``TC``     →  max(0, depth - 1)
  ``TROLLBACK`` / ``TRO``  →  max(0, depth - 1)  (decrement; argumented
                                                  rollback-to-level
                                                  is over-approximated
                                                  as a single decrement)

Meet (multiple predecessors): MAX. We want the worst-case depth on
any path — that's where leaks live.

Postconditional commands update depth only on the "fall" / "branch"
/ "exit" edge; the "skip" edge propagates IN unchanged.
"""

from __future__ import annotations

from m_cli.lint._index import NodeIndex
from m_cli.lint.flow.cfg import build_cfgs
from m_cli.lint.flow.transaction_state import (
    analyze_transactions,
    depth_at_exit,
)
from m_cli.parser import parse


def _analyze(src: bytes):
    tree = parse(src)
    index = NodeIndex(tree)
    cfgs = build_cfgs(src, index)
    return [analyze_transactions(cfg, src) for cfg in cfgs], cfgs


def test_no_transactions_zero_depth() -> None:
    src = b"LBL\n S X=1\n Q\n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    assert results[0][cfg.exit().id] == 0


def test_tstart_increments_depth() -> None:
    src = b"LBL\n TSTART\n Q\n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    assert results[0][cfg.exit().id] == 1


def test_tstart_then_tcommit_balances() -> None:
    src = b"LBL\n TSTART\n TCOMMIT\n Q\n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    assert results[0][cfg.exit().id] == 0


def test_tstart_then_trollback_balances() -> None:
    src = b"LBL\n TSTART\n TROLLBACK\n Q\n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    assert results[0][cfg.exit().id] == 0


def test_tcommit_at_zero_clamps() -> None:
    """``TCOMMIT`` when no transaction is open clamps at 0 — the
    analyzer doesn't go negative."""
    src = b"LBL\n TCOMMIT\n Q\n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    assert results[0][cfg.exit().id] == 0


def test_nested_tstart() -> None:
    src = b"LBL\n TSTART\n TSTART\n Q\n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    assert results[0][cfg.exit().id] == 2


def test_tstart_leak_on_one_path() -> None:
    """``TSTART`` then ``Q:cond`` (early exit) then ``TCOMMIT``.

    Path 1 (cond=true, early Q): depth = 1 at exit
    Path 2 (cond=false, fall through TCOMMIT): depth = 0 at exit
    Max meet at exit: 1 → leak.
    """
    src = b"LBL(C)\n TSTART\n Q:C=1\n TCOMMIT\n Q\n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    assert results[0][cfg.exit().id] == 1


def test_postconditional_tstart_does_not_increment_skip_path() -> None:
    """``TS:cond`` increments only on the "fall" (cond true) path."""
    src = b"LBL(C)\n TS:C=1\n Q\n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    # Max over all paths: 1 (cond=true)
    assert results[0][cfg.exit().id] == 1


def test_depth_at_exit_convenience() -> None:
    src = b"LBL\n TSTART\n TSTART\n TCOMMIT\n Q\n"
    _, cfgs = _analyze(src)
    cfg = cfgs[0]
    assert depth_at_exit(cfg, src) == 1


def test_complex_multi_branch_max_meet() -> None:
    """Multi-branch convergence — max-meet picks the worst path."""
    src = (
        b"LBL(C)\n"
        b" TSTART\n"
        b" Q:C=1\n"  # path 1 exits at depth 1
        b" TSTART\n"  # path 2 reaches depth 2
        b" TCOMMIT\n"
        b" Q\n"  # path 2 exits at depth 1
    )
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    # Both paths end at depth ≥ 1 — leak.
    assert results[0][cfg.exit().id] == 1
