"""Tests for ``m_cli.lint.flow.cfg`` — per-label control-flow graph.

Phase 7 first slice: build a structural CFG over each top-level label.
No dataflow yet — these tests pin the shape (nodes, edges, edge kinds)
so that downstream analyzers (reaching-definitions, lock-state) can
consume a stable graph.

CFG semantics encoded by these tests:

  * One ``Block`` per AST ``command`` node, plus synthetic ``entry``
    (label header) and ``exit`` (sink for QUIT and end-of-label).
  * Edge kinds:
      ``"fall"``    — fall-through to the next command (default)
      ``"branch"``  — postconditional took the true path (e.g. Q:cond → exit)
      ``"skip"``    — postconditional false path (command did NOT run)
      ``"if-skip"`` — IF cond false; skip rest of line
  * QUIT / end-of-label / GOTO out of routine → exit edge.
  * GOTO to a same-label internal label is over-approximated as exit
    in this slice (intra-routine label resolution is a Phase 7+ refinement).
"""

from __future__ import annotations

from m_cli.lint._index import NodeIndex
from m_cli.lint.flow.cfg import CFG, Block, build_cfgs
from m_cli.parser import parse


def _build(src: bytes) -> list[CFG]:
    tree = parse(src)
    index = NodeIndex(tree)
    return build_cfgs(src, index)


def _kw(block: Block, src: bytes) -> str:
    """Return the uppercased command keyword for a command block, or
    'ENTRY' / 'EXIT' for the synthetic blocks. Convenience for test
    assertions that read the graph by command name."""
    if block.kind == "entry":
        return "ENTRY"
    if block.kind == "exit":
        return "EXIT"
    cmd = block.command
    for c in cmd.children:
        if c.type == "command_keyword":
            return src[c.start_byte : c.end_byte].decode("latin-1").upper()
    return "?"


# ---------------------------------------------------------------------------
# Basic shape — one CFG per top-level label
# ---------------------------------------------------------------------------


def test_one_cfg_per_top_level_label() -> None:
    src = b"LBL1\n SET X=1\nLBL2\n SET Y=2\n"
    cfgs = _build(src)
    assert [c.label_name for c in cfgs] == ["LBL1", "LBL2"]


def test_no_labels_no_cfgs() -> None:
    cfgs = _build(b"")
    assert cfgs == []


def test_label_with_empty_body() -> None:
    """Bare label header followed immediately by another label — the
    body is empty so entry connects directly to exit."""
    src = b"LBL\nNXT\n QUIT\n"
    cfgs = _build(src)
    assert len(cfgs) == 2
    cfg = cfgs[0]
    entry = cfg.entry()
    exit_ = cfg.exit()
    assert entry.successors == [exit_.id]
    assert entry.edge_kinds == ["fall"]


def test_label_body_falls_off_end_to_exit() -> None:
    """Last command in a label that doesn't QUIT still exits the label
    (implicit QUIT at end-of-routine semantics)."""
    src = b"LBL\n SET X=1\n SET Y=2\n"
    cfgs = _build(src)
    cfg = cfgs[0]
    # entry → SET X → SET Y → exit
    blocks_in_order = [_kw(b, src) for b in cfg.blocks]
    assert blocks_in_order == ["ENTRY", "SET", "SET", "EXIT"]
    last_set = cfg.blocks[2]
    assert last_set.successors == [cfg.exit().id]
    assert last_set.edge_kinds == ["fall"]


# ---------------------------------------------------------------------------
# Fall-through
# ---------------------------------------------------------------------------


def test_two_commands_chain_falls_through() -> None:
    src = b"LBL\n SET X=1\n SET Y=2\n QUIT\n"
    cfg = _build(src)[0]
    entry = cfg.entry()
    s1 = cfg.block(entry.successors[0])
    s2 = cfg.block(s1.successors[0])
    q = cfg.block(s2.successors[0])
    assert _kw(s1, src) == "SET"
    assert _kw(s2, src) == "SET"
    assert _kw(q, src) == "QUIT"
    assert s1.edge_kinds == ["fall"]
    assert s2.edge_kinds == ["fall"]


def test_multiple_commands_on_one_line_chain_in_order() -> None:
    """`S X=1 S Y=2 Q` on one line: each command is a separate node."""
    src = b"LBL\n S X=1 S Y=2 Q\n"
    cfg = _build(src)[0]
    cmds = [_kw(b, src) for b in cfg.blocks if b.kind == "command"]
    assert cmds == ["S", "S", "Q"]


# ---------------------------------------------------------------------------
# QUIT
# ---------------------------------------------------------------------------


def test_unconditional_quit_goes_to_exit() -> None:
    src = b"LBL\n QUIT\n SET X=1\n"
    cfg = _build(src)[0]
    entry = cfg.entry()
    q = cfg.block(entry.successors[0])
    assert _kw(q, src) == "QUIT"
    assert q.successors == [cfg.exit().id]
    assert q.edge_kinds == ["exit"]


def test_quit_abbrev_recognized() -> None:
    """`Q` (the abbreviation) terminates just like `QUIT`."""
    src = b"LBL\n Q\n SET X=1\n"
    cfg = _build(src)[0]
    q = cfg.block(cfg.entry().successors[0])
    assert _kw(q, src) == "Q"
    assert q.successors == [cfg.exit().id]
    assert q.edge_kinds == ["exit"]


def test_postconditional_quit_branches() -> None:
    """`Q:X=1` → exit if true, fall-through if false (skip path)."""
    src = b"LBL\n Q:X=1\n SET Y=2\n"
    cfg = _build(src)[0]
    pc_q = cfg.block(cfg.entry().successors[0])
    assert _kw(pc_q, src) == "Q"
    # Two successors: one to exit (cond true), one falls through (skip).
    assert len(pc_q.successors) == 2
    targets = sorted(zip(pc_q.successors, pc_q.edge_kinds))
    kinds = sorted(pc_q.edge_kinds)
    assert kinds == ["branch", "skip"]
    # The branch successor must be exit; the skip successor must be SET.
    branch_target = pc_q.successors[pc_q.edge_kinds.index("branch")]
    skip_target = pc_q.successors[pc_q.edge_kinds.index("skip")]
    assert branch_target == cfg.exit().id
    assert _kw(cfg.block(skip_target), src) == "SET"
    _ = targets  # silence


# ---------------------------------------------------------------------------
# Postconditional non-exit commands
# ---------------------------------------------------------------------------


def test_postconditional_set_records_skip_edge() -> None:
    """`S:X=1 Y=2` then `Q` — the SET may not run, so reaching defs
    must see both "Y was set" and "Y not set" paths. The CFG records
    this with a "skip" edge that bypasses the SET.

    Concretely: pc-SET has TWO successors — both pointing at the next
    block (Q), but one tagged "fall" (cond true, command ran) and one
    tagged "skip" (cond false, command did NOT run). Reaching-defs
    treats them differently.
    """
    src = b"LBL\n S:X=1 Y=2\n Q\n"
    cfg = _build(src)[0]
    pc_s = cfg.block(cfg.entry().successors[0])
    assert _kw(pc_s, src) == "S"
    assert sorted(pc_s.edge_kinds) == ["fall", "skip"]
    # Both successors should be the same Q block.
    targets = set(pc_s.successors)
    assert len(targets) == 1
    only = next(iter(targets))
    assert _kw(cfg.block(only), src) == "Q"


# ---------------------------------------------------------------------------
# IF / ELSE — line-scoped postconditional semantics
# ---------------------------------------------------------------------------


def test_if_creates_skip_edge_to_next_line() -> None:
    """`I X=1 W "yes"` on a line followed by `S Y=2`:

        - If X=1: I runs, then W runs, then fall to S Y=2.
        - If X=0: I skips the rest of the line, jump to S Y=2.

    The CFG models this with IF having two successors:
      "fall" → next command on same line (W)
      "if-skip" → next-line first command (S)
    """
    src = b'LBL\n I X=1 W "yes"\n S Y=2\n'
    cfg = _build(src)[0]
    if_block = cfg.block(cfg.entry().successors[0])
    assert _kw(if_block, src) == "I"
    kinds = sorted(if_block.edge_kinds)
    assert kinds == ["fall", "if-skip"]
    fall_idx = if_block.edge_kinds.index("fall")
    skip_idx = if_block.edge_kinds.index("if-skip")
    assert _kw(cfg.block(if_block.successors[fall_idx]), src) == "W"
    assert _kw(cfg.block(if_block.successors[skip_idx]), src) == "S"


# ---------------------------------------------------------------------------
# Reachability helper
# ---------------------------------------------------------------------------


def test_reachable_from_entry() -> None:
    """``CFG.reachable()`` returns the set of blocks reachable from entry.

    `Q` followed by `S X=1` — the SET is unreachable from entry.
    """
    src = b"LBL\n Q\n S X=1\n"
    cfg = _build(src)[0]
    reachable = cfg.reachable()
    keywords = sorted({_kw(cfg.block(bid), src) for bid in reachable})
    assert keywords == ["ENTRY", "EXIT", "Q"]


def test_all_paths_from_entry_to_exit() -> None:
    """Every reachable command must have a path to exit (no infinite
    loops in the structural CFG yet — FOR not modeled)."""
    src = b"LBL\n S X=1\n Q:X=2\n S Y=3\n Q\n"
    cfg = _build(src)[0]
    # Every reachable command should reach exit.
    for bid in cfg.reachable():
        b = cfg.block(bid)
        if b.kind == "exit":
            continue
        # BFS to exit
        seen = {bid}
        queue = [bid]
        found_exit = False
        while queue:
            cur = queue.pop()
            if cur == cfg.exit().id:
                found_exit = True
                break
            for s in cfg.block(cur).successors:
                if s not in seen:
                    seen.add(s)
                    queue.append(s)
        assert found_exit, f"block {bid} ({_kw(b, src)}) cannot reach exit"
