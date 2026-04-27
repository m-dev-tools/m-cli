"""mtime-based change detection for `.m` files under one or more roots.

Each ``poll_once()`` call walks the configured roots, stats every
tracked file, and returns the set of paths whose mtime has shifted (or
which appeared / disappeared) since the previous call. The first call
is a baseline — it returns an empty set even though every file is
"new" to the poller — so callers should run their initial pass before
the first poll, then enter the watch loop.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


class Poller:
    """Polling watcher with mtime-based change detection."""

    def __init__(self, paths: Iterable[Path]) -> None:
        self._roots = list(paths)
        self._mtimes: dict[Path, float] = {}
        self._primed = False

    def poll_once(self) -> set[Path]:
        """Return the set of `.m` files whose state has changed since last call."""
        current = self._scan()
        if not self._primed:
            self._mtimes = current
            self._primed = True
            return set()
        prev = self._mtimes
        changed: set[Path] = set()
        for path, mtime in current.items():
            if path not in prev or prev[path] != mtime:
                changed.add(path)
        for path in prev:
            if path not in current:
                changed.add(path)
        self._mtimes = current
        return changed

    def _scan(self) -> dict[Path, float]:
        out: dict[Path, float] = {}
        for root in self._roots:
            if root.is_dir():
                for p in root.rglob("*.m"):
                    if p.is_file():
                        out[p] = p.stat().st_mtime
            elif root.is_file() and root.suffix == ".m":
                out[root] = root.stat().st_mtime
        return out
