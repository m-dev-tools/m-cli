"""Tests for ``m_cli.lint.flow.dollar_test`` — path-sensitive
``$TEST`` freshness analyzer.

Forward MUST-analysis over the per-label CFG: at each block B, has
a ``$TEST``-affecting command (IF, OPEN, LOCK, READ, JOB — i.e.
the commands that *write* ``$TEST``) executed on EVERY path from
entry to B?

Drives M-MOD-017 ($TEST staleness): reading ``$TEST`` without a
preceding setter on every path means the read could return a value
left over from a much earlier command — almost certainly not what
the programmer intended.

Lattice: boolean (``False`` ⟂, ``True`` ⊤). Meet is logical AND.
The pattern matches :mod:`m_cli.lint.flow.etrap_state`.

Setters in this slice:

  ``IF`` / ``I``           always sets $TEST
  ``OPEN`` / ``O``         may set $TEST (timeout form)
  ``LOCK`` / ``L``         may set $TEST (timeout form)
  ``READ`` / ``R``         may set $TEST (timeout form)
  ``JOB`` / ``J``          may set $TEST (timeout form)

Conservative: treat all of these as setters regardless of whether
they actually carry a timeout. Reduces false positives at the cost
of missing some cases where a programmer used the bare form.
``ELSE`` *reads* ``$TEST`` and does not reset it; not a setter.
"""

from __future__ import annotations

from m_cli.lint._index import NodeIndex
from m_cli.lint.flow.cfg import build_cfgs
from m_cli.lint.flow.dollar_test import (
    analyze_test_freshness,
    fresh_at_exit,
)
from m_cli.parser import parse


def _analyze(src: bytes):
    tree = parse(src)
    index = NodeIndex(tree)
    cfgs = build_cfgs(src, index)
    return [analyze_test_freshness(cfg, src) for cfg in cfgs], cfgs


def test_no_setter_stale_at_exit() -> None:
    src = b"LBL\n S X=1\n Q\n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    assert results[0][cfg.exit().id] is False


def test_if_command_makes_test_fresh() -> None:
    src = b"LBL\n I X=1\n Q\n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    assert results[0][cfg.exit().id] is True


def test_open_command_makes_test_fresh() -> None:
    src = b'LBL\n O "f":(readonly):5\n Q\n'
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    assert results[0][cfg.exit().id] is True


def test_lock_command_makes_test_fresh() -> None:
    src = b"LBL\n L +X:5\n Q\n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    assert results[0][cfg.exit().id] is True


def test_setter_intersection_across_paths() -> None:
    """``Q:cond`` early-exit then ``I X=1``: the early path has no
    setter. Intersection: False."""
    src = b"LBL(C)\n Q:C=1\n I X=1\n Q\n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    assert results[0][cfg.exit().id] is False


def test_setter_on_every_path() -> None:
    """``I X=1`` then ``Q:cond`` then ``I X=2`` then ``Q``.

    Every path passes through the first IF before reaching exit, so
    $TEST is fresh."""
    src = b"LBL(C)\n I X=1\n Q:C=1\n I Y=2\n Q\n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    assert results[0][cfg.exit().id] is True


def test_else_does_not_reset() -> None:
    """ELSE reads $TEST but does not write it — not a setter."""
    src = b'LBL\n E  W "no"\n Q\n'
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    # ELSE alone does not make $T fresh.
    assert results[0][cfg.exit().id] is False


def test_fresh_at_exit_convenience() -> None:
    src = b"LBL\n I X=1\n Q\n"
    _, cfgs = _analyze(src)
    assert fresh_at_exit(cfgs[0], src) is True
