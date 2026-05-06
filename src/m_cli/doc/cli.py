"""`m doc` command — extract M docstrings to Markdown / HTML."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from m_cli.build.runner import discover_files
from m_cli.doc.extract import extract_routine_doc
from m_cli.doc.render import render_html, render_markdown


def doc_command(args: argparse.Namespace) -> int:
    paths = list(args.paths) if args.paths else [Path.cwd()]
    files = discover_files(paths)
    if not files:
        print(
            "m doc: no .m files found in: " + ", ".join(str(p) for p in paths),
            file=sys.stderr,
        )
        return 2

    routines = [extract_routine_doc(f, f.read_bytes()) for f in files]
    fmt = getattr(args, "format", "markdown")
    if fmt == "html":
        body = render_html(routines)
    else:
        body = render_markdown(routines)

    output = getattr(args, "output", None)
    if output:
        Path(output).write_text(body)
    else:
        sys.stdout.write(body)
    return 0
