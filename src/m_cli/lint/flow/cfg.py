"""Per-label control-flow graph construction.

Phase 7 step 1 — purely structural. Walks the AST of each top-level
label, emits one :class:`Block` per ``command`` node, and wires
successors per the M control-flow semantics encoded below. No
dataflow yet; downstream analyzers (reaching-definitions, lock-state)
read this graph in subsequent slices.

Edge kinds
----------

``"fall"``
    Fall-through: the previous command's continuation. Default for
    most commands. Also used by postconditional non-exit commands to
    represent the "command ran" path.

``"branch"``
    Postconditional took the *true* branch and the underlying
    command exited the label (``Q:cond`` → exit, ``G:cond`` → exit).

``"skip"``
    Postconditional took the *false* branch — command did NOT run.
    For exit commands (Q, G, H), the "skip" path falls through to the
    next sibling. For non-exit commands (e.g. ``S:cond X=1``), the
    "skip" edge points at the *same* sibling as the "fall" edge but is
    tagged distinctly so reaching-definitions can model "this SET may
    not have happened on this path".

``"if-skip"``
    ``IF cond`` evaluated false: skip the rest of this *line* and
    jump to the first command on the next line. (M's IF / ELSE are
    line-scoped, not block-scoped.)

``"exit"``
    ``QUIT``, ``HALT``, ``GOTO`` (over-approximated as exit in this
    slice; intra-routine GOTO target resolution is a Phase 7+ refinement),
    or any command whose only successor is the label exit.

Limitations (deliberate, this slice)
------------------------------------
* GOTO targets within the same routine are *not* resolved — every
  GOTO is treated as an exit edge. Adding intra-routine resolution
  is a follow-up; reaching-defs over-approximates safely with this.
* ``ELSE`` is currently treated as a normal command (no $TEST-aware
  branching). Reaching-defs will conservatively report "unknown" for
  variables defined under an IF without ELSE — acceptable for now.
* ``FOR`` loops are currently treated as straight-line (loop body
  always executes once). Adds a back-edge in a later slice.
* Dot-blocks (``DO`` indirection / nested ``.``) — body is included
  but the call/return edge is not modeled.
* Indirection (``@var``) is over-approximated as "any-target", which
  for the CFG means an exit edge.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from m_cli.lint._index import NodeIndex

_Node = Any

# Command keywords (uppercased; we accept the canonical and the
# common abbreviations) that unconditionally exit the current label.
# QUIT/Q is the obvious one. HALT/H exits the process — same effect
# from the CFG's perspective. GOTO/G is over-approximated as exit
# in this slice.
_EXIT_KEYWORDS = frozenset({"Q", "QUIT", "H", "HALT", "G", "GOTO"})
_QUIT_KEYWORDS = frozenset({"Q", "QUIT"})

# IF and its abbreviation. ``IF cond`` evaluated false skips the rest
# of the line.
_IF_KEYWORDS = frozenset({"I", "IF"})


@dataclass
class Block:
    """A node in the per-label CFG.

    ``kind`` distinguishes the synthetic ``"entry"`` and ``"exit"``
    blocks from ``"command"`` blocks (one per AST ``command`` node).

    ``successors`` and ``edge_kinds`` are parallel lists. A command
    with two successors (one ``"branch"``, one ``"skip"``) has both
    lists of length 2.
    """

    id: int
    kind: str  # "entry" | "command" | "exit"
    command: _Node | None = None
    successors: list[int] = field(default_factory=list)
    edge_kinds: list[str] = field(default_factory=list)
    line: int = 0  # 1-based; 0 for synthetic blocks without a clear anchor


@dataclass
class CFG:
    """Per-label control-flow graph.

    Block id 0 is always the entry; the last block is always the
    exit. Other blocks are command blocks, in source order.
    """

    label_name: str
    label_node: _Node
    blocks: list[Block]

    def block(self, bid: int) -> Block:
        return self.blocks[bid]

    def entry(self) -> Block:
        return self.blocks[0]

    def exit(self) -> Block:
        return self.blocks[-1]

    def reachable(self) -> set[int]:
        """Block ids reachable from the entry, via any edge kind."""
        seen: set[int] = set()
        stack = [self.entry().id]
        while stack:
            bid = stack.pop()
            if bid in seen:
                continue
            seen.add(bid)
            for s in self.blocks[bid].successors:
                if s not in seen:
                    stack.append(s)
        return seen


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def _label_body_extents(
    src: bytes, index: NodeIndex
) -> list[tuple[_Node, int, int]]:
    """``[(label_node, header_line_0idx, end_line_0idx_exclusive), ...]``.

    Re-implemented locally (rather than importing from ``_modern``)
    to avoid a circular import path. The semantics match
    ``_modern._label_body_extents`` exactly.
    """
    label_nodes = [
        n
        for n in index.of("label")
        if n.parent is not None and n.parent.type == "line"
    ]
    if not label_nodes:
        return []
    total_lines = src.count(b"\n") + (0 if src.endswith(b"\n") else 1)
    out: list[tuple[_Node, int, int]] = []
    for i, label in enumerate(label_nodes):
        header = label.start_point[0]
        end = label_nodes[i + 1].start_point[0] if i + 1 < len(label_nodes) else total_lines
        out.append((label, header, end))
    return out


def _command_keyword(cmd: _Node, src: bytes) -> str:
    """Uppercased keyword for a ``command`` node, or ``""`` if missing."""
    for c in cmd.children:
        if c.type == "command_keyword":
            return src[c.start_byte : c.end_byte].decode("latin-1", errors="replace").upper()
    return ""


def _has_postconditional(cmd: _Node) -> bool:
    return any(c.type == "postconditional" for c in cmd.children)


def _has_arguments(cmd: _Node) -> bool:
    """True if ``cmd`` has any non-empty argument_list."""
    for c in cmd.children:
        if c.type == "argument_list":
            return any(child.type == "argument" for child in c.children)
    return False


def _is_inside_dot_block(cmd: _Node) -> bool:
    """True if ``cmd``'s enclosing line carries a ``dot_block_prefix``.

    Argumentless QUIT inside a dot-block exits ONLY the dot-block,
    not the entire label — so the CFG must treat such a QUIT as
    fall-through to the next command, not as a label-exit edge.
    """
    seq = cmd.parent  # command_sequence
    if seq is None:
        return False
    line = seq.parent  # line
    if line is None:
        return False
    return any(c.type == "dot_block_prefix" for c in line.children)


def _build_one_cfg(
    src: bytes,
    index: NodeIndex,
    label_node: _Node,
    header_line: int,
    end_line: int,
) -> CFG:
    label_name = src[label_node.start_byte : label_node.end_byte].decode(
        "latin-1", errors="replace"
    )
    cmds = [
        cmd
        for cmd in index.of("command")
        if header_line < cmd.start_point[0] < end_line
    ]

    # Allocate blocks: entry, one per command, exit.
    blocks: list[Block] = [Block(id=0, kind="entry", line=header_line + 1)]
    for i, cmd in enumerate(cmds, start=1):
        blocks.append(
            Block(
                id=i,
                kind="command",
                command=cmd,
                line=cmd.start_point[0] + 1,
            )
        )
    exit_id = len(blocks)
    blocks.append(Block(id=exit_id, kind="exit"))

    # Wire entry → first command (or directly to exit if empty body).
    if cmds:
        blocks[0].successors = [1]
        blocks[0].edge_kinds = ["fall"]
    else:
        blocks[0].successors = [exit_id]
        blocks[0].edge_kinds = ["fall"]

    # For each command block, decide its successors.
    for i, cmd in enumerate(cmds, start=1):
        next_cmd_id = i + 1 if i + 1 < exit_id else exit_id
        kw = _command_keyword(cmd, src)
        is_exit_kw = kw in _EXIT_KEYWORDS
        is_if_kw = kw in _IF_KEYWORDS
        has_pc = _has_postconditional(cmd)

        if is_exit_kw:
            # Argumentless ``Q`` / ``QUIT`` inside a dot-block exits
            # only the dot-block, not the label — model as fall-
            # through to the next sibling rather than label-exit.
            # (Argumented Q in an extrinsic-call context can still
            # exit the routine; over-approximating as fall-through
            # is the safer default for definite-assignment than
            # killing every downstream IN set.)
            quit_in_dot_block = (
                kw in _QUIT_KEYWORDS
                and _is_inside_dot_block(cmd)
                and not _has_arguments(cmd)
            )
            if has_pc:
                if quit_in_dot_block:
                    # Postcond true → fall through (dot-block exit
                    # treated as continuation); false → also next.
                    blocks[i].successors = [next_cmd_id, next_cmd_id]
                    blocks[i].edge_kinds = ["fall", "skip"]
                else:
                    # Postconditional Q/G/H: branch to exit on true,
                    # skip to next on false.
                    blocks[i].successors = [exit_id, next_cmd_id]
                    blocks[i].edge_kinds = ["branch", "skip"]
            else:
                if quit_in_dot_block:
                    blocks[i].successors = [next_cmd_id]
                    blocks[i].edge_kinds = ["fall"]
                else:
                    blocks[i].successors = [exit_id]
                    blocks[i].edge_kinds = ["exit"]
            continue

        if is_if_kw and not has_pc:
            # IF skips the rest of the LINE on false.
            line_idx = cmd.start_point[0]
            skip_target = _first_command_on_line_after(cmds, line_idx)
            skip_id = skip_target if skip_target is not None else exit_id
            blocks[i].successors = [next_cmd_id, skip_id]
            blocks[i].edge_kinds = ["fall", "if-skip"]
            continue

        # Generic command: postconditional yields fall + skip (both
        # land on the same successor; reaching-defs differentiates).
        if has_pc:
            blocks[i].successors = [next_cmd_id, next_cmd_id]
            blocks[i].edge_kinds = ["fall", "skip"]
        else:
            blocks[i].successors = [next_cmd_id]
            blocks[i].edge_kinds = ["fall"]

    return CFG(label_name=label_name, label_node=label_node, blocks=blocks)


def _first_command_on_line_after(cmds: list[_Node], line: int) -> int | None:
    """Block id of the first command whose start line is > ``line``.

    The block id equals ``cmd_index + 1`` because block 0 is entry.
    Returns None if no such command exists.
    """
    for idx, c in enumerate(cmds, start=1):
        if c.start_point[0] > line:
            return idx
    return None


def build_cfgs(src: bytes, index: NodeIndex) -> list[CFG]:
    """One CFG per top-level label."""
    return [
        _build_one_cfg(src, index, lbl, header, end)
        for lbl, header, end in _label_body_extents(src, index)
    ]


# Convenience: iterate every command-bearing block (skips entry/exit).
def command_blocks(cfg: CFG) -> Iterator[Block]:
    for b in cfg.blocks:
        if b.kind == "command":
            yield b
