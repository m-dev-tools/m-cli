"""Tests for the Phase B LSP textDocument/references and workspace/symbol handlers."""

from __future__ import annotations

from pathlib import Path

from lsprotocol.types import (
    DidChangeWatchedFilesParams,
    FileChangeType,
    FileEvent,
    Position,
    ReferenceContext,
    ReferenceParams,
    SymbolKind,
    TextDocumentIdentifier,
    TextDocumentItem,
    WorkspaceSymbolParams,
)
from pygls.workspace import TextDocument

from m_cli.lsp.server import (
    did_change_watched_files,
    references_at,
    text_document_references,
    update_index_for_uri,
    workspace_symbol_handler,
    workspace_symbols_for,
)
from m_cli.workspace import WorkspaceIndex


class FakeWorkspace:
    def __init__(self) -> None:
        self._docs: dict[str, TextDocument] = {}

    def put_text_document(self, item: TextDocumentItem) -> None:
        self._docs[item.uri] = TextDocument(uri=item.uri, source=item.text, version=item.version)

    def get_text_document(self, uri: str) -> TextDocument:
        return self._docs[uri]


class FakeServer:
    def __init__(self) -> None:
        self.workspace = FakeWorkspace()
        self.m_cli_workspace_index: WorkspaceIndex | None = None


def _open(srv: FakeServer, uri: str, src: str) -> None:
    srv.workspace.put_text_document(TextDocumentItem(uri=uri, language_id="m", version=1, text=src))


# ---------------------------------------------------------------------------
# references_at
# ---------------------------------------------------------------------------


def test_references_at_returns_call_sites_from_index(tmp_path: Path) -> None:
    other = tmp_path / "OTHER.m"
    other.write_bytes(b"OTHER ;c\n QUIT\nINNER ;c\n QUIT\n")
    caller = tmp_path / "CALLER.m"
    caller.write_bytes(b"CALLER ;c\n D INNER^OTHER\n QUIT\n")

    idx = WorkspaceIndex()
    idx.add_file(other, other.read_bytes())
    idx.add_file(caller, caller.read_bytes())

    srv = FakeServer()
    srv.m_cli_workspace_index = idx
    caller_uri = caller.as_uri()
    _open(srv, caller_uri, caller.read_text())

    # Cursor on INNER in `D INNER^OTHER`.
    locs = references_at(srv, caller_uri, Position(line=1, character=4))

    assert locs is not None
    # Caller site + declaration (include_declaration default True).
    uris = {loc.uri for loc in locs}
    assert caller.as_uri() in uris
    assert other.as_uri() in uris


def test_references_at_excludes_declaration_when_requested(tmp_path: Path) -> None:
    other = tmp_path / "OTHER.m"
    other.write_bytes(b"OTHER ;c\n QUIT\nINNER ;c\n QUIT\n")
    caller = tmp_path / "CALLER.m"
    caller.write_bytes(b"CALLER ;c\n D INNER^OTHER\n QUIT\n")

    idx = WorkspaceIndex()
    idx.add_file(other, other.read_bytes())
    idx.add_file(caller, caller.read_bytes())

    srv = FakeServer()
    srv.m_cli_workspace_index = idx
    caller_uri = caller.as_uri()
    _open(srv, caller_uri, caller.read_text())

    locs = references_at(
        srv, caller_uri, Position(line=1, character=4), include_declaration=False
    )

    assert locs is not None
    uris = {loc.uri for loc in locs}
    assert other.as_uri() not in uris


def test_references_at_finds_calls_when_cursor_on_declaration(tmp_path: Path) -> None:
    """Cursor on the label declaration (column 0) returns inbound references."""
    other = tmp_path / "OTHER.m"
    other.write_bytes(b"OTHER ;c\n QUIT\nINNER ;c\n QUIT\n")
    caller = tmp_path / "CALLER.m"
    caller.write_bytes(b"CALLER ;c\n D INNER^OTHER\n QUIT\n")

    idx = WorkspaceIndex()
    idx.add_file(other, other.read_bytes())
    idx.add_file(caller, caller.read_bytes())

    srv = FakeServer()
    srv.m_cli_workspace_index = idx
    other_uri = other.as_uri()
    _open(srv, other_uri, other.read_text())

    # Cursor on INNER's declaration line (line 2, 0-indexed).
    locs = references_at(srv, other_uri, Position(line=2, character=2), include_declaration=False)

    assert locs is not None
    assert any(loc.uri == caller.as_uri() for loc in locs)


def test_references_at_returns_none_for_non_m_files() -> None:
    srv = FakeServer()
    srv.m_cli_workspace_index = WorkspaceIndex()
    _open(srv, "file:///tmp/x.py", "import this\n")
    assert references_at(srv, "file:///tmp/x.py", Position(line=0, character=0)) is None


def test_references_at_returns_empty_when_no_index(tmp_path: Path) -> None:
    """Server hasn't built an index yet → empty references list, not crash."""
    srv = FakeServer()
    srv.m_cli_workspace_index = None
    uri = (tmp_path / "C.m").as_uri()
    _open(srv, uri, " D INNER^OTHER\n")
    locs = references_at(srv, uri, Position(line=0, character=4))
    assert locs == []


def test_references_at_dispatches_through_handler(tmp_path: Path) -> None:
    other = tmp_path / "OTHER.m"
    other.write_bytes(b"OTHER ;c\n QUIT\nINNER ;c\n QUIT\n")
    caller = tmp_path / "CALLER.m"
    caller.write_bytes(b"CALLER ;c\n D INNER^OTHER\n QUIT\n")

    idx = WorkspaceIndex()
    idx.add_file(other, other.read_bytes())
    idx.add_file(caller, caller.read_bytes())

    srv = FakeServer()
    srv.m_cli_workspace_index = idx
    caller_uri = caller.as_uri()
    _open(srv, caller_uri, caller.read_text())

    params = ReferenceParams(
        text_document=TextDocumentIdentifier(uri=caller_uri),
        position=Position(line=1, character=4),
        context=ReferenceContext(include_declaration=False),
    )
    locs = text_document_references(srv, params)
    assert locs is not None
    assert other.as_uri() not in {loc.uri for loc in locs}


# ---------------------------------------------------------------------------
# workspace/symbol
# ---------------------------------------------------------------------------


def test_workspace_symbols_for_returns_all_when_query_empty(tmp_path: Path) -> None:
    foo = tmp_path / "FOO.m"
    foo.write_bytes(b"FOO ;c\n QUIT\nINNER ;c\n QUIT\n")
    idx = WorkspaceIndex()
    idx.add_file(foo, foo.read_bytes())

    srv = FakeServer()
    srv.m_cli_workspace_index = idx

    syms = workspace_symbols_for(srv, "")
    names = sorted(s.name for s in syms)
    assert names == ["FOO^FOO", "INNER^FOO"]


def test_workspace_symbols_for_filters_by_substring(tmp_path: Path) -> None:
    foo = tmp_path / "FOO.m"
    foo.write_bytes(b"FOO ;c\n QUIT\nINNER ;c\n QUIT\nOUTER ;c\n QUIT\n")
    idx = WorkspaceIndex()
    idx.add_file(foo, foo.read_bytes())

    srv = FakeServer()
    srv.m_cli_workspace_index = idx

    syms = workspace_symbols_for(srv, "INN")
    assert [s.name for s in syms] == ["INNER^FOO"]


def test_workspace_symbols_match_routine_name(tmp_path: Path) -> None:
    foo = tmp_path / "FOO.m"
    foo.write_bytes(b"FOO ;c\n QUIT\n")
    bar = tmp_path / "BAR.m"
    bar.write_bytes(b"BAR ;c\n QUIT\n")
    idx = WorkspaceIndex()
    idx.add_file(foo, foo.read_bytes())
    idx.add_file(bar, bar.read_bytes())

    srv = FakeServer()
    srv.m_cli_workspace_index = idx

    syms = workspace_symbols_for(srv, "BAR")
    assert [s.name for s in syms] == ["BAR^BAR"]


def test_workspace_symbols_kind_is_function() -> None:
    foo_path = Path("/tmp/FOO.m")
    idx = WorkspaceIndex()
    idx.add_file(foo_path, b"FOO ;c\n QUIT\n")

    srv = FakeServer()
    srv.m_cli_workspace_index = idx

    syms = workspace_symbols_for(srv, "")
    assert all(s.kind == SymbolKind.Function for s in syms)


def test_workspace_symbols_returns_empty_when_no_index() -> None:
    srv = FakeServer()
    srv.m_cli_workspace_index = None
    assert workspace_symbols_for(srv, "anything") == []


def test_workspace_symbol_handler_dispatches(tmp_path: Path) -> None:
    foo = tmp_path / "FOO.m"
    foo.write_bytes(b"FOO ;c\n QUIT\n")
    idx = WorkspaceIndex()
    idx.add_file(foo, foo.read_bytes())

    srv = FakeServer()
    srv.m_cli_workspace_index = idx

    params = WorkspaceSymbolParams(query="FOO")
    syms = workspace_symbol_handler(srv, params)
    assert len(syms) == 1


# ---------------------------------------------------------------------------
# didChangeWatchedFiles + didSave incremental updates
# ---------------------------------------------------------------------------


def test_did_change_watched_files_reindexes_changed_file(tmp_path: Path) -> None:
    foo = tmp_path / "FOO.m"
    foo.write_bytes(b"FOO ;c\n QUIT\nOLD ;c\n QUIT\n")

    idx = WorkspaceIndex()
    idx.add_file(foo, foo.read_bytes())
    assert idx.lookup("FOO", "OLD") is not None

    # Edit the file on disk: replace OLD with NEW.
    foo.write_bytes(b"FOO ;c\n QUIT\nNEW ;c\n QUIT\n")

    srv = FakeServer()
    srv.m_cli_workspace_index = idx
    params = DidChangeWatchedFilesParams(
        changes=[FileEvent(uri=foo.as_uri(), type=FileChangeType.Changed)]
    )
    did_change_watched_files(srv, params)

    assert idx.lookup("FOO", "OLD") is None
    assert idx.lookup("FOO", "NEW") is not None


def test_did_change_watched_files_drops_deleted_file(tmp_path: Path) -> None:
    foo = tmp_path / "FOO.m"
    foo.write_bytes(b"FOO ;c\n QUIT\nINNER ;c\n QUIT\n")
    idx = WorkspaceIndex()
    idx.add_file(foo, foo.read_bytes())
    assert idx.lookup("FOO", "INNER") is not None

    foo.unlink()
    srv = FakeServer()
    srv.m_cli_workspace_index = idx
    did_change_watched_files(
        srv,
        DidChangeWatchedFilesParams(
            changes=[FileEvent(uri=foo.as_uri(), type=FileChangeType.Deleted)]
        ),
    )

    assert idx.lookup("FOO", "INNER") is None


def test_did_change_watched_files_ignores_non_m_files(tmp_path: Path) -> None:
    """A change to a .py file shouldn't crash or mutate the index."""
    idx = WorkspaceIndex()
    srv = FakeServer()
    srv.m_cli_workspace_index = idx

    did_change_watched_files(
        srv,
        DidChangeWatchedFilesParams(
            changes=[FileEvent(uri="file:///tmp/x.py", type=FileChangeType.Changed)]
        ),
    )
    # No crash; index untouched.
    assert len(idx) == 0


def test_update_index_for_uri_uses_in_memory_doc_source(tmp_path: Path) -> None:
    """didSave path: re-index from the workspace document, not disk.
    This catches edits that haven't been persisted to the FS yet."""
    foo = tmp_path / "FOO.m"
    foo.write_bytes(b"FOO ;c\n QUIT\nDISK ;c\n QUIT\n")
    idx = WorkspaceIndex()
    idx.add_file(foo, foo.read_bytes())

    srv = FakeServer()
    srv.m_cli_workspace_index = idx
    # Open a different in-memory version of the same file.
    _open(srv, foo.as_uri(), "FOO ;c\n QUIT\nMEMORY ;c\n QUIT\n")

    update_index_for_uri(srv, foo.as_uri())

    assert idx.lookup("FOO", "DISK") is None
    assert idx.lookup("FOO", "MEMORY") is not None
