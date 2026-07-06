# Preserve range-suppression polarity in the IR

This ExecPlan (execution plan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work
proceeds.

Status: COMPLETE

## Purpose / big picture

Roadmap task 2.1.4 (`docs/roadmap.md`) requires that range suppressions be
*fully resolvable from the IR alone*. Today the Markdown frontend collapses both
range directives — `stilyagi: disable CODE` (opens a suppressed span) and
`stilyagi: enable CODE` (closes it) — onto the single IR value
`SuppressionKind::Range` (see `crates/stilyagi-ir/src/diagnostics.rs` and
`crates/stilyagi-markdown/src/suppression.rs::verb_kind`). A downstream stage
that wants to pair an opening directive with its closing directive has no way to
tell the two apart without re-reading the comment bytes named by each
suppression's `span`. That is exactly the "re-scan comment bytes" the roadmap
task forbids.

After this change, every range suppression in the IR carries an explicit
open/close role. A reader can walk `document.suppressions`, match each `disable`
against a later `enable` for the same code(s), and resolve every suppressed span
without touching the source text again. Success is observable three ways:

1. `IrSuppression` for a `disable` directive reports the new role `open`; for an
   `enable` directive it reports `close`; for `inline`/`file`/`config`
   suppressions the role is absent.
2. The canonical IR JSON (`IrDocument::to_canonical_json`, the form `dump-ir` and
   golden fixtures use) shows `"range_role": "open"` / `"close"` on range
   suppressions and omits the field elsewhere.
3. `cargo test --workspace` passes, with new unit, property, and behaviour-driven
   development (BDD) tests that fail before the change and pass after.

## Constraints

- Work occurs exclusively in the worktree
  `/home/leynos/Projects/stilyagi.worktrees/roadmap-2-1-4`. Do not edit the root
  or control worktree.
- The suppression contract lives in RFC 0001 §8 (`docs/rfcs/`
  `0001-stilyagi-intermediate-representation.md`). The new field must be an
  **optional** addition: existing `inline`, `file`, and `config` suppressions
  MUST serialize byte-for-byte as they do today (RFC 0001 §9 compatibility
  rules: "Producers MUST NOT change field meaning within a major version";
  "Optional fields MAY be added in minor versions").
- `SuppressionKind` string values (`inline`, `range`, `file`, `config`) MUST NOT
  change; RFC 0001 §8 enumerates them and the golden-shape test in
  `crates/stilyagi-ir/src/tests/suppression.rs` pins them. Polarity is carried by
  a *new* field, not by splitting the `range` variant.
- en-GB Oxford spelling ("-ize"/"-yse"/"-our") in all prose, comments, and
  commit messages (AGENTS.md; `docs/documentation-style-guide.md`).
- Rust style per AGENTS.md: module-level `//!` docs, Rustdoc `///` on public
  items, no silenced Clippy lints, `#[derive]`/attributes after doc comments,
  domain enums over primitive "integer soup", `.expect(...)` (not `.unwrap()`)
  in tests.
- Every commit must pass the full gate set at HEAD (see Validation).

## Tolerances (exception triggers)

- Scope: if implementation requires changing more than 8 non-test source files
  or more than ~150 net lines (excluding regenerated snapshots), stop and
  escalate. Note: the `schema_version` bump mechanically edits **18 regenerated
  snapshot files** (5 extract + 12 markdown + 1 test-support); these are
  excluded from the net-line budget above, but the reviewer of work item 1 must
  expect ~18 `.snap` files in the diff whose sole per-file delta is the line-6
  `schema_version` string. A snapshot diff that changes any other line is out
  of tolerance and must be inspected before acceptance.
- Interface: the only public API change permitted is the additive `range_role`
  field plus the new `RangeRole` enum on `stilyagi-ir`. If any other public
  signature must change, stop and escalate.
- Dependencies: if any new external crate is required, stop and escalate (none
  is expected; `serde` already provides `skip_serializing_if`).
- Contract: if a design reviewer or maintainer rejects bumping
  `SCHEMA_VERSION` to `1.1.0`, stop and escalate rather than adding the field
  under `1.0.0`.
- Iterations: if a gate still fails after 3 focused fix attempts, stop and
  escalate with the cited log.

## Risks

- Risk: Bumping `SCHEMA_VERSION` churns golden snapshots and version
  assertions across three crates (`stilyagi-extract`, `stilyagi-markdown`,
  `stilyagi-test-support`) plus the three version assertions in
  `stilyagi-ir`/`stilyagi-markdown`/`stilyagi-pyext`. The snapshot churn is
  **18 files** (5 extract + 12 markdown + 1 test-support), not just the extract
  golden snapshots.
  Severity: low. Likelihood: high.
  Mitigation: the churn is mechanical (regenerate `insta` snapshots across all
  three crates, update three string assertions). Fold it into the first work
  item so the contract is never dishonest, and review the regenerated snapshots
  to confirm the *only* per-file delta is the line-6 `schema_version` string.
  Regenerating only the extract snapshots would leave the twelve markdown and
  one test-support snapshots stale and fail `make test` at the HEAD of work
  item 1, so work item 1 must run `cargo test -p stilyagi-markdown` and
  `cargo test -p stilyagi-test-support` as well as the extract integration test.
- Risk: `serde` `skip_serializing_if` is mis-applied and a `null` `range_role`
  leaks into non-range suppressions, breaking the RFC-shape round-trip test.
  Severity: medium. Likelihood: low.
  Mitigation: the existing test
  `suppression_serialises_and_deserialises_with_the_rfc_shape` acts as a guard;
  a new test asserts the field is *absent* (not `null`) for inline
  suppressions.
- Risk: A future consumer treats a missing `range_role` on a `range`
  suppression as valid.
  Severity: low. Likelihood: low.
  Mitigation: the Markdown frontend always sets `range_role` for range
  directives; a unit test pins that every `range` suppression it emits carries
  `Some(role)`. Document the invariant in RFC 0001 §8.

## Progress

- [x] Work item 1: Introduce the versioned `range_role` contract field on
  `IrSuppression` (type + optional serde field + schema bump), all inline/file
  suppressions unchanged. Delivered as `RangeRole { Open, Close }`, an
  optional `range_role` on `IrSuppression`, `SCHEMA_VERSION = "1.1.0"`, and
  schema/version assertion updates in Rust and Python contract tests.
- [x] Work item 2: Populate range polarity in the Markdown frontend
  (`verb_range_role`, wired into `suppressions_from_candidates`). Implemented
  with polarity tests, a pair-only inline snapshot, and the regenerated
  canonical markdown suppression snapshot.
- [x] Work item 3: Add BDD behavioural coverage for a `disable`/`enable` pair.
- [x] Work item 4: Update the design/contract documentation (RFC 0001, the
  design "Suppression syntax" section, developers' guide).

  Updated RFC 0001 to document `range_role` on range suppressions, clarify the
  `disable` → `open` and `enable` → `close` mapping, and refresh the
  illustrative schema examples to `1.1.0`. Added matching notes to the design
  and developers' guide so downstream stages rely on the IR polarity instead of
  re-scanning comment bytes.

## Surprises & discoveries

- Observation: The **shared extract** Markdown golden fixture
  (`tests/fixtures/corpus/markdown/valid/heading-table-link-suppression.md`,
  consumed by the `stilyagi-extract` integration snapshot) uses the
  *non-canonical* marker `stilyagi-disable-next-line`, which the parser
  deliberately ignores, so it emits **no** suppressions.
  Evidence: `crates/stilyagi-extract/tests/extract/snapshots/`
  `extract_integration__ir_identity__extraction_tests__shared_markdown_fixture_has_a_golden_ir_snapshot.snap`
  contains only that literal comment text and an empty suppression set;
  `crates/stilyagi-markdown/src/tests/suppression.rs::placeholder_non_canonical_marker_is_ignored`
  confirms the behaviour.
  Impact: this **shared extract fixture only** needs no new range-suppression
  *content*; the extract integration snapshot never gains a `suppressions`
  entry from work item 2. **This scoping is deliberately narrow.** It does NOT
  generalize to the markdown crate's own snapshots — see the next observation,
  which corrects a load-bearing scope error.
- Observation (BLOCKING correction, round 3): the claim "no existing golden
  snapshot needs new range-suppression content" is **false** for the markdown
  crate's own fixture. `tests/fixtures/corpus/markdown/valid/`
  `suppression-directives.md.fixture` uses the **canonical** `disable STY` /
  `enable STY` pair (fixture lines 7 and 9) and emits **two** `"kind": "range"`
  suppressions. Its golden snapshot
  `crates/stilyagi-markdown/src/snapshots/`
  `stilyagi_markdown__tests__suppression_directives.snap` records them as `s1`
  (snapshot line 405) and `s2` (line 417), and the case is driven by
  `hardening_fixture_ir_json_round_trips_without_span_drift`
  (`crates/stilyagi-markdown/src/tests.rs:121-125`), which both asserts
  `insta::assert_snapshot!` on the canonical JSON (`tests.rs:150`) AND asserts
  `assert_eq!(parsed, document)` (`tests.rs:146`).
  Evidence: fixture and snapshot read directly in the worktree, 2026-07-05
  (round-3 planning); `grep -n '"kind": "range"'` on the snapshot returns lines
  405 and 417.
  Impact: **work item 2** (which wires `range_role: verb_range_role(parsed.verb)`
  at the construction site) makes `s1` gain `"range_role": "open"` and `s2` gain
  `"range_role": "close"`. That is a *legitimate, expected* content delta — the
  snapshot and the `assert_eq!` round-trip would fail at work item 2's HEAD
  unless the snapshot is regenerated. Work item 2 therefore explicitly
  regenerates and re-accepts this ONE snapshot (see work item 2, Stage C/D), and
  its expected delta is **exactly two new `range_role` lines** (one on `s1`, one
  on `s2`) and nothing else. This is content churn, distinct from the
  `schema_version` field churn covered in the next observation.
- Observation (correction to the round-1 draft): the `schema_version` bump
  churns **18 snapshot files**, not just the extract golden snapshots. The
  round-1 draft wrongly generalized "no range-suppression content churn" into
  "no markdown snapshot churn at all". In fact every full-document IR dump —
  including the twelve `crates/stilyagi-markdown/src/snapshots/*.snap` and the
  one `crates/stilyagi-test-support/tests/snapshots/round_trip_helpers__…​.snap`
  — embeds `"schema_version": "1.0.0"` at line 6 and must be regenerated.
  Evidence: `grep -rl '"schema_version": "1.0.0"' crates` returns 18 files
  (5 extract + 12 markdown + 1 test-support).
  Impact: work item 1 must regenerate snapshots in all three crates
  (`stilyagi-extract`, `stilyagi-markdown`, `stilyagi-test-support`), not just
  the extract integration test, or `make test` fails at its HEAD. The blast
  radius is enumerable and mechanical (only the line-6 string moves per file),
  but it is 18 edited snapshot files, not "small".
- Observation: Only two sites construct `IrSuppression`: the frontend at
  `crates/stilyagi-markdown/src/lib.rs:235` and the shape test at
  `crates/stilyagi-ir/src/tests/suppression.rs:9`.
  Evidence: `grep -rn "IrSuppression {" crates`.
  Impact: the *type change* (adding the field) has a small, enumerable
  construction-site blast radius (two sites). The *snapshot* blast radius from
  the co-located `schema_version` bump is larger (18 files) and is handled
  separately in work item 1.
- Observation: the new BDD scenario for the `disable`/`enable` pair passed on
  the first run against the already-wired `stilyagi-extract` path. No
  production change was required for work item 3 because work items 1 and 2 had
  already carried polarity through the Markdown frontend into the extracted IR.
  Evidence: `cargo test --manifest-path Cargo.toml --workspace --all-features --doc`
  and the `pytest`/nextest portion of `make test` both reported the new
  `markdown_suppression_bdd::a_range_disable_and_enable_pair_record_open_and_close_polarity`
  scenario as passing.
- Observation: the `schema_version` contract also has top-level Python
  assertions and JSON snapshots in `tests/` that must move with the IR version
  bump; leaving them at `1.0.0` causes `make test` to fail even after the Rust
  workspace passes.
  Evidence: `tests/test_package_skeleton_units.py` and the two
  `tests/__snapshots__/*schema_version*.json` fixtures.
  Impact: work item 1 includes the repo-level Python contract assertions that
  exercise the same IR payload, not just the crate-local Rust tests.

## Decision log

- Decision: Carry polarity in a new optional field `range_role:
  Option<RangeRole>` (`RangeRole::{Open, Close}`), not by splitting
  `SuppressionKind::Range` into `RangeOpen`/`RangeClose`.
  Rationale: RFC 0001 §8 enumerates the four `kind` values as the frozen
  contract and §9 forbids changing field meaning within a major version while
  permitting *additive optional* fields in a minor version. A type-safe enum
  beats a boolean (AGENTS.md: model domain values, avoid "integer soup") and
  keeps `kind == range` stable for existing consumers.
  Date/Author: 2026-07-05, planning agent.
- Decision: Bump `SCHEMA_VERSION` from `1.0.0` to `1.1.0` in the same work item
  that adds the field.
  Rationale: RFC 0001 §9 says optional fields "MAY be added in minor versions".
  Bumping in lock-step keeps the emitted `schema_version` honest at every commit
  rather than emitting a new field under a version that does not advertise it.
  Date/Author: 2026-07-05, planning agent.
- Decision: Serialize the field with `#[serde(default,
  skip_serializing_if = "Option::is_none")]`.
  Rationale: preserves the exact serialized shape of inline/file/config
  suppressions (guarding the RFC-shape round-trip test and every golden
  snapshot that embeds a non-range suppression) and lets older payloads
  deserialize unchanged.
  Date/Author: 2026-07-05, planning agent.

## Outcomes & retrospective

Work item 2 is complete: the Markdown frontend now sets `range_role` from the
parsed verb, the range-polarity unit and property coverage are in place, and
the pair-only inline snapshot plus the canonical suppression fixture snapshot
both reflect the new field. The only follow-up structural adjustment was
splitting the new range-polarity tests into a sibling module so Whitaker's
module-length limit stayed green.

Work item 4 is complete: RFC 0001 now records `range_role` as the additive
optional range-suppression polarity field introduced in schema version
`1.1.0`, the design's suppression syntax section explains that downstream
stages can resolve boundaries without re-reading comment bytes, and the
developers' guide points rule authors at the IR field rather than the raw
comments.

## Context and orientation

Stilyagi is a Rust workspace. The pieces relevant to this task:

- `crates/stilyagi-ir/src/diagnostics.rs` — defines `SuppressionKind` (the
  `inline`/`range`/`file`/`config` enum) and `IrSuppression` (the serializable
  suppression record: `id`, `kind`, `codes`, `span`, `origin`). This is the IR
  contract type that carries polarity after this change.
- `crates/stilyagi-ir/src/lib.rs` — re-exports `IrSuppression`, `SuppressionKind`
  and defines `pub const SCHEMA_VERSION: &str = "1.0.0"`.
- `crates/stilyagi-ir/src/document.rs` — `IrDocument`, its `schema_version`
  field, and `to_canonical_json` (deterministic pretty JSON via
  `serde_json::to_string_pretty`, preserving struct field order).
- `crates/stilyagi-ir/src/tests/suppression.rs` — the golden-shape serde test.
- `crates/stilyagi-ir/src/tests/mod.rs:126` — asserts `schema_version == "1.0.0"`.
- `crates/stilyagi-markdown/src/suppression.rs` — parses HTML-comment
  directives. `DirectiveVerb::{IgnoreNext, Disable, Enable, IgnoreFile}` is the
  parsed verb; `verb_kind` maps a verb onto `SuppressionKind`, currently
  collapsing `Disable` and `Enable` both to `Range`.
- `crates/stilyagi-markdown/src/lib.rs:208` — `suppressions_from_candidates`
  builds each `IrSuppression` from a parsed directive (the construction site at
  line 235).
- `crates/stilyagi-markdown/src/tests/suppression.rs` — unit and `proptest`
  coverage for directive parsing and IR wiring.
- `crates/stilyagi-markdown/src/tests/ir_consistency.rs:34` — asserts
  `schema_version == "1.0.0"`.
- `crates/stilyagi-pyext/src/tests/mod.rs:37` — asserts `schema_version` is
  `"1.0.0"` across the PyO3 boundary.
- `crates/stilyagi-extract/tests/features/markdown_suppression.feature` and
  `crates/stilyagi-extract/tests/extract/markdown_suppression_bdd.rs` — the BDD
  feature and step definitions (rstest-bdd).
- `crates/stilyagi-extract/tests/extract/snapshots/*.snap` — golden IR snapshots.
  Five of these (the rust and python full-document dumps) embed
  `schema_version` at line 6 and must be regenerated after the bump. The
  extract **markdown** golden snapshot
  (`..._shared_markdown_fixture_has_a_golden_ir_snapshot.snap`) is the only
  extract IR snapshot that does *not* embed `schema_version`, and it carries no
  canonical suppression, so it is unaffected by the bump — but this is a narrow
  exception, not a general rule (see below).
- The `schema_version` bump churns snapshots **beyond** the extract crate.
  `grep -rl '"schema_version": "1.0.0"' crates` enumerates the full set:
  **five** `crates/stilyagi-extract/tests/extract/snapshots/*.snap`
  (malformed_python, malformed_rust, nested_rust, shared_python, shared_rust);
  **twelve** `crates/stilyagi-markdown/src/snapshots/*.snap` (blockquotes,
  frontmatter, headings, links_and_images, lists, paragraph_inline_markup,
  paragraph_soft_break, paragraph_soft_break_crlf,
  shared_markdown_ir_json_round_trips_without_span_drift, suppression_directives,
  table, yaml_frontmatter); and **one**
  `crates/stilyagi-test-support/tests/snapshots/`
  `round_trip_helpers__golden_python_ir_fixture_serializes_the_shared_fixture.snap`.
  That is **18 snapshot files** in total (5 + 12 + 1). Each embeds
  `schema_version` at line 6 and must be regenerated in work item 1. The
  separate `"version": "1.0.0"` (line 19 of the markdown snapshots) is the
  `MARKDOWN_RS_VERSION` producer constant — it does **not** move; only the
  line-6 `schema_version` string changes per file.

Terms:

- *Range suppression*: a pair of directives (`disable CODE`, later
  `enable CODE`) that brackets a span of source in which the named rule codes are
  suppressed.
- *Polarity / role*: whether a single range directive **opens** (`disable`) or
  **closes** (`enable`) a suppressed span.
- *Canonical IR JSON*: the deterministic JSON produced by
  `IrDocument::to_canonical_json`; the debug/golden contract (RFC 0001 §9).

### Documentation to read

- `docs/roadmap.md` task 2.1.4 (and its parent step 2.1).
- `docs/rfcs/0001-stilyagi-intermediate-representation.md` §8 (suppression
  fields) and §9 (serialization and compatibility).
- `docs/stilyagi-design.md`, the "Suppression syntax" heading (`####` at
  line 603; the load-bearing sentence "Suppression state must be visible in IR
  and debug output" is at line 625). Note: this is a distinct section from
  "§7.1 Intermediate representation" (heading at line 786) — cite the heading by
  name, not by a "§7.1" label, to avoid editing the wrong section.
- `AGENTS.md` — Rust guidance, testing rules, Markdown guidance.
- `docs/developers-guide.md` — internal-interface documentation conventions.

### Skills to load

- `rust-router` first, then the skills it routes to: `rust-types-and-apis`
  (enum/serde field design), `rust-unit-testing` (rstest, insta snapshots),
  `rust-verification` (proptest invariants).
- `execplans` (this document's own conventions).
- `en-gb-oxendict` for all prose and comments.
- `leta` for symbol navigation and reference checks in the worktree.
- `commit-message` when composing each commit.
- `scrutineer` (sub-agent) to run the deterministic commit gates and return a
  bounded report.

## Plan of work

The order is: contract type first (so the field exists and compiles workspace
wide), then behaviour, then behavioural tests, then documentation. Each work
item ends green and is independently committable.

### Work item 1 — Introduce the versioned `range_role` contract field

Implements RFC 0001 §8 (adds a field to the suppression record) and §9
(minor-version bump for an additive optional field).

1. Stage B (red). In `crates/stilyagi-ir/src/tests/suppression.rs`, add tests:
   - `range_role_serialises_open_and_close`: build an `IrSuppression` with
     `kind: SuppressionKind::Range` and `range_role: Some(RangeRole::Open)`;
     assert the JSON contains `"range_role": "open"` and round-trips; repeat for
     `Close` → `"close"`.
   - Extend/keep the existing `..._with_the_rfc_shape` inline test so it also
     asserts that an inline suppression's JSON has **no** `range_role` key
     (guarding `skip_serializing_if`).
   In `crates/stilyagi-ir/src/tests/mod.rs` update the version assertion to
   `"1.1.0"`. These will fail to compile (`RangeRole` and the field do not yet
   exist) — that is the red signal.
2. Stage C (green). In `crates/stilyagi-ir/src/diagnostics.rs`:
   - Add `pub enum RangeRole { Open, Close }` with `#[derive(Debug, Clone, Copy,
     PartialEq, Eq, Serialize, Deserialize)]` and
     `#[serde(rename_all = "snake_case")]`, Rustdoc on the type and each
     variant (`Open` = a `disable` directive that opens a suppressed span;
     `Close` = an `enable` directive that closes it).
   - Add field to `IrSuppression`:
     `#[serde(default, skip_serializing_if = "Option::is_none")]`
     `pub range_role: Option<RangeRole>,` with a Rustdoc comment stating it is
     `Some` only for `SuppressionKind::Range` and records open/close polarity.
   - Re-export `RangeRole` from `crates/stilyagi-ir/src/lib.rs` next to
     `SuppressionKind`.
   - Bump `SCHEMA_VERSION` to `"1.1.0"` in `crates/stilyagi-ir/src/lib.rs`.
3. Keep the workspace compiling: update the two construction sites and the two
   remaining version assertions.
   - `crates/stilyagi-markdown/src/lib.rs:235`: add `range_role: None` (behaviour
     lands in work item 2).
   - `crates/stilyagi-ir/src/tests/suppression.rs:9`: add `range_role: None` to
     the inline fixture.
   - `crates/stilyagi-markdown/src/tests/ir_consistency.rs:34` and
     `crates/stilyagi-pyext/src/tests/mod.rs:38`: change `"1.0.0"` to `"1.1.0"`.
4. Regenerate **every** workspace snapshot that embeds `schema_version` — 18
   files across three crates, not only the extract snapshots. Run the snapshot
   producers in each affected crate, then review and accept:

   ```sh
   cargo test -p stilyagi-extract --test extract_integration
   cargo test -p stilyagi-markdown
   cargo test -p stilyagi-test-support
   cargo insta accept    # or hand-review and commit the .snap updates
   ```

   Before accepting, confirm with `git diff -- '**/*.snap'` that the **only**
   per-file change is the line-6 `schema_version` string moving `1.0.0` →
   `1.1.0` (18 files: 5 extract + 12 markdown + 1 test-support). The line-19
   `"version"` (`MARKDOWN_RS_VERSION`) in the markdown snapshots must **not**
   move. If any snapshot shows any other delta, do not accept — inspect it
   first (it signals an unintended behaviour change or a stale range-suppression
   assumption).
5. Stage D. Run the full gate set, including `make test`, and confirm it is
   green at HEAD (all 18 regenerated snapshots committed) before considering
   this work item complete.

Tests this work item adds/updates:

- Unit (serde): `range_role_serialises_open_and_close` and the amended
  inline-shape assertion in `crates/stilyagi-ir/src/tests/suppression.rs`.
- Version assertions updated in `crates/stilyagi-ir/src/tests/mod.rs`,
  `crates/stilyagi-markdown/src/tests/ir_consistency.rs`,
  `crates/stilyagi-pyext/src/tests/mod.rs`.
- Golden snapshots (`insta`) regenerated for **all 18** snapshots that embed
  `schema_version`: 5 in `crates/stilyagi-extract/tests/extract/snapshots/`,
  12 in `crates/stilyagi-markdown/src/snapshots/`, and 1 in
  `crates/stilyagi-test-support/tests/snapshots/`. The sole per-file delta is
  the line-6 `schema_version` string.

### Work item 2 — Populate range polarity in the Markdown frontend

Implements `docs/stilyagi-design.md`, the "Suppression syntax" section
("Suppression state must be visible in IR and debug output", line 625) and
roadmap 2.1.4's success criterion.

1. Stage B (red). In `crates/stilyagi-markdown/src/tests/suppression.rs`:
   - Add a unit test `range_directives_record_open_and_close_polarity`: extract
     a document containing a canonical `disable STY` then `enable STY` pair;
     assert the two emitted suppressions have
     `range_role == Some(RangeRole::Open)` and
     `Some(RangeRole::Close)` respectively, and that the inline and file
     suppressions in the same document have `range_role == None`.
   - Add a focused `insta` inline snapshot capturing
     `serde_json::to_string_pretty` of just the `document.suppressions` for a
     `disable`/`enable` pair, proving `"range_role": "open"`/`"close"` reaches
     the canonical JSON (per AGENTS.md snapshot rules: narrow, reviewer-useful,
     paired with the semantic assertions above).
   - Add a `verb_range_role` unit assertion (verb → expected role) and extend the
     existing `proptest` `parse_comment_directive_preserves_trimmed_codes` (or add
     a sibling property) to assert: for `disable` the role is `Open`, for
     `enable` it is `Close`, for `ignore-next`/`ignore-file` it is `None`.
   These fail (the mapping/field wiring does not exist yet).
2. Stage C (green). In `crates/stilyagi-markdown/src/suppression.rs` add
   `pub(crate) const fn verb_range_role(verb: DirectiveVerb) ->
   Option<RangeRole>` returning `Some(RangeRole::Open)` for `Disable`,
   `Some(RangeRole::Close)` for `Enable`, and `None` otherwise. Import
   `RangeRole` from `stilyagi_ir`. In `crates/stilyagi-markdown/src/lib.rs`
   import `verb_range_role` and set
   `range_role: verb_range_role(parsed.verb)` at the construction site (replacing
   the `None` placeholder from work item 1).
3. Regenerate the ONE existing golden snapshot whose *content* changes now that
   the frontend emits polarity: the hardening-fixture snapshot for the canonical
   `disable`/`enable` pair. Wiring `range_role` makes `s1`/`s2` in
   `crates/stilyagi-markdown/src/snapshots/`
   `stilyagi_markdown__tests__suppression_directives.snap` gain `"range_role"`,
   so the `insta::assert_snapshot!` and `assert_eq!(parsed, document)` in
   `hardening_fixture_ir_json_round_trips_without_span_drift`
   (`crates/stilyagi-markdown/src/tests.rs:121-125,146,150`) fail until the
   snapshot is re-accepted:

   ```sh
   cargo test -p stilyagi-markdown
   # review the pending .snap diff before accepting — see Stage D
   cargo insta accept    # or hand-review and commit the .snap update
   ```

   No other existing snapshot changes in work item 2: the `schema_version` churn
   was already handled in work item 1, and the shared **extract** fixture emits
   no suppressions (Surprises, observation 1), so only this one markdown snapshot
   moves here.
4. Stage D. Run the full gate set. Confirm the new unit, property, and inline
   snapshot tests pass. Before accepting the regenerated
   `stilyagi_markdown__tests__suppression_directives.snap`, confirm with
   `git diff -- '**/*.snap'` that the **entire** delta is **exactly two added
   lines** — one `"range_role": "open",` on the `s1` (`"kind": "range"`) entry
   and one `"range_role": "close",` on the `s2` entry — and that no other line,
   file, or snapshot moves. Any further delta is out of tolerance and must be
   inspected before acceptance.

Tests this work item adds/updates:

- Unit: `range_directives_record_open_and_close_polarity`; a `verb_range_role`
  mapping test.
- Property (`proptest`): role invariant for each verb.
- Snapshot (`insta` inline): serialized range-suppression pair.
- Golden snapshot (`insta`, regenerated): the single existing markdown snapshot
  `crates/stilyagi-markdown/src/snapshots/`
  `stilyagi_markdown__tests__suppression_directives.snap`, whose sole content
  delta is the two new `range_role` lines on the `s1`/`s2` range entries.

### Work item 3 — BDD behavioural coverage for a range pair

Implements the roadmap success criterion that "later steps can trust one source
of truth" end-to-end through `stilyagi-extract`.

1. Stage B (red). In
   `crates/stilyagi-extract/tests/features/markdown_suppression.feature` add a
   scenario, e.g.:

   ```gherkin
   Scenario: A range disable and enable pair record open and close polarity
     Given a Markdown document with a "stilyagi: disable STY" and "stilyagi: enable STY" pair
     When the document is extracted
     Then the IR suppressions record the disable as a range open
     And the IR suppressions record the enable as a range close
   ```

   Add the matching `#[given]`/`#[then]` steps and a `#[scenario(...)]`
   binding in
   `crates/stilyagi-extract/tests/extract/markdown_suppression_bdd.rs`, importing
   `RangeRole` from `stilyagi_ir`. Run the BDD test and observe it fail (the
   steps assert `range_role` values before wiring is trusted end-to-end).
2. Stage C (green). No production change should be required if work items 1-2
   are complete; the scenario turns green because the frontend already populates
   the field. (If the extract boundary drops the field, that is a discovery —
   record it and fix the boundary within tolerance.)
3. Stage D. Run the full gate set.

Tests this work item adds:

- Behavioural (rstest-bdd): the range-pair scenario in
  `markdown_suppression.feature` with steps in `markdown_suppression_bdd.rs`.

### Work item 4 — Update design and contract documentation

Implements AGENTS.md documentation-maintenance rules; keeps `docs/` the source of
truth.

1. `docs/rfcs/0001-stilyagi-intermediate-representation.md` §8: add
   `range_role` to the suppression field list, stating it is present only for
   `range` suppressions and carries `open`/`close`. Note in §9 (or a short
   changelog line) that the field is an additive optional field introduced at
   `schema_version` `1.1.0`. The RFC's illustrative JSON blocks show
   `"schema_version": "1.0.0"` at lines 107 and 373; either bump them to
   `1.1.0` or add a note that they are historical `1.0.0` illustrations, so the
   RFC does not advertise `1.0.0` while the emitter produces `1.1.0`.
2. `docs/stilyagi-design.md`, the "Suppression syntax" section (heading at
   line 603) implementation
   consequences: add a bullet that range suppressions record open/close polarity
   in the IR so downstream stages resolve range boundaries without re-scanning
   comment bytes.
3. `docs/developers-guide.md`: add a short note (in the IR/extraction internal
   interface material) documenting the `range_role` field and the
   `disable → open`, `enable → close` mapping, so rule authors rely on it rather
   than re-parsing comments.
4. Validate Markdown: `make markdownlint` and `make nixie` (no Mermaid is added,
   but `nixie` is required for `.md` changes per AGENTS.md). Wrap prose at 80
   columns; use en-GB Oxford spelling.

Before committing this work item, format only the touched Markdown files:
`mdtablefix <changed .md files>` then `markdownlint-cli2 --fix <changed .md
files>`, then run the gates. Do not run a repo-global Markdown format.

## Concrete steps

Run everything from the worktree root
`/home/leynos/Projects/stilyagi.worktrees/roadmap-2-1-4`.

Red/green loop for a focused Rust test (example, work item 1):

```sh
cargo test -p stilyagi-ir range_role_serialises_open_and_close
```

Expected before Stage C: compile error `cannot find type RangeRole` /
`no field range_role`. Expected after Stage C: `test result: ok`.

Regenerate golden snapshots (work item 1, after the version bump). All three
crates that embed `schema_version` must be regenerated — 18 files total:

```sh
cargo test -p stilyagi-extract --test extract_integration
cargo test -p stilyagi-markdown
cargo test -p stilyagi-test-support
# review the pending *.snap diffs; the only per-file change must be the
# line-6 schema_version string (git diff -- '**/*.snap')
cargo insta accept    # or hand-review and commit the .snap updates
```

Focused BDD run (work item 3):

```sh
cargo test -p stilyagi-extract --test extract_integration range
```

Full commit gates (every work item, before committing):

```sh
make check-fmt 2>&1 | tee /tmp/check-fmt-stilyagi-roadmap-2-1-4.out
make typecheck 2>&1 | tee /tmp/typecheck-stilyagi-roadmap-2-1-4.out
make lint      2>&1 | tee /tmp/lint-stilyagi-roadmap-2-1-4.out
make test      2>&1 | tee /tmp/test-stilyagi-roadmap-2-1-4.out
```

For the documentation work item additionally:

```sh
make markdownlint 2>&1 | tee /tmp/markdownlint-stilyagi-roadmap-2-1-4.out
make nixie        2>&1 | tee /tmp/nixie-stilyagi-roadmap-2-1-4.out
```

Prefer delegating full gate runs to the `scrutineer` sub-agent, which runs them
sequentially, captures each log under `/tmp`, and returns a bounded report.

## Validation and acceptance

Deterministic commit gates for this run, in order:

1. `make check-fmt`
2. `make typecheck`
3. `make lint`
4. `make test`

For the documentation work item also run `make markdownlint` and `make nixie`.
Do not report gates green unless every one passes at HEAD.

Red-Green-Refactor evidence to record per work item:

- Work item 1 — Red: `cargo test -p stilyagi-ir
  range_role_serializes_open_and_close` fails to compile (missing
  `RangeRole`/field). Green: after adding the enum, field, and re-export, the
  test passes and `make test` is green with regenerated snapshots.
- Work item 2 — Red: `range_directives_record_open_and_close_polarity` fails
  (frontend still emits `None`), and the pre-existing
  `hardening_fixture_ir_json_round_trips_without_span_drift` case flips red
  (`s1`/`s2` now serialize `range_role`, so the golden snapshot and
  `assert_eq!(parsed, document)` mismatch). Green: after `verb_range_role` is
  wired in AND the `stilyagi_markdown__tests__suppression_directives.snap`
  snapshot is re-accepted (sole delta: two `range_role` lines), the new unit
  test, the `proptest` invariant, the inline snapshot, and the regenerated
  golden snapshot all pass.
- Work item 3 — Red: the new BDD scenario fails. Green: it passes once the range
  pair is asserted end-to-end through `stilyagi-extract`.
- Work item 4 — Docs only; validated by `make markdownlint` and `make nixie`.

Behavioural acceptance (observable):

- Extract a document containing `<!-- stilyagi: disable STY -->` … `<!-- stilyagi:
  enable STY -->` and inspect `document.suppressions`: the first range entry has
  `range_role == Some(RangeRole::Open)`, the second `Some(RangeRole::Close)`.
- `IrDocument::to_canonical_json` emits `"range_role": "open"` / `"close"` on
  those entries and omits the key for inline/file suppressions.
- `schema_version` is `"1.1.0"`.

Quality criteria ("done"):

- Tests: new unit, property, and BDD tests pass; `cargo test --workspace` green.
- Lint/typecheck: `make lint` and `make typecheck` clean (no new Clippy warnings,
  no silenced lints).
- Formatting: `make check-fmt` clean.
- Compatibility: inline/file/config suppression JSON unchanged; only additive
  field plus `schema_version` bump differ from `1.0.0`.

## Idempotence and recovery

- All steps are re-runnable. Regenerating snapshots is idempotent. The accepted
  snapshot delta is **scoped per work item**: in **work item 1** the only
  permitted per-file change is the line-6 `schema_version` string (18 files); in
  **work item 2** the only permitted change is the two new `range_role` lines on
  the `s1`/`s2` range entries of
  `stilyagi_markdown__tests__suppression_directives.snap`. A diff that shows
  anything beyond the delta expected for the current work item must be inspected
  before acceptance, not accepted.
- If a gate fails, read the cited `/tmp/*.out` log, apply a fix, and re-run only
  the failing gate, then re-run the sequence from `make check-fmt`.
- No destructive operations. Leave the worktree clean (no stray stashes; if a
  named stash is ever used, follow the `df12-stash v1 …` naming rule).

## Interfaces and dependencies

Use `serde` (already a dependency) for the optional field; no new crates.

In `crates/stilyagi-ir/src/diagnostics.rs`, at the end of the milestone the
following must exist:

```rust
/// Open or close role of a range suppression directive.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RangeRole {
    /// A `disable` directive that opens a suppressed span.
    Open,
    /// An `enable` directive that closes a suppressed span.
    Close,
}
```

and `IrSuppression` gains:

```rust
    /// Open/close polarity for range suppressions; `None` otherwise.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub range_role: Option<RangeRole>,
```

In `crates/stilyagi-markdown/src/suppression.rs`:

```rust
pub(crate) const fn verb_range_role(verb: DirectiveVerb) -> Option<RangeRole> {
    match verb {
        DirectiveVerb::Disable => Some(RangeRole::Open),
        DirectiveVerb::Enable => Some(RangeRole::Close),
        DirectiveVerb::IgnoreNext | DirectiveVerb::IgnoreFile => None,
    }
}
```

`crates/stilyagi-ir/src/lib.rs` re-exports `RangeRole` and sets
`SCHEMA_VERSION = "1.1.0"`.

## Revision note

Round 3 (2026-07-05): resolved both blocking points from the round-3 design
review. (1) Work item 2 previously ended red: wiring
`range_role: verb_range_role(parsed.verb)` makes the canonical `disable STY` /
`enable STY` pair in `tests/fixtures/corpus/markdown/valid/`
`suppression-directives.md.fixture` gain `"range_role"` on its two `"kind":
"range"` entries (`s1` line 405, `s2` line 417 of
`stilyagi_markdown__tests__suppression_directives.snap`), so the
`insta::assert_snapshot!` and `assert_eq!(parsed, document)` in
`hardening_fixture_ir_json_round_trips_without_span_drift`
(`crates/stilyagi-markdown/src/tests.rs:121-125,146,150`) failed at its HEAD.
Work item 2 now explicitly regenerates and re-accepts that one snapshot
(`cargo test -p stilyagi-markdown` + `cargo insta accept`), lists it under
"Tests this work item adds/updates", and its Stage D pins the expected delta to
exactly two new `range_role` lines. (2) The Surprises section previously
generalized the "no golden snapshot needs new range-suppression content" claim
across all snapshots; it was true only of the shared **extract** fixture
(`heading-table-link-suppression.md`, ignored marker, no suppressions). Rescoped
observation 1 to the shared extract fixture only and added a BLOCKING-correction
observation naming the markdown crate's own fixture as the snapshot that does
gain content in work item 2. Also rescoped the Idempotence guidance so the
legitimate work-item-2 `range_role` delta is not mistaken for a regression to
reject. Verified fixture, snapshot, and test wiring directly in the worktree.

Round 2 (2026-07-05): resolved the design reviewer's single blocking point — the
incomplete `schema_version` snapshot blast-radius analysis. The round-1 draft
wrongly claimed the `1.0.0 → 1.1.0` bump churned only the extract rust/python
golden snapshots and that "the markdown golden snapshot does not embed it … so
it is unaffected". Verified via `grep -rl '"schema_version": "1.0.0"' crates`
that 18 snapshot files embed `schema_version` (5 extract + 12 markdown + 1
test-support). Corrected the Context, Risks, Surprises, and Tolerances sections
to state the true 18-file churn, and expanded work item 1 step 4 (and the
Concrete-steps regeneration block) to run `cargo test -p stilyagi-markdown` and
`cargo test -p stilyagi-test-support` alongside the extract integration test, so
every snapshot is regenerated and `make test` is green at the HEAD of work
item 1. Also resolved both advisories: replaced the "§7.1 Suppression syntax"
mislabel with the correct "Suppression syntax" heading (line 603, distinct from
"§7.1 Intermediate representation" at line 786), and added a step to reconcile
the RFC's illustrative `1.0.0` JSON blocks (lines 107, 373).

Initial draft (2026-07-05): first planning round for roadmap task 2.1.4.
Decomposed into four work items — contract type + schema bump, frontend
polarity wiring, BDD coverage, documentation — each independently
gate-passable. Verified against the live code (single `verb_kind` collapse of
`disable`/`enable`; two `IrSuppression` construction sites; RFC 0001 §8/§9
compatibility rules; golden Markdown fixture uses the ignored non-canonical
marker so no range-suppression snapshot churn). No open forks; the additive
optional field with a `1.1.0` minor bump is the pinned mechanism.
