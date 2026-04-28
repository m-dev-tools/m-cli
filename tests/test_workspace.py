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
