# Logisphere design review — roadmap 2.1.4, round 2

Status: CHANGES REQUESTED (plan remains DRAFT)

Reviewer verified every load-bearing claim against the worktree source
(`leta`/grep + snapshot inspection) and the RFC/design docs. One blocking defect
survived; the round-1 blocker (18-file schema_version churn) is correctly
resolved.

## Blocking defect

**Work item 2 does not end green: it silently changes the existing
`suppression_directives` golden snapshot but never regenerates it, and the
plan's own Surprises section asserts the opposite.**

- `crates/stilyagi-markdown/src/tests.rs:121-125` snapshots
  `to_canonical_json` of `suppression-directives.md.fixture` into
  `crates/stilyagi-markdown/src/snapshots/stilyagi_markdown__tests__suppression_directives.snap`.
- That snapshot contains **two `"kind": "range"` suppressions** (`s1` at
  line 405, `s2` at line 417 — the canonical `disable STY` / `enable STY`
  pair).
- Work item 1 adds `range_role: None` at the construction site, so under
  `skip_serializing_if` these range entries emit no `range_role` key — work
  item 1's regeneration of this snapshot is correctly limited to the line-6
  `schema_version` string.
- Work item 2 wires `range_role: verb_range_role(parsed.verb)`, so
  `to_canonical_json` now emits `"range_role": "open"` on `s1` and
  `"range_role": "close"` on `s2`. The `suppression_directives` snapshot gains
  two new lines and its `assert_eq!(parsed, document)` / snapshot assertion
  fails. **`make test` fails at work item 2's HEAD.**
- The plan's Surprises section (lines 125-139) claims "no existing golden
  snapshot needs new range-suppression content (no snapshot gains or changes a
  `suppressions` entry)". That is false: it conflated the shared *extract*
  fixture (`heading-table-link-suppression.md`, which uses the deliberately
  ignored `stilyagi-disable-next-line` marker and emits no suppressions) with
  the markdown crate's own `suppression-directives.md.fixture`, which uses
  canonical `disable`/`enable` and emits two range suppressions.
- The trap is compounded by the Idempotence guidance ("if a snapshot diff shows
  more than the `schema_version` change, do not accept it — inspect the extra
  delta first"): an implementer following the plan would treat the legitimate
  work-item-2 `range_role` delta as an unintended regression to reject.

### Required fix

Work item 2 must explicitly regenerate and re-accept
`stilyagi_markdown__tests__suppression_directives.snap` (run
`cargo test -p stilyagi-markdown` and `cargo insta accept`), list it under
"Tests this work item adds/updates", and its Stage D must expect exactly two
new `range_role` lines (`open` on `s1`, `close` on `s2`) as the sole content
delta. The Surprises section must be corrected: the no-content-churn claim
holds only for the shared extract fixture, not for the markdown crate's
`suppression_directives` snapshot. Confirm no other extract snapshot dumps a
canonical range pair (verified: the 5 extract snapshots are python/rust; the
extract markdown golden uses the ignored marker — both unaffected).

## Verified sound

- 18 `schema_version` snapshot files (5 extract + 12 markdown + 1
  test-support): `grep -rl '"schema_version": "1.0.0"' crates` returns exactly
  those 18. Round-1 blocker resolved.
- Two `IrSuppression` construction sites (`stilyagi-markdown/src/lib.rs:235`,
  `stilyagi-ir/src/tests/suppression.rs:9`); `diagnostics.rs:23` is the struct
  def. Type-change blast radius correctly enumerated.
- RFC 0001 §8 (line 327) / §9 (line 346) exist; illustrative `schema_version`
  JSON at lines 107 and 373 as work item 4 claims.
- Design "Suppression syntax" heading at line 603 (distinct from "7.1
  Intermediate representation" at 786); "Suppression state must be visible in IR
  and debug output" at line 625.
- Additive optional field + `1.1.0` minor bump is RFC §9-conformant; keeps
  `kind == range` stable; `RangeRole` enum over a boolean honours AGENTS.md.
- No standalone red-test commit is required: red/green stages are folded inside
  each work item, which ends green and is independently committable.
- Deterministic gates (`make check-fmt` → `typecheck` → `lint` → `test`, plus
  markdown gates for work item 4) match AGENTS.md and are correctly scoped.

## Advisory

- Work item 3's Stage C assumes the extract boundary already propagates
  `range_role`; it hedges correctly ("if the extract boundary drops the field
  … fix within tolerance"). No change required, but confirm the extract path
  serialises via the same `IrSuppression` so the assumption holds.
