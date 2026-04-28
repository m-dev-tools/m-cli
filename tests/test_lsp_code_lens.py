"""Tests for the LSP ``textDocument/codeLens`` handler — Stage 4b.

Emits a "▶ Run test" lens above each ``t<UpperCase>(pass,fail)``
label inside a ``*TST.m`` suite file. The lens command name is
``m-cli.runTest`` with arguments ``[uri, label]`` — the VS Code
extension is expected to register that command.
"""

from __future__ import annotations

from lsprotocol.types import (
    CodeLensParams,
    TextDocumentIdentifier,
    TextDocumentItem,
)
from pygls.workspace import TextDocument

from m_cli.lsp.server import code_lenses_at, text_document_code_lens


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


_SAMPLE_SUITE = (
    "FOOTST ;c\n"
    " QUIT\n"
    "tGreetWorld(pass,fail) ;@TEST \"greet\"\n"
    " D ASSERT^TESTRUN(pass,fail,1=1)\n"
    " QUIT\n"
    "tFarewell(pass,fail) ;@TEST \"farewell\"\n"
    " D ASSERT^TESTRUN(pass,fail,1=1)\n"
    " QUIT\n"
)


def test_code_lens_returns_one_lens_per_test_label() -> None:
    srv = FakeServer()
    uri = "file:///tmp/FOOTST.m"
    _open(srv, uri, _SAMPLE_SUITE)

    lenses = code_lenses_at(srv, uri)

    titles = [lens.command.title for lens in lenses]
    assert titles == ["▶ Run test tGreetWorld", "▶ Run test tFarewell"]


def test_code_lens_command_carries_uri_and_label() -> None:
    srv = FakeServer()
    uri = "file:///tmp/FOOTST.m"
    _open(srv, uri, _SAMPLE_SUITE)

    lenses = code_lenses_at(srv, uri)
    cmd = lenses[0].command
    assert cmd.command == "m-cli.runTest"
    assert cmd.arguments == [uri, "tGreetWorld"]


def test_code_lens_lens_anchored_at_label_line() -> None:
    srv = FakeServer()
    uri = "file:///tmp/FOOTST.m"
    _open(srv, uri, _SAMPLE_SUITE)

    lenses = code_lenses_at(srv, uri)
    # tGreetWorld is on line 2 (0-indexed) in the sample.
    assert lenses[0].range.start.line == 2
    # tFarewell is on line 5.
    assert lenses[1].range.start.line == 5


def test_code_lens_empty_for_non_suite_file() -> None:
    """A file that isn't named ``*TST.m`` may still parse but won't
    contain ``t<UpperCase>(pass,fail)`` test conventions."""
    srv = FakeServer()
    uri = "file:///tmp/HELLO.m"
    _open(srv, uri, "HELLO ;c\n SET X=1\n QUIT\n")

    assert code_lenses_at(srv, uri) == []


def test_code_lens_skips_non_m_files() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.py"
    _open(srv, uri, "print('not M')\n")
    assert code_lenses_at(srv, uri) == []


def test_code_lens_dispatches_through_handler() -> None:
    srv = FakeServer()
    uri = "file:///tmp/FOOTST.m"
    _open(srv, uri, _SAMPLE_SUITE)
    params = CodeLensParams(text_document=TextDocumentIdentifier(uri=uri))
    lenses = text_document_code_lens(srv, params)
    assert len(lenses) == 2
