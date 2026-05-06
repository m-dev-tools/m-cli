"""m doc — extract M docstrings into Markdown / HTML.

Walks the given paths for ``.m`` files, parses each via tree-sitter-m,
and emits a structured document indexed by routine and label. The
input convention is the modern ``LABEL ; @summary <one-line>`` style
(M-MOD-028) plus the VistA version stub (line 2 ``;;<v>;<pkg>;;<date>;``).
Output: Markdown by default, HTML with ``--format=html``.
"""

from m_cli.doc.cli import doc_command
from m_cli.doc.extract import LabelDoc, RoutineDoc, extract_routine_doc
from m_cli.doc.render import render_html, render_markdown

__all__ = [
    "doc_command",
    "LabelDoc",
    "RoutineDoc",
    "extract_routine_doc",
    "render_html",
    "render_markdown",
]
