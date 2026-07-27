# Logisphere design review — roadmap 2.1.4 ExecPlan (Round 2)

Status: **CHANGES REQUESTED** (plan Status remains DRAFT) Reviewer: Logisphere
crew (adversarial), 2026-07-05.

## Verdict

Not approved. One blocking defect — a symmetric repeat of the Round-1 defect,
in work item 2 instead of work item 1: the plan's snapshot blast-radius is
still incomplete, this time for *range-suppression content* rather than the
`schema_version` string.

## Blocking defect — missed content churn in `suppression_directives.snap`

The Surprises section (lines 134-135) asserts:

> Impact: no existing golden snapshot needs new range-suppression *content*
> (no snapshot gains or changes a `suppressions` entry).

This is **false**. Verified against the worktree:

- `grep -rln '"kind": "range"'` over `crates` returns exactly one golden
  snapshot: `crates/stilyagi-markdown/src/snapshots/`
  `stilyagi_markdown__tests__suppression_directives.snap`.
- That snapshot contains two `range` suppressions, `s1` and `s2` (codes `STY`,
  origins `n7`/`n10`) — i.e. a canonical `disable STY` / `enable STY` pair.
- It is produced by the parametrized test case
  `crates/stilyagi-markdown/src/tests.rs:122` (`suppression_directives`, fixture
  `tests/fixtures/corpus/markdown/valid/suppression-directives.md.fixture`),
  which runs `markdown_ir_document` → the frontend construction site at
  `crates/stilyagi-markdown/src/lib.rs:235` → `to_canonical_json`.

Consequently, when **work item 2** replaces the `range_role: None` placeholder
with `range_role: verb_range_role(parsed.verb)`, entries `s1` and `s2` in this
snapshot gain `"range_role": "open"` and `"range_role": "close"`. The snapshot
changes, and `make test` **fails at work item 2's HEAD** unless it is
regenerated and accepted.

Work item 2 does not account for this:

- Its "Tests this work item adds/updates" list omits
  `suppression_directives.snap`.
- Step 2/3 give no instruction to regenerate or review it; step 3 only says
  "Run the full gate set. Confirm the property and inline-snapshot tests pass."
- Worse, the plan's own Tolerances rule ("A snapshot diff that changes any
  other line is out of tolerance and must be inspected before acceptance") is
  scoped to the work-item-1 `schema_version` churn. An implementer who sees a
  *new* `range_role` key appear during work item 2 could read it as an
  out-of-tolerance surprise and escalate unnecessarily — the opposite of the
  intended flow.

This is exactly the class of error Round 1 flagged (a narrow fixture fact —
"the *shared* markdown fixture uses the non-canonical marker and emits no
suppressions" — over-generalized into "no existing golden snapshot changes").
The shared-fixture observation is correct; its generalization to *all* golden
snapshots is not.

### Required fix

1. Correct the Surprises claim: acknowledge that
   `stilyagi_markdown__tests__suppression_directives.snap` gains a `range_role`
   key on its two `range` entries (`s1`, `s2`) in work item 2 — this is content
   churn, not merely the schema_version string.
2. Add to work item 2 an explicit regeneration + review step:
   `cargo test -p stilyagi-markdown` then review that the *only* deltas to
   `suppression_directives.snap` are `"range_role": "open"` on the `disable`
   entry and `"range_role": "close"` on the `enable` entry (both in the
   `suppressions` array); then `cargo insta accept`.
3. List `suppression_directives.snap` in work item 2's "Tests this work item
   adds/updates" section.
4. Note that this is the *only* existing golden snapshot with range content
   (verified: one file), so the work-item-2 content blast radius is exactly one
   snapshot, two lines.

## Verified and sound (no action)

- 18 `schema_version` snapshot files: confirmed by
  `grep -rl '"schema_version": "1.0.0"' crates` (5 extract + 12 markdown + 1
  test-support). Work item 1's enumeration is exact.
- Construction sites: exactly two (`stilyagi-markdown/src/lib.rs:235`,
  `stilyagi-ir/src/tests/suppression.rs:9`) — confirmed.
- Version assertions: `stilyagi-ir/src/lib.rs:24` (SCHEMA_VERSION),
  `stilyagi-ir/src/tests/mod.rs:126`,
  `stilyagi-markdown/src/tests/ir_consistency.rs:34`,
  `stilyagi-pyext/src/tests/mod.rs:38` — all present as cited.
- `IrSuppression` fields (`id`, `kind`, `codes`, `span`, `origin`) and
  `SuppressionKind` snake_case enum — confirmed in `diagnostics.rs`. Additive
  `Option<RangeRole>` with
  `#[serde(default, skip_serializing_if = "Option::is_none")]` preserves the
  serialized shape of non-range suppressions.
- RFC 0001 §8 (line 327, field list) and §9 (line 346, compatibility rules:
  "Optional fields MAY be added in minor versions"; "Producers MUST NOT change
  field meaning within a major version") support the additive-field + `1.1.0`
  minor-bump mechanism. Illustrative `schema_version: "1.0.0"` blocks at RFC
  lines 107 and 373 — confirmed; work item 4 correctly reconciles them.
- Design doc "Suppression syntax" heading at line 603 and the load-bearing
  sentence at line 625 ("Suppression state must be visible in IR and debug
  output"), distinct from "### 7.1 Intermediate representation" at line 786 —
  all confirmed.
- No standalone red-test commit is mandated; each work item ends green and is
  independently committable. Gate set matches AGENTS.md (`make check-fmt`,
  `typecheck`, `lint`, `test`; plus `markdownlint`/`nixie` for the docs item).
- Deterministic/judgemental boundary untouched: this is a pure IR-contract
  enrichment in the frontend; no rule verdict logic is added.

## Advisory (non-blocking)

- Field position: the plan does not state where `range_role` sits within
  `IrSuppression`. Because `to_canonical_json` preserves struct field order,
  appending it after `origin` is the least surprising choice and keeps the new
  key last on range entries. Worth stating explicitly so the regenerated
  `suppression_directives.snap` diff is predictable during review.
