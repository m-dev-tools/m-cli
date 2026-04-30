"""Taint analysis MVP — Phase 9.

Forward MAY-analysis over the per-label CFG: at each block B, the
SET of local variable names that may hold *untrusted* values
originating from a source. Drives :rule:`M-MOD-036` (untrusted data
flows into an indirection sink) — the differentiating security
feature of the m-cli lint suite.

Lattice element: ``frozenset[str]`` of tainted variable names.
Meet: union (``∪``). A var is tainted at B iff it's tainted on at
least one path from entry to B — the conservative "may be attacker-
controlled" reading wanted for security.

Sources (this MVP)
------------------
* ``READ X`` — terminal input.
* Formal parameters of the label, when ``TaintConfig.formals_tainted``
  is True (default). Public-label formals are attack surface.

Sinks
-----
The analyzer alone does not flag sinks. The companion rule
M-MOD-036 in :mod:`m_cli.lint._modern` reads the analyzer's output
and checks each command for ``indirection`` AST nodes (``@expr``)
and ``XECUTE`` arguments — flagging when their inner expression
contains a tainted var.

Sanitizers
----------
Configurable via ``TaintConfig.sanitizers`` (default: ``$L``,
``$LENGTH``, ``$A``, ``$ASCII`` — all return numeric values whose
content cannot be code-injected). When the analyzer walks an
expression for taint, it skips the contents of any
``function_call`` whose keyword is in the sanitizer set — the
result is treated as clean regardless of the args.

Transfer functions
------------------
``READ X``                  →  tainted ∪= {X}
``SET X=<expr>``            →  if any var in <expr> ∈ tainted:
                                   tainted ∪= {X}
                               else:
                                   tainted -= {X}     (strong update)
``KILL X`` / ``NEW X``      →  tainted -= {X}
argumentless ``KILL`` / ``NEW`` → tainted = ∅
any other                   →  tainted unchanged

Multi-arg SET (``S A=expr1, B=expr2``) is handled per-argument so
the second arg sees the first's effects (``S A=X, B=A`` — if X is
tainted, both A and B end up tainted).

Limitations (this MVP, deliberate)
----------------------------------
* No cross-routine taint propagation — a tainted formal flowing
  into an extrinsic call (``$$F(X)``) doesn't taint the callee's
  return. Cross-routine analysis is a Phase 9+ refinement.
* By-reference DO/JOB calls (``D LBL(.X)``) — X's taint state is
  not modified by the call. The callee may set X to a clean or
  tainted value; we conservatively keep its current state.
* Indirection on the LHS (``S @X=value``) — we don't track which
  global gets written; the taint analyzer just flags this as a
  sink via M-MOD-036.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from m_cli.lint.flow.cfg import CFG
from m_cli.lint.flow.vars import (
    argument_nodes,
    command_keyword,
    effects_of_argument,
    formal_params,
)

_Node = Any


@dataclass(frozen=True)
class TaintConfig:
    """Configuration for the taint analyzer.

    ``formals_tainted``: whether the formal parameters of the label
    are tainted at entry. Default True — public-label formals are
    attack surface; users with strictly-internal labels can set to
    False to suppress noise.

    ``sanitizers``: uppercased intrinsic-function keywords whose
    output is treated as clean regardless of input taint (e.g.
    ``$LENGTH`` returns a number, can't carry code).
    """

    formals_tainted: bool = True
    sanitizers: frozenset[str] = field(
        default_factory=lambda: frozenset({"$L", "$LENGTH", "$A", "$ASCII"})
    )


# Source / propagation / untaint keywords.
_READ_KW = frozenset({"R", "READ"})
_SET_KW = frozenset({"S", "SET"})
_MERGE_KW = frozenset({"M", "MERGE"})
_KILL_KW = frozenset({"K", "KILL"})
_NEW_KW = frozenset({"N", "NEW"})


def _identifier_text(local_var: _Node, src: bytes) -> str:
    for c in local_var.children:
        if c.type == "identifier":
            return src[c.start_byte : c.end_byte].decode(
                "latin-1", errors="replace"
            )
    return ""


def _intrinsic_keyword(function_call_node: _Node, src: bytes) -> str:
    for c in function_call_node.children:
        if c.type == "intrinsic_function_keyword":
            return src[c.start_byte : c.end_byte].decode(
                "latin-1", errors="replace"
            ).upper()
    return ""


def expression_taints(
    node: _Node,
    src: bytes,
    tainted: frozenset[str],
    sanitizers: frozenset[str],
) -> bool:
    """True if walking ``node``'s subtree finds at least one
    ``local_variable`` whose name is in ``tainted``.

    Skips:
      * ``global_variable`` subtrees (we don't track globals)
      * ``function_call`` subtrees whose keyword is a sanitizer
        (their output is clean regardless of input taint)

    Recurses into ``local_variable`` subscripts so that
    ``A(X)`` reads X.
    """
    found = [False]

    def visit(n: _Node) -> None:
        if found[0]:
            return
        if n.type == "global_variable":
            return
        if n.type == "function_call":
            kw = _intrinsic_keyword(n, src)
            if kw in sanitizers:
                return
            for c in n.children:
                visit(c)
            return
        if n.type == "local_variable":
            name = _identifier_text(n, src)
            if name in tainted:
                found[0] = True
                return
            for c in n.children:
                if c.type == "subscripts":
                    visit(c)
            return
        for c in n.children:
            visit(c)

    visit(node)
    return found[0]


def _set_arg_lhs(arg: _Node, src: bytes) -> str | None:
    """The leftmost ``local_variable`` in a SET-like argument — the
    target being assigned. Returns its identifier text, or None for
    malformed args."""

    def visit(n: _Node) -> str | None:
        if n.type == "global_variable":
            return None
        if n.type == "local_variable":
            return _identifier_text(n, src)
        for c in n.children:
            r = visit(c)
            if r is not None:
                return r
        return None

    return visit(arg)


def _set_arg_taint(
    arg: _Node,
    src: bytes,
    tainted: frozenset[str],
    sanitizers: frozenset[str],
) -> bool:
    """Whether the RHS of a SET-like argument propagates taint.

    Walks the arg subtree, skipping:
      * the leftmost local_variable's identifier (it's the LHS,
        not a read), but DOES walk its subscripts (those are reads)
      * sanitizer function_calls (output is clean)

    Any other local_variable whose name is in ``tainted`` returns
    True.
    """
    found = [False]
    seen_first = [False]

    def visit(n: _Node) -> None:
        if found[0]:
            return
        if n.type == "global_variable":
            return
        if n.type == "function_call":
            kw = _intrinsic_keyword(n, src)
            if kw in sanitizers:
                return
            for c in n.children:
                visit(c)
            return
        if n.type == "local_variable":
            if not seen_first[0]:
                seen_first[0] = True
                # LHS — its name doesn't read; only its subscripts do.
                for c in n.children:
                    if c.type == "subscripts":
                        visit(c)
                return
            name = _identifier_text(n, src)
            if name in tainted:
                found[0] = True
                return
            for c in n.children:
                if c.type == "subscripts":
                    visit(c)
            return
        for c in n.children:
            visit(c)

    visit(arg)
    return found[0]


def _apply_command(
    in_tainted: frozenset[str], cmd: _Node, src: bytes, config: TaintConfig
) -> frozenset[str]:
    """Forward transfer for one command. Returns the OUT tainted set."""
    kw = command_keyword(cmd, src)
    out = set(in_tainted)

    if kw in _READ_KW:
        for arg in argument_nodes(cmd):
            eff = effects_of_argument(arg, src, "R")
            out |= eff.defs
        return frozenset(out)

    if kw in _SET_KW or kw in _MERGE_KW:
        for arg in argument_nodes(cmd):
            lhs = _set_arg_lhs(arg, src)
            if lhs is None:
                continue
            if _set_arg_taint(arg, src, frozenset(out), config.sanitizers):
                out.add(lhs)
            else:
                out.discard(lhs)
        return frozenset(out)

    if kw in _KILL_KW or kw in _NEW_KW:
        args = argument_nodes(cmd)
        if not args:
            return frozenset()
        for arg in args:
            eff = effects_of_argument(arg, src, "K")
            out -= eff.kills
        return frozenset(out)

    return frozenset(out)


def _out_for_edge(
    in_tainted: frozenset[str],
    cmd: _Node | None,
    edge_kind: str,
    src: bytes,
    config: TaintConfig,
) -> frozenset[str]:
    if cmd is None or edge_kind == "skip":
        return in_tainted
    return _apply_command(in_tainted, cmd, src, config)


def analyze_taint(
    cfg: CFG, src: bytes, *, config: TaintConfig | None = None
) -> dict[int, frozenset[str]]:
    """Return ``{block_id: tainted_at_entry}`` — the set of local
    variable names that may be tainted on at least one path from
    entry to the block.

    The entry block's IN is initialised from ``config.formals_tainted``
    (and the label's declared formals).
    """
    cfg_config = config or TaintConfig()

    preds: dict[int, list[tuple[int, str]]] = {b.id: [] for b in cfg.blocks}
    for b in cfg.blocks:
        for succ, kind in zip(b.successors, b.edge_kinds):
            preds[succ].append((b.id, kind))

    in_sets: dict[int, frozenset[str]] = {b.id: frozenset() for b in cfg.blocks}

    # Initial taint at entry: the label's formals (if configured).
    initial: frozenset[str] = frozenset()
    if cfg_config.formals_tainted:
        initial = frozenset(formal_params(cfg.label_node, src))
    in_sets[cfg.entry().id] = initial

    work: deque[int] = deque(b.id for b in cfg.blocks)
    iterations = 0
    cap = max(64, len(cfg.blocks) * 8) * 4

    while work:
        iterations += 1
        if iterations > cap:
            break
        bid = work.popleft()
        if bid == cfg.entry().id:
            continue

        new_in: frozenset[str] = frozenset()
        for pbid, kind in preds[bid]:
            pcmd = cfg.block(pbid).command if cfg.block(pbid).kind == "command" else None
            new_in = new_in | _out_for_edge(
                in_sets[pbid], pcmd, kind, src, cfg_config
            )

        if new_in == in_sets[bid]:
            continue
        in_sets[bid] = new_in
        for succ in cfg.block(bid).successors:
            if succ not in work:
                work.append(succ)

    return in_sets


def tainted_at_exit(
    cfg: CFG, src: bytes, *, config: TaintConfig | None = None
) -> frozenset[str]:
    return analyze_taint(cfg, src, config=config)[cfg.exit().id]
