"""Tests for the LSP ``textDocument/documentSymbol`` handler — Stage 4b."""

from __future__ import annotations

from lsprotocol.types import (
    DocumentSymbolParams,
    SymbolKind,
    TextDocumentIdentifier,
    TextDocumentItem,
)
from pygls.workspace import TextDocument

from m_cli.lsp.server import document_symbols_at, text_document_document_symbol


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


def test_document_symbol_returns_one_per_label() -> None:
    srv = FakeServer()
    uri = "file:///tmp/HELLO.m"
    _open(srv, uri, "HELLO ;c\n SET X=1\n QUIT\nINNER(a,b) ;c\n QUIT a+b\n")

    syms = document_symbols_at(srv, uri)

    assert [s.name for s in syms] == ["HELLO", "INNER(a,b)"]
    assert all(s.kind == SymbolKind.Function for s in syms)
    # Selection range covers just the label name on the label line.
    assert syms[0].selection_range.start.line == 0
    assert syms[0].selection_range.end.character == len("HELLO")
    # Full range extends through the body.
    assert syms[0].range.start.line == 0
    assert syms[0].range.end.line == 2


def test_document_symbol_skips_non_m_files() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.py"
    _open(srv, uri, "print('not M')\n")
    assert document_symbols_at(srv, uri) == []


def test_document_symbol_returns_empty_for_unknown_uri() -> None:
    srv = FakeServer()
    assert document_symbols_at(srv, "file:///tmp/never-opened.m") == []


def test_document_symbol_dispatches_through_handler() -> None:
    srv = FakeServer()
    uri = "file:///tmp/HELLO.m"
    _open(srv, uri, "HELLO ;c\n QUIT\n")
    params = DocumentSymbolParams(text_document=TextDocumentIdentifier(uri=uri))
    syms = text_document_document_symbol(srv, params)
    assert syms[0].name == "HELLO"
