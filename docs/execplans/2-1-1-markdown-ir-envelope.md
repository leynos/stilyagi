# Implement the Markdown IR envelope

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
 `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`, `Decision Log`,
and `Outcomes & Retrospective` must be kept up to date as work proceeds.

Status: IN PROGRESS

Approval gate: the user approved implementation on 2026-06-01 by asking to
proceed with the planned functionality. Continue milestone by milestone within
the tolerances below.

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
- Do not add Kani, CrossHair, or Verus proof work unless the implementation
  introduces a substantive invariant that is better proved than tested.
- Run format, typecheck, lint, and tests sequentially. Capture long command
  output with `tee` into `/tmp` logs. Do not run format, lint, typecheck, or
  tests in parallel.
- Run `coderabbit review --agent` after each major implementation milestone,
  but only after deterministic quality gates for that milestone pass. Resolve
  or explicitly document all actionable concerns before moving on.
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

- Risk: widening the PyO3 payload breaks the existing Python extraction tests
  or exposes raw transport details as public API. Severity: medium. Likelihood:
  medium. Mitigation: keep the old minimal fields available where practical,
  add new typed model fields compatibly, update `_stilyagi_rs.pyi`, and test
  through `python/stilyagi/engine/extraction.py` rather than raw dict internals
  alone.

- Risk: Rust and Python golden IR helpers drift into two subtly different
  contracts. Severity: medium. Likelihood: high. Mitigation: make Rust
  canonical JSON the source of truth, then update Python helpers to compare the
  same normalized field names and ordering.

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

Do not begin this stage until the user explicitly approves this plan. Once
approved, update `Status` to `APPROVED`, record the approval in the
`Decision Log`, and then set `Status` to `IN PROGRESS` when implementation
starts.

Check the branch and working tree with `git branch --show-current` and
`git status --short --branch`. Confirm the branch is
`2-1-1-markdown-ir-envelope`. If the branch is not the task branch, stop and
ask whether to rename it before code work. If unrelated user changes exist,
leave them alone and work around them.

Run a baseline gate before code changes so later failures have a comparison
point. Use the project Makefile targets and `tee` logs:

```bash
BRANCH="$(git branch --show-current)"
make check-fmt 2>&1 | tee "/tmp/check-fmt-stilyagi-${BRANCH}.out"
make typecheck 2>&1 | tee "/tmp/typecheck-stilyagi-${BRANCH}.out"
make lint 2>&1 | tee "/tmp/lint-stilyagi-${BRANCH}.out"
make test 2>&1 | tee "/tmp/test-stilyagi-${BRANCH}.out"
```

If any baseline gate fails before implementation, inspect the log and decide
whether the failure is caused by the clean branch, local environment, or
pre-existing unrelated changes. Record the finding in `Surprises & Discoveries`
and stop if the failure would make this plan unverifiable.

### Stage 1: parser and schema spike

Add the smallest parser integration needed to prove the source-position path.
The expected direction is to add the `markdown` crate with the `serde` feature
to `crates/stilyagi-markdown/Cargo.toml` or the narrow crate that owns parsing.
Keep Markdown-specific code in `crates/stilyagi-markdown/src/lib.rs` or a small
module under that crate. Do not place Markdown parser traversal inside PyO3 or
Python model code.

In `crates/stilyagi-ir/`, define the logical IR data types needed by RFC 0001:
document metadata, producer metadata, line index, tree metadata, nodes, spans,
region records, segment records, source segment ranges, suppressions, errors,
and metadata. Prefer named structs and enums over freeform maps where the
contract is known. Keep extensible maps only for `metadata`, `attrs`, and
future parser-specific properties.

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

Use the exact names only if they fit the existing code. The important contract
is that the type belongs to `stilyagi-ir`, and extraction, PyO3, and Python
adapt around it.

Add unit tests in `crates/stilyagi-ir/` for `line_index`, content hash
formatting, canonical JSON ordering, and segment reconstruction helpers. Add a
targeted parser spike test in `crates/stilyagi-markdown/` or
`crates/stilyagi-extract/` that parses the shared Markdown fixture and confirms
that positions are present for the root and at least one heading or paragraph
node.

Run the targeted Rust tests first:

```bash
cargo test -p stilyagi-ir -p stilyagi-markdown 2>&1 \
  | tee "/tmp/test-ir-markdown-stilyagi-${BRANCH}.out"
```

If the parser cannot provide usable offsets for the representative fixture,
stop here and record alternatives in `Decision Log`.

### Stage 2: Markdown flattening and IR envelope

Implement the Markdown IR builder in `crates/stilyagi-markdown/`. It should
take source text plus source identity and produce Markdown-specific structural
facts: an mdast-shaped tree, stable node identifiers, source-backed spans, and
region candidates. Keep the builder deterministic: traversal order, generated
IDs, and JSON output must not depend on hash-map ordering.

Implement region flattening for the minimum Markdown region kinds needed to
prove the envelope:

- `heading`
- `paragraph`
- `list_item`, if the shared fixture or tests need list coverage
- `table_cell`, if the shared fixture's table is included in the first
  snapshot
- `image_alt` and `link_title`, where their source mapping can be made
  trustworthy

For each emitted region, populate `kind`, `scope`, `syntax`, `natural_language`
when known, `text`, `segments`, `origin_nodes`, `owner`, `attrs`, and
`parent_region`. `owner` must be `null` for Markdown regions; do not overload
it with section context.

Represent synthetic insertions explicitly. A soft line break that becomes a
space in region text should create a segment with `source: null` and a stable
synthetic reason such as `softbreak_space`. The surrounding source-backed
segments must retain their original byte ranges.

Update `crates/stilyagi-extract/src/lib.rs` so `extract_document` delegates
Markdown work to the Markdown builder and returns or wraps the richer IR
document. Keep unsupported syntax errors for Python and Rust exactly explicit;
do not silently return empty IR for unsupported extractors.

Add Rust unit tests with `rstest` for source-backed regions and synthetic
segments. Add `proptest` coverage for the invariant that reconstructing a
region from its segments yields exactly the region text for generated simple
segment sequences, and that invalid source ranges cannot be constructed if the
API is designed to prevent them.

Run:

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

After these gates pass, run `coderabbit review --agent` and address all
actionable concerns. Commit this milestone with a focused message.

### Stage 3: canonical JSON and golden fixtures

Move canonical serialization into `crates/stilyagi-ir/src/canonical_json.rs` if
it is not already there. The serializer must produce deterministic JSON for
`IrDocument` and related types. Prefer structured serialization over
handwritten string concatenation.

Update `crates/stilyagi-test-support/src/golden_ir.rs` and
`crates/stilyagi-test-support/src/golden_fixture_builder.rs` so they build the
same logical envelope that production extraction emits. The test support layer
may add fixture conveniences, but it must not invent a second IR schema.

Update Rust snapshots under:

- `crates/stilyagi-extract/tests/snapshots/`
- `crates/stilyagi-test-support/tests/snapshots/`

Update Python golden snapshot support under:

- `tests/support/golden_ir.py`
- `tests/__snapshots__/test_round_trip_helpers/`

Add or update snapshot tests proving that the shared Markdown fixture's
canonical JSON includes document metadata, `content_hash`, `line_index`,
Markdown tree metadata, region text, source-backed segments, and any synthetic
segments included by the fixture.

Use `insta` and `syrupy` update modes only after reviewing the diff:

```bash
INSTA_UPDATE=always cargo test -p stilyagi-extract -p stilyagi-test-support
.venv/bin/python -m pytest tests/test_round_trip_helpers.py --snapshot-update
```

Then run the same tests without update flags to prove the snapshots are stable.
Run full gates, run `coderabbit review --agent`, resolve concerns, and commit
the milestone.

### Stage 4: PyO3 bridge and Python model adaptation

Update `crates/stilyagi-pyext/src/lib.rs` so `extract_document` exposes the new
logical envelope through a Python dictionary that preserves the canonical field
names. Keep the adapter small. Do not duplicate Markdown flattening or
canonical JSON construction in PyO3.

Update `python/stilyagi/_stilyagi_rs.pyi` to describe the richer bridge
payload. Update `python/stilyagi/engine/extraction.py` so it validates the new
shape and adapts it into Python models. Update
`python/stilyagi/model/document.py` and `python/stilyagi/model/region.py` with
typed fields for `line_index`, document metadata, regions, and segments if
those fields become part of the supported Python surface.

Prefer compatibility. Existing callers that inspect `Document.syntax` and
`Region.kind` / `Region.text` should keep working unless the user approves a
breaking change.

Add Python tests for bridge adaptation and model validation. Use `pytest` for
unit tests and existing `pytest-bdd` patterns only if an externally observable
behaviour needs a Gherkin scenario. Add `syrupy` snapshots where output shape
stability matters.

Run:

```bash
make build 2>&1 | tee "/tmp/build-stage4-stilyagi-${BRANCH}.out"
.venv/bin/python -m pytest -q \
  tests/test_round_trip_helpers.py \
  tests/test_package_skeleton_units.py \
  tests/test_package_structure_bdd.py \
  2>&1 | tee "/tmp/pytest-stage4-stilyagi-${BRANCH}.out"
```

Then run full gates, run `coderabbit review --agent`, resolve concerns, and
commit the milestone.

### Stage 5: documentation and roadmap completion

Update `docs/developers-guide.md` to document the new internal IR envelope, the
Markdown flattening boundary, segment invariants, canonical JSON workflow, and
how Rust and Python golden fixtures stay aligned. Update `docs/users-guide.md`
only for consumer-visible changes, such as richer fields on the supported Python
 `Document` or `Region` model.

Update `docs/stilyagi-design.md` only if implementation resolves an ambiguity
or changed the design. Update RFC 0001 only if the accepted contract needs a
substantive field-level correction. If no design or RFC change is needed,
record that decision in this plan instead of editing those files.

After all implementation and documentation gates pass, mark roadmap item 2.1.1
as done in `docs/roadmap.md`. Do not mark 2.1.2 or 2.1.3 done.

For Markdown documentation changes, run:

```bash
make fmt 2>&1 | tee "/tmp/fmt-docs-stage5-stilyagi-${BRANCH}.out"
make markdownlint 2>&1 | tee "/tmp/markdownlint-stage5-stilyagi-${BRANCH}.out"
make nixie 2>&1 | tee "/tmp/nixie-stage5-stilyagi-${BRANCH}.out"
```

Then run the required full gates:

```bash
make check-fmt 2>&1 | tee "/tmp/check-fmt-stage5-stilyagi-${BRANCH}.out"
make typecheck 2>&1 | tee "/tmp/typecheck-stage5-stilyagi-${BRANCH}.out"
make lint 2>&1 | tee "/tmp/lint-stage5-stilyagi-${BRANCH}.out"
make test 2>&1 | tee "/tmp/test-stage5-stilyagi-${BRANCH}.out"
```

Run `coderabbit review --agent`, clear concerns, and make the final feature
commit.

## Concrete steps

All commands in this section run from the repository root. If a shell variable
is useful, set it to the current checkout rather than to a machine-specific
absolute path:

```bash
REPO_ROOT="$(pwd)"
cd "$REPO_ROOT"
```

Create or refresh the `leta` workspace before code navigation:

```bash
leta workspace add "$REPO_ROOT"
```

Inspect symbols with `leta` rather than broad text search when a symbol name is
known:

```bash
leta grep "ExtractDocument|ExtractRegion|RegionKind|IrDocument" -k struct,enum
leta show extract_document
leta refs ExtractDocument
```

Use `rg` only for Markdown prose, configuration keys, snapshots, or other
non-symbol text:

```bash
rg -n "line_index|segments|content_hash|dump-ir" docs tests crates
```

Run implementation milestones in the order described in `Plan of work`. After
each milestone, inspect changed files:

```bash
git status --short
git diff --stat
git diff -- docs/execplans/2-1-1-markdown-ir-envelope.md
```

Use file-based commit messages:

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

Use a more specific subject for each actual milestone commit. The example is a
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

Do not use CodeRabbit to find deterministic format, lint, type, or test
failures that local gates can catch.

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
`Decision Log`, and stop for approval. Do not replace the parser with an ad hoc
Markdown scanner without explicit approval.

If a gate fails because of unrelated user changes, do not revert those changes.
Record the failure and either work around it or ask for direction if it blocks
verification.

If the branch needs to be reset for local experimentation, do not use
destructive Git commands. Prefer new commits, targeted patches, or a separate
scratch branch. Ask before any operation that would discard user work.

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
  `make check-fmt`, `make typecheck`, `make lint`, and `make test` all
  passed.
- [x] (2026-06-01T22:30:00Z) Implemented the Stage 1 parser and schema spike:
  `stilyagi-ir` now owns the first production IR envelope types, content hash
  helper, canonical JSON method, and segment reconstruction invariant tests;
  `stilyagi-markdown` now has a `markdown-rs` parse wrapper and position
  probe.
- [x] (2026-06-01T22:45:00Z) Gated Stage 1 locally. `make markdownlint`,
  `make nixie`, `make check-fmt`, `make typecheck`, `make lint`, and
  `make test` all passed. The full test gate ran 90 Rust tests and 66 Python
  tests.
- [x] (2026-06-01T22:58:00Z) Ran `coderabbit review --agent` for the Stage 1
  milestone after deterministic gates passed. CodeRabbit completed with zero
  findings.
- [x] (2026-06-01T23:18:00Z) Implemented the Stage 2 Markdown IR builder in
  `stilyagi-markdown`. It now builds a deterministic mdast-backed tree,
  source spans, heading/paragraph/table-cell regions, heading depth attrs,
  source-backed text segments, and synthetic soft-break segments. Targeted
  `cargo test -p stilyagi-markdown` passed.
- [x] (2026-06-01T23:31:00Z) Gated Stage 2 locally. `make markdownlint`,
  `make nixie`, `make check-fmt`, `make typecheck`, `make lint`, and
  `make test` all passed. The full test gate ran 92 Rust tests and 66 Python
  tests.
- [x] (2026-06-02T00:08:00Z) Ran `coderabbit review --agent` for the Stage 2
  milestone. The first attempt hit a recoverable rate limit, so the workflow
  slept for 23 minutes as instructed and retried. The retry completed with
  zero findings.
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
- [ ] After approval, implement Stage 4 PyO3 bridge and Python model
  adaptation.
- [ ] After approval, implement Stage 5 documentation and roadmap completion.

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
  and `end.offset`, and the representative spike confirms positions are
  present for the root, a heading, and a paragraph. Evidence:
  `cargo test -p stilyagi-ir -p stilyagi-markdown` passed after adding the
  parser probe. Impact: Stage 2 can proceed with `markdown-rs`; flattening
  must still normalize and test exact byte spans rather than assume every node
  end offset matches naive fixture slicing.

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
  generated the snapshot, and a normal `cargo test -p stilyagi-markdown`
  passed immediately afterwards. Impact: Stage 4 can bridge the same Rust IR
  shape without depending on machine-specific snapshot data.

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
  than a weaker in-memory invariant. Date/Author: 2026-06-01T22:30:00Z /
  Codex.

- Decision: implement Stage 2 regions for `heading`, `paragraph`, and
  `table_cell` only. Rationale: these are the representative fixture kinds
  needed to prove the envelope and mappings now; `image_alt`, `link_title`,
  list items, blockquotes, and broader Markdown coverage remain deferred until
  they can be mapped with trustworthy source spans in later roadmap work or
  Stage 3 fixture expansion. Date/Author: 2026-06-01T23:18:00Z / Codex.

- Decision: defer roadmap completion edits until the feature implementation
  lands. Rationale: marking item 2.1.1 done during plan drafting would
  misrepresent project status. Date/Author: 2026-05-25T00:46:44Z / Codex.

## Outcomes & Retrospective

No implementation outcome exists yet. This is a pre-implementation plan. The
expected outcome after approval and execution is a Markdown-first IR envelope
that can be inspected through canonical JSON snapshots and trusted by later
diagnostic, suppression, cache, and safe-fix work.

Stage 0 outcome: implementation approval was recorded and all baseline quality
gates passed on 2026-06-01 before code changes began.

Stage 1 outcome: the parser and schema spike passed targeted Rust tests on
2026-06-01. The milestone proved that `markdown-rs` can supply usable mdast
positions for representative Markdown blocks and that the IR crate can own the
document envelope, hash helper, deterministic JSON method, and segment
reconstruction invariant independently of parser or bridge adapters.
Full Stage 1 gates also passed before CodeRabbit review. CodeRabbit completed
the Stage 1 milestone review with zero findings.

Stage 2 outcome: `stilyagi-markdown` now builds an internal Markdown IR
document envelope with mdast tree nodes and lintable heading, paragraph, and
table-cell regions. The builder records source-backed segments for text spans
and explicit synthetic segments for soft line breaks. Targeted tests passed;
full deterministic gates passed, and CodeRabbit review is still pending for
this milestone. CodeRabbit later completed the Stage 2 milestone review with
zero findings after a rate-limit backoff and retry.

Stage 3 outcome: the shared Markdown fixture now snapshots the canonical
`IrDocument` JSON generated by `stilyagi-markdown`. The snapshot test proves
JSON deserialization back into `IrDocument`, exact segment reconstruction, and
source-backed segment byte-span agreement with the original fixture source.
Full deterministic gates passed, and CodeRabbit review is still pending for
this milestone. CodeRabbit later completed the Stage 3 milestone review with
zero findings.

## Revision note

Initial draft created for roadmap item 2.1.1. The draft records the approval
gate, implementation stages, validation gates, CodeRabbit review points,
expected crate and Python touchpoints, prior-art findings, and the rule that
roadmap item 2.1.1 is marked done only after the feature implementation is
complete.
