"""`m stdlib` subcommand surface — nested verbs over the m-stdlib manifest.

Wires the 5 m-stdlib reference verbs (`doc`, `search`, `examples`,
`errors`, `manifest`) as sub-actions under a single top-level
namespace, so the surface reads consistently:

    m stdlib doc STDJSON.parse
    m stdlib search "url encode"
    m stdlib examples STDJSON
    m stdlib errors
    m stdlib manifest STDJSON.parse

Each sub-action delegates to its existing handler under :mod:`m_cli.doc`
(handlers unchanged; only the registration site moves out of `cli.py`).

Mirrors the :mod:`m_cli.engine_cli` registration pattern. Follows the
CLI-UX guide § 5.2: no ``required=True`` on the sub-action parser —
bare ``m stdlib`` prints a gh-style overview at exit 0.

The grouping was introduced 2026-05-11; see ``docs/evolution.md``
under "Renames / namespace moves" for the rationale.
"""

from __future__ import annotations

import argparse

from m_cli._overview import print_overview
from m_cli.doc import doc_command
from m_cli.doc.errors import errors_command
from m_cli.doc.examples import examples_command
from m_cli.doc.manifest import manifest_command
from m_cli.doc.search import search_command


def add_stdlib_arguments(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register the ``stdlib`` subcommand tree on the root parser."""
    stdlib_parser = subparsers.add_parser(
        "stdlib",
        help="m-stdlib reference lookups (doc/search/examples/errors/manifest)",
        description="Reference surface over the m-stdlib manifest.",
    )
    actions = stdlib_parser.add_subparsers(
        dest="stdlib_action",
        metavar="<action>",
    )

    _add_doc(actions)
    _add_search(actions)
    _add_examples(actions)
    _add_errors(actions)
    _add_manifest(actions)

    # Bare `m stdlib` prints the gh-style overview; no required=True.
    _TAGLINE = (
        "Look up symbols, search prose, list examples, trace errors, "
        "or dump the raw m-stdlib manifest as JSON."
    )
    stdlib_parser.set_defaults(
        func=lambda _a: print_overview(
            stdlib_parser, actions, tagline=_TAGLINE, word="action"
        ),
    )


# ── individual sub-actions ───────────────────────────────────────────


def _add_doc(actions: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = actions.add_parser(
        "doc",
        help="godoc-style symbol lookup over the m-stdlib manifest",
        description=(
            "Look up a module or label in the m-stdlib manifest and "
            "print its signature, params, returns, raises, examples, "
            "and source pointer. Forms: `m stdlib doc STDJSON` (module "
            "overview), `m stdlib doc STDJSON.parse` (single label), "
            "`m stdlib doc parse` (fuzzy name lookup across modules), "
            "`m stdlib doc` (list every module). The manifest is found "
            "by walking up from cwd looking for "
            "`dist/stdlib-manifest.json`, then by checking "
            "$M_CLI_MANIFEST, then `~/projects/m-stdlib/dist/"
            "stdlib-manifest.json`; --manifest PATH overrides."
        ),
    )
    p.add_argument(
        "symbol",
        nargs="?",
        default="",
        help="Symbol to look up: MODULE, MODULE.label, or bare label name",
    )
    p.add_argument(
        "--short",
        action="store_true",
        help="One-line synopsis instead of full long-form output",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit the raw manifest entry as JSON",
    )
    p.add_argument(
        "--manifest",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to dist/stdlib-manifest.json (default: walk up from cwd)",
    )
    p.set_defaults(func=doc_command)


def _add_search(actions: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = actions.add_parser(
        "search",
        help="Full-text search over the m-stdlib manifest",
        description=(
            "Walk every (module, label) entry and report any whose "
            "synopsis / description / example contains every space-"
            "separated token in the query (case-insensitive). Results "
            "rank synopsis matches above description above example. "
            "Manifest discovery is shared with `m stdlib doc`."
        ),
    )
    p.add_argument(
        "query",
        nargs="?",
        default="",
        help="Search query — space-separated tokens (AND-style match)",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max number of matches to print (default: 50)",
    )
    p.add_argument(
        "--manifest",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to dist/stdlib-manifest.json (default: walk up from cwd)",
    )
    p.set_defaults(func=search_command)


def _add_examples(actions: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = actions.add_parser(
        "examples",
        help="Print every @example from the manifest",
        description=(
            "Walk every public label's @example bodies and emit them "
            "prefixed with `module.label:` so the output is greppable. "
            "With a MODULE argument, scope the walk to that module only."
        ),
    )
    p.add_argument(
        "module",
        nargs="?",
        default="",
        help="Module to scope output to (default: every module)",
    )
    p.add_argument(
        "--manifest",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to dist/stdlib-manifest.json (default: walk up from cwd)",
    )
    p.set_defaults(func=examples_command)


def _add_errors(actions: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = actions.add_parser(
        "errors",
        help="List every U-STD* error code and the labels that raise it",
        description=(
            "Inverted index over the manifest's @raises tags: every "
            "U-STDxxx-NAME code is listed with its producing module + "
            "every label that raises it. Reads dist/errors.json when "
            "available (m-stdlib's WA7 sidecar); otherwise derives the "
            "inversion from the main manifest's per-label `raises` arrays."
        ),
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit the errors index as JSON (the same shape as dist/errors.json)",
    )
    p.add_argument(
        "--manifest",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to dist/stdlib-manifest.json (default: walk up from cwd)",
    )
    p.set_defaults(func=errors_command)


def _add_manifest(actions: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = actions.add_parser(
        "manifest",
        help="Emit the m-stdlib manifest (or a sub-path) as JSON",
        description=(
            "With no path, writes the resolved dist/stdlib-manifest.json "
            "to stdout. With a path like STDJSON / STDJSON.parse / "
            "modules / errors / stdlib_version, emits just that subtree. "
            "Manifest discovery is shared with `m stdlib doc`."
        ),
    )
    p.add_argument(
        "path",
        nargs="?",
        default="",
        help="Sub-path to emit (e.g. STDJSON.parse). Empty = whole manifest.",
    )
    p.add_argument(
        "--manifest",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to dist/stdlib-manifest.json (default: walk up from cwd)",
    )
    p.set_defaults(func=manifest_command)
