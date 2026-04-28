"""Inline lint-suppression directives.

Mirrors the ruff / ESLint pattern: a comment in the source tells
``m lint`` to ignore specific rule diagnostics for a specific scope.

Three forms, each parsed from any ``; m-lint: ...`` comment in the
file:

  - ``; m-lint: disable=RULE[,RULE...]``
        Suppress the listed rules on the same line as the comment.
        ``set X=1 ; m-lint: disable=M-XINDX-047`` lets a one-off
        lowercase command keyword pass without a global rule
        disable.

  - ``; m-lint: disable-next-line=RULE[,RULE...]``
        Suppress on the line immediately after the comment line.
        Useful when the offending construct is too long to fit on
        one line with a trailing comment.

  - ``; m-lint: disable-file=RULE[,RULE...]``
        Suppress for the entire file. Conventionally placed at the
        top, but the parser accepts it anywhere.

The wildcard ``*`` matches every rule (``; m-lint: disable=*``).
Whitespace around the colon and equals sign is forgiving; rule IDs
are case-sensitive (``M-XINDX-019``, not ``m-xindx-019``) since rule
ids are case-sensitive throughout the codebase.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

# A directive comment is `; m-lint: KIND = ID[,ID...]`. We capture the
# kind (one of disable, disable-next-line, disable-file) and the
# value list. Whitespace-tolerant; the value list runs to the next
# whitespace or `;` so a trailing inline comment doesn't bleed in.
_DIRECTIVE_RE = re.compile(
    r";\s*m-lint\s*:\s*(disable(?:-next-line|-file)?)\s*=\s*([^\s;]+)"
)


@dataclass(frozen=True)
class Suppressions:
    """Resolved set of (line, rule_id) suppressions for one file."""

    file_disable: frozenset[str]  # rule IDs disabled file-wide; "*" = all
    line_disable: dict[int, frozenset[str]]  # 1-indexed line -> rule IDs

    @staticmethod
    def empty() -> Suppressions:
        return Suppressions(file_disable=frozenset(), line_disable={})

    def is_suppressed(self, line: int, rule_id: str) -> bool:
        """True iff a directive elsewhere in the file would silence
        the given (line, rule_id) diagnostic."""
        if "*" in self.file_disable or rule_id in self.file_disable:
            return True
        rules = self.line_disable.get(line, frozenset())
        return "*" in rules or rule_id in rules


def parse_directives(src: bytes) -> Suppressions:
    """Walk the source for ``; m-lint: ...`` comments and resolve
    them to a ``Suppressions`` object.

    Multiple directives on the same line accumulate. Unknown / bad
    directive forms are silently ignored — we never want a typo in a
    comment to crash the lint pass."""
    file_disable: set[str] = set()
    line_disable: dict[int, set[str]] = defaultdict(set)

    # Decode line-by-line so byte-offset → line-number is trivial and
    # the regex stays anchored to single-line comments.
    text = src.decode("latin-1", errors="replace")
    for i, raw_line in enumerate(text.splitlines(), start=1):
        for m in _DIRECTIVE_RE.finditer(raw_line):
            kind = m.group(1)
            ids = {s.strip() for s in m.group(2).split(",") if s.strip()}
            if not ids:
                continue
            if kind == "disable-file":
                file_disable.update(ids)
            elif kind == "disable-next-line":
                line_disable[i + 1].update(ids)
            else:  # plain "disable" → same line
                line_disable[i].update(ids)

    return Suppressions(
        file_disable=frozenset(file_disable),
        line_disable={k: frozenset(v) for k, v in line_disable.items()},
    )


__all__ = ["Suppressions", "parse_directives"]
