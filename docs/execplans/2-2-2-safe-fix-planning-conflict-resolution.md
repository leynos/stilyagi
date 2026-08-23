# Implement safe-fix planning, conflict resolution, `--diff`, and `--fix` for Markdown

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
`Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`, `Decision Log`,
and `Outcomes & Retrospective` must be kept up to date as work proceeds.

Status: IN PROGRESS

Roadmap item: 2.2.2. Requires 2.1.1 (Markdown intermediate representation
envelope) and 2.2.1 (`stilyagi check`), both complete.

Branch base: this work stacks on `configure-df12-lints`, not on `main`. That
branch pins the `ty` typechecker and adds the `df12-python-lints` Pylint tier
and the `ambrleaks` snapshot scanner to `make lint`. Every measured fact below
was taken against that base. If the stack is ever re-pointed at `main`,
re-measure the baseline before trusting the gate numbers.

## Purpose / big picture

Today `stilyagi check` reads Markdown, extracts an intermediate representation
(IR), and prints diagnostics. It cannot propose or apply a repair. After this
change a user can run `stilyagi check docs/ --diff` to see exactly which bytes
Stilyagi would rewrite, and `stilyagi check docs/ --fix` to have it rewrite
them — with a hard guarantee that Stilyagi only ever edits bytes the IR vouches
for as coming from the original file, and refuses to touch a file at all when
two rules disagree about the same bytes.

You can see it working like this. Given a Markdown file and a rule that appends
a full stop to a list item, `stilyagi check notes.md --diff` prints a unified
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
  heading-depth limitation is accepted, documented in ADR 008, and raised
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
any gate failure you see is one you introduced.

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

### Measured facts you can rely on

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
- [ ] Milestone 2 — fix model, splice kernel, stub retirement (in progress)
  - 2026-08-24: committed the pure `fixes.py` value-model slice separately to
    preserve the required small rollback points. `Fix` accepts the RFC's bare
    string and list examples while normalizing them to hashable strict values;
    `Diagnostic.fix` is now typed. The package-layout snapshot was updated for
    the new module. The splice kernel, renderer contract, and stub retirement
    remain in this milestone.
- [ ] Milestone 3 — admissibility, selection, conflict resolution
- [ ] Milestone 4 — `--diff`
- [ ] Milestone 5 — `--fix`, `--unsafe-fixes`, and honest exit codes
- [ ] Milestone 6 — documentation, ADR 008, and the RFC 0003 amendment

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
  Recorded in D-03 and ADR 008, and must be raised against roadmap 2.3.1.

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

- Observation: `nodes` is roughly a third of the IR payload and no Python code
  reads it. Evidence: for an 87 KB Markdown file the canonical IR JSON is 2.01
  MB, of which `nodes` is 667 KB. Python reads only `ir["errors"]`,
  `ir["line_index"]`, and `ir["regions"][*]["kind"]` — and, from this slice,
  `segments`. Impact: gating `nodes` and `trees` out of the bridge payload
  would plausibly cut `stilyagi check` runtime by about 30%. **Out of scope** —
  it is a check-path win with no bearing on fix planning, and it would churn
  every golden IR snapshot. Recorded here so the measurement is not lost; raise
  it as a separate roadmap item.

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

You are working in a mixed Rust and Python repository. Rust crates under
`crates/` parse source into the IR; a PyO3 bridge (`crates/stilyagi-pyext/`)
exposes extraction to Python; the Python package under `python/stilyagi/` holds
the command-line interface, configuration, the diagnostic model, and the not
yet built rule engine. **All work in this plan is Python** (see D-11).

Read these first. They are the authority when this plan and the code disagree.

- `docs/stilyagi-design.md` — §4 (the "Applying safe fixes in CI or pre-commit"
  flow, and the "Fix and edit model" and "Diagnostics output" subsections) and
  §7.3.
- `docs/rfcs/0002-stilyagi-python-rule-api.md` §§9–10 — the ratified diagnostic
  and fix shapes. Note the worked example in §4, which passes
  `applicability="safe"` as a bare string and `edits=[...]` as a list; the
  model must accept that (see D-14 and the interface section).
- `docs/rfcs/0003-stilyagi-cli-contract.md` §§3.1, 10, 11, 12.
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
- pytest collects no doctests. The `>>>` examples AGENTS.md requires are
  unverified prose; write them carefully.
- Markdown prose wraps at 80 columns, code blocks at 120; tables and headings
  are unwrapped. Run `make fmt` before `make markdownlint`.
- Spelling is en-GB-oxendict: "-ize", "-yse", "-our". Write "normalize" and
  "serialize" but "behaviour" and "analyse". Backtick every identifier — the
  spelling gate skips code spans. Never hand-edit `typos.toml`; use
  `make spelling-config-write`.

### The files you will touch

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
`docs/adr-008-safe-fix-planning-and-conflict-resolution.md`.

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
    def insert_before(cls, span: ir_view.SourceSpan, text: str) -> "TextEdit": ...

    @classmethod
    def insert_after(cls, span: ir_view.SourceSpan, text: str) -> "TextEdit": ...

    @classmethod
    def replace(cls, span: ir_view.SourceSpan, text: str) -> "TextEdit": ...

    @classmethod
    def delete(cls, span: ir_view.SourceSpan) -> "TextEdit": ...


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
constructs
`Fix(title=..., applicability="safe", edits=[TextEdit.insert_before(...)])` — a
bare string and a list. Without coercion, `fix.applicability.value` in the JSON
renderer raises `AttributeError` on a `str`, and `Fix` becomes unhashable. The
repository already has this pattern: `python/stilyagi/config/schema.py`
normalizes every sequence field in `__post_init__`. Use `object.__setattr__` as
that module does, since the dataclass is frozen.

The constructor helpers are ratified surface — `TextEdit.insert_before` appears
in RFC 0002 §4 and again in RFC 0005. They cost about fifteen lines and they
pin the `span=` parameter shape now, rather than letting 2.3.1 invent one and
retrofit.

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

| Module             | Contents                                                                                                    | Branch budget |
| ------------------ | ----------------------------------------------------------------------------------------------------------- | ------------- |
| `splice.py`        | `apply_edits(source_bytes, edits) -> bytes`                                                                 | 1             |
| `admissibility.py` | `containing_span(edit, spans)` via `bisect`; `classify_edit(...) -> EditRejection \| None`                  | ≤4            |
| `selection.py`     | `is_candidate(diagnostic, level, lint_config) -> bool`; `select_candidates(...)` as a comprehension over it | ≤3            |
| `conflicts.py`     | `coalesce_identical(edits)`; `first_overlap(edits)`                                                         | ≤1            |
| `plan.py`          | `plan_fixes(request) -> FixPlan` — straight-line composition                                                | ≤3            |
| `diff.py`          | `unified_diff(before, after, reported_path) -> str`                                                         | ≤3            |
| `write.py`         | `write_source(path, content)`                                                                               | ≤3            |

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
`shutil.copystat`, then `os.replace`. Never truncate in place. Resolve symbolic
links first and write to the resolved path so a link is not replaced by a
regular file. Skip the write entirely when the new bytes equal the old, so
`--fix` does not churn modification times across a documentation tree and wake
every file watcher.

### `python/stilyagi/cli.py` (Milestone 0)

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
- **`ALL`:** reserved as a pseudo-prefix. Note in ADR 008 that RFC 0002 §12
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
pytest fixture, so you avoid needing
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

### Milestone 6 — documentation, ADR 008, and the RFC amendment

Write `docs/adr-008-safe-fix-planning-and-conflict-resolution.md` with the
sections `docs/documentation-style-guide.md` requires: Status (Accepted, with
date), Date, Context and Problem Statement, Decision Drivers, Requirements,
Options Considered (a comparison table with a caption below it), Decision
Outcome, Goals and Non-Goals, Migration Plan, Known Risks and Limitations, and
Architectural Rationale. In review experience, Decision Drivers, Options
Considered, and Migration Plan are the sections that get stubbed — do not stub
them.

Its substance is D-03, D-04, D-05, D-07, D-10, and D-13. **State explicitly
that a heading-depth rule cannot be auto-fixed under this admissibility
model**, that widening to node spans was considered and rejected as vacuous,
and that roadmap 2.3.1 must be reviewed against this constraint before it
starts.

Amend `docs/rfcs/0003-stilyagi-cli-contract.md` §10 to record that `--fix` with
`--diff` is a usage error, with the rationale. Without this the exit-2 path is
undocumented (D-06).

Update:

- `docs/users-guide.md` §3 — `--fix`, `--unsafe-fixes`, `--diff`; why a fix can
  be refused, in user language ("Stilyagi only edits text it can trace back to
  your file byte-for-byte"); the fix-error identifiers; that a conflict leaves
  the file entirely unmodified and needs a human; that `--fix` may need
  re-running; the stream contract; `lint.fixable`/`unfixable` semantics
  including their orthogonality to `--select`/`--ignore`; and a rewritten exit
  codes block. Also correct the now-false sentence near line 333 saying fix
  workflows land in later slices.
- `docs/developers-guide.md` §2b — a "Fix planning" subsection between
  "Diagnostics" and "Rendering"; the `CheckCollaborators` change under
  "Collaborator injection"; the revised "Exit codes"; and a note that
  `engine.fix_planning.splice.apply_edits` is normative.
- `docs/stilyagi-design.md` — the "Fix and edit model" subsection gains the
  fix-error identifiers, the admissibility rule, and an ADR 008 link. Under
  "Internal golden IR and edit helper scaffolding", update the claim that the
  round-trip helpers establish the safety checks, now that the production
  kernel exists.
- `crates/stilyagi-test-support/src/round_trip_edits.rs` — one sentence in the
  `//!` comment recording that it is deliberately stricter than the engine on
  identical edits and is a golden-fixture oracle, not a second engine. This is
  the only Rust change in the slice.
- `docs/contents.md` — index ADR 008 and this ExecPlan.
- `docs/roadmap.md` — tick 2.2.2, matching the "Completed with validation
  evidence in …" pattern used by earlier entries.

Stage D: `make fmt`, then `make markdownlint` and `make nixie`, then the full
chain.

Commit: `Document safe-fix planning and record ADR 008`.

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
with `os.replace`, so an interrupted run leaves the original intact, and
two-phase execution means an interruption cannot leave a half-fixed tree. When
developing, only run `--fix` against `tmp_path` fixtures or a scratch directory
— never against the repository's own Markdown, which is gated by markdownlint.

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
  tests, with 17 snapshots reviewed. CodeRabbit is intentionally deferred
  until the complete Milestone 2 implementation is ready for review.

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

**Revision 10, 2026-08-24.** Recorded the independently gated, atomic
Milestone 2 fix-model slice. Its small commit satisfies the repository's
rollback policy without declaring the milestone complete or running CodeRabbit
before the kernel and renderer contract are in place.

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
