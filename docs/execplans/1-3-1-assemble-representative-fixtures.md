# Assemble shared validation corpus fixtures

This ExecPlan (execution plan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work
proceeds.

Status: COMPLETE

Approval gate: approved by the user on 2026-05-01 before implementation began.

## Purpose / big picture

Roadmap item 1.3.1 creates the shared source corpus that later Stilyagi slices
will use instead of embedding ad hoc strings in unit and behaviour tests. After
this work, maintainers should be able to point Rust and Python tests at one
versioned set of representative Markdown, Python, and Rust source fixtures,
including malformed-input cases that prove recovery paths stay intentional.

This slice does not implement the final golden intermediate representation
(IR), command-line interface (CLI) snapshots, or fix round-trip helpers. Those
belong to roadmap item 1.3.2. The observable outcome for this slice is a
checked-in fixture corpus, small shared fixture readers for Rust and Python
tests, behaviour tests that exercise the corpus conventions, and documentation
that tells future maintainers where to add cases.

## Context and orientation

The repository is a mixed Rust and Python project. Rust crates live under
`crates/`, Python package code lives under `python/stilyagi/`,
behaviour-driven development (BDD) feature files for Python tests live under
`features/`, and current static test inputs live under `tests/fixtures/`.

The current extraction implementation is intentionally narrow. Rust code in
`crates/stilyagi-extract/src/lib.rs` supports the `markdown`,
`python_docstring`, and `rust_doc_comment` syntax names, but only Markdown
currently returns a document-shaped extraction payload. Python docstring and
Rust documentation-comment extraction currently return explicit unsupported
syntax errors through the Rust and PyO3 layers. This plan therefore treats
Python and Rust source examples as source fixtures for later extractor work,
not as promises that those extractors are implemented in this slice.

The design document already sketches a future `tests/golden/`,
`tests/integration/`, `tests/performance/`, and `tests/rulepacks/` layout. This
slice should create only the directories it actually uses. The canonical source
corpus for this work should live under `tests/fixtures/corpus/` so Python and
Rust test readers can share the same files.

Terms used in this plan:

- Fixture: a checked-in test input file, not generated during a test.
- Corpus: the grouped set of fixtures for one syntax and case class.
- Malformed input: source text with invalid or incomplete syntax that a parser
  should handle by reporting or recovering from rather than crashing.
- Happy path: a valid source fixture that demonstrates intended normal use.
- Unhappy path: an invalid, unsupported, or malformed source fixture that
  demonstrates explicit failure or recovery behaviour.

## Documentation and skill signposts

The implementer should keep these documents open while executing the plan:

- [docs/roadmap.md](../roadmap.md) for the exact 1.3.1 scope and the final
  roadmap checkbox update.
- [docs/stilyagi-design.md](../stilyagi-design.md), especially sections 7.1,
  10, and 11, for the IR vocabulary, repository layout, and validation plan.
- [docs/rfcs/0004-stilyagi-rule-testing-framework.md](
  ../rfcs/0004-stilyagi-rule-testing-framework.md) for the future rule-testing
  harness shape that this corpus must support. Request for Comments (RFC)
  documents record proposed technical contracts.
- [docs/complexity-antipatterns-and-refactoring-strategies.md](
  ../complexity-antipatterns-and-refactoring-strategies.md) for keeping corpus
  helpers small rather than building a premature fixture framework.
- [docs/rust-testing-with-rstest-fixtures.md](
  ../rust-testing-with-rstest-fixtures.md) for Rust `rstest` fixture style.
- [docs/rust-doctest-dry-guide.md](../rust-doctest-dry-guide.md) for doctest
  expectations if public Rust helper APIs are documented.
- [docs/reliable-testing-in-rust-via-dependency-injection.md](
  ../reliable-testing-in-rust-via-dependency-injection.md) for keeping test
  helper IO explicit and injectable.
- [docs/rstest-bdd-users-guide.md](../rstest-bdd-users-guide.md) for Rust
  behaviour tests with `rstest-bdd`.
- [docs/developers-guide.md](../developers-guide.md) for contributor-facing
  fixture conventions and internal test practice.
- [docs/users-guide.md](../users-guide.md) for user-visible behaviour. This
  slice likely needs little or no user-guide change unless a public command or
  API changes, which is outside the intended scope.

The relevant skills are:

- `execplans` to keep this plan current and approval-gated.
- `leta` for symbol-aware code navigation before code changes.
- `rust-router`, then `arch-crate-design`, if the Rust fixture reader touches
  crate boundaries or shared public APIs.
- `rust-errors` if fixture loading introduces recoverable IO or parse errors.
- `domain-cli-and-daemons` only if the work unexpectedly touches CLI behaviour.

## Constraints

- Do not implement roadmap item 1.3.2. Golden IR files, CLI snapshots, and fix
  round-trip helpers are allowed only as design placeholders in this plan, not
  as implementation work for 1.3.1.
- Do not claim Python docstring or Rust documentation-comment extraction works
  if the extractor still reports those syntaxes as unsupported.
- The shared corpus must include Markdown, Python, and Rust source fixtures.
  It must include happy and unhappy paths, including malformed input.
- The corpus must cover, at minimum, headings, tables, links, Python
  docstrings, Rust documentation comments, suppression directives, and parser
  recovery cases.
- Tests must use the checked-in fixtures rather than reintroducing equivalent
  inline strings for the same cases.
- Use `rstest` for Rust unit tests and `pytest` for Python unit tests. Use
  `rstest-bdd` for Rust behaviour tests and `pytest-bdd` for Python behaviour
  tests where behaviour is exercised.
- Keep Makefile commands canonical. Prefer `make check-fmt`, `make lint`, and
  `make test` over lower-level commands for final validation.
- Run format, lint, and test commands sequentially, not in parallel.
- Record any design decision that changes repository layout, fixture naming,
  test practice, or extractor contract in the relevant design or developer
  documentation.
- Update `docs/developers-guide.md` with fixture corpus conventions.
- Update `docs/users-guide.md` only if the implementation changes behaviour or
  user-facing API. If there is no user-facing change, record that decision in
  this plan's `Decision Log`.
- On completion of the implemented feature, mark roadmap item 1.3.1 in
  `docs/roadmap.md` as done. Do not mark it done while this plan is still only
  a draft.
- Commit only after the relevant gates pass.

## Tolerances

- Scope: if implementation needs more than fifteen files or roughly 650 net
  new lines, stop and explain why. The corpus should be representative, not
  exhaustive.
- Fixture count: start with roughly three to five fixtures per syntax, with at
  least one malformed case per syntax. If a larger first corpus seems
  necessary, stop and justify it before expanding.
- Interfaces: if a public Rust or Python API signature must change, stop and
  ask for approval. Small test-only helper modules are acceptable.
- Dependencies: if any new Rust or Python dependency is needed, stop and ask
  for approval. The existing `rstest`, `rstest-bdd`, `pytest`, and `pytest-bdd`
  dependencies should be enough.
- Format: if Markdown formatting or lint rules require material changes to
  fixture contents that would weaken the malformed-input cases, document the
  conflict and ask before changing the case intent.
- Validation: if `make check-fmt`, `make lint`, or `make test` still fails
  after two focused correction passes, stop and record the failing log paths in
  this plan.
- Ambiguity: if there are multiple valid fixture naming or metadata schemes
  and the choice would affect later slices, document the options and ask before
  proceeding.

## Risks

- Risk: this slice could accidentally grow into golden IR contract work.
  Severity: medium. Likelihood: medium. Mitigation: create source fixtures and
  fixture readers only; leave expected canonical IR manifests to 1.3.2.
- Risk: Python and Rust fixtures may look like implemented extractor promises
  before those extractors exist. Severity: high. Likelihood: medium.
  Mitigation: document them as corpus inputs and keep current unsupported
  syntax tests honest until later extraction slices implement them.
- Risk: malformed Markdown fixtures may be altered by Markdown formatters or
  linters. Severity: medium. Likelihood: medium. Mitigation: choose malformed
  cases that remain useful under repository formatting rules, or isolate exact
  source text in fixture files and explain why it must remain as-is.
- Risk: Rust tests may need fixture file paths that differ when run from
  workspace root, crate root, nextest, or cargo test. Severity: medium.
  Likelihood: medium. Mitigation: resolve paths from `CARGO_MANIFEST_DIR` plus
  repository-relative parents, and test through `make test`.
- Risk: Python behaviour tests may read stale or unrelated legacy feature
  files. Severity: low. Likelihood: medium. Mitigation: add a new focused
  feature file and wire only that file into its test module.
- Risk: a large corpus can become hard to maintain. Severity: medium.
  Likelihood: medium. Mitigation: add concise README-style guidance or
  developer-guide text that defines naming, intent, and where new cases go.

## Plan of work

Milestone 1 records the intended fixture layout with failing tests. Add Python
unit tests that expect a `tests/fixtures/corpus/` tree with Markdown, Python,
and Rust fixture groups. Add a Python BDD feature that describes the maintainer
behaviour: "shared corpus fixtures are available for every v1 syntax" and
"malformed fixtures are represented without crashing the reader." Add Rust unit
or behaviour tests that read at least the Markdown fixture cases through a
small helper or test-local path resolver. These tests should initially fail
because the corpus and helper conventions do not exist yet.

Milestone 2 creates the source corpus. Use a directory shape like:

```plaintext
tests/fixtures/corpus/
├── markdown/
│   ├── valid/
│   └── malformed/
├── python/
│   ├── valid/
│   └── malformed/
└── rust/
    ├── valid/
    └── malformed/
```

The initial Markdown fixtures should cover a heading, a table, a link, and a
suppression directive. The initial Python fixtures should cover module, class,
and function docstrings, decorators or nesting if useful, a suppression
comment, and at least one malformed Python source file. The initial Rust
fixtures should cover item-level `///` documentation comments, module or
crate-level documentation, a suppression comment, and at least one malformed or
incomplete Rust source file. Keep each fixture small and purpose-named.

Milestone 3 adds minimal shared fixture readers. For Python tests, add a
test-support module or fixture in `tests/` that enumerates corpus cases using
`pathlib.Path` and returns stable identifiers plus file contents. For Rust
tests, add either test-only helper functions in the relevant crate tests or a
small internal test module that resolves repository fixture paths and reads
UTF-8 fixture contents. Do not add a reusable public fixture framework unless
implementation proves it is needed.

Milestone 4 connects the corpus to existing extraction and bridge tests without
overstating current support. Refactor existing Markdown extraction tests in
`crates/stilyagi-extract/src/lib.rs`, `crates/stilyagi-pyext/src/lib.rs`, or
Python package tests only where it replaces inline Markdown strings with shared
fixture reads. Keep existing unsupported-syntax assertions for Python
docstrings and Rust documentation comments. Add tests that prove those source
fixtures can be loaded and classified today, even if extraction for those
syntaxes still returns `NotImplementedError`.

Milestone 5 updates documentation. Update `docs/developers-guide.md` with the
fixture corpus root, naming convention, and guidance for adding new cases.
Update `docs/stilyagi-design.md` section 11 only if implementation finalizes a
validation-corpus layout that should become normative. Update
`docs/users-guide.md` only if user-visible behaviour changed. Update
`docs/roadmap.md` to mark 1.3.1 done only after the implementation, docs, and
validation gates pass.

Milestone 6 validates and commits. Run formatting, linting, and tests through
Makefile targets with `tee` logs in `/tmp`. Fix only issues caused by this
work. After the gates pass, commit the implementation as one focused change.

## Concrete steps

From the repository root, confirm branch and status:

```bash
git branch --show-current
git status --short
```

Expected branch:

```plaintext
feat/fixture-corpus-plan
```

Before implementation, add the tests that describe the desired corpus and run
the targeted Python and Rust tests. Use logs so truncated terminal output can
be reviewed:

```bash
make test 2>&1 | tee /tmp/test-stilyagi-feat-fixture-corpus-plan.out
```

The expected first result after test edits is failure caused by missing corpus
files or missing fixture helper behaviour. It should not fail because of an
unrelated build-spine regression.

After implementation, run the required gates sequentially:

```bash
make check-fmt 2>&1 | tee /tmp/check-fmt-stilyagi-feat-fixture-corpus-plan.out
make lint 2>&1 | tee /tmp/lint-stilyagi-feat-fixture-corpus-plan.out
make test 2>&1 | tee /tmp/test-stilyagi-feat-fixture-corpus-plan.out
```

If Markdown docs changed, also run:

```bash
make markdownlint 2>&1 | tee /tmp/markdownlint-stilyagi-feat-fixture-corpus-plan.out
make nixie 2>&1 | tee /tmp/nixie-stilyagi-feat-fixture-corpus-plan.out
```

After all gates pass, inspect the final diff:

```bash
git diff --stat
git diff -- docs/roadmap.md docs/developers-guide.md docs/stilyagi-design.md
git status --short
```

Then commit with a file-based commit message, following the repository commit
message rules.

## Validation and acceptance

The implementation is accepted when all of the following are true:

- `tests/fixtures/corpus/` contains representative Markdown, Python, and Rust
  source fixtures split into valid and malformed cases.
- The fixture set covers headings, tables, links, docstrings, documentation
  comments, suppressions, and error-recovery inputs.
- Python `pytest` unit tests read the shared corpus and prove each syntax group
  and malformed group is present.
- Python `pytest-bdd` behaviour tests describe the shared-corpus maintainer
  workflow and pass.
- Rust `rstest` unit tests use shared fixture contents for at least the current
  Markdown extraction path or the Rust fixture reader.
- Rust `rstest-bdd` behaviour tests pass if Rust behaviour coverage is added
  or modified.
- Current unsupported-syntax behaviour for Python docstrings and Rust
  documentation comments remains explicit until those extractors are
  implemented by later roadmap slices.
- `docs/developers-guide.md` documents where shared corpus fixtures live and
  how to add new cases.
- `docs/users-guide.md` is updated if, and only if, user-visible behaviour or
  public API changed.
- `docs/roadmap.md` marks item 1.3.1 as done after successful validation.
- `make check-fmt`, `make lint`, and `make test` all succeed.

## Idempotence and recovery

The corpus files and tests are additive. Re-running the tests and validation
commands should not mutate repository state except for normal build artefacts
under existing ignored directories. If a fixture case proves poorly named or
too broad, rename it before other tests depend on it and update any helper
expectations in the same commit.

If a Makefile gate fails, inspect the matching `/tmp/*.out` log first. If the
failure is unrelated to this work, record it in `Surprises & Discoveries` and
ask before widening scope. If the failure is caused by this work, fix it and
rerun only the failed gate before rerunning the final gate sequence.

If the formatter rewrites Markdown fixture text in a way that damages a
malformed-input case, stop and choose a better fixture representation rather
than weakening the recovery test silently.

## Interfaces and dependencies

No new external dependencies are expected.

Any Python fixture helper should be test-only and should use `pathlib.Path`. It
may expose a simple shape such as:

```python
@dataclass(frozen=True, slots=True)
class CorpusFixture:
    syntax: str
    category: str
    name: str
    path: pathlib.Path
    text: str
```

Any Rust fixture helper should be test-only and should return `Result` for IO
failures rather than panicking inside reusable helper logic. If it lives inside
an existing crate's `#[cfg(test)]` module, it should stay private to that test
module unless another crate genuinely needs it.

The fixture naming convention should prefer stable, descriptive file names such
as `heading-table-link.md`, `module-class-function-docstrings.py`,
`item-doc-comments.rs`, and `unclosed-table.md`. Avoid names that describe the
current implementation limitation rather than the source shape.

## Progress

- [x] (2026-04-30T19:30:54Z) Drafted plan after reading AGENTS guidance,
  roadmap item 1.3.1, the design and RFC references, current Makefile gates,
  current extraction tests, and Wyvern reconnaissance.
- [x] (2026-05-01T00:00:00Z) Received explicit user approval to proceed with
  implementation from this ExecPlan.
- [x] (2026-05-01T00:00:00Z) Added Python `pytest` unit tests and
  `pytest-bdd` scenario coverage for corpus availability.
- [x] (2026-05-01T00:00:00Z) Added shared source corpus fixtures under
  `tests/fixtures/corpus/` for Markdown, Python, and Rust valid and malformed
  source inputs.
- [x] (2026-05-01T00:00:00Z) Added focused Python corpus helpers in
  `tests/test_corpus.py` and test-local Rust fixture readers that resolve
  repository-relative paths from `CARGO_MANIFEST_DIR`.
- [x] (2026-05-01T00:00:00Z) Connected Markdown extraction tests and the PyO3
  bridge BDD scenario to the shared Markdown fixture without changing the
  unsupported Python or Rust extractor contracts.
- [x] (2026-05-01T00:00:00Z) Ran `make test`; after a Rust formatting fix and
  one over-specific lint-expectation fix, the gate passed with 49 Rust tests
  and 51 Python tests.
- [x] (2026-05-01T00:00:00Z) Updated `docs/developers-guide.md`,
  `docs/stilyagi-design.md`, and `docs/roadmap.md`; left `docs/users-guide.md`
  unchanged because no user-visible behaviour changed.
- [x] (2026-05-01T00:00:00Z) Final gates passed: `make check-fmt`,
  `make lint`, `make test`, `make markdownlint`, and `make nixie`.
- [x] (2026-05-06T00:00:00Z) Addressed review comments by adding a Rust
  test-support crate for shared corpus path helpers, centralising the shared
  Markdown fixture path in Rust and Python tests, strengthening malformed
  fixture filename assertions, and expanding uncommon acronyms in this plan.
- [x] (2026-05-07T00:00:00Z) Addressed follow-up review comments by moving the
  `stilyagi-extract` Rust tests into an integration test file, moving PyO3 BDD
  tests into a dedicated test module, centralising `RegionKind` string parsing,
  making repository-root discovery fail fast, and replacing loose Python BDD
  state with a `TypedDict`.
- [x] (2026-05-07T00:00:00Z) Validated the follow-up changes with
  `make check-fmt`, `make lint`, `make test`, `make markdownlint`,
  `make nixie`, and `make typecheck`; `make nixie` needed an escalated rerun
  because Chromium cannot launch inside the sandbox.

## Surprises & Discoveries

- Observation: the documented execplans skill path in the skill registry was
  stale; the installed file was found at
  `/home/leynos/.codex/skills/execplans/SKILL.md`. Evidence: the first attempt
  to read the registry path failed, and `find` located the active skill file.
  Impact: no plan change beyond using the located skill instructions.
- Observation: `leta` workspace setup succeeded, but semantic Rust/Python
  queries failed because the Language Server Protocol (LSP) connection closed
  unexpectedly. Evidence: `leta grep` returned a rust-analyzer startup or
  connection error. Impact: repo inspection used direct file reads and text
  search for planning; implementation should retry `leta` before code edits.
- Observation: Python docstring and Rust documentation-comment syntaxes are
  currently registered but intentionally unsupported by extraction. Evidence:
  `crates/stilyagi-extract/src/lib.rs` maps those syntaxes to
  `ExtractError::UnsupportedSyntax`. Impact: this plan treats Python and Rust
  source fixtures as corpus inputs, not implemented extraction outputs.
- Observation: retrying `leta` at implementation start still failed because
  `rust-analyzer` closed the LSP connection. Evidence: `leta grep` returned
  `Language server 'rust-analyzer' for rust failed to start`. Impact: code
  navigation for this implementation used targeted file reads instead of LSP
  symbol queries.
- Observation: the first full `make test` run failed only at Rust formatting.
  Evidence: Cargo reported import ordering and function signature formatting
  diffs. Impact: `cargo fmt --manifest-path Cargo.toml --all` was enough to
  correct the issue before rerunning the gate.
- Observation: an `#[expect(clippy::expect_used)]` annotation on a Rust test
  fixture became unfulfilled after the helper used `unwrap_or_else` with a
  contextual panic. Evidence: clippy failed with
  `unfulfilled-lint-expectations`. Impact: the unnecessary expectation was
  removed.
- Observation: Ruff parses every `.py` file before tests can treat it as raw
  source, so an intentionally invalid Python fixture with a `.py` suffix breaks
  `make check-fmt`. Evidence: `ruff format --check` reported `invalid-syntax`
  for `tests/fixtures/corpus/python/malformed/`. Impact: malformed Python
  source fixtures use `.py.txt` so they remain raw UTF-8 corpus inputs rather
  than formatter targets.
- Observation: `make fmt` still reaches pre-existing Markdown line-length
  failures outside this branch after running `mdformat-all`. Evidence: the log
  `/tmp/fmt-stilyagi-1-3-1-assemble-representative-fixtures.out` lists MD013
  failures in older architecture decision record (ADR), RFC, and guide files.
  Impact: branch-local Markdown is validated with `make markdownlint` and
  `make nixie`; unrelated formatter churn is reverted.
- Observation: the Rust core and PyO3 tests had duplicated repository-root and
  corpus fixture path helpers. Evidence: review comments and direct search
  showed local `repository_root` helpers in both test modules. Impact: a
  dev-only `stilyagi-test-support` crate now owns the shared Rust corpus path
  helpers and Markdown fixture path.
- Observation: inline Rust tests pushed `crates/stilyagi-extract/src/lib.rs`
  and `crates/stilyagi-pyext/src/lib.rs` beyond the 400-line review guideline.
  Evidence: `wc -l` reported 487 and 486 lines before the follow-up changes.
  Impact: extraction tests now live in
  `crates/stilyagi-extract/tests/extraction_tests.rs`, and PyO3 bridge BDD
  steps live in `crates/stilyagi-pyext/src/bridge_bdd.rs`; both library files
  are now under 400 lines.
- Observation: `mdformat-all` aligns Markdown table columns and may wrap link
  text. Evidence: the final `make test` run failed an exact table-spacing
  assertion after the valid Markdown fixture was formatted. Impact: the Python
  corpus test now asserts table content rather than exact Markdown table
  spacing.

## Decision Log

- Decision: keep 1.3.1 scoped to source fixtures and minimal test readers,
  deferring golden IR, CLI snapshot, and fix round-trip helpers to 1.3.2.
  Rationale: `docs/roadmap.md` assigns those helpers to the next roadmap item,
  and combining them here would obscure the fixture-corpus contract.
  Date/Author: 2026-04-30T19:30:54Z, Codex.
- Decision: use `tests/fixtures/corpus/` as the proposed shared corpus root.
  Rationale: `tests/fixtures/` already exists for checked-in test inputs, while
  `tests/golden/` and other future directories should not be created before
  they are used. Date/Author: 2026-04-30T19:30:54Z, Codex.
- Decision: do not require a user-guide update unless implementation changes
  user-visible behaviour or public API. Rationale: a shared internal fixture
  corpus is primarily developer-facing. Date/Author: 2026-04-30T19:30:54Z,
  Codex.
- Decision: keep the initial corpus to one valid and one malformed fixture per
  syntax. Rationale: the valid fixtures can cover multiple required constructs
  while staying within the plan's file-count and fixture-count tolerances.
  Date/Author: 2026-05-01T00:00:00Z, Codex.
- Decision: reuse the existing Rust bridge feature file for Rust BDD coverage.
  Rationale: the shared Markdown fixture is exercised through the same PyO3
  bridge behaviour surface that already proves Markdown extraction.
  Date/Author: 2026-05-01T00:00:00Z, Codex.
- Decision: move Python corpus BDD coverage into
  `features/stilyagi_fixture_corpus.feature` and keep the helper local to
  `tests/test_corpus.py`. Rationale: `tests/test_package_structure_bdd.py`
  automatically collects every scenario from the package-structure feature, so
  reusing that file required duplicate step wiring and pushed the branch over
  the fifteen-file tolerance. Date/Author: 2026-05-01T00:00:00Z, Codex.
- Decision: store intentionally invalid Python source as `.py.txt` in
  `tests/fixtures/corpus/python/malformed/`. Rationale: the source is still a
  Python fixture, but the suffix prevents Ruff from treating invalid recovery
  input as format-checkable Python code. Date/Author: 2026-05-01T00:00:00Z,
  Codex.
- Decision: do not update `docs/users-guide.md`. Rationale: the change adds
  developer-facing test fixtures and internal test helpers only; it does not
  alter CLI behaviour, public Python API behaviour, or supported user workflow.
  Date/Author: 2026-05-01T00:00:00Z, Codex.

## Outcomes & Retrospective

Complete. The shared corpus now exists under `tests/fixtures/corpus/` with
valid and malformed Markdown, Python, and Rust source inputs. Rust unit tests
read malformed corpus files and exercise Markdown extraction from the shared
Markdown fixture. Rust `rstest-bdd` coverage now extracts that same shared
Markdown fixture through the PyO3 bridge. Python unit tests and a
`pytest-bdd` scenario prove that every v1 syntax has valid and malformed
fixtures and that malformed inputs are read as source text without being
executed.

Documentation now records the corpus location and conventions in
`docs/developers-guide.md` and `docs/stilyagi-design.md`. The roadmap entry
for 1.3.1 is marked done. `docs/users-guide.md` was intentionally not changed
because this slice does not alter user-visible behaviour.

Validation passed with `make check-fmt`, `make lint`, `make test`,
`make markdownlint`, and `make nixie`. `make fmt` was also attempted, but it
still reports pre-existing MD013 line-length failures in older documentation
outside this branch after running `mdformat-all`; branch-local formatter churn
was corrected or reverted.

## Artifacts and notes

Planning used a Wyvern agent to independently inspect roadmap scope, existing
test surfaces, likely fixture layout, documentation updates, and risks. The
agent found the same key boundary captured in this plan: Python and Rust source
fixtures are required now, but their extraction outputs should not be claimed
until later extractor slices implement them.

Revision note: initial draft created for approval. It defines the corpus scope,
constraints, tolerances, risks, implementation milestones, validation gates,
and the explicit stop before implementation.
