"""Tests for the Phase D cross-routine lint rules.

These rules need a ``WorkspaceIndex`` passed as a 5th positional arg
to their ``check`` function. The runner provides it; here we build
small two-file workspaces in tmp dirs and invoke ``lint_source``
directly with the workspace argument.
"""

from __future__ import annotations

from pathlib import Path

from m_cli.lint.diagnostic import Severity
from m_cli.lint.rules import _REGISTRY, all_rules
from m_cli.lint.runner import lint_source
from m_cli.workspace import WorkspaceIndex


def _index_files(*paths: Path) -> WorkspaceIndex:
    idx = WorkspaceIndex()
    for p in paths:
        idx.add_file(p, p.read_bytes())
    return idx


# ---------------------------------------------------------------------------
# M-XINDX-007 — call to undefined routine
# ---------------------------------------------------------------------------


def test_xindx_007_flags_call_to_unknown_routine(tmp_path: Path) -> None:
    caller = tmp_path / "CALLER.m"
    caller.write_bytes(b"CALLER ;c\n D LABEL^MISSING\n QUIT\n")
    idx = _index_files(caller)

    rule = next(r for r in all_rules() if r.id == "M-XINDX-007")
    diags = lint_source(caller, caller.read_bytes(), [rule], workspace=idx)

    rule_ids = [d.rule_id for d in diags]
    assert "M-XINDX-007" in rule_ids
    finding = next(d for d in diags if d.rule_id == "M-XINDX-007")
    assert "MISSING" in finding.message
    assert finding.severity == Severity.FATAL


def test_xindx_007_silent_when_routine_exists(tmp_path: Path) -> None:
    other = tmp_path / "OTHER.m"
    other.write_bytes(b"OTHER ;c\n QUIT\nINNER ;c\n QUIT\n")
    caller = tmp_path / "CALLER.m"
    caller.write_bytes(b"CALLER ;c\n D INNER^OTHER\n QUIT\n")
    idx = _index_files(other, caller)

    rule = next(r for r in all_rules() if r.id == "M-XINDX-007")
    diags = lint_source(caller, caller.read_bytes(), [rule], workspace=idx)

    assert not any(d.rule_id == "M-XINDX-007" for d in diags)


def test_xindx_007_skips_intra_routine_calls(tmp_path: Path) -> None:
    """``$$LABEL`` inside FOO.m targets FOO; the missing label is
    M-XINDX-014's territory, not ours."""
    foo = tmp_path / "FOO.m"
    # No INNER label declared — but reference is intra-routine.
    foo.write_bytes(b"FOO ;c\n W $$INNER\n QUIT\n")
    idx = _index_files(foo)

    rule = next(r for r in all_rules() if r.id == "M-XINDX-007")
    diags = lint_source(foo, foo.read_bytes(), [rule], workspace=idx)

    assert not any(d.rule_id == "M-XINDX-007" for d in diags)


# ---------------------------------------------------------------------------
# M-XINDX-008 — call to undefined label in another routine
# ---------------------------------------------------------------------------


def test_xindx_008_flags_call_to_unknown_label(tmp_path: Path) -> None:
    other = tmp_path / "OTHER.m"
    other.write_bytes(b"OTHER ;c\n QUIT\nKNOWN ;c\n QUIT\n")
    caller = tmp_path / "CALLER.m"
    caller.write_bytes(b"CALLER ;c\n D MISSING^OTHER\n QUIT\n")
    idx = _index_files(other, caller)

    rule = next(r for r in all_rules() if r.id == "M-XINDX-008")
    diags = lint_source(caller, caller.read_bytes(), [rule], workspace=idx)

    finding = next((d for d in diags if d.rule_id == "M-XINDX-008"), None)
    assert finding is not None
    assert "MISSING" in finding.message
    assert "OTHER" in finding.message


def test_xindx_008_silent_when_label_exists(tmp_path: Path) -> None:
    other = tmp_path / "OTHER.m"
    other.write_bytes(b"OTHER ;c\n QUIT\nKNOWN ;c\n QUIT\n")
    caller = tmp_path / "CALLER.m"
    caller.write_bytes(b"CALLER ;c\n D KNOWN^OTHER\n QUIT\n")
    idx = _index_files(other, caller)

    rule = next(r for r in all_rules() if r.id == "M-XINDX-008")
    diags = lint_source(caller, caller.read_bytes(), [rule], workspace=idx)

    assert not any(d.rule_id == "M-XINDX-008" for d in diags)


def test_xindx_008_skips_caret_routine_form(tmp_path: Path) -> None:
    """``^ROUTINE`` (no label named) doesn't have a label to validate."""
    other = tmp_path / "OTHER.m"
    other.write_bytes(b"OTHER ;c\n QUIT\n")
    caller = tmp_path / "CALLER.m"
    # ``$$^OTHER`` — caret-only extrinsic form. M parser may or may not
    # emit this; we just need to verify the rule doesn't panic on it.
    caller.write_bytes(b"CALLER ;c\n D ^OTHER\n QUIT\n")
    idx = _index_files(other, caller)

    rule = next(r for r in all_rules() if r.id == "M-XINDX-008")
    diags = lint_source(caller, caller.read_bytes(), [rule], workspace=idx)
    # Whatever the parser does with `D ^OTHER`, M-XINDX-008 should not
    # claim a missing label — there's no label named.
    assert not any(d.rule_id == "M-XINDX-008" for d in diags)


def test_xindx_008_silent_when_target_routine_unknown(tmp_path: Path) -> None:
    """If the target routine doesn't exist either, that's M-XINDX-007's
    finding — M-XINDX-008 would just duplicate the noise."""
    caller = tmp_path / "CALLER.m"
    caller.write_bytes(b"CALLER ;c\n D LABEL^MISSING\n QUIT\n")
    idx = _index_files(caller)

    rule = next(r for r in all_rules() if r.id == "M-XINDX-008")
    diags = lint_source(caller, caller.read_bytes(), [rule], workspace=idx)

    assert not any(d.rule_id == "M-XINDX-008" for d in diags)


# ---------------------------------------------------------------------------
# M-XINDX-049 — label declared but never referenced
# ---------------------------------------------------------------------------


def test_xindx_049_flags_unused_label(tmp_path: Path) -> None:
    foo = tmp_path / "FOO.m"
    foo.write_bytes(b"FOO ;c\n QUIT\nUSED ;c\n QUIT\nUNUSED ;c\n QUIT\n")
    caller = tmp_path / "CALLER.m"
    caller.write_bytes(b"CALLER ;c\n D USED^FOO\n QUIT\n")
    idx = _index_files(foo, caller)

    rule = next(r for r in all_rules() if r.id == "M-XINDX-049")
    diags = lint_source(foo, foo.read_bytes(), [rule], workspace=idx)

    flagged = [d for d in diags if d.rule_id == "M-XINDX-049"]
    flagged_names = [d.message for d in flagged]
    assert any("UNUSED" in m for m in flagged_names)
    assert not any("USED" in m and "UNUSED" not in m for m in flagged_names)


def test_xindx_049_exempts_routine_entry_label(tmp_path: Path) -> None:
    """The first label (matches filename stem) is conventionally
    callable as ``D ^ROUTINE`` even when no site references it."""
    foo = tmp_path / "FOO.m"
    foo.write_bytes(b"FOO ;c\n QUIT\nINNER ;c\n QUIT\n")
    idx = _index_files(foo)
    # No callers anywhere — but FOO label is still the routine entry.

    rule = next(r for r in all_rules() if r.id == "M-XINDX-049")
    diags = lint_source(foo, foo.read_bytes(), [rule], workspace=idx)

    msgs = [d.message for d in diags if d.rule_id == "M-XINDX-049"]
    # FOO is exempt; INNER fires.
    assert not any("FOO" in m and "INNER" not in m for m in msgs)
    assert any("INNER" in m for m in msgs)


def test_xindx_049_silent_when_label_referenced(tmp_path: Path) -> None:
    foo = tmp_path / "FOO.m"
    foo.write_bytes(b"FOO ;c\n QUIT\nINNER ;c\n QUIT\n")
    caller = tmp_path / "CALLER.m"
    caller.write_bytes(b"CALLER ;c\n D INNER^FOO\n QUIT\n")
    idx = _index_files(foo, caller)

    rule = next(r for r in all_rules() if r.id == "M-XINDX-049")
    diags = lint_source(foo, foo.read_bytes(), [rule], workspace=idx)
    assert not any(d.rule_id == "M-XINDX-049" for d in diags)


# ---------------------------------------------------------------------------
# Runner integration
# ---------------------------------------------------------------------------


def test_workspace_rules_skipped_when_no_workspace(tmp_path: Path) -> None:
    """Without a workspace passed, cross-routine rules silently no-op
    (single-file lint can't validate cross-routine references)."""
    caller = tmp_path / "CALLER.m"
    caller.write_bytes(b"CALLER ;c\n D LABEL^MISSING\n QUIT\n")

    rule = _REGISTRY["M-XINDX-007"]
    diags = lint_source(caller, caller.read_bytes(), [rule])  # no workspace

    assert not any(d.rule_id == "M-XINDX-007" for d in diags)


def test_all_three_rules_carry_needs_workspace_flag() -> None:
    for rid in ("M-XINDX-007", "M-XINDX-008", "M-XINDX-049"):
        rule = _REGISTRY[rid]
        assert rule.needs_workspace is True, f"{rid} missing needs_workspace=True"
