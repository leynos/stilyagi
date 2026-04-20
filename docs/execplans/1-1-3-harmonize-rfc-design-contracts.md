# Harmonize the RFC set with the ratified v1 contracts

This ExecPlan (execution plan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work
proceeds.

Status: COMPLETE

Approval gate: approved by the user on 2026-04-20. Implementation may proceed
within the constraints and tolerances recorded here.

## Purpose / big picture

Roadmap item 1.1.3 exists to remove the last contract mismatch between the
normative design and the narrower RFC set. After this work is complete,
maintainers should be able to read the design document, ADR 002, ADR 003, and
RFCs 0001, 0002, 0003, and 0005 without having to guess which document is stale.

The observable outcome is documentary coherence, not new runtime behaviour. A
reviewer should be able to trace one consistent v1 promise across the IR
contract, the Python rule API, the CLI contract, and the grammar-extension
plan. The key harmonization points are the design's `syntax` terminology,
`RegionTarget` primacy, trimmed v1 discovery scope, preview-only MDX, the
canonical-JSON-versus-hot-path distinction, and the staged grammar-node plan.

## Orientation

The prerequisite decisions are already ratified.
[ADR 002](../adr-002-packaging-boundary.md) fixes the build and runtime
boundary as one Python package with an embedded PyO3 extension built through
`maturin`. [ADR 003](../adr-003-v1-contract-scope.md) narrows the stable v1
promise to Markdown, Python docstrings, and Rust documentation comments; keeps
MDX preview-only; keeps canonical JSON for `dump-ir`, fixtures, and contract
review; and limits formal locale support to English.

The design document already treats those decisions as normative. Section 7 of
[docs/stilyagi-design.md](../stilyagi-design.md) calls out the remaining
weaknesses in RFCs 0001, 0002, 0003, and 0005, and section 12 now lists the
packaging, syntax-scope, transport, and locale questions as resolved.

This step must therefore be a contract-alignment pass, not a feature
implementation pass. It should amend RFC text so that the narrower contracts
match the already-ratified architecture. It must not quietly expand the v1
surface, start the mixed-package skeleton from roadmap item 1.2, or implement
runtime behaviour under the cover of documentation cleanup.

## Documentation and skill signposts

The implementer should keep these documents open while executing the plan:

- [docs/roadmap.md](../roadmap.md) for the step definition, dependency on 1.1.1
  and 1.1.2, and the final "done" update.
- [docs/stilyagi-design.md](../stilyagi-design.md), especially sections 7.1,
  7.2, 7.3, 12, and 13, for the exact contract revisions that the RFCs now need
  to absorb.
- [docs/adr-002-packaging-boundary.md](../adr-002-packaging-boundary.md) and
  [docs/adr-003-v1-contract-scope.md](../adr-003-v1-contract-scope.md) for the
  accepted packaging, syntax-scope, transport, and locale decisions that now
  outrank the older RFC wording.
- the four primary amendment targets for this slice:
  - [docs/rfcs/0001-stilyagi-intermediate-representation.md](
    ../rfcs/0001-stilyagi-intermediate-representation.md)
  - [docs/rfcs/0002-stilyagi-python-rule-api.md](
    ../rfcs/0002-stilyagi-python-rule-api.md)
  - [docs/rfcs/0003-stilyagi-cli-contract.md](
    ../rfcs/0003-stilyagi-cli-contract.md)
  - [docs/rfcs/0005-grammar-capability-and-syntactic-api-extensions.md](
    ../rfcs/0005-grammar-capability-and-syntactic-api-extensions.md)
- [docs/users-guide.md](../users-guide.md) and
  [docs/developers-guide.md](../developers-guide.md) for user-facing and
  maintainer-facing contract statements that may need small cleanups once the
  RFC text is aligned.
- [docs/documentation-style-guide.md](../documentation-style-guide.md) for
  sentence-case headings, British English, wrapping, and link conventions.
- [docs/contents.md](../contents.md) for documentation-set bookkeeping when
  adding this ExecPlan and any further document references.
- [docs/complexity-antipatterns-and-refactoring-strategies.md](
  ../complexity-antipatterns-and-refactoring-strategies.md) as a reminder to
  keep the amendments direct and local rather than sprawling into speculative
  redesign prose.
- [docs/rust-testing-with-rstest-fixtures.md](
  ../rust-testing-with-rstest-fixtures.md) for the repository's testing
  expectations if the scope widens beyond documentation.
- [docs/rstest-bdd-users-guide.md](../rstest-bdd-users-guide.md) for the
  repository's behavioural-test expectations if the scope widens beyond
  documentation.
- [docs/rust-doctest-dry-guide.md](../rust-doctest-dry-guide.md) for the
  repository's doctest guidance if the scope widens beyond documentation.
- [docs/reliable-testing-in-rust-via-dependency-injection.md](
  ../reliable-testing-in-rust-via-dependency-injection.md) for the repository's
  dependency-injection testing guidance if the scope widens beyond
  documentation.

The relevant skills for the person executing this plan are:

- `execplans` to keep this document current during execution.
- `leta` if the work unexpectedly expands into code or symbol-level
  repository inspection.
- `rust-router`, then the relevant Rust sub-skill, only if the user approves a
  widened scope that changes Rust-owned contracts or examples.
- `arch-crate-design` only if contradictions in the RFCs unexpectedly force a
  rethink of public crate or package boundaries, which would exceed this
  roadmap step.

## Constraints

- This slice is roadmap item "1.1.3 Amend RFC 0001, RFC 0002, RFC 0003, and
  RFC 0005 so the design and the narrower contracts agree." Keep it narrower
  than roadmap items 1.2.x and 2.x. Do not implement bridge code, extractor
  code, CLI behaviour, repository reshaping, or new package structure here.
- Treat [docs/stilyagi-design.md](../stilyagi-design.md), ADR 002, and ADR 003
  as the normative contract sources. If an RFC appears to conflict with those
  documents, the RFC should be amended unless fresh repository-local evidence
  proves the design is internally contradictory. If such a contradiction is
  found, stop and escalate instead of improvising a new contract.
- Amend only RFC 0001, RFC 0002, RFC 0003, RFC 0005, and the minimum
  supporting documentation needed to keep the repository coherent. Avoid
  opportunistic rewrites of unrelated design sections, guides, or roadmap
  phases.
- Preserve the accepted v1 scope:
  - stable v1 syntax surfaces are Markdown, Python docstrings, and Rust
    documentation comments;
  - MDX remains preview-only;
  - canonical JSON is required for debug, fixture, and compatibility flows,
    but is not the only allowed in-process Rust-to-Python transport; and
  - English is the only formally supported v1 locale.
- The expected RFC amendments include:
  - RFC 0001: align source-syntax naming to `syntax`, separate
    `natural_language` from source syntax, make `owner` metadata explicit for
    docstrings and comments, keep `summary_line` out of the extractor-level
    region vocabulary, and treat canonical JSON as serialization rather than
    mandatory hot-path transport.
  - RFC 0002: make `RegionTarget` the primary v1 targeting surface, narrow
    `NodeRef` and `NodeTarget` guarantees for non-Markdown trees, add owner and
    locale convenience surfaces, and make rule ordering or fix-conflict
    semantics explicit where the design already requires them.
  - RFC 0003: trim v1 default discovery to `*.md`, `*.py`, and `*.rs`; keep
    MDX preview-only rather than part of the stable default surface; and align
    wording with the narrower `syntax` terminology and canonical-JSON story.
  - RFC 0005: stage the grammar-node rollout so `TokenNode`, `SentenceNode`,
    and the low-level normalized grammar surface land before higher-order
    `NounPhraseNode`, `ClauseNode`, and `CoordinationNode` guarantees.
- Treat this as a documentation-first change. Do not edit Rust or Python
  source files, the Makefile, `pyproject.toml`, CI workflows, or packaging
  metadata unless the user explicitly approves broader scope after a documented
  contradiction is found.
- Documentation must follow the repository style guide: sentence-case
  headings, British English, 80-column wrapping, and updated contents/index
  references.
- The roadmap item must not be marked done until the RFC amendments, any
  necessary guide or design updates, and the requested validation commands have
  all completed successfully.

## Tolerances (exception triggers)

- Scope: if execution requires touching more than nine files, stop and explain
  why. The intended touch-set is the four RFCs, this ExecPlan,
  `docs/roadmap.md`, and a small number of supporting documents such as the
  guides or contents file.
- Interface: if the work appears to require changing any implemented CLI,
  Python API, Rust API, config schema, or PyO3 boundary rather than only the
  documented contract, stop and ask for confirmation because that is no longer
  a documentation-only harmonization step.
- Dependencies: if the work appears to need any new Rust crate, Python
  package, documentation dependency, or build tool, stop and escalate.
- Evidence: if the repository-local sources do not provide a clear answer on a
  target amendment, stop and present the specific ambiguity rather than
  guessing.
- Iterations: if validation still fails after two focused correction passes,
  stop and surface the failing output and affected files.
- Time: if the amendment pass cannot be completed, reviewed, and validated in
  one focused working session, stop and document the blocker rather than
  padding the slice with speculative contract language.
- Ambiguity: if reviewers want this slice to settle fresh design questions
  beyond the already-ratified ADRs and design recommendations, stop and ask
  whether a new ADR or a broader roadmap step is required.

## Risks

- Risk: the task boilerplate asks for unit tests, behavioural tests, guide
  updates, and successful repository gates even though this roadmap step is
  expected to be documentation-first. Severity: high Likelihood: high
  Mitigation: treat executable test additions as conditional. If the work
  remains pure documentation, record that no runtime surface changed and do not
  invent synthetic `rstest`, `rstest-bdd`, `pytest`, or `pytest-bdd` cases.
  Still run the requested repository gates so the documentation change lands in
  a healthy tree. If the scope widens into real code or test-fixture changes,
  follow red-green-refactor and add the required tests first.

- Risk: RFC 0005 contains more speculative future surface than the design wants
  to guarantee in wave one, so "alignment" could accidentally become a large
  redesign. Severity: high Likelihood: medium Mitigation: keep the change
  focused on staged guarantees rather than total rewrite. Preserve
  future-facing material where it is clearly labelled as later-wave or reserved
  work.

- Risk: wording changes in RFC 0001 and RFC 0002 could accidentally create a
  new public contract rather than restating the already-ratified one. Severity:
  medium Likelihood: medium Mitigation: check every normative change against
  section 7 of the design and ADR 003. If a change cannot be traced back to
  those sources, either justify it in the Decision Log and update the design or
  remove it.

- Risk: `docs/users-guide.md` may not need a material update because it already
  matches ADR 003, but the task still requests guide maintenance. Severity:
  medium Likelihood: high Mitigation: verify both guides explicitly. Update
  whichever guide benefits from the RFC-alignment result, and record in the
  Decision Log if one guide remains unchanged because no user-facing or
  maintainer-facing promise changed.

- Risk: the roadmap entry could be marked done before the repository reflects
  that the RFCs are now aligned. Severity: low Likelihood: medium Mitigation:
  treat the roadmap update as the final content change after the RFCs and
  supporting documents are re-read and the validation suite passes.

## Milestones

### Milestone 1: build the contradiction matrix

Re-read the roadmap entry, design sections 7.1 to 7.3, sections 12 and 13, ADR
002, ADR 003, the current guides, and the four target RFCs. Capture a short
working matrix that answers:

1. which design or ADR statements each RFC must now mirror;
2. which RFC clauses are currently broader, ambiguous, or stale;
3. which supporting documents still mention pending RFC alignment; and
4. which items are true contract mismatches versus merely future-facing detail.

At the end of this milestone, the implementer should have a file-by-file list
of planned amendments rather than a generic goal to "make them agree."

### Milestone 2: amend RFC 0001 and RFC 0002 around the v1 core contract

Edit RFC 0001 so its normative language matches the accepted v1 extractor
contract. The finished text should make `syntax` the source-language field,
keep `natural_language` distinct, describe `owner` metadata for docstrings and
comments, keep `summary_line` as an analysis-layer view rather than a base
extractor region kind, and describe JSON as the canonical serialized form
without forcing it as the only in-process transport.

Edit RFC 0002 so the rule API matches the narrowed v1 surface. `RegionTarget`
should read as the primary v1 targeting mechanism, while `NodeRef` and
`NodeTarget` remain available only with narrower guarantees, especially for
non-Markdown source trees. The RFC should also make owner or locale
conveniences and deterministic conflict behaviour explicit where the design
already expects them.

Acceptance for this milestone is documentary: a reviewer can read RFC 0001 and
RFC 0002 beside design sections 7.1 and 7.2 without having to mentally subtract
stale promises.

### Milestone 3: amend RFC 0003 and RFC 0005 around the staged v1 surface

Edit RFC 0003 so the CLI contract reflects the accepted v1 scope. Default
discovery should cover `*.md`, `*.py`, and `*.rs`. MDX should be described as
preview-only rather than a stable default surface. Any remaining wording that
uses `language` when it really means source syntax should be tightened to match
the design's terminology. The RFC should remain clear that canonical JSON is
the stable machine-readable output and debug form, without reintroducing the
claim that JSON is the only in-process engine transport.

Edit RFC 0005 so its public promises are clearly phased. The first guaranteed
wave should centre on `TokenNode`, `SentenceNode`, low-level normalized enums
and morphology access, and capability-planned grammar access. Higher-order
helpers such as `NounPhraseNode`, `ClauseNode`, `CoordinationNode`, and pattern
surfaces should remain documented as later-wave work rather than v1 facts.

Acceptance for this milestone is that RFC 0003 reads like design section 7.3,
and RFC 0005 reads like the staged grammar rollout described in design section
7.2 and final recommendation section 13.

### Milestone 4: align supporting documents and finish the bookkeeping

After the RFCs are amended, re-read the developer's guide, the user's guide,
the design document, and the contents index.

Make only the minimum supporting changes needed:

1. remove stale notes that say RFC alignment is still pending if that note is
   no longer true;
2. add any design-document clarification only if the RFC work revealed a
   genuinely new decision that was not already captured in the design or ADRs;
3. update the contents file for any new or renamed documentation references;
   and
4. mark roadmap item 1.1.3 as done only after the whole contract set is
   aligned and validated.

Acceptance for this milestone is that a newcomer can navigate the design, ADRs,
RFCs, roadmap, and guides without hitting a visible contradiction about v1
scope.

## Validation

Validation should stay sequential so the repository benefits from build caches
and the command logs remain easy to inspect. The implementer should use `tee`
for each step and review the saved logs before committing.

Run the documentation-first validation steps after editing:

```plaintext
make fmt | tee /tmp/fmt-stilyagi-1-1-3-harmonize-rfc-design-contracts.out
make markdownlint | tee /tmp/markdownlint-stilyagi-1-1-3-harmonize-rfc-design-contracts.out
make nixie | tee /tmp/nixie-stilyagi-1-1-3-harmonize-rfc-design-contracts.out
```

Run the requested broader repository gates before marking the roadmap done or
committing the implementation:

```plaintext
make check-fmt | tee /tmp/check-fmt-stilyagi-1-1-3-harmonize-rfc-design-contracts.out
make lint | tee /tmp/lint-stilyagi-1-1-3-harmonize-rfc-design-contracts.out
make test | tee /tmp/test-stilyagi-1-1-3-harmonize-rfc-design-contracts.out
```

If the implementation unexpectedly changes executable code or test fixtures,
add and run the relevant `rstest`, `rstest-bdd`, `pytest`, and `pytest-bdd`
coverage first, following the repository's red-green-refactor guidance. In the
expected documentation-only path, record explicitly that no runtime behaviour
changed and therefore no new executable tests were warranted.

## Commit and review strategy

Keep commits small and ordered. The preferred implementation sequence is:

1. one commit for the RFC harmonization itself;
2. one follow-up commit only if a separate supporting-document cleanup or
   narrow refactor is genuinely clearer on its own.

Each commit must pass the relevant validation before it is created. If the work
remains documentation-only, do not invent extra commits merely to mirror the
number of RFC files touched.

## Progress

- [x] 2026-04-20 18:32 CEST: gathered the roadmap, design, ADR, guide, and RFC
  sources needed to draft this plan.
- [x] 2026-04-20 18:49 CEST: identified the main RFC mismatches around
  `syntax` naming, `RegionTarget`, discovery scope, canonical JSON wording, and
  the staged grammar-node rollout.
- [x] 2026-04-20 19:08 CEST: drafted this ExecPlan, indexed it in
  [docs/contents.md](../contents.md), and ran `make fmt`, `make markdownlint`,
  `make nixie`, `make check-fmt`, `make lint`, and `make test` successfully for
  the planning change.
- [x] 2026-04-20 20:01 CEST: user approved the ExecPlan and execution started.
- [x] 2026-04-20 20:08 CEST: completed the contradiction matrix for RFC 0001,
  RFC 0002, RFC 0003, and RFC 0005. The remaining amendments are limited to
  `syntax` naming, `RegionTarget` primacy, owner and locale conveniences,
  trimmed discovery scope, canonical JSON wording, and explicit grammar-wave
  staging.
- [x] 2026-04-20 20:21 CEST: amended RFC 0001, RFC 0002, RFC 0003, and
  RFC 0005 so they now match the ratified v1 contract around `syntax`
  terminology, `RegionTarget` primacy, narrowed discovery scope, JSON
  serialization policy, and staged grammar guarantees.
- [x] 2026-04-20 20:21 CEST: updated the user and developer guides with the
  user-visible discovery narrowing and the maintainer-facing rule-targeting
  guidance that follow from the RFC changes.
- [x] 2026-04-20 20:29 CEST: ran `make fmt`, `make markdownlint`,
  `make nixie`, `make check-fmt`, `make lint`, and `make test` successfully,
  then marked roadmap item 1.1.3 done.

## Surprises & discoveries

- The guides already reflect ADR 003 more accurately than the RFC set does.
  That means the likely support-document work is cleanup and deconfliction, not
  fresh user-facing contract drafting.
- [docs/developers-guide.md](../developers-guide.md) still contains an explicit
  note that RFC 0001 needs wording alignment in roadmap item 1.1.3. That note
  is a good post-amendment cleanup target.
- The current working tree still contains unrelated uncommitted edits in
  [docs/stilyagi-design.md](../stilyagi-design.md), the ADRs, and earlier
  ExecPlans. This implementation should avoid broadening into those files
  unless a contradiction makes that unavoidable.
- The design document already carried the normative answers needed for this
  slice. The implementation therefore stayed out of
  [docs/stilyagi-design.md](../stilyagi-design.md) instead of mixing new RFC
  alignment with the unrelated pre-existing design edits in the working tree.

## Decision log

- 2026-04-20 18:49 CEST: treated this roadmap step as documentation-first
  contract harmonization rather than executable feature work, because the
  design and both accepted ADRs already settle the intended v1 answers.
- 2026-04-20 18:49 CEST: included the user-requested repository gates in the
  validation section, but made new executable tests conditional on actual code
  or behaviour changes because this slice is expected to amend contracts only.
- 2026-04-20 20:08 CEST: chose a minimal support-document touch-set of
  `docs/users-guide.md`, `docs/developers-guide.md`, and `docs/roadmap.md`
  alongside the four RFCs and this ExecPlan. The design document already
  contained the normative decisions needed for alignment, and updating it would
  have pulled in unrelated pre-existing edits.
- 2026-04-20 20:21 CEST: kept the implementation documentation-only. The RFCs
  and guides changed the stated contract, but no runtime behaviour or test
  fixture changed, so no new `rstest`, `rstest-bdd`, `pytest`, or `pytest-bdd`
  cases were warranted for this slice.
- 2026-04-20 20:40 CEST: normalized the ExecPlan wording to en-GB-oxendict
  `harmonize` / `harmonization` spellings so the plan matches the branch and
  contents naming already used for this slice.
- 2026-04-20 20:52 CEST: applied review follow-ups to RFC 0001 only where the
  findings were still true in the current text. The follow-up clarifies the v1
  `natural_language` policy as `en`-only, narrows `owner` to code entities
  only, and adds short accessibility-oriented descriptions before the complex
  JSON examples.

## Outcomes & retrospective

The repository now has one coherent documented v1 contract set.

RFC 0001 now uses `syntax` and `natural_language` terminology, makes owner
metadata explicit, removes `summary_line` from the base region vocabulary, and
describes canonical JSON as the required serialized and debugging format rather
than the only in-process transport. The follow-up review pass also makes the
RFC 0001 `natural_language` contract explicitly `en`-only for v1, narrows
`owner` to code-entity metadata, and adds short prose descriptions before the
large JSON examples. RFC 0002 now makes `RegionTarget` the primary stable v1
target, narrows non-Markdown node guarantees, adds owner and locale convenience
surfaces, and spells out deterministic rule and fix behaviour. RFC 0003 now
narrows stable discovery to `*.md`, `*.py`, and `*.rs`, keeps MDX preview-only,
adds `--no-cache`, and describes `dump-ir` as canonical JSON. RFC 0005 now
states the grammar rollout in two explicit waves, keeping `TokenNode` and
`SentenceNode` first and higher-order helpers later.

Supporting documentation changed only where the repository contract would have
remained visibly stale. The user's guide now records the narrowed default
discovery set. The developer's guide now removes the "RFC wording still
pending" note and records `RegionTarget` primacy and the narrowed non-Markdown
node promise. The roadmap marks item 1.1.3 complete.

Validation proved the documentation-only implementation landed in a healthy
tree. The following commands all succeeded:

- `make fmt`
- `make markdownlint`
- `make nixie`
- `make check-fmt`
- `make lint`
- `make test`

The main lesson for roadmap item 1.2 is that the design and ADRs were already
specific enough to drive the narrower contract set. The implementation work was
therefore mostly subtraction and clarification, not fresh architecture design.
