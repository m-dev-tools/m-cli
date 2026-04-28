"""m-cli Language Server — Stages 1 + 2 + 3.

Wires the existing ``m_cli.lint`` and ``m_cli.fmt`` libraries to LSP:

  - **Stage 1: diagnostics push.** ``didOpen`` / ``didChange`` /
    ``didSave`` re-lint the document; ``didClose`` clears its
    diagnostics. Each LSP ``Diagnostic`` carries the rule id as
    ``code``, ``source = "m-cli"``, mapped severity, and
    ``data = {"fixer_id": ...}`` when the rule is auto-fixable.

  - **Stage 2: formatting.** ``textDocument/formatting`` runs
    ``format_source(src, rules=canonical_rules())`` and returns a
    full-document ``TextEdit`` (or empty list when already canonical
    or parse-error).

  - **Stage 3: code actions.** ``textDocument/codeAction`` reads the
    in-context diagnostics, groups them by ``fixer_id``, and offers
    one Quick Fix per distinct fixer. Each action's ``WorkspaceEdit``
    runs that one fmt rule file-wide.

Public handler entry points (``did_*``, ``text_document_*``,
``lint_document``, ``format_document``, ``code_actions_for_uri``)
take a ``LanguageServer``-shaped object and the relevant LSP params.
They are registered with the real pygls server in :func:`run_stdio`;
tests drive them with a lighter-weight stub server (see the
``tests/test_lsp_*`` files).
"""

from __future__ import annotations

import logging
from pathlib import Path

from lsprotocol.types import (
    TEXT_DOCUMENT_CODE_ACTION,
    TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_DID_CLOSE,
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_DID_SAVE,
    TEXT_DOCUMENT_FORMATTING,
    CodeAction,
    CodeActionKind,
    CodeActionParams,
    DidChangeTextDocumentParams,
    DidCloseTextDocumentParams,
    DidOpenTextDocumentParams,
    DidSaveTextDocumentParams,
    DocumentFormattingParams,
    Position,
    PublishDiagnosticsParams,
    Range,
    TextEdit,
    WorkspaceEdit,
)
from lsprotocol.types import Diagnostic as LspDiagnostic
from pygls.lsp.server import LanguageServer

from m_cli import __version__
from m_cli.fmt import FmtRule, ParseError, canonical_rules, format_source, rule_by_id
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
# Formatting (Stage 2)
# ---------------------------------------------------------------------------


def format_document(server, uri: str) -> list[TextEdit]:
    """Run the canonical-layout formatter on the workspace document at ``uri``.

    Returns a list of ``TextEdit`` objects. The list is empty when:

      - ``uri`` does not refer to an ``.m`` file
      - the workspace has no document for ``uri``
      - the source has parse errors (we refuse to reformat broken code)
      - the source is already canonical (a no-op format would just churn
        the editor's undo history)

    The non-empty case returns a single ``TextEdit`` that replaces the
    full document with the formatted bytes. Editors apply the edit
    atomically.
    """
    if not uri.endswith(".m"):
        return []
    try:
        doc = server.workspace.get_text_document(uri)
    except KeyError:
        return []
    src_text = doc.source if doc.source is not None else ""
    src_bytes = src_text.encode("latin-1", errors="replace")
    try:
        formatted = format_source(src_bytes, rules=canonical_rules())
    except ParseError:
        return []
    if formatted == src_bytes:
        return []
    new_text = formatted.decode("latin-1", errors="replace")
    return [
        TextEdit(
            range=Range(
                start=Position(line=0, character=0),
                end=_end_position(src_text),
            ),
            new_text=new_text,
        )
    ]


def text_document_formatting(server, params: DocumentFormattingParams) -> list[TextEdit]:
    return format_document(server, params.text_document.uri)


def _end_position(src_text: str) -> Position:
    """Return the LSP Position one past the last character of ``src_text``."""
    if not src_text:
        return Position(line=0, character=0)
    if src_text.endswith("\n"):
        return Position(line=src_text.count("\n"), character=0)
    last_nl = src_text.rfind("\n")
    last_line_len = len(src_text) - (last_nl + 1)
    return Position(line=src_text.count("\n"), character=last_line_len)


# ---------------------------------------------------------------------------
# Code actions (Stage 3)
# ---------------------------------------------------------------------------


def code_actions_for_uri(server, uri: str, diagnostics: list[LspDiagnostic]) -> list[CodeAction]:
    """Build Quick Fix code actions for diagnostics whose data carries a fixer_id.

    Diagnostics sharing the same fixer collapse into one action: the
    fmt rule runs file-wide, so a single edit cleans every occurrence
    in one pass. Diagnostics without a fixer (or pointing to an
    unknown fmt rule) are skipped silently.

    Returns an empty list when the URI is not a ``.m`` file, the
    workspace has no document for it, the source has parse errors,
    or no diagnostic in scope has a known fixer.
    """
    if not uri.endswith(".m"):
        return []
    try:
        doc = server.workspace.get_text_document(uri)
    except KeyError:
        return []

    src_text = doc.source if doc.source is not None else ""
    src_bytes = src_text.encode("latin-1", errors="replace")

    # Group diagnostics by fixer_id, preserving registration order via
    # iteration over diagnostics.
    by_fixer: dict[str, list[LspDiagnostic]] = {}
    for diag in diagnostics:
        if not diag.data:
            continue
        fixer_id = diag.data.get("fixer_id") if isinstance(diag.data, dict) else None
        if not fixer_id:
            continue
        by_fixer.setdefault(fixer_id, []).append(diag)

    actions: list[CodeAction] = []
    for fixer_id, related in by_fixer.items():
        rule = rule_by_id(fixer_id)
        if rule is None:
            continue
        edit = _workspace_edit_for_fmt_rule(uri, src_text, src_bytes, rule)
        if edit is None:
            continue
        actions.append(
            CodeAction(
                title=f"Apply: {rule.title}",
                kind=CodeActionKind.QuickFix,
                diagnostics=related,
                edit=edit,
                is_preferred=True,
            )
        )
    return actions


def text_document_code_action(server, params: CodeActionParams) -> list[CodeAction]:
    return code_actions_for_uri(server, params.text_document.uri, list(params.context.diagnostics))


def _workspace_edit_for_fmt_rule(
    uri: str, src_text: str, src_bytes: bytes, rule: FmtRule
) -> WorkspaceEdit | None:
    """Run a single fmt rule on the source and wrap the result as a
    file-wide WorkspaceEdit. Returns ``None`` when the rule wouldn't
    change the source (no point offering a no-op action) or the
    source doesn't parse (refuse to fix broken code)."""
    try:
        formatted = format_source(src_bytes, rules=[rule])
    except ParseError:
        return None
    if formatted == src_bytes:
        return None
    new_text = formatted.decode("latin-1", errors="replace")
    return WorkspaceEdit(
        changes={
            uri: [
                TextEdit(
                    range=Range(
                        start=Position(line=0, character=0),
                        end=_end_position(src_text),
                    ),
                    new_text=new_text,
                )
            ]
        }
    )


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

    @server.feature(TEXT_DOCUMENT_FORMATTING)
    def _formatting(params: DocumentFormattingParams) -> list[TextEdit]:
        return text_document_formatting(server, params)

    @server.feature(TEXT_DOCUMENT_CODE_ACTION)
    def _code_action(params: CodeActionParams) -> list[CodeAction]:
        return text_document_code_action(server, params)

    logger.info("m-cli LSP %s starting on stdio", __version__)
    server.start_io()
    return 0


__all__ = [
    "lint_document",
    "clear_diagnostics",
    "format_document",
    "text_document_formatting",
    "code_actions_for_uri",
    "text_document_code_action",
    "did_open",
    "did_change",
    "did_save",
    "did_close",
    "run_stdio",
]
