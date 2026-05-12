---
created: 2026-05-11
last_modified: 2026-05-11
revisions: 1
doc_type: [RESEARCH, REFERENCE, GUIDE]
lifecycle: active
owner: rmrich5
title: "CLI UX conventions for m-dev-tools"
---

# CLI UX conventions for m-dev-tools

> *How every command-line tool in the m-dev-tools org should behave at
> every level — root, subcommand group, leaf — when invoked with no
> arguments, with `--help`, and on error. Grounded in a survey of the
> Unix and modern-CLI ecosystem.*

This document is the canonical reference for CLI ergonomics across the
org. It applies to `m-cli` today (`m`, `m engine`, `m doc`, `m ci`, `m
fmt`, `m lint`, `m test`, …) and to any future tool that ships a
command-line entry point from any tier-2 repo (`m-tools`, `m-stdlib`'s
helper scripts, `m-test-engine` CLIs, etc.). Tools that diverge from
this guide need an explicit reason recorded in their own repo's
documentation.

## TL;DR

1. **Bare invocation of a dispatcher prints a short overview**
   (synopsis + common subcommands + pointer to `--help`), not a wall
   of help and not nothing. Apply the rule *recursively* — `m` and `m
   engine` behave the same way.
2. **`-h` / `--help` is the only way to get the full reference**, goes
   to **stdout**, exits **0**.
3. **Errors (unknown subcommand, missing required arg) print a short
   usage line to stderr**, exit non-zero, and point the user at
   `--help`.
4. **Leaf commands** (`m fmt`, `m lint`) either operate on a sensible
   default (cwd, stdin) or print a short usage error — pick one rule
   per tool and apply it consistently across leaves.
5. **Side-effectful actions never run as the default for a bare
   dispatcher invocation.** Listing / inspection defaults are fine
   (`git remote`); mutations are not.

The detailed rationale, the survey behind these rules, and the
Python-argparse implementation pattern follow.

---

## 1. The taxonomy: dispatcher vs leaf

Every node in a CLI's command tree is one of two shapes:

- **Dispatcher** — a node whose only job is to route to children. Has
  no useful work to do on its own. Examples: `m` (root), `m engine`,
  `m doc`, `m ci`, `git`, `git stash` (in some configurations), `gh
  pr`, `kubectl config`, `docker image`.

- **Leaf** — a node that actually performs work. Takes its own flags
  and positional args; may consume input from stdin or the cwd.
  Examples: `m fmt`, `m lint`, `m test`, `git commit`, `gh pr create`,
  `kubectl apply`, `docker run`.

The bare-invocation rule depends on which shape the node is:

| Shape | Bare invocation behavior |
|---|---|
| Dispatcher | Print short overview of children + pointer to `--help`. Exit 0 or 1 (pick one, stay consistent). |
| Leaf with sensible default | Run with the default (e.g. `m lint` lints cwd; `cat` reads stdin). Exit 0 on success. |
| Leaf with required args | Print short usage to stderr + pointer to `--help`. Exit non-zero. |

A node is a *dispatcher* if and only if it has child subcommands and
no useful standalone behavior. Adding children to a former leaf
upgrades it to a dispatcher; the bare-invocation rule changes
accordingly.

---

## 2. Survey: how the popular CLIs actually behave

### Bare-invocation behavior of the root command

| Tool | Bare `tool` behavior | Exit |
|---|---|---|
| `git` | Short usage + common commands list to stderr | 1 |
| `gh` | Help overview to stdout | 0 |
| `kubectl` | Help overview to stdout | 0 |
| `docker` | Help overview to stdout | 0 |
| `cargo` | Help overview to stdout | 0 |
| `aws` | Usage error to stderr, hint to use `aws help` | 252 |
| `npm` | Help overview to stdout | 0 |
| `cp`, `mv`, `ln` | `missing file operand` + short usage to stderr | 1 |
| `grep` | Short usage to stderr | 2 |
| `ssh` | Short usage to stderr | 255 |
| `curl` | `try 'curl --help'` hint to stderr | 2 |
| `tar` | Short usage + hint to `--help` to stderr | 2 |
| `find` (GNU) | Implicit `find .` — defaults to cwd | 0 |
| `cat`, `sort`, `wc`, `tr`, `sed`, `awk` | Read stdin (filter mode) | 0 |
| `python`, `node`, `psql`, `redis-cli`, `sqlite3`, `gdb` | Enter REPL | 0 |

Three families emerge:

1. **Dispatchers** (`git`, `gh`, `kubectl`, `docker`, `cargo`, `npm`,
   `aws`) print an overview or a usage error.
2. **Leaf tools with required args** (`cp`, `mv`, `grep`, `ssh`,
   `curl`, `tar`) print a short usage to stderr and exit non-zero.
3. **Filter / REPL tools** (`cat`, `sort`, `python`) do something
   useful — read stdin or enter interactive mode.

The dispatcher family is what `m` and every `m <group>` belongs to.
The relevant peers are `git`, `gh`, `kubectl`, `docker`, `cargo`.

### Bare-invocation behavior of subcommand groups

| Tool | Bare `tool group` behavior |
|---|---|
| `git remote` | Lists remotes (leaf with inspection default) |
| `git stash` | Runs `git stash push` (leaf with mutating default — controversial) |
| `gh pr` | Help overview for `pr` subcommands |
| `gh repo` | Help overview for `repo` subcommands |
| `kubectl config` | Help overview for `config` subcommands |
| `docker image` | Help overview for `image` subcommands |
| `aws s3` | Usage error + available commands |

The modern consensus (`gh`, `kubectl`, `docker`) is: **dispatcher
groups behave like the root command** — overview of their children,
recursively. `git`'s mixed behavior reflects 20 years of organic
growth and is not the model to copy.

### Best-practice references consulted

- [**clig.dev** — Command Line Interface Guidelines](https://clig.dev/)
  ("Display help text when passed no options, the `-h` flag, or the
  `--help` flag.")
- [**POSIX Utility Conventions**](https://pubs.opengroup.org/onlinepubs/9699919799/basedefs/V1_chap12.html)
  (exit-code semantics, argument parsing).
- [**GNU Coding Standards § Command-Line Interfaces**](https://www.gnu.org/prep/standards/standards.html#Command_002dLine-Interfaces)
  (long-option naming, `--help` and `--version` conventions).
- [**12 Factor CLI Apps** (Jeff Dickey)](https://medium.com/@jdxcode/12-factor-cli-apps-dd3c227a0e46)
  (UX patterns for modern multi-command CLIs).
- Reference implementations: `git`, `gh`, `kubectl`, `docker`,
  `cargo`, `npm`.

---

## 3. Canonical rules for m-dev-tools CLIs

The rules below apply to every CLI shipped from this org. They are
written for `m-cli` but extend to any tier-2 repo that ships a binary.

### 3.1 Bare invocation of a dispatcher

When a user runs `m`, `m engine`, `m doc`, `m ci`, or any future
dispatcher group with no further arguments:

- **Print a short overview to stdout.** Synopsis line + a list of the
  most common subcommands with one-line descriptions + a pointer to
  `<command> --help` for the full reference.
- **Do not print the full `--help` output.** That's hundreds of lines
  for a tool like `m`; reserve it for explicit `-h`/`--help`.
- **Do not silently exit 0 with no output.** The default argparse
  behavior in Python ≤ 3.6 is to do exactly this; it must be
  overridden.
- **Exit code: 0 or 1 — pick one and apply consistently.** The org
  default is **0** (matching `gh`/`kubectl`/`docker`/`cargo`/`npm`),
  on the grounds that the user did not make an error; they just
  invoked the command without picking a subcommand, and the overview
  is the documented response.
- **Apply the rule recursively.** Every dispatcher level — root,
  group, sub-group — uses the same template. Inconsistency between
  levels is the most common smell in evolved CLIs.

### 3.2 Bare invocation of a leaf

When a user runs a leaf command like `m fmt`, `m lint`, `m test` with
no further arguments:

- **Prefer a sensible default over a usage error** when the default
  is unambiguous and non-destructive. `m lint` linting cwd is the
  obvious default. `m fmt --check` checking cwd is the obvious
  default. This matches `find . → find` and is friendlier than an
  error.
- **When no sensible default exists**, print a short usage line to
  stderr and exit non-zero. `m run` (which executes a routine) has no
  obvious default — error is correct.
- **Never mutate state silently as a default.** `m fmt` (without
  `--check`) rewriting cwd on bare invocation would be surprising and
  destructive; the safe default is `--check`-style read-only behavior
  unless the user opts in explicitly.

### 3.3 `--help` and `-h`

- **`--help` and `-h` are equivalent** and always supported.
- **Output goes to stdout** (so users can `m fmt --help | less`).
- **Exit code: 0.** Help is not an error.
- **Content is the full reference for that node.** Synopsis, full
  flag list with descriptions, examples where relevant, list of
  subcommands if dispatcher.

### 3.4 Unknown subcommand / unknown flag

- **Print a short error to stderr** identifying what was unknown.
- **Point the user at `<command> --help`** for the valid set.
- **Exit non-zero** — conventionally `2` (matches POSIX getopt and
  most major CLIs).
- **Do not auto-suggest** unless the suggestion algorithm is
  high-quality (`gh`'s "did you mean...?" is good; many homegrown
  implementations are noisy).

### 3.5 `--version`

- **Every CLI supports `--version`.** Output is a single line:
  `<name> <semver>` (e.g. `m 0.42.1`). Optionally a second line with
  build/commit info.
- **Exit code: 0.** Output to stdout.

### 3.6 Output destination summary

| Output | Destination | Exit |
|---|---|---|
| `--help` content | stdout | 0 |
| `--version` content | stdout | 0 |
| Dispatcher overview (bare invocation) | stdout | 0 |
| Normal command output | stdout | 0 on success |
| Errors, usage hints, warnings | stderr | non-zero |
| Progress / log output (interactive) | stderr | (irrelevant; in-flight) |

This separation lets users pipe real output to other tools without
contamination: `m capabilities --json | jq …` must not mix help text
into stdout.

### 3.7 Exit-code vocabulary

Standardize across all org CLIs:

| Code | Meaning |
|---|---|
| 0 | Success (or help requested) |
| 1 | General error (operation failed for a domain reason) |
| 2 | Usage error (unknown flag/subcommand, malformed args) |
| Other | Domain-specific. Document in the CLI's own reference. |

`m lint --error-on=error` exits non-zero when findings exceed the
threshold; that's a domain signal, separate from this taxonomy, and
the CLI's own docs spell out the codes.

---

## 4. Anti-patterns to avoid

1. **Different behavior at different dispatcher depths.** `m` prints
   help but `m engine` errors out. Users build a mental model from
   the root level and expect it to hold; breaking it at depth is
   confusing.
2. **Dumping full `--help` on bare invocation.** Walls of text on
   accidental invocation. Argparse's `print_help()` is hundreds of
   lines for a tool like `m`. Use a short overview instead.
3. **Silent no-op.** `m engine` prints nothing and exits 0. Users
   think the command is broken. This is the Python ≤ 3.6 argparse
   default and must be overridden.
4. **Mutating state as a bare-invocation default.** `m fmt` (bare)
   rewriting cwd, `git stash` (bare) pushing a stash. Inspection-only
   defaults like `git remote` (lists remotes) are fine; mutations are
   not.
5. **Help to stderr, errors to stdout.** Breaks `m foo --help |
   less`; breaks `m foo 2>/dev/null` for error filtering.
6. **Exit 0 on error.** Breaks shell scripting (`m foo && next-step`
   fires even when `m foo` failed).
7. **`--help` that differs from `-h`.** Surprises users who expect
   them to be aliases.
8. **Inconsistent help formatting across siblings.** All subcommands
   of one dispatcher should use the same section headers (Usage,
   Options, Examples) in the same order.

---

## 5. Implementation pattern (Python / argparse)

Python's `argparse` is the dominant choice in this org (`m-cli` is
the primary user, and any new tier-2 CLI defaults to it). Two
specific configurations are needed to land the conventions above.

### 5.1 Dispatcher overview on bare invocation

```python
def _print_overview(parser: argparse.ArgumentParser) -> int:
    # Short overview: synopsis + common subcommands + pointer to --help.
    # NOT parser.print_help() — that dumps the full reference.
    sys.stdout.write(
        f"Usage: {parser.prog} <command> [options]\n\n"
        "Common commands:\n"
        "  fmt        Format M source\n"
        "  lint       Lint M source\n"
        "  test       Run tests\n"
        "  ...\n\n"
        f"Run '{parser.prog} <command> --help' for more information.\n"
    )
    return 0

# In the dispatcher node:
parser.set_defaults(func=lambda args: _print_overview(parser))
```

The `set_defaults(func=…)` pattern fires when no subcommand is
selected. Applied at every dispatcher level (root `m`, group `m
engine`, group `m doc`, …), it gives the recursive consistency
described in §3.1.

### 5.2 Unknown subcommand → exit 2

```python
subparsers = parser.add_subparsers(dest="command")
# Don't set required=True — argparse's error message is ugly.
# Handle the "no subcommand" case via set_defaults above, and
# handle "unknown subcommand" via argparse's built-in error path,
# which already exits 2.
```

### 5.3 Stdout vs stderr

`argparse`'s `parser.error()` writes to stderr and exits 2 —
correct. `parser.print_help()` writes to stdout — correct. Custom
overview functions must follow the same separation (§3.6).

### 5.4 Testing the contract

Each CLI's test suite should pin the conventions for that CLI:

```python
def test_bare_invocation_prints_overview():
    result = run_cli([])  # no args
    assert result.exit_code == 0
    assert "Usage:" in result.stdout
    assert "--help" in result.stdout
    assert result.stderr == ""

def test_help_goes_to_stdout():
    result = run_cli(["--help"])
    assert result.exit_code == 0
    assert len(result.stdout) > 0
    assert result.stderr == ""

def test_unknown_subcommand_errors():
    result = run_cli(["bogus-command"])
    assert result.exit_code != 0
    assert result.stdout == ""
    assert "bogus-command" in result.stderr
```

These three tests are the minimum CLI-contract gate; recommend
adding them to every tier-2 CLI's test suite.

---

## 6. Applying this guide

- **New CLI in a tier-2 repo** — adopt these conventions from day
  one. Add the three contract tests (§5.4) to the repo's test
  suite. Reference this doc from the repo's CLAUDE.md / README.
- **Existing CLI that diverges** — file an issue noting the
  divergence and the cost of converging. Do not refactor opportunistically
  inside a feature PR; converge on its own PR with the contract tests
  added.
- **Tool that intentionally diverges** — record the reason in the
  repo's own documentation, linking back to this doc. Examples of
  legitimate divergence: a tool whose primary mode is a REPL (would
  enter REPL on bare invocation), a filter tool (would read stdin on
  bare invocation). The taxonomy in §1 already accommodates these.

---

## 7. References

- [clig.dev — Command Line Interface Guidelines](https://clig.dev/)
- [POSIX Utility Conventions](https://pubs.opengroup.org/onlinepubs/9699919799/basedefs/V1_chap12.html)
- [GNU Coding Standards § CLI](https://www.gnu.org/prep/standards/standards.html#Command_002dLine-Interfaces)
- [12 Factor CLI Apps](https://medium.com/@jdxcode/12-factor-cli-apps-dd3c227a0e46)
- Reference implementations: `git`, `gh` (GitHub CLI), `kubectl`,
  `docker`, `cargo`, `npm`.
