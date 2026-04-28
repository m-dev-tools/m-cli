"""Tests for the LSP ``textDocument/signatureHelp`` handler — Stage 4b.

When the cursor sits inside ``$FN(...)``, the server returns the
intrinsic function's syntax format (loaded from m-standard's TSV)
as a single SignatureInformation. Other contexts return None.
"""

from __future__ import annotations

from lsprotocol.types import (
    Position,
    SignatureHelpParams,
    TextDocumentIdentifier,
    TextDocumentItem,
)
from pygls.workspace import TextDocument

from m_cli.lsp.server import signature_help_at, text_document_signature_help


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


def test_signature_help_inside_intrinsic_call() -> None:
    srv = FakeServer()
    uri = "file:///tmp/h.m"
    _open(srv, uri, "H ;c\n W $LENGTH(\"foo\")\n")

    # Position inside the parens of $LENGTH("foo") — column 11 is just
    # after the opening paren.
    sig = signature_help_at(srv, uri, Position(line=1, character=11))

    assert sig is not None
    assert len(sig.signatures) == 1
    label = sig.signatures[0].label
    # The format from m-standard for $LENGTH starts with $L[ENGTH](
    assert label.startswith("$L[ENGTH](")


def test_signature_help_resolves_abbreviation() -> None:
    srv = FakeServer()
    uri = "file:///tmp/h.m"
    _open(srv, uri, "H ;c\n W $L(\"foo\")\n")

    sig = signature_help_at(srv, uri, Position(line=1, character=6))

    assert sig is not None
    assert "$L[ENGTH]" in sig.signatures[0].label


def test_signature_help_returns_none_outside_parens() -> None:
    srv = FakeServer()
    uri = "file:///tmp/h.m"
    _open(srv, uri, "H ;c\n W $LENGTH(\"foo\")\n")

    # Cursor on " W " (column 1) — not inside a call.
    assert signature_help_at(srv, uri, Position(line=1, character=1)) is None


def test_signature_help_returns_none_for_non_intrinsic() -> None:
    """``D MYLABEL(args)`` is a routine call, not an intrinsic — no signature."""
    srv = FakeServer()
    uri = "file:///tmp/h.m"
    _open(srv, uri, "H ;c\n D MYLABEL(\"foo\")\n")

    sig = signature_help_at(srv, uri, Position(line=1, character=12))
    assert sig is None


def test_signature_help_returns_none_for_isv_only() -> None:
    """``$JOB`` is an ISV (no parens) — even mistyped as ``$JOB(...)``,
    we don't claim a function signature."""
    srv = FakeServer()
    uri = "file:///tmp/h.m"
    _open(srv, uri, "H ;c\n W $JOB(\"x\")\n")

    sig = signature_help_at(srv, uri, Position(line=1, character=8))
    assert sig is None


def test_signature_help_skips_non_m_files() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.py"
    _open(srv, uri, "print(len('foo'))\n")
    assert signature_help_at(srv, uri, Position(line=0, character=10)) is None


def test_signature_help_dispatches_through_handler() -> None:
    srv = FakeServer()
    uri = "file:///tmp/h.m"
    _open(srv, uri, "H ;c\n W $LENGTH(\"foo\")\n")
    params = SignatureHelpParams(
        text_document=TextDocumentIdentifier(uri=uri),
        position=Position(line=1, character=11),
    )
    sig = text_document_signature_help(srv, params)
    assert sig is not None
