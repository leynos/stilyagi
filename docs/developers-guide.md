# Developer's guide

This guide is for maintainers working on Stilyagi itself. It documents the
current development environment, the Rust and Python split, the build and
verification workflow, and the boundaries that keep the implementation aligned
with the normative design.

The primary design reference is [Stilyagi design](stilyagi-design.md). The
narrower contracts live in:

- [ADR 002](adr-002-packaging-boundary.md) for the accepted build and runtime
  boundary between the Python package and the embedded Rust engine
- [ADR 003](adr-003-v1-contract-scope.md) for the accepted v1 syntax scope, IR
  transport policy, and locale support boundary
- [ADR 006](adr-006-docstring-owner-metadata.md) for the accepted docstring
  owner metadata shape, Python qualified-name policy, and bounded Python
  node-store contract
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
- `pyproject.toml` hard-pins maturin as
  `build-system.requires = ["maturin==1.13.3"]`
- `whitaker`
- `pypy`, or a `uv`-managed PyPy interpreter for `pylint-pypy-shim`
- `markdownlint-cli2`
- `nixie`

The repository-local virtual environment and dev dependencies are created by
the standard build target:

```bash
make build
```

That target performs four steps:

1. Recreate `.venv`
2. Sync the `dev` dependency group with `uv`
3. Run `maturin develop` against `crates/stilyagi-pyext/Cargo.toml`
4. Run the installed-package smoke check through `python -m stilyagi.smoke`

Developers should prefer the Makefile targets over ad hoc command sequences so
the PyO3 build flags and tool invocation paths stay consistent across local
development and continuous integration (CI).

## 2. Repository responsibilities and boundaries

Stilyagi is a mixed Rust and Python codebase with a strict boundary between
extraction and analysis.

The accepted packaging boundary is a Python-distributed application with an
embedded PyO3 extension built through `maturin`. Stilyagi does not use a
separate helper binary for normal v1 execution; the Rust extractor lives inside
the Python runtime as `stilyagi._stilyagi_rs`.[^1]

The accepted v1 contract scope is narrower than the architecture's long-term
extension points. Current implemented extraction support covers Markdown and
Python docstrings. Rust documentation comments are implemented in the stable v1
syntax vocabulary through `rust_doc_comment` regions with owner metadata.
Markdown with JSX (MDX) remains preview-only, canonical JSON remains required
for the IR bridge, `dump-ir`, fixtures, and compatibility review, and English
is the only formally supported v1 locale.[^2]

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

## 2a. Shared validation corpus

Shared source fixtures live under `tests/fixtures/corpus/`. The corpus is the
common input set for Rust and Python tests, so new extractor, rule, and bridge
tests should prefer these files over inline source strings when the same shape
is useful across languages.

The corpus is grouped by syntax and validity:

```plaintext
tests/fixtures/corpus/
├── markdown/
│   ├── valid/
│   └── malformed/
├── python/
│   ├── valid/
│   └── malformed/
└── rust/
    ├── valid/
    └── malformed/
```

Fixture names should describe the source shape, not the current implementation
limitation. For example, use names like `heading-table-link-suppression.md`,
`module-class-function-docstrings.py`, or `item-doc-comments.rs`. Invalid
Python syntax that repository formatters must not parse can use a `.py.txt`
suffix under `python/malformed/`. Malformed Markdown fixtures under
`markdown/malformed/` use a `.md.fixture` suffix for the same reason: the
suffix prevents repository-wide Markdown formatting and lint sweeps from
processing them. Each malformed fixture must remain readable UTF-8 source text
and must not need to be imported, compiled, or executed by tests.

Python tests should load corpus files through focused `pathlib.Path` helpers
like the ones in `tests/test_corpus.py`. Rust tests should load shared corpus
files through the dev-only `stilyagi-test-support` crate instead of duplicating
repository-root discovery in each crate. Python docstring tests should assert
real extraction behaviour. Rust documentation-comment tests should assert real
extraction behaviour, including owner metadata and recoverable parse errors.

Multi-line Python assertions whose diagnostic must wrap should use
`tests.support.assertions.assert_with_context`. The helper evaluates the
diagnostic on every run, so failure-only message lines do not dilute measured
test coverage. Keep ordinary assertions when the complete condition and message
fit on one line, particularly where the assertion narrows a type. The helper is
test-only and should not be used for application validation or control flow.

### The `.md.fixture` corpus convention

Because `stilyagi check` discovers only `.md` and `.markdown` files, any test
that exercises discovery must strip the trailing `.fixture` suffix when
materializing fixtures into a temporary tree; otherwise the fixtures are
invisible to discovery and the test passes vacuously.

The shared helper `tests/support/malformed_corpus.py` centralizes this:
`materialize_malformed_corpus(destination)` copies each fixture from
`tests/fixtures/corpus/markdown/malformed/` into `destination` under its
discoverable name (suffix stripped), and returns the sorted tuple of
discoverable filenames written. Discovery-facing tests should assert the
discovered file set against that return value so the whole corpus is genuinely
exercised.

This convention exists because a single `.md`-suffixed fixture previously
slipped through the sweep and was the only malformed case reaching discovery.
The `.md.fixture` suffix closes that gap permanently.

<!-- markdownlint-disable MD001 -->

#### RegionKind and typed ExtractRegion API

`RegionKind` is the `#[non_exhaustive]` enum in `crates/stilyagi-extract` that
names the stable discriminators surfaced through that boundary:

```rust
#[non_exhaustive]
pub enum RegionKind {
    Document,  // whole-document prose from Markdown extraction
    PythonDocstring,  // docstring prose from Python extraction
    RustDocComment,  // doc-comment prose from Rust extraction
}
```

`RegionKind::as_str(self) -> &'static str` returns the stable Python-facing
spelling, for example `"document"`, `"python_docstring"`, or
`"rust_doc_comment"`. `impl fmt::Display for RegionKind` delegates to `as_str`.
`TryFrom<&str> for RegionKind` is the canonical string-to-kind conversion; call
sites that receive a kind string from an external boundary should use that
implementation rather than a local match.

`ExtractRegion` exposes two typed entry points:

- `ExtractRegion::new_typed(kind: RegionKind, text: impl Into<String>) -> Self`
  is the preferred constructor; it accepts a typed kind and avoids freeform
  strings at the call site.
- `ExtractRegion::region_kind(&self) -> Option<RegionKind>` returns the typed
  kind when it falls within the built-in vocabulary; it returns `None` for
  region kinds introduced at an external boundary that are not yet part of the
  enum.

Prefer `new_typed` and `region_kind` in Rust code that works with
`stilyagi-extract` types. Reserve the string-typed `kind()` accessor for the
PyO3 serialization boundary, where `RegionKind::as_str` or the `Display`
implementation should be called explicitly.

#### Canonical IR region vocabulary

The canonical IR region vocabulary lives in `crates/stilyagi-ir` as
`stilyagi_ir::RegionKind`. The bridge enum described above keeps a separate
`#[non_exhaustive]` `stilyagi-extract::RegionKind` surface for Python-facing
extraction, while `stilyagi_ir::RegionKind` remains the canonical IR vocabulary.

`RegionKind::ALL` is the bridge enum's exhaustive helper slice for those three
variants only. It is distinct from `stilyagi_ir::RegionKind::ALL`, which is the
canonical IR vocabulary. Use `RegionKind::ir_region_kind()` when code needs to
map bridge variants into the IR vocabulary:

- `RegionKind::Document` maps to `None`, because it is a bridge-only coarse
  region with no IR equivalent.
- `RegionKind::PythonDocstring` maps to
  `Some(stilyagi_ir::RegionKind::PythonDocstring)`.
- `RegionKind::RustDocComment` maps to
  `Some(stilyagi_ir::RegionKind::RustDocComment)`.

Use `stilyagi_ir::RegionKind::ALL` and call `RegionKind::as_str()` on each
`stilyagi_ir::RegionKind` value when code needs the stable IR spellings; the
`supported_region_kinds()` PyO3 export is built from that same source of truth.

Markdown region emission follows ADR 005:

- `list_item` and `blockquote` are thin structural regions. They carry empty
  `text` and `segments`; child paragraph, table, and other prose regions keep
  the structure context through `parent_region`, `scope`, and the structural
  region's `attrs` together.
- `frontmatter` is source-backed over the whole fenced YAML or TOML block.
  `frontmatter_field` is reserved and not emitted until field-level spans can
  be proven without guessing.
- `image_alt` and `link_title` are synthetic `decoded_text` regions with
  `attrs.source_backed = false`.
- Source-backed segments must re-slice exactly to `segment.text`; the Markdown
  IR validator rejects span drift, unresolved `parent_region` links, and
  missing or invalid `origin_nodes`.

#### stilyagi-test-support API reference

The `stilyagi-test-support` crate (at `crates/stilyagi-test-support/`) provides
test-only helpers for fixtures, golden IR snapshots, and edit round-trip checks
that need access to repository-local files:

Table: Repository fixture utilities and signatures.

<!-- markdownlint-disable MD060 -->
| Symbol                          | Signature                                                            | Description                                                                                                                               |
| ------------------------------- | -------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `SHARED_MARKDOWN_FIXTURE_PATH`  | `&str`                                                               | Repository-relative path to the shared valid Markdown corpus fixture.                                                                     |
| `SHARED_PYTHON_FIXTURE_PATH`    | `&str`                                                               | Repository-relative path to the shared valid Python docstring corpus fixture.                                                             |
| `SHARED_RUST_FIXTURE_PATH`      | `&str`                                                               | Repository-relative path to the shared valid Rust doc-comment corpus fixture.                                                             |
| `MALFORMED_PYTHON_FIXTURE_PATH` | `&str`                                                               | Repository-relative path to the malformed Python fixture used for recovery tests.                                                         |
| `MALFORMED_RUST_FIXTURE_PATH`   | `&str`                                                               | Repository-relative path to the malformed Rust fixture used for recovery tests.                                                           |
| `NESTED_RUST_FIXTURE_PATH`      | `&str`                                                               | Repository-relative path to the nested Rust doc-comment corpus fixture.                                                                   |
| `MULTILINE_RUST_FIXTURE_PATH`   | `&str`                                                               | Repository-relative path to the multiline Rust doc-comment corpus fixture.                                                                |
| `repository_root`               | `() -> PathBuf`                                                      | Returns the workspace root resolved from `CARGO_MANIFEST_DIR`. Panics with a descriptive message when the crate layout assumption breaks. |
| `corpus_fixture_path`           | `(impl AsRef<Path>) -> PathBuf`                                      | Resolves a repository-relative path against the workspace root.                                                                           |
| `read_corpus_fixture`           | `(impl AsRef<Path>) -> Result<String, io::Error>`                    | Reads a repository-relative corpus fixture as UTF-8 text.                                                                                 |
| `read_corpus_fixture_bytes`     | `(impl AsRef<Path>) -> Result<Vec<u8>, FixtureReadError>`            | Reads a repository-relative corpus fixture as raw bytes for byte-level tests.                                                             |
| `fixture_paths_in`              | `(impl AsRef<Path>) -> Result<Vec<String>, FixtureReadError>`        | Lists repository-relative fixture entries in deterministic sorted order.                                                                  |
| `golden_markdown_ir_fixture`    | `(impl AsRef<Path>) -> Result<GoldenDocument, io::Error>`            | Builds the private Markdown golden IR shape used by Rust snapshot tests.                                                                  |
| `golden_python_ir_fixture`      | `(impl AsRef<Path>) -> Result<IrDocument, GoldenPythonFixtureError>` | Builds the canonical Python docstring IR used by Rust snapshot tests.                                                                     |
| `golden_rust_ir_fixture`        | `(impl AsRef<Path>) -> Result<IrDocument, GoldenRustFixtureError>`   | Builds the canonical Rust doc-comment IR used by Rust snapshot tests.                                                                     |
| `normalize_repository_path`     | `(impl AsRef<Path>) -> String`                                       | Converts repository-relative paths to `/`-separated snapshot text.                                                                        |
| `apply_round_trip_edits`        | `(&str, &[RoundTripEdit]) -> Result<RoundTripEditResult, Error>`     | Applies source-backed test edits while rejecting synthetic, invalid, or overlapping ranges.                                               |
<!-- markdownlint-enable MD060 -->

Add `stilyagi-test-support` as a dev-dependency in any crate whose tests
require repository-relative fixture access. Do not copy the `repository_root`
resolution pattern into individual crates. Bridge and API contract tests should
use these helpers when asserting canonical IR region kinds, raw source bytes,
or directory-wide fixture coverage so the test corpus is read through one
capability-oriented path.

#### Snapshot and round-trip helper workflow

Golden IR scaffolding is intentionally internal while the public pytest plugin
from RFC 0004 remains future work. Rust snapshot tests use `insta` and write
snapshot files next to the owning test module, for example under
`crates/stilyagi-extract/tests/snapshots/` or
`crates/stilyagi-test-support/tests/snapshots/`. Python snapshot tests use
`syrupy` and write JSON snapshots under `tests/__snapshots__/`. Markdown,
Python docstring, and Rust doc-comment golden helpers all follow the same
canonical IR contract. Update snapshots only when the reviewed contract changes:

```bash
INSTA_UPDATE=always cargo test -p stilyagi-ir -p stilyagi-test-support -p stilyagi-extract
.venv/bin/python -m pytest tests/test_round_trip_helpers.py --snapshot-update
```

The golden IR helper scope currently covers Markdown and Python docstrings.
Markdown helper output records the repository-relative fixture path, syntax,
byte-oriented `line_index`, one whole-document `source` segment for non-blank
Markdown, and an empty diagnostics list. Python helper output delegates to the
tree-sitter-backed extractor and returns the canonical `IrDocument` envelope
with owner metadata, bounded tree nodes, source-backed docstring segments, and
recoverable parse errors where applicable. These helpers are scaffolding for
regression tests, not the final public pytest plugin.

#### Structural performance probe workflow

The cold and warm structural baseline probe is maintainer-facing test
scaffolding. It records the pre-NLP structural fast path through
`stilyagi.engine.extract_document` and the embedded Rust extractor. It does not
exercise `stilyagi check`, and it does not set a universal wall-clock budget
for every workstation.

Run the probe after `make build` so the editable Python environment points at
the current PyO3 extension:

```bash
.venv/bin/python -m tests.performance.structural_probe \
  --mode both \
  --output build/performance/structural-baseline.json
```

The generated report is ignored under `build/performance/`. It contains
repository-relative fixture paths, environment metadata, and per-iteration
nanosecond timings. The committed test snapshot redacts volatile durations and
environment values; update it only when the JSON contract changes:

```bash
.venv/bin/python -m pytest tests/test_structural_performance_probe.py --snapshot-update
```

In this repository, a cold structural run means the measured extraction happens
inside a fresh Python interpreter launched with
`sys.executable -m tests.performance.structural_probe --child-run`. It
deliberately does not flush operating-system page caches or require elevated
host privileges. A warm structural run means one extraction primes the current
interpreter before the measured iterations run in that same interpreter.

Use the probe output as review evidence when changing the structural extractor,
Python adapter, or build spine. Compare cold with cold and warm with warm, and
look for large regressions in context rather than treating one noisy local
sample as a hard threshold. If later roadmap slices extend `stilyagi check`
with additional subcommands or persistent Stilyagi caches, update this section
and the ExecPlan-backed tests together.

Round-trip edit helpers exist to test fix safety before the full rule engine
lands. They must preserve source text outside edited ranges, accept adjacent
source-backed edits, reject synthetic spans, and reject overlapping source
edits. Add property tests for range invariants when examples are too narrow;
the first Rust helper property verifies that a single replacement preserves the
generated prefix and suffix.

<!-- markdownlint-enable MD001 -->

## 2b. The `stilyagi check` pipeline

The `check` command is the first end-to-end pipeline that crosses the
Rust–Python boundary for a user-facing operation. Understanding its seams helps
maintainers add steps, insert new collaborators, and write tests at the right
level.

### Entry point

`cli.py` `main()` builds the argument parser via `cli_args.build_parser()`,
parses the arguments into an immutable `CheckOptions` via
`cli_args.options_from_args()`, and then calls
`run_check(options, *, resolver=None, renderer=None)`.

### Collaborator injection

`run_check` constructs its own collaborators when the caller does not supply
them: a fresh `config.ConfigResolver` and a fresh `engine.RendererRegistry`.
Because both are created inside the call, no configuration cache is shared
between separate `run_check` invocations. Passing pre-constructed collaborators
is the intended seam for tests that need to inspect or stub out either
collaborator.

### Discovery

`run_check` delegates target collection to `_discover_targets`, which calls:

```python
discovery.discover_markdown_files(targets, config) -> list[DiscoveredFile]
```

`DiscoveredFile` is a frozen dataclass with two fields:

- `reported_path` — the command-line-relative POSIX path used for
  user-facing output
- `resolved_path` — the fully resolved filesystem path used for
  de-duplication and stable ordering

Discovery is a single deterministic pass, sorted by resolved path, that skips
known build-noise directories (`.git`, `build`, `dist`, `node_modules`,
`target`, `.venv`) and does not follow symlinked directories. The configuration
that governs discovery is resolved by `cli._resolve_discovery_config` for the
current working directory rather than for each individual file, so
`--isolated`, explicit `--config` values, and CLI rule overrides all stay in
force during the discovery pass.

### Configuration loading and resolution

- `config/load.py` loads and validates individual config files
  (`load_config_file`, `discover_same_directory_config`) through a shared
  `_read_config_document` helper that maps missing, unreadable, or malformed
  files to a typed `InvalidConfigError`. `load_config_table(path)` reads one
  supported TOML file and returns the selected Stilyagi mapping; for
  `pyproject.toml` it selects `[tool.stilyagi]`, while a missing namespace
  selects an empty mapping. Read and TOML parsing failures are reported as
  `InvalidConfigError`.
- `config/parse.py` `parse_config_table(table, path=path)` converts the
  selected mapping into a `StilyagiConfig`, preserving the raw reserved values.
  Unsupported keys and invalid field or section values raise
  `InvalidConfigError` with the source path and offending key.
- `config/resolve.py` defines `ConfigResolver`, which owns the per-run
  discovery and resolved-table caches so one `run_check` invocation reuses
  parsed config across many targets while leaking no state between runs. The
  module-level `resolve_config_for_path` wraps a fresh single-use resolver for
  callers that resolve only one target. The cache contract is deliberate and
  narrow:
  - Caches belong to the instance; separate resolvers never share state, so the
    former process-wide caches cannot leak a stale table into an unrelated run.
  - Nearest-config discovery hands its raw table to the resolver, so a config
    file found while walking ancestors is not read again when it is resolved.
  - Within a run, config files are treated as stable: a file is read and parsed
    once and reused for every target, so an on-disk edit made mid-run is not
    observed. There is no in-run invalidation hook because a single
    `stilyagi check` invocation reads each config once; observing an edit
    requires constructing a new resolver.
  - A single `ConfigResolver` is not safe to share across threads (its caches
    are unsynchronized dicts). The supported model is one resolver per run, so
    concurrent work should give each thread its own resolver.
  - The resolver records discovery and resolved-table cache hit/miss counts,
    queryable through the `cache_stats` property. Each pipeline stage
    (discovery, config load/resolve, extraction, diagnostics mapping,
    rendering, and exit-code computation) emits log records through a
    per-module `logging` logger, so runs can be traced without changing any
    user-facing output.
- `config/schema.py` holds the frozen config dataclasses (`StilyagiConfig`,
  `LintConfig`, `MarkdownExtractConfig`, `NlpConfig`) and the shared
  `ConfigError` base class, with `InvalidCacheDirError` and
  `InvalidConfigError` as typed subclasses.
- `config/validate.py` holds the boundary type validators. In particular,
  `ensure_mapping` requires string keys as well as a mapping value and raises
  `InvalidConfigError` for either violation.

### Diagnostics

For each discovered file, `_check_one_file` extracts the document through the
Rust bridge, resolves the per-file config, and collects diagnostics from two
sources:

- `engine/checker.py` `map_ir_errors(document, reported_path)` maps the
  canonical IR error envelope on `Document.ir` into `diagnostics.Diagnostic`
  objects, propagating each IR-provided error code and falling back to a generic
  `IR000` placeholder only when the IR omits one.
- `rules_registry.run_rules(document, resolved_config)` runs the registered
  rule set against the extracted document.

`diagnostics_location.py` converts IR byte offsets into 1-based line and column
positions. `diagnostics.py` defines the `Diagnostic` dataclass and the
`Severity` enum.

### Rendering

`engine/renderers.py` `RendererRegistry.render(diagnostics, output_format)`
sorts diagnostics by path, location, and code, then renders either:

- deterministic text: one line per finding formatted as
  `path:line:column: severity code message`, followed by a summary line; or
- a stable JSON document.

Unknown format strings raise `ValueError`.

### Exit codes

`cli.compute_exit_code` returns:

- `0` — no diagnostics found
- `1` — one or more diagnostics found
- `2` — error (failed file read, invalid config, extractor failure, or usage
  error)

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

- Syntax and locale scope
  - Current implemented extraction support covers Markdown, Python
    docstrings, and Rust documentation comments.
  - MDX remains preview-only until later evidence upgrades it into the stable
    support matrix.
  - English is the only formally supported locale in v1. Architecture may stay
    locale-aware, but maintainers must not imply broader support before the
    product earns it through later slices and tests.

- IR structure
  - The near-term extractor contract is a stable, region-oriented IR with
    canonical JSON debug output, `line_index`, `content_hash`, `segments`,
    owner metadata, and explicit extraction errors or suppressions where they
    exist.
  - The current RFC 0001 field names are `document.syntax`, `tree.syntax`, and
    `region.syntax`. `region.host_language` is gone, `region.natural_language`
    is now optional, and `region.owner` is now required even when its value is
    `null`.
  - Region kinds `comment_block` and `jsdoc_block` are no longer part of the
    stable extractor vocabulary, and `summary_line` is now a derived
    analysis-layer view rather than an extractor-level region kind.
  - Markdown `list_item` and `blockquote` IR regions are thin containers.
    `frontmatter_field` is reserved but not yet emitted, and Markdown
    `image_alt` / `link_title` regions are synthetic decoded-text surfaces
    until byte-accurate source spans are implemented.[^5]
  - When maintainers update fixtures, adapters, or runtime wrappers, they
    should treat the field migration explicitly. The minimal before or after
    mapping is:

    ```python
    # Before RFC 0001 alignment
    document.language
    tree.language
    region.language
    region.host_language

    # After RFC 0001 alignment
    document.syntax
    tree.syntax
    region.syntax
    region.natural_language  # optional
    region.owner  # required, may be None
    ```

  - The in-process Rust to Python boundary may become more efficient than JSON,
    but JSON remains the canonical debug and test form for `dump-ir`, golden
    fixtures, and contract review.
  - `RegionTarget` is the primary stable v1 rule-targeting surface. Markdown
    node traversal remains supported, but non-Markdown `NodeRef` and
    `NodeTarget` usage should stay narrow and debug-oriented until later slices
    prove a broader node contract.
  - Python docstring owner metadata follows
    [ADR 006](adr-006-docstring-owner-metadata.md). Module docstrings use
    `owner.kind == "module"` with `name` and `qualname` serialized as `null`.
    Class and function docstrings use Python `__qualname__` semantics; a
    definition nested inside a function receives `<locals>` after the function
    frame, for example `outer.<locals>.inner`.
  - Python docstring region text is the verbatim tree-sitter `string_content`
    source slice. Extraction does not decode escapes, dedent, or apply PEP 257
    cleaning; that normalization belongs to later rule layers.
  - The Python tree-sitter producer records `node_store: "bounded"` and
    `owner_qualname: "python"` in producer metadata. V1 rules should depend on
    regions, source-backed `segments`, and `owner` metadata rather than a full
    Python concrete syntax tree. Future work that needs decorators,
    signatures, bases, or package-qualified module names must explicitly widen
    the extractor contract.
- Rule API surface
  - RFC 0002 now treats `syntaxes` as the rule-metadata field for source
    formats. `locales` is the new optional companion field for prose-locale
    constraints.
  - `RegionTarget` now accepts `kind`, `scope_has`, `syntax`,
    `natural_language`, and `owner_kind`. `RuleContext.regions(...)` should use
    the same filter names: `kind`, `syntax`, `natural_language`, and
    `owner_kind`.
  - `Region` runtime objects must carry at minimum `syntax`,
    `natural_language`, and `owner`, plus the convenience accessors
    `owner_kind` and `owner_name`.
  - Stable v1 `NodeRef` and `NodeTarget` usage is Markdown-only. Non-Markdown
    node traversal remains a debug or preview surface and should not be the
    basis of shipped rule-pack contracts.
  - Maintainers updating rules or examples should use the post-alignment
    surface directly. The minimal before or after migration looks like:

    ```python
    # Before RFC 0002 alignment
    class ExampleRule(Rule):
        languages = {"markdown"}
        targets = [RegionTarget(kind={"heading"}, language={"markdown"})]


    ctx.regions(kind={"heading"}, language={"markdown"})


    # After RFC 0002 alignment
    class ExampleRule(Rule):
        syntaxes = {"markdown"}
        locales = {"en"}
        targets = [
            RegionTarget(
                kind={"heading"},
                syntax={"markdown"},
                natural_language={"en"},
                owner_kind=None,
            )
        ]


    ctx.regions(
        kind={"heading"},
        syntax={"markdown"},
        natural_language={"en"},
        owner_kind=None,
    )
    ```

- Suppression semantics
  - Suppression state is extracted once and carried in the IR rather than
    inferred ad hoc by individual rules.
  - V1 suppression remains syntax-native and deliberately narrow: configuration
    ignores, file-level directives, and named inline or range directives in
    host-language comments. Blanket inline suppression remains out of scope.
  - `range_role` records `disable` as `open` and `enable` as `close`, so rule
    authors and downstream stages can rely on the IR instead of re-parsing
    comment bytes.
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

The Rust code now lives in a root Cargo workspace declared by `Cargo.toml`,
with the PyO3 bridge in `crates/stilyagi-pyext/` and the first shared library
boundary in `crates/stilyagi-core/`. The Python package source root lives under
`python/stilyagi/`.

The bridge crate builds as the package-scoped `stilyagi._stilyagi_rs` extension
module. PyO3 provides the binding layer, while `maturin` handles development
installs and wheel builds.

The current integration contract is intentionally small:

- Rust exports Python-callable functions through the `stilyagi._stilyagi_rs`
  module.
- Python package code imports and orchestrates the extension rather than
  duplicating Rust-owned logic.
- Rust tests cover Rust-only behaviour, while Python tests cover package-level
  integration and user-facing behaviour.

The first real extraction path is now:

```plaintext
python/stilyagi/engine/extraction.py
  -> stilyagi._stilyagi_rs.extract_document(source, syntax)
  -> crates/stilyagi-pyext/src/lib.rs
  -> crates/stilyagi-extract/src/lib.rs
```

That split is deliberate. Rust owns extraction mechanics, source-fidelity
metadata, IR construction, and FFI adapter mechanics for exposing stable engine
building blocks. Python owns the public model, package-level orchestration, and
policy layer. The public Python surface adapts Rust bridge output into
`stilyagi.model.Document`, `stilyagi.model.Region`, and the optional
`Document.ir` mapping without moving user-facing policy into the extension
crate.

String-only extraction uses anonymous IR source identity: `document.path` and
`document.uri` are serialized as `null` instead of synthetic memory paths or
URIs. Callers with real file context should use the identity-aware extraction
API once the relevant adapter or CLI surface exposes it, so source identity is
supplied at the boundary rather than invented inside the IR domain.

Table: Current Markdown, Python, and Rust extraction differences.

<!-- markdownlint-disable MD060 -->
| Topic          | Markdown extraction                                                                           | Python docstring extraction                                                                                          | Rust doc-comment extraction                                                                                         |
| -------------- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Parse entry    | Markdown parser over the full source document.                                                | `tree-sitter-python` parser over the full source file.                                                               | `tree-sitter-rust` parser over the full source file.                                                                |
| Traversal      | Markdown flattener walks Markdown structure and emits rendered prose regions.                 | Depth-first tree-sitter walk inspects module, class, and function first statements.                                  | Depth-first tree-sitter walk inspects modules, owner-bearing items, and item bodies for doc comments.               |
| Error recovery | Markdown parser recovery is represented through Markdown IR behaviour and malformed fixtures. | tree-sitter recovery emits partial docstring regions plus `python-parse-recovery` errors.                            | tree-sitter recovery emits partial doc-comment regions plus `rust-parse-recovery` errors.                           |
| Owner metadata | `owner` remains `null`; section context must not overload the owner field.                    | `owner` identifies module, class, or function using Python `__qualname__` semantics.                                 | `owner` identifies module, struct, enum, trait, function, impl, or item using `::` semantics and inner/outer rules. |
| Node store     | Markdown currently exposes the structural nodes needed by Markdown region mapping.            | Python exposes a bounded store: synthetic module root, docstring-owning definitions, and docstring string nodes.     | Rust exposes a bounded store: synthetic crate root, owning items, and doc-comment nodes.                            |
| Text surface   | Markup is flattened and may use synthetic segments for rendered prose.                        | Region text is verbatim `string_content`; no escape decoding, dedent, or PEP 257 cleaning happens during extraction. | Region text is verbatim marker-stripped prose with synthetic separators for merged line runs.                       |
<!-- markdownlint-enable MD060 -->

The `crates/stilyagi-ir` crate owns the syntax-neutral IR vocabulary and
document envelope. The `crates/stilyagi-markdown` crate owns Markdown-specific
IR production, while the `crates/stilyagi-tree-sitter` crate owns Python
docstring and Rust doc-comment IR production. All three producers emit the same
`IrDocument` shape, and unsupported syntaxes must not receive placeholder IR
payloads.

`stilyagi_ir::content_hash_for` computes the stable Secure Hash Algorithm
(SHA-256) content hash that IR documents persist as `document.content_hash`.
The digest suffix is rendered
by the crate-internal `to_lower_hex` helper in `canonical_json.rs` rather than
with the `{:x}` format specifier because `sha2` 0.11 changed `digest()` to
return `hybrid_array::Array<u8, _>`, which does not implement `LowerHex`. The
rendering stays lowercase and zero-padded so persisted IR hashes remain
byte-identical.

The `crates/stilyagi-ir/tests/ui.rs` test runs a `trybuild` compile-fail fixture
that verifies direct `format!("{digest:x}")` formatting does not compile for
the `sha2` 0.11 digest output. The
`crates/stilyagi-ir/tests/ui/sha2_digest_lower_hex.stderr` file records the
expected compiler diagnostic snapshot. If an intentional compiler diagnostic
change occurs, refresh the snapshot with:

```bash
TRYBUILD=overwrite cargo test -p stilyagi-ir --test ui
```

Changes to the FFI boundary should stay narrow. A good boundary exports
source-fidelity primitives, extraction results, and other stable engine
building blocks. A bad boundary exports policy-heavy convenience wrappers that
would force rule-engine churn into the extension crate.

The repository should also resist any drift toward a subprocess helper model
unless a later ADR explicitly reopens that question. The accepted v1 boundary
is in-process, and later roadmap steps may assume that constraint.[^1]

For local testing, the workspace intentionally no longer enables
`pyo3/extension-module` through the shared dependency declaration. Current PyO3
guidance for modern `maturin` releases is to let the build backend manage the
extension-module build mode so `cargo test` can still link and execute the Rust
test binaries.[^3] Because this now relies on the packaging backend exporting
`PYO3_BUILD_EXTENSION_MODULE`, the repository pins maturin in both the
build-system and dev-tooling dependencies.

### 4.1 Maturin and PyO3 compatibility tests

The repository pins maturin in both `pyproject.toml` `[dependency-groups].dev`
and `[build-system].requires`. Keep those pins in sync when updating maturin.
The Python tests in `tests/test_maturin_build.py` validate that contract,
assert that the installed maturin module matches the pin, and build a native
wheel whose normalized metadata and layout are compared with a syrupy snapshot.

To refresh the native wheel snapshot after a maturin or PyO3 update, run:

```bash
uv run --group dev pytest tests/test_maturin_build.py \
    --snapshot-update -k test_maturin_wheel_build_snapshot
```

The PyO3 bridge crate also uses [trybuild](https://github.com/dtolnay/trybuild)
to validate representative macro patterns at compile time. The UI fixtures live
under `crates/stilyagi-pyext/tests/ui/`:

- `pass/` contains Rust files that must compile.
- `fail/` contains Rust files that must fail with diagnostics matching the
  corresponding `.stderr` file.

Run the compile-time UI tests with:

```bash
cargo test --manifest-path Cargo.toml -p stilyagi-pyext compile_time_ui
```

If a PyO3 or compiler upgrade intentionally changes compile-fail diagnostics,
refresh the expectation files with:

```bash
TRYBUILD=overwrite cargo test --manifest-path Cargo.toml \
    -p stilyagi-pyext compile_time_ui
```

Inspect the updated `.stderr` files before committing to confirm that the fail
test still represents a genuine PyO3 contract violation.

### 4.2 Current mixed-package skeleton

The general architecture above now maps to concrete repository modules and
crates. Maintainers should use [repository layout](repository-layout.md) as the
authoritative directory ownership and responsibility map when discussing or
extending the current skeleton.

Those boundaries deliberately mirror the ownership split in section 2. When a
change belongs to extraction fidelity, syntax parsing, or source mapping, it
should usually start in one of the Rust crates. When a change belongs to
configuration discovery, diagnostics, plugin registration, capability planning,
or rule orchestration, it should usually start in one of the Python modules
listed in the repository layout.

There are also three concrete cross-boundary rules worth preserving:

- Python package code should import the embedded extension through
  `stilyagi._stilyagi_rs` and then expose user-facing orchestration from the
  `stilyagi` package surface, rather than letting callers bind to a second
  top-level module.
- The Python extraction adapter lazily caches bridge vocabularies at process
  scope. Syntax-vocabulary validation is protected by a module lock so
  concurrent callers share one validated state, and bridge-patching tests must
  reset that state through the dedicated test helper before observing patched
  vocabularies. Its public `extract_document(source, syntax)` adapter validates
  the bridge vocabulary, converts the Rust payload into a `model.Document`, and
  preserves the optional IR JSON mapping on that document.
- The Rust workspace should not depend on Python package modules for policy or
  plugin decisions. Python owns orchestration and registration; Rust owns
  extraction and source fidelity.

The extraction adapter exposes three vocabulary helpers at the Python/Rust
boundary:

- `supported_region_kinds() -> tuple[str, ...]` returns the canonical
  region-kind names supplied by the Rust bridge. The result is cached and is
  the source used to identify region kinds recognized by Python.
- `warn_unknown_ir_region_kinds(
  ir_payload: collections.abc.Mapping[str, object] | None, *,
  operation: str,
  ) -> None` emits one warning for each canonical IR region kind returned by
  the Rust bridge that Python does not recognize. Each warning includes the
  operation, region index, and unknown kind. The helper does not alter the IR
  payload or abort extraction.
- `reset_extraction_state_for_tests() -> None` is test-only. It resets the
  process-wide syntax-vocabulary validation state and clears the cached
  `supported_region_kinds` result and known-kind lookup data. Tests that patch
  bridge vocabulary functions must call it before and after the patched state;
  production code must not call it.

## 5. Build workflow

The standard development and release workflows are:

```bash
make build
make release
```

`make build` is the development path. It recreates the virtual environment,
installs the editable Python package plus the compiled extension, and leaves
the repository ready for local linting and tests. It finishes by running
`make smoke`, which calls `python -m stilyagi.smoke` through `.venv/bin/python`
and verifies that the public Python engine API crosses into the embedded Rust
extension.

`make release` is the release artefact path. It first runs:

```bash
uv run --group dev maturin build --release --manifest-path crates/stilyagi-pyext/Cargo.toml --out dist
```

That command produces Python wheel artefacts in `dist/`, which is the expected
distribution surface for the mixed package. The target then runs
`make smoke-release`, installs the built wheel into `.venv-release-smoke`, and
executes `python -m stilyagi.smoke` from `/tmp` so the proof uses the wheel
artefact rather than the repository source tree.

The `build-release` target exists as a compatibility alias and should remain
behaviourally identical to `release`.

The `.github/workflows/smoke.yml` workflow is the bounded CI smoke path for
this repository. Its Ubuntu `lint-test` job installs Python, Rust, `uv`, and
the support tools required by the checked targets, then runs `make check-fmt`,
`make markdownlint`, `make nixie`, `make typecheck`, `make lint`, and
`make test`. Its `release-smoke` matrix builds and smoke-tests release wheels
on Ubuntu, macOS, and Windows. The workflow is not release publishing
automation; it proves that local development installs and release wheels
exercise the same PyO3 boundary.

## 6. Lint, typecheck, and test workflow

The Makefile is the canonical workflow entrypoint. `make all` runs the local
commit gates in sequence and is the default target. The current checks are:

- `make all`
- `make fmt`
- `make check-fmt`
- `make markdownlint`
- `make nixie`
- `make lint`
- `make typecheck`
- `make test`

Their responsibilities are:

- `make all`
  - run `make check-fmt`
  - run `make typecheck`
  - run `make lint`
  - run `make test`
  - run `make markdownlint`
  - run `make nixie`
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
  - enforce en-GB-oxendict (Oxford) spelling over the same files with
    `typos`, run at the version pinned by the Makefile `TYPOS_VERSION`
    variable through `uv tool run`
- `make nixie`
  - validate Mermaid diagrams in Markdown files
- `make lint`
  - run Ruff checks through `uv`
  - run Interrogate docstring-coverage checks requiring 100% coverage
  - run focused Pylint checks through the pinned `pylint-pypy-shim` wrapper
    under PyPy
  - run every `df12-python-lints` v0.1.0 Pylint message under CPython 3.14
    from immutable commit `9c835f35b0f1690597ade799c9c6a30bc5922959`
  - scan syrupy snapshots under `tests` with `ambrleaks` from the same locked
    development environment and immutable commit under CPython 3.14
  - run `cargo doc` for all workspace crates and features with Rustdoc warnings
    denied
  - run `cargo clippy` for all workspace crates, targets, and features with
    warnings denied
  - run Whitaker for all workspace crates, targets, and features with warnings
    denied
  - run Skylos as the final strict production dead-code check over
    `python/stilyagi`, excluding `tests`
- `make typecheck`
  - It rebuilds the editable environment when needed.
  - It runs `cargo check` for all workspace crates, targets, and features with
    warnings denied.
  - It runs the pinned `ty` 0.0.72 release through `uv tool run`.
- `make test`
  - verify Rust formatting
  - rerun `cargo clippy`
  - run Rust tests with `cargo-nextest` when available, otherwise `cargo test`
  - run Rust doc tests explicitly with Rustdoc warnings denied
  - run Python tests through `.venv/bin/python -m pytest -v`
- `make smoke`
  - run `python -m stilyagi.smoke` against the development install
- `make smoke-release`
  - rebuild the release wheel if needed
  - install it into `.venv-release-smoke`
  - run `python -m stilyagi.smoke` from outside the repository tree

The project-backed Python tools run through `uv run --group dev` so the
repository uses the locked dev toolchain instead of whatever happens to be on
the host `PATH`. Ruff, Interrogate, and the CPython `df12-python-lints` Pylint
pass use the locked `dev` dependency group. The focused Pylint pass is the
exception: it runs through `uv tool run --python pypy` with the pinned
[`pylint-pypy-shim`](https://github.com/leynos/pylint-pypy-shim) wrapper. Both
`df12-python-lints` commands use the locked development environment under
CPython 3.14, resolving the immutable commit
`9c835f35b0f1690597ade799c9c6a30bc5922959` recorded in `uv.lock`. These Python
tiers run before the Rust lint tiers, with Interrogate enforcing a 100%
docstring-coverage threshold. Skylos runs after the Rust lint tiers as the
final lint step.

### Shared workflow parser

Workflow contract tests use `tests/support/workflows.py::load_workflow` to
parse GitHub Actions YAML with PyYAML's `BaseLoader`. This preserves scalar
values as strings, including the `on` key, so tests can inspect workflow
structure without YAML type coercion. The helper accepts only a top-level
mapping and raises `TypeError` with the message
`A workflow must parse to a top-level mapping` for other document shapes.

Both `tests/test_ci_workflow_units.py` and
`tests/test_skylos_lint_contract.py` reuse this helper instead of maintaining
separate workflow parsers.

### 6a. Python linting architecture

ADR 004 records the accepted Python linting architecture.[^4] The short version
is that Python linting has five tiers:

1. Ruff runs first through `uv run --group dev ruff check`.
2. Interrogate runs second with `--fail-under 100` over `python/stilyagi` and
   `tests`.
3. Pylint runs third through `uv tool run --python pypy` and the pinned
   `pylint-pypy-shim` wrapper.
4. The `df12-python-lints` plugin runs fourth through the locked development
   environment under CPython 3.14, with all v0.1.0 messages enabled, from
   immutable commit `9c835f35b0f1690597ade799c9c6a30bc5922959`.
5. `ambrleaks` runs fifth through that same locked CPython 3.14 environment
   and immutable commit, scanning `tests` for unredacted snapshot values.

`make lint` then continues into the Rust lint tiers owned by the repository:

1. `cargo doc --workspace --all-features --no-deps` with
   `RUSTDOCFLAGS=-D warnings`
2. `cargo clippy --workspace --all-targets --all-features -- -D warnings`
3. `whitaker --all -- --workspace --all-targets --all-features` with
   `RUSTFLAGS=-D warnings`
4. Skylos runs last through its pinned CPython 3.14 tool environment, scanning
   production dead code strictly.

The repository root `clippy.toml` owns the Clippy thresholds used by the
workspace, including the four-argument maximum and the low complexity and
function-length ceilings. Those limits apply to production code, unit tests,
integration tests, and PyO3 bridge code because the Makefile runs all-targets,
all-features checks through `cargo clippy`.

Run the full lint gate with:

```bash
make lint
```

Run lint commands sequentially. The repository uses shared build and tool
caches, and the canonical command order is the one encoded in the Makefile.

The Makefile exposes the lint runner through these variables:

Table: Lint runner Makefile variables.

| Variable                    | Default                                                                                                       | Purpose                                                          |
| --------------------------- | ------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `UV`                        | first `uv` on `PATH`, falling back to `$(HOME)/.local/bin/uv`                                                 | Selects the `uv` executable used by Makefile Python commands.    |
| `UV_ENV`                    | `UV_CACHE_DIR=.uv-cache UV_TOOL_DIR=.uv-tools`                                                                | Keeps `uv` cache and tool state inside the repository worktree.  |
| `UV_RUN`                    | `$(UV_ENV) $(UV) run --group dev`                                                                             | Runs commands in the locked development dependency group.        |
| `INTERROGATE`               | `$(UV_RUN) interrogate`                                                                                       | Selects the docstring-coverage command used by `make lint`.      |
| `INTERROGATE_TARGETS`       | `python/stilyagi tests`                                                                                       | Selects the directories checked by Interrogate.                  |
| `INTERROGATE_FLAGS`         | `--fail-under 100`                                                                                            | Requires complete Python docstring coverage.                     |
| `PYLINT_PYTHON`             | `pypy`                                                                                                        | Selects the interpreter passed to `uv tool run` for Pylint.      |
| `PYLINT_TARGETS`            | `python/stilyagi tests`                                                                                       | Selects the directories checked by the Pylint tier.              |
| `PYLINT_PYPY_SHIM_REF`      | `726d09f968b4d729ee4b29c71fc732e744854f3b`                                                                    | Pins the shim commit used by the Pylint tier.                    |
| `PYLINT_PYPY_SHIM`          | `git+https://github.com/leynos/pylint-pypy-shim.git@$(PYLINT_PYPY_SHIM_REF)`                                  | Expands the pinned shim package source.                          |
| `PYLINT`                    | `$(UV_ENV) $(UV) tool run --python $(PYLINT_PYTHON) --from '$(PYLINT_PYPY_SHIM)' pylint-pypy --load-plugins=` | Builds the focused PyPy Pylint command used by `make lint`.      |
| `DF12_PYTHON`               | `3.14`                                                                                                        | Selects CPython for the df12 Pylint and scanner tiers.           |
| `DF12_PYLINT_MESSAGES`      | all thirteen v0.1.0 message IDs                                                                               | Selects the df12 Pylint diagnostics.                             |
| `DF12_PYLINT`               | project-backed Pylint with `df12_python_lints` loaded                                                         | Builds the CPython df12 Pylint command.                          |
| `AMBRLEAKS`                 | locked `uv run --group dev --python 3.14` environment                                                         | Builds the snapshot leak scanner command from the locked commit. |
| `SKYLOS_VERSION`            | `4.33.2`                                                                                                      | Pins the dead-code detector used by `make lint`.                 |
| `SKYLOS_CLI`                | `$(UV_ENV) $(UV) tool run --python 3.14 --from 'skylos==$(SKYLOS_VERSION)' skylos`                            | Builds the command-only Skylos CLI.                              |
| `SKYLOS`                    | `$(SKYLOS_CLI) --config-file pyproject.toml`                                                                  | Adds scan-only configuration to the Skylos CLI.                  |
| `SKYLOS_PRODUCTION_TARGETS` | `python/stilyagi`                                                                                             | Limits dead-code analysis to production Python sources.          |
| `SKYLOS_EXCLUDE_FOLDERS`    | `tests`                                                                                                       | Excludes tests from the production liveness graph.               |
| `TY_VERSION`                | `0.0.72`                                                                                                      | Pins the `ty` version shared by the Makefile and CI.             |
| `TY`                        | `env $(UV_ENV) $(UV) tool run ty@$(TY_VERSION)`                                                               | Builds the pinned type-checking command.                         |
| `TYPOS_VERSION`             | `1.48.0`                                                                                                      | Pins the `typos` version shared by the Makefile and CI.          |
| `TYPOS`                     | `env $(UV_ENV) $(UV) tool run typos@$(TYPOS_VERSION)`                                                         | Builds the spelling-check command used by `make markdownlint`.   |

Override these variables only for local diagnosis unless the project-wide lint
policy is intentionally changing. For example:

```bash
make lint PYLINT_TARGETS=python/stilyagi
make lint PYLINT_PYTHON=pypy3.11
make lint DF12_PYTHON=3.14
```

The lint policy imported from
[`leynos/episodic`](https://github.com/leynos/episodic) is a policy baseline,
not an automatic upstream subscription. Future Episodic rule changes should be
reviewed deliberately before they are copied into Stilyagi. This branch imports
the current Ruff selector set, deprecated `typing.*` banned API table, and
focused Pylint message allowlist because they match Stilyagi's maintenance
goals: fast first-pass feedback, explicit import discipline, predictable
docstring style, low complexity ceilings, lazy logging, safer subprocess and
file handling, and review pressure on branch-heavy or overgrown functions.

The Python lint configuration lives in `pyproject.toml`:

- `[tool.ruff]`
  - sets the line length, preview mode, and Python target version
- `[tool.ruff.lint]`
  - selects the active Ruff rule families, including `ASYNC`, `D`, and `DOC`
  - ignores only the two pydocstyle conflicts that oppose the chosen style
- `[tool.ruff.lint.per-file-ignores]`
  - allows test-specific assertions and test helper signatures without
    weakening application-code linting
- `[tool.ruff.lint.flake8-import-conventions]`
  - bans broad `from` imports for modules whose aliases are standardized
- `[tool.ruff.lint.flake8-import-conventions.aliases]`
  - records the approved aliases, including `typing as typ`,
    `collections.abc as cabc`, and `datetime as dt`
- `[tool.ruff.lint.flake8-tidy-imports.banned-api]`
  - rejects deprecated `typing.*` generic aliases in favour of modern
    builtins, `collections.abc`, `contextlib`, `collections`, and `re`
- `[tool.ruff.lint.pydocstyle]`
  - keeps NumPy docstring style as the project convention
- `[tool.ruff.lint.pydoclint]`
  - treats concise one-line summaries as complete and requires explicit
    return, yield, and raise contracts for substantive docstrings
- `[tool.ruff.lint.mccabe]`
  - caps cyclomatic complexity at 8
- `[tool.ruff.lint.pylint]`
  - mirrors the strict Ruff-side Pylint compatibility thresholds for
    arguments, boolean expressions, and locals
- `[tool.pylint.main]`
  - sets the Python 3.14 policy baseline, enables recursive directory
    traversal, and caps module length
- `[tool.pylint.design]`
  - sets the focused Pylint design thresholds that complement Ruff
- `[tool.pylint."messages control"]`
  - disables all Pylint messages by default, disables `syntax-error` for the
    PyPy-backed runner, and enables only the explicitly selected focused-Pylint
    diagnostics

When adding or suppressing lint rules, keep the reason near the configuration
or suppression. The df12 plugin requires each lint or type-check suppression to
include an explanation. Ruff suppressions use `# noqa`, while Pylint
suppressions use `# pylint: disable=...`; do not use one tool's suppression
syntax to hide the other tool's finding.

### 6b. Skylos dead-code gate

`make lint` runs a blocking Skylos scan after the existing Python and Rust
linters. It analyses dead code only over `python/stilyagi`, excludes `tests`,
and uses the strict configuration in `pyproject.toml`. `SKYLOS_CLI` pins the
tool under CPython 3.14; `SKYLOS` adds `--config-file` for scans, while the
`skylos-allow` target uses the command-only CLI so its `whitelist` subcommand
is placed before the arguments.

Treat every Skylos finding as a candidate for removal until its caller is
verified. Prefer a typed `[tool.skylos.dead_code]` entry-point rule for an
implicit runtime caller. Only when that rule cannot model the boundary, use a
narrow named exception with its verified runtime caller:

```shell
make skylos-allow SYMBOL=registered_handler \
  REASON="Loaded by the plugin registry; verified in the registry contract test"
```

The target rejects empty `SYMBOL` or `REASON` values with status 2 and records
the explanation under `[tool.skylos.whitelist.documented]`. `SYMBOL` is
required explicitly so WSL's injected `NAME` variable cannot satisfy the
contract.

### 6c. Fallibility in Rust test helpers

Whitaker's `no_expect_outside_tests` and `no_unwrap_or_else_panic` encode a
policy that is easy to misread: **fixture and helper functions are not tests.**
A fixture arranges state, arrangement can fail, and a failure there is a broken
test rather than a test verdict. Clippy's `allow-expect-in-tests` covers a
`#[test]` or `#[rstest]` *body*; it does not cover the helper functions sitting
beside them, and attribute-driven functions (rstest `#[fixture]`, `#[serial]`
tests, and macro-generated step functions) are invisible to the lint because
their attributes are gone by the time it runs.

Resolve a finding in this order.

1. **Propagate.** Change the helper to return `Result` and let the test body
   unwrap. `crates/stilyagi-markdown/src/tests/malformed.rs` shows the shape:
   `document_for` returns `Result<IrDocument, Message>` and each test calls
   `.expect("expected Markdown IR document")` in its own body. Do not convert
   the *test* to return `Result` — `clippy::panic_in_result_fn` is denied
   workspace-wide, so `assert!` and `assert_eq!` are unavailable there.
2. **Attribute the failure to the caller.** Where a helper legitimately
   asserts, mark it `#[track_caller]` so a failure names the calling test
   instead of the helper. This is what otherwise forces shared assertion shapes
   to become macros. `assert_validation_reports` in
   `crates/stilyagi-markdown/src/tests/ir_consistency.rs` is the reference.
3. **Funnel through the one documented boundary.** Some contexts genuinely
   cannot propagate: a `proptest` strategy constructor returns
   `impl Strategy<Value = T>` with nowhere to put an error, and `prop_map`
   closures cannot use `?`. Those use
   [`ExpectValid`](../crates/stilyagi-test-fixtures/src/expect_valid.rs), which
   lives in `stilyagi-test-fixtures` because that crate depends on nothing from
   the extraction crates and so can be consumed from any crate's tests without
   forming a cycle.

```rust,no_run
use proptest::prelude::Strategy;
use proptest::string::string_regex;
use stilyagi_test_fixtures::ExpectValid;

fn regex_strategy(pattern: &'static str) -> impl Strategy<Value = String> {
    string_regex(pattern).expect_valid(pattern)
}
```

**Scope and re-use policy for `ExpectValid`.** Use it only where an error
cannot be propagated — strategy constructors, `prop_map` closures, fixture
builders used by `proptest!` bodies (including helpers also exercised by
deterministic tests), and shared assertion helpers with no `Result`-compatible
contract. Mark the latter `#[track_caller]` so their failures name the calling
test. Do not reach for it to avoid threading a `Result` through an ordinary
fixture; step 1 governs there. Its methods are `#[track_caller]`, so failures
report the fixture that is wrong.

What not to do: do not scatter bespoke `match { Err(error) => panic!(…) }`
helpers or divergent `let`-`else` blocks through test modules. They satisfy the
lint while reproducing the problem it exists to surface — an unnamed panic
boundary per call site. One named, documented boundary is auditable; twenty
anonymous ones are not.

Two crates additionally define `must_ok!` and `must_some!` macros
(`crates/stilyagi-markdown/src/tests.rs` and
`crates/stilyagi-pyext/src/bridge_bdd.rs`). Those remain correct *inside* a
test body, where a macro expands in place. They are duplicated across the two
crates; consolidating them onto `ExpectValid` is tracked as follow-up work
rather than done piecemeal.

### 6d. Spelling gate

`make markdownlint` enforces en-GB-oxendict (Oxford) spelling over the
repository's Markdown prose with [`typos`](https://github.com/crate-ci/typos),
as required by the [documentation style guide](documentation-style-guide.md).
The generated configuration lives in the repository-root `typos.toml` and works
in three layers:

1. The `en-gb` locale corrects American spellings (`color` to `colour`,
   `behavior` to `behaviour`, `analyzed` to `analysed`).
2. The estate-wide base dictionary bundled by `leynos/typos-config-builder`
   restores Oxford spelling, which the locale alone would not enforce. Identity
   entries accept `-ize` inflections that the locale would otherwise "correct"
   to `-ise`, while `-ise` entries are corrected to `-ize`. Stems taking `-yse`
   (`analyse`, `paralyse`) remain with the locale, which already enforces them.
3. `typos.local.toml` adds only Stilyagi-specific accepted words, quoted
   upstream names, and excluded fixtures.

`typos.toml` is a generated file. Never edit its entries by hand. The focused
builder is pinned to immutable commit
`b604f198797fdd36a567dd0f8f07b13f9539b241`. Regenerate from its bundled shared
base and the local overlay with:

```bash
make spelling-config-write
```

The builder conditionally refreshes `.typos-oxendict-base.toml` from its
bundled authority before rendering. The cached base and its
`.typos-oxendict-base.json` freshness metadata are untracked. A newer valid
local cache is not overwritten by an older source, and a populated cache
supports offline generation. `make spelling-config` checks generated drift
without rewriting the tracked output.

Spelling policy has two maintainer-facing homes:

- Generic Oxford stems, accepted terms, and phrase corrections belong in the
  bundled authority in `leynos/typos-config-builder`. Do not add genuinely
  `-ise`-only words (`advise`, `revise`, `exercise`, `supervise`).
- Stilyagi-only accepted words, ignore patterns, and file exclusions belong in
  `typos.local.toml`. Keep exceptions narrow: quoted APIs retain upstream
  spelling and should normally be put in backticks rather than added as
  word-level exceptions.

The spelling gate first checks generated configuration, then applies shared
exact-phrase corrections to eligible tracked UTF-8 text. This enforces
`hand-written` to `handwritten`, which Typos cannot represent after tokenizing
a hyphenated phrase. Typos then runs over the `MD_FILES_FIND` list shared with
markdownlint and nixie. It uses `--force-exclude` so the `typos.toml` excludes
also apply to explicitly passed paths. To fix Typos findings mechanically,
rerun the gate's command with `--write-changes` appended, using the same pinned
version the Makefile prints when `make markdownlint` runs:

```bash
env UV_CACHE_DIR=.uv-cache UV_TOOL_DIR=.uv-tools \
  uv tool run typos@<TYPOS_VERSION> --config typos.toml --force-exclude \
  --write-changes <files>
```

Review automated rewrites before committing; spelling corrections must not
touch code samples, API names, or quoted material.

The phrase helper follows the CodeRabbit-reviewed consumer baseline. Its
isolated test runner supplies Pathspec 1.1.1 without adding a project runtime
or locked development dependency.

### 6e. Tool version alignment between the Makefile and CI

The Makefile and `.github/workflows/smoke.yml` must resolve identical lint tool
versions. The repository uses two mechanisms:

- Ruff and Interrogate are pinned in the `pyproject.toml` `dev` dependency
  group and run through `uv run --group dev`, so both the Makefile and CI
  resolve the same locked version from `uv.lock`. CI must not install either
  tool separately; `tests/test_build_spine_units.py` asserts that no standalone
  Interrogate install step exists in the workflow.
- `typos` is a Rust binary rather than a locked Python dependency, so its
  version is pinned once in the Makefile `TYPOS_VERSION` variable and run
  through `uv tool run typos@$(TYPOS_VERSION)`. CI inherits the pin by calling
  `make markdownlint`.

When bumping any of these versions, update the single source of truth (the
dependency-group pin or `TYPOS_VERSION`), refresh `uv.lock` where relevant, and
rerun the affected gates.

### 6f. Workflow pins and Dependabot

Dependabot owns the upgrade of GitHub Actions and reusable workflows, including
calls into `leynos/shared-actions`. Contract tests that assert a caller's exact
commit SHA create a lockstep dependency: every time Dependabot opens a bump PR,
the test fails until a human edits the pinned constant to match. That defeats
the purpose of automated dependency updates and turns a routine bump into a
manual chore.

Contract tests may still verify the *shape* of a reusable-workflow caller. They
must not verify the specific SHA value.

- Do assert the workflow references the correct reusable workflow path.
- Do assert the ref is pinned to a full 40-character commit SHA, not a
  mutable branch such as `main` or `rolling`.
- Do assert the expected `on:` triggers, least-privilege `permissions:`, and
  the inputs the caller relies on.
- Do not hard-code the current SHA value as an expected string. Match it with
  a pattern instead.
- Do not fail a test purely because Dependabot bumped the pinned SHA.

```python
import re

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def test_uses_pinned_full_sha(caller_step):
    ref = caller_step["uses"].split("@")[-1]
    assert SHA_RE.match(ref), f"expected a 40-hex commit SHA, got {ref!r}"
```

If a workflow's behaviour genuinely depends on a feature only present from a
particular commit onwards, express that as a comment or a changelog note, not
as a test assertion on the SHA string.

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

## References

[^1]: [ADR 002: Ratify the packaging boundary](adr-002-packaging-boundary.md)
[^2]: [ADR 003: Ratify the v1 contract scope](adr-003-v1-contract-scope.md)
[^3]: [PyO3 FAQ: linker issues with `cargo test`](https://pyo3.rs/main/faq)
[^4]: [ADR 004: Adopt layered Python linting](
    adr-004-python-linting-architecture.md)
[^5]: [ADR 005: Scope Markdown region vocabulary](
    adr-005-markdown-region-vocabulary-scope.md)

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

The grammar layer has six maintainer-facing pieces that should move together:
the `GrammarNode` hierarchy, normalized enums, morphology access, pattern
objects, capability planning, and visitor hooks.

### 9.1 GrammarNode hierarchy

`GrammarNode` is the shared source-backed base for derived grammar objects:

```python
class GrammarNode:
    span: SourceSpan
    text: str
    region: RegionNode
    document: DocumentNode

    def walk(self) -> Iterable["GrammarNode"]: ...
    def nearest(self, kind: type[T]) -> T | None: ...
```

`TokenNode` and `SentenceNode` are the first compatibility wave and should land
before higher-order helpers such as `NounPhraseNode`, `ClauseNode`, and
`CoordinationNode`.

```python
class TokenNode(GrammarNode):
    index: int

    lemma: str | None
    pos: UPos | None
    fine_pos: str | None
    morph: MorphFeatures

    dep: Dep | None
    raw_dep: str | None

    head: TokenNode | None
    children: tuple[TokenNode, ...]

    prev: TokenNode | None
    next: TokenNode | None

    confidence: float | None
    provider: str

    def ancestors(self) -> tuple[TokenNode, ...]: ...
    def descendants(self) -> tuple[TokenNode, ...]: ...
    def subtree(self) -> SpanNode: ...
    def next_content(self) -> TokenNode | None: ...
    def prev_content(self) -> TokenNode | None: ...
    def children_with_dep(self, *deps: Dep) -> tuple[TokenNode, ...]: ...
    def has_child(
        self,
        *,
        dep: Dep | None = None,
        pos: UPos | None = None,
    ) -> bool: ...
    def subject(self) -> TokenNode | None: ...
    def object(self) -> TokenNode | None: ...
    def governing_verb(self) -> TokenNode | None: ...
    def is_finite_verb(self) -> bool: ...
    def is_content(self) -> bool: ...
    def is_coordinated(self) -> bool: ...


class SentenceNode(GrammarNode):
    tokens: tuple[TokenNode, ...]

    def content_tokens(self) -> tuple[TokenNode, ...]: ...
    def first_content_token(self) -> TokenNode | None: ...
    def roots(self) -> tuple[TokenNode, ...]: ...
    def verbs(self) -> tuple[TokenNode, ...]: ...
    def finite_verbs(self) -> tuple[TokenNode, ...]: ...
```

The six `SentenceNode` helpers removed above are reserved for a later grammar
wave: `noun_phrases()`, `clauses()`, `coordinations()`, `main_clause()`,
`leading_modifier_clause()`, and `fronted_subordinate_clauses()` MAY return as
later-wave or preview surface once the layer-one token and sentence model has
proven stable.

Maintainers should preserve three behavioural points from RFC 0005:

- `next_content()` and `prev_content()` skip non-content tokens according to
  `is_content()` and must not cross sentence boundaries.
- `is_coordinated()` is the published guard for tokens participating in
  coordination structures that agreement-sensitive rules should treat as
  syntactically plural or multi-headed.
- Higher-order nodes are analysis-layer views derived from token and dependency
  data, not extractor-owned base facts persisted into the IR by default.

### 9.2 Canonical enums and morphology

`UPos` and `Dep` are the normalized enums that make the public grammar API
backend-neutral. `UPos` represents canonical universal part-of-speech tags,
while `Dep` represents normalized dependency relations. Rules should match on
these enums rather than on backend-owned labels. Raw backend labels still
matter, but they stay in `fine_pos` and `raw_dep` for debugging and provider
escape hatches.

`MorphFeatures` is the normalized morphology wrapper that preserves raw feature
data while exposing typed accessors for common cases:

```python
class MorphFeatures:
    raw: Mapping[str, tuple[str, ...]]

    @property
    def number(self) -> str | None: ...

    @property
    def person(self) -> str | None: ...

    @property
    def tense(self) -> str | None: ...

    @property
    def verb_form(self) -> str | None: ...

    @property
    def voice(self) -> str | None: ...

    def has(self, feature: str, value: str) -> bool: ...
    def has_any(self, feature: str, values: set[str]) -> bool: ...
```

When maintainers add provider support, they should normalize onto these fields
instead of re-exporting backend morphology objects directly.

### 9.3 Pattern APIs

RFC 0005 defines two Stilyagi-owned pattern layers:

- `TokenPattern`
  - matches linear token sequences against normalized token fields
  - example shape:

    ```python
    TokenPattern([
        {"POS": UPos.ADV, "LEMMA": {"IN": {"very", "really"}}},
        {"POS": UPos.ADJ},
    ])
    ```

- `DependencyPattern`
  - matches syntactic relations anchored on normalized dependency data
  - example shape:

    ```python
    DependencyPattern(
        anchor={"POS": UPos.VERB},
        children=[
            {"DEP": Dep.NSUBJ_PASS},
            {"DEP": Dep.AUX_PASS, "OPTIONAL": True},
        ],
    )
    ```

Providers may compile these patterns into backend matchers internally, but the
rule-facing contract stays Stilyagi-owned.

### 9.4 Capability enum and provider protocol

RFC 0005's grammar capability model currently defines the following public
names:

```python
class Capability(Enum):
    # Layer-one compatibility wave
    SENTENCES = "sentences"
    TOKENS = "tokens"
    POS = "pos"
    FINE_POS = "fine_pos"
    LEMMA = "lemma"
    MORPH = "morph"
    DEPENDENCY = "dependency"

    # Later wave / preview surface
    NOUN_PHRASES = "noun_phrases"
    CLAUSES = "clauses"
    COORDINATION = "coordination"
    COREFERENCE = "coreference"  # reserved for later wave / preview
    SEMANTIC_LEXICON = "semantic_lexicon"
```

The normative planner relationships are:

- `POS` implies `TOKENS`.
- `FINE_POS` implies `POS`.
- `DEPENDENCY` implies `TOKENS` and `SENTENCES`.
- `NOUN_PHRASES`, `CLAUSES`, and `COORDINATION` require `DEPENDENCY` or a
  provider-specific equivalent.
- `MORPH` may imply `POS` for some providers, but rules must still declare both
  when they need both.

The planner must reject a rule when the configured provider cannot satisfy its
declared capabilities. RFC 0002 remains the current canonical planner
vocabulary until implementation and RFC wording converge, so maintainers should
avoid shipping parallel public constant sets.

The `GrammarProvider` protocol should remain narrow:

```python
class GrammarProvider(Protocol):
    name: str
    capabilities: frozenset[Capability]

    def annotate(
        self,
        regions: Sequence[RegionNode],
        required: set[Capability],
    ) -> GrammarDocument: ...
```

Providers annotate extracted regions after capability planning has decided what
enrichment is required. Backend-owned objects such as spaCy tokens may exist
behind explicit unstable escape hatches, but they are not the public maintainer
contract.

### 9.5 Visitor hook signatures

Rules may implement the following grammar-aware hooks:

```python
# Layer-one hooks
def visit_token(self, ctx, token: TokenNode): ...
def visit_sentence(self, ctx, sentence: SentenceNode): ...


# Later-wave hooks
def visit_noun_phrase(self, ctx, noun_phrase: NounPhraseNode): ...
def visit_clause(self, ctx, clause: ClauseNode): ...
def visit_coordination(self, ctx, coordination: CoordinationNode): ...
```

These hooks extend, rather than replace, the base visitor surface from RFC 0002:

- `prepare(ctx, document)`
- `visit_document(ctx, document)`
- `visit_region(ctx, region)`
- `visit_node(ctx, node)`
- `visit_sentence(ctx, sentence)`
- `visit_token(ctx, token)`
- `finalize(ctx, document)`

The runtime should only invoke hooks whose required capabilities were
materialized for the current run. New hook types should be treated as public
rule-API work and reviewed with the same care as new CLI or IR fields.

### 9.6 Debug surfaces and maintainer rule

`dump-ir` remains the canonical extractor debug view. Grammar-aware debugging
should be additive, for example `dump-ir --include-grammar`, rather than by
baking provider-owned grammar objects into the base IR schema.

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
- Use `make smoke-release` when you need to rerun only the release-wheel smoke
  proof after a release artefact has been built.
- Keep the Python package metadata and the Rust extension build path in sync.
- Treat release-affecting changes to the Makefile, `pyproject.toml`, or
  `crates/stilyagi-pyext/Cargo.toml` as coupled changes that need end-to-end
  verification.

If release packaging changes, this guide, the design document, and the relevant
RFCs should be reviewed together so the documented contract remains accurate.
