"""Tests for ``m_cli.lsp.server`` — diagnostics push handlers.

Pygls' Server is heavy to spin up in tests, so the strategy is to
test the inner ``lint_document`` helper that does the actual lint →
LSP-diagnostic conversion against a stub server. The didOpen /
didChange / didSave / didClose handlers are thin wrappers around it
plus a workspace lookup; we drive those by faking a workspace.
"""

from __future__ import annotations

from typing import Any

from lsprotocol.types import (
    DiagnosticSeverity,
    DidChangeTextDocumentParams,
    DidCloseTextDocumentParams,
    DidOpenTextDocumentParams,
    PublishDiagnosticsParams,
    TextDocumentContentChangeWholeDocument,
    TextDocumentIdentifier,
    TextDocumentItem,
    VersionedTextDocumentIdentifier,
)
from pygls.workspace import TextDocument

from m_cli.lsp.server import (
    did_change,
    did_close,
    did_open,
    lint_document,
)


class FakeWorkspace:
    """Minimal workspace stub: holds documents by URI."""

    def __init__(self) -> None:
        self._docs: dict[str, TextDocument] = {}

    def put_text_document(self, item: TextDocumentItem) -> None:
        self._docs[item.uri] = TextDocument(uri=item.uri, source=item.text, version=item.version)

    def get_text_document(self, uri: str) -> TextDocument:
        return self._docs[uri]

    def remove_text_document(self, uri: str) -> None:
        self._docs.pop(uri, None)


class FakeServer:
    """Captures `text_document_publish_diagnostics` calls for inspection."""

    def __init__(self) -> None:
        self.workspace = FakeWorkspace()
        self.published: list[PublishDiagnosticsParams] = []

    def text_document_publish_diagnostics(self, params: PublishDiagnosticsParams) -> None:
        self.published.append(params)


def _open_doc(srv: FakeServer, uri: str, src: str) -> None:
    item = TextDocumentItem(uri=uri, language_id="m", version=1, text=src)
    srv.workspace.put_text_document(item)


# ---------------------------------------------------------------------------
# lint_document — the inner helper
# ---------------------------------------------------------------------------


def test_lint_document_publishes_diagnostics_for_real_lint_findings() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    src = "hello ;c\n quit \n"  # trailing space → M-XINDX-013
    _open_doc(srv, uri, src)

    lint_document(srv, uri)

    assert len(srv.published) == 1
    pub = srv.published[0]
    assert pub.uri == uri
    rule_ids = {d.code for d in pub.diagnostics}
    assert "M-XINDX-013" in rule_ids


def test_lint_document_pushes_for_every_lint() -> None:
    """Even a near-clean file produces a publish (possibly with no diagnostics)."""
    srv = FakeServer()
    uri = "file:///tmp/HELLO.m"
    src = "HELLO ;c\n QUIT\n"
    _open_doc(srv, uri, src)

    lint_document(srv, uri)

    # We always push so the editor can clear stale diagnostics from a
    # previous lint pass. Whether the list is empty depends on the
    # current rule set.
    assert len(srv.published) == 1
    assert srv.published[0].uri == uri


def test_lint_document_skips_non_m_files() -> None:
    """Don't lint .py / .md / random files even if the editor opens them."""
    srv = FakeServer()
    uri = "file:///tmp/hello.py"
    _open_doc(srv, uri, "print('not M')\n")

    lint_document(srv, uri)

    assert srv.published == []


def test_lint_document_returns_quietly_for_unknown_uri() -> None:
    """If the workspace doesn't know the URI, don't crash."""
    srv = FakeServer()
    lint_document(srv, "file:///tmp/never-opened.m")
    assert srv.published == []


def test_lint_document_uses_lsp_severity_codes() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    src = "hello ;c\n quit \n"
    _open_doc(srv, uri, src)

    lint_document(srv, uri)

    diags = srv.published[0].diagnostics
    # M-XINDX-013 is WARNING in m-cli → DiagnosticSeverity.Warning
    sev_for_013 = next(d.severity for d in diags if d.code == "M-XINDX-013")
    assert sev_for_013 == DiagnosticSeverity.Warning


def test_lint_document_carries_fixer_id_in_data() -> None:
    """Stage 3 will use this to expose Quick Fix actions."""
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    src = "hello ;c\n quit \n"
    _open_doc(srv, uri, src)

    lint_document(srv, uri)

    diags = srv.published[0].diagnostics
    d013 = next(d for d in diags if d.code == "M-XINDX-013")
    assert d013.data == {"fixer_id": "trim-trailing-whitespace"}


def test_lint_document_honors_server_attached_rule_filter() -> None:
    """Stage 4 — the CLI's `--rules` flag stashes a filter on the server.
    A filter that selects no rules should yield zero diagnostics for a
    file that would otherwise trigger M-XINDX-013."""
    srv = FakeServer()
    srv.m_cli_rule_filter = "M-XINDX-019"  # only the line-too-long rule
    uri = "file:///tmp/hello.m"
    _open_doc(srv, uri, "hello ;c\n quit \n")  # trailing space → M-XINDX-013

    lint_document(srv, uri)

    diags = srv.published[0].diagnostics
    rule_ids = {d.code for d in diags}
    assert "M-XINDX-013" not in rule_ids


def test_lint_document_explicit_rule_filter_wins_over_server_attribute() -> None:
    """An explicit ``rule_filter=`` arg overrides the server's stashed value."""
    srv = FakeServer()
    srv.m_cli_rule_filter = "M-XINDX-019"
    uri = "file:///tmp/hello.m"
    _open_doc(srv, uri, "hello ;c\n quit \n")

    lint_document(srv, uri, rule_filter="xindex")

    rule_ids = {d.code for d in srv.published[0].diagnostics}
    assert "M-XINDX-013" in rule_ids


# ---------------------------------------------------------------------------
# Handler wiring: didOpen, didChange, didSave, didClose
# ---------------------------------------------------------------------------


def test_did_open_publishes_diagnostics() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    item = TextDocumentItem(uri=uri, language_id="m", version=1, text="hello \n quit\n")
    srv.workspace.put_text_document(item)

    params = DidOpenTextDocumentParams(text_document=item)
    did_open(srv, params)

    assert len(srv.published) == 1
    assert srv.published[0].uri == uri


def test_did_change_re_publishes_diagnostics() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open_doc(srv, uri, "hello \n quit\n")

    # Caller is responsible for updating the workspace document; we
    # just verify the handler triggers a republish.
    params: Any = DidChangeTextDocumentParams(
        text_document=VersionedTextDocumentIdentifier(uri=uri, version=2),
        content_changes=[TextDocumentContentChangeWholeDocument(text="hello\n quit\n")],
    )
    did_change(srv, params)

    assert len(srv.published) == 1
    assert srv.published[0].uri == uri


def test_did_close_clears_diagnostics() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open_doc(srv, uri, "hello \n quit\n")

    params = DidCloseTextDocumentParams(
        text_document=TextDocumentIdentifier(uri=uri),
    )
    did_close(srv, params)

    assert len(srv.published) == 1
    assert srv.published[0].uri == uri
    assert srv.published[0].diagnostics == []
