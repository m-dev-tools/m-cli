"""Tests for the LSP ``textDocument/codeAction`` handler — Stage 3.

Each lint diagnostic with a ``fixer_id`` in its ``data`` field becomes
a Quick Fix code action: editors expose it as a single-click "Apply
<fixer-title>" entry that runs the linked ``m fmt`` rule on the whole
file. Multiple diagnostics sharing the same fixer collapse into one
action — running ``trim-trailing-whitespace`` once cleans every line.

The handler does **not** invent fixers from thin air. Diagnostics
without ``fixer_id`` produce no actions; the LSP client decides
whether to expose them another way (e.g. "ignore this rule").
"""

from __future__ import annotations

from lsprotocol.types import (
    CodeActionContext,
    CodeActionKind,
    CodeActionParams,
    DiagnosticSeverity,
    Position,
    Range,
    TextDocumentIdentifier,
    TextDocumentItem,
)
from lsprotocol.types import Diagnostic as LspDiagnostic
from pygls.workspace import TextDocument

from m_cli.lsp.server import code_actions_for_uri, text_document_code_action


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


def _diag(
    *,
    code: str = "M-XINDX-013",
    fixer_id: str | None = "trim-trailing-whitespace",
    line: int = 0,
    col: int = 0,
    end_col: int = 5,
) -> LspDiagnostic:
    return LspDiagnostic(
        range=Range(
            start=Position(line=line, character=col),
            end=Position(line=line, character=end_col),
        ),
        severity=DiagnosticSeverity.Warning,
        code=code,
        source="m-cli",
        message="x",
        data={"fixer_id": fixer_id} if fixer_id else None,
    )


# ---------------------------------------------------------------------------
# code_actions_for_uri — the inner helper
# ---------------------------------------------------------------------------


def test_no_diagnostics_returns_no_actions() -> None:
    srv = FakeServer()
    _open(srv, "file:///tmp/hello.m", "hello\n quit\n")
    actions = code_actions_for_uri(srv, "file:///tmp/hello.m", [])
    assert actions == []


def test_diagnostic_without_fixer_returns_no_actions() -> None:
    srv = FakeServer()
    _open(srv, "file:///tmp/hello.m", "hello\n quit\n")
    actions = code_actions_for_uri(
        srv, "file:///tmp/hello.m", [_diag(code="M-XINDX-014", fixer_id=None)]
    )
    assert actions == []


def test_diagnostic_with_known_fixer_produces_action() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "hello   \n quit\n")
    actions = code_actions_for_uri(srv, uri, [_diag()])
    assert len(actions) == 1
    action = actions[0]
    assert action.kind == CodeActionKind.QuickFix
    assert "trailing" in action.title.lower()


def test_action_carries_workspace_edit_replacing_document() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "hello   \n quit\n")
    actions = code_actions_for_uri(srv, uri, [_diag()])
    assert actions[0].edit is not None
    changes = actions[0].edit.changes
    assert changes is not None
    edits = changes[uri]
    assert len(edits) == 1
    assert edits[0].new_text == "hello\n quit\n"


def test_multiple_diagnostics_same_fixer_dedupe_into_one_action() -> None:
    """Two trailing-whitespace findings → one ``trim-trailing-whitespace``
    action whose edit fixes them all in a single pass."""
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "hello  \n quit  \n")
    actions = code_actions_for_uri(
        srv,
        uri,
        [
            _diag(line=0, col=5, end_col=8),
            _diag(line=1, col=4, end_col=7),
        ],
    )
    assert len(actions) == 1
    # The single action's edit fixes both lines.
    edits = actions[0].edit.changes[uri]
    assert edits[0].new_text == "hello\n quit\n"


def test_multiple_diagnostics_different_fixers_produce_distinct_actions() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "hello   \n new x\n quit\n")
    actions = code_actions_for_uri(
        srv,
        uri,
        [
            _diag(code="M-XINDX-013", fixer_id="trim-trailing-whitespace"),
            _diag(code="M-XINDX-047", fixer_id="uppercase-command-keywords"),
        ],
    )
    titles = sorted(a.title for a in actions)
    assert len(actions) == 2
    assert any("trailing" in t.lower() for t in titles)
    assert any("uppercase" in t.lower() or "command keyword" in t.lower() for t in titles)


def test_action_diagnostics_field_links_back_to_originals() -> None:
    """LSP wants the originating diagnostic in the action so the editor
    can dim it after the fix."""
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "hello   \n quit\n")
    diag = _diag()
    [action] = code_actions_for_uri(srv, uri, [diag])
    assert action.diagnostics == [diag]


def test_unknown_fixer_id_skipped() -> None:
    """If a diagnostic claims a fixer we don't know about, drop it
    silently — the lint side advertised something the fmt side can't
    deliver."""
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "hello\n quit\n")
    actions = code_actions_for_uri(srv, uri, [_diag(fixer_id="not-a-real-fmt-rule")])
    assert actions == []


def test_no_op_fixer_skipped() -> None:
    """If the fixer would produce no change (e.g. file already clean),
    don't offer the action — it would be a confusing no-op for the user."""
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "hello\n quit\n")  # already trimmed
    actions = code_actions_for_uri(srv, uri, [_diag()])
    assert actions == []


def test_non_m_uri_returns_no_actions() -> None:
    srv = FakeServer()
    _open(srv, "file:///tmp/hello.py", "print('hi')\n")
    actions = code_actions_for_uri(srv, "file:///tmp/hello.py", [_diag()])
    assert actions == []


def test_parse_error_source_returns_no_actions() -> None:
    """If the source has parse errors we refuse to fix — same policy
    as the formatting handler. The user fixes syntax first."""
    srv = FakeServer()
    uri = "file:///tmp/bad.m"
    _open(srv, uri, 'this is "broken\n')
    actions = code_actions_for_uri(srv, uri, [_diag()])
    assert actions == []


def test_unknown_uri_returns_no_actions() -> None:
    srv = FakeServer()
    actions = code_actions_for_uri(srv, "file:///tmp/never.m", [_diag()])
    assert actions == []


# ---------------------------------------------------------------------------
# textDocument/codeAction handler wiring
# ---------------------------------------------------------------------------


def test_handler_returns_actions_from_helper() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "hello   \n quit\n")
    params = CodeActionParams(
        text_document=TextDocumentIdentifier(uri=uri),
        range=Range(
            start=Position(line=0, character=0),
            end=Position(line=2, character=0),
        ),
        context=CodeActionContext(diagnostics=[_diag()]),
    )
    actions = text_document_code_action(srv, params)
    assert len(actions) == 1
    assert actions[0].kind == CodeActionKind.QuickFix


def test_handler_returns_empty_when_context_has_no_diagnostics() -> None:
    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "hello   \n quit\n")
    params = CodeActionParams(
        text_document=TextDocumentIdentifier(uri=uri),
        range=Range(
            start=Position(line=0, character=0),
            end=Position(line=0, character=0),
        ),
        context=CodeActionContext(diagnostics=[]),
    )
    actions = text_document_code_action(srv, params)
    assert actions == []
