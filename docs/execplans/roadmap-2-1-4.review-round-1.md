# Logisphere design review — roadmap 2.1.4, round 1

Verdict: 🔄 Revise. One blocking defect; the design (additive optional
`range_role` field + `1.1.0` minor bump) is sound, but the plan's blast-radius
analysis for the schema-version bump is materially wrong and would leave a red
gate mid-run.

## 🔴 Blocking — incomplete `schema_version` snapshot blast radius

The plan asserts the `1.0.0 → 1.1.0` bump only churns the extract rust/python
golden snapshots, and states outright that "the markdown golden snapshot does
not embed it … so it is unaffected" (Context lines 194-196; Risks lines 78-85;
Surprises lines 113-125; work item 1 step 4, lines 273-276).

That is false for the wider workspace. `schema_version: "1.0.0"` is embedded in
full-document IR dumps in:

- **12 `crates/stilyagi-markdown/src/snapshots/*.snap`** files (blockquotes,
  headings, table, paragraph_inline_markup, paragraph_soft_break,
  paragraph_soft_break_crlf, shared_markdown_ir_json_round_trips,
  yaml_frontmatter, suppression_directives, frontmatter, links_and_images,
  lists) — each line 6 `"schema_version": "1.0.0"`.
- **`crates/stilyagi-test-support/tests/snapshots/`
  `round_trip_helpers__golden_python_ir_fixture_serializes_the_shared_fixture.snap`
  ** — line 6 `"schema_version": "1.0.0"`. Not referenced anywhere in the plan.

(The `"version": "1.0.0"` at line 19 of those snapshots is the separate
`MARKDOWN_RS_VERSION` producer constant — it does not move. Only line 6 churns.)

Work item 1's regeneration step runs only
`cargo test -p stilyagi-extract --test extract_integration` +
`cargo insta accept`, so these 13 further snapshots stay stale. `make test`
therefore fails at the HEAD of work item 1, breaking the plan's own invariant
that "each work item ends green and is independently committable" and the
deterministic `make test` gate.

Note: the "Suppression syntax" claim in Surprises (that the extract shared
markdown fixture carries no canonical suppression) is itself correct — the
defect is that the plan generalizes "no range-suppression *content* churn" into
"no markdown snapshot churn at all", ignoring the `schema_version` field that
every full-document markdown snapshot embeds.

Fix required:

1. Expand work item 1 to regenerate every workspace snapshot embedding
   `schema_version` — the `stilyagi-markdown` crate snapshots
   (`cargo test -p stilyagi-markdown`) and the `stilyagi-test-support` snapshot
   (`cargo test -p stilyagi-test-support`) — not just the extract integration
   snapshots. State that the only per-file delta must be the `schema_version`
   string.
2. Correct the false "markdown golden snapshot … unaffected" / "small,
   enumerable blast radius" statements in Context, Risks, and Surprises to
   reflect the true ~18-snapshot churn (5 extract + 12 markdown + 1
   test-support).
3. Re-check the Tolerances scope cap wording — it already excludes regenerated
   snapshots from the line budget, so no change to the cap is needed, but the
   file count of *edited* snapshots should be acknowledged.

## 🟡 Advisory

- **Design §7.1 mislabel.** Work item 4 step 2 and Context cite
  `docs/stilyagi-design.md` §7.1 "Suppression syntax". The "Suppression syntax"
  heading is a `####` at line 603; §7.1 ("Intermediate representation") is a
  different section at line 786. The load-bearing sentence ("Suppression state
  must be visible in IR and debug output", line 625) is real, but an
  implementer following "§7.1" could edit the wrong section. Cite the
  "Suppression syntax" heading by name/line, drop the "§7.1" label.
- **RFC example JSON not updated.** RFC 0001 shows `"schema_version": "1.0.0"`
  in illustrative blocks (lines 107, 373). Work item 4 updates §8/§9 prose but
  does not mention these examples; leaving them at `1.0.0` while the emitter
  advertises `1.1.0` is a doc inconsistency. Either bump them or add a note
  that they are historical illustrations.

## Verified as accurate (no action)

- `verb_kind` collapses `Disable`/`Enable` to `SuppressionKind::Range`
  (`crates/stilyagi-markdown/src/suppression.rs:77-83`). ✓
- `DirectiveVerb` has exactly four variants; `verb_range_role` match is
  exhaustive. ✓
- Two `IrSuppression` construction sites (`stilyagi-markdown/src/lib.rs:235`,
  `stilyagi-ir/src/tests/suppression.rs:9`). ✓
- `SCHEMA_VERSION = "1.0.0"` at `stilyagi-ir/src/lib.rs:24`. ✓
- Three version assertions: `stilyagi-ir/src/tests/mod.rs:126`,
  `stilyagi-markdown/src/tests/ir_consistency.rs:34`,
  `stilyagi-pyext/src/tests/mod.rs:38` — all covered by the plan. ✓
- RFC 0001 §8 field list and §9 compatibility rules match the quotes; additive
  optional field is contract-legal. ✓
- The RFC-shape round-trip test uses exact-object equality, so
  `skip_serializing_if` correctness is genuinely guarded. ✓
- Gate set (`make check-fmt`, `make typecheck`, `make lint`, `make test`;
  markdown adds `make markdownlint`, `make nixie`) matches AGENTS.md. Plan
  correctly follows the touched-files-only markdown format rule over the AGENTS
  default `make fmt`. ✓
- No standalone red-test commit is mandated; red/green happens within each work
  item. ✓ Deterministic/judgemental boundary and `SuppressionKind` string
  stability are respected. ✓
