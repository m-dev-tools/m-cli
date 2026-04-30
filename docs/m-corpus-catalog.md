---
title: Open-source M / MUMPS code corpora (non-VistA)
purpose: Candidate corpora for m-cli's modern-rule-set regression gate
inventory_date: 2026-04-29
inventoried_by: research pass for m-cli M-MOD-NN rule design
scope: Public, post-2010-active, NOT VistA-derived, substantial enough to surface real lint findings
---

# Catalog: open-source M / MUMPS / ObjectScript corpora (non-VistA)

## Purpose

`m-cli`'s wild-corpus regression gate today is the OSEHRA VistA M codebase
(~39,330 routines, 1980s-era SAC conventions). For the new **M-MOD-NN** rule
set — modern idioms shared by YottaDB and IRIS (long strings, transactions,
`$INCREMENT`, structured exception handling, modern engine features) — VistA
is the wrong gate: it triggers a flood of false positives against legacy code
that pre-dates the idioms the rules check for.

This catalog is the shortlist of non-VistA, post-2010-active corpora suitable
for a `make lint-modern` regression gate analogous to `make lint-vista`.

## Methodology

- All entries verified live via `gh api` against the GitHub REST API on
  2026-04-29. File counts are exact (recursive tree walk, filtered by
  extension); LOC is approximated from KB/file ratios where the API does not
  surface line counts.
- "Last activity" is the date of the most recent commit on the default
  branch.
- "Engine" reflects what the code is built/tested against. `engine-neutral`
  means the project ships parallel implementations or only uses ANSI-standard
  syntax.
- Corpora that turned out to be VistA forks, abandoned pre-2014, or under
  ~10 routines were dropped from the main tables (a few are listed in the
  "Excluded" section with the reason).
- Where a project lives natively on GitLab and only mirrors to GitHub
  (notably the YottaDB org), the GitHub mirror URL is given since that is
  what `gh api` and casual users hit first; the GitLab URL is in the notes.

## File extensions encountered

| Extension | Meaning | Engines | Parseable by m-cli? |
|---|---|---|---|
| `.m` | Pure M / MUMPS routine source | YottaDB, GT.M, FreeM, Caché-pre-export | **Yes** |
| `.mac` | InterSystems "MAC" routine — pure M body with an InterSystems export header | IRIS, Caché | **Yes** (best-effort; can contain ObjectScript-isms) |
| `.cls` | InterSystems ObjectScript **class** — UDL wrapper + ObjectScript method bodies | IRIS, Caché | **No** (different language; see "Why .cls is excluded" below) |
| `.inc` | Include file (shared macros, `#define`s) | IRIS, Caché | **No** (preprocessor input, not M) |
| `.int` | Compiled-routine "intermediate" view of a `.mac` | IRIS, Caché | (treat same as `.mac`) |

### Why `.cls` is excluded

ObjectScript and MUMPS are *related* but not the *same* language.
InterSystems describes ObjectScript as "a functional superset of the
ANSI-standard MUMPS language" ([IRIS docs](https://docs.intersystems.com/irislatest/csp/docbook/DocBook.UI.Page.cls?KEY=GCOS_syntax)),
which means ObjectScript adds constructs that ANSI MUMPS does not have
and that `tree-sitter-m` does not parse:

- **Class wrapper (UDL).** Top-level `Class Name Extends Parent { ... }`
  with `Parameter`, `ClassMethod`, `Method`, `Property`, `Index`,
  `Storage`, etc. blocks. None of this is MUMPS — it is its own
  declaration language with `;`-terminated parameter statements,
  `{...}` curly-brace bodies, `///` triple-slash docstrings, and
  `As %Type` type annotations.
- **OO operators in method bodies.** Even after extracting the body
  text from the class wrapper, the body code uses ObjectScript-only
  syntax: `..method()` and `..#PARAM` (relative-dot reference),
  `##class(Pkg.Name).%New()` (class instantiation), `$$$MACRO`
  (preprocessor macro reference), `As %Status` / `Output` argument
  modes, `$parameter(...)` / `$THIS`, embedded SQL via `&sql(...)`,
  and embedded JS / HTML islands via `&js<...>` / `&html<...>`.

Spot-check: `intersystems/ipm`'s `%IPM.Repo.UniversalSettings.cls`
declares `Class %IPM.Repo.UniversalSettings Extends %RegisteredObject`
and uses `..#CONFIGURABLE`, `..GetValue(...)`, `..%ClassName(1)`,
`$parameter(...)`, `$$$OK`, `As %Status`, `Output configArray` — all
ObjectScript constructs that have no analog in MUMPS.

Running m-cli's MUMPS lint rules against `.cls` files would emit
parse errors and false positives, not useful findings. Until there
is a `tree-sitter-objectscript` (or a method-extraction shim that
strips ObjectScript-isms back to pure M), `.cls` corpora are not a
useful regression gate for this linter.

`.mac` files are a different story: they are routines, not classes,
and *can* be pure ANSI M. InterSystems explicitly supports
[mixing ObjectScript and legacy MUMPS in the same .MAC](https://community.intersystems.com/post/guidance-mixing-object-script-legacy-mumps-same-int-and-or-mac),
so any given `.mac` file may or may not contain ObjectScript-isms;
treat as best-effort and expect to skip files that fail to parse.

---

## Tier 1 — primary modern corpus (recommended for daily regression)

These are the corpora that combine **substantial size**, **modern idioms**,
**clear license**, **active or recently-archived maintenance**, and —
critically — **`.m` content that m-cli's parser can actually consume**. All
are non-VistA. (The InterSystems `.cls` corpora that appeared in earlier
drafts of this catalog have been moved to "Future / out-of-scope" because
`.cls` is ObjectScript, not MUMPS — see the file-extensions section above.)

| Repo | URL | Engine | M files | License | Last commit |
|---|---|---|---|---|---|
| YottaDB/YDBTest | https://github.com/YottaDB/YDBTest | YottaDB | 4,049 `.m` | Custom (FOSS, source-available) | 2026-04-29 |
| YottaDB/YDBOcto (`src/aux/`, fixtures) | https://github.com/YottaDB/YDBOcto | YottaDB | 92 `.m` (21 in `src/aux`, 70 fixtures, 1 CI) | AGPL-3.0 (per upstream `LICENSE`) | 2026-04-16 |
| robtweed/EWD | https://github.com/robtweed/EWD | YottaDB / GT.M / Caché | 86 `.m` + 4 `.inc` | "free open source" (no SPDX-tagged file) | 2025-10-28 |
| chrisemunt/mgsql | https://github.com/chrisemunt/mgsql | YottaDB + IRIS + Caché (engine-neutral) | 36 `.m` | Apache-2.0 | 2025-03-05 |
| shabiel/M-Web-Server | https://github.com/shabiel/M-Web-Server | YottaDB + Caché | 23 `.m` | Apache-2.0 | 2025-11-19 |

### Why these

- **YDBTest** is the YottaDB regression suite — 4k `.m` files exercising
  every language feature including `TSTART`/`TCOMMIT`, triggers, indirection,
  long strings, `ZBREAK`, M-call-ins. The largest non-VistA M corpus by an
  order of magnitude. Curated for engine-test purposes, so coverage of the
  language is by design unusually broad. Heaviest dirs: `mvts` (714),
  `mugj` (376), `v230` (138), `mprof` (133), `tp` (109), `triggers` (101).
- **YDBOcto** is YottaDB's SQL engine. The 21 `.m` routines under `src/aux`
  are the runtime helpers loaded into every Octo instance and are
  hand-written modern M; the 70 routines under `tests/fixtures` are
  small-but-realistic queryable schemas. Mirror of
  `gitlab.com/YottaDB/DBMS/YDBOcto`.
- **EWD** (Enterprise Web Developer) is Rob Tweed's web framework — 86
  `.m` files of contemporary M aimed at web/JSON workloads, runs on
  YottaDB / GT.M / Caché. Idiomatically post-2010 and still being
  patched. Hand-written modern M, distinct from the YottaDB-engine voice.
- **mgsql** is Chris Munt's engine-neutral SQL gateway — 36 `.m` files
  written to run unchanged on YottaDB, IRIS, and Caché. Highest-value
  repo for testing portability rules: any rule that fires here probably
  has a portability problem.
- **M-Web-Server** is a small but contemporary HTTP server that runs on
  both YottaDB and Caché. Diverse author voice, Apache-2.0.

---

## Tier 2 — supplementary

Smaller or more-focused, but still useful for diversity (different authors,
different domains, different idioms). Worth running through the lint gate
periodically; not the daily corpus. **Restricted to repos with substantive
`.m` or (best-effort) `.mac` content** — pure-`.cls` IRIS community repos
have been moved to "Future / out-of-scope" since they are ObjectScript not
MUMPS.

| Repo | URL | Engine | M files | License | Last commit |
|---|---|---|---|---|---|
| YottaDB/YDB-Web-Server | https://github.com/YottaDB/YDB-Web-Server | YottaDB | 17 `.m` | Apache-2.0 | 2025-11-04 |
| YottaDB/YDBAIM | https://github.com/YottaDB/YDBAIM | YottaDB | 3 `.m` | AGPL-3.0 | 2026-04-27 |
| YottaDB/YDBPosix | https://github.com/YottaDB/YDBPosix | YottaDB | 2 `.m` | (FOSS, mirror) | 2025-07-14 |
| lparenteau/DataBallet | https://github.com/lparenteau/DataBallet | engine-neutral (M) | 18 `.m` | AGPL-3.0 | 2025-04-13 |
| intersystems/isc-codetidy (`.mac` only) | https://github.com/intersystems/isc-codetidy | IRIS | 3 `.mac` (133 `.cls` ignored) | MIT | 2025-06-09 |
| intersystems-community/webterminal (`.mac` only) | https://github.com/intersystems-community/webterminal | IRIS / Caché | 1 `.mac` (24 `.cls` ignored) | MIT | 2024-04-24 |
| intersystems-community/irisdemo-demo-readmission (`.mac` only) | https://github.com/intersystems-community/irisdemo-demo-readmission | IRIS | 4 `.mac` (63 `.cls` ignored) | MIT | 2025-05-23 |

---

## Tier 3 — historical interest / migration patterns

Smaller, older, or hybrid — useful when designing migration-pattern rules
(detecting code that can be modernized) but not heavyweight enough or modern
enough to be a primary gate.

| Repo | URL | Engine | M files | License | Last commit | Note |
|---|---|---|---|---|---|---|
| CoherentLogic/freem | https://github.com/CoherentLogic/freem | FreeM | 57 `.m` | none stated on GitHub mirror | 2014-03-21 (mirror); upstream at gitlab.coherent-logic.com is current | Mirror is stale; the **live** project is at `gitlab.coherent-logic.com/snw/freem` and is ANSI-95 reference code. M files are mostly the FreeM stdlib. |
| CoherentLogic/lorikeem | https://github.com/CoherentLogic/lorikeem | FreeM | 3 `.m` + 2 `.inc` | (Coherent Logic) | varies | MUMPS dev tools for GNU Emacs; mostly Elisp, only a handful of M sample routines. |
| CoherentLogic/mhttpd | https://github.com/CoherentLogic/mhttpd | FreeM | 5 `.m` | AGPL-3.0 | 2024-04-19 | Tiny but a clean-room HTTP server in pure ANSI M. |
| CoherentLogic/mtui | https://github.com/CoherentLogic/mtui | FreeM | 10 `.m` | AGPL-3.0 | 2021-01-05 | Terminal UI library, pure M. |
| neils-s/MUMPS-parser | https://github.com/neils-s/MUMPS-parser | GT.M | small | GPL-2.0 | 2023-03-24 | An ANSI-95 M parser written in M itself — interesting as a target for self-hosted lint tests. |
| robtweed/node-mdb | https://github.com/robtweed/node-mdb | engine-neutral | small | none stated | 2024-09-11 | M side of a SimpleDB-clone; useful for indirection + globals patterns. |
| robtweed/mgweb-server | https://github.com/robtweed/mgweb-server | YottaDB / Caché | (small) | none stated | 2023-07-02 | Templates for the mg_web framework. |

---

## Future / out-of-scope (ObjectScript `.cls` repos)

These InterSystems-community repos are substantial, MIT-licensed, and
modern, but their content is overwhelmingly `.cls` (ObjectScript class
definitions, not MUMPS routines). m-cli's `tree-sitter-m`-based parser
cannot consume them. They become candidate corpora the day a
`tree-sitter-objectscript` (or analogous extraction-and-translation
shim) ships under m-cli; until then they're out of scope.

| Repo | Files | License | Note |
|---|---|---|---|
| intersystems/ipm | 344 `.cls` + 1 `.mac` + 11 `.inc` | MIT | Canonical InterSystems Package Manager. |
| intersystems/isc-rest | 137 `.cls` + 4 `.inc` | MIT | InterSystems' REST framework. |
| intersystems/isc-json | 44 `.cls` + 2 `.inc` | MIT | JSON helpers. |
| intersystems/Samples-BI | 73 `.cls` | MIT | Business-intelligence samples. |
| intersystems/Samples-ObjectScript | 11 `.cls` | MIT | Tiny official samples. |
| intersystems/apps-rest | 46 `.cls` | MIT | REST-app sample. |
| intersystems/git-source-control | 53 `.cls` + 1 `.inc` | unstated | InterSystems' git integration. |
| intersystems/TestCoverage | 45 `.cls` + 1 `.mac` + 1 `.inc` | MIT | (1 `.mac` is too small to break out separately.) |
| intersystems-community/Convergent-Analytics | 23 `.cls` | MIT | Analytics package. |
| intersystems-community/PythonGateway | 50 `.cls` | MIT | IRIS↔Python bridge. |
| intersystems-community/GraphQL | 83 `.cls` + 1 `.inc` | MIT | GraphQL stack for IRIS. |
| intersystems-ib/Healthcare-HL7-XML | 36 `.cls` + 1 `.inc` | MIT | HL7/XML helpers. |
| henryhamon/cosfaker | 24 `.cls` | MIT (archived) | Test-data faker. |
| rfns/port, rfns/frontier | mostly `.cls` | MIT | Web framework + transport. |
| ARSBlue/ToolBox-4-Iris | 30 `.cls` + 8 `.inc` | MIT | Utilities. |

These repos remain a useful research target for "what does a modern,
production IRIS codebase look like" — but they are corpora for
ObjectScript tooling, not for `m-cli`.

## Excluded (with reason)

These came up in searches but were dropped from the recommended catalog.

| Repo | URL | Reason for exclusion |
|---|---|---|
| WorldVistA/VistA-M | https://github.com/WorldVistA/VistA-M | **VistA-derived.** This *is* the VistA distribution — already covered by `make lint-vista`. |
| shabiel/VPE | https://github.com/shabiel/VPE | VistA Programmer Environment — written for / against VistA conventions. |
| WorldVistA/SKIDS | https://github.com/WorldVistA/SKIDS | VistA KIDS distribution tooling. |
| ParaxialTechnologies/SAMI-VAPALS-ELCAP | https://github.com/ParaxialTechnologies/SAMI-VAPALS-ELCAP | VA partnership project, VistA-derived. |
| YottaDB/YDBOctoVistA | https://github.com/YottaDB/YDBOctoVistA | Octo schema *for* VistA — would double-count VistA conventions. |
| YottaDB/YDBDoc | https://github.com/YottaDB/YDBDoc | Documentation only (RST + a handful of M-tagged code blocks); GitHub language-detect mis-tags. |
| seanpm2001-all/mumps-examples, blackstoneDavidJ/Learn-Mumps, sergiosouzalima/mumps_samples, dpoarch/MUMPS-Tetris, etc. | various | "Hello world" tutorial scratchpads — too small (<10 routines) and stylistically inconsistent to be useful as a regression gate. |
| Most `language:M` GitHub results above ~10 stars | various | False positives — GitHub's `language:M` includes MATLAB, Mathematica, Objective-C `.m` files, Power Query M, Wolfram, etc. After manual filtering only the entries above are MUMPS/M. |

---

## Recommended seed for `make lint-modern`

For a single regression command analogous to `make lint-vista`, pick the
**three** below. All carry permissive or clearly-FOSS licenses, all are
post-2025 active, all are pure `.m`, and together they total roughly the
same order-of-magnitude file count as a small VistA package — enough to
surface real findings without exploding CI time.

1. **YottaDB/YDBTest** — 4,049 `.m` files. The single biggest non-VistA M
   corpus on the open internet. License is FOSS (mirror of the upstream
   GitLab project; YottaDB ships under custom-but-clearly-open terms — see
   `LICENSE` in the repo). Modernity: by construction — it is the YottaDB
   regression suite, written by the engine authors, using every modern
   feature the engine supports. **Anchor of the gate.**
2. **chrisemunt/mgsql** — 36 `.m` files. Apache-2.0. Engine-neutral M
   written to run unchanged on YottaDB, IRIS, and Caché. **Portability
   anchor**: any rule that fires here likely points at an engine-portability
   problem worth surfacing. Different author voice from YottaDB-org.
3. **YottaDB/YDBOcto** (`src/aux/` only — not the SQL parser, which is C) —
   21 `.m` files of hand-written runtime support. AGPL-3.0. Authors are
   the YottaDB core team, idioms are bleeding-edge YottaDB. Compact,
   production code, very high signal-to-noise.

Two further candidates worth adding once the gate stabilizes:

- **robtweed/EWD** (no SPDX-tagged license; project description says
  "free open source") — 86 `.m` files, post-2010 web/JSON framework
  for YottaDB / GT.M / Caché. Adds a third voice (different from the
  YottaDB-engine voice and the Munt engine-neutral voice).
- **shabiel/M-Web-Server** (Apache-2.0, 23 `.m`) — small contemporary
  HTTP server that runs on both YottaDB and Caché.

### Suggested layout

```
~/projects/m-modern-corpus/
├── ydbtest/                        # YottaDB/YDBTest (shallow clone)
├── mgsql/                          # chrisemunt/mgsql
├── ydbocto-aux/                    # YottaDB/YDBOcto, src/aux only
├── ewd/             (optional)
└── m-web-server/    (optional)
```

Then a `make lint-modern` target that walks each subtree the way
`make lint-vista` walks `~/vista-meta/vista/vista-m-host/Packages`.

---

## Caveats

0. **Tab-indented dot blocks** were a tree-sitter-m grammar gap until 2026-04-29 — scanner.c only treated `' '` as horizontal whitespace, so any line whose dot-block prefix used a leading TAB (the dominant style in YottaDB / YDBOcto code) failed to parse. Fix landed upstream in scanner.c + grammar.js (now accepting `[ \t]+` as `_sp1`/`_sp2plus`). Modern-corpus parse coverage rose from 888/4,215 routines (21%) to 3,470/4,215 (82%) with this fix alone. The remaining ~745 unparseable routines are mostly YottaDB-specific `$&package.function()` external-call syntax (a separate grammar gap) plus deliberate edge-case syntax in YDBTest.

1. **`.cls` is ObjectScript, not MUMPS — corpora are excluded.** ObjectScript
   is a *superset* of MUMPS that adds class declarations (UDL), OO
   operators (`..method`, `##class`, `$THIS`, `$$$macro`, relative-dot
   references, typed parameters), and embedded SQL/HTML/JS islands.
   `tree-sitter-m` parses the MUMPS subset only; even after stripping the
   `<Method>...</Method>` wrapper, ObjectScript bodies retain non-MUMPS
   tokens that produce parse errors and false-positive findings. The
   InterSystems repos that are predominantly `.cls` are catalogued under
   "Future / out-of-scope" rather than as gate candidates. They become
   candidates the day a `tree-sitter-objectscript` (or analogous) ships.
   `.mac` files are also IRIS/Caché-native but are routine bodies (not
   classes); InterSystems explicitly supports mixing ObjectScript and
   MUMPS in `.mac`, so treat as best-effort and skip files that fail to
   parse.
2. **YottaDB/YDBTest is engine-test code.** It deliberately exercises edge
   cases (deprecated syntax, error-recovery paths, esoteric `ZBREAK`
   patterns). Some "modern style" rules will fire on it because the code
   is *trying* to provoke the engine. Expect to mark a handful of
   directories (e.g. `v230/`, `r204/` — version-regression suites) as
   exempt or downgrade their findings.
3. **Test-fixtures vs production.** YDBOcto's 70-file `tests/fixtures/`
   directory is small queryable schemas — short, idiomatic, not "real
   application code." For lint training they're representative of how
   modern users build SQL-backed apps; for performance baselines they're
   non-representative because each file is tiny.
4. **License compatibility.** AGPL is fine for *running the linter against*
   the corpus (we don't redistribute their code). It does mean any
   AGPL-licensed corpus snapshot bundled into the m-cli repo would
   contaminate; clone-from-source at gate time is the safe path.
5. **GitHub vs GitLab.** All YottaDB repos are GitLab-primary, GitHub-mirror.
   Mirrors lag the upstream by minutes-to-hours — fine for a daily gate,
   not fine for "is this commit X+1 broken yet" queries. Use the GitLab
   URLs (`gitlab.com/YottaDB/...`) when you need authoritative state.
6. **`mac` vs `m`.** `.mac` files use the same M grammar but have an
   InterSystems-specific header comment. Trivial to strip; flag for the
   import script.
7. **FreeM mirror is stale.** The GitHub mirror at `CoherentLogic/freem`
   stopped at 2014. The maintained upstream is at
   `gitlab.coherent-logic.com/snw/freem` (Serena Willis fork). For an
   ANSI-95 reference corpus, clone *that*, not the GitHub mirror.
8. **`language:M` on GitHub is unreliable.** GitHub's Linguist conflates
   MUMPS/M with MATLAB, Mathematica, Power Query M, Objective-C `.m`, and
   Wolfram. Any future automated re-inventory script must filter by
   shebang / first-line / file-content heuristics, not by the Linguist
   tag alone. The entries in this catalog were verified by inspecting
   actual file contents.
