"""Per-command variable extraction (Phase 7 step 2A).

Identifies which local variables a command DEFs, KILLs, or USEs. The
output is the foundation for both reaching-definitions / definite-
assignment (Phase 7 step 2B) and liveness analysis. Globals (``^X``)
are deliberately *not* tracked — the rules consuming this analysis
target local scope only.

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
# variable being read or defined.
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
    """Variable effects of a single command.

    ``defs`` and ``kills`` are sets of variable names; ``kills_all``
    captures the argumentless KILL / NEW semantics (kills every local
    in the current frame). ``uses`` is an *ordered* list so a
    diagnostic can point at a specific use site.
    """

    defs: set[str] = field(default_factory=set)
    kills: set[str] = field(default_factory=set)
    kills_all: bool = False
    uses: list[VarUse] = field(default_factory=list)


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


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


def _postcond_node(cmd: _Node) -> _Node | None:
    for c in cmd.children:
        if c.type == "postconditional":
            return c
    return None


def _identifier_text(local_var: _Node, src: bytes) -> str:
    for c in local_var.children:
        if c.type == "identifier":
            return src[c.start_byte : c.end_byte].decode(
                "latin-1", errors="replace"
            )
    return ""


def _has_subscripts(local_var: _Node) -> bool:
    return any(c.type == "subscripts" for c in local_var.children)


def _walk_local_vars(node: _Node) -> Iterator[_Node]:
    """Yield every ``local_variable`` node in the subtree, in source
    order. Skips the contents of ``global_variable`` (we don't track
    globals) and descends through every other node type — including
    ``function_call``, ``extrinsic_function``, ``subscripts`` — so
    that uses inside function arguments and inside subscript
    expressions are picked up.

    When the yielded node is itself a ``local_variable``, only its
    ``subscripts`` child is recursed into (the ``identifier`` child
    holds the variable's name, not a separate use).
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
# Public API
# ---------------------------------------------------------------------------


def effects(cmd: _Node, src: bytes) -> Effects:
    """Compute the variable effects of a single ``command`` AST node."""
    out = Effects()
    kw = _command_keyword(cmd, src)

    pc = _postcond_node(cmd)
    if pc is not None:
        for lv in _walk_local_vars(pc):
            out.uses.append(_make_use(lv, src))

    args = _argument_nodes(cmd)

    if kw in _SET_KW or kw in _MERGE_KW:
        for arg in args:
            lvars = list(_walk_local_vars(arg))
            if not lvars:
                continue
            lhs = lvars[0]
            out.defs.add(_identifier_text(lhs, src))
            for lv in lvars[1:]:
                out.uses.append(_make_use(lv, src))
        return out

    if kw in _READ_KW:
        for arg in args:
            lvars = list(_walk_local_vars(arg))
            if not lvars:
                continue
            target = lvars[0]
            out.defs.add(_identifier_text(target, src))
            for lv in lvars[1:]:
                out.uses.append(_make_use(lv, src))
        return out

    if kw in _KILL_KW or kw in _NEW_KW:
        if not args:
            out.kills_all = True
            return out
        for arg in args:
            lvars = list(_walk_local_vars(arg))
            if not lvars:
                continue
            target = lvars[0]
            if _has_subscripts(target):
                # Subscripted kill / new is a partial operation —
                # the base variable is still defined; only specific
                # subscripts move. Don't kill the base; record the
                # subscript expressions as uses.
                for lv in lvars[1:]:
                    out.uses.append(_make_use(lv, src))
            else:
                out.kills.add(_identifier_text(target, src))
        return out

    if kw in _FOR_KW:
        for arg in args:
            lvars = list(_walk_local_vars(arg))
            if not lvars:
                continue
            out.defs.add(_identifier_text(lvars[0], src))
            for lv in lvars[1:]:
                out.uses.append(_make_use(lv, src))
        return out

    if kw in _CALL_KW:
        for arg in args:
            lvars = list(_walk_local_vars(arg))
            # Skip the call-target identifier; everything else (the
            # arguments passed in subscripts) is a read.
            for lv in lvars[1:]:
                out.uses.append(_make_use(lv, src))
        return out

    # Generic command: every local var in arguments is a use.
    for arg in args:
        for lv in _walk_local_vars(arg):
            out.uses.append(_make_use(lv, src))
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
