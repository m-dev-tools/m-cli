---
created: 2026-04-27
last_modified: 2026-05-07
revisions: 2
doc_type: [GUIDE, INTEGRATION]
---

# Pre-commit integration

`m-cli` ships a [pre-commit](https://pre-commit.com) hook scaffold so
downstream M (MUMPS) projects can gate every commit on `m fmt --check`
and `m lint --error-on=fatal` without writing any boilerplate.

Three hooks are exported from `.pre-commit-hooks.yaml`:

| Hook id         | What it does                                                         |
|-----------------|----------------------------------------------------------------------|
| `m-fmt-check`   | Fails the commit if any staged `*.m` file is not already formatted   |
| `m-fmt`         | Rewrites staged `*.m` files in place to their canonical form         |
| `m-lint`        | Fails the commit on **fatal** lint findings (e.g. call-to-missing-label) |

Pick `m-fmt-check` *or* `m-fmt` — not both. The first blocks unformatted
commits; the second auto-fixes them.

## Integration: use a system-installed `m`

Install `m-cli` locally (clone + venv) so the `m` binary is on each
developer's `PATH`, then wire pre-commit to it via `language: system`:

```yaml
repos:
  - repo: local
    hooks:
      - id: m-fmt-check
        name: m fmt --check
        entry: m fmt --check
        language: system
        files: \.m$
        types: [file]

      - id: m-lint
        name: m lint --error-on=fatal
        entry: m lint --error-on=fatal
        language: system
        files: \.m$
        types: [file]
```

`language: system` tells pre-commit to skip venv creation and assume
`m` is on `PATH`.

## Tightening the lint gate

`m-lint` defaults to `--error-on=fatal` so it only blocks commits on
real bugs. To also fail on warnings (the SAC violations and the noisier
XINDEX rules), override the entry:

```yaml
      - id: m-lint
        name: m lint --error-on=warning
        entry: m lint --error-on=warning
        language: system
        files: \.m$
        types: [file]
```

## Running ad-hoc

You don't need pre-commit to use these checks:

```bash
m fmt --check Routines/         # exit 1 if anything would change
m lint --error-on=fatal Routines/  # exit 1 on fatal findings only
```

Both commands are designed to be CI-friendly: stable JSON / TAP /
text output, exit codes per [the standard convention][exit-codes], no
network dependencies.

[exit-codes]: https://github.com/<owner>/m-cli/blob/main/CLAUDE.md
