"""m lsp — Language Server Protocol wrapper around m-cli.

Stage 1 of the LSP rollout:

  - Server scaffold over stdio (the default LSP transport)
  - ``textDocument/didOpen`` / ``didChange`` / ``didSave`` /
    ``didClose`` handlers
  - ``textDocument/publishDiagnostics`` push from ``m_cli.lint``

Future stages:

  - Stage 2: ``textDocument/formatting`` driven by ``m_cli.fmt``
  - Stage 3: ``textDocument/codeAction`` driven by the ``Rule.fixer_id``
    linkage (``trim-trailing-whitespace``, ``uppercase-command-keywords``)
  - Stage 4: workspace configuration, completion, hover

The LSP server lives behind the optional ``[lsp]`` extra so plain
``pip install m-cli`` does not pull in ``pygls`` / ``lsprotocol``
unless the user opts in.
"""

from m_cli.lsp.cli import lsp_command
from m_cli.lsp.convert import to_lsp_diagnostic, to_lsp_diagnostics

__all__ = ["lsp_command", "to_lsp_diagnostic", "to_lsp_diagnostics"]
