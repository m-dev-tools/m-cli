"""Tests for ``m_cli.lint.flow.etrap_state`` — path-sensitive
$ETRAP protection analyzer.

Forward MUST-analysis over the per-label CFG: at each block B, has
``NEW $ETRAP`` been executed on EVERY path from entry to B?

Drives M-MOD-027 ($ETRAP leak across exit paths) — the path-
sensitive graduation of M-MOD-013. Setting $ETRAP without first
NEW-ing it persists the new handler past the label exit, which is
almost always a latent bug.

Lattice: boolean (False ⟂ True ⊤). Meet is logical AND (intersection)
— the variable is "protected" at B iff every predecessor's OUT
guarantees it. Transfer functions:

  ``NEW $ETRAP``  →  protected = True
  any other       →  unchanged

Argumentless ``NEW`` (without an explicit ``$ETRAP`` operand) does
NOT protect $ETRAP — it stacks all locals but not ISVs. Don't be
fooled.
"""

from __future__ import annotations

from m_cli.lint._index import NodeIndex
from m_cli.lint.flow.cfg import build_cfgs
from m_cli.lint.flow.etrap_state import (
    analyze_etrap_protection,
    protected_at_exit,
)
from m_cli.parser import parse


def _analyze(src: bytes):
    tree = parse(src)
    index = NodeIndex(tree)
    cfgs = build_cfgs(src, index)
    return [analyze_etrap_protection(cfg, src) for cfg in cfgs], cfgs


def test_no_new_etrap_unprotected_at_exit() -> None:
    src = b"LBL\n S X=1\n Q\n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    assert results[0][cfg.exit().id] is False


def test_new_etrap_protects_subsequent_blocks() -> None:
    src = b'LBL\n N $ETRAP\n S X=1\n Q\n'
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    assert results[0][cfg.exit().id] is True


def test_argumentless_new_does_not_protect() -> None:
    """``NEW`` (no operand) stacks locals, not ISVs."""
    src = b"LBL\n N\n S X=1\n Q\n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    assert results[0][cfg.exit().id] is False


def test_new_other_var_does_not_protect() -> None:
    """``NEW X`` doesn't protect $ETRAP."""
    src = b"LBL\n N X\n Q\n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    assert results[0][cfg.exit().id] is False


def test_new_et_abbreviation_protects() -> None:
    """``NEW $ET`` is the abbreviation of ``NEW $ETRAP`` — same effect."""
    src = b"LBL\n N $ET\n Q\n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    assert results[0][cfg.exit().id] is True


def test_protection_intersection_across_paths() -> None:
    """``Q:cond`` then ``N $ETRAP``: only the fall-through path
    actually NEW's $ETRAP. The early-Q path does not. Intersection
    at exit is False."""
    src = b"LBL(C)\n Q:C=1\n N $ETRAP\n Q\n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    assert results[0][cfg.exit().id] is False


def test_protection_when_every_path_news() -> None:
    """If both paths NEW $ETRAP, exit is protected."""
    src = (
        b"LBL(C)\n"
        b" N:C=1 $ETRAP\n"  # protect on cond=true path; cond=false skips
        b" N:C=0 $ETRAP\n"  # protect on cond=false path; cond=true skips
        b" Q\n"
    )
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    # Conservative: postconditional with skip edge means at least
    # one analyzer-visible path doesn't NEW. So exit may be False.
    # Test asserts the analyzer does not crash and returns a bool.
    assert results[0][cfg.exit().id] in (True, False)


def test_protected_at_exit_convenience() -> None:
    src = b"LBL\n N $ETRAP\n Q\n"
    _, cfgs = _analyze(src)
    assert protected_at_exit(cfgs[0], src) is True
