# m-cli — the M (MUMPS) developer toolchain

`m fmt`, `m lint`, `m test`, `m coverage`, `m watch`, `m lsp`, and friends
for the M (MUMPS) language. The canonical `m <subcommand>` interface
(mirroring `cargo`, `go`, `git`) for the
[m-dev-tools](https://github.com/m-dev-tools) ecosystem.

Engine-neutral at the source layer (`m fmt`, `m lint` care about M syntax,
not a runtime). YottaDB-targeted at the runtime layer (`m test`,
`m coverage`); IRIS portability tracked in fail-soft CI. Works for any M
codebase — you do not need MUMPS or VistA background to use this tool.

```bash
m new myapp              # scaffold a TDD-ready M project
cd myapp
m test                   # run the test suite
m fmt && m lint          # canonicalise + lint
m coverage --min-percent=85
```

## Contents

- [What ships](#what-ships)
- [Install](#install)
- [Quick tour](#quick-tour)
- [Subcommand reference](#subcommand-reference)
  - [`m fmt` — formatter](#m-fmt--formatter)
  - [`m lint` — linter](#m-lint--linter)
  - [`m test` — test runner](#m-test--test-runner)
  - [`m coverage` — coverage](#m-coverage--coverage)
  - [`m watch` — TDD watcher](#m-watch--tdd-watcher)
  - [`m lsp` — Language Server](#m-lsp--language-server)
  - [`m stdlib` — m-stdlib reference](#m-stdlib--m-stdlib-reference-nested-namespace)
  - [Project scaffolding and helpers](#project-scaffolding-and-helpers)
- [Configuration — `.m-cli.toml`](#configuration--m-clitoml)
- [Engine support](#engine-support)
- [Plugin extension](#plugin-extension)
- [Layout](#layout)
- [Documentation](#documentation)
- [Licence](#licence)

## What ships

| Surface | Status | One-line summary |
|---------|:------:|------------------|
| `m fmt`      | ✅ | Round-trip formatter — identity (default), canonical hygiene, four translation presets (`pythonic` / `pythonic-lower` / `compact`). |
| `m lint`     | ✅ | Engine-neutral lint engine with named profiles (`default`, `modern`, `pedantic`, `xindex`, `vista`, `sac`, `pythonic`, `all`); `M-XINDX-NN` + `M-MOD-NN` rule families; configurable thresholds; engine targeting; inline disable directives; auto-fix linkage with `m fmt`. |
| `m test`     | ✅ | Parser-aware discovery (`*TST.m` / `t<UpperCase>(pass,fail)`); single-test selection (`FILE.m::tLabel`); text / TAP / JSON output; `--changed` for diff-driven runs. |
| `m coverage` | ✅ | Label + line coverage via YDB `view "TRACE"`; `--branch` for AST-driven branch points; text / `text --lines` / JSON / LCOV output; `--min-percent` CI gate. |
| `m watch`    | ✅ | Polling file watcher; source→suite affinity; `--once` / `--interval` / `--filter`. |
| `m lsp`      | ✅ | LSP server over stdio — diagnostics, formatting, code actions, hover, completion, document symbols, code lenses, folding, signature help, document highlight, go-to-definition, find-references, workspace symbol search. |
| `m stdlib doc` / `search` / `manifest` / `examples` / `errors` | ✅ | Manifest-driven m-stdlib reference (one nested namespace; grouped under `m stdlib` since 2026-05-11). |
| `m new` / `m run` / `m doctor` / `m ci init` | ✅ | Project scaffolding, ad-hoc execution, environment self-check, CI scaffolding. |
| `m plugins`  | ✅ | Lists out-of-tree subcommands registered via the `m_cli.plugins` entry-point group. |

Pre-commit hooks (`m-fmt-check`, `m-fmt`, `m-lint`) ship in
[`.pre-commit-hooks.yaml`](.pre-commit-hooks.yaml).

## Install

**Prerequisites:** `git`, `docker`, Python 3.12+, [`uv`](https://docs.astral.sh/uv/),
`make`. Docker daemon needs to be running (Docker Desktop on macOS /
Windows, `systemctl start docker` on Linux). Install via your package
manager — `apt install git docker.io python3.12 make` on Debian /
Ubuntu, `brew install git docker python@3.12 uv` on macOS — then
`curl -LsSf https://astral.sh/uv/install.sh | sh` for uv if it's not
in your package manager.

### One-paste install

m-cli's distribution model is **clone-and-install**: `pyproject.toml`
declares [`tree-sitter-m`](https://github.com/m-dev-tools/tree-sitter-m)
(parser) and [`m-standard`](https://github.com/m-dev-tools/m-standard)
(language reference) as sibling checkouts.
[`m-stdlib`](https://github.com/m-dev-tools/m-stdlib) is the standard
library; needed when you write M code that uses it. Clone all four
under one directory, install m-cli, start the engine, verify:

```bash
mkdir -p ~/m-dev-tools && cd ~/m-dev-tools && \
  for r in tree-sitter-m m-standard m-cli m-stdlib; do \
    [ -d "$r" ] || git clone "https://github.com/m-dev-tools/$r"; \
  done && \
  cd m-cli && make install && \
  .venv/bin/m engine install && .venv/bin/m engine start && \
  .venv/bin/m doctor
```

One paste, one wait. If `m doctor` reports anything other than all
checks ✓, fix that before doing anything else — every command below
depends on the engine being healthy.

Add `~/m-dev-tools/m-cli/.venv/bin` to your `PATH` (or use
[`direnv`](https://direnv.net/)) so `m` works without the `.venv/bin/`
prefix.

### Step-by-step (if you'd rather not paste a one-liner)

```bash
mkdir -p ~/m-dev-tools && cd ~/m-dev-tools
git clone https://github.com/m-dev-tools/tree-sitter-m
git clone https://github.com/m-dev-tools/m-standard
git clone https://github.com/m-dev-tools/m-cli
git clone https://github.com/m-dev-tools/m-stdlib       # only if you'll call into stdlib
cd m-cli
make install                                            # uv sync --extra dev + pre-commit hooks
.venv/bin/m engine install                              # docker pull ghcr.io/m-dev-tools/m-test-engine
.venv/bin/m engine start                                # docker run -d -v $HOME/m-work:/m-work …
.venv/bin/m doctor                                      # all checks should be ✓
```

### Engine alternatives

The recommended runtime path is the Docker engine above (cross-platform,
pinned image). If Docker isn't an option, m-cli also supports:

- **Local YottaDB** on `$PATH` — `m doctor` detects it.
- **Remote YDB over SSH** — legacy vista-meta path; advanced.

See [Engine support](#engine-support).

### Bootstrap for working with M code

The [walkthrough](docs/m-cli-tdd-lifecycle-walkthrough.md) shows the
full TDD lifecycle of an M data-analysis app from a fresh install,
exercising every `m <subcommand>`. Re-runnable on any docker-capable
host — read that doc once after install to validate the toolchain is
working end-to-end.

## Quick tour

The TDD inner loop, end to end:

```bash
m new fetcher && cd fetcher                   # scaffold project
make -C ~/projects/m-test-engine up           # start test engine (one-time)

# write tests/FETCHTST.m using STDASSERT (red)
m test                                        # confirm RED
# implement src/fetch.m
m test                                        # GREEN

m fmt                                         # canonicalise
m lint --error-on=error                       # zero errors before commit
m coverage --min-percent=85                   # coverage gate
```

`m watch` collapses the inner loop to a single long-running command:

```bash
m watch                                       # polls cwd, reruns affected suites on change
```

## Subcommand reference

The condensed reference. The deep version with profiles, thresholds, rule
catalogues, and design rationale lives in [`docs/guide.md`](docs/guide.md).

### `m fmt` — formatter

```bash
m fmt path/                                   # rewrite in place (identity, default)
m fmt --rules=canonical path/                 # SAC hygiene: trim + uppercase commands
m fmt --rules=pythonic path/                  # expand abbreviations: S→SET, $L→$LENGTH
m fmt --rules=pythonic-lower path/            # all lowercase: set, $length, $test
m fmt --rules=compact path/                   # compact: SET→S, $LENGTH→$L
m fmt --check src/                            # CI mode — exit 1 on any pending change
m fmt --diff path/file.m                      # unified diff
m fmt --stdout file.m                         # write to stdout
```

Translation presets are AST-shape-preserving and idempotent on
already-normalised input; `compact(pythonic(compact(src))) == compact(src)`.

### `m lint` — linter

```bash
m lint path/                                  # default profile (curated M-MOD subset)
m lint --list-profiles                        # show available profiles
m lint --rules=modern path/                   # full M-MOD modernization track
m lint --rules=xindex path/                   # engine-neutral XINDEX subset (42 rules)
m lint --rules=pythonic path/                 # M-MOD + tighter Python-style thresholds
m lint --rules=M-XINDX-014 path/              # explicit rule list
m lint --format=json path/                    # machine-readable
m lint --format=tap  path/                    # CI integration
m lint --error-on=fatal path/                 # exit 1 only on fatal
m lint --target-engine=yottadb path/          # silence engine-portability false positives
m lint --jobs 16 path/                        # parallel across routines
```

Built-in profiles:

| Profile | Rules | Notes |
|---------|:-----:|-------|
| `default`  | 26 | Curated daily-lint set — M-MOD minus the four pedantic style rules. |
| `modern`   | 30 | Full M-MOD modernization track including pedantic style rules. |
| `pedantic` | 4  | Just the four pedantic style rules — focused style pass. |
| `pythonic` | 30 | `modern` + tighter thresholds (line=100, commands_per_line=1, cyclomatic=10, …). |
| `xindex`   | 34 | Engine-neutral subset of the VA Toolkit XINDEX rule set. |
| `vista`    | 8  | VA-Kernel-specific (`OPEN`→`^%ZIS`, banner conventions, etc.). Opt-in. |
| `sac`      | 23 | VA SAC portable subset — `sac`-tagged rules minus VistA-Kernel ones. |
| `all`      | 72 | Every registered rule. |

Inline disable directives:

```mumps
SET X=1   ; m-lint: disable=M-MOD-031        ; same line
; m-lint: disable-next-line=M-XINDX-013
; m-lint: disable-file=*                      ; whole file
```

Configurable thresholds (CLI flag or `[lint.thresholds]` in
`.m-cli.toml`):

```bash
m lint --threshold line_length=100 --threshold commands_per_line=1 path/
```

### `m test` — test runner

```bash
m test                                        # discover + run every *TST.m
m test src/routines/tests/FOOTST.m            # one suite
m test FOOTST.m::tHappyPath                   # one label
m test --filter happy                         # name-substring filter
m test --changed                              # only suites affine with git-modified .m files
m test --changed-base origin/main             # diff against a specific rev
m test --format=tap                           # CI / aggregator output
m test --format=json
m test --list                                 # discovery only
```

### `m coverage` — coverage

```bash
m coverage                                    # text summary
m coverage --lines                            # per-routine label + line columns
m coverage --branch                           # AST-driven branch coverage
m coverage --format=lcov > cov.info           # genhtml / Codecov / Coveralls
m coverage --format=json
m coverage --min-percent=85                   # CI gate (exit 1 below threshold)
```

### `m watch` — TDD watcher

```bash
m watch                                       # poll cwd; rerun affected suites on change
m watch --once                                # one pass then exit (CI smoke)
m watch --interval 1.0                        # tune poll period (default 0.5 s)
m watch --filter slow                         # restrict to suites matching name substring
```

Affinity rule: `<X>.m` → `<X>TST.m` if it exists; suite-file edits map to
themselves only; non-mappable changes re-run every suite (defensive
default).

### `m lsp` — Language Server

```bash
m lsp                                         # speak LSP over stdio
m lsp --rules xindex,vista                    # override the lint profile for diagnostics
```

VS Code wiring: install
[`tree-sitter-m-vscode`](https://github.com/m-dev-tools/tree-sitter-m-vscode);
the extension spawns `m lsp` on activation. Settings: `m-cli.enabled`,
`m-cli.path` (set to the venv-installed `m` binary if not on `$PATH`),
`m-cli.args`, `m-cli.trace.server`.

### `m stdlib` — m-stdlib reference (nested namespace)

```bash
m stdlib doc parse^STDJSON                    # signature, params, returns, examples
m stdlib search uuid                          # full-text search across the manifest
m stdlib manifest                             # print the active stdlib-manifest.json
m stdlib examples STDCSV                      # runnable examples for a module
m stdlib errors STDB64                        # error catalogue for a module
```

Manifest source:
[`m-stdlib/dist/stdlib-manifest.json`](https://raw.githubusercontent.com/m-dev-tools/m-stdlib/main/dist/stdlib-manifest.json).

### Project scaffolding and helpers

```bash
m new myproj                                  # scaffold TDD-ready M package
m ci init                                     # drop a CI workflow into .github/
m run path/to/routine.m                       # run a routine end-to-end
m doctor                                      # self-check: ydb, parser, m-standard, manifests
m plugins                                     # list registered out-of-tree subcommands
```

## Configuration — `.m-cli.toml`

Both `.m-cli.toml` (preferred) and `[tool.m-cli]` in `pyproject.toml` are
discovered by walking up from the working directory; the walk stops at
`.git`. CLI flags override config; unknown keys are ignored.

```toml
[lint]
rules = "default"                  # profile name or comma list of rule IDs
disable = ["M-XINDX-013"]          # rule ids to skip after selection
target_engine = "yottadb"          # "yottadb" | "iris" | "any"

[lint.severity]
"M-XINDX-019" = "warning"          # remap per-rule severity

[lint.thresholds]
line_length = 100
commands_per_line = 1
cyclomatic = 10

[lint.taint]                       # M-MOD-036 taint analysis
formals_tainted = true
extra_sanitizers = ["$E"]

[fmt]
rules = "canonical"                # "canonical" | "none" | comma list of rule IDs
```

## Engine support

`m test` and `m coverage` need a YottaDB engine.
[`m_cli.engine.detect_engine`](src/m_cli/engine.py) auto-resolves a
transport in this order:

1. **Explicit override** — `M_CLI_ENGINE=local|docker|ssh`.
2. **Docker (m-test-engine)** — a running container named `m-test-engine`.
   The canonical default — pinned image, identical behavior across
   machines.
3. **SSH** — fallback if a `~/data/vista-meta/conn.env` file exists.
   Legacy maintainer path.
4. **Local YottaDB** — fallback if `mumps` / `ydb` is on `$PATH`. For
   offline / no-Docker environments.

Fresh installs typically use option 2:

```bash
git clone https://github.com/m-dev-tools/m-test-engine
make -C m-test-engine up                       # builds + starts the container

cd ~/projects/myapp
m test                                          # auto-detects the running container
```

Force a transport explicitly:

```bash
M_CLI_ENGINE=docker m test
M_CLI_ENGINE=local  m test
```

## Plugin extension

Out-of-tree subcommands register against m-cli via the `m_cli.plugins`
Python entry-point group. After `pip install m-cli-extras` (or any other
plugin), `m plugins` lists them and they appear as regular subcommands:

```
$ m plugins
m-cli plugin API v1

Registered plugins (1):
  m corpus-stats   (m-cli-extras 0.1.0)

$ m corpus-stats /path/to/corpus
corpus                          /path/to/corpus
files                           1234
total_lines                     287654
```

Plugin contract: [`docs/plugin-development.md`](docs/plugin-development.md).
Reference implementation:
[`m-cli-extras`](https://github.com/m-dev-tools/m-cli-extras).

## Layout

```
m-cli/
├── pyproject.toml                # uv-managed; tree-sitter-m + m-standard as path deps
├── src/m_cli/
│   ├── cli.py                    # `m` dispatcher (argparse subcommands)
│   ├── parser.py                 # tree-sitter-m wrapper
│   ├── config.py                 # .m-cli.toml / [tool.m-cli] loader
│   ├── engine.py                 # YDB / Docker / SSH transports
│   ├── workspace.py              # cross-routine label index
│   ├── plugins.py                # entry-point discovery for plugins
│   ├── fmt/                      # m fmt   — round-trip formatter
│   ├── lint/                     # m lint  — engine-neutral lint engine + profiles
│   ├── test/                     # m test  — discovery + ydb runner
│   ├── watch/                    # m watch — polling file watcher
│   ├── coverage/                 # m coverage — view "TRACE" + LCOV emitter
│   ├── lsp/                      # m lsp   — pygls language server
│   ├── doc/                      # m stdlib doc / search / manifest / examples / errors (handlers; wired in stdlib_cli.py)
│   ├── doctor/                   # m doctor — environment self-check
│   ├── new/                      # m new   — project scaffolder
│   ├── ci/                       # m ci    — CI scaffolding
│   └── run/                      # m run   — ad-hoc routine execution
├── tests/                        # one test file per source module
├── scripts/                      # corpus-validation drivers + benches
├── docs/                         # guide + plugin contract + design notes (see below)
└── README.md                     # this file
```

## Documentation

| Doc | Audience |
|-----|----------|
| [`docs/guide.md`](docs/guide.md) | Comprehensive user guide — every subcommand, every flag, every profile, every rule family, with rationale. |
| [`docs/m-linting-user-guide.md`](docs/m-linting-user-guide.md) | Long-form linter user guide — picking a profile, tuning thresholds, writing inline disables. |
| [`docs/plugin-development.md`](docs/plugin-development.md) | Contract for out-of-tree subcommands via `m_cli.plugins` entry-point group. |
| [`docs/pre-commit.md`](docs/pre-commit.md) | Wiring `m-fmt-check` / `m-fmt` / `m-lint` into the pre-commit framework. |
| [`docs/worked-example-accsum.md`](docs/worked-example-accsum.md) | A real M routine walked end-to-end through fmt + lint + test. |
| [`docs/evolution.md`](docs/evolution.md) | **Archaeology.** How m-cli was built, in chronological order. Read this only if you care *why* the tool is shaped this way. |
| [`docs/vista-meta-bootstrap.md`](docs/vista-meta-bootstrap.md) | **Archaeology.** How the VistA corpus was used during initial development, and the explicit verification that m-cli is no longer dependent on it. |
| [CLI UX conventions guide](https://github.com/m-dev-tools/.github/blob/main/docs/dev-practices/cli-ux-conventions-guide.md) | **Org-level.** Rules every `m <subcommand>` follows: bare-dispatcher overview, `--help` to stdout, exit-code vocabulary (0 success / 1 domain / 2 usage), unknown-flag routing. Pinned by `tests/test_cli_ux_contract.py`. |

## Licence

[AGPL-3.0](LICENSE). Family-wide consistency with the rest of
[m-dev-tools](https://github.com/m-dev-tools).
