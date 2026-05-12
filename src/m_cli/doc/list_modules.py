"""``m stdlib list`` — print every m-stdlib module name + synopsis.

A dedicated discoverability verb: "what's in the standard library?"
Equivalent to ``m stdlib doc`` (bare, no symbol arg) but with its
own name so the user can find it via ``m stdlib --help`` without
already knowing that bare ``m stdlib doc`` does the listing.

Output is a single-column table aligned on the longest module name,
sorted alphabetically. ``--json`` emits a structured array for
tooling consumers.
"""

from __future__ import annotations

import argparse
import json
import sys

from m_cli._exit import DOMAIN_FAILURE
from m_cli.doc.lookup import find_manifest, list_modules, load_manifest


def list_command(args: argparse.Namespace) -> int:
    explicit = getattr(args, "manifest", None)
    manifest_path = find_manifest(explicit=explicit)
    if manifest_path is None:
        sys.stderr.write(
            "m stdlib list: could not find dist/stdlib-manifest.json. "
            "Run `make manifest` from m-stdlib or pass --manifest PATH.\n"
        )
        return DOMAIN_FAILURE
    try:
        manifest = load_manifest(manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"m stdlib list: failed to load {manifest_path}: {exc}\n")
        return DOMAIN_FAILURE

    names = list_modules(manifest)
    modules: dict = manifest.get("modules", {})

    if getattr(args, "json", False):
        payload = {
            "stdlib_version": manifest.get("stdlib_version"),
            "modules": [
                {
                    "name": name,
                    "synopsis": (modules[name].get("synopsis") or "").strip(),
                }
                for name in names
            ],
        }
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    ver = manifest.get("stdlib_version") or "(unversioned)"
    sys.stdout.write(f"m-stdlib {ver} — {len(names)} module(s)\n\n")
    width = max((len(name) for name in names), default=0)
    for name in names:
        synopsis = (modules[name].get("synopsis") or "").strip()
        if synopsis:
            sys.stdout.write(f"  {name:<{width}}  {synopsis}\n")
        else:
            sys.stdout.write(f"  {name}\n")
    return 0


__all__ = ["list_command"]
