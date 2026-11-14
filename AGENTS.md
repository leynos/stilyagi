# Assistant instructions

## Code style and structure

- **Code is for humans.** Write code with clarity and empathy—assume a
  tired teammate will need to debug it at 3 a.m.
- **Comment *why*, not *what*.** Explain assumptions, edge cases, trade-offs,
  or complexity. Don't echo the obvious.
- **Clarity over cleverness.** Be concise, but favour explicit over terse or
  obscure idioms. Prefer code that's easy to follow.
- **Use functions and composition.** Avoid repetition by extracting reusable
  logic. Prefer generators or comprehensions, and declarative code to
  imperative repetition when readable.
- **Small, meaningful functions.** Functions must be small, clear in purpose,
  single responsibility, and obey command/query segregation.
- **Clear commit messages.** Commit messages should be descriptive, explaining
  what was changed and why.
- **Name things precisely.** Use clear, descriptive variable and function names.
  For booleans, prefer names with `is`, `has`, or `should`.
- **Structure logically.** Each file should encapsulate a coherent module. Group
  related code (for example, models + utilities + fixtures) close together.
- **Group by feature, not layer.** Colocate views, logic, fixtures, and helpers
  related to a domain concept rather than splitting by type.
- **Use clear file boundaries.** Each module, component, and package should have
  an obvious responsibility and avoid accidental coupling.
- **Use consistent spelling and grammar.** Comments must use en-GB-oxendict
  ("-ize" / "-yse" / "-our") spelling and grammar, with the exception of
  references to external APIs. See [Spelling](#spelling).
- **Illustrate with clear examples.** Function documentation must include clear
  examples demonstrating the usage and outcome of the function. Test
  documentation should omit examples where the example serves only to reiterate
  the test logic.
- **Document public APIs comprehensively.** Public functions, classes, and
  methods must have comprehensive NumPy-style docstrings, including clear
  examples that demonstrate usage and outcome.
- **Keep private helper docstrings concise.** Prefer single-line docstrings for
  private helpers. When a private helper needs an explanatory paragraph,
  inspect whether that need exposes conflated responsibilities, an unclear
  command/query boundary, or another CQRS or cohesion failure:
  - Split the helper when it performs distinct query and command
    responsibilities or combines unrelated concerns.
  - Extract a focused helper when doing so makes the invariant or boundary
    local and simpler.
  - Keep the helper intact when its responsibility is cohesive and the
    explanation documents an unavoidable local constraint; retain the
    paragraph in that case.
- **Structure private helper docstrings selectively.** Use structured
  NumPy-style sections for private helpers only when they describe non-obvious
  behaviour.
- **Keep file size manageable.** No single code file may be longer than 400
  lines. Long switch statements or dispatch tables should be broken up by
  feature and constituents colocated with targets. Large blocks of test data
  should be moved to external data files.

## Documentation maintenance

- **Reference:** Use the markdown files within the `docs/` directory as a
  knowledge base and source of truth for project requirements, dependency
  choices, and architectural decisions. Start with
  [documentation contents](docs/contents.md) and
  [repository layout](docs/repository-layout.md) when orienting within the
  project.
- **Update:** When new decisions are made, requirements change, libraries are
  added/removed, or architectural patterns evolve, **proactively update** the
  relevant file(s) in the `docs/` directory to reflect the latest state. Ensure
  the documentation remains accurate and current.
- **Design decisions:** Record design decisions in the relevant design
  document. When a decision is substantive, capture it in an Architectural
  Decision Record (ADR) following the documentation style guide, and reference
  that ADR from the design document.
- **User-facing behaviour:** Update [users' guide](docs/users-guide.md) for
  behaviour or user-interface changes that users should know about. Add
  migration guidance for compatibility or usage changes.
- **Internal interfaces:** Document internally facing interfaces in the
  relevant component architecture document. Document internally facing
  conventions and practices in [developers' guide](docs/developers-guide.md).
- **Build tooling:** When changing build tooling, document the effective
  toolchain, inherited flags, backend and linker selection, and deliberate
  differences between validation commands.
- **Style:** All documentation must adhere to the
  [documentation style guide](docs/documentation-style-guide.md).
- **Accuracy:** Verify changed examples, commands, imports, links, paths, and
  stated guarantees against the implementation. Update maintained copies and
  indexes when names or locations change. Keep transient validation results in
  the PR or execution record.
- **Decision history:** Preserve accepted ADR decisions; record subsequent
  changes through the
  [ADR amendment and supersession process](docs/documentation-style-guide.md#architectural-decision-records-adrs).
  Capture proof-driven API, representation, and invariant decisions in the
  design documentation.
- **Completed execplans:** Completed execplans are historical documents and
  should reflect the state of the repository at time of implementation. Do not
  retroactively update completed execplan documents to reflect subsequent
  changes in API, structures, or behaviour.

## Planning and verification

- For non-trivial work, prepare or update a self-contained ExecPlan using the
  available planning guidance. Identify the outcome, relevant roadmap and
  design references, prerequisites, scope exclusions, and observable acceptance
  criteria. Signpost relevant documentation and skills.
- Identify affected behavioural contracts, invariants, and failure modes before
  choosing the implementation. Use these to pressure-test the proposed API and
  verification strategy.
- Plan the smallest useful increment. Preserve decision gates and stopping
  conditions; defer abstractions, dependencies, macros, or published components
  until the preceding evidence justifies them.
- Where formal verification is selected, first sketch the independent model,
  premises, invariants, representation relationships, and principal proof
  obligations. Treat proposed lemmas as provisional. Defer detailed proof
  engineering until implementation exposes the verification conditions; do not
  add assumptions, admissions, or trusted proof bodies merely to make
  incomplete proofs pass. Unproved statements may remain in the plan until that
  milestone.
- Give each major milestone explicit acceptance commands, including applicable
  proof checks and the formatting, linting, and test gates. Keep commits
  coherent and useful as rollback points.
- When plan approval is required, deliver the plan for review and wait for
  approval before implementation. Keep the active plan current, and mark
  relevant roadmap entries complete only after their acceptance criteria pass.

## Change quality & committing

- **Atomicity:** Aim for small, focused, atomic changes. Each change (and
  subsequent commit) should represent a single logical unit of work.
- **Quality Gates:** Before considering a change complete or proposing a commit,
  ensure it meets the following criteria:
  - New functionality or changes in behaviour are fully validated by relevant
    unit tests and behavioural tests.
  - Where a bug is being fixed, a unittest has been provided demonstrating the
    behaviour being corrected both to validate the fix and to guard against
    regression.
  - Passes all relevant unit and behavioural tests according to the guidelines
    above.
  - Passes lint checks.
  - Adheres to formatting standards tested using a formatting validator.
- **Before review:** Inspect the complete diff, including tests, fixtures,
  scripts, examples, and documentation. Check file-size limits, module
  documentation, doc-comment placement, assertion diagnostics, duplicated test
  setup, and applicable spelling and formatting gates. Link relevant roadmap
  entries, issues, and the ExecPlan in the PR description.
- **For Python files:**
  - **Testing:** Passes all relevant unit and behavioural tests (`make test`).
  - **Linting:** Passes the complete `make lint` pipeline, including the
    blocking Skylos dead-code scan and the blocking code-duplication gate. The
    CI lint step runs the same target.
  - **Dead code:** Investigate every Skylos finding and remove genuine dead
    code. Record verified false positives with a typed
    `[tool.skylos.dead_code]` entry-point rule for implicit runtime callers.
    Only if that rule cannot model the boundary, use
    `make skylos-allow SYMBOL=handler REASON="Loaded by plugin registry"`,
    including the verified runtime caller in the reason. `SYMBOL` is required
    because WSL may inject `NAME` with the hostname.
  - **Duplication:** Extract the shared logic into one helper when the
    duplication is genuine. When a family is a deliberate parallel rather than
    shared logic, record a reasoned exception with
    `make duplication-allow FIRST=<path[::name]> [SECOND=<path[::name]>]
    REASON='<why this stays>'` and state the independent contract or boundary
    that an extraction would wrongly couple. Never add a repository-wide
    wildcard, a mass-generated reason, or an entry that covers only some of a
    family's locations. Never relabel unresolved duplication as "intentional".
  - **Docstring coverage:** Interrogate, run as part of `make lint`, requires
    100% docstring coverage over `python/stilyagi`, `tests`, and `scripts`. Add
    docstrings with new code rather than suppressing the check.
  - **Formatting:** Adheres to formatting standards (`make check-fmt`; use
    `make fmt` to apply fixes).
  - **Typechecking:** Passes type checking (`make typecheck`).
- **For Rust files:**
  - **Testing:** Passes relevant unit and behavioural tests (`make test`).
  - **Linting:** Passes lint checks (`make lint`).
  - **Formatting:** Adheres to formatting standards (`make check-fmt`; use
    `make fmt` to apply fixes).
- **Markdown files (`.md` only):**
  - **Linting:** Passes markdown lint checks (`make markdownlint`).
  - **Spelling:** Passes the repository spelling gate; see the Spelling
    section below.
  - **Mermaid diagrams:** Passes validation using nixie (`make nixie`).
- **Committing:**
  - Only changes that meet all the quality gates above should be committed.
  - Write clear, descriptive commit messages summarizing the change, following
    these formatting guidelines:
    - **Imperative mood:** Use the imperative mood in the subject line (e.g.,
      "Fix bug", "Add feature" instead of "Fixed bug", "Added feature").
    - **Subject line:** The first line should be a concise summary of the change
      (ideally 50 characters or fewer).
    - **Body:** Separate the subject from the body with a blank line. Subsequent
      lines should explain the *what* and *why* of the change in more detail,
      including rationale, goals, and scope. Wrap the body at 72 characters.
    - **Formatting:** Use Markdown for any formatted text (like bullet points or
      code snippets) within the commit message body.
  - Do not commit changes that fail any of the quality gates.
- **Tool versions:** The Makefile and CI must use identical lint tool versions.
  The Makefile sets the Ruff (`RUFF_VERSION`), `ty` (`TY_VERSION`), Pylint
  (`PYLINT_VERSION`), and spelling gate (`TYPOS_CONFIG_BUILDER_VERSION`) pins
  as variables. Interrogate is pinned in the `pyproject.toml` `dev` dependency
  group and resolved from `uv.lock`. The `nose` duplication detector is pinned
  only by `[tool.nose] version`; the installed `df12-duplication` command
  verifies the download. Bump each pin at its single source of truth rather
  than installing a different version ad hoc, and never add a separate
  tool-install step to CI for a tool the Makefile already provides. Do not make
  a missing binary build from source: fix provisioning instead.

## Refactoring heuristics & workflow

- **Recognizing Refactoring Needs:** Regularly assess the codebase for potential
  refactoring opportunities. Perform refactoring when observing:
  - **Long Methods/Functions:** Functions or methods that are excessively long
    or try to do too many things.
  - **Duplicated Code:** Identical or very similar code blocks appearing in
    multiple places. The code-duplication gate reports these automatically, so
    a failing `make lint` is the usual signal.
  - **Complex Conditionals:** Deeply nested or overly complex `if`/`else` or
    `switch` statements (high cyclomatic complexity).
  - **Large Code Blocks for Single Values:** Significant chunks of logic
    dedicated solely to calculating or deriving a single value.
  - **Primitive Obsession / Data Clumps:** Groups of simple variables (strings,
    numbers, booleans) that are frequently passed around together, often
    indicating a missing class or object structure.
  - **Excessive Parameters:** Functions or methods requiring a very long list of
    parameters.
  - **Feature Envy:** Methods that seem more interested in the data of another
    class/object than their own.
  - **Shotgun Surgery:** A single change requiring small modifications in many
    different classes or functions.
- **Abstraction / port / helper policy:** Before implementing an abstraction,
  port, or extracted helper, the agent must:
  1. Sweep the repository and approved dependencies for equivalent behaviour.
     Reuse it unless demonstrably unsuitable. New abstractions must simplify
     the current change or have a concrete reuse case.
  2. Document the new abstraction's intended scope and re-use policy
     (ownership boundaries, permitted call-sites, and composition rules).
  3. Record the decision in the appropriate architecture, design, or
     developers-guide document using `docs/contents.md` as the index to select
     the correct location.
- **Post-Commit Review:** After committing a functional change or bug fix (that
  meets all quality gates), review the changed code and surrounding areas using
  the heuristics above.
- **Separate Atomic Refactors:** If refactoring is deemed necessary:
  - Perform the refactoring as a **separate, atomic commit** *after* the
    functional change commit.
  - Ensure refactoring adheres to the testing guidelines (behavioural tests
    pass before and after, unit tests added for new units).
  - Ensure the refactoring commit itself passes all quality gates.

## Architecture and operational boundaries

- Keep domain policy separate from filesystem, process, network, framework,
  and telemetry adapters. Inject dependencies where needed through existing
  interfaces or narrow closures; avoid speculative layers and dependency cycles.
- Make fallibility, mutation, and side-effects explicit in APIs. Preserve I/O,
  parsing, and permission errors rather than silently converting them into
  absence, `false`, or empty success. Compose side-effects at orchestration
  boundaries; queries must not hide writes or unrelated workflow policy.
- For streams, subprocesses, retries, caches, queues, and background tasks,
  define applicable size limits, deadlines, ownership, cancellation, and
  cleanup. A timeout does not bound accumulated bytes. Include waiting and
  cleanup in the operation's budget. Define partial-failure and retry behaviour
  where updates span multiple effects; keep locks narrow and ordered, avoiding
  holds across awaits or external calls unless explicitly justified.
- Validate untrusted inputs before privileged effects, use structured APIs
  instead of executable string construction, and grant only required
  permissions.
- When performance materially motivates a change, measure realistic inputs and
  distinguish build, execution, queueing, and cache state. Avoid repeated I/O
  or unnecessary allocation in per-item loops and blocking work on async
  executors.

## Python verification and testing

- For Python work, use `pytest` for unit tests and `pytest-bdd` for behavioural
  tests. Cover happy paths, unhappy paths, and relevant edge cases.
- Snapshot tests (using `syrupy`) should be provided where multivariant output
  format consistency is relevant to the requirements. Snapshot tests must
  capture meaningful, reviewer-useful contracts rather than generic dumps of
  broad objects. Keep snapshots focused on stable output boundaries, pair them
  with semantic assertions for the behaviours they represent, and avoid
  snapshot-only coverage for logic that can be asserted directly. Redact or
  normalize nondeterministic fields such as timestamps, absolute paths, random
  identifiers, ordering-dependent maps, hostnames, and environment-specific
  values before snapshotting. Do not accept brittle snapshots that churn after
  harmless formatting or dependency changes; narrow the captured output until a
  snapshot failure identifies a real contract change.
- Add end-to-end tests where a change affects externally observable workflows,
  integration contracts, persistence, command-line behaviour, network
  boundaries, user interface flows, or other system-level behaviour.
- Use property tests with `hypothesis` or `CrossHair` when a change introduces
  an invariant over a range of inputs, states, orderings, or transitions.
- Run relevant unit, behavioural, property, and end-to-end suites before and
  after each change.

## Rust specific guidance

This repository is written in Rust and uses Cargo for building and dependency
management. Contributors should follow these best practices when working on the
project:

- The toolchain is a dated nightly pinned in `rust-toolchain.toml`, with no
  declared minimum supported Rust version. `.cargo/config.toml` applies the
  development build standard to every bare `cargo` run: the parallel frontend
  (`-Zthreads=8`) and, on Linux, the `mold` linker. It selects no codegen
  backend: the Cranelift exception is recorded in the developer's guide. Make
  recipes that assign `RUSTFLAGS` restate the flags, because an assignment
  displaces the configuration's `rustflags`. Release, coverage, and Whitaker
  routes exclude them. Run `make install-build-tools` once on a new machine;
  build, test, lint, and typecheck routes run `make check-build-tools` first.
  See the developer's guide, section 5a (Development build standard).
- Run `make check-fmt`, `make lint`, and `make test` before committing. These
  targets wrap the following commands, so contributors understand the exact
  behaviour and policy enforced:
  - `make check-fmt` first runs `tools-check`, which verifies that `cargo`,
    `rustfmt`, and `uv` are installed, then executes:

    ```sh
    $(RUFF) format --check
    $(CARGO) fmt --manifest-path $(WORKSPACE_MANIFEST) --all -- --check
    $(MDTABLEFIX) --check $(MDTABLEFIX_SELECT) $(MDTABLEFIX_RULES)
    ```

    validating Python, Rust, and Markdown formatting without modifying files.
    `RUFF` runs the version named by `RUFF_VERSION` through `uv tool run`.
    `MDTABLEFIX_SELECT` checks the Markdown files Git tracks, plus untracked
    files that Git does not ignore.
  - `make lint` runs `lint-clippy`, then `lint-whitaker`. `lint-clippy` depends
    on `check-build-tools`, `tools-lint`, `skylos` (the blocking dead-code
    scan), and `duplication` (the blocking code-duplication gate), and then
    executes:

    ```sh
    $(RUFF) check
    $(INTERROGATE) $(INTERROGATE_FLAGS) $(INTERROGATE_TARGETS)
    $(PYLINT) $(PYLINT_TARGETS)
    $(DF12_PYLINT) $(PYLINT_TARGETS)
    $(AMBRLEAKS) $(AMBRLEAKS_TARGETS)
    RUSTDOCFLAGS="$(RUSTDOC_FLAGS)" RUSTFLAGS="$(RUST_FLAGS)" $(CARGO_BUILD_ENV) $(CARGO) doc $(DOC_FLAGS)
    RUSTFLAGS="$(RUST_FLAGS)" $(CARGO_BUILD_ENV) $(CARGO) clippy $(CLIPPY_FLAGS)
    ```

    `lint-whitaker` then executes:

    ```sh
    RUSTFLAGS="$(WHITAKER_RUST_FLAGS)" $(CARGO_BUILD_ENV) $(WHITAKER) $(WHITAKER_LIBRARIES) -- $(CARGO_FLAGS)
    ```

    The Python stages cover `python/stilyagi`, `tests`, and `scripts`. The
    Interrogate stage requires 100% docstring coverage. Pylint runs on CPython
    3.14, and the df12 Pylint messages run in the same stage. The Rust stages
    build documentation with `--no-deps` for every feature, then run Clippy
    across all workspace targets with all features. By default `RUST_FLAGS` is
    `-D warnings` plus the development build standard (`-Zthreads=8`, and
    `-Clink-arg=-fuse-ld=mold` on Linux), `RUSTDOC_FLAGS` is
    `--cfg docsrs -D warnings`, and `WHITAKER_RUST_FLAGS` is `-D warnings`
    alone. `WHITAKER_LIBRARIES` defaults to `--all`, which loads every
    discovered Dylint lint library. Documentation warnings, Clippy warnings,
    and Whitaker findings fail the command.
  - `make test` depends on `check-build-tools`, `build` (a development
    `maturin develop` install followed by `make smoke`), and `tools-lint`. It
    then executes:

    ```sh
    $(CARGO) fmt --manifest-path $(WORKSPACE_MANIFEST) --all -- --check
    RUSTFLAGS="$(RUST_FLAGS)" $(CARGO_BUILD_ENV) $(CARGO) clippy $(CLIPPY_FLAGS)
    RUSTFLAGS="$(RUST_FLAGS)" $(CARGO_BUILD_ENV) $(CARGO) nextest run --profile default --no-tests pass $(TEST_FLAGS) $(BUILD_JOBS)
    RUSTDOCFLAGS="$(RUSTDOC_FLAGS)" RUSTFLAGS="$(RUST_FLAGS)" $(CARGO_BUILD_ENV) $(CARGO) test $(TEST_FLAGS) --doc $(BUILD_JOBS)
    "$$VENV_PYTHON" -m pytest -v
    "$$VENV_PYTHON" -m pytest -v --doctest-modules python/stilyagi tests/support
    ```

    The Rust test line uses `cargo nextest run` when `cargo nextest` is
    installed, and falls back to `cargo test` when it is not. Rust doctests run
    in a separate `--doc` pass. The Python suite runs twice: once as ordinary
    tests, then with doctests for `python/stilyagi` and `tests/support`. By
    default `TEST_FLAGS` covers `--workspace --all-features`.

  - Use `make fmt` to apply the formatting fixes that `check-fmt` reports. It
    runs `ruff format`, `ruff check --select I --fix`, `mdtablefix --in-place`,
    `markdownlint --fix`, and `cargo fmt --all`.
- The workspace lint tables in `Cargo.toml` and the Clippy configuration in
  `clippy.toml` are authoritative, and they reach a member by two different
  mechanisms. Every new member must inherit the tables with
  `[lints] workspace = true`; Clippy reads `clippy.toml` from the workspace
  root instead, so it needs no per-member stanza. See the developers' guide,
  [Rust lint baseline](docs/developers-guide.md#rust-lint-baseline), for the
  selected estate baseline, consumer additions, and exception rules.
- Rustdoc defaults to `RUSTDOC_FLAGS ?= --cfg docsrs -D warnings`, extended
  through `RUSTDOC_FLAGS_EXTRA`; an environment `RUSTDOC_FLAGS` replaces the
  default. Preserve the documentation and doctest routes and their workspace
  and feature coverage.
- Clippy warnings MUST be disallowed.
- Fix any warnings emitted during tests in the code itself rather than
  silencing them.
- Every `assert!`, `assert_eq!`, and `assert_ne!` invocation must include a
  custom diagnostic message that states the failed expectation and, where
  useful, the relevant values.
- Where a function is too long, extract meaningfully named helper functions
  adhering to separation of concerns and CQRS.
- Where a function has too many parameters, group related parameters in
  meaningfully named structs.
- Keep returned error types semantically focused and small. If a necessary
  payload makes an error variant large, place that payload behind `Box`; use
  `Arc` only when shared ownership or cheap cloning is required.
- Ensure that new features are validated with unit tests using `rstest` and
  behavioural tests using `rstest-bdd` where applicable. Cover happy paths,
  unhappy paths, and relevant edge cases.
- Add snapshot tests using `insta` where structured output, user-interface
  output, diagnostics, or other multivariant output formats need meaningful,
  stable assertions. Keep snapshots focused on stable output boundaries, pair
  them with semantic assertions for business rules and schema contracts, and
  normalize nondeterministic fields before snapshotting. Do not accept brittle
  snapshots that churn after unrelated changes; update snapshots only after
  confirming a snapshot failure identifies a real contract change.
- Add compile-time behaviour tests using `trybuild` where macro expansion,
  trait bounds, feature-gated APIs, or other compile-fail and compile-pass
  contracts are relevant to the requirements. Keep compile-time fixtures free
  of unrelated runtime work.
- Add end-to-end tests where a change affects externally observable workflows,
  integration contracts, persistence, command-line behaviour, network
  boundaries, UI flows, or other system-level behaviour.
- Select verification proportionately: named examples or `rstest` tables for
  finite contracts, `proptest` for broad input spaces or operation sequences,
  and `kani` for exhaustive exploration within explicit bounds. Use `verus` for
  selected lemmas or contractual invariants requiring unbounded proof over a
  suitable semantic model. Proofs must establish the property from appropriate
  premises, not restate or assume it. Straightforward integration and
  presentation work must not acquire artificial proof obligations. Keep
  executable integration and behavioural tests alongside proofs.
- Run relevant unit, behavioural, property, model-checking, proof, and
  end-to-end suites before and after making any change.
- Every module **must** begin with a module level (`//!`) comment explaining the
  module's purpose and utility, including test modules and fixture crate roots.
- Document public APIs using Rustdoc comments (`///`) so documentation can be
  generated with cargo doc.
- Prefer immutable data and avoid unnecessary `mut` bindings.
- Clone to express intentional ownership, sharing, or snapshot semantics;
  prefer borrowing or ownership transfer when a new owned value is unnecessary.
- Use explicit version ranges in `Cargo.toml` and keep dependencies up-to-date.
- Avoid `unsafe` code unless absolutely necessary, and document any usage
  clearly with a "SAFETY" comment.
- Place function attributes **after** doc comments.
- Do not use `return` in single-line functions.
- Use predicate functions for conditional criteria with more than two branches.
- Lints must not be silenced except as a **last resort**.
- Use item-scoped `#[expect(lint, reason = "...")]`; blanket allowances and
  artificial references that hide unused code are forbidden. Narrow feature and
  test-support compilation boundaries instead. Delete unused helpers unless
  concrete tracked work justifies a temporary expectation linked to that work.
- Use `concat!()` to combine long string literals rather than escaping newlines
  with a backslash.
- Prefer single line versions of functions where appropriate. i.e.,

  ```rust
  pub fn new(id: u64) -> Self { Self(id) }
  ```

  Instead of:

  ```rust
  pub fn new(id: u64) -> Self {
      Self(id)
  }
  ```

- Use NewTypes to model domain values and eliminate "integer soup". Reach for
  `newt-hype` when introducing many homogeneous wrappers that share behaviour;
  add small shims such as `From<&str>` and `AsRef<str>` for string-backed
  wrappers. For path-centric wrappers implement `AsRef<Path>` alongside
  `into_inner()` and `to_path_buf()`. Prefer explicit tuple structs whenever
  bespoke validation or tailored trait surfaces are required, customizing
  `Deref`, `AsRef`, and `TryFrom` per type. Use `the-newtype` when defining
  traits and needing blanket implementations that apply across wrappers
  satisfying `Newtype + AsRef/AsMut<Inner>`, or when establishing a coherent
  internal convention that keeps trait forwarding consistent without per-type
  boilerplate. Combine approaches: lean on `newt-hype` for the common case,
  tuple structs for outliers, and `the-newtype` to unify behaviour when owning
  the trait definitions.
- Use `cap_std` and `cap_std::fs_utf8` / `camino` in place of `std::fs` and
  `std::path` for enhanced cross-platform support and capabilities oriented
  filesystem access.

### Testing

- For each changed behaviour, identify a plausible incorrect implementation
  and ensure the test rejects it. Assert observable results, errors, and
  side-effects; mock calls or configuration text alone do not prove execution.
  Negative tests must establish the precondition that would expose the defect.
- Exercise the boundary that owns the promise: public API, executable, or
  protocol adapter. Private-helper tests complement this coverage. Fakes must
  support relevant failures and verify their propagation through orchestration.
  Test local integration contracts rather than third-party tools themselves.
- Test relevant partial failures, cancellation, shutdown, and cleanup with
  deterministic coordination where practical. Avoid relying solely on sleeps or
  exact deltas from shared global counters. Restore fixture resources even when
  assertions fail, and account for host capabilities and privileges.
- Use `rstest` fixtures for shared setup.
- Replace duplicated tests with `#[rstest(...)]` parameterized cases.
- Prefer `mockall` for ad hoc mocks/stubs.
- **Inject the environment instead.** Any behaviour depending upon environment
  variables must accept an injected environment: `mockable::Env`, with
  `mockable::DefaultEnv` supplied at the production composition root and
  `mockable::MockEnv` in tests. A narrow closure seam of the same shape is
  acceptable where a trait object would be disproportionate. Production code
  must not reach for `std::env::var`/`var_os` outside that composition root.
  The Rust crates read no environment variables. Python tests have no
  `mockable` equivalent, so they pass child-process environments through
  explicit `env=` mappings (see `tests/support/subprocess_env.py`), which the
  subprocess exemption below covers.
- **Process-wide locks are not an escape hatch.** Serializing environment
  mutation behind a shared `Mutex`, `OnceLock`, or `serial_test` attribute is
  not an accepted fallback. It serializes the suite, defeats property-based
  tests that run many cases within one process, and leaves the ambient
  dependency embedded in the production signature. Where injection looks
  impossible the signature is wrong; correct the signature.
- **Subprocess isolation is the sole exemption.** End-to-end behavioural tests
  invoking the generated application binary through `assert_cmd` may configure
  the environment via `Command::env`/`Command::env_clear`, because the mutation
  is confined to the child process. A test manipulating the environment
  in-process does not qualify, whatever layer it claims to occupy.

### Dependency management

- **Mandate caret requirements for all dependencies.** All crate versions
  specified in `Cargo.toml` must use SemVer-compatible caret requirements (e.g.,
  `some-crate = "1.2.3"`, equivalent to `^1.2.3`). This is Cargo's default and
  allows for safe, non-breaking updates to minor and patch versions while
  preventing breaking changes from new major versions. This approach is
  critical for ensuring build stability and reproducibility.
- **Prohibit unstable version specifiers.** The use of wildcard (`*`) or
  open-ended inequality (`>=`) version requirements is strictly forbidden, as
  they introduce unacceptable risk and unpredictability. Tilde requirements (
  `~`) should only be used where a dependency must be locked to patch-level
  updates for a specific, documented reason.

### Error handling

- **Prefer semantic error enums**. Derive `std::error::Error` (via the
  `thiserror` crate) for any condition the caller might inspect, retry, or map
  to an HTTP status.
- **Use an *opaque* error only at the app boundary**. Use `eyre::Report` for
  human-readable logs; these should not be exposed in public APIs.
- **Never export the opaque type from a library**. Convert to domain enums at
  API boundaries, and to `eyre` only in the main `main()` entrypoint or
  top-level async task.
- In tests, prefer `.expect(...)` over `.unwrap()` to surface clearer failure
  diagnostics.
- In production code and shared fixtures, avoid `.expect()` entirely: return
  `Result` and use `?` to propagate errors instead of panicking.
- Keep `expect_used` **strict**; do not suppress the lint.
- Recognize that `allow-expect-in-tests = true` **doesn’t cover** helpers
  outside `#[cfg(test)]` or `#[test]`; avoid `expect` in such fixtures.
- Use `anyhow`/`eyre` with `.context(...)` to **preserve backtraces** and
  provide clear, typed failure paths.
- Update helpers (e.g., `set_dir`) to **return errors** rather than panicking.
- Consume fallible fixtures in `rstest` by **making the test return `Result`**
  and applying `?` to the fixture.

### Observability

- Use `tracing` for logging and diagnostics. Prefer structured
  `tracing::{trace, debug, info, warn, error}` events and spans over `println!`,
  `eprintln!`, or direct `log` macros. Add fields for identifiers, state, and
  error context so downstream subscribers can filter and correlate events
  without parsing message text.
- Use `#[tracing::instrument]` or explicit spans around request handling,
  command execution, retries, background jobs, and other meaningful units of
  work. Do not hold `Span::enter()` guards across `.await`; use
  `Instrument::instrument` or scoped synchronous spans instead.
- Use the `metrics` crate for metric emission where usage, uptake, failure,
  or mitigation metrics are required. Prefer `counter!` for cumulative events,
  `gauge!` for values that rise and fall, and `histogram!` for distributions
  such as latency or payload size.
- Describe emitted metrics with `describe_counter!`, `describe_gauge!`, or
  `describe_histogram!` where the unit or purpose is not obvious from the
  metric name. Keep metric names stable and labels low-cardinality; do not put
  user input, request IDs, paths with unbounded parameters, or raw error
  strings into labels.
- Libraries may emit `metrics` and `tracing` instrumentation, but must not
  install global recorders or subscribers. Applications should initialize
  exporters/subscribers once, as early as practical in startup.
- Keep secrets, credentials, raw payloads, and sensitive paths out of logs,
  errors, traces, and snapshots. Prefer stable error categories and bounded
  contextual fields over arbitrary error text.
- For new operational telemetry, document and exercise the application's
  collection path. Verify a relevant event produces a non-zero signal through
  that path; helper-only assertions or comparisons of zero counters do not
  establish useful instrumentation.

## Markdown guidance

- Validate Markdown files using `make markdownlint`. It also runs the
  repository spelling gate, so a Markdown-only change is checked for spelling
  both locally and in CI.
- Run `make fmt` after any documentation changes to format all Markdown
  files and fix table markup.
- Validate Mermaid diagrams in Markdown files by running `make nixie`.
- Markdown paragraphs and bullet points must be wrapped at 80 columns.
- Code blocks must be wrapped at 120 columns.
- Tables and headings must not be wrapped.
- Use dashes (`-`) for list bullets.
- Use GitHub-flavoured Markdown footnotes (`[^1]`) for references and
  footnotes.
- Avoid first-person prose outside README and BDD feature files; allow
  second-person prose in README, AGENTS, BDD feature files, and agent skill
  directories. These exceptions qualify the documentation style guide.
- Quoted API names and identifiers retain upstream spelling. Mark them as
  code using backticks or fenced blocks rather than adding spelling exceptions.

<!-- typos-config-builder:agents-md:start -->

## Spelling

- `make spelling` runs the pinned `typos-config-builder gate`, which
  regenerates `typos.toml` from the shared en-GB-oxendict dictionary and
  `typos.local.toml`, then checks spelling and the shared phrase corrections.
- `typos.toml` is generated: never edit it by hand. Put narrow
  repository-specific exceptions in `typos.local.toml`, as exact or full-line
  patterns rather than bare accepted words.
- When `make spelling` changes `typos.toml`, commit the regenerated file. If
  the change is unrelated to your work, commit it in a separate base pull
  request and stack your branch on it, so each review diff stays focused.

<!-- typos-config-builder:agents-md:end -->

## Project documentation

Record design decisions in the design document. Where a decision is
substantive, record it in an ADR document following the documentation style
guide, then reference that ADR from the design document.

Update `docs/users-guide.md` for any change to application behaviour or user
interface that users should know about. Document internally facing interfaces
or practices in the relevant component architecture document. Document
internally facing conventions or practices in `docs/developers-guide.md`.

## Python development guidelines

For Python development, refer to the detailed guidelines in the `.rules/`
directory:

- [Python code style guidelines](.rules/python-00.md) - Core Python 3.13 style
  conventions.
- [Python context managers](.rules/python-context-managers.md) - Best practices
  for context managers.
- [Python exceptions and logging][python-exceptions] -
  Raising and handling exceptions and logging.
- [Python generators](.rules/python-generators.md) - Generator and iterator
  patterns.
- [Python project configuration](.rules/python-pyproject.md) -
  `pyproject.toml` and packaging.
- [Python return patterns](.rules/python-return.md) - Function return
  conventions.
- [Python typing](.rules/python-typing.md) - Type annotation best practices.

[python-exceptions]: .rules/python-exception-design-raising-handling-and-logging.md

Additional docs:

- [Scripting standards](docs/scripting-standards.md) - Guidance for writing
  robust scripts, including secure command execution via `cuprum`, catalogue
  allowlisting, and command mocking patterns with `cmd-mox`.
- Before adding or updating helper scripts, read the scripting standards guide
  and follow its `Cyclopts`, `cuprum`, `pathlib`, and `cmd-mox` conventions.
