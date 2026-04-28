"""Tests for the Stage 4 LSP ``textDocument/hover`` handler.

The server resolves the M token under the cursor against m-standard's
command/ISV/function tables and returns Markdown describing it. We
drive ``hover_at`` directly with a stub server — no live pygls.
"""

from __future__ import annotations

from lsprotocol.types import (
    HoverParams,
    MarkupKind,
    Position,
    TextDocumentIdentifier,
    TextDocumentItem,
)
from pygls.workspace import TextDocument

from m_cli.lsp.server import hover_at, text_document_hover


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
# hover_at
# ---------------------------------------------------------------------------


def test_hover_on_command_returns_markdown() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "HELLO ;c\n SET X=1\n")

    hover = hover_at(srv, uri, Position(line=1, character=2))

    assert hover is not None
    assert hover.contents.kind == MarkupKind.Markdown
    assert "**SET**" in hover.contents.value
    assert "M command" in hover.contents.value


def test_hover_on_abbreviation_resolves_to_canonical() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "HELLO ;c\n S X=1\n")

    hover = hover_at(srv, uri, Position(line=1, character=1))

    assert hover is not None
    assert "**SET**" in hover.contents.value
    # Abbreviation surfaced when distinct from canonical.
    assert "`S`" in hover.contents.value


def test_hover_on_intrinsic_function() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "HELLO ;c\n W $LENGTH(\"foo\")\n")

    hover = hover_at(srv, uri, Position(line=1, character=5))

    assert hover is not None
    assert "$LENGTH" in hover.contents.value
    assert "intrinsic function" in hover.contents.value


def test_hover_on_unknown_token_returns_none() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "HELLO ;c\n S MYVAR=1\n")

    # Cursor inside the local variable name — not a keyword.
    hover = hover_at(srv, uri, Position(line=1, character=4))

    assert hover is None


def test_hover_on_whitespace_returns_none() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "HELLO ;c\n S X=1\n")

    # Position 0 on the indented line is whitespace.
    hover = hover_at(srv, uri, Position(line=1, character=0))

    assert hover is None


def test_hover_skips_non_m_files() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.py"
    _open(srv, uri, "import this\n")

    hover = hover_at(srv, uri, Position(line=0, character=0))

    assert hover is None


def test_hover_returns_none_for_unknown_uri() -> None:
    srv = FakeServer()
    hover = hover_at(srv, "file:///tmp/never-opened.m", Position(line=0, character=0))
    assert hover is None


def test_hover_handles_position_past_eof() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "HELLO ;c\n S X=1\n")

    hover = hover_at(srv, uri, Position(line=99, character=0))

    assert hover is None


def test_hover_dispatches_through_text_document_hover() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "HELLO ;c\n SET X=1\n")

    params = HoverParams(
        text_document=TextDocumentIdentifier(uri=uri),
        position=Position(line=1, character=2),
    )
    hover = text_document_hover(srv, params)

    assert hover is not None
    assert "**SET**" in hover.contents.value
