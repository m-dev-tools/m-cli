"""``m search <query>`` — full-text search over the m-stdlib manifest.

Linear scan of every ``(module, label)`` entry. For each, we scan the
synopsis, the description, and the body of every ``@example`` —
case-insensitively — for the literal substring of every space-
separated token in the query. A match must contain *all* tokens
(AND-style) to land in the result set.

Ranking is simple and stable:

* Tier A — match in synopsis (the user typed something that names
  the function being looked for; cheapest to scan, most likely the
  thing they wanted).
* Tier B — match in description (deeper prose explaining behaviour).
* Tier C — match only in examples (the keyword appears in usage
  snippets but not in the prose).

Within each tier, results sort by ``module.label`` for determinism.
True fuzzy ranking (BM25, trigram, edit distance) is deliberately
out of scope for v1 — substring + tier is enough to find anything
the user already knows the name of, which is the dominant lookup
shape on a 32-module library.

Per the discoverability plan §4.2, this command shares manifest
discovery with ``m doc`` (``find_manifest()``). Same fallback chain;
same JSON shape; same exit-code conventions (0 = matches, 1 = no
matches, 2 = manifest unreachable).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass

from m_cli.doc.lookup import find_manifest, load_manifest


@dataclass(frozen=True)
class _SearchHit:
    module: str
    label: str
    synopsis: str
    tier: int  # 0 = synopsis, 1 = description, 2 = example


def _scan_label(
    module: str, label: str, label_data: dict, tokens: list[str]
) -> _SearchHit | None:
    """Return a hit (and its tier) iff every token appears in at least
    one of (synopsis | description | examples)."""
    syn = (label_data.get("synopsis") or "").lower()
    desc = (label_data.get("description") or "").lower()
    examples_text = "\n".join(str(e) for e in (label_data.get("examples") or [])).lower()

    # First, every token must be present somewhere in the haystack —
    # otherwise the AND-match fails.
    haystack = syn + "\n" + desc + "\n" + examples_text
    for tok in tokens:
        if tok not in haystack:
            return None

    # Tier: where does the FIRST token land? Synopsis hit wins; else
    # description; else example. We use the first token because the
    # user typed it first — it carries the most weight in their head.
    primary = tokens[0]
    if primary in syn:
        tier = 0
    elif primary in desc:
        tier = 1
    else:
        tier = 2

    return _SearchHit(
        module=module,
        label=label,
        synopsis=label_data.get("synopsis") or "",
        tier=tier,
    )


def _scan_manifest(query: str, manifest: dict) -> list[_SearchHit]:
    tokens = [t.lower() for t in query.split() if t.strip()]
    if not tokens:
        return []
    out: list[_SearchHit] = []
    modules: dict = manifest.get("modules", {})
    for mod_name in sorted(modules.keys()):
        mod = modules[mod_name]
        for label_name, label_data in (mod.get("labels") or {}).items():
            hit = _scan_label(mod_name, label_name, label_data, tokens)
            if hit is not None:
                out.append(hit)
    out.sort(key=lambda h: (h.tier, h.module, h.label))
    return out


def search_command(args: argparse.Namespace) -> int:
    explicit = getattr(args, "manifest", None)
    manifest_path = find_manifest(explicit=explicit)
    if manifest_path is None:
        sys.stderr.write(
            "m search: could not find dist/stdlib-manifest.json. "
            "Run `make manifest` from m-stdlib or pass --manifest PATH.\n"
        )
        return 2
    try:
        manifest = load_manifest(manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"m search: failed to load {manifest_path}: {exc}\n")
        return 2

    query = (getattr(args, "query", "") or "").strip()
    if not query:
        sys.stderr.write("m search: missing query.\n  Usage: m search <words>\n")
        return 2

    limit = getattr(args, "limit", 50) or 50
    hits = _scan_manifest(query, manifest)
    if not hits:
        sys.stderr.write(f"m search: no matches for {query!r}.\n")
        return 1

    truncated = len(hits) > limit
    shown = hits[:limit]

    # Width-align the qualified name column so synopses line up.
    name_w = max(len(f"{h.module}.{h.label}") for h in shown)

    for h in shown:
        qualified = f"{h.module}.{h.label}"
        if h.synopsis:
            sys.stdout.write(f"  {qualified:{name_w}}  {h.synopsis}\n")
        else:
            sys.stdout.write(f"  {qualified}\n")

    if truncated:
        sys.stderr.write(
            f"m search: showing {limit} of {len(hits)} matches "
            f"(use --limit N to see more).\n"
        )
    return 0


__all__ = ["search_command"]
