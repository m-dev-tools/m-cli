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


# ---------------------------------------------------------------------------
# Hover-on-diagnostic — Phase 4-polish
# ---------------------------------------------------------------------------


def test_hover_on_diagnostic_returns_rule_markdown() -> None:
    """When the cursor sits inside a published diagnostic's range,
    the hover should describe the lint rule (id, title, severity)
    rather than fall through to the keyword lookup."""
    from pathlib import Path

    from m_cli.lint.diagnostic import Diagnostic, Severity

    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "HELLO ;c\n SET X=1   \n QUIT\n")
    # Publish a fake M-XINDX-013 (trailing-whitespace) diagnostic on
    # line 2, columns 9-12 (1-indexed columns).
    srv.m_cli_last_diagnostics = {
        uri: [
            Diagnostic(
                rule_id="M-XINDX-013",
                severity=Severity.WARNING,
                message="Blank(s) at end of line",
                path=Path("/tmp/hello.m"),
                line=2,
                column=9,
                column_end=12,
            )
        ]
    }
    # Cursor on the trailing whitespace (line 2, character 9 → 0-indexed 9).
    hover = hover_at(srv, uri, Position(line=1, character=9))

    assert hover is not None
    assert "M-XINDX-013" in hover.contents.value
    assert "Blank(s) at end of line" in hover.contents.value
    assert "warning" in hover.contents.value


def test_hover_outside_diagnostic_range_falls_through_to_keyword() -> None:
    """When the cursor is on a keyword that ISN'T inside a diagnostic
    range, the existing keyword-lookup behaviour wins."""
    from pathlib import Path

    from m_cli.lint.diagnostic import Diagnostic, Severity

    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "HELLO ;c\n SET X=1   \n QUIT\n")
    srv.m_cli_last_diagnostics = {
        uri: [
            Diagnostic(
                rule_id="M-XINDX-013",
                severity=Severity.WARNING,
                message="Blank(s) at end of line",
                path=Path("/tmp/hello.m"),
                line=2,
                column=9,
                column_end=12,
            )
        ]
    }
    # Cursor on SET (line 2, columns 1-3 → 0-indexed character 1).
    hover = hover_at(srv, uri, Position(line=1, character=2))

    assert hover is not None
    # Falls through to keyword lookup → describes SET, not the diagnostic.
    assert "**SET**" in hover.contents.value
    assert "M-XINDX-013" not in hover.contents.value


def test_hover_with_no_diagnostics_cache_uses_keyword_path() -> None:
    """Server has never linted yet → no cached diagnostics → keyword lookup."""
    srv = FakeServer()
    # No m_cli_last_diagnostics attribute at all.
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "HELLO ;c\n SET X=1\n")

    hover = hover_at(srv, uri, Position(line=1, character=2))
    assert hover is not None
    assert "**SET**" in hover.contents.value


def test_hover_on_unknown_rule_id_falls_back_to_message() -> None:
    """If the rule isn't in the registry (e.g. a M-INTERNAL-RULE-CRASH
    diagnostic from a buggy custom rule), use the diagnostic message."""
    from pathlib import Path

    from m_cli.lint.diagnostic import Diagnostic, Severity

    srv = FakeServer()
    uri = "file:///tmp/hello.m"
    _open(srv, uri, "HELLO ;c\n QUIT\n")
    srv.m_cli_last_diagnostics = {
        uri: [
            Diagnostic(
                rule_id="UNKNOWN-RULE-X",
                severity=Severity.ERROR,
                message="something exploded",
                path=Path("/tmp/hello.m"),
                line=1,
                column=1,
                column_end=5,
            )
        ]
    }
    hover = hover_at(srv, uri, Position(line=0, character=2))
    assert hover is not None
    assert "UNKNOWN-RULE-X" in hover.contents.value
    # Falls back to the diagnostic message when no rule entry is found.
    assert "something exploded" in hover.contents.value
