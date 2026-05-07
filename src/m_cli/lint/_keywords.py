"""Keyword/function/ISV sets loaded from m-standard.

Used by rules that need to know which tokens are standard, pragmatic
(both engines), or vendor-specific. Loads on first access; cheap thanks
to lru_cache.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# m-standard lives as a sibling project. Locate it via a search in
# parent dirs of this file. Falls back gracefully if not present.
_THIS = Path(__file__).resolve()


def _find_m_standard() -> Path | None:
    """Find the m-standard repo on disk, if available.

    Returns a path ``P`` such that ``P / "integrated" / *.tsv`` resolves
    to the integrated TSV files. m-standard's layout has shifted between
    a flat ``integrated/`` at the repo root and a nested ``docs/integrated/``;
    we accept either.
    """
    repo_candidates = [
        _THIS.parent.parent.parent.parent.parent / "m-standard",
        _THIS.parent.parent.parent.parent / "m-standard",
        Path.home() / "projects" / "m-standard",
    ]
    for repo in repo_candidates:
        for sub in ("", "docs"):
            cand = repo / sub if sub else repo
            if (cand / "integrated").exists():
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


@dataclass(frozen=True)
class KeywordRecord:
    """Structured row for a single command, ISV, or intrinsic function.

    Used by the LSP wrapper for hover/completion. The lint rules use
    the simpler ``standard_*`` set views above.
    """

    kind: str  # "command" | "isv" | "function"
    canonical: str
    abbreviation: str  # may be empty
    format: str  # syntax format from m-standard, e.g. "S[ET] postcond ..."
    standard_status: str  # "ansi" | "ydb" | "iris" | "ydb-and-iris" | etc.


def _load_records(file: Path, kind: str) -> list[KeywordRecord]:
    if not file.exists():
        return []
    out: list[KeywordRecord] = []
    with file.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            canonical = row.get("canonical_name", "").strip()
            if not canonical:
                continue
            out.append(
                KeywordRecord(
                    kind=kind,
                    canonical=canonical,
                    abbreviation=row.get("abbreviation", "").strip(),
                    format=row.get("format", "").strip(),
                    standard_status=row.get("standard_status", "").strip(),
                )
            )
    return out


@lru_cache(maxsize=1)
def keyword_records() -> list[KeywordRecord]:
    """All commands, ISVs, and intrinsic functions as structured rows.

    Falls back to a synthetic record per name from the simple sets
    when m-standard isn't available — abbreviation/format/status are
    empty in that case.
    """
    root = _find_m_standard()
    if root is None:
        synth: list[KeywordRecord] = []
        for kind, names in (
            ("command", _FALLBACK_COMMANDS),
            ("isv", _FALLBACK_ISVS),
            ("function", _FALLBACK_FUNCTIONS),
        ):
            for name in sorted(names):
                synth.append(
                    KeywordRecord(
                        kind=kind, canonical=name, abbreviation="", format="", standard_status=""
                    )
                )
        return synth
    integrated = root / "integrated"
    return [
        *_load_records(integrated / "commands.tsv", "command"),
        *_load_records(integrated / "intrinsic-special-variables.tsv", "isv"),
        *_load_records(integrated / "intrinsic-functions.tsv", "function"),
    ]


@lru_cache(maxsize=1)
def standard_functions() -> set[str]:
    """Set of standard intrinsic functions (e.g., $LENGTH, $L)."""
    root = _find_m_standard()
    if root is None:
        return _FALLBACK_FUNCTIONS
    canonical = _load_tsv_column(root / "integrated" / "intrinsic-functions.tsv", "canonical_name")
    abbrev = _load_tsv_column(root / "integrated" / "intrinsic-functions.tsv", "abbreviation")
    return canonical | abbrev | _FALLBACK_FUNCTIONS


# Map ``target_engine`` → set of m-standard ``standard_status`` values
# whose tokens are SAFE to use on that engine. Per m-standard's data
# model:
#
#   "ansi"             — pure ANSI M-1995 / ISO 11756; safe everywhere
#   "ydb-extension"    — YottaDB-only extension
#   "iris-extension"   — IRIS-only extension
#   "multi-vendor-ext" — extension supported on both YDB and IRIS but
#                       not in ANSI
#
# An "any" target — meaning "this code must be portable to any future
# M engine" — accepts only ANSI tokens.
_ENGINE_SAFE_STATUSES: dict[str, frozenset[str]] = {
    "any": frozenset({"ansi"}),
    "yottadb": frozenset({"ansi", "ydb-extension", "multi-vendor-ext"}),
    "iris": frozenset({"ansi", "iris-extension", "multi-vendor-ext"}),
}


@lru_cache(maxsize=8)
def engine_allowlist(target_engine: str, kind: str) -> frozenset[str]:
    """Return the set of token names (canonical + abbreviation) safe
    to use on the given engine for the given kind.

    ``target_engine`` is one of ``"any"``, ``"yottadb"``, or ``"iris"``.
    Unknown values fall back to the strictest set (ANSI-only).

    ``kind`` is one of ``"command"``, ``"isv"``, or ``"function"``.

    All returned names are uppercase. The set includes both the
    canonical form (e.g. ``"$ZHOROLOG"``) and the abbreviation
    (``"$ZH"``) when m-standard records one. When m-standard is not
    available, falls back to the simple ``standard_*()`` sets, which
    means engine-aware checks degrade gracefully to "ANSI-only".
    """
    safe_statuses = _ENGINE_SAFE_STATUSES.get(
        target_engine, _ENGINE_SAFE_STATUSES["any"]
    )
    out: set[str] = set()
    has_record_data = False
    for rec in keyword_records():
        if rec.kind != kind:
            continue
        # Distinguish "real status set" from "synthetic fallback" — the
        # synthetic fallback path leaves standard_status empty.
        if rec.standard_status:
            has_record_data = True
            if rec.standard_status not in safe_statuses:
                continue
        if rec.canonical:
            out.add(rec.canonical.upper())
        if rec.abbreviation:
            out.add(rec.abbreviation.upper())
    if not has_record_data:
        # m-standard wasn't available — fall back to the simple sets.
        # All sets here represent the ANSI baseline so this is the
        # strictest behavior, matching ``target_engine="any"``.
        if kind == "command":
            return frozenset(s.upper() for s in standard_commands())
        if kind == "isv":
            return frozenset(s.upper() for s in standard_isvs())
        if kind == "function":
            return frozenset(s.upper() for s in standard_functions())
    return frozenset(out)


# Fallback sets in case m-standard isn't installed. These are the
# ANSI core; engine-specific Z* commands/funcs live in m-standard
# proper. Letting m-standard win when present is the design intent.
_FALLBACK_COMMANDS = {
    "B",
    "BREAK",
    "C",
    "CLOSE",
    "D",
    "DO",
    "E",
    "ELSE",
    "F",
    "FOR",
    "G",
    "GOTO",
    "H",
    "HALT",
    "HANG",
    "I",
    "IF",
    "J",
    "JOB",
    "K",
    "KILL",
    "L",
    "LOCK",
    "M",
    "MERGE",
    "N",
    "NEW",
    "O",
    "OPEN",
    "Q",
    "QUIT",
    "R",
    "READ",
    "S",
    "SET",
    "TC",
    "TCOMMIT",
    "TRE",
    "TRESTART",
    "TRO",
    "TROLLBACK",
    "TS",
    "TSTART",
    "U",
    "USE",
    "V",
    "VIEW",
    "W",
    "WRITE",
    "X",
    "XECUTE",
}

_FALLBACK_ISVS = {
    "$D",
    "$DEVICE",
    "$EC",
    "$ECODE",
    "$ES",
    "$ESTACK",
    "$ET",
    "$ETRAP",
    "$H",
    "$HOROLOG",
    "$I",
    "$IO",
    "$J",
    "$JOB",
    "$K",
    "$KEY",
    "$P",
    "$PRINCIPAL",
    "$Q",
    "$QUIT",
    "$R",
    "$REFERENCE",
    "$ST",
    "$STACK",
    "$S",
    "$STORAGE",
    "$SY",
    "$SYSTEM",
    "$T",
    "$TEST",
    "$TL",
    "$TLEVEL",
    "$TR",
    "$TRESTART",
    "$X",
    "$Y",
    "$ZA",
    "$ZB",
    "$ZC",
    "$ZD",
    "$ZE",
    "$ZG",
    "$ZH",
    "$ZI",
    "$ZJ",
    "$ZL",
    "$ZN",
    "$ZO",
    "$ZP",
    "$ZR",
    "$ZS",
    "$ZT",
    "$ZU",
    "$ZV",
    "$ZEOF",
    "$ZERROR",
    "$ZHOROLOG",
    "$ZIO",
    "$ZJOB",
    "$ZMODE",
    "$ZTRAP",
    "$ZVERSION",
    "$ZPOSITION",
}

_FALLBACK_FUNCTIONS = {
    "$A",
    "$ASCII",
    "$C",
    "$CHAR",
    "$D",
    "$DATA",
    "$E",
    "$EXTRACT",
    "$F",
    "$FIND",
    "$FNUMBER",
    "$G",
    "$GET",
    "$I",
    "$INCREMENT",
    "$J",
    "$JUSTIFY",
    "$L",
    "$LENGTH",
    "$LISTBUILD",
    "$LISTGET",
    "$LIST",
    "$LISTDATA",
    "$LISTFIND",
    "$LISTLENGTH",
    "$LISTNEXT",
    "$LISTSAME",
    "$LISTVALID",
    "$N",
    "$NA",
    "$NAME",
    "$NEXT",
    "$O",
    "$ORDER",
    "$P",
    "$PIECE",
    "$Q",
    "$QLENGTH",
    "$QSUBSCRIPT",
    "$QUERY",
    "$R",
    "$RANDOM",
    "$REVERSE",
    "$S",
    "$SELECT",
    "$ST",
    "$STACK",
    "$T",
    "$TEXT",
    "$TRANSLATE",
    "$V",
    "$VIEW",
    # Z extensions
    "$ZA",
    "$ZB",
    "$ZC",
    "$ZCONVERT",
    "$ZD",
    "$ZDATE",
    "$ZDH",
    "$ZDT",
    "$ZDTH",
    "$ZF",
    "$ZH",
    "$ZHEX",
    "$ZN",
    "$ZP",
    "$ZPREVIOUS",
    "$ZS",
    "$ZSEARCH",
    "$ZSTRIP",
    "$ZT",
    "$ZTH",
    "$ZTIME",
    "$ZTRNLNM",
    "$ZU",
    "$ZW",
    "$ZWIDTH",
    "$ZWRITE",
}
