# Add coverage for inline suppression directives in paragraphs

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
`Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`, `Decision Log`,
and `Outcomes & Retrospective` must be kept up to date as work proceeds.

Status: COMPLETE

## Purpose / big picture

Stilyagi parses Markdown suppression directives (canonical
`<!-- stilyagi: <verb> <codes> -->` HTML comments) into the intermediate
representation (IR) so that later rule and fix stages trust one source of truth
for suppression state. Today's tests only exercise directives that sit on their
own line, where the Markdown parser emits a *flow* (block-level) HTML node. A
directive can also appear *inline*, embedded within a paragraph's prose, for
example `Apples <!-- stilyagi: ignore-next PUN201 --> and pears.`. The Markdown
parser (`markdown-rs`) represents that comment as an inline `Node::Html` child
of the paragraph, and the existing builder already collects every `Node::Html`
node — flow or inline — as a suppression candidate. The verb-driven
classification therefore already flows through inline directives, but nothing
pins that behaviour, so a future refactor could silently drop within-paragraph
directives without any test failing.

This is roadmap task 2.1.3.2 ("Add coverage for inline suppression directives
in paragraphs"; addendum from review:2.1.3, severity low, "lightweight addendum
pass"). See `docs/roadmap.md` lines 152-155.

After this change, a reader can observe that an inline directive within a
paragraph produces the correct IR suppression (kind, codes, span, origin node)
and that inline blanket directives are still refused — proven by focused unit
tests in the `stilyagi-markdown` crate and by a behaviour-driven (BDD) scenario
that drives the public extraction boundary. This is a test-only ("coverage")
change: no production behaviour changes.

## Constraints

Hard invariants that must hold throughout implementation. Violation requires
escalation, not a workaround.

- This is a coverage addendum. Do **not** change production behaviour or public
  API. If a test written here fails against current behaviour, that is a
  discovery to escalate (see `Tolerances`), not a licence to patch the builder
  or parser to make it pass.
- Do not modify the suppression parsing contract in
  `crates/stilyagi-markdown/src/suppression.rs`, the candidate collection in
  `crates/stilyagi-markdown/src/builder.rs`, or the classification wiring in
  `crates/stilyagi-markdown/src/lib.rs`.
- Preserve the source-span faithfulness rule: suppression spans must re-slice
  from the original source bytes to exactly the directive comment
  (`docs/stilyagi-design.md` §5 "Source spans must remain faithful to original
  bytes", §4 "Suppression syntax").
- Blanket inline suppression stays forbidden in v1
  (`docs/stilyagi-design.md` §4 "Blanket inline suppression remains forbidden
  in v1").
- Suppression parsing belongs in extraction and its state must be visible in the
  IR (`docs/stilyagi-design.md` §4 "Suppression parsing belongs in extraction",
  "Suppression state must be visible in IR and debug output").
- en-GB Oxford spelling ("-ize"/"-yse"/"-our") in all prose, comments, and the
  commit subject (`AGENTS.md`; the `en-gb-oxendict` skill).
- All edits target the worktree at
  `/home/leynos/Projects/stilyagi.worktrees/roadmap-2-1-3-2`. Never edit the
  root/control worktree.

## Tolerances (exception triggers)

- Scope: this task should touch at most three files (one unit-test module, one
  BDD step module, one `.feature` file) plus this ExecPlan. If a production
  source file under `crates/stilyagi-markdown/src/` or
  `crates/stilyagi-extract/src/` must change to make a test pass, **stop and
  escalate** — that means the behaviour the roadmap assumed already works does
  not, which is a different (larger) task.
- Behaviour discovery: if `markdown-rs` does **not** emit an inline `Node::Html`
  for a within-paragraph comment, or emits a span that does not re-slice to the
  comment, stop and record the actual behaviour in `Surprises & Discoveries`,
  then escalate before proceeding.
- Interface: if any public API signature must change, stop and escalate.
- Dependencies: if a new external dependency is required, stop and escalate.
- Iterations: if a gate still fails after 3 fix attempts, stop and escalate.
- Ambiguity: if a requirement admits multiple materially different
  interpretations, stop and present options.

## Risks

- Risk: `markdown-rs` might fold the inline comment into surrounding text rather
  than emitting a distinct inline `Node::Html`, so no candidate would be
  collected. Severity: medium. Likelihood: low. Mitigation: static evidence is
  strong — `crates/stilyagi-markdown/src/node_kind.rs` shows a single
  `Node::Html` variant covering both flow and inline HTML, and CommonMark
  treats an HTML comment as inline raw HTML. The first work item writes a
  parser-level assertion (parse the source, find the inline `Node::Html` under
  the paragraph, check its span) so the assumption is proven before any IR
  assertion depends on it. If the assertion fails, escalate per `Tolerances`.
- Risk: an inline directive's span might differ subtly from a flow directive's
  span (for example including a trailing newline). Severity: low. Likelihood:
  low. Mitigation: the unit test re-slices the suppression span from source and
  asserts it equals exactly `<!-- ... -->`, matching the existing
  flow-directive assertions in
  `crates/stilyagi-markdown/src/tests/suppression.rs`.
- Risk: Red-Green-Refactor cannot show a "red" stage because the production
  behaviour already exists, so the new tests pass immediately. Severity: low.
  Likelihood: high (expected). Mitigation: these are *characterization*
  (coverage) tests pinning existing behaviour. The nearest observable
  substitute for a red stage is to first confirm the tests genuinely exercise
  the inline path (temporarily break the expectation and watch it fail, then
  restore) — documented as a manual check in `Concrete steps`. Recorded in
  `Decision Log`.

## Progress

- [x] WI-1: Unit characterization tests for inline directives in
  `crates/stilyagi-markdown` (parser-level node/span assertion plus IR
  classification, span, origin, and inline-blanket rejection).
- [x] WI-2: BDD scenario and feature covering an inline within-paragraph
  directive at the `stilyagi-extract` boundary.

## Surprises & discoveries

- Verified that `markdown-rs` exposes an inline `Node::Html` for the
  within-paragraph comment, that its span re-slices to the directive bytes, and
  that the IR builder classifies it without any production changes.
- Added the extraction-boundary BDD scenario for the inline paragraph case and
  reused the shared span assertion step, keeping the change test-only and
  aligned with the existing feature vocabulary.

## Decision log

- Decision: Treat this task as a test-only coverage addendum and forbid
  production changes. Rationale: the roadmap classifies it as a low-severity
  "lightweight addendum pass" whose intent is to *pin* verb-driven
  classification for within-paragraph comments, and static evidence shows the
  builder already collects every `Node::Html` (flow and inline) as a
  suppression candidate (`crates/stilyagi-markdown/src/builder.rs` lines
  82-87), routed through `parse_comment_directive` and `verb_kind`
  (`crates/stilyagi-markdown/src/lib.rs` lines 208-261). Date/Author:
  2026-07-05, planning agent.
- Decision: Pin the load-bearing behavioural claim ("an inline within-paragraph
  HTML comment becomes a `Node::Html` node whose span re-slices to the comment,
  classified by verb") with the plan's own tests rather than only citing.
  Rationale: `markdown-rs` is a locked dependency (`markdown = "1.0.0"` in
  `Cargo.toml`) and its inline-vs-flow emission is best pinned by an executable
  assertion. Static evidence: `node_kind.rs` maps a single `Node::Html` variant
  for all HTML; CommonMark defines HTML comments as inline raw HTML.
  Date/Author: 2026-07-05, planning agent.
- Decision: Use inline source-string literals (not golden fixtures) for the new
  tests. Rationale: every existing suppression test in
  `crates/stilyagi-markdown/src/tests/suppression.rs` and the BDD steps in
  `crates/stilyagi-extract/tests/extract/markdown_suppression_bdd.rs` uses
  inline `concat!(...)` source strings; matching that idiom keeps the change
  minimal and consistent (`AGENTS.md`: "Write code that reads like the
  surrounding code"). Date/Author: 2026-07-05, planning agent.
- Decision: Perform one manual red-stage inversion on the new parser-level
  assertion before the green run. Rationale: the coverage addendum already had
  passing behaviour, so the temporary inversion proved the new test actually
  exercises the inline paragraph path rather than passing vacuously.
  Date/Author: 2026-07-06, implementing agent.

## Outcomes & retrospective

- WI-2 landed as a focused BDD addendum. The feature file now exercises an
  inline `stilyagi: ignore-next PUN201` comment embedded in a paragraph, and
  the step module wires that scenario into the existing extraction and span
  assertions without changing production code or public APIs.

## Context and orientation

The relevant crates and files (all paths repository-relative, rooted at the
worktree):

- `crates/stilyagi-markdown/src/suppression.rs` — parses the inner text of a
  Markdown HTML comment into a `DirectiveOutcome` (`NotADirective`, `Parsed`, or
  `Rejected`). `DirectiveVerb` values `IgnoreNext`, `Disable`, `Enable`,
  `IgnoreFile` map to IR suppression kinds via `verb_kind`:
  `IgnoreNext -> Inline`, `Disable`/`Enable` -> `Range`, `IgnoreFile -> File`.
- `crates/stilyagi-markdown/src/builder.rs` — `MarkdownIrBuilder::push_node`
  pushes every node and, for `matches!(node, Node::Html(_))`, records a
  `SuppressionCandidate { node_id, span }` (lines 82-87). This is the key line:
  it does not distinguish flow from inline HTML, so an inline comment under a
  paragraph is collected exactly like a block comment.
- `crates/stilyagi-markdown/src/lib.rs` — `suppressions_from_candidates`
  (lines 208-261) re-slices each candidate's span from source, strips `<!--`/
  `-->`, calls `parse_comment_directive`, and emits either an
  `IrSuppression { kind, codes, span, origin }` or an `IrError`
  (`suppression-blanket-forbidden` / `suppression-unknown-verb`).
- `crates/stilyagi-markdown/src/node_kind.rs` — maps mdast nodes to IR kind
  spellings; `Node::Html(_) => "html"` is the single HTML variant (confirming
  flow and inline HTML share one node type).
- `crates/stilyagi-markdown/src/tests/suppression.rs` — the existing unit tests.
  `markdown_parser_exposes_html_comment_spans` (lines 80-91) parses source and
  walks the tree with the helper `find_html_node` (lines 339-345) to assert the
  HTML node's span. `markdown_ir_document_collects_canonical_suppressions`
  (lines 93-148) asserts kind/codes/origin/span for a multi-directive document.
  Helper `html_node_ids` (lines 330-337) lists IR node ids whose kind is
  `"html"`. `source_identity` comes from the parent `tests` module.
- `crates/stilyagi-extract/tests/extract/markdown_suppression_bdd.rs` — BDD
  steps using `rstest-bdd`. `extract_document(source, ExtractSyntax::Markdown)`
  returns an `ExtractDocument` whose `.ir()` yields the `IrDocument`. Existing
  scenarios live in
  `crates/stilyagi-extract/tests/features/markdown_suppression.feature` and are
  registered as a module in
  `crates/stilyagi-extract/tests/extract_integration.rs` (lines 9-10).

Terms of art:

- IR (intermediate representation): the flattened, span-faithful document model
  Stilyagi builds from source before rules run.
- Flow vs inline HTML: a *flow* HTML comment stands alone as a block; an
  *inline* HTML comment is embedded in phrasing content (prose) inside a
  paragraph. Both are `Node::Html` in mdast.
- Directive verb: the token after `stilyagi:` (`ignore-next`, `disable`,
  `enable`, `ignore-file`) that classifies a suppression.
- Characterization test: a test that pins existing behaviour so future changes
  cannot alter it unnoticed.

Design and standards references:

- `docs/stilyagi-design.md` §4 "Suppression syntax" (lines 603-626): the
  user-facing contract, "Suppression parsing belongs in extraction",
  "Suppression state must be visible in IR", "Blanket inline suppression
  remains forbidden in v1"; §5 business rules "Source spans must remain
  faithful to original bytes"; §7.1 the Markdown IR envelope and suppression
  parsing.
- `docs/rfcs/0001-stilyagi-intermediate-representation.md` — the IR contract
  that suppressions are part of.
- `docs/adr-005-markdown-region-vocabulary-scope.md` — Markdown region
  vocabulary scope (confirms HTML comments are the Markdown directive carrier).
- `AGENTS.md` §"Rust specific guidance" (lines 150-227): unit and behavioural
  tests with `rstest`/`rstest-bdd`, cover happy/unhappy/edge paths; module-level
  `//!` docs; en-GB Oxford spelling; gate targets.

## Plan of work

Two ordered, independently committable work items, each ending with the full
commit-gate run.

### WI-1 — Unit characterization tests in `stilyagi-markdown`

Docs to read first: `docs/stilyagi-design.md` §4 "Suppression syntax" and §5
source-span rule; `AGENTS.md` Rust guidance (unit tests with `rstest`, happy
and unhappy paths). Skills to load: `rust-router` then `rust-unit-testing`
(rstest idioms) and `leta` for symbol navigation; `en-gb-oxendict` for prose in
doc comments.

Add tests to `crates/stilyagi-markdown/src/tests/suppression.rs` (the module
already imports `markdown_ir_document`, `parse_markdown_ast`, `SourceSpan`,
`SuppressionKind`, `find_html_node`, `html_node_ids`, and `source_identity`).

1. A parser-level test, e.g. `inline_html_comment_is_a_paragraph_child_node`,
   that parses a within-paragraph directive source such as
   `"Apples <!-- stilyagi: ignore-next PUN201 --> and pears.\n"`, uses the
   existing `find_html_node` helper to locate the inline `Node::Html`, and
   asserts its position re-slices to exactly
   `"<!-- stilyagi: ignore-next PUN201 -->"`. This pins the risk that the
   comment is folded into text.

2. An IR-level `#[rstest]` case test, e.g.
   `markdown_ir_document_collects_inline_paragraph_suppressions`, driving
   `markdown_ir_document` over within-paragraph sources for each verb:
   - `ignore-next PUN201` -> one `SuppressionKind::Inline`, codes `["PUN201"]`;
   - `disable STY` -> `SuppressionKind::Range`, codes `["STY"]`;
   - `enable STY` -> `SuppressionKind::Range`, codes `["STY"]`;
   - `ignore-file MD` inline -> `SuppressionKind::File`, codes `["MD"]`.
   For each, assert `document.errors` is empty, exactly one suppression exists,
   its `origin` equals the inline html node id (via `html_node_ids`), and its
   span re-slices from source to exactly the comment. Follow the assertion
   shape already used in `markdown_ir_document_collects_canonical_suppressions`.

3. An unhappy-path test, e.g.
   `inline_blanket_directive_in_paragraph_emits_error_only`, driving a
   within-paragraph `<!-- stilyagi: ignore-next -->` (no code). Assert
   `document.suppressions` is empty and `document.errors` contains exactly one
   entry with code `"suppression-blanket-forbidden"` whose span re-slices to
   the comment. This pins the "blanket inline suppression forbidden" invariant
   for the inline position.

Keep new helper functions minimal; reuse existing helpers. Every new test uses
inline `concat!`/string literals, matching the module idiom.

### WI-2 — BDD scenario at the extraction boundary

Docs to read first: `AGENTS.md` (behavioural tests with `rstest-bdd`, cover
externally observable workflows); the existing feature and steps. Skills to
load: `rust-router` then `rust-unit-testing`; `leta`; `en-gb-oxendict` for the
feature prose.

1. Append a scenario to
   `crates/stilyagi-extract/tests/features/markdown_suppression.feature`, for
   example:

   ```plaintext
   Scenario: An inline directive within a paragraph becomes a suppression
     Given a Markdown document with an inline "stilyagi: ignore-next PUN201" comment in a paragraph
     When the document is extracted
     Then the IR suppressions contain one inline entry naming PUN201
     And the inline suppression span re-slices to the directive comment
   ```

   Reuse the existing `When the document is extracted` and
   `Then the IR suppressions contain one inline entry naming PUN201` steps.

2. In `crates/stilyagi-extract/tests/extract/markdown_suppression_bdd.rs`, add:
   - a new `#[given]` step whose text matches the new Given line, setting
     `state.source` to a within-paragraph source such as
     `"# Fixture\n\nApples <!-- stilyagi: ignore-next PUN201 --> and pears.\n"`;
   - a new `#[then]` step for the inline span re-slice assertion (the existing
     `the suppression span re-slices to the directive comment` step asserts the
     exact same comment text, so either reuse it by matching its wording or add
     a distinctly worded step that performs the same re-slice check — prefer
     reuse to avoid duplication);
   - a `#[scenario(...)]` binding function referencing the new scenario `name`,
     following the two existing `#[scenario]` bindings.

No change to `extract_integration.rs` is needed; the module is already
registered.

## Concrete steps

Working directory for all commands:
`/home/leynos/Projects/stilyagi.worktrees/roadmap-2-1-3-2`.

Manual red-stage confirmation (per `Risks`, since these are characterization
tests): after writing each new assertion, temporarily invert one expectation
(for example assert the inline suppression kind is `Range` where it should be
`Inline`) and run the focused test to confirm it *fails* for the intended
reason, then restore the correct expectation. This proves the test exercises
the inline path rather than passing vacuously. Record the observed failure in
`Surprises & discoveries` only if it differs from expectation.

Focused test runs (fast iteration):

```sh
cargo test --manifest-path crates/stilyagi-markdown/Cargo.toml suppression
cargo test --manifest-path crates/stilyagi-extract/Cargo.toml --test extract_integration markdown_suppression
```

Expected: the new tests appear in the run summary and pass (after the restore
step). Prior to WI-1 the inline tests do not exist; after WI-1 they pass.

Commit each work item separately (branch is `roadmap-2-1-3-2`, already off
`main`). Use `commit-message` skill; en-GB imperative subject, for example
`Pin inline paragraph suppression classification`.

## Validation and acceptance

Run the deterministic commit gates sequentially (never in parallel; delegate
the full run to the `scrutineer` subagent), in this order, from the worktree
root, before each commit:

```sh
make check-fmt
make typecheck
make lint
make test
```

Because this ExecPlan is a Markdown document, also run the Markdown gates for
the documentation change:

```sh
make markdownlint
make nixie
```

All must pass. `make test` runs `cargo test --workspace`, which includes the new
`stilyagi-markdown` unit tests and the `stilyagi-extract` BDD integration
tests.

Red-Green-Refactor / characterization evidence:

- Red substitute: the manual inverted-expectation check in `Concrete steps`
  (temporarily assert the wrong kind/codes/span and observe the focused test
  fail for the intended reason), because the production behaviour already
  exists and a genuine pre-implementation red is not available for
  coverage-only tests.
- Green: after writing the correct expectations, the focused test commands above
  pass, and the full `make test` passes.
- Refactor: none expected (test-only change); if any helper is extracted, rerun
  the focused tests and `make test`.

Acceptance (behaviour a human can verify):

- `make test` passes with the new unit tests
  `inline_html_comment_is_a_paragraph_child_node`,
  `markdown_ir_document_collects_inline_paragraph_suppressions`, and
  `inline_blanket_directive_in_paragraph_emits_error_only` present and passing.
- `make test` passes with the new BDD scenario "An inline directive within a
  paragraph becomes a suppression" present and passing.
- `make check-fmt`, `make typecheck`, `make lint`, `make markdownlint`, and
  `make nixie` all pass.

Quality criteria (what "done" means):

- Tests: new unit and BDD tests pass; whole workspace suite green.
- Lint/typecheck: `make lint` and `make typecheck` clean (Clippy `-D warnings`).
- Formatting: `make check-fmt` clean.
- No production source file changed.

## Idempotence and recovery

All steps are additive test code and this plan document; re-running the gates
is safe and repeatable. If a focused test fails unexpectedly (not via the
manual inversion), do not patch production code — record the discovery and
escalate per `Tolerances`. To recover a clean tree, `git restore` the touched
test files and re-apply the edits. Do not run repo-global formatters; if
Markdown formatting of this plan is needed, run `mdtablefix` then
`markdownlint-cli2 --fix` on this file only, then re-gate.

## Artifacts and notes

Static evidence gathered during planning (cite when implementing):

- `crates/stilyagi-markdown/src/builder.rs` lines 82-87: every `Node::Html`
  becomes a `SuppressionCandidate`, with no flow/inline distinction.
- `crates/stilyagi-markdown/src/node_kind.rs`: single `Node::Html(_) => "html"`
  variant, confirming flow and inline HTML share one mdast node type.
- `crates/stilyagi-markdown/src/lib.rs` lines 208-261: candidate re-slice →
  `parse_comment_directive` → `verb_kind` → `IrSuppression`/`IrError`.

## Interfaces and dependencies

No new interfaces or dependencies. Tests use existing symbols:

- `stilyagi_markdown::markdown_ir_document`,
  `stilyagi_markdown::parse_markdown_ast`, and the crate-private test helpers
  `find_html_node`, `html_node_ids`, `source_identity` in
  `crates/stilyagi-markdown/src/tests/suppression.rs`.
- `stilyagi_extract::{extract_document, ExtractDocument, ExtractSyntax}` and
  `stilyagi_ir::{IrDocument, SuppressionKind}` in the BDD module.
- `rstest`, `rstest-bdd` (via `rstest_bdd_macros`), and `proptest` are already
  workspace dev-dependencies.
