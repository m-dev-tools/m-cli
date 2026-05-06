"""Tests for the SAC fmt preset and its uppercase-intrinsic-* siblings.

The SAC preset is the AST-preserving subset of VistA SAC compliance:
trim + uppercase-* (commands, intrinsics, special variables) + compact-*.
Structural SAC rules (line-length wrap, label naming, ;; data discipline)
are *not* fmt rules — they violate AST-shape preservation or cross-routine
safety. They live in ``m lint --rules=sac`` instead.

The preset is also the bidirectional partner of ``pythonic-lower``:

    pythonic-lower(sac(src))  == pythonic-lower(src)   # SAC → pythonic-lower
    sac(pythonic-lower(src))  == sac(src)              # pythonic-lower → SAC

Round-trip is *normalizing*, not invertible — mixed-form input collapses
to one canonical form. That matches the existing pythonic / compact
contract documented in ``rules.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from m_cli.fmt.formatter import format_source
from m_cli.fmt.rules import (
    all_rules,
    pythonic_lower_rules,
    rule_by_id,
    sac_rules,
    select_fmt_rules,
    uppercase_intrinsic_functions,
    uppercase_special_variables,
)
from m_cli.parser import parse

FIXTURES = Path(__file__).parent / "fixtures" / "sac"
TRIPLES = ("HELLO", "INTRINS", "SPECVAR", "COMBO")


def _read(name: str, kind: str) -> bytes:
    return (FIXTURES / f"{name}.{kind}.m").read_bytes()


def _apply(src: bytes, rules) -> bytes:
    return format_source(src, rules=rules)


def _ast_shape(src: bytes) -> list[str]:
    """Flatten the parse tree to a list of node types — order-preserving."""
    tree = parse(src)
    out: list[str] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        out.append(node.type)
        stack.extend(reversed(node.children))
    return out


# ---------------------------------------------------------------------------
# Registry: the two new uppercase-* siblings exist
# ---------------------------------------------------------------------------


def test_uppercase_intrinsic_functions_registered() -> None:
    assert rule_by_id("uppercase-intrinsic-functions") is not None


def test_uppercase_special_variables_registered() -> None:
    assert rule_by_id("uppercase-special-variables") is not None


def test_uppercase_intrinsic_functions_uppercases_lowercase_token() -> None:
    src = b"FOO\n S L=$length(\"x\")\n Q\n"
    out = uppercase_intrinsic_functions(src)
    assert b"$LENGTH" in out
    assert b"$length" not in out


def test_uppercase_intrinsic_functions_idempotent() -> None:
    src = b"FOO\n S L=$length(\"x\")\n Q\n"
    once = uppercase_intrinsic_functions(src)
    twice = uppercase_intrinsic_functions(once)
    assert once == twice


def test_uppercase_special_variables_uppercases_lowercase_token() -> None:
    src = b"FOO\n S H=$horolog\n Q\n"
    out = uppercase_special_variables(src)
    assert b"$HOROLOG" in out
    assert b"$horolog" not in out


def test_uppercase_special_variables_idempotent() -> None:
    src = b"FOO\n S H=$horolog\n Q\n"
    once = uppercase_special_variables(src)
    twice = uppercase_special_variables(once)
    assert once == twice


# ---------------------------------------------------------------------------
# Preset: sac_rules() composition
# ---------------------------------------------------------------------------


def test_sac_rules_returns_expected_pipeline_in_order() -> None:
    """uppercase-* runs *before* compact-* so compact's case-preserving
    output ends up upper-case regardless of input case."""
    ids = [r.id for r in sac_rules()]
    assert ids == [
        "uppercase-command-keywords",
        "uppercase-intrinsic-functions",
        "uppercase-special-variables",
        "compact-command-keywords",
        "compact-intrinsic-functions",
        "compact-special-variables",
        "trim-trailing-whitespace",
    ]


def test_select_fmt_rules_sac_matches_sac_rules() -> None:
    assert {r.id for r in select_fmt_rules("sac")} == {r.id for r in sac_rules()}


def test_sac_rules_all_registered() -> None:
    registered = {r.id for r in all_rules()}
    for rule in sac_rules():
        assert rule.id in registered


# ---------------------------------------------------------------------------
# Fixture-driven: pythonic-lower → SAC, and back
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", TRIPLES)
def test_pythonic_lower_to_sac_matches_fixture(name: str) -> None:
    src = _read(name, "pythonic-lower")
    expected = _read(name, "sac")
    out = _apply(src, sac_rules())
    assert out == expected, (
        f"{name}: pythonic-lower → sac mismatch\n"
        f"--- expected ---\n{expected.decode()}\n"
        f"--- got ---\n{out.decode()}"
    )


@pytest.mark.parametrize("name", TRIPLES)
def test_sac_to_pythonic_lower_matches_fixture(name: str) -> None:
    src = _read(name, "sac")
    expected = _read(name, "pythonic-lower")
    out = _apply(src, pythonic_lower_rules())
    assert out == expected, (
        f"{name}: sac → pythonic-lower mismatch\n"
        f"--- expected ---\n{expected.decode()}\n"
        f"--- got ---\n{out.decode()}"
    )


# ---------------------------------------------------------------------------
# Idempotency: applying the SAC preset twice == once
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", TRIPLES)
def test_sac_idempotent_from_pythonic_lower(name: str) -> None:
    src = _read(name, "pythonic-lower")
    once = _apply(src, sac_rules())
    twice = _apply(once, sac_rules())
    assert once == twice


@pytest.mark.parametrize("name", TRIPLES)
def test_sac_no_op_on_already_sac(name: str) -> None:
    src = _read(name, "sac")
    out = _apply(src, sac_rules())
    assert out == src


# ---------------------------------------------------------------------------
# Round-trip: normalizing equivalence (not byte-invertible)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", TRIPLES)
def test_round_trip_through_pythonic_lower_collapses(name: str) -> None:
    """sac(pythonic-lower(sac(src))) == sac(src) — round-trips on
    already-normalized input. The stronger byte-invertibility property
    does NOT hold for mixed-form input; we only pin the normalizing
    contract here."""
    sac_src = _read(name, "sac")
    py_lower = _apply(sac_src, pythonic_lower_rules())
    back_to_sac = _apply(py_lower, sac_rules())
    assert back_to_sac == sac_src


# ---------------------------------------------------------------------------
# AST shape: SAC preset must preserve parse-tree structure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", TRIPLES)
def test_sac_preset_preserves_ast_shape(name: str) -> None:
    src = _read(name, "pythonic-lower")
    out = _apply(src, sac_rules())
    assert _ast_shape(src) == _ast_shape(out), (
        f"{name}: AST shape changed by SAC preset"
    )


# ---------------------------------------------------------------------------
# ;; data lines must never be touched in either direction
# ---------------------------------------------------------------------------


def test_double_semicolon_data_lines_untouched_by_sac() -> None:
    src = (FIXTURES / "DATALINES.both.m").read_bytes()
    out_sac = _apply(src, sac_rules())
    out_py = _apply(src, pythonic_lower_rules())
    # The ;; payload contains literal "set", "$length", "BAR" — none of
    # which should be rewritten because they're inside comment_text
    # nodes, not command/intrinsic/ISV nodes.
    assert b";;set foo=BAR" in out_sac
    assert b";;$length must stay verbatim" in out_sac
    assert b";;set foo=BAR" in out_py
    assert b";;$length must stay verbatim" in out_py
