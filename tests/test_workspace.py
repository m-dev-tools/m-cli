"""Tests for ``m_cli.workspace`` — symbol index + reference parsing."""

from __future__ import annotations

from pathlib import Path

from m_cli.workspace import (
    Reference,
    WorkspaceIndex,
    build_index,
    reference_at,
)

# ---------------------------------------------------------------------------
# WorkspaceIndex — add / lookup / remove
# ---------------------------------------------------------------------------


def test_add_file_indexes_every_label() -> None:
    idx = WorkspaceIndex()
    src = b"HELLO ;c\n SET X=1\n QUIT\nINNER(a,b) ;c\n QUIT\n"
    idx.add_file(Path("/tmp/HELLO.m"), src)

    locs = idx.all_locations()
    assert {(loc.routine, loc.label, loc.line) for loc in locs} == {
        ("HELLO", "HELLO", 1),
        ("HELLO", "INNER", 4),
    }


def test_lookup_label_in_routine() -> None:
    idx = WorkspaceIndex()
    idx.add_file(
        Path("/tmp/HELLO.m"),
        b"HELLO ;c\n QUIT\nINNER ;c\n QUIT\n",
    )

    loc = idx.lookup("HELLO", "INNER")
    assert loc is not None
    assert loc.line == 3


def test_lookup_caret_routine_returns_first_label() -> None:
    """``^ROUTINE`` resolves to the routine entry — the first label."""
    idx = WorkspaceIndex()
    idx.add_file(
        Path("/tmp/HELLO.m"),
        b"HELLO ;c\n QUIT\nINNER ;c\n QUIT\n",
    )

    loc = idx.lookup("HELLO", None)
    assert loc is not None
    assert loc.label == "HELLO"
    assert loc.line == 1


def test_lookup_is_case_insensitive() -> None:
    idx = WorkspaceIndex()
    idx.add_file(Path("/tmp/HELLO.m"), b"HELLO ;c\n QUIT\nINNER ;c\n QUIT\n")

    assert idx.lookup("hello", "inner") is not None
    assert idx.lookup("HELLO", "Inner") is not None


def test_lookup_unknown_returns_none() -> None:
    idx = WorkspaceIndex()
    idx.add_file(Path("/tmp/HELLO.m"), b"HELLO ;c\n QUIT\n")

    assert idx.lookup("MISSING", None) is None
    assert idx.lookup("HELLO", "MISSING") is None


def test_remove_file_drops_its_labels() -> None:
    idx = WorkspaceIndex()
    idx.add_file(Path("/tmp/HELLO.m"), b"HELLO ;c\n QUIT\n")
    idx.add_file(Path("/tmp/OTHER.m"), b"OTHER ;c\n QUIT\n")

    idx.remove_file(Path("/tmp/HELLO.m"))

    assert idx.lookup("HELLO", None) is None
    assert idx.lookup("OTHER", None) is not None


def test_add_file_replaces_prior_entries_for_same_path() -> None:
    """Re-adding a file (e.g. after edit) shouldn't accumulate stale labels."""
    idx = WorkspaceIndex()
    p = Path("/tmp/HELLO.m")
    idx.add_file(p, b"HELLO ;c\n QUIT\nOLD ;c\n QUIT\n")
    idx.add_file(p, b"HELLO ;c\n QUIT\nNEW ;c\n QUIT\n")

    assert idx.lookup("HELLO", "OLD") is None
    assert idx.lookup("HELLO", "NEW") is not None


def test_routine_name_comes_from_filename_not_first_label() -> None:
    """Some real-world M files name the routine differently from the file
    stem. ydb resolves by stem; we mirror that."""
    idx = WorkspaceIndex()
    idx.add_file(Path("/tmp/RENAMED.m"), b"OLDNAME ;c\n QUIT\n")

    loc = idx.lookup("RENAMED", None)
    assert loc is not None
    assert loc.label == "OLDNAME"


# ---------------------------------------------------------------------------
# build_index — directory walk
# ---------------------------------------------------------------------------


def test_build_index_walks_directories(tmp_path: Path) -> None:
    (tmp_path / "HELLO.m").write_bytes(b"HELLO ;c\n QUIT\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "OTHER.m").write_bytes(b"OTHER ;c\n QUIT\n")
    (tmp_path / "ignored.txt").write_text("not M")

    idx = build_index([tmp_path])

    assert idx.lookup("HELLO", None) is not None
    assert idx.lookup("OTHER", None) is not None
    assert len(idx) == 2


def test_build_index_skips_unreadable_files(tmp_path: Path, monkeypatch) -> None:
    """An OSError on read shouldn't kill the whole build."""
    bad = tmp_path / "BAD.m"
    bad.write_bytes(b"BAD ;c\n QUIT\n")
    good = tmp_path / "GOOD.m"
    good.write_bytes(b"GOOD ;c\n QUIT\n")

    real_read = Path.read_bytes

    def flaky(self):
        if self.name == "BAD.m":
            raise OSError("nope")
        return real_read(self)

    monkeypatch.setattr(Path, "read_bytes", flaky)

    idx = build_index([tmp_path])
    assert idx.lookup("GOOD", None) is not None
    assert idx.lookup("BAD", None) is None


def test_build_index_dedups_overlapping_roots(tmp_path: Path) -> None:
    (tmp_path / "HELLO.m").write_bytes(b"HELLO ;c\n QUIT\n")

    idx = build_index([tmp_path, tmp_path])

    assert len(idx) == 1


# ---------------------------------------------------------------------------
# reference_at — cursor-position parsing
# ---------------------------------------------------------------------------


def test_reference_at_label_caret_routine() -> None:
    line = " D LABEL^OTHER"
    # Cursor on the LABEL part.
    ref = reference_at(line, 4)
    assert ref == Reference(label="LABEL", routine="OTHER")


def test_reference_at_caret_routine_only() -> None:
    line = " D ^OTHER"
    ref = reference_at(line, 5)
    assert ref == Reference(label=None, routine="OTHER")


def test_reference_at_extrinsic_with_routine() -> None:
    line = " W $$LABEL^FOO(x)"
    ref = reference_at(line, 6)
    assert ref == Reference(label="LABEL", routine="FOO")


def test_reference_at_extrinsic_without_routine() -> None:
    line = " W $$LABEL(x)"
    ref = reference_at(line, 6)
    assert ref == Reference(label="LABEL", routine=None)


def test_reference_at_bare_label_call() -> None:
    line = " D LBL"
    ref = reference_at(line, 4)
    assert ref == Reference(label="LBL", routine=None)


def test_reference_at_cursor_on_routine_half_resolves_full() -> None:
    """Cursor on the routine part of LABEL^ROUTINE should still
    return the full reference, not just the routine."""
    line = " D LABEL^OTHER"
    ref = reference_at(line, 11)  # cursor inside OTHER
    assert ref == Reference(label="LABEL", routine="OTHER")


def test_reference_at_whitespace_returns_none() -> None:
    assert reference_at("   ", 1) is None


def test_reference_at_out_of_range_returns_none() -> None:
    assert reference_at("LBL", -1) is None
    assert reference_at("LBL", 99) is None


# ---------------------------------------------------------------------------
# WorkspaceIndex.references_to — call-site indexing
# ---------------------------------------------------------------------------


def test_references_to_finds_label_caret_routine_calls(tmp_path: Path) -> None:
    """``D INNER^OTHER`` is indexed as a reference to (OTHER, INNER)."""
    other = tmp_path / "OTHER.m"
    other.write_bytes(b"OTHER ;c\n QUIT\nINNER ;c\n QUIT\n")
    caller = tmp_path / "CALLER.m"
    caller.write_bytes(b"CALLER ;c\n D INNER^OTHER\n QUIT\n")

    idx = WorkspaceIndex()
    idx.add_file(other, other.read_bytes())
    idx.add_file(caller, caller.read_bytes())

    refs = idx.references_to("OTHER", "INNER")
    assert len(refs) == 1
    assert refs[0].path == caller
    assert refs[0].line == 2


def test_references_to_finds_extrinsic_function_calls(tmp_path: Path) -> None:
    """``$$INNER^OTHER(x)`` is indexed as a reference."""
    caller = tmp_path / "CALLER.m"
    caller.write_bytes(b"CALLER ;c\n W $$INNER^OTHER(1)\n QUIT\n")

    idx = WorkspaceIndex()
    idx.add_file(caller, caller.read_bytes())

    refs = idx.references_to("OTHER", "INNER")
    assert len(refs) == 1


def test_references_to_intra_routine_extrinsic_uses_filename_stem(tmp_path: Path) -> None:
    """``$$INNER(x)`` (no ^routine) inside FOO.m targets (FOO, INNER).

    The bare ``D INNER`` form (no ``$$``, no ``^``) is intentionally
    NOT indexed — tree-sitter-m parses it as a ``variable`` node which
    is overloaded with actual variable access, so indexing it would
    produce false-positive references. The extrinsic form has the
    ``$$`` prefix the parser uses to disambiguate."""
    foo = tmp_path / "FOO.m"
    foo.write_bytes(b"FOO ;c\n W $$INNER(1)\n QUIT\nINNER(x) ;c\n QUIT x+1\n")

    idx = WorkspaceIndex()
    idx.add_file(foo, foo.read_bytes())

    refs = idx.references_to("FOO", "INNER")
    assert any(r.line == 2 for r in refs)


def test_references_to_is_case_insensitive(tmp_path: Path) -> None:
    caller = tmp_path / "C.m"
    caller.write_bytes(b"C ;c\n D inner^other\n QUIT\n")

    idx = WorkspaceIndex()
    idx.add_file(caller, caller.read_bytes())

    assert len(idx.references_to("OTHER", "INNER")) == 1
    assert len(idx.references_to("other", "inner")) == 1


def test_references_to_remove_file_drops_call_sites(tmp_path: Path) -> None:
    caller = tmp_path / "C.m"
    caller.write_bytes(b"C ;c\n D INNER^OTHER\n QUIT\n")

    idx = WorkspaceIndex()
    idx.add_file(caller, caller.read_bytes())
    assert len(idx.references_to("OTHER", "INNER")) == 1

    idx.remove_file(caller)
    assert idx.references_to("OTHER", "INNER") == []


def test_references_to_returns_empty_for_unknown_target(tmp_path: Path) -> None:
    idx = WorkspaceIndex()
    assert idx.references_to("NEVER", "EXISTED") == []


def test_references_to_carries_column_range(tmp_path: Path) -> None:
    """Column / end_column point at the call header (LABEL^ROUTINE) so
    the LSP can render a proper Range for the editor highlight."""
    caller = tmp_path / "C.m"
    src = b" D INNER^OTHER\n"
    caller.write_bytes(src)

    idx = WorkspaceIndex()
    idx.add_file(caller, src)

    refs = idx.references_to("OTHER", "INNER")
    assert len(refs) == 1
    # The ` D ` prefix is 3 chars; INNER^OTHER is 11 chars long.
    assert refs[0].column == 3
    assert refs[0].end_column == 3 + len("INNER^OTHER")
