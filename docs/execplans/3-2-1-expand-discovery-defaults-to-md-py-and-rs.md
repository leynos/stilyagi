# Expand discovery defaults to `*.md`, `*.py`, and `*.rs`

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
`Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`, `Decision Log`,
and `Outcomes & Retrospective` must be kept up to date as work proceeds.

Status: DRAFT

Approval gate: **not yet satisfied**. This is planning round 1. Do not begin
implementation until the plan is explicitly approved. Round 1 was produced from
direct inspection of the working tree plus four executed probes against the
built extension (recorded under `Surprises & discoveries`), and was revised
after a community-of-experts design review.

## Purpose / big picture

Roadmap item 3.2.1 (see [docs/roadmap.md](../roadmap.md) §3.2, line 285) is the
first step of the second vertical slice. It turns `stilyagi check` from a
Markdown-only command into a mixed-repository command, per
[Stilyagi design](../stilyagi-design.md) §7.3 and
[RFC 0003](../rfcs/0003-stilyagi-cli-contract.md) §7.

After this change, a maintainer standing in a mixed documentation and source
repository can run:

- `stilyagi check .` and have Stilyagi discover **every** `*.md`, `*.markdown`,
  `*.py`, and `*.rs` file beneath the current directory in one deterministic,
  path-sorted pass, select the correct extractor for each file from its
  extension, extract each file through the existing Rust bridge, and print
  diagnostics attributed to the right path;
- `stilyagi check src/lib.rs docs/guide.md` and have both files analysed, each
  through its own extractor, in one invocation;
- `stilyagi check - --stdin-filename src/mod.rs` and have standard input
  analysed as Rust rather than as Markdown; and
- `stilyagi check .` on this very repository and get exit code `1` with exactly
  two `suppression-blanket-forbidden` **errors** from the two corpus fixtures
  that deliberately contain forbidden blanket suppressions — and **no** errors
  from the deliberately malformed Rust fixture, whose tree-sitter parse-recovery
  notices are reported as warnings and do not fail the run.

The observable success condition is behavioural. A behaviour-driven-development
(BDD) feature drives `stilyagi check` over temporary mixed trees and asserts
per-extension extractor selection, ordering, and exit codes; an end-to-end test
invokes the command as a real subprocess over a mixed tree; property tests pin
discovery determinism and the extension-lookup contract; and snapshot tests pin
the text and JSON renderings of a mixed-source run.

Two downstream roadmap items are unblocked by this one: 3.2.3 (`Requires 3.1.3,
3.2.1, and 2.2.2`) and 3.3.1 (`Requires 3.2.1 and 2.2.3`).

### Scope boundary (what this slice deliberately excludes)

This slice expands *discovery* and *extractor selection*, and makes the minimum
diagnostic-classification change needed for the roadmap's success criterion to
hold. It deliberately stops short of:

- **Built-in docstring and doc-comment rules.** Those are roadmap item 3.2.2.
  The rule registry still matches nothing; `python/stilyagi/rules/registry.py`
  is unchanged by this plan.
- **`dump-ir`, fix planning, `--fix`, `--diff`, and `--no-cache`.** Those are
  roadmap items 2.2.2 and 2.2.3. Only `check` is touched.
- **Cache-key separation by syntax.** That is roadmap item 3.3.1, which
  explicitly `Requires 3.2.1`. No cache code is written here.
- **New extractors.** No new language is implemented. The Rust extractor
  already supports all three syntaxes end to end; this plan only teaches
  discovery and the CLI how to reach the two that were previously unreachable.
- **`.gitignore` honouring.** RFC 0003 §7 makes this a SHOULD, not a SHALL.
  Roadmap item 2.2.1 deferred it to avoid adding a runtime dependency, and this
  plan preserves that deferral. `respect-gitignore` remains accepted-but-not-
  enforced, and the plan does **not** add `pathspec`, `ignore`, or any
  equivalent dependency.
- **`include` / `exclude` configuration keys.** RFC 0003 §6 defines no such
  keys, and roadmap item 2.2.1 explicitly removed an invented `[discovery]
  include` key as out-of-contract. Discovery scope stays a fixed built-in set in
  v1. See Decision Log entry D2.
- **`*.mdx`, `*.pyi`, and every post-v1.0 language.** These are *documented* as
  future targets (work item W7) but not implemented. RFC 0003 §7 keeps MDX
  preview-only.
- **Any IR schema change.** `SCHEMA_VERSION` is not bumped. `IrError` gains no
  fields. See Decision Log entry D5.

## Constraints

Hard invariants. Violating one requires escalation, not a workaround.

1. **No IR schema change.** `crates/stilyagi-ir/src/document.rs`
   `SCHEMA_VERSION` must not change, and `IrError` must not gain or lose
   fields. Mixed-source IR shape is roadmap item 3.2.3's remit.
2. **No new runtime dependency.** Neither `Cargo.toml` nor the `pyproject.toml`
   runtime dependency set may gain an entry. Test-only development dependencies
   already present (`rstest`, `rstest-bdd`, `insta`, `proptest`, `pytest`,
   `pytest-bdd`, `syrupy`, `hypothesis`) may be used freely; adding a *new* one
   is a tolerance breach.
3. **One source of truth for the extension-to-syntax mapping.** The mapping must
   be declared exactly once, in Rust, and reach Python only through the PyO3
   bridge. Python must not carry a second hand-maintained copy. This mirrors the
   existing `supported_syntaxes()` / `supported_region_kinds()` discipline and
   its parity check in `python/stilyagi/engine/extraction.py`
   `_validate_syntax_vocab_once`.
4. **Determinism.** For any target set, `stilyagi check` must process files in a
   total order determined solely by resolved path, independent of the order in
   which targets were supplied, and must process each resolved path exactly
   once.
5. **Exit-code contract.** RFC 0003 §12 stands unchanged: `0` when no violations
   remain, `1` when violations remain, `2` on invalid configuration, invalid
   usage, plugin load failure, or internal error.
6. **Public Python import surface.** The surface documented in
   [users' guide](../users-guide.md) §1a — `stilyagi`, `stilyagi.engine`,
   `stilyagi.model`, `stilyagi.config.StilyagiConfig`,
   `stilyagi.diagnostics.Diagnostic`, `stilyagi.nlp.SpacyProviderConfig` — must
   keep working unchanged. `stilyagi.discovery` is *not* in that surface and may
   be renamed within this plan.
7. **Every commit is gated.** `make check-fmt`, `make typecheck`, `make lint`,
   and `make test` must all pass before each commit, and `make markdownlint`
   plus `make nixie` must additionally pass for any commit touching Markdown.
8. **British English.** All prose uses en-GB-oxendict spelling, enforced by the
   `typos` gate inside `make markdownlint`.

## Tolerances (exception triggers)

Stop and escalate — do not improvize — when any of these is reached.

- **Scope:** more than 24 files changed, or more than 900 net lines added across
  the whole plan.
- **Dependencies:** any new entry in `Cargo.toml` `[dependencies]` or in the
  `pyproject.toml` runtime dependency set. (This is also Constraint 2.)
- **Interface:** any change to the signature of `_stilyagi_rs.extract_document`,
  to `stilyagi.engine.extract_document`, or to any symbol named in Constraint 6.
- **Schema:** any need to change `SCHEMA_VERSION` or `IrError`. (Also
  Constraint 1.)
- **Iterations:** a given gate still failing after 3 corrective attempts.
- **Time:** any single work item exceeding 3 hours.
- **Ambiguity:** if work item W5 (extraction-anomaly severity) proves to require
  reshaping the `Diagnostic` model or the renderers beyond adding a severity
  value that already exists, stop — that is roadmap item 3.2.3's territory and
  the boundary has been misjudged.
- **Performance:** if `stilyagi check .` on this repository takes more than 10×
  the wall-clock time of the pre-change Markdown-only run, stop and escalate
  rather than optimizing opportunistically.

## Risks

- **Risk:** Expanding discovery turns tree-sitter parse-recovery notices into
  user-facing errors, so `stilyagi check .` fails on any repository containing a
  file the pinned grammar cannot fully parse — including generated code,
  templates with source extensions, and files using syntax newer than the pinned
  grammar.
  Severity: high. Likelihood: high (already reproduced — see
  `Surprises & discoveries`, S2).
  Mitigation: work item W5 classifies extraction anomalies as warnings that do
  not drive exit `1`, while genuine authored-directive violations stay errors.

- **Risk:** The expanded ignored-directory list prunes a directory a user
  legitimately wants checked (for example a real source directory named
  `build`).
  Severity: medium. Likelihood: low.
  Mitigation: pruning stays name-based and additive to the existing list; the
  behaviour is documented in the users' guide; a directory named on the command
  line as an explicit target is never pruned (only its descendants are). This
  limitation is recorded in ADR 008 as a known limitation with `include` /
  `exclude` configuration named as the post-v1 remedy.

- **Risk:** Walking `*.py` and `*.rs` makes `stilyagi check .` markedly slower
  on large repositories, because file count roughly quadruples.
  Severity: medium. Likelihood: medium.
  Mitigation: measured, not guessed — work item W6 records a before-and-after
  wall-clock figure on this repository as evidence, and the tolerance above sets
  an escalation threshold. Note the pre-existing directory pruning already
  removes `target/` and `.venv/`, the two largest sources of noise.

- **Risk:** The extension-to-syntax table and the `ExtractSyntax` variants drift
  apart, or two extensions collide on one syntax silently.
  Severity: medium. Likelihood: low.
  Mitigation: the table is the single source of truth (Constraint 3); its
  injectivity is proven exhaustively at compile time by a `const` assertion
  (work item W1); and a property test asserts the lookup is total and agrees
  with a naive reference scan.

- **Risk:** The malformed Python corpus fixture is named
  `unclosed-function.py.txt` precisely so nothing treats it as importable
  Python. A suffix-based discovery rule that looked at anything other than the
  final suffix would start discovering it.
  Severity: low. Likelihood: low.
  Mitigation: matching uses `pathlib.Path.suffix` (the final suffix only), so
  `.py.txt` resolves to `.txt` and is correctly skipped. A regression test pins
  this exact case.

- **Risk:** The design document's §7.3 critique that RFC 0003 "includes too many
  source-language file types" no longer matches the RFC, which already lists
  only `*.md`, `*.py`, and `*.rs`.
  Severity: low. Likelihood: certain (confirmed against history — see S4).
  Mitigation: work item W7 corrects the design text to record that the RFC was
  trimmed by `787526e`, rather than leaving a contradiction in the source of
  truth that the new post-v1.0 table would sit on top of.

## Progress

- [ ] W0. Stage A: confirm the working tree matches this plan's assumptions and
      capture the baseline gate run.
- [ ] W1. Rust: declare the extension-to-syntax table in `stilyagi-extract`,
      with a compile-time injectivity proof and a property test.
- [ ] W2. Rust: classify IR error codes in `stilyagi-ir` into extraction
      anomalies and authored-directive violations, with a compile-time
      disjointness proof.
- [ ] W3. PyO3: expose `default_discovery_extensions()` and
      `extraction_anomaly_error_codes()` from `_stilyagi_rs`.
- [ ] W4. Python: generalize discovery from Markdown-only to the bridge-supplied
      extension set, carrying the selected syntax on each discovered file.
- [ ] W5. Python: select the extractor per file in the `check` loop, classify
      extraction anomalies as warnings, and count only errors towards exit `1`.
- [ ] W6. Tests: BDD features, snapshots, property tests, end-to-end subprocess
      coverage, and the performance measurement.
- [ ] W7. Documentation: ADR 008, design §7.3 post-v1.0 target table, users'
      guide, developers' guide, contents index.
- [ ] W8. Mark roadmap item 3.2.1 done and record outcomes.

## Surprises & discoveries

These were found during planning, by executing probes against the built
extension in the working tree. They are the evidence base for Decision Log
entries D4 and D5, and they are the reason this plan is larger than "add three
strings to a frozenset".

- **S1. The Rust side is already complete; the gap is entirely in Python.**
  Observation: `ExtractSyntax` already has `Markdown`, `PythonDocstring`, and
  `RustDocComment` variants and dispatches all three
  (`crates/stilyagi-extract/src/lib.rs:19-26`, `:167-189`); the PyO3 bridge
  already round-trips all three; and `model.Syntax`
  (`python/stilyagi/model/document.py:13-18`) already has all three members.
  Evidence: `crates/stilyagi-pyext/src/tests/rust_doc_comment.rs`,
  `tests/test_python_docstring_extraction.py`.
  Impact: the load-bearing gap is exactly two things — `_MARKDOWN_SUFFIXES` at
  `python/stilyagi/discovery.py:25`, and the hard-coded
  `model.Syntax.MARKDOWN` at `python/stilyagi/cli.py:280`. No new extractor
  work is needed.

- **S2. Unlike Markdown, the Python and Rust extractors *do* populate IR
  `errors[]`, and every entry currently becomes a `Severity.ERROR` diagnostic.**
  Observation: roadmap item 2.2.1 established that malformed Markdown recovers
  with an empty `errors[]`, so `check` exits `0`. That does not generalize.
  Evidence, from probes run against the built extension:

  ```plaintext
  python/malformed: OK regions=1 errors=2 codes=['python-parse-recovery', 'python-parse-recovery']
  rust/malformed:   OK regions=1 errors=2 codes=['rust-doc-comment-error-subtree', 'rust-parse-recovery']
  garbage/python_docstring: OK regions=0 errors=3
  garbage/rust_doc_comment: OK regions=0 errors=1
  garbage/markdown:         OK regions=1 errors=0
  ```

  Impact: this is the single most important finding in the plan. Because
  `map_ir_errors` (`python/stilyagi/engine/checker.py:85-92`) hard-codes
  `severity=Severity.ERROR` and `compute_exit_code`
  (`python/stilyagi/cli.py:185-189`) returns `1` for any non-empty diagnostic
  list, expanding discovery without W5 would make `stilyagi check .` fail on
  every repository containing a file the pinned grammar cannot fully parse.
  That directly contradicts the roadmap's success criterion. Note also that
  neither extractor *raises* on malformed input — recovery is graceful, so
  there is no exit-`2` explosion, only misclassified severity.

- **S3. A full-repository dry run quantifies the change exactly.**
  Observation: simulating the proposed discovery rules over this repository,
  with the existing pruning list, yields:

  ```plaintext
  discovered counts: {'md': 64, 'py': 76, 'rs': 92} total 232
  files producing IR errors: 3
    tests/fixtures/corpus/python/valid/module-class-function-docstrings.py  1  ['suppression-blanket-forbidden']
    tests/fixtures/corpus/rust/malformed/unclosed-item.rs                   2  ['rust-doc-comment-error-subtree', 'rust-parse-recovery']
    tests/fixtures/corpus/rust/valid/item-doc-comments.rs                   1  ['suppression-blanket-forbidden']
  ```

  Impact: discovery grows from 64 to 232 files (3.6×). Crucially, **all 232
  valid source files produce zero IR errors** — a separate probe over 16
  production files in `python/stilyagi/` and `crates/` returned
  `TOTAL ERRORS on valid sources: 0`. The only noise comes from fixtures that
  are *deliberately* adversarial. This makes the acceptance criterion in
  `Purpose` concrete and checkable, and it validates W5's split: after W5, the
  two `suppression-blanket-forbidden` entries remain errors (they are genuine
  authored-directive violations and *should* fail the run), while the two
  recovery notices on the deliberately malformed fixture become warnings.

- **S4. The design document's §7.3 critique of RFC 0003 is stale, and history
  proves it.**
  Observation: `docs/stilyagi-design.md:1008-1009` says the RFC "includes too
  many source-language file types for a v1 extractor story that has not yet
  earned them", but `docs/rfcs/0003-stilyagi-cli-contract.md:231-239` already
  lists only `*.md`, `*.py`, `*.rs` and explicitly excludes MDX — exactly what
  the design's own "Recommended revisions" (line 1017) asks for.
  Evidence: at the RFC's original commit `bbf93da`, §7 read:

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

  That is the over-claim the design criticized. It was trimmed to the current
  three-extension list by `787526e` ("Add RFC harmonization execplan", roadmap
  item 1.1.3).
  Impact: the critique describes a state that was already remediated, so the
  design now contradicts the RFC it cites. W7 corrects the §7.3 text to record
  that the RFC was trimmed, rather than layering the new post-v1.0 table on top
  of a contradiction. No further history archaeology is needed — this is settled.

- **S5. The complete IR error-code vocabulary is only eight codes, and it splits
  cleanly along exactly the line W5 needs.**
  Observation: enumerating every `code: "..."` minted outside test modules
  yields `python-parse-recovery`, `python-traversal-depth-limit`,
  `rust-parse-recovery`, `rust-traversal-depth-limit`,
  `rust-doc-comment-error-subtree`, `rust-doc-comment-span`,
  `suppression-blanket-forbidden`, and `suppression-unknown-verb`. The first six
  are grammar or traversal anomalies; the last two are things a human wrote
  incorrectly. The doc comment on `IrError`
  (`crates/stilyagi-ir/src/diagnostics.rs:51`) already reads "Non-fatal parser
  or extractor anomaly".
  Impact: W5's classification is not a new taxonomy invented for convenience —
  it makes an existing, already-documented distinction observable. The
  vocabulary is small and closed enough to declare as two `const` arrays with a
  compile-time disjointness proof.

- **S6. `Severity.WARNING` already exists and is entirely unused.**
  Observation: `python/stilyagi/diagnostics.py:9-13` declares both `ERROR` and
  `WARNING`; grepping shows nothing ever constructs a `WARNING` diagnostic.
  Impact: W5 needs no model change — it populates a value the model already
  reserved. This keeps W5 comfortably inside its tolerance.

## Decision log

- **D1. The extension-to-syntax mapping lives in Rust, in `stilyagi-extract`,
  beside `ExtractSyntax`, and reaches Python only through the PyO3 bridge.**
  Rationale: `ExtractSyntax` is already the authority on which syntaxes exist and
  how they are spelled, and the repository already has a working idiom for
  advertising such vocabularies to Python (`supported_syntaxes()`,
  `supported_region_kinds()`) together with a fail-fast parity check
  (`_validate_syntax_vocab_once`). Declaring the table in Python instead would
  create a second copy that can drift from the dispatch it feeds. Rejected
  alternative: a Python-side `dict[str, model.Syntax]`; simpler today, but it
  puts the mapping on the far side of the bridge from the dispatch it selects,
  and every future language would need two coordinated edits.
  Date/Author: 2026-08-16, planning agent.

- **D2. Discovery scope stays a fixed built-in extension set. No `include` /
  `exclude` configuration keys are added.**
  Rationale: RFC 0003 §6's baseline schema defines no such keys, and §7 states
  discovery defaults as a fixed list. Roadmap item 2.2.1 explicitly removed an
  invented `[discovery] include` key as out-of-contract
  (`docs/execplans/roadmap-2-2-1.md:501-502`). Inventing configuration surface
  ahead of the contract is exactly the mistake that decision corrected.
  Consequence: users cannot narrow or widen discovery in v1; this is recorded as
  a known limitation in ADR 008 with configurable patterns named as the post-v1
  remedy.
  Date/Author: 2026-08-16, planning agent.

- **D3. `.markdown` is retained alongside `.md`, and `.pyi` and `.mdx` are
  not added.**
  Rationale: `.markdown` is already discovered today
  (`python/stilyagi/discovery.py:25`); dropping it would be a silent regression
  for existing users. `.mdx` is explicitly preview-only per RFC 0003 §7. `.pyi`
  is not named by the RFC, and stub files carry a different docstring culture
  (frequently none at all), so admitting them is a product decision that has not
  been taken. Both are listed in the ADR 008 post-v1.0 candidate table.
  Date/Author: 2026-08-16, planning agent.

- **D4. Extraction anomalies are reported as warnings and do not by themselves
  produce exit `1`; authored-directive violations remain errors and do.**
  Rationale: RFC 0003 §12 defines exit `1` as "when violations remain". A
  tree-sitter parse-recovery event is not a violation of any prose rule — it is
  a statement that the extractor degraded. `IrError`'s own doc comment already
  calls these "anomalies". Conversely, `suppression-blanket-forbidden` and
  `suppression-unknown-verb` describe something a human wrote incorrectly and
  are properly violations. Without this split, S2 and S3 show `stilyagi check .`
  would fail on any repository containing a file the pinned grammar cannot
  parse, which would make the roadmap's success criterion false. Rejected
  alternative: defer the whole question to roadmap item 3.2.3; rejected because
  3.2.1 owns the success criterion "`stilyagi check .` works on mixed
  documentation and source trees", and it demonstrably would not.
  **This is the decision most likely to warrant reviewer challenge; if the
  reviewer prefers deferral, W5 splits out cleanly and the acceptance criteria
  in `Purpose` change accordingly.**
  Date/Author: 2026-08-16, planning agent.

- **D5. The anomaly-versus-violation classification is expressed as two `const`
  string arrays in `stilyagi-ir`, not as a new `IrError` field.**
  Rationale: adding a `severity` or `class` field to `IrError` would change the
  serialized IR envelope and require a `SCHEMA_VERSION` bump, which Constraint 1
  forbids and which belongs to roadmap items 2.1.1 and 3.2.3. Two `const` arrays
  beside the code definitions give a single source of truth, cost nothing at
  runtime, and can be proven disjoint at compile time. When 3.2.3 reshapes the
  IR envelope it can promote this classification into the schema properly.
  Date/Author: 2026-08-16, planning agent.

- **D6. Invariants are proven with `const` assertions and `proptest`, not with
  `kani` or `verus`.**
  Rationale: neither `kani` nor `verus` is wired into this repository — there is
  no Makefile target, no `.config/` entry, and no CI workflow step for either;
  they appear only as aspirations in prose documents. Introducing a verification
  toolchain would breach the dependency tolerance and dwarf the change it
  verifies. The two invariants that genuinely need exhaustive treatment —
  injectivity of the extension table, and disjointness of the two error-code
  classes — are over small fixed `const` arrays, so a `const fn` assertion
  evaluated by the compiler is *fully* exhaustive over the real domain, not a
  bounded approximation of it. That is a stronger result than a bounded model
  check, obtained for free. The remaining invariant — that the lookup is total
  and case-insensitive over arbitrary input — is genuinely over an unbounded
  input domain and is the right job for `proptest`.
  Date/Author: 2026-08-16, planning agent.

- **D7. `discover_markdown_files` is renamed to `discover_files`, and
  `python/stilyagi/discovery.py` keeps its module path.**
  Rationale: the name would otherwise lie. `stilyagi.discovery` is not part of
  the public import surface documented in users' guide §1a (Constraint 6), so no
  compatibility shim is owed. Keeping the module path avoids churn in the
  developers' guide §2b "Discovery" section, which can be edited in place.
  Date/Author: 2026-08-16, planning agent.

## Outcomes & retrospective

To be completed at W8. Compare the delivered behaviour against the four
acceptance bullets in `Purpose`, record the measured file-count and wall-clock
change from W6, and note whether the W5 boundary against roadmap item 3.2.3 held.

## Context and orientation

Assume no prior knowledge of this repository.

Stilyagi is a prose linter for documentation and for documentation comments
inside source code. It is a mixed Rust and Python project. The Rust crates under
`crates/` parse source files and produce a canonical intermediate representation
(IR); the Python package under `python/stilyagi/` owns the command-line
interface (CLI), configuration, rule execution, and diagnostic rendering. The
two halves meet at a narrow PyO3 bridge module named `_stilyagi_rs`.

Key terms used throughout this plan:

- **IR (intermediate representation).** The canonical JavaScript Object Notation
  (JSON) envelope the Rust extractor produces for one file. It carries prose
  `regions`, `suppressions`, and non-fatal `errors`.
- **Region.** One span of prose the linter may analyse — a Markdown paragraph, a
  Python docstring, a Rust documentation comment.
- **Syntax.** Which extractor to run. Spelled `markdown`, `python_docstring`, or
  `rust_doc_comment`. Note this is *not* the same vocabulary as the IR's
  `metadata.syntax` field, which uses bare language names (`markdown`,
  `python`, `rust`). This plan only touches the former.
- **Discovery.** Walking command-line targets to produce the ordered list of
  files to check.
- **Extraction anomaly.** A non-fatal notice that the extractor degraded — a
  tree-sitter parse recovery, a traversal depth limit, a doc comment absorbed
  into an error subtree.
- **Authored-directive violation.** A notice that a human wrote a Stilyagi
  suppression comment incorrectly.

### The files this plan touches

Rust:

- `crates/stilyagi-extract/src/lib.rs` — declares `ExtractSyntax` (lines 18-60)
  and dispatches extraction (lines 167-189). W1 adds the extension table here.
- `crates/stilyagi-ir/src/diagnostics.rs` — declares `IrError` (line 53). W2
  adds the two error-code classification arrays here.
- `crates/stilyagi-pyext/src/lib.rs` — the PyO3 module. `supported_syntaxes`
  (lines 24-32) and `supported_region_kinds` (lines 35-44) are the two functions
  W3 mirrors; the module registration list is at lines 159-166.

Python:

- `python/stilyagi/discovery.py` — the whole file is Markdown-scoped today:
  module docstring (line 1), `_MARKDOWN_SUFFIXES` (line 25),
  `_IGNORED_DIRECTORY_NAMES` (lines 26-33), `DiscoveredFile` (lines 43-57),
  `discover_markdown_files` (line 60), `_is_markdown_file` (lines 178-180).
  W4 rewrites it.
- `python/stilyagi/cli.py` — `CheckInput` (lines 36-42), `_discover_targets`
  (lines 192-214), `_stdin_check_input` (lines 236-248), `_check_one_file`
  (lines 268-299, with the hard-coded `model.Syntax.MARKDOWN` at line 280), and
  `compute_exit_code` (lines 167-189). W4 and W5 edit these.
- `python/stilyagi/engine/checker.py` — `map_ir_errors` (line 16), which
  hard-codes `severity=Severity.ERROR` at line 89. W5 edits this.
- `python/stilyagi/engine/extraction.py` — the bridge adapter and the parity
  check `_validate_syntax_vocab_once` (lines 67-85), plus the reset hook
  `_reset_extraction_state_for_tests` (lines 88-94) that tests must call after
  patching bridge functions. W3 and W4 extend this.
- `python/stilyagi/cli_args.py` — the `check` sub-parser help string (line 89)
  and the `targets` help string (line 202), both of which say "Markdown".
- `python/stilyagi/engine/api.py` — a docstring at line 35 claiming "The first
  implemented extractor supports `model.Syntax.MARKDOWN`", now stale.

Tests and fixtures:

- `tests/test_discovery.py` and `tests/test_discovery_properties.py` — the
  direct precedents to extend.
- `tests/steps/check_command.py` — pytest-bdd steps for `check`, registered as a
  plugin from `tests/test_package_skeleton_units.py:27`.
- `features/stilyagi_check_command.feature` — the Gherkin feature for `check`.
- `tests/test_cli_e2e.py` — the only true-subprocess CLI test, using
  `tests/support/subprocess_env.py:python_module_environment()`.
- `tests/fixtures/corpus/{markdown,python,rust}/{valid,malformed}/` — the shared
  corpus. Note the malformed Python fixture is `unclosed-function.py.txt`, not
  `.py`, deliberately.
- `crates/stilyagi-extract/tests/extract/` plus
  `crates/stilyagi-extract/tests/features/` — the Rust `rstest` and `rstest-bdd`
  precedents.

### Signposted documentation and skills

Read these before starting the work item that cites them.

| Work item | Read first |
| --- | --- |
| All | [AGENTS.md](../../AGENTS.md); [developers' guide](../developers-guide.md) §2b (the `check` pipeline, lines 351-469) and §6 (lint, typecheck, test workflow) |
| W1, W2 | `rust-router` skill, then `rust-types-and-apis`; [ADR 007](../adr-007-rust-doc-comment-owner-metadata.md) for the owner-metadata precedent |
| W1, W2 | `proptest` skill for the property tests; `arch-crate-design` skill for where a shared `const` belongs |
| W3 | [developers' guide](../developers-guide.md) §4 "Rust and PyO3 integration" (lines 637-785) |
| W4, W5 | `python-router` skill, then `python-types-and-apis` and `python-errors-and-logging`; `hexagonal-architecture` skill for the port boundary argument in D1 |
| W4, W5 | [complexity antipatterns and refactoring strategies](../complexity-antipatterns-and-refactoring-strategies.md) |
| W6 | [rust testing with rstest fixtures](../rust-testing-with-rstest-fixtures.md); [rstest-bdd users' guide](../rstest-bdd-users-guide.md); [reliable testing in Rust via dependency injection](../reliable-testing-in-rust-via-dependency-injection.md); [rust doctest DRY guide](../rust-doctest-dry-guide.md); `rust-unit-testing`, `python-testing`, and `hypothesis` skills |
| W7 | [documentation style guide](../documentation-style-guide.md), especially the ADR template (lines 414-491); `arch-decision-records` skill; `en-gb-oxendict` skill |

*Table 1: which documents and skills to read before each work item.*

## Plan of work

Stages run in order. Each ends with validation; do not start the next stage
while the current stage's validation fails.

### Stage A — orient and baseline (no production code changes)

Confirm the tree matches this plan's assumptions, then capture a clean baseline
so any later gate failure is attributable.

**W0.** Verify that `python/stilyagi/discovery.py:25` still reads
`_MARKDOWN_SUFFIXES = frozenset({".md", ".markdown"})` and that
`python/stilyagi/cli.py:280` still reads
`engine.extract_document(source, model.Syntax.MARKDOWN)`. If either has moved,
stop and escalate — the plan was written against a different tree. Then run the
four gates and record the baseline, and re-run the S3 dry run to confirm the
232-file figure still holds.

Go/no-go: all four gates green, and both anchors confirmed.

### Stage B — red tests and feature specifications

Write the failing tests before any production change. Every test added in this
stage must fail, and must fail for the stated reason.

**W1-red.** In `crates/stilyagi-extract/src/tests.rs` (or a new
`src/tests/discovery_extensions.rs` module included from it), add an `rstest`
table test asserting `ExtractSyntax::from_discovery_extension` maps `"md"` and
`"markdown"` to `Markdown`, `"py"` to `PythonDocstring`, `"rs"` to
`RustDocComment`, `"MD"` and `"Rs"` to the same variants as their lowercase
forms, and `"txt"`, `""`, and `"pyi"` to `None`. Expect a compile failure
(the function does not exist).

**W2-red.** In `crates/stilyagi-ir/src/tests/`, add an `rstest` test asserting
that `is_extraction_anomaly_code` returns `true` for each of the six anomaly
codes and `false` for the two suppression codes and for an unknown code.

**W3-red.** In `crates/stilyagi-pyext/src/tests/`, add tests asserting the two
new module functions are registered and return the expected shapes.

**W4-red.** In `tests/test_discovery.py`, add cases asserting that a tree
containing `a.md`, `b.py`, `c.rs`, `d.txt`, and
`e.py.txt` discovers exactly `a.md`, `b.py`, and `c.rs`, each carrying the right
`syntax`; that an explicit `d.txt` target is skipped with an informative log
record; and that `__pycache__`, `.mypy_cache`, `.ruff_cache`, `.pytest_cache`,
`.tox`, `.nox`, `.eggs`, `site-packages`, and `.stilyagi_cache` directories are
pruned.

**W5-red.** In `tests/test_check_files.py`, add cases asserting that a tree
containing one malformed `.rs` file exits `0` with a warning-severity diagnostic
rather than exiting `1`, and that a tree containing a forbidden blanket
suppression exits `1` with an error-severity diagnostic.

**W6-red.** Extend `features/stilyagi_check_command.feature` with the scenarios
quoted below, and add the matching steps to `tests/steps/check_command.py`.
Extend `crates/stilyagi-extract/tests/features/` with a Rust-side feature for
the extension lookup, mirroring `rust_doc_comment_extraction.feature`.

The Python feature scenarios to add — keep this specification synchronized with
the implementation as work proceeds:

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

  Scenario: check reports a Rust parse recovery as a warning and still succeeds
    Given a temporary tree containing malformed Rust
    When I run "stilyagi check ." in that tree
    Then the exit code is 0
    And the text output reports a warning-severity diagnostic

  Scenario: check reports a forbidden blanket suppression as an error
    Given a temporary tree containing a Python file with a blanket suppression
    When I run "stilyagi check ." in that tree
    Then the exit code is 1
    And the text output reports an error-severity diagnostic

  Scenario: check attributes stdin to the syntax implied by the stdin filename
    Given a temporary tree with two well-formed Markdown files
    When I run "stilyagi check - --stdin-filename src/lib.rs" in that tree
    Then the exit code is 0
    And the standard input was extracted as Rust documentation comments
```

Go/no-go: every new test fails, and each failure message matches the reason the
test was written for. A test that passes at this stage is not exercising the
behaviour it claims to.

### Stage C — implementation

Make the smallest change that turns each red test green, in work-item order.
Commit after each work item, with all four gates green.

**W1. The extension table.** In `crates/stilyagi-extract/src/lib.rs`, beside
`ExtractSyntax`, add the table, the lookup, and the compile-time injectivity
proof. Extensions are stored *without* a leading dot and matched
ASCII-case-insensitively, because callers pass `pathlib.Path.suffix` values
that vary in case on case-insensitive filesystems.

The injectivity proof is a `const` assertion evaluated by the compiler, so it is
exhaustive over the whole table with no runtime cost and no new toolchain:

```rust
/// Default discovery extensions, lowercase and without a leading dot.
pub const DEFAULT_DISCOVERY_EXTENSIONS: [(&str, ExtractSyntax); 4] = [
    ("md", ExtractSyntax::Markdown),
    ("markdown", ExtractSyntax::Markdown),
    ("py", ExtractSyntax::PythonDocstring),
    ("rs", ExtractSyntax::RustDocComment),
];

const fn bytes_equal(left: &[u8], right: &[u8]) -> bool {
    if left.len() != right.len() {
        return false;
    }
    let mut index = 0;
    while index < left.len() {
        if left[index] != right[index] {
            return false;
        }
        index += 1;
    }
    true
}

/// Compile-time proof that no extension is registered against two syntaxes.
///
/// This is exhaustive over the whole table, so a duplicate entry is a build
/// failure rather than a silently ambiguous lookup at runtime.
const _: () = {
    let mut outer = 0;
    while outer < DEFAULT_DISCOVERY_EXTENSIONS.len() {
        let mut inner = outer + 1;
        while inner < DEFAULT_DISCOVERY_EXTENSIONS.len() {
            assert!(
                !bytes_equal(
                    DEFAULT_DISCOVERY_EXTENSIONS[outer].0.as_bytes(),
                    DEFAULT_DISCOVERY_EXTENSIONS[inner].0.as_bytes(),
                ),
                "duplicate discovery extension registered",
            );
            inner += 1;
        }
        outer += 1;
    }
};
```

Then the lookup itself:

```rust
impl ExtractSyntax {
    /// Return the syntax registered for one file extension, if any.
    ///
    /// The extension is supplied without a leading dot and is matched
    /// case-insensitively, so `"RS"` and `"rs"` both select
    /// [`ExtractSyntax::RustDocComment`].
    #[must_use]
    pub fn from_discovery_extension(extension: &str) -> Option<Self> { /* ... */ }
}
```

Add the `proptest` property, in the style of
`crates/stilyagi-ir/src/tests/suppression_proptest.rs`: for an arbitrary string,
`from_discovery_extension` never panics, and its result equals a naive linear
scan of `DEFAULT_DISCOVERY_EXTENSIONS` using ASCII-case-insensitive comparison.
This covers the unbounded input domain the `const` proof cannot.

**W2. Error-code classification.** In `crates/stilyagi-ir/src/diagnostics.rs`,
beside `IrError`, declare the two closed vocabularies and a compile-time
disjointness proof reusing `bytes_equal` (hoist it to a shared `const fn` in
`stilyagi-ir` and re-export, so W1 and W2 share one implementation):

```rust
/// Codes describing a degraded extraction rather than an authored mistake.
pub const EXTRACTION_ANOMALY_ERROR_CODES: [&str; 6] = [
    "python-parse-recovery",
    "python-traversal-depth-limit",
    "rust-parse-recovery",
    "rust-traversal-depth-limit",
    "rust-doc-comment-error-subtree",
    "rust-doc-comment-span",
];

/// Codes describing a Stilyagi directive a human wrote incorrectly.
pub const AUTHORED_DIRECTIVE_ERROR_CODES: [&str; 2] = [
    "suppression-blanket-forbidden",
    "suppression-unknown-verb",
];
```

Add `pub fn is_extraction_anomaly_code(code: &str) -> bool`, and a `const _: ()`
assertion proving the two arrays are disjoint. Add a Rust unit test asserting
that the union of the two arrays equals the set of codes minted across the
workspace; keep that test's expected list beside the arrays so a new code
without a classification fails the suite.

**W3. Bridge exposure.** In `crates/stilyagi-pyext/src/lib.rs`, mirror
`supported_syntaxes` exactly. Add
`default_discovery_extensions() -> tuple[tuple[str, str], ...]`, yielding
`(extension, syntax_name)` pairs in table order, and
`extraction_anomaly_error_codes() -> tuple[str, ...]`. Register both in the
module list at lines 159-166. Update `python/stilyagi/_stilyagi_rs.pyi` with the
new signatures.

**W4. Generalized discovery.** Rewrite `python/stilyagi/discovery.py`:

- Rename `discover_markdown_files` to `discover_files` and update `__all__`, the
  module docstring, and the doctests.
- Add `syntax: model.Syntax` to `DiscoveredFile`.
- Replace `_MARKDOWN_SUFFIXES` with a lazily built mapping derived from the
  bridge, following the `functools.cache` plus module-lock pattern already used
  in `python/stilyagi/engine/extraction.py`. Extend
  `_reset_extraction_state_for_tests` to clear it, so tests that patch the
  bridge behave.
- Add a parity check alongside `_validate_syntax_vocab_once`: every syntax name
  returned by `default_discovery_extensions()` must be a member of
  `model.Syntax`, failing fast with a `RuntimeError` if the vocabularies drift.
- Replace `_is_markdown_file` with `_syntax_for_path`, matching on
  `path.suffix.lower().removeprefix(".")` — the *final* suffix only, so
  `e.py.txt` correctly resolves to `.txt` and is skipped.
- Extend `_IGNORED_DIRECTORY_NAMES` with the entries listed in W4-red. Keep the
  existing six.

**W5. Per-file extractor selection and severity.** In `python/stilyagi/cli.py`:

- Add `syntax: model.Syntax` to `CheckInput` and populate it from
  `DiscoveredFile` in `_discover_targets`.
- In `_stdin_check_input`, derive the syntax from `--stdin-filename`'s suffix,
  falling back to `model.Syntax.MARKDOWN` when no filename is supplied or the
  suffix is unregistered.
- Replace the hard-coded `model.Syntax.MARKDOWN` at line 280 with
  `check_input.syntax`.
- Change `compute_exit_code` to return `1` only when at least one diagnostic has
  `Severity.ERROR`, keeping the `had_error` exit-`2` path unchanged. Update its
  doctests.

In `python/stilyagi/engine/checker.py`, have `_map_one_error` choose
`Severity.WARNING` when the code is in the bridge-supplied anomaly set and
`Severity.ERROR` otherwise.

Also update the three stale strings: the `check` sub-parser help
(`cli_args.py:89`), the `targets` help (`cli_args.py:202`), and the
`engine/api.py:35` docstring.

Go/no-go: every Stage B test now passes, and the four gates are green.

### Stage D — tests, documentation, and cleanup

**W6.** Complete the test matrix. Beyond the Stage B red tests:

- **Property (Python).** Extend `tests/test_discovery_properties.py` with a
  `hypothesis` test generating mixed trees of `.md`, `.py`, `.rs`, and unrelated
  extensions, asserting three invariants: the discovered set equals the set of
  generated files whose final suffix is registered; ordering is total by
  resolved path and **independent of the order targets are supplied**; and each
  discovered file's `syntax` equals the table's mapping for its suffix.
- **Snapshot.** Add a `syrupy` snapshot of the text and JSON renderings of a
  fixed mixed-source run, using `JSONSnapshotExtension` in the style of
  `tests/test_renderers.py`. Normalize paths to the tree root before snapshotting
  so the snapshot is not machine-specific. Pair it with direct semantic
  assertions rather than relying on the snapshot alone. Add an `insta` snapshot
  on the Rust side only if the extension table gains a rendered form; if it does
  not, say so here rather than adding a snapshot for its own sake.
- **End-to-end.** Extend `tests/test_cli_e2e.py` with a real subprocess run over
  a mixed tree, asserting exit code and that all three extensions appear in the
  output.
- **Performance.** Time `stilyagi check .` on this repository before and after,
  record both figures in `Artefacts and notes`, and compare against the
  tolerance. This is a recorded measurement, not a gate.

**W7.** Documentation, in this order:

1. **ADR 008** at `docs/adr-008-v1-discovery-defaults.md`, following the
   template in [documentation style guide](../documentation-style-guide.md)
   lines 414-491 — the sectioned MADR-style structure every existing ADR uses,
   not a one-line Y-Statement. It records D1 through D6, the known limitation
   from D2, and the post-v1.0 candidate table.
2. **`docs/stilyagi-design.md` §7.3.** First apply S4's conclusion: rewrite the
   "Weaknesses and ambiguities" bullet at lines 1008-1009 so it records that the
   RFC *did* over-claim file types and was trimmed by `787526e`, rather than
   asserting in the present tense that it still does. Then add the post-v1.0
   file-type target table immediately after the "Recommended revisions" list
   (after line 1021) and before "Compatibility risks" (line 1023), with a
   caption below it per the style guide, and a footnote reference to ADR 008.
3. **`docs/users-guide.md` §3.** Replace the forward-looking sentence at lines
   253-256 and the "currently analyses Markdown files only" claim at line 261
   with the delivered behaviour: the discovered extension set, the pruned
   directory names, the fact that files with no registered extractor are
   skipped, the warning-versus-error distinction and its effect on exit codes,
   and the absence of `include` / `exclude` configuration in v1.
4. **`docs/developers-guide.md`.** Add `### 4.3 Adding a language extractor` to
   §4, beside the existing per-language comparison table at lines 680-691,
   documenting the four coordinated edits a new language needs: the
   `ExtractSyntax` variant, the `DEFAULT_DISCOVERY_EXTENSIONS` entry, the
   `model.Syntax` member, and any new IR error codes plus their classification.
   Update §2b "Discovery" (lines 374-396) for the rename and the new syntax
   field, and §3's syntax-scope bullets (lines 494-501).
5. **`docs/contents.md`.** Add the ADR 008 entry under
   `## Architecture decision records (ADRs)` after the ADR 007 entry, matching
   the existing nested-bullet pattern.

The post-v1.0 target table to add to design §7.3 — the "documented as post-v1.0
targets" requirement of roadmap item 3.2.1. Admission to v1 requires a
maintained tree-sitter grammar, a documented doc-comment convention, and an
unambiguous file-type discriminator:

| Target | Extensions | Documentation convention | Grammar | Principal admission risk |
| --- | --- | --- | --- | --- |
| Go | `.go` | godoc comments preceding declarations | `tree-sitter-go` (official) | Association breaks on an intervening blank line; indentation is semantically significant |
| TypeScript, JavaScript | `.ts`, `.js` | JSDoc and TSDoc `/** */` | `tree-sitter-typescript`, `tree-sitter-javascript` (official) | `/**` must be distinguished from ordinary `/*` block comments |
| Zig | `.zig` | `///` item and `//!` container comments | `tree-sitter-zig` (community) | Exactly three slashes; four or more are ordinary comments |
| Mojo | `.mojo`, `.🔥` | Python-style docstrings in Markdown | `tree-sitter-mojo` (community fork of the Python grammar) | Grammar is unofficial; field docstrings follow rather than precede declarations |
| Swift | `.swift` | DocC CommonMark comments | `tree-sitter-swift` (community) | Special fields are parsed after Markdown, so field extraction is two-pass |
| Java | `.java` | Javadoc `/** */` | `tree-sitter-java` (official), `tree-sitter-javadoc` for bodies | Javadoc bodies admit raw HTML |
| Nim | `.nim` | `##` comments in reStructuredText or Markdown | `tree-sitter-nim` (community) | Only exported symbols are documented; indentation is derived from the first non-whitespace character |
| C, C++ (Doxygen) | `.c`, `.h`, `.cc`, `.hh`, `.cpp`, `.hpp`, `.cxx`, `.hxx` | Doxygen, in Javadoc, Qt, `///`, or `//!` style | `tree-sitter-c`, `tree-sitter-cpp`, `tree-sitter-doxygen` for bodies | Four comment styles plus trailing-member markers; behaviour depends on Doxygen configuration flags |
| Ansible playbooks | `.yml` | `name` and `description` keys; module `DOCUMENTATION` blocks | `tree-sitter-yaml` (generic) | No reliable discriminator; `ansible-lint` uses structural heuristics such as a top-level list carrying `hosts` or `import_playbook` |
| GitHub Actions workflows | `.yml` | Workflow, job, and step `name`; action `description` | `tree-sitter-yaml` (generic) | Discriminated only by the `.github/workflows/` path, as `actionlint` does |
| Rego | `.rego` | `# METADATA` YAML annotation blocks | `tree-sitter-rego` (community) | Metadata must begin at column 1 and be terminated by a blank line |
| Terraform | `.tf` | `description` arguments on variables and outputs | `tree-sitter-hcl` (community) | No doc-comment convention as such; prose lives in string arguments |
| MDX | `.mdx` | Markdown with embedded JSX | — | Preview-only per RFC 0003 §7; not a stable v1 promise |
| Python stubs | `.pyi` | Python docstrings | `tree-sitter-python` (official) | Stub files frequently carry no docstrings; admitting them is a product decision, not a technical one |

*Table 2: post-v1.0 discovery targets, their documentation conventions, and
the principal risk each poses to extraction. None is a v1 commitment.*

Note the two `.yml` rows: both Ansible playbooks and GitHub Actions workflows
share an extension with arbitrary YAML, so neither can be admitted on extension
alone. Any future admission needs a discriminator — a path convention for
workflows, structural heuristics for playbooks — which is precisely why the
current design keeps discovery a pure extension lookup.

**W8.** Tick roadmap item 3.2.1 in `docs/roadmap.md` line 285, adding a
completion note linking this ExecPlan and ADR 008 in the style of the 3.1.1 and
3.1.2 entries (lines 239-242, 249-252). Complete
`Outcomes & retrospective` here.

Go/no-go: all six gates green, including `make markdownlint` and `make nixie`.

## Concrete steps

Run everything from the repository root. Per AGENTS.md, tee long output to a log
and review the log rather than the truncated terminal, and never run gates in
parallel.

Baseline (W0):

```bash
git branch --show-current   # expect 3-2-1-expand-discovery-defaults-to-md-py-and-rs
make check-fmt 2>&1 | tee "/tmp/check-fmt-$(get-project)-$(git branch --show-current).out"
make typecheck 2>&1 | tee "/tmp/typecheck-$(get-project)-$(git branch --show-current).out"
make lint      2>&1 | tee "/tmp/lint-$(get-project)-$(git branch --show-current).out"
make test      2>&1 | tee "/tmp/test-$(get-project)-$(git branch --show-current).out"
```

Focused red-stage runs (Stage B). Expect failures, and read the reason:

```bash
cargo test -p stilyagi-extract from_discovery_extension
uv run python -m pytest tests/test_discovery.py -v
uv run python -m pytest tests/test_check_files.py -v
uv run python -m pytest tests/test_package_skeleton_units.py -v -k discover
```

Expected red output for W1 is a compile error, not a test failure:

```plaintext
error[E0599]: no function or associated item named `from_discovery_extension` found for enum `ExtractSyntax`
```

Expected red output for W4:

```plaintext
E       AttributeError: module 'stilyagi.discovery' has no attribute 'discover_files'
```

After each work item, rebuild the extension so the Python side sees the new
bridge functions, then re-run the gates in order:

```bash
make build
make check-fmt && make typecheck && make lint && make test
```

Per the shared-cache guidance in AGENTS.md, do not create an isolated Cargo
cache; if another job holds the package-cache lock, wait for it. If a build
fails with `EAGAIN`, fork, or internal-compiler-error noise, retry with
`RUSTC_WRAPPER= CARGO_BUILD_JOBS=2`.

Documentation gates (W7, W8):

```bash
make fmt
make markdownlint 2>&1 | tee "/tmp/markdownlint-$(get-project)-$(git branch --show-current).out"
make nixie        2>&1 | tee "/tmp/nixie-$(get-project)-$(git branch --show-current).out"
```

The acceptance demonstration, run from the repository root once W5 is complete:

```bash
uv run stilyagi check . ; echo "exit=$?"
```

Expected, per the S3 dry run: 232 files processed, two error-severity
`suppression-blanket-forbidden` diagnostics from the two corpus fixtures, two
warning-severity extraction-anomaly diagnostics from
`tests/fixtures/corpus/rust/malformed/unclosed-item.rs`, and `exit=1` — driven
by the two errors, not by the warnings. Removing the two blanket-suppression
fixtures from the target set must yield `exit=0`:

```bash
uv run stilyagi check python/ crates/ docs/ ; echo "exit=$?"   # expect exit=0
```

After each milestone, and only once all four gates are green:

```bash
coderabbit review --agent
```

Clear every concern before starting the next work item. CodeRabbit must not be
used to catch what the deterministic gates already catch.

## Validation and acceptance

Acceptance is behavioural. Each item below names the observation, not the code.

1. **Mixed discovery.** In a tree containing `docs/guide.md`, `src/app.py`, and
   `src/lib.rs`, `stilyagi check .` processes all three, in that resolved-path
   order, and exits `0`. Before the change it processes only `docs/guide.md`.
2. **Per-file extractor selection.** The same run extracts `src/app.py` with
   `python_docstring` and `src/lib.rs` with `rust_doc_comment`. Verified by the
   BDD step "each processed path was extracted with its extension's syntax",
   which asserts against the recorded syntax rather than inferring it.
3. **Unregistered extensions are skipped, not errors.** A tree containing
   `notes.txt` and `data.json` alongside `README.md` processes only `README.md`
   and exits `0`.
4. **Final-suffix matching.** `tests/fixtures/corpus/python/malformed/
   unclosed-function.py.txt` is not discovered.
5. **Extraction anomalies do not fail the run.** A tree containing only
   malformed Rust exits `0` and reports a warning-severity diagnostic.
6. **Authored-directive violations do fail the run.** A tree containing a
   forbidden blanket suppression exits `1` with an error-severity diagnostic.
7. **Standard input follows `--stdin-filename`.**
   `stilyagi check - --stdin-filename src/lib.rs` extracts as
   `rust_doc_comment`.
8. **Determinism.** The `hypothesis` property test passes: discovery output is
   the same total order regardless of the order targets are supplied, and each
   resolved path appears exactly once.
9. **Table invariants.** The `const` assertions compile, and the `proptest`
   property passes for arbitrary input.
10. **Whole-repository acceptance.** The two `uv run stilyagi check` commands in
    `Concrete steps` produce the stated exit codes.

Red-green-refactor evidence to record in `Artefacts and notes`, per work item:
the red command and its failure output, the green command and its pass output,
and the gate sequence after the refactor step.

Quality criteria — what "done" means:

- **Tests:** `make test` passes, covering the Rust workspace suite (`nextest`
  where available, `cargo test` otherwise), Rust doctests, and `pytest`.
- **Formatting:** `make check-fmt` passes.
- **Typecheck:** `make typecheck` passes, including `ty check`.
- **Lint:** `make lint` passes — `ruff`, `interrogate` at 100% docstring
  coverage, `pylint`, `cargo doc`, `clippy` with `-D warnings`, and `whitaker`.
- **Markdown:** `make markdownlint` (including the `typos` en-GB-oxendict gate)
  and `make nixie` pass.
- **Review:** `coderabbit review --agent` reports no outstanding concerns at
  each milestone.

Known pre-existing condition: `make lint`'s `whitaker` step is reported red on
`main` because of `no_expect_outside_tests` findings on pre-existing `.expect()`
calls in test helpers. Confirm at W0 whether this still holds. If it does, it is
not a regression from this branch — record the baseline and do not attempt to
fix it here, but do not add new `.expect()` calls outside `#[cfg(test)]` either.

## Idempotence and recovery

Every step is re-runnable. `make build`, the gates, and the acceptance commands
are read-only with respect to source and may be repeated freely.

- Work items commit independently and in order, so `git revert` of a single
  commit is a clean rollback. W1 through W3 are additive to Rust and change no
  existing behaviour; reverting W4 or W5 alone restores Markdown-only checking.
- If a `syrupy` or `insta` snapshot needs updating, review the diff before
  accepting it. A snapshot that churns on a harmless change is too broad —
  narrow the captured output rather than re-accepting.
- If the bridge rebuild is skipped, Python will raise `AttributeError` on the
  new `_stilyagi_rs` functions. Run `make build` and retry.
- Nothing in this plan is destructive. No file is deleted; no fixture is
  rewritten; the corpus under `tests/fixtures/corpus/` is read-only to this work.

## Artefacts and notes

To be filled in as work proceeds. At minimum, record: the W0 baseline gate
transcript; the red and green transcripts for each work item; the before-and-
after wall-clock and file-count figures from W6; and the final acceptance
transcript of `uv run stilyagi check .`.

The planning-time dry run, retained as the baseline for the W6 comparison:

```plaintext
discovered counts: {'md': 64, 'py': 76, 'rs': 92} total 232
files producing IR errors: 3
```

## Interfaces and dependencies

These signatures must exist when the plan is complete. Names are prescriptive.

In `crates/stilyagi-extract/src/lib.rs`:

```rust
pub const DEFAULT_DISCOVERY_EXTENSIONS: [(&str, ExtractSyntax); 4];

impl ExtractSyntax {
    #[must_use]
    pub fn from_discovery_extension(extension: &str) -> Option<Self>;
}
```

In `crates/stilyagi-ir/src/diagnostics.rs`, re-exported from
`crates/stilyagi-ir/src/lib.rs`:

```rust
pub const EXTRACTION_ANOMALY_ERROR_CODES: [&str; 6];
pub const AUTHORED_DIRECTIVE_ERROR_CODES: [&str; 2];

#[must_use]
pub fn is_extraction_anomaly_code(code: &str) -> bool;
```

In `crates/stilyagi-pyext/src/lib.rs`, registered in the `_stilyagi_rs` module
and declared in `python/stilyagi/_stilyagi_rs.pyi`:

```python
def default_discovery_extensions() -> tuple[tuple[str, str], ...]: ...
def extraction_anomaly_error_codes() -> tuple[str, ...]: ...
```

In `python/stilyagi/discovery.py`:

```python
@dc.dataclass(frozen=True, slots=True)
class DiscoveredFile:
    reported_path: str
    resolved_path: pathlib.Path
    syntax: model.Syntax


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


def compute_exit_code(
    diagnostics_list: cabc.Sequence[diagnostics.Diagnostic],
    *,
    had_error: bool = False,
) -> int: ...
```

Libraries: no new runtime dependency (Constraint 2). Test-only use of `rstest`,
`rstest-bdd`, `insta`, and `proptest` on the Rust side, and `pytest`,
`pytest-bdd`, `syrupy`, and `hypothesis` on the Python side — all already
present. `kani` and `verus` are deliberately not used; see Decision Log D6.

## References

- [Stilyagi design](../stilyagi-design.md) §§3-4, 7.2, 7.3, 13
- [RFC 0002: Stilyagi Python rule API](../rfcs/0002-stilyagi-python-rule-api.md)
- [RFC 0003: Stilyagi CLI contract](../rfcs/0003-stilyagi-cli-contract.md)
  §§5-7, 12
- [Roadmap](../roadmap.md) §3.2
- [ExecPlan for roadmap 2.2.1](roadmap-2-2-1.md) — the `check` loop this plan
  extends
- [ExecPlan for roadmap 3.1.2](roadmap-3-1-2.md) — Rust doc-comment extraction,
  which deferred `*.rs` discovery to this item
- [ExecPlan for roadmap 3.1.3](roadmap-3-1-3.md) — cross-syntax suppression parsing
- [ADR 006](../adr-006-docstring-owner-metadata.md),
  [ADR 007](../adr-007-rust-doc-comment-owner-metadata.md)
- [Developers' guide](../developers-guide.md),
  [users' guide](../users-guide.md),
  [documentation style guide](../documentation-style-guide.md)
- Ruff file-discovery semantics, as prior art for the pruning list and the
  explicit-path rule.[^1]

[^1]: Ruff documents `include`, `extend-include`, `exclude`, `extend-exclude`,
    `respect-gitignore`, and `force-exclude`, and the rule that explicitly
    passed paths are analysed unless `force-exclude` is set. Its default
    exclusion list is the basis for the expanded pruning set in W4.
    <https://docs.astral.sh/ruff/settings/>

## Revision note

Round 1 (2026-08-16). Initial draft. Written from direct inspection of the
working tree, four executed probes against the built extension (recorded as S2,
S3, and S5), reconnaissance across the design documents and RFCs, and external
research into documentation conventions and tree-sitter grammar availability for
the post-v1.0 targets. The plan is larger than the roadmap line suggests because
probing revealed that expanding discovery alone would make `stilyagi check .`
fail on any repository containing a file the pinned grammars cannot fully parse
(S2), which would falsify the roadmap's own success criterion. Work item W5
addresses that; Decision Log D4 records the reasoning and flags it as the point
most open to reviewer challenge.
