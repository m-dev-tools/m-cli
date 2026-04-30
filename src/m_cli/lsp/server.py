"""m-cli Language Server — Stages 1 + 2 + 3 + 4.

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

  - **Stage 4: hover + completion.** ``textDocument/hover`` resolves
    the M token under the cursor against m-standard's command/ISV/
    function tables and returns Markdown with the canonical name,
    abbreviation, and syntax format. ``textDocument/completion``
    returns the same set as completion items so editors can suggest
    keywords as the user types.

The rule filter for diagnostics defaults to ``"default"`` — m-cli's
built-in curated profile; pass ``--rules <filter>`` to ``m lsp`` to
override (e.g. ``--rules all`` for every registered rule, or
``--rules xindex`` for the VA VistA Toolkit profile).

Public handler entry points (``did_*``, ``text_document_*``,
``lint_document``, ``format_document``, ``code_actions_for_uri``,
``hover_at``, ``completion_at``) take a ``LanguageServer``-shaped
object and the relevant LSP params. They are registered with the
real pygls server in :func:`run_stdio`; tests drive them with a
lighter-weight stub server (see the ``tests/test_lsp_*`` files).
"""

from __future__ import annotations

import dataclasses
import logging
from functools import lru_cache
from pathlib import Path

from lsprotocol.types import (
    TEXT_DOCUMENT_CODE_ACTION,
    TEXT_DOCUMENT_CODE_LENS,
    TEXT_DOCUMENT_COMPLETION,
    TEXT_DOCUMENT_DEFINITION,
    TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_DID_CLOSE,
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_DID_SAVE,
    TEXT_DOCUMENT_DOCUMENT_HIGHLIGHT,
    TEXT_DOCUMENT_DOCUMENT_SYMBOL,
    TEXT_DOCUMENT_FOLDING_RANGE,
    TEXT_DOCUMENT_FORMATTING,
    TEXT_DOCUMENT_HOVER,
    TEXT_DOCUMENT_REFERENCES,
    TEXT_DOCUMENT_SIGNATURE_HELP,
    WORKSPACE_DID_CHANGE_WATCHED_FILES,
    WORKSPACE_SYMBOL,
    CodeAction,
    CodeActionKind,
    CodeActionParams,
    CodeLens,
    CodeLensParams,
    Command,
    CompletionItem,
    CompletionItemKind,
    CompletionList,
    CompletionParams,
    DefinitionParams,
    DidChangeTextDocumentParams,
    DidChangeWatchedFilesParams,
    DidCloseTextDocumentParams,
    DidOpenTextDocumentParams,
    DidSaveTextDocumentParams,
    DocumentFormattingParams,
    DocumentHighlight,
    DocumentHighlightKind,
    DocumentHighlightParams,
    DocumentSymbol,
    DocumentSymbolParams,
    FileChangeType,
    FoldingRange,
    FoldingRangeKind,
    FoldingRangeParams,
    Hover,
    HoverParams,
    Location,
    MarkupContent,
    MarkupKind,
    Position,
    PublishDiagnosticsParams,
    Range,
    ReferenceParams,
    SignatureHelp,
    SignatureHelpOptions,
    SignatureHelpParams,
    SignatureInformation,
    SymbolKind,
    TextEdit,
    WorkspaceEdit,
    WorkspaceSymbol,
    WorkspaceSymbolParams,
)
from lsprotocol.types import Diagnostic as LspDiagnostic
from pygls.lsp.server import LanguageServer

from m_cli import __version__
from m_cli.config import Config, load_config
from m_cli.fmt import FmtRule, ParseError, canonical_rules, format_source, rule_by_id
from m_cli.lint import lint_source, select_rules
from m_cli.lint.profiles import DEFAULT_PROFILE
from m_cli.lsp.convert import to_lsp_diagnostics
from m_cli.lsp.structure import find_dot_blocks, find_labels
from m_cli.lsp.symbols import KeywordRecord, all_keywords, lookup_keyword, token_at
from m_cli.test.discovery import find_test_cases
from m_cli.workspace import WorkspaceIndex, build_index, reference_at

logger = logging.getLogger(__name__)

LSP_SERVER_NAME = "m-cli-lsp"


# ---------------------------------------------------------------------------
# Core helper
# ---------------------------------------------------------------------------


def lint_document(server, uri: str, *, rule_filter: str | None = None) -> None:
    """Lint the workspace document at ``uri`` and push diagnostics.

    Skips non-``.m`` URIs and missing documents quietly — the LSP
    spec lets the server publish whatever it wants, and silence is a
    valid response when the file isn't ours to lint.

    Resolution order for the rule filter: explicit ``rule_filter``
    argument → ``server.m_cli_rule_filter`` (CLI ``--rules`` flag) →
    config file's ``[lint] rules`` → :data:`DEFAULT_PROFILE` (m-cli's
    curated, engine-neutral baseline). Config also contributes the
    ``[lint] disable`` list and ``[lint.severity]`` overrides, applied
    after rule selection / linting.
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
    config: Config = getattr(server, "m_cli_config", None) or Config.empty()
    effective_filter = (
        rule_filter
        or getattr(server, "m_cli_rule_filter", None)
        or config.lint_rules
        or DEFAULT_PROFILE
    )
    rules = select_rules(effective_filter)
    if config.lint_disable:
        rules = [r for r in rules if r.id not in config.lint_disable]
    path = Path(doc.path) if getattr(doc, "path", None) else Path(uri)

    # Build a LintContext for context-aware rules. Workspace comes
    # from the LSP's workspace index attribute when present; thresholds
    # come from (profile preset → config → built-in defaults) and
    # target_engine from config.
    from m_cli.lint.context import LintContext
    from m_cli.lint.profiles import get_profile
    from m_cli.lint.thresholds import validate as _validate_thresholds

    # Layer profile preset thresholds (e.g. `pythonic` ships
    # line_length=100) under the user's [lint.thresholds] config.
    profile_defaults: dict[str, int] = {}
    if (
        "," not in effective_filter
        and not effective_filter.startswith("M-")
    ):
        profile = get_profile(effective_filter)
        if profile is not None:
            profile_defaults = dict(profile.default_thresholds)
    layered = dict(profile_defaults)
    layered.update(config.lint_thresholds)
    try:
        thresholds = _validate_thresholds(layered)
    except ValueError:
        thresholds = _validate_thresholds(None)  # fall back to defaults
    ctx = LintContext(
        thresholds=thresholds,
        target_engine=config.lint_target_engine or "any",
        workspace=getattr(server, "m_cli_workspace_index", None),
        config=config,
    )
    diags = lint_source(path, src_bytes, rules, ctx=ctx)
    # Stash the most recent diagnostics for this URI so hover_at can
    # cross-reference cursor-on-squiggle without re-running the linter.
    cache: dict[str, list] = getattr(server, "m_cli_last_diagnostics", None) or {}
    cache[uri] = list(diags)
    setattr(server, "m_cli_last_diagnostics", cache)  # noqa: B010
    if config.lint_severity_overrides:
        diags = [
            dataclasses.replace(d, severity=config.lint_severity_overrides[d.rule_id])
            if d.rule_id in config.lint_severity_overrides
            else d
            for d in diags
        ]
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
    # Refresh the workspace index for this file so cross-routine
    # navigation (definition / references / workspace symbol) stays
    # consistent with the saved-on-disk content. didChangeWatchedFiles
    # also fires for file-system events; this handler covers in-editor
    # saves where the FS notification may not arrive.
    update_index_for_uri(server, params.text_document.uri)


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
# Hover (Stage 4)
# ---------------------------------------------------------------------------


def hover_at(server, uri: str, position: Position) -> Hover | None:
    """Resolve the cursor position to hover content.

    Resolution order:

      1. **Lint diagnostic at this position.** When the cursor sits
         inside a published diagnostic's range, return Markdown for
         the rule (id, title, severity). Most useful — answers "what
         does this squiggle mean?" inline.
      2. **M keyword under the cursor.** Falls through to the
         keyword-table lookup (commands, ISVs, intrinsic functions
         from m-standard).
      3. ``None`` if neither.

    Local labels and user routines aren't described — m-cli doesn't
    have a per-symbol description registry beyond keywords + rules.
    """
    if not uri.endswith(".m"):
        return None
    try:
        doc = server.workspace.get_text_document(uri)
    except KeyError:
        return None
    lines = (doc.source or "").splitlines()
    if position.line < 0 or position.line >= len(lines):
        return None

    diag_md = _diagnostic_hover_markdown(server, uri, position)
    if diag_md is not None:
        return Hover(contents=MarkupContent(kind=MarkupKind.Markdown, value=diag_md))

    token = token_at(lines[position.line], position.character)
    if token is None:
        return None
    record = lookup_keyword(token)
    if record is None:
        return None
    return Hover(contents=MarkupContent(kind=MarkupKind.Markdown, value=_hover_markdown(record)))


def _diagnostic_hover_markdown(server, uri: str, position: Position) -> str | None:
    """Return Markdown for any lint diagnostic that contains the
    cursor position, or None if the cursor isn't on a squiggle.

    Looks up the rule from `m_cli.lint.rules._REGISTRY` to fetch
    title and severity. Multiple overlapping diagnostics (rare but
    possible) all show; rules sort first by id for stable output.
    """
    diags_by_uri = getattr(server, "m_cli_last_diagnostics", None) or {}
    diags = diags_by_uri.get(uri)
    if not diags:
        return None
    line = position.line + 1  # m-cli Diagnostic uses 1-indexed lines
    char = position.character
    matching = []
    for d in diags:
        if d.line != line:
            continue
        col_start = max(0, d.column - 1)  # m-cli columns are 1-indexed
        col_end = (d.column_end - 1) if d.column_end is not None else col_start
        if col_end < col_start:
            col_end = col_start
        # Treat the position as inclusive on the start, exclusive on
        # the end. A zero-width range still matches when char == col_start.
        if col_start <= char <= max(col_start, col_end):
            matching.append(d)
    if not matching:
        return None

    from m_cli.lint.rules import _REGISTRY

    parts: list[str] = []
    for d in sorted(matching, key=lambda x: x.rule_id):
        rule = _REGISTRY.get(d.rule_id)
        title = rule.title if rule is not None else d.message
        sev = d.severity.value
        parts.append(f"**{d.rule_id}** — {title} _(severity: {sev})_")
        if rule is not None and d.message and d.message != rule.title:
            parts.append("")
            parts.append(d.message)
    return "\n".join(parts)


def text_document_hover(server, params: HoverParams) -> Hover | None:
    return hover_at(server, params.text_document.uri, params.position)


_KIND_LABELS: dict[str, str] = {
    "command": "M command",
    "isv": "M intrinsic special variable",
    "function": "M intrinsic function",
}


def _hover_markdown(record: KeywordRecord) -> str:
    """Render a KeywordRecord as a small Markdown block."""
    head = f"**{record.canonical}**"
    if record.abbreviation and record.abbreviation != record.canonical:
        head = f"**{record.canonical}** (`{record.abbreviation}`)"
    parts = [f"{head} — {_KIND_LABELS.get(record.kind, record.kind)}"]
    if record.format:
        parts.append("")
        parts.append(f"```\n{record.format}\n```")
    if record.standard_status:
        parts.append("")
        parts.append(f"_Standard: {record.standard_status}_")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Completion (Stage 4)
# ---------------------------------------------------------------------------


def completion_at(server, uri: str) -> CompletionList:
    """Return the full set of M commands, ISVs, and intrinsic functions.

    The client filters by the user's typed prefix; the server returns
    the unfiltered universe with stable ``label`` / ``kind`` / ``detail``
    fields. ``isIncomplete`` is False — the set doesn't grow per-keystroke.

    Returns an empty list for non-``.m`` URIs so the editor doesn't
    offer M keywords inside other languages it might route through us.
    """
    if not uri.endswith(".m"):
        return CompletionList(is_incomplete=False, items=[])
    return CompletionList(is_incomplete=False, items=_completion_items())


def text_document_completion(server, params: CompletionParams) -> CompletionList:
    return completion_at(server, params.text_document.uri)


_COMPLETION_KIND: dict[str, CompletionItemKind] = {
    "command": CompletionItemKind.Keyword,
    "isv": CompletionItemKind.Constant,
    "function": CompletionItemKind.Function,
}


@lru_cache(maxsize=1)
def _completion_items() -> list[CompletionItem]:
    items: list[CompletionItem] = []
    for record in all_keywords():
        detail = record.format or _KIND_LABELS.get(record.kind, record.kind)
        items.append(
            CompletionItem(
                label=record.canonical,
                kind=_COMPLETION_KIND.get(record.kind, CompletionItemKind.Text),
                detail=detail,
            )
        )
    return items


# ---------------------------------------------------------------------------
# Document symbols (Stage 4b — outline view)
# ---------------------------------------------------------------------------


def document_symbols_at(server, uri: str) -> list[DocumentSymbol]:
    """Return one DocumentSymbol per label declared in the document.

    Each symbol's ``range`` covers the label and its body (until the
    next label or EOF); ``selection_range`` covers just the label
    name. Editors render this as a flat outline — M doesn't have
    nested scopes so we don't build a tree.
    """
    if not uri.endswith(".m"):
        return []
    try:
        doc = server.workspace.get_text_document(uri)
    except KeyError:
        return []
    src_bytes = (doc.source or "").encode("latin-1", errors="replace")
    out: list[DocumentSymbol] = []
    for lbl in find_labels(src_bytes):
        full_range = Range(
            start=Position(line=lbl.start_line, character=0),
            end=Position(line=lbl.end_line, character=0),
        )
        sel_range = Range(
            start=Position(line=lbl.start_line, character=0),
            end=Position(line=lbl.start_line, character=len(lbl.name)),
        )
        out.append(
            DocumentSymbol(
                name=lbl.name + lbl.formals,
                kind=SymbolKind.Function,
                range=full_range,
                selection_range=sel_range,
            )
        )
    return out


def text_document_document_symbol(server, params: DocumentSymbolParams) -> list[DocumentSymbol]:
    return document_symbols_at(server, params.text_document.uri)


# ---------------------------------------------------------------------------
# Code lenses (Stage 4b — "▶ Run test" above each test label)
# ---------------------------------------------------------------------------


def code_lenses_at(server, uri: str) -> list[CodeLens]:
    """Emit a "▶ Run test" lens above each ``t<UpperCase>(pass,fail)``
    label in a ``*TST.m`` suite file.

    The lens carries a ``m-cli.runTest`` command with arguments
    ``[document_uri, label_name]``. The VS Code extension is expected
    to register this command and shell out to ``m test FILE.m::tLabel``.
    Editors that don't register the command still display the lens
    title but the click is a no-op — that's intentional.
    """
    if not uri.endswith(".m"):
        return []
    try:
        doc = server.workspace.get_text_document(uri)
    except KeyError:
        return []
    path = Path(doc.path) if getattr(doc, "path", None) else Path(uri)
    src_bytes = (doc.source or "").encode("latin-1", errors="replace")
    cases = find_test_cases(path, src_bytes)
    out: list[CodeLens] = []
    for case in cases:
        line0 = max(0, case.line - 1)  # find_test_cases returns 1-indexed
        out.append(
            CodeLens(
                range=Range(
                    start=Position(line=line0, character=0),
                    end=Position(line=line0, character=len(case.label)),
                ),
                command=Command(
                    title=f"▶ Run test {case.label}",
                    command="m-cli.runTest",
                    arguments=[uri, case.label],
                ),
            )
        )
    return out


def text_document_code_lens(server, params: CodeLensParams) -> list[CodeLens]:
    return code_lenses_at(server, params.text_document.uri)


# ---------------------------------------------------------------------------
# Folding ranges (Stage 4b)
# ---------------------------------------------------------------------------


def folding_ranges_at(server, uri: str) -> list[FoldingRange]:
    """Fold each label's body and each contiguous dot-block run.

    The label range covers the line *after* the label header through
    its last body line — folding the header itself would hide the
    name and defeat the purpose. Single-line labels emit no fold.
    """
    if not uri.endswith(".m"):
        return []
    try:
        doc = server.workspace.get_text_document(uri)
    except KeyError:
        return []
    src_bytes = (doc.source or "").encode("latin-1", errors="replace")
    out: list[FoldingRange] = []
    for lbl in find_labels(src_bytes):
        if lbl.end_line > lbl.start_line:
            out.append(
                FoldingRange(
                    start_line=lbl.start_line,
                    end_line=lbl.end_line,
                    kind=FoldingRangeKind.Region,
                )
            )
    for blk in find_dot_blocks(src_bytes):
        if blk.end_line > blk.start_line:
            out.append(
                FoldingRange(
                    start_line=blk.start_line,
                    end_line=blk.end_line,
                    kind=FoldingRangeKind.Region,
                )
            )
    return out


def text_document_folding_range(server, params: FoldingRangeParams) -> list[FoldingRange]:
    return folding_ranges_at(server, params.text_document.uri)


# ---------------------------------------------------------------------------
# Signature help (Stage 4b — show $FN signature inside parentheses)
# ---------------------------------------------------------------------------


def signature_help_at(server, uri: str, position: Position) -> SignatureHelp | None:
    """When the cursor is inside ``$FN(...)``, return the function's
    syntax format as a single SignatureInformation entry.

    Resolution is purely text-based: scan left from the cursor for the
    matching unbalanced ``(``, then read the intrinsic-function token
    immediately before it. We don't track active-parameter index —
    M's intrinsic parameter lists are short and the format string
    already shows them.
    """
    if not uri.endswith(".m"):
        return None
    try:
        doc = server.workspace.get_text_document(uri)
    except KeyError:
        return None
    lines = (doc.source or "").splitlines()
    if position.line < 0 or position.line >= len(lines):
        return None
    line = lines[position.line]
    if position.character > len(line):
        return None
    open_idx = _find_enclosing_open_paren(line, position.character)
    if open_idx is None:
        return None
    fn_token = _read_token_ending_at(line, open_idx)
    if not fn_token or not fn_token.startswith("$"):
        return None
    record = lookup_keyword(fn_token)
    if record is None or record.kind != "function":
        return None
    fmt = record.format or record.canonical
    return SignatureHelp(
        signatures=[
            SignatureInformation(
                label=fmt,
                documentation=MarkupContent(
                    kind=MarkupKind.Markdown,
                    value=f"**{record.canonical}** — M intrinsic function",
                ),
            )
        ],
        active_signature=0,
        active_parameter=0,
    )


def text_document_signature_help(server, params: SignatureHelpParams) -> SignatureHelp | None:
    return signature_help_at(server, params.text_document.uri, params.position)


def _signature_help_options() -> SignatureHelpOptions:
    """Trigger ``$FN(`` opens signature help; ``,`` keeps it active."""
    return SignatureHelpOptions(trigger_characters=["("], retrigger_characters=[","])


def _find_enclosing_open_paren(line: str, character: int) -> int | None:
    """Walk backward from ``character`` and return the column of the
    nearest unmatched ``(``. Skips matched ``()`` pairs and stops if
    we leave the line without finding one."""
    depth = 0
    i = character - 1
    while i >= 0:
        c = line[i]
        if c == ")":
            depth += 1
        elif c == "(":
            if depth == 0:
                return i
            depth -= 1
        i -= 1
    return None


def _read_token_ending_at(line: str, end: int) -> str | None:
    """Read the M token that ends at column ``end`` (exclusive).
    Mirrors ``token_at`` but anchored to a known boundary."""
    if end <= 0:
        return None

    def is_word(c: str) -> bool:
        return c.isalnum() or c == "$" or c == "%"

    start = end
    while start > 0 and is_word(line[start - 1]):
        start -= 1
    token = line[start:end]
    return token if token else None


# ---------------------------------------------------------------------------
# Document highlight (Stage 4b — same-file occurrences of a name)
# ---------------------------------------------------------------------------


def document_highlights_at(server, uri: str, position: Position) -> list[DocumentHighlight] | None:
    """Highlight every occurrence of the identifier under the cursor
    inside the current document.

    Match is case-sensitive (M is case-sensitive for *variable* names —
    only command/function keywords are case-insensitive). Returns
    ``None`` when no token is under the cursor; an empty list is
    valid only when the token has zero other occurrences.
    """
    if not uri.endswith(".m"):
        return None
    try:
        doc = server.workspace.get_text_document(uri)
    except KeyError:
        return None
    src_text = doc.source or ""
    lines = src_text.splitlines()
    if position.line < 0 or position.line >= len(lines):
        return None
    token = token_at(lines[position.line], position.character)
    if token is None or len(token) < 2:
        # Single-char tokens are too noisy (e.g. ``X`` matches every X).
        return None
    out: list[DocumentHighlight] = []
    for row, line in enumerate(lines):
        for col in _find_token_occurrences(line, token):
            out.append(
                DocumentHighlight(
                    range=Range(
                        start=Position(line=row, character=col),
                        end=Position(line=row, character=col + len(token)),
                    ),
                    kind=DocumentHighlightKind.Text,
                )
            )
    return out


def text_document_document_highlight(
    server, params: DocumentHighlightParams
) -> list[DocumentHighlight] | None:
    return document_highlights_at(server, params.text_document.uri, params.position)


def _find_token_occurrences(line: str, token: str) -> list[int]:
    """Return all column positions where ``token`` appears as a
    standalone word in ``line`` (word boundaries on both sides)."""
    if not token:
        return []

    def is_word(c: str) -> bool:
        return c.isalnum() or c == "$" or c == "%"

    out: list[int] = []
    n = len(token)
    i = 0
    while i <= len(line) - n:
        if line[i : i + n] == token:
            left_ok = i == 0 or not is_word(line[i - 1])
            right_ok = i + n == len(line) or not is_word(line[i + n])
            if left_ok and right_ok:
                out.append(i)
                i += n
                continue
        i += 1
    return out


# ---------------------------------------------------------------------------
# Go-to-definition (Phase B — workspace symbol index)
# ---------------------------------------------------------------------------


def definition_at(server, uri: str, position: Position) -> Location | None:
    """Resolve ``LABEL^ROUTINE`` / ``^ROUTINE`` / local label under cursor.

    For a cross-routine reference, the workspace index resolves the
    target routine + label to a ``(path, line)``. For a label-only
    reference (``D LBL`` or ``$$LBL``), we fall back to the current
    document's labels — same-routine calls don't need the workspace
    index, and we wouldn't know which other routine to search anyway.
    Returns ``None`` when the cursor isn't on a reference, or the
    target isn't in the index.
    """
    if not uri.endswith(".m"):
        return None
    try:
        doc = server.workspace.get_text_document(uri)
    except KeyError:
        return None
    lines = (doc.source or "").splitlines()
    if position.line < 0 or position.line >= len(lines):
        return None
    ref = reference_at(lines[position.line], position.character)
    if ref is None:
        return None

    if ref.routine is None:
        # Label-only reference — search the current document.
        return _resolve_local_label(uri, doc.source or "", ref.label)

    index: WorkspaceIndex | None = getattr(server, "m_cli_workspace_index", None)
    if index is None:
        return None
    loc = index.lookup(ref.routine, ref.label)
    if loc is None:
        return None
    return Location(
        uri=loc.path.as_uri(),
        range=Range(
            start=Position(line=loc.line - 1, character=0),
            end=Position(line=loc.line - 1, character=len(loc.label)),
        ),
    )


def text_document_definition(server, params: DefinitionParams) -> Location | None:
    return definition_at(server, params.text_document.uri, params.position)


def _resolve_local_label(uri: str, src_text: str, label: str | None) -> Location | None:
    """Find ``label`` in the current document's source. Used for
    intra-routine references (``D LBL`` without a ``^ROUTINE``)."""
    if not label:
        return None
    target = label.upper()
    for row, line in enumerate(src_text.splitlines()):
        if not line or line[0] in (" ", "\t", ";"):
            continue
        # Label is the first identifier on the line, before any space /
        # paren / comment.
        end = 0
        while end < len(line) and (line[end].isalnum() or line[end] in ("%", "$")):
            end += 1
        name = line[:end]
        if name.upper() == target:
            return Location(
                uri=uri,
                range=Range(
                    start=Position(line=row, character=0),
                    end=Position(line=row, character=len(name)),
                ),
            )
    return None


# ---------------------------------------------------------------------------
# Find references (Phase B follow-up)
# ---------------------------------------------------------------------------


def references_at(
    server, uri: str, position: Position, *, include_declaration: bool = True
) -> list[Location] | None:
    """Return every call site that targets the symbol under the cursor.

    The cursor may sit on a reference (``D LABEL^OTHER``) or on a
    label declaration (``LABEL`` at column 0). In either case the
    target is resolved as ``(routine, label)`` and the workspace
    index returns inbound call sites. When ``include_declaration``
    is True (the LSP default), the declaration's location is included
    in the result list.
    """
    if not uri.endswith(".m"):
        return None
    try:
        doc = server.workspace.get_text_document(uri)
    except KeyError:
        return None
    lines = (doc.source or "").splitlines()
    if position.line < 0 or position.line >= len(lines):
        return None

    target = _resolve_reference_target(uri, lines, position)
    if target is None:
        return None
    routine, label = target

    index = getattr(server, "m_cli_workspace_index", None)
    if index is None:
        return []

    refs = index.references_to(routine, label)
    out: list[Location] = []
    for ref in refs:
        out.append(
            Location(
                uri=ref.path.as_uri(),
                range=Range(
                    start=Position(line=ref.line - 1, character=ref.column),
                    end=Position(line=ref.line - 1, character=ref.end_column),
                ),
            )
        )
    if include_declaration and label:
        decl = index.lookup(routine, label)
        if decl is not None:
            out.append(
                Location(
                    uri=decl.path.as_uri(),
                    range=Range(
                        start=Position(line=decl.line - 1, character=0),
                        end=Position(line=decl.line - 1, character=len(decl.label)),
                    ),
                )
            )
    return out


def text_document_references(server, params: ReferenceParams) -> list[Location] | None:
    include = bool(getattr(params.context, "include_declaration", True))
    return references_at(
        server,
        params.text_document.uri,
        params.position,
        include_declaration=include,
    )


def _resolve_reference_target(
    uri: str, lines: list[str], position: Position
) -> tuple[str, str | None] | None:
    """Determine the (routine, label) pair the cursor refers to.

    First tries ``reference_at`` — handles in-line ``LABEL^ROUTINE`` /
    ``$$LABEL`` cursors. Failing that, checks whether the cursor is
    on a label declaration (column 0 word on a label line) and uses
    the file's stem as the routine.
    """
    line = lines[position.line]
    ref = reference_at(line, position.character)
    if ref is not None:
        if ref.routine is not None:
            return ref.routine, ref.label
        # No explicit ^routine — assume current file's routine.
        return _routine_from_uri(uri), ref.label

    # Maybe the cursor is on a label declaration at column 0.
    if line and line[0] not in (" ", "\t", ";"):
        end = 0
        while end < len(line) and (line[end].isalnum() or line[end] in ("%", "$")):
            end += 1
        if 0 < end and position.character <= end:
            return _routine_from_uri(uri), line[:end]
    return None


def _routine_from_uri(uri: str) -> str:
    return Path(uri).stem


# ---------------------------------------------------------------------------
# Workspace symbol search (Phase B follow-up)
# ---------------------------------------------------------------------------


_WORKSPACE_SYMBOL_LIMIT = 1000


def workspace_symbols_for(server, query: str) -> list[WorkspaceSymbol]:
    """Return label declarations matching ``query`` (case-insensitive
    substring match against label OR routine name).

    Empty query returns every label up to the limit. Limit caps the
    response so a Ctrl+T into a 39,000-routine VistA workspace
    doesn't ship 200 MB of JSON over stdio.
    """
    index = getattr(server, "m_cli_workspace_index", None)
    if index is None:
        return []
    q = (query or "").upper()
    out: list[WorkspaceSymbol] = []
    for loc in index.all_locations():
        if q and q not in loc.label.upper() and q not in loc.routine.upper():
            continue
        out.append(
            WorkspaceSymbol(
                name=f"{loc.label}^{loc.routine}",
                kind=SymbolKind.Function,
                location=Location(
                    uri=loc.path.as_uri(),
                    range=Range(
                        start=Position(line=loc.line - 1, character=0),
                        end=Position(line=loc.line - 1, character=len(loc.label)),
                    ),
                ),
            )
        )
        if len(out) >= _WORKSPACE_SYMBOL_LIMIT:
            break
    return out


def workspace_symbol_handler(server, params: WorkspaceSymbolParams) -> list[WorkspaceSymbol]:
    return workspace_symbols_for(server, params.query)


# ---------------------------------------------------------------------------
# Incremental index updates (Phase B follow-up)
# ---------------------------------------------------------------------------


def did_change_watched_files(server, params: DidChangeWatchedFilesParams) -> None:
    """Apply file-system change notifications to the workspace index.

    Created / changed → re-add the file (which replaces prior entries).
    Deleted → drop the file's entries. Non-``.m`` files are ignored.
    Read errors are logged at debug level — a transient stat race
    shouldn't pollute the log.
    """
    index = getattr(server, "m_cli_workspace_index", None)
    if index is None:
        return
    for change in params.changes:
        if not change.uri.endswith(".m"):
            continue
        path = _path_from_uri(change.uri)
        if path is None:
            continue
        if change.type == FileChangeType.Deleted:
            index.remove_file(path)
            continue
        try:
            src = path.read_bytes()
        except OSError as e:
            logger.debug("workspace index: skipping %s: %s", path, e)
            index.remove_file(path)
            continue
        index.add_file(path, src)


def update_index_for_uri(server, uri: str) -> None:
    """Re-index a single URI from the in-memory workspace document.

    Called from didSave so in-editor edits keep references / symbols
    fresh without waiting for a file-system notification (which not
    every client emits on save).
    """
    if not uri.endswith(".m"):
        return
    index = getattr(server, "m_cli_workspace_index", None)
    if index is None:
        return
    try:
        doc = server.workspace.get_text_document(uri)
    except KeyError:
        return
    path = _path_from_uri(uri)
    if path is None:
        return
    src = (doc.source or "").encode("latin-1", errors="replace")
    index.add_file(path, src)


def _path_from_uri(uri: str) -> Path | None:
    """Convert a ``file://`` URI to a Path. Returns None for non-file URIs."""
    if not uri.startswith("file://"):
        return None
    from urllib.parse import unquote, urlparse

    parsed = urlparse(uri)
    return Path(unquote(parsed.path))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_stdio(rule_filter: str | None = None) -> int:
    """Build the pygls server, register handlers, and serve over stdio.

    Pygls' ``@server.feature(...)`` decorator invokes handlers with just
    the LSP params; the server reference is captured via closure here so
    the testable helpers (``did_open(server, params)`` etc.) keep their
    explicit-server signature.
    """
    server = LanguageServer(LSP_SERVER_NAME, __version__)
    if rule_filter:
        # LanguageServer is dynamically attribute-extensible; we stash the
        # CLI-provided filter so lint_document() can read it. Using setattr
        # avoids tripping mypy on the unknown attribute.
        setattr(server, "m_cli_rule_filter", rule_filter)  # noqa: B010
    # Load .m-cli.toml / pyproject.toml [tool.m-cli] from the spawn cwd.
    # VS Code spawns `m lsp` with cwd = workspace folder, so this finds
    # the workspace's project config without needing the initialize URI.
    try:
        config = load_config(Path.cwd())
        if config.source_path is not None:
            logger.info("m-cli LSP loaded config from %s", config.source_path)
        setattr(server, "m_cli_config", config)  # noqa: B010
    except ValueError as e:
        logger.warning("m-cli LSP: ignoring invalid config (%s)", e)
        setattr(server, "m_cli_config", Config.empty())  # noqa: B010

    # Build the workspace symbol index from the spawn cwd. Powers
    # textDocument/definition (and, in follow-ups, references and
    # workspace symbol search). Failures are logged and the index
    # is left empty — the LSP still works without cross-routine nav.
    try:
        index = build_index([Path.cwd()])
        logger.info("m-cli LSP indexed %d label(s) under %s", len(index), Path.cwd())
        setattr(server, "m_cli_workspace_index", index)  # noqa: B010
    except Exception as e:  # pragma: no cover — defensive
        logger.warning("m-cli LSP: workspace index build failed (%s)", e)
        setattr(server, "m_cli_workspace_index", WorkspaceIndex())  # noqa: B010

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

    @server.feature(TEXT_DOCUMENT_HOVER)
    def _hover(params: HoverParams) -> Hover | None:
        return text_document_hover(server, params)

    @server.feature(TEXT_DOCUMENT_COMPLETION)
    def _completion(params: CompletionParams) -> CompletionList:
        return text_document_completion(server, params)

    @server.feature(TEXT_DOCUMENT_DOCUMENT_SYMBOL)
    def _document_symbol(params: DocumentSymbolParams) -> list[DocumentSymbol]:
        return text_document_document_symbol(server, params)

    @server.feature(TEXT_DOCUMENT_CODE_LENS)
    def _code_lens(params: CodeLensParams) -> list[CodeLens]:
        return text_document_code_lens(server, params)

    @server.feature(TEXT_DOCUMENT_FOLDING_RANGE)
    def _folding_range(params: FoldingRangeParams) -> list[FoldingRange]:
        return text_document_folding_range(server, params)

    @server.feature(TEXT_DOCUMENT_SIGNATURE_HELP, _signature_help_options())
    def _signature_help(params: SignatureHelpParams) -> SignatureHelp | None:
        return text_document_signature_help(server, params)

    @server.feature(TEXT_DOCUMENT_DOCUMENT_HIGHLIGHT)
    def _document_highlight(params: DocumentHighlightParams) -> list[DocumentHighlight] | None:
        return text_document_document_highlight(server, params)

    @server.feature(TEXT_DOCUMENT_DEFINITION)
    def _definition(params: DefinitionParams) -> Location | None:
        return text_document_definition(server, params)

    @server.feature(TEXT_DOCUMENT_REFERENCES)
    def _references(params: ReferenceParams) -> list[Location] | None:
        return text_document_references(server, params)

    @server.feature(WORKSPACE_SYMBOL)
    def _workspace_symbol(params: WorkspaceSymbolParams) -> list[WorkspaceSymbol]:
        return workspace_symbol_handler(server, params)

    @server.feature(WORKSPACE_DID_CHANGE_WATCHED_FILES)
    def _did_change_watched(params: DidChangeWatchedFilesParams) -> None:
        did_change_watched_files(server, params)

    logger.info("m-cli LSP %s starting on stdio", __version__)
    server.start_io()
    return 0


__all__ = [
    "lint_document",
    "clear_diagnostics",
    "format_document",
    "text_document_formatting",
    "hover_at",
    "text_document_hover",
    "completion_at",
    "text_document_completion",
    "document_symbols_at",
    "text_document_document_symbol",
    "code_lenses_at",
    "text_document_code_lens",
    "folding_ranges_at",
    "text_document_folding_range",
    "signature_help_at",
    "text_document_signature_help",
    "document_highlights_at",
    "text_document_document_highlight",
    "definition_at",
    "text_document_definition",
    "references_at",
    "text_document_references",
    "workspace_symbols_for",
    "workspace_symbol_handler",
    "did_change_watched_files",
    "update_index_for_uri",
    "code_actions_for_uri",
    "text_document_code_action",
    "did_open",
    "did_change",
    "did_save",
    "did_close",
    "run_stdio",
]
