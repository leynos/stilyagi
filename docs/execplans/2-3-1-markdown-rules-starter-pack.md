# Implement the starter pack of builtin Markdown rules (2.3.1)

This ExecPlan is a living design and delivery document. Its mandatory living
sections are `Constraints`, `Tolerances (exception triggers)`, `Risks`,
`Progress`, `Surprises & discoveries`, `Decision log`,
`Outcomes & retrospective`, `Conformance basis`, and `Verification plan`.

Status: COMPLETE — implementation, validation, and review reconciliation
finished on 2026-11-06, when the final candidate `c5a4bd83` was reconciled
against the accepted plan. The earlier reconciliations of `4a4d107a` and
`d484dab1` are retained as history; the repair rounds that followed them are
recorded in the Progress section. Milestones M1–M3 were approved on 2026-10-28
and are delivered within the stated constraints and tolerances.

Roadmap item: 2.3.1. Prerequisites 2.1.2 (Markdown IR coverage) and 2.2.1
(`stilyagi check`) are complete. Safe-fix planning, 2.2.2, is also complete.

Working branch: `2-3-1-markdown-rules-starter-pack`, tracking
`origin/2-3-1-markdown-rules-starter-pack`. Planning base:
`765915e5f0ff47899184ed24c9a398c3bc9f2b90`.

## Purpose / big picture

The Markdown check command already extracts documents, but its rule runner
returns no findings. After this work, a maintainer can run `stilyagi check` to
catch heading-level jumps, adjacent repeated words, and explicitly configured
banned terms. Every rule will use IR region targeting and source-backed byte
spans. The rules will share deterministic configuration, suppression,
diagnostics, and fix handling, so later packs can use the same substrate. A
heading-level finding remains manual; the repeated-word rule may propose an
explicitly unsafe removal; banned-term findings have no automatic replacement.
Users can inspect exact rule spans and fix decisions in JSON.

The configuration and exact source examples are:

```toml
[tool.stilyagi.lint]
select = ["MD", "STY", "TERM"]

[tool.stilyagi.rule.TERM001]
terms = ["obviously", "clearly"]
case_sensitive = false
```

```plaintext
$ stilyagi check heading.md --output-format json
... MD001 span {"byte_start":8,"byte_end":18}, severity "error" ...
$ stilyagi check repeat.md --output-format json
... STY001 span {"byte_start":4,"byte_end":7}, severity "warning" ...
$ stilyagi check banned.md --output-format json
... TERM001 span {"byte_start":8,"byte_end":17}, severity "error" ...
```

For the latter two exact offsets, `repeat.md` contains `the the.` at byte zero
and `banned.md` contains `This is obviously wrong.` at byte zero. They produce
warning exit 0 and error exit 1 respectively. The heading example is exactly
`# Start\n### Detail\n` and reports the second full heading node at `[8,18)`
with error exit 1. An invalid `TERM001` option exits 2.

## Constraints

1. Preserve the accepted Rust extraction / Python rules boundary. The Rust
   Markdown extractor owns syntax-aware IR; Python owns built-in rule policy,
   orchestration, diagnostics rendering, and rule configuration.
2. Use the canonical IR and `RegionTarget(syntax, kind, scope_has)` as the
   Markdown targeting boundary. Only Markdown syntax is supported here, and
   every `scope_has` tag must be present. Do not add a parallel parser, re-scan
   source syntax with regular expressions, or make rules depend on spaCy.
3. Every reported rule match has a valid half-open UTF-8 byte span into original
   file bytes. Never treat Python character indices as byte offsets or derive
   edits from line and column values.
4. An edit must pass the existing `engine.fix_planning.admissibility`
   source-backing, bounds, UTF-8-boundary, and source-match checks and the
   existing conflict planner. Do not widen ADR 0009's edit admissibility bound.
5. `MD001` always emits a manual fix with an empty edit list: heading markers
   are not source-backed region text and cannot be edited under the current
   bound. `STY001` edits are unsafe because repeated text can be intentional.
   `TERM001` emits no edit because the rule cannot choose a replacement.
6. Preserve deterministic diagnostics and rule ordering. Apply selected/ignored
   rule policy, per-file ignores, and recognized IR suppressions consistently.
   Operational diagnostics and `fix_errors` remain outside rule filtering.
7. Do not introduce a third-party runtime dependency, network access, model
   download, unapproved public interface, or compatibility shim. Tests may use
   already-authorized dependencies and existing project conventions.
8. Do not mark roadmap 2.3.1 complete in the plan branch. The implementor marks
   the roadmap checkbox only after the approved implementation and its gates
   pass.
9. Do not implement `stilyagi rule CODE` / `stilyagi rules` (2.3.2), config
   inspection or IR dumping (2.2.3), docstring rules, plugin discovery, grammar
   rules, or the broader NLP-backed roadmap.

## Tolerances (exception triggers)

- If implementing the typed rule API requires a change to a ratified external
  contract in RFC 0002, RFC 0003, or ADR 0009, stop and propose the smallest
  document amendment before changing code.
- If the established configuration schema cannot represent the proposed rule
  options or selection semantics without an incompatible format change, stop
  and document options and migration impact.
- If exact suppression-to-region semantics cannot be established from the
  current IR and RFC 0003, stop before rule filtering and propose testable
  alternatives.
- If trustworthy spans cannot be recovered for a candidate match, omit that
  match; do not approximate. If that makes one proposed rule unusable on the
  accepted corpus, stop and revise the starter set.
- If a substantive invariant requires a new Rust proof kernel, public API,
  dependency, or Verus toolchain change, return to this plan for review and
  approval before implementation.
- If a named gate still fails after three focused repair attempts, report its
  full captured log and stop that milestone.
- If new evidence contradicts an upstream requirement or a proposed rule's
  user-visible meaning, update the affected trace and decision before further
  work. Do not silently expand scope.

## Risks

- **Risk:** Python diagnostics currently retain line and column but not a
  first-class byte span. Severity: high; likelihood: high. Mitigation: add the
  optional source span at the internal diagnostic boundary and render it
  explicitly in JSON while preserving existing text and location fields.
  Operational diagnostics use `null` span.
- **Risk:** Region text can contain synthetic segments or decoded text that does
  not map one-to-one to source bytes. Severity: high; likelihood: medium.
  Mitigation: resolve each text-rule match within one verified source-backed
  segment; test markup boundaries, Unicode, CRLF, synthetic segments, and
  source mismatch. A failed mapping suppresses the candidate diagnostic.
- **Risk:** per-file ignore paths may be interpreted against the wrong base
  directory when a file uses nearest config, `extend`, or stdin naming.
  Severity: medium; likelihood: medium. Mitigation: carry the effective config
  provenance in `RuleRunRequest`; match config-relative POSIX target paths
  against the effective config file's parent, falling back to the invocation
  working directory without config; use `--stdin-filename` as the path when
  checking stdin. Reuse the existing config merge and any established path
  matcher; do not add filesystem traversal.
- **Risk:** the existing config parser preserves rule option tables but does
  not yet validate them against rule-specific schemas; selection fields and
  suppressions are parsed but not applied by the empty runner. Severity:
  medium; likelihood: high. Mitigation: reuse `LintConfig`, the existing TOML
  parser and config errors, and implement a narrowly typed builtin config
  validator at the rule boundary. Test invalid config through the command.
- **Risk:** suppression directives cover lintable units, and matching a nested
  prose region more than once could leak or duplicate a suppression. Severity:
  high; likelihood: medium. Mitigation: implement the proposed code-prefix
  state machine against IR directive order and document-order regions; test
  `ignore-next`, file, and range behaviour for each rule before enabling it.
- **Risk:** `segment.node` names the owning region node, not necessarily the
  inline leaf that produced each character. Severity: high; likelihood: high.
  Mitigation: build a document-level index of canonical node kinds and byte
  spans once; exclude matches intersecting inline-code node spans. Never infer
  leaf provenance from `segment.node`.
- **Risk:** per-token rescans of IR nodes could make rules scale with the
  product of region and node counts. Severity: medium; likelihood: medium.
  Mitigation: construct source-backed segment and excluded-node indexes once
  per document, tokenize eligible segments once, and include a real-document
  scaling probe before making performance claims.
- **Risk:** some adjacent repeated words are intentional (`had had` can be
  grammatical). Severity: medium; likelihood: high. Mitigation: emit a warning,
  require exact adjacent tokens, do not autofix by default, and label deletion
  unsafe. Keep language-aware or fuzzy repetition out of this slice.
- **Risk:** case folding can expand or otherwise change character sequences.
  Severity: medium; likelihood: medium. Mitigation: use case folding only to
  compare configured terms, then identify and report the original source text
  without deriving offsets from transformed text.
- **Risk:** snapshot assertions can obscure semantic rule failures. Severity:
  low; likelihood: medium. Mitigation: keep semantic span/fix assertions beside
  any focused output snapshot and normalize only nondeterministic fields.

## Progress

- [x] (2026-10-25) Read roadmap 2.3.1 and confirm prerequisites 2.1.2,
  2.2.1, and safe-fix work 2.2.2 are marked complete.
- [x] (2026-10-25) Inspect design §7.2, RFCs 0002 and 0003, diagnostics,
  config parsing, IR span adapters, and the empty `run_rules` seam.
- [x] (2026-10-25) Research established Markdown linting prior art through
  Firecrawl; record links under References.
- [x] (2026-10-25) Obtain architecture, contracts, reliability, performance,
  and maintainability review; resolve findings in the decisions and obligations
  below.
- Planning delivery: the associated draft pull request records formatting and
  Markdown gate results, the publication commit, and the review entrypoint.
- [x] (2026-10-28) Explicit user approval obtained; implementation may begin.
- [x] (2026-10-28) Stage A contract sweep completed against the candidate at
  `4fa47c3`; every mismatch is recorded under *Surprises & discoveries* and
  reconciled in the *Decision log* before any production edit.
- [x] (2026-10-29) Rebased the branch onto `origin/main` and recorded the WIP
  boundary commit. The range-diff against the pre-rebase series is identical;
  no packaging lock file conflicted.
- [x] (2026-10-29) EP-M1 implemented: typed `RegionTarget`/`RuleMetadata`/
  `RuleContext`/`RuleRunRequest`, the per-document projection with source-span
  verification, policy and suppression consumption, and span-carrying JSON
  rendering.
- [x] (2026-10-30) EP-M2 implemented: `MD001`, `STY001`, and opt-in `TERM001`
  with exact spans, the unsafe suffix edit, single tokenization, and the
  no-spaCy fresh-interpreter probe. Focused suites pass:
  `tests/test_builtin_markdown_rules.py` (30), `tests/test_rule_policy.py` (20),
  `tests/test_rule_properties.py` (2),
  `tests/performance/test_builtin_rule_scaling.py` (5), and
  `tests/test_builtin_rules_no_nlp.py` (1).
- [x] (2026-10-30) EP-M3 behavioural coverage added:
  `features/stilyagi_builtin_markdown_rules.feature` with three scenarios and
  `tests/test_builtin_markdown_rules_bdd.py` (3 passing), driving the real
  builtin pack through `stilyagi check`.
- [x] (2026-10-30) EP-M3 documentation: user's guide rule catalogue, policy,
  and suppression; developer's guide rule-execution map; design §7.2
  starter-pack note;
  [ADR 0012](../adrs/adr-0012-adopt-the-source-backed-builtin-rule-contract.md);
  contents index entry.
- [x] (2026-10-31) Post-rebase remediation. The first full `make test` reached
  `pytest` with 13 failures, all consequences of the new typed runner boundary
  and the newly rendered `span` field: the BDD stubs still took
  `(document, config)`, and one expected JSON payload and its snapshot predated
  `span`. Fixed by rebuilding the stubs around `RuleRunRequest`, rejecting an
  inverted edit span in `classify_edit` instead of aborting the planning pass,
  and regenerating the two snapshots. Full Python suite then reported
  `812 passed`; the doctest lane `116 passed, 3 skipped`;
  `make duplication-test` `154 passed`.
- [x] (2026-10-31) Duplication gate repaired. Five of the seven reported
  families were genuine duplication and were extracted into shared helpers
  (`engine.ir_mapping.string_tuple`, `segment_with_text`, `span_fields`,
  `_bounding_span`, `config.rules.parse_optionless`); the remaining two are
  structural parallels recorded as reasoned `[tool.duplication_gate].allow`
  entries. `make lint` reports the gate passing with 9 allowed exceptions.
- [x] (2026-10-31) Focused suite counts re-measured after the rebase:
  `tests/test_builtin_markdown_rules.py` (30), `tests/test_rule_policy.py` (20),
  `tests/test_rule_properties.py` (2),
  `tests/performance/test_builtin_rule_scaling.py` (5),
  `tests/test_builtin_rules_no_nlp.py` (1), and
  `tests/test_builtin_markdown_rules_bdd.py` (3). These are the counts for the
  candidate of that date; the review repairs below changed several of them, and
  their own entries carry the current figures.
- [x] (2026-10-31) Full sequential gates run against HEAD
  `6296a458950251ff48a807011c0c49d2b2a9ccf1` with all changes staged.
  `make check-fmt`, `make typecheck`, `make lint` (including Skylos and the
  duplication gate), `make markdownlint`, and `make nixie` all passed. The
  `make test` nextest lane reported 355 passed and two timeouts, and stopped
  before the later Python lanes; those lanes were therefore run directly and
  passed (see above).
- [x] (2026-10-31) The two timed-out trybuild tests were re-run on the same
  candidate through libtest, which has no wall-clock cap, and both passed:
  `stilyagi-ir` `sha2_0_11_digest_lowerhex_formatting_is_rejected` in 512 s and
  `stilyagi-pyext` `compile_time_ui` in 1299 s. Their durations exceed
  nextest's 600-second `terminate-after`, which is the sole cause of the
  `make test` failure under compile-admission pressure from other repositories;
  no test failed.
- [x] (2026-10-31) Roadmap 2.3.1 ticked; committed and published.
- [x] (2026-10-31) CodeScene code-health findings cleared. The delta review
  flagged five findings: a lengthened `check_one_file`, a duplicated
  optionless-parser pair and a complexity in `config/rules.py`, and nested
  conditionals in `suppression.py`, `repeated_word.py`, and the property-test
  oracle. Repaired by extraction rather than suppression — `check_one_file` now
  delegates diagnostics collection and planning, `parse_optionless` replaces
  the two parser wrappers, and `_validated_term`,
  `_is_range_event`/`_apply_range_event`, and `_extends_run` give each
  predicate one home. `cs delta` against `435f121` then reported no findings;
  the focused suites (86 tests) and the changed modules' doctests (14) pass.
- [x] (2026-10-31) Review repair 1 — per-document indexes. Line starts are
  validated once per document and each finding is located with one binary
  search; inline-code containment is answered by an `InlineCodeIndex` built
  once from the canonical spans. `RuleContext` no longer wraps
  `RuleRunRequest`, only per-document facts and the rule's own config.
  Operation-count tests in `tests/performance` provision the contract without a
  wall-clock threshold (10 passed).
- [x] (2026-10-31) Review repair 2 — preservation property. The V-3 property
  now splices the rule's production edits and compares the result with an
  independently collapsed paragraph, and a mutation control shifts an edit
  boundary one byte into a UTF-8 continuation byte, requiring
  `fix-error/non-utf8-boundary`. `tests/test_rule_properties.py`: 6 passed.
- [x] (2026-10-31) Review repair 3 — suppression evidence. Handwritten
  witnesses cover a finding-free consumer, a thin first list paragraph, an
  empty item, blockquote nesting, and file-directive position. A generated
  Hypothesis sequence property is checked against a per-code replay oracle that
  folds nothing into intervals; it lives in
  `tests/test_suppression_sequences.py` so both modules stay inside the
  400-line lint limit. `tests/test_rule_policy.py`: 28 passed;
  `tests/test_suppression_sequences.py`: 1 passed (80 examples).
- [x] (2026-10-31) Review repair 4 — CLI scoping. Four fresh-process BDD
  scenarios spawn `python -m stilyagi` and prove the per-file glob is anchored
  at the governing config's directory (including through `extend`),
  `--stdin-filename` resolves against the invocation directory, and both a
  non-matching name and `--isolated` report.
  `tests/test_builtin_markdown_rules_bdd.py`: 7 passed.
- [x] (2026-10-31) No-NLP guard widened: the direct probe blocks `spacy`,
  `en_core_web_sm`, and `spacy_lookups_data`, and a second probe runs the real
  `check` command with a `sitecustomize` blocker that records any attempt in a
  marker file. `tests/test_builtin_rules_no_nlp.py`: 2 passed.
- [x] (2026-10-31) Full-gate repair 1 — type narrowing. A `make typecheck` run
  rejected three repairs that had passed their focused suites: `MD001`'s
  predicate returned a boolean, so the caller could not prove a previous depth
  existed; the pack passed `ir_view.line_index`'s optional result to a helper
  accepting only a sequence; and the generated suppression helper's inferred
  dict type was not assignable to its declared one. The predicate now returns
  the reportable baseline, `_validated_line_starts` bridges the optional index,
  and the helper annotates its two lists. `ty check`: all checks passed;
  `ruff check` and Pylint 4.0.9: clean.
- [x] (2026-10-31) Full-gate repair 2 — code health. The repair commits
  themselves introduced two findings: `pipe_named`/`pipe_named_isolated` were
  structurally identical, and `_spy` took five arguments, which Pylint also
  reported as `R0913`. One piped-check step now appends `--isolated` when a
  preceding Given requests it, and `_spy` takes a `(module, attribute)` pair.
  Focused suites: 84 passed.
- [x] (2026-10-31) Full-gate repair 3 — duplication and wheel snapshot. The
  duplication gate reported two families new to this branch: a two-line
  missing-argument guard repeated in `diagnostics_location.py`, and the
  type-only import prologue whose member set had shifted from `rules/base.py` to
  `rules/builtin/text.py` when `base.py` gained a runtime import.
  `line_column_from_offset` now delegates to
  `line_column_from_validated_starts`, leaving one guard, and the existing
  reasoned entry was updated to the detector's current members rather than
  duplicated. The maturin wheel snapshot also predated `rules/inline_code.py`;
  the module was added to its file list. Duplication gate: passed with 9
  reasoned exceptions; focused suites and the wheel snapshot pass.
- [x] (2026-10-31) Final gate run on `e507547c`. `check-fmt`, `typecheck`,
  `lint`, `markdownlint`, and `nixie` pass. `make test` ran 357 nextest tests:
  355 passed and the two trybuild compile-fail tests timed out at the 600-second
  `terminate-after` while queued for compile slots. Every later lane was run
  separately and passed: pytest 842 passed with 19 snapshots, the doctest lane
  120 passed with 3 skipped, and `make duplication-test` 154 passed. The Rust
  tree is byte-identical to the hosted-green `9667e1ef` head.
- [x] (2026-10-31) Assessment repair 5 — V-2 generated coverage. The hosted
  reassessment of `1838d557` cleared every earlier finding but found the
  generated suppression property still filtered on its own outcome
  (`assume(any(...) and not all(...))`), the generator placed at most one
  directive per unit gap, and the replay advanced a shared unit cursor where
  the resolver binds each directive independently. The filter is gone, the
  generator now draws directives independently of unit starts (including
  several before one unit and none before a following unit), and the replay
  binds each directive to its own next unit. Named witnesses pin an empty
  history, an active/inactive transition, a consumed next unit, two directives
  before one unit, and an orphan directive. Focused module: 2 passed.
- [x] (2026-11-02) Rebase onto `3f0de60d`. `origin/main` advanced four commits
  after the previous rebase, and the pull request reported a conflict. The
  branch replayed 19 commits onto the new base; one conflict, in
  `docs/contents.md`, arose because both sides added an ADR 0011 entry. Main's
  build-standard ADR keeps 0011 and this branch's contract ADR became 0012,
  with its file, heading, and every reference updated. `range-diff` shows the
  other 18 commits unchanged.
- [x] (2026-11-02) Rebase onto `d7adfe47` and final gate run on `633ebded`.
  `origin/main` advanced again while the first post-rebase gate run was in
  flight; the branch replayed 20 commits with no conflicts, and `range-diff`
  shows every commit unchanged. The full sequential gate run on `633ebded`
  passes: `check-fmt`, `typecheck`, `lint` (9 reasoned duplication exceptions),
  `markdownlint`, and `nixie`; `make test` passes in full with 362 of 362
  nextest tests, including both trybuild UI tests, pytest 1008 passed with 19
  snapshots, the doctest lane 120 passed with 3 skipped, and
  `make duplication-test` 154 passed with 4 snapshots. The third hosted
  reassessment confirmed the V-2 repair and found no remaining in-scope
  production defect.
- [x] (2026-11-02) Repair the hosted coverage ratchet and rebase onto
  `58f82d73`. The hosted `lint-test` job failed on the Python coverage ratchet:
  the branch measured 91.66% against a 92.88% baseline with a 1.00-point
  tolerance. The baseline is a maximum ratchet, so it does not fall when main
  itself drops. Focused tests now exercise the malformed-IR tolerance paths in
  the projection and span helpers, the suppression resolver's ignored-directive
  cases, the line-index fallback, and the pack inventory and selection seams.
  Local Python coverage rose from 90.00% to 91.20%, which was not enough to
  restore the hosted margin. `origin/main` then advanced to `58f82d73`; the
  branch replayed 22 commits with no conflicts and `range-diff` shows every
  commit unchanged.
- [x] (2026-11-02) Split the tolerance tests and gate the published head
  `e15c0671`. The new coverage tests pushed two modules past the 400-line
  limit, so the malformed-IR and source-coordinate tolerance cases moved to
  `tests/test_rule_boundary_tolerance.py`; the two originals are now 337 and
  317 lines. The full sequential gate run on `e15c0671` passes: `check-fmt`,
  `typecheck`, `lint` (9 reasoned duplication exceptions), `markdownlint` (77
  files, 0 issues), and `nixie`; `make test` passes with 363 nextest tests,
  pytest 1031 passed with 19 snapshots, the doctest lane 120 passed with 3
  skipped, and `make duplication-test` 154 passed. The head was force-pushed
  with a lease bound to the previous remote head `633ebded`.
- [x] (2026-11-02) Close the hosted coverage shortfall. Hosted `lint-test` on
  `e15c0671` measured 91.69% against the 92.88% maximum baseline, so with the
  1.00-point tolerance the gate required 91.88% and failed by 0.19 points. The
  bridge adapter and the config schema retained coverable error branches that
  no test reached, so `tests/test_extraction_payload_validation.py` now injects
  malformed payloads at the `_extract_bridge_payload` seam and
  `tests/test_config_schema_validation.py` exercises each validator's rejection
  path. Local Python coverage rose from 91.20% to 92.39% (224 missed of 2944
  statements), roughly 0.5 points above the hosted requirement.
- [x] (2026-11-03) Reconcile the formal review on `4486f232`. CodeRabbit
  requested changes with five findings and the Codex review raised one; all six
  were verified against the head and upheld, so each is repaired rather than
  rebutted.
  - `SuppressionPlan.suppresses` scanned every interval and inline directive for
    every finding, giving `O(findings × directives)`. The plan now builds a
    per-code span index (`python/stilyagi/rules/suppression_index.py`) whose
    running maximum of span ends keeps one bisection correct even where spans
    overlap.
  - `_config_relative_path` used `os.path.relpath`, which raises `ValueError`
    when target and anchor are on different Windows drives. The helper moved to
    `python/stilyagi/config/paths.py` as `config_relative_path`, uses
    `relative_to(..., walk_up=True)`, and falls back to the absolute POSIX
    spelling; the move also keeps `check_execution.py` within the 400-line
    limit.
  - The ADR 0012 status paragraph, its "Policy is not a rule concern" driver,
    and the design starter-pack bullet said suppression is decided before rules
    run. `run_rules` executes the rules and only then calls
    `filter_diagnostics`, so the prose now matches the ADR's own requirement and
    the code.
  - Both ADR 0012 links in this plan pointed at `docs/execplans/adrs/`; they now
    use `../adrs/`.
  - The user's guide's `[lint]` example did not name its file, so a reader
    copying it into `pyproject.toml` would configure nothing. It now labels the
    standalone file and shows the `[tool.stilyagi.*]` equivalents.
  - The guide said `span` is `null` only when a finding has no source location.
    Diagnostics mapped from extractor errors carry line and column with no span,
    so the text now keeps those coordinates and distinguishes a missing byte
    span from a missing location.
- [x] (2026-11-03) Clear the first gate run on those review repairs. Three
  gates failed, each on a mechanical consequence of the same work:
  - `mdtablefix` wanted the reworded ADR 0012 status paragraph rewrapped.
  - Interrogate measured 99.9% because the new `raiser` stub and the
    previously masked `_spy.wrapper` nested helper had no docstring. Both now
    carry one-line docstrings and interrogate measures 100.0%.
  - The `maturin` wheel-layout snapshot predated the two new modules. The
    documented refresh command added `stilyagi/config/paths.py` and
    `stilyagi/rules/suppression_index.py` to the captured entry list and
    changed nothing else.
- [x] (2026-11-03) Rebase onto `origin/main` `e5663dfa`. Main had advanced
  three commits past the review head: a dependency bump, a hardened spelling
  baseline that scans every tracked file and prefers `-ize`, and a split of
  oversized modules into focused siblings. The replay used Git's built-in merge
  with `zdiff3`, because Weave is selected only by the global attributes file
  and the repository tracks no `.gitattributes`. Two conflicts, both from
  main's spelling rename meeting branch restructuring, were resolved in favour
  of the branch's structure with main's `-ize` prose: `config/tables.py` keeps
  `normalize_extend_values`, and `diagnostics_location.py` keeps
  `validated_line_starts`. All 27 commits replayed, and `range-diff` against
  `58f82d73..42c1ee3f` reports every replayed commit equal. The rebased tip is
  `95109a8d`, and the spelling gate then required two tracked-text fixes
  (`pyproject.toml`, `rules/policy.py`), committed as `21de1458`.
- [x] (2026-11-03) Re-run the full gate set on the rebased tip. `check-fmt`,
  `typecheck`, `lint`, `markdownlint`, `nixie`, the doctest lane, the pytest
  lane (1061 passed, 19 snapshots), the pytest doctest lane, and
  `make duplication-test` all passed. `make test`'s nextest lane reported 361
  of 363 passing: the two trybuild binaries hit nextest's 600 s
  `terminate-after` while the shared compile-admission queue held 100-370
  foreign crates. Both passed when re-run through libtest, which has no
  per-test wall-clock cap (`stilyagi-ir` `ui` in 413 s, `stilyagi-pyext`
  `compile_tests` in 2944 s). The pytest lane's first attempt likewise errored
  on the `maturin build --release` fixture's 600 s subprocess cap; warming that
  build with the fixture's own `RUSTFLAGS=""` environment let the lane pass in
  full. No gate assertion failed on this tip.
- [x] (2026-11-03) Restore the hosted Python coverage ratchet. The new
  `lint-test` run failed only at `ratchet_coverage.py`: Python measured 91.84%
  against a 92.88% baseline with a 1.00 pp tolerance, so the threshold is
  91.88% and the branch missed it by 0.04 pp. Rust measured 91.07% against
  91.48% and passed. The measurement was reproduced exactly off-branch: a
  sequential `slipcover --branch` run of the same pytest lane reported 1061
  passed and 91.8379% over the cobertura XML, matching CI's 91.84%. The cause
  was structural rather than missing tests: the branch adds many modules, and
  each carries an `if TYPE_CHECKING:` guard whose lines can never execute. The
  guard in all 17 new modules now carries `# pragma: no cover - typing only`,
  the convention `tests/conftest.py` already uses, and
  `tests/test_rule_option_validation.py` covers the untested `config/rules.py`
  rejection branches directly. The re-measured report is 92.13% (17239 of 18712
  lines) after 1066 tests pass, 0.25 pp clear of the threshold. The convention
  and its rationale are recorded in the developer's guide §6g.
- [x] (2026-11-04) Review repair 5 — the three findings from the formal
  CodeRabbit review of `eb217fa2`:
  - The public helpers in `config/tables.py` had summary-only docstrings. All
    seven now carry NumPy-style Parameters/Returns/Examples sections, and the
    two that propagate `InvalidConfigError` from a helper say so in prose
    rather than in a `Raises` section, because ruff correctly rejects a
    `Raises` entry for an exception the function never raises itself.
  - `RuleInterval` and `InlineSuppression` had the same gap. Only
    `RuleInterval` moved, to `rules/suppression_records.py`, because
    `InlineSuppression` annotates a `SourceSpan`, which `suppression.py`
    imports for runtime use and the new record module would need only for
    typing. Neither escape hatch is available: the df12 lint forbids
    `from __future__ import annotations` on the 3.14 baseline, and ruff rejects
    a type-checking-only import of a name an eager annotation evaluates. The
    move leaves `suppression.py` at 383 lines, down from 392, and
    `suppression.py` still re-exports `RuleInterval`, so existing import sites
    and doctests are unchanged.
  - Binding each `ignore-next` directive to the next prose unit was
    `O(directives x units)`. The units are now sorted once per document and one
    `bisect.bisect_left` per directive selects the consumer, so the cost is
    `O(units log units + directives log units)`.
  Focused validation: the changed modules' doctests, `test_suppression_index`,
  `test_suppression_sequences`, `test_rule_policy`,
  `test_rule_option_validation`, and `test_doctest_collection` report 50 passed.

- [x] (2026-11-04) Pre-merge reconciliation. The `CodeRabbit` pre-merge table
  reported one error and four warnings against the review of `eb217fa2`.
  - Unit architecture (error): a target's configuration and its provenance
    were resolved twice, and only the first lookup ran inside the configuration
    phase. The second, in `_rule_request`, ran under the rules phase, so a
    configuration I/O failure from it was reported as a rule-run failure. They
    are now one record. `config.resolve`
    defines `ResolvedTargetConfig`, pairing the effective `StilyagiConfig` with
    the config file the resolver discovered; `cli_config.resolve_target_config`
    returns it, and `check_execution._rule_request` consumes it instead of
    re-running `ConfigResolver.config_file_for_path`. The resolver's discovery
    cache still makes the second lookup cheap, but cheapness was never the
    concern: one target now has one resolution, made inside the phase that
    reports configuration failures. `tests/test_cli_config.py` pins both halves
    of the pair, including the inline-only case where no file governs the
    target.
  - Developer documentation (warning): this entry, the `COMPLETE` status, the
    final-state paragraph in the retrospective, and a new "Configuration
    resolution" subsection in the developer's guide covering the record and the
    `config/rules.py` builtin-table boundary.
  - User-facing documentation (warning): the valid half is fixed and the
    migration-guide half is declined on precedent. The README claimed no rules
    ship, showed `stilyagi check docs/` finding zero, and listed built-in rules
    as unbuilt; all three now describe the shipped rules and show a real
    `STY001` finding. No `v0-2-0` migration guide is added. The style guide
    scopes a migration guide to "a release that changes observable behaviour"
    and to "the previous release to the named release"; `gh release list` is
    empty and the `v0.1.0` tag is not a published release, so neither endpoint
    exists. The sibling plan `3-2-1` reached the same conclusion and withdrew
    its version-specific guide for the same reason. `docs/users-guide.md`
    carries the version-neutral account of the three rules.
  - Domain architecture (warning): no change. The reviewer asked for the IR to
    domain translation to move to an adapter and for `resolve_suppressions` to
    receive typed directives. `stilyagi.engine.rule_view` is the recorded
    façade the rest of the engine imports (ADR-0012, "It remains the façade the
    rest of the engine imports"), and `rules/suppression.py` already consumes
    it. Moving the translation behind a second adapter would give the engine two
    translation boundaries to keep in agreement, which is the coupling the
    façade exists to prevent.
  - Observability (warning): implemented. `engine.rule_projection.py` now
    tallies six fixed anomaly categories (`malformed_node`, `invalid_node_span`,
    `malformed_region`, `malformed_segment`, `invalid_segment_span`,
    `source_mismatch`) and reports them once per document: the counts reach
    `stilyagi_check_projection_anomalies_total` through a new PyO3
    `record_projection_anomaly`, and one aggregated debug line carries the
    counts without IR, segment text, or a path. `project(…,
    should_report=False)` keeps suppression resolution's re-projection from
    counting one document twice. The drop and synthetic-demotion paths are
    unchanged; `tests/test_rule_projection_observability.py` pins both the
    counters and the safe-skip behaviour.
  - Gate evidence for this repair round: `check-fmt`, `markdownlint`, `nixie`,
    `typecheck`, and `lint` passed on the revised tree. `lint` forced one
    further structural change: once the reporting was inlined,
    `engine.rule_projection.py` reached 410 lines against Pylint's 400-line
    `C0302` ceiling, so the fixed anomaly vocabulary and its single reporting
    entry point moved to `engine/projection_anomalies.py` (58 lines). The
    projection imports them and passes its tally, which keeps one home for the
    labels and brings the projection back to 379 lines. `make test`'s nextest
    lane then ran 364 tests with 363 passing; `stilyagi-pyext`
    `compile_tests` hit the 600 s `terminate-after` again while the shared
    compile-admission queue held 46–82 foreign crates. Re-run alone on the
    rebased tree under an 1800 s per-test budget it passed in 1102 s
    (`PASS [1102.099s] stilyagi-pyext::compile_tests compile_time_ui`), so the
    timeout is the already recorded admission-contention artefact rather than a
    behavioural failure. The rerun compiled from cold behind the same queue:
    the test profile took 5 m 14 s to build before the binary ran.
  - `make test` aborts at that nextest failure, so the Python lanes it runs
    afterwards needed running directly. The venv had been recreated without its
    `dev` dependency group, which is why the first attempt reported "No module
    named pytest"; `uv sync --group dev` restored the group and `make build`
    reinstalled the development extension. The main lane then failed one
    snapshot, and the failure was real: the new `engine/projection_anomalies.py`
    ships in the wheel, so `tests/__snapshots__/test_maturin_build.ambr` gained
    that single file-list line and nothing else. With the snapshot accepted the
    main lane passed 1077 tests, the doctest lane passed 135 with 3 skipped, and
    `make duplication-test` passed its 154 helper tests.
  - The `compile_tests` rerun is bounded by a harness limit, not by nextest:
    a background command is stopped after its allotted time, and each restart
    truncates its log, so a lane that needs longer is re-run detached and
    polled. The first long Python run looked stuck at 62 % for that reason, not
    because of a hung test; the same suite finished in 162 s once it was allowed
    to complete.
  - The sequence was re-run once more on the exact tree that was pushed, after
    the doc-comment realignment, the seed-helper extraction and the snapshot
    update: `check-fmt`, `markdownlint` (spelling gate included) and `lint` all
    exited 0. Within `lint`, Interrogate and both Pylint passes reported 100 %
    and 10.00/10, and the duplication gate passed with 9 reasoned exceptions.
- [x] (2026-11-05) Second review round. CodeRabbit's review of `b5e7ba8d`
  posted four inline findings and one outside-diff finding; all five were
  verified against the current source and repaired.
  - `rules/builtin/pack.py`: `run_selected` tokenized the document before the
    rule loop, so a structural-only selection paid for prose tokenization no
    rule consumed. A new `_text_rules_selected` predicate gates the call on a
    selected, enabled textual rule. Table validation is unchanged: every
    recognized builtin table is still parsed before the enabled check, and
    there is no early return. `tests/performance/test_builtin_rule_scaling.py`
    pins both the structural-only and ignored-text-rule cases at zero
    tokenization calls.
  - `docs/developers-guide.md`: the tokenizer description now says it covers
    every source-backed segment outside inline code, and records the new
    selection gate. The Rendering section's clean-run example now matches
    `render_text`: `checked 0 files (0 skipped, 0 unreadable); 0 errors, 0
    warnings`, with the fix clause appended only when a fix was handled.
  - `docs/execplans/2-3-1-markdown-rules-starter-pack.md`: the delivery record
    now names `config.resolve`, where `ResolvedTargetConfig` is defined.
  - `README.md`: the stale "Safe-fix planning, `--fix`, and `--diff`" entry is
    gone from "Designed, not yet built", and the implemented capability is
    listed under "Working today".
  - Unit Architecture pre-merge check: `tests/test_check_pipeline_units.py`
    gains a test that makes `resolve_config_for_path` succeed and
    `config_file_for_path` raise `InvalidConfigError`, then asserts the result
    is a configuration failure, the reporter receives that error, and the rule
    runner is never called.
  - Gate evidence: `check-fmt`, `markdownlint`, `nixie`, `typecheck`, `lint`,
    and `test` all exited 0 on the repaired tree. `test` ran nextest 364/364,
    pytest 1080 passed, the docstring lane 135 passed with 3 skipped, and
    `duplication-test` 154 passed.
- [x] (2026-11-05) Merge `main` at `1e1e1190` into the branch. `main` gained
  one commit, "Adopt the workspace formatter profile (#269)", which reformatted
  the whole Rust workspace. Six files changed on both sides, all in
  `crates/stilyagi-pyext/src/check_metrics/` plus `lib.rs`; five of them
  conflicted in their import blocks.
  - Resolution keeps `main`'s one-item-per-line import formatting and re-adds
    this branch's `PROJECTION_ANOMALIES`, `PROJECTION_ANOMALY_KINDS`, and
    `record_projection_anomaly` imports at their sorted positions. No behaviour
    changed, and `make fmt` left the resolved tree unchanged.
  - The merge also explains the missing hosted CI. GitHub does not schedule
    `pull_request` workflows while a pull request has a merge conflict, because
    it cannot build the `refs/pull/N/merge` ref the workflows run against. The
    branch had been `DIRTY` since `main` advanced, which is why only the
    `pull_request_target` automerge run appeared for `84d9bc71`.
  - Gate evidence on merge commit `27fc732e`: `check-fmt`, `markdownlint`,
    `nixie`, `typecheck`, `lint`, and `test` all exited 0. `test` ran nextest
    364/364, pytest 1080 passed, the docstring lane 135 passed with 3 skipped,
    and `duplication-test` 154 passed.
- [x] (2026-11-05) Reconcile the delivery record with the final candidate
  `d484dab1`. The preceding entries keep their revision-specific evidence; this
  entry records what covers the accepted head.
  - The local gate evidence recorded above belongs to `27fc732e`. The
    ExecPlan-recording commit `d484dab1` was gated separately on its exact tree:
    `check-fmt`, `markdownlint`, `nixie`, `typecheck`, `lint`, and `test` all
    exited 0, with nextest 364/364, pytest 1080 passed, the docstring lane 135
    passed with 3 skipped, and `duplication-test` 154 passed. Those local
    results are author-reported here; the hosted run is the independent check.
  - Hosted [Smoke run
    `41981901016`](https://github.com/leynos/stilyagi/actions/runs/41981901016)
    tested `d484dab1` on attempt 1 and passed `lint-test` together with the
    Ubuntu, macOS, and Windows `release-smoke` jobs. The CodeScene Code Health
    Review passed with code health improved, and the Gecko security review
    passed. `Sourcery review` and `automerge` skip on this repository and are
    not required checks.
- [x] (2026-11-06) Close the two testing rows the organization-level pre-merge
  checklist raised against `d70e498d`, and correct the Rust coverage margin.
  - `tests/test_rule_policy.py` gained
    `test_unselected_ignore_next_binds_only_the_first_unit`, which resolves the
    policy with `STY001` outside `lint.select` and asserts on the plan rather
    than on an empty diagnostic list: the directive still consumes the first
    paragraph and not the second. `LintSetup` now exposes `policy()` for this,
    sharing one `request_for()` builder with `run()`.
  - Adding that case pushed `tests/test_rule_policy.py` past the 400-line
    ceiling Pylint enforces on test modules. The `TestSuppressionPlumbing`
    group moved verbatim to `tests/test_suppression_plumbing.py`: it resolves
    plans from handwritten IR and made no policy-level claim, so the split has
    its own boundary rather than being a line-count shuffle.
  - The hosted CodeScene review then failed that module for Code Duplication
    between its two range tests, which shared a body. They are now one
    parameterized case over a `_ToggleCase` table: four rows state code
    granularity and boundary exclusivity instead of two near-identical bodies.
    Local `cs check` reports 10.00 for the module.
  - `tests/test_suppression_sequences.py` gained
    `test_ignore_next_binds_the_first_unit_and_not_the_second`, which pins the
    resolved plan for a directive followed by two prose units.
  - `tests/test_rule_properties.py` gained a Hypothesis property comparing
    `InlineCodeIndex.contains` with a scan of `SourceSpan.contains` over
    generated span lists that are unordered and may overlap, nest, or repeat.
  - The Rust margin in the accepted head's coverage sentence is `0.83` points,
    not `0.17`: coverage measured 91.31% against the 91.48% baseline, so 0.17
    points were consumed of the 1.00-point tolerance. The Python margin of
    0.22 points was already correct.
- [x] (2026-11-06) Reconcile the organization-level pre-merge checklist against
  `08467de8` and repair the four valid rows.
  - Unit Architecture and Observability shared one cause: `project()` recorded
    a metric and a log line, so a read-only query counted the same recovery
    again every time a caller asked for a different slice of the view.
    `project()` now returns an immutable `anomaly_counts` snapshot on
    `DocumentRegionView` and records nothing. `engine/projection_anomalies.py`
    owns the fixed label vocabulary and the single `report_anomalies` boundary;
    `rules/registry.run_rules` is its only caller and reports once per document
    at `INFO`, naming the reported path. Every `rule_view` helper is now a
    read-only query.
  - `tests/test_rule_projection_observability.py` is rewritten around that
    boundary. It pins the snapshot for each anomaly kind, proves the view
    queries record no metric and no record however often they run, pins one
    aggregated record per document carrying its `path`, and drives
    `cli.run_check(..., verbose=True)` end to end so the record is proven to
    reach a supported command level.
  - Testing (Overall): `tests/test_cli_config.py` gains explicit-`--config`
    provenance cases. The last explicit file governs, and per-file globs anchor
    on the explicit config rather than the working directory, with a control
    document proving the ignore is file-specific.
  - Developer Documentation: the guide claimed a rule receives the effective
    configuration. A rule receives `RuleContext`, which carries its own
    validated options; `RuleRunRequest` is the packet that carries the global
    configuration and the configuration-relative path. The guide now states
    both, and ADR 0012 records the boundary in an `## Amendments` entry rather
    than rewriting the original requirement.
  - User-Facing Documentation was rebutted rather than repaired. The
    documentation style guide requires a migration guide per release that
    changes observable behaviour, and this PR creates no release boundary:
    `pyproject.toml` is still `0.1.0` and the only tag is `v0.1.0`. The new
    `INFO` record is documented in the users' guide under "Projection anomaly
    records" instead.
  - Domain Architecture was rebutted on the same evidence recorded in ADR 0012:
    `rules/suppression.py` reaches raw mappings only through the
    `engine.rule_view.raw_suppressions` façade, and the boundary decision is
    already the ADR's subject.

- [x] (2026-11-06) Gate the repair round and record its evidence.
  - The first pass over `8b9d085d` was red for four reasons. `make check-fmt`
    wanted two files reformatted. Ruff rejected a missing final newline in
    `engine/projection_anomalies.py` and a runtime-only `pathlib` import in
    `tests/test_rule_projection_observability.py`. `ty` rejected `_MIXED_IR` as
    a narrower literal than the `dict[str, object]` parameter it was passed to.
    And `make test` timed out two `trybuild` binaries at their 600 s ceiling
    while the compile-admission queue was more than 100 crate compilations
    deep, with sccache not serving.
  - Formatting, both ruff findings and the `ty` finding were repaired directly.
    The two `trybuild` binaries passed on the next run, in 246 s and 515 s with
    admission healthy throughout, which confirms the timeouts were
    environmental rather than a compile error.
  - The second pass over `19336903` exposed one real defect. The new
    `LintSetup.run` doctest used a plain docstring, so ruff's
    `escape-sequence-in-docstring` fired and the doctest parser split the
    example at the `\n`, failing collection of `tests/support/rule_fixtures.py`.
    The docstring is now raw. `make lint` had stopped at ruff in that pass, so
    every later lint stage had no verdict until the third pass.
  - The third pass over `5e05241d`, on a clean tree, is green on all six gates.
    `make check-fmt` reported 332 files formatted and 76 Markdown files
    unchanged. `make typecheck` passed, with `ty 0.0.74` reporting all checks
    passed. `make lint` passed every sub-stage: ruff, interrogate at 100%,
    pylint and the df12 pass both at 10.00/10, ambrleaks, `cargo doc`, Clippy,
    Whitaker, Skylos, and the duplication gate with 9 reasoned exceptions.
    `make markdownlint` reported 77 files and 0 issues, with the spelling gate
    current. `make nixie` validated every diagram. `make test` passed every
    lane: nextest 364 of 364, `cargo test --doc` green, pytest 1094 passed with
    19 snapshots, `--doctest-modules` 138 passed with 3 pre-existing collector
    skips, and `duplication-test` 154 passed with 4 snapshots.

- [x] (2026-11-06) Reconcile the ExecPlan with the repaired candidate
  `4a4d107a`.
  - The pre-merge reassessment accepted four repairs and two documented
    dispositions, and asked for this plan's own summary to be brought into line
    with them. The status line and the retrospective now name `4a4d107a`, and
    the `d484dab1` record is kept as history for the candidate it describes.
  - Validation stays revision-bound. The six-gate evidence above belongs to
    `5e05241d`, the last tree carrying production changes. The delta from
    `5e05241d` to `4a4d107a` is this Markdown file alone, so the documentation
    gates and the pytest lane were re-run on `4a4d107a` and are recorded as
    author-reported. Hosted Smoke run `42219413204` passed `lint-test` and all
    three `release-smoke` jobs on that head, and the CodeScene and Gecko checks
    passed there too.

- [x] (2026-11-06) Repair the Unit Architecture and property-test rows the
  final approval round raised against `df3c9223`.
  - Unit Architecture: `config_relative_path` is now a pure spelling function
    over an already-resolved target and anchor. It reads neither the working
    directory nor the filesystem, so it cannot fail. The resolving half moved to
    the new `python/stilyagi/check_paths.py`, which `check_execution` calls
    inside the recorded `config` phase. A deleted working directory, an
    unreadable parent, or a symlink loop is therefore reported against the file
    being checked rather than escaping as an unexplained rules-phase error.
  - `tests/test_config_relative_paths.py` is rewritten for the pure signature
    and forbids `cwd`, `resolve`, `expanduser`, `stat`, `exists`, and `is_dir`:
    a spelling that consulted any of them would fail the test.
    `tests/test_check_path_failures.py` injects a missing `Path.cwd()` and a
    looping `Path.resolve()`, and asserts each is reported as a per-file
    operational failure with no rule run.
  - Testing (Property / Proof): `tests/test_rule_properties.py` gained a
    Hypothesis property over generated plain and emphasized segments with
    Unicode prefixes. Its oracle is derived from the generator, so it shares no
    offset arithmetic with the projection; it asserts every finding's byte span
    and edit span and that neither crosses a segment boundary. The fixed case
    `"the *the*\n"` proves that two segment texts which concatenate to a repeat
    report nothing. The independent word-run oracle moved to
    `tests/support/word_run_oracle.py`, and the inline-code containment property
    moved to `tests/test_inline_code_index.py`, keeping every module under the
    plan's 400-line limit.

- [x] (2026-11-06) Gate and record the repair, committed as `c5a4bd83`.
  Gate logs are under `/tmp`, named `<gate>-final-stilyagi-...out`.
  - `make check-fmt` passed: 336 Python files formatted, `cargo fmt` clean,
    76 Markdown files unchanged.
  - `make typecheck` passed: `cargo check --all-targets --all-features` clean
    and `ty 0.0.74` reported all checks passed.
  - `make lint` passed every sub-stage: Ruff, interrogate at 100%, Pylint and
    the df12 pass both at 10.00/10, Ambrleaks, `cargo doc`, Clippy under
    `-D warnings`, Whitaker, Skylos, and the duplication gate with 9 reasoned
    exceptions.
  - `make markdownlint` passed: the spelling gate reported `typos.toml`
    current and `markdownlint-cli2` found 0 issues in 77 files.
  - `make nixie` passed: every diagram validated.
  - `make test` passed: nextest 364 of 364, the doctest lanes, pytest 1098
    passed with 19 snapshots, and the application lane 139 passed with 3
    pre-existing collector skips.
  - `make duplication-test` passed: 154 passed, 4 snapshots.
  - The spelling gate did not regenerate the tracked `typos.toml`.

## Surprises & discoveries

- Observation: the rule runner is an intentionally empty seam, and the model
  and execution pipeline already inject it. Evidence:
  `python/stilyagi/rules/registry.py` and `python/stilyagi/check_execution.py`.
  Impact: implement rules at the existing private runner boundary and update
  callers atomically; no CLI composition redesign is proposed.
- Observation: Python diagnostics do not yet carry the span that RFC 0002
  expects. Evidence: `python/stilyagi/diagnostics.py` and
  `docs/rfcs/rfc-0002-stilyagi-python-rule-api.md` §8. Impact: diagnostics span
  support is an enabling part of this slice, not a property already present.
- Observation: RFC 0003 suppression parsing and IR support exist, but the
  check-rule pipeline does not filter rules through them. Evidence:
  `crates/stilyagi-ir/src/suppression.rs` and
  `docs/rfcs/rfc-0003-stilyagi-cli-contract.md` §9. Impact: implementation must
  finish the consumer side for rules in this slice, subject to confirming the
  unit coverage semantics against the actual IR.
- Observation: IR `segment.node` records the region owner, so it cannot
  identify inline code leaves. Evidence: `region_emission.rs` supplies the
  heading/paragraph owner ID to flattening, while flattening reuses it for
  child segments. Impact: exclude inline code using indexed canonical IR node
  spans; do not assume an extractor change is needed.
- Observation: the current config parser accepts `[tool.stilyagi.rule.CODE]`
  but does not accept a pack-level `[tool.stilyagi.rules.builtin]` table.
  Evidence: allowed top-level keys in `python/stilyagi/config/parse.py`.
  Impact: this slice validates the specific per-rule table it needs and does
  not add pack-level config parsing.
- Observation: third-party guides distinguish heading increment checks and
  configurable repeated-word checks. They inform familiar rule behaviour but do
  not define Stilyagi's frontmatter or fix contracts. Impact: the plan uses
  them as prior art only; no runtime dependency is introduced.
- Observation: `RegionTarget(..., scope_has=...)` from RFC 0002 §5 has no
  implementation. The Rust IR field is `scope: Vec<String>`
  (`crates/stilyagi-ir/src/region.rs`), and `scope_has` appears only in
  `docs/rfcs/rfc-0002-stilyagi-python-rule-api.md`, `docs/developers-guide.md`,
  and this plan. Impact: the typed target is new surface in this slice, not a
  wrapper over an existing descriptor; it must match the serialized `scope`
  list.
- Observation: `run_rules(document, config)` receives neither the original
  source bytes nor the reported path, yet `python/stilyagi/check_execution.py`
  holds both as `sourced_input.source_bytes` and `sourced_input.reported_path`
  at the call site. Impact: the private `RuleRunRequest` from Stage C is
  genuinely required for byte spans and per-file policy, and the call site must
  be updated in the same commit.
- Observation: `engine.ir_view.iter_segments` yields only
  `(span, text, synthetic_reason)`. It discards the region `kind`, `attrs`,
  `scope`, and each segment's owning `node`, although all four are serialized
  by the extractor. Impact: MD001 cannot read heading depth and inline-code
  exclusion cannot intersect node spans until a region-aware view exists.
- Observation: `Diagnostic` carries `line`/`column` but no byte span, and
  `engine.renderers.diagnostic_payload` emits only `location.line` and
  `location.column`. Impact: the plan's promised `{"byte_start", "byte_end"}`
  JSON object is new output, so an existing-snapshot check is required.
- Observation: `Document` (`python/stilyagi/model/document.py`) has `syntax`,
  `regions`, and `ir` only. Impact: rules cannot reach original bytes through
  the document; the request object must carry them explicitly.
- Observation: Python slice clamping makes an out-of-bounds advertised span
  look plausible (`source[b"the the"[0:700]]` is the whole file), so a
  verification that only compared decoded text would accept a malformed span
  whenever the clamp happened to match. Impact: `_slice_matches` rejects
  negative or past-EOF bounds before decoding;
  `tests/test_builtin_markdown_rules.py::TestSourceVerification` covers
  wrong-text, past-EOF, and split-code-point controls.
- Observation: the projection initially lived inside `engine/rule_view.py`,
  which then carried the façade, the node walk, and the region model together.
  Impact: the projection moved to `engine/rule_projection.py`; `rule_view`
  stays a thin façade, which also keeps both files under the 400-line limit and
  lets `rules/base.py` depend on `rules/tokens.py` without an import cycle.
- Observation: `--fix` with only an unsafe finding withholds the edit and still
  exits `0`, because the run wrote nothing and the verification re-lint sees
  the warning that was already allowed to pass. Impact: the CLI BDD scenario
  asserts `0` plus the `--unsafe-fixes` hint, not `1`.
- Observation: JSON `fix_applicable` is `diagnostic.fix is not None`, so it is
  `true` for `MD001`'s manual fix as well as for an applicable edit. Impact:
  consumers that need "an edit would be applied" must read `fix.applicability`;
  the user's guide says so explicitly.
- Observation: the Pylint gateway's 400-line module limit covers `tests/`, so a
  generated property block added to `tests/test_rule_policy.py` raised C0302 at
  516 lines. Impact: the suppression oracle moved to its own module rather than
  a lint exception being recorded.
- Observation: `--stdin-filename` is resolved against the invocation directory
  while per-file globs are anchored at the governing config's directory, so the
  same name is ignored from inside the config tree and reported from outside
  it. Impact: the fresh-process scenarios assert on output text, not exit
  status, because `STY001` is a warning and exits `0` either way.
- Observation: the generated suppression replay advanced one shared unit
  cursor, while `_inline_suppressions` resolves each directive independently,
  so the two algorithms could only agree while the generator placed at most one
  directive per gap. Impact: the replay now binds each directive on its own,
  and the generator draws directives independently of unit starts.
- Observation: the host selects Weave for `*.py` and `*.rs` through a global
  attributes block, not through any tracked `.gitattributes`. Evidence:
  `git check-attr merge -- python/stilyagi/rules/suppression.py` reports
  `weave` while the repository has no `.gitattributes`. Impact: the unattended
  rebase bypassed the driver with `-c core.attributesFile=/dev/null` and
  `zdiff3`, as the merge policy requires for ambient selection.
- Observation: the coverage ratchet counts every line slipcover instruments,
  including an `if TYPE_CHECKING:` guard and the imports under it, which no run
  can execute. Evidence: the baseline report marks those lines as a permanent
  miss, and 45 of the 67 missed lines in the branch's new modules were such
  guard lines. Impact: the guard now carries
  `# pragma: no cover - typing only`, the convention `tests/conftest.py`
  already used, and the developer's guide records why the pragma belongs to the
  guard and not to untested code.

## Decision log

- Decision: propose three bounded rules: `MD001` heading-level increments,
  `STY001` adjacent repeated words, and opt-in `TERM001` configured banned
  terms. Defer list punctuation, weasel words, and wordy phrases. Rationale:
  these exercise structural IR, byte-backed lightweight text matching, policy
  configuration, and safe-fix applicability without NLP. Date/author:
  2026-10-25, planning agent; approved 2026-10-28.
- Decision: first heading may be any level; only a subsequent increase that
  skips one or more levels is reported. A frontmatter title does not imply a
  level-one heading. Suppressed headings still update the previous-heading
  state. Rationale: make the rule deterministic while avoiding hidden policy
  inferred from metadata. Date/author: 2026-10-25; approved 2026-10-28.
- Decision: `STY001` matches maximal exact, case-sensitive runs of Unicode
  alphabetic tokens (`str.isalpha`) within one verified prose segment,
  separated only by ASCII spaces or tabs. It reports the second token's span
  for a maximal repeated run and offers one unsafe edit from the end of the
  first token through the end of the last token. Rationale: identify the
  repeated occurrence while keeping run edits non-overlapping and byte-backed;
  do not conflate repetitions across markup or synthetic text. Date/author:
  2026-10-25; approved 2026-10-28.
- Decision: `TERM001` is disabled unless selected, accepts a typed list of
  alphabetic single-token terms (empty list means no matches; an explicit empty
  string or nonalphabetic term is invalid), compares with Unicode case-folding
  by default (optional exact-case mode), performs no Unicode normalization,
  coalesces duplicate terms under the selected comparison mode, reports the
  original token span, and never fixes. Rationale: users choose policy
  vocabulary; no universal banned list or locale claim is appropriate.
  Date/author: 2026-10-25; approved 2026-10-28.
- Decision: proposed suppression consumption follows RFC 0003 and canonical
  IR. `ignore-file` applies its named prefixes to the whole document regardless
  of directive position; an empty code list applies to all builtin rules.
  Resolve prefixes to the concrete builtin code set first. Range `disable`
  marks each matching code active; `enable` clears each matching concrete code
  (so enabling `STY001` re-enables it inside a disabled `STY` range). Repeated
  disables are idempotent, unmatched enables are no-ops, and an unclosed range
  remains active through EOF. `ignore-next` consumes the next nonempty eligible
  prose region in canonical source order, even if no selected rule targets it
  or it produces no finding. Heading, paragraph, and table-cell regions are
  units; thin list and blockquote containers are skipped, nested paragraphs
  remain their own units. Apply filtering after rule state updates using the
  finding's primary span start. Rationale: stable state independent of rule
  selection. Date/author: 2026-10-25; approved 2026-10-28.
- Review resolution: split application `RuleRunRequest` from per-rule frozen
  `RuleContext[T]`; index source-backed segments and inline-code node spans
  once because segment node IDs denote owners; define explicit severity/exit
  status and suppression sequence semantics; add no-spaCy and scaling probes;
  update empty-runner tests without blind snapshot regeneration. These changes
  bound the approved design and add observable contracts, with no
  implementation started. Date/author: 2026-10-25, design reviewers and
  planning author.
- Decision: per-file globs are matched against config-relative POSIX paths from
  the effective config file parent; `extend` provenance remains available to
  the runner, no-config runs anchor at invocation cwd, and stdin targets use
  `--stdin-filename`. The builtin pack runs only when enabled in `plugins`.
  Rationale: make config scope deterministic without adding path traversal or
  silently activating a disabled pack. Date/author: 2026-10-25, reviewers and
  planning author.
- Decision: no Verus milestone is proposed for this plan. Rationale: the
  selected implementation is Python rule orchestration over existing Rust IR;
  no new Rust theorem-bearing kernel or unbounded contractual algorithm has
  been identified. The range and provenance contracts are exercised with
  focused examples and generated inputs against the actual extractor and fix
  planner. If implementation requires a Rust-owned mapping or suppression
  algorithm whose guarantee must hold for all inputs, stop and add an abstract
  specification, preconditions, postconditions, representation relation, lemma
  sketches, and Verus acceptance command to this plan before proceeding. No
  `assume`, `admit`, or trusted proof body is permitted. Date/author:
  2026-10-25; approved 2026-10-28.
- Stage A reconciliation: `RegionTarget` is new surface in this slice. Its
  `scope_has` field maps onto the serialized IR `scope` list, which the
  extractor already emits, so no RFC amendment and no Rust change is needed;
  the descriptor is added at the Python boundary exactly as RFC 0002 §5
  specifies. Rationale: the ratified contract already names the field and the
  IR already carries the data, so this is an implementation gap rather than a
  contract change. Date/author: 2026-10-28, implementation agent.
- Stage A reconciliation: the original source bytes and the reported path
  travel in the new private `RuleRunRequest` because `run_rules` does not
  receive either today, even though `check_execution` already holds both as
  `sourced_input.source_bytes` and `sourced_input.reported_path`. Rationale:
  widening the existing two-argument seam would still leave rules unable to
  produce byte spans or evaluate per-file globs; a request object supplies them
  without touching the public surface. Date/author: 2026-10-28, implementation
  agent.
- Stage A reconciliation: a region-aware view is added beside
  `engine.ir_view.iter_segments` rather than replacing it, because existing
  callers depend on the current three-field `SegmentView`. The new view reads
  `kind`, `scope`, `attrs`, per-segment `node`, and node spans from the same IR
  envelope. Rationale: preserve the established projection while exposing the
  fields this pack needs, with no extractor change. Date/author: 2026-10-28,
  implementation agent.
- Implementation: the private rule contract is recorded as
  [ADR 0012](../adrs/adr-0012-adopt-the-source-backed-builtin-rule-contract.md),
  covering the per-document projection, span verification, one-time
  tokenization, policy resolution order, and the three shipped rules.
  Rationale: these decisions bind every later builtin and third-party pack, and
  a reader of the design would otherwise have to reconstruct them from code.
  Date/author: 2026-10-30, implementation agent.
- Implementation: span verification rejects out-of-range advertised spans
  before decoding rather than relying on the decoded-text comparison alone.
  Rationale: Python slicing clamps, so a past-EOF span can decode to the
  segment text and pass a naive check. Date/author: 2026-10-30, implementation
  agent.
- Review repair: the preservation property splices the rule's production edits,
  and the suppression property replays directives directly, because a property
  built from the same helper the rule uses, or from the resolver's own folding,
  can satisfy both sides of its own comparison. Rationale: the two checks must
  be able to disagree. Date/author: 2026-10-31, implementation agent.
- Rebase: the branch's contract ADR is renumbered from 0011 to 0012 because
  main landed `adr-0011-pinned-nightly-and-build-standard.md` first. Rationale:
  ADR numbers form one sequence, and two records sharing 0011 would make every
  later reference ambiguous. Date/author: 2026-11-02, implementation agent.

## Outcomes & retrospective

The expert review is complete and its corrections are incorporated; user
approval was granted on 2026-10-28. Implementation of M1–M3 is complete and the
branch is rebased onto `origin/main`. The first published candidate `9667e1ef`
passed every hosted check — `lint-test`, all three `release-smoke` platforms,
CodeScene, and Gecko. Later commits respond to the hosted assessment and carry
the final candidate `e507547c`. On that candidate the deterministic gates
`check-fmt`, `typecheck`, `lint`, `markdownlint`, and `nixie` pass. `make test`
runs 357 nextest tests, of which 355 pass; the two trybuild compile-fail UI
tests exceed their 600-second `terminate-after` while waiting for shared
compiler slots. Every later `make test` lane was run separately and passed:
pytest 842 passed with 19 snapshots, the doctest lane 120 passed with 3
skipped, and `make duplication-test` 154 passed. The Rust tree is
byte-identical to `9667e1ef`, so hosted CI covers those two waiting tests; the
hosted checks for `e507547c` remain the acceptance evidence for the final head.
The hosted code-health review flagged five delta findings on the new code; each
was repaired by extraction rather than suppression, and the delta re-run
against the base reported none.

A later hosted review made four further findings, all in this slice's evidence:
per-finding index rebuilding, a preservation property built from its own
oracle, thin suppression coverage, and an unexercised command path for the
no-NLP claim. Each is repaired and re-measured above. The repair commits
introduced two further code-health findings of their own — a duplicated pair of
step functions and an over-parameterized test spy that Pylint also rejected —
and both were removed by a shared step flag and a paired patch target rather
than by suppression. A third gate cycle then found two duplication families and
a stale wheel snapshot: the repeated guard was removed by delegation, and the
existing reasoned entry and snapshot were updated to the current modules
instead of adding exceptions. The final gate run is bound to the repaired head
in the delivery ledger rather than inferred from an earlier candidate.

A second hosted reassessment then cleared all four findings and found one
acceptance gap in the same evidence: the generated suppression comparison was
filtered on its own outcome and could not express two directives before one
unit. Removing the filter, widening the generator, and aligning the replay with
the resolver's independent binding closed it; named witnesses keep the
now-unfiltered property non-vacuous.

A third hosted reassessment confirmed that repair and found no remaining
in-scope production defect. It also noted that this retrospective still named
`e507547c` as the final candidate, so the current candidate is recorded here.
The branch is rebased onto `d7adfe47` and the published head is `633ebded`. On
that head the deterministic gates `check-fmt`, `typecheck`, `lint`,
`markdownlint`, and `nixie` pass, and `make test` passes in full: 362 of 362
nextest tests, including both trybuild UI tests that timed out on the earlier
candidate; pytest 1008 passed with 19 snapshots; the doctest lane 120 passed
with 3 skipped; and `make duplication-test` 154 passed with 4 snapshots. These
counts come from the local gate run on `633ebded`. Hosted results for that head
are recorded separately once they complete, and the `e507547c` results above
remain the record for that candidate.

The hosted `lint-test` job then failed on the Python coverage ratchet: the
branch measured 91.66% against a 92.88% baseline with a 1.00-point tolerance.
Because the baseline is a maximum ratchet, it does not fall when main itself
drops, so the branch had to rise rather than wait for the baseline to move.
Focused tests for the malformed-IR tolerance paths, the suppression resolver's
ignored-directive cases, the line-index fallback, and the pack inventory and
selection seams raised local Python coverage from 90.00% to 91.20%, which
proved insufficient: hosted `lint-test` on `e15c0671` measured 91.69% and
failed by 0.19 points. A second repair added contract tests for the Rust bridge
payload adapter and for each config-schema validator, raising local coverage to
92.39%. The branch is rebased onto `58f82d73`; `e15c0671` split the tolerance
tests into their own module to keep every file under the 400-line limit. On
that head the deterministic gates `check-fmt`, `typecheck`, `lint`,
`markdownlint`, and `nixie` pass, and `make test` passes with 363 nextest
tests, pytest 1031 passed with 19 snapshots, the doctest lane 120 passed with 3
skipped, and `make duplication-test` 154 passed. Hosted results for `e15c0671`
and the second repair head are recorded in the delivery ledger once they
complete.

The lasting lesson from the rebase is that changing a seam and a rendered
payload in the same slice makes every test that stubs the seam a manual-merge
hazard. The runner signature moved from `(document, config)` to a single
`RuleRunRequest`, and the JSON payload gained `span`; neither change surfaced
until a full `pytest` run, because the git-level rebase was textually clean.
Gates are the only place that class of drift is visible, so a clean rebase is a
starting point, not a verdict.

The second lesson is that a property test can be vacuous without failing. The
preservation property held while both sides of its comparison came from the
test's own helpers, and the suppression truth tables held while no case
consumed a directive on a paragraph that reported nothing. Both repairs made
the oracle independent and the witnesses adversarial; a test's ability to fail
is a property of the test, not of its green result.

The third lesson is that runtime green does not imply type green. Three repairs
passed every focused suite and then failed `ty`: a predicate returned a boolean
where the caller needed a narrowed value, an optional index was handed to a
function taking a sequence, and a helper's inferred dict type was narrower than
its declared one. Folding the value into the predicate's return and naming the
optional-index bridge fixed the first two at their source; neither needed a
suppression.

The fourth lesson is that a gate verdict is bound to the tree it ran on. The
published `9667e1ef` was fully green, yet the commits after it introduced two
duplication families and a stale wheel snapshot; only a fresh run on the
repaired head exposed them. An ancestor's green result is evidence for that
ancestor, not for the tip, so each new head renews its own gate evidence.

The fifth lesson is that an outcome-dependent `assume` hides the shapes a
property cannot express. The generated suppression comparison looked
adversarial, but it skipped every history that suppressed nothing or
everything, and its generator could not place two directives before one unit.
Removing the filter and widening the generator exposed a disagreement between
the replay's shared cursor and the resolver's independent binding; named
witnesses now keep the unfiltered property non-vacuous.

Final state at `79511e35`. The rebased candidate `79511e35` passed every
required hosted job in run `41897978130`: `lint-test` with the Python coverage
ratchet at 92.13% against a 92.88% baseline and Rust at 91.08% against 91.48%
(both inside the 1.00-point tolerance), all three `release-smoke` platforms,
CodeScene, and Gecko. The macOS job first sat unassigned and was cancelled
without running a step; the rerun passed. The deterministic gates ran
sequentially on the same tree with no tracked edit between them. The
reconciliation commit that follows closes the pre-merge table's outstanding
rows; it changes no rule behaviour, and its own gate run is the evidence for
that tip rather than this head's.

Final state at `d484dab1`. Two repair rounds, a replay, and a merge of `main`
followed `79511e35`. The accepted head therefore has its own evidence: the
local gate run recorded in the Progress section for that exact tree, and hosted
Smoke run `41981901016`, which passed `lint-test` and all three `release-smoke`
jobs on the head itself. Coverage on that run measured 92.10% for Python
against a 92.88% baseline and 91.31% for Rust against 91.48%, both inside the
1.00-point tolerance, leaving 0.22 and 0.83 percentage points of margin
respectively. Preserve coverage in any later change.

Final state at `4a4d107a`. A further pre-merge reassessment of `d484dab1`
raised six rows, of which four were repaired. The projection is now read-only
and `run_rules` is the single reporting boundary; the anomaly record is `INFO`
with the reported path; the explicit-`--config` provenance cases closed the
Testing (Overall) row; and the developer's guide and ADR 0012 now distinguish
`RuleRunRequest` from `RuleContext`. The other two rows are accepted
dispositions, not implemented refactors: no version-specific migration guide is
required while no release boundary exists, and the domain-boundary deviations in
`rules/suppression.py` and `rules/builtin/pack.py` remain as ADR 0012 records
them. `4a4d107a` is therefore the final candidate, and `d484dab1` keeps its own
hosted evidence as history.

Local gates are revision-bound. The six-gate run recorded in the Progress
section belongs to `5e05241d`, the last tree carrying production changes. The
only later delta is a Markdown-only ExecPlan edit, and the author-reported
re-run of the documentation-relevant gates, the workflow contracts, and the
pytest lane on `4a4d107a` was green. Hosted evidence for the final head is
Smoke run `42219413204`, which passed `lint-test` and all three `release-smoke`
jobs on `4a4d107a` itself, plus the CodeScene code-health review and the Gecko
security review, both successful on the same head.

Final state at `c5a4bd83`. A further approval round on `4a4d107a` raised two
blocking pre-merge rows, and both were repaired. Unit Architecture: the glob
anchor is now resolved at the check boundary in `stilyagi/check_paths.py`, so a
deleted working directory, an unreadable parent, or a symlink loop is a
per-file operational failure reported in the recorded `config` phase while the
rest of the run continues; `config/paths.py` stays a pure spelling function
that reads no filesystem. `tests/test_check_path_failures.py` covers both
failures and `tests/test_config_relative_paths.py` pins the purity. Testing
(Property / Proof): `tests/test_rule_properties.py` gained a Hypothesis
property that generates alternating plain and emphasized segments over an ASCII
and Unicode vocabulary, and checks every finding and edit span against an
independent byte-level oracle in `tests/support/word_run_oracle.py`, including
that no match crosses the markup between two segments.

The seven-gate local run for `c5a4bd83` is green: `make check-fmt`,
`make typecheck`, `make lint` (interrogate at 100%, pylint and the df12 pass
both 10.00/10, Clippy under `-D warnings`, Whitaker, Skylos, and the
duplication gate with 9 reasoned exceptions), `make markdownlint`, `make nixie`,
`make test` (nextest 364/364, the doctest lanes, pytest 1098 passed with 19
snapshots), and `make duplication-test` (154 passed).

Shipped:

- `MD001` `heading-depth` — error severity, manual fix with no edits, reports
  a depth increase greater than one at the heading node span.
- `STY001` `repeated-word` — warning severity, unsafe suffix removal, reports
  the second token of a maximal adjacent run.
- `TERM001` `banned-term` — error severity, opt-in, no fix, whole-token
  matching under `[rule.TERM001] terms` with optional `case_sensitive`.
- Policy: `lint.select`/`ignore`/`per-file-ignores`, `plugins = []`,
  `ALL`/prefix expansion, and the four suppression directives.
- JSON diagnostics carry `span.byte_start`/`span.byte_end` and the `fix`
  payload.

Deferred by design: a public rule-authoring API, rule metadata commands
(2.3.2), pack-level configuration, locale claims, and any NLP-backed rule.

## Context and orientation

The repository has a Rust Markdown parser and canonical IR under
`crates/stilyagi-markdown/` and `crates/stilyagi-ir/`. The Python package under
`python/stilyagi/` holds the check pipeline, configuration, rule seam, fix
planner, diagnostic model, and renderers. Tests live in `tests/`; Python
behaviour specifications live in `features/`. Start with `docs/contents.md`,
`docs/repository-layout.md`, and `docs/stilyagi-design.md` §§3–5 and 7.2.

The IR is an intermediate representation: a structured document produced by the
extractor for downstream analysis. A region is a lintable prose surface such as
a heading or paragraph. A segment is a piece of region text whose source
mapping is either an original half-open byte span or a synthetic insertion.
Text matches and edits require byte-faithful segments; structural heading
findings use canonical node spans without making those spans editable. A rule
target is a typed descriptor that limits the region kinds/scopes a rule may
inspect. A policy is the project's configured choice of which rule codes are
active and what values they use.

The existing `engine.ir_view.SourceSpan` is a Python typed view of byte ranges;
the existing `iter_segments`, `segment_for_span`, and fix admissibility checks
are the starting point. The document model also has compatibility placeholder
regions, so rule matching must prefer validated canonical IR rather than
silently inventing source provenance from placeholder text.

## Conformance basis

- `docs/roadmap.md`, 2.3.1: immediate non-NLP builtins, reuse of targeting and
  source-backed diagnostic substrate, useful first documentation linting.
- `docs/roadmap.md`, 2.1.2: complete Markdown structures and source-map IR.
- `docs/roadmap.md`, 2.2.1–2.2.2: Markdown check, deterministic diagnostics,
  conservative source-backed edits and conflict handling.
- `docs/roadmap.md`, 2.2.2 lines 188–191: heading-depth fix is manual because
  heading markers are outside admissible source-backed text.
- `docs/stilyagi-design.md`, §§3–5 and 7.2: Python rule layer, typed targets,
  capabilities, deterministic execution, source-faithful findings.
- `docs/rfcs/rfc-0002-stilyagi-python-rule-api.md`, §§4–12: rule declaration,
  `RegionTarget`, hook scheduling, diagnostic/fix shape, options and prefixes.
- `docs/rfcs/rfc-0003-stilyagi-cli-contract.md`, §§8–12: configuration,
  suppression, output, and exit-code contract.
- `docs/adrs/adr-0009-safe-fix-planning-and-conflict-resolution.md`: edit
  admissibility, overlap policy, refusal channel, byte fidelity, verification
  re-lint.
- All repository references above are pinned to planning base
  `765915e5f0ff47899184ed24c9a398c3bc9f2b90`. No separate terms-of-reference or
  technical-design revision for this roadmap item exists; the design document
  and RFCs above are the upstream contract. Do not invent one.

Trace links:

```plaintext
2.3.1 rule value -> EP-M2 -> named rule tests + CLI BDD scenarios
2.3.1 targeting and diagnostic substrate -> EP-M1 -> source-span properties + JSON contract tests
2.2.2 safe-fix admissibility -> EP-M2 -> mutation/no-mutation and re-lint scenarios
RFC 0003 suppression/configuration -> EP-M1/M2 -> TOML and directive precedence tests
```

## Verification plan

### Abstract model and obligations

For one original byte string `S`, canonical regions form an ordered sequence
`R`. Each region has a kind and ordered segments. A segment is source-backed
only when its advertised byte slice decodes to exactly its segment text; a
synthetic segment has no source interval. A rule policy `P` selects codes by
prefix, then ignores matching codes and applies per-file and IR suppression.
Per-file glob keys are config-relative POSIX paths, anchored at the effective
config file's parent after the existing `extend` resolution. If no config is
found, use invocation working directory; for stdin, use `--stdin-filename`.
Match paths lexically without new filesystem traversal. The builtin pack is
inactive when omitted from `plugins`. For each enabled rule, its emitted
findings are deterministic functions of `(S, R, P)`. A finding span `[a,b)` is
valid only when `0 <= a <= b <= len(S)`, both offsets are UTF-8 boundaries, and
the span has canonical provenance. For text findings this means containment in
one verified source-backed segment; for structural heading findings it means
the current heading node span. Any attached edit must independently pass the
existing admissibility and conflict planner. This model is independent of the
proposed Python class layout.

The proof sketch precedes the implementation shape. Candidate semantic claims
are hypotheses to pressure-test; implementation evidence may refine or remove
them. No solver proof is presently warranted because no new Rust pure kernel or
unbounded theorem has been identified.

- **V-1 Source representation.** Text findings (`STY001`, `TERM001`)
  scan only one canonical segment advertising byte span `[s,e)` and text `T`.
  For Python character indices `i,j` in that segment, map to original byte
  offsets `a = s + len(T[:i].encode("utf-8"))` and
  `b = s + len(T[:j].encode("utf-8"))`; a precomputed UTF-8 prefix table may
  avoid quadratic work. Never use `i,j` directly as byte offsets. The result
  must be contained in `[s,e)`, lie on UTF-8 boundaries, and its original
  source slice must decode to the expected matched token. Structural `MD001`
  instead uses the canonical heading node's own source span, even when its
  content is empty, code-only, or contains synthetic text; that broad
  diagnostic span never makes the heading marker editable. Representation
  relation: converted Python byte offsets address the same original byte buffer
  as Rust IR offsets; normalized comparison strings never supply offsets.
- **V-2 Rule targeting and order.** `RegionTarget` has `syntax`, `kind`, and
  `scope_has`; all required `scope_has` tags must be present. For fixed IR and
  effective config, only declared targets execute, each selected code executes
  once in stable code order, and region visitation follows canonical document
  order. Prefix selection/ignore precedence, per-file exclusions, and
  suppressions remove findings without changing rule state needed for later
  findings. Suppression semantics: `ignore-file` applies to the entire document
  regardless of directive position. Resolve prefixes against builtin codes;
  range directives toggle individual concrete codes (so `disable STY` followed
  by `enable STY001` leaves sibling STY rules disabled). Repeated disables are
  idempotent, unmatched enables are no-ops, unclosed disables last to EOF,
  empty file-ignore codes mean all builtins. `ignore-next` consumes the next
  nonempty heading, paragraph, or table-cell region in source order regardless
  of selection or whether it emits a finding; thin list/blockquote containers
  are skipped and nested paragraphs remain distinct units. Blanket inline
  suppression remains forbidden. Evaluate stateful rules fully, then filter
  findings whose primary span start is suppressed.
- **V-3 Repetition edit preservation.** For an exact repeated run whose bytes
  are all in one verified segment, the diagnostic spans only the second token
  in that maximal run. The unsafe edit begins at the first token's byte end and
  ends at the last token's byte end. Applying it preserves every byte outside
  that interval and does not split a UTF-8 code point. Distinct maximal runs
  produce disjoint edits.
- **V-4 Fix safety integration.** Rule output cannot bypass the existing
  admissibility, overlap rejection, file-atomic write, or verification re-lint.
  Manual and absent fixes never mutate. Unsafe repetition mutates only when the
  caller explicitly requests unsafe fixes.
- **V-5 Renderer contract.** JSON exposes the original byte span with current
  1-based line and byte-column fields; text keeps its established visible
  format. Existing operational diagnostics serialize `span: null` and remain
  distinguishable from source-backed rule findings. `MD001` is error severity
  and exits 1; `STY001` is warning severity and exits 0; `TERM001` is error
  severity and exits 1; invalid rule options use the existing config-error path
  and exit 2. After a successful mutation, re-lint output determines the final
  status.

### Methods, artefacts, and non-vacuity

- **V-1:** `pytest` examples against the real extractor for ASCII, multibyte
  text before the match, CRLF, inline code/link markup, synthetic soft breaks,
  frontmatter, malformed/mismatched spans, and out-of-bounds spans. Add a
  Hypothesis property over generated Unicode text and segment boundaries. An
  independent oracle decodes the original source slice and compares it to the
  rule's expected token without calling the production offset-mapping helper;
  every output is contained and both ends are UTF-8 boundaries. Artefacts:
  `tests/test_builtin_markdown_rules.py`, `tests/test_diagnostics_location.py`,
  and targeted IR corpus tests in `crates/stilyagi-markdown/src/tests.rs` only
  if a Rust contract is changed. Run focused `uv run --group dev pytest ...`
  and the Rust test command through the established project target.
  Non-vacuity: include ASCII and multibyte witnesses, each skipped syntax
  class, and a negative mutant moving a match start to a UTF-8 continuation
  byte in a multibyte-prefixed fixture; the independent source-slice assertion
  must reject it. No filtering may discard more than documented unsupported
  segments.
- **V-2:** parameterized pytest truth tables for target kind, selected prefix,
  ignored prefix, config-relative per-file glob, stdin filename, config extend,
  and plugin enablement. Add a Hypothesis generated sequence property over
  arbitrary valid `disable`, `enable`, and `ignore-next` sequences, checked
  against an independent simple per-code/set and region-index oracle. Include
  prefix overlap (`disable STY`, `enable STY001`), file-ignore position
  independence, and a clean paragraph consuming `ignore-next`. Use
  deterministic expected diagnostic order and ensure a heading ignored for
  reporting still influences the next heading depth. Confirm `ignore-next`
  region advancement for thin containers and nested paragraphs against Stage A
  evidence. Artefacts: `tests/test_rule_policy.py`,
  `tests/test_suppression_sequences.py` (the generated half, kept separate to
  respect the 400-line module limit), `tests/test_builtin_markdown_rules.py`,
  plus `features/stilyagi_builtin_markdown_rules.feature` and its pytest-bdd
  steps. Use `tests/support/subprocess_env.py::python_module_environment` and
  the existing BDD binding/step patterns for fresh-process CLI checks.
  Non-vacuity: each truth-table row has a positive match witness; generated
  sequences must reach both active and inactive states and consume a next-unit
  directive on a finding-free region. The independent oracle is run over
  generated sequences with no filtering. Negative controls reverse
  select/ignore, prefix overlap, or suppression and must change findings.
- **V-3:** Hypothesis generates Unicode tokens and separator runs. The
  independent oracle uses bytes: after applying one proposed edit, bytes before
  and after its interval are identical, the diagnostic spans only the second
  original token, and the decoded output contains one token for each maximal
  repeated run. Named cases cover `the the`, three-token runs, punctuation,
  newline separation, case changes, and markup/synthetic boundaries. Mutation
  control shifts an edit boundary into a UTF-8 continuation byte and must be
  rejected. Artefacts: `tests/test_builtin_markdown_rules.py` and, if the
  independent relation warrants it, `tests/test_rule_properties.py`.
- **V-4:** named unit tests exercise real `plan_file_fixes` and execution for
  default `--fix`, opt-in `--unsafe-fixes`, `--diff`, two disjoint runs, and a
  conflict. A pytest-bdd scenario verifies a real CLI file is unchanged under
  default fixes, changed only after unsafe opt-in, and clean on verification
  re-lint. Reuse existing tests in `tests/test_fix_command_bdd.py` and
  `features/stilyagi_fix_command.feature`; do not create a parallel fix
  harness. Non-vacuity: assert exact bytes before and after and include a
  manual heading with a visible finding but no changed bytes.
- **V-5:** direct renderer contract tests and focused Syrupy snapshots for the
  required text, JSON, and fix-output variants. Snapshot normalized paths and
  stable diagnostic/fix fields; pair every snapshot with semantic assertions
  for exact span, location, severity, fix applicability, and null span for an
  operational diagnostic. Include a negative control with an off-by-one span
  that changes the expected output.

### Formal verification decision

No Verus milestone is included for the proposed design. The new behaviour is
rule orchestration and string matching in Python over Rust-produced IR; the
existing Rust parser and IR span invariants are already checked by their
repository tests. V-1 and V-3 state substantial invariants, so they receive
property tests with independent byte-level oracles and negative controls, not
just examples or snapshots. V-2 includes a finite configuration truth table
plus arbitrary suppression event sequences, checked by Hypothesis against an
independent state oracle. Prefix expansion is derived from the concrete builtin
code inventory, so `disable STY` followed by `enable STY001` has explicit
semantics. V-4 is an integration contract exercised through the existing
planner and real CLI. V-5 is a serialization contract and is tested at its
renderer boundary.

If implementation reveals a Rust-owned conversion algorithm or introduces
contractual Rust logic, pause and sketch its abstract input/output,
preconditions, postconditions, invariant, representation relation, and
candidate semantic lemmas before changing that design. Select Verus only if the
guarantee must hold over an unbounded domain and the kernel can be connected to
production code. Then name the actual project proof command and proof artefact
as a plan amendment. Do not create a mirrored, disconnected proof, rely on
unsatisfiable premises, or use `assume`, `admit`, or trusted external bodies.

### Semantic claims to pressure-test

The source mapping claim is that encoding the prefix before a token and the
prefix through it gives ordered UTF-8 boundaries, and slicing between them
recovers that original token. Preconditions include valid UTF-8 and exact
segment/source equality; normalized or synthetic text cannot satisfy this
representation relation. Generated tests compare original source slices with
independently constructed expected tokens, rather than calling the mapping
helper twice.

The policy claim is that folding a fixed sequence of directive events over a
per-code boolean state produces one suppression decision at each source
position. Resolving `ignore-next` before rule selection makes selection changes
unable to move its target. Generated event histories and an independent direct
interpreter test this claim; finite examples alone cannot establish it.

The edit claim is a frame property: bytes outside the chosen suffix remain
identical. This is already the existing planner/splice contract, so this slice
verifies that new rule edits meet its premises. It does not replace or claim to
prove the planner. These are candidate semantic lemmas for a future proof if
that boundary changes, not theorem statements assumed by executable code.

### External assumptions

The plan assumes UTF-8 source decoding, the documented half-open UTF-8 byte
span contract in `crates/stilyagi-ir/`, the Markdown extractor's canonical
region order, and the fix planner's documented refusal semantics. These are
third-party or existing-project interfaces, not re-proved here. Exercise the
real bridge and planner at integration boundaries. Firecrawl references below
inform familiar rule semantics only; their behaviour is not a runtime
dependency or correctness oracle.

## Plan of work

### Stage A — confirm contracts before code

Inspect `docs/stilyagi-design.md` §§3–5 and 7.2, RFC 0002, RFC 0003, ADR 0009,
`python/stilyagi/rules/registry.py`, `python/stilyagi/engine/ir_view.py`,
`python/stilyagi/diagnostics.py`, `python/stilyagi/config/`, and the existing
fix planner and CLI tests. Verify where canonical IR contains region kind,
scope, attributes, segments, suppressions, and source line index. Confirm the
actual suppression target/unit algorithm and configuration origin behaviour.
Search for equivalent span and policy helpers before creating any abstraction.

Write the BDD scenario and the smallest rule tests first. Any mismatch between
the actual IR/config contract and the proposal returns to this plan's decision
log for reconciliation. Implementation proceeds under the approved plan.

### Stage B — source mapping and policy red tests

Add failing tests for a source-span diagnostic, exact JSON serialization,
selection precedence, per-file ignore, malformed option errors, and suppression
coverage. Add behaviour scenarios for `stilyagi check` with a heading jump, a
repeated word, configured banned vocabulary, and configuration that selects or
suppresses each result. The runner must be exercised through its existing
injection point and the CLI.

Before changing production code, capture the expected red failure for each new
contract. If a BDD scenario cannot fail for the expected reason because another
pipeline failure occurs first, repair the test setup rather than counting it as
red evidence. Include focused Syrupy snapshots for stable text, JSON, and fix
output variants, paired with direct contract assertions.

### Stage C — typed rule boundary and source-backed diagnostics

Build the smallest API needed by these rules: an immutable private
`RuleRunRequest` carrying the global `StilyagiConfig`, config provenance,
source bytes, reported path, and extracted document; a typed `RegionTarget`;
rule metadata and per-rule frozen config; and a canonical-IR region view. A
rule hook receives only a frozen `RuleContext[T]` with validated rule-specific
config and read-only document/source facts. Rule code must not inspect global
raw TOML mappings or filesystem/config adapters. Reuse config parsing and
existing selection logic where it exists; validate only the option fields this
pack consumes. Confirm the search found no equivalent abstraction before adding
one, and record its intended reuse scope in the relevant architecture or
developer documentation.

Keep domain objects free of filesystem or renderer dependencies. The driving
adapter is the check runner; extraction, config resolution, and source reading
remain application collaborators. Rules do not read files, resolve config,
render output, or call other rules. Update `RuleRunner` and all real and fake
callers together, including verification re-lint. Use the existing explicit
dependency-injection helpers for subprocess tests and keep no-op runners
explicit in tests for unrelated check behaviour.

While building the per-document region view, create source-backed segment and
excluded-inline-node indexes once. `IrSegment.node` is the owning region node;
exclude inline code by intersecting candidate source spans with canonical IR
node spans whose kind is `inlineCode`. Tokenize each eligible segment once. Add
`tests/performance/test_builtin_rule_scaling.py` with 10, 100, and 1,000
paragraph inputs. Assert source/node indexes are built once per document and
each eligible segment is tokenized once; also record elapsed times on the
repository corpus and generated large document as informational evidence only;
shared-host timing is not a pass/fail threshold.

Move the existing typed `SourceSpan` from `engine/ir_view.py` to
`python/stilyagi/model/source.py`, so diagnostics and rules do not depend on
the engine for their source-coordinate type. Update imports atomically; this is
a private pre-release interface and needs no compatibility alias. Add optional
span to diagnostics, map span start to existing byte-based line/column,
serialize byte offsets in JSON, and preserve text renderer output.
Malformed/missing span never fabricates a rule finding.

### Stage D — builtin rules and fix integration

Implement deterministic builtins in `python/stilyagi/rules/builtin/`:

- `MD001` (`heading-depth`): compare successive heading `attrs["depth"]`;
  report only jumps greater than one. First heading may have any depth. Emit a
  manual fix with no edits. Headings update state even when their diagnostic is
  suppressed.
- `STY001` (`repeated-word`): find maximal adjacent repeated Unicode
  alphabetic tokens within a single source-backed region segment, matching
  exact spelling, with only ASCII spaces or tabs between tokens. Emit one
  warning and unsafe suffix-removal edit per maximal run. Do not join matches
  across markup, region, newline, or synthetic boundaries.
- `TERM001` (`banned-term`): inspect explicitly configured single-word terms
  only. Default the comparison to Unicode case-insensitive matching, with a
  narrow typed exact-case option. It is opt-in and has no fix.

Use stable deterministic metadata and the documented code prefix scheme.
Declare structural capability and explicit region targets; no NLP capability or
locale claim. Ensure malformed term options become a normal configuration error
with path/key context and the established exit status. Apply config selection
and ignore precedence, per-file ignores, and IR suppressions only after
validating their exact contract. Expand prefixes against the enabled builtin
code inventory. Apply per-file glob patterns to POSIX paths relative to the
effective config file's parent; without config, anchor at invocation cwd; for
stdin use `--stdin-filename`. Preserve config `extend` merge provenance. An
empty `plugins` list disables builtin execution. Preserve IR extraction
diagnostics and fix refusal reports. Route only valid unsafe edits through the
existing planner. No new runtime dependency.

### Stage E — documentation, review, and final gates

Update the relevant design or RFC text if the approved API, span
representation, suppression behaviour, or configuration schema is clarified
substantively. Add user-facing rule codes/options and the `--unsafe-fixes`
consequence to `docs/users-guide.md`; document internal rule-target/config
reuse in the relevant architecture document and `docs/developers-guide.md`;
update `docs/contents.md` for added docs. Record a major hard-to-reverse
contract as an ADR and link it from the design doc. Follow the documentation
style guide.

At M2, update existing tests whose real `stilyagi check` expectations assumed
an empty runner. Review snapshot diffs semantically; do not accept blanket
snapshot regeneration. Add a fresh-process CLI guard that fails if Stilyagi
imports spaCy or its model packages, and runs a real built-in check. At M3,
expand the dedicated CLI BDD scenarios and user/developer documentation.

At each validated milestone, review adjacent code for domain/adapters
separation, duplicated helpers, complexity, file size, and test independence.
Separate a necessary refactor into a later atomic commit only if it is not
needed to satisfy the current contract. Run format, typecheck, lint, and test
gates sequentially for each major plateau using the repository's designated
`scrutineer` gate runner. Capture each log and inspect failures before fixing.

The implementor may mark roadmap 2.3.1 done only after M3 acceptance and all
required gates pass. This planning branch leaves the checkbox unchanged.

A fresh-process test in M2 uses `python_module_environment` from
`tests/support/subprocess_env.py` to run `python -m stilyagi check` with an
import blocker for `spacy`, `en_core_web_sm`, and `spacy_lookups_data`; a
successful real check proves that the starter pack does not import or download
NLP components. The same milestone updates existing tests that previously
asserted the empty runner result, reviewing each snapshot semantically.

## Milestones and plateaus

### EP-M1 — typed rule boundary and policy contracts

Outcome: rule code can receive validated canonical regions, immutable source
bytes, path and effective config; diagnostics can preserve source byte spans;
rule selection and suppression tests pass. Requirements: RFC 0002 rule
contract, RFC 0003 config/suppression behaviour, source-backed diagnostics.

Acceptance evidence: failing-then-passing unit tests for span rendering and
policy truth table; property obligations V-1/V-2; config error scenario exits 2
through ordinary configuration handling; fresh-process runner excludes NLP
imports; a focused JSON assertion includes exact byte span and current
line/column. Run `make fmt`, `make check-fmt`, `make typecheck`, `make lint`,
and `make test` sequentially.

Conformance check: policy and spans trace to the RFCs; Python domain logic
receives IR through the application boundary; no unapproved public API,
dependency, or persisted format; all policy test classes have witnesses.

Recovery: revert the latest milestone commit and rerun the last passing gates;
no migration is needed for the private pre-release rule API. Remaining gaps: no
user rules until M2. Compatibility decision: none.

### EP-M2 — three deterministic builtins and planner behaviour

Outcome: `MD001`, `STY001`, and opt-in `TERM001` return ordered diagnostics
with documented spans and fix applicability; policy exclusions work. `MD001` and
`TERM001` errors exit 1; `STY001` warnings exit 0. Requirements: roadmap
2.3.1, ADR 0009, V-1–V-4.

Acceptance evidence: named/parameterized unit tests for each rule, Hypothesis
properties for source offsets and repeated-run byte preservation, one-time IR
indexes and single tokenization per eligible segment, and
`tests/performance/test_builtin_rule_scaling.py` at 10, 100, and 1,000
paragraphs, with operation counts as the gate and timing informational on the
shared host. Actual planner tests prove default safe `--fix` leaves repeated
words untouched and unsafe opt-in edits only the repeated suffix. Heading depth
remains reported and unchanged. Every substantive generated invariant has an
independent oracle, a valid witness, and a negative control. Run all five
project gates sequentially as in M1.

Conformance check: matches obey region policy; all edits remain in verified
segments; conflicts still abort file atomically; heading fix is manual; scope
has not expanded to later rules or plugins. Recovery: revert the builtin commit
while retaining the passing M1 boundary. Remaining gaps: full CLI BDD and guide
integration in M3. Compatibility decision: none.

### EP-M3 — real check-command workflow and documentation

Outcome: `stilyagi check` reports all enabled starter rules with stable text
and JSON, obeys selection/suppression, and applies only opted-in unsafe
repeated word edits followed by verification re-lint. Requirements: observable
success criterion for 2.3.1 and V-2–V-5.

Acceptance evidence: pytest-bdd feature scenarios against actual Markdown
files; focused text, JSON, and fix snapshots with semantic assertions; user and
developer docs describe exact supported policy and limitations; full sequential
gates pass. Inspect `git diff --check`, `git status`, and `git diff --stat`
before commit.

Conformance check: CLI behaviour matches RFC 0003; fixes pass ADR 0009; docs
match observed behaviour; all upstream assumptions and trace links remain
valid; no unrelated roadmap item is marked complete. Recovery: retain M1/M2
commits as coherent states or revert M3 docs/test integration. Remaining gaps
are explicitly deferred in the roadmap. Compatibility decision: none.

## Concrete steps

Run commands from the repository root. The examples below are implementation
commands after plan approval; they are not to be run as part of this draft-only
planning task. Use `set -o pipefail` for every gate pipeline so `tee` cannot
hide a failing command.

1. Add a test-first BDD feature,
   `features/stilyagi_builtin_markdown_rules.feature`. Include these scenarios,
   keeping exact names synchronized with pytest-bdd:

   ```gherkin
   Feature: Builtin Markdown rules
     Scenario: report a heading depth jump with a manual fix
       Given a Markdown file has a level one heading followed by a level three heading
       When I run stilyagi check on the file with JSON output
       Then the second heading has an MD001 source span and a manual fix
       And applying fixes leaves the heading markers unchanged

     Scenario: require explicit opt-in for a repeated-word fix
       Given a Markdown file contains the repeated words "the the"
       When I run stilyagi check with fixes enabled
       Then STY001 is reported and the source file is unchanged
       When I run stilyagi check with unsafe fixes enabled
       Then the repeated suffix is removed and verification re-lint is clean

     Scenario: report configured banned terms only when selected
       Given configuration selects TERM001 with the term "obviously"
       And a Markdown paragraph contains "obviously"
       When I run stilyagi check on the file
       Then TERM001 reports the exact original UTF-8 byte span
       And no automatic fix is offered
   ```

2. For each rule, first run the narrow red tests. Example focused commands (use
   the actual test names after writing them):

   ```bash
   uv run --group dev pytest -q tests/test_builtin_markdown_rules.py -k heading_depth
   uv run --group dev pytest -q tests/test_rule_policy.py
   uv run --group dev pytest -q tests/test_builtin_markdown_rules.py -k repeated_word
   uv run --group dev pytest -q tests/test_builtin_markdown_rules.py -k banned_term
   uv run --group dev pytest -q tests/test_builtin_markdown_rules.py tests/test_rule_policy.py
   uv run --group dev pytest -q tests/test_builtin_markdown_rules_bdd.py
   ```

   At the red stage, each new focused test must fail because the behaviour is
   missing, not because fixture setup or extension import failed. Remove any
   strict expected-failure marker in the same change that makes its test pass.

3. Implement the narrowest change for the failing contract; run the focused test
   again. After every refactor, repeat that focused test. Record the observed
   test names and counts in `Progress`; do not invent counts in advance.

4. Run major gates sequentially on this candidate, preferably through
   `scrutineer`, capturing logs under `/tmp` as required by the repository
   instructions:

   ```bash
   set -euo pipefail
   make fmt 2>&1 | tee /tmp/fmt-stilyagi-2-3-1.out
   make check-fmt 2>&1 | tee /tmp/check-fmt-stilyagi-2-3-1.out
   make typecheck 2>&1 | tee /tmp/typecheck-stilyagi-2-3-1.out
   make lint 2>&1 | tee /tmp/lint-stilyagi-2-3-1.out
   make test 2>&1 | tee /tmp/test-stilyagi-2-3-1.out
   make markdownlint 2>&1 | tee /tmp/markdownlint-stilyagi-2-3-1.out
   make nixie 2>&1 | tee /tmp/nixie-stilyagi-2-3-1.out
   ```

   `make fmt` changes files and precedes its check. Each remaining gate starts
   only after the previous one finishes. A failure requires inspecting its
   captured log, fixing the cause, then rerunning the failed gate and any later
   gates made stale by that edit.

5. Review the final changed paths, run `git diff --check`, verify only the
   intended files changed, and update this plan's living sections before each
   milestone commit. Do not run proof tooling unless the plan is amended with a
   Rust proof obligation and an exact project-supported Verus command.

## Validation and acceptance

Success means all of the following hold on the approved implementation head:

- Unit tests specify match boundaries, target policy, option validation,
  suppression behaviour, exact source byte spans, line/column mapping, and fix
  applicability. Rust tests cover Rust changes only; Python unit tests use
  pytest and Rust unit tests use `rstest` with `googletest` assertions and
  `pretty_assertions` where useful.
- Behavioural tests use `pytest-bdd` for the real Python CLI. If Rust-exposed
  behaviour changes, add `rstest-bdd` coverage for the bridge workflow. Do not
  claim BDD acceptance from unit tests alone.
- Syrupy snapshots cover the stable text, JSON, and fix-output variants.
  They normalize paths and pair with semantic assertions. Use `insta` only if
  implementation changes Rust output with its own multivariant contract.
- Hypothesis checks V-1 and V-3 over generated Unicode, separator, and byte
  boundaries. Keep generators constructive (no high-rejection filters), report
  examples accepted/classified, and demonstrate the negative control fails. Use
  `proptest` if implementation introduces a Rust-owned range invariant.
- No Verus proof is due for the currently proposed Python-only policy and
  matching kernels. If the approved design changes to add contractual Rust
  logic, the proof sketch, production-connected proof artefact, verifier
  command, trusted-assumption review, inhabited witnesses, and counterexample
  control become acceptance criteria before that Rust milestone can pass.
- `make check-fmt`, `make typecheck`, `make lint`, `make test`,
  `make markdownlint`, and `make nixie` pass sequentially. The user's required
  four code gates pass after each major milestone.
- A reviewer can inspect exact behaviour from the tests and command output;
  neither snapshot presence nor successful compilation alone counts as proof.

## Idempotence and recovery

Tests create temporary Markdown fixtures and may be re-run without changing the
repository. Rule order and outputs are deterministic. A rejected or conflicting
edit leaves the complete file untouched under ADR 0009. If a milestone fails,
revert only its commit, preserve previous validated plateaus, inspect the gate
log, then retry after correcting the cause. Never delete shared Cargo caches or
interrupt other builds. Draft publication is independently repeatable only
after checking whether a PR already exists for the branch.

## References and skills

Primary repository contracts:

- `docs/roadmap.md` items 2.1.2, 2.2.1–2.2.2, and 2.3.1–2.3.3.
- `docs/stilyagi-design.md` §§3–5, 7.2, and 7.3.
- `docs/rfcs/rfc-0002-stilyagi-python-rule-api.md` and
  `docs/rfcs/rfc-0003-stilyagi-cli-contract.md`.
- `docs/adrs/adr-0009-safe-fix-planning-and-conflict-resolution.md`.
- `docs/complexity-antipatterns-and-refactoring-strategies.md`.
- `docs/rust-testing-with-rstest-fixtures.md`,
  `docs/rust-doctest-dry-guide.md`,
  `docs/reliable-testing-in-rust-via-dependency-injection.md`, and
  `docs/rstest-bdd-users-guide.md`.
- `docs/documentation-style-guide.md`, `docs/users-guide.md`, and
  `docs/developers-guide.md`.

External prior art, retrieved through Firecrawl on 2026-10-25:

- [markdownlint MD001](https://github.com/DavidAnson/markdownlint/blob/main/doc/md001.md)
  describes heading levels that increment one level at a time. Its frontmatter
  behaviour is not adopted as Stilyagi policy; this plan permits any first
  heading and does not infer a heading from metadata.
- [Vale repetition check](https://vale.sh/docs/checks/repetition) documents
  configurable token-based repetition matching. It is prior art for rule
  usefulness only; Stilyagi defines its own bounded token and source-span
  behaviour.
- [`googletest` Rust crate documentation](https://docs.rs/googletest/latest/googletest/)
  is the primary assertion-library reference for the requested Rust unit tests;
  use the repository's `rstest` fixtures and project examples rather than
  copying unrelated crate examples.

Skills for the implementor: `$execplans`, `$codegraph-mcp`, `$firecrawl-mcp`,
`$hexagonal-architecture`, `$rust-router`, `$python-router`,
`$rust-unit-testing`, `$python-testing`, `$hypothesis`, and
`$rust-verification`. Use CodeGraph for symbol relationships if available; if
unavailable, record the fallback to targeted path inspection. Load the smallest
appropriate language/testing skill as the concrete obligation requires. The
project AGENTS instructions assign full repository gates and requested managed
CodeRabbit review to `scrutineer`; do not parallelize gates for this candidate.

## Interfaces and dependencies

The names below describe the proposed end state, not existing public APIs.
Implementation should align exact types and module placement with the approved
contracts after the Stage A sweep.

- A typed `RegionTarget` constrains allowed region kind and scope. It is the
  stable Markdown rule selector; no tree-sitter node or spaCy object crosses
  into rules.
- Each rule declares stable `code`, `name`, `summary`, default severity,
  target, required structural capability, typed option model, and fix mode.
- Private `RuleRunRequest` supplies `Document`, original source bytes,
  reported path, global resolved configuration, and config provenance to the
  application runner. The rule hook receives only `RuleContext[T]`, with a
  validated frozen per-rule option object and read-only document/source facts.
  Rule code does not perform I/O, parse TOML, or render diagnostics.
- Each emitted diagnostic carries path, stable code, message, severity,
  optional source byte span, existing line/column location, and optional fix.
  JSON adds an explicit `{byte_start, byte_end}` span object or `null`; text
  output remains compatible.
- Existing fix values remain `Fix`, `TextEdit`, and `Applicability` from
  `python/stilyagi/fixes.py`. No alternate edit representation or bypass around
  the current planner is permitted.
- Configuration uses existing `[tool.stilyagi.lint]` selection fields and
  `[tool.stilyagi.lint.per-file-ignores]` glob tables plus
  `[tool.stilyagi.rule.CODE]` per-rule tables as parsed by
  `python/stilyagi/config/parse.py`. No pack-level
  `[tool.stilyagi.rules.builtin]` table is currently accepted; adding one is
  out of scope. Per-file globs are relative to the effective config parent (or
  invocation cwd with no config), with stdin filename substituted where
  supplied. `plugins = []` disables builtins. `TERM001` accepts `terms`
  (alphabetic single tokens; an empty sequence is valid) and `case_sensitive`
  (boolean, default false). Rule option errors use the established
  `InvalidConfigError` boundary. Do not add `stilyagi rules` listing or pack
  registry behaviour in this item.
- Dependencies: no new runtime dependency. Test-only use follows the existing
  pinned `pytest`, `pytest-bdd`, `hypothesis`, `rstest`, `rstest-bdd`,
  `googletest`, `pretty_assertions`, `syrupy`, `insta`, and `proptest` setup;
  verify actual locked availability before adding any test dependency. Rust
  unit assertions use `googletest` and `pretty_assertions` with `rstest` as
  documented in the repository testing guide and crate docs.

### Proposed module and callable boundaries

Place pure `Rule[T]`, `RuleContext[T]`, `RegionTarget`, and the structural
capability declaration in `python/stilyagi/rules/base.py`. Put the immutable
canonical region view in `python/stilyagi/model/region.py`; retain no redundant
placeholder representation. Put the canonical-IR adaptation and node-span index
in `python/stilyagi/engine/rule_view.py`. Keep source-byte conversion in
`python/stilyagi/model/source.py` alongside the moved `SourceSpan`, with the
reuse contract documented in the developer's guide.

The application request belongs in `python/stilyagi/rules/registry.py`; its
runner becomes `run_rules(request: RuleRunRequest) -> list[Diagnostic]`. The
rule hook is
`visit_region(ctx: RuleContext[T], region: Region) -> Iterator[Diagnostic]`,
with per-document preparation/reset for heading state. Create one rule instance
per document, never a mutable shared singleton. The registry visits rules in
`(pack_name, code)` order and eligible regions in source order, using stable
region IDs to break equal-position ties. Update
`python/stilyagi/check_execution.py`, `python/stilyagi/fix_execution.py`, and
all injected runners in tests in the same milestone.

Use `python/stilyagi/rules/policy.py` for pure prefix and suppression
decisions; config parsing and typed validation stay in
`python/stilyagi/config/`. `RuleContext` contains no global config object.
Define the three builtin classes in `rules/builtin/heading_depth.py`,
`rules/builtin/repeated_word.py`, and `rules/builtin/banned_term.py` under
`python/stilyagi/`. Common token scanning belongs in `rules/builtin/text.py`
only after the repository-equivalent sweep; both text rules consume the same
immutable per-document token records.

Heading targets are all Markdown heading regions, including empty headings.
Text targets are Markdown headings, paragraphs, and table cells. Nested list
and blockquote paragraphs are ordinary paragraph units; thin containers do not
produce duplicate findings. Exclude frontmatter, image alternatives, link
titles, code blocks, raw HTML, and inline-code spans. Ordinary visible link
text remains eligible; URLs and delimiters do not. Never join adjacent source
segments, even when their bytes touch. Record this deliberate recall limit.

Prefix matching uses exact `ALL` or `code.startswith(prefix)`. Selection must
match, then ignore and per-file ignore win regardless of prefix length.
Unmatched prefixes are valid no-ops, including default families not yet
shipped. Use case-sensitive `fnmatch.fnmatchcase` over the complete
config-relative POSIX path for per-file globs; in this bounded contract `*` may
match `/`. Document that choice and test root and nested paths, inherited
config, stdin filenames, and runs from a different working directory. Preserve
the existing CLI override/extend precedence in `cli_config.py`.

Validate the options of recognized builtin rule tables even when disabled;
unknown options on those tables are configuration errors. Preserve other rule
families' tables for future slices. `MD001` and `STY001` accept empty option
objects only. `TERM001` uses a frozen
`BannedTermConfig(terms=(), case_sensitive=False)`. Do not interpret strings as
sequences of terms or integers as booleans. Absent or empty terms produce no
findings, even when selected. Empty strings or any non-alphabetic character in
a configured term are rejected; duplicates under the selected comparison mode
coalesce.

For both text rules a word is a maximal run of characters satisfying Python
`str.isalpha()`. Digits, underscores, apostrophes, hyphens, and combining marks
are boundaries; there is no Unicode normalization or language-aware token claim.
`STY001` compares exact original tokens and requires only ASCII spaces or tabs
between them. `TERM001` compares each complete original token to the configured
terms, applying `casefold()` only for comparison when requested. Tests document
these deliberate boundaries and case-fold expansion.

## Revision notes

- 2026-10-25: Initial DRAFT written from roadmap, design, RFC, IR/fix pipeline
  reconnaissance, and Firecrawl prior-art lookup. Added source-span
  diagnostics, suppression filtering, and selected three-rule scope as explicit
  proposals; six-perspective expert review completed and its findings were
  incorporated; user approval remains outstanding.
- 2026-10-28: User approved the plan; Status moved from DRAFT to APPROVED and
  implementation milestones M1–M3 are authorized.
- 2026-11-04: Status moved to COMPLETE. Recorded the final hosted evidence for
  `79511e35`, the pre-merge table disposition, and the resolved-configuration
  record that replaced the duplicated provenance lookup.
- 2026-11-05: Reconciled the delivery record with the accepted head
  `d484dab1`. The status date and the final-state note now name that head, the
  earlier `27fc732e` gate evidence is labelled as belonging to that merge
  commit rather than the tip, and hosted run `41981901016` is linked to the
  head it tested. Shorthand `ADR 009` references are normalized to `ADR 0009`.
- 2026-11-06: Reconciled the delivery record with the repaired head
  `4a4d107a`. The status line and the retrospective name that head, the
  `d484dab1` record is retained as history, the local gate evidence is labelled
  by the revision it ran on, and hosted run `42219413204` is recorded against
  the head it tested.
- 2026-11-06: Reconciled the delivery record with the repaired head `c5a4bd83`,
  which closes the Unit Architecture and property-testing rows raised against
  `df3c9223`. The status line and the retrospective name the new head; the
  `4a4d107a` and `d484dab1` records are retained as history; and the seven-gate
  local run for `c5a4bd83` is recorded with its sub-stage results.
