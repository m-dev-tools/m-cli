---
created: 2026-05-09
last_modified: 2026-05-09
revisions: 1
doc_type: [GUIDE, SPEC]
---

# Plugin development

m-cli's built-in subcommands (`m fmt`, `m lint`, `m test`, `m doc`, …)
live in this repository. The toolchain also accepts **out-of-tree
subcommands**: any installed Python package can register its own `m`
subcommand via a Python entry-point, so utility commands that are too
niche or too opinionated for core can ship as siblings without a fork.

This document defines the contract every plugin must follow.

## Quick example

A plugin package exposes one `register(subparsers)` function per
subcommand and declares it as an entry-point in the `m_cli.plugins`
group:

```toml
# pyproject.toml of a plugin package, e.g. m-cli-extras
[project]
name = "m-cli-extras"
version = "0.1.0"
dependencies = ["m-cli"]

[project.entry-points."m_cli.plugins"]
bench = "m_cli_extras.bench:register"
diff  = "m_cli_extras.diff:register"
```

```python
# src/m_cli_extras/bench/__init__.py
from m_cli_extras.bench.cli import register  # re-export
```

```python
# src/m_cli_extras/bench/cli.py
import argparse
from pathlib import Path

def register(subparsers) -> None:
    """Register the `m bench` subcommand."""
    p = subparsers.add_parser(
        "bench",
        help="Benchmark m-cli operations against a corpus",
        description="Walks a corpus and times m fmt / m lint / m test...",
    )
    p.add_argument("corpus", type=Path)
    p.add_argument("--top", type=int, default=10)
    p.set_defaults(func=bench_command)


def bench_command(args: argparse.Namespace) -> int:
    """Handler — same signature every built-in m subcommand uses."""
    # ... do the benchmark, print results, return exit code
    return 0
```

After `pip install m-cli-extras` (or `uv add m-cli-extras`):

```
$ m bench /path/to/corpus --top 5
$ m plugins
m-cli plugin API v1

Registered plugins (2):
  m bench           (m-cli-extras 0.1.0)
  m diff            (m-cli-extras 0.1.0)
```

## Contract

The plugin contract is intentionally minimal:

1. **Entry-point group is `m_cli.plugins`.** Other groups are ignored.
2. **The entry-point's value is `module:attr`** where `attr` is a
   callable taking exactly one positional argument: argparse's
   `subparsers` action.
3. **Inside `register()`, do the same dance built-ins do** —
   `subparsers.add_parser(...)`, add arguments, `set_defaults(func=handler)`.
   The handler receives a parsed `argparse.Namespace` and returns an
   `int` exit code.
4. **The plugin name is the entry-point's left-hand side**
   (`bench = ...` → `m bench`). Name collisions are rejected:
   - **Built-ins always win.** A plugin named `lint` is refused; the
     built-in `m lint` keeps running unaffected.
   - **First-claim wins for plugin-vs-plugin.** If two installed
     packages both register `bench`, the second is reported as a
     conflict. Don't fight over names — pick a unique one.
5. **Don't crash the dispatcher.** A plugin whose `register()` raises
   is reported as a conflict and skipped; sibling plugins keep
   loading. But please return clean tracebacks-on-error from your
   handler rather than letting Python emit a default one.

## Public API

Plugins may import any name listed in `m_cli.__all__`:

```python
from m_cli import (
    parse,                              # parse M source bytes -> Tree
    format_source, canonical_rules,     # m fmt
    lint_source, select_rules,          # m lint
    Diagnostic, Severity, Category,
    # ... see m_cli/__init__.py for the full list
)
```

`tests/test_library_api.py` pins this surface — refactors that would
break a third-party importer are caught at PR time. Anything *not* in
`__all__` is internal; reach into it at your own risk.

If you need engine access (e.g. to run M code), use the multi-transport
abstraction:

```python
from m_cli.engine import detect_engine

def my_command(args):
    engine = detect_engine()  # picks Local / Docker / SSH per env
    cmd = engine.build_xcmd_cmd("write 1+1", "/tmp/myroutines")
    # ... subprocess.run(cmd) etc.
```

`detect_engine()` raises `EngineNotConfigured` with helpful guidance
if no transport is available — let the exception propagate; the user
gets a useful message.

## Versioning

`m_cli.plugins.PLUGIN_API_VERSION` is currently `1`. We bump it on a
**breaking change to the contract** above (e.g. signature change,
required field on `PluginInfo`, change to the entry-point group name).

Plugins are not currently required to declare which version they
target — the contract is small enough that this is fine for now. If
you want defensive versioning in your plugin:

```python
from m_cli.plugins import PLUGIN_API_VERSION

if PLUGIN_API_VERSION != 1:
    raise RuntimeError(
        f"m-cli plugin API v{PLUGIN_API_VERSION} unsupported by this plugin"
    )
```

## Testing your plugin

The cleanest pattern is to test your `register(subparsers)` function
directly, using a fresh `argparse.ArgumentParser` per test:

```python
import argparse
from m_cli_extras.bench.cli import register

def test_bench_registers_subcommand():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    register(subparsers)
    args = parser.parse_args(["bench", "/some/corpus", "--top", "5"])
    assert args.command == "bench"
    assert str(args.corpus) == "/some/corpus"
    assert args.top == 5
```

You don't need to install your plugin to test the registration — going
through the entry-point is the integration boundary, not the
unit-test boundary.

## When a feature should live in core vs a plugin

Pre-decision criteria for whether a new subcommand belongs in `m-cli`
(this repo) or in a plugin package:

| In core | In a plugin |
|---|---|
| Foundational source-level operations (parse, format, lint, test) | Niche or opinionated wrappers |
| Used by ≥80% of `m-cli` users | Used by < 50% |
| Lightweight dependencies (already pulled in) | Heavy deps (`pandas`, `requests`, `matplotlib`) |
| Output format is structured (JSON / TAP / LCOV / argparse-style text) | Output is markdown report / HTML / chart |
| Ships with the toolchain's Python wheel | Independent release cadence |

If a feature is borderline, ship it in a plugin first. Promote to core
only after a release cycle of feedback — the move is reversible
(deprecate the plugin, re-implement in core).

## Reference: `m-dev-tools/m-cli-extras`

The seed plugin package for the m-dev-tools org lives at
[`m-dev-tools/m-cli-extras`](https://github.com/m-dev-tools/m-cli-extras)
(planned per [`m-dev-tools-todo.md`](../../m-dev-tools-todo.md) Tier 6b).
It collects a first batch of niche subcommands — bench, diff, migrate,
audit, corpus-stats — that exercise this plugin contract end-to-end.
Use it as a worked example.
