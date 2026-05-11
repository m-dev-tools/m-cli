"""``m errors`` — list every ``U-STD*`` error code and the labels that raise it.

Inverted index over the manifest's per-label ``raises`` arrays.
Output groups by error code, listing the producing module + every
label that raises it. Useful for answering "where could this $ECODE
come from?" without grepping every src/STD*.m file.

If the dist/ directory ships an ``errors.json`` alongside the main
manifest (m-stdlib's WA7 generator emits this as a derivative —
same data, pre-inverted), this command prefers reading that and
falls back to deriving the inversion from the main manifest. Either
way the output is identical.

Exit codes:

* 0 — at least one error code listed
* 1 — domain failure: manifest is loaded but contains zero error codes
      (and no errors.json sidecar exists), or manifest could not be
      loaded (per CLI-UX guide §3.7)
* 2 — usage error (argparse-level)
"""

from __future__ import annotations

import argparse
import json
import sys

from m_cli._exit import DOMAIN_FAILURE
from m_cli.doc.lookup import find_manifest, load_manifest


def _load_errors_sidecar(manifest_path) -> dict | None:
    """Return the parsed ``errors.json`` adjacent to ``manifest_path``,
    or None if the sidecar is missing / unreadable."""
    sidecar = manifest_path.parent / "errors.json"
    if not sidecar.is_file():
        return None
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _derive_errors_from_manifest(manifest: dict) -> dict:
    """Build the same shape errors.json would have from the main
    manifest's per-label ``raises`` arrays."""
    out: dict[str, dict] = {}
    modules: dict = manifest.get("modules", {})
    for mod_name in sorted(modules.keys()):
        mod = modules[mod_name]
        for label_name, label_data in (mod.get("labels") or {}).items():
            for r in label_data.get("raises") or []:
                code = r.get("code")
                if not code:
                    continue
                bucket = out.setdefault(code, {"module": mod_name, "labels": []})
                if label_name not in bucket["labels"]:
                    bucket["labels"].append(label_name)
    return out


def errors_command(args: argparse.Namespace) -> int:
    explicit = getattr(args, "manifest", None)
    manifest_path = find_manifest(explicit=explicit)
    if manifest_path is None:
        sys.stderr.write(
            "m errors: could not find dist/stdlib-manifest.json. "
            "Run `make manifest` from m-stdlib or pass --manifest PATH.\n"
        )
        return DOMAIN_FAILURE
    try:
        manifest = load_manifest(manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"m errors: failed to load {manifest_path}: {exc}\n")
        return DOMAIN_FAILURE

    errors = _load_errors_sidecar(manifest_path)
    if errors is None:
        errors = _derive_errors_from_manifest(manifest)

    if not errors:
        sys.stderr.write("m errors: no U-STD* error codes in manifest.\n")
        return 1

    if getattr(args, "json", False):
        sys.stdout.write(json.dumps(errors, indent=2, sort_keys=True) + "\n")
        return 0

    # Width-align the code column so the module name lines up across
    # rows. Codes can vary in length (longest in m-stdlib today is
    # `U-STDARGS-MISSING-POSITIONAL` at 28 chars).
    code_w = max(len(c) for c in errors)
    for code in sorted(errors):
        info = errors[code]
        module = info.get("module", "?")
        labels = info.get("labels") or []
        labels_str = ", ".join(labels) if labels else "(no labels)"
        sys.stdout.write(f"  {code:{code_w}}  {module}: {labels_str}\n")
    return 0


__all__ = ["errors_command"]
