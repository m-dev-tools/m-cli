"""m-cli Language Server — Stage 1 (diagnostics push).

Wires the existing ``m_cli.lint`` library to the LSP
``textDocument/publishDiagnostics`` notification. On every open,
change, and save of a ``.m`` file the source is re-linted and the
resulting diagnostics are pushed to the editor.

The handler entry points (`did_open`, `did_change`, `did_save`,
`did_close`) take a ``LanguageServer``-shaped object and the
corresponding ``lsprotocol`` params. They are registered with the
real pygls server in :func:`run_stdio`; tests drive them with a
lighter-weight stub server (see ``tests/test_lsp_server.py``).
"""

from __future__ import annotations

import logging
from pathlib import Path

from lsprotocol.types import (
    TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_DID_CLOSE,
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_DID_SAVE,
    DidChangeTextDocumentParams,
    DidCloseTextDocumentParams,
    DidOpenTextDocumentParams,
    DidSaveTextDocumentParams,
    PublishDiagnosticsParams,
)
from pygls.lsp.server import LanguageServer

from m_cli import __version__
from m_cli.lint import lint_source, select_rules
from m_cli.lsp.convert import to_lsp_diagnostics

logger = logging.getLogger(__name__)

LSP_SERVER_NAME = "m-cli-lsp"


# ---------------------------------------------------------------------------
# Core helper
# ---------------------------------------------------------------------------


def lint_document(server, uri: str, *, rule_filter: str = "xindex") -> None:
    """Lint the workspace document at ``uri`` and push diagnostics.

    Skips non-``.m`` URIs and missing documents quietly — the LSP
    spec lets the server publish whatever it wants, and silence is a
    valid response when the file isn't ours to lint.
    """
    if not uri.endswith(".m"):
        return
    try:
        doc = server.workspace.get_text_document(uri)
    except KeyError:
        # Document not in the workspace yet (e.g. close arrived before open).
        return
    src_text = doc.source if doc.source is not None else ""
    src_bytes = src_text.encode("latin-1", errors="replace")
    rules = select_rules(rule_filter)
    path = Path(doc.path) if getattr(doc, "path", None) else Path(uri)
    diags = lint_source(path, src_bytes, rules)
    server.text_document_publish_diagnostics(
        PublishDiagnosticsParams(uri=uri, diagnostics=to_lsp_diagnostics(diags))
    )


def clear_diagnostics(server, uri: str) -> None:
    """Tell the editor to drop any diagnostics it's holding for ``uri``."""
    server.text_document_publish_diagnostics(PublishDiagnosticsParams(uri=uri, diagnostics=[]))


# ---------------------------------------------------------------------------
# Handlers — registered with the real server in run_stdio()
# ---------------------------------------------------------------------------


def did_open(server, params: DidOpenTextDocumentParams) -> None:
    lint_document(server, params.text_document.uri)


def did_change(server, params: DidChangeTextDocumentParams) -> None:
    lint_document(server, params.text_document.uri)


def did_save(server, params: DidSaveTextDocumentParams) -> None:
    lint_document(server, params.text_document.uri)


def did_close(server, params: DidCloseTextDocumentParams) -> None:
    clear_diagnostics(server, params.text_document.uri)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_stdio() -> int:
    """Build the pygls server, register handlers, and serve over stdio.

    Pygls' ``@server.feature(...)`` decorator invokes handlers with just
    the LSP params; the server reference is captured via closure here so
    the testable helpers (``did_open(server, params)`` etc.) keep their
    explicit-server signature.
    """
    server = LanguageServer(LSP_SERVER_NAME, __version__)

    @server.feature(TEXT_DOCUMENT_DID_OPEN)
    def _did_open(params: DidOpenTextDocumentParams) -> None:
        did_open(server, params)

    @server.feature(TEXT_DOCUMENT_DID_CHANGE)
    def _did_change(params: DidChangeTextDocumentParams) -> None:
        did_change(server, params)

    @server.feature(TEXT_DOCUMENT_DID_SAVE)
    def _did_save(params: DidSaveTextDocumentParams) -> None:
        did_save(server, params)

    @server.feature(TEXT_DOCUMENT_DID_CLOSE)
    def _did_close(params: DidCloseTextDocumentParams) -> None:
        did_close(server, params)

    logger.info("m-cli LSP %s starting on stdio", __version__)
    server.start_io()
    return 0


__all__ = [
    "lint_document",
    "clear_diagnostics",
    "did_open",
    "did_change",
    "did_save",
    "did_close",
    "run_stdio",
]
