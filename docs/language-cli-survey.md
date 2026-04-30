# Language CLI Survey — Tooling Landscape and `m-cli` Gap Analysis

> **Purpose.** A comprehensive survey of the CLI toolchains shipped by five of the
> most popular modern programming languages, scored against their impact on
> developer productivity, code quality, and maintainability across the full
> software development life cycle (SDLC). Closes with a rank-ordered gap analysis
> for `m-cli` — the canonical CLI for the M (MUMPS) language.
>
> **Scope.** Five languages: **Rust, Go, Python, JavaScript/TypeScript, Java.**
> Chosen for top consistent rankings (TIOBE / Stack Overflow / GitHub Octoverse
> 2024–2026) and for spanning the design space — single-binary unified CLIs
> (Rust, Go), recently consolidated federated stacks (Python, JS/TS), and a
> heavyweight build-tool tradition (Java). C/C++ is intentionally omitted: it
> has no canonical CLI, and a survey of CMake / Ninja / Conan / vcpkg / Make
> would dilute the comparison.
>
> **Audience.** `m-cli` maintainers planning Tier 2+ work, and anyone evaluating
> what a "good" language CLI looks like in 2026.
>
> **Last updated.** 2026-04-29.

---

## 1. Ranking criteria — what makes a CLI tool valuable

Every CLI capability in this survey is rated on three axes, then collapsed into
a single 1–5 **Impact** score. The collapse is weighted toward productivity
because productivity gains compound: a tool that saves 30 seconds per edit is
felt every minute of every day, while a tool that catches one bug per quarter
is felt rarely.

| Axis | Weight | What we score |
|---|---|---|
| **Productivity** | 50% | Time saved per developer per day. Boilerplate eliminated. Context-switches avoided. Friction at the edit-test-debug loop. |
| **Code quality** | 30% | Defects caught before merge. Style consistency. Architectural drift detected. Type / contract violations surfaced. |
| **Maintainability** | 20% | Long-term cost of ownership. Onboarding time. Refactor safety. Dependency hygiene. CI / release reproducibility. |

### 1.1 Universal capability ranking

Across all five languages, the SDLC capabilities below are rank-ordered by
Impact. This ordering is the spine of the rest of the document — every
language section and the gap analysis use the same row order.

| Rank | Capability | Impact (1–5) | Why it ranks here |
|---:|---|:---:|---|
| 1 | **Test runner** (discovery + run + filter + watch) | 5 | The single highest-leverage tool. A fast, parser-aware test runner with single-test selection sets the cadence of the entire edit-test loop. |
| 2 | **Formatter** (canonical, idempotent) | 5 | Eliminates a whole category of code-review noise. Canonical layout makes diffs meaningful and reduces merge conflicts. |
| 3 | **Linter** (logic + style, fast on large corpora) | 5 | Catches defects at edit time. Fast feedback (sub-second per file) is the difference between "I'll fix that later" and "fixed before commit". |
| 4 | **Language Server (LSP)** | 5 | Diagnostics, hover, go-to-definition, completion, code actions. The IDE features developers feel constantly. The CLI's `lsp` subcommand is what binds the whole toolchain to the editor. |
| 5 | **Type checker / static analyzer** | 4 | Where the language has one. Catches contract violations across module boundaries that linters miss. |
| 6 | **Dependency / package manager** (resolve, lock, audit) | 4 | Reproducible builds, security audit, version-pin discipline. Painful when missing, invisible when present. |
| 7 | **Project scaffolder** (`new` / `init`) | 4 | Lowers the activation energy for new projects. Encodes idiomatic structure so every project starts the same way. |
| 8 | **Build / compile** | 4 | For compiled languages, the foundation. For interpreted, often subsumed by package-manager install. |
| 9 | **Coverage** | 4 | Quantifies test thoroughness. Per-line coverage with `lcov` output unlocks the entire CI / dashboard ecosystem (Codecov, Coveralls, genhtml). |
| 10 | **Watch mode** | 4 | TDD multiplier. Re-runs the right tests on save with no developer action. |
| 11 | **Pre-commit / git hooks integration** | 4 | Shifts quality gates left from CI to local. The cheapest place to fix a bug is the keyboard. |
| 12 | **Run / execute** (REPL or script entry) | 3 | Important for exploratory work; less so once a project has tests. |
| 13 | **Debugger / DAP** | 3 | High value when needed, but for many workflows the test runner + good logging substitute. |
| 14 | **Documentation generator** | 3 | Auto-generated API docs from comments / signatures. Underrated for libraries; lower priority for apps. |
| 15 | **Benchmark / micro-bench runner** | 2 | Critical for systems / library work; specialized otherwise. |
| 16 | **Profiler** (CPU / memory / allocations) | 2 | High value when performance matters. Specialized. |
| 17 | **Security audit** (dependency CVE scan) | 3 | Promoted from "specialized" to "table stakes" by the SBOM era. Often a thin wrapper around an upstream advisory database. |
| 18 | **Publish / release** (registry push, version bump) | 3 | Important for libraries; mostly invisible for apps. |
| 19 | **Toolchain / version manager** | 2 | One-time setup cost. Important for polyglot teams; invisible once configured. |
| 20 | **Migration / upgrade codemods** | 2 | High peak value during major version bumps; otherwise dormant. |
| 21 | **CI / scaffolding helper** (`ci` subcommand) | 2 | Generates a working pipeline file. Nice-to-have; most teams write CI once and forget it. |

**How to read the language tables.** Each section uses the same row order so
you can scan vertically for a single capability across languages, or
horizontally for a single language across capabilities.

---

## 2. Per-language CLI surveys

### 2.1 Rust — `cargo`

**Design philosophy.** A single, opinionated, batteries-included CLI. `cargo`
is the gold-standard reference for "one tool, all SDLC phases" — ergonomic
defaults, deterministic builds, integrated registry. Almost every external
Rust tool plugs in as a `cargo <name>` subcommand discovered on `$PATH`.

| Capability | Tool / subcommand | Notes |
|---|---|---|
| Test runner | `cargo test` | Built-in. Per-test filter (`cargo test name`), parallel by default, captures stdout. Doc-tests integrated. |
| Formatter | `cargo fmt` (rustfmt) | Canonical layout, configurable via `rustfmt.toml`. Idempotent. |
| Linter | `cargo clippy` | 750+ lints, severity-tunable, autofix via `--fix`. Runs alongside the type checker. |
| Language Server | `rust-analyzer` | Industry-leading LSP. Inlay hints, semantic tokens, structural search/replace, macro expansion preview. |
| Type checker | `cargo check` | Type-checks without codegen. The killer feature: a fast feedback loop on a fully type-checked program. |
| Dependency manager | `cargo` (Cargo.toml + Cargo.lock) | Strict semver, precise lock, workspace support, feature flags, build scripts. |
| Project scaffolder | `cargo new` / `cargo init` | `--lib` vs `--bin`, edition pinning, git init included. |
| Build | `cargo build` | Incremental, parallel, profile-aware (dev / release / custom). Cross-compilation via `--target`. |
| Coverage | `cargo llvm-cov` (community) / `cargo tarpaulin` | LLVM source-based coverage; `lcov` + HTML output. |
| Watch | `cargo watch` (community) | `cargo watch -x test`. Filesystem-event driven. |
| Pre-commit / hooks | community pre-commit hooks; `cargo fmt --check` + `cargo clippy --deny warnings` | Idiomatic CI: fmt-check + clippy-deny. |
| Run | `cargo run` | Build + execute the default binary. `--bin`, `--example`, args after `--`. |
| Debugger | `rust-gdb` / `rust-lldb` wrappers | Type-aware pretty-printers. DAP via CodeLLDB. |
| Doc generator | `cargo doc` | Renders Markdown doc-comments to a navigable HTML site; doc-tests are real tests. |
| Benchmark | `cargo bench` (nightly) / `criterion` crate | Statistical micro-benchmarking; HTML reports. |
| Profiler | `cargo flamegraph` (community) | Wraps perf / dtrace; SVG flamegraph output. |
| Security audit | `cargo audit` | Queries RustSec advisory DB; CI-friendly exit codes. |
| Publish | `cargo publish` | One-command release to crates.io with checksum verification. |
| Toolchain mgr | `rustup` | Channel management (stable / beta / nightly), per-project pin via `rust-toolchain.toml`. |
| Migration / codemod | `cargo fix --edition` | Edition migrations applied automatically; `cargo clippy --fix` for lint-driven rewrites. |
| CI scaffolding | none built-in | Community: `cargo-generate` templates with CI included. |

**Special features.**
- **Workspaces.** Multi-crate monorepos with a single `Cargo.lock`.
- **Features.** Conditional compilation flags expressed as a dependency-graph property — first-class in the resolver.
- **Build scripts (`build.rs`).** Compile-time codegen / linking. Fully typed Rust, not a foreign DSL.
- **Cross-compilation.** First-class via `--target`; `cargo` orchestrates the linker swap.
- **Subcommand discovery.** Any `cargo-foo` binary on `$PATH` becomes `cargo foo`. The ecosystem extends without forking the CLI.

---

### 2.2 Go — `go`

**Design philosophy.** "The `go` command is the language." A single binary
that does everything, with deliberately minimal configuration. Convention over
configuration taken to its extreme: directory layout, import paths, and test
file names are all standardized by the tool itself.

| Capability | Tool / subcommand | Notes |
|---|---|---|
| Test runner | `go test ./...` | Built-in. `-run` regex filter, table-driven idiom standardized. `-race` flag enables the race detector. |
| Formatter | `gofmt` / `go fmt` | The progenitor of all language formatters. No options — there is one canonical Go layout, period. |
| Linter | `go vet` (built-in) / `golangci-lint` (community meta-linter) | `golangci-lint` aggregates 100+ linters behind one config. The de-facto standard. |
| Language Server | `gopls` | Official, ships with the toolchain. Hover, go-to-def, refactor, code actions. |
| Type checker | `go build` / `go vet` | Compile-time only — Go has no separate type-checker pass. |
| Dependency manager | `go mod` (`tidy`, `get`, `vendor`, `download`) | Module-aware since 1.11. Minimum version selection (MVS); `go.sum` for checksums. |
| Project scaffolder | `go mod init <path>` | Minimal — creates `go.mod`. No `src/` / test directory conventions enforced beyond the language. |
| Build | `go build` | Single static binary by default. Fast incremental compilation; cross-compile via `GOOS` / `GOARCH`. |
| Coverage | `go test -cover` / `go test -coverprofile=cover.out` + `go tool cover` | Built-in. HTML + text reports; `lcov` via community converter. |
| Watch | community: `air`, `reflex`, `entr` | Not built-in. |
| Pre-commit / hooks | community pre-commit hooks for `gofmt` / `go vet` / `golangci-lint` | Idiomatic CI: `gofmt -l` exit-1 on diff. |
| Run | `go run main.go` | Compile-and-run in one step; binary goes to a temp dir. |
| Debugger | `dlv` (Delve) | Native Go debugger; DAP support for editors. |
| Doc generator | `go doc` / `pkg.go.dev` | Comments above exported identifiers become public docs automatically. |
| Benchmark | `go test -bench=.` | Built-in. Statistical comparison via `benchstat` (community). |
| Profiler | `go test -cpuprofile` / `go tool pprof` | Built-in CPU / heap / goroutine profilers. Web UI included. |
| Security audit | `govulncheck` | Official. Reports only vulnerabilities the program actually reaches (call-graph aware). |
| Publish | implicit — push a tagged commit | No central registry. Modules are git-resolvable URLs; `pkg.go.dev` indexes them automatically. |
| Toolchain mgr | `go install golang.org/dl/go1.22@latest` / `gvm` (community) | Toolchain pinning via `go` directive in `go.mod` since 1.21. |
| Migration / codemod | `go fix` | Largely dormant since Go 1; reserved for breaking-language-change migrations. |
| CI scaffolding | none built-in | |

**Special features.**
- **Race detector.** `go test -race` instruments the binary at compile time. Built-in. No competing language has anything comparable that ships in the toolchain.
- **`go generate`.** A convention for invoking codegen tools; comments like `//go:generate stringer -type=Pill` are picked up by `go generate ./...`.
- **Workspace mode (`go work`).** Multi-module local development without vendoring or replace directives.
- **Vulnerability checking is reachability-aware.** `govulncheck` only reports CVEs whose vulnerable function is actually called by your code — far less noise than naive dependency scanners.
- **Single static binary.** The build artifact is a single file with no runtime dependency. Deployment is `scp`.

---

### 2.3 Python — `uv` + `ruff` + `pytest` (the 2024–2026 consolidation)

**Design philosophy.** Historically federated — `pip`, `virtualenv`, `setuptools`,
`flake8`, `black`, `isort`, `mypy`, `pytest` — with each tool in its own repo
and config file. The 2024–2026 consolidation has collapsed the front of the
stack into two Rust-implemented tools (`uv` for env/deps, `ruff` for fmt/lint),
which together account for ~95% of daily developer interactions.

| Capability | Tool / subcommand | Notes |
|---|---|---|
| Test runner | `pytest` | De-facto standard. Fixtures, parametrize, plugins, parser-aware collection. `-k` filter, `-x` fail-fast, `--lf` last-failed. |
| Formatter | `ruff format` | Black-compatible output; ~30× faster. Drop-in replacement. |
| Linter | `ruff check` | 800+ rules across pyflakes / pycodestyle / pylint / isort / pyupgrade / bugbear etc. Autofix via `--fix`. Sub-second on large repos. |
| Language Server | `pyright` (Microsoft) / `pylsp` / `ruff server` | Pyright is the type-checker LSP; `ruff server` covers fmt + lint diagnostics. |
| Type checker | `mypy` / `pyright` / `pyre` | Gradual typing; project-level config. `mypy --strict` is the common quality bar. |
| Dependency manager | `uv` (`add`, `remove`, `lock`, `sync`) / `pip` / `poetry` / `pdm` | `uv` reads `pyproject.toml`, writes `uv.lock`. Resolves an environment in seconds. |
| Project scaffolder | `uv init` / `cookiecutter` (community) | `uv init --lib` / `--app`. Cookiecutter is the long-tail templating standard. |
| Build | `uv build` / `python -m build` | Produces wheels + sdists per PEP 517 / 518. |
| Coverage | `coverage.py` + `pytest-cov` | `pytest --cov=src --cov-report=term --cov-report=lcov`. The reference implementation for lcov output. |
| Watch | `pytest-watch` / `entr` / `watchexec` | No first-class watch; community plugins or external tools. |
| Pre-commit / hooks | `pre-commit` framework (Python project, language-agnostic) | Authoritative — every other ecosystem in this survey integrates _via_ pre-commit. |
| Run | `python` / `python -m mod` / `uv run` | `uv run` resolves the env on demand and executes — no manual activate. |
| Debugger | `pdb` / `pytest --pdb` / `debugpy` (DAP) | `breakpoint()` builtin opens `pdb` since 3.7. |
| Doc generator | `sphinx` / `mkdocs` / `pdoc` | Sphinx is the entrenched library standard; mkdocs the modern docs-site choice. |
| Benchmark | `pytest-benchmark` / `hyperfine` (language-agnostic) | Statistical comparison via `--benchmark-compare`. |
| Profiler | `cProfile` (stdlib) / `py-spy` / `scalene` / `pyinstrument` | `py-spy` is sampling, no code change needed; scalene profiles CPU + memory + GPU. |
| Security audit | `pip-audit` / `safety` | Queries PyPI Advisory DB. CI-friendly. |
| Publish | `uv publish` / `twine upload` | Push wheels to PyPI. |
| Toolchain mgr | `uv python install 3.12` / `pyenv` | `uv` ships interpreter management since 0.4. |
| Migration / codemod | `pyupgrade` / `ruff --select=UP` / `libcst` codemods | `ruff` covers most version-upgrade rewrites. |
| CI scaffolding | `tox` (matrix runner) / `nox` (Python-config tox) | Not strict scaffolding — define a matrix once, run locally and in CI. |

**Special features.**
- **`uv run`.** Ephemeral environments resolved per-invocation. `uv run --with httpx python script.py` — no project, no venv, just run.
- **`ruff` config in `pyproject.toml`.** Single-file lint + format config; supports per-file overrides via `[tool.ruff.lint.per-file-ignores]`.
- **`pytest` fixtures.** Dependency-injected setup / teardown; the most copied test-runner idea in the industry.
- **PEP 723 inline script metadata.** Dependencies declared in a script's header comment; `uv run script.py` resolves them. Reproducible single-file scripts.
- **Plugin ecosystem.** `pytest-*` plugins (1000+) cover everything from snapshot testing to async to property-based.

---

### 2.4 JavaScript / TypeScript — `npm` / `pnpm` / `bun` + `biome` / `eslint` + `vitest`

**Design philosophy.** The most fragmented ecosystem in this survey, and the
fastest-moving. Multiple package managers (npm, pnpm, yarn, bun), competing
formatters (prettier, biome, dprint), competing linters (eslint, biome,
oxlint), competing test runners (jest, vitest, node:test, bun test) — but
near-uniform config conventions (`package.json` + `tsconfig.json`) across all
of them. TypeScript adds a separate compiler / type-checker layer (`tsc`).

| Capability | Tool / subcommand | Notes |
|---|---|---|
| Test runner | `vitest` / `jest` / `node --test` / `bun test` | `vitest` is the modern default — Vite-powered, ESM-native, watch mode built in. `node --test` is now built-in. |
| Formatter | `biome format` / `prettier --write` / `dprint fmt` | `biome` is Rust-based, ~25× faster than `prettier`. Prettier remains entrenched. |
| Linter | `biome lint` / `eslint` / `oxlint` | `eslint` is the established standard with 1000s of plugins; `biome` and `oxlint` are the fast Rust-based challengers. |
| Language Server | `typescript-language-server` / `vtsls` / `biome lsp-proxy` | Editors typically run `tsserver` (bundled with TypeScript) for type info plus `biome` / `eslint` LSPs for diagnostics. |
| Type checker | `tsc --noEmit` | TypeScript compiler in type-check-only mode. Slow; `tsgo` (Go-rewrite, in progress) targets 10× speedup. |
| Dependency manager | `npm` / `pnpm` / `yarn` / `bun` | `pnpm` saves disk via content-addressed store + symlinks; `bun` is fastest end-to-end. `package.json` + lockfile. |
| Project scaffolder | `npm init` / `npm create vite` / `degit` | `npm create <template>` is the canonical scaffolder pattern. |
| Build | `tsc` / `esbuild` / `swc` / `vite build` / `bun build` | Many bundlers; `vite` is the modern app default, `tsup` / `unbuild` for libraries. |
| Coverage | `vitest --coverage` / `c8` / `jest --coverage` | Built on V8 native coverage; `lcov` output standard. |
| Watch | `vitest` (default) / `tsc --watch` / `nodemon` / `tsx --watch` | Watch is so universal it's the default mode for most tools. |
| Pre-commit / hooks | `husky` + `lint-staged` | The dominant local hooks pair; `simple-git-hooks` is the lighter alternative. |
| Run | `node` / `tsx` / `ts-node` / `bun` | `tsx` runs TS without a build step; `bun` runs TS natively. |
| Debugger | `node --inspect` + Chrome DevTools / VS Code DAP | `--inspect-brk` to break at start. |
| Doc generator | `typedoc` / `api-extractor` (Microsoft) | Generates from TS types + TSDoc. |
| Benchmark | `vitest bench` / `tinybench` / `mitata` | `vitest bench` integrates statistically with the test runner. |
| Profiler | `node --prof` / `clinic.js` / Chrome DevTools | `clinic doctor` / `clinic flame` / `clinic bubbleprof` — opinionated workflows. |
| Security audit | `npm audit` / `pnpm audit` / `socket` | `socket` adds supply-chain heuristics beyond CVE scanning. |
| Publish | `npm publish` | The original public package registry. `--provenance` for SLSA attestation. |
| Toolchain mgr | `nvm` / `fnm` / `volta` / `corepack` | `corepack` (built-in to Node) pins package-manager version per project. |
| Migration / codemod | `jscodeshift` / `ast-grep` / `codemod` (CLI) | `react`, `next`, `mui` ship dedicated codemods for major version bumps. |
| CI scaffolding | none built-in | Templates from `create-*` packages typically include GitHub Actions. |

**Special features.**
- **`package.json` scripts.** A universal task runner — `npm run build` is the lowest-common-denominator entry point across the entire ecosystem.
- **`workspaces` / monorepos.** Native in npm 7+ / pnpm / yarn / bun; tools like `turbo` and `nx` add caching and task orchestration on top.
- **`exports` field.** Per-environment entry points (ESM / CJS / browser / Node) declared in `package.json` and resolved by every bundler.
- **Provenance attestation.** `npm publish --provenance` produces a signed SLSA statement linking the published artifact to the source commit and CI run.
- **Type-checking is opt-in.** TypeScript is technically separate; `tsc` is invoked explicitly. The type checker is the slowest part of the toolchain — hence the ongoing rewrites in Go (`tsgo`) and Rust (`stc`).

---

### 2.5 Java — `mvn` / `gradle` + JDK tools

**Design philosophy.** The build tool _is_ the SDLC orchestrator. `mvn` and
`gradle` are not narrow CLIs — they are configurable lifecycle engines with
hundreds of plugins. A `mvn package` invocation runs validate → compile →
test → package → verify by convention. The trade-off is verbosity and slower
startup than newer ecosystems, but unmatched plugin coverage and 25 years of
enterprise hardening.

| Capability | Tool / subcommand | Notes |
|---|---|---|
| Test runner | `mvn test` / `gradle test` (JUnit / TestNG / Spock) | JUnit 5 (Jupiter) is the modern default. Lifecycle hooks, parametrized tests, dynamic tests. |
| Formatter | `google-java-format` / `spotless` (gradle / maven plugin) | `spotless:apply` / `spotless:check`. Multi-language (Java, Kotlin, Groovy). |
| Linter | `checkstyle` / `pmd` / `spotbugs` / `error-prone` | Each via maven/gradle plugin. `error-prone` runs as a javac plugin — lints during compile. |
| Language Server | `eclipse.jdt.ls` | The Eclipse JDT Language Server; powers VS Code Java, Theia, etc. |
| Type checker | `javac` (built-in) | Static typing is mandatory. Annotation processors extend the type system at compile time. |
| Dependency manager | `mvn` / `gradle` (Maven Central) | XML (`pom.xml`) vs Groovy/Kotlin DSL (`build.gradle[.kts]`). Transitive resolution + dependency reports. |
| Project scaffolder | `mvn archetype:generate` / `gradle init` / `spring init` | Spring Initializr is the de-facto starter for Spring Boot. |
| Build | `mvn package` / `gradle build` / `javac` | Incremental compile + JAR / WAR / native image (GraalVM). |
| Coverage | `jacoco` (maven / gradle plugin) | XML / HTML / CSV reports; `lcov` via converter. |
| Watch | `gradle --continuous` / `quarkus dev` / `spring-boot:run` (with devtools) | Spring Boot DevTools and Quarkus Dev Mode are the productivity headline features. |
| Pre-commit / hooks | `spotless:check` + `git-code-format-maven-plugin` / `pre-commit` framework | |
| Run | `java -jar` / `mvn exec:java` / `gradle run` / `jbang` | `jbang` runs single-file scripts with deps — closest Java has to `python script.py`. |
| Debugger | `jdb` / IDE-driven JDWP | `--debug` opens a JDWP port; every IDE attaches. |
| Doc generator | `javadoc` (built-in) | Generates HTML API docs from `/** ... */` comments. The original. |
| Benchmark | `jmh` (Java Microbenchmark Harness) | OpenJDK-grade benchmarking; statistical, JIT-aware. The reference for JVM-language benchmarking. |
| Profiler | `jfr` (Java Flight Recorder) / `async-profiler` / `jvisualvm` | JFR is built into the JDK — production-safe, low-overhead, always-on capable. |
| Security audit | `mvn dependency-check:check` (OWASP) / `gradle dependencyCheck` | Cross-references the NVD; SARIF + HTML reports. |
| Publish | `mvn deploy` / `gradle publish` (Sonatype OSSRH → Maven Central) | GPG-signed artifacts; SBOM via CycloneDX plugin. |
| Toolchain mgr | `sdkman` / `jenv` / `mvn`/`gradle` toolchains spec | Toolchains can be declared per-project; the build tool downloads the JDK on demand. |
| Migration / codemod | `OpenRewrite` / `error-prone --fix` / `jdeps` | `OpenRewrite` is the sophisticated codemod platform — recipes for Spring upgrades, JUnit 4 → 5, etc. |
| CI scaffolding | `mvn` / `gradle` wrappers (`mvnw` / `gradlew`) | Wrappers pin the build-tool version per repo — every CI runs the same Maven / Gradle. |

**Special features.**
- **Build-tool wrappers.** `mvnw` / `gradlew` make the build reproducible across dev machines and CI without a global install. The most copied idea in this row of the table.
- **JFR (Java Flight Recorder).** Continuous, low-overhead production profiling shipped in the JDK. Nothing comparable in the other four ecosystems.
- **Annotation processors.** Compile-time codegen / validation extending the type system (Lombok, MapStruct, Dagger, etc.).
- **Toolchain auto-provisioning.** Gradle / Maven download the required JDK if the local one doesn't match — no manual `apt install` step.
- **OpenRewrite.** Codemods written as recipes; a recipe can refactor across thousands of repositories deterministically. State of the art for large-scale migrations.

---

## 3. Cross-language summary table

Same row order as §1.1. Cells show the canonical tool (or "—" if not standard
in the ecosystem). For capabilities with multiple credible options, the
incumbent default is listed first.

| Capability | Rust (`cargo`) | Go (`go`) | Python (`uv`/`ruff`) | JS/TS (`npm`/`biome`) | Java (`mvn`/`gradle`) |
|---|---|---|---|---|---|
| Test runner | `cargo test` | `go test` | `pytest` | `vitest` / `jest` / `node --test` | `mvn test` (JUnit 5) |
| Formatter | `cargo fmt` (rustfmt) | `gofmt` | `ruff format` | `biome format` / `prettier` | `spotless` / `google-java-format` |
| Linter | `cargo clippy` | `go vet` + `golangci-lint` | `ruff check` | `biome lint` / `eslint` | `checkstyle` / `error-prone` |
| Language Server | `rust-analyzer` | `gopls` | `pyright` / `ruff server` | `tsserver` + `biome` | `eclipse.jdt.ls` |
| Type checker | `cargo check` | `go build` (compile-time) | `mypy` / `pyright` | `tsc --noEmit` | `javac` (compile-time) |
| Dependency mgr | `cargo` (Cargo.lock) | `go mod` (go.sum) | `uv` (uv.lock) | `npm` / `pnpm` (lockfile) | `mvn` / `gradle` (Maven Central) |
| Scaffolder | `cargo new` | `go mod init` | `uv init` / `cookiecutter` | `npm create <template>` | `mvn archetype` / `spring init` |
| Build | `cargo build` | `go build` | `uv build` (PEP 517) | `vite build` / `tsc` / `esbuild` | `mvn package` / `gradle build` |
| Coverage | `cargo llvm-cov` | `go test -cover` | `pytest --cov` | `vitest --coverage` / `c8` | `jacoco` |
| Watch | `cargo watch` | `air` / `reflex` | `pytest-watch` / `entr` | `vitest` (built-in) / `tsx --watch` | `gradle --continuous` |
| Pre-commit | community hooks | community hooks | `pre-commit` (canonical) | `husky` + `lint-staged` | `spotless:check` |
| Run | `cargo run` | `go run` | `uv run` / `python` | `node` / `tsx` / `bun` | `java -jar` / `jbang` |
| Debugger | `rust-gdb` / `lldb` (DAP) | `dlv` (DAP) | `pdb` / `debugpy` (DAP) | `node --inspect` (DAP) | `jdb` / JDWP |
| Doc generator | `cargo doc` | `go doc` / pkg.go.dev | `sphinx` / `mkdocs` / `pdoc` | `typedoc` | `javadoc` |
| Benchmark | `cargo bench` / `criterion` | `go test -bench` | `pytest-benchmark` | `vitest bench` / `tinybench` | `jmh` |
| Profiler | `cargo flamegraph` / perf | `go tool pprof` | `py-spy` / `scalene` | `clinic.js` / DevTools | `jfr` / `async-profiler` |
| Security audit | `cargo audit` | `govulncheck` (reachability) | `pip-audit` | `npm audit` / `socket` | OWASP dependency-check |
| Publish | `cargo publish` (crates.io) | tag + push (no registry) | `uv publish` (PyPI) | `npm publish` (registry) | `mvn deploy` (Maven Central) |
| Toolchain mgr | `rustup` | `go install golang.org/dl` | `uv python install` / `pyenv` | `nvm` / `fnm` / `corepack` | `sdkman` / Gradle toolchains |
| Migration / codemod | `cargo fix --edition` | `go fix` (mostly dormant) | `ruff --fix` / `pyupgrade` | `jscodeshift` / `ast-grep` | `OpenRewrite` |
| CI scaffolding | — | — | `tox` / `nox` matrix | — (template-driven) | `mvnw` / `gradlew` wrappers |

**Patterns visible across the table.**

1. **Unified single-binary CLIs (Rust, Go) win on cohesion.** Every SDLC phase reachable with `cargo X` / `go X`. The cost is lock-in to the language's vision; the benefit is zero discovery friction for newcomers.
2. **Recently consolidated stacks (Python via `uv` + `ruff`) approach the unified-CLI feel without giving up plugin diversity.** The Python toolchain in 2026 is closer to Rust's UX than to its own 2020 self.
3. **JS/TS has the most options at every layer and the fastest-evolving runtime.** `bun`, `vite`, `biome`, `oxlint` are all <5 years old and already mainstream. Choice is the productivity tax.
4. **Java's plugin model is the most extensible.** Anything is a Maven / Gradle plugin away — at the cost of a multi-second JVM startup per invocation.
5. **Built-in capabilities migrate up the stack over time.** Watch mode (in vitest), coverage (in `go test`), security audit (`govulncheck`) — all started as community add-ons and were absorbed into the canonical CLI. The trajectory is toward fewer external dependencies.

---

## 4. `m-cli` gap analysis

This section enumerates every capability the five surveyed languages ship and
maps each to `m-cli`'s current state. Columns:

- **Capability** — the SDLC role.
- **Reference tools** — what the surveyed languages call this.
- **`m-cli` state** — Done / Partial / Missing / N/A.
- **Gap rank** — 1 (highest priority to close) → N (lowest). Combines impact
  (§1.1) with the realistic difficulty of building it for M and the size of
  the audience that would feel it.

| # | Capability | Reference tools | `m-cli` state | Notes |
|---:|---|---|:---:|---|
| 1 | Test runner | `cargo test` / `pytest` / `go test` / `vitest` / `mvn test` | ✅ **Done** | `m test` — parser-aware discovery, ydb runner, single-test selection (`FILE.m::tLabel`), text / TAP / JSON output. Smoke gate: 11 m-tools suites / 224 assertions. |
| 2 | Formatter | `rustfmt` / `gofmt` / `ruff format` / `biome` / `spotless` | ✅ **Done** | `m fmt` — identity round-trips 99.04% byte-for-byte across 38,954 VistA routines; `--rules=canonical` is idempotent + AST-preserving. |
| 3 | Linter | `clippy` / `golangci-lint` / `ruff check` / `eslint` / `error-prone` | ✅ **Done** | `m lint --rules=xindex` — 42 of XINDEX's 66 rules ship; cross-routine + control-flow rules; inline `; m-lint: disable=` directives; full VistA in 22.6 s on 16 cores (5.3× under budget). |
| 4 | Language Server | `rust-analyzer` / `gopls` / `pyright` / `tsserver` / `eclipse.jdt.ls` | ✅ **Done** | `m lsp` — diagnostics, formatting, code actions, hover, completion, document symbols, code lenses, folding, signature help, document highlight, go-to-definition, find-references, workspace symbol, incremental index. |
| 5 | Type checker | `cargo check` / `mypy` / `tsc` / `javac` | ⚠️ **N/A** | M is dynamically typed with no static-typing convention. A gradual-typing experiment (annotations in M comments, checked by `m typecheck`) is conceivable but speculative — no demand signal yet. **Skip unless requested.** |
| 6 | Dependency / package manager | `cargo` / `go mod` / `uv` / `npm` / `mvn` | ❌ **Missing** | M has no public package registry. Routines are distributed via VistA fileman / CCR / vendor tarballs. Building `m pkg` is conceivable (git-resolvable routine bundles, `M-PKG.toml`) but is a meta-project, not a CLI feature. **Gap rank 6** — high impact, very high effort. |
| 7 | Project scaffolder | `cargo new` / `go mod init` / `uv init` / `npm create` / `mvn archetype` | ❌ **Missing** | `m new <name>` would create a routine + `<name>TST.m` test scaffold + `.m-cli.toml` + `.gitignore` + `routines/` layout. Cheap to build, real activation-energy reduction for new M projects. **Gap rank 2.** |
| 8 | Build / compile | `cargo build` / `go build` / `tsc` / `mvn package` | ⚠️ **Partial / engine-owned** | `ydb` compiles routines on first call (`.m` → `.o`). `m build` could front-end this (warm-compile a directory, surface compile errors uniformly). Low-medium value — most users let ydb compile lazily. **Gap rank 9.** |
| 9 | Coverage | `cargo llvm-cov` / `go test -cover` / `pytest --cov` / `vitest --coverage` / `jacoco` | ✅ **Done** | `m coverage` — Phase C. YDB `view "TRACE"` for per-line counts; label-level 85/123 = 69.1% on m-tools (byte-identical to `ycover`); line-level 340/637 = 53.4%. Outputs: text / text --lines / json / lcov. |
| 10 | Watch | `cargo watch` / `air` / `pytest-watch` / `vitest` / `gradle --continuous` | ✅ **Done** | `m watch` — polling-based (0.5 s default), source→suite affinity (`FOO.m → FOOTST.m`), `--once` for smoke checks. Pure Python, no extra deps. |
| 11 | Pre-commit / hooks | `pre-commit` framework hooks across all five | ✅ **Done** | `.pre-commit-hooks.yaml` exposes `m-fmt-check`, `m-fmt`, `m-lint`. Schema gated by `tests/test_pre_commit_hooks.py`. Activation pending PyPI publish. |
| 12 | Run / execute | `cargo run` / `go run` / `uv run` / `node`/`bun` / `java -jar` | ⚠️ **Partial (engine-owned)** | `ydb -run ^ROUTINE` is the canonical entry; users invoke it directly. `m run ROUTINE` could wrap it (env composition, exit-code mapping). Low value — the engine command is short. **Gap rank 11.** |
| 13 | Debugger / DAP | `lldb` / `dlv` / `debugpy` / `node --inspect` / JDWP | ⏸️ **Deferred** | Per CLAUDE.md, DAP is its own engineering project; both engines ship `ZBREAK` at the engine level. **Gap rank 5** — high developer-felt value, large engineering scope. |
| 14 | Doc generator | `cargo doc` / `go doc` / `sphinx` / `typedoc` / `javadoc` | ❌ **Missing** | `m doc` could extract `;;` documentation comments + label / formal signatures into Markdown / HTML. M has the `;;` doc-comment convention used by VistA (`Z*` utilities, etc.) — a low-friction starter. **Gap rank 4.** |
| 15 | Benchmark | `cargo bench` / `go test -bench` / `pytest-benchmark` / `vitest bench` / `jmh` | ❌ **Missing** | `m bench` could discover `b<UpperCase>` labels in `*BCH.m` files and report ops/sec. M's `$ZH` provides high-resolution timing. Niche but cheap to build atop the existing test runner architecture. **Gap rank 10.** |
| 16 | Profiler | `cargo flamegraph` / `pprof` / `py-spy` / `clinic.js` / JFR | ❌ **Missing** | YDB's `view "TRACE"` (already wired for coverage) carries enough per-line execution-count data to render a flat profile or flamegraph. **Gap rank 7** — meaningful payoff, manageable engineering. |
| 17 | Security audit | `cargo audit` / `govulncheck` / `pip-audit` / `npm audit` / OWASP | ⚠️ **N/A today** | Not meaningful without a package ecosystem (#6). Also: M's most relevant security concern is SQL/Mumps-injection / `XECUTE` of tainted input — that's a **lint rule territory** (e.g. taint analysis), not a dependency CVE scanner. **Reframe as lint rule.** |
| 18 | Publish / release | `cargo publish` / `npm publish` / `uv publish` / `mvn deploy` | ❌ **Missing** | Same dependency as #6 — needs a registry to publish to. **Defer.** |
| 19 | Toolchain / version mgr | `rustup` / `nvm` / `uv python` / `sdkman` | ⚠️ **N/A** | M engines (YottaDB / GT.M / Caché / IRIS) install via vendor packages, not language-version managers. `m doctor` (env diagnostic) is a closer fit — checks `$ydb_dist`, `$ydb_routines`, parser availability. **Gap rank 8** — small, high-leverage. |
| 20 | Migration / codemod | `cargo fix --edition` / `ruff --fix` / `OpenRewrite` / `jscodeshift` | ⚠️ **Partial** | `m fmt --rules=canonical` already does mechanical rewrites (uppercase keywords, trim trailing whitespace). A general codemod facility (named recipes, structural search/replace over the M tree-sitter grammar) would generalize this. **Gap rank 3.** |
| 21 | CI scaffolding | `mvn`/`gradle` wrappers / template bundles | ❌ **Missing** | `m ci init` could emit a working GitHub Actions workflow running `m fmt --check`, `m lint --error-on=fatal`, `m test`, `m coverage --format=lcov`. Low effort, real lift for greenfield M projects. **Gap rank 12.** |

### 4.1 Gap rank-ordered punch list

The 12 gaps from the table above, ordered by recommended priority. Use this as
input to Tier 3+ planning.

| Rank | Gap | Recommended next action | Approx effort | Why this rank |
|---:|---|---|:---:|---|
| 1 | _(none — top 5 surveyed essentials all shipped)_ | — | — | `m test`, `m fmt`, `m lint`, `m lsp`, `m coverage`, `m watch` are all Done. m-cli already covers the highest-impact rows of §1.1. |
| 2 | **Project scaffolder** (`m new`) | Add `m new <name>` — creates routine + `<name>TST.m` + `.m-cli.toml` + `routines/` layout. | S (1–2 days) | Cheap, encodes idiomatic structure, lowers activation energy. |
| 3 | **Codemod / structural fix** (`m fix`) | Generalize `m fmt --rules=canonical` into named recipes + tree-sitter pattern engine (à la `ast-grep`). | M (1–2 weeks) | Generalizes existing infrastructure; unlocks future XINDEX rule autofixes beyond the current two pairings. |
| 4 | **Doc generator** (`m doc`) | Extract `;;` comments + label signatures into Markdown / HTML. | S (3–5 days) | M already has a doc-comment convention; mostly a serializer. |
| 5 | **Debugger / DAP** (`m debug`) | Wrap ydb `ZBREAK` + `ZSTEP` behind a DAP server. | L (4–6 weeks) | High developer-felt value, but large scope — own project per CLAUDE.md. |
| 6 | **Package manager** (`m pkg`) | Define a routine-bundle manifest (`M-PKG.toml`); resolve from git URLs. | XL (months) | Highest leverage, but a meta-project. Premature without ecosystem buy-in. |
| 7 | **Profiler** (`m profile`) | Render YDB `view "TRACE"` line counts as flat profile + flamegraph SVG. | M (1–2 weeks) | Reuses coverage trace plumbing; serious payoff for performance work. |
| 8 | **Doctor** (`m doctor`) | Diagnose `$ydb_dist`, `$ydb_routines`, parser, m-standard data files; exit-1 on broken env. | S (1 day) | Tiny effort, eliminates a whole class of "why doesn't it work" tickets. |
| 9 | **Build / warm compile** (`m build`) | Front-end `ydb` routine compile; uniform error reporting. | S (3–5 days) | Marginal — `ydb` compiles lazily and developers rarely think about it. |
| 10 | **Benchmark** (`m bench`) | `b<UpperCase>` labels in `*BCH.m` files; `$ZH` timing; ops/sec reporting. | S (3–5 days) | Niche; small audience; reuses test-discovery code. |
| 11 | **Run wrapper** (`m run`) | Wrap `ydb -run`; env composition + exit-code mapping. | XS (hours) | Saves a few keystrokes; near-zero quality impact. |
| 12 | **CI scaffolding** (`m ci init`) | Emit a working GitHub Actions YAML. | XS (hours) | One-time per project; low ongoing impact. |

### 4.2 Items deliberately not on the gap list

Recording these so future planning rounds don't re-litigate the decision.

- **Type checker.** No demand signal; M has no typing convention. Revisit if a gradual-typing proposal emerges in m-standard.
- **Toolchain manager.** YDB / GT.M install via vendor packages; not a language-version-manager problem. `m doctor` covers the realistic need.
- **Security audit.** Without a package registry there are no third-party deps to scan. The injection-style concerns belong in lint rules (taint analysis on `XECUTE` arguments), not a separate `m audit` subcommand.
- **Publish.** Blocked on package manager (#6); defer until that lands.

---

## 5. Conclusions

1. **`m-cli` already ships the top five highest-impact CLI capabilities** from
   §1.1 — test runner, formatter, linter, LSP, coverage — plus watch mode and
   pre-commit integration. By the universal scoring rubric, the existing CLI
   covers ~70% of the developer-facing weight of a modern language toolchain.

2. **The realistic Tier 3 priorities are the small, high-leverage gaps**:
   `m new` (scaffolder), `m fix` (codemod), `m doc`, `m doctor`. Each is days
   to a couple of weeks; each lands a concrete user-visible improvement.

3. **The big-ticket gaps (`m pkg`, `m debug`) are real but should be treated
   as their own engineering projects.** Both are meta-features that change the
   language's ecosystem, not just its CLI. Approach with a separate plan, not
   a Tier-N punch line.

4. **`m-cli`'s closest design analogue is `cargo`** — single dispatcher, dense
   subcommand surface, opinionated defaults, library API for tooling
   consumers. The `cargo`-style growth path (community subcommands discovered
   on `$PATH` as `m-foo`) is worth considering once the subcommand surface
   stabilizes; it's the lowest-friction extensibility model in the survey.

5. **Capabilities migrate up the stack over time.** Watch / coverage / audit
   started as community plugins in every ecosystem and became built-in. The
   right `m-cli` pattern is the same: build the canonical thin version
   in-tree, leave room for community refinement.

---

## 6. Recommended development sequence and roadmap

This section turns §4.1 into a concrete plan that respects the dependencies
between subcommands, the engineering scope of each, and the natural overlap
with existing `m-cli` infrastructure. The goal is a sequence that maximizes
shippable value early and keeps options open for the larger items later.

### 6.1 Dependency graph

Each box is a subcommand. An arrow `A → B` means A is a prerequisite of B —
either directly (B reuses A's machinery) or strategically (B isn't useful
without A). Items with no incoming arrow can ship in any order.

```
                      ┌───────────────────────────────────┐
                      │   Existing Tier 1 + 2 foundation   │
                      │   parser · fmt rule engine ·       │
                      │   lint runner · WorkspaceIndex ·   │
                      │   YDB trace · test discovery       │
                      └────────────────┬──────────────────┘
                                       │
        ┌──────────────┬───────────────┼──────────────┬──────────────┐
        │              │               │              │              │
        ▼              ▼               ▼              ▼              ▼
   ┌────────┐    ┌──────────┐    ┌──────────┐   ┌───────────┐   ┌────────┐
   │ m new  │    │ m doctor │    │  m doc   │   │  m run    │   │ m build│
   │  (S)   │    │   (S)    │    │   (S)    │   │   (XS)    │   │   (S)  │
   └────────┘    └──────────┘    └──────────┘   └───────────┘   └────────┘
        │              │
        └──────┬───────┘
               ▼
        ┌─────────────┐
        │ m ci init   │  ← reuses m new template machinery
        │   (XS)      │
        └─────────────┘

   ┌──────────────────────┐    ┌─────────────────────────┐
   │ fmt rule engine      │    │ test discovery          │
   │ (existing)           │    │ (existing)              │
   └──────────┬───────────┘    └────────────┬────────────┘
              │                              │
              ▼                              ▼
        ┌──────────┐                   ┌──────────┐
        │  m fix   │                   │ m bench  │
        │   (M)    │                   │   (S)    │
        └──────────┘                   └──────────┘

   ┌──────────────────────┐
   │ YDB view "TRACE"     │  (already wired for m coverage)
   └──────────┬───────────┘
              ▼
        ┌─────────────┐
        │  m profile  │
        │     (M)     │
        └─────────────┘

   ┌──────────────────────┐
   │ ydb ZBREAK / ZSTEP   │  (engine-level, no CLI dependency)
   └──────────┬───────────┘
              ▼
        ┌─────────────┐
        │  m debug    │  ← own project; DAP server
        │     (L)     │
        └─────────────┘

        ┌─────────────┐
        │   m pkg     │  ← ecosystem meta-project
        │    (XL)     │
        └──────┬──────┘
               │
        ┌──────┴──────────┐
        ▼                 ▼
   ┌─────────┐      ┌──────────┐
   │ m audit │      │ m publish│
   │   (S)   │      │   (S)    │
   └─────────┘      └──────────┘
```

**Effort key.** XS = hours · S = days · M = 1–2 weeks · L = 4–6 weeks · XL = months.

**Dependency rationale.**

- **`m fix` reuses the fmt rule engine.** Today only `M-XINDX-013` and `M-XINDX-047` have `fixer_id` linkage. Generalizing fmt's per-rule application machinery into a structural-search-and-replace facility lets every future XINDEX rule register an autofix, which in turn upgrades every LSP Quick Fix. Build it on top of `m fmt`, not beside it.
- **`m profile` reuses YDB `view "TRACE"`.** The coverage runner already collects per-line execution counts. Profile is the same data, displayed as time/count rather than hit/miss. Trying to ship them as separate plumbing wastes work.
- **`m bench` reuses test discovery.** A bench label is a test label with a different prefix and a different output convention. The whole `m_cli.test.discovery` + `runner` + `output` skeleton transposes to bench with minimal new code.
- **`m ci init` should bundle with `m new`.** Both are template emitters; sharing a templating mechanism halves the work and ensures `m new` projects come with CI wired by default.
- **`m audit` and `m publish` block on `m pkg`.** Without a routine-bundle manifest there's nothing to audit and nowhere to publish. Don't sequence either before `m pkg`.
- **`m debug` has no CLI dependencies.** It depends on engine primitives (`ZBREAK`, `ZSTEP`) that already exist and on a separately scoped DAP-server build-out. It can run in parallel with any other phase.

### 6.2 Phased roadmap

Five phases. Each phase has a clear theme, an ordered punch list, and an exit
criterion that lets you decide whether to advance, hold, or scope-cut.

#### Phase 3a — Quick wins (weeks 1–4)

**Theme.** Independent, small-scope items that close §4.1 ranks 8, 2, 4, 11,
9, 12 and lower the activation energy for new M projects.

| Order | Subcommand | Effort | Builds on | Deliverable |
|:---:|---|:---:|---|---|
| 1 | `m doctor` | S (1 day) | nothing | Diagnose `$ydb_dist`, `$ydb_routines`, parser availability, m-standard TSV files. Exit-1 on broken env with actionable hints. |
| 2 | `m new <name>` | S (1–2 d) | nothing | Scaffolder. Emits routine + `<name>TST.m` + `.m-cli.toml` + `.gitignore` + `routines/` + `tests/`. |
| 3 | `m ci init` | XS (hrs) | `m new` template engine | Emits `.github/workflows/m-ci.yml` running `m fmt --check` + `m lint --error-on=fatal` + `m test` + `m coverage --format=lcov`. |
| 4 | `m run` | XS (hrs) | nothing | Thin `ydb -run ^ROUTINE` wrapper with env composition + exit-code mapping. |
| 5 | `m build` | S (3–5 d) | nothing | Warm-compile a directory; surface `ydb` compile errors uniformly. Optional `--check` mode for CI. |
| 6 | `m doc` | S (3–5 d) | parser | Extract `;;` doc comments + label signatures into Markdown. HTML rendering optional. |

**Exit criterion.** All six subcommands ship with tests, are documented in
[guide.md](guide.md), and `m new` produces a project that passes
`m fmt --check && m lint && m test && m coverage` on a clean clone.

#### Phase 3b — Generalize existing infrastructure (months 2–3)

**Theme.** Take §4.1 ranks 3, 7, 10 — capabilities that pay back the most by
generalizing machinery already in the repo.

| Order | Subcommand | Effort | Builds on | Deliverable |
|:---:|---|:---:|---|---|
| 1 | `m fix` | M (1–2 wk) | `m fmt` rule engine, lint `fixer_id` linkage | Named recipes + tree-sitter structural search/replace. Every existing `fixer_id`-tagged lint rule becomes auto-fixable; future rules register a fixer alongside the rule. |
| 2 | `m profile` | M (1–2 wk) | YDB `view "TRACE"` (from coverage) | Flat profile (line/label execution counts × time per call) and folded-stack output suitable for `flamegraph.pl`. |
| 3 | `m bench` | S (3–5 d) | `m test` discovery + runner | `b<UpperCase>` labels in `*BCH.m` files; `$ZH` timing; ops/sec reporting; comparison mode (`--baseline`). |

**Exit criterion.** Lint Quick Fixes in the LSP cover ≥10 rules (up from 2);
`m profile` produces a flamegraph for an m-tools test run; `m bench`
discovers and runs at least one bench file in a real M project.

#### Phase 3c — Debugger (months 4–6)

**Theme.** §4.1 rank 5. The single biggest developer-felt feature still
missing. Scoped as its own project per CLAUDE.md.

| Order | Subcommand | Effort | Builds on | Deliverable |
|:---:|---|:---:|---|---|
| 1 | `m debug` (DAP server) | L (4–6 wk) | engine `ZBREAK` / `ZSTEP` / `ZSHOW` | DAP server wrapping ydb's debug primitives. Breakpoints, step in/over/out, locals/watch, call stack, conditional breakpoints. |
| 2 | VS Code DAP wiring | S (3–5 d) | `m debug` | `tree-sitter-m-vscode` registers a debug adapter; F5 launches a debug session. |

**Exit criterion.** Setting a breakpoint in VS Code, hitting it during
`m test`, inspecting locals, and stepping through a routine all work without
manual `ydb` terminal interaction.

#### Phase 4 — Ecosystem (year 2+)

**Theme.** §4.1 rank 6 plus its dependents. A meta-project: defines what an
"M package" is, how it's distributed, and how it's audited.

| Order | Subcommand | Effort | Builds on | Deliverable |
|:---:|---|:---:|---|---|
| 1 | `m pkg` (manifest spec + resolver) | XL (months) | nothing in m-cli; needs ecosystem RFC | `M-PKG.toml` schema; git-URL-resolvable bundles; lockfile; `m pkg add` / `lock` / `sync`; vendor mode for VistA-style monoliths. |
| 2 | `m audit` | S | `m pkg` lockfile | CVE / advisory scan over resolved packages. |
| 3 | `m publish` | S | `m pkg` registry contract | Push a bundle to a registry (or signed git tag, depending on RFC outcome). |

**Exit criterion.** At least three real M projects have adopted `M-PKG.toml`
and a fourth resolves them as dependencies.

#### Phase 5 — Optional polish (opportunistic)

Items deliberately left out of the active plan but worth picking up if the
opportunity arises:

- **`m typecheck`** (gradual typing) — only if the m-standard community proposes typing annotations. Not a feature in search of a problem.
- **`m toolchain`** — only if multi-engine support (GT.M, IRIS, Caché) becomes a stated goal. `m doctor` covers the single-engine case.
- **Cargo-style external subcommand discovery.** Once the in-tree subcommand surface stabilizes, allow any `m-foo` binary on `$PATH` to be invoked as `m foo`. Lowest-friction extensibility model from §3.

### 6.3 Cross-cutting investments

These thread through every phase and should be budgeted explicitly rather
than appearing as line items.

| Investment | When | Why |
|---|---|---|
| **VistA gate maintenance.** Re-run `make vista`, `make lint-vista`, and the smoke tests on every new subcommand that touches the parser or rule engines. | Continuous | The 39,330-routine corpus is the only honest stress test we have. Regressions caught here cost 1 hour; in production they cost weeks. |
| **Library API stability.** Anything new that out-of-tree tools should consume goes into `m_cli.__all__` and is pinned by `tests/test_library_api.py`. | Phase 3a onward | The LSP, pre-commit, and future IDE integrations all consume the library API. Breaking it is a tax on every consumer. |
| **Performance budget.** Every new subcommand that walks the corpus must declare a budget and verify it. | Phase 3b onward | Lint already costs 22.6 s on 16 cores. A coverage / profile / fix run that scales linearly to corpus size needs the same `--jobs` discipline up front. |
| **PyPI publish.** Ship `m-cli` and `tree-sitter-m` to PyPI. | Late Phase 3a | Unblocks the git-repo-style pre-commit hook for downstream M projects (see [pre-commit.md](pre-commit.md)). |

### 6.4 Decision points and risk register

Things to revisit before starting each phase, rather than deciding now.

| Decision | When | Default | Watch for |
|---|---|---|---|
| Continue extending Python codebase vs port hot paths to Rust | Phase 3b end | Stay in Python | Lint perf regressing past 60 s on VistA; test runner startup overhead becoming visible. |
| Build `m debug` on YDB only or design for engine-portable DAP | Phase 3c start | YDB-first, abstraction comes later if Caché / IRIS users appear | Demand signal from non-YDB users; sponsor for Caché support. |
| `m pkg` registry: build one, reuse git, or piggyback on PyPI | Phase 4 RFC | Git-URL-only initially | Spam / malicious packages once any registry exists; trust model needs to land before launch. |
| Cargo-style `$PATH` subcommand discovery | After Phase 3c | Hold | Wait until the in-tree subcommand surface is stable for ≥6 months — premature extension points become migration debt. |

### 6.5 At-a-glance Gantt

```
                  M1   M2   M3   M4   M5   M6   M7   M8   M9   ─── Y2 ───
Phase 3a quick wins █████
Phase 3b infra              █████████
Phase 3c debug                                █████████████
Phase 4  ecosystem                                                ████████████►
PyPI publish              ▲
VistA gate            ◄────────── continuous ──────────────────────────►
```

The two productivity-defining phases (3a + 3b) ship inside one quarter. The
debugger ships inside two quarters. The ecosystem play is explicitly a
year-2+ commitment, contingent on demand signals — not an all-hands push.
