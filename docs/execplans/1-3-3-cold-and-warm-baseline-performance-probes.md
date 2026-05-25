# Add cold and warm structural performance probes

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
 `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`, `Decision Log`,
and `Outcomes & Retrospective` must be kept up to date as work proceeds.

Status: DRAFT

Approval gate: this plan must be approved before implementation starts.

## Purpose / big picture

Roadmap item 1.3.3 records the repository-local measurement method for cold and
warm structural runs before richer natural language processing (NLP) features
land. After this work, maintainers should be able to run one documented probe
that measures the current structural fast path through the mixed Python and
Rust build spine, records normalised machine-readable output, and gives later
roadmap slices a stable way to show they have not made structural-only runs
collapse.

The observable outcome is not a hard performance budget enforced on every
developer workstation. The observable outcome is a checked-in probe harness,
stable JSON output shape, documentation explaining how to run and interpret the
probe, and tests proving that cold and warm runs are classified and reported
deterministically. The first baseline should use the current public Python
adapter over the embedded Rust extractor because the real command-line
interface (CLI) still intentionally fails fast.

## Context and orientation

The repository is a mixed Rust and Python project. Rust crates live under
`crates/`, Python package code lives under `python/stilyagi/`, Python tests
live under `tests/`, shared source fixtures live under
`tests/fixtures/corpus/`, and Python behaviour-driven development (BDD) feature
files live under `features/`. The PyO3 bridge crate `crates/stilyagi-pyext/`
exposes the embedded Rust extension as `stilyagi._stilyagi_rs`.

Roadmap item 1.2.3 has already made `make build` and `make release` the
canonical build spine. `make build` runs `maturin develop` and then
`python -m stilyagi.smoke`. `make release` builds a wheel and smoke-tests it
from a separate virtual environment. Roadmap item 1.3.1 has already created the
shared corpus under `tests/fixtures/corpus/`. Roadmap item 1.3.2 has already
added internal golden intermediate representation (IR), CLI snapshot, and
round-trip helper scaffolding.

The current public structural entry point is
`stilyagi.engine.extract_document(source, syntax)`. The module
`python/stilyagi/cli.py` is still a placeholder that exits with status `2`, and
`pyproject.toml` does not yet expose a console script. The first performance
probe must therefore avoid claiming that `stilyagi check` exists. It should
measure the supported Python adapter backed by the embedded Rust extractor and
name this explicitly as the pre-CLI structural probe. Later roadmap slices can
swap the measured command to the real CLI once `stilyagi check` lands.

Definitions used in this plan:

- Cold run means a measurement run started from a fresh Python interpreter and
  with any repository-local Stilyagi performance scratch state removed before
  the measured operation. It does not mean flushing operating-system page cache
  or requiring privileged commands.
- Warm run means a measurement run in an already-started Python interpreter
  after the same structural extraction path has been primed once.
- Structural run means extraction and structural rule scaffolding that does not
  require NLP providers, spaCy models, part-of-speech tagging, dependency
  parsing, or language-model-backed analysis.
- Probe means a small repository-local measurement command intended to produce
  comparable evidence, not a microbenchmark proving a compiler-level
  optimization.
- Baseline artefact means a checked-in or generated JSON file that records the
  probe schema, corpus selection, run classification, summary timings, and
  environment metadata needed to compare later runs.

## Documentation and skill signposts

The implementer should keep these repository documents open while executing the
plan:

- [docs/roadmap.md](../roadmap.md), especially roadmap item 1.3.3, for the
  exact dependency and completion checkbox.
- [docs/stilyagi-design.md](../stilyagi-design.md), especially sections 7.1,
  10, and 11, for the IR boundary, build spine, and validation plan.
- [docs/rfcs/0004-stilyagi-rule-testing-framework.md](
  ../rfcs/0004-stilyagi-rule-testing-framework.md) for subprocess isolation,
  path normalisation, and future rule-test harness expectations.
- [docs/complexity-antipatterns-and-refactoring-strategies.md](
  ../complexity-antipatterns-and-refactoring-strategies.md) for keeping the
  first harness small and avoiding a premature performance framework.
- [docs/rust-testing-with-rstest-fixtures.md](
  ../rust-testing-with-rstest-fixtures.md) for Rust `rstest` fixture style.
- [docs/rust-doctest-dry-guide.md](../rust-doctest-dry-guide.md) for why
  doctests are not the right home for bulk timing probes.
- [docs/reliable-testing-in-rust-via-dependency-injection.md](
  ../reliable-testing-in-rust-via-dependency-injection.md) for explicit clock,
  filesystem, and environment boundaries in tests.
- [docs/rstest-bdd-users-guide.md](../rstest-bdd-users-guide.md) for Rust BDD
  tests with `rstest-bdd`.
- [docs/developers-guide.md](../developers-guide.md) for maintainer-facing
  probe commands, snapshot conventions, and quality gates.
- [docs/users-guide.md](../users-guide.md) for user-visible behaviour. Update
  it only if the implementation changes a public API or CLI promise.
- [docs/documentation-style-guide.md](../documentation-style-guide.md) for
  Markdown wrapping, spelling, headings, and footnote rules.

The relevant skills are:

- `execplans` to keep this plan current and approval-gated.
- `leta` for symbol-aware code navigation before code changes.
- `hexagonal-architecture` to keep measurement orchestration out of the domain
  extraction logic and treat clocks, process execution, and filesystem state as
  adapters.
- `rust-router`, then `rust-performance-and-layout`, because this slice is
  about measurement discipline and must avoid performance claims without
  numbers.
- `rust-types-and-apis` if Rust probe data transfer objects or public helper
  types are introduced.
- `rust-errors` if reusable Rust probe code needs recoverable error modelling.
- `domain-cli-and-daemons` only if the approved implementation changes CLI
  command behaviour.
- `commit-message`, `pr-creation`, and `en-gb-oxendict-style` when preparing
  commits and the draft pull request.

External tooling references resolved during planning:

- `hyperfine` documents warmup runs, preparation commands, and JSON export at
  <https://github.com/sharkdp/hyperfine>. This is useful prior art for cold and
  warm vocabulary, but the first Stilyagi slice should not require it unless
  the implementation needs process-level macrobenchmarking immediately.
- Criterion.rs documents saved baselines through
  `cargo bench -- --save-baseline <name>` at
  <https://bheisler.github.io/criterion.rs/book/user_guide/command_line_options.html>.
   It is useful later for direct Rust extractor benchmarks, but the initial
  baseline must exercise the Python-to-Rust boundary.
- `pytest-benchmark` documents saved benchmark runs and comparisons at
  <https://pytest-benchmark.readthedocs.io/en/latest/>. It is useful prior art,
  but adding it is not necessary unless a custom harness cannot keep the JSON
  schema and CI behaviour simple.
- Criterion.rs also cautions in its frequently asked questions that cloud
  continuous integration (CI) wall-clock benchmarks are noisy at
  <https://bheisler.github.io/criterion.rs/book/faq.html>. This supports the
  plan's decision to gate schema and repeatability first, not absolute timing
  thresholds.
- `iai-callgrind` records instruction-count and cache-style measurements with
  Valgrind tooling at <https://crates.io/crates/iai-callgrind>. It may be a
  later CI-oriented complement, but it is out of scope for this first
  Python-to-Rust boundary probe.

## Constraints

- Do not implement this plan until it is explicitly approved.
- Do not claim the public CLI exists. `python/stilyagi/cli.py` currently fails
  fast, so the initial probe must target the supported Python adapter and
  embedded Rust extractor.
- Do not require privileged host operations such as clearing the operating
  system page cache. Repository-local cold means fresh interpreter and cleared
  Stilyagi-local scratch state only.
- Do not turn timing noise into a required unit-test pass or fail threshold.
  Tests must verify schema, classification, deterministic corpus selection, and
  command behaviour. Performance budgets belong in review evidence until the
  project has enough measurements to set stable thresholds.
- Do not introduce NLP provider loading, spaCy models, or NLP-backed rule
  execution in this slice. This roadmap item captures the structural fast path
  before NLP features land.
- Do not expose a new public Rust or Python API solely for performance
  measurement. Prefer private test modules, internal support modules, or a
  clearly maintainer-facing module under `tests/performance/`.
- Keep the probe output free of machine-specific absolute paths. Normalise
  repository paths with `/` separators and include environment metadata only in
  fields that tests can redact or classify.
- Snapshot tests must avoid raw timestamps, raw durations, process IDs, random
  temporary paths, terminal colour output, and full hostnames unless those
  fields are redacted.
- Use `rstest` for Rust unit tests and `pytest` for Python unit tests. Use
  `rstest-bdd` for Rust behavioural tests and `pytest-bdd` for Python
  behavioural tests where behaviour is exercised.
- Use `insta` for Rust snapshots and `syrupy` for Python snapshots where output
  format consistency is relevant.
- Use `proptest` for Rust or `hypothesis` for Python only where the
  implementation introduces an invariant over a range of inputs. The likely
  target is deterministic probe-result normalisation, not wall-clock timing.
- Do not introduce Kani, CrossHair, or Verus proofs unless a substantive
  invariant emerges that is better proved than tested.
- Keep Makefile commands canonical. Prefer `make check-fmt`, `make lint`,
  `make typecheck`, `make test`, `make markdownlint`, and `make nixie` over
  lower-level final validation commands.
- Run format, lint, and test commands sequentially, not in parallel. Capture
  long command output with `tee` into `/tmp` logs.
- Use `coderabbit review --agent` after each major implementation milestone and
  resolve all actionable concerns before moving to the next milestone.
- Commit each approved, gated change as a focused commit. Do not commit code or
  documentation that fails required gates.
- On completion of the implemented feature, mark roadmap item 1.3.3 in
  `docs/roadmap.md` as done. Do not mark it done while this plan is still a
  draft or while implementation is incomplete.

## Tolerances (exception triggers)

- Scope: if the implementation needs more than eighteen files or roughly 850 net
  new lines, stop and explain why before continuing.
- Public API: if any public Rust or Python API signature must change, stop and
  request approval.
- CLI contract: if meaningful CLI command behaviour must be implemented beyond
  a private measurement entry point, stop and present options.
- Dependencies: adding `pytest-benchmark`, `criterion`, `hyperfine`, or any
  other new external dependency requires explicit approval. Start with the
  standard library and existing dev dependencies.
- Baseline storage: if the implementation needs to commit machine-specific raw
  timing files instead of a stable schema or sample baseline, stop and present
  alternatives.
- Runtime: the ordinary `make test` path should not add more than ten seconds
  on a warm development checkout. If it does, mark slow probes opt-in and
  update the plan before continuing.
- Iterations: if `make check-fmt`, `make lint`, `make typecheck`, or
  `make test` still fails after two focused correction passes, stop and record
  the failing `/tmp` log paths in this plan.
- Ambiguity: if multiple valid cold/warm definitions would materially change
  what later roadmap slices compare, stop and ask for approval.

## Risks

- Risk: the probe could measure Python process startup more than structural
  extraction. Severity: medium. Likelihood: high. Mitigation: record cold and
  warm as separate classifications, include enough metadata to show whether the
  run was process-level or in-process, and keep the future CLI swap-in explicit.

- Risk: hard timing thresholds could make CI flaky across Linux, macOS,
  Windows, and developer laptops. Severity: high. Likelihood: high. Mitigation:
  gate the schema, not absolute wall-clock numbers, and treat timing
  comparisons as review evidence until the project has a larger baseline
  history.

- Risk: the current placeholder CLI could tempt the implementation to build a
  partial `stilyagi check` before the roadmap is ready. Severity: medium.
  Likelihood: medium. Mitigation: keep the first probe under
  `tests/performance/` or an explicitly private maintainer module and document
  the CLI handoff as future work.

- Risk: adding a benchmark dependency could increase maintenance before the
  project knows its measurement shape. Severity: medium. Likelihood: medium.
  Mitigation: start with a small custom harness using `time.perf_counter_ns`,
  JSON, and existing test tools. Escalate before adding dependencies.

- Risk: warm-run semantics may be weak before Stilyagi has a real cache.
  Severity: medium. Likelihood: high. Mitigation: define warm as an
  interpreter-primed structural run for this slice, and record in the output
  that no persistent Stilyagi cache was exercised if none exists yet.

- Risk: checked-in baseline files may age poorly as the corpus and bridge
  evolve. Severity: medium. Likelihood: medium. Mitigation: store a
  schema/sample baseline that explains its context and update it only when the
  reviewed contract changes. Keep raw local run output generated and untracked
  unless the plan is revised.

## Plan of work

Milestone 1 records the method and failing tests. Add a small
`tests/performance/` package for the structural probe and create tests first.
Python unit tests should expect deterministic corpus discovery, normalised
paths, cold and warm run classifications, and a stable JSON result shape.
Python BDD coverage should describe a maintainer running the structural probe
against the shared Markdown fixture and receiving a JSON report with cold and
warm sections. If Rust code is introduced for shared result types, add `rstest`
coverage first; otherwise, avoid Rust changes in this milestone.

The milestone is complete when the new tests fail for the expected reason: the
probe module or result builder does not exist yet. Record the failing command
and a short transcript in `Progress`.

Milestone 2 implements the smallest useful probe harness. Create a private
Python measurement module under `tests/performance/` or a similarly
maintainer-facing test-support location. The harness should read the existing
shared Markdown fixture from `tests/fixtures/corpus/markdown/valid/`, call
`stilyagi.engine.extract_document` with `model.Syntax.MARKDOWN`, and record
per-iteration durations with `time.perf_counter_ns`. Cold mode should run the
measured extraction in a fresh Python interpreter, using
`sys.executable -m ...` to match RFC 0004's subprocess guidance. Warm mode
should prime extraction once inside one interpreter and then measure repeated
calls in the same interpreter. Both modes should write the same JSON schema.

The first JSON schema should include at least:

```json
{
  "schema_version": 1,
  "probe": "structural-markdown",
  "entrypoint": "stilyagi.engine.extract_document",
  "corpus": {
    "fixture_paths": [
      "tests/fixtures/corpus/markdown/valid/heading-table-link-suppression.md"
    ],
    "file_count": 1
  },
  "runs": [
    {
      "mode": "cold",
      "iterations": 5,
      "durations_ns": [1],
      "summary_ns": {
        "min": 1,
        "median": 1,
        "max": 1
      }
    }
  ]
}
```

Tests should use `syrupy` to snapshot a redacted version of the JSON report,
not the raw timing report. Replace non-deterministic durations, summary values,
timestamps, and environment fields with stable placeholders before comparison.
A redacted snapshot may look like this:

```json
{
  "schema_version": 1,
  "probe": "structural-markdown",
  "environment": {
    "platform": "<redacted>",
    "python": "<redacted>"
  },
  "runs": [
    {
      "mode": "cold",
      "durations_ns": "<redacted>",
      "summary_ns": {
        "min": "<redacted>",
        "median": "<redacted>",
        "max": "<redacted>"
      }
    }
  ]
}
```

The milestone is complete when the unit and BDD tests pass and the probe can
produce a local JSON file under an ignored output path such as
`build/performance/` or another documented generated directory.

Milestone 3 documents the workflow and stores stable evidence. Update
`docs/developers-guide.md` with the command to run the structural performance
probe, the meaning of cold and warm in this repository, where generated output
goes, and how maintainers should compare future runs. Update
`docs/stilyagi-design.md` section 11 only if the implementation settles a
design decision not already captured there. Update `docs/users-guide.md` only
if a public command or public API changes; otherwise record in `Decision Log`
that this is maintainer-facing only.

If a stable sample baseline is checked in, keep it normalised and clearly
labelled as a sample captured on this branch, not as a universal threshold. If
the implementation instead stores only snapshots of the redacted schema, record
that decision in `Decision Log`.

The milestone is complete when documentation explains how a maintainer can run
the probe and interpret its output without reading the implementation.

Milestone 4 validates the full change. Run the quality gates sequentially with
`tee` logs. Use project-specific log paths like these:

```bash
make check-fmt 2>&1 | tee /tmp/check-fmt-stilyagi-1-3-3-cold-and-warm-baseline-performance-probes.out
make lint 2>&1 | tee /tmp/lint-stilyagi-1-3-3-cold-and-warm-baseline-performance-probes.out
make typecheck 2>&1 | tee /tmp/typecheck-stilyagi-1-3-3-cold-and-warm-baseline-performance-probes.out
make test 2>&1 | tee /tmp/test-stilyagi-1-3-3-cold-and-warm-baseline-performance-probes.out
make markdownlint 2>&1 | tee /tmp/markdownlint-stilyagi-1-3-3-cold-and-warm-baseline-performance-probes.out
make nixie 2>&1 | tee /tmp/nixie-stilyagi-1-3-3-cold-and-warm-baseline-performance-probes.out
```

Run the new probe command and capture its output with `tee` as well. If the
implementation adds a Makefile target, prefer that target. If it keeps an
explicit Python module, use a command shaped like this:

```bash
.venv/bin/python -m tests.performance.structural_probe \
  --mode both \
  --output build/performance/structural-baseline.json 2>&1 \
  | tee /tmp/performance-probe-stilyagi-1-3-3-cold-and-warm-baseline-performance-probes.out
```

Run `coderabbit review --agent` after the major implementation milestone and
again before the final commit if the review reports concerns. Clear all
actionable concerns before moving on.

The milestone is complete when all gates pass, the probe produces the expected
JSON, and `Progress` records the exact commands and log paths.

Milestone 5 completes the roadmap slice. Update `docs/roadmap.md` to mark item
1.3.3 done only after the implemented feature is validated. Review the changed
code for nearby refactoring needs using
`docs/complexity-antipatterns-and-refactoring-strategies.md`. If a refactor is
necessary, make it a separate approved and gated commit. Prepare the draft pull
request with title `Record structural performance baselines (1.3.3)` or an
equivalent imperative title that includes `(1.3.3)`, link this ExecPlan in the
summary, and include the Lody session link in a final `## References` section.

## Validation

During implementation, use red-green-refactor discipline:

1. Add or update the relevant tests before implementation.
2. Run the targeted tests and record the expected failure.
3. Implement the smallest change that satisfies the tests.
4. Run targeted tests again and record the passing result.
5. Run the full sequential gates before committing.

Targeted validation should include:

- Python unit tests with `pytest` for corpus discovery, result building, JSON
  parsing, path normalisation, and mode classification.
- Python behavioural tests with `pytest-bdd` for running the maintainer-facing
  structural probe and receiving a cold/warm report.
- Python snapshot tests with `syrupy` for redacted JSON output shape when the
  schema stabilizes.
- Rust `rstest` tests only if Rust probe DTOs or helpers are introduced.
- Rust `insta` snapshots only if Rust code owns an output format.
- Property tests with `hypothesis` or `proptest` only for deterministic
  normalisation invariants, not for absolute wall-clock timing.

End-to-end coverage is required because this slice affects an externally
observable maintainer workflow. The end-to-end check should run the probe
through the built package in `.venv` after `make build`, not through a mocked
bridge.

Final validation must include:

- `make check-fmt`
- `make lint`
- `make typecheck`
- `make test`
- `make markdownlint`
- `make nixie`
- the new structural performance probe command
- `coderabbit review --agent`

## Progress

- [x] 2026-05-25: Loaded the requested `leta`, `hexagonal-architecture`, and
  `rust-router` skills, plus `execplans` and `rust-performance-and-layout` for
  planning.
- [x] 2026-05-25: Created the `leta` workspace for this worktree.
- [x] 2026-05-25: Renamed the local branch to
  `1-3-3-cold-and-warm-baseline-performance-probes`. The matching remote branch
  did not exist yet, so upstream tracking must be established on first push.
- [x] 2026-05-25: Used Wyvern agents for read-only planning support. They
  confirmed that roadmap item 1.3.3 lacks an explicit methodology, that the CLI
  is still a placeholder, and that tests should validate schema and
  classification rather than hard timing budgets.
- [x] 2026-05-25: Used external research to resolve prior-art gaps around
  `hyperfine`, Criterion.rs, `pytest-benchmark`, and `iai-callgrind`.
- [ ] Draft approved by the user.
- [ ] Milestone 1 tests added and observed failing for the expected reason.
- [ ] Milestone 2 probe harness implemented.
- [ ] Milestone 3 documentation updated.
- [ ] Milestone 4 gates and CodeRabbit review passed.
- [ ] Milestone 5 roadmap item marked done and implementation PR prepared.

## Surprises & Discoveries

- The current CLI is intentionally a placeholder and exits with status `2`.
  The initial performance probe must measure the existing Python API over the
  Rust bridge rather than a future `stilyagi check` command.
- No `tests/performance/` directory, Rust `benches/` directory, Criterion.rs
  setup, `pytest-benchmark` setup, or `hyperfine` wrapper exists yet.
- The design document already reserves a `tests/performance/` slot and calls
  for cold and warm performance baselines, but it does not define the
  measurement method, schema, thresholds, or storage convention.

## Decision Log

- 2026-05-25: Treat this branch as a pre-implementation plan branch. Rationale:
  the user explicitly required plan approval before implementation, so this
  plan must stop at a draft pull request.
- 2026-05-25: Define cold and warm in repository-local terms rather than
  operating-system cache terms. Rationale: privileged cache flushing is not
  portable across Linux, macOS, and Windows and would make local validation
  brittle.
- 2026-05-25: Plan a small custom Python harness first rather than adding
  `hyperfine`, Criterion.rs, or `pytest-benchmark`. Rationale: the first
  baseline must exercise the Python-to-Rust boundary and produce a
  Stilyagi-specific JSON schema without adding dependency weight before the
  measurement contract is known.
- 2026-05-25: Keep user-facing guide updates conditional. Rationale: the first
  probe is maintainer-facing unless implementation changes a public API or CLI
  promise.

## Outcomes & Retrospective

This section is intentionally empty while the plan is in draft. During
implementation, record what shipped, what changed from the plan, which
validation evidence proved the feature, and whether the chosen baseline method
was sufficient for later roadmap slices.
