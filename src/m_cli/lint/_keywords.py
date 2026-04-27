"""Keyword/function/ISV sets loaded from m-standard.

Used by rules that need to know which tokens are standard, pragmatic
(both engines), or vendor-specific. Loads on first access; cheap thanks
to lru_cache.
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

# m-standard lives as a sibling project. Locate it via a search in
# parent dirs of this file. Falls back gracefully if not present.
_THIS = Path(__file__).resolve()


def _find_m_standard() -> Path | None:
    """Find the m-standard repo on disk, if available."""
    # Try ../../../../m-standard (when m-cli and m-standard are siblings under projects/)
    candidates = [
        _THIS.parent.parent.parent.parent.parent / "m-standard",
        _THIS.parent.parent.parent.parent / "m-standard",
        Path.home() / "projects" / "m-standard",
    ]
    for cand in candidates:
        integrated = cand / "integrated"
        if integrated.exists():
            return cand
    return None


def _load_tsv_column(file: Path, column: str) -> set[str]:
    """Load one column of a TSV file into a set."""
    if not file.exists():
        return set()
    out = set()
    with file.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            value = row.get(column, "").strip()
            if value:
                out.add(value)
    return out


def _load_tsv_filtered(file: Path, name_col: str, filter_col: str, filter_val: str) -> set[str]:
    """Load one column where another column has a specific value."""
    if not file.exists():
        return set()
    out = set()
    with file.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            if row.get(filter_col, "").strip() == filter_val:
                value = row.get(name_col, "").strip()
                if value:
                    out.add(value)
    return out


@lru_cache(maxsize=1)
def standard_commands() -> set[str]:
    """Set of canonical command names that are part of any standard
    (ANSI, YDB, IRIS) — i.e., NOT a non-standard Z command."""
    root = _find_m_standard()
    if root is None:
        return _FALLBACK_COMMANDS
    cmds = _load_tsv_column(root / "integrated" / "commands.tsv", "canonical_name")
    abbrevs = _load_tsv_column(root / "integrated" / "commands.tsv", "abbreviation")
    return cmds | abbrevs | _FALLBACK_COMMANDS


@lru_cache(maxsize=1)
def standard_isvs() -> set[str]:
    """Set of standard intrinsic special variables (e.g., $HOROLOG, $T)."""
    root = _find_m_standard()
    if root is None:
        return _FALLBACK_ISVS
    canonical = _load_tsv_column(
        root / "integrated" / "intrinsic-special-variables.tsv", "canonical_name"
    )
    abbrev = _load_tsv_column(
        root / "integrated" / "intrinsic-special-variables.tsv", "abbreviation"
    )
    return canonical | abbrev | _FALLBACK_ISVS


@lru_cache(maxsize=1)
def standard_functions() -> set[str]:
    """Set of standard intrinsic functions (e.g., $LENGTH, $L)."""
    root = _find_m_standard()
    if root is None:
        return _FALLBACK_FUNCTIONS
    canonical = _load_tsv_column(
        root / "integrated" / "intrinsic-functions.tsv", "canonical_name"
    )
    abbrev = _load_tsv_column(
        root / "integrated" / "intrinsic-functions.tsv", "abbreviation"
    )
    return canonical | abbrev | _FALLBACK_FUNCTIONS


# Fallback sets in case m-standard isn't installed. These are the
# ANSI core; engine-specific Z* commands/funcs live in m-standard
# proper. Letting m-standard win when present is the design intent.
_FALLBACK_COMMANDS = {
    "B", "BREAK",
    "C", "CLOSE",
    "D", "DO",
    "E", "ELSE",
    "F", "FOR",
    "G", "GOTO",
    "H", "HALT", "HANG",
    "I", "IF",
    "J", "JOB",
    "K", "KILL",
    "L", "LOCK",
    "M", "MERGE",
    "N", "NEW",
    "O", "OPEN",
    "Q", "QUIT",
    "R", "READ",
    "S", "SET",
    "TC", "TCOMMIT",
    "TRE", "TRESTART",
    "TRO", "TROLLBACK",
    "TS", "TSTART",
    "U", "USE",
    "V", "VIEW",
    "W", "WRITE",
    "X", "XECUTE",
}

_FALLBACK_ISVS = {
    "$D", "$DEVICE",
    "$EC", "$ECODE",
    "$ES", "$ESTACK",
    "$ET", "$ETRAP",
    "$H", "$HOROLOG",
    "$I", "$IO",
    "$J", "$JOB",
    "$K", "$KEY",
    "$P", "$PRINCIPAL",
    "$Q", "$QUIT",
    "$R", "$REFERENCE",
    "$ST", "$STACK",
    "$S", "$STORAGE",
    "$SY", "$SYSTEM",
    "$T", "$TEST",
    "$TL", "$TLEVEL",
    "$TR", "$TRESTART",
    "$X",
    "$Y",
    "$ZA", "$ZB", "$ZC", "$ZD", "$ZE", "$ZG", "$ZH", "$ZI", "$ZJ",
    "$ZL", "$ZN", "$ZO", "$ZP", "$ZR", "$ZS", "$ZT", "$ZU", "$ZV",
    "$ZEOF", "$ZERROR", "$ZHOROLOG", "$ZIO", "$ZJOB", "$ZMODE",
    "$ZTRAP", "$ZVERSION", "$ZPOSITION",
}

_FALLBACK_FUNCTIONS = {
    "$A", "$ASCII",
    "$C", "$CHAR",
    "$D", "$DATA",
    "$E", "$EXTRACT",
    "$F", "$FIND", "$FNUMBER",
    "$G", "$GET",
    "$I", "$INCREMENT",
    "$J", "$JUSTIFY",
    "$L", "$LENGTH", "$LISTBUILD", "$LISTGET", "$LIST", "$LISTDATA",
    "$LISTFIND", "$LISTLENGTH", "$LISTNEXT", "$LISTSAME", "$LISTVALID",
    "$N", "$NA", "$NAME", "$NEXT",
    "$O", "$ORDER",
    "$P", "$PIECE",
    "$Q", "$QLENGTH", "$QSUBSCRIPT", "$QUERY",
    "$R", "$RANDOM", "$REVERSE",
    "$S", "$SELECT",
    "$ST", "$STACK",
    "$T", "$TEXT", "$TRANSLATE",
    "$V", "$VIEW",
    # Z extensions
    "$ZA", "$ZB", "$ZC", "$ZCONVERT",
    "$ZD", "$ZDATE", "$ZDH", "$ZDT", "$ZDTH",
    "$ZF",
    "$ZH", "$ZHEX",
    "$ZN",
    "$ZP", "$ZPREVIOUS",
    "$ZS", "$ZSEARCH", "$ZSTRIP",
    "$ZT", "$ZTH", "$ZTIME", "$ZTRNLNM",
    "$ZU",
    "$ZW", "$ZWIDTH", "$ZWRITE",
}
