# Implement Rust documentation-comment extraction with owner metadata

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
`Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`, `Decision Log`,
and `Outcomes & Retrospective` must be kept up to date as work proceeds. Each
revision must remain self-contained.

Status: COMPLETE

Approval gate: satisfied. The user request for roadmap item 3.1.2 is the
explicit approval recorded for this plan. Begin implementation stage work in
order and keep this document current.

## Purpose / big picture

Roadmap item 3.1.2 proves that Stilyagi's extraction and intermediate
representation (IR) loop reaches into Rust source trees, just as item 3.1.1
proved it for Python. It answers one question from
[docs/roadmap.md](../roadmap.md) §3.1: can the extractor recover the owner
metadata and source maps that documentation-comment rules need for Rust
modules, types, functions, and item-level declarations?

After the approved implementation, a maintainer can call the existing
extraction path with the `rust_doc_comment` syntax on a representative Rust
file and inspect canonical IR JSON that contains, for each documentation
comment, a `rust_doc_comment` region whose flattened `text` is the prose
carried by the doc-comment markers, whose `segments` map that text back to
exact source bytes, and whose `owner` identifies the owning item (module,
struct, enum, trait, function, impl, or item-level declaration) by `kind`,
`name`, and `qualname`.

The observable success condition is not "the code compiles". For the shared
Rust fixture, canonical IR JSON snapshots must be stable, every emitted region's
`segments` must reconstruct its `text` exactly, every region's `owner` must
name the correct owning item, and a malformed Rust fixture must still produce
partial extraction plus a recoverable error rather than aborting the run. The
Rust `ExtractSyntax::ALL` and Python `Syntax` vocabularies must still agree,
and the PyO3 bridge must accept `"rust_doc_comment"` and return `ir_json` whose
`Document.ir` exposes the regions with owner metadata.

This slice deliberately stops at owner-aware extraction. It does not implement
Rust documentation-comment lint rules (roadmap item 3.2.2), Rust suppression
parsing (roadmap item 3.1.3), discovery defaults for `*.rs` (roadmap item
3.2.1), or any Markdown-inside-doc-comment analysis. It supplies the IR facts
those later items must trust. It reuses the ADR 006 `owner` field contract
while defining Rust-specific owner kinds and qualified-name semantics, exactly
as [docs/stilyagi-design.md](../stilyagi-design.md) §12 ("Exact owner metadata
shape for Rust documentation comments") anticipates.

## Context and orientation

The repository is a mixed Rust and Python project. Rust crates live under
`crates/`, the Python package lives under `python/stilyagi/`, Python tests live
under `tests/`, shared corpus fixtures live under `tests/fixtures/corpus/`, and
behaviour-driven development (BDD) feature files live under `features/` and
under each crate's `tests/features/`.

The precursor slice, roadmap item 3.1.1 (Python docstring extraction), is
complete and is the template this plan mirrors. Read
[docs/execplans/3-1-1-python-docstring-extraction.md](3-1-1-python-docstring-extraction.md)
in full before implementing: the Rust extractor is a sibling of the Python
extractor and should reuse its shapes, module layout, producer-metadata
pattern, golden-builder pattern, snapshot naming, BDD structure, and Python
parity pattern.

The relevant Rust crates are:

- `crates/stilyagi-ir/`, which owns the stable IR domain vocabulary. It defines
  `IrDocument`, `DocumentMetadata`, `ProducerMetadata`, `IrTree`, `IrNode`,
  `NodeFlags`, `SourceSpan`, `IrRegion`, `IrSegment`, `SegmentOrigin`,
  `IrOwner`, `IrError`, `SourceIdentity`, the `content_hash_for`/
  `line_index_for` helpers, and `SCHEMA_VERSION`. The owner contract already
  exists:
  `IrOwner { kind: String, name: Option<String>, qualname: Option<String> }` in
  `crates/stilyagi-ir/src/region.rs`. Do not redefine these types elsewhere.
- `crates/stilyagi-tree-sitter/`, the tree-sitter-backed source extractor. It
  currently exposes the Python extractor as a `python` module
  (`crates/stilyagi-tree-sitter/src/python/`) plus the public
  `python_docstring_ir_document` and `PythonExtractError`, re-exported from
  `crates/stilyagi-tree-sitter/src/lib.rs`. The Python module is split into
  `mod.rs`, `helpers.rs`, `observe.rs`, `owner.rs`, `support.rs`, and
  `types.rs`. This crate gains a sibling `rust` module with the same layout, so
  item 3.1.2 reshapes nothing that item 3.1.1 built.
- `crates/stilyagi-markdown/`, the Markdown adapter. Its
  `crates/stilyagi-markdown/src/flatten.rs` is the reference implementation for
  emitting a region whose `text` is assembled from more than one segment,
  mixing source-backed `IrSegment`s with synthetic `IrSegment`s (used for the
  soft breaks joining wrapped lines). The Rust extractor reuses this
  synthetic-separator pattern to merge consecutive line doc comments into one
  prose region; its CR-LF soft-break snapshots
  (`crates/stilyagi-markdown/src/snapshots/stilyagi_markdown__tests__paragraph_soft_break_crlf.snap`)
  are the reference for line-ending handling.
- `crates/stilyagi-extract/`, which owns syntax dispatch.
  `crates/stilyagi-extract/src/lib.rs` defines `ExtractSyntax` (with a
  `RustDocComment` variant spelled `"rust_doc_comment"`), `RegionKind` (with
  `Document` and `PythonDocstring` variants), and `ExtractError` (with
  `MarkdownIr`, `PythonIr`, `UnsupportedSyntax`, `UnknownSyntax` arms and a
  compile-time size assertion
  `size_of::<ExtractError>() <= EXTRACT_ERROR_SIZE_LIMIT_BYTES`). Today
  `extract_document_with_source_identity` returns
  `Err(ExtractError::UnsupportedSyntax(ExtractSyntax::RustDocComment))` for
  Rust. This slice wires that arm to a new `extract_rust_document`, mirroring
  the existing `ExtractSyntax::PythonDocstring => extract_python_document` arm.
- `crates/stilyagi-pyext/`, the PyO3 bridge.
  `crates/stilyagi-pyext/src/lib.rs` serializes an attached `IrDocument` to
  canonical `ir_json` and maps `ExtractError::UnsupportedSyntax(_)` to
  `PyNotImplementedError`. `crates/stilyagi-pyext/src/tests.rs` has
  `extract_document_py_exposes_python_docstrings`; a Rust analogue is added.
  Enabling Rust extraction needs no new bridge fields.
- `crates/stilyagi-test-support/`, which provides fixture access and golden IR
  builders. `crates/stilyagi-test-support/src/golden_fixture_builder.rs` defines
  `golden_python_ir_fixture(...) -> Result<IrDocument, GoldenPythonFixtureError>`,
  which reads a corpus fixture and calls the production Python extractor so
  the golden output cannot invent a second schema. A `golden_rust_ir_fixture`
  sibling is added the same way.
- `crates/stilyagi-test-fixtures/`, which owns fixture path constants and
  readers. `crates/stilyagi-test-fixtures/src/fixture_paths.rs` defines
  `SHARED_PYTHON_FIXTURE_PATH`, `MALFORMED_PYTHON_FIXTURE_PATH`,
  `NESTED_PYTHON_FIXTURE_PATH`, and `EDGE_CASE_PYTHON_FIXTURE_PATH`. Rust
  siblings are added here.

The relevant Python modules are:

- `python/stilyagi/engine/extraction.py`, which adapts the raw bridge payload
  into typed `model.Document` objects and parses `ir_json` into `Document.ir`.
- `python/stilyagi/model/document.py`, which defines `Syntax` (a `StrEnum` whose
  members already include `RUST_DOC_COMMENT = "rust_doc_comment"`) and
  `Document`.
- `python/stilyagi/model/region.py`, which defines `Region` with `kind` and
  `text`.
- `python/stilyagi/_stilyagi_rs.pyi`, the type stub mirroring the extension
  payload.

The relevant fixtures (added by roadmap item 1.3.1, already on `main`) are:

- `tests/fixtures/corpus/rust/valid/item-doc-comments.rs`, which contains a
  crate-level inner doc comment (`//!`), an item-level outer doc comment
  (`///`) on `pub struct FixtureExample`, a method outer doc comment inside
  `impl FixtureExample`, a plain non-doc comment
  (`// stilyagi-disable-next-line terminology`), and a free-function outer doc
  comment on `pub fn fixture_function()`.
- `tests/fixtures/corpus/rust/malformed/unclosed-item.rs`, which contains a
  crate-level `//!` doc comment, an outer `///` doc comment on
  `pub fn broken_function()`, and a function body whose block never closes.
  Malformed Rust fixtures keep the plain `.rs` suffix (unlike malformed Python,
  which uses `.py.txt`); `tests/test_corpus.py` encodes this asymmetry
  (`if syntax == "python" and category == "malformed"` is the only `.py.txt`
  branch). The `.rs` malformed fixture already passes repository formatters and
  gates on `main` because it lives under `tests/fixtures/` and is never a Cargo
  compilation target.

Definitions used in this plan:

- IR means intermediate representation: Stilyagi's stable logical payload for
  source structure, lintable prose regions, source positions, and debug output.
- Region means a lintable prose surface. For this slice, the only new region
  kind is `rust_doc_comment`.
- Owner means the code entity a documentation comment documents. RFC 0001
  reserves the region `owner` field for this code-entity contract.
- Segment means a mapping from a span of region text to either original source
  bytes (`source`) or an explicit synthetic insertion (`synthetic`).
- Outer doc comment means `///` (line) or `/** ... */` (block); it documents the
  item that immediately follows it. Inner doc comment means `//!` (line) or
  `/*! ... */` (block); it documents the enclosing item (the crate root, or the
  `mod` whose body it opens). This attachment is fixed by the Rust language;
  reference: the Rust Reference, "Comments" / "Doc comments"
  (<https://doc.rust-lang.org/reference/comments.html>). Web verification of
  that page was attempted during planning but the session's web tooling
  (Firecrawl, WebFetch, WebSearch) is not permitted here; the attachment rules
  restated in this plan are pinned by Stage 1 spike assertions and Stage 2
  table tests, not taken on trust.
- `qualname` means a Rust-style qualified name using `::` separators, built from
  the chain of enclosing named items plus the owned item's name. See the
  `Decision Log` for the precise semantics adopted here.
- tree-sitter is the incremental, error-tolerant parsing library mandated by the
  design. tree-sitter-rust is its Rust grammar. In that grammar, documentation
  comments parse as `line_comment` and `block_comment` nodes; the extractor
  classifies and slices them by their leading source bytes (see the mechanism
  in Stage 2), a policy that does not depend on grammar-version-specific
  doc-comment child nodes.
- Span drift means any mismatch between a reported source offset and the bytes
  that actually produced the corresponding region text.

## Documentation and skill signposts

Before implementing this plan, load and apply these skills:

- `leta`, for symbol-aware Rust and Python navigation. Refresh the workspace
  with `leta workspace add "$(pwd)"` at the start of each session. Use
  `leta show`/`leta refs`/`leta grep` instead of ad-hoc `read-file`/`rg` when a
  symbol name is known.
- `rust-router`, which routes to the smaller Rust skills below.
- `arch-crate-design`, because this change extends the `stilyagi-tree-sitter`
  crate boundary with a sibling `rust` module and its public-versus-internal
  surface.
- `hexagonal-architecture`, to keep the boundary clean: `stilyagi-ir` owns the
  domain IR types; `stilyagi-tree-sitter` is an adapter that depends inward on
  the IR; `stilyagi-extract` orchestrates; `stilyagi-pyext` and the Python
  package are transport and application layers.
- `rust-types-and-apis`, for the new public extractor function signature, the
  Rust owner-derivation types, and the new `ExtractError`/`RegionKind` arms.
- `rust-errors`, for mapping tree-sitter parse anomalies to `IrError` and for
  the new `RustExtractError` and `ExtractError::RustIr` arms.
- `rust-unit-testing` and `rust-testing-with-rstest-fixtures`, for rstest
  fixtures and parameterized owner-derivation tables.
- `proptest`, for the segment-reconstruction and qualname invariants.
- `nextest`, for targeted Rust test execution with `cargo nextest`.
- `python-router`, then `python-testing` and `python-types-and-apis`, for the
  pytest, pytest-bdd, and typed-adapter work. Load `python-verification` then
  `hypothesis` for the Python property test.
- `arch-decision-records`, for the Rust owner-metadata ADR (ADR 007) in
  Y-Statement format.
- `en-gb-oxendict`, for all prose, comments, and commit messages (British
  English, Oxford `-ize`/`-yse`/`-our` spelling).
- `commit-message`, for every commit; messages are written to a temporary file
  and applied with `git commit -F` (never `git commit -m`).
- `pr-creation`, for the eventual draft pull request.

Keep these repository documents open:

- [docs/roadmap.md](../roadmap.md), item 3.1.2 and its requirements on 2.1.1 and
  1.3.1.
- [docs/stilyagi-design.md](../stilyagi-design.md), especially §§3.2, 4, 7.1,
  10, 11, and the §12 open question "Exact owner metadata shape for Rust
  documentation comments".
- [RFC 0001](../rfcs/0001-stilyagi-intermediate-representation.md), the regions
  and owner sections.
- [docs/adr-003-v1-contract-scope.md](../adr-003-v1-contract-scope.md), which
  fixes Rust documentation comments as a stable v1 syntax surface.
- [docs/adr-006-docstring-owner-metadata.md](../adr-006-docstring-owner-metadata.md),
  whose `owner` field contract and bounded-node-store policy this slice reuses;
  its "Follow-on work" explicitly hands Rust owner kinds and qualified-name
  semantics to this item.
- [docs/execplans/3-1-1-python-docstring-extraction.md](3-1-1-python-docstring-extraction.md),
  the precursor slice this plan mirrors.
- [docs/execplans/2-1-1-markdown-ir-envelope.md](2-1-1-markdown-ir-envelope.md),
  for the Markdown envelope shape and the Python-versus-Rust parity pattern.
- [Complexity antipatterns](../complexity-antipatterns-and-refactoring-strategies.md),
  to keep the traversal, classification, and owner-derivation logic small
  enough to review.
- [reliable testing via dependency injection](../reliable-testing-in-rust-via-dependency-injection.md),
  for explicit IO boundaries.
- [docs/rust-doctest-dry-guide.md](../rust-doctest-dry-guide.md), if new public
  Rust documentation includes examples.
- [docs/rstest-bdd-users-guide.md](../rstest-bdd-users-guide.md), for Rust BDD
  behaviour tests.
- [docs/developers-guide.md](../developers-guide.md) and
  [docs/users-guide.md](../users-guide.md), for the documentation updates.

External prior art relied on during planning:

- The `tree-sitter` Rust crate is pinned at `0.25.10` in the workspace
  (`Cargo.toml` `[workspace.dependencies]`). tree-sitter-python `0.25.0`
  already builds against it and exposes its grammar through the `LANGUAGE`
  constant (`tree_sitter_python::LANGUAGE`); the Rust grammar crate follows the
  same `LANGUAGE: LanguageFn` convention. The exact compatible
  `tree-sitter-rust` version is confirmed empirically in Stage 1 before
  pinning, because the session's web tooling (Firecrawl `firecrawl_*`,
  `WebFetch`, `WebSearch`) and the out-of-worktree Cargo registry cache are not
  accessible here, so the exact published version list could not be read during
  planning. This is a version confirmation, not a mechanism fork: the mechanism
  (a tree-sitter-rust grammar loaded through `LANGUAGE`, parsed with
  `tree-sitter` `0.25.x`) is fixed.
- The Rust Reference, "Comments"
  (<https://doc.rust-lang.org/reference/comments.html>), fixes doc-comment
  forms and their inner/outer attachment. As noted above, the page could not be
  fetched in this session; every attachment and classification claim is pinned
  by a Stage 1 spike assertion or a Stage 2 table test rather than taken on
  trust.

## Constraints

- Do not implement this plan until explicit approval is recorded in this file's
  `Decision Log`.
- Preserve roadmap scope. This item implements owner-aware Rust
  documentation-comment extraction into the existing IR envelope. It does not
  implement Rust suppression parsing (3.1.3), discovery defaults (3.2.1),
  documentation-comment rules (3.2.2), or cache-key separation (3.3.1). The
  plain `//` non-doc comment in the shared fixture (the
  `stilyagi-disable-next-line` line) must be ignored by extraction; suppression
  handling is out of scope.
- Keep Markdown and Python behaviour unchanged. Their paths, snapshots, and
  public surfaces must not regress. Do not touch the `python` module of
  `stilyagi-tree-sitter` except to place the new `rust` module beside it.
- The `stilyagi-ir` crate owns the IR domain types. The Rust extractor adapts to
  them. Do not redefine owner, region, segment, span, or document types in
  `stilyagi-tree-sitter`, `stilyagi-extract`, `stilyagi-pyext`, or Python.
- Keep source offsets byte-oriented. tree-sitter byte offsets map directly onto
  `SourceSpan` (UTF-8 bytes); any line or column data is derived from
  `line_index` and never replaces byte offsets as ground truth.
- Region `segments` must reconstruct `text` exactly
  (`IrRegion::segments_reconstruct_text` must hold for every emitted region).
  If a doc-comment shape cannot satisfy this, that shape stays out of scope and
  is recorded as a limitation rather than emitted incorrectly.
- The doc-comment lint surface is the verbatim source bytes carried by the
  markers, with the markers themselves treated as elided markup. For a line doc
  comment the content is the bytes after the `///`/`//!` marker to the end of
  that line, verbatim (leading spaces are content, not stripped). For a block
  doc comment the content is the bytes between the opening `/**`/`/*!` marker
  and the closing `*/`, verbatim. v1 does not apply rustdoc's leading-space
  stripping, common-indentation removal, `*`-column stripping, or Markdown
  parsing during extraction; that normalization belongs to the later rule
  layer. This keeps every source-backed segment fix-safe.
- Consecutive line doc comments of the same flavour (`///` or `//!`) that
  attach to the same owner, with no intervening item, blank line, or non-doc
  token, merge into one `rust_doc_comment` region. The merged region's `text`
  joins each line's content using synthetic `IrSegment` separators exactly as
  `crates/stilyagi-markdown/src/flatten.rs` joins soft-broken lines, so
  `segments_reconstruct_text` holds and the source-backed segments still
  re-slice to their exact source bytes. A block doc comment is one region with
  a single source-backed content segment. Line ending handling for the
  synthetic separators follows the Markdown soft-break convention and is pinned
  by snapshot and property tests rather than restated here.
- `owner` is populated for every `rust_doc_comment` region and follows the
  RFC 0001 / ADR 006 code-entity contract (`kind`, optional `name`, optional
  `qualname`). Outer doc comments own the immediately following item; inner doc
  comments own the enclosing item. Crate-root inner doc comments emit
  `kind: "module"`, `name: null`, `qualname: null`, mirroring the Python module
  owner. `IrOwner` `name`/`qualname` are plain `Option` with no
  `skip_serializing_if`, so a `None` serializes as JSON `null`.
- Traversal and identifiers are deterministic: walk named children depth-first,
  left-to-right; assign node identifiers (`n0`, `n1`, …) in emission order;
  assign region identifiers (`r0`, `r1`, …) in doc-comment-discovery order; and
  append `errors` entries in source order.
- Keep the non-Markdown structural surface minimal, exactly as ADR 006 requires
  for Python. The Rust extractor emits a bounded node store: a synthetic
  `module` (crate) root, each doc-comment-owning item node, and each emitted
  doc-comment node, with honest parent/child links. Undocumented enclosing
  items collapse to the nearest emitted owner. It does not emit the full Rust
  concrete syntax tree. The producer options record `node_store: "bounded"` and
  `owner_qualname: "rust"`.
- Malformed Rust must produce partial extraction plus recoverable `errors`
  entries, never a panic or aborted run. Never unwrap tree-sitter results; walk
  the recovered tree, skip `ERROR`/`MISSING` subtrees while still emitting
  well-formed doc comments, and record one `IrError` per top-level `ERROR`/
  `MISSING` subtree in source order.
- Extraction is pure over `(source, identity)`. No filesystem or environment
  access inside the extractor; IO stays at test and orchestration boundaries.
- Determinism: traversal order, generated identifiers, JSON field order, and
  canonical JSON output must not depend on hash-map ordering or platform
  specifics. Canonical JSON snapshots must avoid machine-specific absolute
  paths, timestamps, nondeterministic ordering, terminal colour, and
  environment values.
- Corpus `.rs` fixtures added by this plan must be `rustfmt`-clean so
  `make check-fmt` never rewrites them and churns snapshot spans. Formatter- or
  line-ending-sensitive shapes (CR-LF doc comments, `////` non-doc comments,
  unusual spacing, block-comment edge cases) live in inline test sources, not
  corpus files, mirroring the 3.1.1 decision to keep the CR-LF case inline.
- Use `rstest` for Rust unit tests, `rstest-bdd` for Rust behaviour tests,
  `insta` for Rust snapshots, `proptest` for Rust invariants, `pytest` for
  Python unit tests, `pytest-bdd` for Python behaviour tests, `syrupy` for
  Python snapshots, and `hypothesis` for the Python property test.
- Do not add Kani, CrossHair, or Verus work unless a substantive unbounded
  invariant emerges that is better proved than tested. The `Decision Log`
  records why none is in scope at planning time (the invariants here — exact
  segment reconstruction and deterministic qualname derivation — are fully
  covered by proptest and table tests, matching 3.1.1).
- Run format, typecheck, lint, and tests sequentially, never in parallel.
  Capture long output with `tee` into `/tmp` logs. Delegate full commit-gate
  runs to the `scrutineer` subagent per repository policy.
- Commit after each gated stage. Never commit failing code. Never use
  `git commit -m`.
- On completion, mark only roadmap item 3.1.2 as done in `docs/roadmap.md`.

## Tolerances (exception triggers)

- Scope: if implementation requires changing more than twenty files or roughly
  1,300 net new lines excluding snapshots and fixtures, stop and ask before
  continuing.
- Dependencies: adding the Rust crate `tree-sitter-rust` (a version compatible
  with `tree-sitter` `0.25.10` and exposing `LANGUAGE`) to the workspace is
  expected. Any other new external dependency requires approval. If no published
  `tree-sitter-rust` builds against `tree-sitter` `0.25.10` because of an
  application binary interface (ABI) mismatch, stop and record the compatible
  pair before pinning.
- Build toolchain: tree-sitter grammars compile vendored C through the `cc`
  crate; a working C compiler must exist locally and in CI. The Python grammar
  already imposes this requirement, so it should already be satisfied. If a
  build host lacks a C compiler, stop and escalate.
- Public API: if a supported Python API or public Rust API must be removed or
  renamed rather than extended compatibly, stop and present options. Updating
  the pyext behaviour that maps `rust_doc_comment` to `PyNotImplementedError`
  into a success path is an expected, in-scope change, not a breaking change.
- Owner semantics: if the shared fixture, nested cases, or the malformed fixture
  reveal that the chosen inner/outer attachment or `qualname` semantics produce
  ambiguous or incorrect owners, stop and record options before changing the
  contract.
- Merging semantics: if merging consecutive line doc comments cannot preserve
  exact reconstruction for some real shape (for example a doc comment
  interleaved with attributes), stop, record the shape, and either narrow the
  merge rule or emit per-line regions for that shape, whichever keeps
  reconstruction exact.
- Test attempts: if the same deterministic gate fails three times after a
  plausible fix, stop and record the failure with its log path.
- Performance: if warm extraction makes `make test` more than 20 seconds slower
  on this machine, document the cause and ask whether to narrow the work.
- Ambiguity: if two valid readings of RFC 0001 or the Rust Reference would
  produce different JSON shapes for `rust_doc_comment` regions, stop and record
  the options before choosing.

## Risks

- Risk: tree-sitter-rust does not tag doc comments distinctly, or tags them
  differently across versions, so relying on grammar-specific doc-comment child
  nodes would be brittle. Severity: high. Likelihood: medium. Mitigation: the
  extractor classifies and slices doc comments from the raw `line_comment`/
  `block_comment` node bytes (leading-marker inspection), a policy independent
  of grammar-specific child nodes. The Stage 1 spike prints the node kinds and
  pins the exact bytes so a grammar upgrade that changes them is caught.

- Risk: byte spans for a line-comment node include or exclude the trailing
  newline inconsistently, causing span drift when merging lines. Severity:
  high. Likelihood: medium. Mitigation: the Stage 1 spike asserts, for the
  shared fixture, that each `line_comment` node's byte range excludes the line
  terminator and that the sliced content after the marker equals the expected
  prose; the merge uses synthetic separators rather than assuming a source
  newline sits inside the content.

- Risk: owner derivation is wrong for outer-versus-inner attachment, for impl
  methods (`Type::method`), for nested modules, or for doc comments separated
  from their item by attributes. Severity: high. Likelihood: medium.
  Mitigation: implement owner derivation as a small, table-tested function over
  an explicit owner stack plus the emitted-node relationship (following sibling
  for outer, enclosing frame for inner); cover crate module, `mod`, struct,
  enum, trait, free function, impl method, nested module, and a block doc
  comment before snapshotting.

- Risk: malformed Rust aborts extraction or panics instead of degrading.
  Severity: high. Likelihood: medium. Mitigation: never unwrap tree-sitter
  results; walk the recovered tree, skip `ERROR`/`MISSING` subtrees while still
  emitting well-formed doc comments, and record an `IrError` per anomaly. Add
  the malformed fixture to the test matrix from the start and pin its exact
  recovery shape from the Stage 1 spike. Reuse the bounded traversal-depth cap
  pattern from the Python extractor
  (`crates/stilyagi-tree-sitter/src/python/mod.rs` `MAX_TRAVERSAL_DEPTH`).

- Risk: a `rustfmt` pass over a new valid `.rs` corpus fixture rewrites it and
  churns snapshot spans. Severity: medium. Likelihood: medium. Mitigation: keep
  all corpus `.rs` fixtures `rustfmt`-clean and run `make check-fmt` right
  after adding them (Stage 1); keep formatter-sensitive shapes inline.

- Risk: consecutive `///` lines are the norm in real Rust, so a per-line region
  policy would fragment prose and make later summary-line rules awkward, while
  a merge policy adds synthetic-segment complexity. Severity: medium.
  Likelihood: high. Mitigation: adopt merging as the single policy (see
  `Decision Log`), reuse the proven Markdown synthetic-separator
  implementation, and pin exact output with snapshots and a reconstruction
  property test.

- Risk: enabling `rust_doc_comment` breaks the pyext behaviour that maps it to
  `PyNotImplementedError` and any syntax-vocabulary parity check. Severity:
  medium. Likelihood: high (this is expected). Mitigation: update those tests
  as part of the bridge stage and confirm the Python `Syntax` enum and the Rust
  `ExtractSyntax::ALL` still agree.

- Risk: the new `ExtractError::RustIr` arm pushes `size_of::<ExtractError>()`
  past `EXTRACT_ERROR_SIZE_LIMIT_BYTES`. Severity: low. Likelihood: medium.
  Mitigation: keep `RustExtractError` a small `Copy` enum like
  `PythonExtractError`; if the assertion fails, raise the budget deliberately
  and record why, exactly as 3.1.1 allowed for `PythonIr`.

- Risk: the tree-sitter-rust grammar adds cold build time and binary size.
  Severity: medium. Likelihood: medium. Mitigation: scope the grammar to the
  one crate that needs it, measure the cold build in Stage 1, and re-run the
  1.3.3 structural performance probe after Stage 2 to catch warm-path
  regression.

- Risk: Rust and Python golden IR helpers drift into two contracts. Severity:
  medium. Likelihood: medium. Mitigation: make Rust canonical JSON the source
  of truth; the Python parity test compares `Document.ir` against the reviewed
  Rust snapshot after the same source-identity normalization, as established in
  2.1.1 and reused in 3.1.1.

## Plan of work

Each stage is independently committable and must pass the full deterministic
gates before its commit. Stages follow Red-Green-Refactor: the tests for a
behaviour land red (failing for the intended reason) before the production code
that makes them green.

### Stage 0: approval and baseline

This stage must not begin until explicit user approval is recorded in the
`Decision Log`. After approval, `Status` changes to `APPROVED`, then to
`IN PROGRESS` when implementation starts.

Confirm the branch and tree, then run a baseline gate before any code change so
later failures have a comparison point:

```bash
git branch --show-current      # expect roadmap-3-1-2
git status --short --branch
BRANCH="$(git branch --show-current)"
make check-fmt 2>&1 | tee "/tmp/check-fmt-baseline-stilyagi-${BRANCH}.out"
make typecheck 2>&1 | tee "/tmp/typecheck-baseline-stilyagi-${BRANCH}.out"
make lint      2>&1 | tee "/tmp/lint-baseline-stilyagi-${BRANCH}.out"
make test      2>&1 | tee "/tmp/test-baseline-stilyagi-${BRANCH}.out"
```

The deterministic commit gates are the separate `make` targets `check-fmt`,
`typecheck`, `lint`, and `test` (AGENTS.md lines 63-94, 156-178). The recovery
pass later updated `make all` so it now runs the commit gates explicitly and
sequentially. This plan keeps the individual target invocations below because
they preserve per-gate logs and make failure recovery clearer. Record the
baseline result in `Surprises & Discoveries`. If a baseline gate fails for
reasons unrelated to this plan, decide whether the failure blocks verification
before proceeding. Prefer delegating this run to the `scrutineer` subagent.

### Stage 1: dependency pin and tree-sitter-rust grammar spike

Add `tree-sitter-rust` to `[workspace.dependencies]` in the root `Cargo.toml`
(version chosen empirically to be ABI-compatible with `tree-sitter = "0.25.10"`
and to expose `LANGUAGE`), and depend on it from
`crates/stilyagi-tree-sitter/Cargo.toml`. Confirm the C toolchain and measure
the cold build:

```bash
cargo build -p stilyagi-tree-sitter 2>&1 \
  | tee "/tmp/build-cold-tree-sitter-rust-stilyagi-${BRANCH}.out"
```

If no `tree-sitter-rust` builds against `tree-sitter` `0.25.10`, or the C
compiler is missing, stop and escalate (see `Tolerances`). Record the resolved
`tree-sitter-rust` version and its `tree-sitter` requirement in the
`Decision Log` before pinning, mirroring how 3.1.1 pinned `tree-sitter-python`.

Add a `PYTHON_GRAMMAR_VERSION`-style `RUST_GRAMMAR_VERSION` regression guard in
the new `rust` module's `support` submodule that reads the workspace manifest
and asserts the pinned dependency matches the producer-metadata version,
exactly as `crates/stilyagi-tree-sitter/src/python/support.rs` does for Python.

Write a spike test in `stilyagi-tree-sitter` that parses
`tests/fixtures/corpus/rust/valid/item-doc-comments.rs`, loads the grammar
through `tree_sitter_rust::LANGUAGE`, and asserts:

1. The root node kind is `source_file`.
2. The crate-level `//!` comment parses as a `line_comment` node whose sliced
   bytes begin with `//!` and whose content after the marker equals
   `Crate-level documentation comment for the shared Stilyagi corpus.` (leading
   space retained).
3. The `///` comment before `pub struct FixtureExample` parses as a
   `line_comment` node whose bytes begin with `///` (and not `////`), and the
   node's next named sibling is a `struct_item` whose `name` field is
   `FixtureExample`.
4. The method `///` comment sits inside the `declaration_list` of the
   `impl_item` for `FixtureExample`, and its next named sibling is a
   `function_item` whose `name` field is `documented_value`.
5. The plain `// stilyagi-disable-next-line terminology` line parses as a
   `line_comment` whose bytes begin with `//` but not `///`, so the extractor
   classifies it as a non-doc comment.
6. Each `line_comment` node's byte range excludes its trailing line terminator
   (the byte-equality check that guards against span drift when merging).

Also write an inline spike over a block doc comment source
(`/** outer */ struct S;` and `/*! inner */`) that asserts these parse as
`block_comment` nodes whose bytes begin with `/**`/`/*!`, and over `////` and
`/**/`/`/***/` sources that assert these are non-doc comments; this pins the
classification edge rules.

Also spike the malformed fixture
`tests/fixtures/corpus/rust/malformed/unclosed-item.rs`: print the recovered
tree's `to_sexp()` and the spans of any `ERROR`/`MISSING` nodes, and record in
the `Decision Log` exactly how tree-sitter recovers it. The current ground
truth is that the crate `//!` doc comment survives, the malformed
`broken_function` item is absorbed into an `ERROR` subtree, the `///` doc
comment on that absorbed item is dropped, and the later well-formed struct doc
comment still survives. This captured behaviour becomes the ground truth for
the Stage 3 malformed snapshot.

Run the targeted test:

```bash
cargo test -p stilyagi-tree-sitter 2>&1 \
  | tee "/tmp/test-tree-sitter-rust-spike-stilyagi-${BRANCH}.out"
```

Confirm no fixture was rewritten by formatting:

```bash
make check-fmt 2>&1 | tee "/tmp/check-fmt-stage1-stilyagi-${BRANCH}.out"
```

Then run the full deterministic commit gates (`make check-fmt`,
`make typecheck`, `make lint`, `make test`) sequentially, resolve concerns, and
commit.

### Stage 2: owner-aware Rust doc-comment extractor and syntax dispatch

Implement the extractor in a new `crates/stilyagi-tree-sitter/src/rust/`
module, a sibling of `python/`, with the same submodule layout (`mod.rs`,
`helpers.rs`, `observe.rs`, `owner.rs`, `support.rs`, `types.rs`). Re-export
the public surface from `crates/stilyagi-tree-sitter/src/lib.rs` beside the
Python re-exports.

Provide a public function equivalent to:

```rust
pub fn rust_doc_comment_ir_document(
    source: &str,
    identity: stilyagi_ir::SourceIdentity,
) -> Result<stilyagi_ir::IrDocument, RustExtractError>;
```

`RustExtractError` covers only fatal failures (grammar load failure or an
absent parse tree). Model it on `PythonExtractError`: a small `Copy` enum with
`GrammarLoad` and `NoParseTree` variants, a `category` label, and `Display` /
`Error` impls. Recoverable parse anomalies are not errors; they become
`IrError` entries on the document.

The extractor:

1. Builds the envelope with
   `IrDocument::empty(DocumentMetadata::new("rust", identity.path, identity.uri,
   source), vec![rust_producer()], source)`.
   `rust_producer()` records `kind: "tree-sitter"`,
   `name: "tree-sitter-rust"`, the pinned `RUST_GRAMMAR_VERSION`, and
   deterministic options `doc_comment_content: "verbatim"`,
   `node_store: "bounded"`, `owner_qualname: "rust"`.
2. Parses the source with tree-sitter and walks named children depth-first,
   left-to-right, maintaining an explicit owner stack. `mod_item` pushes a
   `module` frame (with its `name`); `impl_item` pushes a frame carrying its
   `type` (Self type) name for qualname purposes; `struct_item`, `enum_item`,
   `union_item`, `trait_item`, `function_item`, `const_item`, `static_item`,
   `type_item`, and `macro_definition` are owner-bearing items. Bound the
   recursion with a `MAX_TRAVERSAL_DEPTH` cap as the Python extractor does.
3. Classifies each `line_comment`/`block_comment` node by its leading source
   bytes into outer-line (`///`, not `////`), inner-line (`//!`), outer-block
   (`/**`, not `/**/`/`/***`), inner-block (`/*!`), or non-doc. Non-doc
   comments yield no region. Computes the content span by stripping the marker
   prefix (and the trailing `*/` for block comments), keeping the content
   verbatim.
4. Groups consecutive same-flavour line doc comments that attach to the same
   owner (no intervening item, blank line, or non-doc token) into one region.
   Emits the merged `text` from the per-line content spans joined by synthetic
   `IrSegment` separators, following `crates/stilyagi-markdown/src/flatten.rs`.
   A block doc comment is one region with a single source-backed content
   segment.
5. Derives `owner` per region: outer doc comments own the immediately following
   item (its owner kind/name/qualname); inner doc comments own the enclosing
   frame (crate root → `kind: "module"`, `name: None`, `qualname: None`; a
   `mod foo` body → `kind: "module"`, `name: "foo"`, `qualname: "foo"`).
6. Populates each region with `kind: "rust_doc_comment"`,
   `scope: ["rust", "doc_comment", <owner_kind>]`, `syntax: "rust"`,
   `natural_language: None`, the source-backed (and, when merged, synthetic)
   segments, `origin_nodes` referencing the emitted doc-comment node(s),
   `owner`, empty `attrs`, and `parent_region: None`. Mirror the exact field
   set the Python extractor uses so the two region shapes stay parallel.
7. Emits the bounded node store: a synthetic `module` (crate) root, each
   doc-comment-owning item node, and each emitted doc-comment node, under one
   `IrTree { family: "tree-sitter", syntax: "rust", root: <crate id> }`. Node
   `flags` use `NodeFlags::named_source()`; nodes inside recovered error
   regions set `flags.error`/`flags.missing` as tree-sitter reports them.
8. On recovery anomalies, appends one `IrError` per top-level `ERROR`/`MISSING`
   subtree, in source order, with `code: "rust-parse-recovery"`, a message
   naming the node kind and byte span, and `span: Some(...)`. Well-formed doc
   comments in an otherwise malformed file are still emitted normally.
9. Validates IR consistency before returning (content-hash match, line-index
   match, and `segments_reconstruct_text` for every region), reusing the
   `validate_ir_consistency` pattern from the Python `support` submodule.

Owner derivation (a pure, table-tested function over the owner stack and the
comment's inner/outer flavour):

- crate inner doc: `kind: "module"`, `name: None`, `qualname: None`.
- `mod foo` inner doc: `kind: "module"`, `name: Some("foo")`,
  `qualname: Some("foo")`; nested `mod a { mod b { //! } }` →
  `qualname: "a::b"`.
- struct/enum/union/trait/const/static/type/macro outer doc: `kind` is the
  matching spelling (`"struct"`, `"enum"`, `"union"`, `"trait"`, `"const"`,
  `"static"`, `"type"`, `"macro"`), `name` is the item name, `qualname` is the
  `::`-joined enclosing named items plus the name.
- free function outer doc: `kind: "function"`, `name: Some(<fn name>)`,
  `qualname` = enclosing path plus name.
- impl method outer doc: `kind: "function"`, `name: Some(<method name>)`,
  `qualname: Some("<Self type>::<method>")` (the enclosing `impl` frame
  contributes the Self type name). For a trait impl `impl Trait for Type`, v1
  uses the `Type` name for the qualname prefix; record this in the ADR.
- an outer doc comment directly on an `impl` block: `kind: "impl"`,
  `name: Some(<Self type>)`, `qualname: Some(<Self type>)`.
- an item kind not in the recognized set: `kind: "item"`, `name` from the
  node's `name` field if present, otherwise `None`; document this fallback.

Worked example (the shared fixture):

```plaintext
//! crate-level        -> owner { kind: "module", name: null,  qualname: null }
/// on struct          -> owner { kind: "struct", name: "FixtureExample",
                                  qualname: "FixtureExample" }
/// on impl method     -> owner { kind: "function", name: "documented_value",
                                  qualname: "FixtureExample::documented_value" }
/// on free fn         -> owner { kind: "function", name: "fixture_function",
                                  qualname: "fixture_function" }
```

Wire dispatch in `crates/stilyagi-extract/src/lib.rs`: replace the
`ExtractSyntax::RustDocComment => Err(ExtractError::UnsupportedSyntax(syntax))`
arm with a call to a new `extract_rust_document` that delegates to
`rust_doc_comment_ir_document` and maps `RustExtractError` into a new
`ExtractError::RustIr(...)` arm (re-export `RustExtractError` from
`stilyagi-tree-sitter` beside `PythonExtractError`). Keep the compile-time
`ExtractError` size assertion satisfied (raise the budget deliberately if
needed, recording why). Add a `RegionKind::RustDocComment` variant spelled
`"rust_doc_comment"`, extend `RegionKind::TryFrom<&str>` and `as_str`, and have
the Python-facing region list emit `kind: "rust_doc_comment"` for Rust regions.

Add the fixtures this stage and Stage 3 need, all `rustfmt`-clean:

- `tests/fixtures/corpus/rust/valid/nested-modules-impls.rs`: nested `mod`s with
  inner and outer doc comments, an `impl` block with a documented method, and a
  documented associated `const`/`type`, to exercise `::` qualnames and
  inner/outer attachment.
- `tests/fixtures/corpus/rust/valid/doc-comment-multiline.rs`: an item preceded
  by a run of three `///` lines (to exercise merging) and an item preceded by a
  `/** ... */` block doc comment on one line, both `rustfmt`-clean.

Add `SHARED_RUST_FIXTURE_PATH` (for `item-doc-comments.rs`),
`MALFORMED_RUST_FIXTURE_PATH` (for `unclosed-item.rs`),
`NESTED_RUST_FIXTURE_PATH`, and `MULTILINE_RUST_FIXTURE_PATH` constants in
`crates/stilyagi-test-fixtures/src/fixture_paths.rs` beside the Python
constants, and re-export them from `stilyagi-test-support`.

Formatter- or line-ending-sensitive shapes stay inline: a CR-LF `///` run, a
`////` non-doc comment, a `/**/` empty comment, an empty `///` line, and a doc
comment with embedded quotes and backslashes.

Tests for this stage (Red before the extractor, Green after):

- rstest unit tests in `stilyagi-tree-sitter`, parameterized over owner
  `kind`/`name`/`qualname`, covering at least: crate inner doc; `mod` inner
  doc; nested `mod` inner doc (`a::b`); struct outer doc; enum outer doc; trait
  outer doc; free function outer doc; impl method outer doc (`Type::method`);
  trait impl method (`Type::method`); documented `impl` block; documented
  `const` / `static` / `type`; an unrecognized item kind (fallback
  `kind: "item"`); a non-doc `//` comment and a `////` comment (no region); a
  merged three-line `///` run (one region, exact reconstruction); a block doc
  comment (one source-backed segment); and CR-LF, empty, and embedded-quote doc
  comments (each reconstructs exactly).
- malformed-recovery rstest cases: the corpus malformed fixture must yield
  exactly the surviving doc-comment regions plus at least one `errors` entry,
  and must not panic; plus an inline
  `crate doc -> broken fn -> later well-formed struct with a doc comment` case
  documenting whether recovery reaches the later item. The expected outcome is
  whatever Stage 1 captured; the test pins it so a grammar upgrade that changes
  recovery is caught.
- proptest invariants: for generated valid segment layouts,
  `segments_reconstruct_text` holds and source-backed segment bytes equal the
  source oracle; and the pure Rust `qualname` builder is deterministic and
  matches the adopted `::` semantics over generated owner stacks.

```bash
cargo test -p stilyagi-tree-sitter -p stilyagi-extract 2>&1 \
  | tee "/tmp/test-extract-rust-stilyagi-${BRANCH}.out"
```

After the targeted tests pass, re-run the roadmap 1.3.3 structural performance
probe to confirm warm extraction has not regressed, then run the full
deterministic commit gates (`make check-fmt`, `make typecheck`, `make lint`,
`make test`) sequentially, resolve concerns, and commit.

### Stage 3: canonical JSON, golden fixtures, and snapshots

Add a Rust golden IR builder to
`crates/stilyagi-test-support/src/golden_fixture_builder.rs`, alongside
`golden_python_ir_fixture`, exposing something equivalent to:

```rust
pub fn golden_rust_ir_fixture(
    relative_path: impl AsRef<std::path::Path>,
) -> Result<stilyagi_ir::IrDocument, GoldenRustFixtureError>;
```

Model `GoldenRustFixtureError` on `GoldenPythonFixtureError` (with `From`
conversions for the fixture-read, fixture-path, and `RustExtractError` cases).
It reads the corpus fixture and calls the production extractor so the golden
builder cannot invent a second schema. Re-export it and the new fixture-path
constants from `crates/stilyagi-test-support/src/lib.rs`.

Add insta snapshots for the canonical IR JSON of both the shared valid Rust
fixture and the malformed Rust fixture, placed beside the existing extraction
snapshots in `crates/stilyagi-extract/tests/extract/snapshots/`, following the
existing `..._shared_..._fixture_has_a_golden_ir_snapshot` naming convention
(for example
`..._extraction_tests__shared_rust_fixture_has_a_golden_ir_snapshot` and
`..._malformed_rust_fixture_has_a_golden_ir_snapshot`). Add the driving tests to
`crates/stilyagi-extract/tests/extract/ir_identity.rs`.

Accept a snapshot only after diffing it and confirming each region's `text`,
`segments`, and `owner.kind`/`name`/`qualname` are correct and no spurious
nodes or regions appear. The malformed snapshot must show the surviving
doc-comment regions plus at least one `errors` entry whose `span` covers the
unclosed body, and no region for the string inside the broken body.

```bash
INSTA_UPDATE=always cargo test -p stilyagi-test-support -p stilyagi-extract 2>&1 \
  | tee "/tmp/test-insta-rust-stilyagi-${BRANCH}.out"
cargo test -p stilyagi-test-support -p stilyagi-extract 2>&1 \
  | tee "/tmp/test-insta-rust-verify-stilyagi-${BRANCH}.out"
```

Run the full deterministic commit gates (`make check-fmt`, `make typecheck`,
`make lint`, `make test`) sequentially, resolve concerns, and commit.

### Stage 4: Rust BDD behaviour coverage

Add an rstest-bdd feature describing owner-aware Rust doc-comment extraction,
following
`crates/stilyagi-extract/tests/features/python_docstring_extraction.feature`
and the [rstest-bdd users' guide](../rstest-bdd-users-guide.md). Place the
feature at
`crates/stilyagi-extract/tests/features/rust_doc_comment_extraction.feature`
and the step module beside the existing Python BDD steps
(`crates/stilyagi-extract/tests/extract/`).

```gherkin
Feature: Owner-aware Rust documentation-comment extraction

  Scenario: Extract documentation comments with their owning items
    Given a Rust source file with crate, type, and function doc comments
    When the extractor runs for the rust_doc_comment syntax
    Then each doc-comment region records its prose text
    And each doc-comment region records its owning item kind and qualified name

  Scenario: Recover from a malformed Rust file
    Given a Rust source file whose function body never closes
    When the extractor runs for the rust_doc_comment syntax
    Then the crate documentation comment is still extracted
    And a recoverable parse error is recorded
```

Implement the steps against the `stilyagi-extract` boundary. Run targeted
tests, then the full deterministic commit gates (`make check-fmt`,
`make typecheck`, `make lint`, `make test`) sequentially, resolve concerns, and
commit.

### Stage 5: PyO3 bridge and Python model adaptation

The bridge already serializes an attached `IrDocument` to `ir_json`, so
enabling Rust extraction needs no new bridge fields. Update:

- `crates/stilyagi-pyext/src/tests.rs`: add
  `extract_document_py_exposes_rust_doc_comments`, modelled on
  `extract_document_py_exposes_python_docstrings`, asserting successful
  extraction with an `ir_json` payload whose first `rust_doc_comment` region
  carries an `owner`. Keep any `not_a_syntax` rejection case.
- `crates/stilyagi-pyext/tests/features/bridge_structure.feature` and its steps,
  if they enumerate supported syntaxes, so Rust extraction is covered.
- `python/stilyagi/_stilyagi_rs.pyi`, only if the payload description needs the
  `rust_doc_comment` example; the field shape is unchanged.

Add Python tests under `tests/`:

- `pytest` unit tests calling
  `stilyagi.engine.extraction.extract_document(source, model.Syntax.RUST_DOC_COMMENT)`
  for the shared fixture, asserting the parsed `Document.ir` contains
  `rust_doc_comment` regions with `owner` `kind`, `name`, and `qualname` for
  the crate module, struct, impl method, and free function.
- a `pytest-bdd` feature under `features/` mirroring the Rust BDD scenarios for
  the externally observable workflow.
- a `syrupy` JSON snapshot of `Document.ir` for the shared Rust fixture,
  redacting nondeterministic identity fields, plus a parity assertion that the
  Python-parsed IR matches the reviewed Rust canonical snapshot after the same
  normalization (the 2.1.1 / 3.1.1 parity pattern; reuse the shared redaction
  helper that replaces the producer grammar `version`, normalizes path
  separators, and canonicalizes the source identity).
- a `hypothesis` property test that keeps the Rust shape fixed and varies only
  the prose: render `/// {body}\npub fn {name}() {{}}\n` from an identifier
  strategy (`[A-Za-z_][A-Za-z0-9_]*`, excluding Rust keywords) and a body
  strategy drawn from text excluding characters that would break a single line
  doc comment (no newlines, no null characters), then assert the extractor
  returns exactly one `rust_doc_comment` region whose `owner.qualname` equals
  `{name}` and whose region text equals `{body}` (the retained leading space).
  Generating full Rust syntax with hypothesis is deliberately avoided; the
  fixed-shape table cases carry structural coverage.

Build and run targeted Python tests, then the full deterministic commit gates
run sequentially:

```bash
make build 2>&1 | tee "/tmp/build-stage5-stilyagi-${BRANCH}.out"
.venv/bin/python -m pytest -q tests/test_rust_doc_comment_extraction.py 2>&1 \
  | tee "/tmp/pytest-stage5-stilyagi-${BRANCH}.out"
make check-fmt 2>&1 | tee "/tmp/check-fmt-stage5-stilyagi-${BRANCH}.out"
make typecheck 2>&1 | tee "/tmp/typecheck-stage5-stilyagi-${BRANCH}.out"
make lint      2>&1 | tee "/tmp/lint-stage5-stilyagi-${BRANCH}.out"
make test      2>&1 | tee "/tmp/test-stage5-stilyagi-${BRANCH}.out"
```

Resolve concerns and commit.

### Stage 6: documentation, ADR, and roadmap completion

- Add `docs/adr-007-rust-doc-comment-owner-metadata.md` (Y-Statement format via
  `arch-decision-records`) recording the Rust owner-metadata shape: the owner
  kinds, the `::` qualname semantics (including `Type::method` for impl methods
  and the trait-impl `Type`-prefix decision), the inner/outer attachment rule,
  the verbatim-content flattening decision, the consecutive-line-merge decision
  with synthetic separators, the bounded node-store policy, and the v1
  limitations (no rustdoc leading-space or common-indentation stripping; crate
  module owners carry `name: null`/`qualname: null`; block-comment edge cases
  and the unrecognized-item `kind: "item"` fallback). Reference ADR 006 as the
  reused owner contract.
- Resolve the design §12 open question "Exact owner metadata shape for Rust
  documentation comments" by pointing it at ADR 007, and update
  `docs/stilyagi-design.md` §7.1 to state that Rust documentation comments are
  now implemented with `rust_doc_comment` regions and Rust owner kinds.
- Amend RFC 0001's owner section with a short note pointing to ADR 007 for the
  concrete Rust `qualname` semantics, without changing the field contract.
- Update `docs/developers-guide.md`: extend the extraction section and the
  Markdown-versus-Python comparison into a Markdown-versus-Python-versus-Rust
  comparison (parse entry, traversal, error recovery, owner metadata, node
  store, doc-comment attachment and merging), document the `.rs`
  malformed-fixture convention (plain `.rs`, no `.py.txt`), add the new
  fixture-path constants and the `golden_rust_ir_fixture` helper to their
  tables, and state plainly that v1 rules must rely on `owner` metadata, not on
  navigating a full Rust tree.
- Update `docs/users-guide.md` to record that `rust_doc_comment` extraction is
  now supported and that `Document.ir` exposes `rust_doc_comment` regions with
  `owner` metadata.
- Mark roadmap item 3.1.2 as done in `docs/roadmap.md`. Do not mark 3.1.3 done.

Format only the Markdown files this stage changed, then run the documentation
gates and the full gates:

```bash
mdtablefix docs/adr-007-rust-doc-comment-owner-metadata.md \
  docs/stilyagi-design.md docs/developers-guide.md docs/users-guide.md \
  docs/roadmap.md docs/execplans/roadmap-3-1-2.md \
  docs/rfcs/0001-stilyagi-intermediate-representation.md
markdownlint-cli2 --fix docs/adr-007-rust-doc-comment-owner-metadata.md \
  docs/stilyagi-design.md docs/developers-guide.md docs/users-guide.md \
  docs/roadmap.md docs/execplans/roadmap-3-1-2.md \
  docs/rfcs/0001-stilyagi-intermediate-representation.md
make markdownlint 2>&1 | tee "/tmp/markdownlint-stage6-stilyagi-${BRANCH}.out"
make nixie        2>&1 | tee "/tmp/nixie-stage6-stilyagi-${BRANCH}.out"
make check-fmt    2>&1 | tee "/tmp/check-fmt-stage6-stilyagi-${BRANCH}.out"
make typecheck    2>&1 | tee "/tmp/typecheck-stage6-stilyagi-${BRANCH}.out"
make lint         2>&1 | tee "/tmp/lint-stage6-stilyagi-${BRANCH}.out"
make test         2>&1 | tee "/tmp/test-stage6-stilyagi-${BRANCH}.out"
```

Every path listed in those formatter commands is created or edited by this
stage, so the commands are path-safe. Resolve concerns and make the final
commit.

## Concrete steps

All commands run from the worktree root
(`/home/leynos/Projects/stilyagi.worktrees/roadmap-3-1-2`):

```bash
REPO_ROOT="$(pwd)"
leta workspace add "$REPO_ROOT"
```

Inspect symbols with `leta` rather than broad text search when a name is known:

```bash
leta grep "IrOwner|IrRegion|IrDocument|ExtractSyntax|RegionKind|python_docstring_ir_document" -k struct,enum,fn
leta show python_docstring_ir_document
leta refs ExtractSyntax
```

Use `sem` for history navigation and `rg` only for non-symbol text (fixtures,
prose, snapshots):

```bash
rg -n "rust_doc_comment|owner|qualname" docs tests crates
```

After each gated stage, inspect and commit with a file-based message:

```bash
git status --short
git diff --stat
COMMIT_MSG_DIR="$(mktemp -d)"
cat > "$COMMIT_MSG_DIR/COMMIT_MSG.md" << 'ENDOFMSG'
Add owner-aware Rust doc-comment extractor

Wire tree-sitter-rust through stilyagi-tree-sitter to emit rust_doc_comment IR
regions with source-backed segments and owner metadata for modules, types,
functions, and item-level declarations, per roadmap item 3.1.2.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
ENDOFMSG
git commit -F "$COMMIT_MSG_DIR/COMMIT_MSG.md"
rm -rf "$COMMIT_MSG_DIR"
```

Each stage uses a more specific subject; the example is a shape, not the
required final message.

## Validation and acceptance

Acceptance for the implemented feature:

- Running Rust extraction on
  `tests/fixtures/corpus/rust/valid/item-doc-comments.rs` produces an
  `IrDocument` with `document.syntax == "rust"`,
  `document.encoding == "utf-8"`, a stable `sha256:` `content_hash`, a monotonic
  `line_index`, one `tree-sitter` tree, a bounded node store, and four
  `rust_doc_comment` regions (crate, struct, method, free function). The plain
  `//` comment yields no region.
- The four regions carry owners: `{kind: "module"}` (crate, `name`/`qualname`
  null); `{kind: "struct", name: "FixtureExample", qualname: "FixtureExample"}`;
  `{kind: "function", name: "documented_value", qualname:
  "FixtureExample::documented_value"}`;
  and
  `{kind: "function", name: "fixture_function", qualname: "fixture_function"}`.
- Each region's `segments` reconstruct its `text` exactly, and source-backed
  segment bytes equal the corresponding source slice (no span drift).
- Running extraction on
  `tests/fixtures/corpus/rust/malformed/unclosed-item.rs` still emits the
  surviving doc-comment regions and records at least one `errors` entry; it
  does not panic or abort.
- Canonical IR JSON snapshots for both Rust fixtures are stable across repeated
  runs.
- The PyO3 bridge accepts `"rust_doc_comment"`, returns `ir_json`, and the
  Python `Document.ir` exposes the regions with owner metadata. The Rust
  `ExtractSyntax::ALL` and Python `Syntax` vocabularies still agree.
- Markdown and Python behaviour and snapshots are unchanged.
- `docs/adr-007-rust-doc-comment-owner-metadata.md` exists and is referenced
  from the design; `docs/developers-guide.md` and `docs/users-guide.md` are
  updated; `docs/roadmap.md` marks only item 3.1.2 done.

Red-Green-Refactor evidence to record as work proceeds:

- Red: a chosen owner/region rstest (for example
  `rust_impl_method_doc_owner_uses_type_qualname`) fails before the extractor
  exists, because `rust_doc_comment` extraction returns `UnsupportedSyntax`.
  The malformed-recovery test fails for the expected reason (no region, no
  error).
- Green: after the extractor and dispatch land, the focused tests pass.
- Refactor: owner derivation, classification, and merging are tidied; targeted
  tests and the wider gates rerun green.

Required gates after each stage — run these deterministic commit-gate targets
sequentially (or name exactly these targets when delegating to `scrutineer`):

```bash
make check-fmt
make typecheck
make lint
make test
```

Documentation gates after Markdown changes:

```bash
make markdownlint
make nixie
```

These four targets are the authoritative commit gates in AGENTS.md (lines
63-94, 156-178); `make typecheck` runs the typecheck on current `origin/main`.
Earlier recovery evidence found that `make all` only resolved to the release
smoke path, but the Makefile has since been updated so `make all` runs the
commit-gate sequence. Capture all long gate output with `tee` into `/tmp` logs
and read the log before retrying a failure; re-run a gate only after applying a
fix.

## Idempotence and recovery

Most steps are additive and safe to rerun: tests, snapshot verification, and the
`make` gates. Snapshot update commands (`INSTA_UPDATE=always`,
`--snapshot-update`) are safe only after the implementation diff has been
reviewed; if an update captures unintended churn, revert only the snapshot
changes from that stage and fix the builder before updating again.

If the tree-sitter-rust dependency causes build or licensing problems, remove
the dependency changes from the current stage, record the blocker in the
`Decision Log`, and escalate before broadening build configuration.

If any `git stash` is needed, name it per the workshop convention, for example
`df12-stash v1 task=3.1.2 kind=discard reason="park formatter churn"`; never
use a bare stash message.

## Interfaces and dependencies

At the end of this plan the following must exist:

- In `crates/stilyagi-tree-sitter/src/rust/mod.rs`:

  ```rust
  pub fn rust_doc_comment_ir_document(
      source: &str,
      identity: stilyagi_ir::SourceIdentity,
  ) -> Result<stilyagi_ir::IrDocument, RustExtractError>;

  #[derive(Debug, Clone, Copy, PartialEq, Eq)]
  pub enum RustExtractError { GrammarLoad, NoParseTree }
  ```

  re-exported from `crates/stilyagi-tree-sitter/src/lib.rs` beside the Python
  surface.

- In `crates/stilyagi-extract/src/lib.rs`: `ExtractSyntax::RustDocComment`
  dispatches through `extract_rust_document`;
  `ExtractError::RustIr(RustExtractError)` exists and keeps the size assertion
  satisfied; `RegionKind::RustDocComment` exists with `as_str` returning
  `"rust_doc_comment"` and a `TryFrom<&str>` arm.

- In `crates/stilyagi-test-support/src/golden_fixture_builder.rs`:
  `golden_rust_ir_fixture(...) -> Result<IrDocument, GoldenRustFixtureError>`.

- In `crates/stilyagi-test-fixtures/src/fixture_paths.rs`:
  `SHARED_RUST_FIXTURE_PATH`, `MALFORMED_RUST_FIXTURE_PATH`,
  `NESTED_RUST_FIXTURE_PATH`, and `MULTILINE_RUST_FIXTURE_PATH`.

Dependencies: `tree-sitter-rust` (version confirmed in Stage 1 to be
ABI-compatible with `tree-sitter = "0.25.10"`) added to
`[workspace.dependencies]` and to `crates/stilyagi-tree-sitter/Cargo.toml`. No
other new external dependency without approval.

## Progress

- [x] Stage 0: approval and baseline.
- [x] Stage 1: dependency pin and tree-sitter-rust grammar spike.
- [x] Stage 2: owner-aware Rust doc-comment extractor and syntax dispatch.
- [x] Stage 3: canonical JSON, golden fixtures, and snapshots.
- [x] Stage 4: Rust BDD behaviour coverage.
- [x] Stage 5: PyO3 bridge and Python model adaptation.
- [x] Stage 6: documentation, ADR, and roadmap completion.
- [x] 2026-07-04 fix round 2: added Rust source-byte oracle property tests for
  line, merged-line, and block doc comments; recorded the malformed recovery
  ground truth; reran the `stilyagi-tree-sitter` crate tests green.
- [x] 2026-07-04 addendum pass: implemented roadmap addenda `3.1.2.1` through
  `3.1.2.4`, retried CodeRabbit after the rate-limit window, fixed the branch
  so all required gates passed, and marked the addendum checkboxes complete.

## Surprises & discoveries

- Observation: the malformed Rust corpus fixture uses a plain `.rs` suffix,
  unlike malformed Python which uses `.py.txt`. Evidence:
  `tests/test_corpus.py` gates the `.py.txt` convention on
  `syntax == "python" and category == "malformed"` only, and
  `tests/fixtures/corpus/rust/malformed/unclosed-item.rs` already exists and
  passes gates on `main`. Impact: no `.rs.txt` rename is needed; the extractor
  and snapshots read the fixture directly, and new valid `.rs` fixtures must
  stay `rustfmt`-clean to avoid formatter-driven span churn.

- Observation: web tooling (Firecrawl, WebFetch, WebSearch) and the
  out-of-worktree Cargo registry cache are not accessible in this planning
  session. Evidence: `firecrawl_search`/`WebFetch` returned permission errors
  and `find` outside the working directories was sandbox-blocked. Impact: the
  exact published `tree-sitter-rust` version and the Rust Reference wording are
  confirmed empirically in Stage 1 (spike) rather than cited from a fetched
  page; the mechanism is unchanged and every load-bearing grammar and
  attachment claim is pinned by a Stage 1 assertion or a Stage 2 table test.

- Observation: the requested `coderabbit review --agent` pass stalled after
  connecting and setup, then remained in the analysing phase without returning
  a review envelope before it was aborted. Evidence: the run emitted
  `review_context`, `status` events for `connecting_to_review_service`,
  `setting_up`, `preparing_sandbox`, and `summarizing`, but produced no
  findings or completion record before termination. Impact: the deterministic
  gates are still green, but external AI review is deferred and must be retried
  or replaced by another review path before this item is considered fully
  closed.

- Observation: the recovery adoption pass reran `coderabbit review --agent` and
  received a completed review envelope with zero findings. Evidence:
  `/tmp/coderabbit-adopt-stilyagi-roadmap-3-1-2.out` ends with
  `{"type":"complete","status":"review_completed","findings":0}`. Impact: the
  external AI review gap from the interrupted implementation run is closed for
  this branch.

- Observation: the malformed Rust parse tree currently absorbs the broken
  function and its doc comment into a top-level `ERROR` subtree. Evidence:
  `tree.root_node().to_sexp()` for
  `tests/fixtures/corpus/rust/malformed/unclosed-item.rs` shows the crate doc
  comment, the absorbed `ERROR` subtree, and the later `struct_item`. Impact:
  the malformed snapshot and regression tests intentionally codify the current
  ground truth. If a future grammar version exposes the broken `function_item`
  again, this plan must be updated alongside the tests.

- Observation: the addendum branch initially reported green `make all` evidence,
  but this repository's `make all` target was only the release build and smoke
  path at that point, not the full commit-gate set. Evidence: the manual
  recovery pass reran `make check-fmt`, `make typecheck`, `make lint`,
  `make test`, `make markdownlint`, and `make nixie`; `make lint` caught a
  Clippy nesting failure and then a module-size failure that `make all` had not
  exposed. Impact: the addendum branch needed a manual fix before integration.
  This is recorded as workflow validation evidence rather than treated as a
  Stilyagi roadmap blocker, and `make all` has been changed to run the commit
  gates.

## Decision log

- Decision: approve roadmap item 3.1.2 for implementation in this worktree.
  Rationale: the user explicitly asked for the approved ExecPlan to be executed
  item by item in order, so the approval gate is satisfied and the stage work
  may begin. Date/Author: 2026-07-04, implementation agent.

- Decision: classify and slice Rust doc comments from the raw
  `line_comment`/`block_comment` node bytes by leading marker, rather than
  depending on grammar-specific doc-comment child nodes. Rationale: robust
  across tree-sitter-rust grammar versions and gives exact byte spans; a single
  mechanism, not a version-dependent fork. Date/Author: 2026-07-04, planning
  agent.

- Decision: merge consecutive same-flavour line doc comments attaching to the
  same owner into one region using synthetic `IrSegment` separators (Markdown
  soft-break pattern); treat each block doc comment as one single-segment
  region. Rationale: a Rust doc block is one prose unit; merging makes later
  summary-line and punctuation rules (3.2.2) meaningful, and the Markdown
  flattener already proves the synthetic-separator pattern preserves exact
  reconstruction. Date/Author: 2026-07-04, planning agent.

- Decision: treat Rust attribute nodes as transparent for owner attachment and
  emit owner nodes only for doc-comment-owning items. Rationale: doc comments
  that precede `#[derive]`/`#[cfg]`/similar attributes must still reach the
  real item, and the bounded node store should match the Python extractor by
  collapsing undocumented ancestors to the nearest emitted owner instead of
  materializing every enclosing item. Date/Author: 2026-07-04, implementation
  agent.

- Decision: reuse the ADR 006 `owner` field contract with Rust-specific kinds
  and `::` qualnames; impl methods use `Type::method`; trait impls use the
  `Type` prefix; crate module owners carry `null` name/qualname. Rationale: ADR
  006 "Follow-on work" and design §12 explicitly hand these semantics to this
  slice; `::` matches Rust path syntax. Date/Author: 2026-07-04, planning agent.

- Decision: no Kani/CrossHair/Verus work in scope.
  Rationale: the only unbounded invariants (exact reconstruction, deterministic
  qualname derivation) are fully covered by proptest and table tests, matching
  the 3.1.1 decision. Date/Author: 2026-07-04, planning agent.

- Decision: close the plan after the recovery adoption validation pass.
  Rationale: the branch is clean, the deterministic gates passed on the
  recovered commit, CodeRabbit returned a completed zero-finding review, and
  the roadmap checkbox plus documentation updates already match the implemented
  Rust documentation-comment extraction behaviour. Date/Author: 2026-07-04,
  operator.

- Decision: keep the malformed-recovery tests pinned to the observed `ERROR`
  subtree behaviour instead of forcing synthetic owner recovery. Rationale: the
  parser currently absorbs the broken function and its doc comment into a
  top-level `ERROR` node, so the safest and most truthful contract is to
  preserve the surviving crate and later docs, record the dropped absorbed doc
  as part of the ground truth, and document the recovery limit explicitly.
  Date/Author: 2026-07-04, implementation agent.

- Decision: close addenda `3.1.2.1` through `3.1.2.4` after the manual
  recovery pass. Rationale: module-rooted impl-member qualnames are now pinned
  in the nested Rust snapshot, intervening ordinary comments are covered by
  parameterized addendum tests, CR-LF and whitespace source-oracle cases pass,
  and malformed Rust recovery emits an explicit
  `rust-doc-comment-error-subtree` diagnostic when doc comments are absorbed
  into a tree-sitter `ERROR` subtree. Date/Author: 2026-07-04, operator.

## Outcomes & retrospective

Roadmap item 3.1.2 is complete on this branch. Stilyagi now extracts Rust
documentation comments through the same public extraction path used by Markdown
and Python, emits `rust_doc_comment` IR regions with exact source-backed
segments, and attaches Rust owner metadata for modules, item declarations, impl
blocks, methods, and free functions. The shared and malformed Rust fixtures
have canonical IR snapshots, the PyO3 bridge exposes `rust_doc_comment` to
Python, and the user, developer, design, RFC, and ADR documents describe the
new syntax surface.

The recovery adoption validation pass on 2026-07-04 recorded fresh
deterministic gate evidence for commit `85ae214`:

- `make check-fmt` passed; log:
  `/tmp/check-fmt-adopt-stilyagi-roadmap-3-1-2.out`.
- `make typecheck` passed; log:
  `/tmp/typecheck-adopt-stilyagi-roadmap-3-1-2.out`.
- `make lint` passed; log:
  `/tmp/lint-adopt-stilyagi-roadmap-3-1-2.out`.
- `make test` passed; log:
  `/tmp/test-adopt-stilyagi-roadmap-3-1-2.out`. The Rust nextest run passed
  236/236 tests, Rust doctests passed, and pytest passed 117/117 tests with six
  snapshots. Pytest emitted `pytest_bdd` deprecation warnings from third-party
  fixture registration; no project warning or test failure was introduced by
  this slice.
- `coderabbit review --agent` completed with zero findings; log:
  `/tmp/coderabbit-adopt-stilyagi-roadmap-3-1-2.out`.

The main lesson is that closure evidence must be durable enough for recovery
assessment. The implementation run had already produced a coherent complete
slice, but the stalled CodeRabbit review and unfilled retrospective made the
branch ambiguous to the recovery workflow. Recording the gate and review
evidence here keeps the branch self-contained for adoption.

The addendum recovery pass on 2026-07-04 closed the four roadmap addenda on
commits `c302ee5` and `34f6ce5`. CodeRabbit completed with zero findings after
the earlier rate limit cleared:
`/tmp/coderabbit-stilyagi-roadmap-3-1-2-addendum-manual-final.out`. The
required sequential gates then passed with durable logs:

- `make check-fmt` passed; log:
  `/tmp/check-fmt-stilyagi-roadmap-3-1-2-addendum-manual.out`.
- `make typecheck` passed; log:
  `/tmp/typecheck-stilyagi-roadmap-3-1-2-addendum-manual.out`.
- `make lint` passed; log:
  `/tmp/lint-stilyagi-roadmap-3-1-2-addendum-manual.out`.
- `make test` passed; log:
  `/tmp/test-stilyagi-roadmap-3-1-2-addendum-manual.out`. The Rust nextest run
  passed 246/246 tests, Rust doctests passed, and pytest passed 118/118 tests
  with six snapshots.
- `make markdownlint` passed; log:
  `/tmp/markdownlint-stilyagi-roadmap-3-1-2-addendum-manual.out`.
- `make nixie` passed; log:
  `/tmp/nixie-stilyagi-roadmap-3-1-2-addendum-manual.out`.

## Revision note

Initial draft (2026-07-04): first planning round for roadmap item 3.1.2.
Mirrors the completed 3.1.1 execplan; adds Rust-specific doc-comment
classification, consecutive-line merging, and inner/outer owner attachment.
Records the `.rs` malformed-fixture asymmetry and the planning-session
web/registry tooling limitation, with the mechanism pinned by a Stage 1 spike
so the plan stays implementable. Remaining work: all stages (0–6).

Round 2 revision (2026-07-04): corrected the gate strategy. The prior draft
wrongly asserted that `make all` runs the formatting check, typecheck, lint,
and test suites; the Makefile actually defines `all: release`
(`release: release-artifact smoke-release`), which only builds the maturin
release wheel and runs `python -m stilyagi.smoke`, so it executes none of the
commit gates. Every stage gate invocation and the two false prose claims
(former lines 488 and 1016) now use the authoritative AGENTS.md commit-gate
targets `make check-fmt`, `make typecheck`, `make lint`, and `make test` run
sequentially (plus `make markdownlint` and `make nixie` for Markdown-changing
stages), matching the sibling 3.1.1 execplan. No other content changed.

Round 3 revision (2026-07-04): recorded the external review stall from the
`coderabbit review --agent` attempt. The deterministic gates reached green, but
the review service never returned findings or completion before the run was
aborted, so review remains deferred and should be retried or superseded by a
different review path.

Round 4 revision (2026-07-04): recovery adoption validation reran the
deterministic gates and CodeRabbit review on the preserved branch. All four
commit gates passed, CodeRabbit completed with zero findings, and this plan's
status plus retrospective now reflect the completed branch. Remaining work:
route the branch through ordinary recovery review and integration.

Round 5 revision (2026-07-04): addressed the round-one blocking review for the
Rust doc-comment slice. Attribute nodes now pass through without capturing
pending outer docs, owner nodes are emitted only for doc-comment-owning items,
and undocumented ancestors collapse to the nearest emitted owner in the bounded
node store. Added a corpus fixture for `///` plus `#[derive]` interleaving, a
Rust unit test for attribute pass-through, a nested-fixture canonical JSON
snapshot, and a Python bridge assertion for the new attribute fixture.

Round 6 revision (2026-07-04): resolved the recovered branch's final review
disposition. The round-two fix added source-byte oracle coverage and recorded
the verified tree-sitter malformed-recovery ground truth; the full sequential
gate set and CodeRabbit review then passed at commit `ee71e58`. The remaining
round-three review proposals are accepted as follow-up hardening and contract
work rather than blockers for the completed 3.1.2 extraction slice. They are
tracked as roadmap addenda `3.1.2.1` through `3.1.2.4` so later Rust
doc-comment rules can either consume the improved contracts or see an explicit
documented limitation.

Round 7 revision (2026-07-04): completed the addendum pass. Commit `c302ee5`
implemented the four accepted follow-up items, and commit `34f6ce5` fixed the
manual gate failures found during operator recovery. The roadmap addendum
checkboxes are now checked, the malformed Rust snapshot includes the explicit
doc-comment-drop diagnostic, and the manual CodeRabbit plus gate evidence is
recorded above for integration.

Round 8 revision (2026-07-04): recorded the project-side mitigation for the
addendum gate gap. `make all` now runs the commit gates explicitly and
sequentially, while `make release` remains the release wheel and smoke-test
path. The plan still records the historical false-positive evidence because it
explains the manual recovery work and df12-build issue.
