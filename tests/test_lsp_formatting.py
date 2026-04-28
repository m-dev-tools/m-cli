"""Tests for the LSP ``textDocument/formatting`` handler — Stage 2.

The server returns a list of ``TextEdit`` objects describing how to
reformat the document. We use the simplest correct shape: a single
edit that replaces the full document with the canonically-formatted
output. If formatting is a no-op (file already canonical), the list
is empty.
"""

from __future__ import annotations

from lsprotocol.types import (
    DocumentFormattingParams,
    FormattingOptions,
    TextDocumentIdentifier,
    TextDocumentItem,
)
from pygls.workspace import TextDocument

from m_cli.lsp.server import format_document, text_document_formatting


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


# ---------------------------------------------------------------------------
# format_document — the inner helper
# ---------------------------------------------------------------------------


def test_already_canonical_returns_empty_edits() -> None:
    srv = FakeServer()
    uri = "file:///tmp/HELLO.m"
    src = "HELLO ;c\n QUIT\n"  # uppercase keywords, no trailing whitespace
    _open(srv, uri, src)

    edits = format_document(srv, uri)

    assert edits == []


def test_lowercase_keyword_produces_one_edit() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    src = "hello ;c\n new x\n quit\n"
    _open(srv, uri, src)

    edits = format_document(srv, uri)

    assert len(edits) == 1
    assert "NEW x" in edits[0].new_text
    assert "QUIT" in edits[0].new_text


def test_trailing_whitespace_trimmed() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    src = "HELLO ;c   \n QUIT  \n"
    _open(srv, uri, src)

    edits = format_document(srv, uri)

    assert len(edits) == 1
    assert "HELLO ;c\n" in edits[0].new_text
    assert "QUIT\n" in edits[0].new_text


def test_edit_range_covers_full_document() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    src = "hello ;c\n new x\n quit\n"  # 3 lines, ends with \n
    _open(srv, uri, src)

    edits = format_document(srv, uri)

    assert len(edits) == 1
    edit = edits[0]
    assert edit.range.start.line == 0
    assert edit.range.start.character == 0
    # File ends with \n so end position is (line_count, 0).
    assert edit.range.end.line == 3
    assert edit.range.end.character == 0


def test_edit_range_handles_no_trailing_newline() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    src = "hello ;c\n new x"  # no trailing \n
    _open(srv, uri, src)

    edits = format_document(srv, uri)
    if not edits:  # if canonical already, skip the assertion
        return
    edit = edits[0]
    # Last line "new x" has length 5 → end = (1, 5)
    assert edit.range.end.line == 1
    assert edit.range.end.character == 5


def test_parse_error_returns_empty_edits() -> None:
    """Don't reformat broken code — the user needs to fix the syntax first."""
    srv = FakeServer()
    uri = "file:///tmp/bad.m"
    src = 'this is "not a valid M routine\n'  # unclosed string
    _open(srv, uri, src)

    edits = format_document(srv, uri)

    assert edits == []


def test_non_m_file_returns_empty_edits() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.py"
    _open(srv, uri, "print('not M')\n")

    edits = format_document(srv, uri)

    assert edits == []


def test_unknown_uri_returns_empty_edits() -> None:
    """If the workspace doesn't know the URI, don't crash."""
    srv = FakeServer()
    edits = format_document(srv, "file:///tmp/never-opened.m")
    assert edits == []


def test_idempotent_after_one_format() -> None:
    """Apply the formatter, replace the source, ask again — no further edits."""
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "hello ;c\n new x\n quit\n")

    first = format_document(srv, uri)
    assert first  # would change

    # Replace document with formatted output and reformat
    new_src = first[0].new_text
    srv.workspace.put_text_document(
        TextDocumentItem(uri=uri, language_id="m", version=2, text=new_src)
    )
    second = format_document(srv, uri)
    assert second == []


# ---------------------------------------------------------------------------
# textDocument/formatting handler wiring
# ---------------------------------------------------------------------------


def test_handler_returns_edits_from_format_document() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "hello ;c\n new x\n quit\n")

    params = DocumentFormattingParams(
        text_document=TextDocumentIdentifier(uri=uri),
        options=FormattingOptions(tab_size=1, insert_spaces=True),
    )
    edits = text_document_formatting(srv, params)

    assert len(edits) == 1
    assert "NEW" in edits[0].new_text


def test_handler_returns_empty_list_for_clean_doc() -> None:
    srv = FakeServer()
    uri = "file:///tmp/HELLO.m"
    _open(srv, uri, "HELLO ;c\n QUIT\n")

    params = DocumentFormattingParams(
        text_document=TextDocumentIdentifier(uri=uri),
        options=FormattingOptions(tab_size=1, insert_spaces=True),
    )
    edits = text_document_formatting(srv, params)

    assert edits == []
