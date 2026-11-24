# Add builtin documentation rules (3.2.2)

This execution plan (ExecPlan) is a living document. Keep its constraints,
progress, discoveries, decisions, conformance basis, verification, and outcomes
current at every milestone boundary.

Status: IMPLEMENTED (2026-11-22). All three milestones are complete and roadmap
3.2.2 is ticked; final gate evidence for the delivery commit is recorded in the
Progress section. The prerequisite 2.3.1 merged as commit
`a6ba33a1985b75bdcd07513f1b9cffb2559a5d17` (pull request 240). The
implementation baseline is `fc28da93080eb0b0bfd094de283f74dd53d62586`, the main
tip this branch was rebased onto.

## Purpose / big picture

After implementation, a mixed repository check will identify a missing summary
separator in Python docstrings, missing summary punctuation in Python and Rust
documentation, and summaries that merely repeat their documented owner's name.
These rules will use the same region-oriented rule execution and policy
selection as the Markdown starter pack. A region is an extracted prose unit
with syntax, owner identity, and mappings back to source bytes.

Success means `stilyagi check .` produces useful, deterministic, source-located
rule diagnostics for configured documentation policies. Ordinary comments
remain outside the supported surface. This is a plan-only change: the
implementor marks roadmap item 3.2.2 done only after the acceptance evidence
below passes.

## Constraints

- Preserve the Rust extraction/Python policy boundary. Rules consume the
  shared typed region API and never inspect tree-sitter nodes, read source
  files themselves, or invoke an extractor directly.
- Reuse the policy, registry, diagnostics, suppression, and command pipeline
  delivered by 2.3.1. Add only the bounded Python-side projection and targeting
  extensions described below; do not create a docstring-only engine.
- Support Python docstrings and Rust documentation comments explicitly.
  Standalone Markdown and arbitrary non-documentation comments are excluded
  from these three new rules. Existing Markdown rules remain unchanged.
- Preserve verbatim intermediate representation (IR), owner metadata, segment
  maps, UTF-8 byte offsets, and deterministic ordering. Analysis views must not
  mutate the IR. Never treat Python string escapes as decoded source text.
- Introduce no natural language processing (NLP) requirement, runtime
  dependency, source schema change, or automatic edit in this slice.
- Keep modules below 400 lines. Sweep for existing helpers before adding one;
  document each new helper's limited scope and reuse policy.
- Run gates sequentially, capture output with `tee`, preserve shared Cargo
  caches and compiler admission, and never interrupt another agent's work.

## Tolerances (exception triggers)

Stop implementation, record the proposed deviation, and seek explicit direction
if the merged rule substrate cannot support the planned private projection and
targeting extensions; source mapping needs new extractor metadata; a runtime
dependency, parser, public wire change, or autocorrection is needed; or a rule
cannot meet its specified false-positive exclusions. Do not change the Rust
extractors or wire schema. Private API changes may be made atomically with all
callers; compatibility wrappers are not required.

There is no elapsed-time limit. Three unsuccessful fixes of the same gate
failure require a recorded diagnosis before another attempt, not a weakened
gate. Disk exhaustion or compiler-admission failure requires reporting the
external blocker without bypassing it.

## Risks

The merged rule loop is the baseline, but its projection exposes no owner and
its target accepts one syntax at a time (medium impact). A bounded extension
milestone will add these rule-facing capabilities without changing extraction
or wire formats. Markdown inside Rust comments and verbatim Python strings make
broad summary heuristics prone to false positives (medium impact); restrict
recognition as specified below and test unsupported forms as negative cases.
Synthetic Rust line separators make region offsets different from source
offsets (high impact); use the prerequisite's source mapping and offer no
fixes. Optional owner names are normal, not extraction failures (medium
impact); skip the owner-dependent rule when a trustworthy name is absent.

## Progress

- [x] (2026-10-13) Inspect baseline, requested skills, roadmap, and
      architecture.
- [x] (2026-10-13) Obtain two Wyvern reconnaissance reports and primary-source
  guidance through Firecrawl.
- [x] (2026-10-13) Complete six-lens community review through three agents;
  reconcile summary boundaries, markup exclusions, Unicode spans, CLI evidence,
  mutation witnesses, and fail-fast gate commands.
- [x] (2026-10-13) Markdown lint, spelling, and Mermaid validation pass.
- [x] (2026-10-13) Formatting validation passes after a second format pass.
- [x] (2026-10-13) Publish the validated planning commit as draft PR #225.
- [x] (2026-11-16) Rebase onto the refreshed target and reconcile the plan
  with the merged 2.3.1 rule substrate.
- [x] (2026-11-22) EP-M0 implemented: `RegionOwner` projected onto
      `RegionView`; `RegionTarget.syntaxes` and `owner_kinds` replace the
      scalar syntax; `engine/region_views.py` extracted to keep the projection
      modules under the file-size ceiling. Focused tests in
      `tests/test_docstring_target_projection.py` pass (10), the existing
      extraction, projection, policy, and Markdown-rule suites pass, and a
      mutation disabling `matches_region` was killed by 22 negative cases.
- [x] (2026-11-22) EP-M1 implemented: `DocRuleConfig` with validated
      `enabled`; `rules/builtin/summary.py` (physical lines, summary
      selection, anchor mapping) and `rules/builtin/documentation.py` (the
      three hooks); `DOC001`–`DOC003` registered in the pack. The finite
      matrix (`tests/test_builtin_docstring_rules.py`,
      `tests/test_builtin_owner_summary_rules.py`) and property suite
      (`tests/test_builtin_docstring_properties.py`) pass: 85 focused tests.
      Mutations for character-for-byte anchoring (5 failures) and reversed
      rule order (4 failures) were killed and reverted.
- [x] (2026-11-22) Duplication, typecheck, and wheel-snapshot failures from
      the first full gate chain are fixed: the shared `utf8_offsets` helper is
      reused, one boolean-option parser serves both flags, the three hooks
      share one enabled-findings driver, the conditional-import prologue entry
      was re-recorded across all eight modules, the property test's rule table
      is annotated, and the wheel snapshot gained the three new modules.
      `make duplication` passes with 12 reasoned exceptions and `ty` passes.
- [x] (2026-11-22) Full gate chain green on the EP-M0+EP-M1 candidate:
      `check-fmt`, `typecheck`, `lint`, `test`, `markdownlint`, and `nixie`
      all passed (evidence `/tmp/stilyagi-322-M1b.nJLB6H`). Committed as
      `8cf596b5`.
- [x] (2026-11-22) EP-M2 implemented: `features/builtin_docstring_rules.feature`
      with eight scenarios, `tests/steps/builtin_docstring_rules.py`,
      `tests/test_builtin_docstring_rules_bdd.py`, and
      `tests/test_builtin_docstring_cli.py` (fresh `python -m stilyagi`
      processes, a normalised `syrupy` JSON snapshot, ordering, warning-only
      exit 0, false/absent opt-in, and malformed-option exit 2). One Rust
      `rstest` case was added to `rust_doc_comment_bdd.rs` proving merged
      doc-comment lines keep one source-backed segment each around a
      `softbreak_space`. Documentation updated: users' guide (codes, matrix,
      opt-in, exclusions), developers' guide (target and owner projection,
      documentation rule authoring), design §7.2, repository layout, and the
      roadmap tick for 3.2.2.
- [x] (2026-11-22) Full gate chain re-run on the EP-M2 candidate
      (`e0990edd`): `check-fmt`, `typecheck`, `lint`, `test`, `markdownlint`,
      and `nixie` all passed (evidence `/tmp/stilyagi-322-M2final.lV3hls`).
- [x] (2026-11-22) CodeScene delta cleared by restructuring, not suppression:
      one shared `check_documentation` driver, a `_LineSplitter` replacing the
      nested walk in `_physical_lines`, and two parameterized test families.
      `cs delta origin/main` reports no issues.
- [x] (2026-11-23) Review-response gate evidence. `check-fmt`, `typecheck`,
      `lint` (full, including Whitaker), `markdownlint`, and `nixie` pass on
      the review-response tree. `make test` passes nextest 371/371 and the
      doctest-modules lane (193 passed, 3 skipped); the ordinary pytest lane
      reports 1821 passed with two or three
      `tests/test_lint_policy_behaviour.py` cases failing only as
      `cargo ... timed out after 240 s`. That module's scratch crates compile
      under the shared admission pool, whose queue held 100-365 requests from
      other repositories during these runs; the same module passed 12/12 on
      the same tree when the queue was shallow. The failure is recorded as
      host compile-capacity, not a candidate defect.
- [x] (2026-11-22) Pre-merge review gaps closed: Python multi-line summary,
      trailing whitespace, leading blank lines, a failing wrapped Rust
      paragraph, a two-line Rust property, six explicit table orders, and a
      v0.2.0 migration-guide entry.
- [x] (2026-11-23) ExecPlan completeness assessment answered. CodeRabbit found
      four in-scope gaps, all now closed. (1) The users' guide wrongly claimed
      every Rust block comment is skipped; the exclusion is content-based, and
      a plain `/** Read records */` does report. The guide now says so and
      `tests/test_builtin_docstring_rules.py` carries a plain-block witness.
      (2) The guide gained the per-rule syntax and owner-kind matrix, including
      the nine Rust item kinds `DOC003` accepts. (3) Command-boundary coverage
      now includes the text renderer, an error-severity exit 1 alongside
      documentation warnings, and malformed-source extractor diagnostics with
      the rules enabled and disabled. (4) V2 and V3 evidence gained an
      independently computed anchor position, an IR/source immutability check,
      selection-order permutations, and a Rust-function `DOC003` witness.
      Multi-line assert messages became `assert_with_context` calls, matching
      the repository idiom and keeping the new test files' executable line
      share high for the coverage ratchet.
- [x] (2026-11-24) ExecPlan completeness assessment cleared after four
      evidence rounds: CodeRabbit found no remaining in-scope defect on head
      `099b3b66`. Its later findings, all repaired: content-based block-comment
      documentation; the per-rule target matrix; a mixed Python/Rust/Markdown
      extractor comparison across both opt-in states; generated multibyte
      content before the anchor in both the Python and Rust properties;
      immutability checked on the request that was actually run; and
      whole-`Diagnostic` equality across rule-selection permutations. Hosted
      `Smoke` on `cb62f58f` was fully green, with the coverage ratchet at
      Python 92.34% (floor 91.88%) and Rust 92.13% (floor 90.48%); CodeScene
      reports no issues. The proof assessment is not applicable: this plan
      introduces no CrossHair, Kani, Verus, or LemmaScript asset. The
      original-issue assessment is not applicable: the PR implements a
      roadmap item rather than a GitHub issue.
- [x] (2026-11-24) Ready-for-review findings repaired. The Codex P1 was valid:
      the exported `SummarySource` methods and the `PhysicalLine` class lacked
      the usage examples `AGENTS.md` requires of public APIs. Every public
      method now has a NumPy-style `Examples` section; `anchor` distinguishes a
      character index from a byte offset, shows an out-of-range index, and
      shows a synthetic segment yielding `None`. The examples pushed
      `summary.py` past the file-size ceiling, so the conservative Markdown
      exclusion predicates moved to `rules/builtin/markup.py`, named in the
      layout, design, and developer guidance and added to the wheel snapshot.
      Three CodeRabbit findings were also repaired: the wheel snapshot now
      lists `markup.py` in the sorted position the runner produces (the hosted
      `lint-test` had failed on exactly this order), the Rust extraction test
      pins each segment's stored text as well as its shape, the users' guide
      says `DOC001` anchors on the first non-whitespace character, and the
      mixed-tree CLI test checks both runs' exit status inside its loop.
- [x] (2026-11-24) A further assessment round found two real defects in the
      physical-line walk, both reproduced before fixing. A CR-LF pair left its
      CR inside the `PhysicalLine` range, so `line_text` had to strip it and
      the range contradicted its documented contract; a lone CR was stripped
      although it does not terminate a line; and a CR ending one segment with
      the LF starting the next was not recognised as one terminator. The walk
      now excludes the CR of a CR-LF pair, keeps a lone CR as text, pairs a
      split terminator, and returns ranges verbatim from `line_text`. Three
      regression tests pin those cases. The walk moved with `PhysicalLine`
      into `rules/builtin/line_split.py` so `summary.py` stays inside the
      ceiling, and the doctest spans now match their segment text.

## Surprises & discoveries

At the original planning baseline (`91941ef36df9c262af74e6089e661921d1ae3577`),
the rule runner was a placeholder and 2.3.1 was unchecked. That is historical
context, not the current implementation state. PR #240 merged 2.3.1 as
`a6ba33a1985b75bdcd07513f1b9cffb2559a5d17`; the starter pack now exercises the
shared rule loop. The current gap is narrower: the rule-facing `RegionView`
does not yet project typed owner identity, and `RegionTarget` has one syntax
value and no owner-kind filter.

During the original reconnaissance, CodeGraph indexing did not establish a
useful graph and agent symbol searches failed with `Transport closed`. Focused
repository reads and context packs supplied the evidence instead. No
graph-derived relationships are assumed by this plan.

## Decision log

- 2026-10-13: Keep this task conditional on 2.3.1. Folding in an entire rule
  engine would violate the roadmap dependency and obscure the learning goal.
  This describes the planning baseline; 2.3.1 has since merged.
- 2026-10-13: Propose three conservative structural rules, rather than
  imperative-mood detection or signature analysis. Owner kind and name exist;
  parameters, return types, decorators, and visibility do not form a guaranteed
  owner contract. Grammar rules belong to later capability slices.
- 2026-10-13: All three rules are diagnostic-only and explicitly enabled.
  This followed the shared policy model without choosing a new default style
  for all repositories. Source fix mapping remains the existing engine's
  responsibility; 3.2.3 owns broader mixed-source output/fix work.
- 2026-11-16: Retain per-rule opt-in, but implement it as validated
  `enabled=false` rule configuration. Default `DOC` and `PYDOC` prefixes
  already select these codes, so prefix selection alone cannot satisfy opt-in.
  The rule hook must produce no diagnostics until explicitly enabled; shared
  policy still handles selection, ignores, plugins, and suppression.
- 2026-10-13: Record the proposed rule contract in design §7.2, linked to this
  plan. No new port, transport, schema, or persistent format is proposed, so a
  separate architectural decision record (ADR) is unnecessary. If that changes,
  create an ADR following the documentation style guide before implementing.

## Outcomes & retrospective

Roadmap 3.2.2 is implemented. The rule-facing projection now carries typed
owner metadata and a target that names several syntaxes and owner kinds; three
opt-in, diagnostic-only rules (`DOC001`, `DOC002`, `DOC003`) run through the
same registry, inventory order, and policy path as the Markdown starter pack,
over Python docstrings and Rust documentation comments only.

Evidence, by milestone:

- EP-M0 and EP-M1 were committed together as `8cf596b5` after the whole gate
  chain passed (`/tmp/stilyagi-322-M1b.nJLB6H`: `check-fmt`, `typecheck`,
  `lint` including the blocking duplication and dead-code gates, `test` with
  370/370 nextest and 1787 pytest cases, `markdownlint`, `nixie`).
- Three mutations were killed and reverted: disabling `matches_region` (22
  failures), mapping character indices onto byte offsets (5 failures), and
  reversing the inventory (4 failures).
- EP-M2 adds the mixed-tree BDD feature (eight scenarios), a fresh-process CLI
  suite with a normalised snapshot, and one Rust extraction case proving merged
  doc-comment lines keep per-line source segments around the recorded
  `softbreak_space`.

Two deviations are recorded. First, `engine/region_views.py` was extracted from
`engine/rule_projection.py` when the owner projection pushed the module past
the 400-line ceiling; the private API changed atomically with its callers and
no compatibility wrapper was added. Second, the duplication gate required two
Python refactors rather than exceptions: the shared `text.utf8_offsets` table
replaced a private copy, and one boolean-option parser now serves both
`case_sensitive` and `enabled`. The conditional-import prologue family grew to
eight modules and one reasoned exception covers exactly that family.

Not delivered, and not in scope: automatic fixes (none of the three rules
proposes an edit), Markdown or ordinary-comment surfaces, NLP, and any
extractor or wire-schema change.

## Context and orientation

Read `AGENTS.md`, `docs/contents.md`, and `docs/repository-layout.md` first.
Use the layout guide for path responsibilities and the actual source for
implementation status.

Rust owns source fidelity in `crates/stilyagi-ir/src/region.rs` and the
extractors under `crates/stilyagi-tree-sitter/`. `IrRegion` already carries
syntax, owner, text, and source-backed or synthetic segments. ADRs 006 and 007
specify Python and Rust owner identity. Python owners are module, class, or
function; methods use function, and module names can be absent. Rust includes
module, struct, enum, union, trait, function, const, static, type, macro, impl,
and fallback item. The rule must use those facts, not infer missing semantics.

The delivered path is `python/stilyagi/rules/registry.py::run_rules`, using
`RuleRunRequest` from that module and `RuleContext`, `RuleMetadata`, and
`RegionTarget` from `python/stilyagi/rules/base.py`, plus the private
`BuiltinRule`/`inventory`/`run_selected` pack contract in
`python/stilyagi/rules/builtin/pack.py`. Projection lives in
`python/stilyagi/engine/rule_projection.py::project`; rule-facing regions and
segments are `RegionView` and `RegionSegment` in
`python/stilyagi/model/region.py`. Source mapping helpers `utf8_offsets`,
`token_span`, and `location` are in `python/stilyagi/rules/builtin/text.py`, and
`Diagnostic.span` carries the source span. There is no public `Rule` subclass
or `visit_region` API; hooks run per document. EP-M0 adds typed owner
projection and extends private `RegionTarget.syntax` to
`syntaxes: tuple[str, ...]` plus `owner_kinds`, updating all callers
atomically. No extractor or wire-schema change is required.

`LintConfig.select` already includes `DOC` and `PYDOC`. Each new rule therefore
needs frozen per-rule configuration defaulting to `enabled=False` and validated
TOML opt-in under `[tool.stilyagi.rule.DOC001]` (file scope `[rule.DOC001]`).
The hook returns no diagnostics until enabled, following the existing
`Term001Config.is_active` pattern in `python/stilyagi/config/rules.py`; normal
selection, ignore, plugin, and suppression policy continues to apply. Do not
alter global selection defaults or add a registry activation framework. The CLI
exits 0 for warning-only findings, 1 for error findings, and 2 for
configuration or environment failures; there is no configurable fail-on option.
Names below for new test files are proposals, not claims that those files exist.

## Conformance basis

The current basis is target commit `b52ffc0c0cfe28bd0fb61e019568471112534b05`,
merged prerequisite commit `a6ba33a1985b75bdcd07513f1b9cffb2559a5d17`,
`docs/roadmap.md` item 3.2.2, `docs/stilyagi-design.md` §§3–4, 7.2, and 13,
`docs/rfcs/rfc-0002-stilyagi-python-rule-api.md`,
`docs/adrs/adr-0003-ratify-the-v1-contract-scope.md`,
`docs/adrs/adr-0006-adopt-docstring-owner-metadata.md`,
`docs/adrs/adr-0007-adopt-rust-documentation-comment-owner-metadata.md`,
`docs/adrs/adr-0008-adopt-v1-discovery-defaults.md`, and
`docs/adrs/adr-0012-adopt-the-source-backed-builtin-rule-contract.md`. There is
no separate task-specific terms-of-reference document. RFC 0002 describes
region targets and deterministic ordering. ADR-0012 records the delivered
private implementation contract: one per-document hook per builtin rule,
selected target regions in each context, and deterministic inventory order. The
source API is private and may change atomically with its callers.

Trace R-REUSE (shared loop and merged prerequisite) through EP-M0 and EP-M1 to
the registration/dispatch tests; R-VALUE (summary, punctuation, owner-aware
value) through EP-M1 to the three rule tables; R-SCOPE (explicit surface
targeting and no ordinary comments) through both implementation milestones to
the targeting matrix and mixed-tree command test; R-FIDELITY (source-backed
diagnostics) through EP-M1 and EP-M2 to Unicode properties and renderer
snapshots; R-DELIVERY (documentation and roadmap completion) through EP-M2 to
final gates and the roadmap diff. Keep these links current as work progresses.

Primary-source research on 2026-10-13 used Firecrawl to consult
[PEP 257](https://peps.python.org/pep-0257/) and the
[rustdoc writing guide](https://doc.rust-lang.org/rustdoc/how-to-write-documentation.html).
PEP 257 recommends a summary separated from further explanation by a blank
line. Rustdoc recommends a concise opening summary and supports Markdown. These
are conventions, not syntax errors. The exact bounded policies below are
Stilyagi design choices, not assertions that every upstream convention is
mandatory.

## Proposed rule contract

Reserve `DOC001`, `DOC002`, and `DOC003`, after confirming those codes are
unused. Each declares `requires_nlp=False`, default warning severity, no fix,
and no preview dependency. Explicit per-rule `enabled=true` is required in
addition to shared prefix selection. Policies can narrow these targets; they
cannot broaden a rule into an unsupported syntax. `owner_kinds=()` means the
target accepts any owner state, including absent owner metadata; a nonempty
tuple requires a present owner whose kind matches. No rule needs
locale-sensitive linguistic claims. Physical content lines split only at LF,
treating a preceding CR as part of the CR-LF terminator; Unicode line
separators and a lone CR do not create additional physical lines. Analysis-only
trimming uses Python Unicode whitespace semantics.

`DOC001`, summary separation, targets only Python `python_docstring` regions
with module, class, or function owners. Find the first nonblank physical
content line after ignoring leading blank lines. If it has a nonblank immediate
next line, report that the summary needs a blank separator. A single content
line and an immediate blank line pass. Blank-only content is skipped, because
this slice does not introduce missing-documentation checks. Do not split on the
literal two-character escape `\n`. Anchor the diagnostic on the first
source-backed non-whitespace character of the second content line. This policy
is deliberately not applied to wrapped Rust Markdown summary paragraphs.

`DOC002`, summary terminal punctuation, targets Python `python_docstring` and
Rust `rust_doc_comment` regions for every recognized owner kind, including
anonymous owners. Inspect the first nonblank content line for Python, and the
first paragraph ending at a blank line for Rust. Trim analysis-only whitespace;
accept `.`, `!`, or `?` as the final visible character. This slice supports
plain-text summaries only: skip punctuation checking when the candidate
contains backticks, backslashes, square brackets, angle brackets, emphasis
markers, or double quotes, or any constituent line starts with a Markdown
heading, list marker, block quote, fenced block, thematic break, or doctest
prompt. Inspect each line after leading whitespace: recognize `#`, `>`,
backtick/tilde fences, `-`, `+`, `*`, decimal digits followed by `.` or `)`,
`>>>`, and lines consisting of at least three identical `-`, `_`, `*`, or `=`
characters. This intentionally conservative test is not a Markdown parser. Do
not skip the whole document's other rules. Explain these conservative
exclusions in user documentation. Report a missing terminator on the final
source-backed non-whitespace character of a supported summary; emit at most one
diagnostic per region. Empty content is skipped. This is punctuation policy,
not sentence segmentation.

`DOC003`, owner-only summary, targets Python class/function docstrings and Rust
named struct/enum/union/trait/function/const/static/type/macro documentation
comments. It warns when the trimmed summary is exactly the authoritative
`owner.name`, optionally followed by `()` for function owners and optionally a
single final period. Select the Python first nonblank line or Rust first
paragraph exactly as for DOC002; punctuation-specific exclusions do not apply
to DOC003. Thus Rust `Widget` followed by `stores records.` without a blank
line passes, while `Widget.` followed by a blank line and details warns.
Matching is case-sensitive and whole-summary, not a substring or qualified-name
guess. Anonymous, missing-owner, module, impl, and fallback item owners are
skipped. Thus a class `Widget` documented as `Widget.` warns;
`Widget stores records.` passes. Report on the first source-backed character of
the name. This uses metadata without claiming full signature or semantic
analysis. `DOC002` and `DOC003` may both report `Widget`; retain both
independent findings in the engine's established ordering.

Introduce a private summary-analysis helper only after checking
`python/stilyagi/rules/builtin/text.py` and related rule helpers for an
equivalent. Its sole responsibility is selecting candidate text ranges and
identifying supported forms while retaining offsets into unchanged region text.
Source mapping and reporting stay with the shared context. For Rust block
comments, do not strip decorative `*` prefixes or reparse Markdown: punctuation
checking skips these unsupported forms, and owner matching remains exact. If an
anchor cannot be mapped to a source-backed character, omit that finding; never
substitute a file-level location or synthetic separator. Use the diagnostic
API's half-open UTF-8 byte span for that one complete anchor character, not one
byte of a multibyte character. Point-only renderers use its start. Preserve the
existing 1-based byte-column contract; do not change renderer coordinate units
in this task. `diagnostics.Diagnostic.span` carries the accepted half-open
source span.

## Plan of work and milestones

### EP-M0: conform the rule projection to documentation targets

Start from merged 2.3.1 (`a6ba33a1985b75bdcd07513f1b9cffb2559a5d17`) and
confirm the existing Markdown starter pack through `run_rules`. Add only the
Python rule-facing extensions needed by 3.2.2: project the existing IR owner
into a typed owner value (`kind`, optional `name`, optional `qualname`) on
`RegionView`, and replace scalar `RegionTarget.syntax` with
`syntaxes: tuple[str, ...]` while adding `owner_kinds`. An empty owner-kind
tuple is unrestricted, including regions without owner metadata; a nonempty
tuple requires a present matching owner. Update every private caller and test
in the same change; do not add compatibility wrappers. Keep current Markdown
targets equivalent. Extractor IR and serialized schemas stay unchanged.

First write the narrow projection and target tests and run them red for the
missing fields and matching behaviour. Then implement the projection and target
changes, rerun those tests green, and refactor only while they remain green. Use
`tests/support/rule_fixtures.py::LintSetup` as the real registry harness;
extend its request helper with a syntax parameter if needed, since it currently
extracts Markdown only. Test owner projection and target matching with actual
Python and Rust extracted documents, including absent names, multi-syntax
targets, owner-kind exclusion, and unchanged Markdown dispatch. Verify the
existing extraction tests in `tests/test_python_docstring_extraction.py` and
`tests/test_rust_doc_comment_extraction.py` still pass. Acceptance A0 is the
existing Markdown workflow plus the new typed projection and target truth
table, with concrete references to the API paths above. R-REUSE is established
and R-SCOPE has explicit targeting primitives; the three rules remain for
EP-M1. Run `make check-fmt`, `make typecheck`, `make lint`, and `make test`
sequentially before committing this milestone. If owner projection requires new
extractor facts or a wire change, stop and request a design decision. Recovery
is a revert of this coherent private API change.

### EP-M1: deliver the complete rule policy

Create focused modules under `python/stilyagi/rules/builtin/` for documentation
summary analysis and the three rule declarations. Register them through the
existing `BuiltinRule` inventory and per-document hook contract. Each rule's
frozen config defaults to `enabled=False`; validate its `enabled` TOML value
even when policy ignores the rule. Its hook returns no findings unless enabled.
The default `DOC`/`PYDOC` selection prefixes remain unchanged. Shared policy
selection, plugin disablement, ignores, per-file ignores, and suppression keep
their existing precedence.

Write `tests/test_builtin_docstring_rules.py` and
`tests/test_builtin_docstring_properties.py` first, using the real registry
harness and actual syntax extraction. Observe the expected failures (missing
codes or missing findings), then implement the smallest policy and rerun.
Include a default-prefix run with absent and false per-rule opt-in (no DOC
findings), an enabled and selected run (findings), ignore/plugin suppression,
and malformed `enabled` validation even when ignored. Include both passing and
failing examples for every owner/syntax partition, multiline and blank inputs,
CR-LF, Unicode, unsupported Markdown, literal escapes, optional owner names,
owner names containing underscores, Unicode line separators, and independent
overlapping diagnostics. Include a Rust summary immediately followed by a
heading without a blank line as an explicit skip witness. Test policy
disablement and syntax/owner target matching through the shared dispatch rather
than calling private predicates alone. Extract helpers only after green tests.

Acceptance A1 is the finite rule matrix and invariants V1–V3 below passing,
including source locations on actual extracted Python/Rust fixtures. Run all
four major gates. This plateau provides all three usable diagnostic rules;
EP-M2 adds command-level assurance and delivery documentation. Check R-REUSE,
R-VALUE, R-SCOPE, and R-FIDELITY against the design contract and record whether
any assumption changed. Recovery is a revert of the single coherent milestone
commit. No compatibility aliases or parallel rule implementations are needed.

### EP-M2: prove mixed-tree delivery and close the roadmap item

Add `features/builtin_docstring_rules.feature` and
`tests/test_builtin_docstring_rules_bdd.py`, plus subprocess command tests in
`tests/test_builtin_docstring_cli.py`. Create a temporary tree with Markdown,
Python, Rust, ordinary comments, valid summaries, and invalid summaries. Enable
all three codes using each rule's validated opt-in configuration, then execute
`stilyagi check .` with the supported human and JSON renderers. Snapshot only
stable diagnostic records with normalized temporary paths, and assert codes,
severity, locations, ordering, and exit status separately. Confirm disabling
all three removes their diagnostics and preserves extractor diagnostics.

Reuse and extend existing Rust extractor `rstest` and `rstest-bdd` coverage to
show the owner and segment facts used by these policies survive extraction. Add
cases to existing test modules and fixtures, not a Rust copy of the Python
rules. Use `insta` only when a new stable owner/segment output boundary needs a
snapshot; Python diagnostic output uses `syrupy`. Add no Rust production logic
unless the approved plan is revised for a discovered contract gap.

Update `docs/users-guide.md` with codes, supported syntax/owner matrix, opt-in
configuration, examples, warning severity, no-fix status, and exclusions. Update
`docs/developers-guide.md` with rule authoring, helper reuse, target
selection, and source mapping conventions. Document internal boundaries in
`docs/stilyagi-design.md` §7.2 and reconcile its proposed status with delivery;
update `docs/repository-layout.md` if module responsibilities change. Update
`docs/contents.md` for any new document. Run every major gate plus
documentation gates, record evidence, mark only 3.2.2 `[x]` in
`docs/roadmap.md`, and commit.

Acceptance A2 is the command behaviour and BDD scenarios below, all gates
passing, and documentation matching observed behaviour. Reconcile all five
trace requirements and assumptions before COMPLETE. Recovery is to revert the
EP-M2 commit; EP-M1 remains usable. Do not mark adjacent roadmap tasks complete.

## Verification plan

V1, target confinement: dispatch visits only explicitly enabled matching
syntax/kind/owner tuples; Markdown, ordinary comments, and excluded owner kinds
never produce these codes. Use exhaustive finite pytest tables in
`tests/test_builtin_docstring_rules.py` and a Hypothesis property generating
owner names and irrelevant text in
`tests/test_builtin_docstring_properties.py`. Use actual matching Python and
Rust witnesses so the property cannot pass by skipping every input. A temporary
mutation disabling the entire declared target matcher must be rejected by a
negative case that would otherwise satisfy the rule predicate; removing syntax
alone is insufficient when region kind still filters the input. Record the
killed mutation and then revert it.

V2, source fidelity: every emitted diagnostic anchor maps to the specified
source-backed character inside its own documentation region, even with UTF-8
prefixes, CR-LF, indentation, or merged Rust line comments. Generate valid
Python/Rust fixture templates with Hypothesis, varying Unicode prefix and
summary content without rejection filters; assert both span boundaries and
compare source bytes at the mapped anchor against an independently computed
fixture position. Exercise synthetic separator and multibyte classes
explicitly. Reuse Rust `proptest` segment reconstruction coverage and add cases
only for newly exposed metadata paths. A character-index-for-byte-index
mutation must fail a multibyte witness. No generated sample is presented as an
exhaustive proof of parser correctness.

V3, determinism and immutability: repeated runs with equivalent enabled-rule
sets produce identical ordered diagnostics and leave IR and source unchanged.
Generate rule selection permutations and supported summary strings with
Hypothesis; compare independent runs through the registry. Include a witness
with both DOC002 and DOC003 diagnostics. A reversed rule-order mutation must
fail the expected order assertion. This concerns logical work proportional to
region text size, not a claim of measured performance improvement.

The intermediate contract is that summary analysis retains region-relative
positions and shared context maps them to source bytes. Test it at the real
extraction boundary, not through a mock of the same mapper. Trusted assumptions
are the documented tree-sitter/PyO3 interfaces, Python Unicode behaviour, and
the typed `RuleContext` contract in `python/stilyagi/rules/base.py`.
Third-party internals are not proof obligations; the repository-owned
integration is.

The intended implementation adds Python editorial predicates, no new Rust axiom
or contractual kernel requiring an unbounded proof. If source mapping or new
contractual business logic must be implemented, stop and revise the plan
jointly with verification: prefer a small pure Rust extension kernel and a
substantive Verus proof over all admissible inputs, plus executable integration
tests linking that kernel to the rule path. Identify trusted assumptions,
inhabited preconditions, and a faulty implementation rejected by the proof. Do
not add a proof that assumes its conclusion or a disconnected duplicate. A
bounded Kani or CrossHair check must state its bounds and residual gap and must
not be reported as an unbounded proof.

## Behavioural specification

The proposed `features/builtin_docstring_rules.feature` includes:

```gherkin
Feature: Builtin documentation rules share the mixed-source rule loop
  Scenario: Python summary requires a separator
    Given DOC001 is enabled for Python docstrings
    And a function docstring contains "Read records." followed by "More detail."
    When the mixed-source tree is checked
    Then DOC001 points to the start of "More detail."

  Scenario: Rust summary punctuation is source located
    Given DOC002 is enabled for Rust documentation comments
    And an item has the documentation comment "/// Read records"
    When the mixed-source tree is checked
    Then DOC002 points to the final "s" in "records"
    And no automatic fix is offered

  Scenario: Owner metadata distinguishes a redundant summary
    Given DOC003 is enabled
    And class Widget has the docstring "Widget."
    And class Other has the docstring "Widget."
    When the mixed-source tree is checked
    Then only the Widget docstring receives DOC003

  Scenario: Policy excludes ordinary comments and Markdown
    Given all three documentation rules are enabled
    And matching text occurs in Markdown and ordinary Python and Rust comments
    When the mixed-source tree is checked
    Then none of those surfaces receives a documentation rule diagnostic
```

Add scenarios for disabling a rule, Rust anonymous owners, a blank separator
passing, and mixed-tree ordering. Rust BDD covers extraction of source-backed
regions and owner identity from the same fixture corpus. It does not claim to
execute Python policy.

## Concrete steps and validation

Run from the repository root. Read the Makefile before using focused commands;
its `build` target prepares the native extension. After EP-M0 has supplied the
new test files, the focused commands are:

```sh
uv run pytest tests/test_builtin_docstring_rules.py
uv run pytest tests/test_builtin_docstring_properties.py
uv run pytest tests/test_builtin_docstring_rules_bdd.py
uv run pytest tests/test_builtin_docstring_cli.py
```

Capture each with `set -o pipefail` and a unique `/tmp` log when executing it.
Red evidence must show the intended absent behaviour, not an import/setup
failure. Green evidence must pass without expected-failure markers. Add exact
Rust test filters discovered in EP-M0 before execution; `make test` remains the
full cross-language verification authority.

At every major implementation milestone, delegate gates to `scrutineer` and run
sequentially, never as background jobs:

```sh
set -euo pipefail
evidence_dir=$(mktemp -d /tmp/stilyagi-322-EP-M1.XXXXXX)
make check-fmt 2>&1 | tee "$evidence_dir/check-fmt.out"
make typecheck 2>&1 | tee "$evidence_dir/typecheck.out"
make lint 2>&1 | tee "$evidence_dir/lint.out"
make test 2>&1 | tee "$evidence_dir/test.out"
make markdownlint 2>&1 | tee "$evidence_dir/markdownlint.out"
make nixie 2>&1 | tee "$evidence_dir/nixie.out"
```

The block stops at the first failing pipeline, including failures hidden by
`tee`; do not ignore exit status. Replace EP-M1 in the directory template with
the milestone being validated; each run creates fresh logs without overwriting
evidence. Run `make fmt` after documentation edits and inspect all resulting
diffs. Commit only the intended changes after gates pass. For this plan-only
PR, run documentation gates and formatting; the four code gates above remain
mandatory for each future implementation milestone.

Manual acceptance uses the same mixed-tree fixture and configuration as the
command test: explicit opt-in produces the three specified codes at exact
locations, default or false opt-in produces none, conforming examples do not
warn, policy ignores/plugins suppress findings, and repeated JSON output is
identical. Cover clean input, warning-only input (exit 0), error findings (exit
1), configuration/environment failures (exit 2), and malformed-source
diagnostics with rules enabled and disabled. Do not introduce a configurable
fail-on option; none exists in the current CLI contract.

## Skills and reference signposts

Load `codegraph-mcp` for semantic navigation, `hexagonal-architecture` for
inward dependency checks, and `python-router`/`rust-router` for language work.
Use their testing and verification routes only for the affected obligations. Use
`execplans` to maintain this document, `firecrawl-mcp` for external research,
and `logisphere-experts` for design review. Share cited code through
`context_pack` when delegating. Use Wyvern for read-only reconnaissance, Scribe
for bounded documentation work, and Scrutineer for sequential gates.

Read `docs/complexity-antipatterns-and-refactoring-strategies.md` before
introducing helpers; `docs/rust-testing-with-rstest-fixtures.md`,
`docs/rust-doctest-dry-guide.md`,
`docs/reliable-testing-in-rust-via-dependency-injection.md`, and
`docs/rstest-bdd-users-guide.md` before Rust test changes. Consult
`docs/documentation-style-guide.md` for prose and ADR structure, and
`docs/rfcs/rfc-0004-stilyagi-rule-testing-framework.md` as a proposal: do not
assume its test plugin exists until its actual runner is inspected. Follow
`.rules/` Python guidance and `docs/scripting-standards.md` if scripts become
necessary.

## Idempotence, recovery, and evidence

Tests use isolated temporary source trees and never modify checked-in fixtures
through a live fix command. Repeat checks freely; inspect and accept snapshots
only after semantic assertions pass. Keep each coherent milestone in a gated
commit, preserving pre-change Red logs and post-change Green logs. Recover with
a normal revert of owned commits, not a destructive reset of shared work. Keep
rule, documentation, and roadmap evidence tied to the exact validated commit.
Prerequisite and architecture deviations must be reconciled before feature
completion.

Revision note (2026-10-13): Initial plan records the then-missing prerequisite,
conservative policy contract, verification obligations, and staged delivery.
Community review clarified shared summary selection, per-line markup skips,
physical lines and Unicode spans, exit-status evidence, non-vacuous mutation
witnesses, and fail-fast milestone logging. No runtime scope was added.

Revision note (2026-11-16): Updated after rebasing onto
`b52ffc0c0cfe28bd0fb61e019568471112534b05` and confirming 2.3.1 merged as
`a6ba33a1985b75bdcd07513f1b9cffb2559a5d17` (PR #240). Replaced the obsolete
missing-substrate gate with EP-M0's bounded owner projection and multi-syntax
target extension; documented the actual private rule API, per-rule opt-in
required by default `DOC`/`PYDOC` selection, current CLI exits, canonical
reference paths, and current testing harness. PR #225 contains the planning
draft. The plan remains DRAFT; implementation and roadmap completion remain
approval- and evidence-gated.

Revision note (2026-11-22): Implementation delivered against baseline
`fc28da93080eb0b0bfd094de283f74dd53d62586`. EP-M0 and EP-M1 landed as one gated
commit, `8cf596b5`, after the whole gate chain passed; EP-M2 added the
mixed-tree BDD feature, the fresh-process CLI suite, one Rust extraction case,
and the user, developer, design, layout, and roadmap updates. Two deviations
are recorded in Outcomes: the `engine/region_views.py` extraction forced by the
file-size ceiling, and the two Python refactors the duplication gate required
instead of exceptions. The plan status is now IMPLEMENTED.
