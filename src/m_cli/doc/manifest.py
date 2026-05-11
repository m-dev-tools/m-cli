"""``m manifest [path]`` — emit the resolved m-stdlib manifest as JSON.

Thin wrapper over the manifest discovery in :mod:`m_cli.doc.lookup`.
With no arguments, writes the entire manifest to stdout. With a
``path`` like ``STDJSON.parse`` / ``STDJSON`` / ``modules.STDJSON``,
emits just that subtree — useful for piping into ``jq`` or feeding
an AI agent without paying the round-trip cost of the whole file.

Conventions match :func:`m_cli.doc.cli.doc_command`:

* exit 0 — output written
* exit 1 — domain failure: path resolved to a missing key, or manifest
           could not be loaded (per CLI-UX guide §3.7)
* exit 2 — usage error (argparse-level)

The path syntax is two-dotted-token-max:

* ``STDJSON``                — manifest["modules"]["STDJSON"]
* ``STDJSON.parse``          — manifest["modules"]["STDJSON"]["labels"]["parse"]
* ``modules``                — manifest["modules"]
* ``errors``                 — manifest["errors"]
* ``stdlib_version``         — manifest["stdlib_version"]

Anything more elaborate is the user's job to do via ``jq`` against
the no-arg full output. Substring and wildcard syntax are out of
scope.
"""

from __future__ import annotations

import argparse
import json
import sys

from m_cli._exit import DOMAIN_FAILURE
from m_cli.doc.lookup import find_manifest, load_manifest


def _resolve_path(manifest: dict, path: str) -> tuple[bool, object]:
    """Return ``(found, value)`` for the documented path syntax."""
    p = path.strip()
    if not p:
        return (True, manifest)

    # Top-level keys: stdlib_version / modules / errors / generated_at /
    # any future addition. Dispatch first on the first token; the
    # special "MODULE" or "MODULE.label" forms are sugar for the
    # nested modules path.
    head, _, tail = p.partition(".")
    if head in {"stdlib_version", "modules", "errors"}:
        if not tail:
            if head not in manifest:
                return (False, None)
            return (True, manifest[head])
        # `modules.STDJSON.parse` — walk the rest piece by piece.
        cur: object = manifest[head] if head in manifest else None
        for segment in tail.split("."):
            if not isinstance(cur, dict) or segment not in cur:
                return (False, None)
            cur = cur[segment]
        return (True, cur)

    # Otherwise treat as `MODULE` or `MODULE.label`.
    modules = manifest.get("modules", {})
    if head not in modules:
        return (False, None)
    mod = modules[head]
    if not tail:
        return (True, mod)
    labels = mod.get("labels", {})
    # Allow `MODULE.label` (one dotted level) — anything deeper is
    # not a documented path.
    if tail in labels:
        return (True, labels[tail])
    return (False, None)


def manifest_command(args: argparse.Namespace) -> int:
    explicit = getattr(args, "manifest", None)
    manifest_path = find_manifest(explicit=explicit)
    if manifest_path is None:
        sys.stderr.write(
            "m manifest: could not find dist/stdlib-manifest.json. "
            "Run `make manifest` from m-stdlib or pass --manifest PATH.\n"
        )
        return DOMAIN_FAILURE
    try:
        manifest = load_manifest(manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"m manifest: failed to load {manifest_path}: {exc}\n")
        return DOMAIN_FAILURE

    path = getattr(args, "path", "") or ""
    found, value = _resolve_path(manifest, path)
    if not found:
        sys.stderr.write(f"m manifest: path {path!r} not found in manifest.\n")
        return 1

    sys.stdout.write(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    return 0


__all__ = ["manifest_command"]
