"""godoc-style output formatting for ``m doc``.

Three output forms:

* **Long form** (default) — multi-section render of a single module
  or label entry. Layout matches the example in
  m-stdlib/docs/plans/discoverability-and-tooling-plan.md § 4.1.
* **Short form** (``--short``) — one synopsis line per match.
* **JSON form** (``--json``) — the raw manifest entry, pretty-printed.

The formatter is pure: it takes data structures (LabelMatch /
ModuleMatch from :mod:`m_cli.doc.lookup`) and returns strings. No
file I/O, no manifest loading. Tests run against in-memory fixtures.
"""

from __future__ import annotations

import json

from m_cli.doc.lookup import LabelMatch, ModuleMatch

# ----- Long form -------------------------------------------------------------


def format_module_long(m: ModuleMatch) -> str:
    """Render a module overview: synopsis, label list, error list, source."""
    d = m.module_data
    out: list[str] = []
    syn = (d.get("synopsis") or "").strip()
    out.append(f"module {m.module}")
    if syn:
        out.append("")
        out.append(syn)
    desc = (d.get("description") or "").strip()
    if desc:
        out.append("")
        out.append(desc)
    labels = d.get("labels", {})
    if labels:
        out.append("")
        out.append("public labels:")
        for name in sorted(labels.keys()):
            label_syn = (labels[name].get("synopsis") or "").strip()
            if label_syn:
                out.append(f"  {name:20s} {label_syn}")
            else:
                out.append(f"  {name}")
    errors = d.get("errors") or []
    if errors:
        out.append("")
        out.append("errors:")
        for code in sorted(errors):
            out.append(f"  {code}")
    src = d.get("source") or {}
    if src.get("file"):
        out.append("")
        out.append(f"source: {src['file']}")
    return "\n".join(out) + "\n"


def format_label_long(m: LabelMatch) -> str:
    """Render a single label: signature, synopsis, params, returns, raises,
    examples, since/stable, see, source."""
    d = m.label_data
    out: list[str] = []
    sig = d.get("signature") or f"{m.label}^{m.module}"
    returns = d.get("returns") or {}
    arrow = ""
    if isinstance(returns, dict) and returns.get("type"):
        arrow = f" → {returns['type']}"
    out.append(f"{sig}{arrow}")
    syn = (d.get("synopsis") or "").strip()
    if syn:
        out.append("")
        out.append(syn)

    params = d.get("params") or []
    if params:
        out.append("")
        # Width-aligned name/type columns when possible.
        name_w = max(len(p.get("name", "")) for p in params)
        type_w = max(len(p.get("type", "")) for p in params)
        for p in params:
            name = p.get("name", "")
            ptype = p.get("type", "")
            doc = p.get("doc", "")
            out.append(f"  {name:{name_w}}  {ptype:{type_w}}  {doc}".rstrip())

    if isinstance(returns, dict) and (returns.get("type") or returns.get("doc")):
        out.append("")
        rtype = returns.get("type", "")
        rdoc = returns.get("doc", "")
        if rtype and rdoc:
            out.append(f"returns: {rtype}  {rdoc}")
        elif rtype:
            out.append(f"returns: {rtype}")
        else:
            out.append(f"returns: {rdoc}")

    raises = d.get("raises") or []
    if raises:
        out.append("")
        out.append("raises:")
        for r in raises:
            code = r.get("code", "")
            rdoc = r.get("doc", "")
            if rdoc:
                out.append(f"  {code}  {rdoc}")
            else:
                out.append(f"  {code}")

    since = d.get("since") or ""
    stable = d.get("stable") or ""
    if since or stable:
        bits: list[str] = []
        if since:
            bits.append(f"since: {since}")
        if stable:
            bits.append(stable)
        out.append("")
        out.append("   ".join(bits))

    see = d.get("see_also") or []
    if see:
        out.append("see: " + ", ".join(see))

    examples = d.get("examples") or []
    if examples:
        out.append("")
        out.append("example:")
        for ex in examples:
            for line in str(ex).splitlines():
                out.append(f"  {line}")

    desc = (d.get("description") or "").strip()
    if desc:
        out.append("")
        out.append(desc)

    src = d.get("source") or {}
    if src.get("file"):
        src_line = src.get("line")
        if src_line:
            out.append("")
            out.append(f"source: {src['file']}:{src_line}")
        else:
            out.append("")
            out.append(f"source: {src['file']}")

    return "\n".join(out) + "\n"


# ----- Short form ------------------------------------------------------------


def format_module_short(m: ModuleMatch) -> str:
    syn = (m.module_data.get("synopsis") or "").strip()
    return f"{m.module} — {syn}\n" if syn else f"{m.module}\n"


def format_label_short(m: LabelMatch) -> str:
    syn = (m.label_data.get("synopsis") or "").strip()
    qualified = f"{m.module}.{m.label}"
    return f"{qualified} — {syn}\n" if syn else f"{qualified}\n"


# ----- JSON form -------------------------------------------------------------


def format_module_json(m: ModuleMatch) -> str:
    return json.dumps(m.module_data, indent=2, ensure_ascii=False) + "\n"


def format_label_json(m: LabelMatch) -> str:
    return json.dumps(m.label_data, indent=2, ensure_ascii=False) + "\n"


# ----- Disambiguation list (multi-hit fuzzy) --------------------------------


def format_label_list(matches: list[LabelMatch]) -> str:
    """When a bare-name lookup returns multiple hits, render a one-line
    list keyed on ``module.label``. Caller is expected to print this
    instead of any single-match formatter so users can disambiguate."""
    out: list[str] = []
    out.append(f"{len(matches)} matches:")
    for m in matches:
        syn = (m.label_data.get("synopsis") or "").strip()
        qualified = f"{m.module}.{m.label}"
        if syn:
            out.append(f"  {qualified:30s} {syn}")
        else:
            out.append(f"  {qualified}")
    return "\n".join(out) + "\n"


__all__ = [
    "format_label_json",
    "format_label_list",
    "format_label_long",
    "format_label_short",
    "format_module_json",
    "format_module_long",
    "format_module_short",
]
