"""Per-command variable extraction (Phase 7 step 2A).

Identifies which local variables a command DEFs, KILLs, or USEs. The
output is the foundation for both reaching-definitions / definite-
assignment (Phase 7 step 2B) and liveness analysis. Globals (``^X``)
are deliberately *not* tracked — the rules consuming this analysis
target local scope only.

Two granularity levels:

  * :func:`effects` — aggregate over the whole command. Handy for
    reaching-defs, which models a command as a single transfer step.
  * :func:`effects_of_argument` — per-argument effects. Lets a rule
    walk arguments left-to-right and track running defs (M evaluates
    multi-arg ``SET A=1,B=A`` left to right, so B's RHS sees A
    defined). Also where DO/JOB by-reference handling lives —
    ``D LBL(.X)`` defines X (the callee initializes it).

The semantics are encoded by ``tests/test_lint_flow_vars.py``; that
file is the spec.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

_Node = Any

# Command keyword sets (uppercased; abbreviation OR canonical).
_SET_KW = frozenset({"S", "SET"})
_MERGE_KW = frozenset({"M", "MERGE"})
_READ_KW = frozenset({"R", "READ"})
_KILL_KW = frozenset({"K", "KILL"})
_NEW_KW = frozenset({"N", "NEW"})
_FOR_KW = frozenset({"F", "FOR"})
# Commands whose first argument variable is a *call target*, not a
# variable being read or defined. By-reference args (``.X``) define X.
_CALL_KW = frozenset({"D", "DO", "J", "JOB", "G", "GOTO"})


@dataclass(frozen=True)
class VarUse:
    """A single read of a local variable, anchored at the AST node."""

    name: str
    node: _Node
    line: int
    column: int


@dataclass
class Effects:
    """Variable effects of a command (or a single argument).

    ``defs`` and ``kills`` are sets of variable names; ``kills_all``
    captures the argumentless KILL / NEW semantics (kills every local
    in the current frame). ``uses`` is an *ordered* list so a
    diagnostic can point at a specific use site.
    """

    defs: set[str] = field(default_factory=set)
    kills: set[str] = field(default_factory=set)
    kills_all: bool = False
    uses: list[VarUse] = field(default_factory=list)

    def merge(self, other: Effects) -> None:
        """Aggregate ``other`` into ``self`` (used for command-level
        rollup over per-argument results)."""
        self.defs |= other.defs
        self.kills |= other.kills
        self.kills_all = self.kills_all or other.kills_all
        self.uses.extend(other.uses)


# ---------------------------------------------------------------------------
# AST helpers (public — used by rules that walk the AST directly)
# ---------------------------------------------------------------------------


def command_keyword(cmd: _Node, src: bytes) -> str:
    """Uppercased command keyword, or ``""`` when missing."""
    for c in cmd.children:
        if c.type == "command_keyword":
            return src[c.start_byte : c.end_byte].decode(
                "latin-1", errors="replace"
            ).upper()
    return ""


def argument_nodes(cmd: _Node) -> list[_Node]:
    """Direct ``argument`` children of the command's argument list."""
    for c in cmd.children:
        if c.type == "argument_list":
            return [a for a in c.children if a.type == "argument"]
    return []


def postcond_node(cmd: _Node) -> _Node | None:
    for c in cmd.children:
        if c.type == "postconditional":
            return c
    return None


def _identifier_text(node: _Node, src: bytes) -> str:
    """For a ``local_variable`` returns the leading identifier; for
    a bare ``identifier`` returns its text."""
    if node.type == "identifier":
        return src[node.start_byte : node.end_byte].decode(
            "latin-1", errors="replace"
        )
    for c in node.children:
        if c.type == "identifier":
            return src[c.start_byte : c.end_byte].decode(
                "latin-1", errors="replace"
            )
    return ""


def _has_subscripts(local_var: _Node) -> bool:
    return any(c.type == "subscripts" for c in local_var.children)


def _walk_local_vars(node: _Node) -> Iterator[_Node]:
    """Yield every ``local_variable`` node in ``node``'s subtree, in
    source order. Skips the contents of ``global_variable``. Walks
    into ``function_call``, ``extrinsic_function``, ``subscripts`` so
    uses inside intrinsic args and inside subscript expressions are
    captured. When yielding a ``local_variable``, recurses only into
    its ``subscripts`` child (its ``identifier`` is the variable's
    name, not a separate use).
    """
    if node.type == "global_variable":
        return
    if node.type == "local_variable":
        yield node
        for c in node.children:
            if c.type == "subscripts":
                yield from _walk_local_vars(c)
        return
    for c in node.children:
        yield from _walk_local_vars(c)


def _make_use(local_var: _Node, src: bytes) -> VarUse:
    return VarUse(
        name=_identifier_text(local_var, src),
        node=local_var,
        line=local_var.start_point[0] + 1,
        column=local_var.start_point[1] + 1,
    )


# ---------------------------------------------------------------------------
# Per-argument effects
# ---------------------------------------------------------------------------


def _walk_set_like_arg(arg: _Node, src: bytes, out: Effects) -> None:
    """Walk a SET / MERGE / READ / FOR argument.

    The first ``local_variable`` encountered in source order is the
    LHS / target → recorded as a DEF. Subsequent ``local_variable``
    nodes are USES. ``by_reference`` nodes (which can appear inside
    extrinsic-function calls like ``$$F(.X)`` on the RHS) are DEFs —
    the callee may initialize the variable in the caller's frame.
    """
    target_assigned = [False]

    def visit(node: _Node) -> None:
        if node.type == "global_variable":
            return
        if node.type == "by_reference":
            name = _identifier_text(node, src)
            if name:
                out.defs.add(name)
            return
        if node.type == "local_variable":
            if not target_assigned[0]:
                target_assigned[0] = True
                out.defs.add(_identifier_text(node, src))
                for c in node.children:
                    if c.type == "subscripts":
                        visit(c)
                return
            out.uses.append(_make_use(node, src))
            for c in node.children:
                if c.type == "subscripts":
                    visit(c)
            return
        for c in node.children:
            visit(c)

    visit(arg)


def _walk_generic_arg(arg: _Node, src: bytes, out: Effects) -> None:
    """Walk a generic-command argument (W, Q, etc.).

    Every ``local_variable`` is a USE. ``by_reference`` (rare outside
    DO/JOB but possible if a non-call command has been mis-parsed)
    contributes a DEF for safety.
    """

    def visit(node: _Node) -> None:
        if node.type == "global_variable":
            return
        if node.type == "by_reference":
            name = _identifier_text(node, src)
            if name:
                out.defs.add(name)
            return
        if node.type == "local_variable":
            out.uses.append(_make_use(node, src))
            for c in node.children:
                if c.type == "subscripts":
                    visit(c)
            return
        for c in node.children:
            visit(c)

    visit(arg)


def _call_arg_subscripts(arg: _Node) -> _Node | None:
    """Find the ``subscripts`` node holding the actual call parameters.

    The call target is wrapped either as ``variable > local_variable``
    (for plain ``D LBL(X)``) or as ``entry_reference`` (for
    ``D LBL^ROUTINE(X)`` with the ``^`` separator). In either case
    the parameter list is the ``subscripts`` child. Returns ``None``
    when the call has no parameter list (``D LBL`` / ``D ^ROUTINE``).
    """
    for c in arg.children:
        if c.type == "variable":
            for cc in c.children:
                if cc.type == "local_variable":
                    for ccc in cc.children:
                        if ccc.type == "subscripts":
                            return ccc
            return None
        if c.type == "entry_reference":
            for cc in c.children:
                if cc.type == "subscripts":
                    return cc
            return None
    return None


def _walk_call_arg(arg: _Node, src: bytes, out: Effects) -> None:
    """Walk a DO/JOB/GOTO argument subtree.

    The call target itself contributes nothing to the var analysis —
    it's a label name, not a variable. Within the parameter list:

      * A ``by_reference`` node (``.X``) → recorded as a DEF (the
        callee may initialize X in the caller's frame).
      * Any other ``local_variable`` → recorded as a USE.
    """
    subs = _call_arg_subscripts(arg)
    if subs is None:
        return

    def visit(node: _Node) -> None:
        if node.type == "global_variable":
            return
        if node.type == "by_reference":
            name = _identifier_text(node, src)
            if name:
                out.defs.add(name)
            return
        if node.type == "local_variable":
            out.uses.append(_make_use(node, src))
            for c in node.children:
                if c.type == "subscripts":
                    visit(c)
            return
        for c in node.children:
            visit(c)

    visit(subs)


def effects_of_argument(arg: _Node, src: bytes, keyword: str) -> Effects:
    """Effects produced by evaluating one argument of a command.

    ``keyword`` is the uppercased command keyword (``"S"`` / ``"D"``
    / etc.). The same per-arg helper is used by :func:`effects` for
    command-level aggregation and by rules that need running defs
    across multiple arguments.

    For DO/JOB/GOTO, by-reference arguments (``.X``) contribute defs;
    by-value arguments contribute uses. The call target's identifier
    (the leftmost variable in the argument) is not tracked as either.
    """
    out = Effects()
    kw = keyword

    if (
        kw in _SET_KW
        or kw in _MERGE_KW
        or kw in _FOR_KW
        or kw in _READ_KW
    ):
        _walk_set_like_arg(arg, src, out)
        return out

    if kw in _KILL_KW or kw in _NEW_KW:
        lvars = list(_walk_local_vars(arg))
        if lvars:
            target = lvars[0]
            if _has_subscripts(target):
                # Partial kill — base var stays defined; subscripts are uses.
                for lv in lvars[1:]:
                    out.uses.append(_make_use(lv, src))
            else:
                out.kills.add(_identifier_text(target, src))
        return out

    if kw in _CALL_KW:
        _walk_call_arg(arg, src, out)
        return out

    # Generic: every local var is a use; by-ref (rare) is a def.
    _walk_generic_arg(arg, src, out)
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def uses_in_subtree(node: _Node, src: bytes) -> list[VarUse]:
    """Every local-variable USE inside ``node`` (postcondition,
    expression, etc.) in source order. Convenience for rules that
    need the read sites of an arbitrary subtree."""
    return [_make_use(lv, src) for lv in _walk_local_vars(node)]


def effects(cmd: _Node, src: bytes) -> Effects:
    """Aggregate variable effects of a single ``command`` AST node.

    Aggregates across the postconditional (uses) and every argument
    (per :func:`effects_of_argument`). For commands like
    ``S A=1,B=A`` this rolls A into both defs and uses — rules that
    need argument-level granularity should walk
    :func:`argument_nodes` and call :func:`effects_of_argument`
    directly with running state.
    """
    out = Effects()
    kw = command_keyword(cmd, src)

    pc = postcond_node(cmd)
    if pc is not None:
        for lv in _walk_local_vars(pc):
            out.uses.append(_make_use(lv, src))

    if not kw:
        return out

    # Argumentless K / N kills_all up-front; without the early check
    # we'd miss it because there are no argument nodes to iterate.
    args = argument_nodes(cmd)
    if not args and kw in (_KILL_KW | _NEW_KW):
        out.kills_all = True
        return out

    for arg in args:
        out.merge(effects_of_argument(arg, src, kw))
    return out


def formal_params(label_node: _Node, src: bytes) -> list[str]:
    """Names of the formal parameters declared on a label.

    ``LBL(A,B)`` → ``["A", "B"]``. Returns an empty list when the
    label has no formals.
    """
    parent = label_node.parent
    if parent is None:
        return []
    formals = next((c for c in parent.children if c.type == "formals"), None)
    if formals is None:
        return []
    names: list[str] = []
    for c in formals.children:
        if c.type == "identifier":
            names.append(
                src[c.start_byte : c.end_byte].decode("latin-1", errors="replace")
            )
    return names
