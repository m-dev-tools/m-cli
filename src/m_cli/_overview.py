"""Bare-dispatcher overview helper.

Implements the `gh`-style two-line description + indented COMMANDS block
that bare `m` and bare `m ci` print on invocation. The command list is
sourced from the live `argparse._SubParsersAction.choices` registry so
new subcommands appear automatically — no hand-maintained list to drift.

Rules served: `cli-ux-conventions-guide.md` §3.1 in the org `.github` repo.
"""

from __future__ import annotations

import argparse
import sys


def print_overview(
    parser: argparse.ArgumentParser,
    sub_action: argparse._SubParsersAction,  # type: ignore[type-arg]
    *,
    tagline: str,
    word: str = "command",
) -> int:
    """Print a `gh`-style overview for `parser` and return 0.

    `word` is the noun used in the usage line and the closing hint —
    "command" at the root, "action" inside `m ci`. `tagline` is the
    second description line.
    """
    out = sys.stdout
    out.write(f"{parser.description}\n")
    out.write(f"{tagline}\n")
    out.write("\nUSAGE\n")
    out.write(f"  {parser.prog} <{word}> [options]\n")

    items = _iter_choices(sub_action)
    if items:
        out.write("\nCOMMANDS\n")
        width = max(len(name) for name, _ in items) + 1  # +1 for trailing ":"
        for name, blurb in items:
            out.write(f"  {name + ':':<{width}}  {blurb}\n")

    article = "an" if word[:1].lower() in "aeiou" else "a"
    out.write(
        f"\nRun '{parser.prog} <{word}> --help' "
        f"for more information about {article} {word}.\n"
    )
    return 0


def _iter_choices(
    sub_action: argparse._SubParsersAction,  # type: ignore[type-arg]
) -> list[tuple[str, str]]:
    """Yield (name, help) for each registered subparser, in registration order.

    argparse stores the short `help=` blurb on the SubParsersAction's
    `_choices_actions` list (one `_ChoicesPseudoAction` per choice). The
    private attribute is the standard idiom; `.choices` would give us the
    parsers but not their help text.
    """
    return [
        (action.dest, action.help or "") for action in sub_action._choices_actions
    ]
