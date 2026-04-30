"""Tests for ``m_cli.lint.flow.reaching`` — definite-assignment analyzer.

Phase 7 step 2B: forward MUST-analysis over the per-label CFG.
"Definite assignment" means: at every block B, which local variables
are *guaranteed* to have been DEF'd on every path from entry to B?
This is the foundation for M-MOD-024 (read of local before any SET on
every prior path).

Lattice: ``definitely_defined`` is a set; meet operator is intersection.
The analyzer is monotone (sets shrink toward the fixed point); the
worklist algorithm terminates in finite time over finite block sets.

API:

    analyze(cfg, src, *, formals=()) -> dict[block_id, frozenset[str]]

The returned dict maps each block id to the set of local-variable
names that are DEFINITELY defined upon *entering* that block. Use
"is X in result[block_id]?" to answer "is X definitely defined when
this block runs?".
"""

from __future__ import annotations

from m_cli.lint._index import NodeIndex
from m_cli.lint.flow.cfg import build_cfgs
from m_cli.lint.flow.reaching import analyze
from m_cli.parser import parse


def _analyze(src: bytes, *, formals: tuple[str, ...] = ()):
    tree = parse(src)
    index = NodeIndex(tree)
    cfgs = build_cfgs(src, index)
    return [analyze(cfg, src, formals=formals) for cfg in cfgs], cfgs


def _kw(cfg, bid, src) -> str:
    b = cfg.block(bid)
    if b.kind != "command":
        return b.kind.upper()
    for c in b.command.children:
        if c.type == "command_keyword":
            return src[c.start_byte : c.end_byte].decode("latin-1").upper()
    return "?"


# ---------------------------------------------------------------------------
# Empty / trivial cases
# ---------------------------------------------------------------------------


def test_no_defs_no_uses() -> None:
    """Empty body — entry connects directly to exit; both have empty IN."""
    src = b"LBL\n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    r = results[0]
    assert r[cfg.entry().id] == frozenset()
    assert r[cfg.exit().id] == frozenset()


def test_single_set_propagates_to_exit() -> None:
    src = b"LBL\n S X=1\n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    r = results[0]
    # Entry: nothing defined yet.
    assert r[cfg.entry().id] == frozenset()
    # First (and only) command is `S X=1` — IN is empty.
    set_block = cfg.block(cfg.entry().successors[0])
    assert r[set_block.id] == frozenset()
    # Exit: X is defined.
    assert r[cfg.exit().id] == frozenset({"X"})


# ---------------------------------------------------------------------------
# Sequential commands
# ---------------------------------------------------------------------------


def test_two_sets_accumulate() -> None:
    src = b"LBL\n S X=1\n S Y=2\n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    r = results[0]
    # Find the two SET blocks in source order.
    sets = [b for b in cfg.blocks if b.kind == "command"]
    assert len(sets) == 2
    # Before first SET: nothing.
    assert r[sets[0].id] == frozenset()
    # Before second SET: X is defined.
    assert r[sets[1].id] == frozenset({"X"})
    # At exit: both.
    assert r[cfg.exit().id] == frozenset({"X", "Y"})


# ---------------------------------------------------------------------------
# Postconditional SET — definite-assignment view
# ---------------------------------------------------------------------------


def test_postconditional_set_does_not_definitely_define() -> None:
    """``S:cond X=1`` may not run — so X is NOT definitely defined
    after this command."""
    src = b"LBL\n S:Y=1 X=1\n Q\n"
    results, cfgs = _analyze(src, formals=("Y",))
    cfg = cfgs[0]
    r = results[0]
    # At exit, X must NOT be in the definitely-defined set, because
    # the SET is gated on a postconditional.
    assert "X" not in r[cfg.exit().id]
    # Y was a formal, so it stays defined throughout.
    assert "Y" in r[cfg.exit().id]


def test_unconditional_set_after_postconditional_set_still_defines() -> None:
    """The SECOND, unconditional SET re-defines X regardless of
    whether the first ran."""
    src = b"LBL\n S:Y=1 X=1\n S X=2\n"
    results, cfgs = _analyze(src, formals=("Y",))
    cfg = cfgs[0]
    r = results[0]
    assert "X" in r[cfg.exit().id]


# ---------------------------------------------------------------------------
# QUIT — flow exits the function
# ---------------------------------------------------------------------------


def test_quit_terminates_the_path() -> None:
    src = b"LBL\n S X=1\n Q\n S Y=2\n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    r = results[0]
    # The S Y=2 block is unreachable from entry; analyzer must still
    # produce *some* answer for it (we conservatively use the empty
    # set as the initial value for unreachable blocks).
    # Exit: X is defined; Y is not (only path is via Q).
    assert "X" in r[cfg.exit().id]
    assert "Y" not in r[cfg.exit().id]


# ---------------------------------------------------------------------------
# Postconditional QUIT — branching paths
# ---------------------------------------------------------------------------


def test_quit_postconditional_intersects_paths() -> None:
    """``S X=1 ; Q:cond ; S Y=2`` — at exit, X is on all paths but
    Y only on the fall-through path (which still reaches exit). So
    the intersection at exit is {X}: X is on the Q-branch path AND
    on the fall-through path; Y is only on the fall-through."""
    src = b"LBL\n S X=1\n Q:Z=1\n S Y=2\n"
    results, cfgs = _analyze(src, formals=("Z",))
    cfg = cfgs[0]
    r = results[0]
    out = r[cfg.exit().id]
    assert "X" in out
    assert "Y" not in out  # only set on one of the two paths
    assert "Z" in out  # formal — defined throughout


# ---------------------------------------------------------------------------
# KILL / NEW
# ---------------------------------------------------------------------------


def test_kill_removes_from_definite() -> None:
    """``S X=1 ; K X`` — X is defined after SET, killed by KILL,
    so undefined at exit."""
    src = b"LBL\n S X=1\n K X\n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    r = results[0]
    assert "X" not in r[cfg.exit().id]


def test_new_removes_from_definite() -> None:
    """``S X=1 ; N X`` — NEW un-defines for the current frame."""
    src = b"LBL\n S X=1\n N X\n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    r = results[0]
    assert "X" not in r[cfg.exit().id]


def test_argumentless_kill_clears_all() -> None:
    """``S X=1 ; S Y=2 ; K`` — argumentless KILL removes everything."""
    src = b"LBL\n S X=1\n S Y=2\n K \n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    r = results[0]
    assert r[cfg.exit().id] == frozenset()


# ---------------------------------------------------------------------------
# Formal parameters — defined at entry
# ---------------------------------------------------------------------------


def test_formals_definitely_defined_at_entry() -> None:
    src = b"LBL(A,B)\n S X=A+B\n"
    results, cfgs = _analyze(src, formals=("A", "B"))
    cfg = cfgs[0]
    r = results[0]
    # At entry: A and B are defined.
    assert r[cfg.entry().id] == frozenset({"A", "B"})
    # At exit: all three.
    assert r[cfg.exit().id] == frozenset({"A", "B", "X"})


# ---------------------------------------------------------------------------
# IF — line-scoped postconditional
# ---------------------------------------------------------------------------


def test_if_skip_does_not_definitely_define() -> None:
    """``I cond  S X=1`` — if cond is false, the rest of the line is
    skipped; so X is NOT definitely defined on every path."""
    src = b"LBL\n I Y=1 S X=1\n Q\n"
    results, cfgs = _analyze(src, formals=("Y",))
    cfg = cfgs[0]
    r = results[0]
    assert "X" not in r[cfg.exit().id]


# ---------------------------------------------------------------------------
# Reachability vs analyzer correctness
# ---------------------------------------------------------------------------


def test_unreachable_block_does_not_pollute_exit() -> None:
    """Code after a Q is unreachable, but the analyzer must still
    assign a value to its IN set (typically empty / "top"). Crucially,
    its OUT must NOT propagate to exit because there's no edge."""
    src = b"LBL\n S X=1\n Q\n S Z=99\n"
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    r = results[0]
    # Exit's IN comes only from Q's exit edge → {X}. Z must not be
    # there because the S Z=99 block has no successor edge to exit.
    assert "Z" not in r[cfg.exit().id]
    assert "X" in r[cfg.exit().id]


# ---------------------------------------------------------------------------
# Convergence — analyzer must terminate
# ---------------------------------------------------------------------------


def test_analyzer_terminates_on_complex_label() -> None:
    """Heavier input with multiple branches and KILLs — the analyzer
    must converge in finite steps. (The fact that this returns at
    all is the test; assertions are sanity checks on the result.)"""
    src = (
        b"LBL\n"
        b" S A=1\n"
        b" S:A=1 B=2\n"
        b" Q:A=2\n"
        b" K A\n"
        b" S C=3\n"
        b" Q\n"
    )
    results, cfgs = _analyze(src)
    cfg = cfgs[0]
    r = results[0]
    # C is set on the path that doesn't take Q:A=2.
    # B is conditional. A is killed.
    out = r[cfg.exit().id]
    # On the Q:A=2 branch, A is still defined (we exited before the K).
    # On the fall-through, A is killed; C is defined.
    # Intersection: neither A nor B nor C is on every path. Empty.
    assert "A" not in out
    assert "B" not in out
    assert "C" not in out
