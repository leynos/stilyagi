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
- [ ] Review remediation round two. The pull request drew a review with eight
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

Before pushing, all seven gates were re-run on the exact tree at `13d2e6e`
with the working tree and `typos.toml` hash unchanged. After pushing, run
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
