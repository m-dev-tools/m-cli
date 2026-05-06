# VistA lint presets

Companion configuration for linting VistA M code with `m lint`.

## Quick start

Copy `m-cli.toml.example` to `.m-cli.toml` in the project root (or any
ancestor up to a `.git` boundary), then run:

```bash
m lint --error-on=error Packages/<Package>/Routines/
```

The example file selects:

- **profile** `vista-full` — XINDEX + VistA + SAC rules (~42 rules)
- **engine** `yottadb` — disables non-portability warnings on `$Z*`
- **`[lint.vista] kernel_locals = "default"`** — silences M-MOD-024
  false-positives on Kernel-supplied locals (`U`, `IO`, `DT`,
  `DUZ`, `%UCI`, ...)
- **`[lint.vista] trusted_routines = "default"`** — silences
  M-XINDX-007 false-positives on the canonical FileMan / Kernel /
  MailMan APIs (`^%DT`, `^DIR`, `^XLFDT`, `^XMD`, ...)

Without these allowlists, `default` profile produces ~702K findings
on the canonical 39,375-routine VistA corpus, dominated by ~487K
false-positive M-MOD-024 errors on `U` and friends. With them, the
findings drop to a usable baseline. See
`m-stdlib/docs/vista-corpus-lint-results.md` for the full
before/after numbers and rule-by-rule breakdown.

## When to use

- **Daily dev** of an existing VistA package.
- **CI gate** with `--baseline=...` — capture an "acceptable" baseline
  on first commit, fail PRs that introduce *new* findings beyond
  the baseline.
- **Review pass** of a Kernel patch — the `vista-full` profile
  catches the SAC mandates a Kernel reviewer would want flagged
  (banner format, `LOCK` / `READ` without timeout, LABEL+OFFSET
  fragility).

## When NOT to use

- **Modern non-VA M projects** — use the `default` or `pythonic`
  profiles without the `[lint.vista]` allowlists. The Kernel-locals
  list would silence real undefined-read findings on a project that
  doesn't have Kernel auto-init.
- **YottaDB libraries that ship `^%DT`** — if your project actually
  vendors the FileMan utilities into its own namespace, drop
  `trusted_routines` so M-XINDX-007 still flags genuine typos.

## Extending

Replace `"default"` with an explicit list to override:

```toml
[lint.vista]
kernel_locals = ["U", "DT", "DUZ", "MY-SITE-LOCAL"]
trusted_routines = ["%DT", "DIR", "XMD", "MY-SITE-API"]
```

An explicit list **replaces** the built-in defaults — useful when
you want only a subset, or when adding site-specific globals/APIs
that the canonical lists don't carry.
