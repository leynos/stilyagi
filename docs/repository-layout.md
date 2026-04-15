# Repository layout

This guide is for contributors who need to orient themselves quickly in the
Stilyagi repository. It describes the current tree shape, the responsibilities
of the major paths, and the directories that have unusual constraints or should
not be treated as long-lived source.

The primary architecture reference remains
[Stilyagi design](stilyagi-design.md). The
[developer's guide](developers-guide.md) explains how to build, lint, test, and
release the mixed Rust and Python package. This document is narrower: it
explains where things live.

## 1. Repository map

The tree below is illustrative rather than exhaustive. It includes the paths a
new maintainer needs to recognise quickly and omits transient cache contents.

```plaintext
.
├── .config/
│   └── common-acronyms/
├── .github/
│   └── workflows/
├── .rules/
├── docs/
│   └── rfcs/
├── features/
├── image_out/
├── rust_extension/
│   └── src/
├── scripts/
├── stilyagi/
├── tests/
│   ├── behaviour/
│   ├── fixtures/
│   └── workflows/
├── AGENTS.md
├── Makefile
├── pyproject.toml
└── uv.lock
```

## 2. Top-level source and control files

- `AGENTS.md`
  - Repository-scoped working instructions for agents. Read this before making
    changes anywhere in the tree.
- `Makefile`
  - Canonical maintainer entrypoint for build, format, lint, typecheck, test,
    and release workflows.
- `pyproject.toml`
  - Python package metadata, Ruff configuration, `ty` configuration, pytest
    settings, and `uv` package behaviour.
- `uv.lock`
  - Locked Python dependency graph. Update this when Python dependency changes
    are made through `uv`.
- `.markdownlint-cli2.jsonc`
  - Repository-level Markdown linting configuration.
- `.vale.ini`
  - Legacy Vale-era configuration retained in the repository. It is not the
    architectural centre of the replacement Stilyagi design.

## 3. Source code and runtime boundaries

- `stilyagi/`
  - Python package source.
  - Owns package-level orchestration and the Python-visible runtime surface.
  - Should not absorb Rust-owned extraction logic merely because the Python
    layer can technically reimplement it.
- `rust_extension/`
  - PyO3-based Rust extension crate.
  - Owns the compiled `_stilyagi_rs` module and Rust-side tests.
  - `src/` contains the Rust implementation; `target/` is generated build
    output and should not be treated as authored source.

The ownership boundary matters. Rust is the home for source-fidelity and
extension-boundary concerns. Python is the home for package integration and the
rule-engine-facing runtime.

## 4. Documentation and design material

- `docs/`
  - Maintainer and reviewer documentation.
  - Holds the documentation index, style guide, developer guide, design
    document, and other long-lived reference material.
- `docs/rfcs/`
  - Draft contract and proposal documents.
  - Use this directory for RFCs that still need review or that record narrower
    subcontracts feeding the main design.

Long-lived reference material belongs under `docs/`, not scattered through the
repository root or hidden in issue threads.

## 5. Tests, behaviour checks, and fixtures

- `tests/`
  - Python-level tests and integration checks.
- `tests/behaviour/`
  - Behaviour-oriented tests and scenarios.
- `tests/fixtures/`
  - Static fixture inputs used by tests.
- `tests/workflows/`
  - Workflow-focused test support.
- `features/`
  - Behaviour-driven development feature files used by the Python test stack.

Fixture and scenario paths are semantically important. Test data should be kept
there rather than embedded ad hoc in unrelated modules.

## 6. Supporting and constrained directories

- `.rules/`
  - Repository-specific Python and documentation guidance used as local coding
    standards.
- `.config/common-acronyms/`
  - Repository-local acronym support data.
- `.github/workflows/`
  - Continuous integration and automation workflow definitions.
- `scripts/`
  - Helper scripts. This directory is currently sparse, so new scripts should
    be added deliberately rather than turning it into a general dumping ground.
- `image_out/`
  - Generated or exported image output. Treat this as artefact space, not as a
    home for hand-maintained source files.

## 7. Generated and transient paths

The following paths are operationally useful but are not authoritative source:

- `.venv/`
  - Local virtual environment created by `make build` or `make typecheck`.
- `.uv-cache/`
  - Local `uv` cache data.
- `.ruff_cache/`
  - Local Ruff cache data.
- `.pytest_cache/`
  - Local pytest cache data.
- `rust_extension/target/`
  - Cargo build artefacts, including compiled outputs and wheel-build
    intermediates.

These directories should generally remain untracked and should not be treated
as inputs when documenting the repository structure.

## 8. Change expectations

Update this document when the repository structure changes enough that a new
contributor could otherwise follow stale guidance. Typical triggers include:

- moving source between Python and Rust
- adding a new long-lived top-level directory
- splitting tests or fixtures into new stable paths
- adding a new documentation subtree with repository-wide importance
- introducing a generated-output directory that maintainers must understand
