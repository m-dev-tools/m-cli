"""Tests for the AST-pattern control-flow rules.

Two single-file rules added with Phase D-extension:

  - M-XINDX-009: Unreachable code after unconditional QUIT/HALT/GOTO
  - M-XINDX-051: IF / ELSE with no body on the same line
"""

from __future__ import annotations

from pathlib import Path

from m_cli.lint.rules import _REGISTRY
from m_cli.lint.runner import lint_source

# ---------------------------------------------------------------------------
# M-XINDX-009 — unreachable code after unconditional QUIT / HALT / GOTO
# ---------------------------------------------------------------------------


def _rule(rid: str):
    return _REGISTRY[rid]


def test_xindx_009_flags_code_after_quit(tmp_path: Path) -> None:
    src = (
        b"FOO\n"
        b" SET X=1\n"
        b" QUIT\n"
        b" SET Y=2\n"  # dead — comes after unconditional QUIT
        b" SET Z=3\n"  # also dead
        b"INNER\n"  # new label resets the dead-code state
        b" SET A=1\n"  # NOT dead — different label
    )
    p = tmp_path / "FOO.m"
    diags = lint_source(p, src, [_rule("M-XINDX-009")])

    flagged_lines = sorted(d.line for d in diags if d.rule_id == "M-XINDX-009")
    assert flagged_lines == [4, 5]


def test_xindx_009_flags_code_after_unconditional_goto(tmp_path: Path) -> None:
    src = (
        b"FOO\n"
        b" GOTO LBL\n"
        b" SET X=1\n"  # dead
        b" QUIT\n"  # also dead
    )
    p = tmp_path / "FOO.m"
    diags = lint_source(p, src, [_rule("M-XINDX-009")])
    flagged_lines = sorted(d.line for d in diags if d.rule_id == "M-XINDX-009")
    assert flagged_lines == [3, 4]


def test_xindx_009_silent_when_no_terminator(tmp_path: Path) -> None:
    src = b"FOO\n SET X=1\n SET Y=2\n SET Z=3\n"
    p = tmp_path / "FOO.m"
    diags = lint_source(p, src, [_rule("M-XINDX-009")])
    assert not any(d.rule_id == "M-XINDX-009" for d in diags)


def test_xindx_009_silent_when_terminator_has_postconditional(tmp_path: Path) -> None:
    """``QUIT:X>0`` is conditional, so the SET below it isn't dead."""
    src = b"FOO\n SET X=1\n QUIT:X>0\n SET Y=2\n"
    p = tmp_path / "FOO.m"
    diags = lint_source(p, src, [_rule("M-XINDX-009")])
    assert not any(d.rule_id == "M-XINDX-009" for d in diags)


def test_xindx_009_resets_at_each_label(tmp_path: Path) -> None:
    """A QUIT in label A must not flag code in label B."""
    src = (
        b"A\n QUIT\n SET X=1\n"  # dead in A
        b"B\n SET Y=1\n QUIT\n"  # not dead in B
    )
    p = tmp_path / "FOO.m"
    diags = lint_source(p, src, [_rule("M-XINDX-009")])
    flagged_lines = sorted(d.line for d in diags if d.rule_id == "M-XINDX-009")
    assert flagged_lines == [3]


def test_xindx_009_skips_dot_block_lines(tmp_path: Path) -> None:
    """Dot-block control flow isn't modelled by this rule; lines that
    start with a dot prefix don't trigger it (avoids false positives)."""
    src = (
        b"FOO\n"
        b" QUIT\n"
        b" . SET X=1\n"  # dot-block; not flagged even though it follows QUIT
    )
    p = tmp_path / "FOO.m"
    diags = lint_source(p, src, [_rule("M-XINDX-009")])
    assert not any(d.rule_id == "M-XINDX-009" for d in diags)


def test_xindx_009_silent_on_comment_after_quit(tmp_path: Path) -> None:
    """Comment-only lines after QUIT aren't 'code' — don't flag them."""
    src = b"FOO\n QUIT\n ; just a comment\nINNER\n QUIT\n"
    p = tmp_path / "FOO.m"
    diags = lint_source(p, src, [_rule("M-XINDX-009")])
    assert not any(d.rule_id == "M-XINDX-009" for d in diags)


# ---------------------------------------------------------------------------
# M-XINDX-051 — IF / ELSE with no body on the same line
# ---------------------------------------------------------------------------


def test_xindx_051_flags_bare_if(tmp_path: Path) -> None:
    src = b"FOO\n IF X>0\n SET A=1\n"  # SET on next line is NOT gated by IF
    p = tmp_path / "FOO.m"
    diags = lint_source(p, src, [_rule("M-XINDX-051")])
    flagged = [d for d in diags if d.rule_id == "M-XINDX-051"]
    assert len(flagged) == 1
    assert flagged[0].line == 2


def test_xindx_051_flags_bare_else(tmp_path: Path) -> None:
    src = b"FOO\n ELSE\n SET A=1\n"
    p = tmp_path / "FOO.m"
    diags = lint_source(p, src, [_rule("M-XINDX-051")])
    flagged = [d for d in diags if d.rule_id == "M-XINDX-051"]
    assert len(flagged) == 1


def test_xindx_051_silent_on_if_with_body(tmp_path: Path) -> None:
    """``IF X>0 SET A=1`` has a body on the same line — fine."""
    src = b"FOO\n IF X>0 SET A=1\n"
    p = tmp_path / "FOO.m"
    diags = lint_source(p, src, [_rule("M-XINDX-051")])
    assert not any(d.rule_id == "M-XINDX-051" for d in diags)


def test_xindx_051_silent_on_other_commands(tmp_path: Path) -> None:
    src = b"FOO\n SET X=1\n WRITE X\n QUIT\n"
    p = tmp_path / "FOO.m"
    diags = lint_source(p, src, [_rule("M-XINDX-051")])
    assert not any(d.rule_id == "M-XINDX-051" for d in diags)


# ---------------------------------------------------------------------------
# Both rules are registered with the standard 4-arg signature
# ---------------------------------------------------------------------------


def test_new_rules_dont_need_workspace() -> None:
    for rid in ("M-XINDX-009", "M-XINDX-051"):
        rule = _REGISTRY[rid]
        assert rule.needs_workspace is False
