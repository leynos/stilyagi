# Implement safe-fix planning, conflict resolution, `--diff`, and `--fix` for Markdown

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
`Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`, `Decision Log`,
and `Outcomes & Retrospective` must be kept up to date as work proceeds.

Status: IN PROGRESS

Roadmap item: 2.2.2. Requires 2.1.1 (Markdown intermediate representation
envelope) and 2.2.1 (`stilyagi check`), both complete.

Working branch: `xxx`, tracking `origin/xxx`. This work is based on `main`,
which includes the `configure-df12-lints` changes: the pinned `ty` typechecker,
the `df12-python-lints` Pylint tier and the `ambrleaks` snapshot scanner in
`make lint`. Re-measure the baseline before trusting its gate numbers if the
base changes again.

## Purpose / big picture

Today `stilyagi check` reads Markdown, extracts an intermediate representation
(IR), and prints diagnostics. It cannot propose or apply a repair. After this
change a user can run `stilyagi check docs/ --diff` to see exactly which bytes
Stilyagi would rewrite, and `stilyagi check docs/ --fix` to have it rewrite
them — with a hard guarantee that Stilyagi only ever edits bytes the IR vouches
for as coming from the original file, and refuses to touch a file at all when
two rules disagree about the same bytes.

The working behaviour is this. Given a Markdown file and a rule that appends a
full stop to a list item, `stilyagi check notes.md --diff` prints a unified
diff to standard output that `git apply` accepts, prints its summary to
standard error, leaves the file byte-identical, and exits 1.
`stilyagi check notes.md --fix` rewrites the file and exits 0. If two rules
propose different replacements for overlapping bytes, neither runs, the file
stays byte-identical, and the user is told which two rules collided and that
re-running will not help.

"Conservative and auditable" is the acceptance bar. Conservative means the
engine refuses anything it cannot prove safe. Auditable means every refusal is
reported, never silently skipped, and every mutated file is logged.

### Terms used in this plan

Define these before reading further; they are used precisely throughout.

- **IR** — intermediate representation. The canonical JavaScript Object
  Notation (JSON) document Stilyagi's Rust extractor produces per file. Defined
  in `crates/stilyagi-ir/`; reaches Python as a parsed mapping on `Document.ir`.
- **Region** — one prose surface, such as a heading or a paragraph. Regions
  carry a `text` string that rules read.
- **Segment** — one contiguous piece of a region's `text`. Either
  **source-backed** (its `source` field holds a byte range whose bytes equal
  the segment text exactly) or **synthetic** (`source` is `null` and
  `synthetic` names a reason such as `softbreak_space`).
- **Synthetic span** — the absence of a source byte range. A synthetic segment
  has no byte range at all, so "editing a synthetic span" means addressing
  bytes no source-backed segment vouches for.
- **Byte span / byte offset** — every span in the IR is a half-open range of
  UTF-8 **byte** offsets into the original file. Never character indices, never
  line/column pairs.
- **Edit** — a request to replace the bytes in one span with a replacement
  string.
- **Fix** — a titled, applicability-tagged bundle of one or more edits attached
  to a diagnostic.
- **Applicability** — `safe`, `unsafe`, or `manual`. Only `safe` applies by
  default; `unsafe` requires `--unsafe-fixes`; `manual` never applies
  automatically.
- **Admissible** — an edit whose byte span lies wholly inside one source-backed
  span of its file. This check implements "reject edits against synthetic
  spans".
- **Coalesce** — collapse two byte-for-byte identical edits into one.
- **File-atomic** — either every planned edit for a file applies, or none does
  and the file is left untouched.
- **Verification re-lint** — a second extraction and rule pass over a file that
  `--fix` actually mutated, used to compute an honest exit code.

## Constraints

Hard invariants. Violating one requires escalation, not a workaround.

1. **Edits target original file bytes only.** No edit may be expressed against
   region text offsets, reconstructed text, or line/column coordinates
   (`docs/stilyagi-design.md`, "Fix and edit model").
2. **The bytes Stilyagi reasons about must be the bytes on disk.** Source is
   read as bytes and decoded explicitly; it is never read through Python's
   universal-newline translation. See Decision Log D-10 — this is currently
   violated and fixing it is the first milestone.
3. **Never write to a file whose plan contains an inadmissible or conflicting
   edit.** `docs/stilyagi-design.md` §4: "conflict or invalid edit yields
   diagnostics without mutation."
4. **`manual` fixes never apply**, with or without `--unsafe-fixes`.
5. **Never write to a path whose content came from standard input.**
6. **Ratified contracts must not be contradicted.** `Fix` carries exactly
   `title`, `applicability`, `edits`; `TextEdit` carries exactly `byte_start`,
   `byte_end`, `replacement` (RFC 0002 §10). Exit codes are 0/1/2 (RFC 0003
   §12). Where this plan deviates, it amends the RFC in the same change.
7. **Markdown only.** No Python or Rust source fixing. Do not touch
   `crates/stilyagi-tree-sitter/`.
8. **Do not build the rule engine.** `python/stilyagi/rules/registry.py` keeps
   returning `[]`. Roadmap 2.3.1 owns it. This slice adds only an injection
   seam.
9. **Do not implement caching** (`--no-cache` stays a no-op; roadmap 2.2.3) or
   **suppression filtering** (rule-engine work).
10. **No new runtime dependency**, Python or Rust. The unified diff uses the
    standard library's `difflib`.
11. **No new Rust code.** See Decision Log D-11.
12. **Every module stays under 400 lines**, every function under
    `max-complexity = 8`, `max-args = 4`, `max-locals = 10`, with 100%
    docstring coverage.

## Tolerances (exception triggers)

- **Scope:** more than 30 files touched, or more than 1,800 net non-test lines
  — stop.
- **Interface:** if `Fix`, `TextEdit`, or `Applicability` must diverge from RFC
  0002 §10 — stop.
- **Dependencies:** any new runtime dependency — stop.
- **Iterations:** a gate still failing after 3 focused attempts — stop and
  report the exact output.
- **Ambiguity:** a contract question this plan does not answer, where two
  readings give materially different user-visible behaviour — stop.
- **Milestone size:** any milestone exceeding 4 hours — stop and propose a
  split.
- **Runtime:** if the new property tests add more than 10 seconds to a warm
  `make test` — stop and reduce `max_examples` rather than raising timeouts.

## Risks

- **Risk:** `--fix` silently rewrites every line ending in a CRLF file.
  Severity: high. Likelihood: certain if unaddressed — `python/stilyagi/cli.py`
  reads with `pathlib.Path.read_text`, which opens in universal-newline mode
  and translates CRLF to LF before anything sees it. The repository already
  ships CRLF fixtures. Mitigation: Milestone 0 converts the read path to bytes,
  with a golden fixture asserting a zero-fix `--fix` run is byte-identical.

- **Risk:** `--fix` with `--stdin-filename` overwrites a real file with editor
  buffer content. Severity: high. Likelihood: high — `_stdin_check_input` sets
  `resolved_path` to the named file even though the content came from standard
  input. Mitigation: an explicit guard keyed on `source_text is not None`, plus
  a dedicated test (Milestone 5).

- **Risk:** `--diff` output is polluted by the diagnostic summary and is not
  `git apply`-able. Severity: medium. Likelihood: high — `cli.py`
  unconditionally prints rendered diagnostics to standard output and the text
  renderer always appends an "N diagnostics found" line. Mitigation: the stream
  contract in D-05, plus an end-to-end test piping the output through
  `git apply --check`.

- **Risk:** the complexity gates force an unplanned refactor mid-feature.
  Severity: medium. Likelihood: high. `run_check` is at 9 locals against a
  limit of 10 and 3 arguments against a limit of 4; keyword-only arguments
  count toward `PLR0913`. Mitigation: Milestone 0 does the collaborator
  refactor first, and the module decomposition below is mandatory, not advisory.

- **Risk:** the admissibility rule is too narrow to be useful.
  Severity: medium. Likelihood: low for prose rules, **certain** for heading
  markers. Mitigation: Milestone 3 includes an executable proof that a
  list-punctuation insertion is admissible against the real corpus. The
  heading-depth limitation is accepted, documented in ADR 0009, and raised
  against roadmap 2.3.1.

- **Risk:** an extractor off-by-one turns a wrong diagnostic into a destroyed
  paragraph. Severity: high. Likelihood: low. Mitigation: the segment-text
  cross-check in D-12 — free defence in depth.

- **Risk:** pre-existing gate failures are mistaken for regressions.
  Severity: low. Likelihood: high. Mitigation: the measured baseline below.

### Baseline gate state

Measured 2026-08-23 on a clean tree at `configure-df12-lints` commit `33eea7f`
plus this plan's document, with no code changes. Re-measure if the base moves;
it has already been force-pushed once during this plan's life.

**Every gate is green.** There is no pre-existing failure to work around, so
any gate failure that appears is newly introduced.

- `make check-fmt` — **PASS**
- `make typecheck` — **PASS**. `ty check` reports `All checks passed!`.
- `make lint` — **PASS**. Every tier is clean: ruff, interrogate, the
  PyPy-backed Pylint, the `df12-python-lints` Pylint tier, `ambrleaks`,
  `cargo doc`, clippy, and Whitaker.
- `make test` — **PASS**. pytest reports `213 passed, 28 warnings in 5.80s`
  with `16 snapshots passed`; nextest reports
  `332 tests run: 332 passed, 0 skipped`.
- `make markdownlint` — **PASS** (66 files, 0 errors).
- `make nixie` — **PASS**.

Note for anyone carrying an older copy of this plan: on `main` the Whitaker
Dylint step failed on four pre-existing `no_expect_outside_tests` sites in
`crates/stilyagi-ir/src/tests/`. Those were fixed upstream before this base
branched, so that carve-out no longer applies and must not be used to excuse a
Whitaker failure.

`make test-ci` remains **broken independently of this work**: it runs
`cargo nextest run --profile ci` but no `.config/nextest.toml` exists, so
nextest exits 96 with ``profile `ci` not found``. Cite `make test`, never
`make test-ci`. Fixing it is **out of scope**.

Success means all six gates stay green.

### Measured facts to rely on

Established during planning; use them instead of re-measuring.

- Building and sorting the admissible span set for the largest Markdown file in
  the repository (87 KB, 503 regions, 2,604 segments, 1,878 source-backed)
  takes **0.48 ms**. Membership testing 200 edits costs 4.4 ms linear versus
  0.05 ms with `bisect`. Neither is a bottleneck; use `bisect` for consistency
  with `python/stilyagi/diagnostics_location.py`.
- Across all 73 Markdown files, source-backed spans are **strictly disjoint and
  gap-separated** — zero overlapping pairs, zero byte-adjacent pairs. Merging
  adjacent spans is therefore a no-op in practice, but keep it: it is cheap and
  it makes the containment check correct if the extractor ever changes.
- `stilyagi check` spends **51%** of its time in the extraction call and
  **33%** in `json.loads` of the IR. Rules cost 0%. A full second lint pass
  therefore costs about 84% of a check run per file — which is why the
  verification re-lint in D-13 covers only files actually mutated.
- The parsed IR of one large file costs **6.5 MB resident**. Before-and-after
  text for the entire repository costs **2.8 MB**. Never retain a `Document` or
  its IR across files; retaining fixed bytes is fine.
- `extract_document` costs about **1.06 ms** per call on the shared fixture, so
  corpus-sampling Hypothesis strategies are affordable.

## Progress

- [x] 2026-08-23 — Implementation authorized by the repository owner. PR #109
  title and its Lody session title now omit the planning prefix.
- [x] 2026-08-23 — Milestone 0: reads are byte-faithful; `CheckInput` retains
  decoded text and original bytes; collaborator injection is bundled behind
  `CheckCollaborators`. All six deterministic gates pass and CodeRabbit found
  zero concerns (`43bd949`); Milestone 1 may begin.
- [x] Milestone 1 — typed IR view
  - Blocked 2026-08-23: the `make lint` gate remained red after the third
    focused gate iteration, reaching the `Iterations` tolerance. Awaiting
    explicit direction before changing the assertion structure. The post-turn
    check explicitly instructed this fix on 2026-08-24; one focused exception
    iteration completed with all six deterministic gates green. CodeRabbit
    found zero concerns (`4a3d3ba`); Milestone 2 may begin.
- [x] Milestone 2 — fix model, splice kernel, stub retirement
  - 2026-08-24: committed the pure `fixes.py` value-model slice separately to
    preserve the required small rollback points. `Fix` accepts the RFC's bare
    string and list examples while normalizing them to hashable strict values;
    `Diagnostic.fix` is now typed. The package-layout snapshot was updated for
    the new module. The splice kernel, renderer contract, and stub retirement
    completed in this milestone. The full deterministic gate chain is green;
    CodeRabbit found zero concerns; Milestone 3 may begin.
- [x] Milestone 3 — admissibility, selection, conflict resolution
  - 2026-08-24: the first planner slice is committed as `d44fc34`. It rejects
    malformed, non-UTF-8, synthetic, non-contiguous, and provenance-mismatched
    edits; applies file-atomic candidate selection; coalesces identical edits;
    and aborts conflicting files before mutation. Its six deterministic gates
    passed (240 Python tests, 332 Rust tests, and 17 snapshots).
  - 2026-08-24: Stage C2 now samples 69 real source-backed corpus segments
    and six source-to-synthetic boundaries constructively. The focused planner
    and property suite passes 24 tests; full deterministic gates and the
    required CodeRabbit review remain before Milestone 4.
  - 2026-08-24: committed the corpus-backed Stage C2 properties as `76da310`
    at the owner's explicit request to preserve the completed work. This does
    not satisfy the pending gate or CodeRabbit boundary; Milestone 4 remains
    prohibited until both are complete.
  - 2026-08-24: rebased onto `origin/configure-df12-lints`. The base branch's
    locked `ty` type-checking configuration and configuration-map validation
    supersede the older Pyright replay; the safe-fix commits remain separate.
  - Blocked 2026-08-24: three sequential full-gate attempts passed formatting,
    Ruff, and Interrogate, but the mandated PyPy Pylint tool could not resolve
    existing PyPI dependencies because domain-name lookup failed. No later gate
    or CodeRabbit review was run; await restored dependency access before
    retrying the complete chain.
  - 2026-09-07: a review found that `_segment_matches_source` decoded a
    containing IR segment without first validating that segment's bounds and
    UTF-8 boundaries. Added red/green planner regressions for a segment that
    starts inside a code point and one that extends past the source. Both now
    reject the file with `fix-error/source-mismatch`; the complete gate chain
    and CodeRabbit review remain before Milestone 4.
  - 2026-09-07: all six deterministic gates passed after the malformed-segment
    correction: 266 Python tests, 337 Rust tests, Markdown spelling and
    Mermaid validation. CodeRabbit reviewed pushed commit `f9cb8ae` on draft
    PR #138 and returned zero findings. Milestone 4 may begin.
- [x] Milestone 4 — `--diff`
  - 2026-09-07: the standalone diff-renderer red/green slice passes
    its six focused tests, but three focused full-gate attempts exhausted the
    `Iterations` tolerance. The first required Ruff formatting; the second
    found test subprocess policy errors; the third isolated two missing
    explicit `shell=False` arguments in `tests/test_fix_diff.py`. The post-turn
    gate explicitly instructed a correction. The configured custom rule did
    not recognize those arguments, so the fixed test commands use the
    repository's established, documented exception and a resolved executable.
    Its wheel-layout snapshot now includes `diff.py`. The authorized correction
    and subsequent rebase gates are green. The completed CLI integration has
    also passed its complete milestone gate chain; CodeRabbit review remains.
  - 2026-09-07: the `--diff` pipeline now plans only safe edits against the
    byte-faithful checked source, writes the unified patch to standard output,
    and sends diagnostics and refusal reports to standard error. Focused
    command, renderer, and wheel-layout tests pass; the emitted diff snapshot
    captures the machine/human stream boundary.
  - 2026-09-07: all six deterministic gates passed (275 Python tests and 18
    snapshots), then CodeRabbit reviewed pushed commit `ebbcac7` on draft PR
    #138 and returned zero actionable findings. Milestone 5 may begin.
  - 2026-09-24: rebased onto `origin/main` (`11e6026`). PR #109 was closed
    unmerged rather than squashed, so the whole 27-commit series replayed
    intact against merge-base `c997b28`; the exclusive boundary was the
    graph's ordinary merge-base, with all 27 commits branch-owned. One
    conflict arose, in `tests/test_renderers.py`: both sides appended a test
    at end of file, and both were kept along with main's `import pytest` and
    the branch's `Fix, TextEdit` import. Two failures then surfaced that the
    pre-rebase base could not have caught, because `main` added a doctest lane
    to `make test` after this branch forked: `splice.py` imported `TextEdit`
    only under `typing.TYPE_CHECKING`, so its `apply_edits` example raised
    `NameError` once `pytest --doctest-modules` ran over `python/stilyagi`;
    and `renderers.py`'s `RendererRegistry` doctest still expected
    `'0 diagnostics found\n'` where the branch renders
    `'0 diagnostics found (0 safe fixes, 0 unsafe fixes)\n'`. Both were
    repaired, the second by keeping main's corrected escaping and updating
    only the value. The execplan itself had never passed `mdtablefix --wrap`
    and was reflowed with the gate's own rules.
- [x] Milestone 5 — `--fix`, `--unsafe-fixes`, and honest exit codes
  - 2026-09-07: the atomic-write sub-slice has red/green coverage for mode
    preservation, no-op writes, and file symlinks. `write_source` resolves the
    target, stages bytes in its directory, copies metadata, and swaps with
    `os.replace`; its wheel-layout snapshot was reviewed.
  - 2026-09-28: complete and committed at `cc2fb81`. Dispatch, two-phase
    execution, the verification re-lint, the mutating flags across a real
    process boundary, and the fixed-document emitter's three silent reasons are
    all covered; see Revision 38.
  - 2026-09-28: the CodeRabbit review returned five genuine defects, all
    repaired and each pinned by a test confirmed to fail without its fix; see
    Revision 39.
- [x] Milestone 6 — documentation, ADR 0009, and the RFC 0003 amendment
  - 2026-09-28: all eight Stage D deliverables are in the working tree and were
    verified individually, not assumed; see Revision 39 for the table and for
    the two substantively required statements (ADR 0009's heading-depth
    constraint and the 2.3.1 warning).
  - 2026-09-28: three gate failures found by `scrutineer` at the Revision 40
    tip, all repaired and recorded in Revision 41. `make check-fmt` (Revision
    40's own tables were unformatted, fixed with `make fmt`); `make markdownlint`
    (two `synthesised` spellings in `docs/users-guide.md`, which `typos.toml`
    maps to `-ize`); `make lint` (four DOC201 errors, **introduced by this
    branch's own `e6a2e73`**, which expanded four single-line docstrings into
    multi-line bodies and thereby switched off the `ignore-one-line-docstrings`
    exemption). Fixed at `1d3b660` and `4cf61ef`; the full chain is re-running
    at `4cf61ef`.

- [ ] Milestone 6 review — CodeRabbit pass at `4cf61ef`, not yet requested.
  Waits on a green deterministic chain, because CodeRabbit must not be used for
  what a deterministic gate already catches.

- [x] 2026-09-24 — PR #160 review feedback actioned. CodeRabbit raised nine
  findings and CodeScene four; each was verified against the working tree
  before any edit, and all thirteen were still valid. Two were Major
  correctness defects. `diff.py` split lines with `str.splitlines`, which
  breaks on `\r`, `\v`, `\f`, `\x1c`-`\x1e`, `\x85`, `U+2028`, and `U+2029`, so
  a Markdown line holding one of those characters became two diff lines whose
  first element lacked a terminator and the no-newline marker landed inside the
  hunk. Reproduced against `git apply --check`: all six characters produced
  rejected patches before the fix and accepted patches after it. `write.py`
  compared the target only with the planned content, so an edit made between
  planning and writing would be overwritten; it now takes `original_bytes` and
  refuses a target that no longer holds them (`SourceChangedOnDiskError`),
  which is the missing half of D-16's two-phase execution. Its staging helper
  also removes a partial file when writing raises `OSError`. The remaining
  findings were the four now-dead Skylos exemptions (`--diff` reaches
  `preview_safe_fixes`, so `plan_fixes`, `FixPlanRequest`,
  `_validate_candidates`, and `_overlap_rejection` are live), a precedence bug
  in the `find_source_span` fixture that returned the first match across
  segments instead of requiring exactly one, a test fixture using literal
  backslash-`n` instead of a real newline, and four CodeScene code-health
  findings. The refactors cut `run_check` from 79 to 63 lines and its
  cyclomatic complexity from 13 to 5 by extracting `_aggregate_checked_files`,
  which also brought the module's worst function down from 13 to 9;
  `_add_check_arguments` fell from 71 to 62 lines; and three structurally
  identical planner tests became one parametrized case table.

## Surprises & discoveries

- Observation (2026-08-23): the df12 Pylint tier rejects bare test assertions
  and flags a large inline expected tuple as a snapshot candidate. The first
  two Milestone 1 gate iterations corrected formatter, import-placement, and
  wheel-layout snapshot issues; the third isolated five assertion findings in
  `tests/test_ir_view.py`. Impact: the plan's three-iteration tolerance has
  been reached, so implementation must pause before restructuring the tests.

- Observation (2026-08-23): changing the file read boundary from `read_text`
  to `read_bytes` required the established operational-error test seam to patch
  `Path.read_bytes`. The five existing read-failure cases still pass, now at
  the production boundary rather than the retired newline-translating one.

- Observation: the Python read path destroys line-ending fidelity before the
  Rust extractor ever sees the text. Evidence: `python/stilyagi/cli.py` reads
  with `resolved_path.read_text(encoding="utf-8")`. `Path.read_text` opens with
  `newline=None`, so a 39-byte CRLF file arrives as a 36-character string. The
  Rust extractor is CRLF-exact and has dedicated fixtures
  (`paragraph-soft-break-crlf.md.fixture` and two others) plus a golden
  `line_index` computed on CRLF-bearing text. Impact: the golden IR fixtures
  and the command-line runtime already disagree about byte offsets for CRLF
  files. Today that is invisible because line and column resolve against the
  same normalized string. Under `--fix` it becomes silent whole-file
  line-ending rewriting. This is the highest-severity finding in the review and
  is why Milestone 0 exists.

- Observation: `list_item` and `blockquote` regions carry **zero** segments,
  but their prose is still fixable. Evidence:
  `crates/stilyagi-markdown/src/snapshots/stilyagi_markdown__tests__lists.snap`
  shows each `list_item` region (`"segments": []`) paired with a nested
  `paragraph` region whose `parent_region` points at it and whose segment is
  source-backed — for `- Unordered item`, `{"byte_start": 2, "byte_end": 16}`.
  Blockquotes follow the same pattern, with `scope` recording the container
  chain. Impact: an early reading of the design suggested list punctuation was
  unfixable. It is not. Prose rules target the nested paragraph.

- Observation: heading markers genuinely are outside the admissible set, and
  widening to IR node spans would not help. Evidence: for `# Top Level` the
  heading **node** span is `{"byte_start": 0, "byte_end": 11}` but the heading
  **region** segment covers only `Top Level` (bytes 2–11). The root node spans
  the entire document, so admitting node spans would admit every byte and the
  guard would become vacuous. Impact: a heading-depth rule must ship `manual`.
  Recorded in D-03 and ADR 0009, and must be raised against roadmap 2.3.1.

- Observation: there are already **two** splice implementations, not one.
  Evidence: `tests/support/round_trip.py` (126 lines) is a Python twin of
  `crates/stilyagi-test-support/src/round_trip_edits.rs` — byte offsets, UTF-8
  boundary checks, sort by `(start, end)`, `itertools.pairwise` overlap
  rejection, cursor splice. Impact: the production kernel absorbs the Python
  one, which then delegates, giving 260 lines of existing tests plus a
  behaviour-driven feature as free regression coverage. See D-11 for why the
  Rust one is left alone.

- Observation: an earlier draft claimed the Rust helper contradicts RFC 0002
  §10 on identical edits. It does not. Evidence: RFC 0002 §10 says "Identical
  overlaps **MAY** coalesce" — permissive, not mandatory. A helper that rejects
  duplicates is conforming and is a stricter test oracle. Impact: the planned
  Rust reconciliation milestone was removed. See D-11.

- Observation: the `FIX` prefix collides with an existing linter at the same
  numbers. Evidence: Ruff's flake8-fixme rules are `FIX001` through `FIX004`.
  RFC 0002 §12 states the prefix model "intentionally echoes Ruff's prefix
  model", so Ruff-literate users are the explicit audience. `FIX` is not
  reserved in RFC 0002 §12, so a third-party pack could claim it. Impact:
  planning rejections move to a separate channel with non-rule-shaped
  identifiers. See D-07.

- Observation (2026-08-24): the Milestone 3 full gate chain cannot reach the
  PyPy Pylint check because its existing dependency fetches cannot resolve
  `pypi.org`. Three sequential attempts independently failed resolving `pylint`
  or `astroid`; Ruff and Interrogate passed on each. Evidence is in the three
  `lint` logs with suffixes `11`, `12`, and `13` under `/tmp`. Impact: the plan
  is blocked by its three-iteration tolerance, with no deterministic-code
  failure or CodeRabbit result to act on.

- Observation (2026-09-07): validating only the proposed edit's byte range
  does not make the containing segment safe to decode. An IR segment can begin
  inside a multi-byte UTF-8 code point while still containing a valid edit, and
  a segment that extends beyond the source is silently truncated by slicing.
  Impact: validate the containing segment's bounds and UTF-8 alignment before
  decoding it, then turn any decode failure into the existing non-mutating
  `fix-error/source-mismatch` outcome.

- Observation: `nodes` is roughly a third of the IR payload and no Python code
  reads it. Evidence: for an 87 KB Markdown file the canonical IR JSON is 2.01
  MB, of which `nodes` is 667 KB. Python reads only `ir["errors"]`,
  `ir["line_index"]`, and `ir["regions"][*]["kind"]` — and, from this slice,
  `segments`. Impact: gating `nodes` and `trees` out of the bridge payload
  would plausibly cut `stilyagi check` runtime by about 30%. **Out of scope** —
  it is a check-path win with no bearing on fix planning, and it would churn
  every golden IR snapshot. Recorded here so the measurement is not lost; raise
  it as a separate roadmap item.

- Observation (2026-09-28): **a docstring edit in this repository is not an
  inert change.** `pydoclint.ignore-one-line-docstrings = true` means DOC201
  exempts a docstring by its *shape*, so expanding a one-line docstring into a
  substantive body switches the rule on for that function. Commit `e6a2e73`
  expanded four such docstrings to explain the code, and `make lint` then
  reported four `docstring-missing-returns` errors that had not existed before
  it. Evidence: all three files pass ruff at `e6a2e73^` and fail at the tip.
  Impact: a documentation-shaped commit still needs the affected gate run
  before it is pushed, which is the same lesson as the spelling gate's `-ise`
  map and the Markdown contract tests -- prose here is load-bearing for at
  least three gates. See Revision 41.

## Decision log

- **D-01: The fix planner lives in Python.**
  Rationale: fixes are produced by Python rules (RFC 0002); the whole `check`
  pipeline is Python; the kernel is about 0.5 ms of a 42 ms per-file budget, so
  there is no performance case for Rust. A Rust kernel would marshal every edit
  across a boundary that is already the bottleneck. AGENTS.md's preference for
  `verus` proofs is scoped to "Rust extensions", and neither `verus` nor `kani`
  exists anywhere in this workspace — adopting one would mean standing up a
  proof toolchain on the branch whose job is to ship `--fix`. The Python
  analogue, `hypothesis`, is already a dev dependency. Note:
  `docs/stilyagi-design.md` §10 constrains file *location*, not implementation
  language; it does not by itself decide this. Date/Author: 2026-08-16,
  planning session.

- **D-02: `Fix`, `TextEdit`, and `Applicability` live at
  `python/stilyagi/fixes.py`, not under `engine/`.** Rationale: they are
  produced by rules and merely consumed by the engine. Under `engine/` they
  would force `python/stilyagi/rules/` to import `stilyagi.engine`, and because
  `python/stilyagi/engine/__init__.py` transitively imports the compiled
  `_stilyagi_rs` extension, the zero-dependency `diagnostics.py` would come to
  require the extension at runtime. Date/Author: 2026-08-16, structural review.

- **D-03: Admissibility is containment within a single source-backed segment
  span, after merging touching spans. Markup outside region text is not fixable
  in this slice.** Rationale: merging costs nothing in safety and is strictly
  more useful. Widening to IR node spans was considered and rejected as vacuous
  — the root node spans the whole document. Consequence: a heading-depth rule
  ships `manual`; a list-punctuation rule works. This is a lossy proxy for the
  real hazard (a rule computing an offset in region-text coordinates), so it is
  paired with the cross-check in D-12 rather than relied on alone. Date/Author:
  2026-08-16, verified against real IR snapshots. **Confirmed by the repository
  owner on 2026-08-16**, including the consequence that a heading-depth rule
  ships `manual`. Do not re-litigate this during implementation; if the model
  proves wrong in practice, escalate under Tolerances rather than widening it
  unilaterally.

- **D-04: Conflicts abort the whole file rather than skipping the losing fix.**
  Rationale: `docs/stilyagi-design.md` §4 states the failure path as "conflict
  or invalid edit yields diagnostics without mutation", so the alternatives
  would require amending the design document. The honest trade is **blast
  radius**, not determinism: skip-the-loser can be made fully deterministic by
  sorting on edit content, but file-atomic abort means one conflicting pair
  blocks every unrelated safe fix in that file. That cost is accepted for v1
  because it is the conservative direction and because skip-the-loser is only
  really safe when paired with a fixpoint loop, which this slice does not have.
  Revisit if users report it. Date/Author: 2026-08-16, design review.
  **Confirmed by the repository owner on 2026-08-16**, blast radius accepted.
  Do not substitute skip-the-loser during implementation.

- **D-05: Under `--diff`, and under `--fix` reading standard input, the machine
  artefact owns standard output alone and all diagnostics go to standard
  error.** Rationale: without this, `stilyagi check --diff | git apply` receives
  `0 diagnostics found` and fails on a clean repository — which gets "fixed"
  with `|| true`, permanently disarming the check. Worse, redirecting a
  standard-input `--fix` run back over the user's own buffer would write the
  diagnostic summary into that file. Matches Ruff, which sends the diff to
  standard output and its summary to standard error. Date/Author: 2026-08-16,
  structural and operations review.

- **D-06: `--fix` combined with `--diff` is a usage error (exit 2), and RFC
  0003 §10 is amended to say so.** Rationale: silent precedence between a
  mutating and a non-mutating flag is exactly the surprise this contract exists
  to prevent, and rejection is the relaxable direction — a rejected combination
  can later be given meaning; an accepted one with silent precedence cannot be
  withdrawn. But an exit-2 path that no ratified contract describes may not
  ship, so the RFC is amended in the same change. Date/Author: 2026-08-16,
  contract review.

- **D-07: Planning rejections are reported on a separate channel, not as rule
  codes.** Rationale: `FIX001`–`FIX003` collide with Ruff's flake8-fixme at the
  same numbers, and `FIX` is unreserved in RFC 0002 §12. More fundamentally
  these are engine reports about a rule's defective output, not rules: as rule
  codes they would become `--select`/`--ignore`-able (letting a user silence
  the evidence that a rule emits bad edits while the file still is not fixed),
  and they would have to appear in `stilyagi rule CODE` and `stilyagi rules`,
  which RFC 0003 §§3.2–3.3 define in terms no engine report can satisfy.
  Decision: JSON gains a sibling `fix_errors` array; text output gets a
  distinct prefix. Identifiers are `fix-error/synthetic-span`,
  `fix-error/overlapping-edits`, `fix-error/malformed-span`. They carry no
  exit-code weight of their own — the unfixed diagnostic already forces exit 1
  — and they are exempt from selection and suppression by construction.
  Date/Author: 2026-08-16, contract and operations review.

- **D-08: The production kernel is normative for splice semantics.**
  `tests/support/round_trip.py` becomes a delegating adapter over it, keeping
  its public names so existing tests and
  `features/stilyagi_round_trip_helpers.feature` keep passing and become
  regression coverage of the production kernel. Date/Author: 2026-08-16.

- **D-09: Retire the `engine/fixes.py` `FixPlan(applicability: str)` stub.**
  `FixPlan` becomes the planner's result type. `ExecutionPlan` and
  `EngineRunner` are left untouched. Date/Author: 2026-08-16.

- **D-10: Source is read as bytes and decoded explicitly; edits are spliced on
  bytes; output is written as bytes.** Rationale: this is the only way the IR's
  byte offsets can mean what the ratified contract says they mean. It fixes
  CRLF fidelity, byte-order-mark handling, final-newline handling, and the
  Windows write-path translation in one move, and it makes the byte offsets
  that D-14 exposes in JSON honest. Date/Author: 2026-08-16, operations review.

- **D-11: No Rust changes in this slice.**
  Rationale: the Rust helper's stricter identical-edit handling is conforming
  (RFC 0002 §10 says "MAY"), and a stricter test oracle is a feature. Loosening
  it would weaken the golden tests and pull an entire Rust workstream —
  `cargo doc -D warnings`, clippy across all targets, Whitaker, nextest,
  doctests — into a Python slice. Instead, add one sentence to that module's
  `//!` documentation recording that it is deliberately stricter than the
  engine and is a golden-fixture oracle, not a second engine. If true
  reconciliation is ever wanted, it is a separate task with its own gate run.
  Date/Author: 2026-08-16, viability and alternatives review.

- **D-12: Every admissible edit is cross-checked against its segment's text
  before it is accepted.** Rationale: `IrSegment.text` is documented as
  existing for invariant checking. Asserting
  `source_bytes[byte_start:byte_end].decode() == segment["text"]` for the
  containing segment is free, and it is the difference between an extractor
  off-by-one producing a wrong diagnostic and it eating a paragraph. A failure
  aborts the file. Date/Author: 2026-08-16, operations review.

- **D-13: `--fix` performs one planning pass, then a verification re-lint of
  only those files it actually mutated, and derives the exit code from that.**
  Rationale: RFC 0003 §12's "0 when all found violations were fixed" is not
  computable in a single pass without *assuming* that applying a fix removes
  its diagnostic — an assumption nothing tests and which a partial fix
  falsifies. Re-linting only mutated files keeps the cost proportional to the
  work done. This is not a fixpoint loop: if the re-lint surfaces new fixable
  diagnostics, they are reported, not applied, and the output says so.
  Date/Author: 2026-08-16, alternatives and operations review.

- **D-14: The diagnostics JSON gains a `schema_version`, and `fix_applicable`
  is pinned to pure existence.** Rationale: this slice is the first change to
  the JSON shape and the document has no version field, while RFC 0001 mandates
  one for the IR with explicit compatibility rules. Pinning `fix_applicable` to
  `fix is not None` — rather than "would be applied given current flags" —
  keeps the output reproducible across `--unsafe-fixes` and `lint.fixable`
  combinations; consumers read `fix.applicability` to decide. Without this
  pinning it would report `true` for a `manual` fix, which the design defines
  as not automatically applicable. Date/Author: 2026-08-16, contract review.

- **D-15: `--unsafe-fixes` is not silently inert.** The text renderer's summary
  gains fixability counts, so a user of the default output format can discover
  that unsafe fixes exist. Rationale: "accepted but does nothing" is the one
  option that cannot be tightened later, because anyone who scripts around a
  no-op is broken by giving it meaning. The safe/unsafe split only works if
  users can see what they are opting into. Date/Author: 2026-08-16, contract
  review.

- **D-16: `--fix` plans every file before writing any file.**
  Rationale: file-atomicity does not cover an interruption at file 200 of 400,
  which leaves a half-fixed repository and no record of where it stopped. The
  before-and-after text for an entire repository costs under 3 MB, so two-phase
  execution is affordable. Never retain a `Document` or its IR across files —
  that would cost 6.5 MB per file. Date/Author: 2026-08-16, operations and
  scaling review.

- **D-17: `CheckInput` carries both source bytes and decoded text.** Rationale:
  Milestone 0 needs extraction to receive explicitly decoded, newline-faithful
  text, while later planning and writing need the exact bytes on which the IR
  offsets are based. Keeping them together prevents a later caller from
  re-reading and accidentally normalizing the source. Standard input enters the
  same representation by reading `sys.stdin.buffer`. Date/Author: 2026-08-23,
  implementation.

- **D-18: Pause Milestone 1 at the gate-iteration tolerance.** Evidence: the
  first full gate run found formatting, type-only import, and wheel snapshot
  defects; the second left the type-only import defect; the third left five
  df12 Pylint assertion findings. Options are to authorize a fourth focused
  iteration that adds contextual assertion helpers and a deliberately narrow
  snapshot, or to revise the tests differently. Trade-off: continuing without
  approval would violate the plan's explicit `Iterations` tolerance.
  Date/Author: 2026-08-23, implementation.

- **D-19: Authorize one focused assertion-remediation iteration.** Rationale:
  the post-turn gate on 2026-08-24 explicitly instructed remediation of the
  remaining `C9102` and `R9108` findings. The exception is limited to adding
  assertion messages and one focused line-index snapshot; no production
  contract changes are permitted. The full deterministic chain still gates
  onward progress. Date/Author: 2026-08-24, user-directed implementation.

- **D-20: Generate fix-planning properties from extracted corpus provenance.**
  Rationale: generating arbitrary Markdown makes failures ambiguous between the
  extractor and planner, while filtering generated edit ranges makes Hypothesis
  discard most candidates. A module-level cached corpus loader exposes 69
  source-backed segments and six source-to-synthetic triples, so every accepted
  case is valid by construction and every rejection case crosses a real
  synthetic boundary. Date/Author: 2026-08-24, implementation.

- **D-21: Pause Milestone 3 for unavailable required dependencies.** Evidence:
  three full-gate attempts passed `make check-fmt`, Ruff, and Interrogate, then
  failed while the existing PyPy Pylint wrapper resolved `pylint` or `astroid`
  from PyPI. The problem is external DNS resolution, not a code finding.
  Rationale: bypassing, suppressing, or substituting this mandated lint tier
  would contradict the plan and repository gate policy. The owner subsequently
  requested a local preservation commit (`76da310`); it records the work but
  does not authorize Milestone 4. Retry only after dependency access is
  restored. Date/Author: 2026-08-24, implementation.

- **D-22: Retain the df12 lint base's `ty` configuration on rebase.**
  Rationale: replaying the older strict-Pyright commit would reintroduce
  `pyright` and its lockfile entries after `configure-df12-lints` had replaced
  them with the pinned `ty` runner. The target branch's configuration-map
  validation and locked dependency state are newer shared infrastructure and do
  not overlap the safe-fix feature. Date/Author: 2026-08-24, rebase.

## Outcomes & retrospective

- Milestone 0 (2026-08-23): removed universal-newline translation from the
  disk and standard-input paths without changing the extractor's text API. The
  first red regression used the real CRLF corpus fixture and failed because the
  old path delivered LF text; it passes after the bytes-first change. The
  bundle keeps `run_check` beneath the local-count threshold while giving later
  feature tests a stable, private rule-runner injection seam.
- Milestone 1 (2026-08-24): added a tolerant, typed read-only IR view over the
  real extractor payload. The view preserves source-backed versus synthetic
  provenance, merges touching spans for future containment checks, and keeps
  malformed IR data non-fatal. `checker.py` now consumes its shared line-index
  and span helpers, avoiding duplicate interpretation logic.

## Context and orientation

This is a mixed Rust and Python repository. Rust crates under `crates/` parse
source into the IR; a PyO3 bridge (`crates/stilyagi-pyext/`) exposes extraction
to Python; the Python package under `python/stilyagi/` holds the command-line
interface, configuration, the diagnostic model, and the not yet built rule
engine. **All work in this plan is Python** (see D-11).

Read these first. They are the authority when this plan and the code disagree.

- `docs/stilyagi-design.md` — §4 (the "Applying safe fixes in CI or pre-commit"
  flow, and the "Fix and edit model" and "Diagnostics output" subsections) and
  §7.3.
- `docs/rfcs/rfc-0002-stilyagi-python-rule-api.md` §§9–10 — the ratified
  diagnostic and fix shapes. Note the worked example in §4, which passes
  `applicability="safe"` as a bare string and `edits=[...]` as a list; the
  model must accept that (see D-14 and the interface section).
- `docs/rfcs/rfc-0003-stilyagi-cli-contract.md` §§3.1, 10, 11, 12.
- `docs/developers-guide.md` §2b — the existing pipeline, written for exactly
  this orientation.
- `AGENTS.md` and `docs/documentation-style-guide.md`.
- `docs/complexity-antipatterns-and-refactoring-strategies.md` §5.B before
  splitting modules further than prescribed.

Skills to load: `leta` for navigation (`leta refs` rather than grep),
`python-router` then `python-testing` and `hypothesis`,
`hexagonal-architecture` for the domain/adapter split, and `execplans` to keep
this document current.

### Gate thresholds, measured

State these as facts; they were probed against this repository's own
configuration.

- `PLR0913` max-args = 4. **Keyword-only arguments count**:
  `f(a, *, b, c, d, e)` fails at 5.
- `PLR0914` max-locals = 10. Arguments do not count; 11 assigned locals fails.
- `C901` max-complexity = 8, computed as base 1 plus one per decision point —
  so the budget is **7 branches or loops per function**.
- `FBT001`/`FBT002` are enabled: **no boolean parameters.** Use a `FixLevel`
  enumeration, never `unsafe: bool`.
- `PLR6301` (no-self-use) is enabled: prefer module-level functions to methods.
- `PLR1702` (too many nested blocks) is enabled: return rejection **values**,
  never raise inside per-edit loops.
- `[tool.ruff.lint.per-file-ignores]` exempts `**/test_*.py` and
  `tests/steps/*.py` from `S101`, `S506`, `PLR0913`, `PLR0917`, `PLR2004`, and
  `PLR6301`. It does **not** exempt `tests/support/`, which is held to full
  production strictness including 100% numpy-style docstrings.
- **`make typecheck` runs `ty`, pinned** at the version in the Makefile's
  `TY_VERSION` (currently `0.0.72`) through `uv tool run ty@$(TY_VERSION)`.
  `[tool.ty.src]` sets `include = ["python/stilyagi"]` and excludes `tests`, so
  the test suite is not typechecked. Do not bump `TY_VERSION` as part of this
  work; a typechecker upgrade is its own change with its own blast radius.
  Because `tests` is unchecked, `ir_view.py` must still narrow `object` with
  explicit `isinstance` checks for safety rather than relying on the gate to
  catch a bad assumption.
- **`make lint` runs two further Python tiers** beyond ruff, interrogate, and
  the PyPy-backed Pylint: every `df12-python-lints` v0.2.0 Pylint message
  (thirteen IDs in `DF12_PYLINT_MESSAGES`) under CPython 3.14, and `ambrleaks`
  over `tests`. `ambrleaks` scans syrupy snapshots, so the new `.ambr` and
  `.json` snapshots this plan adds are gated by it.
- **Every lint or type-check suppression must carry an explanation.** The df12
  plugin enforces this. Use `# noqa: RULE - reason` for ruff and
  `# pylint: disable=name  # reason` for Pylint, and never use one tool's
  suppression syntax to hide the other tool's finding.
- pytest collects doctests. `make test` runs
  `pytest --doctest-modules $(PY_DOCTEST_PATHS)` over `python/stilyagi` and
  `tests/support`, and `tests/test_doctest_collection.py` fails when a module
  carrying an example is not covered by that selection. The `>>>` examples
  AGENTS.md requires are therefore executable and must import every name they
  use.
- Markdown prose wraps at 80 columns, code blocks at 120; tables and headings
  are unwrapped. Run `make fmt` before `make markdownlint`.
- Spelling is en-GB-oxendict: "-ize", "-yse", "-our". Write "normalize" and
  "serialize" but "behaviour" and "analyse". Backtick every identifier — the
  spelling gate skips code spans. Never hand-edit `typos.toml`; run
  `make spelling`, which renders it from the shared dictionary and then checks.
  Repository-specific exceptions belong in `typos.local.toml`.

### Files touched

Modified: `python/stilyagi/diagnostics.py`, `python/stilyagi/cli.py` (338 lines
on this base — only 62 lines of headroom under the 400 cap),
`python/stilyagi/cli_args.py`, `python/stilyagi/discovery.py`,
`python/stilyagi/engine/__init__.py`, `python/stilyagi/engine/checker.py`,
`python/stilyagi/engine/renderers.py`, `python/stilyagi/rules/registry.py`,
`tests/support/round_trip.py`, `tests/test_package_skeleton_units.py`, and
`crates/stilyagi-test-support/src/round_trip_edits.rs` (**a documentation
comment only** — see D-11).

New: `python/stilyagi/fixes.py`, `python/stilyagi/engine/ir_view.py`,
`python/stilyagi/engine/fix_planning/` (`__init__.py`, `selection.py`,
`admissibility.py`, `conflicts.py`, `splice.py`, `plan.py`, `diff.py`,
`write.py`), `python/stilyagi/engine/fix_pipeline.py`,
`features/stilyagi_fix_command.feature`, `tests/steps/fix_command.py`,
`tests/support/fix_fixtures.py`, `tests/support/fix_plan_strategies.py`, the
matching `tests/test_*.py` modules, and
`docs/adrs/adr-0009-safe-fix-planning-and-conflict-resolution.md`.

Deleted: `python/stilyagi/engine/fixes.py`.

## Interfaces and dependencies

### `python/stilyagi/fixes.py` (Milestone 2)

Pure value types. Imports nothing from `stilyagi.engine` and nothing from the
compiled extension.

```python
class Applicability(enum.StrEnum):
    """How safe a fix is to apply automatically."""

    SAFE = "safe"
    UNSAFE = "unsafe"
    MANUAL = "manual"


class FixLevel(enum.StrEnum):
    """The applicability ceiling a run is willing to apply."""

    SAFE = "safe"
    UNSAFE = "unsafe"


@dc.dataclass(frozen=True, slots=True, order=True)
class TextEdit:
    """One replacement of a half-open UTF-8 byte range."""

    byte_start: int
    byte_end: int
    replacement: str

    @classmethod
    def replace(cls, span: ir_view.SourceSpan, text: str) -> "TextEdit": ...


@dc.dataclass(frozen=True, slots=True)
class Fix:
    """A titled bundle of edits attached to one diagnostic."""

    title: str
    applicability: Applicability
    edits: tuple[TextEdit, ...]

    def __post_init__(self) -> None:
        """Coerce loosely typed rule-authored values into the strict form."""
```

Two details that are easy to get wrong and expensive to discover late.

`__post_init__` **must** coerce: RFC 0002 §4's ratified worked example
constructs `Fix(title=..., applicability="safe", edits=[TextEdit(...)])` with a
bare string and a list. Without coercion, `fix.applicability.value` in the JSON
renderer raises `AttributeError` on a `str`, and `Fix` becomes unhashable. The
repository already has this pattern: `python/stilyagi/config/schema.py`
normalizes every sequence field in `__post_init__`. Use `object.__setattr__` as
that module does, since the dataclass is frozen.

`order=True` gives the natural sort `(byte_start, byte_end, replacement)`.
Include `replacement` deliberately: it is what makes the conflict report
deterministic when two same-span edits disagree.

`Diagnostic.fix` in `python/stilyagi/diagnostics.py` changes from
`object | None` to `Fix | None`, imported under `if typ.TYPE_CHECKING:` so
`diagnostics.py` keeps zero runtime imports.

### `python/stilyagi/engine/ir_view.py` (Milestone 1)

A typed read-only anti-corruption layer over the untyped `Document.ir` mapping.
**Build this first** — the planner consumes it, and 2.3.1's rules will consume
the same thing unchanged. Building the planner directly against
`Mapping[str, Any]` is the one decision 2.3.1 would genuinely have to undo.

Every accessor tolerates a malformed or absent IR by returning an empty or
`None` result, never by raising. `crates/stilyagi-ir/src/tree.rs`'s
`SourceSpan::try_new` rejects only `byte_start > byte_end` — there is no bounds
check and no character-boundary check — so the IR can legitimately hand Python
a span past end-of-file or mid-code-point.

```python
@dc.dataclass(frozen=True, slots=True, order=True)
class SourceSpan:
    """A half-open UTF-8 byte range in the original source."""

    byte_start: int
    byte_end: int


@dc.dataclass(frozen=True, slots=True)
class SegmentView:
    """One IR segment, with its source span when it has one."""

    span: SourceSpan | None
    text: str
    synthetic_reason: str | None


def iter_segments(document: model.Document) -> cabc.Iterator[SegmentView]:
    """Yield every segment of every region, in document order."""


def source_backed_spans(document: model.Document) -> tuple[SourceSpan, ...]:
    """Return merged, sorted spans of every source-backed segment."""


def segment_for_span(document: model.Document, span: SourceSpan) -> SegmentView | None:
    """Return the source-backed segment wholly containing a span."""


def line_index(document: model.Document) -> tuple[int, ...] | None:
    """Return the IR line index, or None when the IR omits a valid one."""


def byte_start_from_span(span: object) -> int | None:
    """Return a span mapping's byte start when the IR provides one."""
```

`line_index` and `byte_start_from_span` move here from
`python/stilyagi/engine/checker.py` (`_coerce_line_index` and
`_byte_start_from_span`); update `checker.py` to import them rather than
keeping private copies.

`segment_for_span` exists to support the D-12 cross-check.

### `python/stilyagi/engine/fix_planning/` (Milestones 2 and 3)

The monolithic version of this pipeline is literally unbuildable under the
gates: counted as one function it has ten decision points against a budget of
seven, and more than a dozen locals against a budget of ten. This decomposition
is **mandatory**.

| Module             | Contents                                                                                   | Branch budget |
| ------------------ | ------------------------------------------------------------------------------------------ | ------------- |
| `splice.py`        | `apply_edits(source_bytes, edits) -> bytes`                                                | 1             |
| `admissibility.py` | `containing_span(edit, spans)` via `bisect`; `classify_edit(...) -> EditRejection \| None` | ≤4            |
| `selection.py`     | `partition_candidates(...) -> CandidatePartition`; `is_fixable(code, lint_config) -> bool` | ≤3            |
| `conflicts.py`     | `coalesce_identical(edits)`; `first_overlap(edits)`                                        | ≤1            |
| `plan.py`          | `plan_fixes(request) -> FixPlan` — straight-line composition                               | ≤3            |
| `diff.py`          | `unified_diff(before, after, reported_path) -> str`                                        | ≤3            |
| `write.py`         | `write_source(path, content)`                                                              | ≤3            |

Three rules that make this hold and which are easy to violate:

1. **Rejections are values, not exceptions.** `classify_edit` returns an
   `EditRejection` or `None`. Raising inside the per-edit loop forces `try`/
   `except` nesting and costs both `C901` and `PLR1702`.
2. **Group parameters into request objects.**
   `FixPlanRequest(source_bytes, document, diagnostics, level, lint_config)` and
   `FixPlan(...)`. AGENTS.md mandates this and the gates enforce it.
3. **No boolean parameters.** Use `FixLevel`, never `unsafe: bool`.

`coalesce_identical` is `tuple(dict.fromkeys(edits))` — zero branches, and
correct because `TextEdit` is frozen and hashable. `first_overlap` is one
`itertools.pairwise` scan. Note that `previous.byte_end > current.byte_start`
does **not** catch two insertions at the same offset with different text; add
an explicit equal-offset check.

```python
@dc.dataclass(frozen=True, slots=True)
class EditRejection:
    """One refused edit, with the rule code that produced it."""

    identifier: str  # "fix-error/synthetic-span", etc.
    rule_code: str
    detail: str


@dc.dataclass(frozen=True, slots=True)
class FixPlan:
    """The outcome of planning one file's fixes."""

    edits: tuple[fixes.TextEdit, ...]
    fixed_codes: tuple[str, ...]
    rejections: tuple[EditRejection, ...]
    fixed_bytes: bytes | None  # None when nothing may be written
```

The planning algorithm, in order:

1. **Select.** Keep diagnostics whose `fix` is not `None`, whose
   `applicability` is `SAFE`, or is `UNSAFE` when `level` is `UNSAFE`. `MANUAL`
   is always dropped. Then drop any whose `code` fails the fixability predicate.
2. **Validate each fix atomically.** For each edit check
   `0 <= byte_start <= byte_end <= len(source_bytes)`, that both offsets fall
   on UTF-8 code-point boundaries, that the span is contained in one merged
   source-backed span, and the D-12 cross-check that the containing segment's
   recorded text equals the bytes it claims. If any edit of a fix fails, reject
   the **whole** fix and keep none of its edits.
3. **Coalesce** byte-for-byte identical edits.
4. **Order** by natural `TextEdit` order.
5. **Detect conflict.** Any adjacent overlapping pair, or two same-offset
   insertions with different text, yields a plan with empty `edits`,
   `fixed_bytes = None`, and a `fix-error/overlapping-edits` rejection naming
   both rule codes.

An insertion (`byte_start == byte_end`) is admissible at any offset within a
merged span **inclusive of both endpoints**.

### `python/stilyagi/engine/fix_planning/diff.py` (Milestone 4)

```python
def unified_diff(before: str, after: str, reported_path: str) -> str:
    """Render a git-appliable unified diff for one file."""
```

The exact recipe matters and the obvious spelling is wrong. Use
`before.splitlines(keepends=True)`, `fromfile=f"a/{reported_path}"`,
`tofile=f"b/{reported_path}"`, `n=3`, **leave `lineterm` at its default**, and
join with `""`.

Setting `lineterm=""` while feeding lines that keep their endings doubles the
newline on every content line and produces a patch `git apply` rejects with
"corrupt patch". Feeding `splitlines()` output without `keepends` instead
discards line terminators, so a CRLF file yields a patch claiming LF content.
Both were reproduced during review. Return `""` when the texts are equal.

`difflib` cannot emit `\ No newline at end of file`. Append it manually when a
side lacks a trailing newline; without it, a patch touching the last line of a
file with no final newline is either rejected or silently adds one.

### `python/stilyagi/engine/fix_planning/write.py` (Milestone 5)

```python
def write_source(path: pathlib.Path, content: bytes) -> None:
    """Replace a file's contents atomically, preserving mode."""
```

Write to a temporary file in the **same directory** as the target — not `/tmp`,
which risks a cross-device `EXDEV` — copy the original's mode with
`shutil.copystat`, then `Path.replace()` (which invokes `os.replace`). Never
truncate in place. Resolve symbolic links first and write to the resolved path
so a link is not replaced by a regular file. Skip the write entirely when the
new bytes equal the old, so `--fix` does not churn modification times across a
documentation tree and wake every file watcher.

### `python/stilyagi/cli.py` (Milestone 0)

> **Superseded sketch.** This is the Milestone 0 proposal, kept as the record of
> what was originally intended. Do not read the `writer` field below as current
> design. Revision 32 dropped it -- `grep -rn '\.writer\|writer='` over
> `python/` and `tests/` found no reader, and `fix_execution` owns the write
> and takes its target from the plan rather than from an injected collaborator.
> The as-built bundle carries `resolver`, `renderer`, `rule_runner`, `output`,
> and a `reporter`, and its fields default through factories rather than being
> `None` sentinels. See the Revision 32 entry below for the delivered form.

```python
@dc.dataclass(frozen=True, slots=True)
class CheckCollaborators:
    """Injectable collaborators for one check run."""

    resolver: config.ConfigResolver | None = None
    renderer: engine.RendererRegistry | None = None
    rule_runner: rules_registry.RuleRunner | None = None
    writer: FileWriter | None = None
    output: typ.TextIO | None = None


def run_check(
    options: CheckOptions,
    *,
    collaborators: CheckCollaborators | None = None,
) -> int:
    """Run the check command and print rendered diagnostics."""
```

Two arguments, permanently. Update `docs/developers-guide.md` §2b's
"Collaborator injection" subsection in the same change.

### `python/stilyagi/rules/registry.py` (Milestone 0)

Declare the seam's type so the stub cannot drift. `ty` excludes `tests`, so an
untyped stub would fail at runtime mid-suite instead.

```python
class RuleRunner(typ.Protocol):
    """The callable shape the check pipeline expects from a rule runner."""

    def __call__(
        self, document: model.Document, config: StilyagiConfig, /
    ) -> list[diagnostics.Diagnostic]: ...
```

Document in its docstring that `rule_runner` injection is private and unstable,
so plugin authors do not adopt it.

### `lint.fixable` and `lint.unfixable` semantics (Milestone 5)

These are ratified config surface (RFC 0003 §6) that this slice gives behaviour
for the first time. Write the semantics down before implementing:

- **Matcher:** full rule codes or stable prefixes, reusing the same matcher as
  `--select`/`--ignore` (RFC 0003 §8). One prefix matcher in the codebase, not
  two. It belongs in `config/`, not in the fix planner, because it is selection
  logic.
- **Precedence:** `unfixable` is subtractive and unconditional — it always
  beats `fixable`, with no longest-match rule. So `fixable = ["PUN"]` with
  `unfixable = ["PUN201"]` leaves PUN202 fixable and PUN201 not.
- **Orthogonality:** selection decides whether a rule runs and whether its
  diagnostic is *reported*; fixability decides only whether that diagnostic's
  fix is *applied*. A selected but unfixable code still reports. State this
  explicitly in the users' guide — "I set `unfixable` and the warning did not
  go away" is the support question this design will generate.
- **`ALL`:** reserved as a pseudo-prefix. Note in ADR 0009 that RFC 0002 §12
  does not currently reserve it and that a follow-up should.
- Model fixability as a set operation over prefixes so a future `--fixable`
  slots in as replacement and `--extend-fixable` as union, mirroring how
  `cli._build_cli_overrides` already handles `select` and `extend_select`.

### JSON output (Milestone 2, extended in Milestone 4)

```json
{
  "schema_version": "1.0.0",
  "diagnostics": [
    {
      "path": "docs/notes.md",
      "code": "PUN201",
      "message": "Use a serial comma before the final conjunction.",
      "severity": "warning",
      "location": {"line": 12, "column": 30},
      "fix_applicable": true,
      "fix": {
        "title": "Insert serial comma",
        "applicability": "safe",
        "edits": [{"byte_start": 341, "byte_end": 341, "replacement": ","}]
      }
    }
  ],
  "fix_errors": [
    {
      "identifier": "fix-error/overlapping-edits",
      "path": "docs/notes.md",
      "rule_codes": ["PUN201", "STY104"],
      "message": "Edits overlap at bytes 341..344; the file was not modified."
    }
  ]
}
```

`fix` is `null` when absent. `fix_applicable` means **existence only**
(`fix is not None`), never "would be applied given current flags" — that would
make the output non-reproducible across flag combinations. Document that
consumers read `fix.applicability` to decide.

Import RFC 0001's compatibility rules by reference: consumers must reject
unknown major versions and ignore unknown fields within a major version.

## Plan of work

Each milestone ends at a green gate and a commit. Do not start the next until
the current one's validation passes.

### Milestone 0 — byte-faithful reads and the collaborator bundle

**Why first:** every later milestone depends on the bytes being right, and
`run_check` has no argument headroom left.

Stage B (red): add a test asserting that a CRLF fixture read through the
command-line path round-trips byte-identically. Use the existing
`tests/fixtures/corpus/markdown/valid/paragraph-soft-break-crlf.md.fixture`,
which contains genuine `0d 0a` bytes. Observe it fail.

Stage C: change `_read_source` to `resolved_path.read_bytes()` then
`.decode("utf-8")`, returning both the bytes and the decoded text on
`CheckInput`. Add `CheckCollaborators` and change `run_check` to take it,
updating every call site. Add the `RuleRunner` protocol. Extract the per-file
loop body into a helper if the local count rises.

Stage D: gates. Expect some existing tests or snapshots to shift, because the
Python path now agrees with the Rust extractor about CRLF byte offsets where it
previously did not. Investigate each shift before accepting it — a changed
`line_index` or column number is the *expected* correction; a changed region
text is not.

Commit: `Read source as bytes and bundle check collaborators`.

### Milestone 1 — typed IR view

Stage B (red): add `tests/test_ir_view.py`. Build documents through
`engine.extract_document` on the real corpus so the tests exercise the true IR
shape rather than a handwritten mock.

`tests/fixtures/corpus/markdown/valid/heading-table-link-suppression.md` is the
workhorse fixture — its paragraph region `r1` already contains exactly the mix
needed:

```plaintext
segment 0: source 19..46   "This paragraph links to the"   source-backed
segment 1: source null     " "  synthetic softbreak_space
segment 2: source 48..63   "Stilyagi design"               source-backed
segment 3: source 104..105 "."                             source-backed
```

Assert that exact set. Then assert `links-and-images.md.fixture` yields no
source-backed spans for `image_alt` and `link_title`, that adjacent
source-backed segments merge, and that a malformed IR (missing `regions`,
non-integer offsets, absent `segments`) yields an empty tuple rather than
raising.

Stage C: create `ir_view.py`; move `_coerce_line_index` and
`_byte_start_from_span` out of `checker.py` and import them back.

Stage D: gates. Confirm `tests/test_ir_error_adapter.py` still passes.

Commit: `Add a typed read-only view over the extracted IR`.

### Milestone 2 — fix model, splice kernel, stub retirement

Stage B (red): add `tests/test_fixes_model.py` asserting the three
`Applicability` values, that `Fix(applicability="safe", edits=[...])` coerces
to the enumeration and a tuple, that `Fix` is hashable, that `TextEdit` sorts by
`(byte_start, byte_end, replacement)`, and that each constructor helper
produces the expected span. Add a JSON renderer case.

Stage C: create `python/stilyagi/fixes.py` and `engine/fix_planning/splice.py`.
Retype `Diagnostic.fix`. Extend the JSON renderer per the schema above and add
fixability counts to the text renderer's summary (D-15). Delete
`python/stilyagi/engine/fixes.py`, update `engine/__init__.py`'s `__all__`, and
update the two assertions in `tests/test_package_skeleton_units.py` (around
lines 55-66 and 149-170) that pin `engine.__all__` and construct
`engine.FixPlan`.

Then rewrite `tests/support/round_trip.py` as a thin adapter delegating its
splice to `engine.fix_planning.splice.apply_edits`, keeping `SourceEdit`,
`SyntheticEdit`, and `RoundTripEditError` so `tests/test_round_trip_helpers.py`
and `features/stilyagi_round_trip_helpers.feature` keep passing — and thereby
become regression coverage of the production kernel.

Stage C2 (kernel properties): add `tests/test_fix_planner_properties.py` with
the four kernel properties. Generate spans **constructively** — draw sorted
unique cut points, snap to character boundaries, pair them. Never use
`st.filter()` to reject overlaps; with three or more edits the rejection rate
explodes and Hypothesis raises `FailedHealthCheck: filter_too_much`.

1. **Independent oracle.** Compare `apply_edits` against a deliberately naive
   right-to-left in-place splice
   (`for edit in reversed(sorted_edits): b = b[:start] + repl + b[end:]`). Two
   independent implementations, one property. Do *not* reconstruct the expected
   output the same way the splice does — that asserts the code equals itself.
2. **Length arithmetic**, in bytes:
   `len(after) == len(before) - Σ(end - start) + Σ len(replacement.encode())`.
3. **Permutation determinism** via `st.permutations`.
4. **Coalescing idempotence** — appending an exact duplicate changes nothing.

Use `@hyp.settings(max_examples=64, deadline=None)`, matching the repository's
existing sizing. Set `deadline=None` explicitly: the default 200 ms plus a cold
first PyO3 call produces a spurious `DeadlineExceeded` on the first example.

Stage D: gates. Review the snapshot diffs by eye before accepting; adding the
`fix` payload invalidates
`tests/__snapshots__/test_renderers/test_json_renderer_emits_stable_diagnostic_objects.json`
and
`tests/__snapshots__/test_round_trip_helpers/test_cli_check_json_output_matches_snapshot.json`.

Commit: `Add the ratified fix model and the splice kernel`.

### Milestone 3 — admissibility, selection, conflict resolution

Stage B (red): add `tests/test_fix_planner.py`, parametrized, covering: a safe
fix inside a source-backed span is planned; unsafe is dropped without
`FixLevel.UNSAFE` and kept with it; manual is always dropped; a code failing
the fixability predicate is dropped; an edit inside a synthetic region is
rejected; an edit straddling source-backed and synthetic segments is rejected;
an edit straddling two non-contiguous source-backed segments is rejected;
out-of-bounds, inverted, and mid-code-point spans are rejected; a two-edit fix
with one bad edit keeps neither edit; identical edits coalesce; different
replacements for one span conflict and yield `fixed_bytes = None`; two
same-offset insertions with different text conflict; an insertion at a merged
span's end boundary is admissible; and a segment whose recorded text disagrees
with its bytes aborts the file (D-12).

Add `tests/support/fix_fixtures.py` with `find_source_span(document, needle)`
so **no test hard-codes a byte offset**. A stub emitting
`TextEdit(byte_start=48, ...)` encodes the fixture's exact bytes; one fixture
edit and every test rots silently, or worse keeps passing while testing the
wrong span.

Add the guard test from Risks: against the real `lists.md.fixture`, an
insertion at the end of the `- Unordered item` paragraph segment must be
admissible. If it fails, stop and escalate — the model is wrong, not the test.

Stage C: implement `selection.py`, `admissibility.py`, `conflicts.py`, and
`plan.py`.

Stage C2: add the admissibility properties to
`tests/test_fix_planner_properties.py`, with the corpus-sampling generator in
`tests/support/fix_plan_strategies.py`. Sample from the fixed corpus with
`st.sampled_from(corpus_paths)`, extract, walk the IR for source-backed spans,
sample a span, then draw a sub-span *inside* it — admissible by construction,
zero filtering. Do **not** generate Markdown text and feed it to the extractor;
generated Markdown shrinks slowly and its failures are extractor bugs, not
planner bugs. Make the corpus loader a module-level cached function, not a
pytest fixture, avoiding the need for
`suppress_health_check=[HealthCheck.function_scoped_fixture]`.

1. **(a)** Every edit in an accepted plan is contained in a **single**
   source-backed span. Note the union of all spans is strictly weaker than this
   and would pass an implementation that violates the rule. **(b)** With a
   *targeted* generator that deliberately straddles a synthetic segment, the
   plan is always rejected and `fixed_bytes is None`. Property (a) alone can
   never exercise the rejector, because its generator produces only admissible
   edits.
2. **Non-mutation on rejection.** Any conflicting input yields
   `fixed_bytes is None`. This is the design's literal failure path and the
   roadmap's success criterion.
3. **Identity round-trip.** An empty edit set yields `after == before`
   byte-for-byte.
4. **UTF-8 totality.** An accepted plan never raises `UnicodeDecodeError`.

Remember `tests/support/` is held to production lint strictness —
`max-args = 4`, `max-locals = 10`, 100% numpy docstrings. Use
`tests.support.assertions.assert_with_context(condition, message)` for
assertions needing a contextual failure message; the base branch introduced it
and converted the existing suites to it, so a bare `assert` with a trailing
comment is now off-style.

Stage D: gates. Confirm `.hypothesis/` is gitignored.

Commit: `Add safe-fix admissibility, selection, and conflict resolution`.

### Milestone 4 — `--diff`

`--diff` is non-mutating, so it is the lowest-risk first user-visible increment.

Stage B (red): add `tests/test_fix_diff.py` — empty diff for equal texts; a
produced patch accepted by `git apply --check` in a temporary git repository;
CRLF round-trip over the three CRLF fixtures; a file with no trailing newline.
Add the `--diff` scenarios of the feature file below.

Stage C: add `--diff` to `cli_args.py`, implement `diff.py` and
`fix_pipeline.py`, and implement the D-05 stream split.

Stage D: gates plus a syrupy snapshot of the diff output.

Commit: `Add stilyagi check --diff`.

### Milestone 5 — `--fix`, `--unsafe-fixes`, and honest exit codes

Stage B (red): the remaining feature scenarios, plus targeted tests for the
stdin guard, the symlink policy, atomic write preserving mode, the no-op write
skip, and each exit-code case.

Create `features/stilyagi_fix_command.feature`:

```gherkin
# markdownlint-disable MD041

Feature: stilyagi check applies conservative safe fixes

  Scenario: diff prints a patch and leaves the file untouched
    Given a Markdown file and a rule offering one safe source-backed fix
    When I run "stilyagi check . --diff" in that tree
    Then the exit code is 1
    And standard output holds a unified diff that git apply accepts
    And standard error holds the diagnostic summary
    And the Markdown file on disk is unchanged

  Scenario: fix rewrites the file and exits zero
    Given a Markdown file and a rule offering one safe source-backed fix
    When I run "stilyagi check . --fix" in that tree
    Then the exit code is 0
    And the Markdown file on disk contains the repaired text

  Scenario: unsafe fixes are withheld without the opt-in
    Given a Markdown file and a rule offering one unsafe source-backed fix
    When I run "stilyagi check . --fix" in that tree
    Then the Markdown file on disk is unchanged
    And the exit code is 1
    And the text output offers the --unsafe-fixes option

  Scenario: unsafe fixes apply with the explicit opt-in
    Given a Markdown file and a rule offering one unsafe source-backed fix
    When I run "stilyagi check . --fix --unsafe-fixes" in that tree
    Then the exit code is 0
    And the Markdown file on disk contains the repaired text

  Scenario: an edit against a synthetic span is refused
    Given a Markdown file and a rule offering a fix over a soft line break
    When I run "stilyagi check . --fix" in that tree
    Then the text output reports a synthetic-span fix error
    And the Markdown file on disk is unchanged

  Scenario: conflicting edits leave the whole file untouched
    Given a Markdown file and two rules offering different edits to one span
    When I run "stilyagi check . --fix" in that tree
    Then the text output reports an overlapping-edits fix error naming both rules
    And the text output states that the file was not modified
    And the Markdown file on disk is unchanged

  Scenario: identical edits from two rules coalesce
    Given a Markdown file and two rules offering the identical edit
    When I run "stilyagi check . --fix" in that tree
    Then the exit code is 0
    And the Markdown file on disk contains the repaired text

  Scenario: a CRLF file keeps its line endings
    Given a CRLF Markdown file and a rule offering one safe source-backed fix
    When I run "stilyagi check . --fix" in that tree
    Then the Markdown file on disk still uses CRLF line endings
    And only the repaired bytes differ

  Scenario: standard input is never written to disk
    Given a Markdown file named notes.md on disk
    When I run "stilyagi check - --stdin-filename notes.md --fix" in that tree
    Then the fixed document is written to standard output
    And the Markdown file on disk is unchanged

  Scenario: combining fix and diff is a usage error
    Given a temporary tree with two well-formed Markdown files
    When I run "stilyagi check . --fix --diff" in that tree
    Then the exit code is 2
    And the standard error reports that --fix and --diff conflict
```

Bind with `scenarios("../features/stilyagi_fix_command.feature")` from a
`test_*.py` module, with steps in `tests/steps/fix_command.py` following
`tests/steps/check_command.py` — a `typ.TypedDict` for shared state,
`@given(..., target_fixture="...")`, and
`@when(parsers.parse('I run "{command}" in that tree'))`.

The "a rule offering …" steps inject a stub through
`CheckCollaborators.rule_runner`, returning diagnostics whose `Fix` byte
offsets are derived from the real extracted IR via
`tests/support/fix_fixtures.py`.

Stage C: add `--fix` and `--unsafe-fixes`; reject `--fix --diff` with exit 2;
implement two-phase execution (D-16), the stdin guard, the symlink policy in
`discovery.py`, `write.py`, the verification re-lint (D-13), fixability
consumption, and the revised exit codes:

- Without `--fix` or `--diff`: unchanged.
- `--fix`: plan every file, write the ones with applicable plans, re-lint only
  the mutated ones, then exit 0 if no diagnostics remain, 1 if any remain, 2 on
  error. Whenever any fix was applied, tell the user on standard error that
  re-running may apply further fixes.
- `--diff`: 0 when no diff would be produced and no diagnostics remain, 1
  otherwise, 2 on error.

Observability, at INFO so `--verbose` actually reaches it — note every existing
per-stage record in `cli.py` is at DEBUG and there is currently **no
command-line path to DEBUG at all**, so a fix summary logged at DEBUG would be
invisible. Log per file: `source_backed_spans`, fixes considered, filtered by
config, filtered by applicability, coalesced, rejected, applied, and bytes
delta. Log every file written. End with a summary on standard error:
`N files fixed, M fixes applied, K files skipped (conflict), J fixes rejected`.
`files_aborted_on_conflict` is the most important counter — without it, `--fix`
appears to do nothing and the user cannot tell why.

Collapse fix errors to **one report per file per identifier with a count**,
keeping per-edit detail in the log. A buggy rule emitting one bad edit per
paragraph would otherwise produce hundreds of warnings on a large file, and one
line saying "3 conflicts, file left unmodified" is auditable where five hundred
lines is not.

Stage C2: add subprocess coverage to `tests/test_cli_e2e.py` for `--diff` and
`--fix`, including piping `--diff` output to `git apply --check`.

Stage D: gates.

Commit: `Add stilyagi check --fix with conservative conflict handling`.

### Milestone 6 — documentation, ADR 0009, and the RFC amendment

Write `docs/adrs/adr-0009-safe-fix-planning-and-conflict-resolution.md` with
the sections `docs/documentation-style-guide.md` requires: Status (Accepted,
with date), Date, Context and Problem Statement, Decision Drivers,
Requirements, Options Considered (a comparison table with a caption below it),
Decision Outcome, Goals and Non-Goals, Migration Plan, Known Risks and
Limitations, and Architectural Rationale. In review experience, Decision
Drivers, Options Considered, and Migration Plan are the sections that get
stubbed — do not stub them.

Its substance is D-03, D-04, D-05, D-07, D-10, and D-13. **State explicitly
that a heading-depth rule cannot be auto-fixed under this admissibility
model**, that widening to node spans was considered and rejected as vacuous,
and that roadmap 2.3.1 must be reviewed against this constraint before it
starts.

Amend `docs/rfcs/rfc-0003-stilyagi-cli-contract.md` §10 to record that `--fix`
with `--diff` is a usage error, with the rationale. Without this the exit-2
path is undocumented (D-06).

Update:

- `docs/users-guide.md` §3 — `--fix`, `--unsafe-fixes`, `--diff`; why a fix can
  be refused, in user language ("Stilyagi only edits text it can trace back to
  the original file byte-for-byte"); the fix-error identifiers; that a conflict
  leaves the file entirely unmodified and needs a human; that `--fix` may need
  re-running; the stream contract; `lint.fixable`/`unfixable` semantics
  including their orthogonality to `--select`/`--ignore`; and a rewritten exit
  codes block. Also correct the now-false sentence near line 333 saying fix
  workflows land in later slices.
- `docs/developers-guide.md` §2b — a "Fix planning" subsection between
  "Diagnostics" and "Rendering"; the `CheckCollaborators` change under
  "Collaborator injection"; the revised "Exit codes"; and a note that
  `engine.fix_planning.splice.apply_edits` is normative.
- `docs/stilyagi-design.md` — the "Fix and edit model" subsection gains the
  fix-error identifiers, the admissibility rule, and an ADR 0009 link. Under
  "Internal golden IR and edit helper scaffolding", update the claim that the
  round-trip helpers establish the safety checks, now that the production
  kernel exists.
- `crates/stilyagi-test-support/src/round_trip_edits.rs` — one sentence in the
  `//!` comment recording that it is deliberately stricter than the engine on
  identical edits and is a golden-fixture oracle, not a second engine. This is
  the only Rust change in the slice.
- `docs/contents.md` — index ADR 0009 and this ExecPlan.
- `docs/roadmap.md` — tick 2.2.2, matching the "Completed with validation
  evidence in …" pattern used by earlier entries.

Stage D: `make fmt`, then `make markdownlint` and `make nixie`, then the full
chain.

Commit: `Document safe-fix planning and record ADR 0009`.

## Concrete steps

Run everything from the repository root:
`/home/leynos/.lody/repos/github---leynos---stilyagi/worktrees/e4b821de-4fc5-4af5-aaed-598160137666`.

Build once before testing; `make test` and `make typecheck` both depend on
`build`, which runs `maturin develop` and the smoke check.

```shell
make build
```

Run a focused test through the virtual environment interpreter, not through
`uv run` — `uv run` would reinstall the package and replace the
maturin-developed extension:

```shell
.venv/bin/python -m pytest tests/test_fix_planner.py -v
```

Expected shape at the red stage:

```plaintext
tests/test_fix_planner.py::test_safe_fix_inside_a_source_backed_span_is_planned FAILED
E   ModuleNotFoundError: No module named 'stilyagi.engine.fix_planning'
```

Run the gate chain at the end of each milestone, sequentially — the build cache
rewards it — capturing to logs because long output is truncated:

```shell
make check-fmt    2>&1 | tee /tmp/check-fmt-stilyagi-2-2-2.out
make typecheck    2>&1 | tee /tmp/typecheck-stilyagi-2-2-2.out
make lint         2>&1 | tee /tmp/lint-stilyagi-2-2-2.out
make test         2>&1 | tee /tmp/test-stilyagi-2-2-2.out
make markdownlint 2>&1 | tee /tmp/markdownlint-stilyagi-2-2-2.out
make nixie        2>&1 | tee /tmp/nixie-stilyagi-2-2-2.out
```

Review snapshot changes deliberately:

```shell
.venv/bin/python -m pytest tests/test_renderers.py --snapshot-update
git diff tests/__snapshots__/
```

Read that diff before committing. An unreviewed snapshot update is how a
regression becomes the new expected output.

## Validation and acceptance

**Behaviour a human can verify.** In a temporary directory with a Markdown file
and a fix-producing rule injected: `stilyagi check . --diff` prints a patch to
standard output that `git apply --check` accepts, prints its summary to
standard error, leaves the file byte-identical, and exits 1.
`stilyagi check . --fix` rewrites the file, prints no patch, and exits 0.
`stilyagi check . --fix --diff` prints a usage error to standard error and
exits 2. A CRLF file keeps its CRLF endings, with only the repaired bytes
differing. `stilyagi check - --stdin-filename notes.md --fix` writes to
standard output and leaves `notes.md` untouched.

**Refusals are visible.** A fix over a soft line break produces a
`fix-error/synthetic-span` report naming the offending rule and leaves the file
unchanged. Two rules proposing different replacements for one span produce
`fix-error/overlapping-edits` naming both, state that the file was not
modified, and leave it byte-identical — not partially fixed.

**Tests.** `make test` passes. The suite grows from 213 passing pytest tests
and 16 snapshots by the new unit, property, behaviour-driven, and end-to-end
cases. Every new test failed before its implementation and passed after; record
the red transcripts in `Artefacts and notes`. The property tests add no more
than 10 seconds to a warm run.

**Lint and typecheck.** All six gates pass, with no carve-out. `ty` must stay
clean over `python/stilyagi`, and `ambrleaks` must stay clean over the
snapshots this plan adds.

**Review.** After each milestone's gates are green — and only then — run
`coderabbit review --agent` and clear every concern before the next milestone.
CodeRabbit is not a substitute for the deterministic gates.

## Idempotence and recovery

Every step is re-runnable. `make build` is idempotent. Snapshot updates revert
with `git checkout -- tests/__snapshots__/`.

The one destructive operation is `--fix` writing to a user's file. Its recovery
path is the atomic write: content goes to a temporary file and moves into place
with `os.replace`, so an interrupted run leaves the original intact *for the
file being written*. That guarantee is per file, not per run. Two-phase
execution plans every file before the first write, so an interruption leaves a
partial tree with a complete record of what was planned — it does **not**
prevent a half-fixed tree, and `apply_planned_fixes` states the same limit in
its own docstring. Files written before the interruption keep their new bytes.
When developing, only run `--fix` against `tmp_path` fixtures or a scratch
directory — never against the repository's own Markdown, which is gated by
markdownlint.

If a milestone goes wrong, `git reset --hard` to the previous milestone's
commit. That is why each milestone commits separately.

## Artefacts and notes

Record as work proceeds: the red transcript for each new test, the accepted
snapshot diffs, the `git apply --check` transcript proving the diff output is
well formed, and the before-and-after byte dumps for the CRLF fixture test.

- Milestone 0 red evidence:
  `/tmp/red-crlf-stilyagi-2-2-2-safe-fix-planning-conflict-resolution.out`
  records `test_cli_main_preserves_crlf_source_for_extraction` failing because
  extraction received LF-normalized text.
- Milestone 0 focused green evidence:
  `/tmp/green-m0-focused-stilyagi-2-2-2-safe-fix-planning-conflict-resolution.out`
  records all eight `tests/test_check_files.py` cases passing after the
  bytes-first change.
- Milestone 0 full gate evidence:
  `/tmp/{check-fmt,typecheck,lint,test,markdownlint,nixie}-e4b821de-4fc5-4af5-aaed-598160137666-2-2-2-safe-fix-planning-conflict-resolution.out`
  record the final sequentially green gate chain: 214 Python and 332 Rust
  tests, with format, type, lint, Markdown, spelling, and Mermaid checks clean.
- Milestone 0 CodeRabbit evidence:
  `/tmp/coderabbit-stilyagi-2-2-2-safe-fix-planning-conflict-resolution.out`
  records `coderabbit review --agent` completing against `43bd949` with zero
  findings and no rate limit.
- Milestone 1 gate evidence:
  `/tmp/{check-fmt,typecheck,lint,test,markdownlint,nixie}-e4b821de-4fc5-4af5-aaed-598160137666-2-2-2-safe-fix-planning-conflict-resolution.out`
  records the third focused full-chain iteration. Only `make lint` is red:
  `C9102` at lines 74, 87, 95, 100, and 101 plus `R9108` at line 100 of
  `tests/test_ir_view.py`.
- Milestone 1 final gate evidence:
  `/tmp/{check-fmt,typecheck,lint,test,markdownlint,nixie}-e4b821de-4fc5-4af5-aaed-598160137666-2-2-2-safe-fix-planning-conflict-resolution.out`
  records the D-19 exception iteration passing all six gates: 219 Python and
  332 Rust tests, and 17 reviewed snapshots.
- Milestone 1 CodeRabbit evidence:
  `/tmp/coderabbit-e4b821de-4fc5-4af5-aaed-598160137666-2-2-2-safe-fix-planning-conflict-resolution.out`
  records `coderabbit review --agent` completing against `4a3d3ba` with zero
  findings and no rate limit.
- Milestone 2 model-slice red evidence:
  `/tmp/test-e4b821de-4fc5-4af5-aaed-598160137666-2-2-2-safe-fix-planning-conflict-resolution.out`
  records the expected wheel-layout snapshot failure after adding
  `stilyagi/fixes.py`.
- Milestone 2 model-slice green evidence:
  `/tmp/{check-fmt,lint,typecheck,test,markdownlint,nixie}-e4b821de-4fc5-4af5-aaed-598160137666-2-2-2-safe-fix-planning-conflict-resolution-2.out`
  records the complete sequentially green gate chain: 221 Python and 332 Rust
  tests, with 17 snapshots reviewed. CodeRabbit is intentionally deferred until
  the complete Milestone 2 implementation is ready for review.
- Milestone 2 final red evidence:
  `/tmp/{check-fmt,test}-e4b821de-4fc5-4af5-aaed-598160137666-2-2-2-safe-fix-planning-conflict-resolution-4.out`
  records only formatter deltas and the expected wheel-layout snapshot
  addition for `engine/fix_planning`; all other gates were green.
- Milestone 2 final gate evidence:
  `/tmp/{check-fmt,lint,typecheck,test,markdownlint,nixie}-e4b821de-4fc5-4af5-aaed-598160137666-2-2-2-safe-fix-planning-conflict-resolution-5.out`
  records the final sequentially green chain: 226 Python and 332 Rust tests,
  with all 17 snapshots passing.
- Milestone 2 CodeRabbit evidence:
  `/tmp/coderabbit-e4b821de-4fc5-4af5-aaed-598160137666-2-2-2-safe-fix-planning-conflict-resolution-6.out`
  records `coderabbit review --agent` completing with zero findings and no
  rate limit after the final documentation gates passed.

## Deferred follow-ups

Raise these as separate roadmap items; they are **out of scope** here.

1. **Trim the bridge payload.** `nodes` is about a third of the 2.01 MB IR JSON
   for an 87 KB file and no Python code reads it; `trees` is unread too, and
   every `IrSegment` duplicates its containing region's text. Gating these
   behind a debug flag would plausibly cut `stilyagi check` runtime by ~30%. It
   would churn every golden IR snapshot, which is why it is not in this slice.
2. **A fix-planning performance probe.** `tests/performance/structural_probe.py`
   measures only `extract_document`, so it is structurally blind to everything
   this slice builds. A `--probe fix-planning` mode reusing the same
   `ReportPayload` schema and redaction would give 2.3.1 a baseline.
3. **Widen admissibility for markup edits**, so heading-depth and similar rules
   can auto-fix. Needs a provenance-carrying edit model — the engine hands a
   rule a region or node handle and the rule derives offsets from it — rather
   than interval containment. This is rule-API work and belongs with 2.3.1.
4. **Reserve an engine namespace in RFC 0002 §12** covering both the
   fix-error identifiers and the existing unratified `IR000` in
   `engine/checker.py`, and reserve `ALL` as a fixability pseudo-prefix.
5. **`--fixable`, `--unfixable`, `--extend-fixable`, and `--fix-only` flags.**
   Not in RFC 0003 §3.1's guaranteed list, but users will expect them.
6. **Byte-to-character offset mapping for SARIF.** SARIF 2.1.0 supports
   `byteOffset` only for binary artefacts; text artefacts need `charOffset` or
   line/column. The renderer is source-blind today, so roadmap 5.3.1 cannot
   treat SARIF as a pure output adapter without this.
7. **Require the `original_bytes` guard at the collaborator seam.**
   `write_source` accepts `original_bytes` as optional, which keeps it
   assignable to the two-argument `FileWriter` alias
   (`Callable[[Path, bytes], None]`) declared by the `CheckCollaborators`
   bundle that Milestone 0 introduces. The guard is therefore available but not
   compiler-enforced at the call site. When Milestone 5 wires the `writer`
   field into `--fix`, decide whether to require the argument and widen the
   alias, so a caller cannot silently skip the stale-plan check.
8. **First- and second-person pronouns outside `README.md`.** The documentation
   style guide forbids them, but no gate enforces the rule, and 15 tracked
   Markdown files carry 56 matching lines inherited from prior work — including
   one line in `docs/developers-guide.md:1960`. Review feedback on this slice
   named only the pronouns this branch introduced, and those are fixed. A
   repo-wide sweep belongs in a separate editorial change, not here.

## Revision note

**Revision 3, 2026-08-23.** Implementation began after explicit approval. The
PR title and matching Lody session title now identify the implementation rather
than the previously draft-only plan. No technical contract changed.

**Revision 4, 2026-08-23.** Recorded Milestone 0's byte-faithful source path,
collaborator-bundle boundary, red/green evidence, and green full-gate result.
Milestone 1 remains gated on the required CodeRabbit review.

**Revision 5, 2026-08-23.** Recorded Milestone 0's clean CodeRabbit review and
started Milestone 1.

**Revision 6, 2026-08-23.** Marked the plan blocked after Milestone 1 reached
its explicit three-iteration lint tolerance. The remaining failures and
available options are recorded in D-18.

**Revision 7, 2026-08-24.** The post-turn gate explicitly authorized one
focused assertion-remediation iteration, so the plan returned to in-progress
status under the narrow D-19 exception.

**Revision 8, 2026-08-24.** Recorded Milestone 1's complete gate evidence and
the typed IR-view outcome. CodeRabbit review remains required before the next
milestone.

**Revision 9, 2026-08-24.** Recorded Milestone 1's clean CodeRabbit review and
started Milestone 2.

**Revision 10, 2026-08-24.** Recorded the independently gated, atomic Milestone
2 fix-model slice. Its small commit satisfies the repository's rollback policy
without declaring the milestone complete or running CodeRabbit before the
kernel and renderer contract are in place.

**Revision 11, 2026-08-24.** Completed Milestone 2: the production byte-splice
kernel is now normative, its four independent properties pass, the legacy
round-trip adapter delegates to it, the engine fix stub is retired, and
versioned renderer fix data is stable. The full deterministic gate chain is
green; the required CodeRabbit review remains the boundary before Milestone 3.

**Revision 12, 2026-08-24.** Recorded Milestone 2's clean CodeRabbit review and
started Milestone 3.

- **D-23: Adapt to the gates `main` gained while this branch was stacked.**
  `configure-df12-lints` squash-merged into `main`, which has since added a
  blocking Skylos dead-code gate over `python/stilyagi` (tests excluded), moved
  to Ruff 0.16.4, and moved to `ty` 0.0.74. Three consequences for this work.

  First, Ruff 0.16.4's larger default set enforces two blank lines between
  top-level definitions, which the entity-aware merge driver had dropped while
  replaying the rebase. Reformatting is mechanical.

  Second, Skylos correctly reports the milestone 3 planner as dead.
  `plan_fixes`, `FixPlanRequest`, `_validate_candidates`, and
  `_overlap_rejection` are reachable only from tests, because their production
  caller is the `--fix` pipeline in milestone 4. They carry documented
  allow-list entries naming that pipeline. **Delete all four in milestone 4
  once the pipeline calls the planner**; leaving them would suppress genuine
  dead code later.

  Suppressing rather than leaving the gate red is a deliberate trade. A
  permanently failing gate reports nothing about code added afterwards, so four
  narrow documented exceptions keep the gate live for everything else. The
  honest cost is that each entry asserts a caller that does not exist yet,
  which is why the reasons name the milestone and why removal is recorded here
  as a milestone 4 obligation rather than left to memory.

  Adding those entries also required splitting
  `tests/test_skylos_lint_contract.py`, which sat at 399 lines against the
  400-line cap, so *any* new exception broke it. The allow-list constant and
  its configuration test moved to `tests/test_skylos_whitelist_contract.py`;
  the Makefile and command-shape contracts stayed put. That unblocks the next
  exception too, rather than only this one.

  Third, `TextEdit.insert_after` and `TextEdit.delete` were removed rather than
  suppressed, which is a real improvement the gate surfaced. Neither had any
  caller, and the gate's stated policy is to treat a finding as a candidate for
  removal until its caller is verified. Skylos also matches bare names, so
  allowing `delete` would have registered a blanket rule, and roadmap 2.2.3 adds
  `stilyagi clean` — a subsystem very likely to hold a `delete` of its own
  that the rule would then silently hide. `replace` remains because planner
  tests exercise it. `insert_before`, `insert_after`, and `delete` should
  return in roadmap 2.3.1 only alongside the first rule that calls each form,
  which is the point at which a verified caller exists. RFC 0002 and RFC 0005
  now show the equivalent direct `TextEdit` construction. Update this plan's
  Interfaces section before the next implementation milestone. Date/Author:
  2026-08-25, rebase onto `main`.

- **D-24: Validate the containing segment before decoding it for D-12's
  provenance cross-check.** Rationale: an edit can sit on valid UTF-8
  boundaries within an IR segment that itself starts inside a code point, so
  validating the edit alone leaves `.decode()` able to raise. Likewise, Python
  truncates an out-of-bounds slice, allowing a malformed segment to appear to
  match its claimed text. Bounds and UTF-8 alignment therefore apply to the
  segment as well as the edit; a decode error is an ordinary provenance
  mismatch and aborts mutation. Date/Author: 2026-09-07, implementation.

- **D-25: Resolve the Milestone 4 gate-tolerance pause with the post-turn
  correction.** Evidence: the first full-gate attempt failed formatting for
  `tests/test_fix_diff.py`; after formatting, the second failed its subprocess
  command policy; the third isolated two missing explicit `shell=False`
  arguments. The post-turn gate explicitly directed the correction. The custom
  rule requires the repository's documented exception for fixed Git commands,
  even with `shell=False`; the core and rebase gate chains then passed. Date/
  Author: 2026-09-07, implementation.

- **D-26: Pass one immutable request from CLI checking to the diff planner.**
  Rationale: the preview requires six values that must stay correlated — the
  original bytes and decoded text, reported path, extracted document, rule
  diagnostics, and effective lint configuration. `DiffRequest` keeps that
  boundary explicit, leaves `run_check` at its two-argument public contract,
  and prevents a later caller from re-reading or normalizing source. The
  planner's rejections become `FixError` values so renderers expose them on a
  channel distinct from selectable rule diagnostics, as D-07 requires. Date/
  Author: 2026-09-07, implementation.
- **D-27: Inline the writer callable rather than name it with an alias.**
  Rationale: no alias spelling passes both Pylint stages. `df12-pylint` under
  CPython 3.14 enables R9112 and demands the PEP 695 `type` statement for a
  module-level alias; `pylint-pypy` under PyPy 3.11 cannot parse that statement
  and, because `syntax-error` is disabled, silently skips the whole module
  instead of failing. A plain assignment satisfies the PyPy stage but trips
  R9112, so the two cannot both be satisfied. The annotation had one use site,
  so inlining the `cabc.Callable[[pathlib.Path, bytes], None]` type at the
  field removes the construct rather than suppressing either rule, and `cli.py`
  stays visible to the Pylint coverage that catches `too-many-lines`.
  Date/Author: 2026-09-25, implementation.

**Revision 13, 2026-08-24.** Recorded the committed Milestone 3 planner slice
and the in-progress corpus-backed Stage C2 property coverage. The focused suite
passes; the full deterministic chain and required CodeRabbit review remain the
boundary before Milestone 4.

**Revision 14, 2026-08-24.** Marked the plan blocked after all three permitted
full-gate attempts hit the same PyPI DNS failure in the required PyPy Pylint
tier. A later explicit owner request preserved the completed Stage C2 work in
local commit `76da310`; it does not constitute a green gate result. CodeRabbit
was not requested.

**Revision 15, 2026-08-24.** Rebasing onto `configure-df12-lints` retained its
locked `ty` type-checking configuration, configuration-map validation, and
lockfile. The older replayed Pyright configuration was removed rather than
leaving two incompatible type-checking toolchains.

**Revision 2, 2026-08-16.** Revised after a six-lens design review. What
changed and why:

- **Added byte-faithful reads (D-10), now Milestone 0.** The review found that
  `Path.read_text` translates CRLF to LF before extraction, so the IR's byte
  offsets already do not match the bytes on disk for CRLF files. Under `--fix`
  that becomes silent whole-file line-ending rewriting. This was the most
  severe finding and it was absent from revision 1.
- **Added a verification re-lint (D-13).** Revision 1's exit-code contract was
  not implementable in a single pass without assuming a fix removes its own
  diagnostic.
- **Moved planning rejections off the rule-code namespace (D-07).** `FIX001`
  through `FIX003` collide with Ruff's flake8-fixme at the same numbers, and as
  rule codes they would be suppressible and would have to satisfy
  `stilyagi rule`/`stilyagi rules` contracts they cannot.
- **Added `__post_init__` coercion and the `TextEdit` constructors.** Revision
  1's model would have crashed on RFC 0002 §4's own worked example.
- **Added JSON versioning and pinned `fix_applicable` (D-14)**, added the
  segment-text cross-check (D-12), two-phase execution (D-16), the stdin and
  symlink guards, and the `--unsafe-fixes` discoverability affordance (D-15).
- **Corrected the diff recipe.** Revision 1's `lineterm=""` produces a patch
  `git apply` rejects as corrupt; the review reproduced it.
- **Removed the Rust reconciliation milestone (D-11).** Revision 1 claimed the
  Rust helper contradicts RFC 0002 §10. It does not — the clause says "MAY
  coalesce", so a stricter helper is conforming and is a better test oracle.
  Only a documentation comment remains.
- **Mandated the module decomposition and the request objects.** Measured gate
  thresholds show the monolithic pipeline is unbuildable: ten decision points
  against a budget of seven.
- **Reordered milestones** so the typed IR view lands first and the only
  data-destroying capability lands last, after every invariant is proven.
- **Corrected the property-test design.** Revision 1's untouched-bytes property
  was tautological and its admissibility property was both weaker than the rule
  and unexercisable by its own generator.

Revision 1 was written from reconnaissance of the existing pipeline, the IR
span model, and the repository's gate conventions, with prior art from Ruff's
`apply_fixes` and `Applicability` model.

**Revision 16, 2026-08-25.** Rebased onto `main` after `configure-df12-lints`
squash-merged, dropping the duplicated base commits. Two conflicts were
resolved in favour of keeping both sides: `main` had narrowed the extraction
`except` in `_check_one_file` so unexpected failures re-raise instead of
becoming exit 2, and that narrowing is preserved alongside this branch's
byte-faithful read and `rule_runner` seam; `engine/__init__.py` keeps `main`'s
`BridgeExtractionError` export alongside this branch's `FixPlan` stub
retirement. Stale dependency pins were resolved in favour of `main`. See D-23
for the gate changes this rebase had to absorb.

**Revision 17, 2026-09-07.** Renamed the working branch to `xxx`, tracking
`origin/xxx`, and corrected D-12's implementation so a malformed containing
segment cannot crash or bypass provenance validation. Two planner regressions
provide red/green evidence. Milestone 3 remains blocked on the full gate chain
and CodeRabbit review.

**Revision 18, 2026-09-07.** Recorded the green Milestone 3 gate chain and
CodeRabbit review for commit `f9cb8ae`; the planner's malformed-containing-
segment correction is accepted and Milestone 4 may begin.

**Revision 19, 2026-09-07.** Marked Milestone 4 blocked after its standalone
diff-renderer slice reached the three-attempt gate tolerance. The focused tests
pass, but the complete gate chain remains red on two explicit `shell=False`
test-command policy findings; no CLI work or CodeRabbit review may proceed
without further direction.

**Revision 20, 2026-09-07.** The post-turn gate explicitly directed the two
subprocess findings to be fixed. The custom rule requires the repository's
documented exception for fixed Git commands even when `shell=False` is present,
so the tests follow that local convention while retaining a resolved Git
executable. The wheel-layout snapshot was updated for `diff.py`. Milestone 4
remains subject to a green full gate chain before its CLI work or CodeRabbit
review.

**Revision 21, 2026-09-07.** Rebasing `xxx` onto `origin/main` replayed all 22
commits without conflicts. The updated Python dependency pins and both lock
files come from `main` unchanged, as required. RFC 0006 introduces editorial
policy vertical slices but changes no safe-fix contract, helper or boundary.

**Revision 22, 2026-09-07.** The rebase gate found `TextEdit.insert_before` had
no production caller. Removed the dead constructor rather than adding a broad
Skylos exemption, and updated the two RFC examples to use the equivalent
byte-span construction. `TextEdit.replace` remains a tested helper.

**Revision 23, 2026-09-07.** Completed the Milestone 4 CLI integration slice.
`cli_io.py` keeps the byte-faithful input boundary out of the already-large CLI
module; `fix_pipeline.py` turns a checked source into a safe diff preview via
an immutable request. `--diff` reserves standard output for patches and sends
diagnostics and `fix-error` reports to standard error. The focused tests and
reviewed snapshots pass. The full milestone gate chain is green (275 Python
tests and 18 snapshots); CodeRabbit remains pending.

**Revision 24, 2026-09-07.** CodeRabbit reviewed Milestone 4 commit `ebbcac7`
on draft PR #138 after its full deterministic gate chain and returned zero
actionable findings. Marked Milestone 4 complete; Milestone 5 may begin.

**Revision 25, 2026-09-07.** Started Milestone 5 with its destructive boundary
in isolation. `write_source` resolves file symlinks, skips byte-identical
writes, creates the temporary beside the target, copies metadata, and replaces
atomically. Focused red/green tests and the wheel-layout snapshot cover those
contracts; command execution is deliberately deferred until the writer gates.

**Revision 26, 2026-09-07.** Skylos correctly identified the staged atomic
writer as unreachable before the Milestone 5 `--fix` pipeline exists. Added
narrow, documented entry-point exceptions for `write_source` and its private
temporary-file helper. Remove both as soon as the pipeline calls
`write_source`; the full gate stays live for every other production symbol.

**Revision 27, 2026-09-24.** Actioned the review feedback on the rebased branch.
`unified_diff` now splits on LF alone, because `str.splitlines` breaks on `\r`,
`\v`, `\f`, `\x1c`-`\x1e`, `\x85`, and the Unicode line and paragraph
separators, which Git does not treat as line endings; each such character
previously produced a spurious mid-hunk `\ No newline at end of file` marker
that made `git apply` reject the patch. `write_source` gained the
`original_bytes` stale-plan guard described in follow-up 7, and stages its
replacement through `tempfile.mkstemp` so a failed write leaves no partial file
beside the target. Three refactors brought CodeScene measurements back in line:
`run_check` aggregates per-file results through `_aggregate_checked_files` (79
to 63 lines, complexity 13 to 5), `_add_check_arguments` in `cli_args.py`
splits its verbosity and target groups into helpers (71 to 62 lines), and three
duplicated provenance tests became one parametrized test. Four symbols left the
Skylos whitelist after the live `--diff` path proved to reach them. On the
review's own gate: interrogate needs 100% docstring coverage over
`python/stilyagi tests`, so the two nested dunder methods on the test's
`_FailingStream` helper now carry docstrings, and `mdtablefix` reflowed the new
developer-guide prose. Follow-ups 7 and 8 record the two decisions deliberately
left out of scope.

Two further failures surfaced only once the lint target stopped aborting at
interrogate. Pylint's `pylint-pypy` pass rejected the five-parameter
parametrized test with R0913/R0917 against `max-args = 4`, a limit Ruff exempts
for `**/test_*.py` but Pylint does not; removing the redundant `label`
parameter, whose value duplicated the pytest id, brought it to four. Then the
Skylos dead-code gate rejected `SourceChangedOnDiskError`, which this slice
introduces but nothing reachable raises until the `--fix` pipeline exists. That
is the same staged-unreachable pattern as `write_source`, so it takes the same
narrow, documented exemption, recorded in all three places the whitelist
contract test compares (`[tool.skylos.whitelist].names`, its `.documented`
table, and `_REQUIRED_SKYLOS_WHITELIST_NAMES`). Remove it with the other two
when Milestone 5 wires the writer.

All nine `make lint` stages now run to completion and pass, alongside
`check-fmt`, `typecheck`, `test`, `markdownlint`, and `nixie`. `cli.py` then
reached 412 lines, past the configured `max-module-lines = 400`. The ceiling is
not unenforced — this slice had blunted the check that enforces it.

The gate runs Pylint under PyPy 3.11 via `pylint-pypy`
(`PYLINT_PYTHON ?= pypy`), and PyPy 3.11 cannot parse PEP 695 type aliases.
`pyproject.toml` explicitly disables `syntax-error` in the `pylint` pass, with
the comment that this keeps "PyPy-backed Pylint useful on files it can parse".
An unparsable module is therefore skipped silently, and the stage still exits
0. Before this slice, `cli.py` contained no PEP 695 syntax and Pylint saw it; on
`origin/main` the same probe reports
`C0302: Too many lines in module (344/10)`. The slice added
`type FileWriter = cabc.Callable[[pathlib.Path, bytes], None]`, after which
`C0302` could no longer fire at any length. The line growth and the loss of
coverage had the same cause.

Rewriting the alias as a plain assignment does not settle it. The two Pylint
stages demand opposite forms of the same construct: `df12-pylint`, running
under CPython 3.14, enables `R9112` (`prefer-type-statement`), which flags a
plain alias and requires the PEP 695 statement; `pylint-pypy`, running under
PyPy 3.11, cannot parse that statement. Either spelling fails one stage, so the
alias was removed and its one use site annotated inline. `FileWriter` had a
single reference, so nothing was lost, and `cli.py` is now visible to the gate
again while both Pylint stages rate it 10.00/10. This is a standing constraint
worth remembering: on a Python 3.12+ baseline, an alias in a PyPy-covered
target must satisfy a rule that the PyPy parser cannot even read.

`tests/test_package_skeleton_units.py` and `tests/test_config_resolution.py`
are genuinely invisible for the same reason, but they are pre-existing: both
exceed 400 lines on `origin/main` (642 and 471) and both already carried PEP
695 aliases there. `tests/test_makefile_recipes.py` sits exactly at the ceiling
(Pylint counts 400, not 401) and does parse, so it is not a further exception.
Two caveats belong with this finding: the ceiling holds only for modules Pylint
can parse, and a `type` alias introduced anywhere in `python/stilyagi tests`
silently exempts its whole module from every Pylint check, not just
`too-many-lines`. Ruff does not constrain the choice: `UP` is selected, but
`UP040` (`non-pep695-type-alias`) fires only on the explicit
`X: TypeAlias = ...` annotation, so it flags neither spelling. Verified by
running `ruff check` on the module with `UP` selected and again with `UP040`
requested directly, both clean.

**Revision 28, 2026-09-25.** Committed the review feedback as `bd308f5` and
pushed it to the PR branch. Two loose ends surfaced while reconciling the gate
evidence, and both are recorded here because they will recur.

The first is `typos.toml`. It appeared modified with fourteen ignore patterns
belonging to unrelated projects (`HashiCorp`, `AppFactory<Ser`, `var.iamge_id`,
`currentColor`), which looked at first like another session's work leaking into
this worktree. It is not. The gate's own subcommand help states that it "always
runs in write mode", the `markdownlint` log prints `refreshed: typos.toml`
unconditionally, and `bf8b783` records the design decision behind that: the
configuration is regenerated from the live shared dictionary on every run, so
"the drift check and the separate write target are no longer meaningful". The
committed copy is therefore a rendered artefact, not an input.
`typos.local.toml` is the repository's actual overlay, and
`docs/developers-guide.md` is explicit that `typos.toml` is never hand-edited
and never checked for drift in continuous integration. Nothing reads the
committed blob: there is no `--check` invocation anywhere in the Makefile,
workflows, or scripts, and no test asserts on it. The file was restored so this
slice stays scoped to the review, and the fourteen extra lines are upstream
dictionary growth that will reappear on the next spelling run; that is expected
and should not be committed as part of unrelated work.

The second is gate coverage, and it is a process lesson rather than a code one.
A gate run is only evidence about the tree it actually read. Two things make
that easy to get wrong here. First, `mdtablefix` is the last step of
`check-fmt`, and it reflows Markdown, so prose written *after* a gate run
leaves that run stale — and prose that describes the run is written after it by
construction. Second, an edit made while a gate is executing invalidates its
result, and the logs give no warning: the run simply reports a verdict about
content that no longer exists. The working rule is to finish and commit every
line of prose first, confirm `make check-fmt` is clean, and only then start the
full sequential chain — with the tree left untouched until it ends. Notes
recording a gate run cannot usefully sit inside the change set that run is
meant to validate.

For reference, the nine `make lint` stages are ruff, interrogate, pylint-pypy,
df12-pylint, ambrleaks, cargo doc, clippy, whitaker, and skylos. Spelling is
not among them: it is a prerequisite of `markdownlint`
(`markdownlint: tools-docs spelling`), as `AGENTS.md` records.

**Revision 29, 2026-09-25.** Closed the gate-coverage question left open by
Revision 27. The 400-line ceiling was not unenforced; this slice had blinded
the check that enforces it, and the correction is in D-27. `cli.py` reached 412
lines because `bd308f5` added a PEP 695 `type` alias, and PyPy 3.11 — the
interpreter behind the `pylint-pypy` stage — cannot parse that syntax. Because
`syntax-error` is disabled in the pass, the module was skipped silently at
10.00/10 and exit 0, so the very check that should have caught the growth went
quiet. On `origin/main`, which has no PEP 695 syntax, the same probe reports
`C0302: Too many lines in module (344/10)`.

The resolution is to inline the type at its single use site rather than to
choose an alias spelling, because no spelling passes both Pylint stages:
`df12-pylint` under CPython 3.14 enables `R9112` and requires the PEP 695
statement, while `pylint-pypy` cannot read it. Inlining removes the construct
instead of suppressing a rule, which is what the owner's instruction asks for.
The two stdin helpers move to `cli_io.py`, whose docstring already owns
byte-faithful check inputs, returning `cli.py` to 392 lines. That move also
promoted `import pathlib` from `TYPE_CHECKING` to a runtime import in
`cli_io.py`; under `TYPE_CHECKING` it raised `NameError` at call time, which
Ruff's `runtime-import-in-type-checking-block` caught before any test did.

Verified on the frozen commit `c9f0506`, which is the extraction commit after a
`mdtablefix` reflow was folded into it by amend: `check-fmt`, `lint`,
`typecheck`, `test` (591 passed, 1 skipped), `markdownlint`, and `nixie` all
pass, a reduced-ceiling probe confirms `C0302` fires on `cli.py` again, and
both Pylint stages rate it 10.00/10. CI run `36070936581` is green on all four
legs. A follow-up commit `8813e28` qualifies the `cli_args.py` location of the
`_add_check_arguments` refactor, whose 71-to-62 figure was misread during
review as belonging to `cli.py`; AST measurement confirmed the figure itself
was right, against 66 lines on `origin/main`. CI run `36071672467` is green on
all four legs for that head.

Two further findings are recorded rather than fixed, because both pre-date this
branch. `tests/test_package_skeleton_units.py` (642 lines) and
`tests/test_config_resolution.py` (471 lines) exceed the 400-line ceiling on
`origin/main` and carry PEP 695 aliases there, so they are invisible to the
same Pylint stage for the same reason. They are not this slice's regression and
correcting them means splitting two large test modules, which belongs in its
own change. The mechanism is worth stating plainly for whoever picks that up:
any `type` alias in a module under `python/stilyagi tests` exempts that module
from every Pylint check, not only `too-many-lines`.

**Revision 30, 2026-09-27. Rebase onto `origin/main` (`7fdcff3`):
reconnaissance and plan.** The owner asked for this branch to be rebased onto
the remote target of PR #160 and for a plan to be formulated before any
conflict is acted on. This revision records the reconnaissance, because it
corrected three assumptions that an earlier reading of the same evidence had
produced, and each correction changes what the replay must do.

Frozen identities: `OLD_HEAD` `c56efe8`, `MERGE_BASE` `11e6026`, `TARGET`
`7fdcff3`. The replay range is `11e6026..c56efe8`, 36 commits, linear
(`git rev-list --merges` is empty), and every commit in it compiles, which is
what makes a per-replay `compileall` guard safe to attach. The remote branch
head was `c56efe8` at reconnaissance time, so the eventual force-with-lease is
bound to a known-good value rather than a blind one. Recovery refs are created
under `refs/recovery/2-2-2-.../` for all three identities; the pre-existing
`20260924T201350Z` refs are left in place.

Three corrections, in the order they matter:

*Correction 1 — the split relocated the edited function, it did not delete it.*
The earlier reading held that main's #163 split moved branch-relevant
assertions into files the branch never touches, and that
`test_package_skeleton_extraction.py` therefore breaks the rebased branch. Half
right. `engine/fixes.py` was a **main-only** file at the merge base, and the
**branch deletes it** (`D python/stilyagi/engine/fixes.py`) while adding
`engine/fix_planning/` and `engine/fix_pipeline.py`. Main itself never touches
`python/stilyagi/engine/` in `11e6026..7fdcff3`, so it still exports `FixPlan`
from a module the branch removes. The real defect is narrower and sharper than
"new files assert removed APIs": main's split **relocated**
`test_engine_skeleton_dataclasses_preserve_their_fields` from
`test_package_skeleton_units.py:148` to
`test_package_skeleton_extraction.py:32`, and the branch's only edits to that
function — dropping the `engine.FixPlan(applicability=...)` assertion and
updating the renderer string — were made in the *old* file at the *old* line. A
textual three-way merge of `test_package_skeleton_units.py` therefore cannot
carry them: the branch's hunk has no counterpart in the file main kept, and the
file main created arrives fresh from main with the pre-branch assertions intact.

*Correction 2 — there are 13 alias-bearing modules, and the lint tier change is
what exposes them.* `4c0c0a7` (#163) removed the `pylint-pypy` stage. Under it,
`syntax-error` was disabled and any module containing a PEP 695 `type`
statement was **skipped silently at 10.00/10, exit 0** — the trap Revision 29
documents. With the tier gone, `make lint` runs Pylint on managed CPython 3.14
and parses those modules for the first time. Thirteen modules carry a
module-level alias, and two of them exceed the 400-line ceiling at `c56efe8`:
`tests/test_package_skeleton_units.py` (638) and
`tests/test_config_resolution.py` (471). Both are exactly the modules Revision
29 recorded as "not this slice's regression", recorded on the assumption that
correcting them belonged in its own change. That assumption survives the tier
removal only if the rebased branch does not have to pass the new gate over them
— and it does. The branch owns one of the two: it modifies
`test_package_skeleton_units.py` (638 lines, alias at line 23) and never touches
`test_config_resolution.py`, which main already split to 236. So the branch
must not reintroduce main's 471-line version, and must bring its own 638-line
file under the ceiling. This is new work the rebase creates, not a merge
conflict, and it is the reason a clean replay would still fail `make lint`.

*Correction 3 — `tests/test_renderers.py` needs nothing.* The earlier reading
listed it as a second landmine. The branch already updated it: the diff at
`11e6026..c56efe8` rewrites both the `render([], "text")` assertion and the
`"3 diagnostics found"` case to the fix-count spelling, and imports
`Fix, TextEdit` from `stilyagi.fixes`. Main never touches the file. It replays
clean.

The textual conflict surface is exactly three paths, confirmed twice — once by
the pairwise diff, once by `git merge-tree` — and `pyproject.toml` is not
really one of them:

| Path                                   | Branch change                                                               | Main change                                      | Shape                                       |
| -------------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------ | ------------------------------------------- |
| `pyproject.toml`                       | skylos whitelist entries (+3 names, +3 `.documented` reasons) near line 384 | removes the `syntax-error` disable near line 214 | disjoint regions; `merge-tree` auto-merges  |
| `docs/developers-guide.md`             | §2b rewrite (102+/15−)                                                      | 55+/41− revision                                 | overlapping prose; `merge-tree` auto-merges |
| `tests/test_package_skeleton_units.py` | re-export list, renderer string, drops `FixPlan` assertion                  | split 642→157, rest relocated                    | **genuine conflict**; only real one         |

`git merge-tree --write-tree HEAD 7fdcff3` reports a conflict in exactly one
file, `tests/test_package_skeleton_units.py`, and auto-merges the other two.
That is the aggregate shape; a replay can still stop per-commit on the same
paths, so the resolution below is written to apply at whichever commit stops.

Resolution plan, in the order it will be executed:

1. Replay with `--merge --no-fork-point --no-update-refs --no-autostash
   --reapply-cherry-picks --keep-empty --empty=stop --onto 7fdcff3 11e6026`
   under `-c merge.conflictStyle=zdiff3`, with a per-replay
   `--exec 'python -m compileall -q -f python/stilyagi'` guard. Weave is
   registered globally (`WEAVE_EVENT=1 weave-driver %O %A %B %L %P`, 0.5.1) but
   is **not selected** for any of the three paths — `git check-attr merge`
   reports `unspecified` for all three and there is no tracked
   `.gitattributes` — so Git's built-in merge applies and no driver override is
   needed. The guard is justified because all 36 commits compile at `OLD_HEAD`;
   `__pycache__` is gitignored, so it cannot dirty the tree. Under the Weave
   policy this is the ambient-selection case handled by *not opting in*, and
   the decision is recorded here rather than left implicit.
2. `tests/test_package_skeleton_units.py`: take main's split file as the base
   (157 lines) and port the branch's three edits into it — drop `FixPlan` from
   the re-export list, update the renderer string to
   `"0 diagnostics found (0 safe fixes, 0 unsafe fixes)\n"`, and reduce the
   module to main's structure otherwise. Delete the `engine.FixPlan` assertion,
   which asserts an API the branch removes.
3. `tests/test_package_skeleton_extraction.py` (arrives from main, untouched by
   the branch, therefore **not** a merge conflict — a post-replay repair):
   apply the same two edits to the relocated
   `test_engine_skeleton_dataclasses_preserve_their_fields` at line 32, and
   give the file an equivalent alias strategy, since it carries `type JSONType`.
4. `pyproject.toml`: take main's `syntax-error` removal (the tier it existed for
   is gone) and keep the branch's skylos whitelist entries. The two regions are
   disjoint, so this is a review of the auto-merge, not a hand resolution.
5. `docs/developers-guide.md`: reconcile the branch's §2b against main's
   revision; review rather than assume, since `merge-tree` auto-merges it.
6. Post-replay, bring `tests/test_package_skeleton_units.py` under 400 lines —
   requirement (2) above lands it at main's 157 plus the branch's edits, so
   this may already be satisfied; verify rather than assume. Confirm
   `tests/test_config_resolution.py` is main's 236-line version.
7. Re-examine `cli.py` under the single-tier lint. Revision 29 inlined the
   writer type at its one use site because no alias spelling passed both tiers.
   With `R9112` and the CPython pass now the only tiers, that constraint is
   gone, and `df12-pylint` may require the `type` statement instead. Re-run and
   follow the gate.
8. Gate: `make check-fmt`, `make test`, `make typecheck`, `make lint`, plus
   `markdownlint` and `nixie` for the Markdown-touching commits. Then
   `range-diff 11e6026..c56efe8 7fdcff3..NEW_HEAD`, the semantic audit for
   unintended deletions and repeated blocks, commit, and force-with-lease bound
   to `c56efe8`.

The three corrections are the substance of this revision. Corrections 1 and 2
share a structure worth naming: both are cases where a main-side change made an
existing branch assumption false without touching the branch at all, and
neither would have surfaced from a textual conflict — correction 1 because the
merge succeeds and only the *test* fails, correction 2 because the merge
succeeds and only the *lint* fails. A rebase here cannot be accepted on
`merge-tree` exit status, on a clean replay, or on `git range-diff` alone.

**Revision 30 (continued), 2026-09-27. Rebase executed; outcome and the one
prediction that failed.** The replay ran to completion: 37 commits replayed onto
`7fdcff3`, `NEW_HEAD` `8ee6911`, plus one follow-up repair commit `52b8c26`.
Recovery refs for `old-head`, `new-head`, `merge-base`, and `target` are under
`refs/recovery/2-2-2-.../`; the `20260924T201350Z` set is preserved.

Resolution as executed. The replay stopped exactly where predicted, at
`9759afd` on `tests/test_package_skeleton_units.py`, and nowhere else. The
three stages were base 642 lines, ours 157 (main's split, byte-identical to
`7fdcff3`), theirs 638. Resolution took stage two and applied the single edit
whose target function survived the split — dropping `"FixPlan"` from the
re-export list — and deferred the other two edits to `52b8c26`, which applies
them to `test_package_skeleton_extraction.py` where main moved the function.
`range-diff` reports 36 of 37 commits with identical patches and flags
`9759afd` alone, which is precisely this split of one commit's edits across the
replay and the repair. That is the expected signature of the resolution, not a
defect.

Audit results. All three semantic checks pass. Every one of the 19 target-only
paths is byte-identical at `NEW_HEAD`. The only deletion against the target is
`python/stilyagi/engine/fixes.py`, which the branch deletes at `9759afd` and
which main never touched. The repeated-block scan's six hits were all false
positives of the detector: each is a single three-line function whose five-line
sliding window overlaps itself, confirmed by counting definitions.
`pyproject.toml` resolved as planned — main's `syntax-error` removal taken, the
branch's skylos entries kept — and `docs/developers-guide.md` auto-merged
without residue. All six gates pass: `check-fmt`, `typecheck`, `lint` (both
Pylint stages 10.00/10), `test` (608 passed, 1 skipped), `markdownlint`,
`nixie`.

**Correction 2's prediction failed, and that is the finding worth recording.**
Revision 30 predicted that removing the `pylint-pypy` tier would expose the
branch's PEP 695 aliases to genuine linting and that `make lint` would
therefore fail on module length. It did not. The prediction assumed the alias
trap was still latent in *this* tree; in fact the branch's own
`test_package_skeleton_units.py` was already under the ceiling at 638 lines
only on the pre-split file, and the rebased result inherits main's 156-line
split. The alias count was right (12 modules, 15 aliases now parsed) and the
consequence was wrong.

Because "a gate passed" is exactly the evidence that proved unsound in Revision
29 — where the check silently skipped the module — the green result was not
accepted on its own. A positive control was run against the project's exact
Pylint invocation: a synthetic 1266-line module carrying a `type` alias reports
`C0302: Too many lines in module (1266/400)`, identical to the same module
without the alias, and no `invalid-syntax`. The ceiling is genuinely armed
under the new tier, so the passing lint is real evidence rather than the
earlier silent skip. The lesson generalizes: after a change to a *gate's
configuration or interpreter*, a green result from that gate is not
self-validating, and the cheap way to make it trustworthy is to run the gate
against a fixture that must fail.

**Revision 31, 2026-09-28.** Began the `python/stilyagi/cli.py` "Overall Code
Complexity" remediation requested for PR #160. Head verified before editing:
local, `origin`, and the PR head all matched at `0e17ee3`, working tree clean.

**Baseline, measured rather than asserted.**
`cs review python/stilyagi/cli.py --output-format json --pretty` reports
`score: 9.38` with `indication: 2` on the category "Overall Code Complexity";
`cs check` repeats it as `warn: .../cli.py:1: Overall Code Complexity`. Across
the whole package only `cli.py` carries this finding — every other module
reviews clean at 10.00. The rule set names the threshold directly:
`cs rules-config list-thresholds --language Python` gives
`file_mean_cyclomatic_complexity_warning = 4`.

**CodeScene's metric was recovered by experiment, because the free CLI exposes
no per-function breakdown.** A first attempt counted branches with a local AST
walk; it disagreed with CodeScene on two of 45 modules and was discarded rather
than tuned. The replacement is model-free. A module with `n` functions summing
to `S`, padded with `K` helpers of true complexity `c`, has
`mean(K) = (S + cK) / (n + K)`, so the flag boundary is an equation in `S` and
`n`: padding with `c = 3` from a flagged module makes the smallest *clean* `K`
exactly `S - 4n`, and padding with `c = 5` from a clean module makes the
smallest *flagged* `K` exactly `4n - S + 1`. Both recoveries are exact.

Three findings came out of building and validating that instrument, and all
three are invisible in the rule-set JSON:

1. **The flag has a second condition.** A module with six or fewer functions is
   never flagged, whatever its mean: `N = 6` at mean 9 is clean, `N = 7` at
   mean 5 is flagged. The boundary is pinned by bisection over the function
   count at two different means, and confirmed not to be a line-count effect
   (adding 80 inert lines to the six-function module leaves it clean).
2. **The counting rules are not a naive AST walk.** `if`, `for`, `while`,
   `except`, comprehensions, and `and`/`or` *in any position* count;
   conditional expressions, `assert`, `with`, `match`, and comprehension
   filters do not. Two earlier probes were invalid and were rewritten rather
   than believed: one emitted `if` statements with no bodies (a syntax error
   whose "not counted" result was an artefact), and another sat exactly on the
   `> 4` boundary, where four occurrences give a mean of exactly 4 and so
   cannot distinguish "counts" from "does not count".
3. **The instrument validates before use.** Seven synthetic modules with sums
   known by construction are recovered exactly. One of the original seven
   failed — `truth_7_6`, mean 7.0 reported clean — and that failure is what
   exposed finding 1; the case was moved to `n >= 7` and the precondition is
   now enforced in code rather than assumed.

**Baseline for `cli.py`, recovered with the validated instrument:** 11
functions, complexity sum **54**, mean **4.9091** against a threshold of 4. Per
function:

| line | function                    | cc  |
| ---- | --------------------------- | --- |
| 68   | `main`                      | 3   |
| 96   | `_configure_logging`        | 4   |
| 104  | `_build_cli_overrides`      | 5   |
| 124  | `_resolve_config`           | 3   |
| 138  | `run_check`                 | 4   |
| 213  | `_aggregate_checked_files`  | 7   |
| 240  | `_resolve_collaborators`    | 6   |
| 253  | `compute_exit_code`         | 3   |
| 284  | `_discover_targets`         | 8   |
| 309  | `_resolve_discovery_config` | 3   |
| 333  | `_check_one_file`           | 8   |

**`CheckCollaborators.writer` is confirmed dead.**
`grep -rn '\.writer\|writer='` over `python/` and `tests/` returns no
reference: the field is declared at `cli.py:54` and never read, and
`_ResolvedCheckCollaborators` has no writer field at all. It is the
"ineffective seam" the review named, and Deferred follow-up 7 already
anticipated the decision: the alias cannot enforce the stale-plan check that
Milestone 5 needs, so the field goes rather than waiting for a caller that
would silently skip the guard.

**Planned work.** Replace the anonymous per-file tuple with a named, typed
result; make aggregation a single readable pass; move the cohesive per-file
workflow out of `run_check` into a `cli_pipeline` module that depends only
inward (`config`, `engine`, `rules`, `diagnostics`, `model`) and is imported by
`cli`, never the reverse; give `cli_io.read_source` a typed error instead of a
logging, printing, `None`-returning API that swallowed `OSError`; and route the
expected failures at the command boundary through an injectable reporter.

**Revision 32, 2026-09-28. The `cli.py` complexity refactor is implemented, and
its first gate run found work.** The module split is now:

| module            | lines | owns                                           |
| ----------------- | ----- | ---------------------------------------------- |
| `cli.py`          | 263   | discovery, rendering, streams, exit status     |
| `cli_pipeline.py` | 276   | the per-file workflow and the aggregation pass |
| `cli_config.py`   | 98    | option-to-config translation, shared by both   |
| `cli_io.py`       | 176   | byte-faithful reads and the default reporter   |

`cli_config` exists so `cli_pipeline` never imports `cli`: the dependency
direction runs inward, and both modules depend on the translation rather than
on each other. All four are far below the 400-line module ceiling.

**Requirement-by-requirement outcome.**

1. The anonymous `tuple[list[Diagnostic], bool, DiffPreview | None]` is gone.
   `check_one_file` now returns a named `FileCheck`, wrapped by `CheckedFile`
   so the reported path travels with its result.
2. `aggregate_checked_files` is one pass that extends diagnostics, ors the
   failure flag, and appends each preview's patch and refusals. File,
   diagnostic, fix-error, and patch order all follow discovery order, and any
   failed file raises the run's `error` flag.
3. The per-file workflow moved wholesale into `cli_pipeline`. `run_check` now
   does discovery, then `collect_checked_files`, then renders — with rendering
   split out into `_render_and_exit` so the exit-status decision is visible in
   one screen.
4. `read_source` raises `SourceReadError` carrying the path and the original
   `OSError` or `UnicodeDecodeError`; it neither logs nor prints nor returns
   `None`. Its return type is `SourcedInput`, whose bytes and text are both
   non-optional, so the "read succeeded but text is missing" branch the old
   signature needed is now unrepresentable rather than merely unreachable.
   `report_file_error` is gone; `report_check_error` dispatches on the error
   type. Unexpected extraction failures still log with their traceback and
   propagate.
5. Byte-faithful input, non-mutating `--diff`, patches on stdout, diagnostics
   on stderr, collaborator injection, and every exit status are unchanged — the
   five CLI test modules pass with byte-identical messages.
   `CheckCollaborators` gained an injectable `reporter` and dropped the dead
   `writer` field.
6. `tests/test_check_pipeline_units.py` adds 15 tests over the new boundary:
   readable/missing/directory/undecodable reads, bridge refusal, unexpected
   adapter failure, invalid configuration, the aggregation pass's ordering and
   error rule, both injected streams, and both diff outcomes.
7. Re-measurement is still outstanding — see below.

**A design correction worth recording.** The first cut of `check_one_file`
passed `source_bytes`, `source_text`, `reported_path`, and `resolved_path` to
its helpers as four separate primitives. Ruff's `PLR0913` rejected it at five
arguments, and the fix was not a suppression: `SourcedInput` carries exactly
those four values, so the helpers take the value the pipeline actually has. The
same shaped the `CheckRun` bundle, which holds the four collaborators one
invocation fixes across every file.

**Gate evidence, first run.** `make check-fmt` and `make markdownlint` failed
on formatting alone; `make lint` raised 17 errors, whose rules and sites are
recorded above. All have since been fixed and `ruff format --check` and
`ruff check` are clean on the five changed files, with the CLI test modules
green. `make typecheck` and `make test` **could not be evaluated**: the shared
Cargo package cache was held in a circular wait by another agent's session —
the lock holder's own descendant was queued behind it on the same inode — so
both gates blocked before reaching `cargo check`, `ty check`, or pytest. That
is an environment condition, not a branch fault; the two gates are still
unverified and the hand-edited `test_maturin_build.ambr` snapshot has not been
exercised.

**Two test expectations I wrote were wrong, and the code was right.**

1. The read-failure test targeted a file that never existed. Discovery ignores
   a missing target (`discovery.py` logs "ignoring missing or unsupported
   target" and yields nothing), so no file was checked and the run exited 0.
   The realistic shape of a read failure is a file that disappears between
   discovery and its read, which is what the test now arranges.
2. The accepted-preview test expected exit 0. An accepted preview still exits
   1: the diagnostic was found and the source is deliberately left untouched
   for the user to apply, which the existing snapshot pins as
   `{"exit_code": 1}`. The test now asserts 1.

Both were caught by running the tests rather than by reasoning about them.

## Revision 33 (2026-09-28): Requirement 7 met, and the floor that could have faked it

The refactor of Revision 32 left `cli.py` at 7 functions and mean 4.1429, still
flagged (`indication: 2`). Two functions carried it: `_resolve_collaborators`
(cc 7) and `_discover_targets` (cc 8). Both were resolved by removing a real
design defect rather than by moving code to move a metric.

**`_resolve_collaborators` and `_ResolvedCheckCollaborators` are gone.** They
existed only to undo the five `None` sentinels on `CheckCollaborators`. Each
field now declares its production default with `dataclasses.field(...)`, so a
constructed bundle is already complete and no second pass resolves it. This
deletes 22 lines and one type, and it removes a state that was genuinely
representable-but-invalid: a bundle with four fields populated and one `None`.

**`_discover_targets` split along its real seam.** The `-` sentinel contract --
expanding targets, matching the stdin sentinel, and rejecting `-` combined with
a file target -- became `_parse_targets`, which returns the paths and whether
stdin was requested. `_discover_targets` now reads as three steps: parse, take
the stdin path, or walk the filesystem. The function stayed in `cli.py`: it *is*
`run_check`'s discovery responsibility, and moving it out to lower an average
would have been exactly the padding the task prohibited.

`_discover_targets` also stayed in name and location deliberately:
`tests/test_check_files.py` monkeypatches `cli._discover_targets` by attribute
path, so relocating or renaming it would have silently disabled that
substitution rather than failing loudly.

### Measured outcome (requirement 7)

| Reading               | Before Revision 32 | After Revision 32         | After Revision 33 |
| --------------------- | ------------------ | ------------------------- | ----------------- |
| Functions in `cli.py` | 11                 | 7                         | 7                 |
| Complexity sum        | 54                 | 29                        | 24                |
| Mean complexity       | 4.9091             | 4.1429                    | **3.4286**        |
| Threshold             | 4                  | 4                         | 4                 |
| `cs review` verdict   | flagged            | flagged (`indication: 2`) | **clean**         |

The final reading is from CodeScene itself, not from the AST probe:
`cs review python/stilyagi/cli.py --output-format json --pretty` returns
`{"score": 10.0, "review": []}` -- no findings at all. The validated flip-point
instrument independently agrees: 7 functions, sum 24, mean 3.4286, MEETS. Both
agree, and the two were built from different evidence, which is the point of
insisting on both.

**The function-count floor, and why the result is not an artefact of it.**
CodeScene does not flag a file with fewer than 7 functions, whatever its mean.
This was probed directly: a synthetic file of 6 functions at mean complexity
7.0 is not flagged, while the same body at 7 functions is. A module that
reaches "clean" only by dropping to 6 functions would therefore have satisfied
the threshold without being simpler. `cli.py` ends this revision with **7**
functions, so it clears the precondition and the clean verdict is a real
measurement. Had the split overshot into 6, the honest report would have been
"unmeasurable", not "resolved". This is recorded because a future change that
consolidates two functions would silently re-enter the floor and any later
"clean" reading could not be trusted without re-checking the count.

### One real regression caught, and the memory it earned

Converting the `None` sentinels to `default_factory` initially broke two tests:

```text
FAILED tests/test_check_stdin.py::test_cli_main_reads_stdin_and_attributes_diagnostic_to_filename
FAILED tests/test_check_command.py::test_main_renders_json_for_synthetic_diagnostics
```

Both monkeypatch `stilyagi.rules.registry.run_rules` by string. The first cut
wrote `rule_runner: rules_registry.RuleRunner = rules_registry.run_rules`,
which **captures the function object at import time**; rebinding the module
attribute afterwards has no effect on the captured reference. The previous code
evaluated `configured.rule_runner or rules_registry.run_rules` at call time and
was therefore patchable. Every field now resolves through a lambda that
performs the lookup at call time, restoring the old contract exactly. The check
is that a module-level default stays substitutable; it is recorded in the
developers' guide beside the field list, because it is not obvious from reading
the dataclass and it fails silently -- the suite stays green wherever no test
patches the name.

### Gate status at this revision

`make check-fmt`, `make markdownlint`, and `make nixie` are to be re-run with
`make typecheck` and `make test` on this exact tip; the earlier two failures on
formatting alone were fixed before Revision 32. `make typecheck` and
`make test` remain unverified if the shared Cargo package-cache deadlock
persists. The `test_maturin_build.ambr` snapshot is still unexercised until
pytest runs to completion.

## Revision 34 (2026-09-28): the test split, and lint green again

`make lint` failed on a second, unrelated reason after the interrogate gap was
closed: pylint `C0302 too-many-lines` on `tests/test_check_pipeline_units.py`,
at 545 lines against the project's 400-line ceiling.

`too-many-lines` is not an accident of the config. It sits in pylint's **
`enable`** list in `pyproject.toml` under a comment reading *"Match the project
file-size ceiling enforced during review"*, so the ceiling is deliberate
policy. Suppressing it locally, or widening the limit, would have been a policy
change hidden inside a refactor. The module was split along the seam the tests
already had.

### The split

| Module                                     | Lines | Contents                                                            |
| ------------------------------------------ | ----- | ------------------------------------------------------------------- |
| `tests/test_check_pipeline_units.py`       | 261   | `TestCheckOneFile`, `TestAggregateCheckedFiles`                     |
| `tests/test_check_boundaries.py`           | 214   | `TestInjectedStreamsAndReporters`, `TestDiffPreviews`               |
| `tests/support/check_pipeline_fixtures.py` | 128   | shared reporters, runners, preview builders, the read-failure patch |

The seam is behavioural rather than arbitrary: the units module drives
`cli_pipeline` directly, and the boundaries module drives the same code through
`cli.run_check` to pin what only exists at the command boundary -- an injected
`output` stream, an injected `reporter`, and both `--diff` outcomes. The shared
helpers live in `tests/support/` rather than being imported from one test
module into another, so neither module depends on the other's import side
effects.

### Two lint details worth recording

**Ruff's typing-only-import rules are not satisfied by "it is only an
annotation" reasoning at the reader's level; they follow the actual use.**
`cli_io` and `pathlib` had to move *out* of the `if typ.TYPE_CHECKING:` block
in the fixtures module because both are used at runtime there --
`cli_io.CheckInput(...)` in `input_for`, and `pathlib.Path.read_bytes` in
`patch_read_bytes_failure`. `pytest`, `DiffPreview`, and `rules_registry`
stayed inside it, because in that module they really are annotation-only. In
`tests/test_check_pipeline_units.py` the opposite held for `pytest`, which
moved back out to a runtime import because the module calls `pytest.raises` for
real. The rule to apply is per-module: check how the name is used in *this*
file, not how it is used in the file it was copied from.

**`ruff check --fix` reordered the block after the move.** The import block is
sorted as one unit, so moving a name across the `TYPE_CHECKING` boundary
re-sorts it; the fix is to run the fixer rather than hand-tune the blank lines.

### Gate status after the split

| Gate                   | Result                                                                           |
| ---------------------- | -------------------------------------------------------------------------------- |
| `ruff check`           | PASS -- all three modules                                                        |
| `ruff format --check`  | PASS -- 3 files already formatted                                                |
| `pytest` (two modules) | PASS -- 15 passed in 0.19s                                                       |
| `make lint`            | **PASS** -- ruff clean, interrogate 100.0%, pylint 10.00/10, df12 lints 10.00/10 |
| `make check-fmt`       | PASS                                                                             |
| `make markdownlint`    | PASS -- 0 errors                                                                 |
| `make nixie`           | PASS                                                                             |
| `make typecheck`       | NO VERDICT -- blocked on the shared Cargo package-cache lock                     |
| `make test`            | NO VERDICT -- same lock                                                          |

`make lint` reaches `cargo doc` for the workspace and blocks there on the same
lock, but every Python gate in it has already reported. The blocking condition
is external: `flock -w 5 ~/.cargo/.package-cache-mutate true` returns 1, with
roughly eighteen `cargo` processes from other agents' worktrees (`ortho-config`,
`mdtablefix`, `rstest-bdd`) holding it. No process was killed and no isolated
cache was created, per the standing instruction to let the shared cache
serialize naturally. `make typecheck` and `make test` must be re-run on this
tip once the lock clears; a timeout there is not a failure of this branch.

## Revision 35 (2026-09-28): BDD scenarios green, and three findings that were not test bugs

Milestone 5 Stage B is complete: `features/stilyagi_fix_command.feature` and
`tests/test_fix_command_bdd.py` bind all ten planned scenarios and all ten
pass. Getting there surfaced three findings that were **not** test-harness
mistakes, and two of them changed production behaviour.

### Finding 1: pytest-bdd's step registry is session-global

The ten scenarios pass in isolation but failed en masse when the module ran
alongside `tests/test_package_skeleton_units.py`, with
`fixture 'check_command_state' not found` on every scenario.

The cause is that `pytest_bdd` step definitions are registered globally for the
session, not per module: `tests.steps.check_command` defines
`I run "{command}" in that tree` and `the exit code is 0/1/2`, and this
module's steps were reusing those exact texts. Whichever definition is
registered last wins for the whole session, so the check module's `@when`
captured this module's scenarios and demanded *its* `check_command_state`
fixture.

Two options were considered and one rejected:

- **Rejected: add `"tests.steps.check_command"` to `pytest_plugins`.** This is
  what the earlier plan note suggested, and it is wrong. It does not resolve
  the collision, it makes it deterministic -- the two modules would then always
  contest the same four step texts.
- **Adopted: give every step in this module a text no other module uses.**
  Scenario steps now read `the fix command "..." runs in that tree` and
  `the fix command exits with code 0/1/2`. A cross-module scan of
  `tests/steps/*.py` now reports no duplicate step texts, and the tree-building
  Given was renamed to `a tree holding two Markdown files and an injected rule`
  so it does not shadow the check command's two-file tree Given either.

The lesson generalizes: a new BDD steps module must be checked against every
other steps module for step-text collisions, because the registry is not
namespaced.

### Finding 2: a `--fix` run re-lints through the same injected runner

Three scenarios failed with
`SourceTextNotFoundError: source-backed text not found: 'Paragraph'`, traced
through a full-traceback run: at rule time the document was
`Region(kind='paragraph', text='Section text.')` -- the **already rewritten**
text.

`relint_written_files` builds a `CheckRun` with `dc.replace(run, options=...)`,
which keeps `rule_runner`. So every injected stub runs twice per `--fix`
scenario: once against the bytes on disk and once against the bytes it just
wrote. A stub that raises when its needle is missing therefore breaks the
re-lint it is supposed to support.

Every stub in `tests/steps/fix_command.py` is now idempotent by construction.
`_rule_offering` wraps an edit maker that returns `None` when its needle is
gone, and `_two_rules` composes those same runners rather than raw specs. This
is what a real rule does with text it no longer matches, so the fix makes the
stubs *more* faithful, not more permissive.

### Finding 3: a synthetic span cannot be invented; it has to be measured

The synthetic-span scenario was passing for the wrong reason. It used a
hard-coded `TextEdit(1, 2, "")`, and a probe showed the edit being **accepted**:
`DISK: b'Pragraph text.\n'`, no fix-error line. For `"Paragraph text.\n"` the
IR exposes one span, `SourceSpan(byte_start=0, byte_end=15)`, so byte 1 is
source-backed and the edit merely deleted the `a`.

A second probe showed where genuine gaps are: for
`"First line\nsecond line.\n"` the spans are `(0,10)` and `(11,23)`, leaving
byte 10 -- the normalized-away soft line break -- unclaimed. The scenario's
source text is now that two-line paragraph, and the edit range comes from the
new `find_unclaimed_span(document)`, which walks the document for the first
byte no merged source-backed span contains, bounded by the furthest byte the IR
claims. The refusal is now verified by the log:
`spans=2 considered=1 rejected=1 planned=0`.

This closes the gap the plan warned about at line 44: *"A synthetic span cannot
be invented: it has to be a real offset the IR genuinely does not cover."*
Hard-coding an offset would have left the scenario green and vacuous.

### A production change: a stream input's report moved off standard output

`print_unmodified_report` printed to the `output` collaborator unconditionally.
For a stream input that is **wrong**: `emit_fixed_document` has already written
the fixed document to that same stream, so the report was concatenated onto the
text the user is piping out, making it unextractable.

The comment on `print_unmodified_report` claiming a zero-fix run stays
byte-identical to a plain check is true only for file inputs, and the docstring
now says so. The stream decision moved to the command boundary, which is the
only place that knows whether a fixed document already owns standard output:
`_apply_and_exit` passes `sys.stderr` when any plan came from stdin. The
destination is now a positional parameter rather than a fifth keyword argument,
which also keeps the signature inside the project's `max-args = 4`.

The stdin scenario asserts `stdout == _REPAIRED_TEXT` exactly, so it fails if
the report ever lands there again.

### Refusals are read from both streams

The three refusal assertions (synthetic span, overlapping edits, "file was not
modified") now concatenate stdout and stderr. When nothing is written the run
is deliberately byte-identical to a plain check, so the report goes to the
normal diagnostics stream -- and which stream that is for a given run is a
boundary decision, not something the assertion should pre-empt. Reading both
also means the assertion tests *what was said*, not *where*, which is the part
this scenario owns.

### The skylos allow list shrank, and the contract test was updated with it

`tests/test_skylos_whitelist_contract.py` pinned the three milestone-5
temporary exemptions (`write_source`, `_write_temporary_source`,
`SourceChangedOnDiskError`) that Revision 26 said to remove once the pipeline
called `write_source`. The pipeline now does, and the previous commit removed
them from `pyproject.toml`; the pin went stale and failed the full suite.

The pin is now the seven-name list re-listed with its provenance. Revision 26's
instruction is discharged, and its reason for existing is now a module
docstring line so a future reader does not have to reconstruct it.

### Gate status after Stage B

| Gate                  | Result                                                 |
| --------------------- | ------------------------------------------------------ |
| `ruff check`          | PASS -- 0 errors, `tests/` and `python/`               |
| `ruff format --check` | PASS -- 158 files already formatted                    |
| `interrogate`         | PASS -- 100.0%                                         |
| `ty check`            | PASS -- all checks passed                              |
| `pylint`              | PASS -- 10.00/10 over `python/stilyagi tests`          |
| `pytest` (affected)   | PASS -- 57 passed across 7 modules, incl. cross-module |
| `pytest` (full)       | RUNNING -- background shell `bzsrlwobx`                |

The affected-module run is the one that matters for regressions here: it
includes `test_package_skeleton_units.py`, which is the module that exposed
Finding 1, so the collision cannot silently return.

### Still outstanding for Milestone 5

- **Stage C2**: subprocess coverage in `tests/test_cli_e2e.py` for `--diff` and
  `--fix`, including piping `--diff` output to `git apply --check`.
- A dedicated regression test for the stream-input destination decided above;
  the BDD scenario covers it end to end, but the `cli_fix` unit boundary is
  only covered through the command.

## Revision 36 (2026-09-28): a clean tree was reported as fixed

### What was found, and how

While probing real subprocess behaviour before writing the Stage C2 tests, a
`--fix` run over a tree with **zero diagnostics** printed

```console
fixes were applied; re-running may apply further fixes

0 diagnostics found (0 safe fixes, 0 unsafe fixes)
```

to standard error and exited 0, while the file's md5 was identical before and
after. The run claimed a mutation that had not happened. The probe separated
the streams and compared hashes, so the claim was not inferred from the text --
the text was contradicted by the bytes on disk.

### Why it happened

`plan_fixes` ended with

```python
apply_edits(request.source_bytes, edits)
```

With no eligible diagnostic, `edits` is empty and `apply_edits` is an identity,
so `fixed_bytes == source_bytes`. `_apply_and_exit` asks only
`outcome.changed_anything`, which counts `files_written`; `_write_one` counted
a write; and `write.py`'s `if current_bytes == content: return` then skipped
the actual write. The no-op was real in exactly one layer and invisible in the
two that decided what to report.

This is a **contract violation, not a design change**. `PlannedFile`'s
docstring already promised ``fixed_bytes`` is ``None`` for "a file with no
fixable diagnostics at all", and `patch_for` already returns `""` for a `None`
replacement, so `--diff` was never wrong. Only the mutation path read the field
as "bytes came out of the kernel" rather than "bytes to write".

### The fix, and the second route to a no-op

The repair is in the planner, where "no edits" means "no replacement". A new
`_replacement(source_bytes, edits)` splices and then measures the result
against the source, returning `None` when they are byte-identical.

Measuring rather than testing `if not edits` matters, because an empty edit
list is not the only way to reach an identity. **An edit that replaces a span
with the bytes already there is admissible at every check**: the span it names
is genuinely source-backed, so `classify_edit` accepts it, and nothing in the
model forbids a rule from offering one. The new Hypothesis property
`test_edits_replacing_a_span_with_its_own_bytes_offer_nothing_to_write`
constructs exactly that case from the corpus and passes. The field's meaning is
now stated in `FixPlan`'s and `plan_fixes`' docstrings so the next reader does
not have to rediscover it.

Phase two gained `_would_change` as belt and braces against a plan built some
other way: `files_written` counts files whose bytes this run actually changed,
because the caller prints the re-run note on the strength of it.

### Two tests pinned the old behaviour

- `tests/test_fix_planner.py:124` asserted
  `plan.fixed_bytes == source.encode()` with the message "expected an empty
  plan to be an identity". The identity was the defect.
- `tests/test_fix_planner_properties.py:229` asserted the same over every corpus
  case.

Both now assert `is None`, and the property was renamed
`test_empty_plans_offer_nothing_to_write` so its name states the contract
rather than the old implementation.

### Regression coverage added

- `tests/test_check_boundaries.py::TestMutationStreams` -- a clean tree must not
  be reported as fixed, and a stream input's fixed document must own the output
  stream. This is the `cli_fix` unit-boundary test Revision 35 listed as
  outstanding; it belongs in the existing command-boundary module rather than a
  new one.
- `tests/test_fix_planner_properties.py` -- the in-place-edit property above.

The stream-input test asserts exit **1**, not 0. That is D-13 working as
documented, not a contradiction of the repair: the status comes from re-linting
the files the run *wrote*, and a stream input is never written, so its planning
diagnostic still stands. The docstring says so, because a reader who expects 0
would otherwise read the assertion as a bug.

### Verified against the real command

Re-running the original probe after the fix:

```console
EXIT=0
--- STDOUT ---
0 diagnostics found (0 safe fixes, 0 unsafe fixes)
--- STDERR ---
--- before=a0930c8996560212608e858c3a17491c after=a0930c8996560212608e858c3a17491c ---
OK: no re-run note
```

Standard error is empty, the report is on the normal diagnostics stream, and
the file is byte-identical. A two-file tree behaves the same way.

### Stage C2: the blocker, restated with evidence

Revision 35 recorded Stage C2 as blocked because "no builtin rule emits fixes".
That is confirmed and the mechanism is now pinned:

- `grep -rn "Fix(\|fix=\|TextEdit" python/stilyagi/rules/` returns **nothing**,
  over a `rules/` tree whose only rule-bearing module is `registry.py`, and
  whose `run_rules` is documented as "Return no diagnostics until the rule
  engine lands" (roadmap 2.3.1).
- `python/stilyagi/plugins.py` defines `RULE_ENTRY_POINT_GROUP` and
  `CAPABILITY_ENTRY_POINT_GROUP` as *constants only*. Nothing imports the
  module outside `tests/test_package_skeleton_units.py`, and no
  `importlib.metadata` entry-point scan exists anywhere in `python/`. The
  documented `[project.entry-points."stilyagi.rules"]` route is therefore a
  stated intention, not a working seam: a test package cannot register a rule
  that the runtime would load.

So there is **no honest subprocess route** to a fix-producing rule today. The
`--diff`/`--fix` halves that need one cannot be covered end to end without
either wiring plugin loading (a roadmap item in its own right, and a change to
runtime behaviour that this slice should not smuggle in) or installing a fake
distribution, which would test the installer rather than the command.

What *is* coverable at the subprocess boundary, with no rule at all, is every
decision that lives in the command rather than in a rule: the `--fix --diff`
usage error and its exit 2, `--unsafe-fixes` without `--fix`, and the
clean-tree no-op that Revision 36 repaired. Those are the shapes that regressed
in practice, and they are worth pinning across a real process boundary because
the in-process tests inject collaborators that the real entry point does not
have. The rule-dependent halves stay covered by the BDD scenarios, which inject
through `CheckCollaborators.rule_runner` -- the seam that exists today.

## Revision 37 (2026-09-28): two latent defects the gates found, and a wedged cargo lock

### The dead-code gate caught my own leftover

`make lint` ends with `skylos --category dead_code --gate`, and it failed on
`python/stilyagi/engine/fix_planning/selection.py:96`:

```console
python/stilyagi/engine/fix_planning/selection.py:96  SKY-U001  unused function: select_candidates
```

`select_candidates` was a one-line wrapper over
`partition_candidates(...).eligible`, added in `0ad1d4c` and left behind when
`plan.py` came to call `partition_candidates` directly. Nothing referenced it:
not the runtime, not a test, not the Rust bindings. This is exactly the class
of defect the gate exists for, and it is mine rather than pre-existing --
`selection.py` was created on this branch.

The removal is not a coverage loss. `partition_candidates` keeps the doctest
that pins the empty-input contract, and the partition it returns carries all
four groups, so the `.eligible` projection is exercised through `plan.py`.
`select_candidates` only re-exposed one field of a value the caller already
held.

The execplan's own design table had drifted: it still described the module as
`is_candidate(...)` plus a `select_candidates` comprehension. That row now
names the shipped shape, so the plan does not point a later reader at a deleted
function.

### The doctest gate caught a `TYPE_CHECKING`-only name in an example

`make test-doc` runs `pytest --doctest-modules` over `python/stilyagi` and
`tests/support`. It failed on `cli_config.py`:

```console
>>> build_cli_overrides(CheckOptions(targets=("docs",), select=("STY",)))
UNEXPECTED EXCEPTION: NameError("name 'CheckOptions' is not defined")
```

`CheckOptions` is imported under `if typ.TYPE_CHECKING:` in that module, so the
example could never work as written -- a doctest executes in the module's real
namespace, where a typing-only import does not exist. Also mine:
`cli_config.py` was created by `3c6cdaa` on this branch.

The fix follows the convention the rest of the package already uses: import
inside the example. `rules/registry.py`, `engine/checker.py`,
`engine/runner.py` and `discovery.py` all open their doctests that way. A
`--doctest-modules` pass is a real execution, and an example that needs a name
must bring it.

Both defects were invisible to `make test`, which does not collect doctests and
does not run the dead-code gate. That is the argument for running the whole
gateway rather than the suite one believes is relevant.

### The cargo package-cache lock is wedged, and it is not mine

`make build`, `make typecheck` and the Rust half of `make test` could not
complete. The cause is a cycle across two other worktrees, not in this one:

```console
1832225  cargo test --all-targets     <- holds ~/.cargo/.package-cache-mutate EXCLUSIVE
  └─ 1855438  compile_contract test binary
       └─ 1855450  cargo build --bin podbot-tests   <- waits for the SAME lock
```

`cargo test` (the podbot worktree) takes the package-cache lock for the whole
run, and one of the tests it runs shells out to `cargo`, which needs that same
lock. The cycle cannot resolve itself. At the time of writing the holder had
accumulated 4 seconds of CPU across 6.9 hours of wall clock, and 78-82 cargo
and rustc processes from several unrelated repository worktrees were parked in
`locks_lock_inode_wait` behind it.

Per the standing instruction not to kill other agents' processes, nothing was
terminated. The orphaned `cargo rustc` processes that *were* cleared belonged
to this worktree and to gates I had already stopped; clearing those is what
released the uv editable-distribution lock their parent was still holding.

Everything that does not need cargo was therefore run, and the cargo-free route
turned out to be complete for the Python side.
`uv sync --group dev --no-install-project` installs the dev group without
building the extension, and the prebuilt
`python/stilyagi/_stilyagi_rs.cpython-314-x86_64-linux-gnu.so` is newer than
every Python source change, so `PYTHONPATH=python .venv/bin/python` imports the
package and loads the extension. Measured this run:

| Gate                               | Result                                 |
| ---------------------------------- | -------------------------------------- |
| `ruff check`                       | All checks passed                      |
| `ruff format --check`              | 224 files already formatted            |
| `cargo fmt --all -- --check`       | clean (rustfmt does not need the lock) |
| `mdtablefix --check`               | 67 files left unchanged                |
| interrogate `--fail-under 100`     | PASSED (minimum 100.0%, actual 100.0%) |
| pylint                             | 10.00/10                               |
| df12 pylint tier                   | 10.00/10                               |
| skylos dead-code `--gate`          | exit 0 (after the removal above)       |
| `pytest` (full suite)              | 635 passed, 1 skipped, 2 errors        |
| `pytest --doctest-modules`         | 35 passed, 2 skipped                   |
| spelling + markdownlint (68 files) | 0 errors                               |
| nixie (Mermaid)                    | All diagrams validated successfully    |

The two errors are both `tests/test_maturin_build.py`
(`test_maturin_wheel_build_snapshot`, `test_maturin_wheel_executes_correctly`)
raising `subprocess.TimeoutExpired`, because that module shells out to
`maturin` and wants the very lock the cycle holds. It is a file this branch
does not touch. `make typecheck` and the Rust half of `make test` remain unrun
for the same environmental reason and are **not** claimed as passing.

Gate coverage is therefore partial by circumstance rather than by choice. When
the lock frees, the outstanding gates are `make build`, `make typecheck`, and
the `cargo clippy`/`cargo doc`/`cargo test`/`whitaker` sections of `make lint`
and `make test`.

## Revision 38 (2026-09-28): Milestone 5 complete, and the subprocess boundary pinned

Stage C2 is done, and with it every item Milestone 5 was carrying. Three new
tests in `tests/test_cli_e2e.py` and one new class in
`tests/test_check_boundaries.py`, in four commits.

### What the subprocess tests can and cannot reach

Revision 35 recorded Stage C2 as blocked because no builtin rule emits fixes.
That still holds: `rules/registry.py`'s `run_rules` returns `[]` over a tree
whose only rule-bearing module is `registry.py` itself, and `plugins.py`
defines the entry-point group names as constants that nothing imports. So the
rule-dependent halves of `--fix`/`--diff` remain covered by the BDD scenarios,
which inject through `CheckCollaborators.rule_runner`.

What is coverable with no rule at all is every decision that lives in the
command rather than in a rule, and that is what the four new cases pin:

| Case                             | What it pins                                               |
| -------------------------------- | ---------------------------------------------------------- |
| `--fix --diff`                   | exit 2, empty stdout, the conflict on stderr exactly twice |
| `--fix` on a clean tree          | exit 0, no re-run note, every file byte-identical          |
| `--unsafe-fixes` without `--fix` | accepted as a no-op, ordinary report, tree byte-identical  |
| `--diff` on a clean tree         | exit 0, empty stdout, summary moved to stderr              |

The last one is the stream contract the in-process tests could only assert
through an injected object: under `--diff` the machine artefact owns standard
output so `stilyagi check --diff | git apply` stays usable, and the summary has
to move to standard error. Reading two real streams of a real process is the
only place the default wiring is exercised at all.

The `--fix --diff` case counts occurrences rather than testing for presence.
`report_check_error` logs every expected failure at warning level *and* echoes
it to standard error, so two lines are the documented contract; the count is
what catches a third printing, which is the shape of the duplicate call site
Revision 36 removed.

### Three reasons to print nothing, each isolated

`emit_fixed_document` makes one decision that folds two conditions together:
the plan must carry a replacement, and its bytes must have come from a pipe.
The command-level test drove a `#`-headed document, whose fixed text ends in a
newline -- so it could not distinguish an emitted document from one that
`print` appended a newline to, and it reached neither reason to stay silent.

The three direct tests each isolate one branch, and each was checked by
mutation rather than assumed:

| Mutation                                 | Test that fails                                       |
| ---------------------------------------- | ----------------------------------------------------- |
| drop the `from_stdin` guard              | `test_a_file_input_prints_nothing`                    |
| drop `end=""`                            | `test_a_stream_input_prints_its_replacement_verbatim` |
| drop the `fixed_bytes is not None` guard | `test_a_conflicted_stream_input_prints_nothing`       |

Each mutation failed exactly one test and no other, which is the evidence that
the three assertions are load-bearing rather than decoration.

The piped plans are built with `dc.replace` on the shared fixture rather than
by adding a keyword there: `planned_file` already sits at the project's
four-argument ceiling, and `tests/support/` is not covered by the `test_*.py`
per-file exemption.

### The S603 finding, and why HEAD escaped it

`ruff check` failed on the new `_run_check` with
`subprocess-without-shell-equals-true`. The rule had never fired on this
function before, and the reason is worth recording: S603's heuristic looks at
whether the argv is dynamic. HEAD's helper passed a static list literal, so the
rule stayed quiet; adding `*flags` unpacking into that list is what makes it
fire. It was not a pre-existing finding that a whole-repo run had somehow been
missing.

Fixed the way every other `subprocess.run` call site in this repository is: a
call-site `# ruff: ignore[subprocess-without-shell-equals-true]` with a
justification. There are now eight such sites across six test modules, and this
one was the only outlier.

A false lead worth recording: running ruff against a copy of the file in `/tmp`
reported seven errors on HEAD's version. That comparison was invalid -- a
standalone copy in `/tmp` loses the repo-root configuration and the `tests/`
path that the per-file ignores and the file-level import comment depend on. The
authoritative signal is a whole-repo run, and the corrected comparison used
`--stdin-filename tests/test_cli_e2e.py` so the config still applied.

### Milestone 5 items verified as already present

Two Stage C requirements were checked rather than assumed, because a mechanism
that exists but is never reached is indistinguishable from one that does not:

- **Fix-error collapsing** is implemented in
  `fix_execution.summarise_fix_errors` and is wired -- `FixOutcome.fix_errors`
  is built from it at `fix_execution.py:191`, so the renderer only ever sees
  one entry per `(path, identifier)` with a count in the message.
- **The symlink policy** is on both sides. `discovery.py` refuses to follow a
  symlinked directory target and prunes symlinked directories during recursion;
  `write_source` resolves the file path and replaces the *target*, so a
  user-facing symlink survives. Both have tests (`test_discovery.py:114`,
  `test_fix_write.py:53`).

### Gate status after Stage C2

All gates reachable without the cargo package-cache lock, run sequentially on
the committed tip:

| Gate                           | Result                              |
| ------------------------------ | ----------------------------------- |
| `ruff check`                   | All checks passed                   |
| `ruff format --check`          | 224 files already formatted         |
| `mdtablefix --check`           | 67 files left unchanged             |
| interrogate `--fail-under 100` | PASSED (100.0%)                     |
| pylint                         | 10.00/10                            |
| df12 pylint tier               | 10.00/10                            |
| skylos dead-code `--gate`      | exit 0                              |
| `pytest` (full suite)          | 640 passed, 1 skipped               |
| `pytest --doctest-modules`     | 35 passed, 2 skipped                |
| spelling                       | exit 0, `typos.toml` unchanged      |
| markdownlint (68 files)        | 0 errors                            |
| nixie (Mermaid)                | All diagrams validated successfully |

`tests/test_maturin_build.py` is excluded from the full-suite count: its two
tests shell out to maturin and want the lock the cycle holds. It is a file this
branch does not touch. The cargo-dependent gates (`make build`,
`make typecheck`, and the `cargo clippy`/`cargo doc`/`cargo test`/`whitaker`
sections of `make lint` and `make test`) remain blocked by the environmental
deadlock Revision 37 documented, and are **not** claimed as passing.

### What remains

At the time of writing: Milestone 6 only -- ADR 0009, the users'/developers'
guide updates, the RFC 0003 §10 amendment for the `--fix --diff` exit-2 path,
the roadmap tick, and the `docs/contents.md` index entry. **All of these
landed; see Revision 39.**

## Revision 39 (2026-09-28): Milestone 6 documentation, and five review defects repaired

### The Milestone 5 CodeRabbit review returned five genuine defects

The review reported thirteen findings. Each was verified against the working
tree before any edit; five were real defects and are now fixed, and the
remaining were either already repaired or calls this work did not act on.

1. **The exit status described half the run.** `relint_written_files` re-checks
   exactly the files a mutating run *wrote*, and the status was read from that
   re-lint alone. A run that fixed one file while leaving a sibling's
   diagnostic standing therefore exited `0` with the diagnostic still there.
   `reconcile_written_files` now overlays the re-lint onto the planning pass,
   one `CheckedFile` per input, keyed on `resolved_path` -- the identity
   `discovery` already deduplicates on, so the overlay cannot land on the wrong
   file when two targets name one file.

   The first regression test for this **did not discriminate**: it passed
   against the unfixed code. The runner told the files apart by their content
   ("Paragraph"), but the written file's re-lint reads "Section text." and so
   fell through to the heading branch, emitting a diagnostic of its own that
   supplied the exit `1`. Exit `1` came from the written file, which is exactly
   what the old code got right. The runner now has a third branch returning
   nothing for the rewritten text, and the test was confirmed to **fail**
   against the reverted `cli.py` before being accepted.

2. **`OSError` escaped the write path.** `write_source` documents `OSError` in
   its own `Raises` section -- `_write_temporary_source` re-raises a staging
   failure, and the `copystat`/`replace` swap can fail on a full or read-only
   filesystem. Catching only `SourceChangedOnDiskError` let those escape as a
   traceback and abandon every file after them. `_write_one` now returns a
   `WriteAttempt` recording either an applied fix, a refusal, or an operational
   error, and a new `fix-error/write-failed` refusal names the cause.

   The two failure kinds are kept apart deliberately: a conflict refusal is a
   *planning decision*, so the diagnostic still stands and the run exits `1`; a
   write failure is an *environment fault*, so the run exits `2`, mirroring how
   the command already treats an unreadable source. That is why
   `WriteAttempt.operational_error` is a separate flag rather than another
   refusal. Verified by reverting the handler: the test then fails with the
   `PermissionError` escaping as a traceback.

3. **The unsafe-fixes hint asked for something that could not happen.**
   `warn_if_unsafe_withheld` scanned the raw diagnostics for any carrying an
   unsafe fix, but `selection._classify` tests `UNFIXABLE_CODE` *before* the
   level, so a code in `lint.unfixable` is excluded at every level and is never
   `withheld_unsafe`. Advising `--unsafe-fixes` for such a diagnostic would be
   advice that changes nothing. The evidence is now
   `plan.selected.withheld_unsafe`, the planner's own record of what it left
   out for that one reason.

4. **A refusal with no rule codes rendered a dangling separator.** Two of the
   identifiers (`changed-on-disk`, `standard-input`) are raised by the executor
   and the phase-one wrapper rather than by a rule's proposed edit, so they
   carry no codes by construction. `", ".join(())` is `""`, so the line read
   `...: path: : message`. `_render_fix_error` now omits the segment entirely.

5. **Phase-two refusals never reached the renderer at all.** Found while fixing
   the above rather than reported by the review. `FileCheck.fix_errors` returns
   `planned.fix_errors` -- the *phase one* set -- so `changed-on-disk`, and the
   new `write-failed`, were invisible. The run would have exited `2` while
   printing nothing that explained why. `print_mutation_report` now reads
   `outcome.fix_errors`, the only channel holding all three refusal sources.
   Reporting *both* `checked.fix_errors` and `outcome.fix_errors` was
   considered and rejected: `outcome.fix_errors` is already the complete
   collapsed set from both phases, so using both would print every phase-one
   refusal twice.

`tests/test_check_boundaries.py` gained three classes covering mixed outcomes,
write failures, and refusal rendering. All 648 tests pass (up from 644), and
each new test was confirmed to fail against the code it guards, by reverting
the relevant fix in isolation and re-running.

### The duplicate-helper finding, resolved rather than deferred

`_rewrite_paragraph` and `_rewrite_heading_marker` were byte-identical in
`tests/test_check_boundaries.py` and `tests/test_check_diff.py`.
`tests/support/check_pipeline_fixtures.py` already existed for exactly this,
and its docstring already stated the rule -- shared fixtures live there "rather
than being duplicated or imported across test modules" -- so both copies moved
there as `rewrite_paragraph` and `rewrite_heading_marker`. Ruff then caught six
imports that only the deleted copies had needed.

### Two RFC examples had the comma in the wrong place

Both published an insertion at the conjunction's own `byte_start`, which places
the comma *before* the separating space -- `docstrings , and comments` rather
than `docstrings, and comments`. The offset that yields a serial comma is the
preceding item's end, and that item is `items[-2]`, not `items[-1]`: the
coordination items include the item following the conjunction, so `items[-1]`
is "comments" and inserting there would produce `docstrings and comments,`.

The reviewer's wording said "the preceding item's end offset", which is right;
the index is the part worth recording, because `items[-1]` reads like "the last
item before the conjunction" and is not. Both examples now use
`items[-2].span.byte_end`, with a comment stating the arithmetic so the next
editor does not undo it. This is consistent with `has_serial_comma()`, which
tests precisely the comma after `items[-2]`.

### Milestone 6 documentation delivered

All eight Stage D deliverables are in place and were verified in the working
tree rather than assumed:

| Deliverable                   | State                                                        |
| ----------------------------- | ------------------------------------------------------------ |
| `docs/adrs/adr-0009-*.md`     | 362 lines, all required style-guide sections present         |
| `docs/rfcs/rfc-0003-*.md` §10 | +30 lines: the `--fix --diff` usage error and stream rules   |
| `docs/users-guide.md` §3      | +144 lines: `--fix`, `--diff`, refusals, exit codes          |
| `docs/developers-guide.md`    | +182: fix planning, the `--fix` path, no-writer collaborator |
| `docs/stilyagi-design.md`     | +43: fix-error identifiers and the admissibility rule        |
| `round_trip_edits.rs`         | +3: the one-sentence oracle disclaimer                       |
| `docs/contents.md`            | +9: ADR 0009 and this ExecPlan indexed                       |
| `docs/roadmap.md`             | 2.2.2 ticked with evidence, plus the 2.3.1 note              |

The two substance requirements the plan singled out are both present: ADR 0009
states at line 180 that a heading-depth rule cannot be auto-fixed under this
admissibility model, and carries the warning forward to roadmap 2.3.1 at line
306; `roadmap.md:188` repeats the note where 2.3.1 is actually scoped.

### A stale sketch is annotated, not rewritten

`docs/execplans/…:999` sketched `CheckCollaborators` with a `writer` field that
Revision 32 dropped. The sketch is a Milestone 0 *proposal*, so it was left
intact with a superseded note above it rather than edited to match the
delivered code -- rewriting a planning-time record to look like the outcome
destroys the evidence that the design changed. The note names what the as-built
bundle carries and points at Revision 32.

## Revision 40 (2026-09-28): requirement 7 re-measured, and it had regressed

Requirement 7 said to run CodeScene against the **final** code and report the
measured mean complexity for `python/stilyagi/cli.py`. Revision 33 recorded a
clean reading, but the code changed after it, so the reading had to be taken
again rather than carried forward.

**It had regressed.** `cs review python/stilyagi/cli.py` returns
`{"score": 9.38, "review": [{"category": "Overall Code Complexity",
"indication": 2}]}`
-- flagged, not clean.

Tracing the flag across the Milestone 5 commits, with
`cs review <ref>:./python/stilyagi/cli.py` run at each:

| Commit    | Subject                                       | Reading           |
| --------- | --------------------------------------------- | ----------------- |
| `3c6cdaa` | Split the check pipeline out of the CLI       | 10.0, clean       |
| `a201103` | Attribute read failures to the typed error    | 10.0, clean       |
| `661e7e6` | Add `--fix` and `--unsafe-fixes`              | 10.0, clean       |
| `9adec5e` | Cover the `--fix` pipeline with BDD scenarios | 9.38, **flagged** |

The regression enters at `9adec5e`, which grew `cli.py` by adding
`_apply_and_exit`. It is this branch's own change, not a pre-existing
condition: every commit before it reads clean.

Measured per-function at the flagged tip, with the validated AST counter:

| Function             | cc  | Note                 |
| -------------------- | --- | -------------------- |
| `_apply_and_exit`    | 8   | **new in `9adec5e`** |
| `run_check`          | 6   |                      |
| `_parse_targets`     | 5   |                      |
| `main`               | 4   |                      |
| `_configure_logging` | 4   |                      |
| `_render_and_exit`   | 3   |                      |
| `compute_exit_code`  | 3   |                      |
| `_discover_targets`  | 3   |                      |

8 functions, sum 36, **mean 4.5** against a threshold of 4. The same table
after the repair is below; the figures here describe the state this revision
found, not the state it left.

The counter is the same instrument Revision 33 used and agrees with CodeScene
on both sides of the boundary: it reads `3c6cdaa` as clean and `cc2fb81` and
this tip as flagged, so it is measuring the same quantity CodeScene measures
rather than merely correlating with it.

Also re-confirmed: the function-count floor noted in Revision 33 still applies,
and `cli.py` sits at 8 functions, so the file is eligible to be flagged at all.
A reading here is meaningful in a way a 6-function reading would not be.

The obligation this creates is recorded separately below, together with how it
was met; it is written here first so the failure is on the record independently
of the repair.

### The repair: the exit policy was stated twice

`_apply_and_exit` ended in two `return compute_exit_code(...)` tails that were
byte-identical apart from which aggregate they read:

```python
return compute_exit_code(
    checked.diagnostics_list,
    had_error=checked.error or outcome.write_failed,
)
```

and the same for `relinted`. The duplication is not cosmetic. `write_failed` is
an obligation invented after the first tail was written (Revision 39, defect
2), and every further tail would have had to remember to thread it
independently. The copy that forgot would have reported a refused write as exit
`1` rather than `2` -- exactly the defect the flag exists to prevent,
reintroduced by copy-paste rather than by a wrong decision.

`_fix_exit_code(checked, outcome)` now states that policy once and both tails
call it. It is `cc 2`: it is a one-line delegation, which is the point -- there
is nothing left in it to get wrong.

This was verified as a genuine deduplication rather than metric-chasing by
deleting `outcome.write_failed` from the new helper and re-running:
`test_a_permission_failure_is_reported_and_exits_two` fails with "expected a
filesystem refusal to exit two". The thread is still pinned, so the collapsed
version is not hiding a lost branch.

### Measured outcome after the repair

| Reading               | Flagged tip | After repair |
| --------------------- | ----------- | ------------ |
| Functions in `cli.py` | 8           | **9**        |
| Complexity sum        | 36          | 36           |
| **Mean complexity**   | **4.5000**  | **4.0000**   |
| Threshold             | 4           | 4            |
| `cs review` verdict   | flagged     | **clean**    |

The extraction raises the function count from 8 to 9 without changing the sum,
so the mean necessarily falls to exactly 4.0. That is worth stating plainly
because it is also the axis the function-count floor sits on: the mean only
moved because the denominator did, and the honest reading is the CodeScene
verdict, which is clean.

Both instruments were re-run against the repaired file and agree:
`cs review python/stilyagi/cli.py --output-format json` returns
`{"score": 10.0, "review": []}`, and the AST counter reads 9 functions, sum 36,
mean 4.0000. The two were built from different evidence, which is why both are
quoted.

**The threshold was pinned empirically rather than assumed.** A file at exactly
mean 4.0 with 8 functions, eight functions at `cc 4` each, was submitted to
CodeScene and returns `{"score": 10.0, "review": []}`. So 4.0 is inside the
threshold, not on the wrong side of it by rounding. The counter used for the
per-function figures was validated in the same pass: asked for the complexity
of a deliberately branch-heavy method, CodeScene reports `cc = 26` and the
counter reports 26.

### Requirement 7 status

Requirement 7 asked for CodeScene to be run against the **final** code, the
measured mean reported, and the threshold of 4 confirmed or refuted. It is now
met at the final tip: mean **4.0**, `cs review` clean, 9 functions, sum 36.

The instruction not to claim resolution "from an AST branch count or passing
tests alone" is why the two instruments are reported together and why the
threshold probe is recorded: the AST counter is corroboration, and the
CodeScene verdict plus the pinned threshold are the evidence.

## Revision 41 (2026-09-28): three gate failures, and one of them was branch-introduced

The full commit gate chain was delegated to `scrutineer` at the tip that
carried Revision 40. It came back with three failures. All three were real, all
three were in files this branch edits, and one was a defect this branch had
introduced rather than exposed.

### 41.1 `make check-fmt`: Revision 40's own tables

```text
mdtablefix --check --git --include-untracked --wrap --renumber --breaks --ellipsis --fences
docs/execplans/2-2-2-safe-fix-planning-conflict-resolution.md +31 -30
1 file would be reformatted, 67 files left unchanged.
make: *** [Makefile:159: check-fmt] Error 1
```

Revision 40 was written in one pass and never formatted. `mdtablefix`
re-widened the commit-trace and per-function tables and reflowed three prose
paragraphs. Fixed with `make fmt`; the content is unchanged, so this is a
rendering and not a new claim.

### 41.2 `make markdownlint`: two `-ise` spellings

```text
error: `synthesised` should be `synthesized`
    docs/users-guide.md:340:11
error: `synthesised` should be `synthesized`
    docs/users-guide.md:371:72
make: *** [Makefile:189: spelling] Error 2
```

`typos.toml` carries an explicit map from the `-ise` to the `-ize` form for
this stem, so `synthesized` is a hard requirement even though the project
otherwise writes en-GB-oxendict. The permitted `-ise` stems -- `analyse`,
`behaviour`, `normalisation` -- are unaffected, which is why a plain grep for
`-ise` in `docs/` returns many survivors and is not a usable check. Fixed both
occurrences; re-confirmed with `make markdownlint`.

### 41.3 `make lint`: four `docstring-missing-returns` errors, introduced by this branch

This is the one worth recording. Four DOC201 errors in code this branch wrote:
`_render_fix_error` in `python/stilyagi/engine/renderers.py`, and
`rewrite_paragraph` / `rewrite_heading_marker` /
`_fix_one_and_leave_the_other_standing` in the two test modules.

The mechanism is the whole finding:

- `pyproject.toml` sets `lint.pydoclint.ignore-one-line-docstrings = true`, so
  DOC201 **exempts a one-line docstring and applies as soon as it grows a
  second paragraph**. The exemption is not a property of the function; it is a
  property of the docstring's *shape*.
- The repair commit `e6a2e73` expanded all four of these docstrings from one
  line into a substantive body, in order to explain why the code is shaped as
  it is. That is exactly the transition that switches the rule on.
- Each file therefore passes ruff at `e6a2e73^` and fails at the tip.

That last point was verified rather than reasoned. Running ruff over the
pre-repair blobs:

```text
git show e6a2e73^:<path> | ruff check --stdin-filename <path> -
```

returns `All checks passed!` for all three files, where the tip fails all
three. So the cause is this branch's own change and not a stale base.

The rule itself was confirmed to be firing correctly with an isolated probe,
because a rule that fires for the wrong reason would be fixed for the wrong
reason too. A synthetic module holding one multi-line and one one-line
docstring of the same signature, checked with
`--isolated --preview --select DOC201`, flags only the multi-line one:

```text
docstring-missing-returns: `return` is not documented in docstring
 --> probe.py:2:5
```

The probe also showed that DOC201 has no effect without `preview`, which
`pyproject.toml` enables at line 39 -- so the rule is genuinely live here and
the four errors were genuine.

The fix adds the missing `Returns` sections. The diff is 21 insertions across
three files, all inside docstrings, so no code path changed and the behaviour
is untouched. `ruff check` is clean across all 225 files.

### Lesson

The docstring expansion and the rule that scrutinizes it were in the same
commit, and the gate that would have caught it was not run between that commit
and the review request. A docstring edit is not inert: in this repository the
docstring is what DOC201 reads, so explaining the code changed the code's
compliance status. That is the second time in this milestone that a
documentation-shaped change had a gate consequence, and it argues for running
the affected gate immediately after any commit that touches a docstring.

## Revision 42 (2026-10-12): the split clears pylint, and two stale-base failures it exposed

The commit gate chain was run again at `30f6d7a` after the two module splits,
and this time it got past `pylint` for the first time in three revisions.

### 42.1 The `C0302` failures are gone

Revision 41's tip failed `lint` at `Makefile:164` with two `C0302` errors:

```text
python/stilyagi/cli_pipeline.py:1:0: C0302: Too many lines in module (436/400)
tests/test_check_boundaries.py:1:0: C0302: Too many lines in module (571/400)
```

Both files were new on this branch and both crossed the ceiling in `e6a2e73`.
They had been masked: `lint` runs `ruff` at `Makefile:162` before `pylint`, and
`make` aborts on the first failure, so the six steps after `pylint` had never
run at this tip.

After the split, `pylint` is clean -- both invocations report
`Your code has been rated at 10.00/10` and a `grep -c C0302` over the log
returns zero. The split is a split, not a widened limit:
`max-module-lines = 400` is unchanged and is pinned by
`tests/test_pylint_tier_contract.py`, `tests/test_skylos_lint_contract.py` and
`tests/test_skylos_whitelist_contract.py`.

### 42.2 The two halves of the split

| Module                            | Before | After | New module                                                      |
| --------------------------------- | ------ | ----- | --------------------------------------------------------------- |
| `python/stilyagi/cli_pipeline.py` | 436    | 258   | `python/stilyagi/cli_run.py` 214                                |
| `tests/test_check_boundaries.py`  | 571    | 174   | `tests/test_check_mutation.py` 276, `tests/test_cli_fix.py` 116 |

`cli_pipeline.py`'s own docstring drew the first seam: it claimed to own "the
cohesive work one discovered file undergoes" while carrying four functions that
sweep a *collection*. `CheckedFiles`, `collect_checked_files`,
`aggregate_checked_files`, `relint_written_files` and `reconcile_written_files`
moved to `cli_run.py`; the per-file workflow stayed.

The second split followed the test module's docstring the same way. The
mutating tail became `test_check_mutation.py`; `TestFixedDocumentEmission`
became `test_cli_fix.py` because it calls `cli_fix.emit_fixed_document`
directly, which is a different boundary from the mutating command flow -- and
it closes a gap this plan records twice: *"the `cli_fix` unit boundary is only
covered through the command."* `TestRefusalRendering` moved into
`tests/test_renderers.py`, which exercises
`engine.RendererRegistry().render(..., fix_errors=[...])` and had no fix-error
rendering coverage at all.

The two halves are one commit, not two: after the production move alone
`test_check_boundaries.py` was still over the ceiling, so no intermediate
commit could pass `lint`.

The 649-test collection baseline is preserved. The split contributed twelve new
node IDs (`test_check_mutation.py` 4, `test_cli_fix.py` 3,
`test_check_boundaries.py` 5) and moved seven into `test_renderers.py`, and a
`--collect-only` run returns 649 both before and after.

### 42.3 The chain advanced, and exposed two failures that are not this branch's

With `pylint` cleared, `lint` ran steps 4--6 for the first time and stopped at
**step 7**, `Makefile:168` (`cargo clippy`):

```text
error: used `assert!` to check that a value is empty
   --> crates/stilyagi-markdown/src/tests/suppression.rs:230:5
make: *** [Makefile:168: lint] Error 101
```

`make test` stops at its own clippy step (`Makefile:196`) for the identical
reason, so both pytest lanes never ran.

Neither failure is caused by this branch. Ten locations across
`crates/stilyagi-markdown` and `crates/stilyagi-test-support` are
byte-identical at the merge-base `7fdcff34` and at HEAD:

```text
round_trip_helpers.rs   merge-base d912b4a7 = HEAD d912b4a7, main f6373d67
```

and `git merge-base --is-ancestor c3beea9 HEAD` is false while
`--is-ancestor c3beea9 origin/main` is true. `c3beea9` is **"Fix clippy 1.99
assert_is_empty findings (#190)"**, and it is exactly this remedy.
`origin/main` is 40 commits ahead. The branch's only `crates/` change is a
three-line doc comment in a different file, `round_trip_edits.rs`, which clippy
does not flag.

So this is the stale-base pattern this plan already names, not a new defect.
The route to a green `lint` is the already-planned rebase onto `origin/main`,
and steps 8 (`whitaker`, `Makefile:169`) and 9 (`skylos`, `Makefile:170`)
remain unproven until it happens.

### 42.4 `typos.toml` now regenerates identically to `main`

The spelling gate rewrote the working-tree copy during this run. The rendered
result is byte-identical to `origin/main`'s:

```text
git hash-object typos.toml           75d951c831b38d80af706145934020b6d21d494f
git rev-parse origin/main:typos.toml 75d951c831b38d80af706145934020b6d21d494f
```

The file is generated from the shared dictionary, so this is not hand-editing;
it is the pin moving. `main` adopted `typos-config-builder v0.1.3` (the branch
still pins `v0.1.1`) and renders the `--color` pattern differently as a result.
Because the working-tree content already equals `main`'s, the planned rebase
conflict on this file resolves to `main`'s side with no judgement call.

### 42.5 The halted gates that still need evidence

`check-fmt`, `typecheck`, `markdownlint` and `nixie` all pass at this tip. The
unproven set is now exactly: `lint` steps 8--9 (`whitaker`, `skylos`), and
every test lane, because `make test` aborts before reaching `pytest`.

### Lesson: clearing a failure promotes the next one

A green step is not the same as a step that ran, and the corollary is that
clearing one failure **promotes** the next one from hidden to blocking. Three
revisions recorded "`make lint` fails on X" while six steps after X were
unknown; this revision is the first that could read step 7 honestly, and what
it found there was a second, unrelated failure that had been sitting in the
blind spot the whole time. The habit is to state where the chain stopped, by
`Makefile:NNN`, and to treat every step after that as unverified rather than
merely unmentioned.

## Revision 43 (2026-10-12): the five review findings, adjudicated one by one

The five findings CodeRabbit raised on `4b4842c` are not one workstream. Read
against the tip, four were already closed by later commits and one was live.
This revision records the adjudication, because "all five addressed" and "one
of five addressed and four were never broken" are different claims, and only
the second is true.

### 43.1 Finding-by-finding disposition

| Finding                   | Disposition    | Evidence at the tip                                                                                                                                                                                                                                                                                                       |
| ------------------------- | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Testing (Overall)         | Closed earlier | `test_write_source_leaves_no_temporary_file_when_staging_fails` injects an `fdopen` failure raising `ENOSPC` and asserts the directory listing is unchanged; `test_write_source_refuses_a_target_edited_after_planning` pins the refusal; `TestRefusalRendering` covers the multi-error and no-rule-code rendering shapes |
| Unit Architecture         | Closed earlier | `cli_io.read_source` raises `SourceReadError` and neither logs nor prints; `report_check_error` is a separate function at the command boundary that does both                                                                                                                                                             |
| User-Facing Documentation | Closed earlier | The users' guide documents the `--diff` workflow, safe-fix scope, non-mutation, the stdout/stderr split, refusal reporting, exit codes, and the text/JSON fields                                                                                                                                                          |
| Developer Documentation   | Closed earlier | The developers' guide names the three-way split, documents the five collaborator fields and why there is no `writer`, and carries a "Fix planning" section covering `ir_view`, `FixPlanRequest`, the `--diff` split, `schema_version` and `fix_errors`                                                                    |
| Observability             | **Live**       | `grep -c 'logging\|_LOGGER'` over all eight modules of `engine/fix_planning/` returned **0**                                                                                                                                                                                                                              |

### 43.2 The one live finding, and why `logging` is the right answer

The finding asked for operational logs at "the new decision points". `FixPlan`
already carried `source_backed_spans` and `coalesced`, documented as counts "no
later stage can recover" and existing "for the fix summary", but nothing logged
them. The counters were built for a summary that was never written.

The determination the task asked for, measured rather than assumed: the Python
layer has **no `tracing` or `metrics` integration**. Both are dependencies of
the Rust extension only; `docs/stilyagi-design.md:915` states the Rust producer
emits them while "hosts install exporters", and no exporter host exists in the
Python package. The supported integration here is the standard-library
`logging` module, already the idiom in `cli_fix.py` and `fix_execution.py`. The
finding is met with one INFO event carrying the planner's decision as
structured fields -- no new dependency, no architectural change, and the
observable behaviour the finding asked for.

Introducing an OpenTelemetry-style stack into the Python layer, which is the
literal reading of "introduce an integration", is a substantial architectural
addition. It is not smuggled in under a review-warning fix.

### 43.3 A pre-existing defect the fix surfaced

While probing the parser to pin the new observability test, `cli_args.py` raised
`AttributeError: 'tuple' object has no attribute 'append'`. The three
selection flags (`--select`, `--ignore`, `--extend-select`) declared
`action="append"` with `default=()`, and argparse copies the default before
appending to it; copying a tuple yields a tuple, so the first actual use of any
of the three raised.

This is **not** branch-introduced. `git show e86256f` carries identical code,
and `e86256f` arrived with `Implement Markdown check command (2.2.1) (#54)`. It
survived because the only parser test exercised `--diff`, a `store_true` flag
with no default to copy. The users' guide already documented `--select` and
`--ignore` as deciding "which rules run at all", so the documented behaviour
was unreachable through the parser.

`git tag --contains e86256f` is empty and the package version is `0.1.0`, so
**the defect never shipped in a release**. The users' guide is a forward
statement of the settled v1 contract, and the fix makes that statement true
rather than changing behaviour a user has seen, so the argparse repair alone
requires no guide amendment. A regression test pins all three flags and their
defaults.

**Correction (recorded rather than edited away).** An earlier draft of this
section closed with "No users' guide amendment is therefore required." That
branch-level claim was falsified by this same revision's work, for a reason
unrelated to argparse: `run_check` is exported in `cli.py`'s `__all__`, and
this branch adds its keyword-only `collaborators` parameter, so the public
Python surface *did* change and §1a of the users' guide now carries a "Calling
`check` from Python" migration note. The argparse paragraph's reasoning holds
for the argparse fix; it was the generalization to the whole revision that was
wrong. The note is the one documentation change this revision found necessary,
and it was found by re-reading the exported surface rather than by listing the
findings.

### 43.4 Refresh: the CodeScene verdict is bound to the old remote head

The hosted CodeScene failure is attached to `81d2fe1`, which is the
**pre-rebase, pre-fix** remote head. It reports `cli_args.py` at
`10.00 -> 9.60` with `_add_check_arguments` as the flagged Large Method -- the
exact shape the builder extraction in 43.3's sibling change removes. A local
`cs delta` run against `origin/main` reads clean for all five files.

Per the CodeScene skill, a local clean report does not override a hosted
failure. The hosted verdict can only be re-read after the fixed tree is pushed,
so this revision does not claim resolution: it records that the local and
hosted measurements were taken on **different trees**, which is the only
reading consistent with both.

### 43.5 The five findings were not the only gate failures

Running the full chain after the observability work returned a **red** verdict,
and the failures were in this branch's own new code rather than in any of the
five findings:

| Gate                | Verdict  | Evidence                                                                            |
| ------------------- | -------- | ----------------------------------------------------------------------------------- |
| `make check-fmt`    | pass     | ruff 223 files formatted; `cargo fmt` clean; mdtablefix 68 unchanged                |
| `make lint`         | **fail** | aborted at `Makefile:174` (`ruff check`) with 5 errors; steps 175--182 unrun        |
| `make typecheck`    | pass     | `ty 0.0.74` -- `All checks passed!`                                                 |
| `make test`         | pass     | nextest 337/337; Rust doctests 13; pytest 632 passed; doctests 40 passed, 2 skipped |
| `make markdownlint` | pass     | typos gate clean; markdownlint 69 files, 0 errors                                   |
| `make nixie`        | pass     | all diagrams validated                                                              |

The five ruff errors were all mine, and three were consequences of one mistake:
the `plan_records` fixture was annotated with the banned `typing.Iterator`, and
`tests/support/fix_fixtures.py` referenced `cabc` without importing it, so the
alias had to be added in the `TYPE_CHECKING` block the repository's other
modules use. The remaining two were a `docstring-missing-yields` on a generator
fixture and a `yoda-conditions` on a `<=` set comparison. None was
pre-existing; none was reachable before the tree reached this tip.

**A finding that was investigated and deliberately not "fixed".** The missing
`cabc` import looked like a latent `NameError`. It is not one in practice: the
module imports fine, and the tests pass, because PEP 649 defers annotation
evaluation. `inspect.signature` over such a function *does* raise. The decisive
experiment was to run the same probe against `tests/support/ir_identity.py`,
which this branch never touched: it raises
`NameError: name 'cabc' is not defined` and `name 'pathlib' is not defined` for
its own functions. The behaviour is therefore the repository-wide convention for
`TYPE_CHECKING`-only aliases under deferred annotations, not a defect
introduced here, and changing it would be a repo-wide decision rather than a
review-finding repair.

### Lesson: a findings list is a claim about a tree, not a requirement

The five findings were carried for several revisions as an undifferentiated
"remaining work" block. Read against the current tree, four had already been
closed by commits that never referenced them. A findings list is a statement
about the revision the reviewer read; it decays as the branch moves, and the
only way to know which entries are still live is to re-read each against the
tip. The corollary is that "1 of 5 addressed" is a more useful record than "all
5 addressed", because it preserves what was actually done.

## Revision 44 (2026-10-12): the df12 tier runs, and both findings were mine

Revision 43 cleared the five ruff findings, which was the first condition for
`make lint` to advance past its first step. It advanced four steps, and stopped
at the fifth:

```text
tests/test_fix_plan_logging.py:50:4: R9104: Function 'emit' only forwards attribute access or a proxied call (trivial-attribute-wrapper)
tests/test_fix_plan_logging.py:183:4: R9103: Constant comparisons on 'case' would be clearer as a match statement (prefer-match-over-constant-chain)
make: *** [Makefile:177: lint] Error 8
```

Both findings are in the Observability test module this session added, and both
were previously invisible for the same reason the `C0302` pair was invisible in
Revision 42: `make` aborts on the first failure, so the df12 tier at
`Makefile:177` had never executed against this tip. The chain's progress is the
evidence -- ruff, interrogate (100%) and pylint (10.00/10) all pass now, and
the failure line has moved from `174` to `177`.

Neither is a false positive. A sweep of the tree found **no** suppression
convention for either rule: the only `logging.Handler` subclass in the entire
repository was the one in this test module, and no module elsewhere suppresses
`R9103`/`R9104`.

### 44.1 R9104: a bespoke handler where the repository has an idiom

`_RecordCollector` was a nine-line `logging.Handler` whose `emit` did one
thing: forward to `list.append`. That is precisely the shape `R9104` names. The
repair was not to suppress it but to delete it, because the repository already
has a log-capture idiom and this module was the only place not using it:

- `tests/test_discovery.py` (4 sites), `tests/test_check_command.py` (3),
  `tests/test_package_skeleton_bridge_sync.py` (1) all use
  `caplog: pytest.LogCaptureFixture` with
  `with caplog.at_level(logging.INFO, logger=...)`.

The rewrite follows that idiom exactly, including the `logger=` keyword, which
preserves the isolation property the bespoke handler was written to get: a
record emitted by a neighbouring module during the same call cannot satisfy an
assertion here. Extraction into a module-level `_planner_record(caplog)` helper
then replaced the fixture entirely, and with it the `list.append` forwarder,
`typing.Protocol`, `contextlib` and `collections.abc` all became unnecessary.
The module shrank from 311 to 261 lines.

The one-line-loses, multi-paragraph-wins behaviour of ruff's `DOC201` bit again
during this rewrite: expanding `_planner_record`'s docstring past one line
switched the return-contract rule on, and it wanted a `Returns` section.
Recorded here because it is the second occurrence of the same trap.

### 44.2 R9103: a string-keyed dispatch that wanted to be a `match`

The `test_planner_names_which_terminal_path_produced_the_plan` case built one
of three diagnostic tuples from an
`if case == "refused": … elif case == "fixed": …` chain. `R9103` is right that
a constant chain off one value reads better as a `match`, and the repository
already uses that idiom (`cli_pipeline.py:219`, `renderers.py:74`). The rewrite
also removed the duplication the chain had: each branch constructed an identical
`Diagnostic` with only the `TextEdit` differing, so a `_replacement(edit)`
helper now builds the diagnostic and the three cases supply only the edit.

### 44.3 Discrimination, re-established for the new shape

Rewriting a test that had already passed invalidates its discrimination proof,
so it was re-run rather than carried forward. The reverted tree is `HEAD:`'s
`plan.py` (no `_LOGGER`, no `logging` import); the fixed tree is the staged blob
`2651250a6c9992d78123a8a74583423f7d0bb06e`.

| Tree              | `plan.py`                                  | Result                                                                        |
| ----------------- | ------------------------------------------ | ----------------------------------------------------------------------------- |
| Unfixed (`HEAD:`) | `891916a81761c362da31f7b8e68e0677301f2f34` | **7 failed** -- `AssertionError: expected exactly one planner record, got []` |
| Fixed (staged)    | `2651250a6c9992d78123a8a74583423f7d0bb06e` | **7 passed**                                                                  |

The restoration is byte-identical (`sha256 1ef3caad…`), and the staged blob is
unchanged, so the proof did not perturb the tree it describes. The unfixed
failure mode is also the right one: the tests fail because *no event was
emitted*, which is exactly the observability gap the module exists to pin --
not because of a typo in the test.

### 44.4 What is still unverified

`make lint` now reaches `Makefile:177` and stops there. Steps 178--182 --
`ambrleaks`, `cargo doc`, `cargo clippy`, `whitaker`, `skylos` -- have **still
never executed** at this tip. Two of them are new-gate risks: `whitaker` and
`skylos` are the newest additions to the chain. Nothing in this revision
supports a claim about them, and a green `make test` would not change that.

### Lesson: the same masking mechanism, four revisions apart

Revision 42 recorded that a `C0302` pair hid behind an earlier `ruff` failure.
This revision found two `df12` findings hiding behind *that*. The mechanism is
identical and worth naming once: `make` reports the first failure only, so
every step after it is unverified, and "the gates fail on X" silently means "X
is the first thing that failed". The line number is the honest part of the
report, and the only trustworthy reading of a clean pass is one that names the
last step that *ran*.

## Revision 45 (2026-10-12): the assessment defects closed, and three claims re-proved by mutation

The `execplan-completeness-04b984da-1` assessment returned five in-scope
defects, four documentation corrections, and one disposition of its own earlier
claims. This revision records what was done about each, and -- more usefully --
how each new test was shown to be load-bearing rather than merely green.

It also carries the assessment's two explicit retractions, because a reader of
the older revisions would otherwise find them contradicted here: `--fix` is
**not** missing and was implemented before the assessment (Revision 43's
finding was about its *reporting*, not its existence), and **no new Python
tracing stack is required**. The existing stdlib logging boundary is a valid
implementation choice, and the assessment says so directly.

### 45.1 The five defects

| #   | Defect                                               | Repair                                                                                                                                                                  |
| --- | ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Execution refusals dropped when no file was written  | `print_unmodified_report` and `print_mutation_report` both render `outcome.fix_errors`, the only channel holding all of them                                            |
| 2   | A clean stream input produced an empty document      | `_document_bytes` distinguishes a refused plan from an unchanged one; the unchanged case emits `source_bytes`                                                           |
| 3   | Artefacts written through text streams               | `write_artefact` reaches the binary buffer, with a decoding fallback for injected text streams                                                                          |
| 4   | Stale-plan check covered only the pre-staging window | `write_source` revalidates after staging and before the swap, and documents the residual race                                                                           |
| 5   | Operational summary incomplete or invisible          | `cli_log` renders structured fields; the summary line reaches standard error; refusal detail is logged before collapse; the diff-render record measures the drawn patch |

### 45.2 The tests that were re-proved rather than assumed

The assessment's standing objection is that passing tests are not evidence of
coverage, so each new test was checked by breaking the code it claims to pin
and confirming the test fails. Three of them had to be **rewritten** because
the first version passed against the defect:

**The byte-fidelity subprocess test was vacuous.** Its first version passed
against a deliberately lossy writer
(`sys.stdout.write(payload.decode("utf-8"))`). The reason is environmental: on
Linux `os.linesep` is `\n` and Python 3.14 forces UTF-8 stdout even under
`LC_ALL=C`, so the lossy and binary writers emit identical bytes and the
assertion could not tell them apart. Forcing `PYTHONIOENCODING=latin-1` creates
a real discriminator -- latin-1 encodes `é` as one byte where UTF-8 needs two
-- and the test then failed against the lossy writer as it should. The
docstring records that the hostile encoding was verified necessary, so a future
reader does not remove it as decoration.

**The staging-window test needed a deterministic hook.** Concurrency would make
it flaky, so it intercepts `shutil.copystat`, which `write_source` calls
exactly between staging the replacement and swapping it in. Neutering the
revalidation to `if False and ...` made the test fail with
`DID NOT RAISE SourceChangedOnDiskError`.

**The field-list drift test scans the source.** It parses every `extra=` dict
literal under `python/stilyagi` and asserts the union is exactly
`cli_log.STRUCTURED_FIELDS`. Removing one entry from the list makes it fail with
`unlisted: ['patched_files']`. A restated list would have agreed with itself.

The remaining new tests were confirmed discriminating in the same way, one at a
time: the JSON `--diff` refusal test, the unsafe-only diff case, the `--diff`
render-record pair, and the ordered `--config` parser pins.

### 45.3 The unsafe-only diff case, and why it is not vacuous

`test_an_unsafe_only_diagnostic_exits_one_without_a_patch` asserts an empty
patch, and an empty patch has an obvious vacuous reading: maybe nothing was
planned at all. That reading was ruled out by driving the *same* runner through
`--fix --unsafe-fixes`, which writes the file and re-lints clean. So the edit
is well-formed, admissible, and source-backed -- it is excluded by the
applicability level alone, which is precisely the case the users' guide's
second bullet describes.

The runner guards its needle lookup for the same reason: a mutating run re-runs
it over the rewritten file, where "Paragraph" is gone, and an unguarded lookup
would turn a successful fix into a crash. This mirrors the mixed-outcome runner
in `test_check_mutation`.

### 45.4 A pre-existing defect fixed alongside, as the assessment allowed

`--config` combined `action="append"` with `default=()`. argparse's `append`
copies the default before appending to it, and copying a tuple yields a tuple,
so the flag raised `AttributeError: 'tuple' object has no attribute 'append'`
the first time it was used -- it had never worked. The assessment confirmed the
same code exists at the comparison base, so this is pre-existing rather than
branch-introduced. It is fixed at the site, with two parser pins, because it is
the same shape as the `--select`/`--ignore`/`--extend-select` defect already
repaired and the rationale had to be restated at the call site the shared
helper does not build.

### 45.5 Documentation corrected

Three statements the assessment identified as wrong, all of which were claims
about behaviour that the code does not provide:

- The execplan's recovery section claimed two-phase execution "means an
  interruption cannot leave a half-fixed tree". It can: the guarantee is per
  file, not per run, and `apply_planned_fixes` says so in its own docstring.
  The paragraph now states the limit and points at the implementation.
- `docs/users-guide.md` said an empty `--diff` patch exits `0`. Three distinct
  situations produce an empty patch and only the first exits `0`; the second
  (no *safe* fix eligible) and third (eligible fix refused) both exit `1`. The
  guide now lists the three cases, and each has a test.
- The subprocess-coverage limitation note is **retained**, not removed. It
  remains true: fix-producing rules are still not reachable through a real
  subprocess, so the rule-dependent halves are covered by injected
  collaborators. The new byte-fidelity case narrows the gap -- it exercises the
  production stream boundary for real -- without closing it.

### 45.6 The diff-rendering failure signal

The assessment's last observability gap was a missing failure signal at the
diff-rendering boundary. The signal needed care, because diff rendering has no
exception to catch that would distinguish anything: `patch_for` returns the
empty string for a plan with no replacement, and a refusal produces the same
empty string as a plan with nothing to do.

The state that actually needs naming is therefore a *disagreement* -- a file
was planned and contributed no patch -- and the record carries `planned_files`
and `patched_files` as separate counters for exactly that. One counter would
report `0` and be indistinguishable from a run that never planned anything. The
record also carries `elapsed_ms`, measured around the render itself, and
`patch_byte_count`, measured on the assembled patch rather than on the
replacement document (`replacement_byte_count` already measures that, in
`plan.py`, and the two are different quantities: a unified diff carries a
header, hunk context and markers the replacement does not).

`cli_log.STRUCTURED_FIELDS` gained both new keys. That is the failure mode the
drift test exists to catch -- without the test, a field written and never
rendered passes every other assertion in the suite while being invisible to the
human the record is for.

### 45.7 What is still unverified

### 45.8 The proof inventory, answered rather than waived

The assessment asks for the introduced or materially changed proofs and their
scrutiny. This is **not** a `not applicable`: the branch introduces property
tests, and they carry contract claims that are the reason the planning kernel
is trusted. Listing them is the honest answer; declining the question would
have been wrong.

**What the branch introduces.** `tests/test_fix_planner_properties.py` (274
lines) and its strategy module `tests/support/fix_plan_strategies.py` (125
lines) are both new. The properties, and what each actually constrains:

| Property                              | Claim                                                                            |
| ------------------------------------- | -------------------------------------------------------------------------------- |
| splice matches an independent oracle  | The production cursor splice agrees with a separate right-to-left implementation |
| splice length matches byte arithmetic | Removed and inserted UTF-8 lengths account for the result exactly                |
| splice is permutation-invariant       | Caller ordering cannot affect the output bytes                                   |
| exact duplicates coalesce             | Adding a byte-identical duplicate edit does not change the output                |
| accepted edits stay in one span       | Every accepted planned edit lies inside a single source-backed span              |
| in-place edits offer nothing          | An accepted edit rewriting a span with its own bytes reports no replacement      |
| straddling edits always abort         | A span crossing into synthetic text aborts the whole file's plan                 |
| conflicting edits never produce bytes | Two different replacements for one span preserve the source                      |
| empty plans offer nothing             | No eligible fixes means no replacement to write                                  |
| accepted plans remain valid UTF-8     | Accepted edits leave decodable source bytes                                      |

The oracle property is the load-bearing one: `apply_edits_naively` is a
deliberately separate implementation, so agreement is evidence about the kernel
rather than a restatement of it.

**What is deliberately not here.** No `verus`, no `kani`, no `CrossHair`. D-01
records the reason and it is specific, not a preference: both Rust proof tools
are absent from the workspace, the kernel they would verify is Python (by D-01,
because fixes are produced by Python rules), and standing up a proof toolchain
on the branch whose job is to ship the safety property would trade the property
for its ceremony. `hypothesis` is the Python analogue and is already a dev
dependency. This is a scoped decision with a recorded rationale, not an
omission.

**A second oracle, and what it is not.**
`crates/stilyagi-test-support/src/ round_trip_edits.rs` gained a
module-docstring paragraph this round stating that it is a golden-fixture
oracle, deliberately stricter than the production kernel on identical edits,
and that the strictness is intended under RFC 0002 §10 rather than a divergence
to fix. It was added because the temptation is real: a stricter instrument
reports differences that are not defects, and a future reader would otherwise
"fix" the oracle into agreement with the code it exists to check. Nothing
executable changed there -- three doc lines.

**The scrutiny limit.** These properties are evidence at `max_examples=64` per
property, which is Hypothesis's default-adjacent setting and is a *sample*, not
an exhaustive or symbolic result. They say the kernel agrees with its oracle
across 64 drawn cases each; they do not say it agrees for every input. That is
the correct scope for this kernel and it is stated here so no reader upgrades
it into a proof it is not.

### 45.9 What is still unverified

Nothing in this revision is evidence about the gate chain. Every claim above
rests on targeted suites run directly, not on `make lint` reaching its last
step, and the assessment is explicit that hosted checks establish gate success
rather than coverage of these paths. The full chain still has to run -- and per
Revision 44, steps after the first failure remain unverified until it does.

### Lesson: prove the test can fail, or it proves nothing

Three tests in this round were green and worthless. The byte-fidelity one
asserted a property the environment made true for *both* implementations; the
diff-render one would have passed on a field nobody rendered; the unsafe-only
one could have been satisfied by planning nothing at all. None of them was
detectably wrong from the suite output -- all three looked exactly like a
passing test.

The habit that caught them was mechanical: before trusting a new test, break
the thing it claims to pin and confirm the test fails. It is the same lesson
Revision 43 recorded for the `--config` probe ("probe it, do not read it") and
Revision 44 for the planner's event ("assert the failure mode is the right
one"), arriving a third time from a third direction. A test's green light is a
claim about the test, not about the code.

## Revision 46 (2026-10-12): the split left a gate failure behind it, and the mutating reporter had no test

Revision 45 closed with the assessment defects and three claims re-proved by
mutation. Two things happened since, and both are the same shape: a claim that
looked covered was not.

### 46.1 The split commit failed `ruff` after it landed

`f1042e3` split two test modules and rewrote their import blocks to do it. The
rewrite left two `TC` violations behind:

```text
tests/test_check_diff.py:12      typing-only-third-party-import       (pytest)
tests/test_check_mutation.py:24  typing-only-standard-library-import (pathlib)
```

Confirmed by piping each committed blob back through
`ruff check --stdin-filename`, so the finding is about the tree as committed
rather than about the working copy. `make lint` runs `ruff` as its first step
(`make lint`, the `$(RUFF) check` line) and `make` aborts on the first failure,
so the branch tip could not have completed step one -- the same masked-failure
mechanism Revision 42 identified, arriving from the opposite direction.
Revision 42 was pylint failing behind a ruff failure; this was ruff failing
behind nothing, in a commit that had itself just been written to clear a lint
failure.

The Makefile line is cited by target rather than by number on purpose. Revision
42 recorded `Makefile:164` for pylint; by this revision the same step is at
`Makefile:176`, because the file gained and lost lines in between. A line
number is a fact about the Makefile at one moment, so a claim that outlives it
should name the step.

Both names are annotation-only, so each moved into the existing
`if typ.TYPE_CHECKING:` block and no runtime import changed. Repaired in
`b16a6b9`.

**Lesson.** A commit that fixes a lint failure is not thereby a commit that
passes lint. The split was written against a *reason* (the two `C0302` errors)
and verified against targeted `pylint` runs, which is a claim about pylint
alone. `ruff` had been run earlier in the same session and had passed -- on the
pre-split files. Rerunning the whole gate, or at least rerunning `ruff` against
the post-split blobs, is what would have caught it. The specific instrument
worth keeping: `git show HEAD:<path> | ruff check --stdin-filename <path> -`
tests a *committed* blob, which is the only thing a gate will ever see.

### 46.2 `print_mutation_report`'s refusals were entirely uncovered

The assessment named the mutating reporter. Nothing held it to rendering
`outcome.fix_errors`. Mutating that argument to `()` and running the **full**
Python suite gave:

```text
652 passed
```

Zero tests noticed a mutating run silently dropping every refusal it had to
report. This is the same defect class the assessment raised, in the one branch
its tests structurally could not reach. (652 was the count at that moment; the
suite reached 653 once the coverage below landed, and the discrimination was
re-run against the final tree.)

The branch is unreachable from `tests/test_check_refusals.py` for a reason
worth stating: **a refused write leaves its target alone.** So a run whose
writes are all refused changes nothing, `outcome.changed_anything` is false
(`cli_apply.py`), and it reports through `print_unmodified_report`. The
mutating reporter is reached only when *some* write succeeded -- which means a
refusal can only ever be observed there next to a file that was written.

`tests/test_check_partial_runs.py` drives that shape: `a.md` is written, `b.md`
is refused by a selective `Path.replace` stand-in keyed on the target's name,
and the report is read from standard error, because that is where a mutating
run puts it. A blanket stand-in cannot reach the branch at all -- if every
write raises, nothing was written, and the run takes the unmodified path, which
is precisely why the refusals module never needed one.

Two construction details that cost probes to find:

- **Both edits must be source-backed.** An edit the planner rejects outright is
  a *phase-one* refusal that rides along in `checked`. The refusal under test
  is discovered at write time (phase two), so both plans have to be admissible
  enough to reach the writing phase. `rewrite_heading_marker` was tried first
  and produces the wrong kind -- it exits `1` with the refusal in `checked`.
- **The re-lint must be silent for both files.** `a.md` reads back as "Section
  text." and `b.md` as "# Memo", matching neither branch, so the refusal is the
  run's only finding and the exit status cannot stand in for its presence in
  the report.

The module is new rather than an addition to `test_check_mutation.py` because
228 + ~173 lands *above* the 400-line ceiling pylint enforces, not under it --
measured before choosing, per Revision 42's own precedent. 177 / 351 / 229 /
291 / 202 are the five resulting counts.

**Discrimination.** With `fix_errors=()` in `print_mutation_report`, the new
test fails; restored, it passes. That is the only evidence that makes it worth
keeping, and it is Revision 45's lesson applied on the first try rather than
after three bad tests.

### 46.3 The full gate chain runs green for the first time

Handed to `scrutineer` sequentially and all five targets pass at `d951c4c`:

| Target         | Result                                                         |
| -------------- | -------------------------------------------------------------- |
| `check-fmt`    | `ruff` 229 files, `cargo fmt` clean, `mdtablefix` 68 unchanged |
| `lint`         | all nine steps to completion -- the first time on this branch  |
| `typecheck`    | `ty 0.0.74`, all checks passed                                 |
| `markdownlint` | 0 errors across 69 files, `typos` clean                        |
| `nixie`        | all diagrams validated                                         |
| `test`         | 337 nextest + doc-tests + Python suite, 0 failures             |

`lint` reaching its last step is the point: interrogate, pylint 10.00/10,
df12-pylint 10.00/10, ambrleaks, `cargo doc`, clippy, whitaker and skylos had
all been unverified on this branch since Revision 42, because every earlier run
stopped at a step before them.

### 46.4 The environment stopped the work, not the code

Mid-session the single 1.8 TB filesystem holding `/`, `/home` and `/tmp`
reached 100% and then 0 bytes free. Every gate failed with `ENOSPC` rather than
a code defect:

- `check-fmt`: `uv` could not write `.uv-cache/simple-v21/pypi/...`
  (`os error 28`);
- `nixie`: `mkdtemp` raised `FileNotFoundError: No usable temporary directory`
  listing `/tmp`, `/var/tmp`, `/usr/tmp` -- and note the fourth entry, the
  worktree itself, because Python's `tempfile` falls back to the current
  directory and that is on the same full filesystem.

The stop hook then reported both as failures to fix. They were not: nothing in
the diff could have addressed `ENOSPC`, and `markdownlint`'s own line in the
same log already read `Summary: 0 error(s)`. The condition cleared when another
agent's build released space, and both targets then passed unmodified.

**Lesson.** An `ENOSPC` failure is a claim about the machine, not about the
branch, and it arrives through the same channel as a real gate failure. The
discriminator is in the message: a path and `no space left on device`, or a
temp-directory traceback, identifies the environment; a rule identifier and a
line number identifies the code. The corresponding instruction -- stop and tell
the user when the disk fills, do not route around it -- exists because a
plausible-looking repair for `ENOSPC` is to start deleting things that belong
to other agents.

## Revision 47 (2026-10-12): the last hosted gate, and what its rule actually counts

Revision 46 ended with the full gate chain green and left one hosted check
failing. This revision closes it, and records how the target was found.

### 47.1 The failure and why it survived a green local chain

At `532cb99` every deterministic gate passed -- `check-fmt`, all nine `lint`
steps, `typecheck`, 337 nextest plus the Python suite, `markdownlint`, `nixie`
-- and hosted CI still reported `CodeScene Code Health Review (main)` as
`fail`, leaving the PR in `BLOCKED`. The failing check is not part of `make` at
all, which is why a green chain said nothing about it.

Reproduced locally with `cs delta b5b0fe10 532cb99` (the same base and head the
hosted run compares), which named exactly two files and no others:

```text
python/stilyagi/cli.py
Code Health: (10.00 -> 9.38)
  New issue: Overall Code Complexity
     This module has a mean cyclomatic complexity of 4.14 across 7 functions.
     The mean complexity threshold is 4

tests/test_cli_log.py
Code Health: (8.95)
  New issue: Complex Method            _stamped_field_names cyclomatic 9 (threshold 9)
  New issue: Bumpy Road Ahead          _stamped_field_names, 2 nested blocks
  New issue: Deep, Nested Complexity   _stamped_field_names, nesting depth 4
```

The local run agreeing with the hosted one file-for-file is what makes it
usable as a measurement rather than a guess.

### 47.2 Measuring the metric instead of guessing at it

`cli.py` needed its mean complexity below 4.00, but the audit trail's first
instinct -- count every branch-like AST node -- gave a mean of 4.429, which is
not the number CodeScene reported. Rather than extract code until the score
moved, the counting rule was brute-forced: every combination of AST node
categories was scored against the reported 4.14, and exactly one rule
reproduces it.

CodeScene counts `If`, `BoolOp` (each extra operand), `IfExp`, and comprehension
`for`/`if` clauses. It does **not** count `ExceptHandler`, `For`/`While`,
`Assert`, or `With` in this file. The matching measurement:

```text
sum=29  n=7  mean=4.143  per-function=[3, 4, 6, 5, 3, 5, 3]
```

That converts the task from guessing to arithmetic: the mean divides by the
function count, so `sum <= 28` across 7 functions, **or** `sum <= 32` across 8,
both read below 4.00. The second bound is what matters here, because it is the
one a cohesive extraction has to satisfy -- splitting `_render_and_exit` moves
a whole block of decisions from one function to another, so the sum it must
clear is not lowered by the split.

Stating this plainly is necessary, because the arithmetic admits a reading the
policy forbids. A function whose only job is to divide a sum *is* a way to pass
this check, and it is exactly what the CodeScene guidance calls dilution. So
the bounds are a constraint on a decomposition that has to stand on its own
merits, not a licence to manufacture one. Section 47.3 is where that
distinction is argued and measured; what the arithmetic supplies is only the
target, and the fact that a passing extraction is allowed to leave the total
sum unchanged or even slightly higher, provided every function in the result is
a real unit.

### 47.3 The two extractions are cohesion splits, not dilution

`_render_and_exit` carried three concerns behind two `options.diff` guards: it
routed the rendered diagnostics to the right stream, assembled and wrote the
diff patch with its structured record, and computed the exit code. The patch
block -- assemble the bytes, measure and record their shape, write them through
the byte-preserving boundary -- is a unit with its own rationale (D-10), and it
moves to `_emit_patch` intact. Stripping comments, docstrings and indentation
from both versions leaves twelve executable statements that are identical line
for line, except that `resolved_collaborators.output` becomes the parameter
`output`. `_render_and_exit` drops from 5 to 3; the module lands at **sum 30 /
8 functions = 3.75**.

`_stamped_field_names` walked the AST and applied two shape filters inline.
Those filters are the whole of its syntactic knowledge, so they move to
`_extra_arguments` (find `extra=` keywords) and `_string_keys` (read a dict
literal's string keys), leaving the scan reading as a walk over modules.

The equivalence was checked rather than asserted: the pre-refactor body was
reconstructed verbatim alongside the new one and both were run over the tree.
They return identical 27-element sets, with nothing in either difference.
Stating it as "same files, same filters, same result" would have been a claim
about a diff I had written; running both is a claim about behaviour.

Both are the cohesive decomposition the CodeScene guidance asks for. No
threshold was raised, no rule disabled, no suppression added, and no function
was created whose only purpose is to divide a sum.

### 47.4 Discrimination

The repair is only evidence if the same measurement fails without it. Against
`532cb99` the delta names two files; against `0f7be63` it names none:

```text
$ cs delta b5b0fe10 0f7be63
No issues found in checked changes.
$ cs delta --output-format json b5b0fe10 0f7be63
(exit 0, zero-byte payload)
```

The empty JSON payload is CodeScene's machine-readable form of "no new issues",
not a failed invocation -- the exit status distinguishes them.

### Lesson: a gating metric is worth measuring, not approximating

A metric that gates a merge is worth measuring directly rather than
approximating. The first counter built here was wrong by 10%, and acting on it
would have meant extracting code in the wrong places until the number happened
to move -- metric gaming by accident rather than intent. Brute-forcing the rule
took one script and turned the target into arithmetic that can be checked
before an edit is made, which is what let a *single* extraction be chosen with
confidence instead of iterating against CI.

## Revision 48 (2026-10-12): the JSON report was two documents, and the docs described code that is not there

Revision 47 cleared the last hosted gate. The assessment reply at `0f7be63`
came back with three findings, all confirmed against the live tree before any
of them was acted on. Two were documentation that contradicted the code beside
it; one was a real reporting regression.

### 48.1 The JSON report did not parse

`print_unmodified_report` and `print_mutation_report` both appended
`fix_summary_line(...)` unconditionally after the renderer's output. With
`--output-format json` the stream was therefore a document followed by a
sentence:

```text
{
  "schema_version": "1.0.0",
  "diagnostics": [],
  "fix_errors": []
}
0 files fixed, 0 fixes applied, 0 files skipped (conflict), 0 fixes rejected
```

`json.loads` on the complete stream fails with `Extra data: line 6 column 1`.
Reproduced before it was fixed, in both the no-op and the refused-write case.
The users' guide promises `--output-format json` yields "a stable JSON
document", and a consumer parses the stream it is handed, not a substring of
it. This is the same defect class as the rest of this execplan's gate history
-- a claim about output that was only ever checked by substring assertion.

The repair is one predicate, `summarises_on_the_report`, called from both
reporters. The summary is text-format output; the JSON document is not
augmented with it. Nothing is lost, because `apply_fixes` already calls
`log_fix_summary`, which logs the identical sentence at INFO -- the level
`--verbose` selects.

**The stream arrangement differs between the two reporters, and assuming
otherwise was a mistake made here.** For a run that changed nothing, the report
goes to the injected output stream and *that stream parses whole*. For a
mutating run the report goes to standard error beside the rerun hint and the
console log records, so "the stream parses whole" is false there by design and
the document must be extracted. A test asserting the whole-stream property for
the mutating reporter failed for that reason and was replaced by one that pins
the narrower, true contract: the document is intact, and the summary sentence
is absent from the report.

Discrimination: reverting only the two guards makes all three new tests fail --
two with the original `Extra data` error, one on the summary's presence -- and
restoring them makes all three pass. No threshold, suppression, or rule change
was involved.

### 48.2 Two docstrings described the opposite of their code

`emit_fixed_document` claimed a refused plan emits the *original bytes*. The
implementation returns `None` from `_document_bytes` for that plan and emits
nothing, and its own test asserts no document. The bullet stated the intended
contract for the wrong case: emitting the source for a refusal would present a
run that fixed nothing as though it had returned a fixed document. The
docstring now says nothing is emitted and why, and that the return value is how
the caller learns it.

`write_source` claimed two operations remained between the second staleness
comparison and the swap, naming `shutil.copystat` and `Path.replace`.
`copystat` runs *before* the comparison, so it is covered by that check rather
than sitting beside it, and one operation remains in the window. The residual
race is real and unchanged; only its description was wrong.

Both are the failure mode this execplan has now recorded more than once: prose
written against the design that survived a change to the code. Neither was
caught by a gate, because both are docstrings that a passing test suite reads
as consistent.

### 48.3 What was retained

The subprocess-coverage limitation and the per-file atomicity limit both stand,
as the assessment agreed. Neither is hidden by passing hosted checks.

### Lesson: a documented contract needs an assertion at its own boundary

The JSON defect existed in plain sight because every test asserted a
*substring* of the output.
`'"identifier": "fix-error/write-failed"' in stream.getvalue()` is true whether
or not a sentence follows the closing brace, so the document could stop being a
document without any test noticing. The repair's tests assert at the boundary
the contract is written about -- the whole stream a consumer actually receives
-- and the mutating case taught the second half of the lesson: establish
*which* stream a contract applies to before asserting it, because one of the
two reporters shares its stream with human prose on purpose.

## Revision 49 (2026-10-13): the merge landed, lint reached step nine, and a CodeScene finding was misattributed

Revision 48 closed the assessment findings. This revision records the merge
resolution, the three gate repairs that followed it, and one correction to a
premise the earlier revisions worked from.

### 49.1 The merge, and why the push resolves the conflict

The PR read `mergeable: CONFLICTING` / `mergeStateStatus: DIRTY` because the
branch had never been merged with the main that now exists. `origin/main` was
`91941ef`, the merge base was `b5b0fe10`, and 15 paths were unmerged.

The merge was completed locally as `11c0011`, an ordinary two-parent merge
whose second parent is exactly `origin/main`'s tip. Of the 95 paths the merge
result differs from the first parent on, 24 are present in exactly one parent
and are pure additions. The remaining 21 have a merge result differing from
*both* parents, which is where real adjudication happened; none was a
`--ours`/`--theirs` selection.

Two of those are worth naming, because both were prose that had drifted from
code rather than a mechanical conflict:

- `docs/users-guide.md` said a `--diff` run exits `1` "whenever a diagnostic is
  present". That is false, and false in a way a passing suite would not show.
  `engine/checker.py`'s `_map_one_error` mints `Severity.WARNING` for every IR
  error entry whose code is not an authored-directive error code, and
  `diagnostics._FAILING_SEVERITIES` is `frozenset({Severity.ERROR})`. A run
  whose only diagnostics are warnings therefore exits `0`. The paragraph now
  says *failing* diagnostic and links to `#exit-codes`.
- `docs/developers-guide.md` claimed `parse_targets` expands the home
  directory. It does not; discovery owns that step.

**The push is what resolves the conflict.** `b5b0fe10` is an ancestor of the
new tip (76 commits back), so GitHub's merge of the branch into its recorded
base is a fast-forward and the conflicted state clears without any API change.
No base retarget is required, and none was attempted.

### 49.2 Three gate repairs, and the first time lint ran to step nine

Two full chains ran. The first stopped at `make check-fmt` step 3
(`mdtablefix`) and at `make lint` step 3 (`pylint`, `C0302`: the metrics test
module had reached 404 lines against the pinned 400 ceiling). Both were
repaired, committed as `338400a`, and the chain re-run.

That second run is the one that matters, because it reached further than any
before it. `make lint`'s nine steps are Makefile lines 174--182, and every
prior run on this branch had died at step 1 (`ruff`) or step 3 (`pylint`), so
**steps 4--9 had never executed**. The second run reached step 9 and reported:

```text
python/stilyagi/cli_io.py:47  SKY-U003  unused variable: _LOGGER
make: *** [Makefile:182: lint] Error 1
```

The finding is correct rather than a suppression candidate. `_LOGGER` was bound
once and read nowhere; the module reports user-facing messages through
`cli_log.command_logger()`, and every sibling module that keeps a module logger
references it at least twice. The `logging` import existed only to build it, so
deleting the binding alone would have converted the failure into a ruff `F401`.
Both were removed in `4168e56`. The removal also makes the code agree with its
own docstring, which already stated that the read boundary "raises this instead
of logging or printing".

A third full chain on `4168e56` is green end to end: all nine lint steps
complete, skylos silent, 357 nextest + 13 cargo doctests + 727 pytest + 61
docstring doctests (3 skipped).

### 49.3 The assessment's four corrections

CodeRabbit's reply to `execplan-completeness-04b984da-1` accepted the three
Revision 48 repairs and raised four claims that needed correcting. All four
were verified against the tree first:

1. `_json_document_in`'s docstring said slicing to the last brace makes the
   return value fail to parse if a sentence were appended. **It is the
   opposite.** `str.rindex` finds the *last* brace, so a trailing sentence
   carrying no brace is discarded by the slice rather than exposed by it. The
   helper now states this and names the assertion that actually detects the
   regression. This was a claim about detection written into the detector.
2. `fix_summary_line` said the command boundary prints it "unconditionally".
   Both reporters ask `summarises_on_the_report` first, so it prints for
   text-format reports. Corrected.
3. The developer guide stated the JSON stream is a document a consumer parses
   whole. True only for a run that changes nothing; a mutating run shares
   stderr with the rerun hint and log records.
4. The users guide said a program "can parse the whole stream a run hands it".
   Same over-claim, same qualification.

Corrections 3 and 4 are the general lesson of Revision 48 arriving a second
time: the earlier fix corrected the code and left the *description* of it one
step too strong. The docs now distinguish the two reporters explicitly.

### 49.4 What the CodeScene check actually compares, and whose code it flags

The first draft of this section claimed CodeScene was not a pull-request gate
because `.github/workflows/smoke.yml` runs no CodeScene step. That inference
was wrong, and Revision 47's own record is the counter-evidence: hosted
`CodeScene Code Health Review (main)` **failed** at `532cb99` and blocked the
pull request. The workflow grep only showed that the check does not come from
this repository's Actions; it is a separate Codescene App check, and it does
gate.

Re-measured at the comparison the hosted check actually performs -- the pull
request's **base**, `b5b0fe10`, not `origin/main` -- `cs delta b5b0fe10 HEAD`
(CLI 1.0.52) names exactly one file:

```text
python/stilyagi/check_execution.py
Code Health: (9.54)
  New issue: Complex Method   check_one_file cyclomatic complexity 9, threshold 9
  New issue: Large Method     check_one_file 81 lines, threshold 70
```

This is a **false attribution**, and the provenance is decisive:

- The file is **absent at the pull request's base** `b5b0fe10`. It is not part
  of the base the check measures against.
- It was created by `a86c8b8` on `main` and carried into `main` by `91941ef`
  ("Expand discovery defaults to Markdown, Python, and Rust (3.2.1)", #110),
  which is the very commit the merge second-parents.
- `git log b5b0fe10..d8bd85c -- python/stilyagi/check_execution.py` is empty:
  **this branch has never touched the file.**

Because the base lacks the file, the delta sees the whole 290-line file as
added by the comparison and reports main's function as a new issue. The finding
is real code health debt, but it belongs to `main` and to a separate change; it
is not introduced here and there is nothing in this branch to decompose.

Revision 47 did not make this mistake. Its two findings were `cli.py` (14
branch commits touching it) and `tests/test_cli_log.py` (touched by `0f7be63`
and `054b68b`), both genuinely branch-owned, and both were repaired in
`0f7be63` rather than suppressed. The distinction is exactly the one that
matters here: **a finding is actionable only when the branch owns the file**,
and the test for that is whether the file exists at the comparison base and
whether any branch commit touched it.

**Consequence for the merge.** The hosted check compares base `b5b0fe10` to the
pushed head. Once the merged head is pushed, this file stops being "added" by
the comparison, because the merge brings `b5b0fe10`'s descendant `91941ef` into
the head's ancestry and the file is no longer new relative to the base. The
`check_one_file` finding should therefore disappear from the hosted delta on
its own. It is not something this branch remedies, and it is not a reason to
modify a file the branch does not own. This is a prediction to be confirmed
against the hosted check after the push, not a claim to assert on the strength
of the local run.

What does stand from the earlier draft, and is worth keeping:

- The active ruleset `main-required-checks` requires exactly four checks --
  `lint-test`, `release-smoke (ubuntu-latest)`, `release-smoke (macos-latest)`,
  `release-smoke (windows-latest)` -- plus a `deletion` rule. There is no
  `pull_request` rule, so **no approving review is required** by repository
  policy.
- There is no tracked `.codescene/` config, so hosted rules come from project
  settings and the local CLI is a reproduction aid rather than the arbiter.

### 49.5 The stale `CHANGES_REQUESTED`, more precisely

`reviewDecision` reads `CHANGES_REQUESTED`. The cause is narrower than earlier
revisions assumed. The full review inventory is fifteen reviews, of which
exactly one requests changes: CodeRabbit's, submitted 2026-09-24 on `4b4842c`
-- a commit that is **not in this branch's history**, since the branch was
rewritten. Every other review is `codescene-access`, and its last three are
`APPROVED`, including one on the current head.

Two things follow. First, no amount of local work can change `reviewDecision`,
because GitHub recomputes it only when a new review arrives; the superseding
formal review is the mechanism. Second, the pull request is not blocked by a
review requirement at all, only by the mergeability state -- which the push
clears.

### Lesson: a report about a chain is not a report about its end

Three times now the same defect has appeared in a different costume. Revision
41's lesson was that a green step is not the same as a step that ran. Revision
42 found the stop hook over-reporting the targets it had executed. This
revision found `make lint` failing at step *nine* for the first time after nine
revisions of work -- a failure that had been sitting behind seven earlier steps
the whole time, invisible because the chain never got there.

The general form: whenever a pipeline reports the *first* failure, everything
after it is unverified, and any statement about the pipeline is a statement
about its stopping point. The habit that catches this is naming the coordinate
where the chain stopped -- the `Makefile:NNN` line, the step number -- because
a coordinate that has moved forward is the signal that previously hidden work
is now live.

### Lesson: an analysis is only as good as the comparison it names

Section 49.4 was written wrong twice before it was written right, and both
errors were the same error.

The first draft grepped `.github/workflows/` for a CodeScene step, found none,
and concluded the check does not gate. The grep was accurate; the inference was
not. Revision 47 was already on record saying the hosted check *failed* and
blocked the pull request, and the draft was written without reading it. A
negative search result is not a finding about system behaviour -- it is a
finding about one place something might have been configured.

The second draft ran `cs delta origin/main HEAD` and reported what it found.
The command was valid and the result was real, but CodeScene compares the pull
request's **base** `b5b0fe10`, not `origin/main`. The two differ by 73 files.
Measuring against the wrong base produced a plausible one-file finding that
then had to be explained, and the explanation on offer -- that the branch had
introduced code health debt -- was false. The file is absent from the base
entirely and no branch commit has ever touched it.

The habit that catches both: **before interpreting an analysis, state the
comparison it names and confirm it is the comparison that matters.** For a
provenance question the decisive commands are cheap, and they were the ones
that settled it after two wrong answers -- does the file exist at the stated
base, and did any commit in the range touch it. Neither was run before the
first two drafts, and either would have ended the question immediately.

A corollary worth recording separately, because it generalizes past CodeScene:
a file absent from the comparison base is reported as wholly new, so a
base-relative analysis will attribute another change's code to this one. That
is a structural artefact of diffing against a stale base, it will recur every
time a long-lived branch is measured this way, and the discriminator is always
the same pair of queries.
