"""Data-flow infrastructure for path-sensitive lint rules (Phase 7).

Public surface:

  * :class:`CFG`, :class:`Block`, :func:`build_cfgs` — per-label CFG
  * :class:`Effects`, :class:`VarUse`, :func:`effects`,
    :func:`formal_params` — per-command variable extraction
  * :func:`analyze` — definite-assignment (forward MUST) over the CFG
"""

from __future__ import annotations

from m_cli.lint.flow.cfg import CFG, Block, build_cfgs
from m_cli.lint.flow.reaching import analyze
from m_cli.lint.flow.vars import (
    Effects,
    VarUse,
    effects,
    effects_of_argument,
    formal_params,
    uses_in_subtree,
)

__all__ = [
    "CFG",
    "Block",
    "Effects",
    "VarUse",
    "analyze",
    "build_cfgs",
    "effects",
    "effects_of_argument",
    "formal_params",
    "uses_in_subtree",
]
