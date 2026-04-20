# Ratify the packaging boundary with an accepted ADR

This ExecPlan (execution plan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises &
Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up
to date as work proceeds.

Status: COMPLETE

Approval gate: satisfied on 2026-04-20 when the user explicitly approved
implementation of this plan.

## Purpose / big picture

Step 1.1.1 in [docs/roadmap.md](../roadmap.md) exists to remove the packaging
question that would otherwise churn every later slice. After this work is
complete, maintainers should be able to point to one accepted Architecture
Decision Record (ADR) that states, in plain language, whether Stilyagi v1 ships
as a Python package with an in-process PyO3 extension built by `maturin`, or
whether it crosses the Rust and Python boundary through a helper binary.

The observable outcome is documentation, not new runtime behaviour. A reviewer
should be able to open the ADR, the design document, the developer's guide, and
the roadmap and see one coherent story: Stilyagi's build and runtime boundary
is fixed for v1, helper-binary transport is either rejected or explicitly
deferred, and later roadmap items can build on that decision without re-opening
the packaging debate.

## Orientation

The current repository already leans strongly toward the PyO3 plus `maturin`
path. `docs/stilyagi-design.md` recommends that architecture in its executive
summary, stack, repository-layout section, and final recommendation. The
current [Makefile](../../Makefile) uses `maturin develop` for `make build` and
`maturin build` for `make release`. The current
[docs/developers-guide.md](../developers-guide.md) already documents a PyO3
extension crate under `rust_extension/`.

That means this slice is not a green-field architecture search. It is a
ratification step that must convert a strong recommendation into an accepted
decision record and align the surrounding maintainer documentation. The plan
must keep that scope narrow so the work does not accidentally turn into step
1.2.x, which is where mixed-package skeleton and bridge implementation belong.

## Documentation and skill signposts

The implementer should keep these documents open while executing the plan:

- [docs/roadmap.md](../roadmap.md) for the step definition and final "done"
  update.
- [docs/stilyagi-design.md](../stilyagi-design.md), especially sections 7.1,
  10, 11, 12, and 13, for the current recommendation, open-question framing,
  repository shape, and validation expectations.
- [docs/developers-guide.md](../developers-guide.md) for the current
  build-boundary language that must be aligned with the ADR.
- [docs/documentation-style-guide.md](../documentation-style-guide.md) for ADR,
  guide, and contents-file conventions.
- [docs/contents.md](../contents.md) and
  [docs/repository-layout.md](../repository-layout.md) for documentation-set
  bookkeeping when new files or subtrees are introduced.
- [docs/adr-001-spell-checking-provider.md](../adr-001-spell-checking-provider.md)
  as the existing ADR shape to follow.
- [docs/rfcs/0001-stilyagi-intermediate-representation.md](../rfcs/0001-stilyagi-intermediate-representation.md),
  [docs/rfcs/0003-stilyagi-cli-contract.md](../rfcs/0003-stilyagi-cli-contract.md),
  and [docs/rfcs/0004-stilyagi-rule-testing-framework.md](../rfcs/0004-stilyagi-rule-testing-framework.md)
  as upstream contracts that the ADR must not contradict.
- [docs/rust-testing-with-rstest-fixtures.md](../rust-testing-with-rstest-fixtures.md),
  [docs/rstest-bdd-users-guide.md](../rstest-bdd-users-guide.md), and
  [docs/reliable-testing-in-rust-via-dependency-injection.md](../reliable-testing-in-rust-via-dependency-injection.md)
  for the testing standards that later implementation slices must follow, even
  though this ADR-only slice should not introduce new executable behaviour.
- [docs/complexity-antipatterns-and-refactoring-strategies.md](../complexity-antipatterns-and-refactoring-strategies.md)
  as a reminder to keep any supporting prose or examples straightforward rather
  than burying the decision in a sprawling discussion.

The relevant skills for the person executing this plan are:

- `execplans` to keep this document current as execution progresses.
- `leta` if the work unexpectedly expands into code or symbol-level repository
  inspection.
- `rust-router`, then the Rust sub-skill it points to, only if the ADR work
  unexpectedly forces Rust-surface changes and the user approves that broader
  scope.
- `arch-crate-design` if the user broadens the work from "record the
  decision" to "reshape the crate and package layout".

## Constraints

- This slice is the roadmap item "1.1.1 Record the packaging-boundary decision
  as an Architecture Decision Record (ADR)." It must remain narrower than step
  1.2.x. Do not implement bridge code, package reshuffles, helper binaries, or
  build-system changes in this slice.
- The decision recorded here must be consistent with the current design unless
  fresh repository-local evidence proves the design is internally contradictory.
  If the evidence genuinely points away from PyO3 plus `maturin`, stop and
  escalate with the contradiction written down explicitly.
- Keep substantive RFC narrowing out of this slice. Roadmap item 1.1.3 is the
  place for broad RFC alignment. This step may add references to the new ADR,
  but it must not silently rewrite RFC promises.
- Treat this as a documentation-first change. Do not edit Rust or Python source
  files, the Makefile, `pyproject.toml`, or CI workflows unless the user
  expands the scope after seeing the contradiction or gap.
- The ADR must be accepted, not merely proposed, by the end of execution.
- Because the requested outcome is architectural documentation rather than new
  runtime behaviour, new `rstest`, `rstest-bdd`, `pytest`, or `pytest-bdd`
  tests are not expected in the normal path for this slice. If execution
  uncovers a need for code changes or testable build behaviour, stop and seek
  approval because that crosses into later roadmap work.
- Documentation must follow the repository style guide: sentence-case headings,
  British English, 80-column wrapping, and updated contents/index references.

## Tolerances (exception triggers)

- Scope: if execution requires touching more than seven files, stop and
  explain why. The intended touch-set is the new ADR plus a small number of
  supporting documentation files.
- Interface: if the work appears to require any public CLI, Python API, Rust
  API, or build-command change, stop and ask for confirmation because that is
  no longer a documentation-only ratification.
- Dependencies: if the work appears to need any new Rust crate, Python
  dependency, or tooling dependency, stop and escalate.
- Evidence: if the current repository documentation and build files cannot
  support a clear choice between PyO3 plus `maturin` and helper-binary
  transport, stop and present the missing evidence rather than guessing.
- Iterations: if Markdown validation or repository gates still fail after two
  focused correction passes, stop and surface the failing output.
- Time: if the ADR draft cannot be completed, aligned, and validated inside one
  focused working session, stop and document the blocker rather than padding
  the slice with speculative prose.
- Ambiguity: if the user or reviewers interpret this slice as requiring a live
  packaging prototype, stop and request a scope decision, because prototyping
  belongs in a different roadmap step.

## Risks

- Risk: the request bundles general implementation requirements such as new
  unit tests, behavioural tests, and `docs/users-guide.md` updates into a
  roadmap step whose success criterion is an ADR.
  Severity: high
  Likelihood: high
  Mitigation: treat this slice as documentation-first. Record in the ADR and
  supporting guides what users and developers must know about the packaging
  boundary, but do not invent runtime code or synthetic tests to satisfy a
  documentation-only change. Escalate if stakeholders insist on executable
  proof.

- Risk: `docs/users-guide.md` does not currently exist even though the
  repository guidance treats it as a canonical document type.
  Severity: medium
  Likelihood: high
  Mitigation: decide during execution whether the accepted boundary creates a
  user-visible installation or runtime promise that warrants creating a minimal
  users' guide. If yes, create a narrow initial guide and list it in
  `docs/contents.md`. If no, record in `Decision Log` why user-facing
  documentation was not created for this ADR-only slice.

- Risk: the design document already reads as though the decision is made, so an
  ADR could become a duplicate rather than a clarifier.
  Severity: medium
  Likelihood: medium
  Mitigation: make the ADR do work the design does not: capture the explicit
  alternatives, decision drivers, rejected helper-binary path, and the direct
  consequences for later roadmap steps.

- Risk: maintainers may accidentally start broad RFC rewrites while touching
  related documentation.
  Severity: medium
  Likelihood: medium
  Mitigation: keep RFC edits out of scope except for optional cross-links, and
  defer contract narrowing to roadmap item 1.1.3.

- Risk: the new `docs/execplans/` subtree and ADR file could leave
  documentation navigation stale.
  Severity: low
  Likelihood: high
  Mitigation: update `docs/contents.md`, and update
  `docs/repository-layout.md` if the new subtree materially changes repository
  orientation guidance.

## Milestones

### Milestone 1: establish the evidence set

Review the existing evidence that the ADR must ratify rather than re-litigate.
That means re-reading the roadmap item, the design document sections cited
above, the developer's guide, the Makefile, and the existing ADR style. Capture
the exact repository-local facts that support the PyO3 plus `maturin`
recommendation and the exact costs of the helper-binary alternative as they
apply to Stilyagi, not to some abstract mixed-language project.

At the end of this milestone, the implementer should have a short evidence
matrix in working notes that answers four questions: what the current build
spine already does, what the helper-binary alternative would change, what v1
promises depend on the choice, and which later roadmap steps consume the
decision.

### Milestone 2: draft the accepted ADR

Create the next sequential ADR file under `docs/`. If ADR 001 is still the
latest, use `docs/adr-002-packaging-boundary.md`. If another ADR lands first,
use the next free zero-padded number and update all references accordingly.

Write the ADR in the same broad shape as ADR 001, but keep it narrower and more
decisive:

1. State the context and problem in terms of Stilyagi's build and runtime
   boundary.
2. Name the decision drivers, including offline operation, plugin discovery,
   virtual-environment alignment, wheel builds, cross-platform packaging,
   source-fidelity boundaries, and future roadmap dependence.
3. Compare at least two options: `PyO3 + maturin` extension boundary versus a
   helper-binary transport between Python and Rust. If execution uncovers a
   third serious option, record it, but do not pad the ADR with weak
   alternatives.
4. Record one accepted decision. The expected answer is the in-process PyO3
   extension built and distributed with `maturin`, with JSON retained as the
   canonical debug and test representation rather than the only hot-path
   transport.
5. Record consequences, including what later steps may assume and what remains
   out of scope for this ADR.

The ADR should make clear that helper-binary transport is rejected for v1
because it complicates packaging, plugin discovery, environment alignment, and
the clean extraction-versus-analysis boundary already described in the design.

### Milestone 3: align the governing documentation

Once the ADR exists, update the narrow set of surrounding documents that must
stop treating packaging as unresolved:

- `docs/stilyagi-design.md`
  - Update sections 12 and 13 so the packaging-boundary question is no longer
    an unresolved "must resolve" item.
  - Add or update a direct ADR reference in the companion-documents or relevant
    recommendation sections.
- `docs/developers-guide.md`
  - Replace any tentative wording with explicit statements that Stilyagi uses a
    Python package with a PyO3 extension, built with `maturin`, and does not
    rely on a helper binary for normal v1 execution.
- `docs/users-guide.md`
  - If the boundary creates a user-visible installation or operational promise,
    create or update this guide with a minimal section that explains the single
    package installation expectation and the absence of a separate helper
    binary. If execution concludes there is still no user-facing change worth
    documenting, record that decision explicitly in this plan's `Decision Log`
    and do not create filler prose.
- `docs/contents.md`
  - Add the new ADR and list the `execplans/` subtree if it is not already
    indexed.
- `docs/repository-layout.md`
  - Update only if the new `docs/execplans/` subtree or any new guide file
    materially changes repository navigation.

Do not amend the RFCs as part of this milestone beyond optional forward links.
That alignment is a later roadmap item.

### Milestone 4: validate, mark completion, and freeze the slice

Validation for this slice is repository health plus documentary coherence.
Run the repository checks sequentially, never in parallel, and capture logs
with `tee` under `/tmp/` so failures remain inspectable even if command output
is truncated.

The canonical validation sequence is:

```bash
branch_slug=$(git branch --show | tr '/' '_')
make markdownlint 2>&1 | tee /tmp/markdownlint-stilyagi-${branch_slug}.out
make nixie 2>&1 | tee /tmp/nixie-stilyagi-${branch_slug}.out
make check-fmt 2>&1 | tee /tmp/check-fmt-stilyagi-${branch_slug}.out
make lint 2>&1 | tee /tmp/lint-stilyagi-${branch_slug}.out
make test 2>&1 | tee /tmp/test-stilyagi-${branch_slug}.out
```

After the gates pass:

1. Update `docs/roadmap.md` so item 1.1.1 is marked done.
2. Re-read the ADR, design references, guide updates, and roadmap entry
   together to ensure they tell one story.
3. Update this ExecPlan's living sections with what actually happened.

The slice is complete when a reviewer can verify all of the following:

- the ADR exists and is marked accepted;
- the design and developer documentation reference the accepted boundary rather
  than an open question;
- any user-facing packaging promise is either documented or explicitly judged
  non-applicable for this slice;
- the roadmap item is marked done; and
- the validation commands above have passed.

## Concrete execution notes

Use short, reviewable documentation commits. Do not squash the ADR creation
together with broad unrelated doc cleanups. If execution exposes stale prose
outside the intended touch-set, note it and defer it unless it directly
contradicts the accepted decision.

When writing the ADR, prefer explicit consequence statements over vague
"pros and cons". A later implementer should be able to quote one sentence from
the ADR to justify why step 1.2.2 must use the extension boundary instead of
shelling out to a helper process.

Keep examples concrete and repository-local. Cite `make build`, `make release`,
`rust_extension/Cargo.toml`, and the current Python package layout where they
help make the reasoning tangible.

## Progress

- [x] 2026-04-20 00:00Z: Reviewed the roadmap item, design document, developer
  guide, repository layout, Makefile, and existing ADR style to draft this
  plan.
- [x] 2026-04-20 00:00Z: Recorded two repository discoveries that affect scope:
  `docs/execplans/` did not yet exist, and `docs/users-guide.md` is currently
  absent.
- [x] 2026-04-20 00:00Z: User approved the plan and authorized implementation.
- [x] 2026-04-20 00:00Z: Re-checked the evidence set during execution. The
  current design, Makefile, and developer guide all already assume the PyO3
  plus `maturin` path, so the ADR can ratify that direction without widening
  scope into executable packaging work.
- [x] 2026-04-20 00:00Z: Executed Milestones 2 and 3 by drafting
  `docs/adr-002-packaging-boundary.md`, creating `docs/users-guide.md`, and
  aligning the design, developer guide, contents index, and roadmap around the
  accepted boundary.
- [x] 2026-04-20 00:00Z: Ran `make markdownlint`, `make nixie`,
  `make check-fmt`, `make lint`, and `make test` successfully with logs written
  under `/tmp/*-stilyagi-feat_adr-packaging-plan.out`.
- [x] 2026-04-20 00:00Z: Updated the roadmap, finalized this plan's living
  sections, and marked the slice complete.

## Surprises & Discoveries

- `docs/users-guide.md` does not currently exist, even though the repository's
  documentation style guide treats it as a canonical document type.
- The current docs and build files already assume PyO3 plus `maturin` strongly
  enough that the main job of this slice is to make the decision explicit and
  traceable, not to explore the architecture from scratch.
- The repository did not yet have a `docs/execplans/` directory, so the
  documentation index needs to account for that subtree when plans are added.
- The Makefile and developer guide are stronger evidence than the design
  document alone because they show the already-adopted local build and release
  workflow rather than only the target architecture.
- A minimal users' guide is worthwhile even before the feature slices land,
  because the packaging boundary is already a user-visible promise about how
  Stilyagi will install and run.
- The original `tee` filename template from the draft plan breaks on branch
  names that contain `/`, so future runs should sanitize the branch name before
  constructing `/tmp` log paths.

## Decision Log

- 2026-04-20: Treat roadmap item 1.1.1 as a documentation-first ratification
  step, not as executable packaging work.
  Rationale: the roadmap success criterion is "one accepted ADR defines the
  build and runtime boundary for all later work", while actual mixed-package
  implementation starts in step 1.2.x.

- 2026-04-20: Treat the testing requirement for this slice as repository gate
  execution rather than new unit or behavioural test authoring.
  Rationale: an ADR does not add runnable behaviour on its own. If code changes
  become necessary, that is a scope expansion and should be approved before
  proceeding.

- 2026-04-20: Keep substantive RFC amendments out of this slice.
  Rationale: the roadmap already allocates RFC alignment to item 1.1.3, and
  collapsing the two steps would make completion criteria blurry.

- 2026-04-20: Create a minimal `docs/users-guide.md` in this slice.
  Rationale: the approved boundary creates a user-visible packaging promise:
  Stilyagi is expected to install and run as one Python package with an
  embedded extension rather than as a Python wrapper around a separately
  managed helper binary.

- 2026-04-20: Record the accepted ADR as `docs/adr-002-packaging-boundary.md`.
  Rationale: ADR 001 already exists, and this slice needs a stable, sequential
  identifier that later roadmap and design references can cite directly.

- 2026-04-20: Sanitize the branch name before writing validation logs.
  Rationale: this repository uses branch names such as
  `feat/adr-packaging-plan`, and the raw slash causes `tee` to treat the log
  filename as a nested path under `/tmp`.

## Outcomes & Retrospective

Completed on 2026-04-20.

The final ADR is [docs/adr-002-packaging-boundary.md](../adr-002-packaging-boundary.md).
It accepts the in-process PyO3 plus `maturin` boundary, rejects helper-binary
transport for normal v1 execution, and leaves the narrower transport-policy
details to roadmap item 1.1.2.

The supporting documentation now tells one coherent story:

- [docs/stilyagi-design.md](../stilyagi-design.md) references ADR 002 and no
  longer treats the packaging boundary as unresolved.
- [docs/developers-guide.md](../developers-guide.md) states the accepted
  in-process boundary explicitly.
- [docs/users-guide.md](../users-guide.md) records the user-facing packaging
  promise created by the ADR.
- [docs/contents.md](../contents.md) indexes the new ADR and users' guide.
- [docs/roadmap.md](../roadmap.md) marks item 1.1.1 done.

Validation completed successfully with:

- `make markdownlint`
- `make nixie`
- `make check-fmt`
- `make lint`
- `make test`

The main lesson for later roadmap steps is that some "open questions" in the
design are already operationally settled by the Makefile and developer
workflow. When that happens, the ADR should ratify the real repository state
and narrow the remaining questions, rather than pretending the project is still
choosing among equally live alternatives.
