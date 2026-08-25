# Documentation contents

- [Documentation contents](contents.md) lists the current documentation set and
  where each document fits.
- [Stilyagi design](stilyagi-design.md) is the primary technical design for the
  wholesale replacement of the current Vale-oriented repository with the new
  prose, documentation, comment, and docstring linter.
- [Roadmap](roadmap.md) sequences the implementation work into foundations and
  vertical slices, so the project can deliver useful functionality before the
  full architecture is complete.
- [Developer's guide](developers-guide.md) describes the maintainer-facing
  environment setup, Rust and Python boundaries, build workflow, and
  verification flow for the mixed PyO3 package.
- [User's guide](users-guide.md) records the current user-facing promises for
  Stilyagi, including the accepted packaging boundary, supported syntax
  surfaces, and current locale policy for v1.
- [ExecPlans](execplans/) records approved and in-progress execution plans for
  substantial repository work:
  - [1.1.1 packaging boundary decision ADR](
    execplans/1-1-1-packaging-boundary-decision-adr.md)
    tracks the implementation work that ratifies the v1 packaging boundary
    before later build-spine work lands.
  - [1.1.2 record the v1 syntax scope](
    execplans/1-1-2-record-the-v1-syntax-scope.md)
    plans the documentation-first work that ratifies the remaining v1 syntax,
    IR transport, and locale-policy promises before RFC alignment begins.
  - [1.1.3 harmonize RFC design contracts](
    execplans/1-1-3-harmonize-rfc-design-contracts.md)
    plans the RFC amendment pass that aligns RFCs 0001, 0002, 0003, and 0005
    with the ratified v1 design and ADR contract set.
  - [1.2.1 Python package and Rust crate structure](
    execplans/1-2-1-python-package-and-rust-crate-structure.md)
    plans the repository migration from the provisional `stilyagi/` plus
    `rust_extension/` tree to the long-lived `python/` and `crates/`
    mixed-package skeleton.
  - [1.2.2 Rust-to-Python extraction through the PyO3 bridge](
    execplans/1-2-2-rust-to-python-extraction-call-through-pyo3.md)
    plans the first real document-shaped extraction call from Python into the
    embedded Rust extension without helper-binary transport.
  - [1.2.3 Makefile and CI smoke tests](
    execplans/1-2-3-makefile-and-ci-smoke-tests.md)
    plans the Makefile and CI smoke path that proves development installs and
    release artefacts exercise the same embedded Rust extension boundary.
  - [1.3.1 assemble representative fixtures](
    execplans/1-3-1-assemble-representative-fixtures.md)
    plans the corpus fixture set that supports syntax, extraction, diagnostic,
    and round-trip regression testing.
  - [1.3.2 round-trip test helpers](
    execplans/1-3-2-round-trip-test-helpers.md)
    plans the internal golden IR, CLI snapshot, and fix round-trip helper work
    that lets later slices regression-test spans, segments, diagnostics, and
    edits cheaply.
  - [1.3.3 cold and warm baseline performance probes](
    execplans/1-3-3-cold-and-warm-baseline-performance-probes.md)
    plans the repository-local cold and warm structural performance probes
    that let later slices preserve the structural fast path.
  - [3.1.1 Python docstring extraction](
    execplans/3-1-1-python-docstring-extraction.md)
    plans owner-aware Python docstring extraction for modules, classes, and
    functions, including IR bridge coverage and validation evidence.
  - [maturin and PyO3 compatibility tests](
    execplans/maturin-pyo3-test-upgrade.md)
    plans the maturin pin update, native wheel snapshot coverage, and PyO3
    compile-time compatibility tests that support future build-tool upgrades.
  - [PR #102 layered Python linting](
    execplans/pr-102-layered-python-linting.md)
    records the completed layered Python linting implementation, its locked
    toolchain, configuration validation coverage, and extraction contracts.
- [Repository layout](repository-layout.md) maps the major repository paths,
  their responsibilities, and the generated or constrained directories that
  contributors should treat carefully.
- [Documentation style guide](documentation-style-guide.md) defines the
  repository-wide writing and Markdown conventions.
- [`rstest-bdd` user's guide](rstest-bdd-users-guide.md) documents the
  repository's Rust BDD test framework conventions.
- [Reliable testing in Rust via dependency injection](
  reliable-testing-in-rust-via-dependency-injection.md) records deterministic
  Rust testing patterns for IO and process-boundary code.
- [Rust testing with `rstest` fixtures](rust-testing-with-rstest-fixtures.md)
  records Rust fixture and parameterized-test conventions.
- [Scripting standards](scripting-standards.md) describes the expectations for
  shell and automation scripts in this repository.
- [Local validation with act and pytest](
  local-validation-of-github-actions-with-act-and-pytest.md) explains the
  current local workflow for validating GitHub Actions behaviour.

## Architecture decision records (ADRs)

- ADRs record narrower implementation and architecture choices that refine the
  main design:
  - [ADR 001: Select a spell checking provider](
    adr-001-spell-checking-provider.md)
    records the proposed backend choice for dictionary-based spelling support
    and the fallback path if the first provider spike fails.
  - [ADR 002: Ratify the packaging boundary](
    adr-002-packaging-boundary.md)
    records the accepted v1 build and runtime boundary between the Python
    package and the embedded Rust extension.
  - [ADR 003: Ratify the v1 contract scope](adr-003-v1-contract-scope.md)
    records the accepted v1 syntax support matrix, IR transport policy, and
    locale boundary that later roadmap slices may assume.
  - [ADR 004: Adopt layered Python linting](
    adr-004-python-linting-architecture.md)
    records the accepted layered Python linting architecture using Ruff,
    Interrogate, PyPy Pylint, df12 Pylint, ambrleaks, and Skylos, plus its
    Makefile execution model.
  - [ADR 005: Scope Markdown region vocabulary](
    adr-005-markdown-region-vocabulary-scope.md)
    records the accepted thin-container convention and the reserved
    `frontmatter_field` / source-backing deferrals for Markdown IR regions.
  - [ADR 006: Adopt docstring owner metadata](
    adr-006-docstring-owner-metadata.md)
    records the accepted owner metadata shape, Python `__qualname__`
    semantics, verbatim docstring extraction, and bounded Python node-store
    policy.
  - [ADR 007: Adopt Rust documentation-comment owner metadata](
    adr-007-rust-doc-comment-owner-metadata.md)
    records the Rust `owner` contract reuse, `::` qualified-name semantics,
    verbatim doc-comment extraction, and bounded Rust node-store policy.

## Requests for comments (RFCs)

- [RFCs](rfcs/) capture narrower draft contracts and design inputs that feed the
  main design:
  - [RFC 0001: Stilyagi IR](rfcs/0001-stilyagi-intermediate-representation.md)
    proposes the initial IR contract between the Rust extractor and Python
    analysis engine.
  - [RFC 0002: Stilyagi Python rule API](rfcs/0002-stilyagi-python-rule-api.md)
    proposes the Python-facing rule model and plugin surface.
  - [RFC 0003: Stilyagi CLI contract](rfcs/0003-stilyagi-cli-contract.md)
    proposes the command surface, config discovery rules, and suppression
    semantics.
  - [RFC 0004: Stilyagi rule tests](
    rfcs/0004-stilyagi-rule-testing-framework.md)
    proposes a first-party pytest plugin for exercising rules, temporary
    packs, diagnostics, fixes, and IR output against the real Stilyagi engine.
  - [RFC 0005: Grammar capability and syntactic API extensions](
    rfcs/0005-grammar-capability-and-syntactic-api-extensions.md)
    proposes the provider-neutral grammar-node API, capability model, and
    syntax-aware rule helpers for richer editorial analysis.
