# Adopt the `nose` code-duplication gate

Status: COMPLETE

This ExecPlan adopts a blocking, deterministic code-duplication gate in
Stilyagi, following the final `nose` approach recorded in `leynos/episodic`
[PR #276](https://github.com/leynos/episodic/pull/276) and its ADR-021 at
immutable revision `d9e5ac0d254f375e2986f52d91a3b88c117c833b`.

## Constraints

- Work only in `leynos/stilyagi`; no estate-wide rollout.
- Port the five gate/support modules and their focused tests. Do not
  cherry-pick the whole reference pull request.
- Do **not** copy `benchmarks/duplication/**`, `benchmarks/score_support.py`,
  `tests/test_duplication_benchmark*.py`, the benchmark head-to-head report, or
  any benchmarking CI job. The detector choice is reused **by reference**:
  Stilyagi must not re-run a detector competition nor claim episodic's
  precision, recall, or timings.
- Do not import episodic's application fixes, exception entries, package
  names, database fixtures, PGlite/npm caching, Skylos/Pylint migrations,
  coverage changes, or unrelated dependencies. Do not build a shared
  multi-repository tooling framework.
- Do not adopt PyChase, its Python 3.13 / `PYTHONHASHSEED` workarounds, or
  `pyscn`. ADR-021 and the merged `nose` code take precedence over the earlier
  PyChase design still described in the reference pull request's opening.
- The detector is the Rust-built `nose-cli` executable named `nose`
  (`corca-ai/nose`), pinned at `0.20.0`. Do not install the unrelated PyPI
  `nose` test framework.
- Application Python floor (`requires-python = ">=3.14"`), interpreter matrix,
  and runtime dependencies are unchanged. The gate is tooling only.
- No new heavyweight CI job, source build, duplicate full test suite, or
  benchmark lane.
- Do not lower the gate's Python requirement without checking the helper's
  syntax and APIs; `fcntl.flock` and POSIX directory operations are used.
- Do not report unrun checks as passing.

## Tolerances

- The gate's intermediate-language (IL) size floor is neither Python lines nor
  AST nodes; any explanation must say so.
- Ranking is bounded by `top`; the gate adjudicates the highest-ranked
  families, not every family. Documentation must not claim otherwise.
- Where a finding's unit name is absent from the detector report, it is
  reported as an unnamed fragment rather than an invented qualified name.

## Risks

- **Silent scope narrowing.** A mistyped or empty root would make the gate pass
  vacuously. The configured roots are validated to exist and to select the
  intended files.
- **Pin drift.** The pinned version appears in the Makefile, CI, and
  `[tool.nose]`. A contract test keeps the three in agreement.
- **Gate/test coupling.** Gate tests must not be imported into the application
  suite's configuration, nor may an older application interpreter collect
  Python-3.14-only tooling tests.
- **Partial suppression.** An exception that covers only some members of a
  family would let a new member through silently.
- **Unsatisfiable detector pressure.** Extracting a shared helper only because
  the detector fired would couple unrelated contracts. Intentional parallels
  are recorded as reasoned exceptions, not forced extractions.

## Progress

- [x] Load required skills; create the leta workspace.
- [x] Read reference ADR-021 and the five gate modules plus the focused tests
      at the immutable revision.
- [x] Confirm upstream `nose` 0.20.0 usage, configuration, and query-JSON
      contract.
- [x] Provision the pinned binary into `.tools/nose`.
- [x] Reconnaissance: Makefile, `pyproject.toml`, CI workflows, docs, test
      layout, `.gitignore`, existing helpers.
- [x] First real scan of `python/stilyagi`.
- [x] Add `[tool.nose]` and `[tool.duplication_gate]` configuration.
- [x] Port the five gate modules.
- [x] Port and adapt the focused tests.
- [x] Add Make targets and wire the gate into `lint`.
- [x] Add the toolchain pin-agreement contract test.
- [x] Adjudicate this repository's findings.
- [x] Disposable-workspace end-to-end demonstration.
- [x] Documentation and ADR 008.
- [x] Full validation and draft pull request.
      - [x] Final-diff review for benchmark leakage, unrelated migrations,
            copied reference paths, broad suppressions, and runtime-dependency
            or Python-floor changes.
      - [x] Full gate suite run and defects fixed (`make lint` docstring,
            `make test` Skylos contract tests, copied pathname).
      - [x] Rebased onto the updated `origin/main` (`4c0c0a7`), which carried
            PR #163's CPython Pylint tier. One conflict in
            `docs/developers-guide.md`: a lint-variable table where upstream
            replaced the PyPy Pylint rows and this branch added the `nose` rows.
            Resolved by keeping upstream's table, dropping the two now-obsolete
            `PYLINT_PYPY_SHIM` rows, and inserting the five `nose` rows in
            Makefile order, re-rendering the column padding.
      - [x] Full gate suite green over the frozen tree: all eight gates exit 0
            (`check-fmt`, `typecheck`, `lint`, `test`, `markdownlint`, `nixie`,
            `duplication`, `duplication-test`). `test` reported 555 passed /
            1 skipped plus 21 passed / 1 skipped doctests; `lint` ran both
            Pylint tiers on managed CPython 3.14 and completed the duplication
            gate at "4 allowed by reasoned exceptions".
            **Historical.** This run was on the `4c0c0a7` base. It is recorded
            because it found real defects, not because its counts still
            describe the branch -- the second rebase superseded every figure
            in it.
      - [x] Rebased a second time, onto `7fdcff3` (PR #162), after the gate run
            exposed that `origin/main` had advanced again. That commit adds
            `tests/test_codescene_environment_contract.py` and
            `tests/support/codescene_environment_rules.py`, and the contract
            test parses `smoke.yml` -- a file this branch edits. A targeted
            re-verification followed rather than an assumption: the
            workflow-parsing contract tests pass (40 passed), the suite passes
            (564 passed / 1 skipped), and the duplication gate still exits 0.
            CI evaluates the merge, so a green run on a stale base is not
            evidence about the PR.
      - [x] Full gate suite re-run over the frozen `7fdcff3`-rebased tree, all
            eight gates exit 0. `test` reported 564 passed / 1 skipped (up from
            555 by the 9 contract tests the new base adds -- 564 - 555 = 9
            closes exactly against the 9 test functions in
            `tests/test_codescene_environment_contract.py`) plus **22** passed /
            1 skipped doctests, up from 21 by
            `tests/support/codescene_environment_rules.py`, which the
            `--doctest-modules python/stilyagi tests/support` lane collects.
            `lint` ran both Pylint tiers on managed CPython 3.14, `markdownlint`
            linted 69 files with 0 errors, and the duplication gate exited 0 at
            "4 allowed by reasoned exceptions". The changed merge base is
            therefore genuinely re-verified end to end, not inferred from the
            targeted checks.
      - [x] Pre-push review found the `tests/` scan figure had drifted a fourth
            time, to 87, and that the earlier 83 -> 85 correction had missed
            `pyproject.toml`. The exclusions were re-phrased on the durable
            order-of-magnitude gap (87 against 4) with the drift stated, so the
            rationale no longer depends on a digit the next rebase will move.
      - [x] Full gate suite re-run on the exact tip being pushed (`13cfe90`),
            all eight gates exit 0, every count identical to the previous run
            (nextest 337; pytest 564 passed / 1 skipped; doctests 22 passed /
            1 skipped; markdownlint 69 files, 0 errors; duplication "4 allowed
            by reasoned exceptions"; duplication-test 125 passed). The suite was
            re-run rather than inherited because two docs-only commits landed
            after the earlier run, and on this repository a comment-only diff is
            still read by contract tests.
      - [x] Branch pushed with upstream and draft pull request opened:
            [PR #164](https://github.com/leynos/stilyagi/pull/164), draft,
            against `main`, 30 files changed. The gate suite was re-run once
            more on `f925d1b`, the exact commit pushed, and all eight gates
            exited 0 with every count reproduced; the run is logged under
            `/tmp/verify5-<gate>-stilyagi-adopt-nose-code-deduplication.out`.
            This checklist entry is itself the last edit, so the tree the
            gates verified is `f925d1b` and the push is `f925d1b` plus this
            comment-only line.

## Context and orientation

Stilyagi is a prose linter for Markdown and doc comments, written as a mixed
Rust and Python package. Rust owns source-fidelity extraction under `crates/`;
Python owns package integration and the rule-engine runtime under
`python/stilyagi/`, whose import package is `stilyagi` (not derived from
`src/`). The application requires Python 3.14.

The commit gate is `make all`, which runs `check-fmt`, `typecheck`, `lint`,
`test`, `markdownlint`, and `nixie`. `make lint` is the pipeline this work
extends; CI invokes it verbatim from `.github/workflows/smoke.yml`.

`nose` lowers every supported language into one intermediate representation
(IL) and detects clones across three channels: `syntax` (exact token runs),
`semantic` (value-fingerprint "shared core"), and `near` (fuzzy). `min-size`
counts IL tokens, **not** Python lines or AST nodes.

## Plan of work

1. **Configuration.** Add `[tool.nose]` (`version = "0.20.0"`,
   `roots = ["python/stilyagi"]`, `mode = "syntax,semantic,near"`,
   `min-size = 24`, `surface = "all"`, `top = 30`) and an empty
   `[tool.duplication_gate]` to `pyproject.toml`, each with a comment
   explaining the choice. Add `.tools/` and `.*.duplication-gate.lock` to
   `.gitignore`.
2. **Gate modules under `scripts/`.** Port `nose_schema.py`, `nose_detector.py`,
   `duplication_allowlist.py`, `atomic_write.py`, and `duplication_gate.py`,
   preserving source attribution and licence notices, adapting root paths and
   diagnostics to Stilyagi.
3. **Focused tests under `scripts/tests/`.** Port and adapt the reference test
   slice with a `conftest.py` that puts `scripts/` on `sys.path`, and a
   `duplication_gate_test_support.py` with `episodic` paths replaced. Guard
   against collection by an older application interpreter.
4. **Make targets.** `install-nose` (no-op when the pinned version is already
   present; `--disable-strategies compile,quick-install`), `duplication`,
   `duplication-test`, and `duplication-allow` with command-line-only `FIRST`/
   `SECOND`/`REASON` and literal value preservation. Wire
   `$(DUPLICATION_GATE) check` into `lint`.
5. **Pin-agreement contract test.** Assert the Makefile, CI, and
   `[tool.nose]` pins agree without pinning any specific version.
6. **CI.** Add the detector cache keyed on runner OS and the pinned version,
   an install step with a checksum-verified cargo-binstall, and a
   `make duplication-test` step. Reuse pinned actions, least-privilege
   permissions, and existing limits.
7. **Adjudicate.** Extract genuine duplication; record reasoned exceptions.
8. **Demonstrate.** In a disposable workspace with the real binary: clean,
   planted clone fails, narrow exception passes, extra member fails again;
   deterministic across runs; nothing left behind.
9. **Document.** Developer's guide, agent instructions, command help, the
   documentation index, and ADR 008.

## Concrete steps

Run everything from the worktree root. Gate helper tests:

```sh
make duplication-test
```

The gate itself:

```sh
make duplication
```

The disposable-workspace demonstration builds a small workspace, plants a
clone, and runs the real `.tools/nose/nose` through the gate.

## Validation and acceptance

The change is acceptable when:

- `make duplication` passes on the committed tree, and the adjudication record
  accounts for every family in the report.
- `make duplication-test` passes.
- `make lint` and `make check-fmt` pass, still running every pre-existing
  check.
- The planted-clone demonstration fails, passes with a narrow reasoned
  exception, and fails again when a member outside that exception is added.
- The gate exits 2, not 0 or 1, for a missing binary, a version mismatch, a
  timeout, malformed JSON, and an invalid report shape.
- Deterministic normalized output across repeated runs.
- No planted clone, temporary exception, or benchmark artefact remains.

The first full pass ran every gate and produced two real failures, both now
fixed and both recorded under Surprises & Discoveries:

| Gate                    | First pass                          | Cause                                                  |
| ----------------------- | ----------------------------------- | ------------------------------------------------------ |
| `make lint`             | failed, `docstring-missing-returns` | multi-line docstring without a NumPy `Returns` section |
| `make test`             | 2 failed, 549 passed                | `skylos-allow` narrowed to command-line origins        |
| `make duplication`      | exit 0, 4 allowed                   | —                                                      |
| `make duplication-test` | 125 passed                          | —                                                      |
| `make check-fmt`        | exit 0                              | —                                                      |
| `make typecheck`        | exit 0, `All checks passed!`        | —                                                      |
| `make markdownlint`     | exit 0, 0 errors over 69 files      | —                                                      |
| `make nixie`            | exit 0, all diagrams validated      | —                                                      |

_Table 2: First full gate pass, before the two fixes._

## Idempotence and recovery

`make install-nose` is a no-op when the pinned version is already installed, so
re-running is safe. The allowlist writer is atomic and lock-protected; a failed
replacement leaves the original file and its mode intact and removes its
temporary sibling. Removing the exception entries and re-running the gate
returns the tree to its adjudicated state.

## Artefacts and notes

- Reference: `leynos/episodic` PR #276, revision
  `d9e5ac0d254f375e2986f52d91a3b88c117c833b`,
  `docs/adr/adr-021-adopt-nose-duplication-gate.md`.
- Detector: `corca-ai/nose` `v0.20.0`, the Rust `nose-cli` binary.
- Deliberate downstream deviations from the reference: the
  `--disable-strategies compile,quick-install` prohibition; the root scope (here
  `python/stilyagi` alone, where the reference also scans a loose module at
  its repository root); the module home (`scripts/` here, reintroduced); the
  `testpaths` isolation described below; and Stilyagi's own exception entries,
  which replace episodic's 23.

## Surprises & Discoveries

- **There is no `scripts/` directory**, although `docs/repository-layout.md`
  and `docs/scripting-standards.md` both document one. `scripts/` is a genuine
  historical convention: `git log --all -- scripts/` shows
  `scripts/generate_typos_config.py`, `scripts/typos_rollout_check.py`, and
  `scripts/update_acronym_allowlist.py`, since removed. Reintroducing
  `scripts/` therefore restores a documented convention rather than inventing
  one, and `docs/scripting-standards.md:345-346` already specifies
  `scripts/tests/` for script tests.
- **`tests/support/` is the documented shared-helper home** for the
  application suite. The gate modules are not application test support; they
  are maintainer scripts, so they belong under `scripts/` with tests in
  `scripts/tests/`, isolated from `tests/conftest.py`.
- **A bare `pytest` run would collect `scripts/tests/` and hard-fail.**
  The reference project's dev dependency group carries the gate's PEP 723
  dependencies; Stilyagi's does not, so `make test` and the coverage step --
  both of which invoke `pytest` with no path -- died at import with
  `ModuleNotFoundError: No module named 'cyclopts'`. Fixed by setting
  `testpaths = ["tests"]`. `norecursedirs` was rejected because pytest's
  `addini(..., type="args")` _replaces_ the default tuple rather than extending
  it, which would have made `.venv` collectible. A path argument overrides
  `testpaths`, so `make duplication-test` -- which names its files explicitly
  -- is unaffected. Verified in both directions: bare collection yields 541
  tests and none from `scripts/`; explicit-path collection still finds the gate
  tests.
- **No atomic-write or file-locking helper exists** in Stilyagi (`flock`,
  `fcntl`, and `NamedTemporaryFile` all return zero matches). The reference's
  `atomic_write.py` must be ported rather than reusing a local equivalent, and
  its attribution retained.
- **`docs/scripting-standards.md` mandates Cyclopts** for new scripts, which
  the reference gate already uses. This is the rare case where the ported code
  already satisfies the repository convention.
- **The app's Python floor and the tooling interpreter are both 3.14,** so the
  reference's `requires-python = ">=3.14"` needs no change.
- **`typos.local.toml` excludes `tests/fixtures` only.** New Markdown under
  `docs/` is scanned; the reference's prose needs no spelling exception.
- **The repository's existing precedent for a blocking tool gate is Skylos:**
  a pinned version plus command trio in the Makefile, one recipe line at the
  end of `lint`, a `[tool.<gate>]` block in `pyproject.toml`, a
  `tests/test_<gate>_lint_contract.py`, and an ADR addendum.
- **A pre-existing gate's contract is easy to break while adding a new one.**
  The `duplication-allow` target restricts `FIRST`/`SECOND`/`REASON` to
  `origin == command line`, because WSL injects an ambient `NAME`. Applying the
  same helper to the pre-existing `skylos-allow` target silently narrowed it:
  its contract deliberately accepts environment values, and two tests in
  `tests/test_skylos_lint_contract.py` pinned that, so `make test` failed. The
  helper must stay private to the new interface; a shared "improvement" to an
  existing target is a behaviour change and needs its own justification.
- **`ignore-one-line-docstrings = true` decides which docstrings need
  `Returns`.** Ruff's `DOC` rules are selected and the pydocstyle convention is
  `numpy`, so a _multi-line_ docstring on a value-returning function needs a
  NumPy-style `Returns` section while a single-line one does not. The extracted
  `_pyproject_stilyagi_table` was the only new function long enough to trip it;
  its one-line siblings were exempt and passed.
- **A copied pathname can survive a mechanical port.** The command-building
  test carried `openai_test_types.py`, a reference-repository filename that
  does not exist here, as the second configured root. Grep for the reference's
  own paths after a port rather than trusting that adaptation was complete.
- **`test_toolchain_contract.py` does not exist here.** The equivalent
  behaviour is distributed across `tests/test_ci_workflow_units.py`,
  `tests/test_skylos_lint_contract.py`, `tests/test_makefile_recipes.py`, and
  `tests/test_build_spine_units.py`. Rather than fold the pin-agreement
  contract into a fourth module, `tests/test_toolchain_contract.py` was added
  and the Makefile comment naming it was made true.
- **Every family in this repository is fragment-level.** The detector supplies
  no unit name for any of the four, and a `path::name` key never matches an
  unnamed location, so the narrowest key the schema allows here is the whole
  file. This is recorded in the `pyproject.toml` comment above the entries.
- **`nose` exits 1, not 0, for a mistyped root**
  (`Error: path does not exist`). The gate surfaces that as a configuration
  error with status 2 rather than a vacuous pass, so a mistyped or empty scope
  cannot masquerade as a clean result.
- **`cargo-binstall --version` fails**; it reads `--version` as the
  crate-version flag. Use `cargo-binstall -V`.
- **A stale base can fail a gate that upstream has already fixed.** The first
  full gate pass died in the PyPy Pylint tier, on four messages in two files
  whose blobs were byte-identical to `origin/main`. `make lint` on a pristine
  `origin/main` worktree at the same commit reproduced it exactly, and
  `origin/main` had meanwhile moved to `4c0c0a7` (PR #163), which states in its
  own message that PyPy 8 cannot parse this repository's 3.14 syntax and had
  turned every lint lane red. Rebasing onto `4c0c0a7` resolves the whole tier.
  A gate failure on untouched files is a signal to check blob identity and the
  upstream tip before treating it as branch-induced &#8212; re-running the same
  gate on the stale base would only reproduce it.
- **A quoted scan count is a measurement of one tree, and it drifts.** The
  exclusion rationale cited `tests/` as reporting 83 families; the rebased tree
  reports 85, deterministically over five runs. `82` was the pre-rebase
  `origin/main` figure (three documents carried the stale `83` from this
  branch's own earlier tip, and the ExecPlan carried the older `82`). None of
  the three matched the tree that ships. The number moved because PR #163 split
  two over-limit test modules into five, and smaller modules yield more
  cross-file families than the oversized originals. Any family count quoted in
  prose needs re-measuring after a rebase, and the claim should be written so
  the decision does not hinge on the digit.
- **And a correction made once does not stay made.** Fixing the four `83`
  sites was not the end of it. A pre-push review against the _second_ rebase
  measured **87**, because `7fdcff3` added two more `tests/` modules, and the
  figure had by then been 82, 83, 85 and 87 without a single line of this
  branch's gate work changing. Worse, the correcting commit had missed
  `pyproject.toml` entirely — the one file a maintainer actually reads when
  deciding whether to widen the scope — so the shipped config still said `83`
  while three prose documents said `85` and the tree said `87`. The lesson is
  not "correct the number more carefully"; it is that a rationale phrased
  around an exact figure needs re-deriving on every rebase and will not survive
  contact with an active upstream. The exclusions are now phrased on the
  order-of-magnitude gap (87 against 4) with the drift stated alongside, so the
  decision no longer depends on a digit that moves. Re-measure, then write the
  rationale so the next rebase cannot falsify it.

- **A rebase conflict can hide semantic, not just textual, drift.** The one
  conflict here was a Markdown table: upstream replaced the two PyPy Pylint
  rows, and this branch added five `nose` rows. Taking either whole side would
  have silently reverted the other, and the PyPy shim rows would have been
  re-admitted as valid-looking documentation for a tier that no longer exists.
  Resolving a table conflict means resolving the row set, then re-rendering the
  column widths rather than hand-patching cells.
- **A rebase moves more counters than the obvious one.** The second rebase was
  expected to change the pytest total, and it did: 555 to 564. The doctest
  total moved too, 21 to 22, which was not anticipated and was caught only
  because the re-run was full rather than targeted. The new support module
  `tests/support/codescene_environment_rules.py` sits inside the
  `--doctest-modules python/stilyagi tests/support` lane's scope, so a file
  added for an unrelated contract test silently enrolled its examples in the
  doctest gate. A targeted re-verification named only the risk that was
  predicted; the unpredicted count surfaced solely because the whole suite was
  re-run. Re-run the full suite after a rebase even when a focused subset
  already passes, and read every count in the summary rather than the one being
  watched.
- **A benign-looking instruction to expect a stale file was itself stale.**
  `typos.toml` was expected to be rewritten in place by `make spelling` and to
  need committing; its SHA-256 was unchanged before and after. The rule held in
  an earlier session on an earlier tree and did not hold here. Carrying a
  remembered state forward as an expectation, rather than re-measuring, would
  have produced a commit of an unmodified file or a spurious `git checkout`.

## Decision Log

- **Adopt `nose` 0.20.0 by reference.** No detector competition is re-run and
  no episodic precision, recall, or timing figure is carried over.
- **Gate modules live in `scripts/`**, restoring the documented convention,
  with tests in `scripts/tests/` per `docs/scripting-standards.md`.
- **Prohibit compilation fallback.** The downstream Makefile adds
  `--disable-strategies compile,quick-install` to cargo-binstall. The reference
  omits it; this is a deliberate downstream deviation required by the task. A
  missing trusted prebuilt binary is an explicit provisioning failure.
- **Python floor.** The gate keeps the reference's `requires-python = ">=3.14"`,
  which matches the application floor, so the helper's syntax and APIs are
  unchanged.
- **Portability.** The helper uses `fcntl.flock` and POSIX directory
  operations. The gate is documented as a
  Linux/macOS/Windows-Subsystem-for-Linux developer and Linux CI workflow. The
  application's existing platform support is unchanged: the gate is not run by
  `make test`, so the Windows `release-smoke` leg is unaffected. No portability
  adaptation is made because native Windows gate operation is not required.
- **Pipeline integration.** `make lint` and the standalone `make duplication`
  both depend on `make install-nose`, mirroring the reference. `make lint` is
  the gate CI already invokes, so no CI duplication is needed.
- **Scan scope.** `python/stilyagi` only. See the adjudication below.
- **Successor to the Skylos precedent.** Skylos was the one existing blocking
  tool gate and this is the second, so the shape follows it; the ADR should
  note the precedent and say why the detector is a separate tool rather than an
  extension of Skylos.
- **Leave the existing Skylos target alone.** The command-line-origin
  restriction is scoped to `duplication-allow` under its own helper name. An
  earlier revision shared it with `skylos-allow`, which changed that target's
  documented environment-reading behaviour and failed two pre-existing tests;
  the change was reverted.

## Adjudication record

The scan runs over one root, `python/stilyagi`, with the reference's channels
and floor: `mode = "syntax,semantic,near"`, `min-size = 24`, `surface = "all"`,
`top = 30`.

Scope decisions:

- **`tests/` is out of scope.** A configured `tests` root reports an order of
  magnitude more families than the package (87 against 4, measured at the tip
  of this branch; it read 82, 83 and 85 earlier as the branch and its base
  moved), overwhelmingly assertion-shape and fixture-setup repetition. The
  reference gates production sources; gating the suite here would dominate the
  ranked budget with test scaffolding and would require mass exception entries,
  which the task prohibits. `tests/support/` is nonetheless the documented home
  for reusable helpers and is already reused. The exclusion decision does not
  depend on the exact figure, and the Surprises section records why that
  phrasing is deliberate rather than vague.
- **`scripts/` is out of scope.** The gate's own modules would otherwise be
  self-referential; the reference excludes its gate for the same reason.
- **Rust crates are out of scope.** This adoption covers the Python surface
  only (`python/stilyagi`). `crates/**` is a Rust workspace with its own Clippy
  and Whitaker gates.
- **Docs, fixtures, and `target/` are not production targets.**

### What the scan actually reports

A saturation check (`all top=0`, the complete ranked list) reports exactly
**four** families. The configured `top = 30` therefore does not truncate this
repository's ranking, so no family is hidden by the budget. Because the
detector is deterministic and the list is saturated, the gate's coverage here
is total rather than merely the top 30.

Every one of the four is fragment-level: the detector supplies no unit name for
any location. The four, with the disposition of each:

1. **`similar`, value 3.93:**
   `python/stilyagi/cli_args.py:183-187 ~ 188-192`. Two adjacent argparse
   boolean-flag declarations differing only in flag name and help text.
   **Recorded as a reasoned exception.** The repetition is argparse's
   declaration surface, not shared logic: writing them through a helper would
   leave the same declaration spelled two ways, and three sibling flags in the
   same block are already one-liners.
2. **`exact`, value 3.60:** `python/stilyagi/config/resolve.py:66-67` against
   `python/stilyagi/engine/extraction.py:273-274`. Two
   `if <x> is None: return ()` guards in unrelated modules. **Recorded as a
   reasoned exception.** Coincidental shape: one returns an empty tuple because
   the `extend` key is unset, the other because no IR payload was supplied.
   Nothing is shared but the shape of the guard.
3. **`connected`, value 2.21:**
   `python/stilyagi/config/validate.py:49-51 ~ 82-84`. The
   `any(not isinstance(…) for …)` guard over a mapping's non-string keys and
   over a tuple's non-string items. **Recorded as a reasoned exception.** Two
   different container types, each raising its own diagnostic; sharing them
   would require a predicate-taking helper with a boolean mode, which the
   config layer deliberately avoids.
4. **`exact`, value 2.00:**
   `python/stilyagi/engine/extraction.py:88-89 ~ 92-93`. The
   double-checked-locking guard in `_validate_syntax_vocab_once`. **Recorded as
   a reasoned exception.** The unlocked pre-check and the locked re-check are
   the idiom itself; collapsing them into a helper would defeat the purpose,
   since the second read must happen under the lock.

Two families that an earlier reading of this plan listed as genuine are **no
longer reported**, because they were extracted and the extraction removed the
clone from the detector's surface. Both extractions were made on their merits
as code improvements, not to satisfy the detector:

- **`config/load.py`.** `_select_config_table` and `_has_supported_content`
  both walked `tool` → `stilyagi` for `pyproject.toml`, one returning the
  selected mapping and the other a boolean. Discovery has to answer "is this a
  Stilyagi config?" before paying for a parse, and the parse then needs the
  same table, so both now share `_pyproject_stilyagi_table`, a private helper
  returning the candidate mapping or `None`. The two callers reduce to the
  mapping and to `is not None`. Genuine duplication, extracted at the correct
  layer, inside one module, with no new public surface.
- **`config/schema.py` and `config/parse.py`.** Both contained the
  `pathlib.Path()` / `str()` structural match that normalizes a cache-directory
  value. `schema.py`'s `_coerce_path` raises `TypeError` for a dataclass
  `__post_init__`; `parse.py`'s inlined copy raised `InvalidConfigError` naming
  the offending file and key. The shared normalization is now
  `normalise_path_value`, which raises `TypeError` with a field-less message;
  `_coerce_path` wraps it to add a dataclass field name, and `_parse_cache_dir`
  wraps it to add the file and key. Each caller keeps the richer error its own
  contract requires, and the duplicated branch is gone.

Where a family is deliberate, the record states the independent contract or
boundary that an extraction would wrongly couple. No unresolved genuine
duplication is relabelled as "intentional", and no family is left adjudicated
only by the `top` cutoff: the ranking is saturated, so the four above are all
of them.

## Outcomes & Retrospective

Delivered: the gate, its helper tests, four reasoned exception entries, the
pin-agreement contract test, and the documentation. The scan is deterministic
and its ranking is saturated, so the gate's coverage of `python/stilyagi` is
total rather than merely the top 30.

Demonstrated end to end in a disposable workspace with the real pinned binary,
then torn down. No planted clone or temporary exception remains in this
repository, and exactly the four adjudicated entries are present.

| Scenario                                                         | Observed                                           |
| ---------------------------------------------------------------- | -------------------------------------------------- |
| Pristine tree                                                    | exit 0, 4 allowed                                  |
| Planted clone of `engine/checker.py`                             | exit 1, `copy-paste` value 212.4                   |
| One-key exception for that family                                | still exit 1; the entry reported stale             |
| Both keys listed                                                 | exit 0, 5 allowed; comments preserved              |
| A third copy added                                               | exit 1, 5 unsuppressed, both earlier entries stale |
| Five consecutive runs                                            | byte-identical output (one md5)                    |
| `::name` key on a named location                                 | passes; the narrow key works when a name exists    |
| Mistyped root (`python/stilyag`)                                 | exit 2, `path does not exist`                      |
| Clone under `tests/`                                             | exit 0, correctly out of scope                     |
| Clone under `python/stilyagi/nlp/`                               | exit 1, correctly in scope and recursed            |
| Eight concurrent `allow` writers                                 | all 8 recorded, no lost updates                    |
| Hostile reason (`$5`, `$(whoami)`, backticks, quotes, backslash) | round-tripped exactly                              |

_Table 1: End-to-end demonstration results._

Lessons worth carrying forward:

- **A partial exception is worse than none**, because it looks like
  adjudication while still failing. Confirming that a one-key entry leaves the
  family blocking was the check worth running; the coverage rule is the whole
  safety property, and it is now stated in the developer's guide and in
  `AGENTS.md`.
- **`top` is a bound, not a guarantee.** The four-family saturation is a
  measurement of the present tree. Recording it as a measurement rather than as
  a claim that the gate sees everything is what keeps the bound honest when the
  package grows.
- **The default surface is not a safe default.** The detector's dashboard
  reports nothing here; without `surface = "all"` the gate would have passed
  vacuously against four live families.
- **A mistyped root is a provisioning error, not a clean scan.** The detector
  exits 1 for a nonexistent path, and the gate maps that to exit 2, so a scope
  typo cannot masquerade as success. That was verified rather than assumed.
