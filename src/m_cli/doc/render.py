"""Render extracted docs into Markdown / HTML."""

from __future__ import annotations

import html
from typing import Iterable

from m_cli.doc.extract import RoutineDoc


def render_markdown(routines: Iterable[RoutineDoc]) -> str:
    parts: list[str] = ["# M routines\n"]
    for rd in routines:
        parts.append(f"\n## {rd.name}\n")
        if rd.summary:
            parts.append(f"\n{rd.summary}\n")
        meta_bits: list[str] = []
        if rd.version:
            meta_bits.append(f"version `{rd.version}`")
        if rd.package:
            meta_bits.append(f"package `{rd.package}`")
        if rd.path:
            meta_bits.append(f"source `{rd.path}`")
        if meta_bits:
            parts.append("\n_" + " · ".join(meta_bits) + "_\n")

        if rd.labels:
            parts.append("\n### Labels\n")
            for lbl in rd.labels:
                signature = f"`{lbl.name}{lbl.formals or ''}`"
                if lbl.summary:
                    parts.append(f"\n- {signature} — {lbl.summary}")
                else:
                    parts.append(f"\n- {signature}")
            parts.append("\n")
    return "".join(parts)


def render_html(routines: Iterable[RoutineDoc]) -> str:
    body: list[str] = []
    body.append("<h1>M routines</h1>\n")
    for rd in routines:
        body.append(f"<h2>{html.escape(rd.name)}</h2>\n")
        if rd.summary:
            body.append(f"<p>{html.escape(rd.summary)}</p>\n")
        meta_bits: list[str] = []
        if rd.version:
            meta_bits.append(f"version <code>{html.escape(rd.version)}</code>")
        if rd.package:
            meta_bits.append(f"package <code>{html.escape(rd.package)}</code>")
        if rd.path:
            meta_bits.append(f"source <code>{html.escape(str(rd.path))}</code>")
        if meta_bits:
            body.append("<p><em>" + " &middot; ".join(meta_bits) + "</em></p>\n")
        if rd.labels:
            body.append("<h3>Labels</h3>\n<ul>\n")
            for lbl in rd.labels:
                signature = html.escape(f"{lbl.name}{lbl.formals or ''}")
                if lbl.summary:
                    body.append(
                        f"<li><code>{signature}</code> &mdash; "
                        f"{html.escape(lbl.summary)}</li>\n"
                    )
                else:
                    body.append(f"<li><code>{signature}</code></li>\n")
            body.append("</ul>\n")
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        "<title>M routines</title>\n"
        "<style>body{font-family:system-ui,sans-serif;max-width:48rem;"
        "margin:2rem auto;padding:0 1rem;line-height:1.5}"
        "code{background:#f4f4f4;padding:0.1rem 0.3rem;border-radius:3px}"
        "h2{border-bottom:1px solid #ddd;padding-bottom:0.2rem}</style>\n"
        "</head>\n<body>\n" + "".join(body) + "</body>\n</html>\n"
    )
