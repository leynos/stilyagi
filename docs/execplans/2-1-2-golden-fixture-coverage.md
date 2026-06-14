# Cover every v1 Markdown region kind with golden fixtures

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
`Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`, `Decision Log`,
and `Outcomes & Retrospective` must be kept up to date as work proceeds.

Status: IN PROGRESS

Approval gate: this plan must not be implemented until explicit user approval
is recorded in the `Decision Log`. After approval, `Status` changes to
`APPROVED`, then to `IN PROGRESS` when implementation begins.

## Purpose / big picture

Roadmap item 2.1.2 proves that Stilyagi's Markdown intermediate representation
(IR) can represent every lintable surface that v1 promises, and that each one
is locked behind a golden fixture so later rule, fix, and suppression work can
trust it. After this change a maintainer can run Markdown extraction over a
small corpus of fixtures and inspect canonical IR JSON in which headings,
paragraphs, list items, blockquotes, table cells, frontmatter, image
alternative text, and link titles each appear as a region with a stable `kind`,
a `scope`, source-faithful `segments`, and (for structural containers)
`parent_region` links — with malformed Markdown degrading gracefully rather
than panicking or drifting.

The observable success condition is not "the code compiles" and not merely "a
fixture file exists". The executable definition of done is a coverage test that
fails before the work and passes after it: the union of region `kind`s emitted
across the valid Markdown fixture corpus must contain every promised v1
Markdown region kind. Each kind additionally has per-kind structural assertions
and an `insta` snapshot, so a reviewer can see the exact region text,
source-backed byte spans, and synthetic insertions for that construct.

This slice deliberately does not implement Markdown lint rules, suppression
parsing (roadmap item 2.1.3), safe fix planning, or the public `dump-ir`
command (roadmap item 2.2.3). It supplies the region facts those later items
must trust, and it closes a latent correctness gap discovered during planning:
the build-time IR validator currently never re-checks that a source-backed
segment's byte span actually equals the segment's text, so source span drift is
invisible today. This plan makes that drift a hard build error before adding
any new region kind on top of it.

## Context and orientation

The repository is a mixed Rust and Python project. Rust crates live under
`crates/`, Python package code lives under `python/stilyagi/`, Python tests
live under `tests/`, shared corpus fixtures live under
`tests/fixtures/corpus/`, and Rust behaviour-driven development (BDD) feature
files live under each crate's `tests/features/`.

The crates this plan touches:

- `crates/stilyagi-ir/` owns the logical IR schema: `IrDocument`
  (`src/document.rs`), `IrRegion`, `IrSegment`, `SegmentOrigin`, `IrOwner`
  (`src/region.rs`), `IrNode`, `IrTree` (`src/tree.rs`), `IrError`
  (`src/diagnostics.rs`), `SourceSpan`, `SourceIdentity`, canonical JSON
  (`src/canonical_json.rs`), and content-hash/line-index helpers.
- `crates/stilyagi-markdown/` owns Markdown parsing and flattening:
  `markdown_ir_document` and `MarkdownIrBuilder` (`src/lib.rs`), the inline
  flattener (`src/flatten.rs`), source-text byte helpers
  (`src/source_text.rs`), the mdast node-kind map (`src/node_kind.rs`), and the
  `insta` snapshot tests (`src/tests.rs` plus `src/tests/`).
- `crates/stilyagi-extract/` orchestrates syntax selection: `extract_document`,
  `ExtractDocument`, `ExtractRegion`, `ExtractError`, and the coarse bridge
  `RegionKind` enum (currently a single `Document` variant — unrelated to the
  IR region vocabulary).
- `crates/stilyagi-pyext/` exposes the PyO3 bridge: `extract_document_py` and
  `supported_syntaxes` (`src/lib.rs`).
- `crates/stilyagi-test-support/` provides corpus fixture access
  (`src/fixture_paths.rs`, `src/fixture_reads.rs`) and golden IR scaffolding
  (`src/golden_ir.rs`, `src/golden_fixture_builder.rs`).

The relevant Python modules:

- `python/stilyagi/engine/extraction.py` adapts the bridge payload into models
  and validates `syntax` against `supported_syntaxes()`.
- `python/stilyagi/model/document.py` exposes `Document` with an opaque
  `ir: Mapping[str, object] | None`.
- `python/stilyagi/model/region.py` exposes a minimal `Region(kind, text)`.
- `python/stilyagi/_stilyagi_rs.pyi` mirrors the extension payload for type
  checking.
- `tests/support/golden_ir.py` mirrors the Python golden IR shape.

Definitions used in this plan:

- IR means intermediate representation: Stilyagi's stable logical payload for
  source structure, lintable prose regions, source positions, and debug output.
- Region means a lintable surface such as a heading, paragraph, list item,
  blockquote, table cell, frontmatter block, image alternative text, or link
  title. A region has a `kind`, a `scope`, `text`, `segments`, `origin_nodes`,
  `attrs`, and an optional `parent_region`.
- Node means a structural mdast tree node (for example `heading`, `listItem`,
  `blockquote`, `image`). Nodes model structure; regions model lintable text.
- Segment means a mapping from a span of region text to either original source
  bytes (source-backed) or an explicit synthetic insertion.
- Synthetic insertion means text present in the flattened lint surface but
  absent
  as editable bytes in the source file (for example a space substituted for a
  soft line break). The closed reason set today is `softbreak_space`,
  `hardbreak_space`, and `decoded_text`.
- Span drift means any mismatch between a reported source byte offset and the
  bytes that actually produced the corresponding region text.
- Thin structural region means a container region (`list_item`, `blockquote`)
  that carries no prose text of its own; its prose lives in child regions
  linked by `parent_region`, and it exists so rules can name and navigate the
  construct.

The current emission gap, confirmed during planning: `MarkdownIrBuilder`
(`crates/stilyagi-markdown/src/lib.rs`, `push_region_for_node`) emits regions
only for `heading`, `paragraph`, and `table_cell`. RFC 0001
(`docs/rfcs/0001-stilyagi-intermediate-representation.md`, lines 223–236) lists
a v1 region vocabulary that also includes `list_item`, `blockquote`,
`frontmatter`, `frontmatter_field`, `image_alt`, and `link_title` (plus
`python_docstring` and `rust_doc_comment`, which are non-Markdown and out of
scope for this slice).

## Documentation and skill signposts

Before implementing this plan, load and apply these skills:

- `leta`, for symbol-aware Rust and Python navigation; create or refresh the
  workspace with `leta workspace add "$(pwd)"`.
- `rust-router`, then `arch-crate-design`, because this change adds a public
  Rust enum (`RegionKind`) to `stilyagi-ir` and touches crate-facing surfaces.
- `hexagonal-architecture`, to preserve the boundary between the domain IR
  schema
  (`stilyagi-ir`), the Markdown adapter (`stilyagi-markdown`), the PyO3
  transport (`stilyagi-pyext`), and the Python application models.
- `rust-types-and-apis`, for the `RegionKind` and `SyntheticReason` vocabulary
  enums and their `as_str` / `TryFrom` / `ALL` surfaces.
- `rust-errors`, for the new validator error variants.
- `rust-unit-testing` and `nextest`, for `rstest` fixtures, parametrized table
  tests, and targeted Rust test execution.
- `proptest`, for the segment-invariant property tests.
- `rstest-bdd` guidance in `docs/rstest-bdd-users-guide.md`, for the Rust
  behaviour feature.
- `arch-decision-records`, for the Y-Statement ADR that records the
  `frontmatter_field` deferral and region-vocabulary governance.
- `python-router`, then `python-testing`, for the Python bridge parity test and
  any `syrupy` snapshot.
- `commit-message`, for every commit (file-based messages applied with
  `git commit -F`; never `git commit -m`).
- `pr-creation` and `en-gb-oxendict`, for the draft pull request.

Keep these repository documents open:

- `docs/roadmap.md`, item 2.1.2 and its dependency on 2.1.1.
- `docs/stilyagi-design.md`, especially §6 (region model and owner contract) and
  §7.1 (IR review and consequences).
- `docs/rfcs/0001-stilyagi-intermediate-representation.md`, especially §6
  (region
  fields and the v1 `kind` vocabulary, lines 205–292) and §7 (region
  invariants, lines 294–307).
- `docs/execplans/2-1-1-markdown-ir-envelope.md`, the predecessor slice, for the
  envelope shape, the `.md.fixture` suffix rationale, the CRLF `.gitattributes`
  guard, and the existing `insta` snapshot conventions.
- `docs/complexity-antipatterns-and-refactoring-strategies.md`, to keep the
  flattening and region-assembly logic small enough to review.
- `docs/rust-testing-with-rstest-fixtures.md` and
  `docs/reliable-testing-in-rust-via-dependency-injection.md`, for Rust fixture
  and deterministic-IO conventions.
- `docs/developers-guide.md` and `docs/users-guide.md`, for maintainer-facing
  and
  consumer-facing documentation updates.

External prior art checked during planning (Firecrawl plus the installed crate
source at `markdown-1.0.0/src/mdast.rs`):

- The `markdown` crate (markdown-rs 1.0.0) exposes every mdast node with
  `position: Option<Position>` carrying byte `start.offset` / `end.offset`.
  `Blockquote` (one word), `List`, `ListItem`, `Table`, `TableRow`, `TableCell`,
  `Yaml`, and `Toml` all carry faithful byte spans.
- `ListItem` carries `spread: bool` and `checked: Option<bool>` (GFM task
  state);
  the `[x]` / `[ ]` task marker is stripped from the leading child `Text` value
  but the `ListItem` span still covers the marker bytes.
- `Image` is a void node whose `alt: String` is decoded with no sub-position;
  for
  images the positioned child `Text` nodes are discarded. `Link.title` and
  `Image.title` are likewise decoded `String`s with no sub-position. There is
  no built-in way to recover exact source bytes for alt or title text without a
  secondary scan of the parent node span.
- `Yaml` / `Toml` carry `value: String` (fences stripped, end-of-line trimmed)
  and a `position` that includes the `---` / `+++` fences.
  `ParseOptions::gfm()` does not enable frontmatter;
  `options.constructs.frontmatter = true` must be set explicitly (the builder
  already does this).
- For non-MDX input, `to_mdast` is effectively infallible: malformed Markdown
  (unbalanced emphasis, broken reference links, an unclosed GFM table) recovers
  to literal `Text` or best-effort structure rather than returning `Err`.
- Decoded literal values (entities `&amp;` → `&`, escapes `\*` → `*`) are
  shorter
  than their source byte span, so a node's interior must never be indexed by
  source offset; only the node's outer `start.offset..end.offset` is reliable.

## Constraints

- Do not implement this plan until explicit approval is recorded in the
  `Decision Log`.
- Preserve roadmap scope. This item delivers Markdown region-kind coverage and
  golden fixtures. It does not implement suppression parsing (2.1.3), the CLI
  loop (2.2), builtin rules (2.3), or `dump-ir` (2.2.3).
- Keep Markdown first. Do not claim Python docstring or Rust documentation
  comment
  region emission as part of this slice; those `kind`s remain reserved.
- The Rust IR schema in `stilyagi-ir` owns the logical types. PyO3 serialization
  and Python model adaptation are adapters around that schema and must not
  become a second source of truth.
- Keep source offsets byte-oriented. Region segments must reconstruct text
  exactly
  and every source-backed segment's byte span must equal its segment text. If a
  region kind cannot satisfy this, it must use explicit synthetic segments
  rather than a guessed source span.
- `owner` remains `null` for all Markdown regions. Markdown nesting and
  structural
  context live in `parent_region`, `scope`, and `attrs`, never in `owner` (RFC
  0001 §6, lines 289–292).
- `image_alt` and `link_title` are emitted as synthetic `decoded_text` segments
  in
  this slice. They must never be source-backed by an unverified or non-unique
  byte scan. Byte-accurate recovery is recorded as future work.
- `list_item` and `blockquote` are thin structural regions in this slice: they
  carry no prose text and do not re-flatten child prose. No new synthetic
  segment reason (such as a block separator) is introduced.
- Canonical JSON snapshots must avoid machine-specific absolute paths,
  timestamps,
  nondeterministic ordering, terminal colour, and environment values.
- Each new region kind is exercised by a dedicated minimal fixture and snapshot.
  The shared fixture `heading-table-link-suppression.md` must not be grown to
  cover new kinds; its snapshot stays an integration oracle.
- Formatter-sensitive Markdown fixtures (soft breaks, CRLF, frontmatter, list
  and
  blockquote indentation, anything that `mdformat-all` or markdownlint MD041
  would rewrite) use the `.md.fixture` suffix. Only formatter-safe fixtures use
  `.md`.
- Use `rstest` for Rust unit tests, `rstest-bdd` for Rust behaviour tests,
  `insta`
  for Rust snapshots, `proptest` for Rust segment invariants, `pytest` for
  Python unit tests, `pytest-bdd` only where an externally observable behaviour
  needs a Gherkin scenario, and `syrupy` for Python snapshots.
- Run format, typecheck, lint, and tests sequentially using the Makefile
  targets,
  capturing long output with `tee` into `/tmp` logs. Do not run gates in
  parallel.
- Run `coderabbit review --agent` after each major milestone, but only after the
  deterministic gates for that milestone pass. Resolve or explicitly document
  all actionable concerns before moving on.
- Commit after each approved, gated milestone with a file-based message. Do not
  commit failing code. Do not use `git commit -m`.
- On completion, mark only roadmap item 2.1.2 as done in `docs/roadmap.md`.

## Tolerances

- Scope: if implementation requires changes to more than twenty-five files or
  roughly 1,500 net new lines excluding snapshots and fixtures, stop and ask
  for approval to continue.
- Public API: if a supported Python API or an existing public Rust API must be
  removed or renamed (rather than extended compatibly), stop and present
  options. Adding the `RegionKind` enum and a `supported_region_kinds()`
  function is an additive change and is in scope.
- Dependencies: no new external dependency is expected. If implementing any
  region
  kind appears to require a new crate (for example a YAML or TOML parser), stop
  — that signals scope creep into the deferred `frontmatter_field` work.
- Region model: if thin structural containers prove insufficient for the
  coverage
  criterion or break an existing test in a way that cannot be resolved
  additively, stop and present the prose-bearing-container alternative with
  trade-offs before changing the model.
- Span fidelity: if any source-backed segment cannot be proven byte-exact for a
  new kind, that text must be emitted synthetically; if that is impossible
  without drift risk, stop and record the kind as blocked.
- Test attempts: if the same deterministic gate fails three times after a
  plausible fix, stop and record the failure with the relevant log path.
- Performance: if warm extraction of the fixture corpus makes `make test` more
  than fifteen seconds slower on this machine, document the cause and ask
  whether to narrow or defer the expensive check.
- Ambiguity: if two valid interpretations of RFC 0001 would produce different
  JSON
  shapes for a new kind, stop and record the options before choosing.

## Risks

- Risk: the build-time IR validator (`validate_ir_consistency` in
  `crates/stilyagi-markdown/src/lib.rs`) currently checks only that segments
  reconstruct region text; it never re-slices `source[span] == segment.text`,
  so source span drift is invisible. Severity: high. Likelihood: high (latent
  today). Mitigation: Stage 1 adds an `ir-segment-source-mismatch` check to the
  production validator before any new kind is added, converting silent drift
  into a hard build failure for all current and future regions.

- Risk: `image_alt` and `link_title` text is decoded by markdown-rs with no
  sub-position, so a naive first-match byte scan (as the existing
  `source_value_start` helper performs) can source-back the wrong occurrence
  (for example `![cat](cat.png "cat")`), corrupting any future fix. Severity:
  high. Likelihood: high if re-scanning is attempted. Mitigation: emit alt and
  title as synthetic `decoded_text` segments in this slice; never source-back
  them.

- Risk: a prose-bearing container model would double-cover list-item and
  blockquote prose, make `origin_nodes` ambiguous, create two fix targets for
  the same bytes, and force a block-aware refactor of the inline-only flattener
  with a new block-separator synthetic reason whose space-versus-newline choice
  could corrupt prose boundaries. Severity: high. Likelihood: high under that
  model. Mitigation: adopt thin structural containers; prose stays in child
  paragraph regions linked by `parent_region`; no block separator is introduced.

- Risk: malformed Markdown recovers to literal markup text (`*a _b *c`,
  `[x][nope]`) that passes the reconstruction invariant yet is prose garbage; a
  round-trip-only test would declare victory on garbage. Severity: medium.
  Likelihood: high. Mitigation: snapshot the flattened text of each malformed
  fixture so a human reviews the intended degradation, in addition to asserting
  no panic and stable round-trip.

- Risk: GFM task-list markers (`[x]`) sit inside the `ListItem` source span but
  are stripped from the child paragraph text, so a region whose span covers
  bytes its text omits could drift. Severity: medium. Likelihood: medium.
  Mitigation: the Stage 1 re-slice validator catches any source-backed segment
  whose span and text disagree; add a task-list fixture and assert the
  paragraph text and segment spans explicitly.

- Risk: CRLF interacts with list, blockquote, and frontmatter fixtures so that
  parser `\n` text is mapped against source `\r\n` bytes. Severity: medium.
  Likelihood: medium. Mitigation: child paragraphs reuse the existing proven
  dual-cursor soft-break path; add CRLF list and blockquote fixtures and a
  property test that source-backed segments re-slice exactly under both line
  endings.

- Risk: adding region kinds renumbers region ids and churns the large shared
  snapshot, making review unreliable. Severity: medium. Likelihood: medium.
  Mitigation: dedicate one fixture and snapshot per new kind; leave the shared
  fixture and its snapshot unchanged.

- Risk: the `kind` and synthetic `reason` vocabularies are currently loose
  strings
  duplicated between the producer and the test oracle, so a typo (`blockqoute`)
  ships green and drifts from the consumer. Severity: medium. Likelihood:
  medium. Mitigation: introduce a single-source-of-truth `RegionKind` enum in
  `stilyagi-ir` and centralize the synthetic-reason allow-list so the producer
  and tests derive from one constant.

- Risk: deferring `frontmatter_field` silently shrinks a vocabulary that RFC
  0001
  marks `SHALL`. Severity: medium. Likelihood: certain if undocumented.
  Mitigation: record the deferral in a Y-Statement ADR and amend RFC 0001 to
  mark `frontmatter_field` reserved and not-yet-emitted, with the
  YAML/TOML-parser rationale, before relying on the deferral.

- Risk: deeply nested or empty constructs (a five-deep blockquote, an empty list
  item) cause unbounded recursion or stray empty regions. Severity: low.
  Likelihood: low. Mitigation: add adversarial nested and empty fixtures and
  assert region structure and bounded behaviour.

## Plan of work

The work is staged so that the correctness scaffolding lands before any new
region kind, and the executable success criterion (the coverage test) is
written red before the kinds that satisfy it.

### Stage 0: approval and baseline

This stage must not begin until explicit user approval is recorded. After
approval, set `Status` to `APPROVED`, record the approval in the
`Decision Log`, and set `Status` to `IN PROGRESS` when implementation starts.

Confirm the branch with `git branch --show-current` (expected
`2-1-2-golden-fixture-coverage`) and the tree with
`git status --short --branch`. Run the full gates before any code change so
later failures have a comparison point:

```bash
BRANCH="$(git branch --show-current)"
make check-fmt 2>&1 | tee "/tmp/check-fmt-stilyagi-${BRANCH}.out"
make typecheck 2>&1 | tee "/tmp/typecheck-stilyagi-${BRANCH}.out"
make lint 2>&1 | tee "/tmp/lint-stilyagi-${BRANCH}.out"
make test 2>&1 | tee "/tmp/test-stilyagi-${BRANCH}.out"
```

Record the baseline result in `Surprises & Discoveries`. If a baseline gate
fails on the clean branch, stop and determine whether the failure would make
this plan unverifiable.

### Stage 1: correctness scaffolding (red first)

This stage hardens the invariants that every later kind depends on. It is
written test-first.

First, the production validator. In `crates/stilyagi-markdown/src/lib.rs`,
`validate_ir_consistency` must additionally, for every region segment that
carries `Some(source)`, assert that
`source.get(span.byte_start..span.byte_end)` equals the segment text, returning
a new Markdown message with rule id `ir-segment-source-mismatch` on failure. It
must also assert that every `parent_region` resolves to a region id already
present in the document, and that `origin_nodes` is non-empty and references
real node ids, returning `ir-parent-region-unresolved` and
`ir-origin-nodes-invalid` respectively. Add the red tests first (in
`crates/stilyagi-markdown/src/tests/ir_consistency.rs`) by constructing an
`IrDocument` with a deliberately wrong source span, a dangling `parent_region`,
and an empty `origin_nodes`, and asserting each is rejected. Confirm the new
checks pass for all existing fixtures.

Second, the vocabulary single source of truth. In `crates/stilyagi-ir`, add a
`RegionKind` enum covering all eleven RFC 0001 v1 kinds (`heading`, `paragraph`,
`list_item`, `blockquote`, `table_cell`, `frontmatter`, `frontmatter_field`,
`image_alt`, `link_title`, `python_docstring`, `rust_doc_comment`) with
`as_str`, `TryFrom<&str>`, and an `ALL` slice. Keep `IrRegion.kind` serialized
as a `String` on the wire (so a newer producer's kind can deserialize in an
older consumer), but have the Markdown producer construct `kind` only from
`RegionKind::as_str`. Add a unit test asserting every `RegionKind::ALL`
round-trips through `as_str` and `TryFrom`, and that the set equals the RFC
vocabulary.

Third, centralize the synthetic-reason allow-list. Promote the
`SyntheticReason` variants' string mapping into a shared `ALL` (the canonical
home is alongside `SegmentOrigin`; if it must stay in `stilyagi-markdown`,
expose a `pub(crate)` `ALL`). Rewrite the test oracle
`synthetic_segments_use_known_reasons`
(`crates/stilyagi-markdown/src/tests.rs`) to derive its allow-list from that
constant rather than a hand-written `matches!`. No new reason is added in this
slice.

Run the targeted Rust gates, then the full gates:

```bash
cargo test -p stilyagi-ir -p stilyagi-markdown 2>&1 \
  | tee "/tmp/test-stage1-ir-md-stilyagi-${BRANCH}.out"
make check-fmt 2>&1 | tee "/tmp/check-fmt-stage1-stilyagi-${BRANCH}.out"
make typecheck 2>&1 | tee "/tmp/typecheck-stage1-stilyagi-${BRANCH}.out"
make lint 2>&1 | tee "/tmp/lint-stage1-stilyagi-${BRANCH}.out"
make test 2>&1 | tee "/tmp/test-stage1-stilyagi-${BRANCH}.out"
```

Run `coderabbit review --agent`, resolve concerns, and commit.

### Stage 2: executable success criterion and fixtures (red)

Write the coverage test before the emission code so the roadmap success
criterion is literally executable and observed failing first.

Add a test (in `crates/stilyagi-markdown/src/tests/coverage.rs`, included from
`src/tests.rs`) that reads every valid Markdown fixture, builds
`markdown_ir_document`, collects the set of region `kind`s, and asserts the
union contains the promised emitted set for this slice: `heading`, `paragraph`,
`list_item`, `blockquote`, `table_cell`, `frontmatter`, `image_alt`, and
`link_title`. (`frontmatter_field`, `python_docstring`, and `rust_doc_comment`
remain reserved and are explicitly excluded with a comment pointing at the ADR.)

Add the fixtures the test will need, respecting the suffix convention. Expected
new fixtures under `tests/fixtures/corpus/markdown/valid/`:

- `headings.md.fixture`: headings at several depths (covers `heading`, multiple
  `scope` depths).
- `lists.md.fixture`: an unordered list, an ordered list with a non-default
  `start`, and a GFM task list with checked and unchecked items (covers
  `list_item` and its child `paragraph` regions, ordered/unordered/task scope,
  and the stripped task marker).
- `blockquotes.md.fixture`: a single blockquote and a nested blockquote (covers
  `blockquote`, nesting depth scope).
- `table.md.fixture`: a standalone GFM table with header and body rows (covers
  `table_cell` with header-versus-body scope, independent of the shared
  fixture).
- `links-and-images.md.fixture`: an inline link with a title, a reference link
  with a separate definition, a GFM autolink, an inline image with alt text,
  and an image with an entity or escape in its alt text (covers `link_title`,
  `image_alt`, and the decoded fallback path).
- `frontmatter.md.fixture`: a YAML frontmatter block (covers `frontmatter` as a
  whole-block source-backed region). A TOML block may be added if its node span
  is confirmed faithful.

CRLF and adversarial fixtures are added in Stage 4. Run the coverage test and
confirm it fails because the new kinds are not yet emitted:

```bash
cargo test -p stilyagi-markdown coverage 2>&1 \
  | tee "/tmp/test-stage2-coverage-stilyagi-${BRANCH}.out"
```

Do not run the full gates yet; this stage intentionally leaves a red test.
Record the red evidence in `Progress`.

### Stage 3: emit the new region kinds (green)

Extend `MarkdownIrBuilder::push_region_for_node` and the flattener so each new
kind is emitted, satisfying the Stage 2 coverage test. Build region text only
through the `FlattenedRegion` helpers (or, for thin containers and frontmatter,
through the explicit segment constructors) so the reconstruction and re-slice
invariants hold by construction.

`heading`, `paragraph`, and `table_cell` keep their existing behaviour; add the
header-versus-body `scope` tag to `table_cell` by tracking whether a cell's row
is the table header row.

`list_item` and `blockquote` become thin structural regions. Emit the container
region before recursing into its children (pre-order) so its region id precedes
its descendants and `parent_region` always points backward. The container
region has empty `text` and empty `segments`, `origin_nodes` set to the
container node id, `owner: null`, a `scope` describing the construct, and
`attrs` capturing structural facts:

- `list_item` scope includes `markdown`, `list_item`, `ordered` or `unordered`,
  and `task` when applicable; `attrs` includes `ordered`, `spread`, `start`
  (for ordered lists), and `checked` (for task items, when present). Each child
  paragraph region of the item sets `parent_region` to the item region id and
  adds a `list_item` scope tag.
- `blockquote` scope includes `markdown`, `blockquote`, and a nesting depth tag;
  child paragraph regions set `parent_region` to the blockquote region id and
  add a `blockquote` scope tag.

`frontmatter` (mdast `Yaml` or `Toml`) becomes one region whose `text` is the
verbatim fenced block and whose single source-backed segment spans the node
position (fences included, no stripping). Its `attrs` records the frontmatter
format (`yaml` or `toml`).

`image_alt` (mdast `Image`) and `link_title` (mdast `Link` with `Some(title)`)
become regions whose `text` is the decoded alt or title string, emitted as a
single synthetic `decoded_text` segment. `origin_nodes` is the image or link
node id (which carries a real source span, so diagnostics remain locatable per
RFC invariant 5). `attrs` records `url` and, for links, `title`, plus
`source_backed: false`. A new `flatten_inline` arm for `Node::Image` is needed
so images inside paragraphs are handled; the alt-text region is emitted via
`push_region_for_node` on the image node. Place any decoded-value handling in
`source_text.rs` as a named helper if it grows beyond a trivial call.

For each new kind add per-kind structural assertions (region present, expected
text, expected scope and attrs, `parent_region` resolves, segments
source-backed or synthetic as designed) and an `insta` snapshot, extending the
parametrized table in `crates/stilyagi-markdown/src/tests.rs`. Then run:

```bash
cargo test -p stilyagi-ir -p stilyagi-markdown 2>&1 \
  | tee "/tmp/test-stage3-stilyagi-${BRANCH}.out"
make check-fmt 2>&1 | tee "/tmp/check-fmt-stage3-stilyagi-${BRANCH}.out"
make typecheck 2>&1 | tee "/tmp/typecheck-stage3-stilyagi-${BRANCH}.out"
make lint 2>&1 | tee "/tmp/lint-stage3-stilyagi-${BRANCH}.out"
make test 2>&1 | tee "/tmp/test-stage3-stilyagi-${BRANCH}.out"
```

Confirm the Stage 2 coverage test now passes. Run `coderabbit review --agent`,
resolve concerns, and commit.

### Stage 4: malformed, adversarial, and property coverage

Add malformed and adversarial fixtures and strengthen the invariants.

Under `tests/fixtures/corpus/markdown/malformed/`, keep `unclosed-table.md` and
add fixtures for unbalanced emphasis and a broken reference link. For each
malformed fixture add an extraction test that asserts `markdown_ir_document`
returns `Ok` (parser recovery), the document round-trips through canonical
JSON, every region satisfies the reconstruction and re-slice invariants, and
the flattened text of the degraded regions matches an `insta` snapshot so the
intended degradation is reviewed rather than assumed. Note in a comment that
suppression and `errors` emission belong to roadmap item 2.1.3, so
`IrDocument.errors` stays empty here.

Add CRLF variants for a list and a blockquote fixture (suffix `.md.fixture`,
protected by a scoped `.gitattributes` entry mirroring the existing CRLF
soft-break fixture) and a test asserting the checked-out bytes still contain
literal `\r\n`. Add adversarial fixtures for a deeply nested blockquote and an
empty list item, and assert region structure is well formed (no orphan or
empty-garbage region) and recursion is bounded.

Add `proptest` coverage in `crates/stilyagi-ir` (or `crates/stilyagi-markdown`)
asserting, for generated valid documents or generated link/image/list
constructs: every source-backed segment re-slices to its text; segments are
contiguous and reconstruct region text; `parent_region`, when present,
references an earlier region; and synthetic reasons come only from the
centralized allow-list. Prefer strategies that construct valid layouts directly
over filtering.

Add the Rust BDD feature. Create
`crates/stilyagi-markdown/tests/features/region_coverage.feature` with a
scenario stating that extracting the valid Markdown corpus yields at least one
region for each promised v1 Markdown kind, and wire it with `rstest-bdd`. Run:

```bash
cargo test -p stilyagi-ir -p stilyagi-markdown 2>&1 \
  | tee "/tmp/test-stage4-stilyagi-${BRANCH}.out"
make check-fmt 2>&1 | tee "/tmp/check-fmt-stage4-stilyagi-${BRANCH}.out"
make typecheck 2>&1 | tee "/tmp/typecheck-stage4-stilyagi-${BRANCH}.out"
make lint 2>&1 | tee "/tmp/lint-stage4-stilyagi-${BRANCH}.out"
make test 2>&1 | tee "/tmp/test-stage4-stilyagi-${BRANCH}.out"
```

Run `coderabbit review --agent`, resolve concerns, and commit.

### Stage 5: bridge parity and Python surface

Keep the Python surface minimal and compatible. The new region kinds flow
through `Document.ir` canonical JSON automatically because the bridge
serializes the whole `IrDocument`; the typed `Document.regions` list stays
`{kind, text}`.

Add a `supported_region_kinds()` pyfunction in
`crates/stilyagi-pyext/src/lib.rs` that returns `RegionKind::ALL` as strings
(mirroring `supported_syntaxes`), update `python/stilyagi/_stilyagi_rs.pyi`,
and validate region kinds in `python/stilyagi/engine/extraction.py` with a
pass-through-with-warning policy: an unknown kind is logged but not rejected,
because the vocabulary is still growing (in contrast to `syntax`, which rejects
unknowns). Add a Python unit test for the new function and the pass-through
policy. If a `syrupy` snapshot is affected (for example the golden round-trip
helper), update it only after reviewing the diff.

This stage is a `SHOULD`; if the `Tolerances` scope threshold is approached, the
`supported_region_kinds()` export and Python validation may be deferred to a
follow-up with a recorded `Decision Log` entry, provided the Rust `RegionKind`
single source of truth from Stage 1 remains. Run:

```bash
make build 2>&1 | tee "/tmp/build-stage5-stilyagi-${BRANCH}.out"
.venv/bin/python -m pytest -q tests 2>&1 \
  | tee "/tmp/pytest-stage5-stilyagi-${BRANCH}.out"
make check-fmt 2>&1 | tee "/tmp/check-fmt-stage5-stilyagi-${BRANCH}.out"
make typecheck 2>&1 | tee "/tmp/typecheck-stage5-stilyagi-${BRANCH}.out"
make lint 2>&1 | tee "/tmp/lint-stage5-stilyagi-${BRANCH}.out"
make test 2>&1 | tee "/tmp/test-stage5-stilyagi-${BRANCH}.out"
```

Run `coderabbit review --agent`, resolve concerns, and commit.

### Stage 6: documentation, ADR, and roadmap completion

Write `docs/adr-005-markdown-region-vocabulary-scope.md` as a Y-Statement ADR
(use the `arch-decision-records` skill) recording two decisions: that
`list_item` and `blockquote` are thin structural regions with prose in child
regions, and that `frontmatter_field` (and `image_alt` / `link_title`
byte-accurate source backing) are deferred, with the markdown-rs decoded-value
and YAML/TOML-parser rationale. Amend
`docs/rfcs/0001-stilyagi-intermediate-representation.md` to mark
`frontmatter_field` reserved and not-yet-emitted and to reference the ADR, so
the v1 vocabulary promise is corrected in the open rather than silently shrunk.

Update `docs/developers-guide.md` with the region-kind vocabulary single source
of truth (`RegionKind`), the thin-container convention, the documented `scope`
and `attrs` conventions per kind, the synthetic-only alt and title decision,
and the re-slice validator invariant. Update `docs/stilyagi-design.md` §6 and
§7.1 only to reflect resolved ambiguities (the scope and attrs conventions, the
deferral). Update `docs/users-guide.md` only if the supported Python surface
changed (the `supported_region_kinds()` function, if added).

Mark roadmap item 2.1.2 done in `docs/roadmap.md`. Run the documentation gates
and then the full gates:

```bash
make fmt 2>&1 | tee "/tmp/fmt-stage6-stilyagi-${BRANCH}.out"
make markdownlint 2>&1 | tee "/tmp/markdownlint-stage6-stilyagi-${BRANCH}.out"
make nixie 2>&1 | tee "/tmp/nixie-stage6-stilyagi-${BRANCH}.out"
make check-fmt 2>&1 | tee "/tmp/check-fmt-stage6-stilyagi-${BRANCH}.out"
make typecheck 2>&1 | tee "/tmp/typecheck-stage6-stilyagi-${BRANCH}.out"
make lint 2>&1 | tee "/tmp/lint-stage6-stilyagi-${BRANCH}.out"
make test 2>&1 | tee "/tmp/test-stage6-stilyagi-${BRANCH}.out"
```

Run `coderabbit review --agent`, clear concerns, and make the final feature
commit.

## Concrete steps

All commands run from the repository root. Refresh the `leta` workspace before
code navigation:

```bash
REPO_ROOT="$(pwd)"
leta workspace add "$REPO_ROOT"
```

Inspect symbols with `leta` rather than broad text search when a name is known:

```bash
leta show MarkdownIrBuilder.push_region_for_node
leta show validate_ir_consistency
leta show IrRegion
leta refs SyntheticReason
```

Use `rg` only for Markdown prose, configuration keys, fixtures, or snapshots:

```bash
rg -n "list_item|blockquote|frontmatter|image_alt|link_title" docs crates tests
```

After each milestone, inspect the changed files and the plan diff:

```bash
git status --short
git diff --stat
git diff -- docs/execplans/2-1-2-golden-fixture-coverage.md
```

Use file-based commit messages:

```bash
COMMIT_MSG_DIR="$(mktemp -d)"
cat > "$COMMIT_MSG_DIR/COMMIT_MSG.md" << 'ENDOFMSG'
Add Markdown region-kind golden fixture coverage (2.1.2)

Summarise the milestone specifics here.
ENDOFMSG
git commit -F "$COMMIT_MSG_DIR/COMMIT_MSG.md"
rm -rf "$COMMIT_MSG_DIR"
```

## Validation and acceptance

Acceptance for the implemented feature:

- The coverage test in `crates/stilyagi-markdown` fails before Stage 3 and
  passes
  after it; the union of region `kind`s across valid Markdown fixtures contains
  `heading`, `paragraph`, `list_item`, `blockquote`, `table_cell`,
  `frontmatter`, `image_alt`, and `link_title`.
- Each promised kind has a dedicated fixture, per-kind structural assertions,
  and a
  stable `insta` snapshot.
- `list_item` and `blockquote` regions carry no prose text; their child
  paragraph
  regions set `parent_region` to the container region id, and `parent_region`
  always references an earlier region.
- `frontmatter` regions are one source-backed segment over the whole fenced
  block;
  `image_alt` and `link_title` regions are single synthetic `decoded_text`
  segments with `source_backed: false` in `attrs`.
- The production validator rejects a source-backed segment whose span does not
  equal its text (`ir-segment-source-mismatch`), a dangling `parent_region`,
  and empty or invalid `origin_nodes`.
- Malformed fixtures extract without panic, round-trip stably, satisfy the
  reconstruction and re-slice invariants, and have their degraded text
  snapshotted; `IrDocument.errors` remains empty (suppression and error
  emission are 2.1.3).
- `proptest` invariants hold for generated documents and constructs; the Rust
  BDD
  region-coverage scenario passes.
- The Python `Document.ir` continues to expose the canonical IR JSON including
  the
  new kinds; existing Python callers are unaffected; `supported_region_kinds()`
  (if added) returns the full RFC vocabulary and unknown kinds pass through
  with a warning.
- `docs/adr-005-markdown-region-vocabulary-scope.md` exists, RFC 0001 marks
  `frontmatter_field` reserved, and the developers' guide documents the
  conventions.
- `docs/roadmap.md` marks only item 2.1.2 done.

Required gates after each major milestone, captured with `tee` into `/tmp`:

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

CodeRabbit validation runs after the deterministic gates pass for each
milestone:

```bash
coderabbit review --agent
```

CodeRabbit is not used to find deterministic format, lint, type, or test
failures that local gates can catch. If CodeRabbit is rate-limited, wait with
`vsleep "$(shuf -i 15-30 -n 1)m"` before retrying.

## Idempotence and recovery

Most steps are additive and safe to rerun: tests, snapshot verification, and
the four full gates. Snapshot update commands
(`INSTA_UPDATE=always cargo test -p stilyagi-markdown`,
`pytest --snapshot-update`) are safe only after the implementation diff has
been reviewed; if an update captures unintended field churn, revert only the
snapshot changes from that milestone and fix the builder or serializer before
updating again.

If a new region kind cannot be emitted without span drift or a new dependency,
do not invent an ad hoc parser or an unverified byte scan; record the blocker
in the `Decision Log` and stop for approval. If a gate fails because of
unrelated user changes, do not revert them; record the failure and work around
or escalate.

Avoid destructive Git operations. Prefer new commits, targeted patches, or a
scratch branch, and request approval before any operation that would discard
work.

## Interfaces and dependencies

The IR vocabulary single source of truth lives in `crates/stilyagi-ir`.
Expected shape:

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RegionKind {
    Heading,
    Paragraph,
    ListItem,
    Blockquote,
    TableCell,
    Frontmatter,
    FrontmatterField,
    ImageAlt,
    LinkTitle,
    PythonDocstring,
    RustDocComment,
}

impl RegionKind {
    pub const ALL: &'static [RegionKind];
    #[must_use]
    pub const fn as_str(self) -> &'static str;
}

impl TryFrom<&str> for RegionKind {
    type Error = /* a small invalid-kind error */;
}
```

`IrRegion.kind` stays a serialized `String`; the Markdown producer constructs
it only via `RegionKind::as_str`. The Markdown builder
(`crates/stilyagi-markdown/src/lib.rs`) gains thin-container emission for
`Node::List` items and `Node::Blockquote`, whole-block emission for
`Node::Yaml` and `Node::Toml`, and synthetic alt and title emission for
`Node::Image` and `Node::Link`. The production validator
`validate_ir_consistency` gains the `ir-segment-source-mismatch`,
`ir-parent-region-unresolved`, and `ir-origin-nodes-invalid` checks.

The PyO3 bridge (`crates/stilyagi-pyext`) may add:

```rust
#[pyfunction]
fn supported_region_kinds() -> Vec<String>;
```

mirroring `supported_syntaxes`. No new external crate dependency is expected.

## Progress

- [x] (2026-06-12) Loaded `leta`, `hexagonal-architecture`, `python-router`,
  `rust-router`, and `execplans`; created the `leta` workspace.
- [x] (2026-06-12) Ran a planning agent team: one agent mapped the IR
  region-emission, flattener, validator, fixture, bridge, and Makefile
  surfaces; one used Firecrawl plus the installed crate source to resolve
  markdown-rs mdast node shapes and span fidelity.
- [x] (2026-06-12) Ran a Logisphere community-of-experts design review
  (Pandalump, Telefono, Doggylump, Wafflecat) and revised the design:
  production validator re-slice, thin structural containers, synthetic-only alt
  and title, `RegionKind` single source of truth, and an ADR-routed
  `frontmatter_field` deferral.
- [x] (2026-06-12) Drafted this pre-implementation ExecPlan.
- [x] Stage 0: record approval and run baseline gates. Approval recorded;
  baseline gates passed on 2026-06-14.
- [x] Stage 1: correctness scaffolding (validator re-slice, `RegionKind`,
  synthetic-reason allow-list). Implemented and locally gated on 2026-06-14.
- [x] Stage 2: coverage test red plus new valid fixtures. Red evidence
  recorded; commit deferred until Stage 3 makes the test green.
- [x] Stage 3: emit `list_item`, `blockquote`, `frontmatter`, `image_alt`,
  `link_title`; coverage test green. Implemented and locally gated on
  2026-06-14.
- [x] Stage 4: malformed, CRLF, adversarial, `proptest`, and BDD coverage.
  Implemented, locally gated, and CodeRabbit review attempted on 2026-06-14.
- [x] Stage 5: bridge parity and `supported_region_kinds()`. Implemented and
  locally gated, and CodeRabbit review attempted on 2026-06-14.
- [ ] Stage 6: ADR, RFC amendment, guides, and roadmap completion.

## Surprises & Discoveries

- Observation: the build-time IR validator never re-slices source-backed
  segments,
  so source span drift is undetectable today. Evidence:
  `validate_ir_consistency` (`crates/stilyagi-markdown/src/lib.rs`) calls only
  `segments_reconstruct_text`, which checks contiguity and concatenated segment
  text but never reads the source buffer. Impact: Stage 1 closes this before
  any new kind is added.

- Observation: markdown-rs discards positioned child `Text` nodes for images and
  exposes alt and title only as decoded strings, so byte-accurate alt and title
  spans require a secondary scan that is prone to first-match drift. Evidence:
  the Firecrawl and installed-source review of
  `markdown-1.0.0/src/to_mdast.rs`. Impact: alt and title are synthetic-only in
  this slice.

- Observation: `list_item` and `blockquote` contain block children that already
  emit their own paragraph regions, so a prose-bearing container would
  double-cover prose and force a block-aware flattener refactor. Evidence: the
  design review and the inline-only `flatten_inline` dispatcher. Impact: thin
  structural containers were chosen, eliminating the need for a block-separator
  synthetic reason.

- Observation: the clean implementation branch passed all baseline gates before
  code changes. Evidence: `make check-fmt`, `make typecheck`, `make lint`, and
  `make test` all exited successfully with logs at
  `/tmp/check-fmt-stilyagi-2-1-2-golden-fixture-coverage.out`,
  `/tmp/typecheck-stilyagi-2-1-2-golden-fixture-coverage.out`,
  `/tmp/lint-stilyagi-2-1-2-golden-fixture-coverage.out`, and
  `/tmp/test-stilyagi-2-1-2-golden-fixture-coverage.out`. Impact: later gate
  failures can be attributed to this implementation unless new external
  changes appear.

- Observation: the Stage 1 red-first validator tests failed before production
  changes, as intended. Evidence:
  `/tmp/test-stage1-red-ir-consistency-stilyagi-2-1-2-golden-fixture-coverage.out`
  shows failures for `ir-segment-source-mismatch`,
  `ir-parent-region-unresolved`, and `ir-origin-nodes-invalid`. Impact: the
  new validator checks are proven to cover a previously missing behaviour.

- Observation: Stage 1 deterministic gates passed after implementation.
  Evidence: `cargo test -p stilyagi-ir -p stilyagi-markdown`,
  `make check-fmt`, `make typecheck`, `make lint`, and `make test` exited
  successfully with stage-specific logs under `/tmp`. Impact: the validator,
  IR vocabulary, and synthetic-reason changes are locally reviewable.

- Observation: `coderabbit review --agent` started twice for Stage 1 and hung
  after sandbox setup both times without findings or a rate-limit response.
  Evidence: the first run emitted `preparing_sandbox` and stayed silent for
  more than five minutes before PID `1447066` was terminated; the retry emitted
  the same setup status and stayed silent for several minutes before PID
  `1458412` was terminated. Impact: CodeRabbit concerns could not be obtained
  for this milestone; no actionable concerns were available to clear.

- Observation: the Stage 2 coverage test fails before new region emission is
  implemented, as intended. Evidence:
  `/tmp/test-stage2-coverage-stilyagi-2-1-2-golden-fixture-coverage.out`
  shows `valid_markdown_corpus_covers_promised_markdown_region_kinds` failing
  because `list_item` is absent from the emitted valid-corpus kind set. Impact:
  the roadmap success criterion is now executable and red before Stage 3.

- Observation: Stage 3 emits the promised Markdown region kinds and the
  coverage test is green. Evidence:
  `/tmp/test-stage3-coverage-stilyagi-2-1-2-golden-fixture-coverage.out`
  and `/tmp/test-stage3-stilyagi-2-1-2-golden-fixture-coverage.out` show the
  valid Markdown corpus coverage and full test gates passing. Impact:
  `heading`, `paragraph`, `list_item`, `blockquote`, `table_cell`,
  `frontmatter`, `image_alt`, and `link_title` now appear in dedicated valid
  fixtures and snapshots.

- Observation: markdown-rs frontmatter node spans include the opening and
  closing fences but not the trailing newline after the closing fence. Evidence:
  the `frontmatter` and `yaml_frontmatter` snapshots show source-backed
  frontmatter text ending with `---`, while the following blank line is outside
  the node span. Impact: Stage 3 assertions check the fenced block itself
  rather than requiring the separator newline to be part of the region text.

- Observation: the Stage 3 `coderabbit review --agent` run repeated the
  sandbox-setup hang seen in Stage 1. Evidence: the run emitted
  `preparing_sandbox`, stayed silent for more than two minutes, and PID
  `1474292` was terminated after confirming it belonged to this worktree.
  Impact: CodeRabbit concerns were again unavailable; deterministic gates
  remained green.

- Observation: the first Stage 3 implementation pushed Markdown extraction
  responsibilities back toward an over-large `lib.rs`. The builder traversal
  now lives in `crates/stilyagi-markdown/src/builder.rs` and region construction
  lives in `crates/stilyagi-markdown/src/region_emission.rs`. Evidence:
  `wc -l crates/stilyagi-markdown/src/lib.rs
  crates/stilyagi-markdown/src/builder.rs
  crates/stilyagi-markdown/src/region_emission.rs
  crates/stilyagi-markdown/src/tests/coverage.rs` reports 331, 148, 346, and
  234 lines respectively. Impact: the touched Rust files stay below the
  repository's 400-line limit while preserving the green Stage 3 gates.

- Observation: Stage 4 adds malformed recovery snapshots, literal CRLF fixture
  guards, adversarial nested-blockquote and empty-list-item assertions,
  Markdown-generated `proptest` invariant coverage, and an `rstest-bdd`
  region-coverage scenario. Evidence:
  `/tmp/test-stage4-targeted-stilyagi-2-1-2-golden-fixture-coverage.out`
  shows 48 `stilyagi-markdown` tests passing after the malformed snapshots
  were accepted, and `/tmp/test-stage4-stilyagi-2-1-2-golden-fixture-coverage.out`
  shows the full `make test` gate passing with 168 Rust tests and 97 Python
  tests. Impact: parser recovery, CRLF checkout fidelity, parent-region
  ordering, source re-slicing, segment contiguity, and synthetic-reason
  allow-list invariants are now exercised against both fixtures and generated
  Markdown constructs.

- Observation: Stage 4 keeps the new focused Rust files below the repository
  size limit. Evidence: `wc -l` reports 127 lines for
  `crates/stilyagi-markdown/src/region_coverage_bdd.rs`, 122 for
  `crates/stilyagi-markdown/src/tests/malformed.rs`, 72 for
  `crates/stilyagi-markdown/src/tests/properties.rs`, 226 for
  `crates/stilyagi-markdown/src/tests.rs`, and 333 for
  `crates/stilyagi-markdown/src/lib.rs`. Impact: the additional coverage does
  not require another test-module split.

- Observation: the Stage 4 `coderabbit review --agent` run repeated the
  sandbox-setup hang seen in the earlier review attempts. Evidence: the run
  emitted `preparing_sandbox`, stayed silent for more than two minutes, and PID
  `1519252` was terminated after confirming it belonged to this worktree.
  Impact: CodeRabbit concerns were again unavailable; deterministic gates
  remained green and no rate-limit response was emitted.

- Observation: Stage 5 exposes the canonical IR region-kind vocabulary through
  `stilyagi._stilyagi_rs.supported_region_kinds()` and validates canonical IR
  region kinds in the Python adapter with a warn-and-preserve policy for
  unknown future kinds. Evidence:
  `/tmp/build-stage5-stilyagi-2-1-2-golden-fixture-coverage.out`,
  `/tmp/pytest-stage5-stilyagi-2-1-2-golden-fixture-coverage.out`,
  `/tmp/check-fmt-stage5-stilyagi-2-1-2-golden-fixture-coverage.out`,
  `/tmp/typecheck-stage5-stilyagi-2-1-2-golden-fixture-coverage.out`,
  `/tmp/lint-stage5-stilyagi-2-1-2-golden-fixture-coverage.out`, and
  `/tmp/test-stage5-stilyagi-2-1-2-golden-fixture-coverage.out` all passed.
  Impact: Python can query the Rust IR vocabulary, and future IR kinds are
  observable without breaking existing callers.

- Observation: the legacy Python `Document.regions` compatibility list still
  carries `stilyagi-extract`'s coarse `document` kind, which is not part of
  `stilyagi-ir::RegionKind::ALL`. Evidence:
  `crates/stilyagi-extract/src/lib.rs` defines the bridge `RegionKind::Document`
  separately from the canonical IR region vocabulary. Impact: Stage 5 applies
  unknown-kind warnings only to canonical `Document.ir["regions"]`, avoiding a
  warning on every current Markdown extraction.

- Observation: the Stage 5 `coderabbit review --agent` run repeated the
  sandbox-setup hang seen in earlier review attempts. Evidence: the run emitted
  `preparing_sandbox`, stayed silent for more than two minutes, and PID
  `1530011` was terminated after confirming it belonged to this worktree.
  Impact: CodeRabbit concerns were again unavailable; deterministic gates
  remained green and no rate-limit response was emitted.

## Decision Log

- Decision: keep `Status: DRAFT` and block implementation until explicit
  approval.
  Rationale: the execplans approval gate and the user's standing instruction
  that plans are approved before implementation. Date/Author: 2026-06-12,
  planning agent.

- Decision: adopt thin structural `list_item` and `blockquote` regions (no
  prose,
  prose in child regions via `parent_region`) rather than prose-bearing
  containers with a block-separator synthetic. Rationale: the design panel
  converged that prose-bearing containers double-cover bytes, make
  `origin_nodes` ambiguous, create dual fix targets, and force an
  inline-to-block flattener refactor; the coverage criterion only requires the
  kinds to exist as regions, which thin containers satisfy with near-zero
  invariant risk. The prose-bearing alternative is recorded here so the user
  may choose it at approval. Date/Author: 2026-06-12.

- Decision: emit `image_alt` and `link_title` as synthetic `decoded_text`
  segments
  in this slice rather than attempting byte-accurate source backing. Rationale:
  markdown-rs decodes these to strings without sub-positions; a first-match
  byte scan risks source-backing the wrong occurrence and corrupting future
  fixes; synthetic-only is never wrong and is additive to improve later.
  Date/Author: 2026-06-12.

- Decision: defer `frontmatter_field` and route the deferral through ADR-005
  plus
  an RFC 0001 amendment rather than silently shrinking the vocabulary.
  Rationale: field-level spans need a YAML/TOML parser (a new dependency) and
  would otherwise produce plausible-but-wrong spans; RFC 0001 marks the kind
  `SHALL`, so the promise must be corrected in the open. Date/Author:
  2026-06-12.

- Decision: introduce a `RegionKind` single source of truth in `stilyagi-ir`
  (wire type stays `String`) and centralize the synthetic-reason allow-list.
  Rationale: 2.1.2 is the first slice to add several kinds at once and precedes
  three more; enum-gating construction now is the cheapest moment to prevent
  typo and producer/consumer drift. Date/Author: 2026-06-12.

- Decision: proceeded with the conservative defaults (defer `frontmatter_field`;
  expose new kinds via `Document.ir` only) after the scoping clarification
  question was not answered. Rationale: both defaults are reversible at
  approval and avoid new dependencies or public-surface churn. Date/Author:
  2026-06-12.

- Decision: implementation is approved and may proceed. Rationale: the user
  explicitly requested implementation of the planned functionality in
  `docs/execplans/2-1-2-golden-fixture-coverage.md`. Date/Author: 2026-06-14,
  implementation agent.

- Decision: continue after Stage 1 despite unavailable CodeRabbit output.
  Rationale: all deterministic gates passed, CodeRabbit was attempted twice as
  requested and produced no findings or rate-limit response, and both hung
  processes were limited to this worktree and terminated without affecting
  other agents. Date/Author: 2026-06-14, implementation agent.

- Decision: continue after Stage 3 despite unavailable CodeRabbit output.
  Rationale: all applicable deterministic gates passed; CodeRabbit was
  requested after the milestone and produced no findings or rate-limit response
  before hanging at sandbox setup; the hung process was limited to this
  worktree and terminated without affecting other agents. Date/Author:
  2026-06-14, implementation agent.

- Decision: continue after Stage 4 despite unavailable CodeRabbit output.
  Rationale: all applicable deterministic gates passed; CodeRabbit was
  requested after the milestone and again produced no findings or rate-limit
  response before hanging at sandbox setup; the hung process was limited to
  this worktree and terminated without affecting other agents. Date/Author:
  2026-06-14, implementation agent.

- Decision: continue after Stage 5 despite unavailable CodeRabbit output.
  Rationale: all applicable deterministic gates passed; CodeRabbit was
  requested after the milestone and again produced no findings or rate-limit
  response before hanging at sandbox setup; the hung process was limited to
  this worktree and terminated without affecting other agents. Date/Author:
  2026-06-14, implementation agent.

## Outcomes & Retrospective

To be completed at milestones and at completion. Compare the delivered region
coverage against the roadmap success criterion (every promised v1 Markdown
region kind exercised by at least one fixture), note whether the thin-container
model held up, and record any region kind that had to be blocked or deferred.

## Revision note

Initial draft. Captures the planning reconnaissance (region emission,
flattener, validator, fixtures, bridge, Makefile gates), the Firecrawl and
installed-source findings on markdown-rs mdast span fidelity, and the
Logisphere design review that reshaped the design toward a validator re-slice,
thin structural containers, synthetic-only alt and title, a `RegionKind` single
source of truth, and an ADR-routed `frontmatter_field` deferral. No
implementation has begun; the plan awaits approval.
