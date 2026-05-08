"""Manifest loading + symbol resolution for ``m doc``.

The canonical machine-readable surface is m-stdlib's
``dist/stdlib-manifest.json`` — a single JSON file mapping every
public module and label to its signature, source location, and
tag-derived metadata. ``m doc`` is a thin reader on top of that
file; this module owns the resolver.

Discovery order
===============

1. ``--manifest PATH`` flag (CLI override; absolute path).
2. ``$M_CLI_MANIFEST`` environment variable.
3. Walk **up** from the current working directory looking for
   ``dist/stdlib-manifest.json`` — this catches the natural case of
   running ``m doc`` from inside an m-stdlib checkout.
4. Fall back to ``~/projects/m-stdlib/dist/stdlib-manifest.json``
   for users with the conventional layout.

If none of the above resolve, ``find_manifest()`` returns ``None``
and callers emit a help message pointing at the discoverability
plan.

Symbol forms
============

The CLI passes a single string; ``resolve_symbol()`` classifies it:

* ``STDJSON``        — module overview (single match if known)
* ``STDJSON.parse``  — single label (single match if known)
* ``parse``          — fuzzy bare-name lookup; can return any
                       number of label matches across modules
* ``STDXX``          — uppercase but unknown module → empty match
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


# A single fully-qualified label hit returned by the resolver.
@dataclass(frozen=True)
class LabelMatch:
    """One ``MODULE.label`` resolution.

    Both the module name and label name are surfaced so the formatter
    can render the canonical ``$$label^MODULE`` signature without
    re-parsing the symbol string.
    """

    module: str
    label: str
    label_data: dict


# A module-level resolution. ``label_data`` is None — module hits
# render the routine-header view, not a single label.
@dataclass(frozen=True)
class ModuleMatch:
    module: str
    module_data: dict


def find_manifest(
    *,
    explicit: str | None = None,
    env: os._Environ | None = None,
    start: Path | None = None,
) -> Path | None:
    """Resolve the path to ``dist/stdlib-manifest.json`` per the
    discovery order in the module docstring.

    Returns the resolved path or ``None`` if no manifest is reachable.
    Caller decides what error message to present.
    """
    if explicit:
        p = Path(explicit).expanduser()
        return p if p.is_file() else None

    env_map = env if env is not None else os.environ
    env_path = env_map.get("M_CLI_MANIFEST")
    if env_path:
        p = Path(env_path).expanduser()
        if p.is_file():
            return p

    cur = (start or Path.cwd()).resolve()
    # Walk up from cwd, including cwd itself. Cap at the filesystem
    # root so a misconfigured working dir can't loop forever.
    candidates = [cur, *cur.parents]
    for d in candidates:
        candidate = d / "dist" / "stdlib-manifest.json"
        if candidate.is_file():
            return candidate

    fallback = Path.home() / "projects" / "m-stdlib" / "dist" / "stdlib-manifest.json"
    return fallback if fallback.is_file() else None


def load_manifest(path: Path) -> dict:
    """Read and parse the manifest. Caller catches any IO/JSON error."""
    return json.loads(path.read_text(encoding="utf-8"))


# Recognised symbol shapes -----------------------------------------------------


def _classify(symbol: str) -> str:
    """Return one of: ``module``, ``module.label``, ``label``."""
    s = symbol.strip()
    if "." in s:
        return "module.label"
    if s.isupper() and s.startswith("STD"):
        return "module"
    return "label"


def resolve_symbol(
    symbol: str, manifest: dict
) -> tuple[list[ModuleMatch], list[LabelMatch]]:
    """Resolve ``symbol`` against ``manifest``.

    Returns ``(modules, labels)``. The two lists are independent —
    a single ``module.label`` hit fills only ``labels``; a fuzzy bare-
    name hit fills only ``labels`` (potentially many entries); a
    module-overview hit fills only ``modules``. Empty lists mean
    "no match".
    """
    s = symbol.strip()
    if not s:
        return ([], [])

    kind = _classify(s)
    modules_data: dict = manifest.get("modules", {})

    if kind == "module":
        mod = modules_data.get(s)
        if mod is None:
            return ([], [])
        return ([ModuleMatch(module=s, module_data=mod)], [])

    if kind == "module.label":
        mod_name, _, label_name = s.partition(".")
        mod = modules_data.get(mod_name)
        if mod is None:
            return ([], [])
        labels = mod.get("labels", {})
        label_data = labels.get(label_name)
        if label_data is None:
            return ([], [])
        return ([], [LabelMatch(module=mod_name, label=label_name, label_data=label_data)])

    # kind == "label" — fuzzy bare-name lookup across every module.
    hits: list[LabelMatch] = []
    for mod_name in sorted(modules_data.keys()):
        mod = modules_data[mod_name]
        labels = mod.get("labels", {})
        for label_name, label_data in labels.items():
            if label_name == s:
                hits.append(
                    LabelMatch(
                        module=mod_name, label=label_name, label_data=label_data
                    )
                )
    # Sort by (module, label) so output is deterministic.
    hits.sort(key=lambda h: (h.module, h.label))
    return ([], hits)


def list_modules(manifest: dict) -> list[str]:
    """Return every module name in the manifest, sorted."""
    return sorted(manifest.get("modules", {}).keys())


__all__ = [
    "LabelMatch",
    "ModuleMatch",
    "find_manifest",
    "list_modules",
    "load_manifest",
    "resolve_symbol",
]
