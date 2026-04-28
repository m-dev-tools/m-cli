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


def canonical_rules() -> list[FmtRule]:
    """All rules considered safe for the default canonical layout.

    Currently this is *every* registered rule — none are gated behind
    additional opt-in flags. As the rule set grows, this function will
    pick the SAC-default subset.
    """
    return all_rules()


def select_fmt_rules(spec: str) -> list[FmtRule]:
    """Resolve a CLI-style spec to a list of rules.

    Accepted forms:
      - ``"none"`` — empty list (identity formatter)
      - ``"canonical"`` — every safe rule (current default for opted-in users)
      - ``"all"`` — every registered rule
      - ``"<id>,<id>,..."`` — explicit, comma-separated ids
    """
    spec = spec.strip()
    if spec in ("none", ""):
        return []
    if spec == "canonical":
        return canonical_rules()
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


def uppercase_command_keywords(src: bytes) -> bytes:
    """Rewrite every ``command_keyword`` AST node to upper-case ASCII.

    Walks the parse tree, collects byte ranges of ``command_keyword``
    nodes whose text differs from its upper-case form, and applies the
    edits right-to-left so byte indices stay valid. SAC §3.3 prefers
    upper-case command keywords; this is the auto-fix for lint
    ``M-XINDX-047``.

    On a parse-error tree the rule returns ``src`` unchanged — the
    formatter pipeline raises ``ParseError`` further up.
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
        if node.type == "command_keyword":
            text = src[node.start_byte : node.end_byte]
            upper = text.upper()
            if text != upper:
                edits.append((node.start_byte, node.end_byte, upper))
            continue  # command_keyword has no children we care about
        stack.extend(reversed(node.children))
    if not edits:
        return src
    out = bytearray(src)
    for start, end, replacement in sorted(edits, reverse=True):
        out[start:end] = replacement
    return bytes(out)


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
