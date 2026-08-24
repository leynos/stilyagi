# Expand discovery defaults to `*.md`, `*.py`, and `*.rs`

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
`Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`, `Decision Log`,
and `Outcomes & Retrospective` must be kept up to date as work proceeds.

Status: IN PROGRESS

Approval gate: **satisfied on 2026-08-23**. The implementation request
explicitly approves this ExecPlan.

This is planning round 2. Round 1 was written from direct inspection of the
working tree plus executed probes against the built extension. Round 2 rewrites
it after a six-lens design review that changed three of the seven decisions and
removed roughly a third of the proposed Rust surface. The review's substantive
outcomes are recorded in the Decision Log as D1 (reversed), D5 (reversed
polarity and relocated), and the new D8 through D11; its remaining findings are
carried in `Risks` and in the milestone-2 work items. See the Revision note.

## Purpose / big picture

Roadmap item 3.2.1 (see [docs/roadmap.md](../roadmap.md) §3.2) is the first
step of the second vertical slice. It turns `stilyagi check` from a
Markdown-only command into a mixed-repository command, per
[Stilyagi design](../stilyagi-design.md) §7.3 and
[RFC 0003](../rfcs/0003-stilyagi-cli-contract.md) §7.

After this change, a maintainer standing in a mixed documentation and source
repository can run:

- `stilyagi check .` and have Stilyagi discover **every** `*.md`, `*.markdown`,
  `*.py`, and `*.rs` file beneath the current directory in one deterministic,
  path-sorted pass, select the correct extractor for each file from its
  extension, and print diagnostics attributed to the right path;
- `stilyagi check src/lib.rs docs/guide.md` and have both files analysed, each
  through its own extractor, in one invocation;
- `stilyagi check - --stdin-filename src/mod.rs` and have standard input
  analysed as Rust rather than as Markdown; and
- read a summary line that says **how many files were actually checked**, so a
  run that checked nothing is visibly different from a run that checked
  everything.

The primary acceptance demonstration is that, from this repository's root,
`stilyagi check python/ crates/ docs/` processes 176 Python, Rust, and Markdown
files and exits `0`. The corroborating demonstration is that `stilyagi check .`
additionally reaches the deliberately adversarial fixture corpus and exits `1`,
driven by exactly two `suppression-blanket-forbidden` **errors** — and not by
the tree-sitter parse-recovery notices on the deliberately malformed Rust
fixture, which are reported as warnings and do not fail the run.

The observable success condition is behavioural. A behaviour-driven-development
(BDD) feature drives `stilyagi check` over temporary mixed trees and asserts
per-extension extractor selection, ordering, exit codes, and the summary line;
an end-to-end test invokes the command as a real subprocess; a `hypothesis`
property pins discovery determinism; and snapshot tests pin the text and
JavaScript Object Notation (JSON) renderings of a mixed-source run.

Two downstream roadmap items are unblocked by this one: 3.2.3
(`Requires 3.1.3, 3.2.1, and 2.2.2`) and 3.3.1 (`Requires 3.2.1 and 2.2.3`).

### Milestone structure

The work splits into two sequenced milestones on one branch. Both must land
before roadmap item 3.2.1 is ticked. The split exists because they are
different kinds of change with different blast radii, and reviewing them
together obscures that.

- **Milestone 1 — discovery and dispatch.** Purely additive. It changes which
  files are found and which extractor each one gets. Nothing about an existing
  Markdown-only run changes.
- **Milestone 2 — classification, severity, and observability.** This changes
  the meaning of the exit code and the shape of the rendered output for *every*
  run, not just mixed ones. It deserves its own red-green cycle and its own
  review.

### Scope boundary (what this slice deliberately excludes)

- **Built-in docstring and doc-comment rules.** Roadmap item 3.2.2. The rule
  registry still matches nothing; `python/stilyagi/rules/registry.py` is
  unchanged.
- **`dump-ir`, fix planning, `--fix`, `--diff`, and `--no-cache`.** Roadmap
  items 2.2.2 and 2.2.3. Only `check` is touched.
- **Cache-key separation by syntax.** Roadmap item 3.3.1, which explicitly
  `Requires 3.2.1`.
- **New extractors.** No new language is implemented. The Rust extractor already
  supports all three syntaxes end to end; this plan teaches discovery and the
  command-line interface (CLI) how to reach the two that were unreachable.
- **Moving discovery into Rust.** The design document states that Rust owns file
  discovery ([Stilyagi design](../stilyagi-design.md) §1), so today's Python
  walk is the deviation, not the plan. Relocating it needs a new Cargo
  dependency and a faithful reproduction of the reported-path semantics, and it
  is plainly not "expand discovery defaults". See Decision Log D1 and D8.
- **`.gitignore` honouring.** RFC 0003 §7 makes this a SHOULD. Roadmap item
  2.2.1 deferred it to avoid a new Python runtime dependency, and that deferral
  stands. See D8 for why the deferral's justification expires when discovery
  moves to Rust.
- **`include` / `exclude` configuration keys.** RFC 0003 §6 defines none, and
  roadmap item 2.2.1 explicitly removed an invented `[discovery] include` key
  as out-of-contract. See D2.
- **`*.mdx`, `*.pyi`, and every post-v1.0 language.** Documented as future
  targets in ADR 008, not implemented.
- **Any IR schema change.** `SCHEMA_VERSION` is not bumped; `IrError` gains no
  fields. See D5.
- **New CLI flags.** No `--fail-on`, `--max-warnings`, `--max-file-size`, or
  `--jobs`. RFC 0003 defines none of them, and inventing CLI surface ahead of
  the contract is the mistake D2 exists to avoid. Each is recorded in ADR 008
  as required follow-up.

## Constraints

Hard invariants. Violating one requires escalation, not a workaround.

1. **No IR schema change.** `crates/stilyagi-ir/src/document.rs`
   `SCHEMA_VERSION` must not change, and `IrError` must not gain or lose fields.
2. **No new runtime dependency.** Neither `Cargo.toml` `[dependencies]` nor the
   `pyproject.toml` runtime dependency set may gain an entry. Test-only
   development dependencies already present (`rstest`, `rstest-bdd`, `insta`,
   `proptest`, `pytest`, `pytest-bdd`, `syrupy`, `hypothesis`) may be used
   freely.
3. **Vocabularies that appear in bridge payloads are Rust-owned.** Any string
   Python receives from, or sends to, `_stilyagi_rs` must have exactly one
   definition, in Rust, advertised through the bridge and parity-checked in
   Python. This is the rule that justifies `supported_syntaxes()` and
   `supported_region_kinds()`, and it is why IR error codes are Rust-owned.
   Vocabularies that appear in **no** bridge payload — file extensions — are
   outside it. See D1.
4. **Determinism.** For any target set, `stilyagi check` must process files in a
   total order determined solely by resolved path, independent of the order in
   which targets were supplied, and must process each resolved path exactly
   once.
5. **Exit-code contract.** RFC 0003 §12 stands: `0` when no violations remain,
   `1` when violations remain, `2` on invalid configuration, invalid usage,
   plugin load failure, or internal error.
6. **Public Python import surface.** The surface documented in
   [users' guide](../users-guide.md) §1a must keep working unchanged.
   `stilyagi.discovery` is *not* in that surface and may be renamed.
7. **Every commit is gated.** `make check-fmt`, `make typecheck`, `make lint`,
   and `make test` must pass before each commit; `make markdownlint` and
   `make nixie` must additionally pass for any commit touching Markdown.
8. **British English.** en-GB-oxendict spelling throughout, enforced by the
   `typos` gate inside `make markdownlint`.
9. **Fail-safe classification.** Any diagnostic-classification default
   introduced by this plan must fail towards *warning*, never towards *error*.
   An unrecognized extractor notice must not be able to break a user's build.

## Tolerances (exception triggers)

Code and documentation are budgeted separately, because the documentation work
is bounded and predictable while the code work is where surprises live.

- **Code scope:** more than 18 code files changed, or more than 550 net lines of
  code added, across both milestones.
- **Documentation scope:** more than 8 documentation files changed. ADR 008 and
  its tables are expected to be large; that is not a breach.
- **Dependencies:** any new entry in `Cargo.toml` `[dependencies]` or in the
  `pyproject.toml` runtime dependency set. (Also Constraint 2.)
- **Interface:** any change to the signature of `_stilyagi_rs.extract_document`,
  to `stilyagi.engine.extract_document`, or to any symbol in Constraint 6.
- **Schema:** any need to change `SCHEMA_VERSION` or `IrError`.
- **Diagnostic model:** milestone 2 may add a severity *value* to a diagnostic
  and may add a summary object to the renderers. If it needs a new **field** on
  `Diagnostic`, stop — that is roadmap item 3.2.3's territory.
- **Iterations:** a given gate still failing after 3 corrective attempts.
- **Time:** any single work item exceeding 3 hours.
- **Performance:** if the Markdown per-file warm median in the structural probe
  regresses more than 20% against the checked-in roadmap 1.3.3 baseline, stop.
  Nothing in this change should slow Markdown down; if it does, the per-file
  syntax lookup or the anomaly-set membership check is on the hot path.

## Risks

- **Risk:** Extraction degradation silently removes prose from scope. A
  tree-sitter grammar bump, or a language edition the pinned grammar predates,
  makes files parse partially:
  `crates/stilyagi-tree-sitter/src/rust/builder.rs` clears pending doc comments
  on encountering a recovery node, and abandons an entire subtree past
  `MAX_TRAVERSAL_DEPTH`. Under D4 those become warnings and the run exits `0`.
  Severity: high. Likelihood: medium. Mitigation: this is why W6 exists. The
  summary line reports files checked and files degraded, giving the warning
  count a denominator; and a region-count regression test over the fixed corpus
  makes a coverage-reducing grammar bump fail Stilyagi's own suite before it
  reaches users. `--fail-on` / `--max-warnings`, the proper remedy, is recorded
  in ADR 008 as follow-up.

- **Risk:** One unreadable file poisons an entire run. `had_error` is a single
  boolean ORed across every file, and `compute_exit_code` returns `2`
  unconditionally when it is set, discarding every diagnostic found. The JSON
  payload then reports a clean run on stdout while the exit code says internal
  error. Severity: high. Likelihood: medium, and materially raised by this
  change — PEP 263 permits non-UTF-8 `.py` source, so a
  `# -*- coding: latin-1 -*-` file is legal Python that
  `read_text(encoding="utf-8")` rejects. Non-UTF-8 Markdown is a curiosity;
  non-UTF-8 legacy Python is ordinary. Mitigation: W6 widens the read to
  `utf-8-sig`, catches `OSError` and `MemoryError`, and reports the user's path
  rather than the resolved path. The deeper redesign — per-file read failures
  becoming per-file diagnostics rather than a run-wide fatal — is **not**
  attempted here and is recorded in ADR 008 as required follow-up, because it
  changes what exit `2` means.

- **Risk:** The expanded ignored-directory list is name-based, so it prunes a
  directory a user legitimately wants checked, and fails to prune generated
  source that does not match a known name — `CARGO_TARGET_DIR` pointed
  elsewhere, a Cargo `OUT_DIR` full of `bindgen` or `prost` output, `*_pb2.py`,
  `vendor/`, `third_party/`, `bazel-*`. Severity: medium. Likelihood: high for
  the second half. Mitigation: generated source is exactly the code the pinned
  grammar parses worst, so this compounds the first risk. The name list is an
  acknowledged stopgap; ADR 008 records that the remedy is gitignore support
  via the `ignore` crate once discovery moves to Rust, not a perpetually
  growing name list.

- **Risk:** A symlinked directory target is skipped at INFO level, so a CI gate
  can be silently inert from the day it is merged. `/app -> /src`, Bazel output
  trees, and Docker volume mounts all hit this. Severity: high. Likelihood:
  low-to-medium. Mitigation: W6 raises it to WARNING and counts it in the
  summary as skipped.

- **Risk:** Severity is being used as the exit-code axis, but RFC 0003 §3.2
  requires every rule to document a *default severity* and §3.3 requires
  filtering by it. When roadmap item 3.2.2 ships a rule whose default severity
  is `warning`, that rule violation will print without gating. Severity:
  medium. Likelihood: high, at 3.2.2. Mitigation: the distinction actually
  needed is violation versus non-violation, which is orthogonal to severity.
  Introducing that discriminator now would mean a new `Diagnostic` field, which
  the tolerances forbid. Instead W6 names the failing severities in one
  explicit constant, documents on `Diagnostic` that `WARNING` does not gate,
  and ADR 008 records this as a constraint roadmap item 3.2.2 must resolve
  before it ships its first warning-severity rule.

- **Risk:** This repository cannot dogfood `stilyagi check .` in continuous
  integration, because `tests/fixtures/corpus/python/valid/` and
  `tests/fixtures/corpus/rust/valid/` contain deliberate bare
  `# stilyagi: disable` blanket suppressions to exercise the forbidden path.
  Severity: low. Likelihood: certain. Mitigation: the exit `1` is *correct*
  behaviour, so nothing is broken. The acceptance demonstration leads with an
  explicit target list. ADR 008 records the clean remedy — extending the
  existing `.md.fixture` / `.py.txt` naming convention to the adversarial
  Python and Rust corpus files so they fall outside discovery — as follow-up,
  since it touches `crates/stilyagi-test-fixtures/src/fixture_paths.rs` and
  `tests/test_corpus.py`.

- **Risk:** Discovery walks far more files, exposing fixed per-file cost.
  Severity: medium. Likelihood: medium. Mitigation: measured against a real
  baseline rather than guessed. See W6's performance item; note the file count
  grows 3.6× but total bytes only ~1.5×, because this repository's Markdown is
  far larger per file than its source.

- **Risk:** `unclosed-function.py.txt` — the malformed Python fixture named to
  keep tooling from treating it as importable Python — starts being discovered.
  Severity: low. Likelihood: low. Mitigation: matching uses the *final* suffix,
  so `.py.txt` resolves to `.txt`. A regression test pins it.

## Progress

Milestone 1 — discovery and dispatch:

- [x] W0. Confirm the tree matches this plan's anchors; capture the baseline
      (2026-08-23).
- [x] W1. Generalize discovery beyond Markdown, carrying the selected syntax
      (2026-08-24).
- [x] W2. Select the extractor per file in the `check` loop, including stdin
      (2026-08-24).
- [x] W3. Milestone-1 tests: units, `hypothesis` property, BDD scenarios,
      end-to-end subprocess (2026-08-24).
      CodeRabbit review of commit `21471d5` completed with zero concerns.

Milestone 2 — classification, severity, and observability:

- [x] W4. Declare the authored-directive error codes in Rust beside their mint
      sites and advertise them through the bridge (2026-08-24).
- [x] W5. Classify IR errors, make the exit code severity-aware, and harden the
      file read (2026-08-24).
- [x] W6. Emit a run summary; milestone-2 tests, snapshots, region-count
      regression, and the performance measurement (2026-08-24).
      All six deterministic gates passed, then CodeRabbit reviewed commit
      `764bde2` with zero concerns.

Closing:

- [x] W7. Documentation: ADR 008, design §7.3, users' guide, developers' guide,
      contents index (2026-08-24). CodeRabbit reviewed commit `a8456f3` with
      zero concerns.
- [x] W8. Tick roadmap item 3.2.1; record outcomes (2026-08-24). The closing
      Markdown gates passed and CodeRabbit reviewed commit `27696d5` with zero
      concerns. Review remediation passed all six gates (342 Rust tests, 224
      Python tests, 17 snapshots); follow-up CodeRabbit review is pending.

## Surprises & discoveries

Found during planning by executing probes against the built extension, and
during the round-2 design review. These are the evidence base for the Decision
Log; they are why this plan is larger than "add three strings to a frozenset".

- **S15 (review follow-up). Recursive-walk coverage did not prove the explicit
  symlinked-directory target contract.**
  `test_directory_recursion_skips_noise_ and_symlinked_directories` only
  creates a symlink encountered below an ordinary directory target. It
  therefore cannot exercise `_candidates_for_target`'s early return for a
  symlinked directory specified on the command line. Add a CLI regression test
  that asserts its warning and load-bearing
  `checked 0 files (1 skipped, 0 unreadable)` summary. The same review found the
  `.md.fixture` corpus explanation still claimed that only Markdown suffixes
  were discoverable; correct it to describe final-suffix matching and the
  delivered four-suffix default. Date/Author: 2026-08-24, implementation agent.

- **S14 (implementation). The rebased baseline has 236 tracked discovery
  candidates, not 233.** After the baseline gates materialized `.uv-cache`, the
  W1 pruning policy yielded 65 Markdown, 78 Python, and 93 Rust tracked files.
  This is three more source files than the planning-time snapshot (two Python
  and one Rust), while the Markdown count remains 65. The acceptance commands
  must use the live counts established after W1 rather than the stale 233-file
  figures in this draft. This is a base-branch evolution, not a design
  deviation.

- **S1. The Rust side is already complete; the gap is entirely in Python.**
  `ExtractSyntax` already has all three variants and dispatches all three; the
  PyO3 bridge already round-trips all three; `model.Syntax` already has all
  three members. The load-bearing gap is exactly two things:
  `_MARKDOWN_SUFFIXES` in `python/stilyagi/discovery.py`, and the hard-coded
  `model.Syntax.MARKDOWN` in `_check_one_file` in `python/stilyagi/cli.py`. No
  extractor work is needed.

- **S2. Unlike Markdown, the Python and Rust extractors do populate IR
  `errors[]`, and every entry currently becomes an error-severity diagnostic.**
  Roadmap item 2.2.1 established that malformed Markdown recovers with an empty
  `errors[]`, so `check` exits `0`. That does not generalize:

  ```plaintext
  python/malformed: OK regions=1 errors=2 codes=['python-parse-recovery', 'python-parse-recovery']
  rust/malformed:   OK regions=1 errors=2 codes=['rust-doc-comment-error-subtree', 'rust-parse-recovery']
  garbage/python_docstring: OK regions=0 errors=3
  garbage/rust_doc_comment: OK regions=0 errors=1
  garbage/markdown:         OK regions=1 errors=0
  ```

  Because `map_ir_errors` hard-codes error severity and `compute_exit_code`
  returns `1` for any non-empty list, expanding discovery without milestone 2
  would make `stilyagi check .` fail on every repository containing a file the
  pinned grammar cannot fully parse. Neither extractor *raises*, so there is no
  exit-`2` explosion — only misclassified severity.

- **S3. A full-repository dry run quantifies the change exactly.**

  ```plaintext
  discovered counts: {'md': 64, 'py': 76, 'rs': 92} total 232
  files producing IR errors: 3
    tests/fixtures/corpus/python/valid/module-class-function-docstrings.py  1  ['suppression-blanket-forbidden']
    tests/fixtures/corpus/rust/malformed/unclosed-item.rs                   2  ['rust-doc-comment-error-subtree', 'rust-parse-recovery']
    tests/fixtures/corpus/rust/valid/item-doc-comments.rs                   1  ['suppression-blanket-forbidden']
  ```

  Two caveats on that transcript, both instructive. The Markdown count is now
  65, because this ExecPlan is itself a discovered file. And the probe ran
  before any `make` target had materialized `.uv-cache` in the worktree, so it
  did not expose the pruning gap S13 later found — the figure was right by
  luck. With W1's corrected prune list and this file present, the current
  figure is 233.

  Discovery grows 64 → 233 files (3.6×). All valid sources produce zero IR
  errors — a separate probe over 16 production files returned
  `TOTAL ERRORS on valid sources: 0`. The only noise comes from fixtures that
  are deliberately adversarial. Note this is a snapshot against *today's pinned
  grammars*, not a property of the design; the grammar-bump risk is exactly the
  event that invalidates it.

- **S4. The design document's §7.3 critique of RFC 0003 is stale, and history
  proves it.** Design §7.3 says the RFC "includes too many source-language file
  types". At the RFC's original commit `bbf93da`, §7 read:

  ```plaintext
  v1 built-in discovery SHOULD include at least:

  - `*.md`
  - `*.mdx`
  - `*.py`
  - `*.rs`
  - `*.js`
  - `*.ts`
  - `*.tsx`
  ```

  That is the over-claim. It was trimmed to the current three-extension list by
  `787526e` ("Add RFC harmonization execplan", roadmap item 1.1.3). W7 corrects
  the §7.3 text rather than layering new content on a contradiction. Settled;
  no further archaeology needed.

- **S5. The IR error-code vocabulary is eight codes, and it splits cleanly.**
  `python-parse-recovery`, `python-traversal-depth-limit`,
  `rust-parse-recovery`, `rust-traversal-depth-limit`,
  `rust-doc-comment-error-subtree`, and `rust-doc-comment-span` are grammar or
  traversal anomalies. `suppression-blanket-forbidden` and
  `suppression-unknown-verb` are things a human wrote incorrectly. `IrError`'s
  own doc comment already reads "Non-fatal parser or extractor anomaly".

- **S6. `Severity.WARNING` already exists and is entirely unused.** Milestone 2
  needs no model change — it populates a value the model already reserved.

- **S7 (round 2). `stilyagi-ir` is a leaf crate, so six of the eight codes are
  minted downstream of it.** `crates/stilyagi-ir/Cargo.toml` depends only on
  `serde`, `serde_json`, and `sha2`; `stilyagi-tree-sitter` depends on
  `stilyagi-ir`, not the reverse. Six anomaly codes are minted in
  `stilyagi-tree-sitter`; only the two suppression codes are minted locally, in
  `crates/stilyagi-ir/src/suppression.rs`. Round 1 proposed enumerating the
  anomaly codes in `stilyagi-ir` — a second copy of literals owned by a crate
  it cannot see, guarded by a test that cannot mechanically enumerate mint
  sites. Impact: this is why D5 was reversed. Enumerating the *two local* codes
  and defaulting everything else to warning puts the array within fifty lines
  of both its mint sites and makes the drift behaviour fail-safe.

- **S8 (round 2). The design document says Rust owns file discovery.**
  [Stilyagi design](../stilyagi-design.md) §1: "Rust owns file discovery,
  Markdown parsing, host-language comment and docstring extraction, source
  maps, and IR construction. Python owns configuration resolution, capability
  planning, spaCy-backed enrichment, rule execution, diagnostics, fixes, and
  plugin loading." Impact: decisive for D1. Today's Python walk is the
  deviation. Round 1 proposed putting the extension table in Rust while leaving
  the walk in Python — the one arrangement that is neither the current state
  nor the target state, and one where a bridge round-trip fetches four string
  pairs and buys no capability. When discovery does move, a Rust-side table
  would be consumed internally and the bridge function would be dead on arrival.

- **S9 (round 2). A run that checks zero files is byte-identical to a run that
  checks everything.** Probed:

  ```plaintext
  $ stilyagi check --verbose $T          # one .md file present
  0 diagnostics found                                        exit=0

  $ stilyagi check --verbose $T/link     # symlinked dir; ZERO files checked
  INFO:...skipping symlinked directory target: /tmp/.../link
  0 diagnostics found                                        exit=0
  ```

  Impact: this is the load-bearing operational defect. Demoting anomalies to
  warnings without a denominator converts a loud, wrong failure into a quiet,
  wrong success. The summary line in W6 is the cheapest, highest-value change
  in the plan.

- **S10 (round 2). The performance harness already exists and is
  Markdown-only.** `tests/performance/structural_probe.py`, delivered by
  roadmap item 1.3.3, has cold and warm vocabulary, nanosecond resolution, a
  versioned JSON report, and a redacted syrupy snapshot — hard-wired to
  `model.Syntax.MARKDOWN`. Round 1 proposed an unstructured `time` reading
  instead, which is a rigour regression. Also measured: file count grows 3.6×
  but total bytes only ~1.5×, because this repository's Markdown averages 25.4
  KiB per file against 4.2 KiB for Python and 4.8 KiB for Rust. A wall-clock
  tolerance of "10×" could therefore never trip, which makes it not a tolerance.

- **S11 (round 2). `tracing` and `metrics` are already wired, and this change
  inverts the coverage gap.** The two newly reachable extractors are the
  instrumented ones — `stilyagi_python_extraction_documents_total`,
  `stilyagi_rust_extraction_documents_total`, and `*_recovery_errors_total` in
  both `observe.rs` files. Markdown, in `crates/stilyagi-markdown`, has none.
  Nothing anywhere installs a `metrics` recorder, so every counter is
  write-only. Recorded in ADR 008 as a known gap; not fixed here.

- **S13 (round 2). This repository keeps uv's caches *inside* the working tree,
  and pruning them is load-bearing.** `Makefile` sets
  `UV_ENV = UV_CACHE_DIR=.uv-cache UV_TOOL_DIR=.uv-tools`, so running any
  `make` target materializes `.uv-cache` in the repository root — it currently
  holds **3,824** Python files of cached third-party wheels. `.venv` holds a
  further 827. Measured with round 1's proposed prune list, which named neither,
  `stilyagi check .` discovers **1,553** Python files instead of 76.

  The repository already has an authority on this: `MD_FILES_FIND` in the
  `Makefile` excludes `.venv`, `.venv-release-smoke`, `.uv-cache`, `.uv-tools`,
  `target`, and `crates/stilyagi-pyext/target`. Round 1's list matched only two
  of those six. Impact: W1's prune list is aligned to `MD_FILES_FIND` and
  cross-referenced to it in a comment. This also sharpens the review's point
  that name-based pruning is a stopgap — the first repository tested found
  three missing names, and the correct figures below were only reachable after
  fixing them.

- **S12 (round 2). Python doctests never run, and the discovery one is already
  false.** There is no `conftest.py`, and `[tool.pytest.ini_options]` sets no
  `--doctest-modules`, so `make test` never executes them. The example in
  `python/stilyagi/discovery.py` claims
  `discover_markdown_files([Path("docs")], ...)` yields `['docs/guide.md']`;
  `docs/guide.md` does not exist and `docs/` holds 55 Markdown files. Impact:
  "update the doctests" is an unfalsifiable instruction. W1 fixes the false
  example; ADR 008 records enabling `--doctest-modules` as follow-up.

## Decision log

- **D13 (implementation). The explicit implementation request satisfies the
  ExecPlan approval gate, and the rebased source-count baseline supersedes the
  planning snapshot.** W0 confirmed both code anchors, the `ty` typecheck
  recipe, the full lint recipe, `ExpectValid`, and developers' guide §6b. The
  four deterministic code gates passed before any production edit: `check-fmt`,
  `typecheck`, `lint`, and `test` (332 Rust tests and 213 Python tests). The
  plan's implementation-time acceptance evidence will record the observed W1
  count rather than preserving a stale planning-time count. Date/Author:
  2026-08-23, implementation agent.

- **D14 (implementation). Preserve explicit `UnicodeDecodeError` handling when
  broadening read failures to `OSError` and `MemoryError`.** The plan's D11
  wording described `OSError` as subsuming all four prior exceptions, but
  `UnicodeDecodeError` is a `UnicodeError`, not an `OSError`. Removing it would
  let invalid UTF-8 escape the documented exit-2 path. The implementation reads
  with `utf-8-sig`, catches `OSError`, `MemoryError`, and `UnicodeDecodeError`,
  and attributes the one logged message to the reported rather than resolved
  path. Date/Author: 2026-08-24, implementation agent.

- **D15 (implementation). Keep the 20% Markdown performance tolerance as a
  review criterion, but do not fabricate a numeric comparison.** Roadmap item
  1.3.3 deliberately stores only a redacted, schema-level snapshot; its raw
  machine-specific measurements are ignored and no checked-in timing baseline
  exists. W6 extends that established harness with per-syntax, per-file timing,
  throughput, file-count, and byte-count evidence. The live Markdown median is
  recorded below, but cannot truthfully be compared with an unavailable raw
  historical value. Date/Author: 2026-08-24, implementation agent.

- **D1 (reversed in round 2). The extension-to-syntax table lives in Python, in
  `python/stilyagi/discovery.py`. No bridge function is added for it.** Round 1
  put it in Rust behind the PyO3 bridge, reasoning that `ExtractSyntax` owns
  syntax spellings and that `supported_syntaxes()` is the established idiom for
  advertising them. The review falsified both halves. The existing idiom covers
  vocabularies that *appear in bridge payloads* — the `syntax` field, the region
  `kind` field, the argument to `extract_document`. File extensions appear in
  no payload and are passed to no bridge function, so the precedent does not
  reach them. And per S8 the design already assigns file discovery to Rust,
  which means the durable end state moves the walk *and* the table together;
  putting only the table across the bridge is the one arrangement that is
  neither the current state nor the target, and it makes the eventual move an
  unpicking of a seam rather than a relocation of one module. The "two
  coordinated edits" cost cited in round 1 also already exists: `model.Syntax`
  is a hand-maintained Python mirror of `ExtractSyntax` guarded by
  `_validate_syntax_vocab_once`, so a four-entry dict whose *values* are
  `model.Syntax` members is type-checked by `ty` and covered by the parity
  check that already runs. Constraint 3 is restated accordingly. Consequence:
  round 1's W1 and W3 are deleted entirely — the Rust table, the compile-time
  proof, the `proptest`, the bridge function, the `.pyi` change, the
  bridge-derived cache with its lock and reset hook, the second parity check,
  and the Rust BDD feature. Roughly a third of the proposed Rust surface.
  Date/Author: 2026-08-16, planning agent (round 2).

- **D2. Discovery scope stays a fixed built-in extension set. No `include` /
  `exclude` keys, and no new CLI flags.** RFC 0003 §6's baseline schema defines
  no such keys and §7 states discovery defaults as a fixed list. Roadmap item
  2.2.1 explicitly removed an invented `[discovery] include` key as
  out-of-contract; inventing configuration surface ahead of the contract is the
  mistake that decision corrected. The same reasoning bars `--fail-on`,
  `--max-warnings`, and `--max-file-size`, however useful — RFC 0003 §2 defines
  the flag set. All are recorded in ADR 008 as required follow-up rather than
  smuggled in here. Date/Author: 2026-08-16, planning agent.

- **D3. `.markdown` is retained; `.pyi` and `.mdx` are not added.**
  `.markdown` is discovered today and dropping it would be a silent regression.
  `.mdx` is explicitly preview-only per RFC 0003 §7. `.pyi` is not named by the
  RFC and stub files carry a different docstring culture, so admitting them is
  a product decision that has not been taken. Both appear in ADR 008's
  candidate table. Date/Author: 2026-08-16, planning agent.

- **D4 (upheld in round 2). Extraction anomalies are reported as warnings and do
  not by themselves produce exit `1`; authored-directive violations remain
  errors and do.** RFC 0003 §12 defines exit `1` as "when violations remain". A
  tree-sitter parse-recovery event is not a violation of any prose rule —
  `IrError`'s own doc comment calls these anomalies. Conversely
  `suppression-blanket-forbidden` and `suppression-unknown-verb` describe
  something a human wrote incorrectly. Without the split, S2 and S3 show
  `stilyagi check .` would fail on any repository containing a file the pinned
  grammar cannot parse. The review considered and rejected deferring this to
  roadmap item 3.2.3 on the ground that 3.2.3 `Requires 2.2.2` (safe-fix
  planning), which is unstarted — so "let 3.2.3 fix it" means shipping a tool
  that is broken on mixed trees for an indefinite period, and building user CI
  around a behaviour that would later have to be broken. It also rejected a
  cheaper variant that maps *every* IR error to warning, because that demotes
  genuine authored mistakes too. The review's substantive caveat is accepted
  and addressed: demotion without a coverage signal converts a loud wrong
  failure into a quiet wrong success, so D4 is only safe when shipped together
  with the run summary in W6. The two are deliberately in the same milestone.
  Date/Author: 2026-08-16, planning agent; upheld round 2.

- **D5 (reversed in round 2). One `const` array of the two authored-directive
  codes, declared beside its mint sites; everything else defaults to warning.**
  Round 1 declared two arrays in `crates/stilyagi-ir/src/diagnostics.rs` and
  proved them disjoint at compile time. S7 shows why that was wrong: six of the
  eight codes are minted in a downstream crate, so
  `EXTRACTION_ANOMALY_ERROR_CODES` would have been a second copy of literals
  `stilyagi-ir` cannot see, and the proposed "union equals the minted set" test
  would have been a third handwritten copy that no mechanism keeps honest. The
  disjointness proof verified by machine something checkable by eye across
  eight strings, while the drift that matters went unguarded. Worse, the
  polarity was backwards: under "anomaly ⇒ warning, else error", a new code
  minted in `stilyagi-tree-sitter` and not added to the array defaults to
  **error**, newly breaking `stilyagi check .` in the field — precisely the
  failure this plan exists to prevent. So: declare
  `AUTHORED_DIRECTIVE_ERROR_CODES` in `crates/stilyagi-ir/src/suppression.rs`,
  within fifty lines of both mint sites, and classify as "authored ⇒ error,
  else warning". This deletes the second array, the disjointness proof, the
  union test, and the shared `const fn` byte-comparison helper. An unclassified
  future code becomes a warning, which is what `IrError`'s doc comment already
  says it is. Constraint 9 records the polarity as an invariant. The array
  still crosses the bridge, so Constraint 3 applies and it is Rust-owned. The
  review's stronger alternative — replacing the `code: String` with a
  `#[serde(rename_all = "kebab-case")]` enum, which would preserve the wire
  format byte-for-byte while making exhaustiveness a compile error at every
  mint site — is genuinely better and is recorded in ADR 008 as the destination
  for roadmap item 3.2.3, which owns the IR envelope reshape. Date/Author:
  2026-08-16, planning agent (round 2).

- **D6 (upheld, and narrowed). Invariants are proven with tests, not with `kani`
  or `verus`.** Neither is wired into this repository — no Makefile target, no
  `.config/` entry, no CI step; they appear only as aspirations in `AGENTS.md`.
  Introducing a verification toolchain would breach the dependency tolerance
  and dwarf the change it verifies. Round 1 substituted compile-time `const`
  assertions, arguing that a `const fn` assertion over a fixed array is
  exhaustive over the entire real domain and so strictly stronger than a
  bounded model check. That argument is sound and is worth preserving as
  precedent — but per D1 and D5 both arrays it would have guarded are now gone,
  so nothing in this plan needs it. The remaining invariant that genuinely
  spans an unbounded domain is discovery's order-independence, and that is a
  `hypothesis` property. Date/Author: 2026-08-16, planning agent; narrowed
  round 2.

- **D7. `discover_markdown_files` is renamed to `discover_files`; the module
  keeps its path.** The name would otherwise lie. `stilyagi.discovery` is not
  part of the public import surface (Constraint 6), so no shim is owed. The
  module docstring currently describes itself as a public surface; W1 corrects
  that. Date/Author: 2026-08-16, planning agent.

- **D8 (new in round 2). Rust-side discovery is named as the architectural
  destination, and gitignore support is bound to it.** Per S8 the design
  already assigns file discovery to Rust. Roadmap item 2.2.1 deferred
  `.gitignore` because a correct matcher would be a new *Python* runtime
  dependency, and the project advertises none. That justification does not
  survive the move: a Cargo dependency such as the `ignore` crate compiles into
  the wheel and is invisible to users, and `ignore` provides gitignore matching
  as a side effect of the walk. So the remedy for the growing ignored-directory
  name list is not more names — it is the relocation. ADR 008 records this so
  the next maintainer inherits a dated stopgap rather than an open-ended one.
  Date/Author: 2026-08-16, planning agent (round 2).

- **D9 (new in round 2). The run summary is part of this slice, not an
  enhancement.** S9 shows a run that checked zero files is byte-identical to
  one that checked everything. That is tolerable while discovery is one
  extension and every target is a literal Markdown file; it is not tolerable
  once discovery walks mixed trees, prunes fifteen directory names, skips
  unregistered extensions, and demotes a class of failure to non-gating
  warnings. Every one of those is introduced by this plan, and each makes
  "nothing was reported" more ambiguous. The summary is therefore the
  observability this plan owes for the ambiguity it creates, and it is what
  makes D4 safe. Text renderers gain
  `checked N files (M skipped, K unreadable); E errors, W warnings`; the JSON
  renderer gains an additive sibling `summary` object so the exit code is
  derivable from the payload. Date/Author: 2026-08-16, planning agent (round 2).

- **D10 (new in round 2). Severity is used as the exit-code axis, knowingly and
  temporarily.** The review correctly observed that
  violation-versus-non-violation is the distinction actually needed, and that
  severity is an orthogonal, rule-owned presentation axis: RFC 0003 §3.2
  requires each rule to document a default severity and §3.3 requires filtering
  by it, while RFC 0002 §9 requires severity to support at least `error`,
  `warning`, `info`, and `hint` — of which `python/stilyagi/diagnostics.py`
  implements two. So a warning-severity *rule* in roadmap item 3.2.2 would
  print without gating. Introducing the correct discriminator means a new field
  on `Diagnostic`, which the tolerances forbid and which belongs with 3.2.3's
  envelope reshape. Today the conflict is not reachable: the rule registry
  matches nothing, so anomalies are the only warning producer in existence. The
  plan therefore takes the severity axis deliberately, names the failing
  severities in a single explicit constant so widening it is a one-line change,
  documents on `Diagnostic` that `WARNING` does not gate, requires a
  `compute_exit_code` doctest covering the warning case, and records in ADR 008
  that roadmap item 3.2.2 must resolve the axis before shipping its first
  warning-severity rule. Date/Author: 2026-08-16, planning agent (round 2).

- **D11 (new in round 2). File-read hardening is in scope; the run-wide exit-`2`
  redesign is not.** Adding `*.py` makes `UnicodeDecodeError` reachable in a
  way it was not for Markdown, because PEP 263 coding cookies make non-UTF-8
  Python legal. The narrow fixes — read with `utf-8-sig` so a byte-order mark
  does not become a parse-recovery warning, catch `OSError` (which subsumes the
  four currently caught) plus `MemoryError`, and report the user's path rather
  than the resolved path — are small, local, and directly caused by this
  change, so they are in. Converting per-file read failures into per-file
  diagnostics, so that one unreadable file stops discarding every other file's
  results and stops masquerading as an internal error, is the right fix but
  changes what exit `2` means. That is a contract change deserving its own
  item; ADR 008 records it as required follow-up. Date/Author: 2026-08-16,
  planning agent (round 2).

- **D12 (revised). Rust test helpers follow the house remediation order:
  propagate, then `#[track_caller]`, then one documented panic boundary.**
  `ddf791b` bumped PyO3 and `maturin` and, in the same commit, cleared every
  `no_expect_outside_tests` finding by rewriting the `stilyagi-ir` and
  `stilyagi-markdown` test helpers. Whitaker's rule is that clippy's
  `allow-expect-in-tests` covers a `#[test]` or `#[rstest]` *body* but not the
  helper functions beside it, which is where fixture and strategy constructors
  live.

  The first draft of this decision recorded that commit's shape — divergent
  `let`-`else` plus `panic!` — as the convention to follow. That was wrong. It
  satisfies the lint while reproducing the problem the lint exists to surface:
  an unnamed panic boundary at every call site, in a third spelling alongside
  the `must_ok!` and `must_some!` macros the repository already had. The house
  order is:

  1. **Propagate.** Make the helper return `Result`; the test body unwraps,
     because a failure there is the test verdict. Do not make the *test* return
     `Result` — `clippy::panic_in_result_fn` is denied workspace-wide, so
     `assert!` is unavailable in one.
  2. **`#[track_caller]`.** Where a helper legitimately asserts, mark it so a
     failure names the calling test. This is the property that otherwise forces
     shared assertion shapes to become macros.
  3. **One documented boundary.** For contexts that genuinely cannot propagate —
     a `proptest` strategy constructor returning `impl Strategy<Value = T>`, or
     a `prop_map` closure — use `ExpectValid` from `stilyagi-test-fixtures`:

     ```rust
     fn regex_strategy(pattern: &'static str) -> impl Strategy<Value = String> {
         string_regex(pattern).expect_valid(pattern)
     }
     ```

  W6 adds Rust unit tests under `crates/stilyagi-ir/src/tests/`, exactly the
  directory this governs, so any helper it introduces follows this order.

  **Dependency: satisfied.** `ExpectValid` and developers' guide §6b landed on
  `main` in #111, and a second pass over the same helpers landed in #96. Both
  are present on this branch's base, so W6 uses the boundary rather than
  inventing one. Verify at W0 that
  `crates/stilyagi-test-fixtures/src/expect_valid.rs` and developers' guide §6b
  still exist; if either is gone, stop and escalate rather than reintroducing a
  per-crate panic helper.

  Consequence: this also retires the "whitaker is red on `main`" baseline this
  plan previously carried. See `Validation and acceptance`. Date/Author:
  2026-08-16, planning agent (post-rebase; revised after applying the
  `addressing-whitaker-findings` guidance; dependency confirmed satisfied after
  rebasing onto `configure-df12-lints`).

## Outcomes & retrospective

Roadmap item 3.2.1 is delivered. `stilyagi check` now discovers `.md`,
`.markdown`, `.py`, and `.rs` files in deterministic resolved-path order and
selects the extractor carried by each discovered file. The BDD, subprocess,
property, unit, snapshot, corpus, and Rust bridge tests cover the acceptance
behaviours, including final-suffix matching, standard-input syntax selection,
warning-only extraction anomalies, authored-directive errors, and symlinked
directory summaries.

Post-completion review remediation corrected the stale `.md.fixture` guidance
and added the explicit symlinked-directory *target* acceptance test. The test
asserts exit `0`, a warning log entry, and the load-bearing zero-checked,
one-skipped summary, rather than relying on recursive-walk symlink coverage.

The clean acceptance run checked 178 files and exited `0`; the whole-tree run
checked 237 files and exited `1` only because its two deliberately invalid
suppression directives were errors. Its two malformed-Rust recovery notices
were warnings, so the classification boundary is observable rather than merely
documented. The run summary reports checked, skipped, unreadable, error, and
warning counts in both text and JSON output.

The five-iteration structural probe measured warm medians of 200,253 ns/file
for Markdown (1.30 MiB/s), 188,323 ns/file for Python (2.66 MiB/s), and 171,113
ns/file for Rust (3.23 MiB/s). The clean acceptance resolver reported
`{'discovery_misses': 4}`. There is no checked-in raw performance value for the
earlier Markdown probe, so the 20% tolerance remains a review criterion rather
than a fabricated numeric comparison.

The milestone-2 boundary against roadmap item 3.2.3 held: no IR schema field,
public extraction signature, fix workflow, or violation discriminator was
added. The temporary severity-based exit policy and every other deferred
candidate have one home in ADR 008. No runtime dependency was added.

## Context and orientation

Assume no prior knowledge of this repository.

Stilyagi is a prose linter for documentation and for documentation comments
inside source code. It is a mixed Rust and Python project. The Rust crates under
`crates/` parse source files and produce a canonical intermediate
representation (IR); the Python package under `python/stilyagi/` owns the CLI,
configuration, rule execution, and diagnostic rendering. The two halves meet at
a narrow PyO3 bridge module named `_stilyagi_rs`.

Terms used throughout:

- **IR.** The canonical JSON envelope the Rust extractor produces for one file.
  It carries prose `regions`, `suppressions`, and non-fatal `errors`.
- **Region.** One span of prose the linter may analyse — a Markdown paragraph, a
  Python docstring, a Rust documentation comment.
- **Syntax.** Which extractor to run. Spelled `markdown`, `python_docstring`, or
  `rust_doc_comment`. Note this differs from the IR's `metadata.syntax` field,
  which uses bare language names (`markdown`, `python`, `rust`). This plan
  touches only the former; ADR 008 records the two-vocabulary hazard for
  roadmap items 3.2.3 and 3.3.1, which will both key off it.
- **Discovery.** Walking command-line targets to produce the ordered list of
  files to check.
- **Extraction anomaly.** A non-fatal notice that the extractor degraded — a
  parse recovery, a traversal depth limit, a doc comment absorbed into an error
  subtree.
- **Authored-directive violation.** A notice that a human wrote a Stilyagi
  suppression comment incorrectly.

### The files this plan touches

Cited by symbol and section heading rather than by line number, because W1
invalidates line numbers in the files it edits.

Rust:

- `crates/stilyagi-ir/src/suppression.rs` — mints both authored-directive codes.
  W4 declares the array here.
- `crates/stilyagi-ir/src/lib.rs` — re-exports the `stilyagi-ir` surface.
- `crates/stilyagi-pyext/src/lib.rs` — the PyO3 module. `supported_syntaxes` and
  `supported_region_kinds` are the functions W4 mirrors.

Python:

- `python/stilyagi/discovery.py` — Markdown-scoped throughout: module docstring,
  `_MARKDOWN_SUFFIXES`, `_IGNORED_DIRECTORY_NAMES`, `DiscoveredFile`,
  `discover_markdown_files`, `_is_markdown_file`. W1 rewrites it.
- `python/stilyagi/cli.py` — `CheckInput`, `_discover_targets`,
  `_stdin_check_input`, `_read_source`, `_check_one_file` (with the hard-coded
  `model.Syntax.MARKDOWN`), `_report_file_error`, `compute_exit_code`, and
  `run_check`. W2, W5, and W6 edit these.
- `python/stilyagi/engine/checker.py` — `map_ir_errors` and `_map_one_error`,
  which hard-code error severity. W5 edits these.
- `python/stilyagi/engine/renderers.py` — `RendererRegistry`, `_render_text`,
  `_render_json`. W6 adds the summary.
- `python/stilyagi/diagnostics.py` — `Severity` and `Diagnostic`. W5 and W6 add
  the failing-severity constant and the docstring note.
- `python/stilyagi/engine/extraction.py` — owns the bridge, the vocabulary
  parity check `_validate_syntax_vocab_once`, and the test reset hook
  `_reset_extraction_state_for_tests`. W4 extends it for the new bridge
  vocabulary; discovery does **not** reach the bridge (D1).
- `python/stilyagi/cli_args.py` and `python/stilyagi/engine/api.py` — stale
  "Markdown" strings in help text and a docstring.
- `python/stilyagi/_stilyagi_rs.pyi` — the typing stub, for W4's function only.

Tests, fixtures, and harnesses:

- `tests/test_discovery.py`, `tests/test_discovery_properties.py` — the direct
  precedents to extend.
- `tests/steps/check_command.py` and `features/stilyagi_check_command.feature` —
  the pytest-bdd steps and Gherkin feature for `check`. Steps are registered as
  a plugin from `tests/test_package_skeleton_units.py`.
- `tests/test_check_command.py`, `tests/test_check_files.py`,
  `tests/test_renderers.py`, `tests/test_cli_e2e.py`.
- `tests/performance/structural_probe.py` — the roadmap 1.3.3 harness, currently
  Markdown-only. W6 extends it.
- `tests/fixtures/corpus/{markdown,python,rust}/{valid,malformed}/` — the shared
  corpus. Note the malformed Python fixture is `unclosed-function.py.txt`, and
  the Markdown corpus uses a `.md.fixture` suffix; both are existing
  conventions for "corpus content that must not be treated as live source".

### Signposted documentation and skills

Read these before starting the work item that cites them.

| Work item | Read first                                                                                                                                                                                                                                                                                                                                            |
| --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| All       | [AGENTS.md](../../AGENTS.md); [developers' guide](../developers-guide.md) §2b (the `check` pipeline) and §6 (lint, typecheck, test workflow)                                                                                                                                                                                                          |
| W1, W2    | `python-router` skill, then `python-types-and-apis`; `hexagonal-architecture` skill for the boundary argument in D1; [complexity antipatterns and refactoring strategies](../complexity-antipatterns-and-refactoring-strategies.md)                                                                                                                   |
| W3, W6    | [rust testing with rstest fixtures](../rust-testing-with-rstest-fixtures.md); [rstest-bdd users' guide](../rstest-bdd-users-guide.md); [reliable testing in Rust via dependency injection](../reliable-testing-in-rust-via-dependency-injection.md); [rust doctest DRY guide](../rust-doctest-dry-guide.md); `python-testing` and `hypothesis` skills |
| W4        | `rust-router` skill, then `rust-types-and-apis`; [developers' guide](../developers-guide.md) §4 "Rust and PyO3 integration"                                                                                                                                                                                                                           |
| W5        | `python-errors-and-logging` skill; RFC 0003 §12; RFC 0002 §9                                                                                                                                                                                                                                                                                          |
| W7        | [documentation style guide](../documentation-style-guide.md), especially the ADR template; `arch-decision-records` skill; `en-gb-oxendict` skill                                                                                                                                                                                                      |

*Table 1: which documents and skills to read before each work item.*

## Plan of work

### Stage A — orient and baseline (no production code changes)

**W0.** Verify the two anchors: `python/stilyagi/discovery.py` still defines
`_MARKDOWN_SUFFIXES = frozenset({".md", ".markdown"})`, and `_check_one_file` in
`python/stilyagi/cli.py` still calls
`engine.extract_document(source, model.Syntax.MARKDOWN)`. If either has moved,
stop and escalate — the plan was written against a different tree. Then run the
four gates, record the baseline, and re-run the S3 dry run to confirm the
233-file figure. Confirm `.uv-cache` exists and is pruned (S13); if no `make`
target has yet run in this worktree it will be absent, and the figure will look
correct for the wrong reason.

Then re-read the gate recipes rather than trusting this document about them.
`make typecheck` and the Python tiers inside `make lint` have both moved during
this plan's life. Read the `typecheck:` and `lint:` recipes in the `Makefile`,
and confirm `crates/stilyagi-test-fixtures/src/expect_valid.rs` and developers'
guide §6b still exist (D12). If a gate has changed tool, update the quality
criteria in this plan as part of W0 rather than discovering it at the first
commit.

Go/no-go: gates recorded, both anchors confirmed, gate recipes re-read.

______________________________________________________________________

### Milestone 1 — discovery and dispatch

#### Stage B1 — red tests

**W3-red (units).** In `tests/test_discovery.py`, add cases asserting that a
tree containing `a.md`, `b.py`, `c.rs`, `d.txt`, and `e.py.txt` discovers
exactly `a.md`, `b.py`, and `c.rs`, each carrying the right `syntax`; that an
explicit `d.txt` target is skipped with an informative log record; and that
each newly pruned directory name is pruned. Expect
`AttributeError: module 'stilyagi.discovery' has no attribute 'discover_files'`.

**W3-red (property).** In `tests/test_discovery_properties.py`, extend the
`hypothesis` strategy to generate mixed trees of `.md`, `.py`, `.rs`, and
unregistered extensions, asserting three invariants: the discovered set equals
the generated files whose *final* suffix is registered; ordering is total by
resolved path and **independent of the order targets are supplied**; and each
discovered file's `syntax` equals the table's mapping for its suffix. The
order-independence invariant is the highest-value test in this plan — it spans
an unbounded domain and would catch a real regression.

**W3-red (BDD).** Extend `features/stilyagi_check_command.feature` with the
scenarios below and add matching steps to `tests/steps/check_command.py`. Keep
this specification synchronized with the implementation.

```gherkin
  Scenario: check discovers Markdown, Python, and Rust in one pass
    Given a temporary tree with files "docs/guide.md", "src/app.py", and "src/lib.rs"
    When I run "stilyagi check ." in that tree
    Then the exit code is 0
    And the processed paths are "docs/guide.md", "src/app.py", and "src/lib.rs"
    And each processed path was extracted with its extension's syntax

  Scenario: check ignores files with no registered extractor
    Given a temporary tree with files "notes.txt", "data.json", and "README.md"
    When I run "stilyagi check ." in that tree
    Then the exit code is 0
    And the processed paths are "README.md"

  Scenario: check attributes stdin to the syntax implied by the stdin filename
    Given a temporary tree with two well-formed Markdown files
    When I run "stilyagi check - --stdin-filename src/lib.rs" in that tree
    Then the exit code is 0
    And the standard input was extracted as Rust documentation comments

  Scenario: check skips stdin when the stdin filename has no registered extractor
    Given a temporary tree with two well-formed Markdown files
    When I run "stilyagi check - --stdin-filename main.go" in that tree
    Then the exit code is 0
    And no input was extracted
```

**W3-red (end-to-end).** Extend `tests/test_cli_e2e.py` with a real subprocess
run over a mixed tree.

Go/no-go: every new test fails, each for the reason it was written for.

#### Stage C1 — implementation

**W1. Generalized discovery.** Rewrite `python/stilyagi/discovery.py`:

- Rename `discover_markdown_files` to `discover_files`; update `__all__`, the
  module docstring, and the worked example. Correct the false example recorded
  in S12 — and, since doctests do not execute, keep it minimal and verifiable
  by eye rather than elaborate.
- Stop the module docstring describing itself as a public surface (D7).
- Add `syntax: model.Syntax` to `DiscoveredFile`, required and without a
  default. A default would silently mis-attribute every Python and Rust file at
  any construction site that forgot it.
- Replace `_MARKDOWN_SUFFIXES` with the table (D1). Extensions are stored
  without a leading dot, lowercase:

  ```python
  _EXTENSION_SYNTAXES: typ.Final[cabc.Mapping[str, model.Syntax]] = {
      "md": model.Syntax.MARKDOWN,
      "markdown": model.Syntax.MARKDOWN,
      "py": model.Syntax.PYTHON_DOCSTRING,
      "rs": model.Syntax.RUST_DOC_COMMENT,
  }
  ```

- Replace `_is_markdown_file` with a module-level
  `syntax_for_path(path: pathlib.Path) -> model.Syntax | None`, matching on
  `path.suffix.lower().removeprefix(".")` — the *final* suffix only, so
  `e.py.txt` resolves to `.txt` and is skipped, and `Makefile` and `.gitignore`
  resolve to `""` and are unmatched. This function is public within the package
  because W2's stdin path needs the same decision; leaving it private would
  force either a cross-module private import or a hand-copied second table.
- Extend `_IGNORED_DIRECTORY_NAMES`. Keep the existing six and add, in two
  groups. First, the three this repository's own Makefile already excludes and
  which S13 shows are load-bearing: `.uv-cache`, `.uv-tools`, and
  `.venv-release-smoke`. Second, the general Python and tooling caches, for
  which Ruff's default exclusion list is the prior art:[^1] `__pycache__`,
  `.mypy_cache`, `.ruff_cache`, `.pytest_cache`, `.tox`, `.nox`, `.eggs`,
  `site-packages`, and `.stilyagi_cache`.

  Add a comment pointing at `MD_FILES_FIND` in the `Makefile`, naming it as the
  repository's existing authority on what to skip, so the two lists are
  maintained together rather than drifting.
- Raise the symlinked-directory-target log from INFO to WARNING, and return the
  count so W6 can report it as skipped.

**W2. Per-file extractor selection.** In `python/stilyagi/cli.py`:

- Add `syntax: model.Syntax` to `CheckInput`, and give it a
  `from_discovered(cls, file, *, source_text=None)` constructor beside the
  dataclass. `_discover_targets` currently copies `DiscoveredFile` fields one
  by one, and nothing signals when the two shapes diverge; the constructor
  closes that seam before the next language addition trips over it.
- Replace the hard-coded `model.Syntax.MARKDOWN` in `_check_one_file` with
  `check_input.syntax`.
- In `_stdin_check_input`, resolve the syntax from `--stdin-filename` via
  `discovery.syntax_for_path`. When no filename is supplied, default to
  Markdown, as documented today. When a filename *is* supplied but its suffix
  is unregistered, **skip** with a warning rather than silently guessing
  Markdown — otherwise `stilyagi check - --stdin-filename main.go` prose-lints
  an entire Go file as Markdown, which becomes a flood of nonsense once roadmap
  item 3.2.2 ships real rules. Skipping matches what happens for the same file
  on disk.
- Update the stale strings: the `check` sub-parser help and the `targets` help
  in `python/stilyagi/cli_args.py`, and the "first implemented extractor
  supports `model.Syntax.MARKDOWN`" docstring in
  `python/stilyagi/engine/api.py`.

Go/no-go: milestone-1 tests pass; four gates green; commit.

______________________________________________________________________

### Milestone 2 — classification, severity, and observability

#### Stage B2 — red tests

**W6-red.** In `crates/stilyagi-ir/src/tests/`, assert
`is_authored_directive_code` returns `true` for the two suppression codes and
`false` for each of the six anomaly codes and for an unknown code — the last
case pinning Constraint 9's fail-safe polarity. Follow D12's remediation order
for any helper beside these tests: propagate a `Result` first, reach for
`#[track_caller]` when the helper asserts, and funnel a genuinely
non-propagating context through `ExpectValid`. In
`crates/stilyagi-pyext/src/tests/`, assert the new module function is
registered and returns the expected shape. In `tests/test_check_files.py`,
assert a tree containing one malformed `.rs` file exits `0` with a
warning-severity diagnostic, and a tree containing a bare `# stilyagi: disable`
exits `1` with an error-severity diagnostic. In `tests/test_renderers.py`,
assert the summary line and the JSON `summary` object. Add the BDD scenarios
below.

```gherkin
  Scenario: check reports a Rust parse recovery as a warning and still succeeds
    Given a temporary tree containing malformed Rust
    When I run "stilyagi check ." in that tree
    Then the exit code is 0
    And the text output reports a warning-severity diagnostic
    And the summary reports 1 file checked and 0 errors

  Scenario: check reports a forbidden blanket suppression as an error
    Given a temporary tree containing a Python file with a blanket suppression
    When I run "stilyagi check ." in that tree
    Then the exit code is 1
    And the text output reports an error-severity diagnostic

  Scenario: check reports how many files it checked
    Given a temporary tree with files "docs/guide.md", "src/app.py", and "notes.txt"
    When I run "stilyagi check ." in that tree
    Then the exit code is 0
    And the summary reports 2 files checked
```

#### Stage C2 — implementation

**W4. Authored-directive codes.** In `crates/stilyagi-ir/src/suppression.rs`,
beside the two `IrError` mint sites:

```rust
/// Codes describing a Stilyagi directive a human wrote incorrectly.
///
/// Every other IR error code describes a degraded extraction rather than an
/// authored mistake, so classification defaults to "not authored". A new
/// extractor anomaly code therefore becomes a warning without any coordinating
/// edit, which is the fail-safe direction: an unrecognized extractor notice
/// must never be able to break a user's build.
pub const AUTHORED_DIRECTIVE_ERROR_CODES: &[&str] = &[
    "suppression-blanket-forbidden",
    "suppression-unknown-verb",
];

#[must_use]
pub fn is_authored_directive_code(code: &str) -> bool { ... }
```

Use `&'static [_]` rather than a fixed-size array, matching the house idiom in
`crates/stilyagi-ir/src/region.rs` (`RegionKind::ALL`) and avoiding a length
that appears in the type. Re-export from `crates/stilyagi-ir/src/lib.rs`.

In `crates/stilyagi-pyext/src/lib.rs`, mirror `supported_syntaxes` exactly: add
`authored_directive_error_codes() -> tuple[str, ...]`, register it in the
module list, and declare it in `python/stilyagi/_stilyagi_rs.pyi`. These codes
appear in bridge payloads, so Constraint 3 applies and Rust owns them.

Mirror the *current* `supported_syntaxes` rather than any remembered form: this
branch is rebased onto `ddf791b`, which moved PyO3 from 0.28.3 to 0.29.2. The
bump changed `BoundRef` to `&pyo3::Bound` in `#[pymodule]` signature
rejections, and the `trybuild` compile-fail expectations in
`crates/stilyagi-pyext/tests/ui/fail/*.stderr` are pinned to the 0.29 wording.
If W4's addition perturbs those golden files, that is a signal the new function
does not match the established shape — fix the function, not the snapshot.

**W5. Classification, exit code, and read hardening.** In
`python/stilyagi/engine/checker.py`, have `_map_one_error` select
`Severity.ERROR` when the code is in the bridge-supplied authored set and
`Severity.WARNING` otherwise. Load the set through the layer that already owns
the bridge — `python/stilyagi/engine/extraction.py`, which holds the cache, the
lock, the parity check, and `_reset_extraction_state_for_tests` — rather than
adding a second cached bridge vocabulary with its own reset path.

In `python/stilyagi/diagnostics.py`, add
`_FAILING_SEVERITIES: frozenset[Severity] = frozenset({Severity.ERROR})` and
document on `Diagnostic.severity` that `WARNING` does not affect the exit code
(D10). In `python/stilyagi/cli.py`, have `compute_exit_code` return `1` only
when a diagnostic's severity is in that set, leaving the `had_error` exit-`2`
path unchanged. Add a doctest covering the warning case — the existing doctests
exercise only the error default, so without one the new branch is unverified.

Harden `_read_source` (D11): read with `utf-8-sig` so a byte-order mark does
not become a spurious parse-recovery warning on Windows-authored files; catch
`OSError` (which subsumes the four currently caught, and adds `ELOOP`, `EIO`,
`ESTALE`, and `ENAMETOOLONG`) plus `MemoryError`; and pass
`check_input.reported_path` to `_report_file_error` so the message names the
path the user has in their repository. Remove the duplicate emission — the same
message currently reaches the terminal twice, once through the logger's last
-resort handler and once through the explicit `print`.

**W6. Run summary and the rest of the tests.** In
`python/stilyagi/engine/renderers.py`, add a summary to both renderers (D9).
Text gains `checked N files (M skipped, K unreadable); E errors, W warnings`;
JSON gains an additive sibling `summary` object carrying the same counts, so
that the exit code is derivable from the payload rather than only from the
process. This is purely additive to the JSON contract, which matters because
`exit_code != 0` is currently equivalent to a non-empty `diagnostics` array and
after W5 it is not.

`run_check` must thread the counts through: files discovered, files skipped for
an unregistered extension or a symlinked directory target, and files that
failed to read.

Then complete the test matrix:

- **Snapshot.** A `syrupy` snapshot of the text and JSON renderings of a fixed
  mixed-source run, using `JSONSnapshotExtension` in the style of
  `tests/test_renderers.py`. Normalize paths to the tree root first so the
  snapshot is not machine-specific, and pair it with direct semantic assertions
  rather than relying on the snapshot alone. Do **not** add an `insta`
  snapshot: W4 adds no rendered form on the Rust side, and a snapshot for its
  own sake is churn.
- **Region-count regression.** Assert region counts over the fixed corpus, so a
  grammar bump that silently reduces extraction coverage fails Stilyagi's own
  suite rather than shipping. This is the only mechanical guard against the
  first risk.
- **Performance.** Extend `tests/performance/structural_probe.py` to be
  per-syntax rather than hard-wired to `model.Syntax.MARKDOWN` (S10). Record
  the warm median per-file extraction time and throughput in MiB/s for each of
  the three syntaxes, and record total bytes alongside file counts so the 3.6×
  file growth is not confused with the ~1.5× byte growth. Markdown's figure is
  gated against the checked-in roadmap 1.3.3 baseline per the tolerance; the
  Python and Rust figures are new baselines, recorded not gated. If a whole-run
  wall-clock figure is also wanted, take it with
  `hyperfine --warmup 1 --runs 10` — a single `time` reading on a shared
  six-core machine is noise.
- **Config cache evidence.** Log `ConfigResolver.cache_stats` at the end of the
  acceptance run. It already exposes discovery and resolved-table hit and miss
  counts, so this answers "does expanding discovery expose a config problem?"
  with data instead of argument, at zero new code. Note the resolver already
  caches by resolved directory, so there is no quadratic cliff — but it does
  re-run schema validation per call, which 3.6× more files makes 3.6× more
  expensive. Record the numbers for roadmap item 3.3.1; do not optimize here.

Go/no-go: milestone-2 tests pass; all six gates green; commit.

______________________________________________________________________

### Stage D — documentation and closing

**W7.** In this order:

1. **ADR 008** at `docs/adr-008-v1-discovery-defaults.md`, following the
   sectioned template in the
   [documentation style guide](../documentation-style-guide.md) — the structure
   every existing ADR uses, not a one-line Y-Statement. It records D1 through
   D11, the post-v1.0 candidate table, and the follow-up register below. ADR
   008 is the **single home** for the post-v1.0 table: it is dated and
   permitted to be a research snapshot, whereas a design document is a source
   of truth that must not silently rot.

   The follow-up register ADR 008 must carry, each of which this plan
   deliberately declined:

   - `--fail-on` / `--max-warnings`, so a team can gate on extraction
     degradation (needs an RFC 0003 §2 amendment).
   - Per-file read failures as per-file diagnostics, so one unreadable file
     stops discarding a whole run's results (changes what exit `2` means).
   - A violation-versus-non-violation discriminator, required before roadmap
     item 3.2.2 ships a warning-severity rule (D10).
   - Replacing `IrError.code: String` with a `#[serde(rename_all =
     "kebab-case")]` enum, preserving the wire format while making
     classification exhaustive at every mint site — for roadmap item 3.2.3 (D5).
   - Moving discovery to Rust per design §1, delivering `respect-gitignore` via
     the `ignore` crate rather than a growing name list (D8).
   - Installing a `metrics` recorder, since the per-language counters in
     `crates/stilyagi-tree-sitter/src/*/observe.rs` are currently write-only, and
     Markdown has no counters at all (S11).
   - Enabling `--doctest-modules`, since Python doctests never execute today and
     at least one is already false (S12).
   - Renaming the adversarial Python and Rust corpus fixtures to fall outside
     discovery, so this repository can dogfood `stilyagi check .` in CI.
   - `--max-file-size`, parallelism, and incremental output, all of which the
     single-threaded end-of-run render makes acute at monorepo scale.

2. **`docs/stilyagi-design.md` §7.3.** Rewrite the "Weaknesses and ambiguities"
   bullet so it records that the RFC *did* over-claim file types and was
   trimmed by `787526e`, rather than asserting in the present tense that it
   still does (S4). Then add one sentence pointing at ADR 008 for post-v1.0
   targets. Do not duplicate the table here.

3. **`docs/users-guide.md` §3.** Replace the forward-looking sentence and the
   "currently analyses Markdown files only" claim with delivered behaviour: the
   discovered extension set, the pruned directory names, that unregistered
   extensions are skipped, the warning-versus-error distinction and its effect
   on exit codes, the new summary line, and the absence of `include` /
   `exclude` configuration in v1. Update the `#### Exit codes` subsection.

4. **`docs/developers-guide.md`.** Update §2b "Discovery" for the rename and the
   new syntax field, §3's syntax-scope bullets, and the `### Exit codes`
   subsection, which W5 falsifies. Add `### 4.3 Adding a language extractor`
   beside the existing per-language comparison table in §4.

   Write §4.3 from the **real** list, not a plausible short one. Adding a
   language today requires coordinated edits at: the `ExtractSyntax` variant;
   `ExtractSyntax::ALL`; the `as_str` match arm; the `TryFrom<&str>` match arm;
   the dispatch arm in `extract_document_with_source_identity`; the
   `_EXTENSION_SYNTAXES` entry; a tree-sitter grammar dependency plus a module
   tree under `crates/stilyagi-tree-sitter/src/`; the per-language `metrics`
   counter names in `<lang>/observe.rs`; any new IR error codes and their
   classification; the `model.Syntax` member; corpus fixtures under
   `tests/fixtures/corpus/<lang>/{valid,malformed}/`; the structural
   performance probe; the per-language comparison table in §4; the users' guide
   extension list; RFC 0003 §7; and ADR 008's candidate table. That is sixteen
   places. Documenting four would actively mislead the first person who trusted
   it — and naming all sixteen is the honest way to make the shotgun-surgery
   smell visible enough that someone eventually fixes it.

5. **`docs/contents.md`.** Add the ADR 008 entry under
   `## Architecture decision records (ADRs)`, matching the existing pattern.

**W8.** Tick roadmap item 3.2.1, adding a completion note linking this ExecPlan
and ADR 008 in the style of the 3.1.1 and 3.1.2 entries. Complete
`Outcomes & retrospective`.

Go/no-go: all six gates green.

## Concrete steps

Run everything from the repository root. Per AGENTS.md, tee long output to a
log and review the log rather than the truncated terminal, and never run gates
in parallel.

Baseline (W0):

```bash
git branch --show-current   # expect 3-2-1-expand-discovery-defaults-to-md-py-and-rs
make check-fmt 2>&1 | tee "/tmp/check-fmt-$(get-project)-$(git branch --show-current).out"
make typecheck 2>&1 | tee "/tmp/typecheck-$(get-project)-$(git branch --show-current).out"
make lint      2>&1 | tee "/tmp/lint-$(get-project)-$(git branch --show-current).out"
make test      2>&1 | tee "/tmp/test-$(get-project)-$(git branch --show-current).out"
```

Focused red-stage runs. Expect failures, and read the reason:

```bash
uv run python -m pytest tests/test_discovery.py tests/test_discovery_properties.py -v
uv run python -m pytest tests/test_check_files.py tests/test_renderers.py -v
uv run python -m pytest tests/test_package_skeleton_units.py -v
cargo test -p stilyagi-ir is_authored_directive_code
```

Milestone 1 needs no `make build`, because it touches no Rust — one of the
practical gains from D1. Milestone 2 does:

```bash
make build
make check-fmt && make typecheck && make lint && make test
```

Per AGENTS.md, do not create an isolated Cargo cache; if another job holds the
package-cache lock, wait. If a build fails with `EAGAIN`, fork, or
internal-compiler-error noise, retry with `RUSTC_WRAPPER= CARGO_BUILD_JOBS=2`.

Documentation gates (W7, W8):

```bash
make fmt
make markdownlint 2>&1 | tee "/tmp/markdownlint-$(get-project)-$(git branch --show-current).out"
make nixie        2>&1 | tee "/tmp/nixie-$(get-project)-$(git branch --show-current).out"
```

The acceptance demonstration. Lead with the clean run:

```bash
uv run stilyagi check python/ crates/ docs/ ; echo "exit=$?"
```

Observed on 2026-08-24: 178 files checked, 44 skipped, zero unreadable files,
zero errors, zero warnings, and `exit=0`. This is the roadmap item's success
criterion — mixed documentation and source trees work.

Then the corroborating run, which additionally reaches the adversarial corpus:

```bash
uv run stilyagi check . ; echo "exit=$?"
```

Observed on 2026-08-24: 237 files checked, 189 skipped, zero unreadable files,
two error-severity `suppression-blanket-forbidden` diagnostics from the two
corpus fixtures that deliberately carry bare `# stilyagi: disable`, and two
warning-severity extraction anomalies from
`tests/fixtures/corpus/rust/malformed/unclosed-item.rs`; `exit=1` is driven by
the two errors rather than the two warnings. That exit `1` is correct
behaviour, not a defect — the fixtures really do contain forbidden directives.

After each milestone, and only once all gates are green:

```bash
coderabbit review --agent
```

Clear every concern before starting the next milestone. CodeRabbit must not be
used to catch what the deterministic gates already catch.

## Validation and acceptance

Acceptance is behavioural. Each item names an observation, not a code change.

1. **Mixed discovery.** In a tree containing `docs/guide.md`, `src/app.py`, and
   `src/lib.rs`, `stilyagi check .` processes all three in resolved-path order
   and exits `0`. Before the change it processes only `docs/guide.md`.
2. **Per-file extractor selection.** The same run extracts `src/app.py` with
   `python_docstring` and `src/lib.rs` with `rust_doc_comment`, asserted
   against the recorded syntax rather than inferred.
3. **Unregistered extensions are skipped, not errors.** A tree containing
   `notes.txt` and `data.json` alongside `README.md` processes only `README.md`
   and exits `0`, and the summary reports one file checked.
4. **Final-suffix matching.** `unclosed-function.py.txt` is not discovered.
5. **Extraction anomalies do not fail the run.** A tree containing only
   malformed Rust exits `0` and reports a warning-severity diagnostic.
6. **Authored-directive violations do fail the run.** A tree containing a bare
   `# stilyagi: disable` exits `1` with an error-severity diagnostic.
7. **Unclassified codes fail safe.** `is_authored_directive_code` returns
   `false` for an unknown code, so it maps to a warning (Constraint 9).
8. **Standard input follows `--stdin-filename`.**
   `stilyagi check - --stdin-filename src/lib.rs` extracts as
   `rust_doc_comment`; `--stdin-filename main.go` skips rather than guessing.
9. **The summary is truthful and load-bearing.** A run over an empty directory,
   and a run whose only target is a symlinked directory, both report
   `checked 0 files` — visibly different from a healthy run (S9).
10. **Determinism.** The `hypothesis` property passes: discovery output is the
    same total order regardless of target order, and each resolved path appears
    exactly once.
11. **Whole-repository acceptance.** Both commands in `Concrete steps` produce
    the stated counts and exit codes.
12. **Markdown does not regress.** The structural probe's Markdown warm median
    is within 20% of the roadmap 1.3.3 baseline.

Record red-green-refactor evidence per work item in `Artefacts and notes`: the
red command and its failure output, the green command and its pass output, and
the gate sequence after the refactor step.

Quality criteria — what "done" means:

- **Tests:** `make test` passes — Rust workspace suite, Rust doctests, `pytest`.
- **Formatting:** `make check-fmt` passes.
- **Typecheck:** `make typecheck` passes, including the pinned `ty check` pass.
- **Lint:** `make lint` passes — `ruff`, `interrogate` at 100% docstring
  coverage, `pylint`, the df12 `pylint` plugin pass, `ambrleaks` over `tests`,
  `cargo doc`, `clippy` with `-D warnings`, and `whitaker`.
- **Markdown:** `make markdownlint` (including the `typos` gate) and
  `make nixie` pass.
- **Review:** `coderabbit review --agent` reports no outstanding concerns at
  each milestone.

All six gates are green on this branch as of the rebase onto `ddf791b`,
including `whitaker`. That is a change from earlier in this branch's life: the
`no_expect_outside_tests` findings on pre-existing `.expect()` calls in Rust
test helpers were cleared by `ddf791b` itself, so there is no longer a red
baseline to work around. Any `whitaker` finding this branch produces is a
regression it owns. See D12 for the convention that keeps it green.

## Idempotence and recovery

Every step is re-runnable. `make build`, the gates, and the acceptance commands
are read-only with respect to source.

- The two milestones commit independently, so `git revert` of milestone 2
  restores the previous exit-code and rendering semantics while leaving
  expanded discovery in place. Reverting milestone 1 restores Markdown-only
  checking.
- Review any `syrupy` snapshot diff before accepting it. A snapshot that churns
  on a harmless change is too broad — narrow the captured output rather than
  re-accepting.
- If milestone 2's bridge rebuild is skipped, Python raises `AttributeError` on
  `authored_directive_error_codes`. Run `make build` and retry.
- Nothing here is destructive. No file is deleted and no fixture is rewritten;
  `tests/fixtures/corpus/` is read-only to this work.

## Artefacts and notes

To be filled in as work proceeds. Record at minimum: the W0 baseline gate
transcript; red and green transcripts per work item; the per-syntax figures,
byte totals, and `cache_stats` from W6; and the final acceptance transcripts.

W0 evidence, 2026-08-23:

```plaintext
make check-fmt  PASS  /tmp/check-fmt-7dac0d2e-fd47-4ed3-ae7c-3814893c769e-3-2-1-expand-discovery-defaults-to-md-py-and-rs.out
make typecheck  PASS  /tmp/typecheck-7dac0d2e-fd47-4ed3-ae7c-3814893c769e-3-2-1-expand-discovery-defaults-to-md-py-and-rs.out
make lint       PASS  /tmp/lint-7dac0d2e-fd47-4ed3-ae7c-3814893c769e-3-2-1-expand-discovery-defaults-to-md-py-and-rs.out
make test       PASS  /tmp/test-7dac0d2e-fd47-4ed3-ae7c-3814893c769e-3-2-1-expand-discovery-defaults-to-md-py-and-rs.out
```

The test gate reported 332 Rust tests and 213 Python tests. `make` created
`.uv-cache`; its presence was confirmed before recording S14.

Milestone-1 W3 evidence, 2026-08-24:

```plaintext
RED   uv run python -m pytest tests/test_discovery.py \
      tests/test_discovery_properties.py tests/test_cli_e2e.py \
      tests/test_package_skeleton_units.py -q
      -> 8 failed: the missing `discover_files` API and Markdown-only
         extractor selection caused every failure.

GREEN uv run python -m pytest tests/test_discovery.py \
      tests/test_discovery_properties.py tests/test_check_files.py \
      tests/test_cli_e2e.py tests/test_package_skeleton_units.py -q
      -> 53 passed; the property, BDD scenarios, subprocess test, and
         snapshot all passed.

GATES make check-fmt, make typecheck, make lint, make test,
      make markdownlint, and make nixie
      -> PASS; make test reported 332 Rust tests, 218 Python tests, and
         17 snapshots. Logs end in `-4.out` under `/tmp` using the W0 prefix.
```

The first full lint run rejected a runtime `collections.abc` import (TC003),
and the second rejected a large assertion literal (C9102 and R9108). Moving the
import under `TYPE_CHECKING` and replacing the literal with a normalized,
semantic assertion plus a focused snapshot resolved both findings without
changing the intended behaviour.

The planning-time dry run, retained as the W6 baseline:

```plaintext
discovered counts: {'md': 64, 'py': 76, 'rs': 92} total 232
files producing IR errors: 3
```

Measured corpus sizes, so the W6 comparison can separate file-count growth from
byte growth:

| Extension | Files | Total    | Mean     |
| --------- | ----- | -------- | -------- |
| `.md`     | 65    | 1.61 MiB | 25.4 KiB |
| `.py`     | 76    | 0.31 MiB | 4.2 KiB  |
| `.rs`     | 92    | 0.43 MiB | 4.8 KiB  |

*Table 2: file counts and byte totals per extension in this repository, under
W1's prune list. File count grows 3.6× but total bytes only ~1.5×.*

Milestone-2 W4--W6 evidence, 2026-08-24:

```plaintext
RED   cargo test -p stilyagi-ir is_authored_directive_code
      -> E0432: unresolved import before the Rust vocabulary existed.

GREEN cargo test -p stilyagi-ir is_authored_directive_code
      -> 9 passed.
      cargo test -p stilyagi-pyext authored_directive_error_codes
      -> PASS.
      uv run python -m pytest tests/test_discovery.py \
      tests/test_discovery_properties.py tests/test_ir_error_adapter.py \
      tests/test_check_command.py tests/test_check_files.py \
      tests/test_renderers.py tests/test_cli_e2e.py tests/test_corpus.py \
      tests/test_structural_performance_probe.py \
      tests/test_package_skeleton_units.py -v
      -> 92 passed; 9 snapshots passed.
```

The live discovery walk found 236 registered files and 183 unregistered source
candidates: 65 Markdown files totalling 1,716,784 bytes, 78 Python files
totalling 399,684 bytes, and 93 Rust files totalling 469,236 bytes. The
five-iteration W6 probe
(`/tmp/w6-performance-7dac0d2e-fd47-4ed3-ae7c-3814893c769e.out`) recorded warm
medians and throughput of 200,253 ns/file and 1.30 MiB/s for Markdown, 188,323
ns/file and 2.66 MiB/s for Python, and 171,113 ns/file and 3.23 MiB/s for Rust.
The clean three-file acceptance command reported `{'discovery_misses': 4}` from
`ConfigResolver.cache_stats` and a zero-error, zero-warning summary. Full
milestone-2 gates passed: `check-fmt`, `typecheck`, `lint`, `test` (223 Python
tests and 17 snapshots), `markdownlint`, and `nixie`. CodeRabbit reviewed commit
`764bde2` with zero concerns
(`/tmp/coderabbit-7dac0d2e-fd47-4ed3-ae7c-3814893c769e-3-2-1-expand-discovery-defaults-to-md-py-and-rs-2.out`).

## Interfaces and dependencies

These must exist when the plan is complete. Names are prescriptive.

In `crates/stilyagi-ir/src/suppression.rs`, re-exported from
`crates/stilyagi-ir/src/lib.rs`:

```rust
pub const AUTHORED_DIRECTIVE_ERROR_CODES: &[&str];

#[must_use]
pub fn is_authored_directive_code(code: &str) -> bool;
```

In `crates/stilyagi-pyext/src/lib.rs`, registered in `_stilyagi_rs` and
declared in `python/stilyagi/_stilyagi_rs.pyi`:

```python
def authored_directive_error_codes() -> tuple[str, ...]: ...
```

In `python/stilyagi/discovery.py`:

```python
@dc.dataclass(frozen=True, slots=True)
class DiscoveredFile:
    reported_path: str
    resolved_path: pathlib.Path
    syntax: model.Syntax


def syntax_for_path(path: pathlib.Path) -> model.Syntax | None: ...


def discover_files(
    targets: cabc.Iterable[pathlib.Path | str],
    config: StilyagiConfig,
) -> list[DiscoveredFile]: ...
```

In `python/stilyagi/cli.py`:

```python
@dc.dataclass(frozen=True, slots=True)
class CheckInput:
    reported_path: str
    resolved_path: pathlib.Path
    syntax: model.Syntax
    source_text: str | None = None

    @classmethod
    def from_discovered(
        cls,
        file: discovery.DiscoveredFile,
        *,
        source_text: str | None = None,
    ) -> CheckInput: ...
```

Libraries: no new runtime dependency (Constraint 2). Test-only use of `rstest`,
`insta`, and `proptest` on the Rust side and `pytest`, `pytest-bdd`, `syrupy`,
and `hypothesis` on the Python side — all already present. `kani` and `verus`
are deliberately not used; see D6.

## References

- [Stilyagi design](../stilyagi-design.md) §§1, 3-4, 7.2, 7.3, 13
- [RFC 0002: Stilyagi Python rule API](../rfcs/0002-stilyagi-python-rule-api.md)
  §9 (severity vocabulary)
- [RFC 0003: Stilyagi CLI contract](../rfcs/0003-stilyagi-cli-contract.md)
  §§2-3, 5-7, 11-12
- [Roadmap](../roadmap.md) §3.2
- [ExecPlan for roadmap 2.2.1](roadmap-2-2-1.md) — the `check` loop this extends
- [ExecPlan for roadmap 3.1.2](roadmap-3-1-2.md) — Rust doc-comment extraction,
  which deferred `*.rs` discovery to this item
- [ExecPlan for roadmap 3.1.3](roadmap-3-1-3.md) — cross-syntax suppressions
- [ExecPlan for roadmap 1.3.3](1-3-3-cold-and-warm-baseline-performance-probes.md)
  — the structural probe W6 extends
- [ADR 006](../adr-006-docstring-owner-metadata.md),
  [ADR 007](../adr-007-rust-doc-comment-owner-metadata.md)
- [Developers' guide](../developers-guide.md),
  [users' guide](../users-guide.md), [documentation style guide](../documentation-style-guide.md)

[^1]: Ruff documents `include`, `extend-include`, `exclude`, `extend-exclude`,
    `respect-gitignore`, and `force-exclude`, and the rule that explicitly
    passed paths are analysed unless `force-exclude` is set. Its default
    exclusion list is the basis for the expanded pruning set in W1.
    <https://docs.astral.sh/ruff/settings/>

## Revision note

**Round 2 (2026-08-16).** Rewritten after a six-lens design review. Three
decisions changed and the Rust surface shrank by about a third.

What changed and why:

- **D1 reversed.** The extension table moves from Rust to Python. The review
  found that the design document already assigns file discovery to Rust (S8),
  so round 1's arrangement — table in Rust, walk in Python — was the one option
  that is neither the current state nor the target state, with a bridge
  round-trip that bought no capability and would be dead on arrival once
  discovery relocates. Constraint 3 is restated on a principle that
  discriminates ("vocabularies appearing in bridge payloads are Rust-owned")
  rather than one that over-reached. This deletes an entire work item, the
  compile-time proof, a `proptest`, a bridge function, a second parity check,
  and a Rust BDD feature.
- **D5 reversed.** The error-code classification inverts to enumerate only the
  two *authored* codes, declared beside their mint sites, defaulting everything
  else to warning. Round 1 had it backwards in two ways (S7): it enumerated six
  codes minted in a crate that `stilyagi-ir` cannot see, guarded by a test that
  could not mechanically enumerate mint sites; and its default sent
  unclassified future codes to *error*, reintroducing the exact breakage the
  plan exists to prevent. Constraint 9 now records fail-safe polarity as an
  invariant.
- **D6 narrowed.** The argument against `kani` and `verus` stands and is worth
  preserving as precedent, but both arrays the compile-time proofs would have
  guarded are gone, so nothing needs them.
- **D9, D10, D11 added.** The review's operational lens found that a run
  checking zero files is byte-identical to one checking everything (S9), which
  makes D4's demotion of anomalies to warnings unsafe on its own — it converts
  a loud wrong failure into a quiet wrong success. The run summary is therefore
  promoted from nicety to the observability this plan owes for the ambiguity it
  creates, and is deliberately shipped in the same milestone as D4. D10 records
  that severity is knowingly the wrong axis for the exit code and names what
  roadmap item 3.2.2 must resolve. D11 scopes file-read hardening in and the
  run-wide exit-`2` redesign out.
- **W6 rebuilt on existing infrastructure.** Round 1 proposed an unstructured
  `time` reading, unaware that roadmap item 1.3.3 already delivered a versioned
  structural probe (S10) — a rigour regression. The probe is extended
  per-syntax instead, byte totals are recorded alongside file counts, and the
  meaningless "10× wall-clock" tolerance is replaced by a Markdown
  non-regression gate.
- **Work split into two milestones.** Discovery and dispatch are purely
  additive; classification and severity change the meaning of every run. They
  now have separate red-green cycles and separate reviews.
- **Documentation targets corrected.** The post-v1.0 table gets exactly one home
  (ADR 008, which is dated and permitted to be a snapshot) rather than being
  duplicated into a source-of-truth design document. The "adding a language"
  checklist is written from the real sixteen-item list rather than a plausible
  four. Line-number citations are replaced by section headings everywhere
  except W0's anchors, since this plan's own edits invalidate them.
- **Tolerances repaired.** Round 1's single 24-file budget would have tripped on
  day one. Code and documentation are now budgeted separately.

What did not change: D4 was challenged from two directions and upheld, with the
review's caveat accepted (it is only safe alongside the summary). The
probe-driven evidence base S1-S6 is preserved verbatim, and the behavioural
acceptance criteria are unchanged apart from leading with the clean run rather
than the one that exits `1`.

Effect on remaining work: milestone 1 now touches no Rust at all, so it needs no
`make build` and no bridge round-trip. Milestone 2 carries the whole contract
risk and should be reviewed on its own.

**Round 2a (2026-08-16).** Rebased onto `ddf791b` (PyO3 0.28.3 → 0.29.2,
`maturin` 1.13.3 → 1.14.1). No conflicts — `main` touched build, lock, and Rust
test files while this branch touches one document. Two substantive updates were
still needed, because that commit changed facts this plan asserted:

- **The whitaker baseline is retired.** This plan carried a "known pre-existing
  condition" that `make lint`'s `whitaker` step was red on `main` from
  `no_expect_outside_tests` findings. `ddf791b` cleared those findings, and all
  four gates now pass on this branch. Any whitaker finding this branch produces
  is now a regression it owns, so the caveat is replaced by that statement and
  the W0 instruction to characterize the red baseline is removed.
- **D12 added.** `ddf791b` established the convention that Rust test helpers
  outside a `#[test]` body use `let`-`else` plus `panic!` in place of
  `.expect()`, since `allow-expect-in-tests` does not cover helpers beside the
  tests. W6 adds tests in exactly the directory this governs, so the convention
  is recorded and W6-red now cites it. W4 also gained a note that the compile
  -fail golden files are pinned to PyO3 0.29 wording.

Gate evidence after the rebase: `make check-fmt`, `make typecheck`,
`make lint`, and `make test` all exit `0`; 198 Python tests pass with 8
snapshots.

**Round 2b (2026-08-16).** Rebased off `main` and onto `configure-df12-lints`,
and the pull request retargeted to match. Rebased a second time after that
branch was rewritten, using `--onto` so the rewritten base commits were not
replayed. Neither rebase conflicted — this branch touches only this document.
Two updates were needed because the new base moves the gates the plan cites:

- **`make lint` gained two Python tiers**, a df12 `pylint` plugin pass and
  `ambrleaks` over `tests`. The quality criteria enumerate them so a reviewer
  is not surprised by a failure from a gate the plan never mentioned.
- **D12's dependency is satisfied.** `ExpectValid` and developers' guide §6b
  landed in #111, and #96 subsequently reworked the same helpers on top. Both
  are present on this base, so W6 consumes the boundary instead of waiting on a
  branch. W0 now verifies they are still there rather than assuming it.

Checked and found *not* to need changes: developers' guide §6b survives at the
same heading, `assert_validation_reports` and `malformed.rs::document_for` are
still the names §6b cites, and ADR 008 is still the next free number. The
`must_ok!`/`must_some!` consolidation noted as follow-up in §6b remains open.

The typecheck gate moved twice on that branch and settled where it started. An
intermediate commit switched `make typecheck` to a strict `pyright` pass, and
this plan was updated to match; a later commit pinned `ty` and restored it. The
plan now cites `ty check` again. The lesson is recorded rather than the churn:
cite gates by their `make` target, and re-read the recipe at W0 rather than
trusting any statement in this document about which tool sits behind
`make typecheck`.
