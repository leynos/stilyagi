# Ratify the v1 syntax scope, IR transport, and locale policy

This ExecPlan (execution plan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises &
Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up
to date as work proceeds.

Status: DRAFT

Approval gate: pending. Do not begin implementation until the user explicitly
approves this plan.

## Purpose / big picture

Roadmap item 1.1.2 exists to settle the remaining v1 contract questions that
would otherwise keep rippling through every later slice. After this work is
complete, maintainers and early users should be able to point to one accepted
decision record and a small set of aligned guide updates that answer three
questions plainly:

- which syntaxes Stilyagi v1 formally supports, and which remain preview-only
  or deferred;
- whether JavaScript Object Notation (JSON) is the canonical debug and test
  form rather than the only in-process Rust-to-Python transport; and
- whether English-only support is the formal v1 locale policy.

The observable outcome is contractual clarity rather than new runtime
behaviour. A reviewer should be able to read the new ADR, the design document,
the developer's guide, the user's guide, and the roadmap together and see one
coherent v1 promise that matches [docs/stilyagi-design.md](../stilyagi-design.md)
§12's recommendation and §13's final recommendation.

## Orientation

Step 1.1.1 is already complete. [ADR 002](../adr-002-packaging-boundary.md)
freezes the packaging boundary and deliberately leaves the narrower syntax
scope, intermediate representation (IR) transport policy, and locale-policy
questions for this roadmap item.

The design document already points strongly toward the likely answers:

- v1 should keep Markdown with JSX (MDX) preview-only rather than promise it as
  a stable day-one syntax;
- JSON should remain the canonical debug, fixture, and contract format rather
  than the mandatory hot-path transport for every Rust-to-Python call; and
- English is the only locale with an explicit v1 performance and support story.

The complication is that the narrower contract documents do not yet all agree
with that design direction. [RFC 0001](../rfcs/0001-stilyagi-intermediate-representation.md)
still says JSON is the mandatory interchange contract, and
[RFC 0003](../rfcs/0003-stilyagi-cli-contract.md) still speaks about Markdown
and MDX together in places where the design now recommends MDX as
preview-only. That mismatch is expected to be cleaned up in roadmap item 1.1.3
instead of being silently folded into this slice.

This means the work here is not a broad rewrite. It is a ratification step:
record the accepted v1 promise in one place, align the governing design and
guide documents around it, and leave explicit breadcrumbs for the later RFC
amendment step.

## Documentation and skill signposts

The implementer should keep these documents open while executing the plan:

- [docs/roadmap.md](../roadmap.md) for the step definition, dependency on 1.1.1,
  and the final "done" update.
- [docs/stilyagi-design.md](../stilyagi-design.md), especially sections 7.1,
  12, and 13, for the current recommended answers and the final v1 promise that
  this slice must ratify.
- [docs/adr-002-packaging-boundary.md](../adr-002-packaging-boundary.md) for
  the accepted boundary this slice depends on and for ADR tone and structure.
- [docs/developers-guide.md](../developers-guide.md) for the maintainer-facing
  transport and syntax-boundary language that must become explicit.
- [docs/users-guide.md](../users-guide.md) for the current user-facing promise
  and the places where supported syntax and locale policy must be added.
- [docs/contents.md](../contents.md) and
  [docs/repository-layout.md](../repository-layout.md) for documentation-set
  bookkeeping when new ADRs and ExecPlans are added.
- [docs/documentation-style-guide.md](../documentation-style-guide.md) for
  sentence-case headings, British English, link style, and ExecPlan-adjacent
  documentation conventions.
- [docs/rfcs/0001-stilyagi-intermediate-representation.md](../rfcs/0001-stilyagi-intermediate-representation.md),
  [docs/rfcs/0002-stilyagi-python-rule-api.md](../rfcs/0002-stilyagi-python-rule-api.md),
  and [docs/rfcs/0003-stilyagi-cli-contract.md](../rfcs/0003-stilyagi-cli-contract.md)
  as the draft contracts that this slice must not contradict silently, even if
  their normative text is only amended in 1.1.3.
- [docs/complexity-antipatterns-and-refactoring-strategies.md](../complexity-antipatterns-and-refactoring-strategies.md)
  as a reminder to keep the contract story narrow and explicit rather than
  burying it in speculative prose.
- [docs/rust-testing-with-rstest-fixtures.md](../rust-testing-with-rstest-fixtures.md),
  [docs/rstest-bdd-users-guide.md](../rstest-bdd-users-guide.md),
  [docs/rust-doctest-dry-guide.md](../rust-doctest-dry-guide.md), and
  [docs/reliable-testing-in-rust-via-dependency-injection.md](../reliable-testing-in-rust-via-dependency-injection.md)
  for the validation standards later executable slices must follow, even though
  this documentation-first slice is not expected to introduce new runtime code.

The relevant skills for the person executing this plan are:

- `execplans` to keep this document current during implementation.
- `leta` if the work expands into symbol-level code inspection or a follow-on
  change unexpectedly touches source files.
- `rust-router`, then the relevant Rust sub-skill, only if the user approves a
  widened scope that changes Rust-owned transport or extraction behaviour.

## Constraints

- This slice is roadmap item "1.1.2 Record the v1 syntax-scope,
  intermediate-representation (IR) transport, and locale-policy decisions."
  Keep it narrower than roadmap items 1.1.3 and 1.2.x. Do not implement new
  extractor code, CLI behaviour, PyO3 transport surfaces, or repository-layout
  changes beyond documentation.
- The accepted v1 promise must match the current design's recommended
  direction unless new repository-local evidence proves the design is
  internally contradictory. If that contradiction appears, stop and escalate
  instead of improvising a new architecture.
- Record the three decisions together in one accepted ADR unless a specific,
  repository-local reason emerges that makes splitting them clearer. If the
  implementer believes multiple ADRs are necessary, stop and justify that
  change before proceeding because it materially changes the document set.
- The expected substance of the accepted contract is:
  - Markdown, Python docstrings, and Rust documentation comments are the stable
    v1 syntax surfaces;
  - MDX remains preview-only in v1;
  - JSON is the canonical debug, fixture, and compatibility representation for
    IR output, but not the only allowed in-process transport; and
  - English is the only formally supported v1 locale.
- Do not perform the broad RFC amendments allocated to roadmap item 1.1.3.
  Light cross-links or explicit "pending alignment" notes are acceptable; large
  normative rewrites are not.
- Treat this as a documentation-first change. Do not edit Rust or Python
  source, the Makefile, `pyproject.toml`, or CI workflows unless the user
  explicitly approves broader scope after a documented contradiction is found.
- Documentation must follow the repository style guide: sentence-case headings,
  British English, 80-column wrapping, and updated contents/index references.
- The roadmap item must not be marked done until the ADR, supporting
  documentation updates, and validation commands have all completed.

## Tolerances (exception triggers)

- Scope: if execution requires touching more than eight files, stop and explain
  why. The intended touch-set is one new ADR, this ExecPlan, `docs/roadmap.md`,
  and a small number of supporting documentation files.
- Interface: if the work appears to require any public command-line interface
  (CLI), Python API, Rust API, config-schema, or build-command change, stop
  and ask for confirmation because that is no longer a documentation-only
  ratification slice.
- Dependencies: if the work appears to need any new Rust crate, Python package,
  or documentation tool, stop and escalate.
- Evidence: if the current repository-local evidence cannot support a clear
  answer on any of the three contract questions, stop and present the missing
  evidence rather than guessing.
- Iterations: if validation still fails after two focused correction passes,
  stop and surface the failing output.
- Time: if the ADR and supporting guide updates cannot be drafted, aligned, and
  validated inside one focused working session, stop and document the blocker
  rather than padding the slice with speculative analysis.
- Ambiguity: if the user or reviewers interpret this slice as requiring live
  transport or locale prototypes, stop and request a scope decision because
  prototyping belongs in later roadmap work.

## Risks

- Risk: the generic implementation boilerplate in the task asks for new unit
  tests and behavioural tests, even though this roadmap step records
  documentation contracts rather than executable behaviour.
  Severity: high
  Likelihood: high
  Mitigation: treat this slice as documentation-first. Run the repository gate
  suite exactly as requested, but do not invent synthetic `rstest`,
  `rstest-bdd`, `pytest`, or `pytest-bdd` cases unless the work widens into
  real code changes. If real code changes become necessary, stop and request
  approval for the broader scope.

- Risk: the design document, RFCs, and guides do not yet all agree on MDX,
  JSON transport, or locale support, so this slice may temporarily increase the
  visible mismatch until roadmap item 1.1.3 lands.
  Severity: high
  Likelihood: high
  Mitigation: make the new ADR explicit about which RFCs still need
  follow-on alignment, and keep RFC edits intentionally narrow or absent in
  this slice.

- Risk: locale-policy wording could accidentally promise more than the product
  can support, especially if "English-only" is written imprecisely.
  Severity: medium
  Likelihood: medium
  Mitigation: use exact wording that distinguishes formal v1 support from
  future architecture readiness. The contract should say Stilyagi is designed
  so other locales can land later, but only English is supported and validated
  in v1.

- Risk: users' and developers' guides may drift into too much future-facing
  speculation while trying to explain syntax scope and transport policy.
  Severity: medium
  Likelihood: medium
  Mitigation: keep the guides focused on present guarantees, defaults, and
  explicit non-promises. Put design rationale in the ADR and design document,
  not in the operational guides.

- Risk: the roadmap step could be marked done before the validation gates prove
  the documentation set remains healthy.
  Severity: low
  Likelihood: medium
  Mitigation: treat the roadmap update as the final action after validation and
  document reread, not as an early bookkeeping change.

## Milestones

### Milestone 1: establish the evidence and contradiction set

Re-read the roadmap entry, design sections 7.1, 12, and 13, ADR 002, the
developer's guide, the user's guide, and the relevant RFC passages that still
disagree or remain ambiguous. Capture a short working matrix that answers:

1. what the design already recommends for syntax scope, transport, and locale;
2. which current documents still treat those questions as open or say
   something narrower or broader;
3. which parts of the user and maintainer guidance must change once the
   contract is accepted; and
4. which mismatches must be left for roadmap item 1.1.3 rather than "fixed"
   now.

At the end of this milestone, the implementer should be able to state the
three intended decisions and the minimum documentation touch-set needed to
ratify them.

### Milestone 2: draft the accepted ADR for the three remaining v1 contract decisions

Create the next sequential ADR under `docs/`. With ADR 002 already present,
the expected filename is `docs/adr-003-v1-contract-scope.md`. If another ADR
lands first, use the next free zero-padded number and update references
accordingly.

Write one accepted ADR that records the three decisions together because they
jointly define the remaining v1 contract boundary after packaging:

1. Syntax scope:
   - stable v1 extraction and linting promise covers Markdown, Python
     docstrings, and Rust documentation comments;
   - MDX remains preview-only and is not part of the stable day-one support
     promise.
2. IR transport policy:
   - the logical IR schema is the contract;
   - canonical JSON is required for `dump-ir`, golden fixtures, schema review,
     and compatibility checks;
   - Rust-to-Python hot-path calls may use a more efficient in-process
     transport than JSON.
3. Locale policy:
   - English is the only formally supported locale in v1;
   - architecture keeps explicit locale and natural-language fields so later
     locales can land without redesign;
   - broader locale support is deferred rather than implied as best-effort.

The ADR should also spell out why these choices belong together: they define
what v1 promises to parse, how the extractor contract is inspected, and which
natural-language assumptions the first supported rule slices may rely on.

### Milestone 3: align the governing documents around the accepted v1 promise

Once the ADR exists, update the surrounding documents that must stop treating
these questions as unresolved:

- `docs/stilyagi-design.md`
  - Update section 12 so the three questions are no longer listed as unresolved
    "must resolve before implementation" items.
  - Update section 13 and any relevant earlier wording so the final
    recommendation clearly matches the accepted syntax, transport, and locale
    policy.
  - Add direct references to the new ADR where that helps maintainers find the
    normative decision quickly.
- `docs/developers-guide.md`
  - Make the maintainer contract explicit: stable v1 syntax scope,
    JSON-as-canonical-debug-form, non-JSON hot-path transport allowance, and
    English-only formal support.
  - Add a short note that RFC alignment remains a follow-on step in 1.1.3.
- `docs/users-guide.md`
  - Record the user-visible promise about supported syntax surfaces and the
    English-only v1 support boundary.
  - Explain that MDX is preview-only rather than part of the stable support
    matrix.
  - Keep the explanation user-facing; do not bury it in internal transport
    terminology unless the distinction matters for `dump-ir` or debugging.
- `docs/contents.md`
  - Add the new ADR and this ExecPlan entry if missing.
- `docs/repository-layout.md`
  - Update only if the documentation subtree explanation would otherwise be
    stale or misleading after the new ADR is added.

Do not perform the substantive RFC rewrites in this milestone. If the
implementer adds any cross-links or caveat notes, they should explicitly point
to roadmap item 1.1.3 as the normative alignment step.

### Milestone 4: validate, mark completion, and freeze the slice

Validation for this slice is repository health plus documentary coherence. Run
the repository checks sequentially, never in parallel, and capture logs with
`tee` under `/tmp/` so failures remain inspectable even when command output is
truncated.

The canonical validation sequence is:

```bash
branch_slug=$(git branch --show-current | tr '/' '_')
make markdownlint 2>&1 | tee /tmp/markdownlint-stilyagi-${branch_slug}.out
make nixie 2>&1 | tee /tmp/nixie-stilyagi-${branch_slug}.out
make check-fmt 2>&1 | tee /tmp/check-fmt-stilyagi-${branch_slug}.out
make lint 2>&1 | tee /tmp/lint-stilyagi-${branch_slug}.out
make test 2>&1 | tee /tmp/test-stilyagi-${branch_slug}.out
```

After the gates pass:

1. Update `docs/roadmap.md` so item 1.1.2 is marked done.
2. Re-read the ADR, design references, guide updates, and roadmap entry
   together to ensure they now tell one story.
3. Update this ExecPlan's living sections with what actually happened.

The slice is complete when a reviewer can verify all of the following:

- one accepted ADR records the v1 syntax-scope, transport, and locale
  decisions;
- the design, user's guide, and developer's guide all state the same v1
  promise;
- the documentation explicitly keeps MDX preview-only, JSON canonical but not
  mandatory as the only hot-path transport, and English as the only supported
  v1 locale;
- the roadmap item is marked done; and
- the validation commands above have passed.

## Concrete execution notes

Keep the accepted ADR narrow. It should not try to pre-solve the detailed
owner-metadata shape, cache encoding, or grammar-debug schema that the design
explicitly leaves for later.

Use direct, user-verifiable wording in the guides. For example, "Stilyagi v1
supports Markdown, Python docstrings, and Rust documentation comments" is
better than "Stilyagi narrows its extractor promise to a constrained
multi-surface corpus."

If execution exposes stale RFC language that would actively mislead a user or
maintainer after this slice lands, prefer adding an explicit note or
cross-reference rather than rewriting the RFC deeply. The point of the slice is
to ratify the answer, not to collapse 1.1.2 and 1.1.3 into one oversized
documentation edit.

If the repository gate suite fails before any documentation edits are made,
record that baseline failure in `Decision Log` and stop. This slice cannot be
claimed complete without clean validation evidence.

## Progress

- [x] 2026-04-20 00:00Z: Reviewed the roadmap entry, design sections 7.1, 12,
  and 13, ADR 002, the developer's guide, the user's guide, RFC 0001, RFC
  0002, RFC 0003, the Makefile, and the documentation style guide to draft
  this plan.
- [x] 2026-04-20 00:00Z: Identified the main contradiction set that this slice
  must narrow without overreaching: the design already recommends MDX
  preview-only and JSON as canonical debug output, while RFC 0001 and RFC 0003
  still need later alignment.
- [x] 2026-04-20 00:00Z: Wrote this draft plan to
  `docs/execplans/1-1-2-record-the-v1-syntax-scope.md` and updated
  `docs/contents.md` so the new ExecPlan is discoverable from the
  documentation index.
- [x] 2026-04-20 00:00Z: Validated the planning change with `make markdownlint`,
  `make nixie`, `make check-fmt`, `make lint`, and `make test`, with logs
  written under `/tmp/*-stilyagi-feat_plan-v1-syntax-scope.out`.
- [ ] Await explicit user approval before implementation begins.

## Surprises & Discoveries

- `docs/users-guide.md` already exists because roadmap item 1.1.1 created a
  minimal user-facing packaging guide, so this slice can extend that document
  rather than creating it from scratch.
- The design document is materially ahead of the RFC set on these three
  questions. This slice therefore needs to ratify the design's narrower v1
  promise while leaving visible evidence that 1.1.3 still matters.
- The current repository already tells most of the packaging story, but not yet
  the supported syntax matrix or formal locale policy. Those gaps are what make
  this slice user-visible even though it is still documentation-first.
- Even though this turn only writes a plan, the repository gate suite already
  passes cleanly on the branch, so later implementation work can treat current
  failures as regressions rather than inherited baseline noise.

## Decision Log

- 2026-04-20: Treat roadmap item 1.1.2 as a documentation-first contract
  ratification slice rather than an implementation spike.
  Rationale: the roadmap success criterion is a recorded decision set that
  aligns the v1 promise before later feature work depends on it.

- 2026-04-20: Plan for one ADR that records syntax scope, transport policy, and
  locale policy together.
  Rationale: after ADR 002 fixed the packaging boundary, these three remaining
  decisions jointly define the rest of the v1 contract surface described in
  design section 12.

- 2026-04-20: Treat the test requirement for this slice as repository-gate
  execution rather than new unit or behavioural test authoring.
  Rationale: documentation changes alone do not create new executable
  behaviour. If execution uncovers code changes, that is a scope expansion and
  should be approved explicitly.

- 2026-04-20: Defer substantive RFC amendments to roadmap item 1.1.3.
  Rationale: the roadmap already allocates that work to a dedicated alignment
  step, and merging the two slices would blur the completion criteria.

## Outcomes & Retrospective

Not started. Update this section after implementation, validation, and the
roadmap "done" transition have completed.
