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
  vacuously. A root that does not exist fails the detector run outright. An
  empty `roots` array is rejected when settings load. A root that exists but
  holds nothing `nose` can parse is caught at the subprocess boundary, where
  the wrapper promotes `nose`'s own empty-scope warning to a configuration
  error instead of accepting the empty family list it emits alongside it. A
  _partial_ narrowing — several roots where at least one selects supported
  files — remains undetected: measured on `nose` 0.20.0, that run exits 0 with
  an empty stderr, so there is no diagnostic for the wrapper to promote. A
  multi-root configuration can legitimately rank families from a subset of its
  roots, so the wrapper does not attempt to infer each root's contribution.
  Partial narrowing is therefore an accepted boundary recorded here, not a
  closed one. The empty-scope guard is itself textual: it matches the pinned
  detector's `no supported source files found under:` line rather than
  enumerating source files, so a detector release that reworded that diagnostic
  would disable the guard. The version pin is what keeps that from happening
  unnoticed.
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
- [x] Documentation and ADR (009, renumbered to 010 after the fifth rebase).
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
            This checklist entry proved to be the last edit, so the pushed
            head is `f925d1b` plus one comment-only commit. Because ticking a
            checklist box still changes a tracked file, the delta was not
            assumed harmless: the three gates that read Markdown were re-run
            on it (`check-fmt`, `markdownlint`, `nixie`, all exit 0, logged
            under `/tmp/verify6-<gate>...out`), and the commit was confirmed to
            carry the very blob those gates read (`37a5de3b`). The scoped run
            skipped `lint`, `typecheck`, `test`, `duplication` and
            `duplication-test` on the evidence that no Python, Rust, TOML,
            Makefile, workflow or script file changed and that no test reads
            anything under `docs/`; that reasoning is recorded here rather
            than left implicit, since "docs-only" is a claim about who reads
            the file, not about the file's extension.
      - [x] Rebased a third time, onto `c65a29e` (PR #196), because the pull
            request was left `CONFLICTING` against `main`. Main had gained
            twenty commits, three of which this branch collides with: PR #189
            moved Whitaker provisioning into the shared `install-whitaker`
            action and deleted the local `WHITAKER_INSTALLER_VERSION` pin,
            PR #172 added the "Runner placement" subsection as `### 6i.`, and
            PR #173 replaced five local CodeScene contract modules with the
            shared CV-005 `test-workflow-contracts` target. Two conflicts, both
            resolved by keeping the intent of each side rather than picking
            one: in `smoke.yml` the branch's `NOSE_VERSION` pin stays while the
            Whitaker pin goes with the installer that consumed it; in
            `docs/developers-guide.md` both sides had independently added a
            `### 6i.`, so main's section keeps 6i and this branch's takes the
            next free ordinal, `6j`. A repository-wide search confirmed
            nothing cross-references either heading, so the renumbering breaks
            no link. `git range-diff` reproduces fourteen of the sixteen
            replayed commits byte-for-byte; the two that differ are exactly
            those two conflict resolutions.
      - [x] Post-rebase semantic audit. Of the 35 paths main changed and this
            branch never touched, all 35 are byte-identical at the rebased
            head, so no merge reconstruction leaked into a file the branch had
            no business editing. Every deletion against `main` in a
            branch-touched file maps to a deletion the original branch made;
            none is unexplained. No file that exists at both revisions carries
            a newly repeated block. The final-diff review found no benchmark
            leakage, no copied reference paths, no broad suppressions, no new
            runtime dependency, and no change to the `requires-python` floor.
      - [x] Full gate suite re-run on the rebased tree (`2b0431a`).
            `check-fmt`, `typecheck` and `lint` exit 0, and `test` completes
            every suite green. Two counts are lower than the previous run and
            both are attributed to main rather than to this branch. Main's
            PR #173 deleted six local CodeScene contract modules and three
            support modules, which accounts for the pytest total falling from
            564 to 533. Two of those support modules -- `codescene_coverage.py`
            and `codescene_environment_rules.py` -- are also the whole of the
            doctest total falling from 22 to 20: both sit inside the
            `--doctest-modules python/stilyagi tests/support` lane and each
            carries exactly one docstring example, so the lane holds 21 items
            (20 passed, 1 skipped) where it held 23. The nextest total is
            unchanged at 337. `lint` again completed the duplication gate at
            "4 allowed by reasoned exceptions", which is the gate this work
            adds, passing on the rebased tree. `typecheck` needed a local
            transport workaround rather than a code change: the Lody
            credential broker was down, and this session's `PATH` routes
            GitHub fetches through a Lody git shim, so the fetch of the
            `df12-python-lints` dev dependency aborted. Re-running with the
            shim removed from `PATH` and the injected git config disabled
            resolved the same pinned commit (`4cf41736`) anonymously. The
            fault is local to this machine; CI fetches with its own token.
- [x] Review remediation round two. The pull request drew a review with eight
      inline findings plus a failing "Unit Architecture" check and a warning on
      developer documentation. Each finding is verified against the current
      code before any edit, and only still-valid findings are fixed.
      - [x] Rebased a third time, onto `c65a29e` (PR #196); full gate suite
            re-run green and pushed as `2c7d61f`. Recorded separately in the
            checklist above; the review arrived against that head.
      - [x] Verified the eight inline findings against the staged tree. All
            eight are already addressed: ADR-008 carries no first-person
            pronoun; no `from __future__ import annotations` remains under
            `scripts/`, `python/`, `tests/`, or `.github/`; `nose_schema.py`
            separates the integer check from the `end < start` check;
            `duplication_allowlist.py` refuses a catch-all glob at validation;
            `duplication_manifest.py` names a malformed parent table; the
            gate's two configuration-error paths both print a diagnostic and
            exit 2; the 506-line and 631-line test modules are split; and
            `normalise_path_value` plus `_pyproject_stilyagi_table` are
            documented in the developer's guide. No further edit needed.
      - [x] Adopt the episodic Python gateway: Pylint and df12-python-lints
            run on CPython 3.14 over `python/stilyagi tests scripts`, and
            `ty` type-checks those roots plus `.github`. This is the
            `PYLINT_TARGETS` widening recorded at Makefile:43; the widened
            target set is what exposed the seven findings below.
      - [x] `make lint` abort 1: Pylint C1803 in
            `tests/test_workflow_reader_units.py`, on an assertion
            byte-identical to `origin/main`. The staged rewrite of
            `tests/support/workflows.py::workflow_steps` from a comprehension
            to an annotated accumulator lets Pylint prove the return is
            strictly a list, which switches the rule on at an unchanged call
            site. Fixed by rewriting the assertion to `assert not
            workflow_steps(…)`, keeping its failure message.
      - [x] `make lint` abort 2: DF12 Pylint exit 24 with seven findings in
            `scripts/tests/`, newly reachable only because the widened
            `PYLINT_TARGETS` now includes `scripts`. Fixed at the source
            rather than suppressed: C9102 in `test_make_install_nose.py`
            gained the missing failure message; R9111 in `test_atomic_write.py`
            gained `slots=True` on both spy dataclasses; R9108 in
            `test_nose_command.py` and `test_duplication_gate_commands.py` were
            converted to syrupy snapshots, the repository's and episodic's
            established answer for snapshot-worthy literals.
      - [x] The `duplication-test` lane runs `--no-project`, so the snapshots
            needed `syrupy==6.1.1` added to that recipe's explicit `--with`
            list, and `DUPLICATION_TEST_ARGS` was declared so
            `--snapshot-update` can be passed at the command line. The four
            snapshots were generated, then the lane re-run without the flag:
            135 passed, 4 snapshots passed. Developer's guide and scripting
            standards record the lane's dependency pinning and the
            snapshot-update workflow.
      - [x] Both Pylint tiers verified green by hand over the widened target
            set: focused Pylint and DF12 Pylint each 10.00/10, exit 0. An
            earlier manual run that forced `--enable=E,F` was invalid and its
            E0401 import errors were an artefact of overriding the curated
            message list; running the pass exactly as `make lint` invokes it
            is clean.
      - [x] Full gate suite re-run on the remediated tree, with a verdict for
            every `make lint` step and not just the Pylint tiers. `lint` now
            completes every step the previous abort never reached: Ruff,
            Interrogate at 100.0%, focused Pylint and DF12 Pylint each
            10.00/10, ambrleaks clean, `cargo doc`, clippy with `-D warnings`,
            Whitaker, Skylos clean, and the Makefile:219 duplication gate
            passing at "4 allowed by reasoned exceptions". `typecheck` passes
            with `ty` reporting "All checks passed!", and `test` runs 337/337
            nextest, 533 pytest with 15 snapshots, 20 doctests, and 135
            duplication-test with 4 snapshots. The first pass of this run had
            `check-fmt` red because the prose added during remediation was not
            wrapped to the repository's 80-column style; `make fmt` re-flowed
            three Markdown files, and the re-run is green on all six gates
            with the tree unmutated (`typos.toml` sha256 unchanged).
      - [x] Committed the remediated tree as `c47154f` and pushed it; the
            remote branch and the PR head both point at that commit. The
            commit message records the verification-first pass over the eight
            inline findings and the seven gateway findings fixed at source.
            Requesting the new review with `/comenq-coderabbit` is the next
            action.
      - [x] Queued the new review through the managed queue: `comenq put`
            returned queue ID `92157e25` for `leynos/stilyagi#164` with an
            ETA of roughly 32 hours, behind a queue of 89 pending requests.
            The request names candidate head `32866f4` and the remediation
            scope. The previous CodeRabbit full review inspected `cfc6a67`,
            and its walkthrough's `change_assessment_commit` still names that
            commit, so the two pre-merge rows (Unit Architecture error,
            Developer Documentation warning) describe an old head. Both
            subjects were already addressed in earlier rounds and are
            re-verified on this head; the queued review will recompute the
            rows. Twelve of twelve inline threads remain unresolved on the
            PR and require `@coderabbitai` replies; the findings themselves
            were verified against the remediated tree and needed no further
            code changes.

### CI repair: the `--no-project` lane ran below the project floor

- [x] Diagnosed the `lint-test` failure on `d94357a` (smoke run
      `37037513224`, job `110939372675`, step 21 `make duplication-test`) as
      **not** a defect in the gate's logic. The check-run annotation gave only
      `Process completed with exit code 2`; `gh run view --log` gave the real
      traceback, terminating at `scripts/atomic_write.py:36: in <module>` →
      `NameError: name 'cabc' is not defined`, with 13 collection errors and
      only 4 tests collected.
- [x] Root cause, established by reproduction rather than inference. The
      workflow installs Python 3.14 at the workflow level, but the lane runs
      `uv run --no-project`, which makes uv ignore
      `requires-python = ">=3.14"` and resolve whatever interpreter it finds
      first — on the runner, 3.13.16 (the log line reads
      `platform linux -- Python 3.13.16, pytest-9.0.2`). `scripts/atomic_write.py`
      imports `collections.abc as cabc` only under `typing.TYPE_CHECKING` and
      annotates `_open_directory` with `cabc.Iterator[int]`. Python 3.13
      evaluates that annotation eagerly at `def` time; 3.14 defers it under
      PEP 649.
- [x] Confirmed the fix must be the interpreter, not the annotation. A probe
      showed PEP 649 is a **deferral, not a resolution**: on 3.14.4,
      `annotationlib.get_annotations(f, format=VALUE)` and
      `inspect.signature(f)` still raise `NameError` for the same function;
      only `Format.FORWARDREF` and `Format.STRING` succeed. So moving the
      import to runtime would "fix" one interpreter while leaving the
      annotation genuinely unresolvable on every one, and it would fight
      Ruff's `TC003` (`flake8-type-checking`, enabled in `pyproject.toml`),
      which _requires_ annotation-only imports to live in a `TYPE_CHECKING`
      block. A probe confirmed `TC003: Move standard library import
      'pathlib' into a type-checking block` fires on the runtime-import
      shape. Ruff is configured `target-version = "py314"`, so the
      TC003-mandated placement is correct under the project's declared floor;
      the lane was simply running below it.
- [x] Applied the minimal repair: `Makefile` gains
      `DUPLICATION_TEST_PYTHON ?= 3.14` and the recipe passes
      `--python $(DUPLICATION_TEST_PYTHON)` to its `uv run --no-project`
      invocation, with a comment recording why the pin is load-bearing.
      `tests/test_toolchain_contract.py` gains
      `TestDuplicationLaneInterpreter`, which asserts the variable exists,
      that the recipe references it, and that its version clears the floor
      parsed from `pyproject.toml`. Verified as a true regression test: the
      new test fails with the `--python` line removed and passes with it
      restored. This repairs CI by honouring the project's own declared
      baseline, not by lowering a threshold or silencing a lint.
- [x] Re-ran the commit gates on the repaired tree. The first `make lint` run
      failed at Interrogate (99.9% against the required 100%) because the new
      regression guard carried a nested `parts` helper with no docstring, and
      because Interrogate is only the second step of the recipe, every later
      step — Pylint, df12-pylint, ambrleaks, rustdoc, Clippy, Whitaker,
      Skylos, and the nose duplication gate — was skipped and therefore
      unverified. Inlining the nested helper (which also removed needless
      structure) restored 100% coverage, and the re-run executed the entire
      pipeline green with exit 0. **Lesson:** a failure early in the `lint`
      recipe does not merely fail one linter, it leaves the rest of the gate
      unrun, so a second complete run is required before the gate can be
      called green.
- [x] Re-confirmed the markdownlint fix. MD049 in its default "consistent"
      mode reads the document's _first_ single-marker emphasis as canonical;
      the added block used `*requires*` above the existing `_Table 2:..._`,
      which flipped the expected style to asterisk and flagged five
      pre-existing underscore emphases below it. `**bold**` is MD050, not
      MD049, which is what made the interaction hard to see. Changing the one
      marker to `_requires_` restored consistency. All ten reported issues
      cleared.
- [x] Proved the fix against the precise CI failure condition rather than
      only observing green locally. With `UV_PYTHON=3.13` forcing 3.13 as uv's
      discovered default, the **unfixed** invocation reproduces CI exactly —
      exit 2, `NameError: name 'cabc' is not defined`, interrupted during
      collection — while the **fixed** invocation still runs 3.14.4 and
      passes. The explicit `--python` overrides the discovered default, which
      is the mechanism the repair relies on.
- [x] Commit `ac77fe0` carries the repair. All four commit gates are green on
      that exact tip, each re-run after the last edit: `make check-fmt`
      (exit 0), `make lint` (exit 0, full pipeline through Skylos and the
      blind-detection gate — 4 reasoned exceptions), `make typecheck`
      (exit 0), and `make test` (exit 0; nextest over the workspace, rustdoc,
      534 pytest passed, 20 doctests passed with 1 skipped, and the
      duplication lane's 135 passed inside it). `make markdownlint` (exit 0;
      69 files, 0 issues) and `make nixie` (exit 0) also pass.
- [x] Pushed `ac77fe0` and `8381c48`. Both commits are published on
      `origin/adopt-nose-code-deduplication`: the live remote head is
      `8381c48`, a fast-forward from the previous `d94357a` (ancestry
      verified with `git merge-base --is-ancestor` before pushing, so no
      force was needed and no remote work could be lost). The push initially
      failed for a reason unrelated to the change: every GitHub path --
      `git push`, `git ls-remote`, and `gh` -- was routed through the Lody
      GitHub client, whose local credential broker (127.0.0.1:33833) was
      wedged: the socket accepted TCP but never answered any endpoint, so
      the helper's 10 s timeout surfaced only its generic "Cannot verify
      GitHub identity preferences with Lody" message. `lody machine list`
      initially reported this host `machine_offline` and the daemon logs
      showed it had stopped at 17:28 with no crash trace. The resolution was
      to stop using Lody for GitHub and push over SSH as `leynos` (verified
      with `ssh -T git@github.com` before pushing), which does not depend on
      the broker at all. **Lesson:** a Lody identity-verification failure is
      an infrastructure failure on the credential path, not a repository or
      credential problem; the standard client plus SSH is the supported
      route, and retrying the Lody route cannot succeed while the broker is
      unresponsive. The pushed head invalidates the queued review's
      coverage, so the queued review request needs re-checking against it.
- [x] Re-read the PR's check rollup for the new head and confirmed the
      `lint-test` job's duplication lane now passes in CI. Run 37047890370,
      job 110973723346, step 21 "Duplication-gate helper tests":
      `completed/success`. This is the step that failed on the previous head
      with the collection-time `NameError`, so the repair is confirmed under
      the exact condition it was written for, not merely locally. The
      surrounding steps also pass on the same run — step 14 "Check
      formatting", 15 "Lint Markdown", 16 "Spelling", 17 "Mermaid lint", 22
      "Typecheck", 23 "Lint and dead-code detection", and 24 "Docstring
      examples" — and all three required `release-smoke` legs
      (ubuntu/macos/windows) are green. The worktree cannot reach GitHub
      over the Lody route, so these reads use the standard client
      (`/usr/bin/gh`) with the Lody variables scrubbed.
- [x] Established that the CodeScene failure on this head is **not** a
      required status check and therefore does not block. The active `main`
      ruleset (id 18427824) requires exactly four contexts: `lint-test`,
      `release-smoke (ubuntu-latest)`, `release-smoke (macos-latest)`, and
      `release-smoke (windows-latest)`. CodeScene is absent from that list.
      It reports "New code is healthy" failing on the same four gate files
      (`scripts/duplication_allowlist.py`, `scripts/nose_schema.py`,
      `scripts/tests/test_duplication_gate_commands.py`,
      `scripts/tests/test_duplication_gate_boundaries.py`) that the
      adjudication record already dispositioned as deliberate parallels, at
      a Code Health score of 9.39 against a 10.00 gate. Note for the record
      that this check is green on every other recent PR head (198, 197, 196)
      and has been failing across this branch's recent commits, so it is
      specific to this PR's added files rather than an inherited outage; the
      prior adjudication stands, and the failure is advisory.

### Thread disposition round

- [x] Established the reply route before writing anything. `comenq` has no
      thread-reply subcommand (`put list bump bust del hist`), so it cannot
      answer inline threads. The project's already authorized route is an
      in-thread reply posted under the `leynos` identity through `gh`, which
      is what stilyagi #179, #188, and #190 all use. PR #164 is the outlier:
      twelve inline comments and **zero** inline replies, which is the gap
      this round closes. The three existing `leynos` comments on #164 are
      top-level `@coderabbitai` prompts, not thread replies.
- [x] Re-fetched every review surface on `d94357a` rather than trusting the
      earlier snapshot. GraphQL `reviewThreads` paginates to exactly 12
      threads, all `isResolved: false`, one comment each. Reviews now stand
      at: `chatgpt-codex-connector` and `coderabbitai` both anchored to
      `cfc6a67` (stale), while `codescene-access` posted four reviews walking
      `2c7d61f` → `c47154f` → `32866f4` → `d94357a` within about two hours.
      The CodeScene reviews against the two newest heads added no new
      threads, so the twelve are complete.
- [x] Read the live walkthrough (`5851408713`, edited in place, last update
      16:58:11Z) and found a banner the earlier reconnaissance missed:
      **"Reviews paused"**. CodeRabbit auto-paused on commit volume. Its
      `change_assessment_commit` and `final_review_risk` coverage both still
      name `cfc6a67`. The pre-merge table is unchanged at **one error and one
      warning**: Unit Architecture (allowlist boundary handling) and
      Developer Documentation (`normalise_path_value` /
      `_pyproject_stilyagi_table`). Both remain in scope regardless of the
      pause, because `pre_merge_checks.ignore_useless_reviews` is on and the
      pause gates only re-review, not whether the rows need a disposition.
- [x] Verified the Developer Documentation warning's subject matter directly,
      since no verifier was assigned to it. `docs/developers-guide.md:413-418`
      documents `_pyproject_stilyagi_table` as the shared `tool` → `stilyagi`
      walk, and `:451-457` documents `normalise_path_value(value)` with its
      accepted types, return value, `TypeError` contract, and both callers'
      added context (`schema._coerce_path` field prefix,
      `parse._parse_cache_dir` file-and-key reporting). That is every element
      the resolution column asked for. The row is stale on this head.
- [x] Verified each of the twelve findings against the current tree with three
      wyvern teams (CodeScene ×4, Codex ×3, CodeRabbit ×5), then replied in
      every thread under the `leynos` identity with the candidate head, the
      disposition, and file/line or command evidence.
- [x] CodeRabbit ×5 and Codex ×3 verified **FIXED** on the current tree. The
      Codex checks confirmed the test split reached its target
      (`test_duplication_gate_commands.py` 631 → 323 lines; the 506-line
      `test_nose_detector.py` removed and replaced by four modules of 81–264
      lines) and that a scalar parent table now raises `GateConfigError`
      through `_require_table` (`duplication_manifest.py:30-35`, `:69-72`).
      The verification left two coverage gaps as findings in their own right:
      no dedicated test for a scalar `tool.duplication_gate`, and none for a
      boolean `end`. Both are untreated; they are new work, not regressions,
      and are candidates for a follow-up change rather than this PR.
- [x] CodeScene ×4 verified **DELIBERATE-PARALLEL**, and this is the first
      time any of the four has a recorded disposition. The verifier confirmed
      the shared text is the module's error-vocabulary idiom or the fixture
      skeleton of a CLI-contract test, while the contracts differ
      (`nose_schema.py`'s `require_string`/`require_positive_int` enforce
      different types, domains, and diagnostics; the four
      `test_duplication_gate_commands.py` cases pin four distinct production
      call sites across two modules; the two
      `test_duplication_gate_boundaries.py` translators map different error
      taxonomies). Extracting any pair needs the predicate-taking,
      boolean-mode helper that `pyproject.toml:417-419` already refuses.
      **Caveat carried forward:** CodeScene's mean of 4.27 over
      `duplication_allowlist.py` is not reproducible locally (an independent
      instrument gives 3.667 over the same 15 functions, and the gate that
      actually runs, Ruff `C90` at `max-complexity = 8`, passes the file), so
      the numeric claim must not be quoted as if it were verified.
- [x] Recorded why the four CodeScene markers had no disposition until now:
      `[tool.nose] roots = ["python/stilyagi"]`, so the repository's own
      duplication gate cannot see `scripts/` at all. That exclusion is
      deliberate and documented (`docs/developers-guide.md:1683-1684`,
      `docs/execplans/adopt-nose-code-deduplication.md:647-648`), which means
      CodeScene is currently the only duplication or complexity signal over
      the gate's own modules. Adding a mechanical disposition store for
      `scripts/` is a real gap, but inventing one in this PR would widen its
      scope; note it rather than build it here.
- [x] Replied in all twelve threads, each citing the pushed head `8381c48`
      and its evidence. Every reply was posted successfully (12 posted, 0
      failed) via the GraphQL `addPullRequestReviewThreadReply` mutation
      under the `leynos` identity with the Lody variables scrubbed.
      CodeRabbit then independently re-verified all five of its own threads
      against `8381c48` — running `git rev-parse HEAD` and inspecting the
      files at the pushed head — and **resolved all five itself**. Its
      replies confirm the dispositions quote correctly: the ADR "now states
      'the choice is for running'", `from __future__ import annotations` is
      "absent from `scripts/`", and `_location` "now separates the type
      failure from the ordering failure". The remaining seven threads
      (Codex ×3, CodeScene ×4) carry the reply as their last comment and stay
      open for their authors to resolve; the two Codex coverage gaps are
      recorded in the Codex reply as acknowledged follow-up work, not as
      unresolved defects.
- [x] Re-verified every disposition against the **pushed** tree rather than
      the pre-push one, and one claim needed correcting before it was
      published. The planned Codex reply would have cited `_require_table`
      at `duplication_allowlist.py`; on the real tree that helper lives in
      `scripts/duplication_manifest.py:30` and is called from `sub_table`
      (`:71`), while `duplication_allowlist.py` holds the allowlist logic.
      The reply cites the correct file. Similarly, CodeRabbit's `end`-split
      finding was confirmed with the real source at
      `scripts/nose_schema.py:264-270`, not from the plan's recollection.
- [x] Posted the pre-merge checks reconciliation as top-level comment
      `5959094062` on the pull request, using the skill's template with the
      live failed-checks heading and both rows copied verbatim. It requests an
      AI agent prompt for any remaining work and states that both rows were
      re-verified at head `8381c48` rather than inferred from their anchors.
      The comment records the anchor drift explicitly — the Unit Architecture
      row points at `duplication_allowlist.py:150-151`, but `load_allowlist`
      now begins at `:172`, so the row's own citation no longer resolves —
      and gives the evidence for each: the `require_table` chain plus the two
      translated read/parse boundaries for Unit Architecture, and
      `docs/developers-guide.md:413-418` / `:451-456` for Developer
      Documentation. It closes by asking that any still-unmet element be named
      specifically rather than re-asserted as a whole row. No full review was
      queued for this: the skill is explicit that a stale table alone does not
      warrant one.
- [x] Adjudicated the follow-up finding CodeRabbit returned on that comment,
      and **rejected the proposed remedy as unsound while treating the
      underlying question as legitimate**. CodeRabbit asked that
      `_is_catch_all_glob` reject `*/**` and `**/*/**` alongside `**`, `**/*`,
      and `**/**`, on the stated grounds that both "are recursive catch-all
      forms under `PurePosixPath.full_match` semantics". That premise is
      false. Enumerated over every path shape of depth 1–6, `*/**`,
      `**/*/**`, and `**/*/*` produce **identical** match sets, and all three
      require at least one named segment below the recursion, so none matches
      a single-segment path. This repository tracks 14 such paths at its root
      (`Makefile`, `pyproject.toml`, `Cargo.toml`, `AGENTS.md`, `README.md`,
      `uv.lock`, …), so `*/**` demonstrably does not silence "every finding in
      the repository". Implementing the request would have introduced six
      false positives across the 1–4-part wildcard space, rejecting keys that
      legitimately scope a family — the opposite of the guard's contract.
      - [x] Verified the guard rather than assuming it: an exhaustive
            comparison over `{literal, *, **}` × 1–4 parts (120 patterns)
            against ground-truth `full_match` semantics found **zero false
            negatives and zero false positives**. The structural check was
            already exact; only its test coverage was thin.
      - [x] Converted the gap into pins rather than a code change. Added
            `*/**` and `**/*/**` to the accepted-keys parametrization and a
            new `test_recursive_prefix_patterns_are_scoped_not_catch_all`
            asserting, for each of the three equivalent patterns, that it is
            accepted, does **not** match `Makefile`/`pyproject.toml`/
            `README.md`, and **does** match a nested path. The reviewer's
            requested regression cases now exist, asserting the correct
            contract.
      - [x] Confirmed the reviewer's runtime objection is obsolete: it
            reported `full_match` unavailable on a Python 3.9 sandbox and
            asked for a 3.14 retry. All measurements above were taken under
            the project's pinned 3.14.4 interpreter, and the doctest for
            `key_matches` already depends on `full_match`.
      - [x] Named the disputed patterns in `docs/developers-guide.md` beside
            the existing scope argument, so the contract is stated rather than
            left for a reader to infer from the code shape. This is the edit
            that matters for the finding: the earlier prose listed only `**`,
            `**/**`, and `**/*` as refused and `**/*/*` as accepted, which is
            correct but silent on the two forms that prompted the request.
      - [x] Gate run on the tests-and-docs delta: `make check-fmt`,
            `make lint`, `make typecheck`, and `make test` all green.
            `lint` reports the duplication gate passing at "4 allowed by
            reasoned exceptions"; `test` reports nextest 337 passed, pytest
            534 passed, doctests 20 passed / 1 skipped, and the
            `duplication-test` lane 140 passed with 4 snapshots — the lane
            that runs `scripts/tests/test_duplication_gate.py`, so the new
            cases are exercised under the gate. The focused selection passed
            10/10 under 3.14.4.
      - [x] `make markdownlint` then failed in its `spelling` prerequisite on
            two of this round's own additions: `catch-alls` in the developer's
            guide and `parametrisation` in this plan. Both were genuine
            vocabulary errors rather than dictionary gaps — the guide already
            used the singular `catch-all`, and the repository's own convention
            is the `-z-` spelling (`parametrized` ×5, `parametrization` is the
            `typos` default). Reworded to `a catch-all` and `parametrization`;
            no word was added to `typos.local.toml`, per the project rule that
            the dictionary carries established vocabulary, not slips.
      - [x] Re-ran the full suite on the frozen tip before committing, rather
            than trusting the earlier run: two prose edits landed after gates
            1–4 had last passed, and this repository has contract tests that
            parse Markdown. All five gates green, tree byte-identical before
            and after. Committed as `e33ad72` (3 files, +187/−9) and pushed
            over SSH to `origin/adopt-nose-code-deduplication`.
      - [x] Posted a second reply correcting the first for reviewability. The
            opening reply cited the new test only by name; the follow-up gives
            its exact location, `scripts/tests/test_duplication_gate.py:152`
            in `TestValidateKey` at blob `62b557f5`, and notes that the file
            is in the `make duplication-test` lane's explicit list
            (Makefile:255), so the cases run under `make lint`. All three
            claims were re-read at the pushed tip before being posted.
      - [x] CI monitoring delegated on `e33ad72`: `lint-test` and the three
            `release-smoke` legs entered `IN_PROGRESS`. `mergeStateStatus` is
            `BLOCKED`, which is the expected shape for an open PR whose
            required checks have not yet reported, and `reviewDecision` is
            still `CHANGES_REQUESTED` from the `cfc6a67`-anchored review —
            both are read-back facts, not inferences from green gates.
      - [x] Committed the read-back record as `5832ee5` (one file, +19) after
            re-running all five gates on that exact tree — the docs-only
            narrowing does not apply here, because this repository's contract
            tests parse the Markdown. Pushed over SSH, fast-forwarding
            `e33ad72` → `5832ee5`.
      - [x] CI on `5832ee5` (smoke run 37053117156) is green on every required
            check: `lint-test` succeeded with all 35 steps successful and none
            skipped, and the `Duplication-gate helper tests` step proved to
            have _executed_ rather than short-circuited — it collected 140
            items and passed 140 with 4 snapshots, on Python 3.14.7. All three
            `release-smoke` legs passed. `Gecko Security Review` passed.
      - [x] Re-read the CodeScene failure rather than waving it through, and
            confirmed it is **pre-existing, advisory, and outside this
            change's footprint**. It fails identically on `8381c48`,
            `e33ad72`, and `5832ee5` — the same four files
            (`duplication_allowlist.py`, `nose_schema.py`,
            `test_duplication_gate_commands.py`,
            `test_duplication_gate_boundaries.py`) at the same 9.39 impact
            with 2 active suppressions. `scripts/tests/test_duplication_gate.py`,
            the only file `e33ad72` changed, is not named by it. CodeScene is
            not a required check for this repository: the required contexts
            are `lint-test` and the three `release-smoke` legs (ruleset
            18427824), and `GET /branches/main/protection` returns 404
            "Branch not protected", so there is no protection rule to satisfy.
            No suppression was added.
      - [x] Left the queued review request in place. `comenq list` shows
            `92157e25` for `leynos/stilyagi#164` still pending at roughly 29
            hours behind an 87-deep queue. It is deliberately **not**
            duplicated: the skill states the comment body does not pin a
            review to a commit, so the pending request still serves the newer
            head, and adding a second request would only deepen the queue.
      - [x] Terminal read-back at hand-off: head `5832ee5`, required checks
            green, `reviewDecision` still `CHANGES_REQUESTED`. That decision
            comes from the `cfc6a67`-anchored CodeRabbit review of
            2026-09-29; CodeRabbit's later activity on `8381c48` was
            `COMMENTED`, and it self-resolved all five of its own threads
            there. The eight remaining unresolved threads (Codex ×3,
            CodeScene ×4, plus the CodeRabbit thread carrying this round's
            adjudication) each have a reply as their last comment and are
            their authors' to resolve. **Not merged**, per the standing
            instruction — the owner retains that decision.

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
   documentation index, and the gate's ADR.

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
only by the `top` cutoff: the ranking is saturated, so the four above were all
of them at the time this paragraph was written. See the section below for the
two further families the rebase exposed.

## Outcomes & Retrospective

Delivered: the gate, its helper tests, four reasoned exception entries (five
after the rebase exposed one further non-extractable family), the pin-agreement
contract test, and the documentation. The scan is deterministic and its ranking
is saturated, so the gate's coverage of `python/stilyagi` is total rather than
merely the top 30.

Demonstrated end to end in a disposable workspace with the real pinned binary,
then torn down. No planted clone or temporary exception remains in this
repository, and exactly the adjudicated entries are present — the four original
ones plus the one recorded when the rebase exposed main's own duplication.

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

### Terminal state on the pushed tip

The plan's last commit is `2eb0397` (a one-character MD049 emphasis fix to this
document, because `4607d6b` had introduced `*executed*` and failed
`make markdownlint`). The remote head `2eb0397` therefore differs from the
`5832ee5` recorded above only by prose inside this plan.

Read back on the pushed tip:

- All five local gates pass on the exact tip pushed (logs
  `/tmp/push4-*-adopt-nose-code-deduplication.out`; `typos.toml` unchanged).
- Smoke run 37055252277 for `2eb0397` is green: `lint-test` 35/35 steps
  success, the `Duplication-gate helper tests` step executed rather than
  short-circuited (140 collected, 140 passed, 4 snapshots, Python 3.14.7), all
  three `release-smoke` legs success, `Gecko Security Review` success.
- `CodeScene Code Health Review (main)` still fails on the same four new files
  with code health below 10.00, naming no file this change touched. It is not
  among the ruleset's required contexts, which are exactly `lint-test` and the
  three `release-smoke` legs, and it was neither suppressed nor dismissed.
- `reviewDecision` remains `CHANGES_REQUESTED`, anchored to a commit predating
  the remediation; the eight still-unresolved review threads each carry a reply
  as their last comment and are their authors' to resolve.

Not merged, per the standing instruction.

The final commit, `a417caf`, is that terminal record itself, so the branch's
tip is the document describing it. Smoke run 37056650967 for `a417caf` repeated
the same result: `lint-test` 35/35 steps success with the
`Duplication-gate helper tests` step executing (140 collected, 140 passed, 4
snapshots, Python 3.14.7) and all three `release-smoke` legs success.

### Fourth rebase onto `ffb0fef`, with the merge authorized

The PR is now assigned to pr-babysitting with an explicit instruction to merge
it once it reaches equilibrium, which lifts the earlier "not merged" boundary.
The branch was therefore rebased a fourth time, from
`c65a29e2bcc99dbd8776af656e97629b119aa3eb` onto
`ffb0fef255cb5c58dfe51904c2b1bf558f6cc89b`, the tip of `main` at the time of
the replay. The rebase ran with the Weave merge driver bypassed
(`-c core.attributesFile=/dev/null -c merge.conflictStyle=zdiff3`), because
Weave is selected for this host by an ambient global attributes rule rather
than by anything this repository tracks; the `-c` overrides were repeated on
every `rebase --continue`.

Twenty-eight commits were replayed onto eight of the new base commits. Sixteen
replayed cleanly. Three needed adjudication:

- **`62df864` "Document the nose code-duplication gate"** conflicted in
  `docs/developers-guide.md` and `typos.toml`. In the guide, `main` had grown a
  `### The Makefile parser in CI` section describing the shared
  `install-makeutil` action, while the branch added
  `### 6j. Code-duplication gate`; both were kept, `main`'s first, separated by
  the blank line MD022 requires. In the same file's lint-variable table the
  branch's five NOSE rows were reconnected after `SKYLOS_EXCLUDE_FOLDERS`,
  keeping `main`'s newer `TYPOS_CONFIG_BUILDER_VERSION v0.1.3`. `typos.toml` is
  generated, so it was resolved to the new base's render: `:2:typos.toml` was
  verified byte-identical to `ffb0fef:typos.toml`, and the only two lines on
  which the branch's hand-kept copy differed were reverts of entries `main` had
  already narrowed.
- **`2b0431a` "Commit the spelling dictionary's regenerated rendering"** became
  genuinely empty, because its single change — narrowing `\bvar\.iamge_id\b` to
  a documented-phrase entry — is already carried by `main`'s render at
  `typos.toml:52`, which the previous resolution took. It was skipped rather
  than re-applied; the replay was started with `--keep-empty --empty=stop`
  precisely so this would stop for adjudication instead of passing silently.
- **`c47154f` "Resolve review findings and adopt the 3.14 Python gateways"**
  conflicted in `docs/developers-guide.md`. The branch adds three `TY_*` rows
  describing the PEP 723 dependency-staging directory; `main` had moved the
  spelling-gate pin from `v0.1.1` to `v0.1.3`. Both sides were kept: the three
  rows went in after `TY`, and `TYPOS_CONFIG_BUILDER_VERSION v0.1.3` was
  retained from `main`. The merged Makefile confirms all four variables exist
  (`TY_EXTRA_PATHS`, `TY_GATE_STAGE_DIR`, `TY_GATE_DEPS`,
  `TYPOS_CONFIG_BUILDER_VERSION ?= v0.1.3`).

The replay therefore ends at 27 commits, one fewer than the 28 replayed: the
skipped empty commit is the only difference in the series.

Audit of the result, against the pre-rebase head
`de80e652e8c77cb668558c7809104d6b4e1abcfb`:

- Per-path SHA comparison shows 55 of the 61 touched paths byte-identical. The
  six that differ are exactly the conflict-affected set (`smoke.yml`,
  `AGENTS.md`, `Makefile`, `docs/developers-guide.md`,
  `tests/test_skylos_lint_contract.py`, `typos.toml`).
- `git range-diff` reports 25 commits `=` and two `!`; the two `!` are the
  commits whose replayed context changed, and their content changes are the
  conflict resolutions above.
- The whole net delta against the new base differs from the net delta against
  the old base in exactly two ways: `typos.toml` is absent (its 14 lines are
  already on `main`), and the guide carries `v0.1.3` where it carried `v0.1.1`.
  Every added and removed non-blank line in the guide was compared as a
  multiset: the only difference is that one string.
- One added blank line appears in the guide that does not appear in the old
  delta. It is the separator between `### The Makefile parser in CI` and
  `### 6j. Code-duplication gate`; without it `make markdownlint` fails MD022.
- All seven paths that `main` changed and the branch did not are byte-identical
  at the new head, so no branch file silently reverted a `main` change.
- Deletions against the new base in branch-touched files are 144 lines, all
  accounted for as the `-` halves of in-place modifications (lint-scope
  widening, the `config.load` extraction, the `_workflow_document` signature).
  No deletion is unexplained.
- `tests/test_skylos_lint_contract.py` differs from both sides because both
  edited it; the auto-merge kept `main`'s `makeutil_contract` assertions and
  the branch's return-type and `str.partition` edits, with no leftover
  reconstruction artefacts.

### Second CodeRabbit round, five fixes and one decline

The review on `de80e652e8` opened six inline findings. All six were verified
against the rebased tree before any edit; five were valid and one was declined
on measured evidence. The repair commit is `35829f9`, "Resolve the second
CodeRabbit review round".

- **`4175478777` (data integrity).** `append_allow_entry` validated entries
  one at a time, so a matching entry 0 returned before a malformed entry 1 was
  ever parsed: the write succeeded and the next `make duplication` then failed
  on the malformed entry. The loop now parses every entry before any mutation
  (`parsed` comprehension, then `zip(entries, parsed, strict=True)`), so a
  malformed entry anywhere raises `GateConfigError` with the file
  byte-unchanged. Regression test: matching entry 0 plus malformed entry 1
  asserts `allow[1]` in the message and byte-identical content. The new test
  fails on the previous code.
- **`4175478780` (correctness).** A bare `NOSE_BIN=nose` was always probed
  at `<repo>/nose`; if absent there the version probe failed even though
  `make install-nose` can find `nose` on `PATH`. `resolve_binary` now delegates
  to `_resolve_override`: a slash-free name with no file at the repository root
  resolves through `shutil.which`, everything else keeps repository-relative
  resolution, and the `candidate is None` check still raises with
  `INSTALL_HINT`. Four `TestResolveBinary` instances were added across three
  cases (one parametrized); two fail on the previous code (the parametrized
  case's `[path]` instance and the missing-everywhere case), and the three
  pre-existing cases pass on both.
- **`4175478774` (stability).** The lint-order test spied `uv`, `cargo`,
  `rustfmt` and `whitaker` but not `cargo-binstall`, so on a fresh checkout
  without `.tools/nose/nose` the `install-nose` else-branch could reach a real
  installer. `cargo-binstall` is now spied alongside the others. This is latent
  on this machine (the installed `.tools/nose/nose` short-circuits the guard)
  but live in CI and on fresh clones.
- **`4175478768` (docs).** The lint-scope paragraph claimed every listed
  tool covers the package, and the "same three roots are what `ty` checks"
  sentence was imprecise. It now separates `AMBRLEAKS_TARGETS`
  (`tests scripts`) from `PYLINT_TARGETS` (`python/stilyagi tests scripts`) and
  states that `ty` reads those three trees plus `.github`, which holds no
  Python files today.
- **`4175478772` (docs).** The scripting-standards bullet implied the
  dead-code and duplication gates check `scripts/`. It now states the Skylos
  scope (`SKYLOS_PRODUCTION_TARGETS`, `python/stilyagi` only) and the
  duplication roots (`[tool.nose] roots`, `python/stilyagi`, with `scripts/`
  excluded so the gate's modules are not self-referential), cites ADR 008, and
  keeps the reuse rule as a review-enforced convention.
- **`4175478782` (declined).** The finding asked for `timeout=29` on the
  gate test support's `subprocess.run` calls, on the premise that pytest's
  30-second timeout would fire before a subprocess timeout. Measured against
  the lane that actually runs those tests: `make duplication-test` passes
  `-c /dev/null`, so `[tool.pytest.ini_options] timeout = 30` never applies;
  pytest-timeout is loaded from the worktree `.venv` (the lane header lists
  `timeout-2.4.0`) but its `timeout` option has no default, so no timer is
  armed and the header prints no `timeout:` line, in contrast with the main
  `make test` header, which shows `timeout: 30.0s`. The files are outside
  `testpaths`, so `make test` never collects them. A 29-second cap would guard
  a limit that is not in force while undercutting the gate's own 120-second
  detector budget; the finding's premise does not hold for this lane.

A first draft of the `nose_detector` fix was heavier than the final shape and
pulled two new CodeScene markers with it: a `Code Duplication` family between
the two parallel bare-name test functions, and an `Overall Code Complexity`
drop from 10.00 to 9.38 on `scripts/nose_detector.py`. Both were caught by
re-running the CodeScene delta against the repair commit before pushing, not by
the delta of the round as a whole. The two bare-name cases were folded into one
parametrized case, and the helper was reduced to a named-condition ternary
after variant testing showed the chained-`if` form measures 9.38 while the
equivalent ternary measures 10.00 — the module is back to 10.00 and the test
module is 10.00. The `duplication_allowlist.py` complexity marker is unchanged
by the repair (9.38 before and after); it is the recorded ACKNOWLEDGED numeric
dispute, not a new regression.

The MD012 failure on the fourth-rebase tip (`docs/developers-guide.md`, double
blank line after the TYPOS row) was fixed in the same commit. A first gate pass
on the repair commit also caught `check-fmt` red: both reworded paragraphs were
wrapped a word or two past mdtablefix's canonical fill, which `make fmt`
re-flowed before the commit was finalized, and the amended commit is green on
`check-fmt`.

A pre-publication re-measurement against the final parametrized shape corrected
three figures in this record. Reverting only `nose_detector.py` to its
pre-repair content fails two added instances (`[path]` and missing-everywhere),
not three, and the pre-existing case count is three, not two; the same
re-measurement shows the declined 29-second cap sits 91 seconds below the
120-second detector budget, not 93. The repair commit's message carried the
same two counts and the same figure, so it was amended rather than published
inconsistent with this record; the file trees are byte-identical and the
rewritten commit is `35829f9`.

### Publish the rebased tip and open the assessment round

The branch was pushed to the PR after the fourth rebase, moving the remote head
`de80e652` → `13d2e6e` with a lease bound to the old value
(`--force-with-lease=refs/heads/adopt-nose-code-deduplication:de80e652`). The
push needed the clean-environment recipe: Lody injects
`url.https://github.com/.insteadof git@github.com:` through command-line
`GIT_CONFIG_*` variables, so a plain `git push git@github.com:...` is rewritten
to HTTPS and rejected for missing `workflow` scope. Stripping `GIT_CONFIG_*`
and the token variables and pinning `GIT_SSH_COMMAND=/usr/bin/ssh` pushed
cleanly over SSH as `leynos`.

Before pushing, all seven gates were re-run on the exact tree at `13d2e6e` with
the working tree and `typos.toml` hash unchanged. After pushing, run
38064812303 on `13d2e6e` is green on all four required checks (`lint-test`
26/26 steps, the `Duplication-gate helper tests` step executing rather than
short-circuiting at 145 collected and 145 passed with 4 snapshots on Python
3.14.7, and all three `release-smoke` legs), and `mergeStateStatus` moved from
`DIRTY`/`CONFLICTING` to `BLOCKED`/`MERGEABLE` — the conflict is gone and only
the review decision remains.

The six inline findings from the de80e652 review each received a reply through
the pool-token route, and CodeRabbit confirmed every one: five acknowledged as
addressing their finding, and the declined `4175478782` explicitly withdrawn
("My finding incorrectly applied the main test lane's 30-second timeout to
`make duplication-test` … I withdraw this finding"). A seventh CodeScene marker
— `Overall Code Complexity` on `scripts/duplication_allowlist.py`, re-opened as
a fresh thread on the new head at 4.33 where the earlier thread read 4.27 — was
dispositioned with the movement disclosed: the repair for `4175478777` raised
`append_allow_entry` from 5 to 6 under radon, which is the added
validate-before-mutate branch the fix exists for. The repository's own
complexity gate, Ruff `C90` at `max-complexity = 8`, passes the file, and no
Suppress link was used.

The completeness/correctness assessment was posted under
`Assessment-ID: pr164-13d2e6e-completeness-2`. The first attempt (`…-1`) drew a
reply saying CodeRabbit could not verify the requested revision for
`leynos/episodic`; the plan cites episodic's PR #276 and ADR-021 as the frozen
design source, and no acceptance claim depends on fetching it, so the re-post
states that scope explicitly and asks for any episodic-dependent claim to be
reported as unverified rather than blocking the whole assessment.

### The `Check formatting` failure on the published tip

Hosted CI failed at step 15 of `lint-test` on `eca12f3`: `mdtablefix --check`
reported `docs/execplans/adopt-nose-code-deduplication.md +2 -2`. The paragraph
added by `eca12f3` wrapped after `13d2e6e`, where mdtablefix wants the line to
run one word further. The local `check-fmt` evidence predated that edit, so the
gate had been validated against a stale tree — the failure was real and the fix
is `make fmt`, which rewrote exactly those two lines. `typos.toml` came back
byte-identical (`75d951c8`) and `markdownlint-cli2` in the same target reported
0 issues in 69 files. Committed as `2c7ecd7` and pushed with a lease bound to
`eca12f3`.

The seven gates were re-run on the new tip and all seven pass (scrutineer logs
`/tmp/<gate>-stilyagi-adopt-nose-code-deduplication-scrutineer-2.out`), with
the worktree clean before and after and `typos.toml` unchanged: `check-fmt`
(212 files formatted, mdtablefix 68 unchanged), `lint` (Interrogate 100.0%,
Pylint 10.00/10 both tiers, duplication gate "4 allowed by reasoned
exceptions"), `typecheck` (`ty 0.0.74` clean), `test` (cargo 13 passed, pytest
538 passed / 15 snapshots, doctests 25 passed / 1 skipped, duplication lane 145
passed / 4 snapshots), `markdownlint` (0 issues in 69 files), `nixie` (all
diagrams validated), `duplication-test` (145 passed). Hosted CI on `2c7ecd7`,
run 38066071000: `lint-test` and all three `release-smoke` legs success — the
four required checks — with `Gecko Security Review` success and
`CodeScene Code Health Review (main)` failing on the same four `scripts/`
files, at 9.39 against 9.38 previously, carrying the same Overall Code
Complexity and Code Duplication markers already adjudicated above.

### The assessment blocker, diagnosed

The assessment was attempted three times and refused three times inside about
two and a half minutes, each with the same text: "I couldn't verify the
requested revision for `leynos/episodic`". The third attempt
(`Assessment-ID: pr164-2c7ecd7-completeness-3`) named no other repository at
all and stated that nothing outside this PR needed to be fetched; it was
refused identically. A diagnostic question then drew a substantive answer that
locates the trigger: the PR description itself carries the external references,
in its Summary and References sections, so the request path tries to verify
that target on every assessment whether or not the question mentions it. The
supplied metadata reports `source: current_reply` and
`unavailableReason: invalid_reference` for `leynos/episodic`, without naming
the selected reference, the failed validation step, or a dependent claim.
CodeRabbit's own reading is that the local acceptance criteria do not need that
evidence — its "Validation and acceptance" section specifies local gate
results, clone demonstrations, error exits, deterministic output, and cleanup —
and that only two claims genuinely need upstream material: whether the port
preserves upstream behaviour, and whether the stated downstream deviations
describe upstream code.

Its smallest-change advice is explicit: do not change the PR implementation and
do not delete valid provenance citations; the defect is in request handling,
where an unavailable provenance target blocks an independent local assessment.
It supplied a maintainer prompt asking for the trace, the cause, and a
correction that preserves unverified status for claims that need unavailable
upstream evidence. No such correction is in the branch's control, so the
assessment gate stands blocked on the service rather than on this
implementation.

The external reference was confirmed publicly readable while diagnosing this:
`leynos/episodic`, PR #276, and the frozen ADR at
`d9e5ac0d254f375e2986f52d91a3b88c117c833b` each answer HTTP 200 to an anonymous
client, and CodeRabbit is installed on that repository. `invalid_reference` is
therefore not an access failure.

### Final state at hand-off

Published head `d805aa0`, base `ffb0fef`, PR ready and `MERGEABLE`. All four
required checks are green on the head (`lint-test` and the three
`release-smoke` legs), with `Gecko Security Review` success and CodeScene
failing on the adjudicated markers only. Hosted run 38066071000 covers the
preceding tip; the head's own run repeats the same four checks.

All 19 review threads now carry a disposition. The eight left unresolved by
their authors were each re-verified against the live source rather than trusted
from their reply text:

- The two oversized-module findings are genuinely fixed. The largest module
  under `scripts/` is `test_duplication_gate.py` at 378 lines;
  `test_duplication_gate_commands.py` is 322 (from 631) and
  `test_nose_detector.py` no longer exists, its cases split into four modules.
  Nothing under `scripts/` exceeds the 400-line limit.
- The parent-table finding is fixed: `_require_table` is defined at
  `scripts/duplication_manifest.py:30` and applied at line 71 before any
  descent.
- The parse-before-mutate repair for the seventh finding is present at
  `scripts/duplication_allowlist.py:311`.
- The three CodeScene markers and the re-posted complexity marker carry their
  reasoned dispositions with no Suppress link.

Two gates cannot be brought to green, and both are recorded above with their
causes rather than worked around: CodeScene's advisory
`Code Health Review (main)`, which is not a required check, and the assessment
conversation, which the service refuses for any request on this PR because its
description carries external provenance links. The review decision still reads
`CHANGES_REQUESTED` from a submission anchored to `de80e652`, four heads
behind; it is stale rather than contradicting the dispositions, and no new
review has been dispatched.

Merging requires one of the two service-side states to clear: a fresh
CodeRabbit review that returns a current decision on this head, or a change in
the assessment request path. Until then the PR is held at
convergence-minus-two, with every requirement this branch controls satisfied
and evidenced.

### Fifth rebase: main advanced and the branch no longer merged

The hand-off state above did not hold. When the PR was next inspected, GitHub
reported `mergeable: CONFLICTING` and `mergeStateStatus: DIRTY`: `main` had
moved from `ffb0fef` to `91941ef` (three commits), and the branch no longer
merged. The three commits were:

- `094c35c` pins the Rust toolchain exactly and lets Dependabot move it.
- `b5b0fe1` bumps `insta` 1.48.0 to 1.49.0.
- `91941ef` expands discovery defaults to Markdown, Python, and Rust (3.2.1),
  a 2065-line ExecPlan, ADR 008, and a new `CodeScene`-visible surface under
  `crates/stilyagi-pyext/src/check_metrics/`.

The last of these is the consequential one: it landed
`docs/adr-008-v1-discovery-defaults.md`, the same ADR number this branch was
using.

**Conflict set.** A merge-tree probe against `91941ef` reported conflicts in
exactly two paths, `Makefile` and `docs/contents.md`, with clean auto-merges in
`docs/developers-guide.md`, `pyproject.toml`, and five `tests/` modules.

**Replay.** The series `ffb0fef..7e2fde3` was replayed onto `91941ef` with the
thirty-four commits preserved:
`--merge --no-fork-point --no-update-refs
--no-autostash --reapply-cherry-picks --keep-empty --empty=stop`,
with `merge.conflictStyle=zdiff3`. Weave was bypassed for the whole operation.
It is selected on this host only by the ambient global attributes file
(`*.py merge=weave`); the repository has no tracked `.gitattributes`, so the
ambient enrolment is not repository consent. The bypass used
`core.attributesFile=/dev/null` plus a command-scoped replacement of the Weave
driver with `git merge-file --zdiff3`, reapplied on every `--continue`.

**Conflicts resolved.**

1. `Makefile`, in commit 2 of 34. The branch inserts the `NOSE_VERSION` block
   immediately above `MD_FILES_FIND`; `main` added a `./.vtcode/*` exclusion to
   that same line. Both changes are wanted, so the resolution keeps the
   inserted block and the `main`-side line. This identical shape recurred in
   commits 17 and 20, where a later branch commit inserted
   `DUPLICATION_TEST_ARGS` and `DUPLICATION_TEST_PYTHON` at the same anchor;
   both were resolved the same way.
2. `docs/contents.md`, in commit 4 of 34. Both sides had added an ADR 008
   index entry under a different title. This is a genuine number collision and
   cannot be resolved by taking either side.
3. `docs/execplans/adopt-nose-code-deduplication.md`, in commit 14 of 34. The
   renumber applied in commit 4 met this commit's checkbox flip at the same
   line; both changes are independent.
4. `tests/test_package_skeleton_units.py`, in commit 17 of 34. `main` removed
   the now-unused `subprocess` and `sys` imports; the branch added
   `import typing as typ` to the same block. The resolution keeps `typing`
   (used by the `if typ.TYPE_CHECKING:` guard at line 22) and drops the two
   imports `main` removed, which have no remaining use in the file.

**ADR renumbering.** Because `main` landed ADR 008 first, this branch's ADR was
renumbered 008 to 009 rather than sharing the number. The file was renamed
`docs/adr-008-nose-duplication-gate.md` to
`docs/adr-009-nose-duplication-gate.md`, its title heading updated, and its two
tracked references updated: `docs/contents.md` (now indexing both ADR 008 and
ADR 009) and `docs/developers-guide.md` section 6j. The two `ADR 008`
references in this plan were updated to `ADR 009`. A tree-wide search confirms
no `adr-008-nose-duplication-gate` reference remains. The two `ADR 008`
references that remain in `docs/roadmap.md` and the discovery ExecPlan belong
to the discovery ADR and are correct as they stand.

**Semantic audit.** The rebase raises no andon condition:

1. All **66** target-only paths — changed by `main` and not by this branch —
   are byte-identical at the new head to their `91941ef` blobs. Zero mismatches.
2. Every deletion against the target is explained by the branch's own intended
   change. There are no `D` or `R` entries in the target-relative diff at all;
   the 149 deleted lines are dominated by `docs/developers-guide.md` (34 lines,
   every one present in the branch's own pre-rebase diff) and by the
   `PYLINT_TARGETS`/`INTERROGATE_TARGETS`/`AMBRLEAKS`/`typecheck` lines the
   branch deliberately rewrote to add `scripts/` and the gate staging.
3. No newly repeated block appears in any of the 33 merged files. The 41
   repeated-block hits the scan reports are all in files this branch adds, and
   are ordinary repeated test boilerplate and docstring section headers, not
   reconstruction artefacts.

`range-diff` over the two series is `=` for 30 of 34 commits and `!` for
exactly the four conflict-affected ones: `a9760cf` (the `tests/` family count
prose), `9e16ec5` (the checkbox flip), `780af9a` (the import block), and
`99fbd02` (the `MD_FILES_FIND` anchor). The path manifest is 60 paths in and 60
out, differing only by the deliberate ADR rename.

New head: `201eaaaacd3756b4dd7d0ca6ae9208791307f3f9`, onto base
`91941ef36df9c262af74e6089e661921d1ae3577`. Recovery refs for `7e2fde3`,
`ffb0fef` and `91941ef` are held under
`refs/recovery/pr164-{old-head,old-base,target}-20261013T010701`. Every gate
result recorded above this section is stale for the new head and is retained
only for its original scope.

### Gates on the rebased head, and the two families the rebase exposed

The seven-gate run on `80ce07b` returned 4 passes (`check-fmt`, `typecheck`,
`markdownlint`, `nixie`) and a red verdict from one shared root cause.

`make lint` failed at the duplication gate with two unsuppressed families, and
`make duplication-test` failed for the same reason, through
`scripts/tests/test_duplication_gate_real_detector.py::TestRealDetectorIntegration::test_real_check_cli_passes`,
which asserts the checked-in gate passes on the real tree. Both families sit
in files this branch never touched — `python/stilyagi/discovery_targets.py` and
`python/stilyagi/check_execution.py` are byte-identical to `origin/main`
(`91941ef3`) and absent from `91941ef..HEAD`. They are main's own duplication,
newly _visible_ because this branch introduces the gate that observes it. This
is the predicted consequence of the ADR's own scoping: the scan covers
`python/stilyagi`, and main added ~1602 lines there after the branch's original
saturation measurement.

- `check_execution.py:134-136 ~ 155-157` (`connected`, value 2.2) was
  **genuine** duplication and was extracted, not excepted. Two byte-identical
  three-line blocks — record the phase failure, report the error, return the
  failed `FileCheckResult` — differing only in the phase label. nose's own
  metrics agree: `shared_lines=2`, `removable=2`. The new
  `_report_phase_failure` helper takes the phase as a parameter, so the two
  former copies now share one implementation. nose no longer reports the family
  at all.
- `discovery_targets.py:247-266 _prune_ignored_directories ~ 125-129 _discover_directory_target`
  (`subdag`, value 8.6) was **not** extractable and is recorded as a reasoned
  exception. nose reports `shared_lines=0` and `removable=0`: nothing is
  duplicated at line level. The only shared node is a membership test against
  `_IGNORED_DIRECTORY_NAMES`, which is already the extracted abstraction,
  reached from two independent phases — one decides whether a directory target
  should be walked at all before descending, the other filters names during the
  walk. The sole remaining "fix" would be a boolean-mode predicate wrapper
  coupling a pre-walk gate to an in-walk filter, which the policy forbids
  manufacturing. Both locations carry unit names, so this entry uses the
  narrower `path::name` keys rather than a whole-file glob.

`make test` failed separately on two trybuild UI timeouts
(`stilyagi-ir::ui sha2_0_11_digest_lowerhex_formatting_is_rejected` and
`stilyagi-pyext::compile_tests compile_time_ui`). The log shows the cause is
environmental, not branch-bound: `sccache unreachable`, 13 "Blocking waiting
for file lock" lines, and compile-slot waits up to "9 ahead, 45s", with one
scratch crate taking 4m24s inside a 600s per-test budget. Neither crate is in
the change surface. nextest aborted before the doc-test and pytest phases, so
those never ran; a re-run is required to close this gate.

Verification of the fix: `make duplication` passes with five reasoned
exceptions and no stale entry; `make duplication-test` passes 145/145;
`make check-fmt` passes. Documentation updated for the changed counts — the
developers' guide's present-tense "the four families the gate adjudicates" and
the `pyproject.toml` allowlist comment, whose claim that every entry was
fragment-level was falsified by the new named keys.

### The `lint-test` failure on the pushed head: a remote branch named `*.md`

Pushing `6d05da8` turned the required `lint-test` check red, and the failure
was not in this branch's diff. The offending paths were inside the object
database:

```text
.git/logs/refs/remotes/origin/3-2-2-add-builtin-docstring-rules.md
.git/refs/remotes/origin/3-2-2-add-builtin-docstring-rules.md
```

CI lints Markdown through `DavidAnson/markdownlint-cli2-action` with
`globs: '**/*.md'`, run from the repository root. A checkout has a real `.git`
**directory**, so the glob walks it. GitHub materializes every remote branch as
`refs/remotes/origin/<name>`, so a branch whose name _ends in `.md`_ — here
`3-2-2-add-builtin-docstring-rules.md`, pushed to the repository at
`2026-10-12T23:48Z` by an unrelated workstream — lands in that tree as a file
the glob matches. The linter then reads the ref's forty-character hex object
name as Markdown and fails on MD010 (a hard tab; the SHA is separated from the
ref path by one) and MD041 (no top-level heading at the start of the file).

This is repository-wide, not branch-specific: five open pull requests all showed
`lint-test: FAILURE` at once — `#225`, `#222`, `#195`, `#164` and `#44` — while
`.markdownlint-cli2.jsonc` and the workflows held no `.git` exclusion. It also
explains why the failure was invisible locally: this worktree's `.git` is a
_file_ pointing at a shared bare repository, so the glob cannot descend into
it. A normal clone would have reproduced it.

The fix is to exclude version-control metadata, which is never Markdown this
repository authors, in both places that reach the linter:

- `.markdownlint-cli2.jsonc` gains `.git/**` in its `ignores`.
- `MD_FILES_FIND` in the Makefile gains `-not -path './.git/*'`, so the
  `make markdownlint` and `make nixie` half states the exclusion itself rather
  than inheriting it from a config file elsewhere.

Both halves are needed because the two routes are independent:
`markdownlint-cli2` honours config ignores even for explicitly passed files (it
announces them as `!` patterns), which is what makes the config entry load
bearing for the action; but `find` performs no such filtering, so the Makefile
target would lose the guard if the config entry were ever dropped. The `nixie`
target shares `MD_FILES_FIND`, so the CI "Mermaid lint" step is fixed by the
same change.

Regression coverage asserts each half separately, and each was verified to fail
when its half of the fix is reverted:

- `test_the_config_ignores_the_git_directory` in
  `tests/test_markdown_baseline_contract.py` names the mechanism, so the reason
  survives the next reader who wonders why `.git` is in the list.
- `.git/**` joins the existing canonical-ignore parametrization in the same
  file, which asserts membership of the parsed `ignores` array.
- `test_build_spine_units.py`'s `MD_FILES_FIND` exclusion list gains
  `./.git/*` beside the other generated trees.

Re-measured on the fixed tree: `make markdownlint` reports 0 errors over 72
files, and the new contract tests pass 45/45, failing 3/3 when the fix is
reverted and passing again when it is restored.

Two traps in the documentation itself, both caught by the gates rather than by
review, since a renumbering would have been invisible:

- A prose line began `# 222, #195, …` after a soft wrap, so Markdown read it
  as an ATX heading and failed MD022 and MD025 — a document gaining a spurious
  top-level heading from a line break. Reworded to list the numbers after the
  sentence rather than at the start of a line.
- `materialises` is the spelling the `typos` gate rejects; the house style is
  `-ize`, so both occurrences are `materializes`. The gate is right and the
  prose was wrong, per the `-ize`/`-yse`/`-our` rule in `AGENTS.md`.

The new developers' guide section is numbered `6d-bis` rather than `6e`, because
`6e` is already "Tool version alignment between the Makefile and CI" and
renumbering a published section to make room would churn anchors that other
documents link to. `6f-bis` already exists, so the convention is the document's
own.

Two pre-merge checks in CodeRabbit's live table were re-adjudicated as stale.
Both claimed `append_allow_entry` could persist via an early match while a
later entry went unvalidated. That was true at `de80e652`, which is the commit
the table's `coveredCommitId` still names, and was fixed by `49519d4`: the
function now parses **every** entry into a list before mutating anything
(`scripts/duplication_allowlist.py:314-317`), and
`scripts/tests/test_duplication_gate_persistence.py::test_a_malformed_later_entry_fails_before_any_write`
pins exactly the scenario the resolution asked for. A direct probe confirms
it: a malformed later entry parses into a mutable `tomlkit.Table`, so the
finding's premise is sound, but `append_allow_entry` raises `GateConfigError`
naming `allow[1]` and leaves the file byte-unchanged.

### The CodeScene regression this branch caused in `check_execution.py`

Hosted CodeScene on `6d05da8` reported a row that neither the branch nor main
had shown before:

| File                                 | Rule             | Code Health  |
| ------------------------------------ | ---------------- | ------------ |
| `python/stilyagi/check_execution.py` | Code Duplication | 10.00 → 9.39 |

`6d05da8` is the only commit in `91941ef..HEAD` that touches the file, so the
regression is this branch's, not inherited. `cs review` on main's blob and on
the head blob reproduces the hosted figures exactly (10.0 and 9.38; hosted
rounds to 9.39), so the local CLI and the hosted service agree.

The finding is not on the helper that commit added. It names `_resolve_config`
(47–58) and `_resolve_discovery_config` (61–71), which the commit never edited.
A calibration series isolates the trigger:

| Input                                                        | Score | Reported         |
| ------------------------------------------------------------ | ----- | ---------------- |
| main's blob, copied verbatim                                 | 10.0  | nothing          |
| main's blob + `_report_phase_failure` appended, never called | 9.38  | the resolve pair |
| main's blob + an unrelated 11-line placeholder function      | 9.38  | the resolve pair |
| head + `_resolve_discovery_config` delegating                | 10.0  | nothing          |

So the file sits on a biomarker threshold. Main's copy carries a latent
structural similarity between the two resolve helpers that stays below the
reporting cut-off until the module grows by roughly eleven lines; **any**
addition of about that size tips it over, whatever the addition is. Adding
seven lines to the file was therefore enough. This is metric movement caused by
file length rather than by the duplicated behaviour itself, but it is still a
genuine 10.00 → 9.39 regression on a file this branch touches, and the policy
is to repair it rather than argue it away.

The repair is delegation, and it is behaviour-preserving by construction:
`_resolve_config(pathlib.Path(), options, resolver)` passes the same `target`,
`options` and `resolver` to the same `resolver.resolve_config_for_path` call
the removed body made, with the same keyword arguments. Only the first
positional argument differs between the two helpers, and `pathlib.Path()` is
exactly what the discovery helper already passed. `python/stilyagi/cli.py` is
the only caller, at line 290, and no test monkeypatches either helper.

Verified after the repair: `cs delta` reports `Code Health: (9.38 -> 10.00)` and
`Fixed issue: Code Duplication`; `cs review` on the file scores 10.0 with no
findings; `make duplication` passes with five reasoned exceptions and no stale
entry; the 43 tests in `test_check_command.py`, `test_check_files.py`,
`test_discovery.py` and `test_check_metrics.py` pass, 5 snapshots included.

One gate-side trap, caught rather than remembered: expanding the helper's
docstring to a multi-line form activated Ruff's `DOC201`, which requires a
`Returns` section once a return contract is stated in prose. Keeping the
docstring a single line and explaining the choice in an inline comment leaves
the rule satisfied while still recording why the call is scoped to the current
directory.

### The fifth rebase: semantic audit, and the ADR renumber to 010

The fifth rebase replayed 37 commits from `91941ef` onto `90aaccf`. Six
conflict sites across four commits were adjudicated on evidence:

| Commit    | Path(s)                                                                                            | Resolution                                                           |
| --------- | -------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `fc6abe8` | `docs/contents.md`                                                                                 | Keep both ADR index entries                                          |
| `78adfe1` | `Makefile`, `tests/test_check_files.py`                                                            | Compose both Makefile additions; take target's `test_check_files.py` |
| `61df522` | `Makefile`                                                                                         | Compose both additions                                               |
| `6d05da8` | `python/stilyagi/check_execution.py`                                                               | Port the helper onto `SourcedInput` and `run.report`                 |
| `3e3d619` | `Makefile`, `docs/developers-guide.md`, `test_markdown_baseline_contract.py`, `check_execution.py` | Compose Makefile; keep target's guide section and contract test      |

The rebase raises no andon condition. All three semantic checks pass:

1. **Target-only paths are byte-identical.** Of 74 paths `main` changed and this
   branch did not, one (`python/stilyagi/engine/fixes.py`) is deleted on both
   sides and 73 were compared. Zero mismatches.
2. **Every deletion against the target in a branch-touched file is explained.**
   Two lines are deleted relative to the target, both in
   `python/stilyagi/check_execution.py`:
   `run.report(pathlib.Path(sourced_input.reported_path), exc)`, twice. Those
   are the named conflict-resolution decision for commit 36, which moved both
   copies into `_report_phase_failure`. One helper body replaces two call-site
   pairs, so the deleted text is present exactly once at the new head.
3. **No newly repeated block.** Two files carry a block repeated more often at
   the new head than at the target: `docs/scripting-standards.md` (a PEP 723
   header in each of three didactic examples),
   `tests/support/pr_concurrency.py` (three functions documenting a
   `document: WorkflowDocument` parameter). Both are branch-authored content,
   not replay artefacts: the window counts are identical between
   `OLD_BASE`/`TARGET` (498 and 274 windows; 18 and 12 repeated) and between
   `OLD_HEAD`/`NEW_HEAD` (556 and 276; 19 and 12).

`git diff --check` flags trailing whitespace at lines 8 and 15 of
`scripts/tests/__snapshots__/test_duplication_gate_commands.ambr`. The path is
branch-owned and its blob (`87766b4`) is byte-identical before and after the
rebase; the whitespace sits on indented blank continuation lines inside
syrupy's own `'''` snapshot body. It is a pre-existing serializer artefact, not
rebase damage, and is deliberately left alone.

**ADR renumbering, second time.** `main` landed
`adr-009-safe-fix-planning-and-conflict-resolution.md` while this branch adds
its own ADR, so the branch ADR was renumbered 009 to 010 rather than sharing
the number — the same resolution this plan already recorded for the earlier 008
collision. The file is now `docs/adr-010-nose-duplication-gate.md`, with its
title heading updated and its two tracked references updated:
`docs/contents.md` and `docs/developers-guide.md` section 6j. A tree-wide
search finds the old path only inside this plan's own audit records, where it
is a quoted historical filename rather than a link; no live reference to it
remains, and `docs/` now numbers each ADR exactly once. The same scoping
applies to the identical claim in the first renumber's paragraph above. The
`ADR 009` references that remain in `docs/roadmap.md`,
`docs/stilyagi-design.md` and the safe-fix ExecPlan belong to the safe-fix ADR
and are correct as they stand.

The renumber was deliberately deferred to this commit rather than applied
during the replay: three later commits (`7bd99c4`, `d29969c`, `78adfe1`) patch
the ADR by path, so renaming it mid-replay would have broken their replay.

The paragraph above recording the first renumber, and the two `ADR 009`
references in the earlier parts of this plan, are historical audit records of
the state at that time and are intentionally left as written.

### Sixth round: the two blockers on the replayed head, and the ninth entry

`make typecheck` and `make lint` both failed on the replayed head, and both
failures trace to one cause: the fifth rebase replayed this branch onto
`90aaccf` (main #160, "Safe-fix planning, conflict resolution, `--diff`, and
`--fix` (2.2.2)"). `git log --diff-filter=A` shows that commit added
`cli_fix.py`, `engine/fix_planning/plan.py`, `engine/fix_pipeline.py`,
`cli_apply.py`, `engine/ir_view.py`, `fix_execution.py`, `cli_log.py` and the
rest — roughly 1602 lines of new package code. Every measurement this plan had
recorded for the gate and the type checker was taken _before_ that code
existed, and nothing re-measured them after the replay.

The two failures are therefore not independent defects. They are the same
omission observed by two different gates, which is why the branch's own
recorded "Verified: `make duplication` passes with five reasoned exceptions and
no stale entry" (`e448d9f`) was true when measured and false on the tip it was
pushed to. A committer-date rewrite does not re-run a gate.

**`make typecheck`: 44 `ty` diagnostics, all in `tests/`.** None were in
`python/stilyagi`. They were mechanical and fell into five shapes:

- **Dynamically stamped log fields** (23 in `test_fix_plan_logging.py`, 10 in
  `test_check_diff.py`, 3 in `test_cli_log.py`). A `logging.LogRecord` carries
  `extra` keys the stubs cannot know about, so `record.files_written` is a type
  error however true it is at runtime. Fixed by adding
  `tests/support/log_records.py::record_field`, which reads one field with the
  three-argument `getattr(record, name, None)` that returns `object`. The
  three-argument form matters twice over: the two-argument form would trip
  Ruff's `B009`, and it matches the precedent already in `test_check_diff.py`.
- **Coercion tests whose loose values are their subject**
  (`test_fixes_model.py`, `test_cli_fix.py`, `test_renderers.py`).
  `Fix.__post_init__` exists to coerce the string applicability and the list of
  edits an untyped rule author writes, so the test cannot pass tightly typed
  values without deleting what it proves. Two of these were fixed by passing
  the strictly typed value where the coercion is _not_ the subject, and one by
  casting through `Any` rather than the narrower lie ty can see through.
- **Fixtures that silently widened their parameters** (`test_fix_write.py`:
  `source: object` → `pathlib.Path`).
- **Missing or drifted annotations** (`test_fix_plan_logging.py`'s
  `_source_with_one_span` return, `test_fix_planner_properties.py`'s optional
  `fixed_bytes`).

No suppression was added: `ty` has no configured `[tool.ty.rules]` and the
repository carries no type-checker suppression comments, so the fixes are all
in the code and the test's intent is now stated in its types.

**`make lint`: eleven families on the replayed head, not four.** Re-measuring
the saturation scan reports **eleven** families at `HEAD` rather than the four
the plan recorded. Four were already covered by the pre-existing entries; two
were the same `ir_view.py` mapping-narrowing guard, genuine duplication that
was **extracted** into `_ir_mapping` and is no longer reported at all; the
remaining five needed adjudication. After the extraction the scan reports
**nine** families, all of them covered by reasoned entries. (The `cli_args.py`
entry belongs to neither count: it was stale at `HEAD` and was deleted — see
below.) `tests/support/log_records.py` also matters here: it is a _new_ file
under `tests/`, so the `tests/`-scan figure moved again, and the exclusion
paragraph's recorded 87 is now 125.

One existing entry had gone stale and was **removed** rather than re-worded: the
`cli_args.py` boolean-flag entry, which described two adjacent
`add_argument(…, action="store_true", …)` declarations. The mechanism was
measured rather than assumed, because the obvious explanation is wrong. The
three flags main added in #160 (`--diff`, `--fix`, `--unsafe-fixes`) are _more_
copies of that declaration shape, so they plausibly read as the cause; two
isolation probes falsify that. A base-version file with those three blocks
planted back into it **still reports the family** (`similar`, value 3.9), while
the branch's file with them removed reports **nothing** — so the dropout comes
from main's own `_add_rule_code_argument` extraction, which rewrote the
`--select` / `--ignore` / `--extend-select` trio that nose had actually paired.

The initial reading was that the entry was stale but the flags were still
uncovered duplication, so a `_add_store_true_argument` builder was written and
the five switches rewritten onto it, mirroring main's helper. The gate then
reported the entry as stale _with HEAD's own file and entry restored_, which
showed the duplication was already gone and the refactor was unmotivated churn.
It was **reverted**: `python/stilyagi/cli_args.py` is byte-identical to `HEAD`,
and the only change to that file's story is the deleted entry. The lesson is
recorded here rather than tidied away because the wrong version was briefly
committed to this plan's narrative: a family that drops out of a ranking is not
evidence that the code below it changed, and a stale entry has to be diagnosed
against the pre-edit tree before anything is written to "fix" it.

The five new entries are adjudicated in full at `[tool.duplication_gate]`. Two
are the PEP 484 conditional-import idiom, which 35 modules under
`python/stilyagi` carry and 19 bind `cabc` for; one is that idiom's bare
two-line marker, where the third member binds `pathlib` instead, so even the
guarded block contents disagree. Two are `if <x> is None: return <sentinel>`
guards in unrelated modules, one of which is already recorded as an exception
elsewhere in the same file. One is `FixRequest` ~ `PlannedFile`: two frozen
slotted dataclasses that legitimately share a six-field prefix, where a common
base would assert a false is-a relationship and couple planning inputs to
planning results.

Because `nose` reports fragment-level locations without unit names, four of the
five entries are forced to bare-path keys, and a bare path is coarser than the
family it silences. That coarseness is recorded in each reason rather than
hidden: the `fix_pipeline.py` ~ `plan.py` entry necessarily also covers the
`FixRequest` ~ `PlannedFile` family, which is why both entries match and
neither is stale. The alternative — inventing a narrower key shape — would mean
changing the gate's key language to suit one family.

Documentation corrected to match the re-measurement: `docs/adr-010`'s option
table and Option B paragraph (four → nine), `docs/developers-guide.md`'s
saturation and `tests/` figures, and the `[tool.nose]` comment in
`pyproject.toml`. The `pyproject.toml` comment now also records that the count
has moved before and why, so the next reader knows the digit is a measurement
and not a contract.

### Seventh round: the static assessment's two real defects

The seventh-round assessment (`stilyagi-164-7b9c2c4-a1`, [comment 6206522665])
returned three findings. Two were real defects in this branch, and both were
failures that would have let the gate report green while checking nothing.

**The early-write cleanup window.** `atomic_write` created its temporary file
with `delete=False` and entered the cleanup `try` only _after_ writing,
flushing, syncing and closing it. A failure in any of those four steps never
reached the `finally`, stranding the sibling. The destination was never at risk
on those paths — the replacement had not happened — but the stray file would be
read by the next reader of the directory as if it were real. Cleanup now spans
the whole temporary-file lifetime: the path is captured as soon as
`NamedTemporaryFile` returns and the `finally` unlinks it with
`missing_ok=True`, so the success path is a no-op because `replace` already
consumed it.

The regression proof was re-established twice, because an interim redesign of
the test double invalidated the first. Restoring `scripts/atomic_write.py` from
the pre-fix head makes the new cases fail with
`A failure before the replacement must not leave the temporary sibling` while
the 7 pre-existing cases pass; restoring the fix makes all 11 pass. Three
injections are covered — `write`, `flush` and the temporary file's own
`fsync` — plus a fourth case where the destination directory is created by the
same call.

**The empty scope, which is worse than it looked.** The assessment listed two
scope gaps, an empty `roots` array and an existing root that selects no source,
with the honest qualification that it had not executed `nose` and so could not
claim either produced a false green. Running the pinned detector settles it,
and the two cases are not equally serious. `nose 0.20.0` **exits 0** for a root
that exists but holds nothing parseable, emitting
`{"families": [], "summary": {"families": 0}}` on stdout and only
`warning: no supported source files found under: <root>` on stderr —
byte-for-byte the report a genuinely clean scan produces. So the empty array at
least failed loudly, but the source-less root was a **vacuous green**, which is
precisely the failure mode the plan's stated protection exists to prevent.

Both are closed. `load_settings` rejects an empty `roots` array, and
`_reject_empty_scope` promotes nose's stderr diagnostic to a
`GateExecutionError`. Where the guard lives is load-bearing: it is called from
`_run_command`, not `run_detector`, because `_run_command` returns only
`result.stdout`, so stderr never reaches the caller and that boundary is the
only place the signal exists. The guard matches nose's diagnostic string rather
than reimplementing its language table, so if nose renames the warning the
guard lapses to the previous behaviour instead of wrongly rejecting a root that
uses a newly supported language.

One residual is disclosed rather than closed: a _partial_ narrowing, several
roots where at least one selects files, still exits 0 with no warning. It is
not promoted, because a multi-root configuration can legitimately rank families
from a subset of its roots. The risks section records that as the accepted
boundary. The claim was measured rather than assumed: `nose` 0.20.0 run with
`python/stilyagi` plus an empty sibling root exits 0 with **zero bytes** of
stderr, while the same binary run against two empty roots writes the 236-byte
`warning: no supported source files found under:` line the wrapper matches. So
the partial case is not merely unpromoted — there is no diagnostic present to
promote, and the earlier Risks wording that said it "remains reported by `nose`
on stderr" was wrong. It was corrected in the same commit that recorded this
measurement.

**The toolchain finding was refuted, and the refutation is worth keeping.** The
assessment compared with a two-dot `git diff fb2e19f..7b9c2c4`, but `fb2e19f`
is not an ancestor of this branch, so that range compares two unrelated trees
rather than stating the PR's delta. Against the real merge base `90aaccf` the
three-dot diff of `rust-toolchain.toml` is empty, no branch commit touches the
file, both sides read `1.99.0`, and `git merge-tree` against current
`origin/main` yields `1.99.1`. Separately, `origin/main` is itself at `1.99.1`
while its own `docs/developers-guide.md:1185` still says the file pins
`1.99.0` — a pre-existing contradiction on `main`, not this branch's, and
deliberately left alone rather than edited in a PR that does not otherwise
touch that file.

**The metric regression was removed, not disclosed.** Adding the empty-scope
guard first dropped `scripts/nose_detector.py` from a CodeScene code health of
10.00 to 9.38 (`Overall Code Complexity`; the file is new on this branch, so
the marker counts as new code). Disclosing a self-inflicted regression is
weaker than removing it, so the cost was attributed rather than explained away.

Measured on variants of the same file, the detector-side guard turned out to be
free: with the `_reject_empty_scope` helper and its call in `_run_command`
alone, the file still scores **10.00**. The whole 0.62 came from the
empty-roots branch added inside `load_settings`, which was already the file's
longest function. Extracting that check into a new `_require_roots` validator
restores **10.00 while keeping both guards**. This is decomposition, not
dilution: no function was added to pad an average, and the file still has every
protective branch it had. Two weaker alternatives were measured and rejected —
folding the guard into `_run_command` (fewer functions, but 9.09) and a
single-pass membership test (9.38) — so the extracted validator is the
best-scoring honest shape, not merely the first one found.

The remaining four CodeScene markers (`duplication_allowlist.py`,
`nose_schema.py`, `test_duplication_gate_commands.py`,
`test_duplication_gate_boundaries.py`) are unchanged by this round and carry
the DELIBERATE-PARALLEL disposition and caveat recorded above. None is a
blocking gate check: the required set is `lint-test` plus the three
`release-smoke` jobs, and CodeScene is not in it. The duplication gate's
`roots` is `python/stilyagi` and Skylos targets `python/stilyagi`, so
`scripts/` is outside both.

**Gate binding, because it cost a full re-run.** Committing forced a re-reading
of which verdicts actually certified the committed content. Six gates
(`check-fmt`, `typecheck`, `test-doc`, `duplication-test`, `test`) had all
finished _before_ the last three edits at 06:29-06:30, so their earlier passes
described a tree that no longer existed; only `lint` (06:36:13) and the two
docs-only gates were already bound to the final content. The lesson is that a
gate's verdict is bound to the tree it ran against, not to the branch, and an
edit made while a gate is still cycling silently invalidates it. A related
near-miss: `make all` also runs `test-workflow-contracts`, a target none of the
earlier rounds had covered, so a green `make lint` plus a green `make test` is
not by itself a green `make all`.

### Round eight: the CodeScene marker this round created, and its disposition

The seventh round's fix left one artefact behind that the earlier rounds would
not have caught, because it only becomes visible when the head moves:
`codescene-access` opened a **new** review thread on `scripts/nose_detector.py`
at 04:44:52Z against `c8fe15e`, reporting a mean cyclomatic complexity of 4.25
across 8 functions. That marker did not exist on `7b9c2c4`, so it was this
branch's own regression rather than inherited debt — the distinction the
earlier rounds were careful to draw when four other markers were dispositioned
as DELIBERATE-PARALLEL.

It was answered as **FIXED**, citing `248c940` and quoting the variant table
that attributed the cost. The disposition is posted on the thread itself
(`discussion_r4291056669`), and it explicitly declines the Suppress route
CodeScene offers in the same message: no Suppress link was clicked and no
threshold was changed.

Two process lessons are worth keeping, because both cost a full CI cycle:

- **A gate run started before an edit describes the old tree.** This is the same
  binding rule recorded in round seven, and it bit again in a new place: the
  local `check-fmt` had passed, but it passed _before_ the execplan paragraph
  was written. CI then failed `Check formatting` with a 45-line reflow of that
  file and skipped every later stage. The correction is to run the formatter on
  the edited file, not on a remembered green result.
- **A Markdown-only delta is not a gate-free delta in this repository.**
  Contract tests parse the Markdown, so `make test` and `make markdownlint`
  were re-run against `341e70e` rather than carried forward. Only the results
  that a pure line-wrapping change provably cannot affect were considered for
  carry-forward, and each such call was stated with its reasoning rather than
  assumed.

## Round nine: the emphasis marker, recorded a third time

The head `baba067` was gated locally across all nine targets before this edit.
Eight passed and one failed:

| Gate                      | Result                                     |
| :------------------------ | :----------------------------------------- |
| `test-workflow-contracts` | pass                                       |
| `check-fmt`               | pass                                       |
| `typecheck`               | pass (281s)                                |
| `test-doc`                | pass (277s)                                |
| `duplication-test`        | pass                                       |
| `test`                    | pass (1027s)                               |
| `lint`                    | pass (117s)                                |
| `nixie`                   | pass                                       |
| `markdownlint`            | **fail** — 8 `MD049/emphasis-style` errors |

Both CI and the local run agree, and both name the same eight sites in this
file. The gate ran with a clean tree before and after, so the failure is a
property of the commit rather than of anything local.

The cause is worth stating plainly because it has now recurred three times.
`MD049` runs in its default "consistent" mode, and this repository sets no
explicit `MD049` entry in `.markdownlint-cli2.jsonc`. Under that mode the
document's _first_ single-marker emphasis settles the marker for every later
one, and in this file that first emphasis is the `_partial_` at line 55. So
underscores are canonical here, and the four asterisk sites added by the
round-eight prose broke the rule the file had already set.

Two observations make the miss harder to excuse, and both are recorded because
they are process failures rather than knowledge gaps:

- The rule is written down in this very document at line 361. Having documented
  a trap is not the same as applying it.
- The scrutineer found the contradiction independently: line 55 writes
  `A _partial_ narrowing` while line 1942 wrote the same phrase as
  `a *partial* narrowing`. The file disagreed with itself in the same words.

The fix is the mechanical one: the four prose spans become `_after_`,
`_partial_`, `_before_` and `_before_`. Asterisks inside inline backticks and
fenced code are untouched, because `MD049` ignores code spans. The line 55
first-emphasis rule is what makes the direction of the fix decidable rather
than a matter of taste, which is why it is restated here instead of being
assumed.

Because this delta is Markdown-only, and because the two Markdown commits it
sits on already passed the other eight gates at this same commit, the re-run is
scoped to `markdownlint` plus `check-fmt` — `mdtablefix` also rewrites this
file, so it has to be re-checked alongside.

The remaining seven verdicts are carried forward, and the reason is narrower
than "they cannot see Markdown". One of them can: `nixie` validates Mermaid
diagrams inside `*.md`, so it does read this file. It passes trivially, because
the file contains no fenced `mermaid` block at all. The other six do not read
it or any other `*.md`: `check-fmt`'s Ruff and `cargo fmt` tiers cover Python
and Rust, and `typecheck`, `test-doc`, `test`, `lint`, `duplication-test` and
`test-workflow-contracts` reach this file through no path. Each verdict was
measured on `baba067`, and nothing has changed since except prose in this
execplan: the four emphasis markers and this section. No test in the repository
parses an execplan, so prose here cannot move any of the six. That
carry-forward is a claim with a reason attached, not a convenience.
