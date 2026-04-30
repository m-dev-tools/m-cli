"""Path-sensitive LOCK state analyzer (Phase 7 step 3A).

Forward MAY-analysis over the per-label CFG: at each block B, the
SET of variable names that are held by ``LOCK`` on AT LEAST ONE
path from entry to B. Drives :rule:`M-MOD-025` (LOCK leak across
exit paths) — the path-sensitive graduation of M-MOD-011.

Differs from :mod:`m_cli.lint.flow.reaching` (definite-assignment)
in two ways: lattice elements are sets of LOCK-target names; meet
is *union* (``∪``) — a leak on any single path is a real leak, so
we want the over-approximating "may be held" set, not the under-
approximating "must be held" set.

Transfer functions
------------------

For each ``argument`` of a ``LOCK`` command, in source order:

  ``+X``    incremental acquire   →  held |= {X}
  ``-X``    incremental release   →  held -= {X}
  ``X``     plain (replace form)  →  held = {X}     (clears all, then sets X)

Special-case the whole command:

  ``L``     argumentless          →  held = ∅  (release everything)

Postconditional ``L:cond +X`` updates held only on the "fall" /
"branch" / "exit" edge — the "skip" edge propagates IN unchanged
(command did not run). This is the same edge-kind handling the
:mod:`reaching` analyzer uses.

Subscripted LOCK targets (``L +A(1,2)``) are tracked under the base
identifier (``A``) — modeling subscript-level locks would need
either symbolic state (intractable) or per-subscript expansion
(combinatorial). The base-identifier approximation is what the
existing M-MOD-011 already uses.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from m_cli.lint.flow.cfg import CFG

_Node = Any

_LOCK_KEYWORDS = frozenset({"L", "LOCK"})


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


def _identifier_text(local_var: _Node, src: bytes) -> str:
    for c in local_var.children:
        if c.type == "identifier":
            return src[c.start_byte : c.end_byte].decode(
                "latin-1", errors="replace"
            )
    return ""


def _lock_arg(arg: _Node, src: bytes) -> tuple[str, str]:
    """Decode one LOCK argument as ``(polarity, name)``.

    Polarity is ``"+"`` (acquire), ``"-"`` (release), or
    ``"plain"`` (replace form). Name is the LOCK target's base
    identifier — subscripts are tracked at the base name only.

    Returns ``("", "")`` for malformed args (e.g. parse-error
    nodes); the caller should treat that as a no-op.
    """
    polarity = "plain"
    payload = None
    for c in arg.children:
        if c.type == "unary_expression":
            for cc in c.children:
                if cc.type == "operator":
                    op = src[cc.start_byte : cc.end_byte].decode(
                        "latin-1", errors="replace"
                    )
                    if op == "+":
                        polarity = "+"
                    elif op == "-":
                        polarity = "-"
                if cc.type == "variable":
                    payload = cc
            break
        if c.type == "variable":
            payload = c
            break
    if payload is None:
        return "", ""
    for cc in payload.children:
        if cc.type == "local_variable":
            return polarity, _identifier_text(cc, src)
    return "", ""


def _apply_command(
    in_set: frozenset[str], cmd: _Node, src: bytes
) -> frozenset[str]:
    """OUT for a LOCK command (``IN`` for non-LOCK commands is
    propagated unchanged). Plain replace form clears the held set
    before setting the named target."""
    kw = _command_keyword(cmd, src)
    if kw not in _LOCK_KEYWORDS:
        return in_set
    args = _argument_nodes(cmd)
    if not args:
        return frozenset()  # argumentless LOCK clears
    held = set(in_set)
    for arg in args:
        polarity, name = _lock_arg(arg, src)
        if not name:
            continue
        if polarity == "+":
            held.add(name)
        elif polarity == "-":
            held.discard(name)
        else:
            # Plain replace form: clear and set.
            held = {name}
    return frozenset(held)


def _out_for_edge(
    in_set: frozenset[str], cmd: _Node | None, edge_kind: str, src: bytes
) -> frozenset[str]:
    if cmd is None or edge_kind in ("skip", "if-skip"):
        return in_set
    return _apply_command(in_set, cmd, src)


def analyze_locks(cfg: CFG, src: bytes) -> dict[int, frozenset[str]]:
    """Return ``{block_id: held_set_at_entry}`` for every block in
    ``cfg``. Uses union meet — a name appears at B iff it is held
    on at least one path from entry to B.
    """
    preds: dict[int, list[tuple[int, str]]] = {b.id: [] for b in cfg.blocks}
    for b in cfg.blocks:
        for succ, kind in zip(b.successors, b.edge_kinds):
            preds[succ].append((b.id, kind))

    in_sets: dict[int, frozenset[str]] = {b.id: frozenset() for b in cfg.blocks}

    work: deque[int] = deque(b.id for b in cfg.blocks)
    iterations = 0
    cap = max(64, len(cfg.blocks) * 8) * 4

    while work:
        iterations += 1
        if iterations > cap:
            break
        bid = work.popleft()
        new_in: frozenset[str] = frozenset()
        for pbid, kind in preds[bid]:
            pcmd = cfg.block(pbid).command if cfg.block(pbid).kind == "command" else None
            new_in = new_in | _out_for_edge(in_sets[pbid], pcmd, kind, src)
        if bid == cfg.entry().id:
            new_in = frozenset()  # entry always starts clean
        if new_in == in_sets[bid]:
            continue
        in_sets[bid] = new_in
        for succ in cfg.block(bid).successors:
            if succ not in work:
                work.append(succ)

    return in_sets


def held_at_exit(cfg: CFG, src: bytes) -> frozenset[str]:
    """Convenience: held set entering the exit block."""
    return analyze_locks(cfg, src)[cfg.exit().id]
