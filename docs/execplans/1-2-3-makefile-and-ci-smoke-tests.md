# Wire Makefile and CI smoke tests to the mixed package spine

This ExecPlan (execution plan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work
proceeds.

Status: COMPLETE

Approval gate: approved for implementation on 2026-04-24. Implementation must
remain within the constraints and tolerances below.

## Purpose / big picture

Roadmap item 1.2.3 exists to make the mixed Rust and Python package skeleton
usable through one reproducible build spine. After roadmap items 1.2.1 and
1.2.2, the repository already has a `python/` source root, a Cargo workspace in
`crates/`, and an in-process PyO3 bridge exposed as `stilyagi._stilyagi_rs`.
This slice should make those boundaries the normal local and CI path rather
than something developers remember to exercise manually.

The observable outcome is that `make build` and `make release` remain the
canonical workflows and both prove the same boundary: Python imports the
installed package, calls the public engine surface, and receives a document
created through the embedded Rust extension rather than through a helper
binary. A maintainer should also be able to inspect GitHub Actions and see the
same smoke path used in CI.

## Orientation

The repository is already on the long-lived layout described in
[docs/stilyagi-design.md](../stilyagi-design.md) section 10. The current
Makefile defines `make build`, `make release`, `make lint`, `make typecheck`,
`make test`, `make markdownlint`, and `make nixie`. The package metadata in
`pyproject.toml` points `maturin` at `crates/stilyagi-pyext/Cargo.toml`, sets
`python-source = "python"`, and builds the extension module as
`stilyagi._stilyagi_rs`.

There is no `.github/workflows/` directory in this worktree at the time this
plan is drafted. Creating CI is therefore part of this slice, but it must stay
smoke-focused. This item is not the place to add a full release matrix, publish
wheels, expand CLI behaviour, or redesign the extractor.

## Documentation and skill signposts

The implementer should keep these documents open while executing the plan:

- [docs/roadmap.md](../roadmap.md) for the exact 1.2.3 scope, dependency on
  1.2.1 and 1.2.2, and the final "done" update.
- [docs/stilyagi-design.md](../stilyagi-design.md), especially sections 7.3,
  8, 10, and 11, for the CLI and CI parity expectations, packaging risk,
  repository layout, and validation classes.
- [docs/adr-002-packaging-boundary.md](../adr-002-packaging-boundary.md) for
  the accepted PyO3 plus `maturin` boundary and rejection of helper-binary
  transport for normal execution.
- [docs/adr-003-v1-contract-scope.md](../adr-003-v1-contract-scope.md) for the
  v1 syntax and transport scope that the smoke path must not broaden.
- [docs/developers-guide.md](../developers-guide.md) for the local build,
  verification, and internal boundary guidance that must reflect any new smoke
  target or CI practice.
- [docs/users-guide.md](../users-guide.md) for any user-visible change to the
  supported install or release-artifact smoke behaviour.
- [docs/local-validation-of-github-actions-with-act-and-pytest.md](
  ../local-validation-of-github-actions-with-act-and-pytest.md) for local CI
  workflow validation expectations if the new GitHub Actions workflow can be
  exercised with `act`.
- [docs/complexity-antipatterns-and-refactoring-strategies.md](
  ../complexity-antipatterns-and-refactoring-strategies.md) to keep Makefile
  and CI logic simple, explicit, and resistant to duplicated command strings.
- [docs/rust-testing-with-rstest-fixtures.md](
  ../rust-testing-with-rstest-fixtures.md) for Rust fixture style.
- [docs/rust-doctest-dry-guide.md](../rust-doctest-dry-guide.md) for Rust
  doctest expectations.
- [docs/reliable-testing-in-rust-via-dependency-injection.md](
  ../reliable-testing-in-rust-via-dependency-injection.md) for testable Rust
  dependency boundaries.
- [docs/rstest-bdd-users-guide.md](../rstest-bdd-users-guide.md) for Rust
  behaviour-test style.

The relevant skills for the implementer are:

- `execplans` to keep this plan current during implementation.
- `leta` for symbol-aware code navigation when inspecting the current bridge.
- `rust-router`, then `arch-crate-design`, if Makefile or CI failures expose a
  Rust crate-boundary problem.
- `rust-errors` if the smoke helper has to classify failures from the bridge or
  release-artifact import path.
- `domain-cli-and-daemons` if the work touches CLI invocation behaviour rather
  than only package import and extraction smoke tests.

## Constraints

- This slice is roadmap item 1.2.3. It depends on 1.2.1 and 1.2.2 and must
  preserve their repository layout and in-process PyO3 extraction boundary.
- Keep `make build` and `make release` as the canonical workflows. New helper
  targets may exist, but they must support these entry points rather than
  replace them.
- Development installs and release artefacts must exercise the same boundary:
  Python imports the package, calls the public engine extraction API, and
  crosses into Rust through `stilyagi._stilyagi_rs`.
- Do not introduce a helper binary, subprocess transport, JSON-over-stdio
  bridge, or pure-Python fallback to satisfy the smoke path.
- Keep this slice build-spine focused. Do not implement the full CLI contract,
  the full intermediate representation (IR), rule execution, suppression
  parsing, or wheel publishing matrix.
- Add or modify tests before changing behaviour. The initial test run should
  fail for the missing Makefile or CI smoke guarantee, then pass after the
  implementation.
- Use `rstest` for Rust unit coverage and `rstest-bdd` for Rust behavioural
  coverage when Rust-side smoke contracts change. Use `pytest` and `pytest-bdd`
  for Python unit and behavioural coverage when package-level or workflow smoke
  behaviour changes.
- Update design documentation when a build or CI design decision is taken.
  Update the user and developer guides for any changed user command, release
  artefact expectation, or development practice.
- Mark roadmap item 1.2.3 as done only after tests, docs, CI workflow files,
  Makefile changes, and validation gates all pass.
- Commit the completed implementation only after the quality gates pass.

## Tolerances

- Scope: if implementation needs more than twelve files or roughly 450 net new
  lines, stop and explain why. This should be a build-spine smoke slice, not a
  hidden release-system rewrite.
- CI breadth: if the work needs more than one new GitHub Actions workflow or a
  cross-platform wheel matrix, stop and ask for approval. Cross-platform wheel
  release hardening is a later concern unless the user explicitly expands this
  slice.
- Interface: if satisfying the smoke path appears to require renaming
  `stilyagi`, `_stilyagi_rs`, `make build`, or `make release`, stop and ask for
  confirmation.
- Dependencies: if any new third-party Rust or Python dependency is needed,
  stop and justify it. The existing `pytest`, `pytest-bdd`, `rstest`,
  `rstest-bdd`, `maturin`, and `uv` tooling should be enough.
- Workflow tools: if CI requires a hosted tool that is not already documented
  as part of the local development environment, either document it explicitly
  or stop if the dependency changes local prerequisites.
- Validation: if `make check-fmt`, `make lint`, or `make test` still fails
  after two focused correction passes, stop and capture the failing log paths.
- Environment: if failures are caused by missing system tools, unavailable
  Python 3.14, Cargo package-cache contention, or GitHub Actions behaviour that
  cannot be reproduced locally, document the evidence and ask before working
  around the environment.

## Risks

- Risk: no CI workflow exists yet, so adding one can easily expand into a full
  release matrix. Severity: high. Likelihood: medium. Mitigation: create a
  single smoke workflow that runs the canonical Makefile targets and package
  smoke checks, leaving publishing and platform matrices to later roadmap items.
- Risk: `make build` and `make release` might drift by using different import
  or bridge checks. Severity: high. Likelihood: medium. Mitigation: factor the
  smoke proof into one reusable script, test, or Makefile target that both
  workflows invoke.
- Risk: release artefact tests may accidentally import the source tree instead
  of the built wheel. Severity: high. Likelihood: medium. Mitigation: run the
  release smoke from an isolated working directory or use a command that proves
  the installed artefact path before calling `stilyagi.engine.extract_document`.
- Risk: CI may pass while local developers still bypass the PyO3 boundary.
  Severity: medium. Likelihood: medium. Mitigation: keep `make build` as the
  local path and make CI call it instead of duplicating ad hoc `uv` and
  `maturin` commands.
- Risk: adding Makefile smoke logic can duplicate shell fragments and make
  future changes brittle. Severity: medium. Likelihood: medium. Mitigation:
  prefer one explicit target or helper script with clear names over repeated
  inline snippets across Makefile and workflow YAML.
- Risk: documentation could overstate feature readiness by describing CI smoke
  as product release readiness. Severity: medium. Likelihood: medium.
  Mitigation: describe the new workflow as a smoke path for the mixed package
  boundary, not as final release automation.

## Proposed implementation shape

Add a small smoke contract that can be reused locally and in CI. The preferred
shape is one Makefile target, tentatively named `smoke`, that assumes the
current environment has already been built and then runs a Python command
through `.venv/bin/python`. That command should import `stilyagi.engine`, call
`extract_document("# Title", Syntax.MARKDOWN)` or the current public
equivalent, and assert that the returned document reports Markdown syntax and
at least one region backed by Rust extraction. If the public API names differ
during implementation, update this plan with the exact names before changing
code.

Keep `make build` responsible for development installation with
`maturin develop`, and have it run or clearly enable the same smoke target.
Keep `make release` responsible for building a wheel with
`maturin build --release`, then add a release smoke target that installs the
built wheel into a fresh environment or otherwise proves the artefact can be
imported without falling back to the source tree.

Add one GitHub Actions workflow under `.github/workflows/`, tentatively named
`smoke.yml`. It should check out the repository, install Python, install the
Rust toolchain, install required command-line tools, and run the canonical
Makefile gates sequentially. The workflow should call Makefile targets rather
than duplicating the underlying `uv`, `maturin`, Cargo, and pytest commands.

## Milestone 1: capture current smoke gaps with failing tests

Start by identifying the existing tests that prove package import and bridge
behaviour:

- `tests/test_package_smoke.py`
- `tests/test_package_skeleton_units.py`
- `tests/test_package_structure_bdd.py`
- `crates/stilyagi-pyext/tests/features/bridge_structure.feature`
- Rust tests in `crates/stilyagi-pyext/src/lib.rs` and
  `crates/stilyagi-extract/src/lib.rs`

Add or update the smallest tests that express the missing 1.2.3 behaviour. Good
candidates are:

- a Python `pytest` unit test that calls the same smoke helper used by the
  Makefile;
- a `pytest-bdd` scenario in `features/` proving a development install exposes
  the Rust-backed extraction boundary;
- a Rust `rstest` unit test only if the existing Rust bridge smoke does not
  already cover the underlying extraction result; and
- a Rust `rstest-bdd` scenario only if the PyO3 bridge behaviour changes.

Run the targeted tests before implementation and capture the failing output in
`/tmp/test-stilyagi-feat-plan-makefile-ci-smoke.out` or a similarly specific
log file. The expected failure should be about the missing smoke target,
missing release artefact proof, or missing CI workflow contract, not about an
unrelated extractor regression.

## Milestone 2: make the local Makefile spine exercise the bridge

Update `Makefile` so the local build spine has explicit smoke semantics while
preserving the existing entry points:

- `make build` still recreates `.venv`, syncs the dev group with `uv`, and
  runs `maturin develop` against `crates/stilyagi-pyext/Cargo.toml`.
- `make release` still builds the release artefact with `maturin build
  --release` against the same PyO3 crate.
- a new or clarified smoke target proves that the installed package imports
  and calls the Rust-backed extraction path through the public Python API.
- any release smoke target proves the built artefact, not merely the source
  tree, can satisfy the same import and extraction smoke.

Prefer one reusable smoke helper over duplicating Python snippets in multiple
Makefile recipes. If a helper script is added, keep it under a repository path
that matches existing conventions and cover it with pytest.

## Milestone 3: add the CI smoke workflow

Create a bounded GitHub Actions workflow under `.github/workflows/`. The
workflow should be named for smoke or CI validation rather than publishing. It
should run on pull requests and pushes to the active branch patterns used by
the repository, unless existing project guidance says otherwise.

The workflow should run commands sequentially. A reasonable first pass is:

```yaml
name: Smoke

on:
  pull_request:
  push:

jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - install Python 3.14
      - install the Rust toolchain
      - install uv and required lint tools
      - run: make check-fmt
      - run: make lint
      - run: make test
      - run: make release
      - run: make smoke-release
```

The exact syntax should use maintained actions and documented setup steps, but
do not add publishing credentials, upload artefacts, or a platform matrix in
this slice. If local validation with `act` is practical, run it and record the
result. If it is not practical because Python 3.14, Rust, or nested container
support is unavailable, record that limitation instead of broadening the plan.

## Milestone 4: update documentation and design records

Update documentation in the same implementation change:

- `docs/stilyagi-design.md` should record any design decision about how local
  development installs and release artefacts share the same PyO3 smoke boundary.
- `docs/developers-guide.md` should describe the new or clarified Makefile
  smoke targets, the CI workflow, and the expected local verification order.
- `docs/users-guide.md` should be updated only for user-visible behaviour, such
  as a supported release artefact install smoke or changed install command.
- `docs/contents.md` should list this ExecPlan if it is not already listed.
- `docs/roadmap.md` must mark item 1.2.3 done only after all implementation
  and validation work is complete.

Keep the documentation precise. The new CI workflow proves the mixed package
boundary; it does not yet promise production-grade release automation.

## Milestone 5: validate sequentially and commit

Run formatting and gates sequentially, using `tee` to preserve logs under
`/tmp`:

```bash
make fmt 2>&1 | tee /tmp/fmt-stilyagi-feat-plan-makefile-ci-smoke.out
make check-fmt 2>&1 | tee /tmp/check-fmt-stilyagi-feat-plan-makefile-ci-smoke.out
make lint 2>&1 | tee /tmp/lint-stilyagi-feat-plan-makefile-ci-smoke.out
make typecheck 2>&1 | tee /tmp/typecheck-stilyagi-feat-plan-makefile-ci-smoke.out
make test 2>&1 | tee /tmp/test-stilyagi-feat-plan-makefile-ci-smoke.out
make markdownlint 2>&1 | tee /tmp/markdownlint-stilyagi-feat-plan-makefile-ci-smoke.out
make nixie 2>&1 | tee /tmp/nixie-stilyagi-feat-plan-makefile-ci-smoke.out
```

Also run the new smoke target or targets directly if they are not already
covered by `make test`, `make build`, and `make release`. The final state must
include a successful `make check-fmt`, `make lint`, and `make test` run, as
requested by the task.

After the gates pass, inspect `git diff` for unrelated changes. Commit only the
files that belong to this slice. The commit message should be imperative,
describe the Makefile and CI smoke path, and mention that the smoke path proves
the shared PyO3 boundary.

## Progress

- [x] 2026-04-24: Loaded the `execplans` and `leta` skills, confirmed the
  current branch is `feat/plan-makefile-ci-smoke`, and created this draft plan.
- [x] 2026-04-24: Used a Wyvern side agent for planning-only reconnaissance.
  The side agent confirmed there is no existing `.github/workflows/` directory
  and recommended keeping CI creation smoke-only.
- [x] 2026-04-24: Created a `context_pack` package for agent-team exchange
  named "Makefile and CI smoke plan context" with id `pk_kglg5xae`.
- [x] 2026-04-24: Received explicit user approval to proceed with
  implementation and moved this ExecPlan to `Status: IN PROGRESS`.
- [x] 2026-04-24: Added Python unit and `pytest-bdd` checks for the missing
  smoke path. The targeted run failed first with
  `ImportError: cannot import name 'smoke' from 'stilyagi'`, proving the
  missing shared helper.
- [x] 2026-04-24: Added `python -m stilyagi.smoke`, wired `make build` to
  `make smoke`, split release artifact construction into `release-artifact`,
  and wired `make release` to `smoke-release`.
- [x] 2026-04-24: Added `.github/workflows/smoke.yml` as a single bounded
  GitHub Actions workflow that calls `make check-fmt`, `make lint`,
  `make test`, and `make release`.
- [x] 2026-04-24: Re-ran the targeted tests in
  `/tmp/test-targeted-stilyagi-feat-plan-makefile-ci-smoke.out`; all eight
  targeted tests passed.
- [x] 2026-04-24: Updated `docs/stilyagi-design.md`,
  `docs/developers-guide.md`, and `docs/users-guide.md` with the shared smoke
  boundary, Makefile targets, and bounded CI workflow.
- [x] 2026-04-24: `make build` passed and ran the development smoke check
  through `.venv/bin/python -m stilyagi.smoke`.
- [x] 2026-04-24: The first `make release` run failed because the wheel was
  written to `target/wheels` while the release smoke installed from `dist`.
  Adding `--out dist` fixed the release artefact location.
- [x] 2026-04-24: `make release` passed after installing the fresh wheel from
  `dist/` into `.venv-release-smoke` and running `python -m stilyagi.smoke`
  from `/tmp`.
- [x] 2026-04-24: `make fmt`, `make check-fmt`, `make lint`,
  `make typecheck`, and `make test` passed. `make test` ran 44 Rust tests and
  31 Python tests.
- [x] 2026-04-24: The first `make markdownlint` run failed because
  `.venv-release-smoke` exposed pip's vendored Markdown licence files. The
  Makefile now excludes `.venv-release-smoke` from Markdown and Mermaid scans.
- [x] 2026-04-24: `make markdownlint`, `make nixie`, and
  `mbake validate Makefile` passed.
- [x] 2026-04-24: Marked roadmap item 1.2.3 done after implementation and
  validation.
- [x] 2026-04-24: Fixed the GitHub Actions resolver failure for
  `astral-sh/setup-uv@v8` by pinning the workflow to the existing
  `astral-sh/setup-uv@v8.1.0` tag.
- [x] 2026-04-24: Replaced the setup-uv version tag with the exact commit SHA
  `08807647e7069bb48b6ef5acd8ec9567f424441b` for `v8.1.0`.

## Surprises & Discoveries

- The current Makefile already has `build` and `release` targets wired to the
  mixed package layout, including `crates/stilyagi-pyext/Cargo.toml`.
- This worktree has no `.github/workflows/` directory, so the CI smoke path
  will likely be created from scratch.
- The existing `pyproject.toml` already declares `maturin` as the build backend
  and sets `module-name = "stilyagi._stilyagi_rs"` and
  `python-source = "python"`.
- Implementation will use the currently available public API
  `stilyagi.engine.extract_document("# Heading", stilyagi.model.Syntax.MARKDOWN)`
  as the shared smoke proof.
- The release smoke target should remove `dist/` immediately before building
  so `pip install --no-index --find-links dist stilyagi` cannot select a stale
  wheel from a previous run.
- `maturin build --release` writes wheels to `target/wheels` by default in this
  repository. The release smoke path needs `--out dist` so the expected install
  directory exists and contains only the fresh wheel for this run.
- Creating `.venv-release-smoke` exposed that `make markdownlint` and
  `make nixie` need to exclude generated virtual environments, or they scan
  pip's vendored licence Markdown files.
- GitHub could not resolve `astral-sh/setup-uv@v8`. The setup-uv repository
  has exact `v8.0.0` and `v8.1.0` tags, but no `v8` moving tag.

## Decision Log

- 2026-04-24: Keep this plan in `Status: DRAFT` and require explicit approval
  before implementation. Rationale: the user explicitly requested planning and
  stated that the plan must be approved before implementation.
- 2026-04-24: Treat CI creation as in scope but bounded to one smoke workflow.
  Rationale: no existing workflow files are present, and roadmap item 1.2.3
  specifically asks for a CI smoke path rather than a full release matrix.
- 2026-04-24: Prefer a reusable Makefile smoke target or helper over duplicated
  inline Python snippets. Rationale: both development installs and release
  artefacts must exercise the same boundary, and duplication would make the two
  paths drift.
- 2026-04-24: Implement the shared smoke proof as
  `python -m stilyagi.smoke`. Rationale: a package module is included in both
  development installs and release wheels, can be covered by `pytest`, and lets
  Makefile and CI call the same boundary check without embedding long Python
  snippets in shell recipes.
- 2026-04-24: Pin the workflow to maintained setup actions and exact action
  revisions, including `actions/checkout`, `astral-sh/setup-uv`, `setup-bun`,
  and the shared Rust setup action. Rationale: CI should use maintained setup
  actions, while the actual build logic remains in Makefile targets.
- 2026-04-24: Direct `maturin build --release` to `--out dist`. Rationale:
  `make smoke-release` installs from `dist` with `--no-index`; letting maturin
  use its default `target/wheels` path caused the first release smoke run to
  fail because the install directory did not exist.
- 2026-04-24: Exclude `.venv-release-smoke` from Markdown and Mermaid scans
  and remove it in `make clean`. Rationale: the release-smoke environment is a
  generated artefact and should not make repository documentation gates inspect
  pip's installed package metadata.
- 2026-04-24: Do not install `cargo-nextest` in the smoke workflow. Rationale:
  `make test` already falls back to `cargo test` when nextest is absent, and
  omitting the install keeps the CI smoke path narrower.
- 2026-04-24: Pin `astral-sh/setup-uv` to `v8.1.0` instead of `v8`.
  Rationale: GitHub Actions requires the referenced action version to exist,
  and the setup-uv repository publishes exact v8 release tags rather than a
  `v8` alias.
- 2026-04-24: Prefer the setup-uv commit SHA over the version tag in the
  workflow. Rationale: SHA pinning makes the action reference immutable while
  preserving the same verified `v8.1.0` code.

## Outcomes & Retrospective

Implemented the shared build-spine smoke path for roadmap item 1.2.3.
`python -m stilyagi.smoke` now exercises the public Python engine API backed by
the embedded Rust extension. `make build` runs that smoke proof after
`maturin develop`, and `make release` builds a fresh wheel into `dist/`,
installs it into `.venv-release-smoke`, and runs the same proof from `/tmp` to
avoid importing the repository source tree.

The repository now has a bounded `.github/workflows/smoke.yml` workflow that
sets up Python, Rust, `uv`, and documentation tools, then calls the canonical
Makefile gates rather than duplicating build logic. Documentation records the
new development and release practice, and `docs/roadmap.md` marks item 1.2.3 as
done.

The main lesson from implementation is that generated verification environments
must also be excluded from repository-wide documentation scans. The
release-smoke environment made the release proof more trustworthy, but it also
introduced installed package metadata under the worktree, so `make clean`,
`make markdownlint`, and `make nixie` now account for it explicitly.
