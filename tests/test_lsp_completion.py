"""Tests for the Stage 4 LSP ``textDocument/completion`` handler.

The server returns the universe of M commands, ISVs, and intrinsic
functions as completion items; the client filters by typed prefix.
"""

from __future__ import annotations

from lsprotocol.types import (
    CompletionItemKind,
    CompletionParams,
    Position,
    TextDocumentIdentifier,
    TextDocumentItem,
)
from pygls.workspace import TextDocument

from m_cli.lsp.server import completion_at, text_document_completion


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
# completion_at
# ---------------------------------------------------------------------------


def test_completion_returns_set_keyword() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "HELLO ;c\n S\n")

    result = completion_at(srv, uri)

    labels = {item.label for item in result.items}
    assert "SET" in labels


def test_completion_marks_kinds_correctly() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "HELLO ;c\n")

    result = completion_at(srv, uri)
    by_label = {item.label: item for item in result.items}

    assert by_label["SET"].kind == CompletionItemKind.Keyword
    assert by_label["$LENGTH"].kind == CompletionItemKind.Function
    # $JOB is an ISV-only canonical (some names like $HOROLOG appear as
    # both ISV and function in ANSI; we use a non-ambiguous one here).
    assert by_label["$JOB"].kind == CompletionItemKind.Constant


def test_completion_skips_non_m_files() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.py"
    _open(srv, uri, "import this\n")

    result = completion_at(srv, uri)

    assert result.items == []


def test_completion_is_complete_flag_is_false() -> None:
    """The set doesn't grow per-keystroke; not incomplete."""
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "HELLO ;c\n")

    result = completion_at(srv, uri)

    assert result.is_incomplete is False


def test_completion_dispatches_through_text_document_completion() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "HELLO ;c\n")

    params = CompletionParams(
        text_document=TextDocumentIdentifier(uri=uri),
        position=Position(line=1, character=0),
    )
    result = text_document_completion(srv, params)

    assert any(item.label == "SET" for item in result.items)
