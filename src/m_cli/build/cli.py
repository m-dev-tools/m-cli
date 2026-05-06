"""`m build` command — warm-compile M routines."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

from m_cli.build.runner import BuildResult, compile_file, discover_files
from m_cli.run.runner import resolve_ydb_binary

# Type alias for an injectable compile runner used in unit tests.
RunnerFn = Callable[[str, Path], tuple[int, str]]


def build_command(args: argparse.Namespace, *, runner: RunnerFn | None = None) -> int:
    runner_fn: RunnerFn = runner or compile_file

    binary = resolve_ydb_binary()
    if binary is None:
        print(
            "m build: no `ydb` binary found. Set $YDB, $ydb_dist, or "
            "ensure `ydb` is on PATH.",
            file=sys.stderr,
        )
        return 2

    paths = list(args.paths) if args.paths else [Path.cwd()]
    files = discover_files(paths)
    if not files:
        print("m build: no .m files found in: " + ", ".join(str(p) for p in paths), file=sys.stderr)
        return 2

    results: list[BuildResult] = []
    o_files_created: set[Path] = set()
    for f in files:
        before = _existing_o_for(f)
        rc, output = runner_fn(binary, f)
        after = _existing_o_for(f)
        if after and not before:
            o_files_created.add(after)
        ok = rc == 0
        results.append(BuildResult(file=f, returncode=rc, output=output, ok=ok))
        if not ok:
            sys.stdout.write(f"{f}: compile failed (rc={rc})\n")
            if output:
                for line in output.splitlines():
                    sys.stdout.write(f"  {line}\n")
        elif not getattr(args, "quiet", False):
            sys.stdout.write(f"{f}: ok\n")

    n_ok = sum(1 for r in results if r.ok)
    n_fail = sum(1 for r in results if not r.ok)
    if not getattr(args, "quiet", False):
        sys.stdout.write(f"\n{n_ok} compiled, {n_fail} failed\n")

    if getattr(args, "check", False):
        for o in o_files_created:
            if o.exists():
                try:
                    o.unlink()
                except OSError:
                    pass

    return 0 if n_fail == 0 else 1


def _existing_o_for(m_file: Path) -> Path | None:
    o = m_file.with_suffix(".o")
    return o if o.exists() else None
