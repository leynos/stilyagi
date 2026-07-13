# Unify the region-kind vocabulary across `stilyagi-ir` and `stilyagi-extract`

This ExecPlan (execution plan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work
proceeds.

Status: COMPLETE

## Purpose / big picture

Stilyagi has two crates that both name lintable prose "region kinds", and today
they name them independently:

- `stilyagi-ir` owns the canonical region-kind vocabulary as the enum
  `stilyagi_ir::RegionKind` (`crates/stilyagi-ir/src/region.rs`). Its eleven
  variants and their stable string spellings are the v1 contract named by RFC
  0001 §6 (region `kind` vocabulary) and clarified by ADR 005.
- `stilyagi-extract` defines a *second*, unrelated enum, also called
  `RegionKind` (`crates/stilyagi-extract/src/lib.rs`), with three variants —
  `Document`, `PythonDocstring`, `RustDocComment` — whose spellings
  (`"document"`, `"python_docstring"`, `"rust_doc_comment"`) are hand-written
  string literals in a `match`.

The two enums overlap on the spellings `"python_docstring"` and
`"rust_doc_comment"`, but nothing ties them together. If someone renamed a
shared spelling in one crate (or in the tree-sitter extractor that *populates*
`IrRegion.kind` with the same hand-written literals), the other crate would keep
the old spelling and the divergence would compile and pass tests silently. The
Python/Rust extraction paths in `stilyagi-extract` copy `IrRegion.kind` strings
straight through (`crates/stilyagi-extract/src/lib.rs`
`extract_python_document` / `extract_rust_document`), so a silent rename would
produce region kinds that no longer match `stilyagi-extract`'s own
`RegionKind::try_from` — with no test to catch it.

Roadmap item 6.4.1 asks us to make this impossible: "Keep the shared vocabulary
as the single source of truth **or** add a cross-checking test that fails on
drift. Success: the two crates cannot silently diverge on region names or
meanings."

After this change:

1. `stilyagi_ir::RegionKind` is the *single source of truth* for every region
   spelling that both crates share. `stilyagi_extract::RegionKind` derives those
   spellings from it instead of re-typing string literals, so a shared spelling
   physically exists in exactly one place.
2. An exhaustive, adversarial cross-checking test proves that every region kind
   `stilyagi-extract` can emit — including the kinds that flow through the IR
   from the tree-sitter extractor — is a member of the shared IR vocabulary,
   with the coarse bridge-only `document` region as the single, explicitly
   documented exception.

Observable success: running `make test` passes; and if a developer changes a
shared spelling in only one crate (for example renames the IR spelling of
`python_docstring`, or edits the hand-written `"rust_doc_comment"` literal in
`stilyagi-tree-sitter`), a named test fails and names the drift. The plan
records the exact temporary-mutation demonstration that proves each guard test
actually catches drift.

## Constraints

Hard invariants that must hold throughout implementation. Violation requires
escalation, not a workaround.

- The stable v1 IR region-kind vocabulary is fixed by RFC 0001 §6
  (`docs/rfcs/0001-stilyagi-intermediate-representation.md`, the
  "`kind` SHALL come from a stable, small vocabulary" list) and ADR 005
  (`docs/adr-005-markdown-region-vocabulary-scope.md`). Do **not** add, remove,
  rename, or reorder any `stilyagi_ir::RegionKind` variant or spelling. In
  particular, `document` is **not** an IR region kind and must not be added to
  `stilyagi_ir::RegionKind`; `frontmatter_field` stays reserved.
- Public serialized spellings must not change. `IrRegion.kind` is a `String`
  field serialized via serde (`crates/stilyagi-ir/src/region.rs`); all existing
  golden fixtures and snapshots must continue to match byte-for-byte.
- `stilyagi_extract::RegionKind` is `#[non_exhaustive]`; keep it so. Its three
  existing variants (`Document`, `PythonDocstring`, `RustDocComment`) and their
  spellings must remain unchanged — this work only changes *where the spelling
  comes from*, not the spelling itself.
- Follow the en-GB Oxford-spelling convention ("-ize"/"-yse"/"-our") in all
  prose, comments, and commit messages (AGENTS.md).
- Do not modify crates outside `stilyagi-ir`, `stilyagi-extract`, and (for the
  optional hardening item only) `stilyagi-tree-sitter`.

## Tolerances (exception triggers)

- Scope: if implementation requires changes to more than 3 non-test source
  files or more than roughly 150 net lines of code, stop and escalate.
- Interface: if any *public* API signature in `stilyagi-ir` or
  `stilyagi-extract` must change in a breaking way (removing or renaming an
  existing public item), stop and escalate. Adding `pub const ALL` and a
  `pub const fn` mapping is additive and allowed.
- Dependencies: if any new external crate dependency is required, stop and
  escalate. (`stilyagi-extract` already depends on `stilyagi-ir`;
  `stilyagi-tree-sitter` already depends on `stilyagi-ir`. No new deps expected.)
- Iterations: if a gate still fails after 3 fix attempts, stop and escalate.
- Vocabulary: if a genuine product decision is needed about whether `document`
  should join the IR vocabulary (rather than staying a bridge-only exception),
  stop and escalate — that is an RFC/ADR change, not an implementation choice.

## Risks

- Risk: the drift-guard tests pass on day one because the spellings already
  coincide, so they read as new behaviour when they are really regression
  guards.
  Severity: medium. Likelihood: high.
  Mitigation: for each guard test, the plan requires a temporary local mutation
  (flip a shared spelling), observe the named failure, then revert — recording
  the transcript as the Red evidence. This proves the guard bites.
- Risk: forwarding `stilyagi_extract::RegionKind::as_str` to
  `stilyagi_ir::RegionKind::as_str` fails to compile in `const` context.
  Severity: low. Likelihood: low.
  Mitigation: `stilyagi_ir::RegionKind::as_str` is already `pub const fn`
  (`crates/stilyagi-ir/src/region.rs`), so a `const fn` in `stilyagi-extract`
  may call it. If the compiler disagrees, drop the `const` qualifier on the
  extract method (it is not part of any const-eval contract) and record the
  reason in the Decision Log.
- Risk: the behavioural cross-check depends on shared test fixtures whose region
  set changes later.
  Severity: low. Likelihood: low.
  Mitigation: the behavioural test asserts a *membership* invariant ("every
  emitted kind parses as an IR kind"), not an exact list, so adding fixtures or
  regions cannot break it unless a genuine drift occurs.
- Risk: scope creep into `stilyagi-tree-sitter` (Work item 3) draws objection
  because the roadmap names only two crates.
  Severity: low. Likelihood: medium.
  Mitigation: Work item 3 is independently committable and can be dropped
  without weakening Work items 1–2; the behavioural cross-check in Work item 2
  already fails on tree-sitter literal drift even if the literal is left in
  place. See the Decision Log entry on scope.

## Progress

- [x] 2026-07-14: The developer API docs and roadmap completion state were
      synchronized after verification.
- [x] 2026-07-14: The two inline documentation findings were verified and
      corrected.
- [x] 2026-07-14: The post-turn Whitaker gate's reported test-only
      `unwrap_or_else` panic sites were verified by wyvern, minimal `expect`
      replacements were applied across the affected test modules, and all six
      gates (`check-fmt`, `lint`, `typecheck`, `test`, `markdownlint`,
      `nixie`) passed.
- [x] 2026-07-07: Confirmed the branch is `roadmap-6-4-1`, already tracking
      `origin/roadmap-6-4-1`; renamed the Lody session to
      `roadmap-6-4-1 region vocabulary unification`.
- [x] 2026-07-07: Re-read the plan, RFC 0001 §6, ADR 003, ADR 005, the design
      note's IR section, the developer guide's region-kind notes, and the
      `leta`, `execplans`, `rust-router`, `rust-types-and-apis`,
      `rust-unit-testing`, and `sem` skills before editing.
- [x] 2026-07-07: Work item 1 implemented, red evidence recorded, deterministic
      gates passed, and `coderabbit review --agent` completed with zero
      findings.
- [x] Work item 1: `stilyagi-ir` is the single source of truth for shared bridge
      spellings; `stilyagi_extract::RegionKind` forwards to it and gains
      `ALL` + an `ir_region_kind` mapping.
- [x] 2026-07-07: Work item 2 implemented. Added the registered
      `region_vocabulary` integration test, filled the `RustDocComment`
      spelling-display coverage gap, and captured both required drift
      demonstrations. Deterministic gates passed after one style fix, and
      `coderabbit review --agent` completed with zero findings.
- [x] Work item 2: exhaustive + behavioural cross-check test proves every
      extract-emitted region kind is in the IR vocabulary (bar the documented
      `document` exception); fill the pre-existing `RustDocComment` coverage gap.
- [x] 2026-07-07: Work item 3 implemented. Replaced the two producer-side
      tree-sitter region-kind literals with `stilyagi_ir::RegionKind` spellings
      and confirmed the focused extract vocabulary test still passes.
      Deterministic gates passed, and `coderabbit review --agent` completed
      with zero findings.
- [x] Work item 3 (recommended hardening): replace the hand-written
      `"python_docstring"` / `"rust_doc_comment"` literals in
      `stilyagi-tree-sitter` with the shared `stilyagi_ir::RegionKind` constants.

## Surprises & discoveries

- Observation: the full lint gate exposed the same `no_unwrap_or_else_panic`
  rule beyond the initial three hook-reported sites.
  Impact: the test-only `unwrap_or_else` panics need the same replacement
  treatment once wyvern verification confirms the remaining hits.
- Observation: Memtrace is available in this session, but its briefing reported
  no indexed repository for this worktree. The repository-list/index tools were
  not exposed after tool discovery.
  Evidence: `get_codebase_briefing` returned "No indexed repository found. Run
  index_directory first."
  Impact: source-code navigation for this task uses `leta` plus bounded
  exact-path reads from this ExecPlan, rather than Memtrace graph queries.
- Observation: the Work item 1 consistent-IR-rename drift demonstration fails
  at the extract spelling round-trip boundary, as intended.
  Evidence: after temporarily changing the IR Python docstring spelling in
  `crates/stilyagi-ir/src/region.rs` from `python_docstring` to
  `py_docstring` in both `as_str` and `TryFrom`, the focused command
  `cargo test -p stilyagi-extract region_kind_as_str_round_trips_through_try_from`
  failed with
  `spelling_display::region_kind_as_str_round_trips_through_try_from::case_2`;
  the assertion reported `left: Err("py_docstring")` and
  `right: Ok(PythonDocstring)`. The temporary mutation was reverted before
  continuing.
  Impact: a consistent IR spelling rename cannot silently pass extract's
  existing typed spelling round-trip once `as_str` forwards to the IR.
- Observation: the Work item 1 un-forwarding drift demonstration fails at the
  new `shared_bridge_spelling_comes_from_ir` guard, as intended.
  Evidence: after temporarily replacing the forwarding arm in
  `stilyagi_extract::RegionKind::as_str` with `Some(_) => "py_docstring"`, the
  focused command
  `cargo test -p stilyagi-extract shared_bridge_spelling_comes_from_ir` failed;
  the assertion reported `left: "py_docstring"` and
  `right: "python_docstring"`. The temporary mutation was reverted before
  continuing.
  Impact: a future edit that reintroduces divergent local spellings in extract
  is caught by a named guard.
- Observation: `RegionKind` is `#[non_exhaustive]`, so external integration
  tests cannot exhaustively match all variants without a wildcard.
  Evidence: the first Work item 2 focused compile failed in
  `crates/stilyagi-extract/tests/extract/region_vocabulary.rs` with
  `E0004: non-exhaustive patterns: &_ not covered` when matching
  `RegionKind::Document | RegionKind::PythonDocstring |
  RegionKind::RustDocComment`.
  Impact: the integration cross-check now uses the public
  `RegionKind::ir_region_kind()` mapping and a direct equality check for the
  `Document` exception, preserving the invariant without depending on an
  externally exhaustive match.
- Observation: Work item 2's first full gate run caught local style issues in
  the new `region_vocabulary` integration test before CodeRabbit review.
  Evidence: `make check-fmt` reported rustfmt wrapping drift at
  `crates/stilyagi-extract/tests/extract/region_vocabulary.rs:35`, and
  `make lint` reported Clippy `single_match_else` at line 11. The test was
  reshaped to use `if let` for the mapped IR kind and rustfmt-compatible
  assertion wrapping.
  Impact: this stayed within the first fix attempt for Work item 2 and did not
  alter the tested invariant.
- Observation: the Work item 2 tree-sitter drift demonstration fails at the new
  behavioural cross-check, as intended.
  Evidence: after temporarily changing
  `crates/stilyagi-tree-sitter/src/python/mod.rs` from
  `kind: "python_docstring".to_owned()` to `kind: "python_doc".to_owned()`, the
  focused command
  `cargo test -p stilyagi-extract extracted_ir_regions_use_only_the_shared_vocabulary`
  failed with
  `region_vocabulary::extracted_ir_regions_use_only_the_shared_vocabulary::case_1_python_docstrings`;
  the Rust doc-comment case passed. The temporary mutation was reverted before
  continuing.
  Impact: a producer-side typo in emitted IR region spellings is caught before
  it can silently cross the extract boundary.
- Observation: the Work item 2 `document` exception demonstration fails at the
  new static cross-check, as intended.
  Evidence: after temporarily changing the bridge-only `Document` spelling in
  `stilyagi_extract::RegionKind::as_str` from `document` to `paragraph`, the
  focused command
  `cargo test -p stilyagi-extract every_shared_bridge_kind_is_an_ir_kind`
  failed with `region_vocabulary::every_shared_bridge_kind_is_an_ir_kind`; the
  assertion expected `stilyagi_ir::RegionKind::try_from(kind.as_str())` to be
  `Err`. The temporary mutation was reverted before continuing.
  Impact: a future change that makes the bridge-only `Document` kind collide
  with the canonical IR vocabulary is caught by a named guard.
- Observation: after Work item 3, the Python and Rust tree-sitter producers no
  longer contain hand-written `python_docstring` or `rust_doc_comment` region
  `kind` assignments.
  Evidence: `crates/stilyagi-tree-sitter/src/python/mod.rs` now uses
  `RegionKind::PythonDocstring.as_str().to_owned()`, and
  `crates/stilyagi-tree-sitter/src/rust/builder.rs` now uses
  `RegionKind::RustDocComment.as_str().to_owned()`.
  Impact: producer-side shared spelling drift now requires changing the IR
  source of truth instead of editing independent string literals.
- Observation: rebasing onto `origin/main` on 2026-07-07 brought in
  syntax-native suppression parsing, the tree-sitter 0.26 update, and related
  Rust doc-comment builder changes. The rebase applied without textual
  conflicts, but the rebased Work item 3 import edit dropped the IR type import
  that `main` still needs in `crates/stilyagi-tree-sitter/src/rust/builder.rs`.
  Evidence: the first post-rebase gate run failed to compile
  `stilyagi-tree-sitter` because `IrNode`, `IrRegion`, and `IrError` were not
  in scope. Restoring `use stilyagi_ir::{IrError, IrNode, IrRegion, NodeFlags,
  RegionKind};` preserves `main`'s builder changes while keeping this branch's
  shared-vocabulary hardening.
  Impact: the branch now reflects `main`'s newer suppression and tree-sitter
  patterns without losing the region-kind single-source-of-truth change.
- Observation: `stilyagi-extract`'s own spelling test coverage is already
  incomplete — `region_kind_as_str_round_trips_through_try_from` and the
  display/`as_str` cases in
  `crates/stilyagi-extract/tests/extract/spelling_display.rs` cover `Document`
  and `PythonDocstring` but **omit** `RustDocComment`.
  Evidence: `spelling_display.rs` lines 56–100 (only two `#[case]`s each).
  Impact: Work item 2 closes this gap while adding the cross-check.
- Observation: the tree-sitter extractor hand-writes the same region-kind
  spellings the IR owns (`"python_docstring"` at
  `crates/stilyagi-tree-sitter/src/python/mod.rs:318`, `"rust_doc_comment"` at
  `crates/stilyagi-tree-sitter/src/rust/builder.rs:246`), and those values
  become `IrRegion.kind` that `stilyagi-extract` copies through verbatim.
  Evidence: `extract_python_document` / `extract_rust_document` in
  `crates/stilyagi-extract/src/lib.rs` map `region.kind.clone()`.
  Impact: divergence can originate in a *third* crate. Work item 2's behavioural
  test catches it; Work item 3 removes the hazard at source.
- Observation: `stilyagi-extract`'s integration tests are **not** registered via
  a `tests/extract/mod.rs` (there is none). The single test binary is
  `crates/stilyagi-extract/tests/extract_integration.rs`, which registers each
  file with `#[path = "extract/<file>.rs"] mod <name>;`. A new file added under
  `tests/extract/` without a matching entry is not compiled or run.
  Evidence: `extract_integration.rs` (path-attribute registrations);
  `ls tests/extract/` shows no `mod.rs`.
  Impact: Work item 2 must add the `region_vocabulary` registration there or its
  cross-check silently never runs (round-1 blocking defect B1).

## Decision log

- Decision: proceed with implementation even though the existing plan header
  said `Status: DRAFT`.
  Rationale: the user explicitly instructed this agent on 2026-07-07 to proceed
  with implementation of `docs/execplans/roadmap-6-4-1.md`, which serves as the
  execution approval required by the `execplans` skill.
  Date/Author: 2026-07-07, implementation agent.
- Decision: do not add a property test for Work item 1's closed
  `RegionKind::ALL` invariant or Work item 2's static bridge-kind
  cross-check.
  Rationale: the verification skill routes input-space gaps to `proptest`, but
  this invariant is over a closed enum set. The exhaustive `ALL` iteration plus
  compile-time non-wildcard match in crate-private tests and the public
  `ir_region_kind()` mapping in integration tests give the necessary coverage
  with less machinery.
  Date/Author: 2026-07-07, implementation agent.
- Decision: implement *both* allowed mechanisms — single source of truth (Work
  item 1) and a cross-checking drift test (Work item 2) — rather than only one.
  Rationale: the roadmap permits either; doing both is strictly stronger and
  cheap. Forwarding removes the duplicated literal; the test guards the
  relationship (including drift that originates in tree-sitter, which forwarding
  alone cannot cover).
  Date/Author: 2026-07-05, planning agent.
- Decision: keep `document` as a bridge-only region kind and explicitly assert
  it is *not* in the IR vocabulary, instead of adding it to
  `stilyagi_ir::RegionKind`.
  Rationale: RFC 0001 §6 fixes the IR vocabulary at eleven kinds and does not
  include `document`; ADR 005 constrains the Markdown subset. `document` is a
  coarse whole-source bridge region on `ExtractRegion`, not an `IrRegion` kind.
  Adding it to the IR enum would be an RFC/ADR change and is out of scope.
  Date/Author: 2026-07-05, planning agent.
- Decision: include the tree-sitter literal replacement as Work item 3 but mark
  it independently committable and droppable.
  Rationale: the roadmap names `stilyagi-ir` and `stilyagi-extract`; touching
  `stilyagi-tree-sitter` is a scope boundary. Work item 2 already fails on
  tree-sitter drift, so Work item 3 is hardening (remove the hazard) rather than
  a correctness prerequisite. Framing it as separable lets a reviewer trim scope
  without reopening Work items 1–2.
  Date/Author: 2026-07-05, planning agent.
- Decision: Red-Green-Refactor is applied via the temporary-mutation
  demonstration for the drift guards (the guarded invariant already holds, so a
  natural failing test is unavailable).
  Rationale: execplans skill permits the nearest observable substitute when
  Red-Green is genuinely unavailable; a documented mutate-observe-revert step is
  that substitute and directly proves the guard catches drift.
  Date/Author: 2026-07-05, planning agent.

## Outcomes & retrospective

Implemented the roadmap 6.4.1 region-vocabulary guard.
`stilyagi_extract::RegionKind` now forwards shared Python and Rust bridge
spellings through `stilyagi_ir::RegionKind`, while keeping `document` as the
single bridge-only exception. The extract integration suite now has a registered
`region_vocabulary` test module that proves shared bridge spellings round-trip
through the IR vocabulary and that emitted Python/Rust IR regions use only
canonical IR region kinds. The existing spelling-display test matrix now covers
`RustDocComment`.

The recommended tree-sitter hardening also landed: Python docstring and Rust
doc-comment producers now populate `IrRegion.kind` from
`stilyagi_ir::RegionKind` instead of independent literals.

The drift guards were deliberately mutated and observed to fail before each
mutation was reverted. Deterministic gates passed for all three work items, and
CodeRabbit review completed with zero findings after each major milestone.

## Context and orientation

Read these before starting. Paths are repository-relative.

- `docs/rfcs/0001-stilyagi-intermediate-representation.md` §6 (the
  "`kind` SHALL come from a stable, small vocabulary" list, lines ~223–251):
  the authoritative eleven-kind vocabulary and the note that `summary_line` is
  a derived view, not a region kind. This is what "the shared vocabulary" means.
- `docs/adr-005-markdown-region-vocabulary-scope.md`: why `list_item` /
  `blockquote` are thin, why `frontmatter_field` is reserved, and why
  `image_alt` / `link_title` are synthetic. Confirms the vocabulary is closed.
- `docs/adr-003-v1-contract-scope.md`: the v1 contract-freezing discipline that
  makes "cannot silently diverge" a real requirement.
- `docs/stilyagi-design.md` §7.1 (Intermediate representation, lines ~786+):
  design commentary confirming region vocabulary is engine-owned and stable.
- `AGENTS.md`: quality gates and testing rules (unit + behavioural tests
  required for behaviour changes; en-GB Oxford spelling).

Key code:

- `crates/stilyagi-ir/src/region.rs`: `RegionKind` enum, `RegionKind::ALL`,
  `as_str` (a `pub const fn`), `Display`, `TryFrom<&str>`, and `InvalidRegionKind`.
  This is the single source of truth. Existing exhaustiveness/round-trip tests
  live in `crates/stilyagi-ir/src/tests/mod.rs` (the
  `region_kind_ordering_is_stable` expected-list test at lines ~54–73 and the
  `region_kind_round_trips_through_stable_spelling` case list at lines ~75–89).
- `crates/stilyagi-extract/src/lib.rs`: the *second* `RegionKind` enum
  (`Document`, `PythonDocstring`, `RustDocComment`) at lines ~152–193, its
  `as_str` / `Display` / `TryFrom<&str>`, `ExtractRegion` (a coarse bridge
  region with a `String` `kind`), and the extraction functions
  `extract_markdown_document_with` (emits one `Document` region),
  `extract_python_document`, `extract_rust_document` (copy `IrRegion.kind`).
- `crates/stilyagi-extract/tests/extract/spelling_display.rs`: existing extract
  spelling/round-trip tests (with the `RustDocComment` coverage gap).
- `crates/stilyagi-extract/tests/extract/ir_identity.rs`,
  `crates/stilyagi-extract/tests/extract_integration.rs`, and
  `crates/stilyagi-extract/tests/extract/test_utils.rs`: existing
  integration-test harness and helpers, including `shared_python_source` /
  `shared_rust_source` helpers and `stilyagi-test-support` fixture constants —
  reuse these for the behavioural cross-check.
- `crates/stilyagi-tree-sitter/src/python/mod.rs:318` and
  `crates/stilyagi-tree-sitter/src/rust/builder.rs:246`: the hand-written
  region-kind literals that populate `IrRegion.kind`. `stilyagi-tree-sitter`
  already depends on `stilyagi-ir` and already imports from it.

Term definitions:

- **Region kind**: a stable string tag on a lintable prose region (`heading`,
  `python_docstring`, …). The IR owns the canonical set.
- **Bridge region** (`ExtractRegion`): a coarse `{kind, text}` pair surfaced by
  `stilyagi-extract`; for Markdown it is a single whole-source `document`
  region. Distinct from the fine-grained `IrRegion`.
- **Drift**: two crates disagreeing on a region name/meaning without any test
  failing.

## Plan of work

Three ordered, independently committable work items. Each ends with the full
gate sequence. Work items 1 and 2 satisfy the roadmap success criterion on the
named `stilyagi-ir`/`stilyagi-extract` seam; Work item 3 is recommended
hardening on the IR-producing side.

### Work item 1 — `stilyagi-ir` as the single source of truth; `stilyagi-extract` forwards

Implements: RFC 0001 §6 (canonical vocabulary), ADR 003 (frozen v1 contract),
roadmap 6.4.1 ("keep the shared vocabulary as the single source of truth").

Docs to read first: RFC 0001 §6; ADR 005; `docs/stilyagi-design.md` §7.1.
Skills to load: `rust-router` (route to `rust-types-and-apis` for the enum
mapping and `const fn` question, and `rust-unit-testing` for the guard test);
`leta` for symbol navigation; `sem` for the region-kind history.

Edit `crates/stilyagi-extract/src/lib.rs` on the `RegionKind` enum:

1. Add an associated mapping from the extract kind to the shared IR kind:

   ```rust
   impl RegionKind {
       /// The shared IR region kind this bridge kind denotes, when it is part
       /// of the canonical `stilyagi_ir` vocabulary. `Document` is a
       /// bridge-only coarse region with no IR region-kind equivalent.
       #[must_use]
       pub const fn ir_region_kind(self) -> Option<stilyagi_ir::RegionKind> {
           match self {
               Self::Document => None,
               Self::PythonDocstring => Some(stilyagi_ir::RegionKind::PythonDocstring),
               Self::RustDocComment => Some(stilyagi_ir::RegionKind::RustDocComment),
           }
       }
   }
   ```

2. Reimplement `as_str` so shared spellings come *only* from the IR enum, with
   `Document` as the single local literal:

   ```rust
   pub const fn as_str(self) -> &'static str {
       match self.ir_region_kind() {
           Some(kind) => kind.as_str(),
           None => "document",
       }
   }
   ```

   (If `const` evaluation across the crate boundary fails to compile, drop the
   `const` qualifier and record it in the Decision Log — see Risks.)

3. Add an ordered `ALL` constant so tests can iterate every variant and cannot
   silently forget a new one:

   ```rust
   impl RegionKind {
       /// All bridge region kinds, in canonical order.
       pub const ALL: &'static [Self] = &[Self::Document, Self::PythonDocstring, Self::RustDocComment];
   }
   ```

Leave `TryFrom<&str>` as-is for now (it still hand-writes the three spellings);
Work item 2's test pins it against the forwarded `as_str`, so it cannot drift
from the source of truth without a failure.

Tests (unit, in `crates/stilyagi-extract/src/lib.rs` `#[cfg(test)] mod tests`,
or extend `tests/extract/spelling_display.rs`):

- `region_kind_all_is_exhaustive`: assert `RegionKind::ALL.len()` equals the
  number of variants by matching each in a helper that returns `()` for every
  arm (a `match` with no `_` wildcard, so adding a variant fails to compile
  until `ALL` is updated).
- `shared_bridge_spelling_comes_from_ir`: for each `k` in `RegionKind::ALL`,
  if `k.ir_region_kind()` is `Some(ir)`, assert `k.as_str() == ir.as_str()`;
  else (`Document`) assert `stilyagi_ir::RegionKind::try_from(k.as_str())` is
  `Err`.

Red evidence (mutate-observe-revert, since the invariant already holds). Two
*different* mutations are required, because the two guards catch two different
drifts — and, critically, `shared_bridge_spelling_comes_from_ir` is
definitionally true while `as_str` forwards (its `k.as_str() == ir.as_str()`
arm compares a value against itself once `as_str` is `ir.as_str()` by
construction), so a *consistent* IR rename propagates through the forward to
**both** sides of that equality and the guard keeps passing. It bites only when
the forwarding is broken. Record both transcripts in `Surprises & discoveries`:

- Guard for a **consistent IR rename** (extract `TryFrom` still hand-writes the
  old spelling): temporarily change `stilyagi_ir::RegionKind::PythonDocstring`'s
  spelling in `crates/stilyagi-ir/src/region.rs` (`as_str` **and** `TryFrom`) to
  `"py_docstring"`, run `make test`, and observe the extract
  `region_kind_*_round_trips_*` tests in `spelling_display.rs` fail — forwarded
  `as_str` now yields `"py_docstring"` while extract `TryFrom` still expects
  `"python_docstring"`. `shared_bridge_spelling_comes_from_ir` does **not** fail
  here (both sides moved together); do not claim it does. Then revert.
- Guard for **un-forwarding** (a hand-written literal reintroduced into extract
  `as_str`): temporarily replace the `Some(kind) => kind.as_str()` arm of the new
  `stilyagi_extract::RegionKind::as_str` with a divergent literal, e.g.
  `Some(_) => "py_docstring"`, run `make test`, and observe
  `shared_bridge_spelling_comes_from_ir` fail (for `PythonDocstring`,
  `k.as_str()` is now `"py_docstring"` but `ir.as_str()` is `"python_docstring"`).
  Then revert. This is the mutation that proves *this* named guard bites, and it
  is its true purpose: catch a future edit that stops forwarding.

Validation: `make check-fmt` then `make typecheck` then `make lint` then
`make test`. Commit: `Forward extract region spellings to the IR vocabulary`.

### Work item 2 — exhaustive + behavioural cross-check that fails on drift

Implements: roadmap 6.4.1 ("add a cross-checking test that fails on drift";
"the two crates cannot silently diverge on region names or meanings"); RFC 0001
§6; AGENTS.md testing rules (unit + behavioural coverage).

Docs to read first: RFC 0001 §6; ADR 005 (the closed vocabulary);
`AGENTS.md` testing section. Skills to load: `rust-router` →
`rust-unit-testing`; `rust-verification` (to judge whether a property/`proptest`
case adds value over the enumerated cross-check — see below); `leta`.

Add a new integration test file
`crates/stilyagi-extract/tests/extract/region_vocabulary.rs`. This crate's
integration tests are **not** registered through a `tests/extract/mod.rs` file
(none exists); the single test binary is `crates/stilyagi-extract/tests/extract_integration.rs`,
which pulls each file in via a `#[path = "extract/<file>.rs"] mod <name>;`
attribute. Register the new file the same way by adding, in alphabetical
position alongside the existing entries:

```rust
#[path = "extract/region_vocabulary.rs"]
mod region_vocabulary;
```

to `crates/stilyagi-extract/tests/extract_integration.rs`. A file dropped into
`tests/extract/` **without** this entry is not compiled or run, so the
cross-check would silently never execute in `make test` — this registration is
load-bearing, not optional.

Static cross-check (adversarial, exhaustive over `RegionKind::ALL`):

- `every_shared_bridge_kind_is_an_ir_kind`: for each `k` in
  `stilyagi_extract::RegionKind::ALL`, assert exactly one of:
  - `k == RegionKind::Document` and `stilyagi_ir::RegionKind::try_from(k.as_str())`
    is `Err` (the documented, intentional bridge-only exception), or
  - `stilyagi_ir::RegionKind::try_from(k.as_str())` is `Ok(ir)` **and**
    `ir.as_str() == k.as_str()` (spelling identity round-trip).
  A test comment cites RFC 0001 §6 and the `document` Decision Log entry so a
  future editor who adds `document` to the IR enum is forced to revisit this
  assertion.

Behavioural cross-check (proves the *emitted* IR only uses vocabulary kinds,
catching tree-sitter/markdown literal drift feeding `IrRegion.kind`):

- `extracted_ir_regions_use_only_the_shared_vocabulary`: parametrized over the
  Python and Rust shared fixtures (reuse `shared_python_source` /
  `shared_rust_source` and/or the `stilyagi-test-support` fixture constants used
  in `ir_identity.rs`). For each, call the extract entry point
  (`stilyagi_extract::extract_document(&source, syntax)`), then obtain the IR
  via the `Option`-returning accessor exactly as `ir_identity.rs:192` does —
  `let ir = document.ir().expect("expected IR payload");` — and iterate
  `ir.regions`. Assert every `region.kind` satisfies
  `stilyagi_ir::RegionKind::try_from(region.kind.as_str()).is_ok()`. Also assert
  `!ir.regions.is_empty()` (guard against a vacuously-true pass, mirroring the
  existing `assert!(!ir.regions.is_empty())` in `ir_identity.rs`).

Coverage-gap fix (Surprises): extend
`crates/stilyagi-extract/tests/extract/spelling_display.rs` so the five
region-kind case tables also cover `RustDocComment`. The `ExpectedSpelling`
enum **already** carries a `RustDocComment` arm mapping to `"rust_doc_comment"`
(`spelling_display.rs:14,25`), so **reuse it directly — do not add a new
`RustDocCommentRegion` arm.** Add exactly these `#[case]`s:

- `region_kind_as_str_returns_the_expected_spelling`: add
  `#[case(RegionKind::RustDocComment, ExpectedSpelling::RustDocComment)]`.
- `region_kind_try_from_accepts_the_expected_spelling`: add
  `#[case("rust_doc_comment", RegionKind::RustDocComment)]`.
- `region_kind_display_matches_as_str`: add
  `#[case(RegionKind::RustDocComment, ExpectedSpelling::RustDocComment)]`.
- `region_kind_as_str_round_trips_through_try_from`: add
  `#[case(RegionKind::RustDocComment)]`.
- `region_kind_try_from_round_trips_through_as_str`: add
  `#[case("rust_doc_comment")]`.

Keep the en-GB, existing naming style.

Property-test decision: an enumerated cross-check over the closed `ALL` set is
strictly exhaustive, so a `proptest`/Hypothesis-style generator adds no
coverage here. Load `rust-verification` only to confirm this and record the
conclusion; do **not** add a property test purely for form.

Red evidence (mutate-observe-revert): (a) temporarily edit the hand-written
`"python_docstring"` literal in `crates/stilyagi-tree-sitter/src/python/mod.rs`
to `"python_doc"`, run `make test`, observe
`extracted_ir_regions_use_only_the_shared_vocabulary` fail for the Python
fixture, then revert; (b) temporarily change extract `RegionKind::Document`'s
spelling to a real IR spelling such as `"paragraph"`, run `make test`, observe
`every_shared_bridge_kind_is_an_ir_kind` fail (the `Document`-must-be-Err arm),
then revert. Record both transcripts.

Validation: `make check-fmt` then `make typecheck` then `make lint` then
`make test`. Commit: `Cross-check extract region kinds against IR vocabulary`.

### Work item 3 (recommended hardening) — remove the hand-written literals in `stilyagi-tree-sitter`

Implements: roadmap 6.4.1 success criterion ("cannot silently diverge on region
names or meanings") at the IR-producing source; RFC 0001 §6.

Docs to read first: RFC 0001 §6; the Work item 2 Decision Log scope entry.
Skills to load: `rust-router` → `rust-types-and-apis`; `leta` (confirm the two
call sites and that `stilyagi_ir::RegionKind` is importable there — the crate
already `use`s `stilyagi_ir`); `memtrace` `get_impact` on the two literals
before editing.

Edits:

- `crates/stilyagi-tree-sitter/src/python/mod.rs:318`: replace
  `kind: "python_docstring".to_owned(),` with
  `kind: stilyagi_ir::RegionKind::PythonDocstring.as_str().to_owned(),`
  (add `RegionKind` to the existing `use stilyagi_ir::{…}` group).
- `crates/stilyagi-tree-sitter/src/rust/builder.rs:246`: replace
  `kind: "rust_doc_comment".to_owned(),` with
  `kind: stilyagi_ir::RegionKind::RustDocComment.as_str().to_owned(),`
  (extend the existing `use stilyagi_ir::{IrError, IrNode, IrRegion, NodeFlags};`).

No serialized value changes (the spellings are identical), so all existing
tree-sitter, extract, and pyext behavioural tests and golden fixtures continue
to pass unchanged. The Work item 2 behavioural cross-check now has nothing to
catch on this path — that is the point.

Red evidence: this item changes no behaviour; its correctness is that the full
suite stays green *and* Work item 2's behavioural test still passes. As a
belt-and-braces check, confirm `make test` is green before and after.

Validation: `make check-fmt` then `make typecheck` then `make lint` then
`make test`. Commit:
`Source tree-sitter region kinds from the IR vocabulary`.

## Concrete steps

Run everything from the worktree root
`/home/leynos/Projects/stilyagi.worktrees/roadmap-6-4-1`.

1. Confirm the branch: `git branch --show-current` → `roadmap-6-4-1`.
2. Implement Work item 1; run the gate sequence; commit.
3. Implement Work item 2 (including the coverage-gap fix); run the gate
   sequence; commit.
4. Implement Work item 3; run the gate sequence; commit.

For each drift-guard, perform the documented mutate-observe-revert step and
paste the failing-test line into `Surprises & discoveries` before moving on.

Delegate the full gate sequence to the `scrutineer` subagent, which runs the
gates sequentially, tees each to a `/tmp` log, and returns a bounded report.

## Validation and acceptance

Deterministic commit gates, run sequentially (AGENTS.md is authoritative; these
are the named targets — do not assume `make all` aggregates them):

1. `make check-fmt`
2. `make typecheck`
3. `make lint`
4. `make test`

This change touches no Markdown behaviour except this ExecPlan; when committing
Markdown (this file), also run `make markdownlint` and `make nixie` (this plan
has no Mermaid, so `nixie` is a no-op but is run for consistency). Format only
the files you changed: `mdtablefix docs/execplans/roadmap-6-4-1.md` then
`markdownlint-cli2 --fix docs/execplans/roadmap-6-4-1.md`, then gate. Do not run
a repo-global format.

Acceptance (behaviour a human can verify):

- `make test` passes with the new tests present.
- Temporarily renaming the IR spelling of `python_docstring` consistently (in
  `crates/stilyagi-ir/src/region.rs` `as_str` **and** `TryFrom`) makes the
  extract `region_kind_*_round_trips_*` tests in `spelling_display.rs` fail
  (forwarded `as_str` vs extract's still hand-written `TryFrom`);
  `shared_bridge_spelling_comes_from_ir` keeps passing because the forward moves
  both sides of its equality together. Un-forwarding extract `as_str` (a
  divergent literal in its `Some(_)` arm) is what makes
  `shared_bridge_spelling_comes_from_ir` fail. Reverting either restores green.
- Temporarily editing the `"python_docstring"` literal in
  `crates/stilyagi-tree-sitter/src/python/mod.rs` (before Work item 3) makes
  `extracted_ir_regions_use_only_the_shared_vocabulary` fail; reverting restores
  green. After Work item 3 that literal no longer exists, so the drift cannot be
  written in the first place.
- Temporarily giving extract `RegionKind::Document` an IR spelling makes
  `every_shared_bridge_kind_is_an_ir_kind` fail.

Quality criteria for "done":

- Tests: all four gates pass at HEAD; the new cross-check and behavioural tests
  are present and demonstrated to catch drift.
- Lint/typecheck: `make lint` and `make typecheck` clean.
- No public spelling or serialized value changed; golden fixtures unchanged.

## Idempotence and recovery

Each work item is a separate commit; re-running a gate is safe and read-only
except for `--fix` formatters, which are idempotent on already-clean files. The
mutate-observe-revert demonstrations must be reverted (`git checkout --` the
touched file) before committing the work item; never commit a mutation.

## Interfaces and dependencies

Prescriptive end state:

- In `crates/stilyagi-extract/src/lib.rs`, `stilyagi_extract::RegionKind` gains:

  ```rust
  impl RegionKind {
      pub const ALL: &'static [Self];
      pub const fn ir_region_kind(self) -> Option<stilyagi_ir::RegionKind>;
      // as_str now forwards shared spellings to stilyagi_ir::RegionKind::as_str
  }
  ```

- No change to `stilyagi_ir::RegionKind`'s public surface (it is already the
  source of truth: `pub const fn as_str`, `pub const ALL`, `TryFrom<&str>`).
- `stilyagi-extract` and `stilyagi-tree-sitter` continue to depend on
  `stilyagi-ir` (path deps already present); no new dependencies.

## Signposts (docs and skills relied upon while planning)

- Docs: `docs/rfcs/0001-stilyagi-intermediate-representation.md` §6 (region
  vocabulary), `docs/adr-005-markdown-region-vocabulary-scope.md`,
  `docs/adr-003-v1-contract-scope.md`, `docs/stilyagi-design.md` §7.1,
  `AGENTS.md` (gates + testing rules).
- Skills: `execplans` (this document's structure), `rust-router` (and the
  `rust-types-and-apis`, `rust-unit-testing`, `rust-verification` skills it
  routes to), `leta` (symbol navigation), `sem` (history), `scrutineer` (gate
  running).

## Revision note

Round 1 (2026-07-05). Initial draft: established the ir↔extract
single-source-of-truth forwarding plus an exhaustive and behavioural
cross-checking test, with an optional third work item that removes the
hand-written region-kind literals in `stilyagi-tree-sitter`.

Round 2 (2026-07-05). Resolved the two blocking defects raised in
`roadmap-6-4-1-review-r1.md`:

- **B1 (test never runs):** corrected Work item 2's test registration. This
  crate has no `tests/extract/mod.rs`; integration tests are registered in
  `crates/stilyagi-extract/tests/extract_integration.rs` via
  `#[path = "extract/<file>.rs"] mod <name>;`. The plan now specifies the exact
  `#[path = "extract/region_vocabulary.rs"] mod region_vocabulary;` entry and
  warns that an unregistered file is silently uncompiled. Verified by inspecting
  `extract_integration.rs` and confirming no `mod.rs` exists.
- **B2 (Red evidence for a guard that cannot fail under the stated mutation):**
  corrected Work item 1's mutate-observe-revert step. A *consistent* IR rename
  forwards through `as_str` to both sides of `shared_bridge_spelling_comes_from_ir`'s
  equality, so that guard keeps passing; only the extract round-trip tests fail.
  The plan now attributes the IR-rename mutation to the round-trip tests and adds
  a distinct un-forwarding mutation (divergent literal in extract `as_str`) that
  actually makes `shared_bridge_spelling_comes_from_ir` bite. The Acceptance
  section was corrected to match.

Also folded in both advisories: Work item 2's behavioural test now uses the
`Option`-returning `document.ir().expect(...)` accessor (mirroring
`ir_identity.rs:192`), and the coverage-gap fix reuses the existing
`ExpectedSpelling::RustDocComment` arm (no new `RustDocCommentRegion` arm) with
the exact `#[case]`s enumerated. No implementation had begun at that point;
Status was DRAFT pending re-review.
