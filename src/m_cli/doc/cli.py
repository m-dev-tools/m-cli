"""``m doc`` — godoc-style symbol lookup over the m-stdlib manifest.

Forms (per
m-stdlib/docs/plans/discoverability-and-tooling-plan.md § 4.1):

* ``m doc STDJSON``        — module overview (label list + errors).
* ``m doc STDJSON.parse``  — single label (full long-form render).
* ``m doc parse``          — fuzzy lookup; lists every matching label
                             across modules.
* ``m doc``                — list every module's name + synopsis.

Flags:

* ``--short``              — one-line synopsis instead of long form.
* ``--json``               — raw manifest entry as JSON.
* ``--manifest PATH``      — override manifest discovery (otherwise
                             walks up from cwd, then falls back to
                             ``~/m-dev-tools/m-stdlib/dist/stdlib-manifest.json``).

Exit codes (per CLI-UX guide §3.7):
*  0 — match found, output written.
*  1 — domain failure: symbol not found (also when fuzzy lookup found
       0 matches), or manifest could not be loaded (missing/unreadable).
*  2 — usage error (argparse-level: unknown flag, malformed argument).

The legacy path-based behaviour (extract M docstrings to Markdown /
HTML) has been moved aside — :mod:`m_cli.doc.extract` and
:mod:`m_cli.doc.render` still exist for direct programmatic use, but
``m doc`` no longer dispatches to them. The discoverability and
tooling plan (WB1) repurposes the command to be a manifest reader.
"""

from __future__ import annotations

import argparse
import json
import sys

from m_cli._exit import DOMAIN_FAILURE
from m_cli.doc.format import (
    format_label_json,
    format_label_list,
    format_label_long,
    format_label_short,
    format_module_json,
    format_module_long,
    format_module_short,
)
from m_cli.doc.lookup import (
    find_manifest,
    list_modules,
    load_manifest,
    resolve_symbol,
)


def _print_no_manifest(stderr) -> None:
    stderr.write(
        "m doc: could not find dist/stdlib-manifest.json.\n"
        "  Tried: --manifest flag, $M_CLI_MANIFEST, walking up from cwd,\n"
        "         ~/m-dev-tools/m-stdlib/dist/stdlib-manifest.json\n"
        "  Generate it with `make manifest` from inside an m-stdlib\n"
        "  checkout, or pass --manifest PATH.\n"
    )


def _print_no_match(symbol: str, stderr) -> None:
    stderr.write(
        f"m doc: no match for symbol {symbol!r}.\n"
        "  Try `m doc` (no args) for the module list, or `m doc MODULE` "
        "for that module's labels.\n"
    )


def doc_command(args: argparse.Namespace) -> int:
    explicit = getattr(args, "manifest", None)
    manifest_path = find_manifest(explicit=explicit)
    if manifest_path is None:
        _print_no_manifest(sys.stderr)
        return DOMAIN_FAILURE

    try:
        manifest = load_manifest(manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"m doc: failed to load {manifest_path}: {exc}\n")
        return DOMAIN_FAILURE

    symbol = (getattr(args, "symbol", "") or "").strip()
    short = bool(getattr(args, "short", False))
    as_json = bool(getattr(args, "json", False))

    # No symbol → list every module with its synopsis. The user
    # discovers what's available, and a follow-up `m doc <name>` zooms
    # in. ``--json`` returns the raw manifest minus the leaf labels;
    # ``--short`` is the same as the default here.
    if not symbol:
        if as_json:
            sys.stdout.write(
                json.dumps(
                    {
                        "stdlib_version": manifest.get("stdlib_version"),
                        "modules": sorted(manifest.get("modules", {}).keys()),
                    },
                    indent=2,
                )
                + "\n"
            )
            return 0
        ver = manifest.get("stdlib_version") or "(unversioned)"
        sys.stdout.write(f"m-stdlib {ver}\n\n")
        sys.stdout.write("modules:\n")
        for mod_name in list_modules(manifest):
            mod = manifest["modules"][mod_name]
            syn = (mod.get("synopsis") or "").strip()
            if syn:
                sys.stdout.write(f"  {mod_name:14s} {syn}\n")
            else:
                sys.stdout.write(f"  {mod_name}\n")
        return 0

    modules, labels = resolve_symbol(symbol, manifest)
    if not modules and not labels:
        _print_no_match(symbol, sys.stderr)
        return 1

    if as_json:
        # JSON form: emit the raw manifest entry. For module hits
        # render the module dict; for one label hit, the label dict;
        # for multiple label hits, an array.
        if modules:
            sys.stdout.write(format_module_json(modules[0]))
        elif len(labels) == 1:
            sys.stdout.write(format_label_json(labels[0]))
        else:
            payload = [
                {
                    "module": m.module,
                    "label": m.label,
                    "data": m.label_data,
                }
                for m in labels
            ]
            sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        return 0

    if short:
        if modules:
            sys.stdout.write(format_module_short(modules[0]))
        else:
            for m in labels:
                sys.stdout.write(format_label_short(m))
        return 0

    # Long form (default).
    if modules:
        sys.stdout.write(format_module_long(modules[0]))
        return 0
    if len(labels) == 1:
        sys.stdout.write(format_label_long(labels[0]))
        return 0
    # Multiple bare-name fuzzy hits — list with synopses so the user
    # can pick. Caller can re-invoke with `m doc MODULE.label` to
    # zoom into a specific one.
    sys.stdout.write(format_label_list(labels))
    return 0


__all__ = ["doc_command"]
