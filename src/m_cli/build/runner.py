"""Pure helpers for ``m build``: file discovery and compile invocation."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BuildResult:
    file: Path
    returncode: int
    output: str
    ok: bool


def discover_files(paths: list[Path]) -> list[Path]:
    """Walk ``paths`` and collect every ``.m`` file (sorted, deduped)."""
    seen: set[Path] = set()
    out: list[Path] = []
    for p in paths:
        if p.is_file():
            if p.suffix == ".m":
                resolved = p.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    out.append(p)
            continue
        if not p.is_dir():
            continue
        for f in sorted(p.rglob("*.m")):
            resolved = f.resolve()
            if resolved not in seen:
                seen.add(resolved)
                out.append(f)
    out.sort(key=lambda f: f.name)
    return out


def compile_file(binary: str, file: Path) -> tuple[int, str]:
    """Run ``binary <file>`` and return ``(returncode, combined_output)``.

    YottaDB's ``mumps``/``ydb`` binary compiles routines passed as
    positional arguments. Stdout + stderr are merged so the caller can
    surface a uniform error block per file.
    """
    proc = subprocess.run(
        [binary, str(file)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        cwd=file.parent,
    )
    return proc.returncode, proc.stdout.decode("latin-1", errors="replace")
