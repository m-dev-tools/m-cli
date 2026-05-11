"""``m examples [MODULE]`` — print every ``@example`` from the manifest.

Walks every label's ``examples`` array and emits each line prefixed
with the qualified ``module.label:`` so the output is greppable.
With a ``MODULE`` argument, scope the walk to that module only.

Use case: showing a developer (or an AI agent) every canonical usage
snippet at a glance, without having to ``m doc`` each label one at a
time. Pairs naturally with shell pipes:

    m examples STDJSON | grep parseFile
    m examples           | wc -l        # how many examples ship?

Exit codes match the rest of the family:

* 0 — examples found and written
* 1 — domain failure: module name resolved but has zero examples, or
      unknown module, or manifest could not be loaded
      (per CLI-UX guide §3.7)
* 2 — usage error (argparse-level)
"""

from __future__ import annotations

import argparse
import json
import sys

from m_cli._exit import DOMAIN_FAILURE
from m_cli.doc.lookup import find_manifest, load_manifest


def _walk_examples(manifest: dict, module_filter: str = "") -> list[tuple[str, str, str]]:
    """Return ``[(module, label, example_body), ...]`` in deterministic order."""
    out: list[tuple[str, str, str]] = []
    modules: dict = manifest.get("modules", {})
    for mod_name in sorted(modules.keys()):
        if module_filter and mod_name != module_filter:
            continue
        mod = modules[mod_name]
        for label_name in sorted((mod.get("labels") or {}).keys()):
            label = mod["labels"][label_name]
            for ex in label.get("examples") or []:
                out.append((mod_name, label_name, str(ex)))
    return out


def examples_command(args: argparse.Namespace) -> int:
    explicit = getattr(args, "manifest", None)
    manifest_path = find_manifest(explicit=explicit)
    if manifest_path is None:
        sys.stderr.write(
            "m examples: could not find dist/stdlib-manifest.json. "
            "Run `make manifest` from m-stdlib or pass --manifest PATH.\n"
        )
        return DOMAIN_FAILURE
    try:
        manifest = load_manifest(manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"m examples: failed to load {manifest_path}: {exc}\n")
        return DOMAIN_FAILURE

    module_arg = (getattr(args, "module", "") or "").strip()
    if module_arg:
        if module_arg not in manifest.get("modules", {}):
            sys.stderr.write(
                f"m examples: module {module_arg!r} not found in manifest.\n"
            )
            return 1

    items = _walk_examples(manifest, module_filter=module_arg)
    if not items:
        if module_arg:
            sys.stderr.write(f"m examples: module {module_arg!r} has no examples.\n")
        else:
            sys.stderr.write("m examples: no examples in manifest.\n")
        return 1

    for module, label, body in items:
        # Multi-line example bodies stay readable when each line is
        # individually qualified — caller can pipe through `column`
        # or `awk -F: '{print $1}'` to slice if they want.
        for line in body.splitlines() or [body]:
            sys.stdout.write(f"{module}.{label}: {line}\n")
    return 0


__all__ = ["examples_command"]
