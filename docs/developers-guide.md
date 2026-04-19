# Developer's guide

This guide is for maintainers working on Stilyagi itself. It documents the
current development environment, the Rust and Python split, the build and
verification workflow, and the boundaries that keep the implementation aligned
with the normative design.

The primary design reference is [Stilyagi design](stilyagi-design.md). The
narrower contracts live in:

- [RFC 0001](rfcs/0001-stilyagi-intermediate-representation.md) for the
  intermediate representation (IR)
- [RFC 0002](rfcs/0002-stilyagi-python-rule-api.md) for the Python rule API
- [RFC 0003](rfcs/0003-stilyagi-cli-contract.md) for the command-line
  interface (CLI)
- [RFC 0004](rfcs/0004-stilyagi-rule-testing-framework.md) for the
  rule-testing framework
- [RFC 0005](rfcs/0005-grammar-capability-and-syntactic-api-extensions.md) for
  the grammar layer, grammar-node model, and syntax-aware rule extensions
- [Roadmap](roadmap.md) for the ordered implementation sequence across the six
  phases, including which architectural questions should be settled before
  later slices are expanded

Documentation changes in this repository must also follow the
[documentation style guide](documentation-style-guide.md).

## 1. Environment setup

The repository targets Python 3.14 and Rust 2024. The development toolchain is
centred on `uv` for Python environments and dependency management, `maturin`
for building the PyO3 extension, and Cargo for Rust formatting, linting, and
tests.

The minimum local setup is:

- Python 3.14 available to `uv`
- Rust toolchain with `cargo`, `rustfmt`, and `clippy`
- `uv`
- `whitaker`
- `markdownlint-cli2`
- `nixie`

The repository-local virtual environment and dev dependencies are created by
the standard build target:

```bash
make build
```

That target performs three steps:

1. Recreate `.venv`
2. Sync the `dev` dependency group with `uv`
3. Run `maturin develop` against `rust_extension/Cargo.toml`

Developers should prefer the Makefile targets over ad hoc command sequences so
the PyO3 build flags and tool invocation paths stay consistent across local
development and continuous integration (CI).

## 2. Repository responsibilities and boundaries

Stilyagi is a mixed Rust and Python codebase with a strict boundary between
extraction and analysis.

- Rust owns source-oriented work:
  - file-format-aware parsing
  - Markdown and host-language extraction
  - byte spans, line mapping, and source fidelity
  - construction of the IR passed into Python
  - the PyO3 bridge surface exported to Python
- Python owns analysis-oriented work:
  - configuration discovery and override handling
  - rule registration and plugin loading
  - capability planning
  - optional spaCy-backed enrichment
  - diagnostics, fixes, and output rendering

This boundary is deliberate. Rules should never parse source files for
themselves, and the Rust layer should not absorb policy decisions that belong
in the rule engine.

## 3. Roadmap-aligned implementation boundaries

The [roadmap](roadmap.md) is the maintainer view of build order. It is not just
a delivery checklist. It records the architectural questions that each phase is
supposed to settle before the later ones rely on them.

The six phases currently break down into:

- Phase 1: ratify v1 contracts, packaging, repository layout, and shared test
  scaffolding
- Phase 2: deliver the first Markdown slice with real spans, suppression
  handling, and conservative fixes
- Phase 3: extend the same loop into Python docstrings and Rust documentation
  comments
- Phase 4: add capability-planned language-aware enrichment without breaking
  the structural fast path
- Phase 5: stabilize extension, testing, CI, and release-facing surfaces for
  team adoption
- Phase 6: evaluate Markdown with JSX (MDX), semantic, and editor-facing
  extensions only after the core v1 promise is already stable

For the near-term phases, developers should preserve four boundaries in
particular.

- IR structure
  - The near-term extractor contract is a stable, region-oriented IR with
    canonical JSON debug output, `line_index`, `content_hash`, `segments`,
    owner metadata, and explicit extraction errors or suppressions where they
    exist.
  - The in-process Rust to Python boundary may become more efficient than JSON,
    but JSON remains the canonical debug and test form for `dump-ir`, golden
    fixtures, and contract review.
- Suppression semantics
  - Suppression state is extracted once and carried in the IR rather than
    inferred ad hoc by individual rules.
  - V1 suppression remains syntax-native and deliberately narrow: configuration
    ignores, file-level directives, and named inline or range directives in
    host-language comments. Blanket inline suppression remains out of scope.
- Safe-fix planning
  - Fix planning stays source-faithful and conservative. Safe fixes may target
    only source-backed spans, must reject overlapping non-identical edits, and
    must not mutate synthetic spans introduced during flattening.
  - The CLI surfaces for this work are `check --fix`, `check --diff`, and
    `dump-ir`, because maintainers need both mutation and inspection paths
    while the core slices are still settling.
- Capability planning
  - Language-aware rules declare capabilities up front, and the runtime plans
    the cheapest provider set that satisfies the active rules.
  - Structural-only runs must continue to avoid natural language processing
    (NLP) startup entirely. Sentence and token enrichment should land before
    heavier part-of-speech, lemma, or dependency features, and backend escape
    hatches remain explicitly unstable.

When implementation work crosses one of those boundaries, update the design,
the relevant RFC, and the roadmap together. The roadmap is part of the current
maintainer contract, not a disposable planning artefact.

## 4. Rust and PyO3 integration

The Rust extension crate lives under `rust_extension/` and is built as the
`_stilyagi_rs` Python extension module. PyO3 provides the binding layer, while
`maturin` handles development installs and wheel builds.

The current integration contract is intentionally small:

- Rust exports Python-callable functions through the `_stilyagi_rs` module.
- Python package code imports and orchestrates the extension rather than
  duplicating Rust-owned logic.
- Rust tests cover Rust-only behaviour, while Python tests cover package-level
  integration and user-facing behaviour.

Changes to the FFI boundary should stay narrow. A good boundary exports
source-fidelity primitives, extraction results, and other stable engine
building blocks. A bad boundary exports policy-heavy convenience wrappers that
would force rule-engine churn into the extension crate.

## 5. Build workflow

The standard development and release workflows are:

```bash
make build
make release
```

`make build` is the development path. It recreates the virtual environment,
installs the editable Python package plus the compiled extension, and leaves
the repository ready for local linting and tests.

`make release` is the release artefact path. It runs:

```bash
uv run --group dev maturin build --release --manifest-path rust_extension/Cargo.toml
```

That command produces Python wheel artefacts under the Rust target wheels
output, which is the expected distribution surface for the mixed package.

The `build-release` target exists as a compatibility alias and should remain
behaviourally identical to `release`.

## 6. Lint, typecheck, and test workflow

The Makefile is the canonical workflow entrypoint. The current checks are:

- `make fmt`
- `make check-fmt`
- `make markdownlint`
- `make nixie`
- `make lint`
- `make typecheck`
- `make test`

Their responsibilities are:

- `make fmt`
  - format Python with Ruff
  - fix import ordering with Ruff
  - format Markdown with `mdformat-all`
  - format Rust with `cargo fmt`
- `make check-fmt`
  - verify Python formatting with Ruff
  - verify Rust formatting with `cargo fmt --check`
- `make markdownlint`
  - lint all Markdown files in the repository
- `make nixie`
  - validate Mermaid diagrams in Markdown files
- `make lint`
  - run Ruff checks through `uv`
  - run `cargo clippy` with warnings denied
  - run Whitaker from `rust_extension/`
- `make typecheck`
  - rebuilds the editable environment if needed
  - runs `ty check` through `uv`
- `make test`
  - verify Rust formatting
  - rerun `cargo clippy`
  - run Rust tests with `cargo-nextest` when available, otherwise `cargo test`
  - run Python tests through `.venv/bin/python -m pytest -v`

The Python tools are intentionally run through `uv run --group dev` so the
repository uses the locked dev toolchain instead of whatever happens to be on
the host `PATH`.

## 7. Development responsibilities

Maintainer responsibilities in this repository are stricter than a normal
single-language package.

- Keep the Rust and Python boundary narrow and explicit.
- Preserve source-fidelity guarantees when changing extraction or span logic.
- Update the design or RFC documents when implementation decisions materially
  change the architecture or public contracts.
- Keep Makefile targets honest; do not let local convenience diverge from
  documented or CI behaviour.
- Treat third-party plugins as trusted code. The repository should never imply
  sandboxing that does not exist.
- Keep documentation current when toolchain, workflow, or ownership boundaries
  change.

Substantial architecture changes should update both the code and the documents
that define the current contracts. Stale documentation is treated as a defect,
not as optional follow-up work.

## 8. API boundaries

The most important API boundaries are:

- Rust extractor API
  - should expose stable primitives for extraction, spans, and source mapping
  - should avoid embedding lint-policy decisions
- Python runtime API
  - should expose rule-facing objects and orchestration surfaces
  - should not bypass the Rust extractor for source parsing
- Rule and plugin API
  - should remain stable enough for third-party rule packs
  - should make required capabilities explicit
- CLI and output contracts
  - should remain aligned with the CLI RFC and machine-readable output
    guarantees

When a change crosses one of these boundaries, the change should be treated as
contract work rather than a local refactor. That usually means tests,
documentation, and compatibility review all need to move together.

## 9. Grammar layer and capability planning

RFC 0005 extends the narrower rule API contract with a grammar layer for
sentence-aware and syntax-aware rules. Maintainers should treat this as an
analysis-layer extension, not as an extractor-level replacement for the
region-oriented IR.

The grammar layer has five key moving parts:

- grammar-node hierarchy
  - `GrammarNode` is the shared source-backed base for derived grammar
    objects.
  - `TokenNode` and `SentenceNode` are the first compatibility wave and should
    land before higher-order helpers.
  - `NounPhraseNode`, `ClauseNode`, and `CoordinationNode` are higher-order
    abstractions built on top of token and dependency data rather than
    extractor-owned base facts.
- `GrammarProvider` protocol
  - Providers annotate extracted regions after capability planning has decided
    what enrichment is required.
  - The provider contract should remain narrow: take regions plus required
    capabilities, then return grammar-aware document views.
  - Backend-owned objects such as spaCy tokens may exist behind explicit
    unstable escape hatches, but they are not the public maintainer contract.
- visitor hooks
  - Rules may implement `visit_token`, `visit_sentence`,
    `visit_noun_phrase`, `visit_clause`, and `visit_coordination`.
  - The runtime should only invoke hooks whose required capabilities were
    materialized for the current run.
  - New hook types should be treated as public rule-API work and reviewed with
    the same care as new CLI or IR fields.
- capability relationships
  - RFC 0002 remains the current canonical planner vocabulary until the
    implementation and RFCs are updated together.
  - RFC 0005 adds grammar-facing names and explicitly maps them onto the
    existing planner terms so maintainers can avoid shipping parallel public
    constant sets.
  - Dependency-heavy capabilities must continue to preserve the structural fast
    path for runs that only need structural or lightweight text analysis.
- debug surfaces
  - `dump-ir` remains the canonical extractor debug view.
  - Grammar-aware debugging should be additive, for example
    `dump-ir --include-grammar`, rather than by baking provider-owned grammar
    objects into the base IR schema.

The practical rule for maintainers is simple: extracted regions and source
spans come first, provider-backed grammar objects come second, and rule hooks
sit on top of both. If a change tries to invert that order, it is almost
certainly crossing the wrong boundary.

## 10. Debugging and verification workflow

When behaviour looks wrong, debugging should start at the boundary most likely
to be at fault.

- Suspected span or extraction bug:
  - inspect the Rust extractor and its tests first
  - confirm the source offsets before touching rule logic
- Suspected rule or capability-planning bug:
  - inspect the Python runtime and rule-selection flow
  - verify whether the required enrichment was actually requested
- Suspected packaging or import bug:
  - rerun `make build`
  - verify that the editable install still points at the `maturin develop`
    extension rather than a stale wheel

For verification, prefer the Makefile targets over ad hoc tool runs. The
targets encode the repository's intended order of operations and catch
cross-language regressions that isolated commands can miss.

## 11. Release expectations

Release work should assume wheel artefacts are the primary distributable output
of the mixed package.

- Use `make release` for release builds.
- Keep the Python package metadata and the Rust extension build path in sync.
- Treat release-affecting changes to the Makefile, `pyproject.toml`, or
  `rust_extension/Cargo.toml` as coupled changes that need end-to-end
  verification.

If release packaging changes, this guide, the design document, and the relevant
RFCs should be reviewed together so the documented contract remains accurate.
