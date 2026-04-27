"""`m fmt` command implementation.

Resolves arguments to a list of `.m` files, formats each, and writes /
checks / diffs as requested.
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

from m_cli.fmt.formatter import ParseError, format_source


def fmt_command(args: argparse.Namespace) -> int:
    """Entry point for `m fmt`. Returns process exit code.

    Exit codes:
      0 — success (or, in --check mode, all files already formatted)
      1 — one or more files would change (--check) or had parse errors
      2 — usage / argument error
    """
    files = _collect_files(args.paths)
    if not files:
        print("m fmt: no .m files found", file=sys.stderr)
        return 2

    if args.stdout and len(files) > 1:
        print("m fmt: --stdout requires exactly one file", file=sys.stderr)
        return 2

    n_changed = 0
    n_errors = 0
    n_unchanged = 0
    for path in files:
        try:
            src = path.read_bytes()
            formatted = format_source(src)
        except ParseError as e:
            print(f"m fmt: {path}: parse error — {e}", file=sys.stderr)
            n_errors += 1
            continue
        except OSError as e:
            print(f"m fmt: {path}: {e}", file=sys.stderr)
            n_errors += 1
            continue

        changed = formatted != src

        if args.stdout:
            sys.stdout.buffer.write(formatted)
            return 0

        if args.diff:
            if changed:
                _print_diff(path, src, formatted)
                n_changed += 1
            else:
                n_unchanged += 1
            continue

        if args.check:
            if changed:
                if not args.quiet:
                    print(f"would reformat {path}")
                n_changed += 1
            else:
                n_unchanged += 1
            continue

        # Default: rewrite in place when changed
        if changed:
            path.write_bytes(formatted)
            if not args.quiet:
                print(f"reformatted {path}")
            n_changed += 1
        else:
            n_unchanged += 1

    if not args.quiet:
        _print_summary(args, n_changed, n_unchanged, n_errors)

    if n_errors > 0:
        return 1
    if args.check and n_changed > 0:
        return 1
    return 0


def _collect_files(paths: list[Path]) -> list[Path]:
    """Expand directory args to .m files; pass through file args."""
    out: list[Path] = []
    for p in paths:
        if p.is_dir():
            out.extend(sorted(p.rglob("*.m")))
        elif p.is_file() and p.suffix == ".m":
            out.append(p)
        elif p.exists():
            out.append(p)  # not .m suffix, but trust the user
        else:
            print(f"m fmt: {p}: no such file or directory", file=sys.stderr)
    return out


def _print_diff(path: Path, before: bytes, after: bytes) -> None:
    diff = difflib.unified_diff(
        before.decode("latin-1", errors="replace").splitlines(keepends=True),
        after.decode("latin-1", errors="replace").splitlines(keepends=True),
        fromfile=str(path),
        tofile=str(path) + " (formatted)",
    )
    sys.stdout.writelines(diff)


def _print_summary(args, n_changed: int, n_unchanged: int, n_errors: int) -> None:
    parts = []
    if args.check:
        parts.append(f"{n_changed} would be reformatted" if n_changed else "all formatted")
    elif args.diff:
        parts.append(f"{n_changed} would change")
    else:
        parts.append(f"{n_changed} reformatted")
    if n_unchanged:
        parts.append(f"{n_unchanged} unchanged")
    if n_errors:
        parts.append(f"{n_errors} errors")
    print("m fmt: " + ", ".join(parts), file=sys.stderr)
