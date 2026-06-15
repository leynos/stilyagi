# Implement Python docstring extraction with owner metadata

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
`Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`, `Decision Log`,
and `Outcomes & Retrospective` must be kept up to date as work proceeds.

Status: COMPLETED

Approval gate: satisfied on 2026-06-15. The `Decision Log` records explicit
approval before implementation began.

## Purpose / big picture

Roadmap item 3.1.1 proves that Stilyagi's extraction and intermediate
representation (IR) loop can reach beyond Markdown into Python source trees. It
answers one question from [docs/roadmap.md](../roadmap.md) §3.1: can the
extractor recover the owner metadata and source maps that docstring rules need
for Python modules, classes, and functions?

After the approved implementation, a maintainer should be able to call the
existing extraction path with the `python_docstring` syntax on a representative
Python file and inspect canonical IR JSON that contains, for each docstring, a
`python_docstring` region whose flattened `text` is the prose between the
string delimiters, whose `segments` map that text back to exact source bytes,
and whose `owner` identifies the enclosing module, class, or function by `kind`,
`name`, and `qualname`.

The observable success condition is not merely "the code compiles". For the
shared Python fixture, canonical IR JSON snapshots must be stable, every
emitted region's `segments` must reconstruct its `text` exactly, every region's
`owner` must name the correct owning symbol, and a malformed Python fixture
must still produce partial extraction plus a recoverable error rather than
aborting the run.

This slice deliberately stops at owner-aware extraction. It does not implement
Python docstring lint rules (roadmap item 3.2.2), Python suppression parsing
(roadmap item 3.1.3), Rust documentation-comment extraction (roadmap item
3.1.2), discovery defaults for `*.py` (roadmap item 3.2.1), or PEP 257
docstring normalization. It supplies the IR facts those later items must trust.

## Context and orientation

The repository is a mixed Rust and Python project. Rust crates live under
`crates/`, the Python package lives under `python/stilyagi/`, Python tests live
under `tests/`, shared corpus fixtures live under `tests/fixtures/corpus/`, and
behaviour-driven development (BDD) feature files live under `features/`.

The relevant Rust crates are:

- `crates/stilyagi-ir/`, which owns the stable IR domain vocabulary. It already
  defines `IrDocument`, `DocumentMetadata`, `ProducerMetadata`,
  `IrBuildContext`, `IrTree`, `IrNode`, `NodeFlags`, `SourceSpan`, `IrRegion`,
  `IrSegment`, `SegmentOrigin`, `IrOwner`, `IrSuppression`, `IrError`,
  `SourceIdentity`, the `content_hash_for`/`line_index_for` helpers, and
  `SCHEMA_VERSION` (`"1.0.0"`). The owner contract already exists:
  `IrOwner { kind: String, name: Option<String>, qualname: Option<String> }` in
  `crates/stilyagi-ir/src/region.rs`.
- `crates/stilyagi-tree-sitter/`, currently a placeholder exposing only
  `TreeSitterBoundary`. This crate becomes the tree-sitter-backed source
  extractor and is the natural home for Python docstring extraction (and, in
  item 3.1.2, Rust doc-comment extraction). The design names this crate for
  tree-sitter work in [docs/stilyagi-design.md](../stilyagi-design.md) §§4, 10.
- `crates/stilyagi-markdown/`, the existing Markdown adapter. It is the
  reference pattern for this slice:
  `markdown_ir_document(source, identity) -> Result<IrDocument, Message>`
  parses, builds a tree and node store, flattens regions with source-backed and
  synthetic segments, and validates IR consistency. The new Python extractor
  mirrors this shape.
- `crates/stilyagi-extract/`, which owns syntax dispatch. `ExtractSyntax`
  already has a `PythonDocstring` variant spelled `"python_docstring"`, but
  `extract_document_with_source_identity` currently returns
  `ExtractError::UnsupportedSyntax(ExtractSyntax::PythonDocstring)`. This slice
  wires that variant to the new extractor.
- `crates/stilyagi-pyext/`, the PyO3 bridge. `extract_document_py` already
  serialises an attached `IrDocument` to canonical `ir_json`. Enabling Python
  extraction makes `python_docstring` a supported syntax through the existing
  bridge shape with no new bridge fields.
- `crates/stilyagi-test-support/`, which provides fixture access
  (`corpus_fixture_path`, `read_corpus_fixture`,
  `SHARED_MARKDOWN_FIXTURE_PATH`) and golden IR builders
  (`golden_markdown_ir_fixture`). This slice adds a Python golden IR builder
  alongside the Markdown one.

The relevant Python modules are:

- `python/stilyagi/engine/extraction.py`, which adapts the raw bridge payload
  into typed `model.Document` objects and parses `ir_json` into `Document.ir`.
- `python/stilyagi/model/document.py`, which defines `Syntax` (a `StrEnum` with
  `MARKDOWN`, `PYTHON_DOCSTRING`, `RUST_DOC_COMMENT`) and `Document`.
- `python/stilyagi/model/region.py`, which defines `Region` with `kind` and
  `text`.
- `python/stilyagi/_stilyagi_rs.pyi`, the type stub mirroring the extension
  payload.

The relevant fixtures (added by roadmap item 1.3.1) are:

- `tests/fixtures/corpus/python/valid/module-class-function-docstrings.py`,
  which contains a module docstring, a class docstring, a `@staticmethod`
  method docstring, and a module-level function docstring.
- `tests/fixtures/corpus/python/malformed/unclosed-function.py.txt`, which
  contains a valid module docstring followed by a function whose signature
  never closes. Malformed Python fixtures use the `.py.txt` suffix so
  formatters and linters do not try to process them; `tests/test_corpus.py`
  registers this convention.

Definitions used in this plan:

- IR means intermediate representation: Stilyagi's stable logical payload for
  source structure, lintable prose regions, source positions, and debug output.
- Region means a lintable prose surface. For this slice, the only new region
  kind is `python_docstring`.
- Owner means the code entity that encloses a docstring. RFC 0001 reserves the
  region `owner` field for this code-entity contract and forbids reusing it for
  Markdown section context.
- Segment means a mapping from a span of region text to either original source
  bytes (`source`) or an explicit synthetic insertion (`synthetic`).
- `qualname` means a qualified name, following Python's `__qualname__`
  convention. See the `Decision Log` for the precise semantics adopted here.
- tree-sitter is the incremental, error-tolerant parsing library mandated by
  the design for host-language parsing. tree-sitter-python is its Python
  grammar. A `string` node in that grammar exposes `string_start`,
  `string_content`, and `string_end` children, so the prose between the quotes
  is a distinct, source-backed span.
- Span drift means any mismatch between a reported source offset and the bytes
  that actually produced the corresponding region text.

## Documentation and skill signposts

Before implementing this plan, load and apply these skills:

- `leta`, for symbol-aware Rust and Python navigation. Refresh the workspace
  with `leta workspace add "$(pwd)"` at the start of each session.
- `rust-router`, then `arch-crate-design`, because this change activates the
  `stilyagi-tree-sitter` crate boundary and its public versus internal surface.
- `hexagonal-architecture`, to keep the boundary clean: `stilyagi-ir` owns the
  domain IR types; `stilyagi-tree-sitter` is an adapter that depends inward on
  the IR; `stilyagi-extract` orchestrates; `stilyagi-pyext` and the Python
  package are transport and application layers.
- `rust-types-and-apis`, for the new public extractor function signature and
  any owner-derivation types.
- `rust-errors`, for mapping tree-sitter parse anomalies to `IrError` and any
  new `ExtractError` arms.
- `rust-unit-testing`, for rstest fixtures and parameterized owner-derivation
  tables.
- `proptest`, for the segment-reconstruction and qualname invariants. Load
  `rust-verification` first only if a deductive proof is considered; this plan
  records why Verus and Kani are out of scope (see `Decision Log`).
- `python-router`, then `python-testing` and `python-types-and-apis`, for the
  pytest, pytest-bdd, and typed-adapter work. Load `python-verification` then
  `hypothesis` for the Python property test.
- `arch-decision-records`, for the owner-metadata ADR.
- `nextest`, if targeted Rust test execution uses `cargo nextest`.
- `commit-message`, for every commit; messages are written to a temporary file
  and applied with `git commit -F`.
- `pr-creation` and `en-gb-oxendict`, for the draft pull request and prose.

Keep these repository documents open:

- [docs/roadmap.md](../roadmap.md), especially item 3.1.1 and its requirements
  on 2.1.1 and 1.3.1.
- [docs/stilyagi-design.md](../stilyagi-design.md), especially §§3.2, 4, 7.1,
  10, 11, and the §12 open question on owner metadata shape.
- [docs/rfcs/0001-stilyagi-intermediate-representation.md](
  ../rfcs/0001-stilyagi-intermediate-representation.md), especially the regions
  and owner sections.
- [docs/adr-003-v1-contract-scope.md](../adr-003-v1-contract-scope.md), which
  fixes Python docstrings as a stable v1 syntax surface.
- [docs/execplans/2-1-1-markdown-ir-envelope.md](2-1-1-markdown-ir-envelope.md),
  the precursor slice whose shape this plan mirrors.
- [docs/complexity-antipatterns-and-refactoring-strategies.md](
  ../complexity-antipatterns-and-refactoring-strategies.md), to keep the
  traversal and owner-derivation logic small enough to review.
- [docs/rust-testing-with-rstest-fixtures.md](
  ../rust-testing-with-rstest-fixtures.md) and
  [docs/reliable-testing-in-rust-via-dependency-injection.md]( ../reliable-testing-in-rust-via-dependency-injection.md),
  for Rust test style and explicit IO boundaries.
- [docs/rust-doctest-dry-guide.md](../rust-doctest-dry-guide.md), if new public
  Rust documentation includes examples.
- [docs/rstest-bdd-users-guide.md](../rstest-bdd-users-guide.md), for Rust BDD
  behaviour tests.
- [docs/developers-guide.md](../developers-guide.md) and
  [docs/users-guide.md](../users-guide.md), for the documentation updates.

External prior art checked during planning (Firecrawl):

- The `tree-sitter` Rust crate (current 0.25.x) provides `Parser`,
  `Parser::set_language`, byte-oriented `Node` spans (`start_byte`/`end_byte`),
  field access (`child_by_field_name`), named-child cursors, and recovery flags
  (`is_error`, `is_missing`, `has_error`). Reference:
  <https://docs.rs/tree-sitter>.
- The `tree-sitter-python` crate is at `0.25.0` and exposes the grammar through
  a `LANGUAGE` constant (`tree_sitter_python::LANGUAGE`). It requires a
  compatible `tree-sitter` 0.25.x. References:
  <https://crates.io/crates/tree-sitter-python>,
  <https://docs.rs/tree-sitter-python>.
- The tree-sitter-python grammar represents a docstring as the first
  `expression_statement` whose child is a `string`, placed first in a `module`
  (file scope) or first in the `block` body of a `class_definition` or
  `function_definition`. A widely used query is
  `(function_definition body: (block . (expression_statement (string) @doc)))`.
  Decorated definitions are wrapped by a `decorated_definition` node whose
  `definition` field holds the inner `function_definition`/`class_definition`.
  Reference: <https://github.com/tree-sitter/tree-sitter-python/issues/197>.
- A `string` node has `string_start`, `string_content`, and `string_end`
  children, so the prose can be mapped to `string_content` byte ranges that
  exclude quote delimiters and any string prefix. Reference: the grammar
  `node-types`/playground documented at
  <https://tree-sitter.github.io/tree-sitter/>.

## Constraints

- Do not implement this plan until explicit approval is recorded in this file.
- Preserve roadmap scope. This item implements owner-aware Python docstring
  extraction into the existing IR envelope. It does not implement Rust
  doc-comment extraction (3.1.2), Python suppression parsing (3.1.3), discovery
  defaults (3.2.1), docstring rules (3.2.2), or cache-key separation (3.3.1).
- Keep Markdown behaviour unchanged. The Markdown path, its snapshots, and its
  public surface must not regress.
- The `stilyagi-ir` crate owns the IR domain types. The Python extractor adapts
  to them. Do not redefine owner, region, segment, span, or document types in
  `stilyagi-tree-sitter`, `stilyagi-extract`, `stilyagi-pyext`, or Python.
- Keep source offsets byte-oriented. tree-sitter byte offsets map directly onto
  `SourceSpan` (UTF-8 bytes); any line or column data is derived from
  `line_index` and never replaces byte offsets as ground truth.
- Region `segments` must reconstruct `text` exactly
  (`IrRegion::segments_reconstruct_text` must hold for every emitted region).
  If a docstring shape cannot satisfy this, that shape stays out of scope and
  is recorded as a limitation rather than emitted incorrectly.
- The docstring lint surface is the verbatim bytes of `string_content`. v1 does
  not decode escape sequences, dedent, or apply PEP 257 cleaning during
  extraction; quote delimiters and string prefixes are elided markup. This
  keeps every docstring segment source-backed and fix-safe. Normalization
  belongs to the later rule layer.
- `owner` is populated for every `python_docstring` region and follows the
  RFC 0001 code-entity contract (`kind`, optional `name`, optional `qualname`).
  It must not be reused for non-code ancestry. The `IrOwner` `name` and
  `qualname` fields are plain `Option` with no `skip_serializing_if`, so a
  `None` serialises as JSON `null` (not an omitted key); module owners
  therefore emit `"name": null, "qualname": null`.
- Traversal and identifiers are deterministic: walk named children depth-first,
  left-to-right; assign node identifiers (`n0`, `n1`, …) in emission order;
  assign region identifiers (`r0`, `r1`, …) in docstring-discovery order; and
  append `errors` entries in source order.
- The docstring region is emitted as a single source-backed `IrSegment`
  spanning the `string_content` byte range. Because region `text` is then the
  exact source slice, `segments_reconstruct_text` holds trivially even for
  multi-line docstrings, CR-LF line endings, raw strings, escape sequences, and
  embedded quotes. No CR-LF-aware re-flow (unlike the Markdown flattener) is
  required, precisely because no synthetic insertion or markup elision happens
  inside the content span.
- Keep the non-Markdown structural surface minimal. RFC 0001 does not promise a
  stable full-node public surface for non-Markdown syntaxes in v1, so the
  Python extractor emits a bounded node store: a synthetic `module` root, each
  docstring-owning definition node, and each docstring `string` node, with
  honest parent/child links among them. It does not emit the full Python
  concrete syntax tree.
- Malformed Python must produce partial extraction plus recoverable `errors`
  entries, never a panic or aborted run.
- Extraction is pure over `(source, identity)`. No filesystem or environment
  access inside the extractor; IO stays at test and orchestration boundaries.
- Determinism: traversal order, generated identifiers (`n0`, `n1`, …; `r0`,
  `r1`, …), JSON field order, and canonical JSON output must not depend on
  hash-map ordering or platform specifics.
- Canonical JSON snapshots must avoid machine-specific absolute paths,
  timestamps, nondeterministic ordering, terminal colour, and environment
  values.
- Use `rstest` for Rust unit tests, `rstest-bdd` for Rust behaviour tests,
  `insta` for Rust snapshots, `proptest` for Rust invariants, `pytest` for
  Python unit tests, `pytest-bdd` for Python behaviour tests, `syrupy` for
  Python snapshots, and `hypothesis` for the Python property test.
- Do not add Kani, CrossHair, or Verus work unless a substantive unbounded
  invariant emerges that is better proved than tested. The Decision Log records
  why none is in scope at planning time.
- Run format, typecheck, lint, and tests sequentially, never in parallel.
  Capture long output with `tee` into `/tmp` logs.
- Run `coderabbit review --agent` after each major milestone, only after the
  deterministic gates for that milestone pass. Resolve or explicitly document
  all actionable concerns before moving on.
- Commit after each approved, gated milestone. Never commit failing code.
  Never use `git commit -m`.
- On completion, mark only roadmap item 3.1.1 as done in `docs/roadmap.md`.

## Tolerances (exception triggers)

- Scope: if implementation requires changing more than eighteen files or roughly
  1,200 net new lines excluding snapshots and fixtures, stop and ask before
  continuing.
- Dependencies: adding the Rust crates `tree-sitter` (0.25.x) and
  `tree-sitter-python` (0.25.x) to the workspace is expected. Any other new
  external dependency requires approval. If `tree-sitter-python` 0.25.x does
  not build against the chosen `tree-sitter` 0.25.x because of an application
  binary interface (ABI) mismatch, stop and record the compatible pair before
  pinning.
- Build toolchain: tree-sitter grammars compile vendored C through the `cc`
  crate. If the build host or CI lacks a working C compiler and this cannot be
  resolved within the existing CI image, stop and escalate before broadening
  build configuration.
- Public API: if a supported Python API or public Rust API must be removed or
  renamed rather than extended compatibly, stop and present options. Note that
  the existing pyext test asserting `python_docstring` is rejected is an
  expected, in-scope update, not a breaking change.
- Owner semantics: if the shared fixture or nested cases reveal that the chosen
  `qualname` semantics produce ambiguous or incorrect owners, stop and record
  options before changing the contract.
- Test attempts: if the same deterministic gate fails three times after a
  plausible fix, stop and record the failure with its log path.
- Performance: if warm extraction makes `make test` more than 20 seconds slower
  on this machine, document the cause and ask whether to narrow the work.
- Ambiguity: if two valid readings of RFC 0001 would produce different JSON
  shapes for `python_docstring` regions, stop and record the options before
  choosing.

## Risks

- Risk: tree-sitter byte spans for the `string`/`string_content` nodes do not
  line up with the exact prose bytes Stilyagi needs (for example around string
  prefixes or unusual quoting). Severity: high. Likelihood: medium. Mitigation:
  begin with a parser spike that prints `string_content` spans for the shared
  fixture and asserts the sliced bytes equal the region text before committing
  to type shapes; keep byte offsets canonical.

- Risk: owner derivation is wrong for nested or decorated declarations (for
  example treating a `decorated_definition` as the owner, or mis-joining
  `qualname`). Severity: high. Likelihood: medium. Mitigation: implement owner
  derivation as a small, table-tested function over an explicit owner stack;
  cover module, class, method, function-in-function, class-in-function, and
  decorated cases with rstest parameterization before snapshotting.

- Risk: malformed Python aborts extraction or panics instead of degrading.
  Severity: high. Likelihood: medium. Mitigation: never unwrap tree-sitter
  results; walk the recovered tree, skip `ERROR`/`MISSING` subtrees while still
  emitting well-formed docstrings, and record an `IrError` for detected
  anomalies. Add the malformed fixture to the test matrix from the start.

- Risk: f-strings or implicitly concatenated string literals are mis-classified
  as docstrings (an f-string is not a docstring in CPython). Severity: medium.
  Likelihood: medium. Mitigation: treat only a single `string` node with no
  interpolation and no format prefix as a docstring; document
  `concatenated_string` docstrings as a known v1 limitation with a test that
  asserts the current behaviour.

- Risk: emitting a bounded node store still implies a stable full-tree surface
  to consumers. Severity: medium. Likelihood: low. Mitigation: document the
  bounded node-store policy in the developers' guide and keep the Python tree
  `family` as `tree-sitter` with only the nodes the regions reference.

- Risk: Rust and Python golden IR helpers drift into two contracts. Severity:
  medium. Likelihood: medium. Mitigation: make Rust canonical JSON the source
  of truth; the Python parity test compares `Document.ir` against the reviewed
  Rust snapshot after the same source-identity normalization, as established in
  the 2.1.1 slice.

- Risk: enabling `python_docstring` breaks the existing pyext test that asserts
  rejection and the syntax-vocabulary parity check. Severity: medium.
  Likelihood: high (this is expected). Mitigation: update those tests as part
  of the bridge milestone and confirm the Python `Syntax` enum and the Rust
  `ExtractSyntax::ALL` still agree.

- Risk: the tree-sitter dependency increases cold build time and binary size,
  and requires a C compiler on every build host. Severity: medium. Likelihood:
  medium. Mitigation: confirm a working C compiler on CI in Stage 1, measure
  the cold build there and locally, keep the grammar scoped to the one crate
  that needs it, and stop and escalate if cold build plus `make test` breaches
  the 20-second tolerance. Re-run the 1.3.3 performance probe after Stage 2 to
  catch warm-path regression.

- Risk: canonical JSON field ordering churns as the Python region shape settles.
  Severity: low. Likelihood: medium. Mitigation: centralize serialization in
  `stilyagi-ir`, snapshot the output, and update snapshots only after reviewing
  the logical contract.

## Plan of work

### Stage 0: approval and baseline

This stage must not begin until explicit user approval is recorded. After
approval, `Status` changes to `APPROVED`, the approval is logged in the
`Decision Log`, and `Status` changes to `IN PROGRESS` when implementation
starts.

Confirm the branch and tree:

```bash
git branch --show-current   # expect 3-1-1-python-docstring-extraction
git status --short --branch
```

Run a baseline gate before any code change so later failures have a comparison
point:

```bash
BRANCH="$(git branch --show-current)"
make check-fmt 2>&1 | tee "/tmp/check-fmt-stilyagi-${BRANCH}.out"
make typecheck 2>&1 | tee "/tmp/typecheck-stilyagi-${BRANCH}.out"
make lint     2>&1 | tee "/tmp/lint-stilyagi-${BRANCH}.out"
make test     2>&1 | tee "/tmp/test-stilyagi-${BRANCH}.out"
```

Record the baseline result in `Surprises & Discoveries`. If a baseline gate
fails for reasons unrelated to this plan, decide whether the failure blocks
verification before proceeding.

### Stage 1: dependency and parser spike

Add `tree-sitter` and `tree-sitter-python` to `[workspace.dependencies]` in the
root `Cargo.toml` and depend on both from
`crates/stilyagi-tree-sitter/Cargo.toml`. Add `stilyagi-ir` as a path
dependency of `stilyagi-tree-sitter` (it currently has none).

First confirm the build toolchain. tree-sitter grammars compile vendored C
through the `cc` crate, so a working C compiler must exist locally and in CI.
Measure the cold build cost of the new dependencies and record it:

```bash
cargo build -p stilyagi-tree-sitter 2>&1 \
  | tee "/tmp/build-cold-tree-sitter-stilyagi-${BRANCH}.out"
```

If the CI image lacks a C compiler, or if the cold build plus `make test`
breaches the 20-second `make test` tolerance on the CI image, stop and escalate
before pinning the dependencies (see `Tolerances`).

Write a throwaway-then-promoted spike test in `stilyagi-tree-sitter` that parses
`tests/fixtures/corpus/python/valid/module-class-function-docstrings.py`,
loads the grammar through `tree_sitter_python::LANGUAGE`, and asserts:

1. The root node kind is `module`.
2. The first `expression_statement` child of `module` wraps a `string`.
3. The `string` node exposes a `string_content` child whose sliced source bytes
   equal the expected module-docstring prose verbatim (the byte-equality check
   that guards against span drift).
4. The `@staticmethod` method is reachable through a `decorated_definition`
   whose `definition` field is a `function_definition`, and the owning
   `function_definition` carries a `name` field of `method`.
5. An f-string first statement (`f"""x"""`) exposes an `interpolation` child
   and/or an `f` in its `string_start` text, and a `"a" "b"` first statement
   parses as `concatenated_string`, not `string`. These are the signals the
   extractor uses to reject non-docstrings.

Also spike the malformed fixture
`tests/fixtures/corpus/python/malformed/unclosed-function.py.txt`: print the
recovered tree's `to_sexp()` and the spans of any `ERROR`/`MISSING` nodes, and
record in the `Decision Log` exactly how tree-sitter recovers it — in
particular, confirm that the module docstring on line 1 survives recovery and
that the string inside the unclosed signature is *not* a first-statement
docstring (it sits inside the broken parameter list / `ERROR` subtree). This
captured behaviour becomes the ground truth for the Stage 3 malformed snapshot.

Run the targeted test:

```bash
cargo test -p stilyagi-tree-sitter 2>&1 \
  | tee "/tmp/test-tree-sitter-spike-stilyagi-${BRANCH}.out"
```

If the grammar cannot provide usable `string_content` spans for the fixture,
stop and record alternatives (for example, computing the content span from the
`string_start`/`string_end` children) in the `Decision Log` before proceeding.

### Stage 2: owner-aware Python extractor

Implement the extractor in `crates/stilyagi-tree-sitter/`, mirroring the
`stilyagi-markdown` boundary. Suggested module layout: keep generic tree-sitter
helpers in `lib.rs` (or a `support` module) and put Python-specific logic in a
`python` module, so item 3.1.2 can add a sibling `rust` module without
reshaping the crate.

Provide a public function equivalent to:

```rust
pub fn python_docstring_ir_document(
    source: &str,
    identity: stilyagi_ir::SourceIdentity,
) -> Result<stilyagi_ir::IrDocument, PythonExtractError>;
```

`PythonExtractError` covers only fatal failures (grammar load failure or an
absent parse tree). Recoverable parse anomalies are not errors; they become
`IrError` entries on the document. Keep the error type small.

The extractor:

1. Builds the envelope with:

   ```rust
   IrDocument::empty(
       DocumentMetadata::new("python", identity.path, identity.uri, source),
       vec![python_producer()],
       source,
   )
   ```

   `python_producer()` records `kind: "tree-sitter"`,
   `name: "tree-sitter-python"`, the pinned grammar version, and deterministic
   options.
2. Parses the source with tree-sitter and walks named children depth-first,
   left-to-right, maintaining an explicit owner stack. Only `class_definition`
   and `function_definition` nodes push an `OwnerFrame`; a
   `decorated_definition` is transparent (the walk descends through its
   `definition` field to the inner definition, and the decorator itself never
   appears in the stack or the qualname). `async def` is a
   `function_definition` and yields `kind: "function"` with no special marker.
   The stack frame is pushed on entry to a definition body and popped on exit,
   so it always reflects lexical ancestry.
3. For the `module` root and for each `class_definition`/`function_definition`
   body `block`, inspects the first statement. It emits a `python_docstring`
   region only when that statement is an `expression_statement` whose single
   child is a `string` node that (a) is not a `concatenated_string`, (b) has no
   `interpolation` child, and (c) whose `string_start` text contains no `f`/`F`
   format prefix. Concatenated-string and f-string first statements are not
   docstrings in v1 (documented limitation, with pinned rejection tests). A
   declaration whose first statement is anything else yields no region.
4. For each emitted region, populates `kind: "python_docstring"`,
   `scope: ["python", "docstring", <owner_kind>]`, `syntax: "python"`,
   `natural_language: None`, `text` from `string_content`, one source-backed
   `IrSegment` over the `string_content` byte span, `origin_nodes` referencing
   the emitted docstring node, `owner` from the owner stack, empty `attrs`, and
   `parent_region: None`.
5. Emits the bounded node store: a synthetic `module` root node, each
   docstring-owning definition node, and each docstring `string` node, all
   under one
   `IrTree { family: "tree-sitter", syntax: "python", root: <module id> }`. Node
   `flags` use `NodeFlags::named_source()`; nodes inside recovered error
   regions set `flags.error`/`flags.missing` as tree-sitter reports them.
6. On recovery anomalies, appends one `IrError` per top-level `ERROR`/`MISSING`
   subtree (not one giant whole-file error), in source order, then continues.
   Each entry uses `code: "python-parse-recovery"`, a message naming the node
   kind and byte span (for example, `"recovered ERROR node at bytes 56..118"`),
   and `span: Some(...)` for the affected range. Docstring `string` nodes that
   are themselves well-formed are still emitted normally with
   `flags.error == false`; the anomaly lives in `errors`, so rules can still
   process docstrings found in otherwise malformed files. The exact spans must
   match what the Stage 1 spike captured.
7. Validates IR consistency before returning, reusing the Markdown checks:
   content-hash match, line-index match, and `segments_reconstruct_text` for
   every region.

Owner derivation (a pure, table-tested function over the owner stack):

- module docstring: `kind: "module"`, `name: None`, `qualname: None`.
- class docstring: `kind: "class"`, `name: Some(<class name>)`,
  `qualname: Some(<qualname>)`.
- function/method docstring: `kind: "function"`, `name: Some(<def name>)`,
  `qualname: Some(<qualname>)`.
- `qualname` follows Python's `__qualname__` rules: dotted ancestry of named
  declarations, inserting `<locals>` between a function and any class or
  function declared inside its body (see `Decision Log`). The top-level module
  contributes no prefix. Decorators (`@staticmethod`, `@classmethod`,
  `@property`, or any user decorator), `async`, and statement nesting (`if`,
  `for`, `with`) do not change the qualname; only enclosing named `class`/
  `function` declarations do, with `<locals>` inserted after each enclosing
  function.

Worked example (the shared fixture path
`module > class FixtureExample > @staticmethod def method`):

```plaintext
stack on entering method body: [class FixtureExample] then [class FixtureExample, function method]
owner.kind     = "function"
owner.name     = "method"
owner.qualname = "FixtureExample.method"
```

For `def outer(): class Inner: """doc"""` the stack is
`[function outer, class Inner]` and `qualname = "outer.<locals>.Inner"`. For
`def outer(): def inner(): """doc"""` it is `outer.<locals>.inner`. For a
function defined inside `if`/`for`/`with` at function scope, `<locals>` still
applies because the enclosing scope is a function.

Wire dispatch in `crates/stilyagi-extract/src/lib.rs`: replace the
`PythonDocstring` arm of `extract_document_with_source_identity` with a call to
a new `extract_python_document` that delegates to
`python_docstring_ir_document` and maps `PythonExtractError` into a new
`ExtractError` arm (for example `ExtractError::PythonIr(...)`), keeping the
compile-time `ExtractError` size assertion satisfied (raise the budget
deliberately if needed). The coarse `ExtractRegion` list for Python mirrors the
emitted docstring regions (`kind: "python_docstring"`, `text`); add a
`RegionKind::PythonDocstring` variant for the typed spelling. `RustDocComment`
remains `UnsupportedSyntax`.

Before writing the extractor, add the fixtures this stage and Stage 3 need, so
the corpus anchors the snapshots (these augment the 1.3.1 corpus):

- `tests/fixtures/corpus/python/valid/nested-declarations.py`: a
  function-in-function with a docstring, a class-in-function with a docstring,
  a function-in-class (method) with a docstring, and a doubly decorated method,
  to exercise `<locals>` and decorator transparency.
- `tests/fixtures/corpus/python/valid/docstring-edge-cases.py`: a multi-line
  docstring, a raw (`r"""..."""`) docstring, a docstring containing embedded
  `"` and `'` quotes and backslash escapes, an empty docstring (`""""""`), and
  a whitespace-only docstring, plus an f-string first statement and a
  concatenated-string first statement that must *not* be extracted.

A CR-LF docstring case is covered by an inline test source (not a corpus file)
to avoid the formatter rewriting line endings; the test asserts the source
slice still contains literal `\r\n` and that reconstruction is exact.

Tests for this stage (run before the full gate):

- rstest unit tests in `stilyagi-tree-sitter`, parameterized over owner
  `kind`/`name`/`qualname`, covering at least: module docstring; class
  docstring; method (single and doubly decorated); `@classmethod`,
  `@staticmethod`, and `@property` methods (decorators must not change the
  qualname); `async def` at module and class scope; module-level function;
  function-in-function (`<locals>`); class-in-function (`<locals>`);
  function-in-class; a function defined inside `if`/`for`/`with` at function
  scope (`<locals>`); a declaration with no docstring; an f-string first
  statement (no region); a concatenated-string first statement (no region); and
  multi-line, raw, embedded-quote, empty, whitespace-only, and CR-LF docstrings
  (each reconstructs exactly).
- malformed-recovery rstest cases: the corpus malformed fixture must yield
  exactly one region (the module docstring) plus at least one `errors` entry,
  and must not panic; plus an inline source case
  (`module docstring → broken function → a later well-formed class with a docstring`)
  that documents whether tree-sitter recovery reaches the later class. The
  expected outcome is whatever Stage 1 captured; the test pins it so a grammar
  upgrade that changes recovery is caught.
- proptest invariants: for generated valid segment layouts,
  `segments_reconstruct_text` holds and source-backed segment bytes equal the
  source oracle; and the pure `qualname` builder is deterministic and matches
  `__qualname__` semantics over generated owner stacks of `(OwnerKind, name)`
  pairs.

```bash
cargo test -p stilyagi-tree-sitter -p stilyagi-extract 2>&1 \
  | tee "/tmp/test-extract-python-stilyagi-${BRANCH}.out"
```

After the targeted tests pass, re-run the roadmap 1.3.3 structural performance
probe to confirm warm extraction has not regressed against the recorded
baseline, and note the result on the milestone:

```bash
.venv/bin/python -m pytest -q tests/test_structural_performance_probe.py 2>&1 \
  | tee "/tmp/perf-probe-stage2-stilyagi-${BRANCH}.out"
```

Then run the full deterministic milestone gates (`make check-fmt`,
`make typecheck`, `make lint`, `make test`), then `coderabbit review --agent`,
resolve concerns, and commit.

### Stage 3: canonical JSON, golden fixtures, and snapshots

Add a Python golden IR builder to `crates/stilyagi-test-support/`, alongside
`golden_markdown_ir_fixture`, exposing something equivalent to:

```rust
pub fn golden_python_ir_fixture(
    relative_path: &str,
) -> Result<stilyagi_ir::IrDocument, FixtureReadError>;
```

It reads the corpus fixture and calls the production extractor, so the golden
builder cannot invent a second schema. Add a stable
`SHARED_PYTHON_FIXTURE_PATH` constant for
`tests/fixtures/corpus/python/valid/module-class-function-docstrings.py` and a
`MALFORMED_PYTHON_FIXTURE_PATH` constant for the malformed fixture.

Add insta snapshots for the canonical IR JSON of both Python fixtures (valid
and malformed). Place them beside the existing extraction snapshots
(`crates/stilyagi-extract/tests/extract/snapshots/`), using descriptive names
such as `python_docstring_valid_fixture` and
`python_docstring_malformed_fixture` (mirroring the existing
`..._shared_markdown_fixture_has_a_golden_ir_snapshot` convention). Accept a
snapshot only after diffing it and confirming each region's `text`, `segments`,
and `owner.kind`/`name`/`qualname` are correct and no spurious nodes or regions
appear. Review the diff, then:

```bash
INSTA_UPDATE=always cargo test -p stilyagi-test-support -p stilyagi-extract 2>&1 \
  | tee "/tmp/test-insta-python-stilyagi-${BRANCH}.out"
cargo test -p stilyagi-test-support -p stilyagi-extract 2>&1 \
  | tee "/tmp/test-insta-python-verify-stilyagi-${BRANCH}.out"
```

The malformed snapshot must show exactly one `python_docstring` region (the
module docstring) plus at least one `errors` entry whose `span` covers the
unclosed-signature region, and no region for the string sitting inside the
broken parameter list. Run the full gates, then `coderabbit review --agent`,
resolve concerns, and commit.

### Stage 4: Rust BDD behaviour coverage

Add an rstest-bdd feature describing owner-aware Python docstring extraction,
following `crates/stilyagi-pyext/tests/features/` and the
[rstest-bdd users' guide](../rstest-bdd-users-guide.md). The feature exercises
the externally observable extraction behaviour:

```gherkin
Feature: Owner-aware Python docstring extraction

  Scenario: Extract docstrings with their owning symbols
    Given a Python source file with module, class, and function docstrings
    When the extractor runs for the python_docstring syntax
    Then each docstring region records its prose text
    And each docstring region records its owning symbol kind and qualified name

  Scenario: Recover from a malformed Python file
    Given a Python source file whose function signature never closes
    When the extractor runs for the python_docstring syntax
    Then the module docstring is still extracted
    And a recoverable parse error is recorded
```

Implement the steps against the extractor (or the `stilyagi-extract` boundary).
Run targeted tests, then the full gates, then `coderabbit review --agent`,
resolve concerns, and commit.

### Stage 5: PyO3 bridge and Python model adaptation

The bridge already serialises an attached `IrDocument` to `ir_json`. Enabling
Python extraction therefore needs no new bridge fields. Update:

- `crates/stilyagi-pyext/src/lib.rs`: change the test that asserts
  `python_docstring` is rejected so it now asserts successful extraction with an
  `ir_json` payload whose first `python_docstring` region carries an `owner`.
  Keep the `not_a_syntax` rejection case.
- `crates/stilyagi-pyext/tests/features/bridge_structure.feature` and its steps,
  if they enumerate supported syntaxes, so Python extraction is covered.
- `python/stilyagi/_stilyagi_rs.pyi`, only if the payload description needs the
  `python_docstring` example; the field shape is unchanged.

Add Python tests:

- `pytest` unit tests calling
  `stilyagi.engine.extraction.extract_document(source, model.Syntax.PYTHON_DOCSTRING)`
  for the shared fixture, asserting the parsed `Document.ir` contains
  `python_docstring` regions with `owner` `kind`, `name`, and `qualname` for
  module, class, method, and function.
- a `pytest-bdd` feature under `features/` mirroring the Rust BDD scenarios for
  the externally observable Python workflow.
- a `syrupy` JSON snapshot of `Document.ir` for the shared Python fixture,
  redacting nondeterministic identity fields, and a parity assertion that the
  Python-parsed IR matches the reviewed Rust canonical snapshot after the same
  normalization (the 2.1.1 parity pattern; do not compare `ir_json` to itself).
  Define one shared redaction helper used by both the syrupy snapshot and the
  parity check that replaces the producer grammar `version` with a placeholder,
  normalises path separators to `/`, and canonicalises the source identity, so
  the two sides differ only in genuine contract terms. Run the parity test
  against the already-reviewed, checked-in Rust snapshot.
- a `hypothesis` property test that keeps the Python *shape* fixed and varies
  only the prose: it renders the template `def {name}():\n    """{body}"""`
  from an identifier strategy (`[A-Za-z_][A-Za-z0-9_]*`, excluding Python
  keywords) and a body strategy drawn from text excluding `"`, `\`, and
  newlines and not empty, then asserts the extractor returns exactly one
  `python_docstring` region whose `owner.qualname` equals `{name}` and whose
  region text equals `{body}`. Generating full Python syntax with hypothesis is
  deliberately avoided; the fixed-shape table cases above carry the structural
  coverage.

Build and run targeted Python tests:

```bash
make build 2>&1 | tee "/tmp/build-stage5-stilyagi-${BRANCH}.out"
.venv/bin/python -m pytest -q \
  tests/test_python_docstring_extraction.py \
  2>&1 | tee "/tmp/pytest-stage5-stilyagi-${BRANCH}.out"
```

Run the full gates, then `coderabbit review --agent`, resolve concerns, and
commit.

### Stage 6: documentation, ADR, and roadmap completion

- Add `docs/adr-005-docstring-owner-metadata.md` (Y-Statement format via
  `arch-decision-records`) recording the owner-metadata shape and the
  `__qualname__` semantics, the verbatim-`string_content` flattening decision,
  the bounded node-store policy, and the v1 limitations: module owners carry
  `name: null`/`qualname: null` (no package resolution from a path-only
  identity), and `concatenated_string` and f-string first statements are not
  treated as docstrings. Record a migration path for a future package-qualified
  module owner. Reference the ADR from `docs/stilyagi-design.md` §7.1 and
  resolve the §12 open question ("Exact owner metadata shape for docstrings and
  comments").
- Amend RFC 0001's owner section with a short note pointing to ADR 005 for the
  concrete Python `qualname` semantics, without changing the existing field
  contract.
- Update `docs/developers-guide.md` with the tree-sitter extraction boundary,
  owner derivation, `qualname` semantics, the verbatim-content flattening rule,
  the bounded node-store policy, and malformed-input handling. Include a short
  Markdown-versus-Python comparison table (parse entry, traversal, error
  recovery, owner metadata, node store) so maintainers see the deliberate
  differences at a glance. Record the bounded node store as a discoverable fact
  by setting a deterministic Python producer option (for example
  `"node_store": "bounded"`) rather than adding a field to the IR domain types,
  and state plainly that v1 rules must rely on `owner` metadata, not on
  navigating a full Python tree. Note that future rule work needing deeper
  inspection (decorators, signatures, bases) must plan its own full-tree change.
- Update `docs/users-guide.md` to record that `python_docstring` extraction is
  now supported and that `Document.ir` exposes `python_docstring` regions with
  `owner` metadata.
- Mark roadmap item 3.1.1 as done in `docs/roadmap.md`. Do not mark 3.1.2 or
  3.1.3 done.

Run the documentation gates and the full gates:

```bash
make fmt          2>&1 | tee "/tmp/fmt-stage6-stilyagi-${BRANCH}.out"
make markdownlint 2>&1 | tee "/tmp/markdownlint-stage6-stilyagi-${BRANCH}.out"
make nixie        2>&1 | tee "/tmp/nixie-stage6-stilyagi-${BRANCH}.out"
make check-fmt    2>&1 | tee "/tmp/check-fmt-stage6-stilyagi-${BRANCH}.out"
make typecheck    2>&1 | tee "/tmp/typecheck-stage6-stilyagi-${BRANCH}.out"
make lint         2>&1 | tee "/tmp/lint-stage6-stilyagi-${BRANCH}.out"
make test         2>&1 | tee "/tmp/test-stage6-stilyagi-${BRANCH}.out"
```

Run `coderabbit review --agent`, resolve concerns, and make the final commit.

## Concrete steps

All commands run from the repository root:

```bash
REPO_ROOT="$(pwd)"
cd "$REPO_ROOT"
leta workspace add "$REPO_ROOT"
```

Inspect symbols with `leta` rather than broad text search when a name is known:

```bash
leta grep "IrOwner|IrRegion|IrDocument|ExtractSyntax|extract_document" -k struct,enum,fn
leta show python_docstring_ir_document
leta refs ExtractSyntax
```

Use `rg` only for non-symbol text (fixtures, prose, snapshots):

```bash
rg -n "python_docstring|owner|qualname" docs tests crates
```

After each milestone, inspect and commit with a file-based message:

```bash
git status --short
git diff --stat
COMMIT_MSG_DIR="$(mktemp -d)"
cat > "$COMMIT_MSG_DIR/COMMIT_MSG.md" << 'ENDOFMSG'
Add owner-aware Python docstring extractor

Wire tree-sitter-python through stilyagi-tree-sitter to emit python_docstring
IR regions with source-backed segments and owner metadata for modules,
classes, and functions, per roadmap item 3.1.1.
ENDOFMSG
git commit -F "$COMMIT_MSG_DIR/COMMIT_MSG.md"
rm -rf "$COMMIT_MSG_DIR"
```

Each milestone uses a more specific subject; the example is a shape, not the
required final message.

## Validation and acceptance

Acceptance for the implemented feature:

- Running Python extraction on
  `tests/fixtures/corpus/python/valid/module-class-function-docstrings.py`
  produces an `IrDocument` with `document.syntax == "python"`,
  `document.encoding == "utf-8"`, a stable `sha256:` `content_hash`, a monotonic
  `line_index`, one `tree-sitter` tree, a bounded node store, and four
  `python_docstring` regions.
- The four regions carry owners: `{kind: "module"}`;
  `{kind: "class", name: "FixtureExample", qualname: "FixtureExample"}`;
  `{kind: "function", name: "method", qualname: "FixtureExample.method"}`; and
  `{kind: "function", name: "fixture_function", qualname: "fixture_function"}`.
- Each region's `segments` reconstruct its `text` exactly, and source-backed
  segment bytes equal the corresponding source slice (no span drift).
- Running extraction on
  `tests/fixtures/corpus/python/malformed/unclosed-function.py.txt` still emits
  the module docstring region and records at least one `errors` entry; it does
  not panic or abort.
- Canonical IR JSON snapshots for both Python fixtures are stable across
  repeated runs.
- The PyO3 bridge accepts `"python_docstring"`, returns `ir_json`, and the
  Python `Document.ir` exposes the regions with owner metadata. The Rust
  `ExtractSyntax::ALL` and Python `Syntax` vocabularies still agree.
- Markdown behaviour and snapshots are unchanged.
- `docs/adr-005-docstring-owner-metadata.md` exists and is referenced from the
  design; `docs/developers-guide.md` and `docs/users-guide.md` are updated;
  `docs/roadmap.md` marks only item 3.1.1 done.

Red-Green-Refactor evidence to record as work proceeds:

- Red: the chosen owner/region rstest (for example
  `python_method_docstring_owner_uses_class_qualname`) fails before the
  extractor exists, because `python_docstring` extraction returns
  `UnsupportedSyntax`. The malformed-recovery test fails for the expected
  reason (no region, no error).
- Green: after the extractor and dispatch land, the focused tests pass.
- Refactor: owner derivation and traversal are tidied; targeted tests and the
  wider gates rerun green.

Required gates after each major milestone:

```bash
make check-fmt
make typecheck
make lint
make test
```

Documentation gates after Markdown documentation changes:

```bash
make fmt
make markdownlint
make nixie
```

CodeRabbit validation after deterministic gates pass for each milestone:

```bash
coderabbit review --agent
```

CodeRabbit is not used to catch deterministic format, lint, type, or test
failures that local gates already catch. If CodeRabbit is rate-limited, wait
with `vsleep "$(shuf -i 15-30 -n 1)m"` before retrying. Capture all long gate
output with `tee` into `/tmp` logs and read the log before retrying a failure.

## Idempotence and recovery

Most steps are additive and safe to rerun: tests, snapshot verification, and the
`make` gates. Snapshot update commands (`INSTA_UPDATE=always`,
`--snapshot-update`) are safe only after the implementation diff has been
reviewed; if an update captures unintended churn, revert only the snapshot
changes from that milestone and fix the builder before updating again.

If the tree-sitter dependencies cause build or licensing problems, remove the
dependency changes from the current milestone, record the blocker in the
`Decision Log`, and stop for approval rather than substituting an ad hoc Python
scanner.

If a gate fails because of unrelated user changes, do not revert them; record
the failure and either work around it or escalate if it blocks verification.
Prefer new commits and targeted patches over destructive Git operations, and
request approval before any operation that could discard user work.

## Interfaces and dependencies

New workspace dependencies in `Cargo.toml`:

```toml
[workspace.dependencies]
tree-sitter = "0.25"
tree-sitter-python = "0.25"
```

`crates/stilyagi-tree-sitter/Cargo.toml` gains `tree-sitter.workspace = true`,
`tree-sitter-python.workspace = true`,
`stilyagi-ir = { path = "../stilyagi-ir" }`, `serde_json.workspace = true` (for
region attrs and producer options), and dev-dependencies
`rstest.workspace = true`, `rstest-bdd.workspace = true`,
`rstest-bdd-macros.workspace = true`, `insta.workspace = true`,
`proptest.workspace = true`, and
`stilyagi-test-support = { path = "../stilyagi-test-support" }`.

Crate spine: keep each language self-contained.
`crates/stilyagi-tree-sitter/ src/lib.rs` is the public surface and re-exports
from a `python` module; it does not host a speculative language-agnostic
abstraction layer. Genuinely shared tree-sitter helpers (for example, a "byte
span of a node" or "named child by field" convenience) move into a small
`support` module only if item 3.1.2's Rust extractor actually needs them; until
then, premature generalization is avoided.

Public Rust surface added in `crates/stilyagi-tree-sitter/src/`:

```rust
pub fn python_docstring_ir_document(
    source: &str,
    identity: stilyagi_ir::SourceIdentity,
) -> Result<stilyagi_ir::IrDocument, PythonExtractError>;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PythonExtractError {
    /// The Python grammar failed to load into the parser.
    GrammarLoad,
    /// tree-sitter returned no parse tree for the source.
    NoParseTree,
}
```

`PythonExtractError` carries only fatal cases and no owned payload, so it is a
small fieldless enum. Recoverable parse anomalies are never fatal; they become
`IrError` entries on the document. This deliberately keeps the bridged error
type tiny.

Owner derivation is a pure helper over an explicit stack:

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum OwnerKind { Module, Class, Function }

struct OwnerFrame { kind: OwnerKind, name: String }

fn owner_for(stack: &[OwnerFrame]) -> stilyagi_ir::IrOwner;
fn qualname_for(stack: &[OwnerFrame]) -> Option<String>;
```

`crates/stilyagi-extract/src/lib.rs` gains an
`ExtractError::PythonIr( PythonExtractError)` arm carrying the small fieldless
enum above. Because that payload is tiny, the existing 128-byte `ExtractError`
size assertion still holds and is not raised; if a future change does enlarge
it, raise the budget deliberately in a separate, justified step. The crate also
gains a `RegionKind::PythonDocstring` variant, routes
`ExtractSyntax::PythonDocstring` to the new path, and keeps `RustDocComment`
returning `UnsupportedSyntax`. `map_extract_error` in the PyO3 bridge maps
`ExtractError::PythonIr` to a `PyRuntimeError`, matching the Markdown arm.

`crates/stilyagi-test-support/src/` gains `golden_python_ir_fixture`,
`SHARED_PYTHON_FIXTURE_PATH`, and `MALFORMED_PYTHON_FIXTURE_PATH`, re-exported
from `lib.rs`.

The PyO3 bridge and Python models keep their current shapes; only behaviour
(syntax support) and tests change. `python/stilyagi/model/region.py` is not
required to gain an owner field in this slice because owner metadata travels in
`Document.ir`; adding a typed owner to the Python `Region` model is deferred to
the rule-facing work in roadmap item 3.2.2 unless review requires it sooner.

## Artifacts and notes

Planning used read-only reconnaissance agents over the roadmap, design, RFC
0001, the 2.1.1 execplan, the IR crate, the Markdown adapter, the PyO3 bridge,
the fixture corpus, and the test-support crate. Their shared conclusions:

- The IR owner contract already exists (`IrOwner` with `kind`/`name`/
  `qualname`), so this slice produces owners rather than designing the type.
- `stilyagi-tree-sitter` is the design-sanctioned home for Python (and later
  Rust) extraction and is currently an empty placeholder.
- The highest-risk areas are owner derivation for nested/decorated declarations
  and source-faithful `string_content` segment mapping.
- Enabling `python_docstring` is an expected, in-scope change to the pyext
  rejection test and the syntax-vocabulary parity check, not a breaking change.

Firecrawl confirmed the external tooling facts recorded in the documentation
signposts: `tree-sitter` 0.25.x and `tree-sitter-python` 0.25.0 with a
`LANGUAGE` constant, the `expression_statement (string)` docstring pattern, the
`decorated_definition` wrapper, and the `string_start`/`string_content`/
`string_end` node structure.

A community-of-experts review (Pandalump, Wafflecat, Buzzy Bee, Telefono,
Doggylump, Dinolump) stress-tested this draft before delivery. Accepted
revisions folded into the plan: keep `lib.rs` as a thin spine over a `python`
module (no premature generalization); commit `ExtractError::PythonIr` to a
small fieldless payload so the 128-byte size assertion holds; specify `None`
owner fields serialise as `null`; make the single-source-backed-segment
reconstruction guarantee explicit (covers CR-LF, raw strings, escapes, embedded
quotes, empty docstrings); pin determinism of traversal and identifier
assignment; concretise f-string and `concatenated_string` rejection; expand the
owner test table (`async`, `@classmethod`/`@staticmethod`/`@property`, nested
decorators, function-in-function, class-in-function, statement-nested defs) and
add `nested-declarations.py` and `docstring-edge-cases.py` fixtures; require
the Stage 1 spike to capture tree-sitter's recovery of the malformed fixture
and a cold-build measurement plus C-compiler check; make the malformed
acceptance exact (one region plus per-`ERROR`-subtree `IrError`s); define
IR-error message content; specify snapshot naming and a shared parity redaction
helper; keep the hypothesis test to fixed-shape source with generated prose;
and record the manual-walk, bounded-store, and module-anonymity decisions in
the Decision Log and ADR 005. The tensions surfaced (bounded store versus
future rule depth; hypothesis breadth versus flakiness; query elegance versus
single-pass owner tracking) were resolved in favour of the bounded v1 contract,
documented for the 3.1.2 and 3.2.2 follow-ups.

## Progress

- [x] (2026-06-12) Loaded `leta`, `hexagonal-architecture`, `python-router`,
  and `rust-router` skills and created the `leta` workspace.
- [x] (2026-06-12) Drafted this pre-implementation ExecPlan with agent-team
  reconnaissance, Firecrawl tooling research, and a community-of-experts review
  whose accepted revisions are folded into the plan and Decision Log.
- [x] (2026-06-12) Renamed the branch to `3-1-1-python-docstring-extraction`,
  pushed with upstream tracking, and opened draft PR
  <https://github.com/leynos/stilyagi/pull/30> for the execplan.
- [x] (2026-06-15) User approved implementation by requesting that the planned
  functionality be implemented from this execplan.
- [x] (2026-06-15) Stage 0 approval and baseline gates captured. Logs:
  `/tmp/check-fmt-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/typecheck-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/lint-stilyagi-3-1-1-python-docstring-extraction.out`, and
  `/tmp/test-stilyagi-3-1-1-python-docstring-extraction.out`.
- [x] (2026-06-15) Stage 0 CodeRabbit review completed with zero findings.
  Log: `/tmp/coderabbit-stage0-stilyagi-3-1-1-python-docstring-extraction.out`.
- [x] (2026-06-15) Stage 1 dependency and parser spike completed. Logs:
  `/tmp/build-cold-tree-sitter-stilyagi-3-1-1-python-docstring-extraction.out`
  and
  `/tmp/test-tree-sitter-spike-stilyagi-3-1-1-python-docstring-extraction.out`.
- [x] (2026-06-15) Stage 1 deterministic gates and CodeRabbit review passed
  with zero findings. Logs:
  `/tmp/check-fmt-stage1-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/typecheck-stage1-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/lint-stage1-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/test-stage1-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/markdownlint-stage1-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/nixie-stage1-stilyagi-3-1-1-python-docstring-extraction.out`, and
  `/tmp/coderabbit-stage1-stilyagi-3-1-1-python-docstring-extraction.out`.
- [x] (2026-06-15) Stage 2 owner-aware Python extractor and dispatch
  implemented. Red evidence:
  `/tmp/test-tree-sitter-stage2-red-stilyagi-3-1-1-python-docstring-extraction.out`
  failed with the expected `NoParseTree` stub. Green evidence:
  `/tmp/test-extract-python-stilyagi-3-1-1-python-docstring-extraction.out`
  passed for `stilyagi-tree-sitter` and `stilyagi-extract`, and
  `/tmp/perf-probe-stage2-stilyagi-3-1-1-python-docstring-extraction.out`
  passed 16/16 structural performance probe tests in 0.23s.
- [x] (2026-06-15) Stage 2 bridge and Python facade follow-up completed after
  the full test gate exposed stale unsupported-syntax expectations. Evidence:
  `/tmp/test-stage2-stilyagi-3-1-1-python-docstring-extraction.out` failed
  because the PyO3 rejection test still expected `python_docstring` to error;
  `/tmp/test-stage2-rerun-stilyagi-3-1-1-python-docstring-extraction.out` then
  failed because the typed Python facade test still treated
  `model.Syntax.PYTHON_DOCSTRING` as unsupported. Focused fixes passed in
  `/tmp/test-pyext-python-docstring-focused-stilyagi-3-1-1-python-docstring-extraction.out`
  and
  `/tmp/test-python-facade-stage2-focused-stilyagi-3-1-1-python-docstring-extraction.out`.
- [x] (2026-06-15) Stage 2 deterministic gates passed before CodeRabbit.
  Logs:
  `/tmp/check-fmt-stage2-final-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/typecheck-stage2-final-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/lint-stage2-final-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/test-stage2-final-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/markdownlint-stage2-final-stilyagi-3-1-1-python-docstring-extraction.out`,
  and `/tmp/nixie-stage2-final-stilyagi-3-1-1-python-docstring-extraction.out`.
- [x] (2026-06-15) Stage 2 CodeRabbit review returned one trivial finding.
  Evidence:
  `/tmp/coderabbit-stage2-stilyagi-3-1-1-python-docstring-extraction.out`. The
  direct suggestion to use `expect(...)` conflicted with the crate's
  `clippy::expect_used` gate, so the helper cleanup was implemented with
  explicit `match` expressions instead. Follow-up gates passed in
  `/tmp/check-fmt-stage2-coderabbit-match-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/typecheck-stage2-coderabbit-match-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/lint-stage2-coderabbit-match-stilyagi-3-1-1-python-docstring-extraction.out`,
  and
  `/tmp/test-stage2-coderabbit-match-stilyagi-3-1-1-python-docstring-extraction.out`.
- [x] (2026-06-15) Stage 2 follow-up CodeRabbit review returned one trivial
  finding asking for an inline comment documenting Python `<locals>` qualname
  semantics. Evidence:
  `/tmp/coderabbit-stage2-rerun-stilyagi-3-1-1-python-docstring-extraction.out`.
  The comment was added in `python/owner.rs`, and gates passed in
  `/tmp/check-fmt-stage2-coderabbit-comment-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/typecheck-stage2-coderabbit-comment-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/lint-stage2-coderabbit-comment-stilyagi-3-1-1-python-docstring-extraction.out`,
  and
  `/tmp/test-stage2-coderabbit-comment-stilyagi-3-1-1-python-docstring-extraction.out`.
- [x] (2026-06-15) Stage 2 third CodeRabbit review returned 13 findings:
  stronger qualname properties, narrower fixture suppressions, and explanatory
  Rustdoc/rationale comments for Python extractor helpers. Evidence:
  `/tmp/coderabbit-stage2-comment-rerun-stilyagi-3-1-1-python-docstring-extraction.out`.
  All were addressed while keeping `python/mod.rs` at the 400-line limit.
  Focused evidence:
  `/tmp/ruff-fixtures-stage2-coderabbit-docs-stilyagi-3-1-1-python-docstring-extraction.out`
  and
  `/tmp/test-owner-stage2-coderabbit-docs-stilyagi-3-1-1-python-docstring-extraction.out`.
  Full gates passed in
  `/tmp/check-fmt-stage2-coderabbit-docs-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/typecheck-stage2-coderabbit-docs-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/lint-stage2-coderabbit-docs-stilyagi-3-1-1-python-docstring-extraction.out`,
  and
  `/tmp/test-stage2-coderabbit-docs-stilyagi-3-1-1-python-docstring-extraction.out`.
- [x] (2026-06-15) Stage 2 fourth CodeRabbit review returned 6 findings.
  Evidence:
  `/tmp/coderabbit-stage2-docs-rerun-stilyagi-3-1-1-python-docstring-extraction.out`.
  The valid concerns were addressed by splitting Python helper functions into
  `python/helpers.rs`, making text extraction fallible, documenting the
  defensive source-span fallback, and centralizing the `<locals>` marker. The
  repeated `expect(...)` test-helper suggestion was not applied because the
  repository's `clippy::expect_used` gate had already rejected that exact
  change. Full gates passed in
  `/tmp/check-fmt-stage2-helpers-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/typecheck-stage2-helpers-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/lint-stage2-helpers-stilyagi-3-1-1-python-docstring-extraction.out`,
  and `/tmp/test-stage2-helpers-stilyagi-3-1-1-python-docstring-extraction.out`.
- [x] (2026-06-15) Stage 2 final CodeRabbit review completed with zero
  findings. Evidence:
  `/tmp/coderabbit-stage2-helpers-rerun-stilyagi-3-1-1-python-docstring-extraction.out`.
- [x] (2026-06-15) Stage 3 Python golden fixture builder and canonical IR
  snapshots implemented. The new `golden_python_ir_fixture` delegates to the
  production tree-sitter extractor to avoid a second schema implementation,
  while extraction snapshots pin both the valid shared fixture and the
  malformed fixture. Evidence:
  `/tmp/test-insta-python-preupdate-stilyagi-3-1-1-python-docstring-extraction.out`
  failed only because the reviewed snapshots were new,
  `/tmp/test-insta-python-stilyagi-3-1-1-python-docstring-extraction.out`
  accepted them, and
  `/tmp/test-insta-python-verify-stilyagi-3-1-1-python-docstring-extraction.out`
  passed without update mode.
- [x] (2026-06-15) Stage 3 deterministic gates passed after replacing direct
  test indexing with `.first()`. Evidence:
  `/tmp/lint-stage3-stilyagi-3-1-1-python-docstring-extraction.out` first
  failed on `clippy::indexing_slicing`; rerun logs
  `/tmp/check-fmt-stage3-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/typecheck-stage3-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/lint-stage3-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/test-stage3-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/markdownlint-stage3-stilyagi-3-1-1-python-docstring-extraction.out`, and
  `/tmp/nixie-stage3-stilyagi-3-1-1-python-docstring-extraction.out` passed.
- [x] (2026-06-15) Stage 3 CodeRabbit review completed with zero findings.
  Evidence:
  `/tmp/coderabbit-stage3-stilyagi-3-1-1-python-docstring-extraction.out`.
- [x] (2026-06-15) Stage 4 Rust BDD behaviour coverage implemented for the
  `stilyagi-extract` boundary. Evidence:
  `/tmp/test-extract-bdd-stage4-stilyagi-3-1-1-python-docstring-extraction.out`
  first failed because step functions used a fixture parameter name that did
  not match `python_docstring_state`;
  `/tmp/test-extract-bdd-stage4-rerun-stilyagi-3-1-1-python-docstring-extraction.out`
  then failed on a stale expected function docstring;
  `/tmp/test-extract-bdd-stage4-green-stilyagi-3-1-1-python-docstring-extraction.out`
  passed with 47/47 `stilyagi-extract` tests.
- [x] (2026-06-15) Stage 4 deterministic gates passed before CodeRabbit.
  Evidence:
  `/tmp/check-fmt-stage4-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/typecheck-stage4-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/lint-stage4-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/test-stage4-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/markdownlint-stage4-stilyagi-3-1-1-python-docstring-extraction.out`, and
  `/tmp/nixie-stage4-stilyagi-3-1-1-python-docstring-extraction.out` passed.
- [x] (2026-06-15) Stage 4 CodeRabbit review returned four trivial findings
  asking for `.expect(...)` in test-only BDD helpers. Evidence:
  `/tmp/coderabbit-stage4-stilyagi-3-1-1-python-docstring-extraction.out`. The
  suggestions were applied with tightly scoped `clippy::expect_used`
  expectations and reasons, matching the existing PyO3 BDD style. Follow-up
  gates passed in
  `/tmp/check-fmt-stage4-coderabbit-rerun2-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/typecheck-stage4-coderabbit-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/lint-stage4-coderabbit-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  and
  `/tmp/test-stage4-coderabbit-rerun-stilyagi-3-1-1-python-docstring-extraction.out`.
- [x] (2026-06-15) Stage 4 second CodeRabbit review returned two findings:
  remove a `const fn` marker from the BDD IR helper and remove `let _ = ...`
  from scenario bodies. Evidence:
  `/tmp/coderabbit-stage4-rerun-stilyagi-3-1-1-python-docstring-extraction.out`.
  The regular helper shape was kept with a scoped `missing_const_for_fn`
  rationale because CodeRabbit correctly identified the runtime panic path, and
  empty scenario bodies retained the exact fixture parameter names required by
  `rstest-bdd`. Follow-up gates passed in
  `/tmp/check-fmt-stage4-coderabbit2-rerun2-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/typecheck-stage4-coderabbit2-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/lint-stage4-coderabbit2-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  and
  `/tmp/test-stage4-coderabbit2-rerun-stilyagi-3-1-1-python-docstring-extraction.out`.
- [x] (2026-06-15) Stage 4 final CodeRabbit review completed with zero
  findings. Evidence:
  `/tmp/coderabbit-stage4-rerun2-stilyagi-3-1-1-python-docstring-extraction.out`.
- [x] (2026-06-15) Stage 5 Python-facing bridge/model coverage implemented.
  The existing PyO3 bridge support was extended with dedicated Python tests for
  shared-fixture owners, malformed recovery, Rust snapshot parity, a syrupy
  snapshot, and a fixed-shape Hypothesis property. Evidence:
  `/tmp/pytest-stage5-preupdate-stilyagi-3-1-1-python-docstring-extraction.out`
  failed only because the syrupy snapshot was new,
  `/tmp/pytest-stage5-snapshot-update-stilyagi-3-1-1-python-docstring-extraction.out`
  generated the snapshot and exposed that NUL/control characters are invalid
  in the generated Python source shape, and
  `/tmp/pytest-stage5-focused-stilyagi-3-1-1-python-docstring-extraction.out`
  passed after excluding control characters from the generated docstring body.
- [x] (2026-06-15) Stage 5 deterministic gates passed before CodeRabbit.
  `make check-fmt` initially reported Python/Markdown formatting drift, and
  `make fmt` applied the canonical formatting. Evidence:
  `/tmp/fmt-stage5-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/check-fmt-stage5-rerun3-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/typecheck-stage5-rerun2-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/lint-stage5-rerun2-stilyagi-3-1-1-python-docstring-extraction.out`, and
  `/tmp/test-stage5-stilyagi-3-1-1-python-docstring-extraction.out` passed;
  the full test gate reported 159 Rust tests, 102 Python tests, and five
  snapshots passing.
- [x] (2026-06-15) Stage 5 CodeRabbit review returned one trivial test
  readability finding: add descriptive assertion messages to the Python BDD
  helper assertions. Evidence:
  `/tmp/coderabbit-stage5-stilyagi-3-1-1-python-docstring-extraction.out`. The
  finding was applied without changing test behaviour. Follow-up gates passed in
  `/tmp/pytest-stage5-coderabbit-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/check-fmt-stage5-coderabbit-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/typecheck-stage5-coderabbit-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/lint-stage5-coderabbit-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  and
  `/tmp/test-stage5-coderabbit-rerun-stilyagi-3-1-1-python-docstring-extraction.out`.
- [x] (2026-06-15) Stage 5 follow-up CodeRabbit review returned one invalid
  critical finding that treated the shared-fixture syrupy snapshot as if it
  were generated from `nested-declarations.py`. Evidence:
  `/tmp/coderabbit-stage5-rerun-stilyagi-3-1-1-python-docstring-extraction.out`.
  The test and snapshot were verified against
  `module-class-function-docstrings.py`; to make the contract unambiguous, the
  snapshot test was renamed to reference the shared fixture explicitly and the
  snapshot was regenerated in
  `/tmp/pytest-stage5-snapshot-rename-stilyagi-3-1-1-python-docstring-extraction.out`.
- [x] (2026-06-15) Stage 5 second follow-up deterministic gates and
  CodeRabbit review completed cleanly. Evidence:
  `/tmp/check-fmt-stage5-coderabbit2-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/typecheck-stage5-coderabbit2-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/lint-stage5-coderabbit2-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/test-stage5-coderabbit2-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/markdownlint-stage5-coderabbit2-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/nixie-stage5-coderabbit2-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  and
  `/tmp/coderabbit-stage5-rerun2-stilyagi-3-1-1-python-docstring-extraction.out`
  passed with zero CodeRabbit findings.
- [x] (2026-06-15) Stage 6 documentation updates drafted. Added
  `docs/adr-005-docstring-owner-metadata.md`, referenced ADR 005 from the
  contents and design documents, amended RFC 0001 with a Python owner-semantics
  note, documented Python docstring owner metadata in the user and developer
  guides, and marked only roadmap item 3.1.1 complete.
- [x] (2026-06-15) Stage 6 deterministic gates passed before CodeRabbit.
  Evidence: `/tmp/fmt-stage6-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/markdownlint-stage6-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/nixie-stage6-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/check-fmt-stage6-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/typecheck-stage6-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/lint-stage6-stilyagi-3-1-1-python-docstring-extraction.out`, and
  `/tmp/test-stage6-stilyagi-3-1-1-python-docstring-extraction.out` passed; the
  full test gate reported 159 Rust tests, 102 Python tests, and five snapshots
  passing.
- [x] (2026-06-15) Stage 6 CodeRabbit review returned three ADR findings:
  remove first-person Y-Statement wording, reflow the ADR, and reshape ADR 005
  to match the repository's Context, Problem statement, and Decision structure.
  Evidence:
  `/tmp/coderabbit-stage6-stilyagi-3-1-1-python-docstring-extraction.out`. The
  ADR was restructured and revalidated with
  `/tmp/fmt-stage6-coderabbit-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/markdownlint-stage6-coderabbit-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  and
  `/tmp/nixie-stage6-coderabbit-rerun-stilyagi-3-1-1-python-docstring-extraction.out`.
- [x] (2026-06-15) Stage 6 follow-up CodeRabbit review returned two ADR
  findings: use Oxford `serialize` spelling and convert the alternatives list
  into a captioned comparison table. Evidence:
  `/tmp/coderabbit-stage6-rerun-stilyagi-3-1-1-python-docstring-extraction.out`.
  The ADR was updated and revalidated with
  `/tmp/fmt-stage6-coderabbit2-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/markdownlint-stage6-coderabbit2-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  and
  `/tmp/nixie-stage6-coderabbit2-rerun-stilyagi-3-1-1-python-docstring-extraction.out`.
- [x] (2026-06-15) Stage 6 second follow-up CodeRabbit review returned two ADR
  wording findings: remove a repeated `needs` phrase and avoid the contested
  `serialize` spelling in favour of `emit`. Evidence:
  `/tmp/coderabbit-stage6-rerun2-stilyagi-3-1-1-python-docstring-extraction.out`.
  The ADR was updated and revalidated with
  `/tmp/fmt-stage6-coderabbit3-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/markdownlint-stage6-coderabbit3-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  and
  `/tmp/nixie-stage6-coderabbit3-rerun-stilyagi-3-1-1-python-docstring-extraction.out`.
- [x] (2026-06-15) Stage 6 third follow-up CodeRabbit review returned two
  trivial ADR style findings: move the alternatives table caption below the
  table and replace `its own implementation slice` with
  `a separate implementation slice`. Evidence:
  `/tmp/coderabbit-stage6-rerun3-stilyagi-3-1-1-python-docstring-extraction.out`.
- [x] (2026-06-15) Stage 6 fourth follow-up CodeRabbit review returned one
  trivial ADR finding and one minor Python snapshot-stability finding. The ADR
  now links PEP 257, and `_normalize_python_ir` redacts `document.content_hash`
  before JSON snapshot comparison. Evidence:
  `/tmp/coderabbit-stage6-rerun4-stilyagi-3-1-1-python-docstring-extraction.out`.
  The affected snapshot was updated with
  `/tmp/pytest-stage6-coderabbit5-snapshot-update-stilyagi-3-1-1-python-docstring-extraction.out`,
  the focused Python docstring test file passed in
  `/tmp/pytest-stage6-coderabbit5-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  and the full gates passed in
  `/tmp/fmt-stage6-coderabbit5-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/markdownlint-stage6-coderabbit5-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/nixie-stage6-coderabbit5-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/check-fmt-stage6-coderabbit5-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/typecheck-stage6-coderabbit5-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  `/tmp/lint-stage6-coderabbit5-rerun-stilyagi-3-1-1-python-docstring-extraction.out`,
  and
  `/tmp/test-stage6-coderabbit5-rerun-stilyagi-3-1-1-python-docstring-extraction.out`.
- [x] (2026-06-15) Stage 6 fifth follow-up CodeRabbit review returned two ADR
  structure findings: fold the date into the Status section and combine Context
  with Problem Statement under the repository ADR heading convention. Evidence:
  `/tmp/coderabbit-stage6-rerun5-stilyagi-3-1-1-python-docstring-extraction.out`.
- [x] (2026-06-15) Stage 6 final CodeRabbit review completed with zero
  findings. Evidence:
  `/tmp/coderabbit-stage6-rerun6-stilyagi-3-1-1-python-docstring-extraction.out`.
- [x] (2026-06-15) Stage 6 final validation completed, committed as
  `c1c913f Document Python docstring metadata`, and pushed to
  `origin/3-1-1-python-docstring-extraction`.
- [x] (2026-06-15) Formatter-only follow-up for the unrelated completed
  maturin/PyO3 execplan was committed as `e7e193c Format maturin execplan` and
  pushed with the branch so the worktree ended clean.

## Surprises & Discoveries

- Observation: the IR crate already models the owner contract and the
  `python_docstring` region vocabulary is anticipated throughout the codebase
  (`ExtractSyntax::PythonDocstring`, `Syntax.PYTHON_DOCSTRING`). Evidence:
  `crates/stilyagi-ir/src/region.rs` defines `IrOwner`;
  `crates/stilyagi-extract/src/lib.rs` already spells `python_docstring`.
  Impact: this slice fills in the producer, not the contract.

- Observation: the pre-implementation baseline is clean on 2026-06-15. Evidence:
  `make check-fmt`, `make typecheck`, `make lint`, and `make test` all passed
  sequentially, with `make test` reporting 131/131 Rust tests and 97/97 Python
  tests passed. Impact: subsequent gate failures should be treated as caused by
  this implementation unless a new unrelated change is discovered.

- Observation: `tree-sitter` 0.25.10 and `tree-sitter-python` 0.25.0 build
  locally through the vendored C grammar. Evidence:
  `cargo build -p stilyagi-tree-sitter` passed after adding the dependencies,
  with Cargo waiting briefly for the shared build directory lock and then
  finishing in 5.16s. Impact: Stage 1 did not hit the C-toolchain or ABI
  tolerance.

- Observation: `tree-sitter-python` exposes the shared fixture's module
  docstring as `module > expression_statement > string`, but the first named
  child of `string` is `string_start`; `string_content` must be selected by
  kind rather than by position. Evidence: the spike test
  `python_fixture_exposes_docstring_content_spans` failed with
  `left: "string_start"` before the test was corrected. Impact: the extractor
  must search direct string children by kind to avoid span drift.

- Observation: decorated methods are represented as `decorated_definition`
  nodes whose `definition` field is the inner `function_definition`, and the
  shared fixture's method name field is `method`. Evidence:
  `python_fixture_reaches_staticmethod_definition_through_decorator` passes.
  Impact: Stage 2 can treat decorators as transparent owner wrappers.

- Observation: the malformed fixture preserves the module docstring inside a
  recovered tree whose root first named child is an `ERROR`; descendant `ERROR`
  spans are `0..168` and `57..77`, and no top-level `function_definition` is
  emitted. Evidence: `malformed_python_fixture_recovers_the_module_docstring`
  pins these spans. Impact: Stage 2 should emit the module docstring and record
  recoverable parse diagnostics without treating the broken signature string as
  a function docstring.

- Observation: the Stage 3 test-support snapshot was created only when the
  planned `INSTA_UPDATE=always` command was run; the pre-update failure
  surfaced only the two extraction snapshots because those were the first new
  snapshots hit in the combined package run. Evidence:
  `/tmp/test-insta-python-stilyagi-3-1-1-python-docstring-extraction.out`.
  Impact: accepting snapshots through the full targeted package set is
  necessary so helper-level and integration-level contracts stay in sync.

- Observation: `rstest-bdd` binds step fixtures by parameter name, not just
  type. Evidence:
  `/tmp/test-extract-bdd-stage4-stilyagi-3-1-1-python-docstring-extraction.out`
  reported that step fixture `state` was missing while scenario fixture
  `python_docstring_state` was available. Impact: new BDD steps should keep
  scenario fixture parameter names identical across the scenario and every step
  definition.

- Observation: fixed-shape Python docstring generation must exclude raw control
  characters as well as quotes, backslashes, and newlines. Evidence:
  `/tmp/pytest-stage5-snapshot-update-stilyagi-3-1-1-python-docstring-extraction.out`
  shrank to `body='\x00'`, which produced invalid Python source with no
  extracted docstring. Impact: the property remains structural but constrains
  generated prose to source text that can appear literally in the triple-quoted
  template.

- Observation: empty Python docstrings have no `string_content` node in the
  tree-sitter-python grammar. Evidence: the Stage 2 edge-case test failed until
  extraction computed an empty source span between `string_start` and
  `string_end`. Impact: the extractor handles empty docstrings explicitly
  rather than treating the missing child as an absent docstring.

- Observation: Python `__qualname__` semantics insert `<locals>` after an
  enclosing function, not before every function frame. Evidence: the shared
  fixture initially produced `FixtureExample.<locals>.method`; the corrected
  owner helper now pins `FixtureExample.method` and
  `outer_function.<locals>.LocalClass`. Impact: Stage 2 owner derivation is
  covered by rstest table cases and a proptest determinism check.

- Observation: splitting the Python extractor into `python/mod.rs`,
  `python/owner.rs`, `python/support.rs`, and `python/tests.rs` keeps each code
  file at or below the repository's 400-line limit. Evidence: `wc -l` reported
  `python/mod.rs` at 394 lines and `stilyagi-extract/src/lib.rs` at 400 lines
  after the split. Impact: further Stage 2 work should avoid growing these
  files; add sibling modules for new behaviour.

- Observation: enabling `python_docstring` at the Rust dispatch layer changes
  user-visible Python package behaviour immediately because
  `python/stilyagi/engine/extraction.py` delegates every bridge-supported
  spelling through `_stilyagi_rs.extract_document`. Evidence: full `make test`
  first failed in the PyO3 unsupported-syntax table, then in
  `test_engine_extract_document_rejects_unsupported_syntaxes[python_docstring]`.
  Impact: Stage 2 must update PyO3 tests, typed Python facade tests, and
  living docs as part of the same behaviour change.

## Decision Log

- Decision: keep `Status: DRAFT` and block implementation until the user
  records explicit approval. Rationale: the execplans approval gate.
  Date/Author: 2026-06-12, planning agent.

- Decision: implement Python extraction in `crates/stilyagi-tree-sitter` rather
  than a new crate. Rationale: the design §10 crate list names this crate for
  tree-sitter work and excludes a separate `stilyagi-python` crate; item 3.1.2
  will add Rust extraction beside it. Date/Author: 2026-06-12, planning agent.

- Decision: parse with `tree-sitter` + `tree-sitter-python` rather than a
  Python AST parser (for example RustPython). Rationale: the design mandates
  tree-sitter for error-tolerant host-language extraction, which is required by
  the malformed-input acceptance criterion. Date/Author: 2026-06-12, planning
  agent.

- Decision: the docstring lint surface is the verbatim `string_content` bytes,
  with quote delimiters and string prefixes treated as elided markup and no
  escape decoding, dedenting, or PEP 257 cleaning at extraction time.
  Rationale: keeps every docstring segment source-backed and fix-safe and
  defers normalization to the rule layer (3.2.2). Date/Author: 2026-06-12,
  planning agent.

- Decision: `qualname` follows Python's `__qualname__` semantics, inserting
  `<locals>` between a function and entities declared in its body, with no
  prefix for module-level entities. Rationale: it is the canonical,
  well-defined qualified-name format Python rules are most likely to expect;
  the alternative (a plain dotted path) silently collides for function-local
  declarations. Recorded for ratification in ADR 005 and an RFC 0001 note.
  Date/Author: 2026-06-12, planning agent.

- Decision: emit a bounded node store (synthetic `module` root, owning
  definition nodes, and docstring `string` nodes) rather than the full Python
  concrete syntax tree. Rationale: RFC 0001 does not promise a stable full-node
  surface for non-Markdown syntaxes in v1, and a bounded store still satisfies
  `origin_nodes` and segment `node` references. Date/Author: 2026-06-12,
  planning agent.

- Decision: treat only a single non-format `string` first statement as a
  docstring; f-strings and `concatenated_string` first statements are not
  docstrings in v1. Rationale: matches CPython for f-strings and bounds scope;
  the concatenated-string case is a documented limitation with a pinned test.
  Date/Author: 2026-06-12, planning agent.

- Decision: do not add Kani, CrossHair, or Verus work. Rationale: the only
  introduced invariants (segment reconstruction; deterministic `qualname`
  construction) are bounded and well covered by proptest and hypothesis; no
  unbounded numeric or ordering property warrants a deductive proof. Revisit if
  a substantive provable axiom emerges. Date/Author: 2026-06-12, planning agent.

- Decision: discover docstrings by a manual depth-first walk with an owner stack
  rather than tree-sitter S-expression queries. Rationale: owner derivation is
  inherently hierarchical and the bounded node store is built in the same
  single pass; a query would still need a second traversal to recover
  `<locals>` context, adding work without reducing coupling. Date/Author:
  2026-06-12, planning agent (community-of-experts review).

- Decision: `ExtractError::PythonIr` wraps the small fieldless
  `PythonExtractError`; recoverable diagnostics live in `IrError`. Rationale:
  keeps the bridged error type tiny so the existing 128-byte `ExtractError`
  size assertion holds without a deliberate budget raise. Date/Author:
  2026-06-12, planning agent (community-of-experts review).

- Decision: `IrOwner` `name`/`qualname` `None` serialises as JSON `null` (the
  fields have no `skip_serializing_if`), so module owners emit
  `"name": null, "qualname": null`. Module owners stay anonymous in v1 because
  string-only extraction has no package context; a package-qualified module
  owner is reserved as a future migration recorded in ADR 005. Date/Author:
  2026-06-12, planning agent (community-of-experts review).

- Decision: the Python hypothesis test keeps the source shape fixed
  (`def {name}(): """{body}"""`) and varies only the identifier and prose;
  structural coverage comes from fixed parametrized rstest cases. Rationale:
  generating arbitrary valid Python with hypothesis adds flakiness without
  finding real owner-derivation bugs. Date/Author: 2026-06-12, planning agent
  (community-of-experts review).

- Decision: mark this execplan `IN PROGRESS` and begin implementation.
  Rationale: the user explicitly approved implementation on 2026-06-15 by
  requesting that the planned functionality be implemented from this file.
  Date/Author: 2026-06-15, implementation agent.

- Decision: include the PyO3 bridge and typed Python facade support in Stage 2
  rather than leaving them to Stage 5. Rationale: once
  `ExtractSyntax::PythonDocstring` dispatch returns an implemented document,
  the bridge and facade already expose it; keeping tests and docs in an
  unsupported state would contradict the shipped API. Date/Author: 2026-06-15,
  implementation agent.

## Outcomes & Retrospective

Roadmap item 3.1.1 is complete. The implementation delivers owner-aware Python
docstring extraction for modules, classes, functions, nested declarations,
decorated definitions, and malformed-input recovery without disturbing the
Markdown extraction path or the IR domain contract.

The final behaviour is backed by Rust unit and integration coverage, Python
adapter tests, rstest-bdd scenarios, property tests for Python owner qualified
names, canonical Rust and Python snapshots, and documentation updates. ADR 005
records the owner metadata decision: Python docstring regions expose explicit
`owner` metadata, use Python `__qualname__` semantics for class and function
owners, keep module owners anonymous in v1, and preserve verbatim
`string_content` spans rather than decoding or cleaning docstring text during
extraction.

The completed validation suite passed `make fmt`, `make markdownlint`,
`make nixie`, `make check-fmt`, `make typecheck`, `make lint`, and `make test`.
CodeRabbit completed the final review with zero findings. The branch was pushed
to `origin/3-1-1-python-docstring-extraction`.

## Revision note

Initial draft created on 2026-06-12. Implementation was approved and completed
on branch `3-1-1-python-docstring-extraction`, with roadmap item 3.1.1 marked
complete after the code, tests, documentation, deterministic gates, and
CodeRabbit review all passed.
