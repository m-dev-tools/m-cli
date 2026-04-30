"""Tests for the M-MOD-NN modernization rules (Phase 2).

Each rule has at least one positive (must fire) and one negative
(must not fire) test, plus a configurable-threshold test that pins
the override behavior.
"""

from __future__ import annotations

from pathlib import Path

from m_cli.lint import lint_source, select_rules
from m_cli.lint.context import LintContext
from m_cli.lint.thresholds import validate as validate_thresholds


def _ctx(**overrides) -> LintContext:
    """Build a LintContext with the given threshold overrides;
    defaults fill in the rest."""
    return LintContext(thresholds=validate_thresholds(overrides))


def _lint(src: bytes, rule_id: str, *, ctx: LintContext | None = None):
    rules = select_rules(rule_id)
    return lint_source(Path(rule_id.replace("-", "") + ".m"), src, rules, ctx=ctx)


# ---------------------------------------------------------------------------
# M-MOD-001 — line length
# ---------------------------------------------------------------------------


class TestLineLength:
    def test_fires_at_default_200(self):
        src = b"hello ;c\n " + b"x" * 250 + b"\n quit\n"
        diags = _lint(src, "M-MOD-001", ctx=_ctx())
        assert len(diags) == 1
        assert diags[0].rule_id == "M-MOD-001"
        assert diags[0].line == 2

    def test_silent_under_default(self):
        src = b"hello ;c\n " + b"x" * 100 + b"\n quit\n"
        assert _lint(src, "M-MOD-001", ctx=_ctx()) == []

    def test_threshold_override_via_config_lowers_limit(self):
        # 100 bytes — fires at threshold=80 but not at default 200.
        src = b"hello ;c\n " + b"x" * 100 + b"\n quit\n"
        assert _lint(src, "M-MOD-001", ctx=_ctx(line_length=80)) == [] or True
        diags = _lint(src, "M-MOD-001", ctx=_ctx(line_length=80))
        assert len(diags) == 1
        assert diags[0].line == 2

    def test_message_carries_actual_and_limit(self):
        src = b"hello ;c\n " + b"x" * 250 + b"\n quit\n"
        diags = _lint(src, "M-MOD-001", ctx=_ctx())
        assert "251 bytes" in diags[0].message  # 250 'x's + leading space
        assert "limit: 200" in diags[0].message


# ---------------------------------------------------------------------------
# M-MOD-002 — code line length (excludes comment-only)
# ---------------------------------------------------------------------------


class TestCodeLineLength:
    def test_fires_on_long_code_line(self):
        # 1100 bytes of code — exceeds default 1000.
        src = b"hello ;c\n s x=" + b"1" * 1100 + b"\n quit\n"
        diags = _lint(src, "M-MOD-002", ctx=_ctx())
        assert len(diags) == 1
        assert diags[0].line == 2

    def test_silent_on_long_comment_only_line(self):
        # 1500-byte comment-only line — must NOT fire.
        src = b"hello ;c\n ;" + b"x" * 1500 + b"\n quit\n"
        assert _lint(src, "M-MOD-002", ctx=_ctx()) == []

    def test_silent_under_default(self):
        src = b"hello ;c\n s x=42\n quit\n"
        assert _lint(src, "M-MOD-002", ctx=_ctx()) == []

    def test_threshold_override(self):
        # 50-byte code line, threshold lowered to 40.
        src = b"hello ;c\n s x=" + b"1" * 50 + b"\n quit\n"
        diags = _lint(src, "M-MOD-002", ctx=_ctx(code_line_length=40))
        assert len(diags) == 1


# ---------------------------------------------------------------------------
# M-MOD-003 — routine LOC
# ---------------------------------------------------------------------------


class TestRoutineLines:
    def test_fires_above_threshold(self):
        # 12 lines, threshold 10.
        src = b"hello ;c\n" + b" quit\n" * 11
        diags = _lint(src, "M-MOD-003", ctx=_ctx(routine_lines=10))
        assert len(diags) == 1
        assert diags[0].line == 1
        assert "12 lines" in diags[0].message
        assert "limit: 10" in diags[0].message

    def test_silent_at_threshold(self):
        src = b"hello ;c\n" + b" quit\n" * 9  # 10 lines
        assert _lint(src, "M-MOD-003", ctx=_ctx(routine_lines=10)) == []

    def test_silent_under_default(self):
        # Default 1000; a 10-line file is fine.
        src = b"hello ;c\n" + b" quit\n" * 9
        assert _lint(src, "M-MOD-003", ctx=_ctx()) == []

    def test_handles_no_trailing_newline(self):
        # 5 lines, no trailing \n — still 5 lines.
        src = b"hello ;c\n quit\n quit\n quit\n quit"
        diags = _lint(src, "M-MOD-003", ctx=_ctx(routine_lines=4))
        assert len(diags) == 1
        assert "5 lines" in diags[0].message

    def test_empty_source_no_finding(self):
        assert _lint(b"", "M-MOD-003", ctx=_ctx()) == []


# ---------------------------------------------------------------------------
# M-MOD-004 — label body LOC
# ---------------------------------------------------------------------------


class TestLabelLines:
    def test_fires_on_long_body(self):
        # entry: 1 line; SUBR has 5 body lines; threshold 3.
        body = b" w 1\n" * 5
        src = b"hello ;c\n quit\nSUBR\n" + body + b" quit\n"
        diags = _lint(src, "M-MOD-004", ctx=_ctx(label_lines=3))
        # Only SUBR exceeds (its body is 6 lines: 5 writes + the quit).
        # The entry "hello" body is only 1 line.
        assert any(d.rule_id == "M-MOD-004" and "SUBR" in d.message for d in diags)

    def test_silent_short_bodies(self):
        src = b"hello ;c\n quit\nSUBR\n quit\n"
        assert _lint(src, "M-MOD-004", ctx=_ctx(label_lines=10)) == []

    def test_threshold_override(self):
        # Entry body = 4 lines. threshold=3 → fires; threshold=10 → silent.
        src = b"hello ;c\n s a=1\n s b=2\n s c=3\n quit\n"
        assert (
            len(_lint(src, "M-MOD-004", ctx=_ctx(label_lines=3))) == 1
        )
        assert _lint(src, "M-MOD-004", ctx=_ctx(label_lines=10)) == []

    def test_no_labels_no_finding(self):
        src = b""
        assert _lint(src, "M-MOD-004", ctx=_ctx()) == []


# ---------------------------------------------------------------------------
# M-MOD-005 — cyclomatic complexity
# ---------------------------------------------------------------------------


class TestCyclomaticComplexity:
    def test_silent_on_simple_label(self):
        src = b"hello ;c\n s x=1\n quit\n"
        assert _lint(src, "M-MOD-005", ctx=_ctx(cyclomatic=2)) == []

    def test_fires_on_too_many_branches(self):
        # 4 IFs + 1 base = cyclomatic 5; threshold 3.
        src = (
            b"hello ;c\n"
            b" if a s x=1\n"
            b" if b s y=2\n"
            b" if c s z=3\n"
            b" if d s w=4\n"
            b" quit\n"
        )
        diags = _lint(src, "M-MOD-005", ctx=_ctx(cyclomatic=3))
        assert len(diags) == 1
        assert "complexity 5" in diags[0].message
        assert "limit: 3" in diags[0].message

    def test_postconditional_counts(self):
        # 3 postconditionals + 1 base = 4; threshold 3.
        src = b"hello ;c\n s:a x=1\n s:b y=2\n s:c z=3\n quit\n"
        diags = _lint(src, "M-MOD-005", ctx=_ctx(cyclomatic=3))
        assert len(diags) == 1
        assert "complexity 4" in diags[0].message

    def test_for_loop_counts(self):
        # 2 FORs + 1 base = 3; threshold 2.
        src = b"hello ;c\n for i=1:1:10 s x(i)=i\n for j=1:1:5 s y(j)=j\n quit\n"
        diags = _lint(src, "M-MOD-005", ctx=_ctx(cyclomatic=2))
        assert len(diags) == 1

    def test_per_label_isolation(self):
        # First label is heavy (4 IFs); second is clean. Only first fires.
        src = (
            b"big ;c\n"
            b" if a w 1\n"
            b" if b w 2\n"
            b" if c w 3\n"
            b" if d w 4\n"
            b" quit\n"
            b"small ;c\n"
            b" s x=1\n"
            b" quit\n"
        )
        diags = _lint(src, "M-MOD-005", ctx=_ctx(cyclomatic=3))
        assert len(diags) == 1
        assert "'big'" in diags[0].message


# ---------------------------------------------------------------------------
# M-MOD-006 — cognitive complexity
# ---------------------------------------------------------------------------


class TestCognitiveComplexity:
    def test_silent_on_flat_label(self):
        # 3 flat IFs → cognitive 3; threshold 5.
        src = b"hello ;c\n if a w 1\n if b w 2\n if c w 3\n quit\n"
        assert _lint(src, "M-MOD-006", ctx=_ctx(cognitive=5)) == []

    def test_nested_decision_counts_more(self):
        # Two flat IFs (cost 2) + one IF inside depth-2 dot-block (cost 1+2=3)
        # → total cognitive 5. Threshold 4 → fires.
        src = (
            b"hello ;c\n"
            b" if a w 1\n"
            b" if b do\n"
            b" . if c do\n"
            b" . . if d w 4\n"
            b" quit\n"
        )
        diags = _lint(src, "M-MOD-006", ctx=_ctx(cognitive=4))
        assert len(diags) == 1
        assert "complexity" in diags[0].message

    def test_threshold_override(self):
        src = b"hello ;c\n if a w 1\n if b w 2\n quit\n"
        # Cognitive = 2; over threshold 1 fires, under threshold 5 silent.
        assert len(_lint(src, "M-MOD-006", ctx=_ctx(cognitive=1))) == 1
        assert _lint(src, "M-MOD-006", ctx=_ctx(cognitive=5)) == []


# ---------------------------------------------------------------------------
# M-MOD-007 — dot-block nesting depth
# ---------------------------------------------------------------------------


class TestDotBlockDepth:
    def test_silent_at_threshold(self):
        # depth 2 is at threshold 2 (not over).
        src = (
            b"hello ;c\n"
            b" if x do\n"
            b" . if y do\n"
            b" . . s z=1\n"
            b" quit\n"
        )
        assert _lint(src, "M-MOD-007", ctx=_ctx(dot_block_depth=2)) == []

    def test_fires_above_threshold(self):
        # depth 3 → threshold 2 → 1 finding (only the depth-3 line).
        src = (
            b"hello ;c\n"
            b" if x do\n"
            b" . if y do\n"
            b" . . if z do\n"
            b" . . . s w=1\n"
            b" quit\n"
        )
        diags = _lint(src, "M-MOD-007", ctx=_ctx(dot_block_depth=2))
        assert len(diags) == 1
        assert "depth 3" in diags[0].message

    def test_silent_no_dot_blocks(self):
        src = b"hello ;c\n s x=1\n s y=2\n quit\n"
        assert _lint(src, "M-MOD-007", ctx=_ctx()) == []


# ---------------------------------------------------------------------------
# M-MOD-008 — argument count
# ---------------------------------------------------------------------------


class TestArgumentCount:
    def test_silent_on_short_arg_list(self):
        src = b"hello ;c\nadd(a,b) ; sum two\n quit a+b\n"
        assert _lint(src, "M-MOD-008", ctx=_ctx(argument_count=7)) == []

    def test_fires_on_too_many_args(self):
        # 8 args, threshold 7 → fires.
        src = (
            b"hello ;c\n"
            b"big(a,b,c,d,e,f,g,h) ; eight args\n"
            b" quit a+b+c+d+e+f+g+h\n"
        )
        diags = _lint(src, "M-MOD-008", ctx=_ctx(argument_count=7))
        assert len(diags) == 1
        assert "8 formal arguments" in diags[0].message
        assert "'big'" in diags[0].message

    def test_threshold_override(self):
        src = b"hello ;c\nfn(a,b,c) ; three args\n quit a+b+c\n"
        # 3 args, threshold 2 → fires.
        assert len(_lint(src, "M-MOD-008", ctx=_ctx(argument_count=2))) == 1
        # 3 args, threshold 5 → silent.
        assert _lint(src, "M-MOD-008", ctx=_ctx(argument_count=5)) == []

    def test_no_formals_no_finding(self):
        # Plain label without parens — no formals node, no finding
        # even at the lowest valid threshold (1).
        src = b"hello ;c\nplain ;c\n s x=1\n quit\n"
        assert _lint(src, "M-MOD-008", ctx=_ctx(argument_count=1)) == []


# ---------------------------------------------------------------------------
# M-MOD-009 — commands per line
# ---------------------------------------------------------------------------


class TestCommandsPerLine:
    def test_silent_at_threshold(self):
        # 3 commands at threshold 3 → silent.
        src = b"hello ;c\n s x=1 s y=2 w x\n quit\n"
        assert _lint(src, "M-MOD-009", ctx=_ctx(commands_per_line=3)) == []

    def test_fires_above_threshold(self):
        # 4 commands, threshold 3 → fires.
        src = b"hello ;c\n s x=1 s y=2 w x w y\n quit\n"
        diags = _lint(src, "M-MOD-009", ctx=_ctx(commands_per_line=3))
        assert len(diags) == 1
        assert "4 commands" in diags[0].message

    def test_threshold_override(self):
        src = b"hello ;c\n s x=1 s y=2\n quit\n"
        # 2 commands, threshold 1 → fires.
        assert len(_lint(src, "M-MOD-009", ctx=_ctx(commands_per_line=1))) == 1
        # 2 commands, threshold 5 → silent.
        assert _lint(src, "M-MOD-009", ctx=_ctx(commands_per_line=5)) == []

    def test_silent_on_blank_or_comment_only_lines(self):
        # Blank and comment-only lines have no command_sequence;
        # even at threshold=1 they don't contribute to the count.
        src = b"hello ;c\n ;just a comment\n\n quit\n"
        # `quit` alone is 1 command at threshold 1 → not over.
        assert _lint(src, "M-MOD-009", ctx=_ctx(commands_per_line=1)) == []


# ===========================================================================
# Phase 4 — Tier 1 concurrency / transaction rules
# ===========================================================================


# ---------------------------------------------------------------------------
# M-MOD-010 — LOCK without timeout (modern, ERROR)
# ---------------------------------------------------------------------------


class TestLockNoTimeoutModern:
    def test_fires_on_plain_lock(self):
        src = b"hello ;c\n LOCK ^X\n QUIT\n"
        diags = _lint(src, "M-MOD-010", ctx=_ctx())
        assert len(diags) == 1
        assert diags[0].severity.value == "error"

    def test_fires_on_incremental_lock_no_timeout(self):
        src = b"hello ;c\n LOCK +^X\n QUIT\n"
        assert len(_lint(src, "M-MOD-010", ctx=_ctx())) == 1

    def test_silent_with_timeout(self):
        src = b"hello ;c\n LOCK ^X:5\n QUIT\n"
        assert _lint(src, "M-MOD-010", ctx=_ctx()) == []

    def test_silent_with_incremental_timeout(self):
        src = b"hello ;c\n LOCK +^X:5\n QUIT\n"
        assert _lint(src, "M-MOD-010", ctx=_ctx()) == []

    def test_silent_on_release_form(self):
        # Release LOCK -^X never needs a timeout — must not fire.
        src = b"hello ;c\n LOCK -^X\n QUIT\n"
        assert _lint(src, "M-MOD-010", ctx=_ctx()) == []

    def test_silent_on_argumentless_lock(self):
        # Argumentless LOCK releases everything; no timeout meaningful.
        src = b"hello ;c\n LOCK \n QUIT\n"
        assert _lint(src, "M-MOD-010", ctx=_ctx()) == []

    def test_handles_multi_arg_lock(self):
        # `LOCK ^X,^Y:5` — first arg has no timeout, second does.
        # First-cut behavior: emit ONE diagnostic per command (the
        # break in the implementation). That captures the issue
        # without flooding.
        src = b"hello ;c\n LOCK ^X,^Y:5\n QUIT\n"
        diags = _lint(src, "M-MOD-010", ctx=_ctx())
        assert len(diags) == 1


# ---------------------------------------------------------------------------
# M-MOD-011 — LOCK acquire/release imbalance per label
# ---------------------------------------------------------------------------


class TestLockLeak:
    def test_fires_on_unmatched_incremental_acquire(self):
        # +^X with no -^X release → leak.
        src = b"hello ;c\n LOCK +^X:5\n SET ^GBL=1\n QUIT\n"
        diags = _lint(src, "M-MOD-011", ctx=_ctx())
        assert len(diags) == 1
        assert "1 incremental acquire" in diags[0].message
        assert "0 release" in diags[0].message

    def test_silent_when_paired(self):
        src = (
            b"hello ;c\n"
            b" LOCK +^X:5\n"
            b" SET ^GBL=1\n"
            b" LOCK -^X\n"
            b" QUIT\n"
        )
        assert _lint(src, "M-MOD-011", ctx=_ctx()) == []

    def test_silent_when_argumentless_lock_releases_all(self):
        # `LOCK ` argumentless releases everything — no leak.
        src = (
            b"hello ;c\n"
            b" LOCK +^X:5\n"
            b" LOCK +^Y:5\n"
            b" SET ^GBL=1\n"
            b" LOCK \n"
            b" QUIT\n"
        )
        assert _lint(src, "M-MOD-011", ctx=_ctx()) == []

    def test_silent_on_plain_lock(self):
        # Plain `LOCK X` (no +/-) is intentionally not counted.
        src = b"hello ;c\n LOCK ^X:5\n QUIT\n"
        assert _lint(src, "M-MOD-011", ctx=_ctx()) == []

    def test_per_label_isolation(self):
        # Two separate labels — each has its own balance check.
        # First leaks; second is balanced.
        src = (
            b"leak ;c\n"
            b" LOCK +^A:5\n"
            b" QUIT\n"
            b"clean ;c\n"
            b" LOCK +^B:5\n"
            b" LOCK -^B\n"
            b" QUIT\n"
        )
        diags = _lint(src, "M-MOD-011", ctx=_ctx())
        assert len(diags) == 1
        assert "'leak'" in diags[0].message


# ---------------------------------------------------------------------------
# M-MOD-012 — TSTART without TCOMMIT/TROLLBACK
# ---------------------------------------------------------------------------


class TestTransactionLeak:
    def test_fires_on_unbalanced_tstart(self):
        src = b"hello ;c\n TSTART\n SET ^GBL=1\n QUIT\n"
        diags = _lint(src, "M-MOD-012", ctx=_ctx())
        assert len(diags) == 1
        assert "1 TSTART" in diags[0].message

    def test_silent_when_tcommit_pairs(self):
        src = b"hello ;c\n TSTART\n SET ^GBL=1\n TCOMMIT\n QUIT\n"
        assert _lint(src, "M-MOD-012", ctx=_ctx()) == []

    def test_silent_when_trollback_pairs(self):
        src = b"hello ;c\n TSTART\n SET ^GBL=1\n TROLLBACK\n QUIT\n"
        assert _lint(src, "M-MOD-012", ctx=_ctx()) == []

    def test_recognises_abbreviations(self):
        # TS + TC abbreviations.
        src = b"hello ;c\n TS\n S ^GBL=1\n TC\n QUIT\n"
        assert _lint(src, "M-MOD-012", ctx=_ctx()) == []

    def test_fires_on_partial_pairing(self):
        # Two TSTARTs, one TCOMMIT — still leaks one.
        src = b"hello ;c\n TSTART\n TSTART\n TCOMMIT\n QUIT\n"
        diags = _lint(src, "M-MOD-012", ctx=_ctx())
        assert len(diags) == 1
        assert "2 TSTART" in diags[0].message
        assert "1 TCOMMIT" in diags[0].message


# ---------------------------------------------------------------------------
# M-MOD-013 — $ETRAP without NEW
# ---------------------------------------------------------------------------


class TestEtrapLeak:
    def test_fires_on_set_without_new(self):
        src = b'hello ;c\n SET $ETRAP="D ERR Q"\n SET X=1\n QUIT\n'
        diags = _lint(src, "M-MOD-013", ctx=_ctx())
        assert len(diags) == 1
        assert "$ETRAP" in diags[0].message

    def test_silent_with_preceding_new(self):
        src = b'hello ;c\n NEW $ETRAP SET $ETRAP="D ERR Q"\n SET X=1\n QUIT\n'
        assert _lint(src, "M-MOD-013", ctx=_ctx()) == []

    def test_silent_with_new_anywhere_in_label(self):
        # NEW after the SET is also fine — same scope.
        src = b'hello ;c\n SET $ETRAP="D ERR Q"\n NEW $ETRAP\n QUIT\n'
        assert _lint(src, "M-MOD-013", ctx=_ctx()) == []

    def test_per_label_scoping(self):
        # Label A has NEW, label B doesn't — only B fires.
        src = (
            b'safe ;c\n'
            b' NEW $ETRAP SET $ETRAP="D HANDLE Q"\n'
            b' QUIT\n'
            b'unsafe ;c\n'
            b' SET $ETRAP="D HANDLE Q"\n'
            b' QUIT\n'
        )
        diags = _lint(src, "M-MOD-013", ctx=_ctx())
        assert len(diags) == 1
        assert diags[0].line >= 4  # in 'unsafe' block


# ---------------------------------------------------------------------------
# M-MOD-014 — OPEN without matching CLOSE
# ---------------------------------------------------------------------------


class TestOpenCloseImbalance:
    def test_fires_on_unmatched_open(self):
        src = b'hello ;c\n OPEN 51:("foo.txt":"R")\n USE 51\n QUIT\n'
        diags = _lint(src, "M-MOD-014", ctx=_ctx())
        assert len(diags) == 1
        assert "1 OPEN" in diags[0].message

    def test_silent_when_paired(self):
        src = b'hello ;c\n OPEN 51:("foo.txt":"R")\n USE 51\n CLOSE 51\n QUIT\n'
        assert _lint(src, "M-MOD-014", ctx=_ctx()) == []

    def test_silent_with_argumentless_close(self):
        # Argumentless `CLOSE` closes every device — no leak.
        src = b'hello ;c\n OPEN 51:("foo.txt":"R")\n CLOSE \n QUIT\n'
        assert _lint(src, "M-MOD-014", ctx=_ctx()) == []

    def test_per_label_isolation(self):
        src = (
            b'leak ;c\n'
            b' OPEN 51:("a.txt":"R")\n'
            b' QUIT\n'
            b'clean ;c\n'
            b' OPEN 52:("b.txt":"R")\n'
            b' CLOSE 52\n'
            b' QUIT\n'
        )
        diags = _lint(src, "M-MOD-014", ctx=_ctx())
        assert len(diags) == 1
        assert "'leak'" in diags[0].message


# ===========================================================================
# Phase 5 — Tier 2 control-flow + correctness rules
# ===========================================================================


# ---------------------------------------------------------------------------
# M-MOD-015 — $SELECT without final default arm
# ---------------------------------------------------------------------------


class TestSelectDefault:
    def test_silent_with_default_arm(self):
        src = b'hello ;c\n S X=$S(A=1:"one",A=2:"two",1:"other")\n Q\n'
        assert _lint(src, "M-MOD-015", ctx=_ctx()) == []

    def test_fires_without_default(self):
        src = b'hello ;c\n S X=$S(A=1:"one",A=2:"two")\n Q\n'
        diags = _lint(src, "M-MOD-015", ctx=_ctx())
        assert len(diags) == 1
        assert "$SELECT" in diags[0].message

    def test_recognises_full_form(self):
        src = b'hello ;c\n S X=$SELECT(A=1:"one")\n Q\n'
        assert len(_lint(src, "M-MOD-015", ctx=_ctx())) == 1

    def test_silent_with_one_only_default_arm(self):
        # `$S(1:val)` is degenerate but technically has a default.
        src = b'hello ;c\n S X=$S(1:"only")\n Q\n'
        assert _lint(src, "M-MOD-015", ctx=_ctx()) == []

    def test_fires_when_last_cond_is_not_literal_one(self):
        # `$S(A:val,B:val2)` — neither is `1:`, so no default.
        src = b'hello ;c\n S X=$S(A:1,B:2)\n Q\n'
        assert len(_lint(src, "M-MOD-015", ctx=_ctx())) == 1


# ---------------------------------------------------------------------------
# M-MOD-016 — Side-effecting postconditional
# ---------------------------------------------------------------------------


class TestPostcondSideEffect:
    def test_fires_on_extrinsic_call_in_postcond(self):
        src = b'hello ;c\n S:$$check(.x) Y=1\n Q\n'
        diags = _lint(src, "M-MOD-016", ctx=_ctx())
        assert len(diags) == 1

    def test_fires_on_increment_in_postcond(self):
        src = b'hello ;c\n W:$INCREMENT(^cnt) "hi",!\n Q\n'
        assert len(_lint(src, "M-MOD-016", ctx=_ctx())) == 1

    def test_silent_on_pure_postcond(self):
        src = b'hello ;c\n S:X=1 Y=2\n W:$L(X)>5 X,!\n Q\n'
        assert _lint(src, "M-MOD-016", ctx=_ctx()) == []

    def test_silent_on_select_in_postcond(self):
        # $SELECT is pure — must not fire.
        src = b'hello ;c\n S:$S(X=1:1,1:0) Y=2\n Q\n'
        assert _lint(src, "M-MOD-016", ctx=_ctx()) == []


# ---------------------------------------------------------------------------
# M-MOD-018 — Argumentless FOR without conditional exit
# ---------------------------------------------------------------------------


class TestForNoQuit:
    def test_fires_on_argless_for_with_no_q(self):
        src = b'hello ;c\n F  W "infinite",!\n Q\n'
        diags = _lint(src, "M-MOD-018", ctx=_ctx())
        assert len(diags) == 1

    def test_silent_with_q_postcond(self):
        src = b'hello ;c\n F  Q:done  W "loop",!\n Q\n'
        assert _lint(src, "M-MOD-018", ctx=_ctx()) == []

    def test_silent_with_for_args(self):
        # `F I=1:1:10` has its own bound — never an "infinite" risk.
        src = b'hello ;c\n F I=1:1:10 W I,!\n Q\n'
        assert _lint(src, "M-MOD-018", ctx=_ctx()) == []

    def test_silent_with_goto_postcond(self):
        # `G:done end` is also a valid exit.
        src = b'hello ;c\n F  G:done end  W "loop",!\nend Q\n'
        assert _lint(src, "M-MOD-018", ctx=_ctx()) == []


# ---------------------------------------------------------------------------
# M-MOD-019 — Broad pattern operator
# ---------------------------------------------------------------------------


class TestBroadPattern:
    def test_fires_on_dot_E(self):
        src = b'hello ;c\n S X=Y?.E\n Q\n'
        diags = _lint(src, "M-MOD-019", ctx=_ctx())
        assert len(diags) == 1
        assert "?.E" in diags[0].message

    def test_silent_on_constrained_pattern(self):
        # `?1A.AN` is "one alpha, then any alphanumerics" — constrains.
        src = b'hello ;c\n S X=Y?1A.AN\n Q\n'
        assert _lint(src, "M-MOD-019", ctx=_ctx()) == []

    def test_silent_on_richer_pattern(self):
        # `?.E1A.E` requires at least one alpha somewhere — also fine.
        src = b'hello ;c\n S X=Y?.E1A.E\n Q\n'
        assert _lint(src, "M-MOD-019", ctx=_ctx()) == []


# ---------------------------------------------------------------------------
# M-MOD-020 — By-reference unused intra-routine
# ---------------------------------------------------------------------------


class TestByrefUnused:
    def test_fires_on_unused_byref(self):
        # caller passes .unused; callee never writes p1.
        src = (
            b'caller ;c\n'
            b' D handler(.unused,.touched)\n'
            b' Q\n'
            b'handler(p1,p2) ;c\n'
            b' S p2=99\n'
            b' Q\n'
        )
        diags = _lint(src, "M-MOD-020", ctx=_ctx())
        # Only the first byref (p1) should fire; p2 IS written.
        assert len(diags) == 1
        assert ".unused" in diags[0].message
        assert "p1" in diags[0].message

    def test_silent_when_all_byrefs_written(self):
        src = (
            b'caller ;c\n'
            b' D handler(.a,.b)\n'
            b' Q\n'
            b'handler(p1,p2) ;c\n'
            b' S p1=1\n'
            b' S p2=2\n'
            b' Q\n'
        )
        assert _lint(src, "M-MOD-020", ctx=_ctx()) == []

    def test_skips_cross_routine_calls(self):
        # `D ^helper(.x)` — cross-routine; deferred to Phase 7.
        src = b'caller ;c\n D ^helper(.x)\n Q\n'
        assert _lint(src, "M-MOD-020", ctx=_ctx()) == []

    def test_silent_when_callee_unknown(self):
        # Calling a label that doesn't exist in this file — no formals
        # to compare against, so silent (M-XINDX-014 will catch the
        # missing label separately).
        src = b'caller ;c\n D missing(.x)\n Q\n'
        assert _lint(src, "M-MOD-020", ctx=_ctx()) == []

    def test_extrinsic_byref(self):
        # `S X=$$check(.var)` — extrinsic call form also detected.
        src = (
            b'caller ;c\n'
            b' S X=$$check(.unused)\n'
            b' Q\n'
            b'check(p) ;c\n'
            b' Q 1\n'
        )
        diags = _lint(src, "M-MOD-020", ctx=_ctx())
        assert len(diags) == 1
        assert ".unused" in diags[0].message


# ===========================================================================
# Phase 6 — Engine-aware Z-extension allowlists
# ===========================================================================


def _engine_ctx(engine: str) -> LintContext:
    """Build a LintContext with the given target_engine (defaults
    elsewhere)."""
    from m_cli.lint.thresholds import validate as validate_thresholds

    return LintContext(
        thresholds=validate_thresholds(None),
        target_engine=engine,
    )


# ---------------------------------------------------------------------------
# M-MOD-021 — Z-command engine-aware
# ---------------------------------------------------------------------------


class TestZCommandEngineAware:
    def test_strict_any_flags_zbreak(self):
        # ZBREAK is an extension on both engines, so portable code
        # ("any") should flag it.
        src = b"hello ;c\n ZBREAK ENT^FOO\n QUIT\n"
        diags = _lint(src, "M-MOD-021", ctx=_engine_ctx("any"))
        assert len(diags) == 1
        assert "ZBREAK" in diags[0].message

    def test_yottadb_silent_on_zbreak(self):
        src = b"hello ;c\n ZBREAK ENT^FOO\n QUIT\n"
        assert _lint(src, "M-MOD-021", ctx=_engine_ctx("yottadb")) == []

    def test_iris_silent_on_zbreak(self):
        # ZBREAK is multi-vendor — both engines accept it.
        src = b"hello ;c\n ZBREAK ENT^FOO\n QUIT\n"
        assert _lint(src, "M-MOD-021", ctx=_engine_ctx("iris")) == []

    def test_silent_on_ansi_command(self):
        # SET, WRITE, QUIT are ANSI — never flagged regardless of engine.
        src = b'hello ;c\n SET X=1 WRITE X,! QUIT\n'
        for engine in ("any", "yottadb", "iris"):
            assert _lint(src, "M-MOD-021", ctx=_engine_ctx(engine)) == []


# ---------------------------------------------------------------------------
# M-MOD-022 — $Z* ISV engine-aware
# ---------------------------------------------------------------------------


class TestZIsvEngineAware:
    def test_strict_any_flags_zhorolog(self):
        src = b'hello ;c\n W $ZHOROLOG,!\n Q\n'
        diags = _lint(src, "M-MOD-022", ctx=_engine_ctx("any"))
        assert len(diags) == 1
        assert "$ZHOROLOG" in diags[0].message

    def test_yottadb_silent_on_zhorolog(self):
        # $ZHOROLOG is in both engines; YottaDB target should accept.
        src = b'hello ;c\n W $ZHOROLOG,!\n Q\n'
        assert _lint(src, "M-MOD-022", ctx=_engine_ctx("yottadb")) == []

    def test_iris_silent_on_zhorolog(self):
        src = b'hello ;c\n W $ZHOROLOG,!\n Q\n'
        assert _lint(src, "M-MOD-022", ctx=_engine_ctx("iris")) == []

    def test_silent_on_ansi_isv(self):
        # $HOROLOG, $JOB, $TEST are ANSI — never flagged.
        src = b'hello ;c\n W $HOROLOG,! W $JOB,! W $TEST,!\n Q\n'
        for engine in ("any", "yottadb", "iris"):
            assert _lint(src, "M-MOD-022", ctx=_engine_ctx(engine)) == []


# ---------------------------------------------------------------------------
# M-MOD-023 — $Z* function engine-aware
# ---------------------------------------------------------------------------


class TestZFunctionEngineAware:
    def test_strict_any_flags_zsearch(self):
        src = b'hello ;c\n W $ZSEARCH("*.m"),!\n Q\n'
        diags = _lint(src, "M-MOD-023", ctx=_engine_ctx("any"))
        assert len(diags) == 1
        assert "$ZSEARCH" in diags[0].message

    def test_silent_on_pure_intrinsics(self):
        # $LENGTH, $EXTRACT, $SELECT are ANSI — never flagged.
        src = b'hello ;c\n W $L("hi"),! W $E("hi",1,1),!\n Q\n'
        for engine in ("any", "yottadb", "iris"):
            assert _lint(src, "M-MOD-023", ctx=_engine_ctx(engine)) == []

    def test_silent_when_target_is_implementing_engine(self):
        # $ZSEARCH is in both YDB and IRIS — neither target should
        # complain.
        src = b'hello ;c\n W $ZSEARCH("*.m"),!\n Q\n'
        assert _lint(src, "M-MOD-023", ctx=_engine_ctx("yottadb")) == []
        assert _lint(src, "M-MOD-023", ctx=_engine_ctx("iris")) == []


# ---------------------------------------------------------------------------
# engine_allowlist — the helper backing the three rules
# ---------------------------------------------------------------------------


class TestEngineAllowlist:
    def test_any_subset_of_yottadb(self):
        # Every ANSI command is also in the YDB allowlist.
        from m_cli.lint._keywords import engine_allowlist

        ansi_cmds = engine_allowlist("any", "command")
        ydb_cmds = engine_allowlist("yottadb", "command")
        assert ansi_cmds <= ydb_cmds

    def test_any_subset_of_iris(self):
        from m_cli.lint._keywords import engine_allowlist

        ansi_cmds = engine_allowlist("any", "command")
        iris_cmds = engine_allowlist("iris", "command")
        assert ansi_cmds <= iris_cmds

    def test_unknown_engine_falls_back_to_strictest(self):
        from m_cli.lint._keywords import engine_allowlist

        ansi = engine_allowlist("any", "isv")
        unknown = engine_allowlist("borogroves", "isv")
        assert ansi == unknown


# ===========================================================================
# Phase 8 — Documentation + style polish
# ===========================================================================


# ---------------------------------------------------------------------------
# M-MOD-028 — label docstring
# ---------------------------------------------------------------------------


class TestLabelDocstring:
    def test_silent_with_header_comment(self):
        src = b"hello ; sums two ints\n quit\n"
        assert _lint(src, "M-MOD-028", ctx=_ctx()) == []

    def test_silent_with_first_body_comment(self):
        src = b"hello\n ; the docstring\n quit\n"
        assert _lint(src, "M-MOD-028", ctx=_ctx()) == []

    def test_fires_when_no_doc(self):
        src = b"hello\n s X=1\n quit\n"
        diags = _lint(src, "M-MOD-028", ctx=_ctx())
        assert len(diags) == 1
        assert "hello" in diags[0].message


# ---------------------------------------------------------------------------
# M-MOD-029 — comment density
# ---------------------------------------------------------------------------


class TestCommentDensity:
    def test_skips_short_bodies(self):
        # Body of 2 lines — exempt regardless of density.
        src = b"hello ;c\n s X=1\n q\n"
        assert _lint(src, "M-MOD-029", ctx=_ctx()) == []

    def test_fires_below_threshold(self):
        # 10 non-blank body lines, no comments → 0% density at threshold 10%.
        src = (
            b"hello ;c\n"
            + b"".join(f" s V{i}={i}\n".encode() for i in range(10))
            + b" quit\n"
        )
        diags = _lint(src, "M-MOD-029", ctx=_ctx())
        assert len(diags) == 1

    def test_silent_above_threshold(self):
        # 5 commented lines, 5 code lines → 50% density well above 10%.
        src = (
            b"hello ;c\n"
            + b"".join(
                f" ;comment {i}\n s V{i}={i}\n".encode() for i in range(5)
            )
            + b" quit\n"
        )
        assert _lint(src, "M-MOD-029", ctx=_ctx()) == []

    def test_threshold_override(self):
        # 10% default already silent at 50%; lower threshold to 80%
        # forces a fire.
        src = (
            b"hello ;c\n"
            + b"".join(
                f" ;comment {i}\n s V{i}={i}\n".encode() for i in range(5)
            )
            + b" quit\n"
        )
        assert (
            len(_lint(src, "M-MOD-029", ctx=_ctx(comment_density_pct=80))) == 1
        )


# ---------------------------------------------------------------------------
# M-MOD-030 — TODO / FIXME ownership
# ---------------------------------------------------------------------------


class TestTodoOwnership:
    def test_fires_on_bare_todo(self):
        src = b"hello ;c\n ;TODO add validation\n quit\n"
        diags = _lint(src, "M-MOD-030", ctx=_ctx())
        assert len(diags) == 1
        assert "TODO" in diags[0].message

    def test_silent_with_paren_owner(self):
        src = b"hello ;c\n ;TODO(rafael) handle null\n quit\n"
        assert _lint(src, "M-MOD-030", ctx=_ctx()) == []

    def test_silent_with_at_owner(self):
        src = b"hello ;c\n ;FIXME @rafael revisit\n quit\n"
        assert _lint(src, "M-MOD-030", ctx=_ctx()) == []

    def test_silent_with_ticket(self):
        src = b"hello ;c\n ;XXX [PROJ-123] race\n quit\n"
        assert _lint(src, "M-MOD-030", ctx=_ctx()) == []

    def test_silent_with_jira_style_ticket(self):
        # PROJ-99 directly in the comment.
        src = b"hello ;c\n ;HACK PROJ-99 monkey-patch\n quit\n"
        assert _lint(src, "M-MOD-030", ctx=_ctx()) == []

    def test_recognises_all_markers(self):
        src = (
            b"hello ;c\n"
            b" ;TODO bare1\n"
            b" ;FIXME bare2\n"
            b" ;XXX bare3\n"
            b" ;HACK bare4\n"
            b" quit\n"
        )
        assert len(_lint(src, "M-MOD-030", ctx=_ctx())) == 4


# ---------------------------------------------------------------------------
# M-MOD-031 — magic numbers
# ---------------------------------------------------------------------------


class TestMagicNumber:
    def test_silent_on_exempt_set(self):
        src = b"hello ;c\n s A=0\n s B=1\n s C=2\n s D=-1\n quit\n"
        assert _lint(src, "M-MOD-031", ctx=_ctx()) == []

    def test_fires_on_42(self):
        src = b"hello ;c\n s A=42\n quit\n"
        diags = _lint(src, "M-MOD-031", ctx=_ctx())
        assert len(diags) == 1
        assert "42" in diags[0].message

    def test_fires_on_negative_99(self):
        src = b"hello ;c\n s A=-99\n quit\n"
        diags = _lint(src, "M-MOD-031", ctx=_ctx())
        assert len(diags) == 1
        assert "-99" in diags[0].message

    def test_silent_in_for_step(self):
        # F I=1:1:10 — the 10 is in argument_postconditional, exempt.
        src = b"hello ;c\n f I=1:1:10 s X(I)=I\n quit\n"
        assert _lint(src, "M-MOD-031", ctx=_ctx()) == []


# ---------------------------------------------------------------------------
# M-MOD-032 — single-letter variable
# ---------------------------------------------------------------------------


class TestSingleLetterVar:
    def test_fires_on_X_outside_for(self):
        src = b"hello ;c\n s X=42\n quit\n"
        diags = _lint(src, "M-MOD-032", ctx=_ctx())
        assert len(diags) == 1

    def test_silent_on_for_counter(self):
        # I is a FOR counter somewhere; exempt globally in this file.
        src = b"hello ;c\n f I=1:1:5 w I,!\n quit\n"
        assert _lint(src, "M-MOD-032", ctx=_ctx()) == []

    def test_silent_on_multi_char_name(self):
        src = b"hello ;c\n s count=42\n quit\n"
        assert _lint(src, "M-MOD-032", ctx=_ctx()) == []

    def test_for_counter_exempted_file_wide(self):
        # I is FOR counter in `counter` label; even in `other` label,
        # I won't be flagged because the exemption is file-wide.
        src = (
            b"counter ;c\n f I=1:1:5 w I,!\n q\n"
            b"other ;c\n s I=99\n q\n"
        )
        # `I=99` is a magic number too, but for M-MOD-032 only test
        # the single-letter aspect — should be silent.
        diags = _lint(src, "M-MOD-032", ctx=_ctx())
        # "I" is exempt; nothing else single-letter in the file.
        assert diags == []


# ---------------------------------------------------------------------------
# M-MOD-033 — argumentless NEW
# ---------------------------------------------------------------------------


class TestArglessNew:
    def test_fires_on_argless_new(self):
        src = b"hello ;c\n NEW \n quit\n"
        diags = _lint(src, "M-MOD-033", ctx=_ctx())
        assert len(diags) == 1

    def test_fires_on_abbrev_argless(self):
        src = b"hello ;c\n N \n quit\n"
        assert len(_lint(src, "M-MOD-033", ctx=_ctx())) == 1

    def test_silent_with_args(self):
        src = b"hello ;c\n NEW X,Y\n quit\n"
        assert _lint(src, "M-MOD-033", ctx=_ctx()) == []

    def test_silent_with_exclusive_form(self):
        # NEW (X,Y) — exclusive new; has argument_list.
        src = b"hello ;c\n NEW (X,Y)\n quit\n"
        assert _lint(src, "M-MOD-033", ctx=_ctx()) == []


# ---------------------------------------------------------------------------
# M-MOD-034 — SET X=X+N → $INCREMENT
# ---------------------------------------------------------------------------


class TestSetIncrement:
    def test_fires_on_plus_one(self):
        src = b"hello ;c\n s counter=counter+1\n quit\n"
        diags = _lint(src, "M-MOD-034", ctx=_ctx())
        assert len(diags) == 1
        assert "$INCREMENT(counter)" in diags[0].message

    def test_fires_on_minus_one(self):
        src = b"hello ;c\n s counter=counter-1\n quit\n"
        diags = _lint(src, "M-MOD-034", ctx=_ctx())
        assert len(diags) == 1
        assert "$INCREMENT(counter,-1)" in diags[0].message

    def test_fires_on_plus_n(self):
        src = b"hello ;c\n s tally=tally+10\n quit\n"
        diags = _lint(src, "M-MOD-034", ctx=_ctx())
        assert len(diags) == 1
        assert "$INCREMENT(tally,10)" in diags[0].message

    def test_silent_when_lhs_rhs_differ(self):
        # `s a=b+1` — different vars; not an increment of `a`.
        src = b"hello ;c\n s a=b+1\n quit\n"
        assert _lint(src, "M-MOD-034", ctx=_ctx()) == []

    def test_silent_on_multiplication(self):
        # `s x=x*2` — not an additive increment.
        src = b"hello ;c\n s x=x*2\n quit\n"
        assert _lint(src, "M-MOD-034", ctx=_ctx()) == []


# ---------------------------------------------------------------------------
# M-MOD-035 — $Z* function abbreviation
# ---------------------------------------------------------------------------


class TestZFunctionCanonical:
    def test_fires_on_dollar_zd(self):
        src = b'hello ;c\n W $ZD($H,1),!\n Q\n'
        diags = _lint(src, "M-MOD-035", ctx=_ctx())
        assert len(diags) == 1
        assert "$ZD" in diags[0].message
        assert "$ZDATE" in diags[0].message

    def test_silent_on_canonical_name(self):
        src = b'hello ;c\n W $ZDATE($H,1),!\n Q\n'
        assert _lint(src, "M-MOD-035", ctx=_ctx()) == []


# ---------------------------------------------------------------------------
# M-MOD-024 — Read of local before any SET on every prior path
# ---------------------------------------------------------------------------
#
# Phase 7 first user-visible rule: reads the per-label CFG and
# definite-assignment analyzer (m_cli.lint.flow) and flags a use
# of a local variable that is NOT in the "definitely defined"
# set when the use occurs.


class TestReadOfUndefined:
    def test_fires_on_read_of_never_set_local(self):
        """``W X`` with X never SET — uninitialized read."""
        src = b"LBL\n W X\n Q\n"
        diags = _lint(src, "M-MOD-024", ctx=_ctx())
        assert len(diags) == 1
        assert diags[0].rule_id == "M-MOD-024"
        assert "X" in diags[0].message
        assert diags[0].line == 2

    def test_silent_after_set(self):
        """``S X=1 W X`` — X is definitely defined when read."""
        src = b"LBL\n S X=1\n W X\n Q\n"
        assert _lint(src, "M-MOD-024", ctx=_ctx()) == []

    def test_silent_on_formal_parameter(self):
        """Formals are definitely defined at label entry."""
        src = b"LBL(A,B)\n W A,B\n Q\n"
        assert _lint(src, "M-MOD-024", ctx=_ctx()) == []

    def test_fires_after_conditional_set(self):
        """``S:cond X=1`` does not definitely define X — subsequent
        read is unsafe."""
        src = b"LBL(C)\n S:C=1 X=2\n W X\n Q\n"
        diags = _lint(src, "M-MOD-024", ctx=_ctx())
        assert any(d.rule_id == "M-MOD-024" and "X" in d.message for d in diags)

    def test_fires_after_kill(self):
        """``S X=1 K X W X`` — X was killed; reading is unsafe."""
        src = b"LBL\n S X=1\n K X\n W X\n Q\n"
        diags = _lint(src, "M-MOD-024", ctx=_ctx())
        assert any(d.rule_id == "M-MOD-024" and "X" in d.message for d in diags)

    def test_fires_on_read_in_postconditional(self):
        """``Q:Y=1`` reads Y in the condition; Y was never set."""
        src = b"LBL\n Q:Y=1\n Q\n"
        diags = _lint(src, "M-MOD-024", ctx=_ctx())
        assert any(d.rule_id == "M-MOD-024" and "Y" in d.message for d in diags)

    def test_silent_on_global_read(self):
        """``W ^X`` reads a global; M-MOD-024 only tracks locals."""
        src = b"LBL\n W ^X\n Q\n"
        assert _lint(src, "M-MOD-024", ctx=_ctx()) == []

    def test_dedups_repeated_use_of_same_undefined_local(self):
        """A var read several times with no intervening SET produces
        ONE diagnostic per (label, var) — not one per use site —
        to keep signal high on long-running undefined-read patterns."""
        src = b"LBL\n W X\n W X\n W X\n Q\n"
        diags = [d for d in _lint(src, "M-MOD-024", ctx=_ctx()) if d.rule_id == "M-MOD-024"]
        assert len(diags) == 1
        assert "X" in diags[0].message

    def test_separate_labels_track_independently(self):
        """``X`` undefined in LBL1 but DEFINED-and-USED in LBL2 —
        only LBL1's read fires."""
        src = b"LBL1\n W X\n Q\nLBL2\n S X=1 W X\n Q\n"
        diags = [d for d in _lint(src, "M-MOD-024", ctx=_ctx()) if d.rule_id == "M-MOD-024"]
        assert len(diags) == 1
        assert diags[0].line == 2

    def test_silent_on_set_x_reads_x_after_initialization(self):
        """The ``S X=X+1`` increment pattern: X is read AND defined.
        After a prior ``S X=0``, the read is safe."""
        src = b"LBL\n S X=0\n S X=X+1\n Q\n"
        assert _lint(src, "M-MOD-024", ctx=_ctx()) == []

    def test_fires_on_set_x_reads_x_without_prior_initialization(self):
        """Same ``S X=X+1`` pattern, but X was never previously set —
        the RHS read of X is uninitialized."""
        src = b"LBL\n S X=X+1\n Q\n"
        diags = [d for d in _lint(src, "M-MOD-024", ctx=_ctx()) if d.rule_id == "M-MOD-024"]
        assert len(diags) == 1
        assert "X" in diags[0].message

    def test_silent_on_byref_passing_pattern(self):
        """The m-tools test-framework idiom:

            new pass,fail
            do start^TESTRUN(.pass,.fail)
            do report^TESTRUN(pass,fail)

        ``new`` un-defines pass/fail; the by-ref ``do start^TESTRUN``
        call defines them (callee initializes); subsequent by-value
        read in ``do report^TESTRUN(pass,fail)`` is safe."""
        src = (
            b"SUITE\n"
            b" new pass,fail\n"
            b" do start^TESTRUN(.pass,.fail)\n"
            b" do report^TESTRUN(pass,fail)\n"
            b" quit\n"
        )
        diags = [d for d in _lint(src, "M-MOD-024", ctx=_ctx()) if d.rule_id == "M-MOD-024"]
        assert diags == []

    def test_silent_on_cross_argument_def_then_use(self):
        """``S A=1, B=A`` — multi-argument SET with a use of A in arg 2.
        M evaluates left-to-right, so A is defined when arg 2 reads it.
        The rule must walk arguments per-arg with running defs."""
        src = b"LBL\n S A=1, B=A\n Q\n"
        diags = [d for d in _lint(src, "M-MOD-024", ctx=_ctx()) if d.rule_id == "M-MOD-024"]
        assert diags == []


# ---------------------------------------------------------------------------
# M-MOD-025 — LOCK leak across exit paths (path-sensitive)
# ---------------------------------------------------------------------------


class TestLockLeakPathSensitive:
    def test_fires_when_lock_held_on_any_exit_path(self):
        """``L +X`` then ``Q:cond`` then ``L -X`` then ``Q``.

        The Q:cond branch exits while X is still held — leak."""
        src = b"LBL(C)\n L +X\n Q:C=1\n L -X\n Q\n"
        diags = [d for d in _lint(src, "M-MOD-025", ctx=_ctx()) if d.rule_id == "M-MOD-025"]
        assert len(diags) == 1
        assert "X" in diags[0].message

    def test_silent_when_release_on_every_path(self):
        """Unconditional acquire + unconditional release — no leak."""
        src = b"LBL\n L +X\n L -X\n Q\n"
        assert _lint(src, "M-MOD-025", ctx=_ctx()) == []

    def test_silent_with_argumentless_release(self):
        """``L +X`` then ``L`` (release-all) — no leak."""
        src = b"LBL\n L +X\n L \n Q\n"
        assert _lint(src, "M-MOD-025", ctx=_ctx()) == []

    def test_fires_on_multiple_leaked_locks(self):
        """Multiple LOCK targets leaked → one diagnostic per target."""
        src = b"LBL\n L +A,+B,+C\n Q\n"
        diags = [d for d in _lint(src, "M-MOD-025", ctx=_ctx()) if d.rule_id == "M-MOD-025"]
        assert len(diags) == 3
        assert {d.message.split("'")[1] for d in diags} == {"A", "B", "C"}

    def test_silent_when_no_locks_at_all(self):
        src = b"LBL\n S X=1\n Q\n"
        assert _lint(src, "M-MOD-025", ctx=_ctx()) == []

    def test_anchors_diagnostic_on_label_header(self):
        """The diagnostic line points at the label header, not at
        the QUIT — so an editor outline shows the leak right at the
        label name."""
        src = b"LBL\n L +X\n Q\n"
        diags = [d for d in _lint(src, "M-MOD-025", ctx=_ctx()) if d.rule_id == "M-MOD-025"]
        assert len(diags) == 1
        assert diags[0].line == 1  # the label header

    def test_each_label_independent(self):
        """LBL1 leaks; LBL2 clean — only one finding."""
        src = b"LBL1\n L +X\n Q\nLBL2\n L +Y\n L -Y\n Q\n"
        diags = [d for d in _lint(src, "M-MOD-025", ctx=_ctx()) if d.rule_id == "M-MOD-025"]
        assert len(diags) == 1
        assert "X" in diags[0].message


# ---------------------------------------------------------------------------
# M-MOD-026 — TSTART leak across exit paths (path-sensitive)
# ---------------------------------------------------------------------------


class TestTransactionLeakPathSensitive:
    def test_fires_on_unbalanced_tstart(self):
        """``TSTART`` then ``Q:cond`` then ``TCOMMIT`` — early exit
        leaks an open transaction."""
        src = b"LBL(C)\n TSTART\n Q:C=1\n TCOMMIT\n Q\n"
        diags = [d for d in _lint(src, "M-MOD-026", ctx=_ctx()) if d.rule_id == "M-MOD-026"]
        assert len(diags) == 1
        assert "Transaction" in diags[0].message

    def test_silent_on_balanced(self):
        """``TSTART`` then ``TCOMMIT`` on every path — clean."""
        src = b"LBL\n TSTART\n TCOMMIT\n Q\n"
        assert _lint(src, "M-MOD-026", ctx=_ctx()) == []

    def test_silent_on_trollback_close(self):
        """``TROLLBACK`` also closes the transaction."""
        src = b"LBL\n TSTART\n TROLLBACK\n Q\n"
        assert _lint(src, "M-MOD-026", ctx=_ctx()) == []

    def test_fires_when_no_close(self):
        """Plain ``TSTART`` with no closer — leak."""
        src = b"LBL\n TSTART\n Q\n"
        diags = [d for d in _lint(src, "M-MOD-026", ctx=_ctx()) if d.rule_id == "M-MOD-026"]
        assert len(diags) == 1
        assert "depth 1" in diags[0].message

    def test_fires_on_nested_unclosed(self):
        """Nested TSTART without matching TCOMMITs — depth > 1 at exit."""
        src = b"LBL\n TSTART\n TSTART\n Q\n"
        diags = [d for d in _lint(src, "M-MOD-026", ctx=_ctx()) if d.rule_id == "M-MOD-026"]
        assert len(diags) == 1
        assert "depth 2" in diags[0].message

    def test_silent_on_no_transactions(self):
        src = b"LBL\n S X=1\n Q\n"
        assert _lint(src, "M-MOD-026", ctx=_ctx()) == []

    def test_anchors_diagnostic_on_label_header(self):
        src = b"LBL\n TSTART\n Q\n"
        diags = [d for d in _lint(src, "M-MOD-026", ctx=_ctx()) if d.rule_id == "M-MOD-026"]
        assert len(diags) == 1
        assert diags[0].line == 1


# ---------------------------------------------------------------------------
# M-MOD-027 — $ETRAP leak across exit paths (path-sensitive)
# ---------------------------------------------------------------------------


class TestEtrapLeakPathSensitive:
    def test_fires_on_set_etrap_without_new(self):
        """Setting $ETRAP without prior NEW $ETRAP — handler escapes."""
        src = b'LBL\n S $ETRAP="D ^HANDLE"\n Q\n'
        diags = [d for d in _lint(src, "M-MOD-027", ctx=_ctx()) if d.rule_id == "M-MOD-027"]
        assert len(diags) == 1
        assert "$ETRAP" in diags[0].message

    def test_silent_when_new_etrap_precedes(self):
        """``NEW $ETRAP`` then ``SET $ETRAP=...`` — protected."""
        src = b'LBL\n N $ETRAP\n S $ETRAP="D ^HANDLE"\n Q\n'
        assert _lint(src, "M-MOD-027", ctx=_ctx()) == []

    def test_silent_when_new_et_abbrev_precedes(self):
        """``NEW $ET`` is the abbreviation."""
        src = b'LBL\n N $ET\n S $ETRAP="D ^HANDLE"\n Q\n'
        assert _lint(src, "M-MOD-027", ctx=_ctx()) == []

    def test_fires_when_new_only_on_some_paths(self):
        """``Q:cond`` exits early; later branch does NEW $ETRAP then SET.
        Wait — once we get past the early Q, NEW happens before SET.
        The leak case is: SET happens BEFORE NEW on some path."""
        src = (
            b"LBL(C)\n"
            b' S $ETRAP="early"\n'  # leak: no NEW yet
            b" N $ETRAP\n"
            b' S $ETRAP="protected"\n'
            b" Q\n"
        )
        diags = [d for d in _lint(src, "M-MOD-027", ctx=_ctx()) if d.rule_id == "M-MOD-027"]
        # The first SET fires; the second is protected.
        assert len(diags) == 1
        assert diags[0].line == 2

    def test_silent_on_no_etrap_set(self):
        """``SET X="x"`` is unrelated."""
        src = b'LBL\n S X="x"\n Q\n'
        assert _lint(src, "M-MOD-027", ctx=_ctx()) == []

    def test_silent_on_argumentless_new(self):
        """``NEW`` (argumentless) doesn't protect $ETRAP — but no
        SET $ETRAP follows here, so no diagnostic either."""
        src = b"LBL\n N\n S X=1\n Q\n"
        assert _lint(src, "M-MOD-027", ctx=_ctx()) == []

    def test_fires_on_argumentless_new_followed_by_set_etrap(self):
        """Argumentless ``NEW`` does NOT protect $ETRAP. SET still leaks."""
        src = b'LBL\n N\n S $ETRAP="x"\n Q\n'
        diags = [d for d in _lint(src, "M-MOD-027", ctx=_ctx()) if d.rule_id == "M-MOD-027"]
        assert len(diags) == 1
