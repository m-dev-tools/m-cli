"""Tests for ``m_cli.lint.flow.vars`` — per-command variable extraction.

Phase 7 step 2A: identify which local variables each command DEFs,
KILLs, or USEs. Generic primitive — both reaching-definitions /
definite-assignment (Phase 7 step 2B) and liveness analysis consume
this output.

Semantics encoded by these tests:

  defs   — local vars this command introduces / overwrites with a value
           (SET LHS, READ, FOR control variable, MERGE LHS)
  kills  — local vars this command un-defines for the current scope
           (KILL, NEW); argumentless variants kill *everything*
  uses   — local vars this command reads (RHS expressions, postcond
           condition, FOR limit, WRITE arguments, indexes inside an
           LHS subscript, etc.)

Globals (``^X``) and intrinsic functions (``$LENGTH``) are not
tracked — the rules that consume this analysis (M-MOD-024 etc.)
target *local* scope only.
"""

from __future__ import annotations

from m_cli.lint.flow.vars import effects
from m_cli.parser import parse


def _first_command(src: bytes):
    tree = parse(src)
    for line in tree.root_node.children:
        if line.type != "line":
            continue
        for c in line.children:
            if c.type == "command_sequence":
                for cmd in c.children:
                    if cmd.type == "command":
                        return cmd
    raise AssertionError("no command found")


def _ef(src: bytes):
    return effects(_first_command(src), src)


# ---------------------------------------------------------------------------
# SET — the most common def site
# ---------------------------------------------------------------------------


def test_set_simple_lhs_is_def() -> None:
    e = _ef(b" S X=1\n")
    assert e.defs == {"X"}
    assert e.kills == set()
    assert e.kills_all is False
    assert {u.name for u in e.uses} == set()


def test_set_rhs_locals_are_uses() -> None:
    e = _ef(b" S X=Y+Z\n")
    assert e.defs == {"X"}
    assert {u.name for u in e.uses} == {"Y", "Z"}


def test_set_subscripted_lhs_def_with_subscript_uses() -> None:
    """``S A(I,J)=B(K)`` — A is def; I, J, K are uses; B is also a use."""
    e = _ef(b" S A(I,J)=B(K)\n")
    assert e.defs == {"A"}
    assert {u.name for u in e.uses} == {"I", "J", "K", "B"}


def test_set_multiple_arguments() -> None:
    """``S X=1,Y=2`` defines both X and Y (separated by argument list)."""
    e = _ef(b" S X=1,Y=2\n")
    assert e.defs == {"X", "Y"}


# ---------------------------------------------------------------------------
# READ — defines a local from terminal input
# ---------------------------------------------------------------------------


def test_read_target_is_def() -> None:
    e = _ef(b" R X\n")
    assert e.defs == {"X"}


# ---------------------------------------------------------------------------
# KILL / NEW — un-define
# ---------------------------------------------------------------------------


def test_kill_with_arg_kills_named_var() -> None:
    e = _ef(b" K X\n")
    assert e.kills == {"X"}
    assert e.kills_all is False


def test_kill_argumentless_kills_all() -> None:
    e = _ef(b" K \n")
    assert e.kills_all is True


def test_new_with_arg_kills_named_var() -> None:
    """``NEW X`` un-defines X for the current stack frame."""
    e = _ef(b" N X\n")
    assert e.kills == {"X"}


def test_new_argumentless_kills_all() -> None:
    e = _ef(b" N \n")
    assert e.kills_all is True


# ---------------------------------------------------------------------------
# FOR — control variable is a def
# ---------------------------------------------------------------------------


def test_for_control_var_is_def() -> None:
    e = _ef(b" F I=1:1:10\n")
    assert e.defs == {"I"}


# ---------------------------------------------------------------------------
# MERGE — LHS is def, RHS is use
# ---------------------------------------------------------------------------


def test_merge_lhs_is_def_rhs_is_use() -> None:
    e = _ef(b" M X=Y\n")
    assert e.defs == {"X"}
    assert {u.name for u in e.uses} == {"Y"}


# ---------------------------------------------------------------------------
# WRITE / QUIT / etc. — pure-use commands
# ---------------------------------------------------------------------------


def test_write_args_are_uses() -> None:
    e = _ef(b" W X,Y\n")
    assert e.defs == set()
    assert {u.name for u in e.uses} == {"X", "Y"}


def test_quit_with_arg_is_use() -> None:
    e = _ef(b" Q X\n")
    assert e.defs == set()
    assert {u.name for u in e.uses} == {"X"}


def test_quit_argumentless_no_uses() -> None:
    e = _ef(b" Q\n")
    assert e.defs == set()
    assert e.uses == []


# ---------------------------------------------------------------------------
# Postconditionals — condition is a use
# ---------------------------------------------------------------------------


def test_postconditional_locals_are_uses() -> None:
    """``Q:X=1`` uses X (the postcondition is evaluated)."""
    e = _ef(b" Q:X=1\n")
    assert {u.name for u in e.uses} == {"X"}


def test_postconditional_set_combines_def_and_pc_use() -> None:
    """``S:X=1 Y=Z`` — Y is def, X and Z are uses."""
    e = _ef(b" S:X=1 Y=Z\n")
    assert e.defs == {"Y"}
    assert {u.name for u in e.uses} == {"X", "Z"}


# ---------------------------------------------------------------------------
# Globals / intrinsic functions — not tracked
# ---------------------------------------------------------------------------


def test_globals_are_ignored_in_uses() -> None:
    e = _ef(b" S X=^Y\n")
    assert e.defs == {"X"}
    # ^Y is a global; must NOT appear in local uses.
    assert "Y" not in {u.name for u in e.uses}


def test_intrinsic_functions_are_ignored_in_uses() -> None:
    """``S X=$LENGTH(Y)`` — $LENGTH is an intrinsic call, not a local."""
    e = _ef(b" S X=$L(Y)\n")
    assert e.defs == {"X"}
    assert {u.name for u in e.uses} == {"Y"}


# ---------------------------------------------------------------------------
# Formal parameters — extracted from the label header
# ---------------------------------------------------------------------------


def test_formals_extraction() -> None:
    """``LBL(A,B)`` has formals A and B — both are defs at label entry."""
    from m_cli.lint.flow.vars import formal_params

    src = b"LBL(A,B)\n S X=A+B\n"
    tree = parse(src)
    label = next(
        n
        for line in tree.root_node.children
        if line.type == "line"
        for n in line.children
        if n.type == "label"
    )
    names = formal_params(label, src)
    assert names == ["A", "B"]


def test_no_formals_returns_empty() -> None:
    from m_cli.lint.flow.vars import formal_params

    src = b"LBL\n S X=1\n"
    tree = parse(src)
    label = next(
        n
        for line in tree.root_node.children
        if line.type == "line"
        for n in line.children
        if n.type == "label"
    )
    assert formal_params(label, src) == []


# ---------------------------------------------------------------------------
# By-reference parameters in DO calls — ignored for now
# ---------------------------------------------------------------------------


def test_do_call_passes_args_as_uses() -> None:
    """``D LBL(X,Y)`` — X and Y are read (passed in); not tracked as
    defs from the caller's perspective in this slice."""
    e = _ef(b" D LBL(X,Y)\n")
    assert e.defs == set()
    assert {u.name for u in e.uses} == {"X", "Y"}
