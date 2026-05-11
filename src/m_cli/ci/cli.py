"""`m ci init` — write the GitHub Actions workflow."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from m_cli.ci.scaffold import render_workflow


def ci_command(args: argparse.Namespace) -> int:
    action = getattr(args, "ci_action", None) or "init"
    if action != "init":
        print(f"m ci: unknown action {action!r}; only `init` is supported", file=sys.stderr)
        return 2

    target = Path(args.path) if args.path else Path.cwd()
    workflow_path = target / ".github" / "workflows" / "m-ci.yml"
    workflow = render_workflow()

    # Preview mode (default): never mutate state. Print the planned path
    # and the workflow YAML to stdout and exit 0. The user opts into the
    # write with `--write` (CLI-UX guide §3.2; anti-pattern #4).
    if not getattr(args, "write", False):
        if not getattr(args, "quiet", False):
            rel = (
                workflow_path.relative_to(target)
                if workflow_path.is_relative_to(target)
                else workflow_path
            )
            print(f"# preview: would write {rel}")
            print("# pass --write to scaffold the file")
            print(f"# ----- {workflow_path.name} -----")
            print(workflow, end="" if workflow.endswith("\n") else "\n")
        return 0

    if workflow_path.exists() and not getattr(args, "force", False):
        print(
            f"m ci init: {workflow_path} already exists (pass --force to overwrite)",
            file=sys.stderr,
        )
        return 1

    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(workflow)

    if not getattr(args, "quiet", False):
        if workflow_path.is_relative_to(target):
            rel = workflow_path.relative_to(target)
        else:
            rel = workflow_path
        print(f"  create {rel}")
        print("\nNext: commit the workflow and push to a branch with GitHub Actions enabled.")
    return 0
