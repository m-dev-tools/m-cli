"""Path-sensitive ``$TEST`` freshness analyzer (Phase 7 step 3D).

Forward MUST-analysis over the per-label CFG: at each block B, has
a ``$TEST``-affecting command run on EVERY path from entry to B?

Drives :rule:`M-MOD-017` ($TEST staleness). Reading ``$TEST`` without
a preceding setter on every path means the read returns a value
left over from a much earlier command (potentially before the
current label was entered) — almost certainly not what the
programmer intended.

Setters
-------
``IF`` always writes $TEST; the timeout-bearing forms of ``OPEN``,
``LOCK``, ``READ``, and ``JOB`` write it on timeout. We treat all
of these as setters regardless of whether they carry a timeout —
the conservative reading reduces false positives.

``ELSE`` and ``FOR`` *read* $TEST but do not write it; not setters.

Lattice element is a boolean; meet is logical AND. Same shape as
:mod:`m_cli.lint.flow.etrap_state`.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from m_cli.lint.flow.cfg import CFG

_Node = Any

# Conservative setter set — all commands that *can* write $TEST.
# Includes the canonical and abbreviated keyword forms.
_SETTERS = frozenset(
    {
        "I", "IF",
        "O", "OPEN",
        "L", "LOCK",
        "R", "READ",
        "J", "JOB",
    }
)


def _command_keyword(cmd: _Node, src: bytes) -> str:
    for c in cmd.children:
        if c.type == "command_keyword":
            return src[c.start_byte : c.end_byte].decode(
                "latin-1", errors="replace"
            ).upper()
    return ""


def _is_setter(cmd: _Node, src: bytes) -> bool:
    return _command_keyword(cmd, src) in _SETTERS


def _apply_command(in_fresh: bool, cmd: _Node, src: bytes) -> bool:
    if _is_setter(cmd, src):
        return True
    return in_fresh


def _out_for_edge(
    in_fresh: bool, cmd: _Node | None, edge_kind: str, src: bytes
) -> bool:
    """Edge-kind semantics for $TEST analysis.

    The ``if-skip`` edge from an IF means the IF *itself* ran
    (setting $TEST as part of evaluating its condition) but the
    rest of the line was skipped. So the setter effect applies on
    if-skip just like on fall — the only edge where the command
    didn't run is ``skip`` (postconditional false)."""
    if cmd is None or edge_kind == "skip":
        return in_fresh
    return _apply_command(in_fresh, cmd, src)


def analyze_test_freshness(cfg: CFG, src: bytes) -> dict[int, bool]:
    """Return ``{block_id: fresh_at_entry}`` — True iff some
    ``$TEST``-setter has executed on every path from entry to the
    block.

    Initial state at entry is False. Other blocks initialize to True
    (the AND-meet identity); predecessors propagate downward as
    they're computed.
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

    for b in cfg.blocks:
        if b.id not in computed:
            in_state[b.id] = False

    return in_state


def fresh_at_exit(cfg: CFG, src: bytes) -> bool:
    return analyze_test_freshness(cfg, src)[cfg.exit().id]
