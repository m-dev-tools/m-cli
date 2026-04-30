"""Tests for ``m_cli.lint.flow.taint`` — taint-analysis MVP.

Phase 9 first slice: forward MAY analysis tracking which local
variables hold *untrusted* values that originated from a source
(READ from terminal, formal parameters of a public label, etc.).
Drives :rule:`M-MOD-036` (untrusted data flows into an indirection
sink), the differentiating security feature of this lint suite.

Lattice element: ``frozenset[str]`` of tainted variable names.
Meet: union (``∪``). A var is tainted at B iff it's tainted on at
least one path from entry to B — that's the conservative "may be
attacker-controlled" reading we want for security.

Transfer functions (this MVP):

  READ X            →  tainted ∪= {X}             (source)
  SET X=<expr>      →  if any var in <expr> ∈ tainted: tainted ∪= {X}
                       else: tainted -= {X}        (strong update)
  KILL X / NEW X    →  tainted -= {X}              (untaint by removal)
  argumentless K/N  →  tainted = ∅                 (kill all locals)
  $LENGTH(X)        →  result is clean             (sanitizer)
  $ASCII(X)         →  result is clean             (sanitizer)
  any other         →  tainted unchanged

Formal parameters of a label are tainted at entry by default
(``formals_tainted=True`` in TaintConfig) — public labels are
attack surface.
"""

from __future__ import annotations

from m_cli.lint._index import NodeIndex
from m_cli.lint.flow.cfg import build_cfgs
from m_cli.lint.flow.taint import TaintConfig, analyze_taint
from m_cli.parser import parse


def _analyze(src: bytes, *, config: TaintConfig | None = None):
    tree = parse(src)
    index = NodeIndex(tree)
    cfgs = build_cfgs(src, index)
    cfg = cfgs[0]
    return analyze_taint(cfg, src, config=config or TaintConfig()), cfg


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


def test_no_sources_no_taint() -> None:
    src = b"LBL\n S X=1\n S Y=2\n Q\n"
    taint, cfg = _analyze(src)
    assert taint[cfg.exit().id] == frozenset()


def test_read_taints_target() -> None:
    src = b"LBL\n R X\n Q\n"
    taint, cfg = _analyze(src)
    assert "X" in taint[cfg.exit().id]


def test_formal_parameters_tainted_at_entry() -> None:
    """Public-label formals are attack surface — tainted by default."""
    src = b"LBL(A,B)\n W A,B\n Q\n"
    taint, cfg = _analyze(src)
    # At entry, A and B should be tainted.
    assert "A" in taint[cfg.entry().id]
    assert "B" in taint[cfg.entry().id]


def test_formals_can_be_disabled() -> None:
    """``formals_tainted=False`` opts out of the formals-as-source model."""
    src = b"LBL(A,B)\n W A,B\n Q\n"
    taint, cfg = _analyze(src, config=TaintConfig(formals_tainted=False))
    assert "A" not in taint[cfg.entry().id]
    assert "B" not in taint[cfg.entry().id]


# ---------------------------------------------------------------------------
# Propagation
# ---------------------------------------------------------------------------


def test_set_propagates_taint_through_assignment() -> None:
    """``READ X; SET Y=X`` — taint flows from X into Y."""
    src = b"LBL\n R X\n S Y=X\n Q\n"
    taint, cfg = _analyze(src)
    assert "X" in taint[cfg.exit().id]
    assert "Y" in taint[cfg.exit().id]


def test_set_propagates_taint_through_concatenation() -> None:
    """``READ X; SET Y="prefix"_X`` — concatenation propagates."""
    src = b"LBL\n R X\n S Y=\"prefix\"_X\n Q\n"
    taint, cfg = _analyze(src)
    assert "Y" in taint[cfg.exit().id]


def test_set_clean_rhs_clears_lhs() -> None:
    """``READ X; SET X=42`` — strong update removes X from tainted set."""
    src = b"LBL\n R X\n S X=42\n Q\n"
    taint, cfg = _analyze(src)
    assert "X" not in taint[cfg.exit().id]


def test_set_clean_rhs_does_not_taint_new_var() -> None:
    """``READ X; SET Y=42`` — Y stays clean even though X is tainted."""
    src = b"LBL\n R X\n S Y=42\n Q\n"
    taint, cfg = _analyze(src)
    assert "X" in taint[cfg.exit().id]
    assert "Y" not in taint[cfg.exit().id]


# ---------------------------------------------------------------------------
# Sanitizers
# ---------------------------------------------------------------------------


def test_dollar_length_sanitizes() -> None:
    """``$L(X)`` returns a number — output is clean regardless of X's taint."""
    src = b"LBL\n R X\n S Y=$L(X)\n Q\n"
    taint, cfg = _analyze(src)
    assert "X" in taint[cfg.exit().id]  # source still tainted
    assert "Y" not in taint[cfg.exit().id]  # sanitized result


def test_dollar_length_canonical_name() -> None:
    src = b"LBL\n R X\n S Y=$LENGTH(X)\n Q\n"
    taint, cfg = _analyze(src)
    assert "Y" not in taint[cfg.exit().id]


def test_dollar_ascii_sanitizes() -> None:
    src = b"LBL\n R X\n S Y=$A(X)\n Q\n"
    taint, cfg = _analyze(src)
    assert "Y" not in taint[cfg.exit().id]


def test_sanitizer_inside_concatenation() -> None:
    """``S Y=$L(X)_Z`` where X is tainted but Z is clean — Y is clean."""
    src = b"LBL\n R X\n S Z=42\n S Y=$L(X)_Z\n Q\n"
    taint, cfg = _analyze(src)
    assert "Y" not in taint[cfg.exit().id]


def test_sanitizer_does_not_block_taint_from_other_subtree() -> None:
    """``S Y=$L(X)_Z`` where Z is *also* tainted — Y becomes tainted."""
    src = b"LBL\n R X\n R Z\n S Y=$L(X)_Z\n Q\n"
    taint, cfg = _analyze(src)
    assert "Y" in taint[cfg.exit().id]


# ---------------------------------------------------------------------------
# Untainting
# ---------------------------------------------------------------------------


def test_kill_removes_taint() -> None:
    src = b"LBL\n R X\n K X\n Q\n"
    taint, cfg = _analyze(src)
    assert "X" not in taint[cfg.exit().id]


def test_argumentless_kill_clears_all_taint() -> None:
    src = b"LBL\n R X\n R Y\n K \n Q\n"
    taint, cfg = _analyze(src)
    assert taint[cfg.exit().id] == frozenset()


def test_new_removes_taint() -> None:
    """``NEW X`` un-defines X for the current frame; current taint is gone."""
    src = b"LBL\n R X\n N X\n Q\n"
    taint, cfg = _analyze(src)
    assert "X" not in taint[cfg.exit().id]


# ---------------------------------------------------------------------------
# Path sensitivity (UNION meet)
# ---------------------------------------------------------------------------


def test_taint_on_one_path_propagates_to_join() -> None:
    """If READ runs on one path and not the other, the join is
    tainted (MAY analysis — over-approximate to catch real bugs)."""
    src = b"LBL(C)\n R:C=1 X\n Q\n"
    taint, cfg = _analyze(src)
    assert "X" in taint[cfg.exit().id]


# ---------------------------------------------------------------------------
# Subscripts inside LHS — no taint introduced from the LHS structure
# ---------------------------------------------------------------------------


def test_subscript_uses_in_lhs_propagate() -> None:
    """``S A(X)=42`` where X is tainted — A is tainted (subscript path)."""
    src = b"LBL\n R X\n S A(X)=42\n Q\n"
    taint, cfg = _analyze(src)
    # Conservative: tainted subscript means A's "shape" is attacker-
    # controlled, so A is tainted.
    assert "A" in taint[cfg.exit().id]


# ---------------------------------------------------------------------------
# By-reference DO/JOB calls — callee may write tainted data
# ---------------------------------------------------------------------------


def test_by_ref_call_taints_arg() -> None:
    """``D LBL(.X)`` — the callee may write any value (including
    untrusted) into X. MAY-analysis taints X conservatively."""
    src = b"LBL\n D F(.X)\n Q\n"
    taint, cfg = _analyze(src)
    assert "X" in taint[cfg.exit().id]


def test_by_ref_call_taints_multiple() -> None:
    src = b"LBL\n D F(.X,.Y,Z)\n Q\n"
    taint, cfg = _analyze(src)
    assert "X" in taint[cfg.exit().id]
    assert "Y" in taint[cfg.exit().id]
    # Z is by-value — untouched (and Z's prior state is "clean" since
    # nothing has set it).
    assert "Z" not in taint[cfg.exit().id]


def test_by_ref_call_through_extrinsic_taints_arg() -> None:
    """``S R=$$F(.X)`` — extrinsic call may write to X (and the result
    R is also tainted because $$F may return user-influenced value).
    The MVP's strong-update SET handling already taints R when X is in
    the post-call tainted set; this test pins the by-ref leg."""
    src = b"LBL\n S R=$$F(.X)\n Q\n"
    taint, cfg = _analyze(src)
    assert "X" in taint[cfg.exit().id]


def test_by_value_call_does_not_taint() -> None:
    """``D F(X)`` where X is clean stays clean (no by-ref writes)."""
    src = b"LBL\n S X=1\n D F(X)\n Q\n"
    taint, cfg = _analyze(src)
    assert "X" not in taint[cfg.exit().id]


def test_by_ref_call_does_not_untaint() -> None:
    """If X is already tainted, ``D F(.X)`` keeps it tainted (the
    callee MIGHT clean it, but we conservatively assume it might
    not — MAY analysis)."""
    src = b"LBL\n R X\n D F(.X)\n Q\n"
    taint, cfg = _analyze(src)
    assert "X" in taint[cfg.exit().id]
