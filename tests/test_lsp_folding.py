"""Tests for the LSP ``textDocument/foldingRange`` handler — Stage 4b."""

from __future__ import annotations

from lsprotocol.types import (
    FoldingRangeKind,
    FoldingRangeParams,
    TextDocumentIdentifier,
    TextDocumentItem,
)
from pygls.workspace import TextDocument

from m_cli.lsp.server import folding_ranges_at, text_document_folding_range


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


def test_folding_ranges_one_per_label_body() -> None:
    srv = FakeServer()
    uri = "file:///tmp/HELLO.m"
    _open(srv, uri, "HELLO ;c\n SET X=1\n QUIT\nINNER(a,b) ;c\n QUIT a+b\n")

    folds = folding_ranges_at(srv, uri)

    # HELLO covers rows 0-2; INNER covers rows 3-4. Both > start.
    assert len(folds) == 2
    assert folds[0].start_line == 0 and folds[0].end_line == 2
    assert folds[1].start_line == 3 and folds[1].end_line == 4
    assert all(f.kind == FoldingRangeKind.Region for f in folds)


def test_folding_ranges_skip_single_line_labels() -> None:
    """A label whose body is on the same line as the header has no
    fold — there's nothing to collapse."""
    srv = FakeServer()
    uri = "file:///tmp/HELLO.m"
    _open(srv, uri, "ONLY\n")
    assert folding_ranges_at(srv, uri) == []


def test_folding_ranges_include_dot_blocks() -> None:
    srv = FakeServer()
    uri = "file:///tmp/HELLO.m"
    src = (
        "TOP ;c\n"
        " . W \"a\"\n"
        " . S X=1\n"
        " . S Y=2\n"
        " QUIT\n"
    )
    _open(srv, uri, src)

    folds = folding_ranges_at(srv, uri)
    starts = [(f.start_line, f.end_line) for f in folds]
    # One label fold (TOP, rows 0-4) and one dot-block fold (rows 1-3).
    assert (0, 4) in starts
    assert (1, 3) in starts


def test_folding_ranges_skip_non_m_files() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.py"
    _open(srv, uri, "print('not M')\n")
    assert folding_ranges_at(srv, uri) == []


def test_folding_ranges_dispatches_through_handler() -> None:
    srv = FakeServer()
    uri = "file:///tmp/HELLO.m"
    _open(srv, uri, "HELLO ;c\n SET X=1\n QUIT\n")
    params = FoldingRangeParams(text_document=TextDocumentIdentifier(uri=uri))
    folds = text_document_folding_range(srv, params)
    assert len(folds) == 1
