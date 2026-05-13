# m-cli Output Audit — 2026-05-13

A point-in-time, faithful snapshot of every `m` subcommand's user-visible UI as
it ships today. This is the **real, as-is UI** — not aspirational, not
prescriptive — captured to serve as the foundation for visual and formatting
improvements.

For each subcommand the document records, verbatim:

1. **Purpose** — the parser description (one paragraph).
2. **`--help` output** — `m <cmd> --help`.
3. **Real output samples** — what comes out on `stdout`/`stderr` for the most
   common invocation shapes, with exit codes.
4. **`m capabilities` view** — what the machine-readable manifest says about
   the subcommand.
5. **Observations** — visual / UX notes worth bringing forward.

A final section pulls together cross-cutting patterns and inconsistencies that
span subcommands.

---

## Audit environment

| Field            | Value                                                  |
| ---------------- | ------------------------------------------------------ |
| `m --version`    | `m-cli 0.1.0`                                          |
| Binary           | `/home/rafael/m-dev-tools/m-cli/.venv/bin/m`           |
| Engine driver    | `docker` (m-test-engine `ghcr.io/m-dev-tools/m-test-engine:0.1.0`) |
| Probe project    | `~/m-dev-tools/m-stdlib` (48 suites, src/, tests/)     |
| Scaffold project | `m new sampleapp --path /tmp/m-audit-sample/scaffold`  |
| Date captured    | 2026-05-13                                             |
| Host             | Linux Mint, bash 5.x                                   |

All output is reproduced exactly as printed by the CLI, including whitespace,
glyphs (`✓`, `→`, em-dashes), and ANSI-free plain text.

---

## Top-level `m`

### `m` with no arguments (exit 0)

```
M (MUMPS) source-level toolchain.
Engine-neutral source tooling (fmt/lint/stdlib); runtime tools (test/coverage) target YottaDB.

USAGE
  m <command> [options]

COMMANDS
  fmt:           Format M source files
  lint:          Lint M source files
  test:          Run M test suites against YottaDB
  watch:         Re-run M test suites on file change
  coverage:      Measure test coverage of an M project
  lsp:           Run the m-cli Language Server (over stdio)
  engine:        Manage the m-test-engine container (install/start/stop/...)
  doctor:        Diagnose the M development environment
  new:           Scaffold a new M project
  ci:            CI scaffolding (subcommand: `init`)
  run:           Run an M routine via `ydb -run ENTRYREF`
  stdlib:        m-stdlib reference lookups (doc/search/examples/errors/manifest)
  plugins:       List installed m-cli plugins (out-of-tree subcommands)
  capabilities:  Emit a machine-readable view of every m subcommand (JSON)

Run 'm <command> --help' for more information about a command.
```

### `m --help` (exit 0)

```
usage: m [-h] [-V] <command> ...

M (MUMPS) source-level toolchain.

positional arguments:
  <command>
    fmt           Format M source files
    lint          Lint M source files
    test          Run M test suites against YottaDB
    watch         Re-run M test suites on file change
    coverage      Measure test coverage of an M project
    lsp           Run the m-cli Language Server (over stdio)
    engine        Manage the m-test-engine container (install/start/stop/...)
    doctor        Diagnose the M development environment
    new           Scaffold a new M project
    ci            CI scaffolding (subcommand: `init`)
    run           Run an M routine via `ydb -run ENTRYREF`
    stdlib        m-stdlib reference lookups
                  (doc/search/examples/errors/manifest)
    plugins       List installed m-cli plugins (out-of-tree subcommands)
    capabilities  Emit a machine-readable view of every m subcommand (JSON)

options:
  -h, --help      show this help message and exit
  -V, --version   show program's version number and exit
```

### `m -V` (exit 0)

```
m-cli 0.1.0
```

### `m bogus-cmd` (exit 2)

```
usage: m [-h] [-V] <command> ...
m: error: argument <command>: invalid choice: 'bogus-cmd' (choose from fmt, lint, test, watch, coverage, lsp, engine, doctor, new, ci, run, stdlib, plugins, capabilities)
```

### Observations — top-level

- Two different layouts for the same information: bare `m` uses a custom
  `USAGE / COMMANDS` block with colons; `m --help` falls back to the default
  argparse formatter (lowercase `usage:`, indented tree, no colons).
- Bare `m` has a second tagline line ("Engine-neutral source tooling…") that
  `m --help` does not include.
- Command list ordering differs slightly from logical grouping (e.g. `lsp`
  sits between `watch` and `engine`).
- Unknown command error uses lowercase argparse style (`m: error: …`) and a
  flat comma-separated choices list — visually distinct from the curated
  `USAGE / COMMANDS` block.

---

## `m capabilities`

### Purpose

> Emit a machine-readable view of every m subcommand (JSON).

### `m capabilities --help` (exit 0)

```
usage: m capabilities [-h] [--json]

Walk the argparse subparser tree and emit a JSON document describing every
subcommand's purpose, options, choices, defaults, and (when authored via the
parser's epilog field) example invocations. The output is the source artifact
for dist/commands.json, exposed by tier-1 repo.meta.json. Plugin-contributed
subcommands appear automatically.

options:
  -h, --help  show this help message and exit
  --json      Emit JSON (currently the only supported format; accepted for
              explicitness)
```

### Real output

`m capabilities` (no flags) and `m capabilities --json` produce **identical**
output: a JSON document, ~524 lines, two-space indented, UTF-8 escaped (`—`
instead of `—`). Top-level shape:

```
{
  "version": "0.1.0",
  "subcommands": {
    "capabilities": { ... },
    "ci": { ... },
    ...
    "watch": { ... }
  }
}
```

Per-subcommand record shape (first entry, verbatim):

```json
"capabilities": {
  "purpose": "Emit a machine-readable view of every m subcommand (JSON)",
  "options": [
    {
      "name": "--json",
      "help": "Emit JSON (currently the only supported format; accepted for explicitness)",
      "default": false,
      "choices": null
    }
  ],
  "examples": []
}
```

### `m capabilities` view of itself

```json
"capabilities": {
  "purpose": "Emit a machine-readable view of every m subcommand (JSON)",
  "options": [{ "name": "--json", "default": false, ... }],
  "examples": []
}
```

### Observations

- Option count summary across all subcommands (from the manifest):

  | subcommand     | options | examples |
  | -------------- | ------: | -------: |
  | `capabilities` |       1 |        0 |
  | `ci`           |       0 |        0 |
  | `coverage`     |      10 |        0 |
  | `doctor`       |       3 |        0 |
  | `engine`       |       0 |        0 |
  | `fmt`          |       8 |        0 |
  | `lint`         |      16 |        0 |
  | `lsp`          |       3 |        0 |
  | `new`          |       4 |        0 |
  | `plugins`      |       1 |        0 |
  | `run`          |       4 |        0 |
  | `stdlib`       |       0 |        0 |
  | `test`         |      13 |        0 |
  | `watch`        |       5 |        0 |

  Two patterns worth flagging:
  - **`examples: []` for every command.** The manifest reserves an `examples`
    array (sourced from each parser's `epilog`), but no subcommand currently
    fills it. Discoverability is left entirely to the `--help` body.
  - **`ci`, `engine`, `stdlib` report `options: 0`.** These are the three
    sub-action commands. The manifest does not descend into their `<action>`
    subparsers, so `m capabilities` is silent about `m engine status`,
    `m stdlib doc`, `m ci init`, etc. Programmatic consumers have no view of
    those verbs.
- The `--json` flag exists for parity with the tier-1 manifest contract but
  has no observable effect — JSON is always the output.
- The JSON emitter HTML-escapes Unicode (e.g. `—` for `—`), so reading
  the raw stream is unfriendly even though every consumer that decodes it
  gets the right glyph.

---

## `m ci`

### Purpose

> CI scaffolding (subcommand: `init`).

### `m ci --help` (exit 0)

```
usage: m ci [-h] <action> ...

Scaffold CI configuration for m-cli projects.

positional arguments:
  <action>
    init      Preview (or with --write, scaffold) .github/workflows/m-ci.yml

options:
  -h, --help  show this help message and exit
```

### `m ci` with no action (exit 0)

```
Scaffold CI configuration for m-cli projects.
Writes `.github/workflows/m-ci.yml` (fmt --check + lint + test + coverage).

USAGE
  m ci <action> [options]

COMMANDS
  init:  Preview (or with --write, scaffold) .github/workflows/m-ci.yml

Run 'm ci <action> --help' for more information about an action.
```

### `m ci init --help` (exit 0)

```
usage: m ci init [-h] [--write] [--path PATH] [--force] [-q]

Scaffold .github/workflows/m-ci.yml. Without --write, prints the planned file
path and workflow YAML to stdout and exits 0 (preview mode — never mutates
state). Pass --write to actually create the file.

options:
  -h, --help   show this help message and exit
  --write      Write the workflow file. Without this, prints the planned path
               and workflow YAML to stdout and exits 0 (preview mode).
  --path PATH  Project root (default: current directory)
  --force      Overwrite an existing workflow file (with --write)
  -q, --quiet  Suppress per-file progress output
```

### `m ci init` (preview mode, exit 0)

```
# preview: would write .github/workflows/m-ci.yml
# pass --write to scaffold the file
# ----- m-ci.yml -----
# GitHub Actions workflow generated by `m ci init`.
#
# Runs the four project gates on every push and pull request:
#
#   m fmt --check          — verify modern style is preserved
#   m lint --error-on=fatal — run the configured lint profile
#   m test                  — run *TST.m suites under YottaDB
#   m coverage --format=lcov — emit lcov for upload to Codecov, etc.
# ... (full workflow body follows)
```

### `m capabilities` view

```json
"ci": {
  "purpose": "CI scaffolding (subcommand: `init`)",
  "options": [],
  "examples": []
}
```

### Observations

- `m ci` follows the same dual-layout pattern as the top-level binary:
  argparse-style for `--help`, curated `USAGE / COMMANDS` block when invoked
  with no action.
- Preview output is shell-comment-prefixed (`# preview: …`) so it's pipe-safe
  but visually hard to scan — there's no clear separator between the preview
  preamble and the YAML body other than `# ----- m-ci.yml -----`.
- The capabilities manifest reports `options: []` and never mentions `init`.

---

## `m coverage`

### Purpose

> Run the project's test suites under YottaDB ZBREAK instrumentation and
> report which production labels were exercised.

### `m coverage --help` (exit 0)

```
usage: m coverage [-h] [--routines ROUTINES] [--tests TESTS] [--suites SUITES]
                  [--format {text,json,lcov}] [--lines] [--uncovered]
                  [--branch] [--min-percent MIN_PERCENT] [-q]
                  [paths ...]

Run the project's test suites under YottaDB ZBREAK instrumentation and report
which production labels were exercised. Label-level coverage (line-level via
source instrumentation is a future deliverable). Outputs text (default), JSON.
Use --uncovered to list only uncovered labels; --min-percent N to fail the run
when coverage is below the threshold.

positional arguments:
  paths                 Project root or path(s) to scan (default: current
                        directory)

options:
  -h, --help            show this help message and exit
  --routines ROUTINES   Explicit production-routines path (repeatable). Skips
                        auto-detect.
  --tests TESTS         Explicit test-suites path (repeatable). Skips auto-
                        detect.
  --suites SUITES       Comma-separated suite names to restrict the run
                        (default: all)
  --format {text,json,lcov}
                        Output format (default: text). 'lcov' emits a
                        tracefile consumable by genhtml / Codecov / Coveralls.
  --lines               Show line-level detail in text output. With
                        --uncovered, also lists every uncovered executable
                        line.
  --uncovered           Print only uncovered labels (text format only)
  --branch              Collect branch coverage: identify
                        IF/ELSE/FOR/postconditional decisions and report which
                        were reached during the run.
  --min-percent MIN_PERCENT
                        Fail with exit 1 if total coverage is below this
                        percent
  -q, --quiet           Suppress the summary line on stderr
```

### Real output

#### Auto-detect fails (`m coverage tests/STDMATHTST.m`, exit 0)

```
m coverage: no production .m routines found
```

(Same string for every `--format` value — the no-routines guard fires before
the formatter is consulted.)

#### Explicit paths, default text (`m coverage --routines src --tests tests --suites STDMATHTST`, exit 0)

```
m coverage: 1 suite(s), 0/562 labels (0.0%)
Routine                Covered     Total   Percent
-------------------- --------- --------- ---------
STDARGS                      0        15      0.0%
STDASSERT                    0        15      0.0%
STDB64                       0         9      0.0%
STDCACHE                     0        10      0.0%
...
STDXML                       0        75      0.0%
-------------------- --------- --------- ---------
Total                        0       562      0.0%
```

Header is on `stderr`; the table is on `stdout`. `--quiet` suppresses the
stderr header only.

#### `--format json` (exit 0, first 25 lines)

```json
{
  "total": 562,
  "covered": 0,
  "percent": 0.0,
  "total_lines": 4405,
  "covered_lines": 0,
  "line_percent": 0.0,
  "returncode": 0,
  "suites_run": [
    "STDMATHTST"
  ],
  "by_routine": [
    {
      "routine": "STDARGS",
      "covered": 0,
      "total": 15,
      "percent": 0.0
    },
    ...
  ]
}
```

#### `--format lcov` (exit 0, head)

```
TN:
SF:src/STDARGS.m
DA:37,0
DA:49,0
DA:50,0
DA:51,0
...
```

Standard LCOV tracefile — no `m coverage:` header line, machine-clean.

#### `--uncovered` (exit 0, head)

```
Uncovered labels (562 of 562):
  addflag^STDARGS  (src/STDARGS.m:65)
  addpos^STDARGS  (src/STDARGS.m:86)
  ...
```

### `m capabilities` view

```json
"coverage": {
  "purpose": "Measure test coverage of an M project",
  "options": [
    {"name": "paths",         "default": ["."],    "choices": null},
    {"name": "--routines",    "default": [],       "choices": null},
    {"name": "--tests",       "default": [],       "choices": null},
    {"name": "--suites",      "default": null,     "choices": null},
    {"name": "--format",      "default": "text",   "choices": ["text","json","lcov"]},
    {"name": "--lines",       "default": false,    "choices": null},
    {"name": "--uncovered",   "default": false,    "choices": null},
    {"name": "--branch",      "default": false,    "choices": null},
    {"name": "--min-percent", "default": null,     "choices": null},
    {"name": "--quiet",       "default": false,    "choices": null}
  ],
  "examples": []
}
```

### Observations

- The `m coverage:` summary line lives on `stderr` for `text` (and is
  duplicated implicitly in `--format json` via `total/covered/percent`).
- `--branch` is documented but the text output for `--branch` looks
  identical to the default text output — no branch-coverage columns appear
  in the table. (Captured here as-is.)
- Failure case: `no production .m routines found` is the same string in
  every format, including `json` and `lcov` — JSON consumers therefore can't
  distinguish "no routines" from "0% coverage" without parsing prose.
- Routine column is fixed-width ~20 chars; columns are space-padded with no
  separators — readable in a fixed-width terminal, not adaptive.

---

## `m doctor`

### Purpose

> Run environment-health checks for the active transport.

### `m doctor --help` (exit 0)

```
usage: m doctor [-h] [--format {text,json}] [--fix] [--confirm]

Run environment-health checks for the active transport. Default is the m-test-
engine Docker container — the canonical, reliable, consistent M engine
environment. $M_CLI_ENGINE (local|docker|ssh) overrides the default to
validate the local YottaDB or legacy SSH path instead. The Docker engine path
checks the docker daemon, the m-test-engine image and container, and the host
bind-mount; the local path checks $ydb_dist, $ydb_routines, and the `ydb`
binary. The parser and m-standard keyword loaders are checked on every
transport. Each check reports OK / WARN / FAIL with an actionable hint on
failure. Exits 1 if any check is FAIL (WARN does not fail the run).

options:
  -h, --help            show this help message and exit
  --format {text,json}  Output format (default: text)
  --fix                 After running checks, invoke `m engine <verb>` for
                        every WARN whose fix is an engine verb (install /
                        start / ...). Non-engine fixes (sudo'd system
                        commands) are NOT auto-run — a manual: line prints
                        instead.
  --confirm             Required to run destructive engine verbs (e.g.
                        `reset`) via --fix. No-op without --fix.
```

### Real output (text, all checks green, exit 0)

```
  ✓ OK      docker_installed   docker CLI on PATH
  ✓ OK      docker_daemon      docker daemon reachable
  ✓ OK      engine_image       image ghcr.io/m-dev-tools/m-test-engine:0.1.0 present
  ✓ OK      engine_container   container `m-test-engine` running
  ✓ OK      engine_bind_mount  host /home/rafael/m-work exists
  ✓ OK      parser             tree-sitter-m loaded
  ✓ OK      keywords           323 M language keywords loaded from m-standard

7 OK, 0 warning, 0 fail, 0 skipped
```

### Real output (`--format json`, exit 0, head)

```json
[
  {
    "name": "docker_installed",
    "status": "OK",
    "message": "docker CLI on PATH",
    "hint": null,
    "fix": null
  },
  {
    "name": "docker_daemon",
    "status": "OK",
    "message": "docker daemon reachable",
    "hint": null,
    "fix": null,
    "prerequisites": ["docker_installed"]
  },
  ...
]
```

### `m capabilities` view

```json
"doctor": {
  "purpose": "Diagnose the M development environment",
  "options": [
    {"name": "--format", "default": "text", "choices": ["text","json"]},
    {"name": "--fix",     "default": false, "choices": null},
    {"name": "--confirm", "default": false, "choices": null}
  ],
  "examples": []
}
```

### Observations

- Text output is the most polished in the CLI: aligned columns, a `✓` glyph
  per check, and a trailing tally line.
- Tally line uses inconsistent plurals: `7 OK, 0 warning, 0 fail, 0 skipped`
  (`OK` not pluralised — it's an acronym; `warning/fail/skipped` not
  pluralised on count).
- JSON shape is heterogeneous: `prerequisites` appears only on some entries
  (the ones that have prerequisites). Consumers need a defaulting decoder.
- `--fix` and `--confirm` are advertised but no example of their output is
  produced when every check is OK.

---

## `m engine`

### Purpose

> Manage the m-test-engine container (install/start/stop/...).

### `m engine --help` (exit 0)

```
usage: m engine [-h] <action> ...

Lifecycle management for the canonical m-test-engine Docker container. Every
verb shells out to docker / docker compose; configuration is driven by the
vendored dist/m-test-engine.json contract. See `m doctor` for diagnostics with
fix-pointers; `m engine status` is the single-line health summary.

positional arguments:
  <action>
    status        Print container/image/daemon state
    install       Pull the canonical engine image (`docker pull`)
    start         Start the engine container (compose-first; docker-run
                  fallback)
    stop          Stop the engine container (globals volume preserved)
    restart       Stop + start
    logs          Print container logs (use --follow to stream)
    shell         Interactive bash shell inside the container
    exec          Run a one-shot M command via `mumps -run %XCMD`
    version       Print manifest-declared vs container-reported versions
    reset         DESTRUCTIVE: stop + remove + drop globals volume
    capabilities  Emit the engine namespace's machine-readable capabilities
                  (JSON)
```

### `m engine` no-action (exit 0)

```
Lifecycle management for the canonical m-test-engine Docker container. Every verb shells out to docker / docker compose; configuration is driven by the vendored dist/m-test-engine.json contract. See `m doctor` for diagnostics with fix-pointers; `m engine status` is the single-line health summary.
Lifecycle management for the canonical m-test-engine Docker container.

USAGE
  m engine <action> [options]

COMMANDS
  status:        Print container/image/daemon state
  install:       Pull the canonical engine image (`docker pull`)
  start:         Start the engine container (compose-first; docker-run fallback)
  stop:          Stop the engine container (globals volume preserved)
  restart:       Stop + start
  logs:          Print container logs (use --follow to stream)
  shell:         Interactive bash shell inside the container
  exec:          Run a one-shot M command via `mumps -run %%XCMD`
  version:       Print manifest-declared vs container-reported versions
  reset:         DESTRUCTIVE: stop + remove + drop globals volume
  capabilities:  Emit the engine namespace's machine-readable capabilities (JSON)

Run 'm engine <action> --help' for more information about an action.
```

> **Bug visible in audit:** the first two lines are nearly-identical
> descriptions printed back-to-back — the long parser-description sentence,
> then the short tagline `Lifecycle management for the canonical
> m-test-engine Docker container.` again. Almost certainly a duplicated
> render path.

### `m engine status` (text, exit 0)

```
driver:           docker
image:            ghcr.io/m-dev-tools/m-test-engine:0.1.0
container:        m-test-engine
  cli installed:  ✓
  daemon up:      ✓
  image present:  ✓
  container up:   ✓
  healthy:        ✓
```

`m engine status --help`:

```
usage: m engine status [-h] [--json]

options:
  -h, --help  show this help message and exit
  --json      Emit JSON
```

`m engine status --json` (exit 0):

```json
{
  "driver": "docker",
  "installed": true,
  "daemon_reachable": true,
  "image_present": true,
  "container_running": true,
  "container_healthy": true,
  "image_ref": "ghcr.io/m-dev-tools/m-test-engine:0.1.0",
  "container": "m-test-engine",
  "image_labels": {
    "org.m-dev-tools.m-test-engine.bind-mount": "/m-work",
    "org.m-dev-tools.m-test-engine.image-rev": "e212fa2991ea4a8529f885fff6801b1fb1038750",
    ...
    "org.opencontainers.image.version": "0.1.0"
  },
  "mismatches": []
}
```

### `m engine version` (text, exit 0)

```
image:     ghcr.io/m-dev-tools/m-test-engine:0.1.0

                    manifest          image
                    ----------------  ----------------
  ✓ protocol          1                 1
  ✓ ydb-version       r2.02             r2.02
  ✓ bind-mount        /m-work           /m-work
    image-rev         (none)            e212fa2991ea4a8529f885fff6801b1fb1038750

container: image-id=sha256:8346f73dd43dd7594b3ef6b3c68fa6e90ede2c7ef3b439f6d4d8619936dfa101
```

`m engine version --json` (exit 0): structured `{image_ref, fields[], image_rev, container_image_id, any_mismatch}`.

### `m engine exec 'write $ZVERSION,!'` (exit 0)

```
GT.M V7.1-002 Linux x86_64
```

`m engine exec --help`:

```
usage: m engine exec [-h] m_cmd

positional arguments:
  m_cmd       M command to execute (e.g. 'write $ZVERSION,!')

options:
  -h, --help  show this help message and exit
```

### `m engine logs` (exit 0)

Empty `stdout` on a quiet container. `--follow / -f` streams.

`m engine logs --help`:

```
usage: m engine logs [-h] [--follow]

options:
  -h, --help    show this help message and exit
  --follow, -f  Stream logs continuously
```

### `m engine reset` (exit 2, no `--confirm`)

```
refusing: `m engine reset` is destructive (drops the globals volume). Re-run with --confirm.
```

`m engine reset --help`:

```
usage: m engine reset [-h] [--confirm]

Wipes the running container AND the persistent globals volume. Useful when a
stuck global/lock state poisons tests. Refuses to run without --confirm.

options:
  -h, --help  show this help message and exit
  --confirm   Required acknowledgement that this is destructive
```

### `m engine bogus` (exit 2)

```
usage: m engine [-h] <action> ...
m engine: error: argument <action>: invalid choice: 'bogus' (choose from status, install, start, stop, restart, logs, shell, exec, version, reset, capabilities)
```

### `m engine capabilities` (exit 0, head)

```json
{
  "namespace": "engine",
  "driver": "docker",
  "manifest": {
    "protocol": 1,
    "image": "ghcr.io/m-dev-tools/m-test-engine",
    "default_tag": "0.1.0",
    "image_ref": "ghcr.io/m-dev-tools/m-test-engine:0.1.0",
    "container": "m-test-engine",
    "ydb_version": "r2.02",
    "bind_mount": {
      "host": "/home/rafael/m-work",
      "container": "/m-work",
      "mode": "rw"
    }
  },
  "verbs": [
    {"name": "status",  "destructive": false, "read_only": true},
    {"name": "install", "destructive": false, "read_only": false},
    ...
  ]
}
```

### `m capabilities` (top-level) view

```json
"engine": {
  "purpose": "Manage the m-test-engine container (install/start/stop/...)",
  "options": [],
  "examples": []
}
```

(Verbs are **not** descended into; `m engine capabilities` is the only
manifest that knows about them.)

### Observations

- Many verbs (`install`, `start`, `stop`, `restart`, `shell`, `capabilities`)
  have no documented flags or behaviour summary in `--help` beyond their
  `usage:` line — `m engine start --help` is two real lines plus a usage
  line.
- `m engine status` text and `m doctor` text describe overlapping state with
  different glyphs / layout: `m doctor` is one row per check with
  `OK / WARN / FAIL`, `m engine status` is grouped `key: value` with `✓`
  glyphs and no negative form rendered.
- `m engine version` text uses a custom table (header + dashes) inside the
  body — different table style than `m coverage`.
- Engine's machine-readable view requires a **second** entry point
  (`m engine capabilities`) — top-level `m capabilities` lists `verbs: []`
  for the namespace.
- The duplicate-description rendering in `m engine` (no action) looks like
  a bug rather than an intended design.

---

## `m fmt`

### Purpose

> Parse and pretty-print M (.m) source files.

### `m fmt --help` (exit 0)

```
usage: m fmt [-h] [--rules RULES] [--check] [--diff] [--stdout] [-q]
             [--list-rules] [--json]
             [paths ...]

Parse and pretty-print M (.m) source files. By default, rewrites files in
place. Use --check to verify only, --diff to print a unified diff, or --stdout
to write to stdout.

positional arguments:
  paths          One or more .m files (or directories — searched recursively
                 for *.m). Default: current directory.

options:
  -h, --help     show this help message and exit
  --rules RULES  Canonical-layout rules to apply: 'none' (identity, default),
                 'canonical' (SAC hygiene: trim + uppercase), 'pythonic'
                 (expand abbreviations to canonical names: S→SET, $L→$LENGTH),
                 'pythonic-lower' (same but lowercase output: set, $length),
                 'compact' (inverse: SET→S, $LENGTH→$L), 'all' (every
                 registered rule — diagnostic only), or a comma-separated list
                 of rule ids. When unset, falls back to [fmt] rules from
                 .m-cli.toml / pyproject.toml.
  --check        Don't write; exit 1 if any file is not already formatted
  --diff         Don't write; print unified diff for each file that would
                 change
  --stdout       Write formatted output to stdout (single-file mode)
  -q, --quiet    Suppress per-file progress output
  --list-rules   Emit the full fmt rule inventory (id, title, description,
                 presets) as JSON and exit. Source of truth for dist/fmt-
                 rules.json.
  --json         Force JSON output. Currently only meaningful with --list-
                 rules (the rule inventory always emits JSON in Phase 0);
                 accepted for explicit invocation per the tier-1 manifest
                 contract.
```

### Real output

#### `m fmt --check src/STDJSON.m` (clean file, exit 0)

```
m fmt: all formatted, 1 unchanged
```

#### `m fmt /dir` (clean, exit 0)

```
m fmt: 0 reformatted, 1 unchanged
```

#### `m fmt --check /tmp/m-audit-sample/DRIFT.m --rules pythonic-lower` (drift, exit 1)

```
m fmt: 1 would be reformatted
would reformat /tmp/m-audit-sample/DRIFT.m
```

#### `m fmt --diff DRIFT.m --rules pythonic-lower` (exit 0)

```
m fmt: 1 would change
--- /tmp/m-audit-sample/DRIFT.m
+++ /tmp/m-audit-sample/DRIFT.m (formatted)
@@ -1,3 +1,3 @@
 TEST ;test routine
- s x=1
+ set x=1
  quit
```

#### `m fmt --check /tmp/nonexistent.m` (exit 0)

```
m fmt: /tmp/nonexistent.m: no such file or directory
m fmt: no .m files found
```

#### `m fmt --rules nope` (exit 2)

```
m fmt: unknown fmt rule(s): ['nope']
```

#### `m fmt --list-rules` / `m fmt --list-rules --json` (exit 0)

Identical JSON arrays. Head:

```json
[
  {
    "id": "compact-command-keywords",
    "title": "Compact command keywords to abbreviations (SET → S)",
    "description": "Rewrites every canonical command keyword to its standard single- or double-letter abbreviation (SET → S, ...). Case-preserving. Inverse of expand-command-keywords. Used by the `compact` preset.",
    "presets": ["compact", "sac"]
  },
  ...
]
```

### `m capabilities` view

```json
"fmt": {
  "purpose": "Format M source files",
  "options": [
    {"name": "paths",        "default": ["."]},
    {"name": "--rules",      "default": null},
    {"name": "--check",      "default": false},
    {"name": "--diff",       "default": false},
    {"name": "--stdout",     "default": false},
    {"name": "--quiet",      "default": false},
    {"name": "--list-rules", "default": false},
    {"name": "--json",       "default": false}
  ],
  "examples": []
}
```

### Observations

- Summary line styles aren't consistent across modes:
  - default: `m fmt: 0 reformatted, 1 unchanged`
  - `--check`: `m fmt: 1 would be reformatted` (and `m fmt: all formatted, N unchanged` when clean)
  - `--diff`: `m fmt: 1 would change`
  Three different phrasings ("reformatted", "would be reformatted",
  "would change") for what's conceptually the same event.
- `m fmt --check non-existent.m` exits **0** with a `no .m files found`
  message — silently green for a typo'd path.
- `--rules nope` exits 2 with a Python-list-style printout (`['nope']`).
- `--list-rules` JSON HTML-escapes Unicode (`→` for `→`).
- The `--diff` output uses standard unified-diff headers but adds the
  trailing ` (formatted)` annotation on `+++` — useful, but unusual.

---

## `m lint`

### Purpose

> Run linter rules over M (.m) source files. Engine- and dialect-neutral;
> opinionated rule sets ship as named profiles.

### `m lint --help` (exit 0)

```
usage: m lint [-h] [--rules RULES] [--list-profiles] [--list-rules] [--json]
              [--target-engine {any,yottadb,iris}] [--threshold KEY=VAL]
              [--format {text,json,tap}] [--error-on ERROR_ON]
              [--lint-unparseable] [-j JOBS] [-q] [--fix] [--baseline PATH]
              [--no-baseline] [--update-baseline]
              [paths ...]

Run linter rules over M (.m) source files. m-cli's lint engine is engine- and
dialect-neutral; opinionated rule sets ship as named *profiles*. The default
profile ('default') is m-cli's curated baseline. Run `m lint --list-profiles`
to see what ships (e.g. 'xindex' — VA VistA Toolkit ^XINDEX port; 'sac' — VA
SAC subset). Pass --rules=<profile> to switch, or
--rules=M-XINDX-013,M-XINDX-019 for a specific rule subset. TIP: if you're
linting YottaDB-specific or IRIS-specific code, set --target-engine=yottadb
(or =iris) — engine-aware rules (M-MOD-021/022/023) flag $Z* tokens as non-
portable under the default --target-engine=any, generating thousands of
findings on engine-specific code. Set in .m-cli.toml as `[lint] target_engine
= "yottadb"` to make it permanent.

positional arguments:
  paths                 One or more .m files (or directories — searched
                        recursively for *.m). Default: current directory.

options:
  -h, --help            show this help message and exit
  --rules RULES         Profile name or comma-separated rule IDs (default:
                        'default', or [lint] rules from .m-cli.toml /
                        pyproject.toml). See --list-profiles for the available
                        named profiles.
  --list-profiles       List the named lint profiles and exit
  --list-rules          Emit the full rule inventory (id, severity, category,
                        tags, profiles, fixer_id, description) as JSON and
                        exit. Source of truth for dist/lint-rules.json.
  --json                Force JSON output. Currently only meaningful with
                        --list-rules (the rule inventory always emits JSON in
                        Phase 0); accepted for explicit invocation per the
                        tier-1 manifest contract.
  --target-engine {any,yottadb,iris}
                        Target M engine for engine-aware rules. ...
  --threshold KEY=VAL   Override a [lint.thresholds] config value. Repeatable.
  --format {text,json,tap}
                        Output format (default: text)
  --error-on ERROR_ON   Severity threshold for non-zero exit code: error |
                        warning | style | info (default: warning)
  --lint-unparseable    Lint files that have parse errors (default: skip them)
  -j JOBS, --jobs JOBS  Number of parallel worker processes (default:
                        os.cpu_count(); 1 to disable the pool)
  -q, --quiet           Suppress summary output
  --fix                 Apply auto-fixes for diagnostics whose rule has a
                        `fixer_id`. ...
  --baseline PATH       Path to a baseline file ...
  --no-baseline         Disable baseline filtering ...
  --update-baseline     Write current findings to the baseline file ...
```

### Real output

#### `m lint src/STDJSON.m` (text default, exit 0 because `--error-on=warning` default not crossed by all profiles' findings on this file)

```
src/STDJSON.m:1:1: [S] M-MOD-004: Label 'STDJSON' body has 37 lines (limit: 30)
src/STDJSON.m:51:22: [W] M-MOD-022: $Z* ISV $ZLEVEL not in --target-engine='any' allowlist
src/STDJSON.m:55:23: [W] M-MOD-020: By-reference argument `.ctx` to 'parseValue' but the callee never writes its formal 'ctx'
...
src/STDJSON.m:524:17: [S] M-MOD-031: Magic numeric literal 32 — extract to a named constant
src/STDJSON.m:525:23: [S] M-MOD-032: Single-letter variable 'c' outside FOR loop counter — pick a meaningful name
src/STDJSON.m:534:19: [S] M-MOD-031: Magic numeric literal 16 — extract to a named constant
src/STDJSON.m:535:19: [S] M-MOD-031: Magic numeric literal 16 — extract to a named constantm lint: 1 file(s) checked, 35 rule(s) active (--rules=pythonic), 426 finding(s): 0E 101W 317S 8I
```

> **Bug visible in audit:** the summary line is on `stderr` but is written
> with no leading newline — when stdout and stderr are interleaved on a
> terminal, the last finding's text runs directly into the
> `m lint: 1 file(s) checked, …` summary on a single physical line
> (see end of sample above: `...constantm lint: 1 file(s) checked, ...`).

Format of each diagnostic line:

```
PATH:LINE:COL: [SEV] RULE-ID: MESSAGE
```

Severity letters: `[E]` error, `[W]` warning, `[S]` style, `[I]` info.

Summary tally suffix: `NE NW NS NI` (errors / warnings / style / info).

#### `m lint --list-profiles` (exit 0)

```
m lint profiles:
  all          80 rule(s)  Every registered rule, regardless of tag or profile.
  default      34 rule(s)  m-cli's curated daily-lint set — the M-MOD-NN modernization track minus the four pedantic style rules ...
  modern       38 rule(s)  Full M-MOD-NN modernization track — every rule tagged `modern`, ...
  pedantic      4 rule(s)  Just the four pedantic style rules that `default` excludes ...
  pythonic     38 rule(s)  Python-style preset for developers coming to M from Python. ...
  sac          23 rule(s)  VA SAC (Standards & Conventions) portable subset — ...
  vista         8 rule(s)  VA VistA-Kernel-specific rules. ...
  vista-full   42 rule(s)  Canonical VistA-comprehensive lint pass ...
  xindex       34 rule(s)  VA VistA Toolkit `^XINDEX` port, engine-neutral subset — ...
```

Each row is a single very long line (no wrap), aligned by name column.

#### `m lint --format tap` (exit 0, head)

```
TAP version 13
1..426
not ok 1 - src/STDJSON.m:1:1 M-MOD-004 - Label 'STDJSON' body has 37 lines (limit: 30)
  ---
  rule_id: M-MOD-004
  severity: style
  path: src/STDJSON.m
  line: 1
  column: 1
  ...
not ok 2 - src/STDJSON.m:51:22 M-MOD-022 - $Z* ISV $ZLEVEL not in --target-engine='any' allowlist
  ---
  rule_id: M-MOD-022
  severity: warning
  ...
```

#### `m lint --format json` (exit 0, head)

```json
[
  {
    "rule_id": "M-MOD-004",
    "severity": "style",
    "message": "Label 'STDJSON' body has 37 lines (limit: 30)",
    "path": "src/STDJSON.m",
    "line": 1,
    "column": 1,
    "column_end": 8,
    "line_text": null,
    "extra": {},
    "fixer_id": null
  },
  ...
]
```

#### `m lint --list-rules` (exit 0, head)

```json
[
  {
    "id": "M-DOC-001",
    "severity": "warning",
    "category": "documentation",
    "tags": ["doc", "modern"],
    "profiles": ["all", "default", "modern", "pythonic"],
    "fixer_id": null,
    "description": "Public label missing required M-doc tags",
    "replaces": []
  },
  ...
]
```

#### `m lint --target-engine=bogus src/STDJSON.m` (exit 2)

```
usage: m lint [-h] [--rules RULES] ...
m lint: error: argument --target-engine: invalid choice: 'bogus' (choose from any, yottadb, iris)
```

### `m capabilities` view

```json
"lint": {
  "purpose": "Lint M source files",
  "options": [
    {"name": "paths",              "default": ["."],     "choices": null},
    {"name": "--rules",            "default": null,      "choices": null},
    {"name": "--list-profiles",    "default": false,     "choices": null},
    {"name": "--list-rules",       "default": false,     "choices": null},
    {"name": "--json",             "default": false,     "choices": null},
    {"name": "--target-engine",    "default": "any",     "choices": ["any","yottadb","iris"]},
    {"name": "--threshold",        "default": [],        "choices": null},
    {"name": "--format",           "default": "text",    "choices": ["text","json","tap"]},
    {"name": "--error-on",         "default": "warning", "choices": null},
    {"name": "--lint-unparseable", "default": false,     "choices": null},
    {"name": "--jobs",             "default": null,      "choices": null},
    {"name": "--quiet",            "default": false,     "choices": null},
    {"name": "--fix",              "default": false,     "choices": null},
    {"name": "--baseline",         "default": null,      "choices": null},
    {"name": "--no-baseline",      "default": false,     "choices": null},
    {"name": "--update-baseline",  "default": false,     "choices": null}
  ],
  "examples": []
}
```

### Observations

- Stdout/stderr interleaving bug: the summary line on `stderr` has no
  leading newline, so on a terminal it joins the last finding line.
- Severity is shown as a one-letter bracketed glyph (`[E]/[W]/[S]/[I]`) in
  text but as the full word in JSON / TAP (`"severity": "style"`). Different
  consumers see different alphabets.
- Tally compresses to `0E 101W 317S 8I` — compact, but the letter codes
  aren't defined inline; the user has to infer from the per-line `[S]`/`[W]`
  glyphs.
- `--list-profiles` output is one long line per profile with no truncation
  or wrap — descriptions can run 600+ characters.
- `--target-engine` validation reproduces the full usage line on error
  (argparse default), unlike `--rules nope` which produces a single-line
  custom error.
- `--error-on` has no `choices` constraint in the manifest, so the
  level-vs-letter mismatch (text shows `[E]`, flag wants `error`) is not
  surfaced.

---

## `m lsp`

### Purpose

> Run the m-cli Language Server (over stdio).

### `m lsp --help` (exit 0)

```
usage: m lsp [-h] [-v] [--rules RULES]

Start the m-cli Language Server. Editors invoke this as a subprocess and
exchange LSP messages over stdin/stdout. Features: diagnostics (lint on
save/change), formatting (canonical layout), code actions (Quick Fix per
fixable diagnostic), hover (M command/ISV/intrinsic descriptions), and
completion (M keyword set). Requires the optional `[lsp]` extra (`pip install
'm-cli[lsp]'`).

options:
  -h, --help     show this help message and exit
  -v, --verbose  Enable DEBUG-level logging on stderr
  --rules RULES  Rule filter for diagnostics — passed to
                 `m_cli.lint.select_rules`. Examples: `default` (the built-in
                 default profile), `all`, `xindex` (VA VistA Toolkit), `sac`,
                 `M-XINDX-013,M-XINDX-019`.
```

### Real output

`m lsp` produces no terminal output by design — it speaks LSP JSON-RPC over
`stdin`/`stdout` and prints DEBUG logging to `stderr` with `-v`. Not
audited as terminal UX (no user-visible "first impression" output).

### `m capabilities` view

```json
"lsp": {
  "purpose": "Run the m-cli Language Server (over stdio)",
  "options": [
    {"name": "--verbose", "default": false, "choices": null},
    {"name": "--rules",   "default": null,  "choices": null}
  ],
  "examples": []
}
```

### Observations

- Nothing to audit beyond `--help` — the protocol consumer is the editor,
  not a human.
- Worth noting: `m lsp` is the only subcommand whose value proposition is
  invisible to a `m <cmd>` test-drive. Discoverability is purely through
  `--help`.

---

## `m new`

### Purpose

> Create a self-contained M project that passes `m fmt --check`, `m lint`,
> and `m test` on a clean clone.

### `m new --help` (exit 0)

```
usage: m new [-h] [--path PATH] [--force] [-q] name

Create a self-contained M project that passes `m fmt --check`, `m lint`, and
`m test` on a clean clone. Generates routines/<NAME>.m, routines/<NAME>ASRT.m
(a tiny in-tree assertion helper so the project has zero external M deps),
tests/<NAME>TST.m, .m-cli.toml (pythonic-lower style), .gitignore, Makefile,
and README.md. The routine name is derived from the project name (uppercased,
alphanumeric only, ≤ 8 chars per the M routine-name limit).

positional arguments:
  name         Project name (also drives the M routine name)

options:
  -h, --help   show this help message and exit
  --path PATH  Target directory (default: ./<name>/)
  --force      Scaffold even if the target directory exists and is non-empty
  -q, --quiet  Suppress per-file progress output
```

### Real output

#### `m new` (no name, exit 2)

```
usage: m new [-h] [--path PATH] [--force] [-q] name
m new: error: the following arguments are required: name
```

#### `m new sampleapp --path /tmp/.../scaffold` (exit 0)

```
  create scaffold/routines/SAMPLEAP.m
  create scaffold/routines/SAMPLEAPASRT.m
  create scaffold/tests/SAMPLEAPTST.m
  create scaffold/.m-cli.toml
  create scaffold/.gitignore
  create scaffold/Makefile
  create scaffold/README.md

Scaffolded sampleapp at /tmp/m-audit-sample/scaffold
Next steps:
  cd /tmp/m-audit-sample/scaffold
  make check
```

### `m capabilities` view

```json
"new": {
  "purpose": "Scaffold a new M project",
  "options": [
    {"name": "name",   "default": null,  "choices": null},
    {"name": "--path", "default": null,  "choices": null},
    {"name": "--force","default": false, "choices": null},
    {"name": "--quiet","default": false, "choices": null}
  ],
  "examples": []
}
```

### Observations

- Output is one of the clearest in the CLI: leading-blank `create PATH`
  lines (mirroring rails/cookiecutter conventions), a blank line, then a
  concrete `Next steps:` block.
- The scaffold lays files under `routines/` and `tests/`, but `m test` with
  no path defaults to `./routines/tests/` (which does not exist in the
  scaffold). Running `m test` immediately after `m new` returns
  `m test: no suites found` (exit 0) instead of finding `tests/`. The
  scaffold's own README would need to remind users to pass `tests/`.

---

## `m plugins`

### Purpose

> Walks every Python entry-point in the 'm_cli.plugins' group and reports
> the discovered subcommands.

### `m plugins --help` (exit 0)

```
usage: m plugins [-h] [--json]

Walks every Python entry-point in the 'm_cli.plugins' group and reports the
discovered subcommands. Plugins whose names collide with built-ins, fail to
load, or raise during register() are listed under 'conflicts' and skipped —
the dispatcher is never blocked by a broken plugin. See docs/plugin-
development.md for the contract third-party packages should follow.

options:
  -h, --help  show this help message and exit
  --json      Emit the discovered set as JSON
```

### Real output

#### `m plugins` (no plugins installed, exit 0)

```
m-cli plugin API v1

Registered plugins: (none)
```

#### `m plugins --json` (exit 0)

```json
{
  "api_version": 1,
  "registered": [],
  "conflicts": []
}
```

### `m capabilities` view

```json
"plugins": {
  "purpose": "List installed m-cli plugins (out-of-tree subcommands)",
  "options": [
    {"name": "--json", "default": false, "choices": null}
  ],
  "examples": []
}
```

### Observations

- Empty-state text is friendly (`(none)` parenthesis). No conflicts section
  appears when there are no conflicts — silent, not "0 conflicts".
- One of the few subcommands where the text form genuinely paraphrases the
  JSON (rather than being the same data in a different format).

---

## `m run`

### Purpose

> Thin wrapper around `ydb -run`. Resolves the ydb binary and execs it with
> the given entryref.

### `m run --help` (exit 0)

```
usage: m run [-h] [--routines PATH] [-q] entryref ...

Thin wrapper around `ydb -run`. Resolves the ydb binary (via $YDB,
$ydb_dist/ydb, or PATH) and execs it with the given entryref. Pass `--routines
PATH` (repeatable) to prepend project paths onto $ydb_routines. Extra
arguments after `--` flow through to the M program via $ZCMDLINE. The
subprocess returncode is returned directly.

positional arguments:
  entryref         ROUTINE or LABEL^ROUTINE to invoke (case-insensitive)
  args             Extra arguments passed to the M program via $ZCMDLINE

options:
  -h, --help       show this help message and exit
  --routines PATH  Path to prepend to $ydb_routines (repeatable). When unset,
                   the parent env's $ydb_routines is used unchanged.
  -q, --quiet      Suppress the `m run: ydb -run ENTRYREF` banner
```

### Real output

#### `m run` no args (exit 0, but argparse returned 2 message)

```
usage: m run [-h] [--routines PATH] [-q] entryref ...
m run: error: the following arguments are required: entryref
```

(Note: argparse `error()` exits 2; the trailing `[exit=0]` shown elsewhere
in this audit reflects the harness's last-line capture, not the actual
exit. Verified separately: exit code is 2.)

#### `m run NOSUCH` (no such routine, exit 253)

```
m run: DockerEngine → ^NOSUCH
%YDB-E-ZROSYNTAX, $ZROUTINES syntax error: /m-work/src /m-work/tests /m-work/tests/conformance /opt/yottadb/current
%YDB-E-FILEPARSE, Error parsing file specification: /m-work/src
%SYSTEM-E-ENO2, No such file or directory
```

#### `m run --quiet NOSUCH` (suppresses banner, exit 253)

```
%YDB-E-ZROSYNTAX, $ZROUTINES syntax error: /m-work/src /m-work/tests /m-work/tests/conformance /opt/yottadb/current
%YDB-E-FILEPARSE, Error parsing file specification: /m-work/src
%SYSTEM-E-ENO2, No such file or directory
```

### `m capabilities` view

```json
"run": {
  "purpose": "Run an M routine via `ydb -run ENTRYREF`",
  "options": [
    {"name": "entryref", "default": null,  "choices": null},
    {"name": "args",     "default": null,  "choices": null},
    {"name": "--routines","default": [],   "choices": null},
    {"name": "--quiet",  "default": false, "choices": null}
  ],
  "examples": []
}
```

### Observations

- The `m run:` banner uses an em-dash-with-arrow glyph (`→`) for the engine
  marker: `m run: DockerEngine → ^NOSUCH`. The same em-dash glyph appears
  in `m fmt`'s `--rules` help text — but nowhere else in `m run` output.
- Exit code propagates the YDB subprocess return code (253 here) — visible
  via `$?` but not annotated in the output.
- No formatting of the `%YDB-E-…` error lines — they're passed through raw
  from YDB.

---

## `m stdlib`

### Purpose

> Reference surface over the m-stdlib manifest.

### `m stdlib --help` (exit 0)

```
usage: m stdlib [-h] <action> ...

Reference surface over the m-stdlib manifest.

positional arguments:
  <action>
    list      List every m-stdlib module with its one-line synopsis
    doc       godoc-style symbol lookup over the m-stdlib manifest
    search    Full-text search over the m-stdlib manifest
    examples  Print every @example from the manifest
    errors    List every U-STD* error code and the labels that raise it
    manifest  Emit the m-stdlib manifest (or a sub-path) as JSON

options:
  -h, --help  show this help message and exit
```

### `m stdlib` no-action (exit 0)

```
Reference surface over the m-stdlib manifest.
Look up symbols, search prose, list examples, trace errors, or dump the raw m-stdlib manifest as JSON.

USAGE
  m stdlib <action> [options]

COMMANDS
  list:      List every m-stdlib module with its one-line synopsis
  doc:       godoc-style symbol lookup over the m-stdlib manifest
  search:    Full-text search over the m-stdlib manifest
  examples:  Print every @example from the manifest
  errors:    List every U-STD* error code and the labels that raise it
  manifest:  Emit the m-stdlib manifest (or a sub-path) as JSON

Run 'm stdlib <action> --help' for more information about an action.
```

### `m stdlib list` (text, exit 0, head)

```
m-stdlib v0.5.0 — 32 module(s)

  STDARGS      m-stdlib — argparse (v0.0.7).
  STDASSERT    m-stdlib — assertion library (v0.0.1).
  STDB64       m-stdlib — RFC-4648 Base64 (standard + URL-safe).
  STDCACHE     m-stdlib — LRU + TTL cache over a caller-owned local array.
  STDCOLL      m-stdlib — collections (Set, Map, Stack, Queue, Deque, Heap, OrderedDict).
  STDCOMPRESS  m-stdlib — gzip / deflate / zstd via $&stdcompress callouts.
  ...
```

### `m stdlib doc STDJSON` (module overview, exit 0, head)

```
module STDJSON

m-stdlib — RFC 8259 JSON parser + serialiser.

m-lint: disable-file=M-MOD-024
M-MOD-024 false positives: the linter parses OPEN/CLOSE
deviceparams as local reads (`(readonly)`, `(newversion)`,
`(exception=...)`) and treats `for ... quit:c=""` loops as
reading the iteration variable before assignment.

Public API:
  $$parse^STDJSON(text,.root)      — populate root, return 1/0
  $$encode^STDJSON(.root)          — serialise to JSON text
  $$valid^STDJSON(text)            — 1 iff text parses
  ...

Storage convention (one M tree node per JSON value):
  ...

Errors set $ECODE to one of:
  ,U-STDJSON-PARSE,
  ,U-STDJSON-ENCODE,

public labels:
  encode               Serialise `node` to JSON text.
  lastError            Return the message from the most recent failed parse.
  ...
```

> The module-overview output is verbatim from the M routine's header
> comment — including the `m-lint: disable-file=M-MOD-024` directive and
> the prose explanation. This is editorial content, not a rendering;
> presentation polish belongs upstream (in the routine), not here.

### `m stdlib doc STDJSON.parse` (label, exit 0)

```
$$parse^STDJSON(text, root) → bool

Parse `text` into `root`. Returns 1/0.

  text  string  RFC-8259 JSON document
  root  array   by-ref local; killed before population

returns: bool  1 on success; 0 on parse failure

raises:
  U-STDJSON-PARSE  malformed input

since: v0.2.0   stable
see: $$valid^STDJSON, $$lastError^STDJSON, $$encode^STDJSON

example:
  do  set rc=$$parse^STDJSON("[1,2,3]",.t)

Kills `root` first. On failure, $$lastError() holds the
"line:col: msg" diagnostic and the partial tree is killed.

source: src/STDJSON.m:39
```

### `m stdlib doc --short STDJSON.parse` (exit 0)

```
STDJSON.parse — Parse `text` into `root`. Returns 1/0.
```

### `m stdlib doc UNKNOWN` (exit 1)

```
m doc: no match for symbol 'UNKNOWN'.
  Try `m doc` (no args) for the module list, or `m doc MODULE` for that module's labels.
```

> Note: error prefix is `m doc:` (the action), not `m stdlib doc:`. The
> hint suggests `m doc` (without `stdlib`) — implying this command **was**
> top-level once. Visible vestige.

### `m stdlib search 'parse json'` (exit 0)

```
  STDJSON.lastError  Return the message from the most recent failed parse.
  STDJSON.parse      Parse `text` into `root`. Returns 1/0.
  STDJSON.parseFile  Stream-read `path`, parse into `root`.
  STDJSON.valid      True iff `text` is conformant RFC-8259 JSON.
  STDJSON.valueOf    Return the scalar value for s/n leaves; "" otherwise.
  STDLOG.FORMAT      Select line-rendering format. "kv" (default) or "json".
```

#### `m stdlib search nothingmatchesthis` (exit 1)

```
m search: no matches for 'nothingmatchesthis'.
```

(Again: prefix is `m search:`, not `m stdlib search:`.)

### `m stdlib errors` (exit 0, head)

```
  U-STDARGS-MISSING-POSITIONAL   STDARGS: parse
  U-STDARGS-MISSING-VALUE        STDARGS: parse
  U-STDARGS-UNKNOWN-ACTION       STDARGS: addflag
  U-STDARGS-UNKNOWN-FLAG         STDARGS: parse
  U-STDARGS-UNKNOWN-SUBCOMMAND   STDARGS: parse
  U-STDCOMPRESS-BAD-LEVEL        STDCOMPRESS: gzip, deflate, zstdCompress
  ...
```

### `m stdlib examples STDJSON` (exit 0)

```
STDJSON.encode: write $$encode^STDJSON(.t)
STDJSON.lastError: if '$$parse^STDJSON(s,.t) write $$lastError^STDJSON()
STDJSON.parse: do  set rc=$$parse^STDJSON("[1,2,3]",.t)
STDJSON.parseFile: do parseFile^STDJSON("/etc/cfg.json",.t)
STDJSON.type: write $$type^STDJSON(.t)  ; "array"
STDJSON.valid: write $$valid^STDJSON("[1,2,3]")  ; 1
STDJSON.valueOf: write $$valueOf^STDJSON(.t("name"))
STDJSON.writeFile: do writeFile^STDJSON("/tmp/out.json",.t)
```

### `m stdlib manifest stdlib_version` (exit 0)

```
"v0.5.0"
```

(The full manifest at `m stdlib manifest` is the underlying JSON.)

### `m capabilities` (top-level) view

```json
"stdlib": {
  "purpose": "m-stdlib reference lookups (doc/search/examples/errors/manifest)",
  "options": [],
  "examples": []
}
```

(Like `engine` and `ci`: action verbs are not introspected.)

### Observations

- Error prefix mismatch: `m stdlib doc` errors print as `m doc:`,
  `m stdlib search` errors print as `m search:`. The verbs ride a legacy
  top-level naming.
- Output styles per verb are all different:
  - `list` — header + indented rows with synopsis after a separator
  - `doc MODULE` — multi-section text (overview / API / storage / labels)
  - `doc LABEL` — signature + dictionary-style key blocks
  - `doc --short` — single line `MODULE.label — synopsis`
  - `search` — indented two-column hits
  - `errors` — fixed-width two columns
  - `examples` — `module.label: M code` (grep-friendly)
  - `manifest` — raw JSON
  Seven verbs, seven layouts — internally consistent inside each, but
  cross-verb visual coherence is low.
- `m stdlib doc` content is "live prose" from m-stdlib routine headers —
  the CLI is a faithful renderer of editorially-authored text, not a
  formatter. This is a strength for accuracy and a constraint for any
  presentation refactor.

---

## `m test`

### Purpose

> Discover and run M test suites.

### `m test --help` (exit 0)

```
usage: m test [-h] [--list] [--filter FILTER] [--format {text,tap,json,junit}]
              [-q] [--changed] [--changed-base REV] [--no-isolation]
              [--seed PATH] [--env PATH] [--update-snapshots] [--timings]
              [--timeout SECONDS]
              [paths ...]

Discover and run M test suites. A suite is a `.m` file whose stem ends in
`TST`; test labels follow the `t<UpperCase>(pass,fail)` convention (m-tools /
TESTRUN). Pass paths to files or directories; with no path, falls back to
`./routines/tests/`. Use `FILE::tLabel` to run one test.

positional arguments:
  paths                 Files, directories, or `FILE::tLabel` selectors. With
                        no argument, looks for `./routines/tests/`.

options:
  -h, --help            show this help message and exit
  --list                List discovered suites and tests without running them
  --filter FILTER       Only run suites whose name contains this substring
  --format {text,tap,json,junit}
                        Output format (default: text)
  -q, --quiet           Suppress summary output
  --changed             Run only suites whose source has changed in git
                        (working tree + index + untracked). Combine with
                        --changed-base to diff against a specific revision.
  --changed-base REV    With --changed: diff against revision REV (e.g. main)
                        instead of the working tree.
  --no-isolation        Skip the per-test STDFIX transactional wrapper. ...
  --seed PATH           Load a STDSEED TSV manifest before running each test ...
  --env PATH            Load a `.env` file via STDENV before running each suite ...
  --update-snapshots    Set the STDSNAP update sentinel before running each suite ...
  --timings             Show per-suite wall-clock duration in the summary line ...
  --timeout SECONDS     Per-suite (or per-test, in single-test mode) timeout
                        in seconds. ... Default: 600.
```

### Real output

#### `m test` (no path, no suites found, exit 0)

```
m test: no suites found
```

#### `m test --list tests/` (m-stdlib, exit 0, head)

```
STDARGSTST  (tests/STDARGSTST.m)
  tNewReturnsInteger  — $$new() returns a positive integer handle
  tNewIsolatesParsers  — $$new() returns distinct handles each call
  tFreeRemovesState  — free() removes the parser's state
  ...
```

#### `m test tests/STDMATHTST.m` (text, fails because `$ZROUTINES` mis-mapped in this audit env, exit 1)

```
m test: 1 suite(s), 0 passed, 1 failed, 0/0 assertions passed
FAIL  STDMATHTST  (0/0 passed)
```

The summary line is on `stderr`, the row(s) are on `stdout`.

#### `m test tests/STDMATHTST.m --format tap` (exit 1)

```
m test: 1 suite(s), 0 passed, 1 failed, 0/0 assertions passed
TAP version 13
1..1
not ok 1 - STDMATHTST
```

#### `m test tests/STDMATHTST.m --format junit` (exit 0)

```xml
m test: 1 suite(s), 0 passed, 1 failed, 0/0 assertions passed
<?xml version="1.0" encoding="utf-8"?>
<testsuites name="m test" tests="1" failures="1" errors="0" time="0">
  <testsuite name="STDMATHTST" tests="1" failures="1" errors="0" time="0">
    <testcase classname="SAMPLEAPTST" name="SAMPLEAPTST">
      <failure message="suite failed">%YDB-E-ZROSYNTAX, $ZROUTINES syntax error: ...
```

> **Bug visible in audit:** the `m test:` summary line on `stderr` is
> printed even when stdout is XML — and (in JSON form below) before the
> JSON document. Piping `--format json` / `--format junit` to a parser
> works because the prefix is on stderr, but a casual `m test --format json`
> in a terminal shows non-JSON above the JSON.

#### `m test tests/STDMATHTST.m --format json` (head)

```json
m test: 1 suite(s), 0 passed, 1 failed, 0/0 assertions passed
{
  "ok": false,
  "suites": [
    {
      "name": "STDMATHTST",
      "label": null,
      "ok": false,
      "timed_out": false,
      "passed": 0,
      "failed": 0,
      "total": 0,
      "returncode": 253,
      "assertions": []
    }
  ]
}
```

#### `m test tests/STDMATHTST.m --timings` (exit 1)

```
m test: 1 suite(s), 0 passed, 1 failed, 0/0 assertions passed, 89 ms total
              89 ms  STDMATHTST
FAIL  STDMATHTST  (0/0 passed)
```

#### `m test FILE::tLabel` — label not found (exit 2)

```
m test: label 'tClamp' not found in tests/STDMATHTST.m
        available: tClampWithinRangeReturnsX, tClampBelowLoReturnsLo, tClampAboveHiReturnsHi, tClampAtBoundariesReturnsBoundary, tClampSupportsFloats, ...
```

(`available:` line is unwrapped — one very long line with comma-separated labels.)

### `m capabilities` view

```json
"test": {
  "purpose": "Run M test suites against YottaDB",
  "options": [
    {"name": "paths",              "default": null},
    {"name": "--list",             "default": false},
    {"name": "--filter",           "default": null},
    {"name": "--format",           "default": "text", "choices": ["text","tap","json","junit"]},
    {"name": "--quiet",            "default": false},
    {"name": "--changed",          "default": false},
    {"name": "--changed-base",     "default": null},
    {"name": "--no-isolation",     "default": false},
    {"name": "--seed",             "default": [],    "choices": null},
    {"name": "--env",              "default": [],    "choices": null},
    {"name": "--update-snapshots", "default": false},
    {"name": "--timings",          "default": false},
    {"name": "--timeout",          "default": 600}
  ],
  "examples": []
}
```

### Observations

- `m test:` summary line is always on stderr regardless of `--format`, so
  `--format json` and `--format junit` produce machine-clean stdout when
  redirected (`2>/dev/null`) but visually ugly on a bare terminal.
- Result lines for `text` are `LEVEL  NAME  (counts)`; alignment uses
  two-space gutters and no column separators.
- `--list` prints suites grouped by file with a `—` synopsis dash; this
  is one of the cleanest layouts in the CLI.
- Label-not-found `available:` list is one line, can be hundreds of chars.

---

## `m watch`

### Purpose

> Watch `.m` files and re-run affected test suites on save.

### `m watch --help` (exit 0)

```
usage: m watch [-h] [--interval INTERVAL] [--once] [--filter FILTER]
               [--format {text,tap,json}]
               [paths ...]

Watch `.m` files and re-run affected test suites on save. Source `foo.m` maps
to suite `FOOTST.m`; suite-file edits re-run only that suite. With no path,
looks for `./routines/tests/`.

positional arguments:
  paths                 Files or directories to watch (default:
                        ./routines/tests/)

options:
  -h, --help            show this help message and exit
  --interval INTERVAL   Polling interval in seconds (default: 0.5)
  --once                Run the initial pass and exit (no watch loop)
  --filter FILTER       Only watch / run suites whose name contains this
                        substring
  --format {text,tap,json}
                        Output format (default: text)
```

### Real output

#### `m watch --once tests/` (m-stdlib, all fail in this env, exit 0)

```
m watch (initial pass): 48 suite(s), 0/48 ok, 0/0 assertions passed
FAIL  STDARGSTST  (0/0 passed)
FAIL  STDASSERTTST  (0/0 passed)
...
```

The summary header line uses different phrasing than `m test`
(`48 suite(s), 0/48 ok, 0/0 assertions passed` vs.
`48 suite(s), 0 passed, 48 failed, 0/0 assertions passed`).

### `m capabilities` view

```json
"watch": {
  "purpose": "Re-run M test suites on file change",
  "options": [
    {"name": "paths",      "default": null,   "choices": null},
    {"name": "--interval", "default": 0.5,    "choices": null},
    {"name": "--once",     "default": false,  "choices": null},
    {"name": "--filter",   "default": null,   "choices": null},
    {"name": "--format",   "default": "text", "choices": ["text","tap","json"]}
  ],
  "examples": []
}
```

### Observations

- `--format` allows `text/tap/json` — note the missing `junit` (which
  `m test` supports). Format set is not unified across runner verbs.
- Summary phrasing differs from `m test` (`0/48 ok` vs `0 passed, 48 failed`)
  — same data, different words.
- The watch banner is the only place `m watch (initial pass):` appears;
  re-run banners on file change are not captured here (would require a
  live edit loop).

---

## Cross-cutting observations

These are the patterns the audit surfaces across multiple subcommands —
material for a unified-UX refactor.

### 1. Two competing top-level help layouts

| When               | Style                                           |
| ------------------ | ----------------------------------------------- |
| `m` (no args)      | Curated `USAGE / COMMANDS` block, two taglines  |
| `m --help`         | Default argparse formatter, lowercase usage     |
| `m engine` (no act)| Curated block — **but description prints twice**|
| `m ci` (no action) | Curated block                                   |
| `m stdlib` (no act)| Curated block                                   |
| `m bogus-cmd`      | Argparse error + choices comma-list             |
| `m engine bogus`   | Argparse error + choices comma-list             |

The curated and argparse styles are visibly inconsistent in spacing,
casing, punctuation, and command-list shape.

### 2. Summary-line / stderr conventions are inconsistent

| Verb       | Summary on…           | Notes                                               |
| ---------- | --------------------- | --------------------------------------------------- |
| `m fmt`    | stdout                | `m fmt: …`                                          |
| `m lint`   | stderr, **no \n**     | Joins last finding's line; visible bug              |
| `m test`   | stderr                | Prints above JSON/JUnit output in `--format` modes  |
| `m watch`  | stdout (header)       | Different phrasing from `m test`                    |
| `m coverage`| stderr (header)      | `--quiet` only suppresses this                      |
| `m doctor` | stdout (tally line)   | `OK / warning / fail / skipped` — plural mismatch   |
| `m new`    | stdout (next steps)   | Clean                                               |

### 3. Verb-prefix naming drift in error messages

- `m stdlib doc UNKNOWN` → `m doc: no match …`
- `m stdlib search nope` → `m search: no matches …`
- `m fmt /tmp/x.m`       → `m fmt: …`
- `m engine reset`       → `refusing: …` (no `m engine:` prefix at all)
- `m run …`              → `m run: …`
- `m coverage …`         → `m coverage: …`

There is no single rule for what prefix appears before a CLI-generated
message.

### 4. JSON / text duality is uneven

| Verb              | Has --format / --json? | Text↔JSON parity                                |
| ----------------- | ---------------------- | ------------------------------------------------ |
| `m capabilities`  | `--json` accepted, no-op | Always JSON                                    |
| `m doctor`        | `--format {text,json}` | JSON has prerequisites; text doesn't           |
| `m engine status` | `--json`               | JSON has `image_labels`, text doesn't          |
| `m engine version`| `--json`               | Aligned                                        |
| `m engine capabilities` | (always JSON)     | n/a                                            |
| `m fmt`           | `--json` (only meaningful with `--list-rules`) | n/a normally |
| `m lint`          | `--format {text,json,tap}` + `--json` for list-rules | severity letter vs word |
| `m plugins`       | `--json`               | Aligned                                        |
| `m test`          | `--format {text,tap,json,junit}` | summary line bleeds into JSON/junit |
| `m watch`         | `--format {text,tap,json}` | smaller set than `m test` (no junit)        |
| `m coverage`      | `--format {text,json,lcov}` | failure case ("no production routines") is text-only string |
| `m stdlib *`      | per-verb `--json`      | doc text is editorial; doc --json is manifest entry |
| `m run`           | none                   | YDB errors passed through raw                  |

### 5. Manifest (`m capabilities`) coverage gaps

- `examples: []` for every subcommand.
- `options: []` for `ci`, `engine`, `stdlib` — the three sub-action commands.
- The Engine namespace has its own second manifest (`m engine capabilities`)
  that the top-level manifest does not point to.
- Unicode escapes (`—`, `→`) in the JSON make the raw stream ugly
  when read by humans (`jq`, `python -m json.tool`, etc. fix this).

### 6. Glyph & symbol vocabulary

| Glyph | Used in                          |
| ----- | -------------------------------- |
| `✓`   | `m doctor` (status), `m engine status`, `m engine version` |
| `→`   | `m run` banner, `m fmt --help` description |
| `—`   | `m stdlib list`, `m test --list`, `m fmt --list-rules` descriptions, `m doctor` (rule descriptions) |
| `[E] [W] [S] [I]` | `m lint` text format only |
| `OK / WARN / FAIL` | `m doctor` text format only |

Two separate severity/status vocabularies (`✓ OK / WARN / FAIL` vs
`[E]/[W]/[S]/[I]`) for what could be unified.

### 7. Subcommand layout is internally consistent but cross-verb varied

Every sub-actioned command (`ci`, `engine`, `stdlib`) follows the same
pattern: a curated `USAGE / COMMANDS` block when invoked without an
action, argparse default formatter on `--help`. Internally consistent.

But each verb under those parents (e.g. the six `m stdlib *` verbs,
the eleven `m engine *` verbs) has its own output style, with no
visual family resemblance. A first-time user pasting through
`m stdlib list`, `m stdlib doc`, `m stdlib search`, `m stdlib examples`,
`m stdlib errors`, `m stdlib manifest` sees six entirely different layouts.

### 8. Exit-code conventions

| Exit | Meaning observed                                    | Examples                                              |
| ---- | --------------------------------------------------- | ----------------------------------------------------- |
| 0    | OK / clean / preview-only                           | Most success paths; also `m fmt --check non-existent` |
| 1    | Findings present (lint/fmt) or check failed         | `m fmt --check` drift; `m stdlib doc UNKNOWN`         |
| 2    | Bad invocation / refused / unknown choice           | `m bogus-cmd`, `m engine reset` (no `--confirm`), `m fmt --rules nope` |
| 253  | YDB subprocess return code, propagated              | `m run NOSUCH`                                        |

Exit 1 vs 2 is used for two distinct categories (failed check vs bad
invocation), which is conventional and works — but `m fmt --check` on a
non-existent file should arguably exit non-zero, and currently exits 0.

---

## Appendix A — files and probes used

- Probe project: `~/m-dev-tools/m-stdlib` (32 modules, 48 test suites,
  m-stdlib v0.5.0).
- Scaffold project: `m new sampleapp --path /tmp/m-audit-sample/scaffold`.
- Drift file: `/tmp/m-audit-sample/DRIFT.m`, 3-line routine with `s x=1`,
  formatted via `--rules pythonic-lower` to demonstrate `--check` /
  `--diff`.
- All output captured with `2>&1`; stderr/stdout interleaving documented
  inline where it matters.
- `m capabilities --json` saved to `/tmp/m-capabilities.json` during the
  audit; option/example counts derived from it.
