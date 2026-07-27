# Extend suppression parsing to Python and Rust syntax-native comments

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
`Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`, `Decision Log`,
and `Outcomes & Retrospective` must be kept up to date as work proceeds.

Status: COMPLETE

## Purpose / big picture

Today Stilyagi only understands suppression directives written in Markdown HTML
comments (`<!-- stilyagi: ignore-next PUN201 -->`). The parser and its rules
live inside the `stilyagi-markdown` crate, so Python and Rust source files
carry no suppression state at all: a `# stilyagi: disable PYDOC210` line in a
`.py` file or a `// stilyagi: ignore-next RUSTDOC110` line in a `.rs` file is
silent noise in the intermediate representation (IR).

Roadmap task 3.1.3 ("Extend suppression parsing to Python and Rust
syntax-native comments"; requires 3.1.1 and 3.1.2) closes that gap. Its success
criterion is: "suppression state is extracted once and applied consistently
across all v1 source syntaxes." After this change:

- The syntax-agnostic directive grammar (the verbs `ignore-next`, `disable`,
  `enable`, `ignore-file`; the comma-separated code list; the blanket-inline
  prohibition) lives in one place and is shared by every extractor.
- A user can add `# stilyagi: ...` directives to Python source and
  `// stilyagi: ...` directives to Rust source, and those directives appear in
  the IR `suppressions` list with the same shape, the same identifiers, the
  same validation, and the same `dump-ir` visibility as Markdown directives.

Observable success: after implementation, extracting a Python or Rust file that
contains a syntax-native directive yields an `IrDocument` whose `suppressions`
vector contains an `IrSuppression` with the correct `kind`, `codes`, `span`,
and a resolvable `origin`; a blanket inline directive yields a
`suppression-blanket-forbidden` IR error exactly as Markdown does; and the
golden IR snapshots for the shared Python and Rust fixtures render the new
directives.

This plan implements the "Suppression syntax" contract in
[docs/stilyagi-design.md](../stilyagi-design.md) §4 (lines 603-626: "Markdown
uses HTML comments; Python uses `#`; Rust and JavaScript use `//`";
"Suppression parsing belongs in extraction"; "Suppression state must be visible
in IR and debug output"; "Blanket inline suppression remains forbidden in v1")
and the "Suppression semantics" bullet in
[docs/developers-guide.md](../developers-guide.md) (lines 454-459: "Suppression
state is extracted once and carried in the IR rather than inferred ad hoc by
individual rules … syntax-native and deliberately narrow"). It also serves the
top-level requirement at design §3 line 179 ("file-level and range-level
suppression directives") and the IR contract at design §7.1 (line 391: the IR
carries "segments, suppressions, and extraction errors").

## Constraints

Hard invariants that must hold throughout implementation. Violation requires
escalation, not a workaround.

- Do not modify anything outside the assigned git worktree at
  `/home/leynos/Projects/stilyagi.worktrees/roadmap-3-1-3`.
- Source spans must remain faithful to original bytes (design §5 "Business
  requirements"). Every emitted `IrSuppression.span` and every emitted comment
  IR node span must be a real byte range of the source; the existing
  source-byte oracle and `validate_ir_consistency` checks must continue to pass.
- Blanket inline suppression remains forbidden in v1 (design §4 line 626;
  developers-guide line 459). `ignore-next`, `disable`, and `enable` directives
  that name no code must produce a `suppression-blanket-forbidden` error, not a
  suppression. `ignore-file` may carry an empty code list.
- The public `IrSuppression` shape in
  `crates/stilyagi-ir/src/diagnostics.rs` (`id`, `kind`, `codes`, `span`,
  `origin`) and the `SuppressionKind` enum must not change. The IR schema
  version must not change: no envelope field is added or removed.
- The directive grammar must be identical across syntaxes. There must be exactly
  one implementation of verb parsing, code parsing, the blanket rule, and the
  verb-to-`SuppressionKind` mapping. No syntax may fork the grammar.
- Existing Markdown suppression behaviour (verbs, error codes
  `suppression-blanket-forbidden` / `suppression-unknown-verb` /
  `suppression-span-invalid`, `s{n}` identifier scheme, origin/span validation)
  must remain byte-for-byte observable; the Markdown golden snapshot for
  `heading-table-link-suppression.md` must not change.
- Rust suppression directives are recognized only in non-doc line comments
  (`//`). Doc comments (`///`, `//!`) and block comments are not suppression
  directives (see Decision Log). Python directives are recognized only in `#`
  line comments.
- Python and Rust emit a source-backed `"comment"` IR node **only** for a
  comment whose delimiter-stripped, trimmed inner text begins with the canonical
  `stilyagi:` marker (as decided by the shared
  `stilyagi_ir::is_directive_marker` predicate). Ordinary comments emit no IR
  node and no candidate; directive-free Python/Rust source files remain
  byte-for-byte identical in the IR and in every golden snapshot. This gate
  must precede node-id allocation so no id is consumed by a non-marker comment.
- en-GB Oxford spelling ("-ize"/"-yse"/"-our") in all new prose, comments, and
  commit messages.

## Tolerances (exception triggers)

- Scope: if any single work item requires changing more than 8 files or more
  than ~400 net lines, stop and escalate.
- Interface: if `IrSuppression`, `SuppressionKind`, or the `IrDocument`
  envelope must change shape to deliver a work item, stop and escalate.
- Dependencies: if a new external crate (beyond the tree-sitter grammars and
  workspace crates already present) is required, stop and escalate.
- Grammar divergence: if any syntax appears to need a directive grammar that the
  shared parser cannot express, stop and escalate rather than forking the
  parser.
- Iterations: if a gate still fails after 3 focused fix attempts on the same
  work item, stop and escalate.
- Ambiguity: if the correct comment-node vocabulary for a grammar cannot be
  confirmed from tree-sitter output within a bounded probe, stop and present
  findings.

## Risks

- Risk: tree-sitter comment node kinds differ from assumptions (`comment` for
  Python; `line_comment` / `block_comment` for Rust). Severity: medium.
  Likelihood: low. Mitigation: the Rust extractor already switches on
  `line_comment` and `block_comment` and classifies doc flavour via
  `classify_doc_comment`
  (`crates/stilyagi-tree-sitter/src/rust/helpers.rs:31-45,143`). WI-Rust reuses
  that exact vocabulary. For Python, WI-Python adds a red test that first
  asserts the `comment` node kind against a real parse before relying on it.
- Risk: emitting synthetic comment IR nodes for directive origins perturbs
  node-id numbering and breaks unrelated golden snapshots. Severity: medium.
  Likelihood: medium. Mitigation: node emission is **directive-gated**
  (Decision Log). The sweep calls `stilyagi_ir::is_directive_marker` on each
  comment's stripped inner text and allocates a node id + candidate **only**
  when the marker matches; ordinary `#`/`//` comments allocate nothing. The
  sweep runs after the existing docstring/doc-comment walk and draws ids from
  the same monotonic counter, so a file with no `stilyagi:` marker keeps its
  existing node ids and its snapshot is byte-for-byte unchanged. Only fixtures
  that contain a `stilyagi:` marker gain nodes; those are new or intentionally
  re-blessed snapshots. This is verified against
  `crates/stilyagi-tree-sitter/src/rust/tests.rs:149`
  (`// stilyagi-disable-next-line …`, a non-marker) which must produce no new
  node and no snapshot churn.
- Risk: a directive comment sitting inside a tree-sitter `ERROR` subtree is
  missed. Severity: low. Likelihood: low. Mitigation: the sweep descends into
  all subtrees (mirroring `collect_doc_comment_nodes`, which recurses through
  recovered subtrees at
  `crates/stilyagi-tree-sitter/src/rust/helpers.rs:199-211`). A malformed-input
  test covers this; if recovery cannot reach the comment, that is an accepted,
  documented limitation consistent with 3.1.2.4.
- Risk: hoisting the parser out of `stilyagi-markdown` silently changes Markdown
  behaviour. Severity: medium. Likelihood: low. Mitigation: WI-Hoist is a pure
  move with a re-export; the Markdown suppression unit tests and the
  `heading-table-link-suppression.md` snapshot run unchanged as the regression
  oracle before any new syntax is wired.

## Progress

- [x] WI-Hoist: move the syntax-agnostic directive parser into `stilyagi-ir`.
- [x] WI-Assembly: hoist candidate-to-`IrSuppression` assembly and origin/span
  validation into `stilyagi-ir`; re-point Markdown onto it.
- [x] WI-Python: extract `# stilyagi:` directives in the Python extractor.
- [x] WI-Rust: extract `// stilyagi:` directives in the Rust extractor.
- [x] WI-Parity: cross-syntax parity fixtures, golden IR snapshots, and doc
  confirmation.

## Surprises & discoveries

- Observation: the `IrDocument` envelope already carries and serializes
  `suppressions` unconditionally. Evidence:
  `crates/stilyagi-ir/src/document.rs:29-30,53` —
  `pub suppressions: Vec<IrSuppression>` with no `skip_serializing_if`. Impact:
  no IR envelope or schema change is needed; Python/Rust only need to populate
  the field, so `dump-ir` visibility is automatic.
- Observation: the shared suppression assembly and validation helpers now live
  in `stilyagi-ir`, and Markdown delegates both candidate assembly and
  origin/span checks to that crate. Impact: the syntax-specific frontend now
  only extracts comment bodies and nodes, while the IR crate owns the shared
  suppression contract used by later Python and Rust work items.
- Observation: the Python extractor now emits source-backed comment nodes only
  for directive-bearing `# stilyagi:` comments, preserving node ids for
  ordinary comments while surfacing suppression IR from the same source span.
  Impact: Python suppression extraction now has a concrete regression harness
  for comment-node vocabulary, directive mapping, blanket rejection, and
  ordinary-comment no-churn behaviour.
- Observation: the shared parity fixtures now use syntax-native `stilyagi:`
  markers in the Python and Rust corpora, which also refreshed the checked-in
  golden IR snapshots and the round-trip snapshot in `stilyagi-test-support`.
  Impact: the cross-syntax contract is now visible in both the Rust and Python
  snapshot suites, not only in the extractor internals.
- Observation: Whitaker enforced the 400-line module cap on
  `crates/stilyagi-tree-sitter/src/rust/builder.rs` while this work item was
  landing. Impact: the Rust doc-comment text helper moved into `helpers.rs` so
  the builder module stayed under the limit without changing extractor
  behaviour.

## Decision log

- Decision: home the shared directive grammar in `stilyagi-ir`, not
  `stilyagi-core` or a new crate. Rationale: both `stilyagi-markdown` and
  `stilyagi-tree-sitter` already depend on `stilyagi-ir`
  (`crates/stilyagi-markdown/Cargo.toml:13`,
  `crates/stilyagi-tree-sitter/Cargo.toml:13`), and `stilyagi-ir` already owns
  `SuppressionKind` and `IrSuppression`. Placing the parser there gives a
  single shared implementation with no new dependency edges and satisfies
  "extracted once". Date/Author: 2026-07-05, planner.
- Decision: recognize Rust directives only in non-doc line comments (`//`), and
  do not treat block comments (`/* ... */`) as suppression directives.
  Rationale: design §4 line 624 states "Rust and JavaScript use `//`"; it does
  not mention block comments. Restricting to `//` keeps the contract exactly as
  specified and avoids inventing scope. A block comment that happens to contain
  `stilyagi:` is treated as `NotADirective`. Date/Author: 2026-07-05, planner.
- Decision: give each directive-bearing comment a real, source-backed IR comment
  node and use its id as the `IrSuppression.origin`, mirroring Markdown.
  Rationale: the existing origin/span validation
  (`crates/stilyagi-markdown/src/validation.rs:251-288`) requires `origin` to
  resolve to an emitted node whose span is a real byte range. Emitting a
  comment node keeps Python/Rust suppressions inside the same validated
  contract instead of introducing an unvalidated origin convention.
  Date/Author: 2026-07-05, planner.
- Decision: for Python and Rust, gate comment-node **and** candidate emission on
  the canonical `stilyagi:` marker; ordinary comments emit nothing. Rationale:
  this is the blocking correction from design-review round 1. Markdown emits an
  IR node for **every** `Node::Html` (`builder.rs:83-88`) because HTML comments
  are already part of Markdown's IR tree, so passing all of them as candidates
  does not change IR shape. Python and Rust do **not** emit ordinary-comment IR
  nodes today (they emit only docstring/doc-comment nodes), so emitting a node
  per comment would add nodes, alter node counts, and churn the
  `stilyagi-extract` golden snapshots for every directive-free source file —
  falsifiable at `crates/stilyagi-tree-sitter/src/rust/tests.rs:149`, an
  existing fixture whose plain `// stilyagi-disable-next-line …` line comment is
  `NotADirective` (no `stilyagi:` prefix). To avoid this, the sweep
  pre-detects the marker with the shared `stilyagi_ir::is_directive_marker`
  predicate (the single definition of the grammar's own accept rule, pinned by
  test to `parse_directive_body`) **before** allocating any node id: only a
  comment whose delimiter-stripped, trimmed inner text begins with `stilyagi:`
  gets a comment node + `SuppressionCandidate`. A non-directive such as
  `// see stilyagi: docs` (inner text `see stilyagi: docs`, no leading
  `stilyagi:`) emits nothing. This keeps the shared
  `suppressions_from_candidates` interface unchanged (Markdown still passes
  every HTML candidate, some `NotADirective`; Python/Rust pass only markers),
  keeps exactly one grammar, and guarantees directive-free Python/Rust files
  are byte-for-byte unchanged. Date/Author: 2026-07-05 (round 2), planner.
- Decision: parent every emitted suppression comment node on the builder's root
  node id and link it into `root.children`. Rationale: advisory 1 from round 1.
  The Rust builder exposes `super::root_node_id()` and `push_child`
  (`rust/builder.rs:49-51,378-386`); `push_module_root` asserts the root is
  `n0`. Use `root_node_id()` (not a hard-coded `"n0"`) as the parent and call
  `push_child(root, comment)` so the node appears in both the flat `nodes` list
  and the child tree, which the mixed-source `dump-ir` consumer (roadmap 3.2.3)
  reads consistently. Date/Author: 2026-07-05 (round 2), planner.
- Decision: in the Python extractor, treat parsed comment bodies as directive
  candidates before allocating a node id. Ordinary `#` comments stay invisible
  to the IR; directive-bearing comments gain a source-backed comment node and a
  suppression candidate from the same span. Rationale: this keeps the Python
  node sequence stable for ordinary comments, preserves source-faithful spans
  for emitted suppressions, and gives the extraction tests a direct no-churn
  oracle. Date/Author: 2026-07-06, agent.
- Decision: expose the canonical suppression marker predicate from
  `stilyagi-ir` and rename the shared grammar entry point to
  `parse_directive_body`. Rationale: the marker predicate now gates Python and
  Rust comment-node emission before node-id allocation, and the renamed parser
  reflects that it operates on delimiter-stripped inner text for every v1
  syntax rather than on comment delimiters themselves. Date/Author: 2026-07-06,
  agent.
- Decision: wire the shared `validate_suppressions` guard into Rust debug-build
  consistency checks alongside Python's existing guard. Rationale: both
  tree-sitter extractors now catch source/origin regressions in debug builds,
  keeping the cross-language invariant coverage symmetrical. Date/Author:
  2026-07-06, agent.
- Decision: expand the shared Python and Rust parity fixtures to cover
  `ignore-next`, `disable`/`enable`, `ignore-file`, and one rejected blanket
  directive, and add an explicit cross-syntax suppression-shape parity test.
  Rationale: the milestone now proves the same logical directive shape across
  Markdown, Python, and Rust instead of relying on snapshot coincidence.
  Date/Author: 2026-07-06, agent.

## Outcomes & retrospective

WI-Parity is complete. The shared Python and Rust corpus fixtures now carry
syntax-native `stilyagi:` directives, and the golden IR snapshots in both the
Rust and Python snapshot suites now show the resulting `suppressions` entries
with source-backed origins and spans.

The doc contract already matched the implementation intent in
`docs/stilyagi-design.md` and `docs/developers-guide.md`, so no additional
design prose was needed beyond keeping this execplan current. The work item
validated the final cross-syntax surface without changing the IR schema or the
Markdown suppression snapshot.

## Context and orientation

Stilyagi extracts prose from source files into a shared IR. The relevant crates:

- `crates/stilyagi-ir` — the IR data model. Owns `SuppressionKind` and
  `IrSuppression` (`src/diagnostics.rs`), the `IrDocument` envelope
  (`src/document.rs`), spans, nodes, regions, and errors. Depends only on
  `serde`/`sha2`. This is the shared home for the directive grammar.
- `crates/stilyagi-markdown` — Markdown extraction. Contains the directive
  parser today at `src/suppression.rs` (`DirectiveVerb`, `ParsedDirective`,
  `DirectiveOutcome`, `DirectiveError`, `parse_comment_directive`, `verb_kind`)
  and the candidate-to-suppression assembly at `src/lib.rs:208-277`
  (`suppressions_from_candidates`). Candidate comment spans are gathered by the
  AST builder at `src/builder.rs:16-83` (`SuppressionCandidate`). Origin/span
  validation lives at `src/validation.rs:117-288`.
- `crates/stilyagi-tree-sitter` — Python and Rust extraction.
  - Python: `src/python/mod.rs` (`python_docstring_ir_document`,
    `PythonIrBuilder`), `src/python/helpers.rs`, `src/python/support.rs`
    (`validate_ir_consistency`, `python_producer`, `parse_python`).
  - Rust: `src/rust/mod.rs` (`rust_doc_comment_ir_document`),
    `src/rust/builder.rs` (`RustIrBuilder`), `src/rust/helpers.rs`
    (`classify_doc_comment`, `collect_doc_comment_nodes`, node-kind vocabulary),
    `src/rust/support.rs`.
- `crates/stilyagi-extract` — orchestration (`extract_document*`) that wraps
  each frontend and carries the full `IrDocument` (`ir()`), plus the golden IR
  snapshot tests under `tests/extract/`.
- `crates/stilyagi-test-fixtures` — shared corpus fixture paths/readers.

Terms of art:

- Directive: a `stilyagi:` instruction embedded in a host-language comment.
- Verb: the first token of a directive (`ignore-next`, `disable`, `enable`,
  `ignore-file`).
- Blanket inline suppression: an `ignore-next`/`disable`/`enable` directive that
  names no rule code; forbidden in v1.
- Origin: the IR node id of the comment node that produced a suppression.
- Candidate: a comment whose byte span is a directive-parsing candidate before
  the grammar has accepted or rejected it.

Current grammar entry point (now shared with behaviour preserved),
`crates/stilyagi-ir/src/suppression.rs:93-116`:

```rust
pub fn parse_directive_body(inner: &str) -> DirectiveOutcome {
    let trimmed = inner.trim();
    let Some(directive_body) = trimmed.strip_prefix("stilyagi:") else {
        return DirectiveOutcome::NotADirective;
    };
    // verb parse -> code parse -> blanket check
}
```

The input `inner` is already the text *between* the comment delimiters.
Markdown strips `<!--`/`-->` before calling it (`src/lib.rs:224-231`). This is
why the grammar is already syntax-agnostic: each frontend strips its own
delimiters and hands over the inner text.

## Plan of work

The five work items are ordered so each is independently committable and passes
all gates. WI-Hoist and WI-Assembly are pure refactors that keep Markdown
behaviour observable; WI-Python and WI-Rust add the new syntaxes; WI-Parity
proves cross-syntax consistency end to end.

### WI-Hoist — one shared directive grammar in `stilyagi-ir`

Implements: design §4 "Suppression parsing belongs in extraction" (single
grammar); developers-guide "Suppression state is extracted once" (lines
454-456). Enables the success criterion "extracted once".

- Read first: `docs/stilyagi-design.md` §4 lines 603-626;
  `docs/developers-guide.md` lines 454-459;
  `crates/stilyagi-markdown/src/suppression.rs` (whole file);
  `crates/stilyagi-markdown/src/lib.rs:208-261`.
- Skills to load: `rust-router` (route to `rust-types-and-apis` for the public
  API shape and `arch-crate-design` for the crate-boundary move); `leta` for
  reference/import navigation; `sem` for the entity-level move diff.
- Move `DirectiveVerb`, `ParsedDirective`, `DirectiveOutcome`, `DirectiveError`,
  the parse function, and `verb_kind` into a new public module
  `crates/stilyagi-ir/src/suppression.rs`, re-exported from
  `crates/stilyagi-ir/src/lib.rs` as
  `pub use suppression::{DirectiveError,
  DirectiveOutcome, DirectiveVerb, ParsedDirective, is_directive_marker,
  parse_directive_body, verb_kind};`.
  Rename the entry point from `parse_comment_directive` to
  `parse_directive_body` because it now parses already-stripped inner text for
  any syntax, not just a comment. Make the types `pub` (they cross crate
  boundaries) and keep `verb_kind` returning `SuppressionKind`.
- Add, in the same module, the single canonical accept-rule predicate
  `is_directive_marker`, whose body is `inner.trim().starts_with("stilyagi:")`.
  This is exactly the prefix test `parse_directive_body` already performs
  (`suppression.rs:51-53`: `inner.trim()` then `strip_prefix("stilyagi:")`), so
  there remains exactly one definition of the marker. The Python and Rust
  sweeps (WI-Python/WI-Rust) call this to gate node emission before allocating
  a node id. It must NOT be reimplemented in any extractor.
- Update `stilyagi-markdown` to import the parser from `stilyagi_ir` and delete
  `crates/stilyagi-markdown/src/suppression.rs` and its `mod suppression;`
  declaration. Adjust the call site in `src/lib.rs` to the renamed function.
- Tests (Red-Green-Refactor): the parser's behavioural unit tests move with it.
  - Red: move the existing directive unit tests (or add equivalents if they live
    only under `stilyagi-markdown`) into `crates/stilyagi-ir/src/tests/` as the
    new home, plus one added case proving `parse_directive_body` is called on
    already-stripped text (no `<!--` awareness inside the parser). Add a pinning
    test that ties the marker predicate to the parser: for a corpus of inner
    strings (markers, non-markers with embedded `stilyagi:`, whitespace-padded
    markers, unknown-verb and blanket markers), assert
    `is_directive_marker(s) == !matches!(parse_directive_body(s),
    DirectiveOutcome::NotADirective)` — i.e. the predicate accepts exactly the
    inputs the grammar does not classify as `NotADirective`. Run
    `cargo nextest run -p stilyagi-ir` (via `make test`) and expect the new
    module to fail until the code is moved.
  - Green: perform the move; the tests pass.
  - Refactor: re-run `make test`; the `stilyagi-markdown` suppression unit tests
    (`crates/stilyagi-markdown/src/tests/suppression.rs`) and the
    `heading-table-link-suppression.md` snapshot must pass unchanged — this is
    the no-behavioural-change oracle.
- Acceptance: `make test` green; Markdown suppression snapshot unchanged; no
  `parse_comment_directive`/`mod suppression` remains in `stilyagi-markdown`
  (`leta grep parse_comment_directive` returns nothing); `is_directive_marker`
  is exported from `stilyagi-ir` and its pinning test passes.

### WI-Assembly — shared candidate assembly and validation in `stilyagi-ir`

Implements: design §4 "Suppression state must be visible in IR" and "applied
consistently"; requires WI-Hoist. Ensures all three syntaxes produce identical
`IrSuppression` ids, error codes, and origin/span validation.

- Read first: `crates/stilyagi-markdown/src/lib.rs:208-277`;
  `crates/stilyagi-markdown/src/validation.rs:117-123,251-288`;
  `crates/stilyagi-ir/src/diagnostics.rs`.
- Skills to load: `rust-router` → `rust-types-and-apis`, `arch-crate-design`;
  `rust-errors` for the `IrError` construction; `leta`.
- Add to `stilyagi-ir` a syntax-neutral assembly helper, e.g.
  `pub fn suppressions_from_candidates(candidates: &[SuppressionCandidate]) ->
  (Vec<IrSuppression>, Vec<IrError>)`,
  where `SuppressionCandidate` is a small public struct
  `{ span: SourceSpan, origin: String, inner: String }` (`inner` is the
  already-delimiter-stripped comment body). The helper: assigns `s{n}` ids in
  order; calls `parse_directive_body`; on `Parsed` emits an
  `IrSuppression { id, kind: verb_kind(verb), codes, span, origin }`; on
  `Rejected(BlanketForbidden)` / `Rejected(UnknownVerb)` emits the existing
  error codes `suppression-blanket-forbidden` / `suppression-unknown-verb`; on
  `NotADirective` emits nothing. Add a shared origin/span validation helper
  `pub fn validate_suppression(suppression, source, node_ids) -> Result<(),
  IrError>`
  producing the existing codes `ir-suppression-origin-unresolved` and
  `ir-suppression-source-mismatch`.
- Re-point Markdown: `suppressions_from_candidates` in
  `crates/stilyagi-markdown/src/lib.rs` becomes a thin adapter that strips
  `<!--`/`-->`, builds `SuppressionCandidate`s, and delegates; the Markdown
  validation functions delegate to the shared validator (keeping the
  `Message`-typed wrapper Markdown needs). Preserve the existing
  `suppression-span-invalid` "span outside source" pre-check where it currently
  runs — it stays in the Markdown adapter and is intentionally not part of the
  shared `suppressions_from_candidates` signature, because Python/Rust spans
  come straight from real tree nodes and cannot fall outside source (advisory
  3). The parity test must therefore not assert `suppression-span-invalid`
  cross-syntax.
- Tests (Red-Green-Refactor):
  - Red: add `stilyagi-ir` unit tests asserting id sequencing, each error code,
    the `ignore-file` empty-codes acceptance, and both validation error codes.
    Run `make test`; expect failure until the helper exists.
  - Green: implement the helper; tests pass.
  - Refactor: re-run `make test`; Markdown suppression snapshot and unit tests
    unchanged. Property test (proptest, in `stilyagi-ir`): for any vector of
    candidates, ids are exactly `s0..sN` over accepted directives and are
    strictly increasing (grammar determinism).
- Acceptance: `make test` green; Markdown behaviour byte-identical; a single
  assembly + validation implementation is now reachable from `stilyagi-ir`.

### WI-Python — `# stilyagi:` directives in the Python extractor

Implements: design §4 "Python uses `#`"; roadmap 3.1.3; requires WI-Assembly.

- Read first: `crates/stilyagi-tree-sitter/src/python/mod.rs` (builder walk,
  `next_node_id`, `push_node`, `push_child`);
  `crates/stilyagi-tree-sitter/src/python/helpers.rs` (`source_span`,
  `text_for_node`, `collect_error_nodes`);
  `crates/stilyagi-tree-sitter/src/python/support.rs`
  (`validate_ir_consistency`); the `IrSuppression` contract in `stilyagi-ir`.
- Skills to load: `rust-router` → `rust-unit-testing` and `rust-types-and-apis`;
  `leta` for tree-sitter node navigation; verification: consider `proptest`
  (`rust-verification`) for span-faithfulness.
- Verify the comment vocabulary before relying on it: add a red assertion test
  that parses `# stilyagi: disable PYDOC210\n` and confirms tree-sitter-python
  emits a node of kind `comment` covering the `#…` span. (This pins the
  load-bearing grammar fact; do not proceed on assumption.)
- Add a comment sweep in `PythonIrBuilder`: after `visit_module`, walk the whole
  tree (including error subtrees, mirroring `collect_error_nodes`) collecting
  `comment` nodes. For each comment, take the comment text and strip the single
  leading `#` to obtain `inner`. **Gate emission on the marker**: call
  `stilyagi_ir::is_directive_marker(&inner)` first; if it returns `false`
  (ordinary comment, shebang `#!`, etc.) emit **nothing** — no node id is
  allocated and no candidate is built. Only when it returns `true`: emit one
  source-backed IR comment node (kind `"comment"`, parent = the module root
  node id via the builder's root-id accessor, real span, `NodeFlags` from
  `node_flags`) allocated from the same `next_node` counter, link it into the
  root's `children` (mirroring the child-linkage the builder uses for other
  nodes), and build `SuppressionCandidate { span, origin, inner }` with
  `origin` set to that node id. Collect the marker candidates, call the shared
  `stilyagi_ir::suppressions_from_candidates`, then push results into
  `document.suppressions` and extend `document.errors`. (Because the sweep
  passes only markers, `suppressions_from_candidates` sees no `NotADirective`
  here; a marker with a bad verb still yields `suppression-unknown-verb` and a
  blanket marker still yields `suppression-blanket-forbidden`, exactly as
  Markdown.) Extend the Python `validate_ir_consistency` to run the shared
  `validate_suppression` over each emitted suppression. Note: Python
  `validate_ir_consistency` is a `debug_assert`-guarded build-time invariant
  check (`python/support.rs:54`), so `validate_suppression` here is a
  construction-time guard, not a runtime `IrError` producer — the builder
  controls origin and span by construction (advisory 2). Python spans come
  straight from real nodes, so the Markdown-only `suppression-span-invalid`
  "span outside source" pre-check does not apply and is not emitted here
  (advisory 3).
- Tests (Red-Green-Refactor), in
  `crates/stilyagi-tree-sitter/src/python/tests.rs` and/or a new
  `python/suppression_tests.rs`:
  - Red: unit test — a module with `# stilyagi: disable PYDOC210` yields one
    `IrSuppression { kind: Range, codes: ["PYDOC210"], origin resolvable, span ==
    comment span }`. Run `make test`; expect failure.
  - Behavioural: `ignore-next`/`ignore-file`/`enable` each map to the correct
    `SuppressionKind`; a non-directive comment (`# ordinary note`, a `#!`
    shebang, and `# see stilyagi: docs` where `stilyagi:` is not the leading
    token) yields no suppression; a blanket `# stilyagi: disable` yields a
    `suppression-blanket-forbidden` error and no suppression.
    No-churn assertion: extract a module containing only ordinary (non-marker)
    comments and assert the emitted `nodes` count and ids are identical to the
    same module with the comments removed — proving non-marker comments allocate
    no IR node (guards the round-1 blocker directly).
    Property/robustness: a directive comment nested inside a function body and one
    inside a malformed (`ERROR`) region are still collected or, if unreachable,
    covered by an explicit documented assertion.
  - Green then Refactor: implement the sweep; re-run `make test`.
- Acceptance: `make test` green; a Python source with directives produces the
  expected `suppressions`; files without directives keep unchanged node ids
  (existing Python snapshots unaffected).

### WI-Rust — `// stilyagi:` directives in the Rust extractor

Implements: design §4 "Rust and JavaScript use `//`"; roadmap 3.1.3; requires
WI-Assembly.

- Read first: `crates/stilyagi-tree-sitter/src/rust/helpers.rs:9-45,143,199-211`
  (`DocCommentFlavor`, `classify_doc_comment`, comment-kind vocabulary,
  `collect_doc_comment_nodes`);
  `crates/stilyagi-tree-sitter/src/rust/builder.rs` (node emission, id counter);
  `crates/stilyagi-tree-sitter/src/rust/support.rs`
  (`validate_ir_consistency`).
- Skills to load: `rust-router` → `rust-unit-testing`, `rust-types-and-apis`;
  `leta`.
- Add a comment sweep in `RustIrBuilder`: after `visit_container`, walk the tree
  (including recovered subtrees, like `collect_doc_comment_nodes`) collecting
  `line_comment` nodes for which `classify_doc_comment` returns `None` (i.e.
  plain `//`, not `///`/`//!`). Skip `block_comment` (Decision Log). Strip the
  leading `//` to obtain `inner`. **Gate emission on the marker**: call
  `stilyagi_ir::is_directive_marker(&inner)` first; if `false` emit nothing (no
  node id allocated, no candidate). This is the exact fix for the round-1
  blocker: the existing fixture at
  `crates/stilyagi-tree-sitter/src/rust/tests.rs:149`
  (`// stilyagi-disable-next-line …`) has inner text
  `stilyagi-disable-next-line …`, which does **not** start with `stilyagi:`, so
  `is_directive_marker` returns `false` and no node is emitted — the fixture's
  snapshot is unchanged. Only when the predicate returns `true`: emit a
  source-backed IR comment node (kind `"comment"`, parent =
  `super::root_node_id()`, real span) from the shared id counter, link it into
  the root's `children` via `push_child` (`rust/builder.rs:378-386`), and set
  `origin` to that node id. Delegate the marker candidates to
  `stilyagi_ir::suppressions_from_candidates`, populate `document.suppressions`/
  `errors`, and extend the Rust `validate_ir_consistency` with the shared
  `validate_suppression` (build-time invariant guard, per advisory 2; Rust
  spans come from real nodes, so `suppression-span-invalid` is not emitted here
  — advisory 3).
- Tests (Red-Green-Refactor), in
  `crates/stilyagi-tree-sitter/src/rust/tests.rs` and/or a new
  `rust/suppression_tests.rs`:
  - Red: unit test — `// stilyagi: ignore-next RUSTDOC110\n/// doc\nfn f(){}`
    yields one `IrSuppression { kind: Inline, codes: ["RUSTDOC110"], origin
    resolvable, span == comment span }`. Run `make test`; expect failure.
  - Behavioural: `disable`/`enable`/`ignore-file` map correctly; a `///` doc
    comment containing `stilyagi:` text yields NO suppression (doc comments are
    prose, not directives); a `//!` inner doc likewise; a plain `// note` and a
    non-marker `// stilyagi-disable-next-line …` (hyphen, no colon) each yield
    none and emit no comment node; a blanket `// stilyagi: disable` yields
    `suppression-blanket-forbidden`.
    Regression guard for the round-1 blocker: add a test that extracts a Rust
    source of only non-marker `//` comments and asserts the `nodes` list is
    identical (count and ids) to the same source with those comments removed.
    Source-byte oracle: assert the suppression span reproduces the exact `//…`
    bytes (reuse the oracle pattern from `rust/source_oracle_tests.rs`).
  - Green then Refactor: implement; re-run `make test`.
- Acceptance: `make test` green; Rust source with `//` directives produces the
  expected `suppressions`; doc comments never do; existing Rust snapshots for
  directive-free fixtures are unchanged.

### WI-Parity — cross-syntax parity fixtures, snapshots, and doc confirmation

Implements: success criterion "applied consistently across all v1 source
syntaxes"; design §7.1 IR/`dump-ir` visibility; feeds roadmap 3.2.3
(mixed-source `dump-ir`).

- Read first: `crates/stilyagi-extract/tests/extract/` golden IR snapshot tests
  and the shared fixtures under `crates/stilyagi-test-fixtures/`; the Markdown
  `heading-table-link-suppression.md` fixture as the reference shape;
  `docs/developers-guide.md` lines 454-459; `docs/stilyagi-design.md` §4.
- Skills to load: `rust-router` → `rust-unit-testing`; `leta`; for the
  documentation confirmation, `scribe` may format prose; `en-gb-oxendict` for
  spelling.
- Add a Python fixture and a Rust fixture that each contain a representative mix
  of directives (`ignore-next`, `disable`/`enable` pair, `ignore-file`) and one
  intentionally rejected blanket directive, alongside ordinary docstrings/doc
  comments. Add golden IR snapshot coverage through `stilyagi-extract` so the
  new `suppressions` and errors render in `dump-ir`-shaped output, mirroring
  the Markdown fixture. A cross-syntax parity unit test asserts that the same
  logical directive (`disable <CODE>`) produces `IrSuppression`s with identical
  `kind` (`Range`), an identical `codes` vector, and the identical `s{n}` id
  scheme across Markdown, Python, and Rust — proving "extracted once, applied
  consistently". The grammar is code-agnostic, so any code string works; use a
  language-neutral placeholder code (e.g. `X001`) rather than a Markdown-only
  pun code so the shape-parity assertion does not read oddly (advisory 4).
  Where a fixture is exercising a real rule the per-language code is fine
  (`PYDOC210`/`RUSTDOC110`); the parity assertion tests shape, not code
  semantics.
- Documentation: confirm design §4 and developers-guide §"Suppression semantics"
  already describe this behaviour; if any wording still implies Markdown-only
  suppression, correct it (en-GB). No new ADR is required — this implements the
  existing design contract rather than deciding a new one; record that in the
  Decision Log if a doc edit is made. If Markdown docs are edited, run
  `make markdownlint` and `make nixie`.
- Tests (Red-Green-Refactor): add snapshot tests (new `.snap` files are created
  on first accepted run via `cargo insta review`, then committed); the parity
  unit test is green on first correct implementation since this WI runs last.
  Treat any snapshot churn in unrelated fixtures as a regression to
  investigate, not to bless.
- Acceptance: `make test` green; new snapshots show Python and Rust suppressions
  in the same IR shape as Markdown; parity test passes; markdown gates green if
  docs changed.

## Concrete steps

Run everything from the worktree root
`/home/leynos/Projects/stilyagi.worktrees/roadmap-3-1-3`.

1. Confirm the branch and clean tree:

   ```bash
   git -C /home/leynos/Projects/stilyagi.worktrees/roadmap-3-1-3 status
   ```

   Expect branch `roadmap-3-1-3`.

2. For each work item, follow Red-Green-Refactor, then run the commit gates in
   order (see Validation). Format only the files you changed. Commit after each
   green work item with an en-GB imperative subject, e.g.
   `Hoist suppression grammar into stilyagi-ir`.

3. Re-bless snapshots only via `cargo insta review` (never blind-accept) and
   only for the fixtures this task adds or intentionally changes.

## Validation and acceptance

Commit gates, in this exact order, from the worktree root (AGENTS.md "Quality
gates" lines 63-94, 156-184):

```bash
make check-fmt
make typecheck
make lint
make test
```

For any Markdown documentation change (WI-Parity only, and only if docs are
edited), additionally:

```bash
make markdownlint
make nixie
```

Prefer these repository gates over handwritten file lists. If formatting
changed Rust files, `make check-fmt` (rustfmt) is the authority; do not run a
repo-global Markdown reformat that churns unrelated files. Delegate full gate
runs to the `scrutineer` subagent, which captures each gate's output to a
`/tmp` log and returns a bounded report.

Red-Green-Refactor evidence to record per code work item:

- Red: the focused `cargo nextest run -p <crate> <filter>` (via `make test`)
  fails for the intended reason before the production change.
- Green: the same focused test passes after the minimal change.
- Refactor: `make test` passes and no unrelated snapshot changed.

Quality criteria ("done"):

- Tests: all `make test` suites pass; new Python and Rust suppression unit,
  behavioural, and snapshot tests pass; the cross-syntax parity test passes;
  the Markdown suppression snapshot is unchanged.
- Lint/typecheck: `make check-fmt`, `make typecheck`, `make lint` all clean.
- Behaviour: extracting a Python or Rust file with a syntax-native directive
  yields a populated, validated `suppressions` list; a blanket inline directive
  yields `suppression-blanket-forbidden`; directives are visible in the IR /
  `dump-ir` output.

## Idempotence and recovery

Each work item is a self-contained commit. The refactor work items (WI-Hoist,
WI-Assembly) are behaviour-preserving; if a gate fails, revert the single
commit and retry. Snapshot creation is idempotent: re-running tests after
`cargo insta review` is stable. No destructive or irreversible steps. If a
snapshot is blessed in error, delete the `.snap` file and re-run to regenerate.

## Artifacts and notes

Reference shape (Markdown, today) that Python and Rust must match, one
`IrSuppression` per accepted directive:

```json
{
  "id": "s0",
  "kind": "range",
  "codes": ["PYDOC210"],
  "span": { "byte_start": 0, "byte_end": 26 },
  "origin": "n3"
}
```

## Interfaces and dependencies

Use the existing tree-sitter grammars and workspace crates only; no new
external dependency.

At the end of WI-Hoist, in `crates/stilyagi-ir/src/suppression.rs`:

```rust
pub enum DirectiveVerb { IgnoreNext, Disable, Enable, IgnoreFile }
pub struct ParsedDirective { pub verb: DirectiveVerb, pub codes: Vec<String> }
pub enum DirectiveOutcome { NotADirective, Parsed(ParsedDirective), Rejected(DirectiveError) }
pub enum DirectiveError { BlanketForbidden, UnknownVerb }
pub fn parse_directive_body(inner: &str) -> DirectiveOutcome;
pub const fn verb_kind(verb: DirectiveVerb) -> crate::SuppressionKind;
/// The single canonical accept-rule marker predicate; the Python and Rust
/// sweeps call this to gate node emission before allocating a node id.
pub fn is_directive_marker(inner: &str) -> bool; // inner.trim().starts_with("stilyagi:")
```

At the end of WI-Assembly, in `stilyagi-ir` (module path to be finalized, e.g.
`crate::suppression`):

```rust
pub struct SuppressionCandidate { pub span: crate::SourceSpan, pub origin: String, pub inner: String }
pub fn suppressions_from_candidates(candidates: &[SuppressionCandidate])
    -> (Vec<crate::IrSuppression>, Vec<crate::IrError>);
pub fn validate_suppression(
    suppression: &crate::IrSuppression,
    source: &str,
    node_ids: &std::collections::BTreeSet<&str>,
) -> Result<(), crate::IrError>;
```

Python (`crates/stilyagi-tree-sitter/src/python/mod.rs`) and Rust
(`crates/stilyagi-tree-sitter/src/rust/builder.rs`) builders each gain a
comment sweep that, **for markers only** (gated by `is_directive_marker` before
any node-id allocation), emits a source-backed `"comment"` IR node parented on
the module root (`root_node_id()`) and linked into `root.children`, builds a
`SuppressionCandidate` (Python strips one `#`; Rust strips `//` from non-doc
`line_comment`s), delegates to `suppressions_from_candidates`, and populates
`IrDocument::suppressions`/`errors`, with `validate_suppression` wired into
each crate's build-time `validate_ir_consistency`. Non-marker comments emit
nothing, so directive-free files keep their existing node ids and snapshots.

## Revision note

Initial draft (2026-07-05): first planning round. Decomposes roadmap 3.1.3 into
five ordered, independently gate-passable work items — two behaviour-preserving
refactors that consolidate the directive grammar and assembly/validation into
`stilyagi-ir`, then Python and Rust syntax-native extraction, then a
cross-syntax parity milestone. No behavioural forks left open: the grammar
home, the Rust `//`-only scope, and the source-backed origin-node decision are
all fixed in the Decision Log against verified source and design citations.

Round 2 (2026-07-05): resolve the design-review blocker and advisories.

- BLOCKER (unconditional comment-node emission). Node emission is now
  **directive-gated**: WI-Hoist adds a single canonical `is_directive_marker`
  predicate to `stilyagi-ir` (the parser's own `stilyagi:` accept rule, pinned
  by test to `parse_directive_body` so there is one grammar). WI-Python and
  WI-Rust now call `is_directive_marker` **before** allocating any node id and
  emit a comment node + candidate only for markers; ordinary `#`/`//` comments
  emit nothing. This is reconciled with the shared interface by pre-detecting
  the marker in the sweep, leaving `suppressions_from_candidates` unchanged
  (Markdown still passes all HTML candidates). Verified against
  `crates/stilyagi-tree-sitter/src/rust/tests.rs:149`
  (`// stilyagi-disable-next-line`, a non-marker) which now provably produces
  no node and no snapshot churn; new no-churn regression tests in both
  extractors assert node-count/id identity for non-marker comments.
  Constraints, the node-id Risk, WI-Python/WI-Rust acceptance, and the Decision
  Log are all reconciled with this gate.
- Advisory 1 (parent linkage / `n0`). Comment nodes are now parented on
  `root_node_id()` (not a hard-coded `"n0"`) and linked into `root.children` via
  `push_child`, so they render consistently for the roadmap 3.2.3 `dump-ir`
  consumer.
- Advisory 2 (validation asymmetry). The plan now states Python/Rust
  `validate_suppression` is a build-time (`debug_assert`) invariant guard, not
  a runtime `IrError` producer.
- Advisory 3 (`suppression-span-invalid` scope). The plan now states this check
  stays in the Markdown adapter and is not asserted cross-syntax.
- Advisory 4 (parity code). The parity assertion now uses a language-neutral
  placeholder code and tests shape, not code semantics.
