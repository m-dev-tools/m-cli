"""Path-sensitive $ETRAP protection analyzer (Phase 7 step 3C).

Forward MUST-analysis over the per-label CFG: at each block B, has
``NEW $ETRAP`` been executed on EVERY path from entry to B?

Drives :rule:`M-MOD-027` ($ETRAP leak across exit paths) — the
path-sensitive graduation of M-MOD-013. Setting ``$ETRAP`` without
first ``NEW``-ing it persists the new handler past the label exit
into whatever caller stacked, which is almost always a bug.

Lattice element is a boolean (``False`` ⟂, ``True`` ⊤). Meet is
logical AND (intersection) — protected at B iff *every* predecessor
guarantees it. Transfer functions:

  ``NEW $ETRAP`` / ``NEW $ET``  →  protected = True
  any other                     →  unchanged

Note: argumentless ``NEW`` stacks all locals but does NOT protect
ISVs like $ETRAP. ``NEW X`` protects only X. Only an explicit
``NEW $ETRAP`` (or ``NEW $ET``) qualifies.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from m_cli.lint.flow.cfg import CFG

_Node = Any

_ETRAP_NAMES = frozenset({"$ETRAP", "$ET"})
_NEW_KW = frozenset({"N", "NEW"})


def _command_keyword(cmd: _Node, src: bytes) -> str:
    for c in cmd.children:
        if c.type == "command_keyword":
            return src[c.start_byte : c.end_byte].decode(
                "latin-1", errors="replace"
            ).upper()
    return ""


def _argument_nodes(cmd: _Node) -> list[_Node]:
    for c in cmd.children:
        if c.type == "argument_list":
            return [a for a in c.children if a.type == "argument"]
    return []


def _arg_special_var_name(arg: _Node, src: bytes) -> str:
    """Uppercased ``$ETRAP`` / ``$ET`` etc. when ``arg`` directly
    references a special variable; ``""`` otherwise."""
    for c in arg.children:
        if c.type == "special_variable":
            return src[c.start_byte : c.end_byte].decode(
                "latin-1", errors="replace"
            ).upper()
    return ""


def _is_new_etrap(cmd: _Node, src: bytes) -> bool:
    """True if ``cmd`` is ``NEW $ETRAP`` (or ``NEW $ET``)."""
    if _command_keyword(cmd, src) not in _NEW_KW:
        return False
    for arg in _argument_nodes(cmd):
        if _arg_special_var_name(arg, src) in _ETRAP_NAMES:
            return True
    return False


def _apply_command(in_protected: bool, cmd: _Node, src: bytes) -> bool:
    if _is_new_etrap(cmd, src):
        return True
    return in_protected


def _out_for_edge(
    in_protected: bool, cmd: _Node | None, edge_kind: str, src: bytes
) -> bool:
    if cmd is None or edge_kind in ("skip", "if-skip"):
        return in_protected
    return _apply_command(in_protected, cmd, src)


def analyze_etrap_protection(cfg: CFG, src: bytes) -> dict[int, bool]:
    """Return ``{block_id: protected_at_entry}`` — True iff NEW $ETRAP
    has executed on every path from entry to the block.

    Initial state: entry is False (no protection at function start).
    Other blocks start at True (lattice top, identity for AND meet)
    and are refined downward as predecessors propagate.
    """
    preds: dict[int, list[tuple[int, str]]] = {b.id: [] for b in cfg.blocks}
    for b in cfg.blocks:
        for succ, kind in zip(b.successors, b.edge_kinds):
            preds[succ].append((b.id, kind))

    in_state: dict[int, bool] = {b.id: True for b in cfg.blocks}
    in_state[cfg.entry().id] = False
    computed: set[int] = {cfg.entry().id}

    work: deque[int] = deque(cfg.entry().successors)
    iterations = 0
    cap = max(64, len(cfg.blocks) * 8) * 4

    while work:
        iterations += 1
        if iterations > cap:
            break
        bid = work.popleft()
        if bid == cfg.entry().id:
            continue

        # Intersect over predecessors that have been computed.
        results: list[bool] = []
        for pbid, kind in preds[bid]:
            if pbid not in computed:
                continue
            pcmd = cfg.block(pbid).command if cfg.block(pbid).kind == "command" else None
            results.append(_out_for_edge(in_state[pbid], pcmd, kind, src))
        if not results:
            continue
        new_state = all(results)

        if bid in computed and new_state == in_state[bid]:
            continue
        in_state[bid] = new_state
        computed.add(bid)
        for succ in cfg.block(bid).successors:
            if succ not in work:
                work.append(succ)

    # Unreachable blocks default to False (no protection assumed).
    for b in cfg.blocks:
        if b.id not in computed:
            in_state[b.id] = False

    return in_state


def protected_at_exit(cfg: CFG, src: bytes) -> bool:
    return analyze_etrap_protection(cfg, src)[cfg.exit().id]
