"""Data-flow infrastructure for path-sensitive lint rules (Phase 7).

Public surface:

  * :class:`CFG`, :class:`Block` — per-label control-flow graph
  * :func:`build_cfgs` — construct CFGs for every top-level label

Downstream analyzers (reaching-definitions, lock-state) layer on top
of this graph; their public API will be added here as Phase 7
progresses.
"""

from __future__ import annotations

from m_cli.lint.flow.cfg import CFG, Block, build_cfgs

__all__ = ["CFG", "Block", "build_cfgs"]
