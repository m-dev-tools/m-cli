"""Tests for the LSP ``textDocument/documentHighlight`` handler — Stage 4b.

When the cursor is on a multi-character identifier, every same-name
occurrence inside the document is highlighted. Single-character
tokens are ignored to avoid noisy matches against ``X``, ``Y``, etc.
"""

from __future__ import annotations

from lsprotocol.types import (
    DocumentHighlightParams,
    Position,
    TextDocumentIdentifier,
    TextDocumentItem,
)
from pygls.workspace import TextDocument

from m_cli.lsp.server import document_highlights_at, text_document_document_highlight


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


def _open(srv: FakeServer, uri: str, src: str) -> None:
    srv.workspace.put_text_document(TextDocumentItem(uri=uri, language_id="m", version=1, text=src))


def test_highlight_finds_every_occurrence_in_file() -> None:
    srv = FakeServer()
    uri = "file:///tmp/h.m"
    src = "H ;c\n SET COUNT=1\n SET COUNT=COUNT+1\n W COUNT\n"
    _open(srv, uri, src)

    # Cursor on the first COUNT (line 1, column 5).
    highs = document_highlights_at(srv, uri, Position(line=1, character=5))

    assert highs is not None
    # COUNT appears 4 times: line 1 col 5, line 2 cols 5 and 11, line 3 col 3.
    starts = sorted((h.range.start.line, h.range.start.character) for h in highs)
    assert starts == [(1, 5), (2, 5), (2, 11), (3, 3)]


def test_highlight_word_boundary_avoids_substring_match() -> None:
    """``X`` inside ``XCOORD`` should not match a hover on plain ``XX``."""
    srv = FakeServer()
    uri = "file:///tmp/h.m"
    _open(srv, uri, "H ;c\n SET XX=1\n SET XXY=2\n")

    highs = document_highlights_at(srv, uri, Position(line=1, character=5))

    assert highs is not None
    # XX must not match inside XXY.
    starts = [(h.range.start.line, h.range.start.character) for h in highs]
    assert starts == [(1, 5)]


def test_highlight_returns_none_for_short_token() -> None:
    """Single-character names (X, Y, S as in commands) are too noisy."""
    srv = FakeServer()
    uri = "file:///tmp/h.m"
    _open(srv, uri, "H ;c\n S X=1\n W X\n")

    assert document_highlights_at(srv, uri, Position(line=1, character=3)) is None


def test_highlight_returns_none_outside_token() -> None:
    srv = FakeServer()
    uri = "file:///tmp/h.m"
    _open(srv, uri, "H ;c\n SET COUNT=1\n")

    # Position 0 on line 1 is whitespace.
    assert document_highlights_at(srv, uri, Position(line=1, character=0)) is None


def test_highlight_skips_non_m_files() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.py"
    _open(srv, uri, "count = 1\nprint(count)\n")
    assert document_highlights_at(srv, uri, Position(line=0, character=2)) is None


def test_highlight_dispatches_through_handler() -> None:
    srv = FakeServer()
    uri = "file:///tmp/h.m"
    _open(srv, uri, "H ;c\n SET COUNT=1\n W COUNT\n")
    params = DocumentHighlightParams(
        text_document=TextDocumentIdentifier(uri=uri),
        position=Position(line=1, character=5),
    )
    highs = text_document_document_highlight(srv, params)
    assert highs is not None
    assert len(highs) == 2
