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

## 3. Rust and PyO3 integration

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

## 4. Build workflow

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

## 5. Lint, typecheck, and test workflow

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
  - rebuild the editable environment if needed
  - run `ty check` through `uv`
- `make test`
  - verify Rust formatting
  - rerun `cargo clippy`
  - run Rust tests with `cargo-nextest` when available, otherwise `cargo test`
  - run Python tests through `.venv/bin/python -m pytest -v`

The Python tools are intentionally run through `uv run --group dev` so the
repository uses the locked dev toolchain instead of whatever happens to be on
the host `PATH`.

## 6. Development responsibilities

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

## 7. API boundaries

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

## 8. Debugging and verification workflow

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

## 9. Release expectations

Release work should assume wheel artefacts are the primary distributable output
of the mixed package.

- Use `make release` for release builds.
- Keep the Python package metadata and the Rust extension build path in sync.
- Treat release-affecting changes to the Makefile, `pyproject.toml`, or
  `rust_extension/Cargo.toml` as coupled changes that need end-to-end
  verification.

If release packaging changes, this guide, the design document, and the relevant
RFCs should be reviewed together so the documented contract remains accurate.
