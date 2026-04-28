"""`m lsp` command implementation.

Starts the m-cli Language Server over stdio (the default LSP
transport). Editors invoke ``m lsp`` as a subprocess and exchange
LSP messages on stdin/stdout.
"""

from __future__ import annotations

import argparse
import logging
import sys


def lsp_command(args: argparse.Namespace) -> int:
    """Entry point for `m lsp`. Returns process exit code.

    The server runs until the editor closes its stdin (the standard
    LSP shutdown signal). Logging goes to stderr — stdout is reserved
    for the LSP message channel.
    """
    _configure_logging(args.verbose)
    try:
        from m_cli.lsp.server import run_stdio
    except ImportError as e:
        print(
            f"m lsp: missing optional dependency — install with `pip install 'm-cli[lsp]'` ({e})",
            file=sys.stderr,
        )
        return 2
    return run_stdio()


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        stream=sys.stderr,
    )
