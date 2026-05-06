"""`m new` command — scaffold a new M project."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from m_cli.new.scaffold import render_scaffold


def new_command(args: argparse.Namespace) -> int:
    name = args.name
    target = Path(args.path) if args.path else Path.cwd() / name
    force = bool(getattr(args, "force", False))
    quiet = bool(getattr(args, "quiet", False))

    try:
        scaffold = render_scaffold(name)
    except ValueError as exc:
        print(f"m new: {exc}", file=sys.stderr)
        return 2

    if target.exists() and any(target.iterdir()) and not force:
        print(
            f"m new: target {target} is not empty (pass --force to scaffold anyway)",
            file=sys.stderr,
        )
        return 1

    target.mkdir(parents=True, exist_ok=True)
    for relpath, content in scaffold.files.items():
        out = target / relpath
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content)
        if not quiet:
            print(f"  create {out.relative_to(target.parent) if target.parent != Path() else out}")

    if not quiet:
        print(f"\nScaffolded {scaffold.project_name} at {target}")
        print("Next steps:")
        print(f"  cd {target}")
        print("  make check")
    return 0
