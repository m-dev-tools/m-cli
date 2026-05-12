---
created: 2026-05-11
last_modified: 2026-05-11
revisions: 1
doc_type: [PLAN, SUMMARY]
lifecycle: active
owner: rmrich5
title: "CLI UX remediation — review summary for m-cli"
---

# CLI UX remediation — review summary

> **Companion to** [`cli-ux-conventions-guide.md`](cli-ux-conventions-guide.md) (the rules)
> and [`m-cli/docs/plans/cli-ux-conventions-remediation.md`](https://github.com/m-dev-tools/m-cli/blob/main/docs/plans/cli-ux-conventions-remediation.md) (the full plan).
>
> **Purpose.** A one-page summary of the proposed work — so the owner can
> review options and answer open questions **before** any code is written.
> All decision points are surfaced explicitly in §4.

## 1. What's wrong now (one-paragraph)

Bare `m` and bare `m ci` exit 2 with an argparse stderr error instead of
the guide's stdout overview. `m ci init` (no flags) silently *writes*
`.github/workflows/m-ci.yml` — a mutation as the bare-invocation default.
`m --help` repeats the 18-subcommand list three times (synopsis +
description + positional-args block), and the description sentence is
already stale (names 6 of 18). Thirteen of eighteen leaves print
root-level usage on unknown-flag instead of their own usage. Six leaves
return exit code 2 for domain failures (missing manifest, missing ydb)
where the guide reserves 2 for usage errors.

## 2. Findings at a glance

| Severity | Count | Examples |
|---|---|---|
| **P0** — hard guide violation | 2 | bare `m` exits 2 stderr; bare `m ci` exits 2 stderr |
| **P1** — guide violation or anti-pattern | 3 | `m ci init` mutates on bare; unknown-flag → root usage; domain errors use exit 2 |
| **P2** — UX quality / soft violation | 3 | `m --help` triplicates the list; bare fmt/lint/coverage error instead of defaulting to cwd; `m capabilities` dumps 630 lines on bare |
| **P3** — record-and-move-on | 2 | `m lsp` filter/REPL divergence (intentional); per-subcommand `--version` (out of scope) |
| **Compliant today** | — | `--help` / `-h` aliasing; help on stdout; `m new` / `m run` missing-arg errors; `m doctor` / `m plugins` inspection defaults |

Empirical evidence: probe TSV at `/tmp/m-cli-cli-ux-probe.tsv`, raw
stdout/stderr captures in `/tmp/m-cli-cli-ux-logs/`.

## 3. Proposed changes (concise list)

| # | Change | Touches |
|---|---|---|
| 4.1 | Add `print_overview(parser, common)` helper (short overview per §5.1) | new helper |
| 4.2 | Drop `required=True` on root + `m ci` subparsers; bind overview to each | `cli.py:57`, `cli.py:580` |
| 4.3 | Two-pass parsing so unknown flags hit the *subparser's* `error()` | `main()` in `cli.py` |
| 4.4 | `m ci init` gated behind `--write`; bare = preview to stdout, exit 0 | `cli.py` ci_init block + `ci/cli.py` |
| 4.5 | `fail_domain(msg) → 1` helper; replace `parser.error` in build + 5 doc-family leaves | new helper + 6 sites |
| 4.6 | cwd default for `fmt`/`lint`/`coverage`; "no suites found = exit 0" for `test`/`watch` | 5 leaf CLIs |
| 4.7 | `m capabilities` bare prints short overview; `--json` (or non-TTY stdout) emits JSON | `capabilities/cli.py` |
| 4.8 | One-line LSP-divergence note in CLAUDE.md citing the guide | `CLAUDE.md` |
| 4.9 | `metavar="<command>"` on subparsers; trim root `description` to one sentence | `cli.py:42-50`, `:57`, `:580` |

All changes localized to `src/m_cli/cli.py` and a handful of leaf CLIs. No
public-API breakage. Each change ships with contract tests pinned in a
new `tests/test_cli_ux_contract.py`.

## 4. Open questions — decide before implementation

These are the editorial calls. The plan picks a default for each; the
owner should confirm or override.

### Q1 — `m ci init` opt-in mechanism

**Plan default:** `--write` opt-in. Bare `m ci init` prints the planned path + the workflow YAML to stdout and exits 0 (preview mode). `--write` performs the existing mutation.

**Alternative:** bare `m ci init` prints a one-liner `will write .github/workflows/m-ci.yml — re-run with --write to confirm` (no YAML preview).

Decision: **preview body, or short notice?**

### Q2 — Unknown-flag routing implementation

**Plan default:** two-pass parsing (`parse_known_args` to identify the subcommand, then dispatch to the resolved subparser).

**Alternative:** `exit_on_error=False` + manual try/except around the parse.

Both yield the same user-visible result. The first is contained in `main()`; the second touches every parser construction.

Decision: **two-pass, or exit_on_error?**

### Q3 — cwd default for fmt / lint / coverage

**Plan default:** when `paths` is empty, set `paths = [Path(".")]` rather than erroring.

**Alternative:** keep the current "no .m files found" exit-2 behavior on the grounds that explicit > implicit.

Decision: **cwd-default, or keep explicit?**

### Q4 — `m test` / `m watch` when nothing is discoverable

**Plan default:** exit **0** with `m test: no suites found` to stdout — "nothing to do" is not a failure.

**Alternative:** exit **1** (domain failure) or stay at **2** (usage).

Decision: **0 / 1 / 2 for nothing-to-test?**

### Q5 — `m capabilities` bare mode

**Plan default:** short overview text on bare; JSON only with `--json` or when stdout is not a TTY (matches `cargo metadata` style).

**Alternative A:** keep current behavior (always JSON; `--json` redundant).
**Alternative B:** introduce a `--summary`/`--inventory` text mode and keep JSON as the bare default.

Decision: **short-overview-by-default, A, or B?**

### Q6 — `--help` synopsis approach

**Plan default:** `metavar="<command>"` collapses the wrapping `{fmt,lint,…,capabilities}` set to `<command>`. The positional-args block remains the canonical place users see every subcommand with a one-liner.

**Alternative:** custom `formatter_class` that suppresses the synopsis subcommand set entirely and lays out the help section-by-section (more work, more control).

Decision: **metavar only, or custom formatter?**

### Q7 — Sequencing

**Plan default:** seven sequenced PRs (one per change-set), in the order listed in §3 above. PR 1 bundles §4.1 + §4.2 + §4.9 because they all touch the root parser.

**Alternative:** fewer, larger PRs (e.g., one for all dispatcher changes, one for all leaf changes, one for help-output polish).

Decision: **seven small PRs, or batch?**

### Q8 — Where the implementation session lives

Per [`parallel-multi-repo-git-hygiene.md`](https://github.com/m-dev-tools/.github/blob/main/docs/dev-practices/parallel-multi-repo-git-hygiene.md),
this should be implemented in its own m-cli session (`cd ~/m-dev-tools/m-cli`),
not from the workspace root. This is just a reminder, not a question — but worth
flagging since the discovery/planning was done at the workspace root for cross-repo
cataloging.

## 5. Suggested PR order (assuming defaults above)

1. **PR 1** — §4.1 + §4.2 + §4.9 — dispatcher overview, drop `required=True`, concise synopsis + trimmed description.
2. **PR 2** — §4.4 — `m ci init` requires `--write`.
3. **PR 3** — §4.3 — subparser-scoped unknown-flag errors.
4. **PR 4** — §4.5 — exit 1 for domain errors (build + 5 doc-family).
5. **PR 5** — §4.6 — cwd defaults; "no suites found" exits 0.
6. **PR 6** — §4.7 — `m capabilities` overview / JSON split.
7. **PR 7** — §4.8 — CLAUDE.md LSP-divergence note; README pointer to the guide.

Each PR adds its slice of tests to `tests/test_cli_ux_contract.py` (created in PR 1).

## 6. What is **not** in this plan

- Migration of plugins (`m-cli-extras`) to the new conventions — separate ticket, after PR 1 lands.
- A custom argparse formatter — the `metavar` fix in §4.9 covers the visible quality problem with minimal churn.
- Per-subcommand `--version`. `m --version` covers the binary; that's the guide's intent.
- Anything in `~/m-dev-tools/m-tools/` (archived) or `~/projects/archive/`.

## 7. Verification (post-merge)

```bash
make check                                  # full CI gate (lint + mypy + cov)
pytest tests/test_cli_ux_contract.py -v     # the new contract gate
make check-manifest                         # dist/commands.json drift gate
```

Then re-run the probe (`/tmp/m-cli-cli-ux-probe.sh`) and confirm:

- Bare `m` and `m ci` exit 0 with stdout overview.
- `m --help` synopsis is one line, no triplicate.
- `m fmt --__bogus__` shows `usage: m fmt …` (not root usage).
- `m doc` (with no manifest) exits 1, not 2.
- `m ci init` (bare) does not write the workflow file.

## 8. References

- [`cli-ux-conventions-guide.md`](cli-ux-conventions-guide.md) — the rules being enforced.
- [`parallel-multi-repo-git-hygiene.md`](https://github.com/m-dev-tools/.github/blob/main/docs/dev-practices/parallel-multi-repo-git-hygiene.md) — implementation-session hygiene (in the org `.github` repo).
- [Full plan](https://github.com/m-dev-tools/m-cli/blob/main/docs/plans/cli-ux-conventions-remediation.md) (in the m-cli repo).
