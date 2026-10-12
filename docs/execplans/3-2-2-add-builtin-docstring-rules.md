# Add builtin documentation rules (3.2.2)

This execution plan (ExecPlan) is a living document. Keep its constraints,
progress, discoveries, decisions, conformance basis, verification, and outcomes
current at every milestone boundary.

Status: DRAFT. Planning is complete enough for review; implementation requires
approval and delivery of prerequisite 2.3.1. No feature is implemented here.

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
- Reuse the existing policy targeting, registry, diagnostics, suppression, and
  command pipeline delivered by 2.3.1. Do not create a docstring-only engine.
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
if prerequisite 2.3.1 remains absent; the shared policy API cannot express the
specified targets; owner or source mapping needs new extraction metadata; a
runtime dependency, parser, public wire change, or autocorrection is needed; or
a rule cannot meet its specified false-positive exclusions. Do not implement
missing prerequisite work under this task number. Mechanical renames of the
prerequisite's unpublished Python API are allowed only when recorded with all
plan references updated; compatibility wrappers are not required.

There is no elapsed-time limit. Three unsuccessful fixes of the same gate
failure require a recorded diagnosis before another attempt, not a weakened
gate. Disk exhaustion or compiler-admission failure requires reporting the
external blocker without bypassing it.

## Risks

The prerequisite is definitely absent at the recorded baseline (high impact).
An explicit entry gate prevents accidental engine construction in this task.
Markdown inside Rust comments and verbatim Python strings make broad summary
heuristics prone to false positives (medium impact); restrict recognition as
specified below and test unsupported forms as negative cases. Synthetic Rust
line separators make region offsets different from source offsets (high
impact); use the prerequisite's source mapping and offer no fixes. Optional
owner names are normal, not extraction failures (medium impact); skip the
owner-dependent rule when a trustworthy name is absent.

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
- [ ] Publish the validated planning commit as a draft pull request.
- [ ] EP-M0: verify prerequisite delivery and bind the plan to its actual API.
- [ ] EP-M1: deliver three registered rules with focused verification.
- [ ] EP-M2: prove mixed-source workflow behaviour and document delivery.

## Surprises & discoveries

At baseline `91941ef36df9c262af74e6089e661921d1ae3577`, extraction and
mixed-source file discovery exist, but
`python/stilyagi/rules/registry.py::run_rules` returns an empty list.
`python/stilyagi/model/region.py::Region` contains only `kind` and `text`; the
execution planner and runner are placeholders. Roadmap 2.3.1 is unchecked. RFC
0002 describes the intended rule API, not a present working implementation.
Planning can proceed; implementation cannot yet pass EP-M0.

CodeGraph indexing did not establish a useful graph for this checkout and agent
symbol searches failed with `Transport closed`. Focused repository reads and
context packs supplied the evidence instead. No graph-derived relationships are
assumed by this plan.

## Decision log

- 2026-10-13: Keep this task conditional on 2.3.1. Folding in an entire rule
  engine would violate the roadmap dependency and obscure the learning goal.
- 2026-10-13: Propose three conservative structural rules, rather than
  imperative-mood detection or signature analysis. Owner kind and name exist;
  parameters, return types, decorators, and visibility do not form a guaranteed
  owner contract. Grammar rules belong to later capability slices.
- 2026-10-13: All three rules are diagnostic-only and explicitly enabled.
  This follows the shared policy model without choosing a new default style for
  all repositories. Source fix mapping remains the existing engine's
  responsibility; 3.2.3 owns broader mixed-source output/fix work.
- 2026-10-13: Record the proposed rule contract in design §7.2, linked to this
  plan. No new port, transport, schema, or persistent format is proposed, so a
  separate architectural decision record (ADR) is unnecessary. If that changes,
  create an ADR following the documentation style guide before implementing.

## Outcomes & retrospective

The current deliverable is a pre-implementation plan, not completed 3.2.2
behaviour. The missing shared rule substrate is an explicit delivery gate.
Implementation outcomes, exact gate logs, commits, and any approved deviations
must replace this paragraph as milestones complete. Do not mark the plan
COMPLETE while prerequisite, acceptance, or upstream documentation work remains.

## Context and orientation

Read `AGENTS.md`, `docs/contents.md`, and `docs/repository-layout.md` first.
The current layout guide's skeleton language is older than the extraction
implementation; use the actual source for implementation status.

Rust owns source fidelity in `crates/stilyagi-ir/src/region.rs` and the
extractors under `crates/stilyagi-tree-sitter/`. `IrRegion` already carries
syntax, owner, text, and source-backed or synthetic segments. ADRs 006 and 007
specify Python and Rust owner identity. Python owners are module, class, or
function; methods use function, and module names can be absent. Rust includes
module, struct, enum, union, trait, function, const, static, type, macro, impl,
and fallback item. The rule must use those facts, not infer missing semantics.

`python/stilyagi/engine/api.py::extract_document` is the supported extraction
entrypoint. `python/stilyagi/engine/checker.py::map_ir_errors` maps extraction
errors, while `python/stilyagi/rules/registry.py::run_rules` is the current
empty rule seam. `python/stilyagi/rules/builtin/__init__.py` reserves the
builtin namespace. EP-M0 must identify the actual Rule, RegionTarget,
context-reporting, source mapping, configuration, and registration APIs
introduced by 2.3.1. Record the existing CLI exit statuses and renderer
contracts, including whether configurable fail-on severity exists, before EP-M2
begins. Names below for new files are proposals, not claims that those files
exist.

## Conformance basis

The baseline revision above applies to `docs/roadmap.md` item 3.2.2,
`docs/stilyagi-design.md` §§3–4, 7.2, and 13,
`docs/rfcs/0002-stilyagi-python-rule-api.md`, and ADRs 003, 006, 007, and 008.
There is no separate task-specific terms-of-reference document. RFC 0002
requires explicit region targets, capability declarations, hook dispatch only
for matching targets, and ordering by pack name, rule code, and document order.

Trace R-REUSE (shared loop and prerequisite) through EP-M0 and EP-M1 to the
registration/dispatch tests; R-VALUE (summary, punctuation, owner-aware value)
through EP-M1 to the three rule tables; R-SCOPE (explicit surface targeting and
no ordinary comments) through both implementation milestones to the targeting
matrix and mixed-tree command test; R-FIDELITY (source-backed diagnostics)
through EP-M1 and EP-M2 to Unicode properties and renderer snapshots;
R-DELIVERY (documentation and roadmap completion) through EP-M2 to final gates
and the roadmap diff. Keep these links current after prerequisite integration.

Primary-source research on 2026-10-13 used Firecrawl to consult
[PEP 257](https://peps.python.org/pep-0257/) and the
[rustdoc writing guide](https://doc.rust-lang.org/rustdoc/how-to-write-documentation.html).
PEP 257 recommends a summary separated from further explanation by a blank
line. Rustdoc recommends a concise opening summary and supports Markdown. These
are conventions, not syntax errors. The exact bounded policies below are
Stilyagi design choices, not assertions that every upstream convention is
mandatory.

## Proposed rule contract

Reserve `DOC001`, `DOC002`, and `DOC003` subject to an EP-M0 collision check.
If the prerequisite establishes another code namespace, record the mechanical
substitution everywhere before writing tests. Each declares only the existing
structural capability, default warning severity, no fix, no preview dependency,
and explicit opt-in through the shared rule selection configuration. Policies
can narrow these targets; they cannot broaden a rule into an unsupported
syntax. No rule needs locale-sensitive linguistic claims. Physical content
lines split only at LF, treating a preceding CR as part of the CR-LF
terminator; Unicode line separators and a lone CR do not create additional
physical lines. Analysis-only trimming uses Python Unicode whitespace semantics.

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

Introduce a private summary-analysis helper only after checking the
prerequisite for an equivalent. Its sole responsibility is selecting candidate
text ranges and identifying supported forms while retaining offsets into
unchanged region text. Source mapping and reporting stay with the shared
context. For Rust block comments, do not strip decorative `*` prefixes or
reparse Markdown: punctuation checking skips these unsupported forms, and owner
matching remains exact. If an anchor cannot be mapped to a source-backed
character, omit that finding; never substitute a file-level location or
synthetic separator. When the prerequisite diagnostic API accepts a span, use
the half-open UTF-8 byte span of that one complete anchor character, not one
byte of a multibyte character. Point-only renderers use its start. Preserve the
existing 1-based byte-column contract; do not change renderer coordinate units
in this task.

## Plan of work and milestones

### EP-M0: establish the usable prerequisite

Inspect the accepted 2.3.1 commit and its tests. Record its revision and actual
API paths in this plan. Require a working Markdown builtin through the real
check pipeline, typed owner/segment access, shared policy target matching,
explicit enable/disable selection, source-span reporting, and deterministic
registration. Verify 3.1.1 and 3.1.2 extractor tests still pass. If any
required substrate is absent, stop at this stable plateau and report the
missing prerequisite rather than implementing it here. This baseline currently
fails that entry condition. Do not mark 2.3.1 done merely to advance this plan.

After the prerequisite lands, run the four major gates below and record the
baseline results. Acceptance A0 is the passing Markdown rule workflow plus
concrete references for each required API. R-REUSE is established; all new rule
behaviour remains for EP-M1. Recovery is a clean restart from the prerequisite
commit; no compatibility layer or change to extractors is justified.

### EP-M1: deliver the complete rule policy

Create focused modules under `python/stilyagi/rules/builtin/` for documentation
summary analysis and the three rule declarations. Register them through the
same mechanism as the Markdown pack, updating the prerequisite's registry and
configuration metadata only where necessary. Use `visit_region` and shared
`RegionTarget` descriptors. Do not extend the currently empty registry directly
before EP-M0 establishes its replacement.

Write `tests/test_builtin_docstring_rules.py` and
`tests/test_builtin_docstring_properties.py` first, using the prerequisite's
real rule harness. Observe the expected failures (missing codes or missing
findings), then implement the smallest policy and rerun. Include both passing
and failing examples for every owner/syntax partition, multiline and blank
inputs, CR-LF, Unicode, unsupported Markdown, literal escapes, optional owner
names, owner names containing underscores, Unicode line separators, and
independent overlapping diagnostics. Include a Rust summary immediately
followed by a heading without a blank line as an explicit skip witness. Test
policy disablement and narrowed syntax/owner targeting through the shared
dispatch rather than calling private predicates alone. Extract helpers only
after green tests.

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
all three codes using the prerequisite's documented configuration, then execute
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
the prerequisite's typed context contract. Third-party internals are not proof
obligations; the repository-owned integration is.

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
execute Python policy. Record the actual Rust feature path during EP-M0.

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
command test: enabled warnings appear with the three specified codes and exact
locations, conforming examples do not warn, disabling the rules removes their
findings, and repeated JSON output is identical. Cover clean input,
warning-only input under default behaviour, configured fail-on behaviour if the
prerequisite supports it, and malformed-source diagnostics with rules enabled
and disabled. If fail-on is unavailable, record that fact rather than
introducing the option. Assert the prerequisite CLI's existing warning/fail-on
contract; do not invent a new exit-code policy.

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
`docs/rfcs/0004-stilyagi-rule-testing-framework.md` as a proposal: do not
assume its test plugin exists until EP-M0 confirms it. Follow `.rules/` Python
guidance and `docs/scripting-standards.md` if scripts become necessary.

## Idempotence, recovery, and evidence

Tests use isolated temporary source trees and never modify checked-in fixtures
through a live fix command. Repeat checks freely; inspect and accept snapshots
only after semantic assertions pass. Keep each coherent milestone in a gated
commit, preserving pre-change Red logs and post-change Green logs. Recover with
a normal revert of owned commits, not a destructive reset of shared work. Keep
rule, documentation, and roadmap evidence tied to the exact validated commit.
Prerequisite and architecture deviations must be reconciled before feature
completion.

Revision note (2026-10-13): Initial plan records the missing prerequisite,
conservative policy contract, verification obligations, and staged delivery.
Community review clarified shared summary selection, per-line markup skips,
physical lines and Unicode spans, exit-status evidence, non-vacuous mutation
witnesses, and fail-fast milestone logging. No runtime scope was added.
