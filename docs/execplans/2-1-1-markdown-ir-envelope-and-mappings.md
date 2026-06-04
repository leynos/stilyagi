# Implement the Markdown IR envelope and segment mappings

This ExecPlan (execution plan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work
proceeds.

Status: DRAFT

## Purpose / big picture

Roadmap item 2.1.1 makes the Markdown extractor produce a first-class
intermediate representation (IR) envelope so the rest of the v1 product can be
built against a trustworthy contract. After this slice, Markdown extraction
should return a versioned envelope that carries source-faithful byte spans, a
canonical `line_index`, region text with explicit `segments` mappings (covering
synthetic insertions such as soft-break spaces), a `content_hash`, and a
producer record. Canonical JSON serialization of that envelope should
round-trip representative Markdown fixtures without span drift.

The observable outcomes are:

- A Rust extractor that accepts Markdown source and returns an `IrDocument`
  whose canonical JSON validates against the IR contract described in RFC 0001
  section 4.
- A PyO3 bridge function that returns the same envelope to Python, plus a
  canonical JSON parity field so Python tests can confirm the bridge wire
  format has not drifted from the Rust serializer.
- A typed Python `model.Document` surface that exposes `line_index`,
  `content_hash`, regions, and `segments` without requiring callers to read the
  raw bridge dictionary.
- Golden snapshots (`insta` in Rust and `syrupy` in Python) and property tests
  (`proptest`) that prove segments concatenate exactly to region text for
  every representative Markdown shape covered by 2.1.1.

This slice deliberately stops short of comprehensive Markdown region coverage,
suppression parsing, owner metadata, and CLI surfaces. Those are 2.1.2, 2.1.3,
2.2.x and slice-3 deliverables respectively. The aim is to land the envelope
plus enough region kinds to prove the segments model, not to ship the full v1
extractor in one slice.

## Context and orientation

Stilyagi is a mixed Rust and Python repository. Rust crates live under
`crates/`; the Python package lives under `python/stilyagi/`; shared corpus
fixtures live under `tests/fixtures/corpus/`; Python tests live under `tests/`;
and Python behaviour-driven development (BDD) feature files live under
`features/`. The bridge that lets Python call into Rust is the PyO3 extension
crate `crates/stilyagi-pyext/`, exposed as the runtime module
`stilyagi._stilyagi_rs`.

Roadmap item 1.1.3 narrowed the v1 contract scope. Roadmap item 1.2.2 added
the first live Rust-to-Python bridge that currently returns `{syntax, regions:
[{kind, text}]}` for Markdown sources. Roadmap item 1.3.1 added the shared
fixture corpus under `tests/fixtures/corpus/`. Roadmap item 1.3.2 added
internal golden-IR helpers and edit round-trip helpers inside
`crates/stilyagi-test-support/`. Roadmap item 1.3.3 added structural
performance probes.

The current implementation touchpoints are:

- `crates/stilyagi-ir/src/lib.rs` is still a marker crate. It owns
  `line_index_for` and the `IrBoundary` unit type. It is the natural home for
  production IR data transfer objects (DTOs) added by this slice.
- `crates/stilyagi-markdown/src/lib.rs` is a marker crate today. It is the
  natural home for the `markdown-rs` (mdast) adapter, the inline flattener,
  and the segments-builder added by this slice.
- `crates/stilyagi-extract/src/lib.rs` is the orchestration layer. It currently
  owns `ExtractDocument`, `ExtractRegion`, `RegionKind`, `ExtractSyntax`,
  `ExtractError`, and `extract_document`. After this slice, orchestration
  delegates to `stilyagi-markdown` for region production, computes the line
  index and content hash in-house, and returns an `IrDocument`.
- `crates/stilyagi-pyext/src/lib.rs` is the PyO3 driving adapter. It currently
  exposes `extract_document_py`, which returns a narrow dictionary. After this
  slice, it also exposes a new entrypoint that returns the full IR envelope as
  a Python dictionary plus a canonical JSON parity field.
- `crates/stilyagi-test-support/src/golden_ir.rs` and
  `golden_fixture_builder.rs` host the dev-only `GoldenDocument`,
  `GoldenRegion`, `Segment`, `ByteSpan` shapes plus their canonical JSON
  serializer and the Markdown fixture builder. After this slice, the
  golden-fixture builder produces an `IrDocument`-derived snapshot rather than
  a parallel narrower shape.
- `python/stilyagi/engine/extraction.py` is the typed adapter that wraps the
  PyO3 bridge into `model.Document`. After this slice, it exposes a
  document-shaped typed surface plus `Document.from_canonical_json` for parity
  testing.
- `python/stilyagi/model/document.py` and `python/stilyagi/model/region.py`
  hold the typed model surface. After this slice, they carry `DocumentMeta`,
  `Producer`, segment kinds, and the expanded `Region` shape.
- The `python/stilyagi/_stilyagi_rs.pyi` stub declares the PyO3 bridge
  signature for Python type checkers. After this slice, the stub describes the
  new extractor entrypoint and the canonical JSON parity field.

The shared validation corpus currently contains:

- `tests/fixtures/corpus/markdown/valid/heading-table-link-suppression.md`
- `tests/fixtures/corpus/markdown/malformed/unclosed-table.md`
- Python and Rust valid and malformed fixtures that 2.1.1 must not touch.

There is no frontmatter fixture, no inline-markup paragraph fixture, and no
soft-break fixture in the current corpus. This slice adds those because the
segments model cannot be proven without them. The roadmap entry for 1.3.1
lists "headings, tables, links, docstrings, documentation comments,
suppressions, and error recovery cases", but the present corpus omits
paragraph-shaped Markdown samples and frontmatter samples. Adding the gap
fixtures as part of 2.1.1 is the cleanest option; the alternative (amending
1.3.1 retroactively) is recorded in `Decision Log` for visibility.

Definitions used in this plan:

- IR means intermediate representation: Stilyagi's source-faithful document
  payload, contract-described in RFC 0001.
- Envelope means the top-level IR document object defined by RFC 0001 section
  4, including `schema_version`, `document`, `producers`, `line_index`,
  `trees`, `nodes`, `regions`, `suppressions`, `errors`, and `metadata`.
- Region text means the flattened lintable surface that rules see. It is not
  always a contiguous source slice; for Markdown paragraphs, it omits inline
  markup delimiters and replaces soft breaks with single spaces.
- Segment means a mapping entry that ties a slice of region text back to
  original source bytes (source segment) or marks the slice as inserted by the
  extractor (synthetic segment). Synthetic segments cover soft-break spaces
  and hard-break newlines.
- mdast means the Markdown abstract syntax tree produced by the `markdown-rs`
  crate, with `unist::Position { start: Point, end: Point }` byte offsets.
- Hexagonal architecture means an inner domain isolated from infrastructure
  through ports and adapters. For this slice: `stilyagi-ir` is the inner
  domain; `stilyagi-markdown` is the inbound parser adapter; `stilyagi-pyext`
  is the inbound driving adapter for Python callers.

## Documentation and skill signposts

The implementer should keep these repository documents open while executing
the plan:

- [docs/roadmap.md](../roadmap.md) section 2.1 for the exact dependency
  checkbox.
- [docs/stilyagi-design.md](../stilyagi-design.md) sections 6, 7.1, and 11 for
  the target IR contract, repository layout, and validation plan.
- [docs/rfcs/0001-stilyagi-intermediate-representation.md](../rfcs/0001-stilyagi-intermediate-representation.md)
  for the full envelope vocabulary, region invariants, and serialization
  rules.
- [docs/rfcs/0003-stilyagi-cli-contract.md](../rfcs/0003-stilyagi-cli-contract.md)
  for the future `dump-ir` command that this slice's canonical JSON output
  will feed.
- [docs/adr-002-packaging-boundary.md](../adr-002-packaging-boundary.md) for
  the accepted PyO3 plus `maturin` boundary.
- [docs/adr-003-v1-contract-scope.md](../adr-003-v1-contract-scope.md) for the
  English-only locale promise, the canonical JSON debug requirement, and the
  stable v1 syntax surface.
- [docs/complexity-antipatterns-and-refactoring-strategies.md](../complexity-antipatterns-and-refactoring-strategies.md)
  to keep helper abstractions small and avoid premature framework code.
- [docs/rust-testing-with-rstest-fixtures.md](../rust-testing-with-rstest-fixtures.md)
  for Rust `rstest` fixture style.
- [docs/rust-doctest-dry-guide.md](../rust-doctest-dry-guide.md) for doctest
  expectations on any new documented Rust API.
- [docs/reliable-testing-in-rust-via-dependency-injection.md](../reliable-testing-in-rust-via-dependency-injection.md)
  for explicit input or output and deterministic test helper design.
- [docs/rstest-bdd-users-guide.md](../rstest-bdd-users-guide.md) for Rust BDD
  tests with `rstest-bdd`.
- [docs/developers-guide.md](../developers-guide.md) for maintainer-facing
  testing conventions and the current internal helper inventory.
- [docs/users-guide.md](../users-guide.md) for user-visible promises; do not
  update this in 2.1.1 because there is no new user-visible behaviour.
- [docs/repository-layout.md](../repository-layout.md) for the crate and
  package map; update it only if this slice changes which directories are
  authoritative.
- [docs/execplans/1-3-2-round-trip-test-helpers.md](1-3-2-round-trip-test-helpers.md)
  for the style and structure that this plan deliberately matches, including
  internal helper boundaries and snapshot quality rules.

The relevant skills are:

- `execplans` to keep this plan current and approval-gated.
- `leta` for symbol-aware code navigation before changes.
- `hexagonal-architecture` to keep the domain crate free of adapter concerns.
- `rust-router`, then `arch-crate-design`, because this slice gives marker
  crates real responsibilities and must keep public and internal boundaries
  clear.
- `rust-types-and-apis` for the new IR DTO type signatures.
- `rust-errors` for the new extractor error types.
- `rust-memory-and-state` if borrow checking around mdast walking needs care.
- `proptest` for the segments-concatenation invariant.
- `nextest` if targeted Rust test execution needs `cargo nextest`.
- `python-router`, then `python-data-shapes` for the dataclass surface.
- `python-types-and-apis` if the typed surface grows generics or protocols.
- `python-testing` and `hypothesis` for Python test design (do not add new
  Python property tests unless an invariant emerges).
- `commit-message`, `pr-creation`, and `en-gb-oxendict` when preparing
  commits and the draft pull request.
- Run `coderabbit review --agent` after each major milestone and resolve all
  actionable concerns before moving on.

External tooling references resolved during planning:

- `markdown-rs` exposes `to_mdast(value, &ParseOptions) -> Result<Node,
  Message>` and `unist::Position { start: Point { line, column, offset }, end:
  Point { ... } }`, with `offset` as a UTF-8 byte index into the source. See
  <https://docs.rs/markdown/latest/markdown/>.
- The mdast Node vocabulary is documented at
  <https://docs.rs/markdown/latest/markdown/mdast/index.html>.
- mdast positional fidelity for soft breaks: soft breaks live as embedded
  newlines inside `mdast::Text` values; hard breaks are explicit `mdast::Break`
  nodes.
- `sha2` is the canonical Rust SHA-2 crate at <https://docs.rs/sha2/>.
- `insta` snapshot reviewing is documented at <https://insta.rs/docs/>.
- `syrupy` JSON snapshot extensions are documented at
  <https://syrupy-project.github.io/syrupy/>.
- `proptest` strategies for recursive grammars are documented at
  <https://docs.rs/proptest/>.

## Constraints

- Do not implement this plan until it is explicitly approved.
- Keep `crates/stilyagi-ir` free of PyO3 dependencies, IO, and the
  `markdown` crate. The IR crate is the inner domain; only `stilyagi-markdown`
  may depend on `markdown-rs`, and only `stilyagi-pyext` may depend on PyO3.
- Do not freeze the PyO3 bridge dictionary as a public Python contract. The
  supported Python surface is `stilyagi.model.Document` and its typed
  children. The bridge dictionary is an internal mirror of the canonical IR
  envelope. Parity is asserted by reconstructing canonical JSON from the
  Python typed model and comparing against the Rust serializer's snapshot;
  the bridge dictionary itself does not carry a `_canonical_json` field, so
  the parity oracle is not self-referential.
- Do not claim Python docstring or Rust documentation-comment IR support in
  this slice. The new envelope is Markdown-only. `extract_document` for
  Python or Rust syntaxes must continue to return the existing
  `NotImplementedError` mapping.
- Preserve the existing `stilyagi.engine.extract_document` adapter as a
  Markdown-only typed surface. If it must change shape to expose envelope
  fields, the change must be additive: existing callers must keep compiling
  and behaving identically.
- Preserve the existing `extract_document_py` PyO3 entry point during this
  slice. Adding the new entry point is allowed; removing the old one happens
  in a follow-up commit after every internal caller has migrated.
- Hold every RFC 0001 section 7 region invariant. The segments concatenation
  invariant (`concat(segment.text) == region.text`) is the most important;
  back it with a `proptest`. Synthetic segments must never carry source bytes;
  source segments must carry text that exactly matches their byte range in
  the source. Fixes must never target synthetic spans (this slice does not
  apply fixes, but the segment classification must be preserved end to end so
  later slices can rely on it).
- Canonical JSON is the supported debug and golden-fixture form for the IR.
  Snapshots compare canonical JSON, not ad hoc string fragments. The Rust
  serializer and the Python serializer must produce byte-identical output for
  the same fixture, and that parity must be asserted in tests.
- Canonical JSON style is fixed across Rust and Python serializers:
  - UTF-8 only.
  - Two-space indentation with `\n` line endings throughout. A single trailing
    `\n` byte ends the document.
  - Object keys are sorted byte-wise (lexicographic on UTF-8 bytes).
  - Numbers are emitted as decimal integers with no leading zero. Floating
    point values are rejected at the serializer; non-finite floats cause an
    error (debug builds may panic).
  - String escapes follow the reduced set already in use by
    `stilyagi-test-support`: `\"`, `\\`, `\n`, `\r`, `\t`, and `\uXXXX` for
    any other control character below 0x20. Forward slash is not escaped.
  - Enum spellings use lowercase snake_case (`"softbreak_space"`,
    `"hardbreak_newline"`, `"heading"`, `"paragraph"`, `"frontmatter"`,
    `"source"`, `"synthetic"`).
- The content hash must be computed over the raw source bytes received by the
  extractor, not over normalized text. The format is `"sha256:<lowercase
  hex>"`.
- `schema_version` MUST be `"1.0.0"`. `Document.from_canonical_json` and the
  Rust round-trip constructor MUST reject any envelope whose major version is
  not `1` (RFC 0001 section 9). Minor and patch differences MUST be accepted;
  unknown object fields MUST be ignored within the same major version.
- Error variants returned through `Result<IrDocument, ExtractError>` must
  respect the workspace clippy lint `result_large_err = "deny"`. Variants
  larger than three pointer-widths must be `Box`-wrapped. A
  `static_assertions::const_assert!` (or equivalent compile-time check) MUST
  pin the size of `ExtractError`.
- Rust enums that appear in canonical JSON MUST use `#[serde(rename_all =
  "snake_case")]` or, when serialization is handled by the bespoke serializer,
  emit the lowercase snake_case spelling and a unit test MUST pin every
  spelling.
- The IR envelope MUST distinguish fatal extraction failures from recoverable
  parse anomalies. Fatal failures return `Err(ExtractError)` and do not
  produce an envelope. Recoverable anomalies populate the envelope's `errors`
  array and allow extraction to continue. In 2.1.1 the conservative cut is:
  any failure raised by `markdown::to_mdast` is treated as fatal; recoverable
  anomalies are deferred to 2.1.2. Stage D pins this policy with at least one
  unit test per branch.
- `markdown::to_mdast` calls MUST be wrapped in `std::panic::catch_unwind`
  (or a documented equivalent) so a panic in the third-party parser cannot
  cross the PyO3 boundary as a `PanicException`. Convert any caught panic to a
  fatal `ExtractError` variant.
- Do not introduce a new public CLI surface in this slice. `dump-ir` belongs
  in 2.2.3.
- Use `rstest` for Rust unit tests, `pytest` for Python unit tests,
  `rstest-bdd` for Rust behaviour tests, and `pytest-bdd` for Python behaviour
  tests.
- Use `insta` for Rust snapshots and `syrupy` for Python snapshots where
  output format consistency is relevant. Snapshots must not embed
  machine-specific paths, timing, environment values, terminal colour output,
  or non-deterministic ordering.
- Use `proptest` for the segments-concatenation invariant. Do not introduce
  Kani, Verus, or CrossHair for this slice; the invariant is over an unbounded
  input space and is well-suited to randomized property testing, not bounded
  model checking. Property test runs must remain deterministic enough to keep
  `make test` stable.
- Run Makefile gates sequentially, never in parallel, and capture long
  command output with `tee` into `/tmp` logs as `AGENTS.md` requires.
- Use `coderabbit review --agent` after each major implementation milestone
  and resolve all actionable concerns before moving to the next milestone.
- Commit each approved, gated change as a focused commit. Do not commit code
  or documentation that fails required gates.
- On completion of the implemented feature, update `docs/roadmap.md` to mark
  item 2.1.1 done. Do not mark it done while this plan is still a draft or
  while implementation is incomplete.

## Tolerances (exception triggers)

- Scope: if implementation requires changing more than roughly fifteen files
  or roughly twelve hundred net new lines of code, stop and explain why
  before continuing.
- Public API: if any existing public Rust or Python API signature must change
  in a non-additive way, stop and request approval.
- Dependencies: adding `markdown = "1.0"` to `crates/stilyagi-markdown`,
  `sha2 = "0.10"` to `crates/stilyagi-ir`, and `static_assertions = "1"` to
  `crates/stilyagi-extract` is pre-approved by this plan. Any other external
  dependency requires approval.
- Bridge contract: if the PyO3 wire shape must diverge from the canonical JSON
  envelope (for example, to ship a binary payload), stop and present options.
- Snapshot churn: the existing `extraction_tests__shared_markdown_fixture_has_a_golden_ir_snapshot.snap`
  will be regenerated. That change is expected. If any other unrelated
  snapshot churns, investigate before accepting.
- Property tests: keep generated cases bounded and deterministic. If a
  property test becomes flaky or slow after two focused fixes, narrow it,
  document the trade-off, and ask before disabling.
- Runtime: the new tests should not add more than roughly fifteen seconds to a
  warm `make test` run on the development machine. If they do, document the
  cause and ask whether to narrow the corpus.
- Validation: if `make check-fmt`, `make lint`, or `make test` still fails
  after two focused correction passes, stop and record the failing log paths
  in this plan.
- Review: if `coderabbit review --agent` raises a concern that conflicts with
  this plan, record the conflict in `Decision Log` and ask for direction
  before changing scope.
- Ambiguity: if multiple valid envelope shapes or segment representations
  remain after reading the relevant source, document the options and ask
  before proceeding.

## Risks

- Risk: span drift across inline markup elision. mdast's `Text` position
  covers the inner text bytes; the wrappers (`Emphasis`, `Strong`, `Link`,
  `InlineCode`) elide their delimiters. A walker that computes child spans
  from parent bounds will be off by one or more. Severity: high. Likelihood:
  medium. Mitigation: trust child `Position.offset` values verbatim; back the
  invariant with a `proptest` that generates nested inline markup such as
  `*foo *bar* baz*` or strong markup wrapping inline code or links wrapping
  emphasis, and asserts the segments concatenation invariant.

- Risk: off-by-one in mdast positions. `unist::Point.offset` is a byte
  offset; `line` and `column` are 1-based. Mixing the two causes silent
  drift. Severity: medium. Likelihood: medium. Mitigation: anchor every
  computation to `offset`. Treat `line` and `column` as derived debug values.
  Add a unit test that pins the heading region span at file offset 0 to the
  bytes that follow the heading's leading hash and space delimiters.

- Risk: CRLF versus LF handling. Soft breaks inside `mdast::Text` values
  appear as embedded newlines, but the source may be CRLF on Windows-edited
  files. If the walker splits on `\n` without accounting for the preceding
  `\r`, the source spans will be one byte short. Severity: high.
  Likelihood: medium. Mitigation: add a CRLF fixture
  (`paragraph-with-soft-break-crlf.md` stored with literal CRLF endings), add
  an explicit unit test, and include CRLF-bearing inputs in the proptest.
  Fallback: if CRLF handling cannot be made byte-faithful inside the timebox,
  document the limitation, require LF-normalized input at the extractor
  boundary, and capture the decision in `Decision Log` before proceeding.

- Risk: bridge wire shape freeze. If anything outside
  `python/stilyagi/engine/extraction.py` starts reading the PyO3 dictionary
  directly, the wire shape becomes a de-facto contract that resists later
  refactors. Severity: medium. Likelihood: medium. Mitigation: keep
  `engine.extraction` as the only consumer; gate every change with the
  canonical JSON parity test; document the rule in the developers' guide and
  in the proposed ADR addendum.

- Risk: golden snapshot churn obscuring real changes. The existing snapshot
  for the shared Markdown fixture currently encodes a single whole-document
  region with one source-backed segment. The new envelope changes its shape
  meaningfully. Severity: low. Likelihood: high. Mitigation: regenerate the
  snapshot intentionally in one commit, review it by hand, and write a clear
  commit message that records what changed.

- Risk: dual canonical JSON serializers diverging. The Rust serializer in
  `stilyagi-ir` and the Python serializer in `stilyagi.model.Document` can
  drift on field ordering, whitespace, numeric formatting, or escape rules.
  Severity: high. Likelihood: medium. Mitigation: pin the canonical JSON
  style as documented in `Constraints`; add Rust unit tests for each style
  rule; add a Python parity test that loads each fixture, builds the typed
  `Document` via the bridge, calls `Document.to_canonical_json()`, and asserts
  byte-identical output against the matching Rust `insta` snapshot file.

- Risk: line-ending normalization via git. A CRLF fixture stored on disk can
  be silently rewritten to LF on checkout by `core.autocrlf` or by an
  unscoped `*.md text=auto` `.gitattributes` rule. Severity: medium.
  Likelihood: medium. Mitigation: add a scoped
  `tests/fixtures/corpus/markdown/.gitattributes` entry that marks
  `paragraph-with-soft-break-crlf.md` as `-text` so git treats it as binary;
  add a unit test that asserts the on-disk file still contains literal CRLF
  bytes before parsing.

- Risk: the existing `stilyagi-test-support` golden shape leaking into
  production. The `GoldenDocument`, `GoldenRegion`, and `Segment` types in
  `crates/stilyagi-test-support` predate this slice. They model a narrower
  schema than the new envelope and were always intended as test-only DTOs.
  Severity: medium. Likelihood: low. Mitigation: regenerate the dev-only
  golden shapes from the production `IrDocument` via a snapshot serializer;
  do not promote the dev-only DTOs into `stilyagi-ir`; remove redundant DTOs
  after the production envelope lands.

- Risk: corpus gap surfacing as 2.1.1 fixture work the plan did not name.
  Severity: medium. Likelihood: high. Mitigation: this plan explicitly
  treats the missing frontmatter, inline-markup, and soft-break fixtures as
  2.1.1 deliverables; the alternative of amending 1.3.1 retroactively is
  recorded in `Decision Log` so the decision is visible.

- Risk: roadmap dependency on 1.3.1 misstated. The roadmap claims 1.3.1
  satisfies 2.1.1's input needs; the corpus does not yet contain paragraph or
  frontmatter shapes. Severity: low. Likelihood: high (already observed).
  Mitigation: add the missing fixtures in this slice and note the gap in
  `Surprises & Discoveries`.

- Risk: `Region.id` allocation ambiguity. In 2.1.1 the natural id strategy is
  document walk order (`"r1"`, `"r2"`, ...), but 2.1.2 will introduce nested
  regions and a downstream cache. Walk-order ids invalidate cache entries on
  any structural edit upstream of a region. Severity: low for this slice,
  medium long-term. Likelihood: medium. Mitigation: document in `Decision
  Log` that 2.1.1 uses walk-order ids as an explicit interim choice and that
  a content-derived id strategy (for example `sha256(scope || span)`) may
  replace it before any cache is built.

- Risk: `result_large_err` lint trips when error variants grow. Workspace
  clippy denies large error returns. Adding spans, owned source slices, or
  string payloads to `ExtractError` or new `MarkdownError` variants can
  silently push them past the threshold. Severity: medium. Likelihood:
  medium. Mitigation: add a `static_assertions::const_assert!` pinning
  `mem::size_of::<ExtractError>() <= mem::size_of::<usize>() * 3` (or
  equivalent) when Stage E lands the new error type, and `Box`-wrap any
  variant that carries owned data.

## Plan of work

Stage A. Stabilise the contract on paper before code.

This stage produces no code, only a final read-through of RFC 0001, ADR 003,
and the design document. The implementer should be able to recite the
envelope's mandatory fields, the region invariants from RFC 0001 section 7,
and the canonical JSON style rules before opening an editor. The stage ends
when the implementer can write the expected canonical JSON for one of the
existing fixtures by hand. There is no code or documentation change in this
stage; the gate is reading and short notes captured in `Decision Log`.

Stage B. Add failing tests and the missing fixtures (red bar).

Add the three missing Markdown fixtures under `tests/fixtures/corpus/markdown`
(`paragraph-with-emphasis.md`, `paragraph-with-soft-break.md`,
`yaml-frontmatter.md`) and one CRLF-bearing fixture
(`paragraph-with-soft-break-crlf.md`, saved with literal CRLF bytes). Add
failing Rust unit tests in `crates/stilyagi-ir/src/document.rs` for the
envelope shape, in `crates/stilyagi-ir/src/line_index.rs` for the `LineIndex`
newtype, and in `crates/stilyagi-ir/src/content_hash.rs` for SHA-256
construction. Add failing snapshot tests in `crates/stilyagi-extract/tests/`
for the new region kinds. Add a failing `rstest-bdd` scenario in
`crates/stilyagi-pyext/tests/features/bridge_structure.feature` that calls the
new envelope entry point. Add a failing `pytest` test in `tests/` that asserts
the typed Python `Document` includes the envelope fields and a failing
`pytest-bdd` scenario in `features/` for the Python typed surface. The bar
fails because the production types and bridge entrypoint do not exist, not
because of an unrelated build break. The stage ends with a single commit
named after the failing-test scope. Validation: `make test` shows the
expected failures, and `make markdownlint` plus `make nixie` still pass.

Stage C. Implement the IR domain crate.

Add `sha2 = "0.10"` to `crates/stilyagi-ir/Cargo.toml`. Introduce the
`IrDocument`, `DocumentMeta`, `Producer`, `Region`, `Segment`, `Span`,
`LineIndex`, `ContentHash`, `Suppression`, and `IrError` types in dedicated
modules under `crates/stilyagi-ir/src/`. Promote the existing
`line_index_for` into `LineIndex::for_source`.

The 2.1.1 envelope does not ship a typed `trees`/`nodes` Rust surface. The
serializer emits both as empty JSON arrays (`"trees": []`, `"nodes": []`)
straight from constants; the `IrDocument` struct holds them as
zero-sized markers (`TreesSentinel`, `NodesSentinel`) until 2.1.2 introduces
the real types. The `metadata` field is typed as `BTreeMap<String,
EnvelopeJsonValue>` where `EnvelopeJsonValue` is a hand-defined enum that
admits only objects, arrays, strings, signed integers, booleans, and null —
floats are rejected at construction. This eliminates the long-term hazard of
floating-point formatting drift between Rust and Python.

Keep `stilyagi-ir` free of `markdown-rs`, PyO3, and IO. The canonical JSON
serializer follows the style fixed in `Constraints`: UTF-8 only, two-space
indentation, byte-wise sorted object keys, single trailing `\n`, the
documented escape set, decimal integers with no leading zero, no floats. Unit
tests in this crate must pass without depending on `stilyagi-test-support`.
Each canonical JSON style rule MUST have a focused unit test that uses a
targeted fixture (escape rule, sort order, indentation, trailing newline,
integer formatting). Each enum spelling MUST have a unit test that pins its
lowercase snake_case form. Unit tests MUST cover empty source (`""` → empty
regions, `line_index == [0, 0]`), source without a trailing newline, and a
canonical JSON round trip that rejects a version-2 envelope.

The stage ends with all `stilyagi-ir` unit tests green. Validation:
`cargo test -p stilyagi-ir` passes; `make check-fmt` and `make lint` pass
for the crate.

Stage D. Implement the Markdown adapter crate.

Add `markdown = "1.0"` and `stilyagi-ir = { path = "../stilyagi-ir" }` to
`crates/stilyagi-markdown/Cargo.toml`. Introduce
`crates/stilyagi-markdown/src/parse.rs` for the `markdown::to_mdast` call
wrapped in `std::panic::catch_unwind`, `walker.rs` for the recursive inline
flattener, `regions.rs` for the block region producer (heading, paragraph,
frontmatter), and `error.rs` for typed parse failures. The walker must emit
a `Segment::Source` for each contiguous inline text byte range, a
`Segment::Synthetic { kind: SoftbreakSpace }` for each soft break inside a
`Text` value, and a `Segment::Synthetic { kind: HardbreakNewline }` for each
`mdast::Break`. The frontmatter handler emits one source-backed segment for
the YAML body (TOML support follows the same shape).

This stage adds the `proptest` invariant in
`crates/stilyagi-markdown/tests/proptest_segments.rs`: for every generated
Markdown snippet, the concatenation of region segments' text equals the
region text exactly, every source segment's span lies inside the region
node's position bounds, synthetic segments carry only the closed text set,
and `text_start/text_end` values are contiguous and cover the region text.
Configure proptest with `cases = 64` (override via `PROPTEST_CASES` for local
deep runs); store regression seeds at
`crates/stilyagi-markdown/proptest-regressions/segments.txt` and commit
them.

Stage D also pins the fatal-vs-recoverable error policy stated in
`Constraints`. The mdast call's `Result<Node, Message>` `Err` arm and any
`catch_unwind` failure become fatal `MarkdownError` values that the
orchestration crate maps to `ExtractError`; the envelope `errors` array
remains empty in 2.1.1. A unit test pins each branch.

Validation: `cargo test -p stilyagi-markdown` passes including proptest
cases.

Stage E. Update the orchestration crate.

`crates/stilyagi-extract::extract_document(source, ExtractSyntax::Markdown)`
now returns `Result<IrDocument, ExtractError>`. The function: delegates to
`stilyagi-markdown` for region production; computes `LineIndex::for_source`
in-house; computes `ContentHash::sha256_of_bytes`; assembles the `producers`
record (including the `markdown-rs` version reported through a small wrapper
constant in `stilyagi-markdown` so the orchestration crate does not need to
parse `Cargo.lock`); fills the `document` metadata with the supplied path
and the `utf-8` encoding constant; and returns an envelope with empty
`trees`, `nodes`, `suppressions`, and `errors`.

Add `static_assertions = "1"` as a dev-dependency and assert that
`mem::size_of::<ExtractError>() <= mem::size_of::<usize>() * 3` so future
variants cannot quietly trip the workspace `result_large_err = "deny"` lint.
Variants that must carry owned data must `Box`-wrap their payload.

The existing `ExtractDocument`, `ExtractRegion`, and `RegionKind::Document`
shapes remain only if the bridge keeps using them for back-compat through
this slice; otherwise they are removed in this stage. The extraction
integration tests in `crates/stilyagi-extract/tests/` get updated snapshots.
Validation: `cargo test -p stilyagi-extract` passes; `cargo clippy -p
stilyagi-extract --workspace --all-targets -- -D warnings` reports no
`result_large_err` violations.

Stage F. Update the PyO3 bridge.

Add `extract_ir_document_py` in `crates/stilyagi-pyext/src/lib.rs`. It calls
`stilyagi_extract::extract_document` inside `py.detach` (matching the
existing `extract_document_py` GIL discipline) and returns a `PyDict` whose
structure mirrors the canonical IR envelope exactly. Field names follow
snake_case as required by `Constraints`. The bridge dictionary does not
carry a `_canonical_json` field; canonical JSON for parity testing is
produced by a separate, narrow debug entry point
`canonical_json_for_ir_document_py(source: &str, syntax: &str) -> str` that
returns the Rust serializer's output for the same input. Keep this debug
entry point behind a stable name so future `dump-ir` work can call it
without re-implementing serialization.

Keep `extract_document_py` in place through this stage so existing tests
continue to pass. Add Rust BDD scenarios in `bridge_structure.feature` for
the new entrypoint, the envelope shape, and the canonical JSON debug entry.
Update `python/stilyagi/_stilyagi_rs.pyi` with explicit signatures for the
new entry points and a `TypedDict` describing the envelope mirror. Validation:
`cargo test -p stilyagi-pyext` passes including new BDD scenarios.

Stage G. Update the typed Python surface.

Grow `python/stilyagi/model/document.py` with `DocumentMeta`, `Producer`,
and the expanded `Document` dataclass (envelope-shaped, with
`schema_version`, `document`, `producers`, `line_index`, `regions`,
`suppressions`, `errors`, `metadata`). Grow `python/stilyagi/model/region.py`
with `RegionKind` (heading, paragraph, frontmatter; placeholder values for
later kinds may be declared but must not be produced), `Span`,
`SourceSegment`, `SyntheticSegment`, the `Segment` union with the canonical
`source`/`synthetic` tag, and the expanded `Region` carrying `id`, `kind`,
`scope`, `syntax`, `natural_language`, `text`, `segments`, `origin_nodes`,
`owner`, `attrs`, and `parent_region` per RFC 0001 section 6.

Update `python/stilyagi/engine/extraction.py` to coerce the new bridge
dictionary into the typed model. Add `Document.to_canonical_json()` and
`Document.from_canonical_json()`. The serializer follows the canonical JSON
style pinned in `Constraints`; the parser rejects any envelope whose major
version is not `1` and ignores unknown fields within the same major version
(RFC 0001 section 9).

Add the parity test in `tests/test_ir_canonical_json_parity.py`: for each
fixture, call the bridge to get the typed `Document`, call
`Document.to_canonical_json()`, and assert byte-identical output against the
matching Rust `insta` snapshot file content. The parity oracle is the
Rust-side snapshot, not a bridge field. Add a unit test for the major-version
rejection branch and a unit test that ignores unknown fields on the same
major version.

Add the `pytest-bdd` scenario for the Python typed surface. Update `syrupy`
snapshots. Validation: `make test` passes for the Python side; canonical
JSON parity tests pass.

Stage H. Tighten and clean up.

Remove `ExtractDocument`, `ExtractRegion`, and `RegionKind::Document` if any
remain after Stage E. Remove `extract_document_py` from the PyO3 bridge if no
test still depends on it; otherwise document why it is retained. Replace the
dev-only `golden_markdown_ir_fixture` builder with one that derives its
snapshot from the production `IrDocument`. Confirm the structural performance
probe at `tests/performance/structural_probe.py` still completes inside its
existing warm-budget tolerance after the envelope build path lands; record
the measurement in `Surprises & Discoveries`. Validation: `make check-fmt`,
`make lint`, `make typecheck`, and `make test` all pass; the workspace
contains no dead adapters; `coderabbit review --agent` has no unresolved
actionable concerns.

Stage I. Documentation and roadmap tick.

Update `docs/stilyagi-design.md` section 7.1 to record that the bridge now
carries the full envelope and that `Document`, `Region`, and `Segment` are
the supported Python surface. Include the canonical JSON style block from
`Constraints` either inline or as an appendix so future readers do not have
to dig into the plan to recover it. Update `docs/developers-guide.md` with
the snapshot-update workflow for the new envelope and the rule that the
canonical JSON parity test gates every bridge change. Update
`docs/repository-layout.md` to describe `stilyagi-ir` and `stilyagi-markdown`
as real domain and adapter crates rather than markers. Add the ADR
addendum (see `Decision Log`) recording that the PyO3 wire format mirrors the
canonical JSON IR and is not a public contract. Update `docs/roadmap.md` to
mark item 2.1.1 done. Do not change `docs/users-guide.md` because no
user-visible behaviour changes in this slice. Validation: `make
markdownlint` and `make nixie` pass.

Each stage ends with the focused gates that protect its work. The full
sequence of stage validations is the milestone gate; the milestone-level
gates are documented in `Progress`.

## Concrete steps

From the repository root, confirm branch and status:

```bash
git branch --show-current
git status --short
```

Expected branch:

```plaintext
2-1-1-markdown-ir-envelope-and-mappings
```

Refresh the `leta` workspace and reconnoitre the IR-adjacent symbols:

```bash
leta workspace add "$(pwd)"
leta files crates/
leta grep "ExtractDocument" -k struct
leta grep "GoldenDocument" -k struct
leta grep "line_index_for" -k function
```

Add tests first. A likely first targeted failing run is:

```bash
make test 2>&1 | tee /tmp/test-stilyagi-2-1-1-markdown-ir-envelope-red.out
```

The expected first result after test edits is failure caused by missing
envelope types, missing bridge entrypoints, missing fixtures, or missing
snapshots. It should not fail because of an unrelated packaging or smoke
regression.

When adding dependencies, keep them in their respective crates:

```toml
# crates/stilyagi-ir/Cargo.toml
[dependencies]
sha2 = "0.11"

# crates/stilyagi-markdown/Cargo.toml
[dependencies]
markdown = "1.0"
stilyagi-ir = { path = "../stilyagi-ir" }
```

Run focused crate tests as each stage lands:

```bash
$(CARGO) test -p stilyagi-ir 2>&1 | tee /tmp/test-stilyagi-ir-2-1-1.out
$(CARGO) test -p stilyagi-markdown 2>&1 | tee /tmp/test-stilyagi-markdown-2-1-1.out
$(CARGO) test -p stilyagi-extract 2>&1 | tee /tmp/test-stilyagi-extract-2-1-1.out
$(CARGO) test -p stilyagi-pyext 2>&1 | tee /tmp/test-stilyagi-pyext-2-1-1.out
```

Run the major-milestone review after each coherent commit candidate:

```bash
coderabbit review --agent 2>&1 | tee /tmp/coderabbit-stilyagi-2-1-1-milestone.out
```

After implementation, run the required gates sequentially:

```bash
make check-fmt 2>&1 | tee /tmp/check-fmt-stilyagi-2-1-1.out
make lint 2>&1 | tee /tmp/lint-stilyagi-2-1-1.out
make typecheck 2>&1 | tee /tmp/typecheck-stilyagi-2-1-1.out
make test 2>&1 | tee /tmp/test-stilyagi-2-1-1.out
```

If Markdown documentation changed, also run:

```bash
make markdownlint 2>&1 | tee /tmp/markdownlint-stilyagi-2-1-1.out
make nixie 2>&1 | tee /tmp/nixie-stilyagi-2-1-1.out
```

Inspect the final diff before committing:

```bash
git diff --stat
git diff -- docs/roadmap.md docs/developers-guide.md docs/stilyagi-design.md
git status --short
```

Then commit with a file-based commit message, following the repository commit
message rules.

## Validation and acceptance

The implementation is accepted when all of the following are true:

- `stilyagi-extract::extract_document` for the Markdown syntax returns a
  populated `IrDocument` whose canonical JSON validates against RFC 0001
  section 4 for every fixture used in 2.1.1.
- The envelope sets `schema_version` to `1.0.0`, sets `document.encoding` to
  `utf-8`, sets `document.syntax` to `markdown`, sets `document.content_hash`
  to a `sha256:<hex>` value computed from the raw source bytes, and includes
  a non-empty `producers` array describing the markdown-rs producer.
- The envelope includes `line_index` byte offsets that match the source line
  starts and end-of-document offset.
- Regions cover heading, paragraph, and frontmatter shapes for every 2.1.1
  fixture. Each region carries `segments` such that
  `concat(segment.text) == region.text` exactly, with synthetic insertions
  marked synthetic and source-backed slices marked source.
- A property test using `proptest` asserts the segments concatenation
  invariant across generated Markdown snippets that include emphasis, strong,
  inline code, link text, hard breaks, and soft breaks (including a CRLF
  case).
- A canonical JSON parity test asserts that the Rust serializer's output for
  each fixture equals the Python round-trip of the same envelope read via the
  bridge.
- The PyO3 bridge exposes `extract_ir_document_py` returning the envelope
  dictionary (no `_canonical_json` field) and a separate
  `canonical_json_for_ir_document_py` returning the Rust serializer's
  canonical JSON for the same input. Bridge field names use snake_case.
- The supported Python typed surface (`stilyagi.model.Document`,
  `model.Region`, `model.Segment`, `model.DocumentMeta`, `model.Producer`,
  `model.SourceSegment`, `model.SyntheticSegment`, `model.Span`) exposes every
  envelope field listed in RFC 0001 section 6 (`id`, `kind`, `scope`,
  `syntax`, `natural_language`, `text`, `segments`, `origin_nodes`, `owner`,
  `attrs`, `parent_region`) as a typed value.
- `Document.from_canonical_json` rejects envelopes whose major version is not
  `1` and ignores unknown fields within the same major version.
- The structural performance probe (`tests/performance/structural_probe.py`)
  still completes inside its existing warm-budget tolerance after Stage H.
- `cargo test -p stilyagi-ir`, `cargo test -p stilyagi-markdown`,
  `cargo test -p stilyagi-extract`, `cargo test -p stilyagi-pyext`, and the
  workspace test target all pass.
- `pytest` and `pytest-bdd` suites pass, including the new envelope tests
  and the canonical JSON parity test.
- `insta` snapshots for the IR envelope and `syrupy` snapshots for the Python
  surface review cleanly without machine-specific paths, timing, environment
  values, terminal colour output, or non-deterministic ordering.
- `make check-fmt`, `make lint`, `make typecheck`, and `make test` all
  succeed. `make markdownlint` and `make nixie` succeed for any Markdown
  documentation touched in this slice.
- `coderabbit review --agent` has no unresolved actionable concerns.
- `docs/stilyagi-design.md` records the envelope contract change in section
  7.1.
- `docs/developers-guide.md` documents the snapshot-update workflow and the
  canonical JSON parity rule.
- An ADR addendum or new ADR records that the PyO3 bridge wire format is an
  internal mirror of the canonical IR JSON and is not a public contract.
- `docs/roadmap.md` marks item 2.1.1 as done.
- The corpus contains the new Markdown fixtures introduced by this slice and
  the existing fixtures continue to load without changes to their bytes.

## Idempotence and recovery

The implementation should be additive on the test surface and replacement on
the bridge surface. Re-running tests and validation commands should not
mutate repository state except for ordinary ignored build artefacts,
temporary snapshot review files, or `/tmp` logs. If snapshot update commands
create `.new` or equivalent review artefacts, inspect them, accept only
intentional changes, and remove rejected artefacts before committing.

If a Makefile gate fails, inspect the matching `/tmp/*.out` log first. If
the failure is unrelated to this work, record it in
`Surprises & Discoveries` and ask before widening scope. If the failure is
caused by this work, fix it and rerun only the failed gate before rerunning
the final gate sequence.

If snapshot output churns because the canonical JSON serializer is unstable
(field ordering, indentation, line endings), stabilise the serializer rather
than approving churn. If the output churns because the implementation
corrected a span, segment, content hash, or producer record, regenerate the
snapshot intentionally and record the reason in `Decision Log`.

If `coderabbit review --agent` fails for an environmental reason, rerun it
once and capture the log. If it still cannot run, record the failure,
include the log path in this plan, and ask whether to proceed without that
review gate.

If the CRLF-bearing fixture cannot be made to satisfy the segments invariant
within the timebox, capture the limitation in `Decision Log`, remove the
CRLF fixture and its tests for this slice, document the LF-only constraint
in the design document, and ask whether the slice should still proceed.

## Interfaces and dependencies

Expected runtime dependency changes:

- `crates/stilyagi-ir/Cargo.toml` gains `sha2 = "0.10"`.
- `crates/stilyagi-markdown/Cargo.toml` gains `markdown = "1.0"` and
  `stilyagi-ir = { path = "../stilyagi-ir" }`.
- `crates/stilyagi-extract/Cargo.toml` gains nothing new; it already depends
  on `stilyagi-ir` and `stilyagi-markdown`.

Expected test-only dependency changes:

- `crates/stilyagi-extract/Cargo.toml` gains `static_assertions = "1"` as a
  dev dependency for the `ExtractError` size assertion. `insta`, `rstest`,
  `rstest-bdd`, `proptest`, `pytest`, `pytest-bdd`, and `syrupy` are already
  present.

Expected Rust interfaces (illustrative; final names land during
implementation):

```rust
// crates/stilyagi-ir/src/document.rs
pub struct IrDocument {
    pub schema_version: SchemaVersion,
    pub document: DocumentMeta,
    pub producers: Vec<Producer>,
    pub line_index: LineIndex,
    pub trees: TreesSentinel,      // ZST; serializes as []
    pub nodes: NodesSentinel,      // ZST; serializes as []
    pub regions: Vec<Region>,
    pub suppressions: Vec<Suppression>, // empty in 2.1.1
    pub errors: Vec<IrError>,      // empty in 2.1.1
    pub metadata: BTreeMap<String, EnvelopeJsonValue>,
}

pub enum EnvelopeJsonValue {
    Null,
    Bool(bool),
    Int(i64),
    Str(String),
    Array(Vec<EnvelopeJsonValue>),
    Object(BTreeMap<String, EnvelopeJsonValue>),
}

pub struct DocumentMeta {
    pub uri: Option<String>,
    pub path: String,
    pub syntax: Syntax,
    pub encoding: Encoding,
    pub content_hash: ContentHash,
    pub natural_language: Option<Locale>,
}

pub struct Region {
    pub id: RegionId,
    pub kind: RegionKind,
    pub scope: Vec<String>,
    pub syntax: Syntax,
    pub natural_language: Option<Locale>,
    pub text: String,
    pub segments: Vec<Segment>,
    pub origin_nodes: Vec<NodeId>,  // empty in 2.1.1
    pub owner: Option<Owner>,       // null in 2.1.1
    pub attrs: BTreeMap<String, EnvelopeJsonValue>,
    pub parent_region: Option<RegionId>,
}

pub enum Segment {
    Source {
        text_start: usize,
        text_end: usize,
        span: Span,
        node: Option<NodeId>,
        text: String,
    },
    Synthetic {
        text_start: usize,
        text_end: usize,
        kind: SyntheticKind,
        text: String,
    },
}

pub enum SyntheticKind {
    SoftbreakSpace,
    HardbreakNewline,
}

pub struct Span { pub byte_start: usize, pub byte_end: usize }
```

`Region.id` is a walk-order id (`"r1"`, `"r2"`, ...) in 2.1.1. A
content-derived strategy (for example `sha256(scope || span)`) may replace
it before any cache layer ships; see `Decision Log`.

`Tree` and `Node` types are not introduced in 2.1.1. They land with 2.1.2,
which will replace the `TreesSentinel` and `NodesSentinel` ZST markers with
typed collections.

Expected Python interfaces:

```python
@dc.dataclass(frozen=True, slots=True)
class DocumentMeta:
    uri: str | None
    path: str
    syntax: Syntax
    encoding: str = "utf-8"
    content_hash: str = ""
    natural_language: str | None = None


@dc.dataclass(frozen=True, slots=True)
class Producer:
    kind: str
    name: str
    version: str
    options: dict[str, object]


@dc.dataclass(frozen=True, slots=True)
class Span:
    byte_start: int
    byte_end: int


@dc.dataclass(frozen=True, slots=True)
class Owner:
    kind: str
    name: str | None = None
    qualname: str | None = None


@dc.dataclass(frozen=True, slots=True)
class Document:
    schema_version: str
    document: DocumentMeta
    producers: tuple[Producer, ...]
    line_index: tuple[int, ...]
    regions: tuple["Region", ...]
    suppressions: tuple[object, ...] = ()
    errors: tuple[object, ...] = ()
    metadata: dict[str, object] = dc.field(default_factory=dict)

    @classmethod
    def from_canonical_json(cls, text: str) -> "Document": ...

    def to_canonical_json(self) -> str: ...


class RegionKind(enum.StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    FRONTMATTER = "frontmatter"


class SyntheticSegmentKind(enum.StrEnum):
    SOFTBREAK_SPACE = "softbreak_space"
    HARDBREAK_NEWLINE = "hardbreak_newline"


@dc.dataclass(frozen=True, slots=True)
class SourceSegment:
    text_start: int
    text_end: int
    span: Span
    node: str | None
    text: str


@dc.dataclass(frozen=True, slots=True)
class SyntheticSegment:
    text_start: int
    text_end: int
    kind: SyntheticSegmentKind
    text: str


Segment = SourceSegment | SyntheticSegment


@dc.dataclass(frozen=True, slots=True)
class Region:
    id: str
    kind: RegionKind
    scope: tuple[str, ...]
    syntax: Syntax
    natural_language: str | None
    text: str
    segments: tuple[Segment, ...]
    origin_nodes: tuple[str, ...] = ()
    owner: Owner | None = None
    attrs: dict[str, object] = dc.field(default_factory=dict)
    parent_region: str | None = None
```

Expected bridge entrypoints:

```rust
#[pyfunction(name = "extract_ir_document")]
fn extract_ir_document_py(py: Python<'_>, source: &str, syntax: &str)
    -> PyResult<Py<PyDict>>;

#[pyfunction(name = "canonical_json_for_ir_document")]
fn canonical_json_for_ir_document_py(py: Python<'_>, source: &str, syntax: &str)
    -> PyResult<String>;
```

`extract_ir_document_py` returns a `PyDict` that mirrors the canonical JSON
envelope exactly, with snake_case field names. The dictionary carries no
`_canonical_json` or other meta field.

`canonical_json_for_ir_document_py` returns the Rust serializer's canonical
JSON for the same input. It is the parity oracle used by the Python parity
test in Stage G and a building block for the future `dump-ir` command.

Both bridge entry points wrap the parser call in `py.detach` so the Python
GIL is released for the duration of extraction.

Expected new Markdown corpus fixtures (Stage B):

- `tests/fixtures/corpus/markdown/valid/paragraph-with-emphasis.md`
- `tests/fixtures/corpus/markdown/valid/paragraph-with-soft-break.md`
- `tests/fixtures/corpus/markdown/valid/paragraph-with-soft-break-crlf.md`
  (saved with literal CRLF bytes)
- `tests/fixtures/corpus/markdown/valid/yaml-frontmatter.md`
- `tests/fixtures/corpus/markdown/.gitattributes` with
  `paragraph-with-soft-break-crlf.md -text` so git does not normalise the
  CRLF fixture on checkout.

## Progress

Use a list with checkboxes to summarise granular steps. Every stopping point
must be documented here, even if it requires splitting a partially completed
task into two ("done" vs. "remaining"). This section must always reflect the
actual current state of the work.

- [x] (2026-06-05) Drafted plan after loading the `leta`,
  `hexagonal-architecture`, `python-router`, `rust-router`, `firecrawl`, and
  `execplans` skills; creating the `leta` workspace; reading the roadmap,
  design document, RFC 0001, ADR 002, ADR 003, repository layout, developers'
  guide, fixtures, and current `stilyagi-extract`, `stilyagi-ir`,
  `stilyagi-test-support`, and `stilyagi-pyext` sources; resolving
  `markdown-rs` and `sha2` documentation through Firecrawl; dispatching a
  planning agent for the architectural brief; and adopting a Logisphere
  community-of-experts review of the draft.
- [ ] Stage A. Stabilise the contract on paper. Gate: short notes added to
  `Decision Log` confirming the envelope, region invariants, and canonical
  JSON style are understood; no code changes yet.
- [ ] Stage B. Add failing tests and the missing fixtures (red bar). Gate:
  `make test` fails with the new test names; `make markdownlint` and
  `make nixie` still pass; the four new fixtures and the `.gitattributes`
  entry exist on disk with the expected line endings.
- [ ] Stage C. Implement the IR domain crate. Gate: `cargo test -p
  stilyagi-ir` green; `cargo clippy -p stilyagi-ir -- -D warnings` clean;
  unit tests cover every canonical JSON style rule and the major-version
  rejection branch.
- [ ] Stage D. Implement the Markdown adapter crate. Gate: `cargo test -p
  stilyagi-markdown` green including the proptest invariant
  (`cases = 64`); CRLF fixture exercises the soft-break splitter; the
  `markdown::to_mdast` panic boundary has a unit test.
- [ ] Stage E. Update the orchestration crate. Gate: `cargo test -p
  stilyagi-extract` green; the regenerated snapshot file
  `extraction_tests__shared_markdown_fixture_has_a_golden_ir_snapshot.snap`
  is reviewed by hand; the `result_large_err` static assertion compiles.
- [ ] Stage F. Update the PyO3 bridge. Gate: `cargo test -p stilyagi-pyext`
  green including new BDD scenarios; the `.pyi` stub describes
  `extract_ir_document` and `canonical_json_for_ir_document` with explicit
  signatures.
- [ ] Stage G. Update the typed Python surface. Gate: `pytest -v` green
  including the canonical JSON parity test; the typed `Document` carries
  every field listed in `Validation and acceptance`; the major-version
  rejection has a passing unit test.
- [ ] Stage H. Tighten and clean up. Gate: `make check-fmt`, `make lint`,
  `make typecheck`, and `make test` all green; the structural performance
  probe still passes inside its existing budget; `coderabbit review --agent`
  has no unresolved actionable concerns.
- [ ] Stage I. Documentation and roadmap tick. Gate: `make markdownlint`
  and `make nixie` green; `docs/roadmap.md` shows item 2.1.1 ticked.

## Surprises & discoveries

- Observation: the shared validation corpus produced by roadmap item 1.3.1
  does not contain a frontmatter fixture, a paragraph-with-inline-markup
  fixture, or a soft-break fixture. RFC 0001 section 6 names paragraph and
  frontmatter as v1 region kinds, and the segments invariant cannot be
  proven without those shapes.
  Evidence: `tests/fixtures/corpus/markdown/valid/` contains only
  `heading-table-link-suppression.md`; `tests/fixtures/corpus/markdown/malformed/`
  contains only `unclosed-table.md`.
  Impact: this slice introduces the missing fixtures rather than amending
  1.3.1 retroactively. The corpus gap is recorded in `Decision Log`.

## Decision log

- Decision: keep `crates/stilyagi-ir` as the inner-hexagon domain crate with
  no PyO3, no `markdown-rs`, and no IO. Promote `crates/stilyagi-markdown` to
  the Markdown adapter, owning the `markdown-rs` dependency. Keep
  `crates/stilyagi-extract` as orchestration and `crates/stilyagi-pyext` as
  the inbound driving adapter.
  Rationale: this places the dependency graph one-way (ir <- markdown <-
  extract <- pyext) and matches hexagonal-architecture guidance for keeping
  domain logic infrastructure-free. Slice-3 docstring extraction will land
  in `stilyagi-tree-sitter` without disturbing the IR crate.
  Date/Author: 2026-06-05, plan author.

- Decision: ship the segments model for heading, paragraph, and frontmatter
  regions in 2.1.1. Defer `list_item`, `blockquote`, `table_cell`,
  `image_alt`, `link_title`, and `frontmatter_field` to 2.1.2.
  Rationale: heading, paragraph, and frontmatter together exercise every
  segments-model mechanism (delimiter elision, inline-markup elision,
  soft-break synthesis, source-contiguous regions) without doubling the
  scope of 2.1.1. The remaining v1 region kinds add fixture and rule work
  without new envelope mechanics.
  Date/Author: 2026-06-05, plan author.

- Decision: add `sha2 = "0.11"` to `crates/stilyagi-ir` for content hashing.
  Rationale: RFC 0001 mandates `sha256:` content hashes and the cache-key
  contract depends on this. `sha2` is the canonical Rust SHA-2 crate and
  brings a minimal compiled footprint. Hand-rolling SHA-256 would create an
  audit surface for no benefit; alternative hash families would violate the
  RFC.
  Date/Author: 2026-06-05, plan author.

- Decision: add `markdown = "1.0"` to `crates/stilyagi-markdown`.
  Rationale: the design document names `markdown-rs` as the Markdown parser
  of record; the crate exposes `to_mdast`, byte-faithful `unist::Position`,
  and the mdast vocabulary required by RFC 0001 section 6.
  Date/Author: 2026-06-05, plan author.

- Decision: keep the PyO3 bridge dictionary an internal mirror of the
  canonical JSON IR. Surface the canonical JSON itself as a `_canonical_json`
  field so Python tests can assert byte-faithful parity against the Rust
  serializer.
  Rationale: freezing the PyO3 dict as a contract would lock the project
  into a specific dictionary shape and resist future refactors. The typed
  Python `model.Document` is the supported consumer surface; the parity
  field gives the test suite a single oracle for bridge drift.
  Date/Author: 2026-06-05, plan author.

- Decision: add the missing Markdown fixtures (frontmatter, inline-markup
  paragraph, soft-break paragraph, CRLF soft-break paragraph) under
  `tests/fixtures/corpus/markdown/valid/` as part of 2.1.1 rather than
  amending roadmap item 1.3.1.
  Rationale: the fixtures are required to prove the segments invariant.
  Adding them in this slice keeps the work atomic and the roadmap entries
  truthful (1.3.1 was satisfied at the time; the gap is a slice-design
  issue, not a slipped deliverable).
  Date/Author: 2026-06-05, plan author.

- Decision: defer Kani, Verus, and CrossHair for 2.1.1. Use `proptest` for
  the segments-concatenation invariant.
  Rationale: the invariant is over an unbounded input space and is
  well-suited to randomized property testing. Bounded model checking would
  cap input length artificially; deductive proof tools would require a
  formal model of mdast that does not exist. Revisit only when there is a
  load-bearing safety invariant.
  Date/Author: 2026-06-05, plan author.

- Decision: write a short new ADR (proposed number ADR 005) recording that
  the PyO3 bridge wire format is an internal mirror of the canonical IR
  JSON and is not a public contract.
  Rationale: ADR 002 covers the packaging boundary; ADR 003 covers the v1
  syntax and locale promises. Neither describes the in-process transport
  shape. A short, focused ADR is clearer than amending one of the existing
  ADRs and gives later slices an obvious place to revisit transport
  decisions if necessary.
  Date/Author: 2026-06-05, plan author.

- Decision: remove the `_canonical_json` bridge field. Expose canonical JSON
  through a separate, narrowly-scoped bridge entry point
  (`canonical_json_for_ir_document_py`). Implement
  `Document.to_canonical_json()` in Python so the parity test compares
  Python-typed-model output to Rust-typed-model output for the same fixture
  using the Rust `insta` snapshot file as the oracle.
  Rationale: a `_canonical_json` field on the envelope dict produces a
  self-referential parity oracle: the bridge has the JSON because the bridge
  built the JSON. A separate function makes the oracle explicit, simplifies
  the dictionary shape, and gives the future `dump-ir` command a clean
  building block. Rejected alternative: drop the dict mirror entirely and
  always parse JSON in Python; rejected because the dict mirror is the
  natural performance path for the typed-model conversion and the existing
  bridge already follows this pattern.
  Date/Author: 2026-06-05, plan author after Logisphere review.

- Decision: do not introduce `Tree` or `Node` Rust types in 2.1.1. Use
  zero-sized `TreesSentinel` and `NodesSentinel` markers that serialize as
  empty JSON arrays. 2.1.2 will replace them with the typed collections.
  Rationale: defining `Tree` and `Node` in 2.1.1 forces a guess at the mdast
  representation that 2.1.2 will then refine. Shipping placeholders avoids a
  rename across every dependent crate.
  Date/Author: 2026-06-05, plan author after Logisphere review.

- Decision: `IrDocument.metadata` uses a typed `BTreeMap<String,
  EnvelopeJsonValue>` whose value enum admits null, bool, signed integer,
  string, array, and object only. Float values are rejected at construction.
  Rationale: this removes the long-term divergence hazard between Rust and
  Python JSON serializers for floating-point values. Later slices may add a
  float variant once a single formatting rule is pinned across both
  languages.
  Date/Author: 2026-06-05, plan author after Logisphere review.

- Decision: pin `sha2 = "0.10"`, not `"0.11"`. The 0.11 line had not been
  published at planning time; 0.10 is the stable current version.
  Rationale: corrects a draft error surfaced by the Logisphere review.
  Date/Author: 2026-06-05, plan author after Logisphere review.

- Decision: enforce the workspace `result_large_err = "deny"` lint through a
  `static_assertions::const_assert!` pinning the size of `ExtractError`.
  Rationale: error variants tend to grow as features land; the lint catches
  this but the assertion makes the budget explicit and gives future authors
  a clear signal to `Box`-wrap rather than working around the lint.
  Date/Author: 2026-06-05, plan author after Logisphere review.

- Decision: `Region.id` follows document walk order in 2.1.1 (`"r1"`,
  `"r2"`, ...). A content-derived strategy (such as `sha256(scope || span)`)
  may replace it before any analysis cache ships.
  Rationale: walk-order ids are sufficient while there is no cross-run
  cache; content-derived ids carry implementation cost that this slice does
  not need. The decision is recorded so the next slice author can revisit it
  before adding the cache.
  Date/Author: 2026-06-05, plan author after Logisphere review.

- Decision: keep `crates/stilyagi-markdown` as a separate adapter crate
  rather than collapsing into `crates/stilyagi-extract`.
  Rationale: although mdast is currently the only Markdown frontend, keeping
  the adapter crate separate preserves the hexagonal boundary, allows a
  future alternative Markdown parser or a wasm build target to swap in
  without disturbing orchestration, and matches the slice-3 split where
  tree-sitter extraction will land in `crates/stilyagi-tree-sitter`. Cost
  of one extra crate compiled is small; cost of merging later is also
  small, so the choice is reversible if circumstances change.
  Date/Author: 2026-06-05, plan author after Logisphere review.

- Decision: configure proptest with `cases = 64` for the segments-
  concatenation invariant and store regression seeds at
  `crates/stilyagi-markdown/proptest-regressions/segments.txt`. Document the
  `PROPTEST_CASES=512` override for long local runs.
  Rationale: keeps CI runtime predictable while preserving the ability to
  raise coverage during exploratory debugging.
  Date/Author: 2026-06-05, plan author after Logisphere review.

- Decision: protect the CRLF fixture with a scoped `.gitattributes` entry
  marking it `-text` so git does not normalise line endings on checkout.
  Rationale: an autocrlf or `*.md text=auto` rule would silently rewrite the
  fixture and cause spurious soft-break test failures across platforms.
  Date/Author: 2026-06-05, plan author after Logisphere review.

## Outcomes & retrospective

To be filled in at completion. Compare the result against the purpose
statement, record any deferred work, and capture what would be done
differently next time. This section must not claim completion before
roadmap item 2.1.1 is ticked in `docs/roadmap.md`.

## Revision note

2026-06-05: initial draft.

2026-06-05: revised after a Logisphere community-of-experts review. Changes:
canonical JSON style is now fully specified in `Constraints`; `_canonical_json`
removed in favour of a separate bridge entry point and a Python
`Document.to_canonical_json()`; the `IrDocument` Rust shape uses
zero-sized `TreesSentinel`/`NodesSentinel` markers in 2.1.1 and a typed
`EnvelopeJsonValue` enum for `metadata`; `sha2` pinned to `0.10`; major-
version rejection now mandatory on the parser; `result_large_err` lint
enforced by a `static_assertions` budget; Stage D pins a panic boundary,
proptest case budget, and explicit fatal-vs-recoverable error split; Python
typed skeleton brought up to RFC 0001 section 6; `Region.id` derivation
documented; CRLF fixture protected by a `.gitattributes` entry;
`repository-layout.md` added to the Stage I documentation update list;
`Progress` checkboxes now carry per-stage gate criteria; file-count
tolerance tightened to fifteen.

Pending approval before implementation begins.
