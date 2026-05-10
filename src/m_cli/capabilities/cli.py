"""`m capabilities` implementation.

Walks the argparse parser tree built by :func:`m_cli.cli.build_parser`
and emits a JSON-ready dict. Source of truth = the parser itself, so
new subcommands and plugin-contributed subcommands appear automatically.

The output is the artifact backing ``dist/commands.json``; the manifest
drift gate diffs that file against the regenerated value, so this
function must be deterministic — no timestamps, no env-dependent
fields, sorted keys.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from m_cli import __version__


def _find_subparsers_action(
    parser: argparse.ArgumentParser,
) -> argparse._SubParsersAction | None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def _safe_default(value: Any) -> Any:
    """JSON-encodable rendering of an argparse default."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_safe_default(v) for v in value]
    # Path, custom sentinel, function, etc. → string repr.
    return str(value)


def _parse_examples(epilog: str | None) -> list[str]:
    """Extract example invocations from a subparser ``epilog``.

    Lines that start with ``m `` (or ``$ m ``) are taken as examples.
    Empty epilogs return an empty list. Phase 0 ships no per-subcommand
    examples; this hook lets Phase 1 author them in-place via the
    standard argparse ``epilog`` field without changing the schema.
    """
    if not epilog:
        return []
    out: list[str] = []
    for raw in epilog.splitlines():
        line = raw.strip()
        if line.startswith("$ "):
            line = line[2:].strip()
        if line.startswith("m "):
            out.append(line)
    return out


def _entry_for(sub: argparse.ArgumentParser, short_help: str | None) -> dict[str, Any]:
    purpose = (short_help or sub.description or "").strip()
    options: list[dict[str, Any]] = []
    for action in sub._actions:
        if isinstance(action, (argparse._HelpAction, argparse._VersionAction)):
            continue
        if isinstance(action, argparse._SubParsersAction):
            # Nested sub-actions (e.g. `m ci init`) ship a flat view
            # for Phase 0; recursive introspection lands in Phase 1.
            continue
        if action.dest.startswith("_plugin_"):
            continue
        if not action.option_strings:
            opt_name = action.dest
        else:
            longs = [s for s in action.option_strings if s.startswith("--")]
            opt_name = longs[0] if longs else action.option_strings[0]
        help_text = action.help if action.help is not argparse.SUPPRESS else None
        # NOTE: deliberately omit `required` — argparse derives it for
        # positionals from `nargs` in a way that varies across CPython
        # 3.12.x patch releases (observed: 3.12.13 reports False for
        # `nargs='*'` positionals; some earlier patches report True).
        # The drift gate runs in CI on a different patch than the
        # contributor's local Python, so emitting `required` was
        # producing spurious manifest drift on every run.
        options.append(
            {
                "name": opt_name,
                "help": help_text,
                "default": _safe_default(action.default),
                "choices": list(action.choices) if action.choices else None,
            }
        )
    return {
        "purpose": purpose,
        "options": options,
        "examples": _parse_examples(sub.epilog),
    }


def build_capabilities(
    parser: argparse.ArgumentParser | None = None,
    *,
    include_plugins: bool = False,
) -> dict[str, Any]:
    """Walk the parser tree and return a JSON-ready capability map.

    Parameters
    ----------
    parser:
        Optional parser to introspect. When ``None`` (the default),
        :func:`m_cli.cli.build_parser` is called to construct a fresh
        instance — this is the common path; tests pass a custom parser
        when they want to verify the walker independent of the live
        dispatcher tree.
    include_plugins:
        When False (the default), only the m-cli built-in subcommands
        appear in the output. The ``dist/commands.json`` drift gate
        relies on this — otherwise a contributor with extra plugins
        installed would commit a different manifest than CI regenerates.
        Set True to introspect everything in the parser, plugins
        included (useful for ``m doctor`` or ad-hoc inspection).
    """
    if parser is None:
        # Local import to avoid a circular import at module load.
        from m_cli.cli import build_parser

        parser = build_parser()
    subaction = _find_subparsers_action(parser)
    subcommands: dict[str, Any] = {}
    if subaction is not None:
        builtins = parser.get_default("_m_cli_builtins")
        short_helps = {a.dest: a.help for a in subaction._choices_actions}
        for name in sorted(subaction.choices.keys()):
            if (
                not include_plugins
                and builtins is not None
                and name not in builtins
            ):
                continue
            subcommands[name] = _entry_for(subaction.choices[name], short_helps.get(name))
    return {"version": __version__, "subcommands": subcommands}


def capabilities_command(args: argparse.Namespace) -> int:
    """`m capabilities` handler — JSON-only output."""
    payload = build_capabilities()
    json.dump(payload, sys.stdout, indent=2, sort_keys=False)
    sys.stdout.write("\n")
    return 0
