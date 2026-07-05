# Parse Markdown suppression directives into the IR (roadmap 2.1.3)

This ExecPlan (execution plan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work
proceeds.

Status: COMPLETE

## Purpose / big picture

Today the Markdown frontend flattens a document into an intermediate
representation (IR) that already carries a `suppressions` array, but nothing
ever fills it: `crates/stilyagi-ir/src/document.rs` initialises
`suppressions: Vec::new()` and the Markdown builder
(`crates/stilyagi-markdown/src/lib.rs`) never touches it. Suppression comments
such as `<!-- stilyagi: ignore-next PUN201 -->` are parsed by `markdown-rs`
into ordinary HTML nodes and then dropped on the floor.

After this change, authoring a canonical Stilyagi suppression directive in a
Markdown file causes that directive to appear as a structured entry in the IR
`suppressions` array, visible in the canonical IR JSON ("dump-ir"). A reader
can observe success by running the Markdown crate's fixture round-trip snapshot
test and seeing a populated `"suppressions"` block whose spans re-slice the
original source bytes, whose `kind` classifies the directive
(`inline`/`range`/`file`), and whose `codes` list the named rule codes. A
blanket inline directive (one that names no code) is refused and recorded as a
non-fatal IR error rather than silently accepted, matching the v1 contract that
"blanket inline suppression is forbidden".

The point of the roadmap item is single-source-of-truth: later rule and CLI
work (2.2.x, 3.1.3) must trust the frontend's `suppressions` array and must not
re-scan comments ad hoc. This plan makes the frontend the sole producer of
suppression state for Markdown.

## Outcome you can observe

1. The AGENTS.md commit gates pass: `make check-fmt`, `make lint`, `make test`,
   and `make typecheck` (AGENTS.md:156; Makefile targets `check-fmt`, `lint`,
   `test`, `typecheck`). Note: `make all` builds and smoke-tests the release
   wheel (Makefile:38 `all: release`; Makefile:48 `release: release-artifact
   smoke-release`) and does NOT run the test suite, Clippy, fmt-check, or `ty`
   typecheck — so it is not the validation gate here.
2. In `crates/stilyagi-markdown`, a new fixture round-trip snapshot shows a
   populated `"suppressions"` array for a document containing canonical
   directives, and each suppression `span` satisfies `source[span]` equal to
   the directive's HTML comment bytes.
3. A blanket inline directive produces an entry in the IR `errors` array and
   *no* corresponding `suppressions` entry.
4. A non-canonical marker (for example the placeholder
   `<!-- stilyagi-disable-next-line terminology -->`) is ignored: it produces
   neither a suppression nor an error, so existing golden snapshots do not
   churn.

## Constraints

Hard invariants that must hold throughout implementation.

- Source fidelity: every suppression `span` MUST be source-backed and
  re-sliceable, i.e. `source[span.start..span.end]` returns the exact directive
  comment bytes. This mirrors the IR business rules in
  `docs/stilyagi-design.md` §7.1 ("Source spans must remain faithful to
  original bytes") and RFC 0001 §7.
- Ownership: suppression parsing lives in the Markdown frontend
  (`crates/stilyagi-markdown`), not in any downstream rule. Design
  `docs/stilyagi-design.md` §7.1 ("Suppression parsing belongs in extraction")
  and roadmap 2.1.3 ("Do not let later rules infer suppression state ad hoc").
- Vocabulary boundary: suppressions are NOT IR regions. They populate the
  document-level `suppressions` array only, never `regions`. This respects
  `docs/adr-005-markdown-region-vocabulary-scope.md`, which fixes the Markdown
  region vocabulary and does not include a suppression/HTML-comment region kind.
- Canonical grammar: the only recognised directive form is the RFC 0003 §9.1
  logical grammar delivered through the Markdown HTML-comment form of RFC 0003
  §9.2, namely `<!-- stilyagi: <verb> [CODE[,CODE...]] -->` where `<verb>` is
  one of `ignore-next`, `disable`, `enable`, `ignore-file`. `ignore-file` may
  omit the code list entirely; the other verbs may not. No second grammar is
  invented (RFC 0003 §9.2 forbids it).
- Blanket refusal (verb-scoped): an *inline* (`ignore-next`) or *range*
  (`disable`/`enable`) directive that names no code MUST be refused, per
  `docs/stilyagi-design.md` §7.1 (`docs/stilyagi-design.md:626`, "Blanket
  inline suppression remains forbidden in v1") and RFC 0003 §9.1
  (`docs/rfcs/0003-stilyagi-cli-contract.md:281`, "Range and inline directives
  MUST name at least one code or prefix"). A *file* (`ignore-file`) directive
  that names no code is NOT refused: the v1 contract permits a whole-file
  exemption without a code (Decision D6), so it is accepted with an empty
  `codes` vector.
- Determinism: suppression order in the array MUST be deterministic (document
  order), consistent with the deterministic-IR requirement in RFC 0001 §9 and
  the existing canonical-JSON contract.
- Do not modify the shared corpus placeholder invariant: `tests/test_corpus.py`
  asserts the placeholder string `stilyagi-disable-next-line` appears in the
  Markdown, Python, and Rust corpus fixtures (roadmap 1.3.1). That placeholder
  is deliberately *not* canonical directive syntax; leave it and its assertions
  untouched (Python/Rust directive parsing is roadmap 3.1.3, out of scope
  here).

## Tolerances (exception triggers)

- Scope: if implementation requires touching more than 12 files or more than
  ~400 net lines of code (excluding new fixtures and regenerated snapshots),
  stop and escalate.
- Schema: if aligning `IrSuppression` to RFC 0001 §8 forces a bump of
  `SCHEMA_VERSION` (`crates/stilyagi-ir/src/lib.rs`, currently `"1.0.0"`) or
  changes the meaning of an already-shipped populated field, stop and escalate
  (see Risk R1 and Decision D2).
- Dependencies: if a new external crate is required (for example a dedicated
  parser for the directive grammar), stop and escalate. The grammar is simple
  enough for hand-written parsing over `&str`.
- Parser behaviour: if `markdown-rs` does not expose HTML comments as
  positioned `Node::Html` nodes as assumed (Risk R2), stop and escalate before
  inventing a byte-scanning workaround.
- Iterations: if the focused tests still fail after 3 attempts on any work
  item, stop and escalate.
- Ambiguity: if the RFC-mandated `origin` field cannot be given a single
  unambiguous meaning (Decision D3), stop and present options.

## Risks

- Risk R1: `IrSuppression` currently has fields `{id, span, rules, reason}`
  which do NOT match RFC 0001 §8 (`{id, kind, codes, span, origin}`). Aligning
  the type changes the canonical IR JSON schema for the `suppressions` element.
  Severity: medium. Likelihood: certain. Mitigation: the array has only ever
  serialised as `[]` (no producer populated it), so no consumer depends on the
  element shape; align now, before the first populated suppression ships, and
  keep `SCHEMA_VERSION` at `1.0.0` because no field *meaning* changes for
  already-emitted data (empty array stays empty). See Decision D2.
- Risk R2: the design assumes `markdown-rs` 1.0.0 surfaces `<!-- ... -->`
  comments as positioned `Node::Html` nodes (both block/flow and inline). The
  crate registry is outside the sandbox and `firecrawl` scraping of docs.rs was
  denied in this planning session (see Surprises S2), so this is pinned by a
  test rather than by reading vendored source. Severity: medium. Likelihood:
  low. Mitigation: work item WI-2's first red test asserts, against the real
  parser, that a lone HTML comment yields a `Node::Html` whose `position`
  re-slices to the comment bytes; if that assumption is false the test fails
  loudly before any wiring is built.
- Risk R3: the fixture `tests/fixtures/corpus/markdown/valid/heading-table-link-suppression.md`
  is named for suppression but its comment uses the non-canonical placeholder
  `stilyagi-disable-next-line terminology`. If the parser were made lenient
  enough to accept it, four existing golden snapshots plus a Python snapshot
  would churn and the 1.3.1 corpus invariant would be muddied. Severity: low.
  Likelihood: low. Mitigation: the parser recognises only the canonical
  `stilyagi:` marker; the placeholder is ignored by design and pinned by a
  regression test (WI-2). See Decision D4.
- Risk R4: HTML comments can appear inline inside a paragraph as well as at
  block level. An inline comment's span still re-slices, but its classification
  as `inline`/`range` must be driven by the directive verb, not by the node's
  block/inline placement. Severity: low. Likelihood: medium. Mitigation:
  classification is a pure function of the verb (WI-2); placement does not enter
  into it.

## Progress

- [x] WI-1: Align `IrSuppression` to the RFC 0001 §8 contract.
- [x] WI-2: Implement the directive-grammar parser/classifier AND wire it into
  Markdown IR construction in one commit (produce `suppressions` and
  inline/range blanket-directive `errors`). The parser and its sole library
  consumer land together so no crate-private item is dead code in the `--lib`
  build (design-review round 3, point 1).
- [x] WI-3: Fixtures, golden snapshots, coverage, and behavioural (BDD)
  observability.
- [x] WI-4: Documentation touch-ups and final full-gate validation.

## Surprises & discoveries

- Observation S1: the `suppressions` array and the `IrSuppression` type already
  exist but are never populated. Evidence:
  `crates/stilyagi-ir/src/document.rs:53` sets `suppressions: Vec::new()`, and
  no code path assigns to `document.suppressions`. Impact: this task is
  "populate and align", not "invent from scratch".
- Observation S2: `IrSuppression` (`crates/stilyagi-ir/src/diagnostics.rs`)
  fields `{id, span, rules, reason}` diverge from RFC 0001 §8
  (`{id, kind, codes, span, origin}`). Evidence: file read versus RFC 0001 §8.
  Impact: WI-1 harmonises the type. Recorded here because it is a real contract
  gap, not an anticipated risk.
- Observation S3: `firecrawl_scrape` of `docs.rs` for the `markdown-rs`
  `mdast::Html` struct was denied in this planning session ("Claude requested
  permissions ... but you haven't granted it yet"), and the Cargo registry
  source lies outside the sandbox's allowed directories. Impact: the
  `markdown-rs` HTML-comment behaviour is pinned by a red test (WI-2) rather
  than by citing vendored source; see Risk R2.
- Observation S4: the full canonical IR envelope (including `"suppressions"`
  and `"schema_version"`) is already snapshotted per-fixture by
  `hardening_fixture_ir_json_round_trips_without_span_drift` in
  `crates/stilyagi-markdown/src/tests.rs`. Impact: the "dump-ir exposes
  suppressions" observable is delivered by adding one `#[case]` to that
  existing harness rather than by building a new dump path.
- Observation S5: the current docs already describe suppression emission from
  the frontend, so WI-4 did not require prose changes. Impact: the docs audit
  was a confirmatory check only; the plan still records the validation step.

## Decision log

- Decision D1: recognise only the canonical RFC 0003 §9.1/§9.2 directive form
  `<!-- stilyagi: <verb> CODE[,CODE...] -->`. Rationale: RFC 0003 §9.2 forbids
  inventing a second suppression grammar; the design (§7.1) and RFC 0001 §8
  treat this as the contract. Date/Author: 2026-07-04, planning agent.
- Decision D2: align `IrSuppression` to RFC 0001 §8 exactly
  (`id`, `kind`, `codes`, `span`, `origin`), dropping the speculative `reason`
  field and renaming `rules` to `codes`, and keep `SCHEMA_VERSION = "1.0.0"`.
  Rationale: no populated suppression has ever been emitted, so no consumer
  depends on the element shape and no field meaning changes for already-emitted
  (empty) data; the directive grammar (RFC 0003 §9.1) has no reason token.
  Escalate if a versioning policy elsewhere treats element-schema changes as
  major. Date/Author: 2026-07-04, planning agent.
- Decision D3: define suppression `origin` as the IR node id (for example
  `"n7"`) of the `Node::Html` comment that produced the directive. Rationale:
  `IrRegion.origin_nodes` already references IR node ids as the "which node
  produced this" link (`crates/stilyagi-ir/src/region.rs:176`), so reusing node
  ids keeps one referencing convention across the IR and gives downstream
  consumers a stable back-pointer. Date/Author: 2026-07-04, planning agent.
- Decision D4: the non-canonical placeholder `stilyagi-disable-next-line ...`
  is ignored entirely (no suppression, no error), because it lacks the
  canonical `stilyagi:` marker. Rationale: preserves the 1.3.1 corpus invariant
  and avoids churning four existing golden snapshots; Python/Rust directive
  parsing is roadmap 3.1.3. Date/Author: 2026-07-04, planning agent.
- Decision D5: map directive verbs to `kind` as: `ignore-next` -> `inline`,
  `disable`/`enable` -> `range`, `ignore-file` -> `file`. The `config` kind of
  RFC 0001 §8 is produced by configuration loading, not by the Markdown
  frontend, and is out of scope here. Rationale: RFC 0003 §9 strata map onto
  RFC 0001 §8 kinds this way. Date/Author: 2026-07-04, planning agent.
- Decision D6: the blanket-code prohibition is scoped by verb, not applied to
  all four verbs. A codeless inline (`ignore-next`) or range
  (`disable`/`enable`) directive is refused (`Rejected(BlanketForbidden)`); a
  codeless file directive (`ignore-file`) is *accepted* as a whole-file
  exemption with an empty `codes` vector. Rationale: RFC 0003 §9.1
  (`docs/rfcs/0003-stilyagi-cli-contract.md:281`) scopes the "MUST name at
  least one code" mandate to "Range and inline directives" and forbids only
  "Blanket inline suppression"; design §7.1 (`docs/stilyagi-design.md:626`)
  forbids only "Blanket inline suppression"; RFC 0003 §9's overview
  (`docs/rfcs/0003-stilyagi-cli-contract.md:268`) enumerates "file-level
  exemptions" as a first-class stratum. Emitting an IR error for a codeless
  `ignore-file` would refuse input the v1 contract permits, contradicting an
  established contract. This supersedes the round-1/2 reading that refused
  blanket for every verb, and requires the `IrSuppression.codes` doc comment to
  drop its "never empty" claim. Date/Author: 2026-07-04, planning agent
  (design-review round 3).
- Decision D7: no documentation text needed updating for WI-4 because the
  design and users' guide already describe suppression emission from the
  frontend. Rationale: the docs audit was confirmatory, not corrective, so the
  durable record is the completed validation step rather than a prose diff.
  Date/Author: 2026-07-05, implementation agent.

## Outcomes & retrospective

The roadmap is complete. Markdown suppression directives now flow from the
frontend into the IR `suppressions` array, and the canonical snapshot plus BDD
coverage prove the contract end to end:

- canonical directives populate the IR with source-faithful spans
- blanket inline and range directives without codes are rejected as IR errors
- file-level directives without codes are accepted as whole-file exemptions
- the existing placeholder suppression fixture remains ignored

Validation is green at the required gates: `make check-fmt`, `make typecheck`,
`make lint`, `make test`, `make markdownlint`, and `make nixie`.

## Context and orientation

The reader is assumed to know nothing about this repository. Key facts:

- The workspace is a Rust/Python hybrid. Markdown extraction is a Rust crate;
  Python consumes the IR through a PyO3 bridge. Build/test is driven by the
  `Makefile`. The commit gates are `make check-fmt`, `make lint`, `make test`,
  and `make typecheck` (AGENTS.md:156). Do NOT rely on `make all` as a gate:
  `all: release` (Makefile:38) builds and smoke-tests the release wheel
  (Makefile:48-70) but runs none of the test suite, Clippy, fmt-check, or `ty`
  typecheck.
- The IR types live in `crates/stilyagi-ir/`:
  - `src/document.rs` — `IrDocument` envelope. Field
    `pub suppressions: Vec<IrSuppression>` at line 30; constructed empty in
    `IrDocument::empty` at line 53. `to_canonical_json` (line 65) is the
    canonical "dump-ir" serialisation (deterministic pretty JSON).
  - `src/diagnostics.rs` — `IrSuppression` and `IrError` (the non-fatal anomaly
    type with `{code, message, span}`).
  - `src/region.rs` — `IrRegion`, `RegionKind`, and `origin_nodes` (line 176),
    the existing node-id back-reference convention.
  - `src/lib.rs` — re-exports and `SCHEMA_VERSION` (line 24).
- The Markdown frontend lives in `crates/stilyagi-markdown/`:
  - `src/lib.rs` — public entry `markdown_ir_document` (line 127) and the
    internal `markdown_ir_document_with_context` (line 154) which parses the AST
    with `to_mdast`, builds nodes/regions via `MarkdownIrBuilder`, sets
    `document.nodes`/`document.regions`, then runs
    `validate_ir_consistency`. This is where `document.suppressions` and
    `document.errors` must be populated.
  - `src/builder.rs` — `MarkdownIrBuilder`. `push_node` (line 54) assigns node
    ids `n0`, `n1`, ... in pre-order and maps every mdast node into an
    `IrNode`. `node_kind(node)` returns `"html"` for `Node::Html`
    (`src/node_kind.rs:22`).
  - `src/tests.rs` — the parameterised `#[case]` harness
    `hardening_fixture_ir_json_round_trips_without_span_drift` (line ~121) that
    builds the full IR, serialises canonical JSON, checks span re-slicing, and
    `insta::assert_snapshot!`s the envelope. Snapshots live in
    `crates/stilyagi-markdown/src/snapshots/`.
  - `src/tests/properties.rs` — proptest-based invariants over generated
    Markdown.
  - `src/tests/markers.rs` — existing unit tests (a natural home for
    grammar-level unit cases if a dedicated module is not created).
- Markdown fixtures are at
  `tests/fixtures/corpus/markdown/valid/*.md.fixture` (read in tests via
  `stilyagi_test_support::read_corpus_fixture`).
- Behavioural (BDD) tests use `rstest-bdd` with `.feature` files; see
  `crates/stilyagi-extract/tests/features/python_docstring_extraction.feature`
  and `crates/stilyagi-extract/tests/extract/python_docstring_bdd.rs`. The
  `stilyagi-extract` crate re-exports the Markdown path via `extract_document`,
  so a Markdown suppression scenario belongs there.

Terms of art (defined on first use):

- IR (intermediate representation): the structured, source-mapped document the
  frontend emits; its canonical serialisation is deterministic JSON.
- Directive/suppression: an author-written comment asking Stilyagi to ignore
  one or more rule codes for the next block, a range, or the whole file.
- Region: a lintable prose span in the IR. Suppressions are not regions.
- Span: a half-open byte range `[start, end)` into the original source.

Design and contract references, by section:

- `docs/stilyagi-design.md` §7.1 — suppression syntax, "Suppression parsing
  belongs in extraction", "Suppression state must be visible in IR and debug
  output", "Blanket inline suppression remains forbidden in v1".
- `docs/rfcs/0001-stilyagi-intermediate-representation.md` §8 — suppression
  fields `{id, kind, codes, span, origin}` and kinds
  `inline`/`range`/`file`/`config`; §9 — canonical JSON and compatibility
  rules.
- `docs/rfcs/0003-stilyagi-cli-contract.md` §9, §9.1, §9.2 — three suppression
  strata, the logical directive grammar, the Markdown HTML-comment form, and
  the prohibition on inventing a second grammar.
- `docs/adr-003-v1-contract-scope.md` — v1 syntax/contract scope (Markdown
  first; blanket suppression forbidden).
- `docs/adr-005-markdown-region-vocabulary-scope.md` — the fixed Markdown
  region vocabulary (justifies keeping suppressions out of `regions`).
- `AGENTS.md` — quality gates and the testing rules (rstest, rstest-bdd, insta
  snapshots, proptest for new invariants; en-GB Oxford spelling in prose and
  comments).

## Plan of work

Delivery is test-first (Red-Green-Refactor) throughout. Each work item is
independently committable and must pass the gates named in its "Validation"
paragraph before the next begins.

### WI-1: Align `IrSuppression` to the RFC 0001 §8 contract

Implements: RFC 0001 §8; `docs/stilyagi-design.md` §7.1.

Read first: RFC 0001 §8 and §9; `crates/stilyagi-ir/src/diagnostics.rs`;
`crates/stilyagi-ir/src/lib.rs` (`SCHEMA_VERSION`, re-exports).

Skills to load: `rust-router` (routes to `rust-types-and-apis` for the enum and
serde attributes, and `rust-unit-testing`); `en-gb-oxendict` for doc comments.

Change `IrSuppression` in `crates/stilyagi-ir/src/diagnostics.rs` to:

```rust
// crates/stilyagi-ir/src/diagnostics.rs
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SuppressionKind {
    Inline,
    Range,
    File,
    Config,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IrSuppression {
    /// Stable, document-local suppression identifier (for example `s0`).
    pub id: String,
    /// Directive stratum: inline, range, file, or config.
    pub kind: SuppressionKind,
    /// Rule codes or prefixes named by the directive. Non-empty for inline
    /// and range directives (which MUST name at least one code, RFC 0003
    /// §9.1); MAY be empty for a file-scope (`ignore-file`) directive, which
    /// the v1 contract permits to name no code (Decision D6).
    pub codes: Vec<String>,
    /// Source span covering the directive comment.
    pub span: SourceSpan,
    /// IR node id of the comment node that produced this directive.
    pub origin: String,
}
```

Re-export `SuppressionKind` from `crates/stilyagi-ir/src/lib.rs` alongside
`IrSuppression`. Keep `SCHEMA_VERSION = "1.0.0"` (Decision D2); if any check
suggests a bump is required, stop per the Schema tolerance.

Tests (Red first): add a serde round-trip unit test in
`crates/stilyagi-ir/src/tests/mod.rs` (or a new `suppression.rs` test module
wired the same way as the existing test modules) asserting that a hand-built
`IrSuppression { kind: Inline, codes: vec!["PUN201"], ... }` serialises with
keys `id`, `kind` (`"inline"`), `codes`, `span`, `origin` and deserialises back
to an equal value. This is a unit test with no runtime component, so the
observable substitute for a "running system" is the serde contract itself.

Note on snapshots: existing full-envelope snapshots emit `"suppressions": []`;
because the array stays empty for all current fixtures, WI-1 alone should not
change any snapshot. If any snapshot changes, that is a signal the element
schema leaked into shipped data — investigate before accepting.

Validation: run the AGENTS.md commit gates (AGENTS.md:156) — `make check-fmt`,
`make lint`, `make test`, and `make typecheck` — delegated to `scrutineer`. No
`docs/**.md` is touched in this work item, so `make markdownlint`/`make nixie`
are not required. (`make all` is not a gate: it only builds and smoke-tests the
release wheel.)

### WI-2: Directive-grammar parser and its Markdown IR wiring (one commit)

Implements: RFC 0003 §9.1 and §9.2; `docs/stilyagi-design.md` §7.1 (blanket
prohibition, "visible in IR"); RFC 0001 §8; roadmap 2.1.3 ("Do not let later
rules infer suppression state ad hoc").

Gate-passability note (design-review round 3, point 1): the pure parser
(`parse_comment_directive`, `verb_kind`) is crate-private
(`pub(crate)`/module-private) and its ONLY library consumer is the IR wiring in
`markdown_ir_document_with_context`. `make lint` runs `cargo clippy
--all-targets --workspace -- -D warnings` (AGENTS.md:172; Makefile:117); the
plain `--lib` target compiles with `cfg(test)` OFF, so a crate-private item
referenced only from `#[cfg(test)]` code is `dead_code` and `-D warnings`
promotes it to a hard error. Existing `pub(crate)` helpers such as
`flatten_region`/`validate_ir_consistency` avoid this only because non-test lib
code calls them. Therefore the parser and its wiring MUST be introduced in the
SAME commit as a single work item; committing the parser alone would fail
`make lint`. This is the reason the former WI-2 (parser) and WI-3 (wiring) are
fused here.

Read first: RFC 0003 §9.1/§9.2; `crates/stilyagi-markdown/src/node_kind.rs`;
`crates/stilyagi-markdown/src/source_text.rs` (existing source-byte slicing
patterns); `crates/stilyagi-markdown/src/lib.rs`
(`markdown_ir_document_with_context`); `crates/stilyagi-markdown/src/builder.rs`
(`push_node`, node-id assignment); `crates/stilyagi-ir/src/diagnostics.rs`
(`IrError`).

Skills to load: `rust-router` -> `rust-types-and-apis` (small parser API,
`Result`), `rust-errors` (error enum), `rust-unit-testing`, and `proptest`
(property tests); `leta` to trace node-id assignment and callers of
`markdown_ir_document_with_context`. `en-gb-oxendict` for comments.

Order of work within the single commit: (a) pin the parser assumption, (b)
build the pure parser module, (c) wire it into IR construction. All three land
together so the crate-private parser is exercised by non-test lib code the
moment it is introduced.

First, pin the parser assumption (Risk R2). Add a red test in
`crates/stilyagi-markdown/src/tests` that parses the source
`"<!-- stilyagi: ignore-next PUN201 -->\n"` with `parse_markdown_ast` and
asserts that the tree contains a node whose `node_kind` is `"html"` and whose
source span re-slices to the exact comment bytes. This proves `markdown-rs`
exposes positioned HTML comments before any wiring depends on it. If it fails,
stop (Parser-behaviour tolerance).

Then create a new module `crates/stilyagi-markdown/src/suppression.rs` with a
pure API (no IR types, no I/O) operating on the raw comment text:

```rust
// crates/stilyagi-markdown/src/suppression.rs
pub(crate) enum DirectiveVerb { IgnoreNext, Disable, Enable, IgnoreFile }

pub(crate) struct ParsedDirective {
    pub verb: DirectiveVerb,
    pub codes: Vec<String>,
}

pub(crate) enum DirectiveOutcome {
    /// Not a Stilyagi directive at all (no canonical `stilyagi:` marker);
    /// callers ignore it entirely.
    NotADirective,
    /// A well-formed directive.
    Parsed(ParsedDirective),
    /// A recognised directive that violates a rule (for example blanket).
    Rejected(DirectiveError),
}

pub(crate) enum DirectiveError {
    /// Named no code where at least one is required.
    BlanketForbidden,
    /// Verb token was not one of the four canonical verbs.
    UnknownVerb,
}

/// Parse the *inner text* of an HTML comment (the bytes between `<!--` and
/// `-->`), tolerant of surrounding whitespace.
pub(crate) fn parse_comment_directive(inner: &str) -> DirectiveOutcome;
```

Parsing rules (pin each with a test):

1. Trim surrounding ASCII whitespace. The comment must begin with the marker
   `stilyagi:` (exactly that token, colon included) after trimming; otherwise
   return `NotADirective`. The placeholder `stilyagi-disable-next-line`
   therefore returns `NotADirective` (Decision D4).
2. The next whitespace-delimited token is the verb; map to `DirectiveVerb` or
   return `Rejected(UnknownVerb)`.
3. The remainder is a comma-separated code list. Split on `,`, trim each token,
   discard empty tokens. Codes are stored verbatim (the frontend does not yet
   validate codes against a rule registry, which does not exist).
4. If the resulting code list is empty, apply the blanket rule *by verb*
   (Decision D6). RFC 0003 §9.1 requires at least one code only for range and
   inline directives ("Range and inline directives MUST name at least one code
   or prefix. Blanket inline suppression is forbidden in v1",
   `docs/rfcs/0003-stilyagi-cli-contract.md:281`), and design §7.1 forbids only
   "Blanket inline suppression" (`docs/stilyagi-design.md:626`). Neither
   forbids a codeless whole-file exemption. Therefore:
   - For `ignore-next` (inline) and `disable`/`enable` (range) verbs, an empty
     code list returns `Rejected(BlanketForbidden)`.
   - For `ignore-file` (file) an empty code list is *permitted*: return
     `Parsed` with an empty `codes` vector (a whole-file exemption naming no
     code). RFC 0003 §9 explicitly lists "file-level exemptions"
     (`docs/rfcs/0003-stilyagi-cli-contract.md:268`) alongside inline/range
     suppressions, and §9.1's mandate does not name `ignore-file`.
5. Otherwise return `Parsed`.

Because the blanket rule is verb-sensitive, `parse_comment_directive` must know
the verb before deciding rule 4; parse the verb (rule 2) first, then classify
the empty-code case against that verb.

Also provide `verb_kind(verb) -> SuppressionKind` implementing Decision D5.

Parser tests (Red first, then Green):

- Unit (rstest, parameterised) in a new
  `crates/stilyagi-markdown/src/tests/suppression.rs` module (wired via
  `#[path = ...]` like the sibling test modules): each verb parses; codes with
  and without spaces; `ignore-file MD,DOC` yields two codes; codeless inline
  `stilyagi: ignore-next` is `Rejected(BlanketForbidden)`; codeless range
  `stilyagi: disable` and `stilyagi: enable` are `Rejected(BlanketForbidden)`;
  codeless file `stilyagi: ignore-file` is `Parsed` with an empty `codes`
  vector and (via `verb_kind`) `SuppressionKind::File` (Decision D6); unknown
  verb rejected; `stilyagi-disable-next-line terminology` and a plain
  `<!-- comment -->` both return `NotADirective`.
- Property (proptest), added to
  `crates/stilyagi-markdown/src/tests/properties.rs` or the new suppression
  test module: for a generated verb plus a non-empty list of code-like tokens
  (`[A-Z][A-Z0-9]{0,7}`) joined by commas with arbitrary interior spaces,
  `parse_comment_directive` returns `Parsed` with codes equal to the trimmed
  input tokens in order; for `ignore-next`/`disable`/`enable` with an empty
  code list it always returns `Rejected(BlanketForbidden)`; and for
  `ignore-file` with an empty code list it always returns `Parsed` with empty
  `codes` (Decision D6).

Then wire the parser into IR construction (same commit).

Design: extend `MarkdownIrBuilder` to record, during `push_node`, a lightweight
list of HTML-comment candidates as `(node_id, SourceSpan)` whenever
`node_kind(node) == "html"`. After the builder run in
`markdown_ir_document_with_context`, iterate those candidates in document order
and, for each:

1. Slice the comment bytes from `source` using the recorded span, strip the
   `<!--` / `-->` delimiters to obtain the inner text, and call
   `parse_comment_directive`.
2. On `Parsed`, push an `IrSuppression { id: "s{n}", kind: verb_kind(verb),
   codes, span, origin: node_id }` onto `document.suppressions`.
3. On `Rejected(BlanketForbidden)`, push an `IrError { code:
   "suppression-blanket-forbidden", message: <descriptive>, span: Some(span) }`
   onto `document.errors`; emit no suppression.
4. On `Rejected(UnknownVerb)`, push an `IrError { code:
   "suppression-unknown-verb", ... }`; emit no suppression.
5. On `NotADirective`, do nothing.

Keep classification purely verb-driven (Risk R4). Suppression ids are assigned
in document order for determinism. Ensure `validate_ir_consistency` still
passes; if it needs to learn about suppression spans (it currently validates
nodes/regions/segments), extend it minimally so a suppression span that does
not re-slice is a hard build error, reinforcing the source-fidelity constraint.

Wiring tests (Red first) — in the same commit as the parser:

- Unit (rstest) in `crates/stilyagi-markdown/src/tests/suppression.rs`: build
  the IR for an in-test source containing one `ignore-next PUN201`, a
  `disable STY`/`enable STY` pair, and one `ignore-file MD,DOC`; assert
  `document.suppressions` has the expected `kind`/`codes`/`origin` and that each
  `span` re-slices to the comment bytes; assert `document.errors` is empty.
- Unit (rstest): a codeless file directive `<!-- stilyagi: ignore-file -->`
  yields exactly one `IrSuppression` with `kind == SuppressionKind::File`, an
  empty `codes` vector, and a re-slicing span, and `document.errors` is empty
  (Decision D6 — a codeless whole-file exemption is permitted, not an error).
- Unit (rstest): a blanket inline `<!-- stilyagi: ignore-next -->` and a blanket
  range `<!-- stilyagi: disable -->` each yield no suppression and exactly one
  `IrError` with code `"suppression-blanket-forbidden"` whose span re-slices
  (verb-scoped refusal, Decision D6).
- Regression (rstest): a source containing the placeholder
  `<!-- stilyagi-disable-next-line terminology -->` yields empty `suppressions`
  and empty `errors` (Decision D4, Risk R3).

Validation: run the AGENTS.md commit gates (AGENTS.md:156) — `make check-fmt`,
`make lint`, `make test`, and `make typecheck` — delegated to `scrutineer`.
Because the parser and its lib consumer land together, the crate-private parser
is exercised by non-test lib code and `make lint`'s `-D warnings` `--lib` build
sees no dead code (design-review round 3, point 1). No `docs/**.md` is touched
in this work item, so `make markdownlint`/`make nixie` are not required.
(`make all` is not a gate: it only builds and smoke-tests the release wheel.)

### WI-3: Fixtures, golden snapshots, coverage, and behavioural observability

Implements: roadmap 2.1.3 success ("dump-ir exposes suppressions"); AGENTS.md
testing rules (golden/insta snapshots, rstest-bdd); RFC 0003 §9.2 (Markdown
form).

Read first: `crates/stilyagi-markdown/src/tests.rs`
(`hardening_fixture_ir_json_round_trips_without_span_drift`);
`crates/stilyagi-extract/tests/extract/python_docstring_bdd.rs` and
`crates/stilyagi-extract/tests/features/python_docstring_extraction.feature`.

Skills to load: `rust-router` -> `rust-unit-testing`; `nextest` (test runner
conventions); `en-gb-oxendict` for fixture prose.

Add a new fixture
`tests/fixtures/corpus/markdown/valid/suppression-directives.md.fixture`
containing a heading and paragraph plus canonical directives exercising every
frontend kind:

```markdown
<!-- markdownlint-disable -->
# Suppression Fixture

<!-- stilyagi: ignore-next PUN201 -->
Apples, bananas and pears.

<!-- stilyagi: disable STY -->
A questionable section.
<!-- stilyagi: enable STY -->

<!-- stilyagi: ignore-file MD,DOC -->
```

(The fixture is a `.fixture` file, not linted Markdown, so it does not enter the
`make markdownlint`/`make nixie` path; only real `docs/**` Markdown does.)

Add one `#[case]` to `hardening_fixture_ir_json_round_trips_without_span_drift`
in `crates/stilyagi-markdown/src/tests.rs` referencing the new fixture with a
snapshot name such as `suppression_directives` and an `ExpectedText` that
appears in an emitted paragraph region. Running it with `INSTA_UPDATE` (or
`cargo insta review`) produces a new full-envelope snapshot in
`crates/stilyagi-markdown/src/snapshots/` whose `"suppressions"` block is
populated with three entries (`inline`, two `range`, `file`) — this is the
"dump-ir exposes suppressions" observable. The existing test body already
asserts span re-slicing for source-backed segments; add an assertion in this
case (or a dedicated sibling test) that every suppression span re-slices too.

Add a coverage test (rstest) that asserts, for the new fixture, that the set of
emitted suppression `kind`s covers `inline`, `range`, and `file`, mirroring the
style of `valid_markdown_corpus_covers_promised_markdown_region_kinds` in
`src/tests/coverage.rs`.

Behavioural (BDD): add
`crates/stilyagi-extract/tests/features/markdown_suppression.feature` and a
matching `rstest-bdd` step file
`crates/stilyagi-extract/tests/extract/markdown_suppression_bdd.rs`, wired into
the extract test harness the same way as `python_docstring_bdd.rs`. Feature
specification to embed:

```gherkin
Feature: Markdown suppression directives surface in the IR

  Scenario: A canonical ignore-next directive becomes a suppression
    Given a Markdown document with a "stilyagi: ignore-next PUN201" comment
    When the document is extracted
    Then the IR suppressions contain one inline entry naming PUN201
    And the suppression span re-slices to the directive comment

  Scenario: A blanket directive is refused
    Given a Markdown document with a "stilyagi: disable" comment naming no code
    When the document is extracted
    Then the IR suppressions are empty
    And the IR errors contain a blanket-forbidden entry
```

The BDD scenario runs before the wiring is complete (Red) and passes after
(Green); it exercises the public `extract_document` path, proving the
observable travels through the extraction boundary the same way downstream
consumers will see it.

Validation: run the AGENTS.md commit gates (AGENTS.md:156) — `make check-fmt`,
`make lint`, `make test`, and `make typecheck` — delegated to `scrutineer`. The
new fixture is a `.fixture` file and the feature/step files live under
`crates/`, so no `docs/**.md` is touched and `make markdownlint`/`make nixie`
are not required. (`make all` is not a gate: it only builds and smoke-tests the
release wheel and would not run the new snapshot, coverage, or BDD tests.)

### WI-4: Documentation touch-ups and final validation

Implements: `AGENTS.md` (keep `docs/` current).

Read first: `docs/developers-guide.md` and `docs/stilyagi-design.md` §7.1 to
confirm whether either needs a sentence noting that Markdown suppression
directives are now populated by the frontend.

Skills to load: `scribe` for prose edits; `en-gb-oxendict` for spelling.

If (and only if) a docs file materially describes suppression state as
unimplemented, update it to reflect that the Markdown frontend now emits
`suppressions`. Keep edits minimal and en-GB Oxford-spelled. If no docs change
is warranted, record that in the Decision Log and skip.

Validation: run the AGENTS.md commit gates (AGENTS.md:156) — `make check-fmt`,
`make lint`, `make test`, and `make typecheck` — delegated to `scrutineer`; and,
if any `docs/**.md` file was edited in this work item, additionally
`make markdownlint` and `make nixie` (the Markdown gates; Makefile:125,128).
(`make all` is not a gate: it only builds and smoke-tests the release wheel.)

## Concrete steps

Run everything from the worktree root
`/home/leynos/Projects/stilyagi.worktrees/roadmap-2-1-3`.

1. Per work item, write the red test(s) first and run the focused crate tests to
   observe the expected failure. Focused runs during development, for example:

   ```bash
   cargo test -p stilyagi-ir --lib
   cargo test -p stilyagi-markdown --lib
   cargo test -p stilyagi-extract --test extract_integration
   ```

   Expect the new test to fail for the intended reason before implementation.

2. Implement the minimal change to make the red test pass; rerun the focused
   test.

3. For WI-3 snapshots, review and accept the new insta snapshot deliberately
   (for example `cargo insta review`), confirming the `"suppressions"` block is
   populated and spans re-slice; never blind-accept.

4. Before each commit, delegate the full gate run to the `scrutineer` subagent
   (per the repository's gate policy) rather than running gates in the planning
   context. The authoritative gates are the AGENTS.md commit-gate set
   (AGENTS.md:156):

   ```bash
   make check-fmt
   make lint
   make test
   make typecheck
   ```

   Do NOT substitute `make all`: `all: release` (Makefile:38) only builds and
   smoke-tests the release wheel (Makefile:48-70) and runs none of `cargo test
   --workspace`, Clippy, fmt-check, or the `ty` typecheck — so a green `make
   all` would leave every test written for this task unexecuted.

   If a `docs/**.md` file was edited (only possible in WI-4), also run the
   Markdown gates:

   ```bash
   make markdownlint
   make nixie
   ```

5. Commit each work item separately with an en-GB Oxford-spelled message
   referencing roadmap 2.1.3.

## Validation and acceptance

Quality criteria ("done"):

- Tests: `make test` (`cargo test --workspace`, AGENTS.md:178-182) passes,
  including the new unit, property, coverage, golden snapshot, and BDD tests.
  Each new test fails before its work item's implementation and passes after
  (Red-Green recorded in Progress).
- Lint/typecheck: `make lint` (Rust Clippy `-D warnings`, Python lint, Whitaker)
  and `make typecheck` (Makefile:120-123) pass with no new warnings (AGENTS.md:
  fix warnings, do not silence). `make check-fmt` passes (Rust + Python format
  check).
- Observable: the `suppression_directives` fixture snapshot shows a populated
  `"suppressions"` array; the blanket-directive test shows an `errors` entry and
  no suppression; the placeholder regression test shows neither.

Do NOT use `make all` as the acceptance gate: `all: release` (Makefile:38) only
builds and smoke-tests the release wheel (Makefile:48-70); it never runs the
workspace test suite, Clippy, `check-fmt`, or the `ty` typecheck, so it cannot
observe any of the Red-Green evidence above.

Quality method:

- Delegate the AGENTS.md commit gates — `make check-fmt`, `make lint`,
  `make test`, and `make typecheck` (and, only for WI-4 `docs/**.md` edits,
  `make markdownlint` and `make nixie`) — to the `scrutineer` gate-runner
  subagent; read the cited log on failure and re-run only after a fix.

Red-Green-Refactor evidence to record in Progress as work proceeds:

- Red: focused `cargo test -p <crate>` command and the expected failure message.
- Green: the same command passing after the minimal change.
- Refactor: the AGENTS.md commit gates (`make check-fmt`, `make lint`,
  `make test`, `make typecheck`) passing after cleanup.

## Idempotence and recovery

- All steps are re-runnable. Re-running tests or `make all` is safe.
- Snapshot acceptance is the only manual, semi-destructive step; if an
  unexpected snapshot appears, reject it and investigate rather than accepting.
- New files (fixture, feature, step file, suppression module) are additive and
  can be deleted to revert a work item cleanly.
- If WI-1's schema change is escalated (Schema tolerance), revert
  `crates/stilyagi-ir/src/diagnostics.rs` to restore the prior type; no other
  work item can start until WI-1 lands.

## Interfaces and dependencies

Prescriptive end-state:

- In `crates/stilyagi-ir/src/diagnostics.rs`: `pub enum SuppressionKind {
  Inline, Range, File, Config }` (serde `snake_case`) and `pub struct
  IrSuppression { id: String, kind: SuppressionKind, codes: Vec<String>, span:
  SourceSpan, origin: String }`, both re-exported from
  `crates/stilyagi-ir/src/lib.rs`.
- In `crates/stilyagi-markdown/src/suppression.rs` (new, crate-private):
  `parse_comment_directive(inner: &str) -> DirectiveOutcome` and
  `verb_kind(verb: DirectiveVerb) -> stilyagi_ir::SuppressionKind`.
- In `crates/stilyagi-markdown/src/lib.rs`:
  `markdown_ir_document_with_context` populates `document.suppressions` and
  `document.errors` from recorded HTML-comment candidates before validation.
- No new external crate dependencies.

## Revision note

Initial draft (2026-07-04). Establishes the five work items, the RFC 0001 §8
schema alignment, the RFC 0003 §9 grammar, and the "dump-ir" snapshot as the
observable. Records the `firecrawl`/registry tooling limits (S2/S3) and pins the
`markdown-rs` HTML-comment assumption with a red test (Risk R2) rather than an
unverifiable citation.

Revision 2 (2026-07-04). Design-review round 2: corrected the validation gate
throughout. The plan previously named `make all` as the authoritative gate in
every work item, in Concrete Steps step 4, and in Validation & Acceptance.
Verified against the worktree `Makefile`: `.DEFAULT_GOAL := all`, `all: release`
(Makefile:38), `release: release-artifact smoke-release` (Makefile:48), where
`release-artifact` runs only `maturin build --release` (Makefile:50-52) and
`smoke-release` builds a wheel and runs `stilyagi.smoke` (Makefile:60-70). Thus
`make all` compiles and smoke-tests the release wheel but never runs the
workspace test suite, Clippy, `ty` typecheck, or fmt-check. Replaced it
everywhere with the AGENTS.md commit-gate set (AGENTS.md:156) — `make check-fmt`,
`make lint`, `make test` (`cargo test --workspace`, AGENTS.md:178-182), and
`make typecheck` (Makefile:120-123) — retaining `make markdownlint` and
`make nixie` (Makefile:125,128) as the additional gates for the documentation
work item's `docs/**.md` edit.

Revision 3 (2026-07-04). Design-review round 3 resolved two blocking points.

Point 1 (WI-2 not independently gate-passable): the former WI-2 introduced a
crate-private parser (`parse_comment_directive`, `verb_kind`) whose only
consumer until the old WI-3 was `#[cfg(test)]` code. `make lint` runs
`cargo clippy --all-targets --workspace -- -D warnings` (AGENTS.md:172;
Makefile:117); the `--lib` target compiles with `cfg(test)` OFF, so a
crate-private item used only from test code is `dead_code` and `-D warnings`
promotes it to an error — the parser-only commit would have failed `make lint`.
Fixed by fusing the parser and its IR wiring into a single work item (now WI-2)
so the parser is exercised by non-test lib code the moment it is introduced.
Work items renumbered: former WI-4 -> WI-3 (fixtures/snapshots/BDD), former
WI-5 -> WI-4 (documentation).

Point 2 (blanket rule over-reached the contract): the round-1/2 parsing rule 4
and Decision D5 classified a codeless `<!-- stilyagi: ignore-file -->` as
`Rejected(BlanketForbidden)` and emitted a `suppression-blanket-forbidden` IR
error "for all four verbs". RFC 0003 §9.1
(`docs/rfcs/0003-stilyagi-cli-contract.md:281`) scopes the "MUST name at least
one code" mandate to "Range and inline directives" and forbids only "Blanket
inline suppression"; design §7.1 (`docs/stilyagi-design.md:626`) forbids only
"Blanket inline suppression"; and RFC 0003 §9's overview
(`docs/rfcs/0003-stilyagi-cli-contract.md:268`) enumerates "file-level
exemptions" as a first-class stratum. Emitting an error for a codeless
`ignore-file` refused input the v1 contract permits. Fixed by adding Decision
D6: the blanket refusal is now verb-scoped — codeless inline/range directives
are refused, but a codeless `ignore-file` is accepted as a whole-file exemption
with an empty `codes` vector. Corrected parsing rule 4, the "Blanket refusal"
constraint, Decision D5's cross-reference, the `IrSuppression.codes` doc comment
(dropped the "never empty" claim), and added parser and wiring tests for the
codeless-`ignore-file` case.
