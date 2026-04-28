"""Tests for the LSP ``textDocument/definition`` handler — Phase B.

Resolves ``LABEL^ROUTINE`` / ``^ROUTINE`` / local-label references
under the cursor against a workspace symbol index, returning a
``Location`` the editor can jump to.
"""

from __future__ import annotations

from pathlib import Path

from lsprotocol.types import (
    DefinitionParams,
    Position,
    TextDocumentIdentifier,
    TextDocumentItem,
)
from pygls.workspace import TextDocument

from m_cli.lsp.server import definition_at, text_document_definition
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


def test_definition_jumps_to_cross_routine_label(tmp_path: Path) -> None:
    other = tmp_path / "OTHER.m"
    other.write_bytes(b"OTHER ;c\n QUIT\nINNER ;c\n QUIT\n")
    idx = WorkspaceIndex()
    idx.add_file(other, other.read_bytes())

    srv = FakeServer()
    srv.m_cli_workspace_index = idx
    caller_uri = (tmp_path / "CALLER.m").as_uri()
    _open(srv, caller_uri, " D INNER^OTHER\n")

    loc = definition_at(srv, caller_uri, Position(line=0, character=4))

    assert loc is not None
    assert loc.uri == other.as_uri()
    # INNER is on line 3 (1-indexed) → 0-indexed line 2.
    assert loc.range.start.line == 2


def test_definition_caret_routine_jumps_to_first_label(tmp_path: Path) -> None:
    other = tmp_path / "OTHER.m"
    other.write_bytes(b"OTHER ;c\n QUIT\nINNER ;c\n QUIT\n")
    idx = WorkspaceIndex()
    idx.add_file(other, other.read_bytes())

    srv = FakeServer()
    srv.m_cli_workspace_index = idx
    caller_uri = (tmp_path / "CALLER.m").as_uri()
    _open(srv, caller_uri, " D ^OTHER\n")

    loc = definition_at(srv, caller_uri, Position(line=0, character=5))

    assert loc is not None
    assert loc.uri == other.as_uri()
    # OTHER is on line 1 → 0-indexed line 0.
    assert loc.range.start.line == 0


def test_definition_local_label_resolves_within_current_doc(tmp_path: Path) -> None:
    """``D LBL`` (no ``^routine``) resolves against the current doc's
    labels, not the workspace index."""
    srv = FakeServer()
    srv.m_cli_workspace_index = WorkspaceIndex()
    uri = "file:///tmp/H.m"
    src = "H ;c\n D INNER\n QUIT\nINNER ;c\n QUIT\n"
    _open(srv, uri, src)

    loc = definition_at(srv, uri, Position(line=1, character=4))

    assert loc is not None
    assert loc.uri == uri
    assert loc.range.start.line == 3


def test_definition_returns_none_for_unknown_routine(tmp_path: Path) -> None:
    srv = FakeServer()
    srv.m_cli_workspace_index = WorkspaceIndex()
    uri = (tmp_path / "C.m").as_uri()
    _open(srv, uri, " D LABEL^MISSING\n")

    assert definition_at(srv, uri, Position(line=0, character=4)) is None


def test_definition_returns_none_when_not_on_reference(tmp_path: Path) -> None:
    srv = FakeServer()
    srv.m_cli_workspace_index = WorkspaceIndex()
    uri = (tmp_path / "C.m").as_uri()
    _open(srv, uri, "H ;c\n SET X=1\n")

    # Cursor on whitespace between ``SET`` and ``X``.
    assert definition_at(srv, uri, Position(line=1, character=4)) is None


def test_definition_skips_non_m_files() -> None:
    srv = FakeServer()
    srv.m_cli_workspace_index = WorkspaceIndex()
    uri = "file:///tmp/hello.py"
    _open(srv, uri, "import this\n")

    assert definition_at(srv, uri, Position(line=0, character=0)) is None


def test_definition_returns_none_when_no_index_attached() -> None:
    """If the server hasn't built a workspace index yet, cross-routine
    definitions just return None — no crash."""
    srv = FakeServer()
    srv.m_cli_workspace_index = None
    uri = "file:///tmp/C.m"
    _open(srv, uri, " D LABEL^OTHER\n")

    assert definition_at(srv, uri, Position(line=0, character=4)) is None


def test_definition_dispatches_through_handler(tmp_path: Path) -> None:
    other = tmp_path / "OTHER.m"
    other.write_bytes(b"OTHER ;c\n QUIT\n")
    idx = WorkspaceIndex()
    idx.add_file(other, other.read_bytes())

    srv = FakeServer()
    srv.m_cli_workspace_index = idx
    caller_uri = (tmp_path / "CALLER.m").as_uri()
    _open(srv, caller_uri, " D ^OTHER\n")

    params = DefinitionParams(
        text_document=TextDocumentIdentifier(uri=caller_uri),
        position=Position(line=0, character=5),
    )
    loc = text_document_definition(srv, params)
    assert loc is not None
    assert loc.uri == other.as_uri()
