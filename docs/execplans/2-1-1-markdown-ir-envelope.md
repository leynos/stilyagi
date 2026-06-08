# Implement the Markdown IR envelope

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
`Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`, `Decision Log`,
and `Outcomes & Retrospective` must be kept up to date as work proceeds.

Status: DONE

Approval gate: the user approved implementation on 2026-06-01 by asking to
proceed with the planned functionality. Milestone work proceeds within the
tolerances below.

Hardening note: the IR envelope is syntax-neutral. `DocumentMetadata::new(...)`
constructs metadata for any syntax string, `DocumentMetadata::markdown(...)`
delegates to that neutral constructor, and Markdown production uses an
`IrBuildContext` at the envelope boundary. Markdown remains the only
implemented IR producer in this slice; Python docstring and Rust documentation
comment extraction continue to return unsupported-syntax errors rather than
placeholder IR.

## Purpose / big picture

Roadmap item 2.1.1 proves that Markdown can be flattened into Stilyagi's
source-faithful intermediate representation (IR). After the approved
implementation, a maintainer should be able to run the existing extraction path
on representative Markdown fixtures and inspect canonical IR JSON that contains
a full document envelope, a byte-oriented `line_index`, content hashes,
Markdown structural nodes, lintable regions, and `segments` mappings from
flattened prose back to source bytes.

The observable success condition is not merely "the code compiles". The shared
Markdown fixture must round-trip through canonical JSON snapshots without span
drift, and invariant tests must prove that every region's `segments`
reconstruct its `text` exactly while distinguishing source-backed content from
synthetic insertions such as spaces introduced for soft line breaks.

This is the first implementation slice that turns Stilyagi's earlier scaffold
into a useful, inspectable extraction contract. It does not implement Markdown
lint rules, suppression parsing, safe fix planning, or the public `dump-ir`
command; those are later roadmap items. It does, however, supply the IR facts
those later items must trust.

## Context and orientation

The repository is a mixed Rust and Python project. Rust crates live under
`crates/`, Python package code lives under `python/stilyagi/`, Python tests
live under `tests/`, shared corpus fixtures live under
`tests/fixtures/corpus/`, and behaviour-driven development (BDD) feature files
live under `features/`.

The relevant Rust crates are:

- `crates/stilyagi-ir/`, which currently owns the small IR boundary marker,
  canonical JSON helper module, and line-index helper added by earlier roadmap
  work.
- `crates/stilyagi-markdown/`, which is currently a Markdown boundary marker
  and should become the Markdown-specific parsing and flattening adapter.
- `crates/stilyagi-extract/`, which owns `ExtractSyntax`, `RegionKind`,
  `ExtractRegion`, `ExtractDocument`, `ExtractError`, `ExtractBoundary`, and
  `extract_document`.
- `crates/stilyagi-pyext/`, which exposes the PyO3 bridge consumed by Python.
- `crates/stilyagi-test-support/`, which provides repository fixture access,
  golden IR scaffolding, and edit round-trip helpers for tests.

The relevant Python modules are:

- `python/stilyagi/engine/extraction.py`, which adapts the raw bridge payload.
- `python/stilyagi/model/document.py`, which currently exposes a minimal
  `Document`.
- `python/stilyagi/model/region.py`, which currently exposes a minimal
  `Region`.
- `python/stilyagi/_stilyagi_rs.pyi`, which mirrors the extension payload for
  type checking.
- `tests/support/golden_ir.py`, which has a private Python-side golden IR
  shape that must not drift away from the Rust test-support shape.

The current extraction contract is deliberately narrow. Markdown extraction
currently yields a document-shaped result containing `syntax` and regions with
`kind` and `text`. Earlier documentation records that it does not yet expose
the full IR shape with `line_index`, `segments`, owner metadata, structural
nodes, parse errors, or canonical IR JSON. This plan fills that Markdown-first
gap.

Definitions used in this plan:

- IR means intermediate representation: Stilyagi's stable logical payload for
  source structure, lintable prose regions, source positions, and debug output.
- Canonical JSON means the deterministic JSON form used by snapshots,
  compatibility review, and future `dump-ir` output.
- `line_index` means a list of UTF-8 byte offsets for every line start in the
  source document.
- Region means a lintable prose surface such as a heading, paragraph,
  list item, table cell, image alternative text, or link title.
- Segment means a mapping from a span of region text to either original source
  bytes or an explicit synthetic insertion.
- Synthetic insertion means text that exists in the flattened lint surface but
  was not present as editable bytes in the source file.
- Span drift means any mismatch between a reported source offset and the bytes
  that actually produced the corresponding region text.

## Documentation and skill signposts

Before implementing this plan, load and apply these skills:

- `leta`, for symbol-aware Rust and Python navigation.
- `rust-router`, then `arch-crate-design`, because this change affects Rust
  crate boundaries and public versus internal interfaces.
- `hexagonal-architecture`, to preserve the boundary between domain IR types,
  Markdown adapter code, PyO3 transport, and Python application models.
- `rust-types-and-apis`, if the IR envelope, region, segment, span, node, or
  producer types need public or crate-facing API decisions.
- `rust-errors`, if parser or serialization errors need new reusable error
  variants.
- `rust-performance-and-layout`, only if the implementation starts making
  allocation or hot-path performance claims.
- `nextest`, if targeted Rust test execution uses `cargo nextest`.
- `commit-message`, for every commit; commit messages must be written to a
  temporary file and applied with `git commit -F`.
- `pr-creation` and `en-gb-oxendict-style`, for the draft pull request.

Keep these repository documents open:

- [docs/roadmap.md](../roadmap.md), especially item 2.1.1 and its
  dependencies on 1.1.3, 1.2.2, and 1.3.1.
- [docs/stilyagi-design.md](../stilyagi-design.md), especially sections 6,
  7.1, 10 and 11.
- [docs/rfcs/0001-stilyagi-intermediate-representation.md](
  ../rfcs/0001-stilyagi-intermediate-representation.md), especially sections 4
  through 10.
- [docs/complexity-antipatterns-and-refactoring-strategies.md](
  ../complexity-antipatterns-and-refactoring-strategies.md), for keeping the
  flattening and mapping logic small enough to review.
- [docs/rust-testing-with-rstest-fixtures.md](
  ../rust-testing-with-rstest-fixtures.md), for Rust fixture style.
- [docs/rust-doctest-dry-guide.md](../rust-doctest-dry-guide.md), if any new
  Rust type documentation includes examples.
- [docs/reliable-testing-in-rust-via-dependency-injection.md](
  ../reliable-testing-in-rust-via-dependency-injection.md), for explicit,
  deterministic IO boundaries.
- [docs/rstest-bdd-users-guide.md](../rstest-bdd-users-guide.md), for Rust
  BDD behaviour tests.
- [docs/developers-guide.md](../developers-guide.md), for maintainer-facing
  testing, fixture, and API conventions.
- [docs/users-guide.md](../users-guide.md), for any externally visible bridge
  or model behaviour that consumers should know about.

External prior art checked during planning:

- `markdown-rs` exposes `to_mdast()` and has a `serde` feature for abstract
  syntax tree and configuration serialization. This matches the design's
  preferred Markdown parser and supports a Rust-first mdast-shaped path.
  Reference: <https://docs.rs/markdown/>.
- mdast is the established Markdown Abstract Syntax Tree vocabulary and covers
  headings, lists, blockquotes, links, images, tables, frontmatter, inline
  code, and other Markdown structures that later roadmap items must exercise.
  Reference: <https://github.com/syntax-tree/mdast>.
- unist defines source positions, generated nodes, JSON-expressible syntax
  trees, and the distinction between syntax-tree structure and source file
  positions. Its offset model is character-oriented, so Stilyagi must keep its
  own UTF-8 byte offsets as the canonical source coordinates. Reference:
  <https://github.com/syntax-tree/unist>.

## Constraints

- Do not implement this plan until explicit approval is recorded in this file.
- Preserve roadmap scope. This item implements the Markdown IR envelope,
  `line_index`, region text, `segments`, source-backed positions, synthetic
  insertions, and content hashes. It does not implement item 2.1.2's full
  fixture expansion, item 2.1.3's suppression parsing, item 2.2's CLI loop, or
  item 2.3's builtin rules.
- Keep Markdown first. Do not claim Python docstring or Rust documentation
  comment extraction support as part of this slice.
- Keep full non-Markdown structural trees internal or absent. RFC 0001 allows
  future tree-sitter-backed debug output, but v1's stable full-node public
  surface is Markdown-only.
- Do not let the Python bridge become the domain model. The Rust IR schema must
  own logical IR types; PyO3 serialization and Python model adaptation are
  adapters around that model.
- Keep source offsets byte-oriented. Any line and column fields are derived
  from `line_index` and must not replace byte offsets as the ground truth.
- Canonical JSON snapshots must avoid machine-specific absolute paths,
  timestamps, nondeterministic ordering, terminal colour, and environment
  values.
- Region `segments` must reconstruct `text` exactly. If the implementation
  cannot prove this for a region kind, that region kind must remain out of
  scope until a later approved change.
- Fix planning must not be implemented here, but the segment shape must
  preserve enough information for later code to reject edits against synthetic
  spans.
- Use `rstest` for Rust unit tests, `rstest-bdd` for Rust behaviour tests,
  `insta` for Rust snapshots, `pytest` for Python unit tests, `pytest-bdd` for
  Python behaviour tests where externally observable behaviour is involved, and
  `syrupy` for Python snapshots.
- Use `proptest` for Rust segment and span invariants introduced by this
  change. If property tests prove too expensive or imprecise, stop and record
  the reason before substituting examples only.
- Treat the alternative
  `2-1-1-markdown-ir-envelope-and-mappings` plan as follow-up hardening input,
  not as a retroactive expansion of this completed slice. Its recommended CRLF,
  frontmatter, inline-markup, bridge-parity, parser-panic, and error-size
  checks are valuable, but any unimplemented item must be tracked as a later
  hardening or 2.1.2 task rather than silently changing the acceptance bar for
  this branch.
- Do not add Kani, CrossHair, or Verus proof work unless the implementation
  introduces a substantive invariant that is better proved than tested.
- Run format, typecheck, lint, and tests sequentially. Capture long command
  output with `tee` into `/tmp` logs. Do not run format, lint, typecheck, or
  tests in parallel.
- Run `coderabbit review --agent` after each major implementation milestone,
  but only after deterministic quality gates for that milestone pass. Resolve
  or explicitly document all actionable concerns before moving on.
- The follow-up hardening recommendations adopted on 2026-06-05 are now in
  scope for implementation at the user's request. Implement them as a focused
  post-2.1.1 hardening stage without broadening into all of roadmap item 2.1.2.
- Commit after each approved, gated major milestone. Do not commit failing
  code. Do not use `git commit -m`.
- On completion of the implemented feature, mark roadmap item 2.1.1 in
  `docs/roadmap.md` as done. Do not mark it done while this plan is still a
  draft or while implementation is incomplete.

## Tolerances

- Scope: if implementation requires changes to more than twenty files or
  roughly 1,200 net new lines excluding snapshots, stop and ask for approval to
  continue.
- Public API: if a supported Python API or public Rust API must be removed or
  renamed rather than extended compatibly, stop and present options.
- Dependency scope: adding the Rust crates `markdown`, `serde`, `serde_json`,
  `sha2`, and `proptest` is expected for this slice if they are not already
  present. Any other new external dependency requires approval.
- Parser scope: if `markdown-rs` cannot produce the required positions for the
  representative fixture without a second parser or a custom lexer, stop and
  document alternatives.
- Region scope: start with the region kinds needed by the existing
  representative Markdown fixture plus synthetic soft-break coverage. If
  tables, frontmatter, blockquotes, or malformed Markdown require broad parser
  work beyond the envelope contract, defer that breadth to item 2.1.2 unless
  approval is given to expand 2.1.1.
- Bridge scope: expose enough IR fields through PyO3 and Python models to keep
  the existing extraction contract coherent. If this requires a public
  `dump-ir` command, stop; `dump-ir` belongs to item 2.2.3.
- Test attempts: if the same deterministic gate fails three times after a
  plausible fix, stop and record the failure with the relevant log path.
- Performance: if warm extraction of the shared Markdown fixture becomes
  visibly slow enough to make `make test` more than 20 seconds slower on this
  machine, document the cause and ask whether to narrow or defer the expensive
  check.
- Ambiguity: if two valid interpretations of RFC 0001 would produce different
  JSON shapes, stop and record the options before choosing.

## Risks

- Risk: `markdown-rs` positions may not directly map every flattened prose
  fragment to the exact source byte range Stilyagi needs. Severity: high.
  Likelihood: medium. Mitigation: start with a parser spike against the shared
  fixture and a soft-break fixture before committing to type shapes; keep byte
  offsets canonical and derive other coordinates from `line_index`.

- Risk: segment reconstruction can drift around inline markup, links, emphasis,
  code spans, blockquote markers, table separators, or soft line breaks.
  Severity: high. Likelihood: high. Mitigation: implement the flattener as a
  small, tested state machine over mdast nodes; add example tests and
  `proptest` invariants that reconstruct region text from segments.

- Risk: CRLF line endings can break soft-break span mapping if text splitting
  treats `\n` as the only line terminator while the source bytes contain
  `\r\n`. Severity: high. Likelihood: medium. Mitigation: add a CRLF-preserving
  Markdown fixture protected by a scoped `.gitattributes` entry, assert the
  fixture still contains literal CRLF bytes on checkout, and include that
  fixture in segment reconstruction tests before broadening Markdown mapping
  coverage.

- Risk: the current fixture corpus proves the first envelope but does not cover
  every shape needed to trust later Markdown mappings. Severity: medium.
  Likelihood: high. Mitigation: add paragraph-with-inline-markup,
  paragraph-with-soft-break, CRLF soft-break, and YAML frontmatter fixtures in
  the next hardening pass or in roadmap item 2.1.2, then snapshot each shape
  with source-backed and synthetic segment assertions.

- Risk: widening the PyO3 payload breaks the existing Python extraction tests
  or exposes raw transport details as public API. Severity: medium. Likelihood:
  medium. Mitigation: keep the old minimal fields available where practical,
  add new typed model fields compatibly, update `_stilyagi_rs.pyi`, and test
  through `python/stilyagi/engine/extraction.py` rather than raw dict internals
  alone.

- Risk: bridge parity can become self-referential if the bridge returns a
  canonical JSON string and the Python side merely compares that field to
  itself. Severity: medium. Likelihood: medium. Mitigation: if Python gains a
  first-class IR model serializer, compare Python-produced canonical JSON
  against Rust canonical JSON or a reviewed Rust snapshot for the same source.
  Keep the PyO3 dictionary documented as an internal transport mirror rather
  than a public contract.

- Risk: Rust and Python golden IR helpers drift into two subtly different
  contracts. Severity: medium. Likelihood: high. Mitigation: make Rust
  canonical JSON the source of truth, then update Python helpers to compare the
  same normalized field names and ordering.

- Risk: Markdown parser panics or large error variants can cross boundaries in
  surprising ways as the extractor grows. Severity: medium. Likelihood: medium.
  Mitigation: before adding richer Markdown error payloads, wrap the parser
  boundary in `catch_unwind` or document the equivalent panic boundary, map
  fatal parser failures to `ExtractError`, and pin `ExtractError` size with a
  compile-time assertion so `result_large_err` is caught deliberately.

- Risk: this slice grows into all of item 2.1.2 by trying to cover every
  Markdown construct in one pass. Severity: medium. Likelihood: medium.
  Mitigation: make envelope correctness the milestone objective and defer
  fixture breadth unless it is needed to prove the envelope can represent the
  required kinds.

- Risk: content hashes differ across platforms because of path, newline, or
  encoding assumptions. Severity: medium. Likelihood: low. Mitigation: hash
  source bytes only, include the `sha256:` prefix required by RFC 0001, and
  test fixtures as checked-in UTF-8 text.

- Risk: canonical JSON field ordering changes frequently as the schema settles.
  Severity: low. Likelihood: medium. Mitigation: centralize canonical
  serialization in `stilyagi-ir`, snapshot the output, and update snapshots
  only after reviewing the logical contract.

## Plan of work

### Stage 0: approval and baseline

This stage must not begin until explicit user approval is recorded. After
approval, `Status` changes to `APPROVED`, the approval is recorded in the
`Decision Log`, and `Status` changes to `IN PROGRESS` when implementation
starts.

The branch and working tree are checked with `git branch --show-current` and
`git status --short --branch`. The expected branch is
`2-1-1-markdown-ir-envelope`. If the branch is not the task branch, work stops
until branch naming is confirmed. Unrelated user changes remain in place and
are worked around.

A baseline gate runs before code changes so later failures have a comparison
point. The project Makefile targets are used with `tee` logs:

```bash
BRANCH="$(git branch --show-current)"
make check-fmt 2>&1 | tee "/tmp/check-fmt-stilyagi-${BRANCH}.out"
make typecheck 2>&1 | tee "/tmp/typecheck-stilyagi-${BRANCH}.out"
make lint 2>&1 | tee "/tmp/lint-stilyagi-${BRANCH}.out"
make test 2>&1 | tee "/tmp/test-stilyagi-${BRANCH}.out"
```

If any baseline gate fails before implementation, the log is inspected to
determine whether the failure is caused by the clean branch, local environment,
or pre-existing unrelated changes. The finding is recorded in
`Surprises & Discoveries`, and work stops if the failure would make this plan
unverifiable.

### Stage 1: parser and schema spike

The smallest parser integration needed to prove the source-position path is
added. The expected direction is to add the `markdown` crate with the `serde`
feature to `crates/stilyagi-markdown/Cargo.toml` or the narrow crate that owns
parsing. Markdown-specific code remains in
`crates/stilyagi-markdown/src/lib.rs` or a small module under that crate.
Markdown parser traversal is not placed inside PyO3 or Python model code.

In `crates/stilyagi-ir/`, define the logical IR data types needed by RFC 0001:
document metadata, producer metadata, line index, tree metadata, nodes, spans,
region records, segment records, source segment ranges, suppressions, errors,
and metadata. Named structs and enums are preferred over freeform maps where
the contract is known. Extensible maps remain limited to `metadata`, `attrs`,
and future parser-specific properties.

The first concrete type surface should include names equivalent to:

```rust
pub struct IrDocument {
    pub schema_version: String,
    pub document: SourceDocument,
    pub producers: Vec<Producer>,
    pub line_index: Vec<usize>,
    pub trees: Vec<IrTree>,
    pub nodes: Vec<IrNode>,
    pub regions: Vec<IrRegion>,
    pub suppressions: Vec<IrSuppression>,
    pub errors: Vec<IrError>,
    pub metadata: BTreeMap<String, JsonValue>,
}
```

The exact names are used only if they fit the existing code. The important
contract is that the type belongs to `stilyagi-ir`, and extraction, PyO3, and
Python adapt around it.

Unit tests are added in `crates/stilyagi-ir/` for `line_index`, content hash
formatting, canonical JSON ordering, and segment reconstruction helpers. A
targeted parser spike test in `crates/stilyagi-markdown/` or
`crates/stilyagi-extract/` that parses the shared Markdown fixture and confirms
that positions are present for the root and at least one heading or paragraph
node is added.

The targeted Rust tests run first:

```bash
cargo test -p stilyagi-ir -p stilyagi-markdown 2>&1 \
  | tee "/tmp/test-ir-markdown-stilyagi-${BRANCH}.out"
```

If the parser cannot provide usable offsets for the representative fixture,
stop here and record alternatives in `Decision Log`.

### Stage 2: Markdown flattening and IR envelope

The Markdown IR builder is implemented in `crates/stilyagi-markdown/`. It
should take source text plus source identity and produce Markdown-specific
structural facts: an mdast-shaped tree, stable node identifiers, source-backed
spans, and region candidates. The builder remains deterministic: traversal
order, generated IDs, and JSON output must not depend on hash-map ordering.

Region flattening is implemented for the minimum Markdown region kinds needed
to prove the envelope:

- `heading`
- `paragraph`
- `list_item`, if the shared fixture or tests need list coverage
- `table_cell`, if the shared fixture's table is included in the first
  snapshot
- `image_alt` and `link_title`, where their source mapping can be made
  trustworthy

For each emitted region, `kind`, `scope`, `syntax`, `natural_language` when
known, `text`, `segments`, `origin_nodes`, `owner`, `attrs`, and
`parent_region` are populated. `owner` must be `null` for Markdown regions and
is not overloaded with section context.

Synthetic insertions are represented explicitly. A soft line break that becomes
a space in region text should create a segment with `source: null` and a stable
synthetic reason such as `softbreak_space`. The surrounding source-backed
segments must retain their original byte ranges.

`crates/stilyagi-extract/src/lib.rs` is updated so `extract_document` delegates
Markdown work to the Markdown builder and returns or wraps the richer IR
document. Unsupported syntax errors for Python and Rust remain exactly
explicit; empty IR is not silently returned for unsupported extractors.

Rust unit tests with `rstest` cover source-backed regions and synthetic
segments. `proptest` coverage is added for the invariant that reconstructing a
region from its segments yields exactly the region text for generated simple
segment sequences, and that invalid source ranges cannot be constructed if the
API is designed to prevent them.

The targeted extraction tests run:

```bash
cargo test -p stilyagi-ir -p stilyagi-markdown -p stilyagi-extract 2>&1 \
  | tee "/tmp/test-extract-ir-stilyagi-${BRANCH}.out"
```

Then run the full deterministic milestone gates:

```bash
make check-fmt 2>&1 | tee "/tmp/check-fmt-stage2-stilyagi-${BRANCH}.out"
make typecheck 2>&1 | tee "/tmp/typecheck-stage2-stilyagi-${BRANCH}.out"
make lint 2>&1 | tee "/tmp/lint-stage2-stilyagi-${BRANCH}.out"
make test 2>&1 | tee "/tmp/test-stage2-stilyagi-${BRANCH}.out"
```

After these gates pass, `coderabbit review --agent` runs and all actionable
concerns are addressed. The milestone is committed with a focused message.

### Stage 3: canonical JSON and golden fixtures

Canonical serialization moves into `crates/stilyagi-ir/src/canonical_json.rs`
if it is not already there. The serializer must produce deterministic JSON for
`IrDocument` and related types. Structured serialization is preferred over
handwritten string concatenation.

`crates/stilyagi-test-support/src/golden_ir.rs` and
`crates/stilyagi-test-support/src/golden_fixture_builder.rs` so they build the
same logical envelope that production extraction emits. The test support layer
may add fixture conveniences, but it must not invent a second IR schema.

Rust snapshots are updated under:

- `crates/stilyagi-extract/tests/snapshots/`
- `crates/stilyagi-test-support/tests/snapshots/`

Python golden snapshot support is updated under:

- `tests/support/golden_ir.py`
- `tests/__snapshots__/test_round_trip_helpers/`

Snapshot tests prove that the shared Markdown fixture's canonical JSON includes
document metadata, `content_hash`, `line_index`, Markdown tree metadata, region
text, source-backed segments, and any synthetic segments included by the
fixture.

Use `insta` and `syrupy` update modes only after reviewing the diff:

```bash
INSTA_UPDATE=always cargo test -p stilyagi-extract -p stilyagi-test-support
.venv/bin/python -m pytest tests/test_round_trip_helpers.py --snapshot-update
```

The same tests then run without update flags to prove the snapshots are stable.
Full gates and `coderabbit review --agent` run, concerns are resolved, and the
milestone is committed.

### Stage 4: PyO3 bridge and Python model adaptation

`crates/stilyagi-pyext/src/lib.rs` is updated so `extract_document` exposes the
new logical envelope through a Python dictionary that preserves the canonical
field names. The adapter remains small. Markdown flattening and canonical JSON
construction are not duplicated in PyO3.

`python/stilyagi/_stilyagi_rs.pyi` is updated to describe the richer bridge
payload. `python/stilyagi/engine/extraction.py` is updated so it validates the
new shape and adapts it into Python models. `python/stilyagi/model/document.py`
and `python/stilyagi/model/region.py` with typed fields for `line_index`,
document metadata, regions, and segments if those fields become part of the
supported Python surface.

Compatibility is preferred. Existing callers that inspect `Document.syntax` and
`Region.kind` / `Region.text` should keep working unless the user approves a
breaking change.

Python tests are added for bridge adaptation and model validation. `pytest` is
used for unit tests and existing `pytest-bdd` patterns only if an externally
observable behaviour needs a Gherkin scenario. `syrupy` snapshots are added
where output shape stability matters.

The bridge adaptation tests run:

```bash
make build 2>&1 | tee "/tmp/build-stage4-stilyagi-${BRANCH}.out"
.venv/bin/python -m pytest -q \
  tests/test_round_trip_helpers.py \
  tests/test_package_skeleton_units.py \
  tests/test_package_structure_bdd.py \
  2>&1 | tee "/tmp/pytest-stage4-stilyagi-${BRANCH}.out"
```

Full gates and `coderabbit review --agent` then run, concerns are resolved, and
the milestone is committed.

### Stage 5: documentation and roadmap completion

`docs/developers-guide.md` is updated to document the new internal IR envelope,
the Markdown flattening boundary, segment invariants, canonical JSON workflow,
and how Rust and Python golden fixtures stay aligned. `docs/users-guide.md` is
updated only for consumer-visible changes, such as richer fields on the
supported Python `Document` or `Region` model.

`docs/stilyagi-design.md` is updated only if implementation resolves an
ambiguity or changed the design. RFC 0001 is updated only if the accepted
contract needs a substantive field-level correction. If no design or RFC change
is needed, that decision is recorded in this plan instead of editing those
files.

After all implementation and documentation gates pass, roadmap item 2.1.1 is
marked as done in `docs/roadmap.md`. Items 2.1.2 and 2.1.3 are not marked done.

For Markdown documentation changes, these commands run:

```bash
make fmt 2>&1 | tee "/tmp/fmt-docs-stage5-stilyagi-${BRANCH}.out"
make markdownlint 2>&1 | tee "/tmp/markdownlint-stage5-stilyagi-${BRANCH}.out"
make nixie 2>&1 | tee "/tmp/nixie-stage5-stilyagi-${BRANCH}.out"
```

The required full gates then run:

```bash
make check-fmt 2>&1 | tee "/tmp/check-fmt-stage5-stilyagi-${BRANCH}.out"
make typecheck 2>&1 | tee "/tmp/typecheck-stage5-stilyagi-${BRANCH}.out"
make lint 2>&1 | tee "/tmp/lint-stage5-stilyagi-${BRANCH}.out"
make test 2>&1 | tee "/tmp/test-stage5-stilyagi-${BRANCH}.out"
```

`coderabbit review --agent` runs, concerns are cleared, and the final feature
commit is made.

### Stage 6: follow-up mapping hardening

The user requested implementation of the follow-up recommendations that were
added from the alternative envelope-and-mappings plan. Treat this as a focused
hardening stage over the completed 2.1.1 slice, not as a blanket implementation
of roadmap item 2.1.2.

Representative Markdown fixtures are added for paragraph inline markup, soft
line breaks, CRLF soft line breaks, and YAML frontmatter. The CRLF fixture is
protected with a scoped `.gitattributes` rule, and a test reads the checked-out
fixture bytes and asserts that literal `\r\n` pairs are present. Snapshot or
otherwise assert each fixture's canonical IR so reviewers can see region text,
source-backed spans, and synthetic break segments.

Rust property tests around segment invariants are strengthened. Generated
segment layouts must prove contiguous `text_start` and `text_end` ranges, exact
region-text reconstruction, source-backed segment text agreement with original
source bytes where a source oracle is present, and the closed set of supported
synthetic break reasons. Strategies that construct valid layouts are preferred
directly rather than filtering invalid generated data.

Parser boundary tests and implementation are added for fatal Markdown parser
failures or panics so panics do not cross the extraction boundary. If
`markdown-rs` exposes only infallible parsing for the currently used path, the
parser call is wrapped in a narrow `catch_unwind` boundary and unwinds are
mapped to the existing Markdown error type.

An explicit `ExtractError` size assertion is added before richer owned error
payloads are introduced. This assertion documents the current
`result_large_err` budget and gives future changes a clear failure when the
error type becomes too large.

For Python parity, only the non-self-referential check supported by the current
surface is added: the Python `Document.ir` model parsed from the bridge must
match the canonical Rust IR snapshot for the same fixture after the same stable
normalization. The bridge raw `ir_json` string is not compared to itself.

Targeted tests for changed crates and Python modules run first. Then the
required full gates run:

```bash
make check-fmt 2>&1 | tee "/tmp/check-fmt-stage6-stilyagi-${BRANCH}.out"
make typecheck 2>&1 | tee "/tmp/typecheck-stage6-stilyagi-${BRANCH}.out"
make lint 2>&1 | tee "/tmp/lint-stage6-stilyagi-${BRANCH}.out"
make test 2>&1 | tee "/tmp/test-stage6-stilyagi-${BRANCH}.out"
```

After deterministic gates pass, `coderabbit review --agent` runs. If CodeRabbit
is rate-limited, `vsleep "$(shuf -i 15-30 -n 1)m"` is used before retry.
Actionable concerns are resolved before the hardening milestone is committed.

## Concrete steps

All commands in this section run from the repository root. If a shell variable
is useful, set it to the current checkout rather than to a machine-specific
absolute path:

```bash
REPO_ROOT="$(pwd)"
cd "$REPO_ROOT"
```

The `leta` workspace is created or refreshed before code navigation:

```bash
leta workspace add "$REPO_ROOT"
```

Symbols are inspected with `leta` rather than broad text search when a symbol
name is known:

```bash
leta grep "ExtractDocument|ExtractRegion|RegionKind|IrDocument" -k struct,enum
leta show extract_document
leta refs ExtractDocument
```

`rg` is used only for Markdown prose, configuration keys, snapshots, or other
non-symbol text:

```bash
rg -n "line_index|segments|content_hash|dump-ir" docs tests crates
```

Implementation milestones run in the order described in `Plan of work`. After
each milestone, changed files are inspected:

```bash
git status --short
git diff --stat
git diff -- docs/execplans/2-1-1-markdown-ir-envelope.md
```

File-based commit messages are used:

```bash
COMMIT_MSG_DIR="$(mktemp -d)"
cat > "$COMMIT_MSG_DIR/COMMIT_MSG.md" << 'ENDOFMSG'
Implement Markdown IR envelope

Add the Markdown-first IR envelope, source-backed region segments,
canonical JSON coverage, and bridge adaptation required by roadmap item
2.1.1.
ENDOFMSG
git commit -F "$COMMIT_MSG_DIR/COMMIT_MSG.md"
rm -rf "$COMMIT_MSG_DIR"
```

Each actual milestone commit uses a more specific subject. The example is a
shape, not a required final message.

## Validation and acceptance

Acceptance for the implemented feature:

- Running Markdown extraction on the shared valid fixture produces an IR
  document with `schema_version`, `document`, `producers`, `line_index`,
  `trees`, `nodes`, `regions`, `suppressions`, `errors`, and `metadata`.
- `document.syntax` is `markdown`, `document.encoding` is `utf-8`, and
  `document.content_hash` is a stable `sha256:` hash of the source bytes.
- `line_index` is a monotonically increasing list of UTF-8 byte offsets for
  line starts.
- Markdown structural nodes preserve mdast-like kind names where practical and
  carry source-backed spans when the parser provides positions.
- Each emitted region has text, origin nodes, and `segments`; reconstructing
  text from `segments` exactly matches the stored region text.
- Synthetic insertions are explicit and never masquerade as source-backed
  bytes.
- Canonical JSON snapshots for representative Markdown fixtures are stable
  across repeated test runs.
- The Python bridge still supports the existing extraction call path and now
  exposes the richer IR fields through typed Python adaptation where approved.
- Unsupported Python and Rust extraction remain explicit unsupported-syntax
  paths unless later roadmap work implements them.
- `docs/developers-guide.md` documents internal IR and segment conventions.
- `docs/users-guide.md` is updated if the supported Python surface changes.
- `docs/roadmap.md` marks only item 2.1.1 done after implementation is
  complete.

Required gates after each major milestone:

```bash
make check-fmt
make typecheck
make lint
make test
```

Required documentation gates after Markdown documentation changes:

```bash
make fmt
make markdownlint
make nixie
```

All long gate runs must be captured with `tee` into `/tmp` logs. If a gate
fails, read the log before retrying.

CodeRabbit validation is required after deterministic gates pass for each major
milestone:

```bash
coderabbit review --agent
```

CodeRabbit is not used to find deterministic format, lint, type, or test
failures that local gates can catch.

Recommended follow-up tests adopted from the alternative envelope-and-mappings
plan:

- Dedicated Markdown fixtures cover paragraph emphasis, paragraph soft
  breaks, CRLF soft breaks, and YAML frontmatter before broader Markdown
  mapping coverage.
- Any CRLF fixture is protected with a scoped `.gitattributes` rule and covered
  by a test that verifies the checked-out fixture still contains literal `\r\n`
  bytes.
- Extend the Rust `proptest` coverage so generated segment layouts assert
  contiguous `text_start`/`text_end` ranges, exact region-text reconstruction,
  source-backed segment text matching the original source bytes, and closed-set
  synthetic segment kinds for soft and hard breaks.
- Explicit tests cover fatal Markdown parser failures and parser panic
  containment before richer parse-error recovery is exposed.
- If Python gains typed IR objects or a serializer, add a canonical JSON parity
  test that compares Python-produced JSON with Rust-produced canonical JSON for
  the same fixture. The bridge-provided JSON string is not compared to itself.
- Before adding owned payloads to extractor errors, add a compile-time size
  assertion for `ExtractError` so the workspace `result_large_err` budget is
  explicit.

## Idempotence and recovery

Most steps are additive and can be rerun safely. Re-running tests, snapshot
verification, `make check-fmt`, `make typecheck`, `make lint`, and `make test`
is safe.

Snapshot update commands are safe only after the implementation diff has been
reviewed. If a snapshot update captures unintended field churn, revert only the
snapshot changes made in that milestone and fix the serializer or builder
before updating again.

If a new parser dependency causes build or licensing problems, remove the
dependency changes from the current milestone, record the blocker in
`Decision Log`, and stop for approval. The parser is not replaced with an ad
hoc Markdown scanner without explicit approval.

If a gate fails because of unrelated user changes, those changes are not
reverted. The failure is recorded and either worked around or escalated if it
blocks verification.

When a branch requires resetting for local experimentation, avoid destructive
Git commands; prefer new commits, targeted patches, or a separate scratch
branch, and request approval before performing any operation that would discard
user work.

## Interfaces and dependencies

The domain IR surface should live in `crates/stilyagi-ir`. Expected logical
types include:

```rust
pub struct SourceSpan {
    pub byte_start: usize,
    pub byte_end: usize,
    pub line_start: usize,
    pub column_start: usize,
    pub line_end: usize,
    pub column_end: usize,
}

pub struct RegionSegment {
    pub text_start: usize,
    pub text_end: usize,
    pub source: Option<SourceByteRange>,
    pub synthetic: Option<SyntheticKind>,
    pub node: Option<String>,
}

pub struct IrRegion {
    pub id: String,
    pub kind: RegionKind,
    pub scope: Vec<String>,
    pub syntax: String,
    pub natural_language: Option<String>,
    pub text: String,
    pub segments: Vec<RegionSegment>,
    pub origin_nodes: Vec<String>,
    pub owner: Option<Owner>,
    pub attrs: BTreeMap<String, JsonValue>,
    pub parent_region: Option<String>,
}
```

The exact names may change during implementation, but the information carried
by these types must remain equivalent to RFC 0001.

The Markdown adapter should live in `crates/stilyagi-markdown` and expose a
small function equivalent to:

```rust
pub fn extract_markdown_ir(input: MarkdownInput<'_>) -> Result<IrDocument, MarkdownError>;
```

`MarkdownInput` should carry source text and source identity, not filesystem IO
unless a later approved adapter needs it. This keeps parsing testable and keeps
IO at the extraction orchestration boundary.

`crates/stilyagi-extract` should orchestrate syntax selection. It may wrap the
IR document in an existing extraction type for compatibility, but it should not
own Markdown flattening internals.

`crates/stilyagi-pyext` should serialize the IR document into Python-native
dicts and lists. It should not compute source spans, flatten Markdown, or
construct canonical JSON independently.

Python model additions should be typed, immutable where practical, and
compatible with current callers. If a Python consumer-facing API needs to
change incompatibly, stop for approval.

## Artifacts and notes

Planning used a Wyvern agent team for read-only reconnaissance. One agent
reviewed roadmap, design, RFC, and execplan style. Another inspected crate and
test layout. Their shared conclusions were:

- The implementation is likely centred on `crates/stilyagi-ir`,
  `crates/stilyagi-markdown`, `crates/stilyagi-extract`,
  `crates/stilyagi-pyext`, Python extraction models, and existing golden IR
  test support.
- The highest-risk area is `segments` correctness around flattened Markdown
  text and synthetic insertions.
- The PyO3 bridge currently exposes only a narrow `{syntax, regions}` payload,
  so bridge widening must be staged and tested.
- Existing Rust and Python golden IR helpers already create drift risk and
  must be aligned with one canonical schema.

Firecrawl was used to check current external tooling and prior art. The useful
findings were:

- `markdown-rs` provides the Rust parser path and `to_mdast()`.
- mdast supplies the Markdown node vocabulary Stilyagi already references.
- unist supplies useful position and generated-node concepts, but Stilyagi
  must retain byte offsets as its own canonical coordinate system.

## Progress

- [x] (2026-05-25T00:46:44Z) Loaded the requested `leta`,
  `hexagonal-architecture`, and `rust-router` skills, plus `execplans`,
  `firecrawl-mcp`, `commit-message`, `pr-creation`, and `en-gb-oxendict-style`
  for this planning and PR workflow.
- [x] (2026-05-25T00:46:44Z) Created the `leta` workspace for the repository.
- [x] (2026-05-25T00:46:44Z) Renamed the local branch to
  `2-1-1-markdown-ir-envelope`.
- [x] (2026-05-25T00:46:44Z) Used two Wyvern agents for read-only planning
  reconnaissance.
- [x] (2026-05-25T00:46:44Z) Used Firecrawl to check `markdown-rs`, mdast, and
  unist prior art.
- [x] (2026-05-25T00:46:44Z) Drafted this pre-implementation ExecPlan.
- [x] (2026-06-01T21:56:54Z) User approved implementation and asked to keep
  this ExecPlan current during work.
- [x] (2026-06-01T21:56:54Z) Ran baseline gates before implementation:
  `make check-fmt`, `make typecheck`, `make lint`, and `make test` all passed.
- [x] (2026-06-01T22:30:00Z) Implemented the Stage 1 parser and schema spike:
  `stilyagi-ir` now owns the first production IR envelope types, content hash
  helper, canonical JSON method, and segment reconstruction invariant tests;
  `stilyagi-markdown` now has a `markdown-rs` parse wrapper and position probe.
- [x] (2026-06-01T22:45:00Z) Gated Stage 1 locally. `make markdownlint`,
  `make nixie`, `make check-fmt`, `make typecheck`, `make lint`, and
  `make test` all passed. The full test gate ran 90 Rust tests and 66 Python
  tests.
- [x] (2026-06-01T22:58:00Z) Ran `coderabbit review --agent` for the Stage 1
  milestone after deterministic gates passed. CodeRabbit completed with zero
  findings.
- [x] (2026-06-01T23:18:00Z) Implemented the Stage 2 Markdown IR builder in
  `stilyagi-markdown`. It now builds a deterministic mdast-backed tree, source
  spans, heading/paragraph/table-cell regions, heading depth attrs,
  source-backed text segments, and synthetic soft-break segments. Targeted
  `cargo test -p stilyagi-markdown` passed.
- [x] (2026-06-01T23:31:00Z) Gated Stage 2 locally. `make markdownlint`,
  `make nixie`, `make check-fmt`, `make typecheck`, `make lint`, and
  `make test` all passed. The full test gate ran 92 Rust tests and 66 Python
  tests.
- [x] (2026-06-02T00:08:00Z) Ran `coderabbit review --agent` for the Stage 2
  milestone. The first attempt hit a recoverable rate limit, so the workflow
  slept for 23 minutes as instructed and retried. The retry completed with zero
  findings.
- [x] (2026-06-02T00:18:00Z) Implemented Stage 3 canonical JSON and golden
  fixture coverage for the internal Markdown IR builder. The shared Markdown
  fixture now has an `insta` snapshot in `stilyagi-markdown`, and the test
  deserializes canonical JSON back into `IrDocument` and verifies all
  source-backed segments match the original source bytes. Targeted
  `cargo test -p stilyagi-markdown` passed with and without snapshot update
  mode.
- [x] (2026-06-02T00:29:00Z) Gated Stage 3 locally. `make markdownlint`,
  `make nixie`, `make check-fmt`, `make typecheck`, `make lint`, and
  `make test` all passed. The full test gate ran 93 Rust tests and 66 Python
  tests.
- [x] (2026-06-02T00:43:00Z) Ran `coderabbit review --agent` for the Stage 3
  milestone after deterministic gates passed. CodeRabbit completed with zero
  findings.
- [x] (2026-06-02T00:55:00Z) Implemented Stage 4 PyO3 bridge and Python model
  adaptation. Markdown extraction now attaches an `IrDocument` to the Rust
  extraction result, the PyO3 bridge exposes it as canonical `ir_json`, and the
  Python adapter parses that into `model.Document.ir` while preserving the
  existing `syntax` and minimal `regions` contract. Targeted
  `cargo test -p stilyagi-extract -p stilyagi-pyext` passed.
- [x] (2026-06-02T01:08:00Z) Gated Stage 4 locally. `make markdownlint`,
  `make nixie`, `make check-fmt`, `make typecheck`, `make lint`, and
  `make test` all passed. The full test gate ran 94 Rust tests and 66 Python
  tests.
- [x] (2026-06-02T01:49:00Z) Ran `coderabbit review --agent` for the Stage 4
  milestone after deterministic gates passed. The first two attempts were
  rate-limited, so the required random 18-minute and 15-minute backoffs were
  observed before retrying. The third attempt completed with zero findings.
- [x] (2026-06-02T01:56:00Z) Drafted Stage 5 documentation and roadmap updates.
  `docs/users-guide.md` now documents `Document.ir` for Markdown,
  `docs/developers-guide.md` and `docs/stilyagi-design.md` record the canonical
  Markdown IR bridge, and `docs/roadmap.md` marks item 2.1.1 done.
- [x] (2026-06-02T02:06:00Z) Gated Stage 5 locally. `make fmt`,
  `make markdownlint`, `make nixie`, `make check-fmt`, `make typecheck`,
  `make lint`, and `make test` all passed. The full test gate ran 94 Rust tests
  and 66 Python tests.
- [x] (2026-06-02T02:19:00Z) Ran `coderabbit review --agent` for the Stage 5
  milestone after deterministic gates passed. CodeRabbit completed with zero
  findings.
- [x] (2026-06-05T00:00:00Z) Reviewed the alternative plan at
  `2-1-1-markdown-ir-envelope-and-mappings` and incorporated its useful
  hardening recommendations into this plan. Accepted improvements cover CRLF
  fixture protection, broader Markdown mapping fixtures, stronger `proptest`
  invariants, Python/Rust canonical JSON parity, Markdown parser panic
  containment, and explicit `ExtractError` size-budget guidance. Broader
  unimplemented API changes from that plan remain deferred rather than
  retroactively changing this branch's completed acceptance criteria.
- [x] (2026-06-05T18:42:42Z) Began Stage 6 after the user explicitly requested
  implementation of the previously recorded follow-up recommendations. The
  stage is scoped to hardening 2.1.1 with fixtures, invariants, parser-boundary
  containment, Python parity, and `ExtractError` size-budget checks.
- [x] (2026-06-05T18:52:00Z) Implemented the Stage 6 hardening changes:
  frontmatter parsing is enabled and recorded in producer metadata; Markdown
  parser panics are contained as parser messages; CRLF-aware flattening keeps
  source byte spans aligned after checked-out CRLF soft breaks; new fixtures
  cover inline markup, LF soft breaks, CRLF soft breaks, and YAML frontmatter;
  `stilyagi-ir` property tests now generate segment layouts and assert
  contiguity, reconstruction, source-byte agreement, and closed synthetic
  reasons; `stilyagi-extract` has an explicit `ExtractError` size budget; and
  Python now compares `Document.ir` against a reviewed Rust snapshot after
  source identity normalization.
- [x] (2026-06-05T18:52:00Z) Targeted Stage 6 validation passed:
  `cargo test -p stilyagi-ir -p stilyagi-markdown -p stilyagi-extract`,
  `make build`, and
  `.venv/bin/python -m pytest -q tests/test_package_skeleton_units.py`.
- [x] (2026-06-05T18:58:02Z) Full deterministic Stage 6 gates passed:
  `make fmt`, `make markdownlint`, `make nixie`, `make check-fmt`,
  `make typecheck`, `make lint`, and `make test`. The full test gate ran 101
  Rust tests and 83 Python tests.
- [x] (2026-06-05T19:10:32Z) Ran `coderabbit review --agent` for the Stage 6
  milestone after deterministic gates passed. CodeRabbit completed with zero
  findings.

## Surprises & Discoveries

- Observation: the repository already contains Rust and Python golden IR
  helpers from roadmap item 1.3.2. Evidence:
  `crates/stilyagi-test-support/src/golden_ir.rs` and
  `tests/support/golden_ir.py` both model snapshot payloads. Impact:
  implementation must avoid creating a third IR shape.

- Observation: the current Markdown extraction path is narrower than the
  target IR by design. Evidence: `crates/stilyagi-extract/src/lib.rs` exposes
  `ExtractDocument` and `ExtractRegion` with `syntax`, `kind`, and `text`,
  while the design says `line_index`, `segments`, owner metadata, and canonical
  IR JSON are not yet exposed. Impact: bridge and model widening are expected
  work, not accidental scope.

- Observation: unist positions are useful prior art but use character-oriented
  offsets, while Stilyagi's RFC requires UTF-8 byte offsets. Evidence: the
  unist specification describes point offsets as character positions and
  Stilyagi RFC 0001 requires byte offsets. Impact: parser positions must be
  normalized into Stilyagi spans rather than copied blindly.

- Observation: the approved branch starts from a healthy baseline. Evidence:
  on 2026-06-01, `make check-fmt`, `make typecheck`, `make lint`, and
  `make test` all passed before implementation. Impact: later failures can be
  attributed to implementation changes unless the environment changes.

- Observation: `markdown-rs` exposes mdast node positions with `start.offset`
  and `end.offset`, and the representative spike confirms positions are present
  for the root, a heading, and a paragraph. Evidence:
  `cargo test -p stilyagi-ir -p stilyagi-markdown` passed after adding the
  parser probe. Impact: Stage 2 can proceed with `markdown-rs`; flattening must
  still normalize and test exact byte spans rather than assume every node end
  offset matches naive fixture slicing.

- Observation: `markdown-rs` with `ParseOptions::gfm()` parses the shared
  table fixture into table-cell mdast nodes and represents Markdown soft line
  breaks in text node values. Evidence: the Stage 2 tests for
  `markdown_ir_document` pass for GFM table cells and a paragraph containing
  `First line\nsecond line`. Impact: the first flattener can cover the
  representative fixture without a second parser, while recording synthetic
  `softbreak_space` segments when prose text replaces a newline with a space.

- Observation: the shared Markdown fixture's canonical IR JSON snapshot is
  stable using repository-relative paths and a synthetic `file:///repo/...`
  URI. Evidence: `INSTA_UPDATE=always cargo test -p stilyagi-markdown`
  generated the snapshot, and a normal `cargo test -p stilyagi-markdown` passed
  immediately afterwards. Impact: Stage 4 can bridge the same Rust IR shape
  without depending on machine-specific snapshot data.

- Observation: the existing Python extraction model can be widened
  compatibly by adding an optional `Document.ir` field. Evidence: targeted Rust
  bridge tests passed after preserving `syntax` and `regions` in the raw
  payload and adding `ir_json` as an extra field. Impact: existing callers can
  continue using the minimal region contract while consumers that need the IR
  can inspect `document.ir`.

- Observation: the alternative envelope-and-mappings plan identifies test
  coverage that is valuable but broader than the completed 2.1.1 branch.
  Evidence: it calls out paragraph-with-inline-markup, soft-break, CRLF
  soft-break, and YAML frontmatter fixtures; a CRLF `.gitattributes` guard;
  `proptest` cases covering emphasis, strong, inline code, links, hard breaks,
  soft breaks, and CRLF; parser panic containment; Python/Rust canonical JSON
  parity; and an explicit `ExtractError` size assertion. Impact: these are now
  recorded as follow-up hardening recommendations for 2.1.2 or a focused
  post-2.1.1 hardening slice rather than silently treated as already complete.

- Observation: `markdown-rs` preserves literal `\r\n` in text node values for
  the CRLF soft-break fixture, rather than normalizing the value to `\n`.
  Evidence: the first Stage 6 hardening fixture test failed because the region
  text still contained `\r` before the flattener learned to treat `\r\n` as one
  soft break. Impact: `FlattenedRegion::push_source_text` now walks parser text
  and original source bytes with separate cursors so LF and CRLF both produce
  one synthetic `softbreak_space` segment without span drift.

- Observation: enabling Markdown frontmatter support changes the canonical
  producer metadata for all Markdown IR snapshots. Evidence: the shared
  Markdown snapshot changed only by adding `"frontmatter": true` under the
  `markdown-rs` producer options, while the new YAML fixture records a `yaml`
  structural node and a paragraph region after the frontmatter. Impact:
  snapshots were updated deliberately after review, and Python parity compares
  against the updated Rust snapshot.

- Observation: the repository Markdown formatter rewrites ordinary `.md`
  fixture paragraphs, including joining soft-break lines. Evidence: the first
  Stage 6 `make fmt` attempt rewrote the LF and CRLF soft-break fixtures and
  then failed MD041 because the fixture files lacked top-level headings.
  Impact: the new hardening fixtures use a `.md.fixture` suffix under the
  Markdown corpus, and the corpus helper explicitly treats that suffix as
  Markdown source while documentation formatters ignore it.

## Decision Log

- Decision: keep this plan in `Status: DRAFT` and explicitly block code
  implementation until approval. Rationale: the user requested a plan and
  stated that it must be approved before implementation. Date/Author:
  2026-05-25T00:46:44Z / Codex.

- Decision: move the plan to `Status: IN PROGRESS` and begin Stage 0 baseline
  validation. Rationale: the user explicitly approved implementation on
  2026-06-01. Date/Author: 2026-06-01T21:56:54Z / Codex.

- Decision: centre the implementation on a Rust logical IR in
  `crates/stilyagi-ir`, with Markdown parsing and flattening in
  `crates/stilyagi-markdown`. Rationale: this preserves the hexagonal boundary
  between domain contract and parser adapter, and prevents PyO3 or Python
  models from becoming the source of truth. Date/Author: 2026-05-25T00:46:44Z /
  Codex.

- Decision: treat `markdown-rs` as the planned parser dependency unless Stage
  1 proves its positions inadequate. Rationale: the design and RFC already name
  `markdown-rs`, and Firecrawl confirmed that it exposes `to_mdast()` and
  serde-enabled AST/configuration serialization. Date/Author:
  2026-05-25T00:46:44Z / Codex.

- Decision: use property tests for segment reconstruction invariants.
  Rationale: region text reconstructed from `segments` is an invariant over a
  range of generated segment layouts, not just one representative fixture.
  Date/Author: 2026-05-25T00:46:44Z / Codex.

- Decision: keep `IrSegment.text` in the initial Rust domain type even though
  RFC examples focus on source and synthetic span metadata. Rationale: the
  field lets Stage 1 and Stage 2 prove `segments` reconstruct region text
  without relying on external source slices or parser state; if canonical v1
  JSON later omits it, that will be a deliberate serializer decision rather
  than a weaker in-memory invariant. Date/Author: 2026-06-01T22:30:00Z / Codex.

- Decision: implement Stage 2 regions for `heading`, `paragraph`, and
  `table_cell` only. Rationale: these are the representative fixture kinds
  needed to prove the envelope and mappings now; `image_alt`, `link_title`,
  list items, blockquotes, and broader Markdown coverage remain deferred until
  they can be mapped with trustworthy source spans in later roadmap work or
  Stage 3 fixture expansion. Date/Author: 2026-06-01T23:18:00Z / Codex.

- Decision: adopt the alternative plan's testing recommendations as follow-up
  hardening rather than changing this branch's completed acceptance bar.
  Rationale: the alternative plan usefully tightens edge-case validation, but
  it also proposes new bridge entrypoints, richer Python typed IR objects,
  frontmatter and CRLF fixtures, parser panic policy, and error-size assertions
  that were outside the approved and implemented 2.1.1 scope. Recording the
  recommendations keeps the next slice honest without misrepresenting this
  branch as having implemented them. Date/Author: 2026-06-05T00:00:00Z / Codex.

- Decision: prefer Python/Rust canonical JSON parity through independent
  serializers or reviewed Rust snapshots if Python grows a full typed IR
  serializer. Rationale: comparing against a `_canonical_json` value carried in
  the same bridge payload risks a self-referential test oracle. The bridge may
  continue carrying internal transport data, but the public consumer surface
  should remain the Python model. Date/Author: 2026-06-05T00:00:00Z / Codex.

- Decision: treat CRLF handling and frontmatter mapping as explicit follow-up
  acceptance items before claiming broad Markdown mapping coverage. Rationale:
  the current branch proves the envelope and representative mappings, while the
  alternative plan correctly notes that line-ending normalization and
  frontmatter/paragraph fixtures are necessary to trust later v1 rule and fix
  planning over the full Markdown surface. Date/Author: 2026-06-05T00:00:00Z /
  Codex.

- Decision: promote the follow-up hardening recommendations into this branch's
  active implementation scope without treating the whole of roadmap item 2.1.2
  as in scope. Rationale: the user explicitly requested the remaining planned
  functionality including those recommendations, while the roadmap still keeps
  exhaustive Markdown construct coverage as the next item. Date/Author:
  2026-06-05T18:42:42Z / Codex.

- Decision: enable `markdown-rs` frontmatter parsing in the existing Markdown
  parser options rather than adding a second parser or pre-scan. Rationale:
  frontmatter is an existing `markdown-rs` construct, keeps the adapter
  boundary single-source, and produces mdast `yaml` nodes that fit the current
  IR tree model. Date/Author: 2026-06-05T18:52:00Z / Codex.

- Decision: keep parser panic containment inside `stilyagi-markdown` and map
  unwinds to `markdown::message::Message`. Rationale: this preserves the
  current public `Result<Node, Message>` and `Result<IrDocument, Message>`
  signatures while preventing parser panics from crossing into extraction or
  PyO3 adapters. Date/Author: 2026-06-05T18:52:00Z / Codex.

- Decision: store formatter-sensitive Markdown hardening corpus files with a
  `.md.fixture` suffix. Rationale: these files are source fixtures whose exact
  line breaks are test data, not prose documentation to reflow; keeping them
  under `tests/fixtures/corpus/markdown/valid/` preserves corpus locality while
  avoiding destructive Markdown formatting. Date/Author: 2026-06-05T18:58:02Z /
  Codex.

- Decision: defer roadmap completion edits until the feature implementation
  lands. Rationale: marking item 2.1.1 done during plan drafting would
  misrepresent project status. Date/Author: 2026-05-25T00:46:44Z / Codex.

## Outcomes & Retrospective

Implementation is complete for roadmap item 2.1.1. The branch delivers a
Markdown-first IR envelope that can be inspected through canonical JSON
snapshots and trusted by later diagnostic, suppression, cache, and safe-fix
work. Follow-up hardening preserved the Markdown slice while making source
identity explicit, keeping the IR envelope syntax-neutral, and validating
content hash plus line-index consistency before Markdown IR is returned.

Stage 0 outcome: implementation approval was recorded and all baseline quality
gates passed on 2026-06-01 before code changes began.

Stage 1 outcome: the parser and schema spike passed targeted Rust tests on
2026-06-01. The milestone proved that `markdown-rs` can supply usable mdast
positions for representative Markdown blocks and that the IR crate can own the
document envelope, hash helper, deterministic JSON method, and segment
reconstruction invariant independently of parser or bridge adapters. Full Stage
1 gates also passed before CodeRabbit review. CodeRabbit completed the Stage 1
milestone review with zero findings.

Stage 2 outcome: `stilyagi-markdown` now builds an internal Markdown IR
document envelope with mdast tree nodes and lintable heading, paragraph, and
table-cell regions. The builder records source-backed segments for text spans
and explicit synthetic segments for soft line breaks. Targeted tests and full
deterministic gates passed. CodeRabbit completed the Stage 2 milestone review
with zero findings after a rate-limit backoff and retry.

Stage 3 outcome: the shared Markdown fixture now snapshots the canonical
`IrDocument` JSON generated by `stilyagi-markdown`. The snapshot test proves
JSON deserialization back into `IrDocument`, exact segment reconstruction, and
source-backed segment byte-span agreement with the original fixture source.
Full deterministic gates passed. CodeRabbit completed the Stage 3 milestone
review with zero findings.

Stage 4 outcome: Markdown extraction now carries the richer IR envelope through
Rust extraction, the PyO3 bridge, and the Python `engine.extract_document`
adapter. The raw bridge uses `ir_json` to avoid hand-built nested Python
dictionaries inside PyO3, and the Python model exposes the parsed envelope as
`Document.ir`. Full deterministic gates passed for this milestone, and
CodeRabbit completed the milestone review with zero findings after two
rate-limit backoffs.

Stage 5 outcome: the user guide now documents the Markdown `Document.ir`
surface, the developer guide and design document record the implemented
canonical Markdown IR bridge, and roadmap item 2.1.1 is marked done. Full
deterministic gates passed for this milestone, and CodeRabbit completed the
milestone review with zero findings.

Alternative-plan review outcome: the broader
`2-1-1-markdown-ir-envelope-and-mappings` plan was reviewed after this branch
had already implemented and validated the approved 2.1.1 slice. Its strongest
recommendations are now incorporated as hardening guidance: add paragraph,
frontmatter, soft-break, and CRLF fixtures before claiming broader Markdown
mapping coverage; strengthen property tests around segment contiguity and
source-byte matching; avoid self-referential bridge parity tests; contain
parser panics before they cross the bridge; and make extractor error-size
budgets explicit before richer error payloads land. These items should guide a
focused follow-up or roadmap item 2.1.2 rather than rewriting the acceptance
history of the completed branch.

Stage 6 outcome: the follow-up hardening recommendations requested by the user
are implemented for the 2.1.1 slice. The Markdown parser now enables
frontmatter and contains panics inside the Markdown adapter boundary. New
hardening fixtures cover inline markup, LF soft breaks, CRLF soft breaks, and
YAML frontmatter, with a scoped `.gitattributes` rule proving the CRLF fixture
is checked out with literal `\r\n` bytes. Segment property tests now generate
layouts and assert reconstruction, contiguity, source-byte agreement, and known
synthetic break reasons. Python adaptation is checked against the reviewed Rust
canonical snapshot after source identity normalization, and `ExtractError` has
an explicit compile-time size budget. Full deterministic gates passed, and
CodeRabbit completed the milestone review with zero findings.

## Revision note

Initial draft created for roadmap item 2.1.1. The draft records the approval
gate, implementation stages, validation gates, CodeRabbit review points,
expected crate and Python touchpoints, prior-art findings, and the rule that
roadmap item 2.1.1 is marked done only after the feature implementation is
complete.

2026-06-05: reviewed the alternative `2-1-1-markdown-ir-envelope-and-mappings`
plan and incorporated its useful testing and hardening recommendations as
follow-up guidance. The current plan now explicitly calls out CRLF fixture
protection, broader Markdown fixture coverage, stronger segment property tests,
Python/Rust canonical JSON parity, Markdown parser panic containment, and
`ExtractError` size-budget assertions as future work where not already
implemented.

2026-06-05: the user requested implementation of the remaining planned
functionality, including the follow-up recommendations. Stage 6 records that
hardening scope and its validation requirements.

2026-06-06: PR #15 failed-check hardening restored the blank Markdown
compatibility region while keeping the Markdown IR payload attached, removed
the remaining hard-coded English locale policy from `DocumentMetadata`, added
closed-vocabulary spelling fixtures, strengthened canonical helper property
tests, added an injectable Markdown IR failure-path seam, and kept PyO3 IR JSON
checks structural. Source identity (#23), broader Markdown observability (#24),
and cross-syntax IR generalization (#25) were triaged as PR #15 failed-check
hardening topics. Source identity and syntax-neutral IR envelope hardening were
implemented on this branch. Broader Markdown observability remains tracked in
issue #24.

2026-06-06: source identity hardening replaced fake memory path and URI values
with explicit anonymous identity for string-only Markdown extraction. The
existing `extract_document(source, syntax)` API remains backwards-compatible
and delegates to the identity-aware extraction boundary with `path` and `uri`
set to `null` in canonical IR JSON. Callers that know a real path or URI can
now pass `SourceIdentity` through the Rust extraction boundary.

2026-06-07: Markdown IR consistency hardening now validates that returned IR
metadata still matches `content_hash_for(source)` and `line_index_for(source)`.
Mismatch diagnostics use `stilyagi-markdown` messages with stable rule IDs and
phase/path/URI context.
