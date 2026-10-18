# Inject clock, subprocess, and environment dependencies into the structural probe

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
`Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`, `Decision Log`,
and `Outcomes & Retrospective` must be kept up to date as work proceeds.

Status: COMPLETE

## Purpose / big picture

Roadmap item 1.3.3 delivered a repository-local cold and warm structural
performance probe, landing in pull request (PR) #16 and merged as commit
`face7ed`. The review of that PR identified that the probe hard-codes its
infrastructure dependencies, so the measurement orchestration cannot be unit
tested without spawning real subprocesses, reading real files, and consulting
the real clock and platform.

The observable outcome of this task is that the three infrastructure seams in
the probe are injectable callables with production defaults. A test can drive
`_measure_run` down the cold path with a stub subprocess runner and down the
warm path with a stub clock, can force `_measure_cold_iteration` to fail in
each of its three documented ways without a real child process, can pin the
report's environment section to fixed values, and can call `measure_probe` with
source text supplied by the caller rather than read from the fixture on disk.
Existing command-line behaviour, JSON schema, and the recorded baseline all
stay byte-identical.

Issue: <https://github.com/leynos/stilyagi/issues/17>

## Context and orientation

The probe lives in the maintainer-facing package `tests/performance/`, which
`docs/repository-layout.md` section 5 reserves for "performance probes and
baselines used to check cold and warm structural behaviour". The package was
split into three modules before this task began:

- `tests/performance/structural_probe.py` (368 lines) holds the probe entry
  point, fixture discovery, report building, redaction, the argument parser, and
  `main`.
- `tests/performance/structural_probe_execution.py` (109 lines) holds the
  measurement loop: `measure_probe`, `measure_extraction`, `_measure_run`,
  `_measure_cold_iteration`.
- `tests/performance/structural_probe_reporting.py` (82 lines) holds the
  typed-dictionary JSON payloads (`ReportPayload`, `RunPayload`,
  `EnvironmentPayload`, `CorpusPayload`, `SummaryNs`),
  `normalise_repository_path`, and `summarise_durations`.

`tests/test_structural_performance_probe.py` (399 lines) is the single test
module: one `pytest-bdd` scenario driven from
`features/stilyagi_structural_performance_probe.feature`, plus unit tests and a
`syrupy` JSON snapshot.

Three infrastructure dependencies must become injectable. Each is a call that
leaves the process from a function that should be testable without it:

- `structural_probe_execution.measure_extraction` calls
  `time.perf_counter_ns()` directly, so extraction timing cannot be stubbed.
- `structural_probe_execution._measure_cold_iteration` calls `subprocess.run`
  directly, so cold-path tests must spawn a real interpreter.
- `structural_probe.build_report` calls `platform.platform()` and
  `platform.python_version()` inline, so the environment section cannot be
  pinned.

Two further call-chain problems follow from those, and are the reason the first
three are not the whole task:

- `structural_probe_execution._measure_run` calls `_measure_cold_iteration`
  and `measure_extraction` directly, so cold and warm cannot be distinguished
  without a real subprocess. Injecting the clock and the runner is what makes
  this distinction observable.
- `structural_probe.measure_probe` delegates to the execution module, which
  calls `fixture.path.read_text()` internally, so fixture content cannot be
  injected at all. This one is fixed by passing data rather than by a port.

Issue #17 also asks to remove `# type: ignore[return-value]` suppressions in
`redact_report` and `_redact_run`. Those suppressions no longer exist: PR #16's
later review rounds replaced the untyped `dict[str, object]` report shape with
the `TypedDict` payloads in `structural_probe_reporting.py`, and
`git grep -n "type: ignore" HEAD -- '*.py'` now returns nothing across the
repository. The redaction functions already construct their payloads through the
`TypedDict` constructor, which is what issue #17 asks for. This part of the
issue is therefore already satisfied, and is recorded here so a reader does not
look for work that cannot be found. The verification is re-run and recorded in
`Progress`.

### Hard numeric limits

These come from `pyproject.toml` and were confirmed empirically during
planning. They shape the design and are not negotiable:

- `[tool.ruff.lint.pylint] max-args = 4` counts keyword-only parameters. A
  probe-scoped callable defaulted parameter therefore makes `build_report` and
  `measure_probe` exceed the limit.
- `[tool.ruff.lint.mccabe] max-complexity = 8` and
  `[tool.pylint.design] max-statements = 70` bound `main`, whose cold-run path
  already imports, reads, measures, and prints.
- `[tool.pylint.main] max-module-lines = 400` bounds every module.
  `structural_probe.py` is at 368 of 400 with the new code to be added.
- `ruff rule B008` forbids a function call in an argument default. A frozen
  dataclass used as a default must be passed as the class itself (a
  module-level name, which passes), not as an instance. `ruff rule RUF009`
  enforces the same for report payload classes.

## Constraints

- Preserve all existing command-line behaviour, the JSON schema, the snapshot
  at `tests/__snapshots__/test_structural_performance_probe/`, and the
  re-exported public names in `tests/performance/structural_probe.py`. This is
  a testability refactor, not a behaviour change.
- Do not add a public Python or Rust API for measurement. The probe stays
  under `tests/performance/`, per the 1.3.3 ExecPlan constraint.
- Do not introduce a performance budget or a timing threshold into any test.
  The 1.3.3 ExecPlan forbids turning timing noise into a pass/fail threshold.
- Do not make tests hermetic by monkeypatching. Issue #17 asks for explicit
  callable injection; a monkeypatched seam gives no tests for the real
  subprocess, platform, or clock path.
- Every new function needs a docstring, because `interrogate --fail-under 100`
  covers both `python/stilyagi` and `tests`.
- Keep en-GB-oxendict spelling in prose and comments.
- Run gates sequentially, never in parallel.

## Tolerances (exception triggers)

- Scope: if the change needs more than eight files or roughly 500 net new
  lines, stop and explain before continuing.
- Behaviour: if any existing test needs its assertion changed rather than its
  call signature, stop and explain. That would mean the refactor changed
  behaviour.
- Public API: if the `stilyagi` package's public surface must change, stop and
  request approval.
- Schema: if the JSON report schema must change, stop and request approval.
- Gates: if a gate failure cannot be fixed without suppressing a rule, stop and
  request approval rather than adding a suppression.

## Risks

The main risk is that threading four dependencies through five functions pushes
three of them past the `max-args = 4` ceiling and `main` past its complexity
and statement ceilings. The mitigation is to bundle the three testability seams
into one frozen dataclass passed as a single keyword-only argument, which the
`python-data-shapes` skill calls a typed kwargs payload. Gathering related
parameters into a struct with a domain-appropriate name is also what
`AGENTS.md` prescribes when a function has too many parameters. The three seams
are a clump: they are always bound together at the command boundary and handed
down the same call chain, which is the "data clumps" signal listed under the
refactoring heuristics in `AGENTS.md`.

A second risk is that passing a bundle to the leaf functions that only need one
seam is abstraction leakage of a different kind. `_measure_extraction` needs
only the clock and `_measure_cold_iteration` needs only the subprocess runner,
so both keep their single, directly-named parameter, and both keep a real
default so existing callers are unaffected.

A third risk is lint-boundary interaction with the bundle default.
`ruff rule RUF009` only fires on `dataclasses.field`-like call defaults in
classes, so a data class is safe to declare as a function default; `B008`
permits a default that is a module-level name rather than a call. Both were
verified empirically before implementation.

## Plan of work

Milestone 1 adds the injection seams. The ports and the bundles that carry them
live in a new module, `tests/performance/structural_probe_boundary.py`, which
is now the only place in the probe that names `time`, `subprocess.run`, or
`platform`. Three module-level PEP 695 aliases sit beside the constants:

```python
type ClockFn = cabc.Callable[[], int]
type SubprocessRunner = cabc.Callable[..., subprocess.CompletedProcess[str]]
type EnvironmentProvider = cabc.Callable[[], EnvironmentPayload]
```

`cabc` must be imported at runtime, not inside `if typ.TYPE_CHECKING`, because
the aliases are lazy: reading `ClockFn.__value__` evaluates the right-hand side
in the module namespace, and a `TYPE_CHECKING`-only binding raises `NameError`.
Ruff accepts the guarded form, so nothing but a runtime read catches this; it
was caught in review and confirmed against the interpreter. A frozen slotted
`ProbeDependencies` dataclass holds `clock`, `subprocess_runner`, and
`environment_provider`, defaulting to `time.perf_counter_ns`, `subprocess.run`,
and a new `default_environment()` helper that reads `platform.platform()` and
`platform.python_version()`. Its single instance, `DEFAULT_DEPENDENCIES`, is
the default for every injectable probe parameter.

Fixtures travel as data rather than through a fourth callable port.
`ProbeRequest` holds `path`, `source`, `syntax`, and `byte_count`, read once by
`ProbeRequest.from_fixture`; `ProbeCorpus` holds the already-read requests plus
the root their report paths are recorded against. That is what makes
`measure_probe` file-free once the corpus exists: no measurement function reads
a path or a size.

Then thread the seams:

- `measure_extraction(source, syntax, *, clock=DEFAULT_DEPENDENCIES.clock)`.
- `_measure_cold_iteration(request, *, dependencies=DEFAULT_DEPENDENCIES)`.
- `_measure_run(*, mode, iterations, request, dependencies=DEFAULT_DEPENDENCIES)`.
- `build_report(*, corpus, runs, environment_provider=default_environment)`.
- `measure_probe(*, mode, iterations, root, dependencies=DEFAULT_DEPENDENCIES)`,
  in both the re-export and the execution module.

`main` continues to call `discover_structural_fixtures()` and read the chosen
fixture itself, which is how the child-run mode still works from the command
line.

Milestone 2 adds the unit tests. Every module in scope currently parses and
lints clean, so failing tests must be written before the production change to
prove they are not vacuous. The tests cover:

- `_measure_run` cold path calls the injected runner and never the clock;
- `_measure_run` warm path calls the injected clock and never the runner;
- `_measure_cold_iteration` builds an argument vector containing `--child-run`
  and `--source`;
- `_measure_cold_iteration` propagates a raised `CalledProcessError`;
- `_measure_cold_iteration` rejects non-JSON stdout with `json.JSONDecodeError`;
- `_measure_cold_iteration` rejects a non-integer `duration_ns` with
  `TypeError`;
- `build_report` returns the injected environment payload verbatim;
- `measure_probe` uses the injected source and touches no filesystem.

Milestone 3 records the work. Update `docs/developers-guide.md` where it
describes the probe: add a "Probe ports and adapters" subsection naming each
port, its production adapter, and why they are bundled. Update
`docs/stilyagi-design.md` where the validation plan describes the baseline, so
it names the three-syntax corpus rather than the Markdown fixture alone. Re-run
the gates and commit.

## Validation

The acceptance evidence is:

1. `make check-fmt`, `make typecheck`, `make lint`, `make test`,
   `make markdownlint`, and `make nixie` all pass on the final tip.
2. `tests/test_structural_performance_probe.py` passes unchanged in its
   existing assertions, including the JSON snapshot, proving the refactor did
   not move the observable contract.
3. The new tests fail against the pre-change code and pass against the
   post-change code.
4. The end-to-end `pytest-bdd` scenario still runs the probe as a real
   subprocess and still produces cold and warm runs, proving the production
   defaults are correctly wired.
5. `coderabbit review --agent` raises no unresolved concerns.

## Surprises & Discoveries

- The `# type: ignore[return-value]` suppressions named in issue #17 no longer
  exist. `git grep -n "type: ignore" HEAD -- '*.py'` returns nothing, and
  `git log --all -S'type: ignore[return-value]' -- '*.py'` finds no commit that
  ever introduced one. A later review round on PR #16 replaced the untyped
  report shape with the `TypedDict` payloads and removed the need for casts and
  ignores. The issue text is stale on this point.
- `ruff`'s `max-args = 4` counts keyword-only parameters. A five-keyword-only
  function fails `PLR0913`. This is the single constraint that forced the
  dependency bundle.
- `ruff rule B008` permits a module-level class name as a default but rejects a
  call in the default position, and `RUF009` does not fire on function
  defaults. A frozen data class is therefore the safe carrier for the bundle.
- Ruff reports `unresolved-reference` on a PEP 695 `type` alias whose right-hand
  side names an imported symbol that lives only in a type-checking block. The
  alias's imports must be at runtime.
- `build_report` still reached the filesystem after the first pass, through
  `fixture.path.stat().st_size`. Two of the new tests caught it: they supply a
  synthetic request whose `byte_count` disagrees with the fixture's real size
  and assert the caller's value survives into the report. The fix was to change
  `build_report` from taking `repository_root` plus fixtures to taking a
  `ProbeCorpus`, so byte counts can only come from the request. A test that
  asserts on a value the implementation could have re-derived is what makes the
  seam verifiable; without the deliberate mismatch, an implementation that read
  the disk would pass.
- Ruff's `property-docstring-starts-with-verb` rejects "Return the …" on a
  `@property`, and `DOC502` rejects a `Raises` section that documents an
  exception the function only propagates. Propagation is described in the
  docstring prose instead.

## Decision Log

- Decision: bundle the clock, subprocess runner, and environment factory into
  one frozen data class rather than adding three separate keyword-only
  parameters. Rationale: `max-args = 4` counts keyword-only parameters, so
  three extra parameters breach the ceiling in `build_report` and
  `measure_probe`. The three seams are a genuine data clump: they are bound
  once at the command boundary and travel together down the same chain.
  `AGENTS.md` prescribes grouping related parameters in meaningfully named
  structs and warns against data clumps and excessive parameters. Date:
  2026-10-13

- Decision: keep `clock` and `subprocess_runner` as directly named single
  parameters with production defaults on `measure_extraction` and
  `_measure_cold_iteration`, rather than passing the bundle down. Rationale:
  each leaf needs exactly one seam, so naming it keeps the leaf honest and
  keeps every pre-existing caller source-compatible. Only `_measure_run` and
  the two entry points take the bundle. Date: 2026-10-13

- Decision: pass source text into `measure_probe` rather than having it read the
  fixture. Rationale: goal 5 of issue #17. It also mirrors `main`, which must
  read the path chosen by `--source` for the child-run mode anyway. Date:
  2026-10-13

- Decision: do not change `# type: ignore` suppressions, because none exist.
  Rationale: issue #17's fourth bullet is already satisfied by the `TypedDict`
  payloads delivered during PR #16 review. Recorded rather than silently
  skipped so the discrepancy is auditable. Date: 2026-10-13

- Decision: collect the ports and their bundles in a new boundary module rather
  than growing `structural_probe_execution.py`, and have `structural_probe.py`
  re-export them. Rationale: `structural_probe.py` was at 368 of 400 lines, so
  the ports could not be added there without breaching the module ceiling, and
  `structural_probe_execution.py` is the measurement loop rather than the
  outside world. A named boundary module also states the dependency rule in the
  file layout: every call that leaves the process is in one file, and the
  measurement loop depends only on the ports it defines. `structural_probe.py`
  keeps its re-exports so the pre-existing public names stay importable. Date:
  2026-10-13

- Decision: carry fixtures as an in-memory `ProbeCorpus` of `ProbeRequest`
  values rather than adding a fourth callable port for reading source.
  Rationale: issue #17 asks for source text as a `measure_probe` parameter, not
  for a reader port. Reading once, up front, in `read_probe_corpus` satisfies
  that directly and removes the remaining filesystem dependency from the
  measurement path, which the byte-count tests then pin. It also keeps
  `build_report` at three parameters instead of needing both a root and a
  provider per fixture. Date: 2026-10-13

- Decision: carry the request's source text across the child-process boundary
  rather than having the child reopen `--source`. Rationale: CodeRabbit review
  found that a `ProbeRequest` whose `source` differs from its `path` would be
  measured as the file, silently benchmarketing the wrong text. The argv is a
  list, so no shell re-parses the text, and the path still travels for error
  messages and manual reproduction. A request too large for the platform's
  argument limit fails loudly with `OSError` rather than silently measuring the
  wrong thing, which is the failure mode worth having. Date: 2026-10-18

- Decision: move the shared corpus read from module import into a
  module-scoped `structural_corpus` fixture. Rationale: CodeRabbit review found
  that an import-time read raises `FileNotFoundError` during collection, which
  aborts every test in the module rather than the four that need the corpus. No
  `testpaths` is configured, so this is a real exposure rather than a
  hypothetical one. Renamed from `MARKDOWN_CORPUS` because the corpus holds
  Markdown, Python, and Rust requests. Date: 2026-10-18

- Decision: import `collections.abc as cabc` at module scope in the boundary
  module. Rationale: CodeRabbit review found that the PEP 695 aliases are lazy,
  so reading `ClockFn.__value__` under a `TYPE_CHECKING`-only binding raises
  `NameError`. Confirmed against the interpreter. Ruff accepts the guarded
  form, so only a runtime read catches it. Date: 2026-10-18

## Progress

- [x] 2026-10-13: Renamed the worktree branch to
  `issue-17-inject-clock-subprocess-and-environment-dependencies-into-structural-probe-for-testability`
  and set the Lody session title.
- [x] 2026-10-13: Reconnaissance. Read all three probe modules, the test
  module, the feature file, the 1.3.3 ExecPlan, `pyproject.toml` lint limits,
  and the developers' guide probe section. Confirmed the `type: ignore` bullet
  is stale.
- [x] 2026-10-13: Milestone 1, injection seams. Added
  `tests/performance/structural_probe_boundary.py` with the three ports, the
  `ProbeDependencies` bundle, `default_environment`, `ProbeRequest`,
  `ProbeCorpus`, and `read_probe_corpus`; rewrote the measurement loop in
  `structural_probe_execution.py` to take its clock, runner, and request from
  parameters; changed `build_report` to take a `ProbeCorpus` so corpus totals
  come from the requests.
- [x] 2026-10-13: Milestone 2, unit tests. Added
  `tests/test_structural_probe_injection.py` covering both `_measure_run`
  paths, all three `_measure_cold_iteration` failure modes, the argv the child
  command is built from, the injected environment provider, and the fact that
  `measure_probe` reads no file. Updated the four `build_report` call sites in
  the existing test module for the new signature.
- [x] 2026-10-18: Milestone 3, docs and gates. Added the "Probe ports and
  adapters" subsection to the developers' guide, corrected the design
  document's validation plan to name all three corpus syntaxes, and ran every
  commit gate. `make check-fmt`, `make lint`, `make typecheck`,
  `make markdownlint`, and `make nixie` passed first time. `make test` needed
  two re-runs: the first two attempts timed out on two `trybuild` tests that
  sat behind shared Cargo-cache and compile-admission contention, which had the
  scratch crate still linking when the 600 s override expired. Warming those
  two tests under the gate's own `RUSTFLAGS`, `--all-features`, and nextest
  profile immediately before dispatch made the third run pass: 357 Rust tests,
  608 Python tests, and 38 doctest targets.
- [x] 2026-10-13: Ran the focused checks: `ruff check` clean,
      `ruff format --check` clean, `pylint` 10.00/10,
      `interrogate --fail-under 100` at 100.0%,
      and 28 probe tests passing with the JSON snapshot unchanged.
- [x] 2026-10-18: CodeRabbit review round one. Six findings, two of them
  duplicates of each other, which reduced to four distinct items. Three were
  real and were fixed: the runtime `cabc` binding for the lazy PEP 695 aliases,
  the cold child protocol transmitting source text rather than reopening the
  path, and the import-time corpus read that could abort collection. One was a
  documentation-accuracy fix in this plan. Re-ran every gate: check-fmt, lint,
  typecheck, markdownlint, and nixie green; `make test` once more hit the same
  `compile_time_ui` contention and passed on a warm re-run. Final counts: 357
  Rust tests, 612 Python tests, 38 doctest targets.

## Outcomes & Retrospective

The probe now reaches the outside world through three named ports and takes its
inputs as data. `tests/performance/structural_probe_boundary.py` owns every
outbound call: `ClockFn` (default `time.perf_counter_ns`), `SubprocessRunner`
(default `subprocess.run`), and `EnvironmentProvider` (default
`default_environment`, backed by `platform`). It also owns `ProbeRequest`,
which carries the text and byte count read once by `read_probe_corpus`, and
`ProbeCorpus`, which carries the already-read requests. `ProbeDependencies`
bundles the three ports so every function stays inside the four-parameter
ceiling.

`structural_probe_execution.py` is now a measurement loop over those ports, and
`structural_probe.py` re-exports the boundary names so the pre-existing public
surface is unchanged. `build_report` takes a `ProbeCorpus` and reads its totals
from the requests, so nothing in the report path touches the filesystem.
`measure_probe` takes the corpus rather than a root, satisfying the issue's
request that source text travel as a parameter.

`tests/test_structural_probe_injection.py` is the evidence that the seams are
real rather than nominal: twelve tests drive the cold path through a stub
runner with a clock that fails if read, the warm path through a stub clock with
a runner that fails if called, all three child-failure modes, the argv the
child command is built from, an injected environment payload, and a
`measure_probe` call with `Path.read_text` disabled. A byte-count test pins the
corpus totals to the caller's request, so a fallback to `Path.stat` would fail
it.

Two things are worth recording for the next maintainer.

First, the issue's fourth bullet, remove the `type: ignore[return-value]`
suppressions, was already satisfied. No such suppression exists in the tree; the
`TypedDict` payloads delivered during the PR #16 review replaced them. The
Decision Log records this rather than leaving the bullet silently unaddressed.

Second, `make test` compiles the `trybuild` scratch crates inside the per-test
600 s nextest override. Under shared Cargo-cache and compile-admission
contention that compile exceeded the budget twice, timing out two tests that
have no relation to this change. The gate passed once those two tests were
compiled first under the gate's exact flags, which is the shape of the
contention rather than a property of the code. It is worth knowing before
blaming a future timeout on whatever change happens to be in the tree.
