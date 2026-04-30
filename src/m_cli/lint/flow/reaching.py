"""Definite-assignment analyzer (Phase 7 step 2B).

Forward MUST-analysis over the per-label CFG. At each block B,
computes the set of local variable names that are GUARANTEED to
have been DEF'd on every path from entry to B.

Differs from classical reaching-definitions in two ways:

  1. The lattice element is a *set of variable names*, not a set
     of definition sites. We don't need to identify *which* SET
     defines X; only whether X is definitely defined.
  2. The meet operator is *intersection*, not union. A variable
     is definitely defined at B iff it is defined on every path
     reaching B.

The analyzer drives M-MOD-024 (read of local before any SET on every
prior path). The lattice is finite (≤ |universe of variable names
in the label|), the transfer functions are monotone, so the worklist
algorithm terminates.

Edge-kind handling
------------------
The CFG tags each successor edge with a kind. The analyzer interprets
them as follows:

  ``"fall"`` / ``"branch"`` / ``"exit"``
      Command *ran*. Predecessor's OUT applies the command's effects:
      ``(IN - kills) ∪ defs`` (or ``∅`` if ``kills_all``).

  ``"skip"`` / ``"if-skip"``
      Command did *not* run. Predecessor's OUT is just its IN
      (effects bypassed). For postconditional commands, this models
      the false branch; for IF, it models the line-skip.
"""

from __future__ import annotations

from collections import deque

from m_cli.lint.flow.cfg import CFG
from m_cli.lint.flow.vars import Effects, effects


def _out_set(
    in_set: frozenset[str], eff: Effects | None, edge_kind: str
) -> frozenset[str]:
    """OUT set for one outgoing edge from a block with the given IN set
    and command effects."""
    if eff is None or edge_kind in ("skip", "if-skip"):
        return in_set
    if eff.kills_all:
        return frozenset()
    return (in_set - eff.kills) | eff.defs


def analyze(
    cfg: CFG, src: bytes, *, formals: tuple[str, ...] = ()
) -> dict[int, frozenset[str]]:
    """Return ``{block_id: definitely_defined_at_entry}``.

    ``formals`` is the tuple of formal-parameter names declared on
    the label header (use ``flow.vars.formal_params`` to obtain).
    Formals are definitely defined at the entry block.

    Unreachable blocks are reported with the empty set.
    """
    effs: dict[int, Effects | None] = {}
    for b in cfg.blocks:
        if b.kind == "command":
            effs[b.id] = effects(b.command, src)
        else:
            effs[b.id] = None

    # Predecessor table: for each block, the (predecessor_id, edge_kind)
    # pairs leading into it.
    preds: dict[int, list[tuple[int, str]]] = {b.id: [] for b in cfg.blocks}
    for b in cfg.blocks:
        for succ, kind in zip(b.successors, b.edge_kinds):
            preds[succ].append((b.id, kind))

    in_sets: dict[int, frozenset[str]] = {}
    computed: set[int] = set()

    entry_id = cfg.entry().id
    in_sets[entry_id] = frozenset(formals)
    computed.add(entry_id)

    work: deque[int] = deque(b.id for b in cfg.blocks if b.id != entry_id)
    # Always re-process entry's successors first.
    for succ in cfg.entry().successors:
        if succ in work:
            work.remove(succ)
            work.appendleft(succ)

    iterations = 0
    max_iterations = max(64, len(cfg.blocks) * 8)

    while work:
        iterations += 1
        if iterations > max_iterations * 4:
            # Safety net — this should never trigger in practice
            # because the lattice is finite and the transfer functions
            # are monotone, but if a future graph extension breaks the
            # invariant we want a clean abort, not an infinite loop.
            break

        bid = work.popleft()

        pred_outs: list[frozenset[str]] = []
        for pbid, kind in preds[bid]:
            if pbid not in computed:
                continue
            pred_outs.append(_out_set(in_sets[pbid], effs[pbid], kind))

        if not pred_outs:
            # No predecessor has produced a value yet. Defer.
            continue

        new_in = pred_outs[0]
        for s in pred_outs[1:]:
            new_in = new_in & s

        prev = in_sets.get(bid)
        if bid in computed and prev == new_in:
            continue

        in_sets[bid] = new_in
        computed.add(bid)
        for succ in cfg.block(bid).successors:
            if succ not in work:
                work.append(succ)

    for b in cfg.blocks:
        if b.id not in in_sets:
            in_sets[b.id] = frozenset()

    return in_sets


def out_set_for_block(
    cfg: CFG, src: bytes, in_sets: dict[int, frozenset[str]], block_id: int
) -> frozenset[str]:
    """OUT set of a block, applying its command's effects to its IN set.

    For postconditional commands this returns the "command ran" OUT;
    callers that want the "skip" view should consult the IN of the
    skip-edge successor instead.
    """
    b = cfg.block(block_id)
    if b.kind != "command":
        return in_sets[block_id]
    eff = effects(b.command, src)
    return _out_set(in_sets[block_id], eff, "fall")
