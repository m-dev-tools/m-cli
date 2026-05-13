# Schema-First CLI Architecture for m-cli

A design proposal for a JSON-/YAML-manifest-driven m-cli where every
surface (grammar, verbs, nouns, arguments, outputs, inputs, error
codes, exit semantics) is declared in version-controlled schemas, with
the runtime dispatcher being a thin shell that consumes those schemas.

Companion to:

- [`cli-output-audit-2026-05-13.md`](cli-output-audit-2026-05-13.md)
- [`audit-m-engine-2026-05-13.md`](audit-m-engine-2026-05-13.md)
- [`audit-remediation-plan0-2026-05-13.md`](audit-remediation-plan0-2026-05-13.md)

The remediation plan's P5 phase ("subcommand registry") is the seedling
of what this document expands into a full architecture. The plan is
incremental and pragmatic; this is the long-arc, "what would the
finished thing look like" view. Read it after the remediation plan,
not instead of it.

This is a design discussion, not a finalised decision. The reader is
expected to push back on individual proposals.

---

## Table of contents

1. [What problem are we solving?](#1-what-problem-are-we-solving)
2. [Industry survey — schema-first CLIs in production](#2-industry-survey--schema-first-clis-in-production)
3. [Patterns for semantic consistency](#3-patterns-for-semantic-consistency)
4. [Vocabulary discipline — verbs, nouns, grammars](#4-vocabulary-discipline--verbs-nouns-grammars)
5. [The proposed manifest stack — five layers](#5-the-proposed-manifest-stack--five-layers)
6. [Approaches compared — pros & cons](#6-approaches-compared--pros--cons)
7. [Recommended path for m-cli](#7-recommended-path-for-m-cli)
8. [Open questions](#8-open-questions)
9. [Appendix A — concrete manifest sketch for `m engine status`](#appendix-a--concrete-manifest-sketch-for-m-engine-status)
10. [Appendix B — vocabulary tables (verbs, nouns)](#appendix-b--vocabulary-tables-verbs-nouns)

---

## 1. What problem are we solving?

The audits showed m-cli's surface drifts because there is no single
source of truth. Today the same fact — *"`m engine status` accepts
`--json`"* — lives in three places:

1. `argparse` wiring in `engine_cli.py:78`.
2. Hand-curated payload in `_cmd_capabilities` (`engine_cli.py:265-277`).
3. (Not at all) — the on-disk manifest `dist/m-test-engine.json`
   describes verbs but not their options.

When the author of a verb adds a flag, only #1 gets updated. #2 drifts.
#3 was never aware of options in the first place. The audits caught
~30 such drifts across the CLI.

The remediation plan's earlier phases (P0-P4) fix this by introducing
shared output primitives and contract tests. P5 was deferred precisely
because it's a much bigger architectural move: replacing the implicit
"argparse is the spec" with an **explicit manifest** that all surfaces
derive from.

**The question this document asks**: if we were to do P5 — adopt a
schema-first architecture wholesale — what would it look like, what
does the industry teach us, and is it worth the cost?

---

## 2. Industry survey — schema-first CLIs in production

Twelve case studies, grouped by how aggressively they commit to
schemas as source of truth. The point isn't to copy any one of them;
it's to map the design space.

### 2.1 The "schema *is* the CLI" tier — fully generated

These CLIs are generated end-to-end from a machine-readable API
specification. The CLI source code is largely a build artifact.

#### AWS CLI / botocore

- **Source of truth.** Per-service JSON files known as **service
  models** (`service-2.json` in the `botocore/data/<service>/<version>/`
  tree). Each model declares operations, request/response *shapes* (the
  schemas), error codes, paginators, waiters.
- **Grammar.** `aws <service> <operation>` maps 1:1 to a model
  operation. The CLI does no semantic invention; it parses the model
  and renders argparse equivalents at runtime.
- **What's automatic.** Help text, flags, value coercion, response
  formatting, JSON output, pagination, retry logic, shape validation
  on input.
- **What's hand-curated.** A small "customizations" layer for
  ergonomics (`aws s3 cp`, `aws s3 sync`) that intercepts before the
  generated path. Roughly 5% of the surface.
- **Surface size.** ~300 services × ~50 operations average = ~15,000
  CLI verbs. Hand-authoring is not an option at this scale.
- **Lesson for m-cli.** Schema-first scales linearly with surface
  size; at m-cli's ~50-verb scale the overhead/benefit ratio is much
  less favourable, but the pattern of "every per-verb fact has exactly
  one machine-readable home" is exactly the discipline the audits
  found missing.

#### Oracle Cloud (OCI) CLI

- **Source of truth.** OCI's REST API OpenAPI v3 spec.
- **Grammar.** Verb–noun–noun: `oci compute instance list`, `oci iam
  user create`. The middle term names the resource family; the last
  term is a canonical verb (`list`, `get`, `create`, `update`,
  `delete`).
- **Build pipeline.** Internal codegen consumes the OpenAPI spec and
  emits Python modules per service. No human writes a verb.
- **What it enforces.** Total grammar uniformity. Every resource has
  the same five base verbs unless the API explicitly forbids one.
- **Lesson for m-cli.** When verbs are autogenerated, grammar
  consistency is free. m-cli's grammar inconsistencies (`m fmt PATH`
  vs `m engine status` vs `m stdlib doc SYMBOL`) exist because each
  verb's grammar is set by a human at coding time, and there's no rule
  that says "you must pick from these patterns."

#### Stripe CLI

- **Source of truth.** Stripe's OpenAPI spec (public, in
  `stripe/openapi` repo).
- **Grammar.** Resource-oriented: `stripe customers list`, `stripe
  charges create`. Same verb set as OCI plus webhook-specific
  commands.
- **Implementation.** Go (cobra), with an autogenerated commands tree
  for each API resource. A hand-curated layer exists for `stripe
  login`, `stripe listen`, etc.
- **Lesson for m-cli.** OpenAPI gives you *resource* schemas for free
  (request/response shapes) but doesn't itself describe *CLI*
  surfaces. The CLI generator must apply conventions on top
  ("resource X with `list` operation → `<cli> X list`"). m-cli has no
  REST surface, so OpenAPI isn't directly applicable — but the
  CLI-conventions layer on top is.

### 2.2 The "manifest-driven, declarative" tier

These CLIs are not generated from an external API spec; the CLI is the
primary artifact, but its surface is declared in YAML/JSON, not in
imperative code. The runtime dispatcher reads the manifest at startup.

#### Google Cloud SDK (`gcloud`)

- **Source of truth.** A YAML "command surface" tree under
  `googlecloudsdk/surface/<group>/<command>.yaml`. Each declarative
  command is a YAML file declaring args, flags, help, examples, the
  underlying API call, output formatting, error handling.
- **Framework.** Google built **Calliope**, an internal Python CLI
  framework, specifically for this. Calliope reads each YAML and
  constructs the argparse parser, the help text, the
  Markdown-renderable documentation, and the `gcloud meta`
  introspection output from the same declaration.
- **What's enforced.**
  - Every command has examples (Calliope refuses to register a
    command with no `examples:` block in dev mode).
  - Every flag has help text (validated at registration).
  - Release tracks (`alpha` / `beta` / `GA`) are first-class — the
    same logical command can have parallel manifests across tracks,
    and the dispatcher routes by `gcloud alpha foo` / `gcloud foo`.
  - Output formats (`--format=table[…]`, `--format=json`,
    `--format=yaml`, `--format=csv`) are uniform across the entire
    CLI because they're a framework feature, not a per-command one.
- **Introspection.** `gcloud meta list-commands`, `gcloud meta
  generate-help-docs`, `gcloud meta debug` — the entire CLI surface
  is queryable as data.
- **Scale.** ~6000+ commands.
- **Lesson for m-cli.** This is the closest commercial analogue to
  what the user is proposing. The key insight is that *Calliope is
  more important than the YAML* — the framework that interprets the
  manifest is where consistency lives. A YAML schema with no
  framework underneath is just documentation.

#### Oclif (Heroku / Salesforce / npm CLI generator)

- **Source of truth.** Each command is a TypeScript file with a
  static `flags` / `args` / `description` declaration. `oclif
  manifest` walks the tree and emits `oclif.manifest.json` — a single
  JSON document describing every command, flag, and argument across
  the CLI **including plugins**.
- **Plugins.** First-class. A plugin is an npm package with its own
  oclif manifest; installing it merges its manifest into the host
  CLI's view at runtime.
- **What's in the manifest.** Command id, description, flags
  (name/char/type/required/default/options), args
  (name/required/description), examples, hidden state, plugin
  provenance. ~30 fields per command.
- **Used by.** Heroku CLI (origin), Salesforce CLI (`sf`), and the
  npm CLI generator for many internal company CLIs.
- **Lesson for m-cli.** Plugin merging works because the manifest is
  data, not code. m-cli's plugin contract (in
  `docs/plugin-development.md`) currently relies on each plugin
  calling `argparse` itself — there's no way to introspect a plugin's
  flags without loading the Python module. A manifest-first design
  would change that.

#### Azure CLI (`az`) / Knack

- **Source of truth.** Hybrid. Some Azure services have **autogenerated
  command modules** (Azure Auto-generated Commands — "aaz") derived
  from the Azure REST API specs in `azure-rest-api-specs`. Other
  modules are hand-curated.
- **Framework.** **Knack** — Microsoft's open-source Python CLI
  framework, originally built for Azure CLI. Knack provides a
  declarative command table API plus uniform `--output {json,jsonc,
  table,tsv,yaml,none}` handling across every command.
- **Configuration layering.** `az configure` writes to
  `~/.azure/config`; commands read defaults from there in a fixed
  precedence order (env > flag > config > default).
- **Lesson for m-cli.** Hybrid is real — even at Microsoft's scale,
  not every Azure surface is autogenerated. The interesting bit is
  that Knack imposes the **output-format** layer uniformly even when
  the command itself isn't autogenerated. Output is the right place
  to start enforcing schemas; argument parsing can stay imperative
  longer.

### 2.3 The "discovery-driven" tier — schema at runtime

These CLIs have no shipped manifest at all; they discover the surface
by talking to a server that publishes a machine-readable schema.

#### kubectl

- **Source of truth.** The Kubernetes API server's OpenAPI v3
  endpoint, fetched at `kubectl` startup.
- **Grammar.** `kubectl <verb> <resource> [<name>]` — verb-resource,
  with verbs drawn from a fixed canonical set (`get`, `describe`,
  `create`, `apply`, `delete`, `edit`, `patch`, `scale`, `rollout`,
  `logs`, `exec`, `port-forward`, `cp`, `top`, `wait`).
- **Why it works.** Kubernetes has ~40-60 built-in resource kinds and
  unbounded CRDs (Custom Resource Definitions). Hard-coding the
  resource list is impossible. So `kubectl` asks the cluster:
  *"what resources do you have? what's their schema?"* and renders
  the surface from the response.
- **`kubectl explain <resource>`** — reads the OpenAPI to describe
  any field of any resource. This is documentation as a query against
  the schema.
- **Plugins.** `kubectl-foo` becomes `kubectl foo` automatically. No
  central registry; just `$PATH` lookup.
- **Lesson for m-cli.** Discovery-driven is only worth it when the
  surface is unbounded or owned by a different team. m-cli's surface
  is bounded and owned by us; we should ship the manifest, not
  discover it. But the *concept* of `kubectl explain` — every field
  of every output is queryable as data — is something `m capabilities`
  could deliver to its fullest.

#### Terraform / Pulumi

- **Source of truth.** Per-**provider** schemas published by each
  cloud's provider plugin. `terraform providers schema -json` dumps
  the active providers' resource schemas as JSON. Pulumi's
  `schema.json` per package serves the same role.
- **What's in the schema.** Resource types, their attributes,
  validation rules, nested blocks, deprecation flags, sensitive
  flags.
- **Use.** Both the CLI (for validation) and the IDE plugins (for
  completion and inline documentation) read the same schema.
- **Lesson for m-cli.** Provider isolation. Terraform's core knows
  nothing about AWS; the AWS provider plugin is the schema source for
  AWS resources. m-cli could analogously isolate **engine drivers**
  (Docker, Local YDB, future IRIS, future SSH) behind a driver
  manifest. The audit found the engine has manifests-within-manifests
  already; the pattern fits.

### 2.4 The "imperative but disciplined" tier

These frameworks don't use external schemas, but they impose strong
internal conventions that achieve similar consistency through
language-level mechanisms.

#### PowerShell cmdlets

- **Source of truth.** Cmdlet class attributes in C#/PowerShell.
- **The rule.** Every cmdlet name is `Verb-Noun` where `Verb` comes
  from a fixed canonical list. `Get-Verb` returns the ~100 approved
  verbs (Get, Set, New, Remove, Add, Clear, Open, Close, Read, Write,
  Show, Find, Search, Sort, Select, Out, Import, Export, Test, Trace,
  Resume, Suspend, Wait, Start, Stop, Restart, Enable, Disable,
  Install, Uninstall, Update, …).
- **Enforcement.** Modules emit warnings on load if a cmdlet uses an
  unapproved verb. Microsoft's own modules are linted in CI.
- **Common parameters.** Every cmdlet gets `-Verbose`, `-Debug`,
  `-ErrorAction`, `-ErrorVariable`, `-OutVariable`, `-WhatIf`,
  `-Confirm` for free — provided by the framework, not the cmdlet
  author.
- **Pipeline.** Cmdlets pass objects, not text. Output schemas exist
  but as .NET types, not external JSON.
- **Lesson for m-cli.** Convention enforcement doesn't require a
  manifest if you have a strict naming rule + a linter. PowerShell
  proves this at industrial scale. But Python lacks the cmdlet
  framework's pipeline-object model, so adopting PowerShell's exact
  approach isn't possible.

#### git (subcommand discovery via `$PATH`)

- **Source of truth.** `git foo` runs `git-foo` if it exists on
  `$PATH`. The "registry" is the filesystem.
- **Grammar.** Verb-first: `git commit`, `git push`, `git rebase`.
  Imperative — every verb is an action.
- **Help.** Each subcommand is responsible for its own `--help`.
  `man git-foo` if a man page exists. No central manifest.
- **Lesson for m-cli.** The simplest discovery model possible.
  Powerful for plugins (anyone can ship a `git-foo` binary) but pays
  zero consistency dividend. The audit's findings — divergent help
  styles, divergent error prefixes, divergent exit codes — are
  inherent in this model and exactly what schema-first architectures
  exist to fix.

### 2.5 The "completion-spec" tier

Worth mentioning because it solves a slice of the problem from a
different angle.

#### Fig / inshellisense / carapace

- **Source of truth.** External completion specs (TypeScript objects
  in Fig's `withfig/autocomplete` repo, YAML in carapace) describing
  the grammar of *third-party* CLIs.
- **Coverage.** ~600+ CLIs at last count for Fig.
- **What they describe.** Subcommand tree, flags, args, completion
  generators (e.g., "this arg completes from `git branch --list`").
- **Lesson for m-cli.** The completion world has already converged on
  external schemas for CLIs. If m-cli's manifest were in a public
  schema format, it could be the canonical completion spec for free —
  no separate `withfig/autocomplete/m-cli.ts` needed.

### 2.6 Summary table

| CLI / Framework  | Schema source           | Grammar pattern   | Surface size  | Manifest format |
| ---------------- | ----------------------- | ----------------- | ------------- | --------------- |
| AWS CLI          | botocore service models | service-operation | ~15,000 verbs | JSON            |
| OCI CLI          | OpenAPI (REST)          | verb-noun-noun    | ~3,000 verbs  | OpenAPI         |
| Stripe CLI       | OpenAPI (REST)          | resource-action   | ~500 verbs    | OpenAPI         |
| gcloud / Calliope| Surface YAML tree       | flexible/scoped   | ~6,000 cmds   | YAML            |
| Oclif            | TS-derived `oclif.manifest.json` | verb / topic-verb | per-CLI | JSON          |
| Azure CLI / Knack| Hybrid (aaz + curated)  | verb-noun         | ~3,000 cmds   | Python tables   |
| kubectl          | OpenAPI v3 from cluster | verb-resource     | ~50 verbs × ∞ resources | OpenAPI |
| Terraform        | Provider schemas        | resource type     | per-provider  | JSON Schema     |
| Pulumi           | Per-package `schema.json` | resource type   | per-provider  | JSON Schema     |
| PowerShell       | C# attributes           | Verb-Noun         | thousands     | .NET reflection |
| git              | `$PATH` discovery       | verb-first        | extensible    | (none)          |
| Fig / carapace   | External completion spec| describes others  | 600+ CLIs     | TS / YAML       |

---

## 3. Patterns for semantic consistency

Six patterns recur across the case studies. m-cli implements **some**
of them today; the audits map onto the ones it doesn't.

### 3.1 Single declarative manifest per command

The fact that "`m engine status` takes `--json`" is recorded in
exactly **one** file. Every consumer (argparse generator, help
renderer, capabilities exporter, contract test, completion exporter)
reads from that file.

**Who does this.** gcloud (each YAML in `surface/`), Oclif (each
`Command` subclass before manifest generation), AWS CLI (each
operation in the service model).

**Where m-cli fails.** Three places today: `argparse` wiring, hidden
hand-written capabilities payload, separate vendored manifest for the
engine. The audits showed all three drift.

### 3.2 Auto-generated argument parser

Argparse / cobra / commander is a build artifact, not the source of
truth. Authoring happens in the manifest; the parser is generated
either at runtime (Calliope) or at build time (Oclif).

**Who does this.** Calliope (runtime), Oclif (at `oclif manifest`
build time), AWS CLI's generated commands.

**Why it matters.** Once the parser is generated, there is nowhere
for a flag to "exist" without being in the manifest. The drift
problem collapses to zero by construction.

### 3.3 Output formats as a framework feature

Every command supports the same set of output formats
(`{text, json, yaml, table, csv, tap, junit, lcov}`) because the
framework owns the formatting, not the command.

**Who does this.** Knack (Azure CLI's `--output`), Calliope's
`--format`, kubectl's `-o`. Each command produces a typed result;
the framework renders it.

**Where m-cli fails.** Each command rolls its own. `m test` supports
`{text, tap, json, junit}`; `m watch` supports `{text, tap, json}`
(no junit); `m coverage` supports `{text, json, lcov}`; `m lint`
supports `{text, json, tap}` (no junit, no lcov). The audits flagged
this as C2 / C4.

### 3.4 Exit-code policy is uniform and documented

Either codified globally (`0=success, 1=domain error, 2=usage error`,
with rare extensions) or per-command but **documented in the
manifest**.

**Who does this.** Calliope (exit codes part of the spec), Oclif (via
typed errors), AWS CLI (uniform: 0/255/254/253/252 = success / cli /
service / usage / signal).

**Where m-cli fails.** Audit finding C5 / "Exit codes": `m engine
status` returns 1 when the container is down, but this is invisible
in `--help`. `m fmt --check non-existent.m` exits 0, contradicting
the principle.

### 3.5 Help, capabilities, completion, docs — one manifest, many renderers

The same manifest entry produces: `--help` body, capabilities JSON,
shell-completion spec, online HTML/Markdown docs, contract tests.

**Who does this.** Calliope (the Markdown reference docs at
cloud.google.com/sdk/gcloud/reference are autogenerated from the same
YAML that drives the CLI). Oclif (`oclif readme` regenerates README
from manifest).

**Where m-cli fails.** `cli-output-audit-2026-05-13.md` is hand-typed
from probing the CLI. A manifest-first m-cli would emit the audit's
content as a make target.

### 3.6 Plugin / extension contract is the same as the core contract

A plugin is a manifest fragment; the dispatcher merges fragments at
startup. The plugin doesn't need to call the framework's parsing API;
it just declares its surface.

**Who does this.** Oclif (npm-installable plugins with their own
manifest), kubectl (plugins via `$PATH`, but completion specs can
extend), Helm (chart manifest + values).

**Where m-cli fails.** Today's plugin contract
(`docs/plugin-development.md`) requires plugins to call argparse
directly. No way to introspect a plugin's surface without importing
its Python module. The audit's C4 (capabilities doesn't descend) is a
symptom: even the **built-in** sub-actions aren't introspectable.

---

## 4. Vocabulary discipline — verbs, nouns, grammars

The audits documented surface-level inconsistencies. Underneath them
is a deeper one: m-cli has no controlled vocabulary. Each verb's name,
each argument's name, each output field's name was chosen ad hoc by
the verb's author.

### 4.1 What "controlled vocabulary" means

Three industry references converge:

- **Google Cloud's API Improvement Proposals (AIPs)**, specifically
  AIP-122 (resource names), AIP-130 (standard methods: List, Get,
  Create, Update, Delete), AIP-136 (custom methods).
- **PowerShell Approved Verbs** — `Get-Verb` enumerates the ~100
  verbs Microsoft accepts. Modules that ship cmdlets using
  unapproved verbs get warnings on load.
- **POSIX Utility Conventions** (POSIX.1 §12.2) — argument naming
  rules, `-` for stdin, `--` for end-of-options, `-h/-?` for help.

These don't agree on which verbs are canonical, but they agree that
**there must be a list**, and **deviations require justification**.

### 4.2 m-cli's current grammar surface

Four grammars coexist:

| Grammar              | Examples in m-cli                                            |
| -------------------- | ------------------------------------------------------------ |
| `m <verb> [arg]`     | `m fmt`, `m lint`, `m test`, `m coverage`, `m run`, `m new`  |
| `m <noun> <verb>`    | `m engine status`, `m engine start`, `m engine stop`, …      |
| `m <namespace> <verb>` | `m stdlib doc`, `m stdlib search`, `m stdlib list`, …      |
| `m <verb>` (singular)| `m doctor`, `m capabilities`, `m plugins`, `m watch`, `m lsp`|

`m engine` and `m stdlib` are both sub-action dispatchers but they
use different mental models. `engine` is **a thing you act on** (so
noun-then-verb feels right). `stdlib` is **a knowledge base you
query** (so namespace-then-verb feels right). The two patterns are
defensible, but the user can't tell them apart at a glance.

### 4.3 Canonical verb sets in industry

| Source              | Verb set                                                                                       |
| ------------------- | ---------------------------------------------------------------------------------------------- |
| Google AIP-130      | `List`, `Get`, `Create`, `Update`, `Delete`                                                    |
| AIP-136 (custom)    | imperative or noun-form, last word of method name                                              |
| kubectl             | `get`, `describe`, `create`, `apply`, `delete`, `edit`, `patch`, `scale`, `rollout`, `logs`, `exec`, `port-forward`, `cp`, `top`, `wait`, `explain` |
| PowerShell (common) | `Get`, `Set`, `New`, `Remove`, `Add`, `Clear`, `Open`, `Close`, `Read`, `Write`, `Show`, `Find`, `Search`, `Sort`, `Select`, `Import`, `Export`, `Test`, `Trace`, `Resume`, `Suspend`, `Wait`, `Start`, `Stop`, `Restart`, `Enable`, `Disable`, `Install`, `Uninstall`, `Update` |
| OCI CLI             | `list`, `get`, `create`, `update`, `delete`, plus per-resource customs                         |

m-cli's actual verbs today (deduplicated): `fmt`, `lint`, `test`,
`watch`, `coverage`, `lsp`, `doctor`, `new`, `init` (under ci), `run`,
`status`, `install`, `start`, `stop`, `restart`, `logs`, `shell`,
`exec`, `version`, `reset`, `capabilities`, `list`, `doc`, `search`,
`examples`, `errors`, `manifest`, `plugins`. ~28 distinct verbs.

A proposed **m-cli verb vocabulary** (Appendix B) maps each of these
to a canonical form and disallows synonyms (no `show` vs `display`
vs `get` for the same action).

### 4.4 Noun discipline

Less visible than verbs, but the audits surfaced it. The same concept
appears under different names across the JSON outputs:

| Concept                  | Names used today                              |
| ------------------------ | --------------------------------------------- |
| Container's running state| `container_running` (status JSON), `container up:` (text), `container running` (doctor)  |
| Image label              | `image_ref` (status), `image_ref` (version), `image:` (text header) |
| Diagnostic severity      | `severity: error` (lint JSON), `[E]` (lint text), `OK / WARN / FAIL` (doctor text), `severity_marker` (none) |
| Total finding count      | `findings` (lint summary), no JSON top-level field |

A noun glossary — one term per concept, used everywhere — would
collapse this.

### 4.5 Grammar normalisation proposal (illustrative)

The disciplined version of m-cli's grammar could be:

```
m <verb> [args]                  — leaf verbs that act on the cwd / args
                                   (fmt, lint, test, watch, coverage,
                                   doctor, new, run, lsp)

m <namespace> <verb> [args]      — verbs that act on a domain
                                   (engine status, stdlib doc, ci init,
                                   plugins list)

m get <resource> [name]          — uniform read across resources
                                   (m get engine, m get plugin, m get rule)

m capabilities                   — meta-introspection (special)
```

The first two are status quo, normalised: `engine` and `stdlib` are
both **namespaces**, and the inconsistency the user sees today
disappears if we recategorise mentally.

The third row is **new** and contentious — it imposes an AIP-130-style
`get/list` pattern on m-cli that doesn't exist today. Whether to add
this is a major design choice; the alternative is "m-cli has no
resource model and that's fine."

---

## 5. The proposed manifest stack — five layers

Borrowed from Kustomize / Crossplane / Terraform's layered model and
adapted to m-cli. Each layer is YAML, each is git-versioned, each is
lintable. The layers are walked at startup; the dispatcher builds the
runtime CLI from the merged result.

### 5.1 The five layers

```
┌─────────────────────────────────────────────┐
│  Layer 5 — Provider                         │  Driver-supplied schema
│  e.g. DockerDriver, LocalEngine, IRISDriver │  (engines, runners)
│  schema/providers/<name>.yaml               │
└────────────────────┬────────────────────────┘
                     │ (consumed by)
┌────────────────────┴────────────────────────┐
│  Layer 4 — Overlay                          │  User / project config
│  .m-cli.toml / pyproject.toml [tool.m-cli]  │  (defaults, profiles,
│  ~/.config/m/config.yaml                    │   plugin toggles)
└────────────────────┬────────────────────────┘
                     │ (extends)
┌────────────────────┴────────────────────────┐
│  Layer 3 — Imported manifest                │  Sub-tool manifests
│  m-test-engine.json, m-stdlib-manifest.json │  vendored from siblings
│  m-cli/dist/imported/*.json                 │
└────────────────────┬────────────────────────┘
                     │ (extends)
┌────────────────────┴────────────────────────┐
│  Layer 2 — Native schema                    │  m-cli's own commands
│  schema/surface/<verb>.yaml                 │  (fmt, lint, test, …)
│  schema/surface/<namespace>/<verb>.yaml     │
└────────────────────┬────────────────────────┘
                     │ (validated against)
┌────────────────────┴────────────────────────┐
│  Layer 1 — Surface meta-schema              │  Schema-of-schemas
│  schema/cli-manifest.schema.json            │  (governs every layer)
└─────────────────────────────────────────────┘
```

### 5.2 Layer 1 — Surface meta-schema

A JSON Schema (Draft 2020-12) that defines what a command manifest
*is*. Every layer 2-5 file is validated against this. Validation
failures block CI.

```yaml
# schema/cli-manifest.schema.json — illustrative excerpt
$schema: "https://json-schema.org/draft/2020-12/schema"
$id: "https://m-dev-tools.github.io/m-cli/schemas/manifest/v1.json"
type: object
required: [name, purpose, layer]
properties:
  name: {type: string, pattern: "^[a-z][a-z0-9-]*$"}
  parent: {type: string}                # for nested verbs
  purpose: {type: string, minLength: 10}
  description: {type: string}
  verb_category:                        # AIP-style canonical verb
    enum: [list, get, create, update, delete,
           start, stop, restart, install, exec,
           apply, check, run, watch, search, doc, manifest,
           refresh, reset, status, version, capabilities]
  args: {type: array, items: {$ref: "#/$defs/arg"}}
  options: {type: array, items: {$ref: "#/$defs/option"}}
  output:
    type: object
    properties:
      formats: {type: array, items: {enum: [text, json, yaml, tap, junit, lcov, csv]}}
      schemas:
        type: object              # per-format output schema $refs
  exit_codes:
    type: object                  # explicit per-code documentation
    additionalProperties: {type: string}
  examples:
    type: array
    minItems: 1                   # mandatory ≥1 example (mirrors Calliope)
    items: {$ref: "#/$defs/example"}
  errors:
    type: array
    items: {$ref: "#/$defs/error"}
  stability:
    enum: [experimental, beta, stable, deprecated]
$defs:
  arg: {…}
  option: {…}
  example: {…}
  error: {…}
```

The meta-schema is the **only** hand-authored JSON Schema in the
system. Everything else is data validated against it.

### 5.3 Layer 2 — Native schema

m-cli's own subcommands. Each verb is one YAML file:

```
schema/surface/
├── fmt.yaml
├── lint.yaml
├── test.yaml
├── watch.yaml
├── coverage.yaml
├── doctor.yaml
├── new.yaml
├── run.yaml
├── lsp.yaml
├── plugins.yaml
├── capabilities.yaml
├── ci/
│   ├── _group.yaml         # namespace metadata
│   └── init.yaml
├── engine/
│   ├── _group.yaml
│   ├── status.yaml
│   ├── install.yaml
│   ├── start.yaml
│   ├── stop.yaml
│   ├── restart.yaml
│   ├── logs.yaml
│   ├── shell.yaml
│   ├── exec.yaml
│   ├── version.yaml
│   ├── reset.yaml
│   └── capabilities.yaml
└── stdlib/
    ├── _group.yaml
    ├── list.yaml
    ├── doc.yaml
    ├── search.yaml
    ├── examples.yaml
    ├── errors.yaml
    └── manifest.yaml
```

A concrete example is in [Appendix A](#appendix-a--concrete-manifest-sketch-for-m-engine-status).

### 5.4 Layer 3 — Imported manifests

m-cli already consumes machine-readable artifacts from sibling repos:

- `dist/m-test-engine.json` (vendored from `m-test-engine`).
- `dist/stdlib-manifest.json` (read from `~/m-dev-tools/m-stdlib/`).

Today these are read ad-hoc by the verbs that need them. In the
proposed architecture they live under `schema/imported/` (or are
fetched at install time), are validated against an import-shape
meta-schema, and contribute facts to the merged surface.

Examples:

- `schema/imported/m-test-engine.yaml` declares the available engine
  verbs *as a contract* — `m engine status` is wired only if the
  imported manifest advertises it. This kills the verb-set-drift bug
  the engine audit found (manifest's 13 verbs vs argparse's 11).
- `schema/imported/m-stdlib.yaml` declares STD* modules; `m stdlib`
  verb handlers consume them.

### 5.5 Layer 4 — Overlay

Project- and user-level customisation. Today's `.m-cli.toml`
(`[fmt]`, `[lint]`, `[lint.thresholds]`, etc.) is already an overlay
in spirit; this layer formalises it.

```yaml
# Example overlay — what .m-cli.toml becomes
overlay:
  fmt:
    rules: pythonic-lower         # default --rules
  lint:
    rules: default
    target_engine: yottadb
    thresholds:
      line_length: 100
  engine:
    driver: docker                # pin a driver
  plugins:
    enabled: [m-corpus-stats]
    disabled: []
```

The dispatcher resolves precedence: command-line flag > overlay >
imported-manifest default > native default.

### 5.6 Layer 5 — Provider

The pluggable execution layer. Today's `LocalEngine` / `DockerEngine`
/ `SSHEngine` (`m_cli.engine`) are providers. So would be a future
IRIS engine, a future remote-cluster engine, etc.

Each provider declares its capabilities in a YAML manifest:

```yaml
# schema/providers/docker-engine.yaml
provider: docker
implements: [engine.status, engine.start, engine.stop, …]
capabilities:
  can_exec: true
  can_shell: true
  can_isolate_per_test: true        # advertises STDFIX support
  can_branch_coverage: true
  ydb_version: "r2.02"
manifest_ref: imported/m-test-engine.yaml
```

Why this matters: today, code like `m_cli.engine.detect_engine()` has
to *guess* what each engine supports. With provider manifests, the
dispatcher knows that `LocalEngine` doesn't support `m engine shell`
and emits a clean "unavailable on local engine" message instead of
breaking at the docker call.

### 5.7 What the dispatcher does at startup

```
1. Load Layer 1 meta-schema.
2. Walk Layer 2 (schema/surface/) — validate each file against Layer 1.
3. Walk Layer 3 (schema/imported/) — validate against the same.
4. Compute the merged command surface (layer 2 ∪ layer 3, with
   layer 3 attaching to surface-declared mount points).
5. Apply Layer 4 (overlay): defaults injected per-command.
6. Resolve Layer 5 (provider) for the active engine; intersect each
   verb's required capabilities against the provider's.
7. Build argparse parser from the merged surface.
8. Dispatch.
```

Steps 1-6 are read-only and cacheable; only step 7 is per-invocation
cost.

### 5.8 What lints against the manifests

| Lint                  | Asserts                                                          |
| --------------------- | ---------------------------------------------------------------- |
| `m-meta lint`         | Every Layer 2 file validates against Layer 1.                    |
| `m-meta drift`        | argparse registry built from manifests matches a `make manifest`-emitted snapshot byte-for-byte. |
| `m-meta vocab`        | Every `verb_category` in every manifest is in the canonical verb set. |
| `m-meta examples`     | Every command has ≥ 1 example (and the example's invocation parses against the same manifest). |
| `m-meta exit-codes`   | Every documented exit code matches what tests observe.           |
| `m-meta outputs`      | Each `--format`'s output schema validates against actual command output. |

These are the runtime equivalent of the audit document: every
finding the audit caught becomes a lint that fails CI.

---

## 6. Approaches compared — pros & cons

Five paths forward. The user has explicitly asked about two of them:
full schema-first (Approach E) and pure argparse (Approach A). The
middle three are useful framing.

### 6.1 Approach A — pure argparse (status quo)

Keep using `argparse` per-verb; no manifest, no registry.

**Pros**
- Zero infrastructure cost.
- Maximum simplicity for the verb author.
- No build step. `m foo` works directly from source.
- Idiomatic Python.

**Cons**
- Everything the audits found. Drift is the natural state.
- Capabilities is hand-maintained.
- Help, exit codes, output destination policy enforced (if at all) in
  contract tests, not at the source.
- Plugins must call argparse themselves; manifest-level introspection
  impossible.

**Verdict.** What's there. Audited. Found wanting.

### 6.2 Approach B — argparse + light registry (the remediation plan's P5)

A small `@subcommand(...)` decorator that records metadata alongside
argparse wiring. Manifest is in-process Python, exported as JSON.

**Pros**
- Incremental — port one verb at a time.
- Low risk; if the registry is wrong, argparse still works.
- No new file formats, no build step.
- Closest in spirit to Knack (Azure CLI) and Click + introspection
  helpers.

**Cons**
- Two sources of truth during migration. Manifest can silently drift
  from argparse until contract tests catch it.
- Doesn't solve the plugin-introspection problem (the plugin still
  has to use the same decorator API).
- Doesn't give external consumers (IDEs, Fig, autocomplete) a clean
  YAML/JSON they can read.

**Verdict.** Best risk-adjusted upgrade. Already endorsed by the
remediation plan as optional P5.

### 6.3 Approach C — adopt an existing framework (Click / Typer / Cement / Knack)

Drop argparse; rebuild on a maintained Python CLI framework.

**Pros**
- Mature plugin ecosystems.
- Click in particular has excellent docs and a strong community.
- Typer leverages Python type hints to derive flags.
- Knack provides Azure-CLI-style uniform output formats.

**Cons**
- Migration cost is high (every verb's parser rewritten).
- None of these frameworks are **schema-first** in the sense the user
  asked for. They have introspection helpers but no
  manifest-as-source-of-truth.
- Adds a dependency to a project that today has zero runtime deps.
- Doesn't address the cross-cutting concerns (output policy,
  capabilities recursion, manifest drift) — those are still per-verb
  problems in any of these frameworks.

**Verdict.** Solves the wrong problem. The audits' findings aren't
"argparse is bad"; they're "we have no manifest." Switching argparse
implementations doesn't fix the absence.

### 6.4 Approach D — generate argparse from YAML manifests at build time

YAML manifests are source of truth. A build step (`make manifest`)
generates Python files that call argparse. The runtime is unchanged.

**Pros**
- Single source of truth (the YAML).
- Argparse is still the runtime parser — zero behavioural change.
- Generated Python is reviewable; debugging is straightforward.
- Pattern is well-trodden (protobuf, OpenAPI generators, the
  capnp/thrift/grpc family).

**Cons**
- Build step. Contributors must run `make manifest` after editing a
  YAML.
- Generated code is checked-in vs. generated-fresh-on-every-build —
  a project-policy choice.
- Slower dev loop than Approach B (decorator).
- Mostly redundant once Approach E is in place.

**Verdict.** Sensible interim. Reasonable for a 6-month transitional
window before full Approach E. Probably skipped if Approach B has
already been adopted.

### 6.5 Approach E — full schema-first dispatcher (Calliope-style)

YAML manifests are source of truth. The dispatcher reads them at
**runtime** (no build step) and constructs argparse parsers, help
bodies, capabilities JSON, completion specs, and contract tests
in-process.

**Pros**
- Single source of truth, end to end.
- Plugins are manifest fragments → introspectable without import.
- Capabilities recursion is free (the dispatcher already walks the
  tree).
- Help-body completeness, exit-code documentation, example
  enforcement become **load-time errors**: a manifest that omits
  `examples:` doesn't load.
- Output-format policy is a framework feature, not per-verb.
- The "audit" becomes a `make audit` target that diffs the manifests
  against probed output.
- IDE/Fig/inshellisense integration is essentially free — they
  already read YAML schemas.

**Cons**
- Largest engineering investment. Realistic effort: 4-8 weeks of
  focused work.
- New file format to maintain (YAML + meta-schema).
- Startup cost (~50ms to walk and validate every YAML at startup —
  measurable but small).
- Risk of premature abstraction. m-cli's surface is bounded (~50
  verbs) — at this scale, Approach B might deliver 80% of the
  benefit at 20% of the cost.
- All P0-P4 of the remediation plan are prerequisites — Approach E
  on top of today's `display` chaos would just be a fancier wrapper
  around the same drift.

**Verdict.** The right finish line. Wrong starting point.

### 6.6 Side-by-side

|                                  | A — argparse | B — registry | C — Click/Knack | D — YAML→argparse codegen | E — full schema-first |
| -------------------------------- | :-----------: | :----------: | :-------------: | :-----------------------: | :-------------------: |
| Source of truth                  | scattered     | Python decorator | scattered    | YAML                      | YAML                  |
| Drift between SOT and surface    | high          | medium       | high            | low                       | impossible            |
| Plugin introspection without import | no         | no           | no              | partial                   | yes                   |
| Capabilities recursion           | manual        | manual        | manual         | automatic                 | automatic             |
| Output-format policy enforcement | per verb     | per verb     | framework        | framework                 | framework             |
| Example enforcement at load time | no           | possible     | no              | possible                  | yes                   |
| External tooling (Fig, IDE) friendly | no       | partial      | no              | yes                       | yes                   |
| Cost to adopt                    | $0           | $             | $$$$           | $$                        | $$$$$                 |
| Cost to maintain per new verb    | $$           | $$           | $$$             | $                         | $                     |
| Runtime startup cost             | baseline     | baseline      | baseline       | baseline                  | +~50ms                |
| Dependency footprint             | stdlib       | stdlib        | + framework    | stdlib + build step       | stdlib + YAML lib     |
| Suitability at m-cli's scale (~50 verbs) | ✓     | ✓✓✓          | ✗               | ✓✓                        | ✓ (overkill if surface stays small) |
| Suitability if m-cli grows 10×   | ✗            | ✓             | ✓               | ✓✓                        | ✓✓✓                   |

---

## 7. Recommended path for m-cli

The audits and the remediation plan point to a clear sequencing:

### 7.1 Now (Plan-0 P0-P4)

**Ship the remediation plan.** Pin contracts, build `m_cli.display`,
make capabilities recursive, enforce help-body completeness, codify
output-format policy. Most of what the audits caught is fixable
without leaving Approach A.

### 7.2 Next 3-6 months (Plan-0 P5 = Approach B)

**Adopt the registry decorator.** A `@subcommand(...)` API alongside
argparse, with a `make manifest` target that emits
`dist/cli-surface.json` from the registry. This makes m-cli's surface
machine-readable without breaking anything.

This is also where the **vocabulary** gets codified — controlled
verbs, controlled nouns, AIP-style grammar — because the decorator
becomes the place to enforce them at registration.

### 7.3 6-12 months out (Approach D or E)

**If — and only if — Approach B's discipline is holding and the
surface is still growing**, migrate the registry's Python source of
truth to YAML.

This is the move that gives plugins manifest-level introspection and
makes external tooling (Fig, IDE plugins) trivial. It's also the move
that justifies the **layered-stack** model in §5 — at Approach B
scale, the five layers exist conceptually but live in Python; at
Approach D/E scale, they're physical files in `schema/`.

### 7.4 What this means concretely

| Phase           | Source of truth         | Layer model            | Effort to adopt  |
| --------------- | ----------------------- | ---------------------- | ---------------- |
| Today           | argparse + ad-hoc       | implicit, in code      | 0                |
| Plan-0 P0-P4    | argparse + display + tests | implicit, in code   | ~3 weeks         |
| Plan-0 P5 = B   | `@subcommand` decorator | Python objects        | ~2 weeks         |
| Approach D      | YAML in `schema/surface/`, codegen → Python | YAML files | ~3-4 weeks       |
| Approach E      | YAML, no codegen, runtime walker | YAML files + meta-schema + provider/overlay layers | ~6-8 weeks       |

### 7.5 The honest take

For a single-developer, single-user hobbyist project at m-cli's
current scale, **Approach B is plenty.** The audits' findings can all
be fixed without YAML. The schema-first architecture is genuinely the
right design at scale — and m-cli might reach that scale if it picks
up an IRIS engine, a remote runner, several plugins, and an editor
ecosystem — but those drivers don't exist yet.

The valuable thing to do *now* is to write the meta-schema (Layer 1)
even if no files validate against it yet. The meta-schema is the
contract. Once it exists, every Plan-0 phase becomes a step toward
populating it; the decision between Approach B and Approach E
collapses to "where do we store the manifest data — Python objects or
YAML files?" — and that question is much smaller than "should we
adopt schema-first?"

---

## 8. Open questions

These are decisions that should happen before any of this is
implemented. Each has a default and an alternative; the answer
shapes the rest.

### Q1 — Manifest format: YAML or JSON?

**Default:** YAML for hand-edited Layer 2; emitted JSON for
distribution (`dist/manifest.json`). YAML for readability, JSON for
consumption.

**Alternative:** JSON for both, with YAML-flavoured JSON5 if comments
matter.

Decision: **YAML+JSON, or JSON5, or JSON-only?**

### Q2 — Build step or no build step?

**Default:** No build step. The dispatcher reads YAML at runtime.
Adopts Approach E in 7.3 directly.

**Alternative:** Build step (`make manifest` generates Python from
YAML). Approach D.

The build-step path has better startup time and worse contributor
ergonomics. Decision shapes Approach D vs E.

Decision: **runtime or build-time consumption of the manifest?**

### Q3 — Controlled verb list — strict or advisory?

**Default:** Strict. The meta-schema's `verb_category` is an enum,
and no manifest can declare a verb outside it. Adding a new verb
requires a meta-schema bump.

**Alternative:** Advisory. The meta-schema warns on unknown verbs but
doesn't block.

Strictness gives PowerShell-level discipline. Advisory gives
git-level extensibility. Decision shapes how easy it is to add a new
verb.

Decision: **strict, advisory, or pattern-matching (e.g. enum + custom verbs gated by `experimental:` stability)?**

### Q4 — Where do output schemas live?

**Default:** Each Layer 2 manifest references `output.schemas.json` /
`output.schemas.text` $refs that point into `schema/outputs/`. JSON
Schema for JSON outputs; a markdown-doc reference for text outputs
(no machine schema for human prose).

**Alternative:** Inline the schemas inside each manifest. Simpler
single-file editing, larger files.

Decision: **$ref-based or inline output schemas?**

### Q5 — Plugin manifest distribution

**Default:** A plugin's manifest ships inside the plugin's Python
wheel (via `importlib.resources`); m-cli reads it on plugin
registration.

**Alternative:** Plugins call a `register(subparser)` function that
returns a manifest dict; m-cli stitches it in.

The first is more "data"; the second matches today's plugin contract.

Decision: **shipped manifest file, or registration-time dict?**

### Q6 — How aggressive should the noun discipline be?

The audits surfaced that `container_running` (JSON), `container up:`
(text), and `container running` (doctor prose) all name the same
concept. Three options:

- **Default — Noun glossary, advisory.** A `schema/glossary.yaml`
  documents canonical terms; new manifests get warnings (via lint)
  for using non-glossary terms in user-facing strings.
- **Strict noun glossary.** Lint fails on non-glossary terms in
  manifest user-facing fields.
- **No glossary.** Names stay free-form.

Decision: **advisory, strict, or none?**

### Q7 — Backwards compatibility horizon

If Approach E lands, today's `m engine reset` may become `m engine
delete` (closer to AIP-130). Existing scripts break.

**Default:** Maintain old names as aliases for 1 release cycle, warn
on use, remove in the next major.

**Alternative:** Hard rename, no aliases — given m-cli is pre-1.0.

Decision: **alias-with-warning, or hard rename?**

---

## Appendix A — concrete manifest sketch for `m engine status`

What a Layer 2 manifest for the audited `m engine status` verb might
look like. Annotated.

```yaml
# schema/surface/engine/status.yaml
$schema: ../../cli-manifest.schema.json
schema_version: 1

# ── Identity ─────────────────────────────────────────────────────
name: status
parent: engine                          # the dispatcher namespace
verb_category: status                   # canonical AIP-style verb
stability: stable

# ── Help body ────────────────────────────────────────────────────
purpose: |
  Print container/image/daemon state for the active engine driver.
description: |
  Builds a snapshot from up to five docker probes (CLI presence,
  daemon reachability, image presence, container running, container
  health). Text output uses ✓ / ✗ / - glyphs; JSON output mirrors
  the same fields plus image OCI labels.

  Exits 0 when the container is running, 1 when it isn't. Both
  text and --json paths return this code; CI authors can branch on
  `m engine status --quiet`'s return value.

# ── Arguments / options ──────────────────────────────────────────
options:
  - name: --json
    type: boolean
    default: false
    help: Emit JSON instead of the text table.
    affects_output_format: true         # framework knows to switch renderer
  - name: --quiet
    short: -q
    type: boolean
    default: false
    help: Suppress text output; rely on exit code only.

args: []                                # status takes no positionals

# ── Outputs ──────────────────────────────────────────────────────
output:
  formats: [text, json]                 # framework enforces this list
  default: text
  schemas:
    json: ../../outputs/engine-status.schema.json
    text: ../../outputs/engine-status.text.md    # human-prose reference

# ── Exit codes ───────────────────────────────────────────────────
exit_codes:
  0: container running
  1: container not running
  2: usage error                        # from argparse, framework-supplied

# ── Examples ─────────────────────────────────────────────────────
examples:
  - command: m engine status
    description: Single-line health check.
  - command: m engine status --json
    description: Machine-readable for CI.
  - command: m engine status --quiet || echo "engine down"
    description: Exit-code-driven script branching.

# ── Errors (documented, not exhaustive) ──────────────────────────
errors:
  - condition: docker daemon unreachable
    text: surfaced via `daemon_reachable: false` in JSON; ✗ glyph in text
    exit_code: 1
  - condition: image not pulled locally
    text: `image_present: false` in JSON; ✗ glyph in text
    exit_code: 1
    hint: run `m engine install`

# ── Provider requirements ────────────────────────────────────────
requires_provider: engine               # this verb only makes sense
                                        # when a Layer-5 engine provider
                                        # is active
```

The same data drives:

- the argparse subparser for `m engine status`,
- the `--help` body,
- the JSON entry for `m capabilities --json`,
- one row in the autogenerated reference doc,
- the contract tests asserting exit-code 0/1 behaviour,
- the completion spec exported for Fig / fish / zsh,
- the schema-validation test that probes actual `--json` output.

---

## Appendix B — vocabulary tables (verbs, nouns)

Illustrative canonical sets. To be debated and ratified before being
encoded in the meta-schema.

### B.1 m-cli proposed canonical verbs

| Verb category    | Allowed names | Audit verbs that map | Notes |
| ---------------- | ------------- | -------------------- | ----- |
| `list`           | `list`        | `m stdlib list`, `m plugins`, `m lint --list-profiles` | retrieve a collection |
| `get`            | `get`         | (new — no current verb) | retrieve a single item |
| `describe`       | `describe`, `doc` | `m stdlib doc` | render documentation |
| `search`         | `search`, `find` | `m stdlib search` | full-text query |
| `check`          | `check`       | `m fmt --check`, `m lint` | validate without mutating |
| `apply`          | `fmt`, `apply` | `m fmt` (write mode) | mutate |
| `run`            | `run`, `exec`, `test`, `watch`, `coverage` | `m run`, `m engine exec`, `m test`, `m watch`, `m coverage` | execute |
| `create`         | `create`, `new`, `init` | `m new`, `m ci init` | create new resource |
| `delete`         | `delete`, `reset` | `m engine reset` | destructive removal |
| `start`          | `start`       | `m engine start`     | start a process |
| `stop`           | `stop`        | `m engine stop`      | stop a process |
| `restart`        | `restart`     | `m engine restart`   | stop + start |
| `install`        | `install`     | `m engine install`   | install/pull |
| `status`         | `status`      | `m engine status`, `m doctor` | health summary |
| `version`        | `version`     | `m engine version`, `m --version` | report version metadata |
| `capabilities`   | `capabilities`, `manifest`, `errors`, `examples` | `m capabilities`, `m engine capabilities`, `m stdlib manifest`, `m stdlib errors`, `m stdlib examples` | introspection |
| `shell`          | `shell`, `lsp` | `m engine shell`, `m lsp` | interactive session |
| `logs`           | `logs`        | `m engine logs`      | retrieve log stream |

This set has 18 verb categories. Compare to PowerShell's ~100 (too
many for our surface) and Google AIP-130's 5 (too few — they don't
cover lifecycle).

### B.2 m-cli proposed canonical nouns (excerpt)

| Concept                | Canonical noun         | Used everywhere as                          |
| ---------------------- | ---------------------- | ------------------------------------------- |
| The Docker engine container | `container`       | `container_running`, `container_healthy`    |
| A Docker image reference | `image_ref`          | `image_ref`, never `image:`                 |
| An M language test     | `test`                 | `tests_run`, `tests_passed`, never `assertions` for the unit |
| An M language assertion within a test | `assertion` | `assertions_run`, never `tests` for the unit |
| A lint finding         | `finding`              | `findings`, `finding_count`, never `diagnostic` (which is internal) |
| Severity of a finding  | `severity` ∈ `{error,warning,style,info}` | uniform across text and JSON |
| An output line of an `m fmt` decision | `change` | `would_change`, `changed`, never "reformat" / "format" mixed |
| A lint or fmt rule     | `rule`                 | `rule_id`, `rule_count`                     |
| A test suite           | `suite`                | always `suite`, never `file` / `module` for the unit |

The noun glossary's job is **collapsing synonyms**. Today the audits
caught `assertions` and `tests` being used for the same concept in
adjacent strings. A glossary makes this a lint failure.

---

*End of design. Plan 0 sequencing remains the priority; this document
describes the destination, not the road.*
