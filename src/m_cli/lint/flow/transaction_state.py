"""Path-sensitive transaction nesting analyzer (Phase 7 step 3B).

Forward MAY-analysis over the per-label CFG: at each block B, the
maximum transaction nesting depth on any path from entry to B.
Drives :rule:`M-MOD-026` (TSTART leak across exit paths) — the
path-sensitive graduation of M-MOD-012's intra-label balance check.

Lattice element is a non-negative integer; meet is ``max`` (we want
worst-case depth — that's where leaks live). Transfer functions:

  ``TSTART`` / ``TS``      →  depth + 1
  ``TCOMMIT`` / ``TC``     →  max(0, depth - 1)
  ``TROLLBACK`` / ``TRO``  →  max(0, depth - 1)

Argumented ``TROLLBACK n`` (rollback to level *n*) is over-
approximated as a single decrement — full level-tracking would need
symbolic state. The conservative reading flags slightly more cases
than strictly necessary; for v1 this trades precision for simplicity.

Termination
-----------
The lattice has no a-priori finite ceiling, but in practice TSTARTs
in any one label are bounded by a small constant (≤ 5 in real M
code). The analyzer caps depth at a configurable ``MAX_DEPTH`` to
guarantee monotonicity and finite convergence; depths beyond the
cap saturate.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from m_cli.lint.flow.cfg import CFG

_Node = Any

_TSTART_KW = frozenset({"TS", "TSTART"})
_TCOMMIT_KW = frozenset({"TC", "TCOMMIT"})
_TROLLBACK_KW = frozenset({"TRO", "TROLLBACK"})

# Saturation cap. Any real-world M label has < 5 nested TSTARTs;
# the cap exists so the lattice has a finite top, guaranteeing
# convergence even on pathological inputs.
MAX_DEPTH = 32


def _command_keyword(cmd: _Node, src: bytes) -> str:
    for c in cmd.children:
        if c.type == "command_keyword":
            return src[c.start_byte : c.end_byte].decode(
                "latin-1", errors="replace"
            ).upper()
    return ""


def _apply_command(in_depth: int, cmd: _Node, src: bytes) -> int:
    kw = _command_keyword(cmd, src)
    if kw in _TSTART_KW:
        return min(MAX_DEPTH, in_depth + 1)
    if kw in _TCOMMIT_KW or kw in _TROLLBACK_KW:
        return max(0, in_depth - 1)
    return in_depth


def _out_for_edge(
    in_depth: int, cmd: _Node | None, edge_kind: str, src: bytes
) -> int:
    if cmd is None or edge_kind in ("skip", "if-skip"):
        return in_depth
    return _apply_command(in_depth, cmd, src)


def analyze_transactions(cfg: CFG, src: bytes) -> dict[int, int]:
    """Return ``{block_id: max_depth_at_entry}`` — the maximum
    transaction nesting depth on any path entering the block."""
    preds: dict[int, list[tuple[int, str]]] = {b.id: [] for b in cfg.blocks}
    for b in cfg.blocks:
        for succ, kind in zip(b.successors, b.edge_kinds):
            preds[succ].append((b.id, kind))

    in_depths: dict[int, int] = {b.id: 0 for b in cfg.blocks}

    work: deque[int] = deque(b.id for b in cfg.blocks)
    iterations = 0
    cap = max(64, len(cfg.blocks) * 8) * 4

    while work:
        iterations += 1
        if iterations > cap:
            break
        bid = work.popleft()
        if bid == cfg.entry().id:
            continue  # entry is always 0
        new_depth = 0
        for pbid, kind in preds[bid]:
            pcmd = cfg.block(pbid).command if cfg.block(pbid).kind == "command" else None
            new_depth = max(new_depth, _out_for_edge(in_depths[pbid], pcmd, kind, src))
        if new_depth == in_depths[bid]:
            continue
        in_depths[bid] = new_depth
        for succ in cfg.block(bid).successors:
            if succ not in work:
                work.append(succ)

    return in_depths


def depth_at_exit(cfg: CFG, src: bytes) -> int:
    """Convenience: max transaction nesting depth entering exit."""
    return analyze_transactions(cfg, src)[cfg.exit().id]
