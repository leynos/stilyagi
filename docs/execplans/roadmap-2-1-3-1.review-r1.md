# Logisphere design review — roadmap 2.1.3.1, round 1

Status: CHANGES REQUESTED (ExecPlan remains DRAFT).

Reviewer: adversarial design panel (Pandalump, Wafflecat, Buzzy Bee, Telefono,
Doggylump, Dinolump) plus pre-mortem and alternatives checkpoint.

## Verdict

⚠️ Revise. The core design — a behaviour-agnostic per-comment scan of each
`Node::Html` source slice, emitting one IR suppression/error per comment with
byte-accurate per-comment spans and a shared `origin` node id — is sound,
contract-conformant (RFC 0001 §7–§8; ADR-005 Markdown scope), and robust to
either `markdown-rs` node shape. It was verified against the live source. One
blocking defect prevents approval: Work item 1, as specified, does not leave the
tree gate-green.

## Blocking

1. **Work item 1 will fail `make lint` — the additive helper is dead code in the
   library build.** `make lint` runs
   `cargo clippy --workspace --all-targets -- -D warnings` (AGENTS.md lines
   167–178). `--all-targets` builds the plain lib target with `cfg(test)` OFF.
   `scan_comment_spans` / `CommentSpan` are declared in the production module
   `mod suppression;` (lib.rs:8, non-`cfg(test)`) but WI1 references them only
   from `#[cfg(test)] mod tests;` (lib.rs:302). A `pub(crate)` item used only by
   test code is `dead_code` in the lib-target compilation → `-D warnings` fails.
   WI1's stated acceptance ("the helper is unused by production code so far, so
   gates stay green") is therefore false, and each work item is required to be a
   single gate-green commit. Silencing with `#[allow(dead_code)]` is disallowed
   (AGENTS.md line 189).
   Remedy (pick one): fold WI1's helper into WI2 so the helper lands in the same
   commit as its production caller in `suppressions_from_candidates`; or reorder
   so WI1 both adds the helper and wires it into production. Keep the pure-helper
   unit/property tests, but do not commit the helper without a production caller.

## Advisory

- WI2 constructs `SourceSpan { byte_start, byte_end }` by struct literal. Fields
  are `pub` so it compiles, but `SourceSpan::new`/`try_new` exist to guard
  `byte_start <= byte_end`. The invariant holds here (`rel_start < rel_end`
  always), so this is style only; prefer the constructor for consistency if it
  is used elsewhere in `lib.rs`.
- The `.feature` file is Gherkin, not Markdown; markdownlint/nixie correctly do
  not apply to it. No action needed — noted so the implementer does not add it to
  the Markdown gate file list.

## Verification performed (facts confirmed against the worktree)

- `suppressions_from_candidates` (lib.rs:208–261) slices the whole node span,
  strips one `<!--`/`-->` pair, parses once — confirming the directive-loss bug
  and the plan's fix target. The strip requires the node slice to begin exactly
  with `<!--` and end exactly with `-->`, so for a single-comment node the
  per-comment sub-span is byte-identical to `candidate.span`; existing span
  assertions remain valid (plan's Risk-3 reasoning holds).
- `verb_kind` (suppression.rs:77–83) maps `Disable | Enable → Range`; the WI2
  "both `SuppressionKind::Range`, codes `[\"STY\"]`" assertion is correct.
- `parse_comment_directive` (suppression.rs:50–74) rejects a codeless
  `enable` as `BlanketForbidden` (not `IgnoreFile`), so the WI2 mixed case
  (one suppression + one `suppression-blanket-forbidden`) is correct.
- IR suppression id is `format!("s{}", suppressions.len())`; looping over
  scanned comments keeps ids monotonic in source order, so existing id/order
  assertions are unaffected.
- Referenced helpers all exist: `parse_markdown_ast` (lib.rs:32),
  `find_html_node`/`html_node_ids` (tests/suppression.rs), `source_identity`
  (tests.rs:62), `extracted_ir`/`the_document_is_extracted`
  (markdown_suppression_bdd.rs). Feature and BDD files exist.
- Roadmap item 2.1.3.1 (docs/roadmap.md:147–151) and its addendum text match the
  ExecPlan quotation. Gate targets match AGENTS.md (`check-fmt`, `typecheck`,
  `lint`, `test`; `markdownlint`, `nixie`).
- `SourceSpan` (stilyagi-ir/src/tree.rs:45) has `pub byte_start`/`byte_end`.
- No standalone red-test commit is mandated: Red→Green happens within a single
  work-item commit.

## Pre-mortem (Doggylump)

- Most likely incident: an implementer commits WI1 verbatim, `make lint` fails on
  `dead_code`, and the run halts or the implementer improvises a commit-boundary
  deviation. Mitigation: the blocking remedy above.
- Second: a byte-offset error in per-comment span arithmetic. Mitigated by the
  plan's mandatory re-slice assertions in every new test and
  `validate_ir_consistency`.

## Alternatives checkpoint (Wafflecat)

The "split multi-comment HTML nodes" alternative was correctly rejected in the
Decision Log: it perturbs node ids and every downstream span/consistency check
for no benefit the scan approach lacks. No stronger alternative exists; the scan
design is on solid ground once the WI1 commit boundary is fixed.

## Tooling note

Memtrace/Leta were not driven in this review session; verification was performed
by direct file inspection inside the worktree, which is sufficient for a
branch-local design review. This is a documented fallback, not a blocker.

---

## Round 1 (resumed) — re-review of the current three-item plan

Status: CHANGES REQUESTED (ExecPlan remains DRAFT).

The prior round-1 dead-code blocker is **resolved**: current WI1 folds the
`scan_comment_spans` helper into the same commit as its
`suppressions_from_candidates` caller, and `Makefile:13-14,123` +
`AGENTS.md:172` confirm the `--all-targets`/`-D warnings` reasoning. Two new
blocking defects remain.

### Blocking Notes

1. **Self-contradicting Tolerance vs. declared scope.** Tolerances say "if the
   fix requires touching more than 4 source/test files … stop and escalate," but
   the plan enumerates 5 source/test files: `suppression.rs`, `lib.rs`,
   `tests/suppression.rs`, `markdown_suppression.feature`, and
   `markdown_suppression_bdd.rs`. As written the implementer must escalate on the
   5th file. Raise the threshold (~6) or reword to exempt the enumerated set.

2. **Unverified, likely-false library-behaviour premise underlies WI1's red
   test.** Purpose (line 26) and WI1's `coalesced_directives_all_captured` treat
   the *adjacent-line* form (`<!-- a -->\n<!-- b -->\n`) as a coalesced single
   node that loses the second directive before the change. Per CommonMark
   HTML-block type 2, each line that begins `<!--` and contains `-->` closes its
   own block, so adjacent single-line comments produce TWO `Node::Html` nodes and
   are already handled correctly today — that sub-case is green before the change,
   not red. The same-line form IS genuinely coalesced (verified: current parser
   yields one suppression with garbage code `STY --> <!-- stilyagi: enable STY`),
   so the overall test still goes red via the same-line case, but the plan's
   per-case framing and Purpose premise are wrong and rest on uncited, unexecuted
   memory about markdown-rs 1.0.0. Fix: ground WI1's red/green evidence solely on
   the same-line form, reclassify the adjacent-line case as a separate-node
   regression guard, and correct the Purpose framing. WI2's characterization
   test already anticipates `_separates_`, so this is a correctness/framing fix,
   not a redesign.

### Advisory Notes

- WI1 proptest: constrain generated comment inner text to exclude `<!--`/`-->`
  or the naive scanner's count assertion can spuriously fail.
- WI1 Part B: state explicitly that `id: format!("s{}", suppressions.len())` is
  retained (currently only implied by "id counter unchanged").
- The 8+ durability rounds (3–12) are environmental git-commit churn; condense to
  keep the ExecPlan readable. Not a design blocker.
