# Python CLI frameworks — comparative landscape

> **Why this doc lives here.** `m-cli` is a Python CLI built on `argparse`.
> Every few quarters someone (sometimes the maintainer) asks why we picked
> argparse over Click / Typer / Fire. This file is the comparative
> evidence — gathered once, kept current — so the discussion starts from
> facts. It is **not** a switch-frameworks proposal; see "Why m-cli still
> uses argparse" at the bottom for the resolved position.

**Data snapshot:** 2026-05-11. GitHub metrics via `gh api repos/<o>/<r>`.
Activity windows are trailing 12 months (since 2025-05-11). PR counts via
`gh api search/issues?q=…+is:pr+is:closed`. Contributor counts via
`Link`-header pagination on `/contributors?per_page=1&anon=1` (anonymous
co-authors inflate the number — treat as an upper bound).

Regenerating: see [Refresh procedure](#refresh-procedure) at the bottom.

---

## Summary table

| Framework | Stars | Commits 12mo | Closed PRs 12mo | Latest release | Style | Type-hint driven | Maintained |
|---|---:|---:|---:|---|---|---|---|
| [argparse](#1-argparse--python-stdlib) | (stdlib) | (cpython) | — | Python 3.14 (2025-10) | imperative | no | yes (cpython) |
| [Click](#2-click--pallets-click) | 17,477 | 469 | 327 | 8.3.3 (2026-04-22) | decorators | no | very active |
| [Typer](#3-typer--fastapi-typer) | 19,387 | 578 | 377 | 0.25.1 (2026-04-30) | function + hints | **yes** | very active |
| [Fire](#4-fire--google-python-fire) | 28,188 | 14 | 34 | 0.7.1 (2025-08-16) | object reflection | no | slow |
| [docopt](#5a-docopt--docoptdocopt) | 8,007 | 1 | 1 | none (last tag 0.6.2, 2014) | docstring | no | **unmaintained** |
| [docopt-ng](#5b-docopt-ng--jazzbanddocopt-ng) | 220 | 0 | 0 | 0.9.0 (2023-05-30) | docstring | partial | dormant |
| [cleo](#6-cleo--python-poetrycleo) | 1,345 | 19 | 34 | 2.1.0 (2023-10-30) — v3 WIP | class-based | no | active, no release |
| [argh](#7-argh--neithereargh) | n/a | n/a | n/a | n/a (repo moved) | function sig | partial | n/a |
| [plac](#8-plac--ialbertplac) | 300 | 0 | 0 | 1.4.3 (2024-02-22) | function sig | minimal | dormant |
| [rich-click](#9-rich-click--ewelsrich-click) | 807 | 300 | 60 | 1.9.7 (2026-01-31) | Click wrapper | inherits Click | very active |
| [Rich (companion lib)](#companion-rich--textualizerich) | 56,323 | 245 | 185 | 15.0.0 (2026-04-12) | (not a framework) | — | very active |

---

## Feature matrix

| Feature | argparse | Click | Typer | Fire | docopt(-ng) | cleo | argh | plac | rich-click |
|---|---|---|---|---|---|---|---|---|---|
| Ships with Python | ✓ | | | | | | | | |
| Zero runtime deps | ✓ | ✓ | | ✓¹ | ✓ | | ✓ | ✓ | |
| Decorator style | | ✓ | ✓ | | | | ✓ | | ✓ |
| Class-based commands | | ✓ | | | | ✓ | | | |
| Function-signature driven | | | ✓ | ✓ | | | ✓ | ✓ | |
| Type hints derive arg spec | | | ✓ | partial | | | partial | minimal | inherits |
| Auto `--help` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ (rich) |
| Nested subcommands | ✓ | ✓ | ✓ | implicit | partial | ✓ | ✓ | ✓ | ✓ |
| Built-in shell completion | | ✓ | ✓ | partial | | ✓ | | | inherits |
| Colored output built in | | ✓ | ✓ (rich) | minimal | | ✓ | | | ✓ |
| Async support | | external | | | | | | | external |
| Plugin / entry-point system | | ✓ (`Group.add_command`) | inherits Click | | | | | | inherits Click |
| Built-in testing helper | | `CliRunner` | `CliRunner` | | | `CommandTester` | | | `CliRunner` |

¹ Fire pulls in `termcolor` — one tiny dep, often counted as "zero" by users.

---

## Per-framework detail

### 1. argparse — Python stdlib

- **Where it lives:** `Lib/argparse.py` in CPython. No standalone repo.
- **Activity:** released with every Python (3.13 in 2024-10, 3.14 in 2025-10).
- **Style:** imperative — instantiate `ArgumentParser`, call `add_argument()`.
- **Subcommands:** `add_subparsers()`; arbitrarily deep.
- **Completion:** none built in — most users add `argcomplete` (~1.4k stars).
- **Color / rich help:** none.
- **Testing:** call `parser.parse_args([...])` directly; no `CliRunner`.
- **Unique:** every Python interpreter on Earth has it.
- **Key reason to use:** single-file scripts, no-dep policies, internal
  tooling that must run on a stock interpreter, or anything where adding
  a dependency is more friction than the boilerplate it saves.

### 2. Click — `pallets/click`

- 17,477 stars · 130 open issues · `pushed_at` 2026-05-08 · BSD-3-Clause.
- 469 commits / 327 closed PRs / 431+ contributors in last 12 mo.
- Latest release **8.3.3** (2026-04-22).
- **Style:** decorators (`@click.command`, `@click.option`, `@click.argument`).
- **Subcommands:** `Group` composition — Flask, pip, and most large
  Python CLIs use this model.
- **Completion:** bash/zsh/fish built in.
- **Plugin system:** documented entry-point pattern; widely used.
- **Testing:** `click.testing.CliRunner` (the de-facto pattern).
- **Unique:** composable `Group`/`Command` model — became the Python CLI
  default after `setuptools` adopted it.
- **Key reason to use:** multi-subcommand CLIs of any size where you
  benefit from a large ecosystem (`click-plugins`, `click-completion`,
  `rich-click`, …).

### 3. Typer — `fastapi/typer`

- 19,387 stars · 77 open issues · `pushed_at` 2026-05-11 · MIT.
- 578 commits / 377 closed PRs / 101+ contributors in last 12 mo.
- Latest release **0.25.1** (2026-04-30). Still 0.x — no 1.0 yet despite
  wide adoption.
- **Style:** plain functions, decorated with `@app.command()`; argument
  type and default come from the signature; `typer.Option(...)` /
  `typer.Argument(...)` carry metadata (help text, prompt, env-var).
- **Type hints:** **central** — annotations *are* the CLI spec; IDE
  autocomplete works on options/args.
- **Subcommands:** nested `Typer()` apps mounted on parents.
- **Completion:** bash/zsh/fish/powershell built in.
- **Rich help:** auto, via Rich (mandatory dependency since ~0.12).
- **Built on Click** — inherits its plugin / testing model.
- **Dependencies:** `click`, `rich`, `shellingham`, `typing-extensions`.
- **Unique:** type hints drive the parser — fewer lines of CLI plumbing
  than any other framework when the codebase is already typed.
- **Key reason to use:** modern Python 3.10+ codebase, you want minimum
  boilerplate, you don't mind the dependency chain.

### 4. Fire — `google/python-fire`

- 28,188 stars · 175 open issues · `pushed_at` 2026-04-01 · Apache-2.0.
- 14 commits / 34 closed PRs / 67+ contributors in last 12 mo.
- Latest release **0.7.1** (2025-08-16). Maintenance mode — slow, but alive.
- **Style:** `fire.Fire(obj)` — wrap any function, class, module, or dict.
- **Help:** auto, but verbose / reflection-style.
- **Subcommands:** implicit via attribute/method chains on classes.
- **Completion:** generates a bash completion script (limited).
- **Testing:** none built in.
- **Unique:** zero-effort exposure of an existing object graph as a CLI.
- **Key reason to use:** "I have this class / module — make it a CLI"
  without writing any CLI code; great for internal tools, exploration,
  Jupyter-adjacent workflows.

### 5a. docopt — `docopt/docopt`

- 8,007 stars · 266 open issues · `pushed_at` 2025-06-23 · MIT.
- **1 commit / 1 closed PR in last 12 mo. No GitHub release ever
  published.** Last meaningful release `0.6.2` (2014).
- **Verdict:** **unmaintained** for ~10 years. Do not use for new
  projects. Use `docopt-ng` (next entry) if you like the model.
- **Style:** parse the program's `--help` docstring — the help text *is*
  the spec.
- **Unique:** spec is the docstring; nothing else to learn.
- **Key reason to use:** don't, for new projects.

### 5b. docopt-ng — `jazzband/docopt-ng`

- 220 stars · 17 open issues · `pushed_at` 2025-08-11 · MIT.
- **0 commits / 0 closed PRs in last 12 mo.** Latest release **0.9.0**
  (2023-05-30). Dormant but the maintained fork at Jazzband.
- **Improvements over docopt:** type hints, magic-mode
  (`docopt(__doc__)` reads the caller's docstring), Python 3 cleanup.
- **Key reason to use:** you specifically want the docstring-as-spec
  model and accept a small, slow-moving project.

### 6. cleo — `python-poetry/cleo`

- 1,345 stars · 48 open issues · `pushed_at` 2026-05-04 · MIT.
- 19 commits / 34 closed PRs / 38+ contributors in last 12 mo.
- Latest release **2.1.0** (2023-10-30) — no new release in ~19 months
  despite recent commits. README states a **3.0 rewrite is in progress**.
- **Style:** Symfony-Console-port — subclass `Command`, declare
  `arguments`/`options` lists, override `handle()`.
- **Subcommands:** `Application.add()`.
- **Completion:** built in, Symfony-style.
- **Color / formatter:** built in (no Rich dependency).
- **Testing:** `CommandTester` built in.
- **Unique:** Symfony Console ergonomics in Python — verbose but
  explicit; rich built-in output without Rich.
- **Key reason to use:** you like Symfony Console; powers `poetry` itself
  (so the API is unlikely to disappear).

### 7. argh — `neithere/argh`

- `gh api repos/akrylysov/argh` returns 404 — the original repo moved.
  The maintained location appears to be `neithere/argh` (the original
  author's GitHub). Hard numbers **not gathered** in this pass; treat
  this row as **n/a** until refreshed.
- **Style (from project knowledge):** thin wrapper around argparse using
  function signatures + decorators (`@argh.arg`).
- **Type hints:** partial — recent versions read annotations for type
  coercion.
- **Subcommands:** yes (`argh.add_commands`).
- **Completion / color:** none built in.
- **Unique:** argparse under the hood, function-signature on top —
  "argparse without the boilerplate."
- **Key reason to use:** you want argparse-compatible behavior with
  decorator-style ergonomics and no new dependencies.

### 8. plac — `ialbert/plac`

- 300 stars · 3 open issues · `pushed_at` 2025-04-04 · BSD-2-Clause.
- **0 commits / 0 closed PRs in last 12 mo.** Latest release **1.4.3**
  (2024-02-22). Dormant.
- **Style:** function signature → CLI; `plac.call(func)`.
- **Type hints:** minimal — uses annotations as plac-specific parser
  spec strings.
- **Subcommands:** yes, plus an interactive REPL mode generated from the
  same signatures.
- **Single-file, zero-dep.**
- **Unique:** generates a CLI *and* an interactive REPL from one function
  signature; single .py with no dependencies — copyable.
- **Key reason to use:** tiny scripts where copying one file beats
  adding a dependency.

### 9. rich-click — `ewels/rich-click`

- 807 stars · 9 open issues · `pushed_at` 2026-01-31 · MIT.
- 300 commits / 60 closed PRs / 32+ contributors in last 12 mo.
- Latest release **1.9.7** (2026-01-31).
- **Not a standalone framework.** Drop-in `import rich_click as click`
  wrapper. Adds Rich-formatted help, panels, ~100 themes, SVG/HTML help
  export, and a `rich-click` CLI that re-renders *other* Click/Typer
  apps' help.
- **Dependencies:** `click`, `rich`.
- **Unique:** single-line monkey-patch makes any Click CLI look polished.
- **Key reason to use:** you already use Click and want pretty `--help`
  without rewriting in Typer.

### Companion: Rich — `Textualize/rich`

- 56,323 stars · 320 open issues · `pushed_at` 2026-04-12 · MIT.
- 245 commits / 185 closed PRs / 289+ contributors in last 12 mo.
- Latest release **15.0.0** (2026-04-12).
- **Not a CLI framework** — a terminal rendering library. Listed here
  only because it is the engine behind Typer's and rich-click's polished
  output, and many CLIs use it directly for formatting tables, progress
  bars, tracebacks, syntax highlighting.

---

## Choosing between them

Decision tree, in priority order:

1. **Single file / zero deps non-negotiable?** → `argparse` (or `plac`
   if you want function-signature style).
2. **Already typed Python 3.10+ and want minimum boilerplate?** → `Typer`.
3. **Multi-subcommand CLI of moderate-to-large size, ecosystem matters,
   willing to add one dependency?** → `Click`. Add `rich-click` later
   for prettier help.
4. **Exposing an existing object graph as a CLI for internal use?** →
   `Fire`.
5. **You write Symfony PHP for a living and want the same ergonomics?**
   → `cleo`.
6. **You want the docstring to be the spec?** → `docopt-ng` (knowing it
   is dormant). Avoid `docopt` itself.
7. **You want argparse with decorator sugar and zero deps?** → `argh`
   (verify activity at `neithere/argh` first).

---

## Why m-cli still uses argparse

- `m-cli` is the canonical `m` dispatcher for the M language toolchain.
  It ships as a single installable package with hard guarantees about
  what its `--help` output and `--json` capability manifest look like
  (`dist/commands.json` is generated from the argparse tree, then
  validated by CI for drift).
- We rely on argparse's `add_subparsers()` + custom action classes
  throughout the CLI (every subcommand under `src/m_cli/*/cli.py` adds
  its parser into the same dispatcher tree). The capability manifest
  introspection walks `argparse._SubParsersAction` directly.
- Zero runtime CLI-framework dependency keeps the install surface small
  and means a stock CPython is enough to run `m doctor` and bootstrap.
  Our optional extras (`m-cli[lsp]` → `pygls`) are the only deps that
  matter to users.
- Migration to Click/Typer would buy: shell completion + slightly nicer
  decorators. It would cost: rewriting the manifest generator, the
  plugin entry-point loader (`m_cli.plugins`), every test that asserts
  argparse error text, and the documented `m capabilities --json`
  contract. The trade is not worth it for the surface area we have.

If the dispatcher were starting from scratch today and there were no
manifest contract, `Typer` would be the obvious choice. We are not
starting from scratch.

---

## Refresh procedure

To regenerate the numbers in this doc:

```bash
# Replace SINCE with today-minus-1y, ISO 8601.
SINCE=2025-05-11T00:00:00Z

# Repo basics (one per row in the table):
gh api repos/pallets/click         --jq '{stars:.stargazers_count, issues:.open_issues_count, pushed:.pushed_at, license:.license.spdx_id}'

# Commits in last 12 months (read Link: rel="last" page count):
gh api -i "repos/pallets/click/commits?since=${SINCE}&per_page=1" | grep -i '^link:'

# Closed PRs in last 12 months:
gh api "search/issues?q=repo:pallets/click+is:pr+is:closed+closed:>${SINCE%T*}&per_page=1" --jq .total_count

# Contributors (upper bound — includes anonymous co-authors):
gh api -i "repos/pallets/click/contributors?per_page=1&anon=1" | grep -i '^link:'

# Latest release:
gh api repos/pallets/click/releases/latest --jq '{tag:.tag_name, published:.published_at}'
```

Re-run for each repo in the summary table. Update the `Data snapshot:`
date at the top.
