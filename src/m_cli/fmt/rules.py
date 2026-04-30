"""Canonical-layout transformations for ``m fmt``.

Each rule is a pure ``bytes -> bytes`` transformation that must:

  1. Be **idempotent** — applying twice yields the same output as once.
  2. Preserve **AST shape** — the parsed tree before and after has the
     same structure (same nodes in the same order). Whitespace and the
     text inside ``command_keyword`` etc. may change, but no node
     type may appear or disappear.
  3. Be **safe on parse errors** — input that doesn't parse cleanly
     should be returned unchanged (the formatter handles parse errors
     up the stack via ``ParseError``).

Rules are tagged so callers can opt in by family or by id:
``--rules=canonical`` enables every rule; ``--rules=trim-trailing-
whitespace`` enables one. ``--rules=none`` (the default) is identity.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

from m_cli.lint._keywords import keyword_records
from m_cli.parser import parse

# A rule is a single-arg ``bytes -> bytes`` callable.
RuleFn = Callable[[bytes], bytes]


@dataclass(frozen=True)
class FmtRule:
    id: str
    title: str
    description: str
    apply: RuleFn


_REGISTRY: dict[str, FmtRule] = {}


def _register(rule: FmtRule) -> FmtRule:
    if rule.id in _REGISTRY:
        raise ValueError(f"duplicate fmt rule id: {rule.id}")
    _REGISTRY[rule.id] = rule
    return rule


def all_rules() -> list[FmtRule]:
    """Every registered rule, in registration order."""
    return list(_REGISTRY.values())


def rule_by_id(rule_id: str) -> FmtRule | None:
    """Return the registered rule with this id, or ``None`` if unknown.

    Public helper for tooling consumers (LSP code-action handlers, CI
    integrations) that need to resolve a ``fixer_id`` string back to the
    actual ``FmtRule`` callable.
    """
    return _REGISTRY.get(rule_id)


_CANONICAL_RULE_IDS = (
    "trim-trailing-whitespace",
    "uppercase-command-keywords",
)


def canonical_rules() -> list[FmtRule]:
    """The SAC-default canonical layout — hygiene, no translation.

    Excludes the ``expand-*`` and ``compact-*`` translation rules (they
    are mutually exclusive and would race when applied together).
    Translation rules ship under explicit opt-in presets:
    :func:`pythonic_rules` (expand all) and :func:`compact_rules`.
    """
    return [r for r in (rule_by_id(rid) for rid in _CANONICAL_RULE_IDS) if r is not None]


def select_fmt_rules(spec: str) -> list[FmtRule]:
    """Resolve a CLI-style spec to a list of rules.

    Accepted forms:
      - ``"none"`` — empty list (identity formatter)
      - ``"canonical"`` — SAC-default hygiene (trim + uppercase)
      - ``"pythonic"`` — expand abbreviations to canonical names (uppercase)
      - ``"pythonic-lower"`` — expand abbreviations, but lowercase output
        (``set X=1 write $length(X)``)
      - ``"compact"`` — compact canonical names to abbreviations
      - ``"all"`` — every registered rule (mostly useful for diagnostics;
        do NOT use as a formatter pipeline because expand-* and
        compact-* would race)
      - ``"<id>,<id>,..."`` — explicit, comma-separated ids
    """
    spec = spec.strip()
    if spec in ("none", ""):
        return []
    if spec == "canonical":
        return canonical_rules()
    if spec == "pythonic":
        return pythonic_rules()
    if spec == "pythonic-lower":
        return pythonic_lower_rules()
    if spec == "compact":
        return compact_rules()
    if spec == "all":
        return all_rules()
    requested = {s.strip() for s in spec.split(",") if s.strip()}
    out = [r for r in all_rules() if r.id in requested]
    missing = requested - {r.id for r in out}
    if missing:
        raise ValueError(f"unknown fmt rule(s): {sorted(missing)}")
    return out


# ---------------------------------------------------------------------------
# Rule: trim-trailing-whitespace
# ---------------------------------------------------------------------------


def trim_trailing_whitespace(src: bytes) -> bytes:
    """Remove trailing spaces and tabs from each line.

    Preserves line terminators (``\\n`` or ``\\r\\n``) and final-line
    handling: a file with no terminator stays without one. Auto-fixes
    the lint warning ``M-XINDX-013``.
    """
    if not src:
        return src
    out = bytearray()
    for line in src.splitlines(keepends=True):
        if line.endswith(b"\r\n"):
            out += line[:-2].rstrip(b" \t") + b"\r\n"
        elif line.endswith(b"\n"):
            out += line[:-1].rstrip(b" \t") + b"\n"
        elif line.endswith(b"\r"):
            out += line[:-1].rstrip(b" \t") + b"\r"
        else:
            out += line.rstrip(b" \t")
    return bytes(out)


_register(
    FmtRule(
        id="trim-trailing-whitespace",
        title="Strip trailing whitespace from every line",
        description=(
            "Removes spaces and tabs at the end of each line, preserving "
            "line terminators. Auto-fixes lint M-XINDX-013."
        ),
        apply=trim_trailing_whitespace,
    )
)


# ---------------------------------------------------------------------------
# Rule: uppercase-command-keywords
# ---------------------------------------------------------------------------


def _rewrite_node_case(
    src: bytes, node_type: str, transform: Callable[[bytes], bytes]
) -> bytes:
    """Apply ``transform`` to the bytes of every ``node_type`` node.

    Shared engine for case-folding rules: walks the parse tree, finds
    every node of the given type, and replaces its bytes with
    ``transform(text)``. AST shape is preserved because M is
    case-insensitive on command / function / ISV keywords.

    Returns ``src`` unchanged when the source is empty, has parse
    errors, or contains no matching nodes that need rewriting.
    """
    if not src:
        return src
    tree = parse(src)
    if tree.root_node.has_error:
        return src
    edits: list[tuple[int, int, bytes]] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == node_type:
            text = src[node.start_byte : node.end_byte]
            new_text = transform(text)
            if text != new_text:
                edits.append((node.start_byte, node.end_byte, new_text))
            continue  # keyword leaf nodes have no children we care about
        stack.extend(reversed(node.children))
    if not edits:
        return src
    out = bytearray(src)
    for start, end, replacement in sorted(edits, reverse=True):
        out[start:end] = replacement
    return bytes(out)


def uppercase_command_keywords(src: bytes) -> bytes:
    """Rewrite every ``command_keyword`` AST node to upper-case ASCII.

    SAC §3.3 prefers upper-case command keywords; this is the auto-fix
    for lint ``M-XINDX-047``. Inverse of
    :func:`lowercase_command_keywords`.
    """
    return _rewrite_node_case(src, "command_keyword", bytes.upper)


_register(
    FmtRule(
        id="uppercase-command-keywords",
        title="Uppercase command keywords (SAC §3.3)",
        description=(
            "Rewrites every command keyword (NEW, SET, QUIT, …) and "
            "its abbreviations to upper-case ASCII. Auto-fixes lint "
            "M-XINDX-047."
        ),
        apply=uppercase_command_keywords,
    )
)


# ---------------------------------------------------------------------------
# Rules: lowercase-{command-keywords, intrinsic-functions, special-variables}
# ---------------------------------------------------------------------------
#
# Mirrors of the uppercase rule for the three keyword node types. Used by the
# `pythonic-lower` preset to produce all-lowercase output (``set x=1`` rather
# than ``SET X=1``). M is case-insensitive on these keywords, so the output
# parses identically; lint M-MOD-035 (canonical-form $Z*) and SAC §3.3 are
# the policy reasons most projects prefer uppercase, but Python-influenced
# shops that want PEP-8-style lowercase keywords get this opt-in.


def lowercase_command_keywords(src: bytes) -> bytes:
    """Rewrite every ``command_keyword`` AST node to lower-case ASCII.

    Inverse of :func:`uppercase_command_keywords`. The two rules are
    mutually exclusive — apply one or the other, not both.
    """
    return _rewrite_node_case(src, "command_keyword", bytes.lower)


_register(
    FmtRule(
        id="lowercase-command-keywords",
        title="Lowercase command keywords (PEP-8 style)",
        description=(
            "Rewrites every command keyword (SET, NEW, QUIT, …) and its "
            "abbreviations to lower-case ASCII. Inverse of "
            "uppercase-command-keywords. Used by the `pythonic-lower` "
            "preset for Python-influenced projects."
        ),
        apply=lowercase_command_keywords,
    )
)


def lowercase_intrinsic_functions(src: bytes) -> bytes:
    """Rewrite every ``intrinsic_function_keyword`` AST node to lower-case."""
    return _rewrite_node_case(src, "intrinsic_function_keyword", bytes.lower)


_register(
    FmtRule(
        id="lowercase-intrinsic-functions",
        title="Lowercase intrinsic functions ($LENGTH → $length)",
        description=(
            "Rewrites every intrinsic-function keyword ($LENGTH, $EXTRACT, "
            "$ZDATE, …) and its abbreviations to lower-case ASCII. Used "
            "by the `pythonic-lower` preset."
        ),
        apply=lowercase_intrinsic_functions,
    )
)


def lowercase_special_variables(src: bytes) -> bytes:
    """Rewrite every ``special_variable_keyword`` AST node to lower-case."""
    return _rewrite_node_case(src, "special_variable_keyword", bytes.lower)


_register(
    FmtRule(
        id="lowercase-special-variables",
        title="Lowercase special variables ($TEST → $test)",
        description=(
            "Rewrites every intrinsic special-variable keyword ($TEST, "
            "$HOROLOG, $JOB, …) and its abbreviations to lower-case "
            "ASCII. Used by the `pythonic-lower` preset."
        ),
        apply=lowercase_special_variables,
    )
)


# ===========================================================================
# Translation rules — mechanical conversion between compact (S, $L, $T) and
# canonical (SET, $LENGTH, $TEST) forms. Each rule is its own inverse:
# `compose(expand, compact) == identity` for any registered token, modulo
# whitespace. AST shape is preserved (only the text inside command_keyword /
# intrinsic_function_keyword / special_variable_keyword nodes changes).
#
# Operator-spacing translation (PEP-8-style ` = ` around assignment) is NOT
# offered as a fmt rule because M's whitespace-as-separator semantics break
# parsing on `S X = 1` — try it: tree-sitter-m correctly emits ERROR.
# Statement-splitting (one-command-per-line) is not offered either; it
# violates the fmt rule contract's AST-shape-preservation requirement.
# ===========================================================================


def _build_translation_maps(kind: str) -> tuple[dict[str, str], dict[str, str]]:
    """Return ``(abbrev_to_canonical, canonical_to_abbrev)`` for ``kind``.

    ``kind`` is one of ``"command"``, ``"function"``, or ``"isv"``. Both
    maps are uppercase-keyed; case is preserved at apply time.

    Skips records where canonical == abbreviation (no translation needed)
    and where either is missing. When m-standard isn't installed, the
    fallback ``keyword_records()`` returns synthetic entries with empty
    abbreviation, so both maps come out empty — the rules degrade to
    no-ops, which is the right behavior.
    """
    a2c: dict[str, str] = {}
    c2a: dict[str, str] = {}
    for rec in keyword_records():
        if rec.kind != kind:
            continue
        if not rec.canonical or not rec.abbreviation:
            continue
        canon = rec.canonical.upper()
        abbrev = rec.abbreviation.upper()
        if canon == abbrev:
            continue
        a2c[abbrev] = canon
        c2a[canon] = abbrev
    return a2c, c2a


@lru_cache(maxsize=8)
def _translation_map(kind: str, direction: str) -> dict[str, str]:
    """Cached lookup for the translation maps. ``direction`` is ``"expand"``
    (abbreviation → canonical) or ``"compact"`` (canonical → abbreviation)."""
    a2c, c2a = _build_translation_maps(kind)
    return a2c if direction == "expand" else c2a


def _apply_case(reference: str, replacement: str) -> str:
    """Match ``replacement`` to the case style of ``reference``.

    - All-lower reference → all-lower replacement (`s` → `set`)
    - Anything else → upper replacement (`S` → `SET`, `Set` → `SET`)

    Preserves the typographic intent without trying to mirror unusual
    casings (which are rare in M and unlikely to be deliberate).
    """
    if reference.islower():
        return replacement.lower()
    return replacement.upper()


def _translate_keyword_nodes(
    src: bytes, target_node_type: str, mapping: dict[str, str]
) -> bytes:
    """Apply ``mapping`` to every node of ``target_node_type`` in ``src``.

    For each matching node, looks up its uppercase text in ``mapping``;
    if found, replaces the bytes with the mapped value, with case
    preserved per ``_apply_case``. Idempotent and AST-shape-preserving:
    the new bytes are still a valid token of the same node type.

    Returns ``src`` unchanged when (a) the mapping is empty,
    (b) the source has parse errors, or (c) no nodes match.
    """
    if not src or not mapping:
        return src
    tree = parse(src)
    if tree.root_node.has_error:
        return src
    edits: list[tuple[int, int, bytes]] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == target_node_type:
            text = src[node.start_byte : node.end_byte].decode(
                "latin-1", errors="replace"
            )
            target = mapping.get(text.upper())
            if target is not None:
                replacement = _apply_case(text, target)
                if replacement != text:
                    edits.append(
                        (node.start_byte, node.end_byte, replacement.encode("latin-1"))
                    )
            continue
        stack.extend(reversed(node.children))
    if not edits:
        return src
    out = bytearray(src)
    for start, end, replacement_bytes in sorted(edits, reverse=True):
        out[start:end] = replacement_bytes
    return bytes(out)


# ---------------------------------------------------------------------------
# Rule: expand-command-keywords (S → SET)
# ---------------------------------------------------------------------------


def expand_command_keywords(src: bytes) -> bytes:
    """Rewrite abbreviated command keywords to their canonical names.

    ``S`` → ``SET``, ``W`` → ``WRITE``, ``Q`` → ``QUIT``, etc. Case is
    preserved: ``s`` → ``set`` (lowercase in, lowercase out), ``S`` →
    ``SET``. Pure inverse of :func:`compact_command_keywords` —
    composing the two (in either order) is identity modulo case.

    Use this in the ``pythonic`` preset to translate VistA-style
    compact code into more readable canonical form.
    """
    return _translate_keyword_nodes(
        src, "command_keyword", _translation_map("command", "expand")
    )


_register(
    FmtRule(
        id="expand-command-keywords",
        title="Expand abbreviated command keywords (S → SET)",
        description=(
            "Rewrites every abbreviated command keyword to its canonical "
            "name (S → SET, W → WRITE, Q → QUIT, …). Case-preserving. "
            "Inverse of compact-command-keywords. Used by the `pythonic` "
            "preset for translating VistA-style compact code."
        ),
        apply=expand_command_keywords,
    )
)


# ---------------------------------------------------------------------------
# Rule: compact-command-keywords (SET → S)
# ---------------------------------------------------------------------------


def compact_command_keywords(src: bytes) -> bytes:
    """Rewrite canonical command keywords to their canonical abbreviations.

    ``SET`` → ``S``, ``WRITE`` → ``W``, ``QUIT`` → ``Q``, etc. Case is
    preserved. Inverse of :func:`expand_command_keywords`.

    Use this in the ``compact`` preset to translate verbose code back
    to traditional VistA-style compact form.
    """
    return _translate_keyword_nodes(
        src, "command_keyword", _translation_map("command", "compact")
    )


_register(
    FmtRule(
        id="compact-command-keywords",
        title="Compact command keywords to abbreviations (SET → S)",
        description=(
            "Rewrites every canonical command keyword to its standard "
            "single- or double-letter abbreviation (SET → S, WRITE → W, "
            "QUIT → Q, …). Case-preserving. Inverse of "
            "expand-command-keywords. Used by the `compact` preset."
        ),
        apply=compact_command_keywords,
    )
)


# ---------------------------------------------------------------------------
# Rule: expand-intrinsic-functions ($L → $LENGTH)
# ---------------------------------------------------------------------------


def expand_intrinsic_functions(src: bytes) -> bytes:
    """Rewrite abbreviated intrinsic functions to their canonical names.

    ``$L(...)`` → ``$LENGTH(...)``, ``$E(...)`` → ``$EXTRACT(...)``,
    ``$ZD(...)`` → ``$ZDATE(...)``, etc. Case-preserving (M intrinsics
    are conventionally written upper-case but the parser is
    case-insensitive). Auto-fix companion to lint ``M-MOD-035``.
    """
    return _translate_keyword_nodes(
        src,
        "intrinsic_function_keyword",
        _translation_map("function", "expand"),
    )


_register(
    FmtRule(
        id="expand-intrinsic-functions",
        title="Expand abbreviated intrinsic functions ($L → $LENGTH)",
        description=(
            "Rewrites every abbreviated intrinsic-function keyword to its "
            "canonical form ($L → $LENGTH, $E → $EXTRACT, $ZD → $ZDATE, "
            "…). Case-preserving. Inverse of compact-intrinsic-functions. "
            "Auto-fix companion to lint M-MOD-035."
        ),
        apply=expand_intrinsic_functions,
    )
)


# ---------------------------------------------------------------------------
# Rule: compact-intrinsic-functions ($LENGTH → $L)
# ---------------------------------------------------------------------------


def compact_intrinsic_functions(src: bytes) -> bytes:
    """Rewrite canonical intrinsic functions to abbreviations.

    ``$LENGTH(...)`` → ``$L(...)``, ``$EXTRACT(...)`` → ``$E(...)``, etc.
    Case-preserving. Inverse of :func:`expand_intrinsic_functions`.
    """
    return _translate_keyword_nodes(
        src,
        "intrinsic_function_keyword",
        _translation_map("function", "compact"),
    )


_register(
    FmtRule(
        id="compact-intrinsic-functions",
        title="Compact intrinsic functions to abbreviations ($LENGTH → $L)",
        description=(
            "Rewrites every canonical intrinsic-function keyword to its "
            "abbreviation ($LENGTH → $L, $EXTRACT → $E, $ZDATE → $ZD, "
            "…). Case-preserving. Inverse of expand-intrinsic-functions."
        ),
        apply=compact_intrinsic_functions,
    )
)


# ---------------------------------------------------------------------------
# Rule: expand-special-variables ($T → $TEST)
# ---------------------------------------------------------------------------


def expand_special_variables(src: bytes) -> bytes:
    """Rewrite abbreviated intrinsic special variables to canonical names.

    ``$T`` → ``$TEST``, ``$H`` → ``$HOROLOG``, ``$J`` → ``$JOB``,
    ``$ZH`` → ``$ZHOROLOG``, etc. Case-preserving.
    """
    return _translate_keyword_nodes(
        src,
        "special_variable_keyword",
        _translation_map("isv", "expand"),
    )


_register(
    FmtRule(
        id="expand-special-variables",
        title="Expand abbreviated special variables ($T → $TEST)",
        description=(
            "Rewrites every abbreviated intrinsic special-variable keyword "
            "to its canonical form ($T → $TEST, $H → $HOROLOG, $J → "
            "$JOB, $ZH → $ZHOROLOG, …). Case-preserving. Inverse of "
            "compact-special-variables."
        ),
        apply=expand_special_variables,
    )
)


# ---------------------------------------------------------------------------
# Rule: compact-special-variables ($TEST → $T)
# ---------------------------------------------------------------------------


def compact_special_variables(src: bytes) -> bytes:
    """Rewrite canonical special variables to abbreviations.

    ``$TEST`` → ``$T``, ``$HOROLOG`` → ``$H``, ``$JOB`` → ``$J``, etc.
    Case-preserving. Inverse of :func:`expand_special_variables`.
    """
    return _translate_keyword_nodes(
        src,
        "special_variable_keyword",
        _translation_map("isv", "compact"),
    )


_register(
    FmtRule(
        id="compact-special-variables",
        title="Compact special variables to abbreviations ($TEST → $T)",
        description=(
            "Rewrites every canonical intrinsic special-variable keyword "
            "to its abbreviation ($TEST → $T, $HOROLOG → $H, $JOB → "
            "$J, $ZHOROLOG → $ZH, …). Case-preserving. Inverse of "
            "expand-special-variables."
        ),
        apply=compact_special_variables,
    )
)


# ---------------------------------------------------------------------------
# Translation presets
# ---------------------------------------------------------------------------


def pythonic_rules() -> list[FmtRule]:
    """The ``pythonic`` translation preset — expand all abbreviations.

    Rewrites compact VistA-style code (``S X=1 W $L(X)``) into the
    canonical-name form (``SET X=1 WRITE $LENGTH(X)``) that's easier
    to read for developers coming from Python or other modern languages
    without M's tradition of one-/two-character abbreviations.

    Includes :func:`trim_trailing_whitespace` since hygiene composes
    naturally with translation. Both presets are *normalizing* — the
    output is in one canonical form regardless of input. So they round-
    trip on already-normalized input
    (``compact(pythonic(compact(src))) == compact(src)``) but on
    *mixed-form* input (where some keywords are abbreviated and others
    canonical), the round-trip will collapse to all-canonical or all-
    abbreviated, which is the intended behavior.
    """
    rule_ids = (
        "expand-command-keywords",
        "expand-intrinsic-functions",
        "expand-special-variables",
        "trim-trailing-whitespace",
    )
    return [r for r in (rule_by_id(rid) for rid in rule_ids) if r is not None]


def compact_rules() -> list[FmtRule]:
    """The ``compact`` translation preset — abbreviate canonical names.

    Inverse of :func:`pythonic_rules`. Rewrites verbose
    ``SET X=1 WRITE $LENGTH(X)`` back to the traditional VistA-style
    ``S X=1 W $L(X)``. Includes trim-trailing-whitespace.
    """
    rule_ids = (
        "compact-command-keywords",
        "compact-intrinsic-functions",
        "compact-special-variables",
        "trim-trailing-whitespace",
    )
    return [r for r in (rule_by_id(rid) for rid in rule_ids) if r is not None]


def pythonic_lower_rules() -> list[FmtRule]:
    """The ``pythonic-lower`` translation preset — expand to lowercase.

    Like :func:`pythonic_rules` but produces all-lowercase output:
    ``S X=1 W $L(X),$T`` → ``set X=1 write $length(X),$test``. Order
    matters: the lowercase rules run *before* the expand rules so that
    expand sees a lowercase abbreviation (``s``) and — via
    :func:`_apply_case` — emits a lowercase canonical (``set``).

    M is case-insensitive on commands, intrinsic functions, and special
    variables, so the result parses identically to the upper-case
    pythonic preset; choose based on aesthetic preference.
    """
    rule_ids = (
        "lowercase-command-keywords",
        "lowercase-intrinsic-functions",
        "lowercase-special-variables",
        "expand-command-keywords",
        "expand-intrinsic-functions",
        "expand-special-variables",
        "trim-trailing-whitespace",
    )
    return [r for r in (rule_by_id(rid) for rid in rule_ids) if r is not None]
