"""tree-sitter-m parser wrapper.

A thin façade over the tree_sitter_m Python bindings, hiding the
Language/Parser construction so callers just say `parse(src)`.

Public library surface (stable for out-of-tree tooling):

    from m_cli.parser import parse  # (src: bytes) -> tree_sitter.Tree
"""

from __future__ import annotations

from functools import lru_cache

import tree_sitter_m
from tree_sitter import Language, Parser, Tree

__all__ = ["parse"]


@lru_cache(maxsize=1)
def _language() -> Language:
    return Language(tree_sitter_m.language())


@lru_cache(maxsize=1)
def _parser() -> Parser:
    return Parser(_language())


def parse(src: bytes) -> Tree:
    """Parse M source bytes and return the resulting tree.

    The parser accepts bytes (not str). M source is line-oriented and
    typically Latin-1 / ASCII; UTF-8 is fine for comment text.
    """
    if not isinstance(src, (bytes, bytearray)):
        raise TypeError(f"parse() expects bytes, got {type(src).__name__}")
    return _parser().parse(bytes(src))
