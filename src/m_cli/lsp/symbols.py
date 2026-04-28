"""Symbol identification for the LSP — Stage 4 (hover + completion).

Two responsibilities:

  - ``token_at(line, character)`` extracts the M identifier or
    intrinsic name under the cursor (e.g. ``SET``, ``$LENGTH``,
    ``$ZTRNLNM``).
  - ``lookup_keyword(token)`` resolves a token to its m-standard
    metadata — kind (command/isv/function), canonical name,
    abbreviation, syntax format, standard status. ``all_keywords()``
    returns the full set for completion.

The data comes from ``m_cli.lint._keywords.keyword_records()`` which
loads m-standard's TSVs (with a synthetic fallback for environments
that don't have m-standard checked out).
"""

from __future__ import annotations

from functools import lru_cache

from m_cli.lint._keywords import KeywordRecord, keyword_records


def token_at(line: str, character: int) -> str | None:
    """Return the M identifier at ``character`` on ``line``, or None.

    Word characters are ``[A-Za-z0-9$%]``. The cursor may sit on or
    just past the token (LSP convention: ``character`` can equal the
    line length when the cursor is at end-of-line).
    """
    if character < 0 or character > len(line):
        return None

    def is_word(c: str) -> bool:
        return c.isalnum() or c == "$" or c == "%"

    start = character
    while start > 0 and is_word(line[start - 1]):
        start -= 1
    end = character
    while end < len(line) and is_word(line[end]):
        end += 1
    token = line[start:end]
    return token if token else None


@lru_cache(maxsize=1)
def _by_token() -> dict[str, KeywordRecord]:
    """Index every record under both its canonical name and abbreviation,
    upper-cased. M is case-insensitive for command keywords and intrinsics."""
    out: dict[str, KeywordRecord] = {}
    for r in keyword_records():
        out[r.canonical.upper()] = r
        if r.abbreviation:
            out[r.abbreviation.upper()] = r
    return out


def lookup_keyword(token: str) -> KeywordRecord | None:
    """Return the m-standard record for ``token`` (case-insensitive),
    or None if the token is not a known command, ISV, or function."""
    return _by_token().get(token.upper())


def all_keywords() -> list[KeywordRecord]:
    """All known commands, ISVs, and intrinsic functions, in canonical
    order. Used to build the completion list."""
    return list(keyword_records())


__all__ = ["token_at", "lookup_keyword", "all_keywords", "KeywordRecord"]
