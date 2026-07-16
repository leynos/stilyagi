# Implement `stilyagi check` for Markdown files with nearest-config discovery

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
`Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`, `Decision Log`,
and `Outcomes & Retrospective` must be kept up to date as work proceeds.

Status: COMPLETE

Approval gate: satisfied. This is planning round 6. Round 6 closes the two
fresh blocking defects from the saved re-review
([roadmap-2-2-1-review-round-1.md](roadmap-2-2-1-review-round-1.md) §Re-review):
the prescriptive-interface contradictions on `discover_markdown_files` (now a
single authoritative `list[DiscoveredFile]` return type carrying both the
resolved path and the command-line-relative POSIX reported path, replacing the
`list[pathlib.Path]` declaration and the "objects or pairs" menu) and on
`map_ir_errors` (the Interfaces entry now reads the two-argument
`map_ir_errors(document, reported_path)` the W4 body and
`tests/test_ir_error_adapter.py` pin), and corrects the stale
`crates/stilyagi-pyext/src/tests.rs:14`/`:140` citations to the real
`crates/stilyagi-pyext/src/tests/mod.rs:18`/`:144`. No work-item mechanism
changed. Round 5 corrects the
whole validation/gate story after re-verifying the worktree Makefile: the branch
Makefile has advanced since round 2, so `make all` now **chains** the commit
gates (`Makefile:38`) and `make release` (`Makefile:54`) is what builds the
wheel — reversing the round-2/round-3/round-4 claim that "`make all` runs no
gates". The deterministic commit gates are now stated as the four distinct
targets the workflow host re-runs, in order — `make check-fmt`, then
`make typecheck`, then `make lint`, then `make test` — with `make check-fmt`
(formatting) listed as its own gate rather than folded into `make lint`, per
AGENTS.md §"Rust specific guidance". No work item's mechanism changed; only the
validation commands and the `make all`/`make release` narrative. Round 4 closed
the two remaining blocking defects from the saved Round-1 adversarial review
([roadmap-2-2-1-review-round-1.md](roadmap-2-2-1-review-round-1.md)) that earlier
rounds left open — defect 2 (the incomplete enumeration of skeleton tests broken
by the W4 diagnostic/renderer reshape, which would leave a red gate at the W4
commit) and defect 3 (the mischaracterised, non-hermetic `cli.main()` snapshot
test and its stored artefact) — and landed the review's six advisories (file
failure modes, `Document.ir is None`, the JSON `path` form, the `sarif` error
message, the fate of `NodeRef`/`Fix`, and `--config` inline-vs-path
disambiguation). See the Revision note. (Round 1 decomposed the task; round 2
resolved review defect 1 — the `make all` gate claim — and review defect 4 — the
strict config schema that rejected the RFC 0003 §6 baseline; round 3 resolved the
unimplementable exit-`1` path and the mis-applied cross-syntax snapshot claim.)

## Purpose / big picture

Roadmap item 2.2.1 (see [docs/roadmap.md](../roadmap.md) §2.2) delivers the
first user-facing command of the Markdown vertical slice: `stilyagi check`. It
answers whether the v1 command-line interface (CLI) contract is already strong
enough to support normal repository linting for Markdown-only users, per
[Stilyagi design](../stilyagi-design.md) §7.3 and
[RFC 0003](../rfcs/0003-stilyagi-cli-contract.md).

After this change a maintainer can run, from a documentation repository:

- `stilyagi check .` and have Stilyagi discover every Markdown file beneath the
  current directory in a deterministic, path-sorted order, resolve the nearest
  supported configuration file for each target, extract each file through the
  existing Rust bridge, and print human-readable diagnostics;
- `stilyagi check docs/ --output-format json` and receive stable machine
  readable JavaScript Object Notation (JSON) diagnostics derived from one
  internal diagnostic model;
- `stilyagi check README.md --isolated` to bypass configuration discovery
  entirely; and
- observe the documented exit-code discipline: `0` when no violations remain,
  `1` when violations remain, and `2` on invalid configuration or CLI usage.

The observable success condition is behavioural, not "the code compiles". A
new behaviour-driven-development (BDD) feature drives `stilyagi check` over
temporary Markdown trees and asserts file ordering, config resolution, output
formats, and exit codes; snapshot tests pin the text and JSON renderings; and
an end-to-end test invokes the command as a subprocess.

### Scope boundary (what this slice deliberately excludes)

This slice implements the `check` *loop* and its supporting config, discovery,
diagnostic, and rendering machinery. It deliberately stops short of:

- Built-in lint rules. Those land in roadmap item 2.3.1. Until then the rule
  registry is an explicit, empty extension seam; `--select`/`--ignore` are
  parsed and threaded into the resolved configuration but match no rules yet.
- Safe-fix planning and the `--fix`, `--unsafe-fixes`, and `--diff` flags. Those
  land in roadmap item 2.2.2. This slice does not define them; passing one is a
  usage error (exit `2`).
- The `config`, `clean`, and `dump-ir` sub-commands and `--no-cache` cache
  behaviour beyond flag acceptance. Those land in roadmap item 2.2.3.
- Python and Rust discovery defaults (`*.py`, `*.rs`). Roadmap item 2.2.1
  explicitly limits discovery scope to Markdown; `*.py`/`*.rs` land in 3.2.1.
- Full `.gitignore` honouring. See the Decision Log; this is deferred to avoid
  introducing a new runtime dependency in this slice, which the RFC permits
  because gitignore handling is a SHOULD, not a SHALL.

Because no rules exist yet, there is no *content-driven* way to reach the
exit-`1` "violations remain" path in this slice. The real Markdown extractor
recovers malformed input to degraded regions and deliberately does **not**
populate the IR `errors[]` array for user content (verified below), so malformed
Markdown exits `0`, not `1`; the only extraction failure mode is an internal
parser panic or invalid span, which raises a Python exception and maps to
exit `2` ("internal error", RFC 0003 §12), not `1`. The exit-`1` path is
therefore a real *production* code path — the exit-code computation returns `1`
whenever the collected diagnostics list is non-empty — that this slice exercises
at the unit level by driving a synthetic `Diagnostic` through the empty
rule-registry seam, rather than by fabricating a malformed-Markdown extraction
that the real extractor never produces. The same diagnostics pipeline carries
real rule diagnostics in 2.3.1, at which point exit `1` becomes reachable from
content. See the Decision Log entry "exit-`1` is exercised synthetically" and
the "malformed Markdown recovers with empty `errors[]`" discovery.

## Context and orientation

The repository is a mixed Rust and Python project. Rust crates live under
`crates/`, the Python package lives under `python/stilyagi/`, Python tests live
under `tests/`, shared corpus fixtures live under `tests/fixtures/corpus/`, and
BDD feature files live under `features/`. The developer workflow and quality
gates are described in [docs/developers-guide.md](../developers-guide.md) and
[AGENTS.md](../../AGENTS.md).

Key existing surfaces this plan builds on:

- `python/stilyagi/cli.py` currently defines `def main() -> int` that prints a
  "not implemented" message to stderr and returns `2`. This is a placeholder to
  replace. Two tests exercise it today and must be updated in lockstep:
  `tests/test_package_skeleton_units.py::test_cli_main_reports_placeholder_exit_code`
  (asserts `cli.main() == 2`) and `tests/test_round_trip_helpers.py` line 93
  (`exit_code = cli.main()`).
- `python/stilyagi/config.py` defines the frozen dataclass `StilyagiConfig`
  (currently only `cache_dir`) and `InvalidCacheDirError`. Both are imported by
  `tests/test_package_skeleton_units.py`. Any refactor must keep
  `from stilyagi import config`, `config.StilyagiConfig`, and
  `config.InvalidCacheDirError` importable.
- `python/stilyagi/engine/api.py` exposes
  `extract_document(source: str, syntax: model.Syntax) -> model.Document`, which
  delegates to `python/stilyagi/engine/extraction.py`. The returned
  `model.Document` carries `.syntax`, `.regions`, and `.ir` (the canonical
  intermediate-representation (IR) mapping, or `None`).
- The IR envelope (`crates/stilyagi-ir/src/document.rs`) carries `line_index`,
  `regions`, `suppressions`, and `errors` (`IrError`). The `"errors"` array is
  always present in the JSON shape but, for Markdown user content in this slice,
  is always **empty**. Verified against the real Markdown extractor, not a
  cross-syntax analogue: the golden snapshot
  `crates/stilyagi-markdown/src/snapshots/stilyagi_markdown__tests__frontmatter.snap`
  line 192 shows `"errors": []`, and the malformed-fixture test
  `crates/stilyagi-markdown/src/tests/malformed.rs:47-49` asserts
  `document.errors.is_empty()` for all three malformed fixtures (unclosed-table,
  unbalanced-emphasis, broken-reference-link) with the comment that "non-fatal
  error emission belong[s] to roadmap item 2.1.3, so parser recovery must not
  fabricate IR errors in this slice". Python extraction is out of scope here
  (`model.Syntax.MARKDOWN` only; Python defers to 3.2.1), so no Python snapshot
  is evidence for the Markdown path and none is relied upon. Consequence: the IR
  `errors[]` → diagnostic adapter this slice ships is a forward-looking seam for
  2.1.3, pinned against a synthetically constructed IR mapping and against the
  real extractor's *empty* Markdown `errors[]`; it is not a content-reachable
  exit-`1` trigger today.
- `python/stilyagi/diagnostics.py` holds placeholder `NodeRef`, `Fix`, and
  `Diagnostic` dataclasses. The current `Diagnostic(code, message, span=NodeRef)`
  shape is pinned by
  `tests/test_package_skeleton_units.py::test_diagnostic_preserves_code_and_message`
  (line 92, verified this worktree). W4 reshapes `Diagnostic` (adds a required
  `path`, replaces `span` with resolved `line`/`column`), so that test **must**
  be rewritten in the same commit or the W4 gate stays red. See W4 for the
  decided fate of `NodeRef` and `Fix`.
- `python/stilyagi/engine/renderers.py` holds a placeholder `RendererRegistry`
  whose no-argument construction and `default_format == "text"` are pinned by
  `tests/test_package_skeleton_units.py::test_engine_skeleton_dataclasses_preserve_their_fields`
  (line 115, verified this worktree). W4 rewrites `RendererRegistry` to render
  diagnostics, so that assertion **must** be updated in lockstep with the W4
  commit.
- Two tests call `cli.main()` with **no arguments** and would, under a default
  target of `.`, recurse the repository working directory the test runs in —
  slow, current-working-directory-coupled, and non-deterministic:
  `tests/test_package_skeleton_units.py::test_cli_main_reports_placeholder_exit_code`
  (asserts `== 2`) and
  `tests/test_round_trip_helpers.py::test_cli_placeholder_output_matches_snapshot`
  (a `syrupy` snapshot of `{exit_code, stdout, stderr}` stored at
  `tests/__snapshots__/test_round_trip_helpers/test_cli_placeholder_output_matches_snapshot.json`,
  verified present this worktree). W5 redefines **both** to pass an explicit
  `argv` against a `tmp_path` tree (hermetic; never the repo CWD) and accounts for
  the stored snapshot artefact (regenerate for the new hermetic output, or delete
  it and drop `test_cli_placeholder_output_matches_snapshot`, replacing its
  coverage with the W5 `text`/`json` renderer snapshots). This closes Round-1
  review defect 3.
- `python/stilyagi/rules/` and `python/stilyagi/rules/builtin/` are namespace
  packages with no rules yet.
- `python/stilyagi/plugins.py` defines the entry-point group names but no loader.

Load-bearing external-behaviour facts verified in this worktree (not assumed):

- The Rust bridge `extract_document` accepts exactly `(source, syntax)` as
  positional arguments and rejects unexpected keyword arguments. Verified in
  `crates/stilyagi-pyext/src/tests/mod.rs:18`
  (`bridge_extract_document(source, syntax)`) and the negative test
  `extract_document_function_rejects_unexpected_kwargs`
  (`crates/stilyagi-pyext/src/tests/mod.rs:144`). Consequence: **the extractor is
  path-agnostic**. It does not receive the on-disk path, so the `check` command
  must own the mapping from a discovered file path to the diagnostics it
  produces; the IR `source.path` field must not be relied upon to carry the
  caller's path.
- `model.Syntax` is a closed `StrEnum` with `MARKDOWN = "markdown"`
  (`python/stilyagi/model/document.py`). Markdown is the only syntax this slice
  targets.
- TOML parsing is available from the standard library via `tomllib` (Python
  3.11+; the project targets 3.14 per `pyproject.toml` `requires-python`). No
  new dependency is needed to read configuration files.
- `argparse` from the standard library is sufficient for the sub-command and
  option surface this slice needs. No CLI framework dependency is added. See
  Decision Log.

## Constraints

Hard invariants that must hold throughout implementation. Violation requires
escalation, not a workaround.

- Work only inside this worktree
  (`/home/leynos/Projects/stilyagi.worktrees/roadmap-2-2-1`).
- Do not add any new runtime (non-dev) dependency. The project currently
  declares zero `[project.dependencies]`; keep it that way. Use `tomllib` and
  `argparse` from the standard library. If a work item appears to require a new
  runtime dependency (for example, a gitignore matcher such as `pathspec`),
  stop and escalate.
- Preserve public import paths already relied upon by tests:
  `from stilyagi import cli, config, diagnostics, engine, model, nlp, plugins,
  rules`, plus `config.StilyagiConfig`, `config.InvalidCacheDirError`, and
  `engine.extract_document`.
- Do not change the Rust extraction bridge signature or the IR schema. This
  slice is Python-only above the existing bridge.
- Keep discovery scope limited to Markdown (`*.md`, `*.markdown`). Do not add
  `*.py`/`*.rs` discovery (roadmap 2.2.1 constraint; that is 3.2.1).
- Do not implement fixes (`--fix`, `--diff`, `--unsafe-fixes`); those are
  roadmap 2.2.2.
- No single code file may exceed 400 lines (AGENTS.md §Code style). Split by
  feature into sibling modules or a package.
- All prose, comments, docstrings, and commit messages use en-GB Oxford
  spelling ("-ize"/"-yse"/"-our"), per AGENTS.md and the `en-gb-oxendict` skill.
- Follow Red-Green-Refactor: add the failing test first for each behaviour.

## Tolerances (exception triggers)

- Scope: if the implementation of any single work item requires net changes to
  more than 8 files or more than 500 net lines, stop and escalate.
- Interface: if delivering a work item requires changing the Rust bridge
  signature or the IR JSON schema, stop and escalate.
- Dependencies: if any work item requires a new runtime dependency, stop and
  escalate (see Constraints).
- Iterations: if a focused test still fails after 5 fix attempts, stop and
  escalate.
- Ambiguity: if the config-precedence rules, exit-code mapping, or file-ordering
  rule admit two materially different interpretations not resolved by RFC 0003
  or the design doc, stop and present options.

## Risks

- Risk: Existing skeleton tests (`test_cli_main_reports_placeholder_exit_code`,
  `test_round_trip_helpers.py`) assume `cli.main()` returns `2` with no args.
  Severity: medium. Likelihood: high. Mitigation: update those tests as part of
  W5, changing `main()` to accept an explicit `argv` and giving no-arg
  invocation a defined meaning (default target `.`); make the change in the same
  commit as the CLI rewrite so no gate is left red.
- Risk: The W4 reshape of `Diagnostic` (add `path`, replace `span`) and rewrite
  of `RendererRegistry` (render diagnostics, drop the `default_format`-only
  placeholder) break two existing skeleton assertions —
  `test_package_skeleton_units.py::test_diagnostic_preserves_code_and_message`
  (line 92) and `::test_engine_skeleton_dataclasses_preserve_their_fields`
  (line 115). Severity: medium. Likelihood: high. Mitigation: W4 enumerates both
  as in-lockstep edits in the same commit as the reshape, and decides the fate of
  `NodeRef`/`Fix` and of `RendererRegistry`'s no-arg construction explicitly, so
  the W4 gate is never left red. This closes Round-1 review defect 2.
- Risk: Malformed on-disk inputs (non-UTF-8 bytes, permission-denied files,
  symlink cycles during recursion) could crash discovery or extraction rather
  than producing a clean exit code. Severity: medium. Likelihood: medium.
  Mitigation: W3 walks directories without following symlinked directories (so a
  symlink cycle cannot loop) and W5 wraps per-file read/decode in a typed handler
  that maps `UnicodeDecodeError`, `PermissionError`, `FileNotFoundError`, and
  `IsADirectoryError` to an actionable stderr message and exit `2` ("internal
  error"/invalid usage, RFC 0003 §12) — never `1`. Tests cover each mode.
- Risk: `.gitignore` honouring is a documented SHOULD but has no dependency-free
  implementation. Severity: low. Likelihood: high. Mitigation: deferred with an
  explicit Decision Log entry and a logged notice; discovery still skips VCS and
  build noise directories and restricts discovery to the fixed Markdown
  extension set (`.md`, `.markdown`) owned by W3. Escalate only
  if the user requires full gitignore semantics in this slice.
- Risk: The extractor is path-agnostic, so span→line/column mapping for
  diagnostics must use the IR `line_index` rather than any bridge-provided path.
  Severity: low. Likelihood: medium. Mitigation: W4 maps offsets to line/column
  using `document.ir["line_index"]`; a property test asserts the mapping is
  monotonic and within bounds.
- Risk: `maturin` is the build backend; adding `[project.scripts]` must not
  break the wheel build. Severity: low. Likelihood: low. Mitigation: W5 adds the
  entry point and validates the wheel/console script with `make release` (which
  builds and smoke-tests the release wheel via `python -m stilyagi.smoke`; it
  runs no lint/typecheck/test gates), and validates behaviour with a subprocess
  e2e test through `python -m stilyagi` under `make test`.

## Progress

- [x] W1 — Configuration schema and same-directory TOML loading.
  - Implemented the `python/stilyagi/config/` package split with schema
    dataclasses, same-directory TOML loading, and preserved raw reserved
    values.
  - Added focused schema and property tests, then refreshed the wheel snapshot
    after the package layout changed.
- [x] W2 — Nearest-config discovery, `extend` chain, CLI overrides, `--isolated`.
- [x] W3 — Deterministic Markdown file discovery.
- [x] W4 — Diagnostic model and `text`/`json` renderers; IR-error adapter seam.
- [x] W5 — `check` command, argparse CLI, exit codes, console entry point.
  - Added the missing file-failure regression surface in `tests/test_check_files.py`
    for non-UTF-8, permission-denied, removed-mid-run, directory, and extractor
    failure paths, and added a real malformed-Markdown CLI acceptance case so the
    documented exit-`0` recovery path is exercised end-to-end.
  - Restored the named W5 coverage surface that the round-6 plan called for:
    `tests/test_check_command.py` now owns the `main([...])` return-code and JSON
    renderer assertions, `tests/test_cli_e2e.py` exercises `python -m stilyagi
    check` through the subprocess boundary, and
    `features/stilyagi_check_command.feature` now contains the two missing
    behavioural scenarios for invalid configuration and isolated-mode config
    skipping.
- [x] W6 — Standard-input support (`-` and `--stdin-filename`).
- [x] W7 — Documentation and roadmap update.

## Surprises & discoveries

- Observation: The Rust extraction bridge takes only `(source, syntax)` and
  rejects extra kwargs. Evidence: `crates/stilyagi-pyext/src/tests/mod.rs:18`
  and `:144`. Impact: the CLI, not the extractor, owns file-path attribution for
  diagnostics; recorded as a Constraint and reflected in W4/W5.
- Observation: Malformed Markdown recovers to degraded regions and never
  populates IR `errors[]` in this slice; non-fatal error emission is roadmap
  2.1.3 work, not 2.2.1. Evidence: `crates/stilyagi-markdown/src/tests/malformed.rs:47-49`
  asserts `document.errors.is_empty()` for every malformed fixture, and the
  frontmatter snapshot line 192 shows `"errors": []`. Impact: the round-2 design
  (exit-`1` driven by extraction errors) was unimplementable — no malformed
  Markdown content can produce a diagnostic today. The plan now exercises the
  exit-`1` path synthetically through the empty rule-registry seam (see the
  Decision Log and the reworked W4/W5), and pins the IR-error adapter against a
  hand-built IR mapping plus the real extractor's empty Markdown `errors[]`.

- Observation: `firecrawl_scrape` required an interactive permission grant that
  the planning session could not satisfy, so external library docs were not
  fetched in this round. Evidence: the tool returned "requested permissions …
  but you haven't granted it yet". Impact: none on load-bearing choices — this
  slice adds no runtime library (CLI via stdlib `argparse`, TOML via stdlib
  `tomllib`), so no locked third-party API needs external verification. All
  load-bearing facts here are pinned to in-worktree source (`crates/…`,
  `python/…`, `pyproject.toml`, `Makefile`) or to in-repo contract docs, not to
  scraped web pages.

- Observation (W5): the new BDD steps under `tests/steps/` did not register
  reliably until `tests` became a real package in this worktree. Evidence: the
  feature collected but pytest-bdd reported missing step definitions until
  `tests/__init__.py` was added and the step module was loaded as a pytest
  plugin. Impact: keep the shared step module importable through the package
  path when extending the CLI scenario coverage.

- Observation (W5 fix round 2): the saved round-6 plan explicitly named six
  behavioural scenarios, a dedicated `tests/test_check_command.py`, and a
  dedicated `tests/test_cli_e2e.py`, but the worktree only retained four feature
  scenarios and scattered CLI assertions. Impact: this fix round restores the
  named surfaces rather than treating the dispersed coverage as an acceptable
  substitute, so the ExecPlan now matches the committed tree again.

- Observation (W6): stdin support now reads from `sys.stdin`, uses
  `--stdin-filename` for reported-path attribution and config resolution, and
  rejects mixed stdin/file targets with exit `2`. The gate run also surfaced a
  stale wheel snapshot, which was regenerated so the test suite reflects the
  current wheel layout.

- Observation (round 5): the worktree Makefile has advanced since round 2. `all`
  is now `all: ## Run commit gates` chaining `check-fmt`, `typecheck`, `lint`,
  `test`, `markdownlint`, and `nixie` (`Makefile:38-44`), and `release:
  release-artifact smoke-release` (`Makefile:54`) is what builds/smoke-tests the
  wheel — the opposite of the round-2 `all: release` finding this plan carried
  forward. AGENTS.md §"Rust specific guidance" (lines 156-186) confirms the four
  gate targets are distinct and that `make check-fmt` (not `make lint`) performs
  the formatting check. Impact: the validation commands, the Decision Log gate
  entry, both W-item and whole-change acceptance lines, and the wheel-build
  reference were corrected to the four deterministic gates in host order and to
  `make release` for the wheel check. No work-item mechanism changed.

- Observation (round 5): `git` (log/status/diff) and `grep` via the shell were
  denied by the session's command-approval layer, so branch history could not be
  read through git in this planning session. Evidence: repeated "This command
  requires approval" on `git -C … log`. Impact: none on implementability —
  branch-local premises were re-verified by direct file inspection instead: the
  `check` command is still the placeholder `def main() -> int` returning `2`
  (`python/stilyagi/cli.py`), `config.py` is still a single module (not yet a
  package), no `features/stilyagi_check_command.feature` exists, and the skeleton
  test anchors (`test_diagnostic_preserves_code_and_message` line 92 using
  `NodeRef`; `test_engine_skeleton_dataclasses_preserve_their_fields` line 115
  asserting `default_format == "text"`) are present as the plan describes. No
  roadmap-2.2.1 implementation is committed on this branch; the plan's premises
  hold.

- Observation (W3): Hypothesis reuses the same `tmp_path` fixture directory
  across examples, so the discovery property test clears its workspace subtree
  before each draw. Evidence: the first property run failed on a pre-existing
  `workspace/` directory until the test switched to an explicit cleanup step.
  Impact: the generated-path property stays hermetic without changing the
  implementation contract.

- Observation (W4): `interrogate` counts the new private helpers in
  `diagnostics_location.py`, `checker.py`, and `renderers.py`, so the helper
  functions needed docstrings to keep coverage at 100%. The wheel snapshot also
  changed intentionally to include `python/stilyagi/diagnostics_location.py` in
  the built artefact list.

- Observation (W1): `interrogate` counts the new private helpers in
  `python/stilyagi/config` and `tests`, so the W1 config surface needed
  docstrings to keep the repo at 100% coverage. The wheel snapshot also changed
  deliberately because the package split moved `config.py` into `config/`.

- Observation (W2): adding `python/stilyagi/config/resolve.py` changed the
  maturin wheel contents, so `tests/test_maturin_build.py::test_maturin_wheel_build_snapshot`
  needed a snapshot refresh after the new module landed.

## Decision log

- Decision: Discovery returns a `list[DiscoveredFile]`, where `DiscoveredFile`
  is a frozen dataclass with `reported_path: str` (command-line-relative POSIX)
  and `resolved_path: pathlib.Path`, rather than a bare `list[pathlib.Path]`.
  Rationale: W4/W5 need the resolved path for de-duplication and deterministic
  ordering and, independently, the command-line-relative POSIX reported path for
  diagnostic attribution and the pinned renderer `path` form. A single explicit
  element type removes the round-5 prescriptive contradiction between the
  Interfaces section and the W3/W5 bodies; `map_ir_errors(document,
  reported_path)` consumes `DiscoveredFile.reported_path`.
  Date/Author: 2026-07-06, planning agent.
- Decision: Use the standard-library `argparse` for the CLI rather than a
  third-party framework (Click, Typer, Cyclopts).
  Rationale: The project declares zero runtime dependencies and a Constraint
  forbids adding one. `argparse` supports sub-commands and the option surface
  this slice needs. Ruff's *contract* (command names, precedence, exit codes) is
  the model, not its Rust `clap` implementation.
  Date/Author: 2026-07-04, planning agent.
- Decision: Parse configuration with the standard-library `tomllib`.
  Rationale: Available since Python 3.11; project targets 3.14. No dependency
  needed. Date/Author: 2026-07-04, planning agent.
- Decision: Defer full `.gitignore` honouring to a later slice.
  Rationale: RFC 0003 §7 states Stilyagi SHOULD respect `.gitignore`; it is not
  a SHALL. A correct implementation needs a gitignore matcher (for example
  `pathspec`), which would be a new runtime dependency and breach a Constraint.
  Discovery still skips `.git` and obvious build directories and restricts to
  the fixed Markdown extension set (`.md`, `.markdown`); the RFC §6
  `respect-gitignore` key is accepted (and preserved) in config and its deferral
  is logged in verbose mode. Date/Author: 2026-07-04, planning agent.
- Decision: In this slice the exit-`1` "violations remain" path is exercised
  **synthetically** at the unit level, not by real Markdown content.
  Rationale: The round-2 design assumed malformed Markdown yields recoverable
  `IrError` entries that surface as diagnostics. The real Markdown extractor
  contradicts this — `crates/stilyagi-markdown/src/tests/malformed.rs:47-49`
  asserts `document.errors.is_empty()` for every malformed fixture, and non-fatal
  error emission is explicitly roadmap 2.1.3 work (2.2.1 requires only 2.1.1 and
  1.2.3, so it cannot depend on 2.1.3). With zero rules and empty `errors[]`,
  no CLI content can reach exit `1`; an internal parser panic raises and maps to
  exit `2` ("internal error", RFC 0003 §12), not `1`. The exit-code computation
  is nonetheless real production code, so W5 tests it two ways: (1) a direct unit
  test that `compute_exit_code([<one synthetic Diagnostic>])` returns `1`; and
  (2) a `run_check` unit test that monkeypatches the empty rule-registry seam
  `run_rules` to return one synthetic `Diagnostic`, asserting the whole compose
  path returns `1` and renders it. Real malformed Markdown is pinned to exit `0`
  (recovers cleanly, no diagnostics). This exercises the genuine exit-`1` code
  path without fabricating an extraction behaviour the extractor never produces;
  when 2.3.1 adds rules, exit `1` becomes reachable from content through the same
  seam. The reviewer's option (b) — depend on 2.1.3 and reorder — is rejected
  because it would change the roadmap's stated dependencies for 2.2.1.
  Date/Author: 2026-07-04 (round 3), planning agent.
- Decision: The IR `errors[]` → `Diagnostic` adapter is retained as a
  forward-looking seam for 2.1.3, but pinned honestly.
  Rationale: The adapter (`map_ir_errors`) is small and lets 2.1.3 light up the
  violations path without reworking the checker. In this slice it is tested (1)
  in isolation against a hand-built IR mapping carrying a synthetic `errors[]`
  entry — asserting the mapping shape — and (2) against the **real** Markdown
  extractor: extracting a real malformed fixture yields `ir["errors"] == []` and
  therefore zero diagnostics. No Python snapshot or other cross-syntax evidence
  is used to justify Markdown behaviour. Date/Author: 2026-07-04 (round 3).
- Decision: The config schema accepts the full RFC 0003 §6 v1 baseline;
  reserved keys are preserved, not rejected.
  Rationale: RFC 0003 §6 documents a recommended baseline containing
  `line-length`, `[lint] fixable`/`unfixable`, `[lint.per-file-ignores]`,
  `[nlp]`, and `[rule.<CODE>]`. A repo copying that baseline (or already carrying
  a matching `[tool.stilyagi]` block) must not fail with exit `2`, or the plan
  would break the established config contract and CI parity. W1 therefore models
  the whole §6 key set: keys the slice consumes drive behaviour now; keys
  reserved for 2.2.2/2.3.1/later NLP slices are accepted, type-checked for basic
  shape, and preserved on the resolved config untouched. `InvalidConfigError` is
  raised only for keys outside the §6 contract entirely. TOML kebab-case keys are
  mapped to snake-case fields by an explicit key map. The round-1 invented
  `[lint] extend-select` and `[discovery] include` keys are removed
  (`--extend-select` is a CLI flag per §§3.1/8; discovery scope is a fixed
  Markdown extension set, not a schema key). Date/Author: 2026-07-04 (round 2).
- Decision: The deterministic commit gates are `make check-fmt`, then
  `make typecheck`, then `make lint`, then `make test`; `make release` is run
  separately only as a wheel/console build-integrity check.
  Rationale (superseded round 5): the round-2 claim that "`make all` resolves to
  `all: release` and runs no gates" was pinned to the then-current `origin/main`
  Makefile. On the current worktree branch the Makefile has advanced —
  `all: ## Run commit gates` (`Makefile:38`) chains `check-fmt`, `typecheck`,
  `lint`, `test`, `markdownlint`, and `nixie`, and `release: release-artifact
  smoke-release` (`Makefile:54`) is what builds and smoke-tests the wheel.
  AGENTS.md §"Rust specific guidance" (lines 156-186) is authoritative: the four
  gate targets are **distinct**, and `make check-fmt` (not `make lint`) runs the
  formatting check (`ruff format --check` + `cargo fmt --check`). Formatting is
  therefore listed as its own gate, ahead of typecheck/lint/test, matching the
  order the workflow host re-runs. The behavioural acceptance (BDD, unit,
  property, snapshot, e2e) runs under `make test`; `ty check` under
  `make typecheck`; ruff/pylint/clippy/Whitaker under `make lint`. Date/Author:
  2026-07-04 (round 2); corrected 2026-07-06 (round 5), planning agent.
- Decision: Convert `python/stilyagi/config.py` into a `python/stilyagi/config/`
  package that re-exports `StilyagiConfig` and `InvalidCacheDirError` from its
  `__init__`, keeping `from stilyagi import config` and its attributes stable.
  Rationale: The full config surface (schema, discovery, resolution) would
  exceed the 400-line file limit in one module. Date/Author: 2026-07-04.
- Decision (round 4): Retire the placeholder `NodeRef` diagnostic span and the
  `Fix` placeholder when reshaping `Diagnostic`; keep `Diagnostic` the single
  internal model with `path`/`code`/`message`/`severity`/`line`/`column` and a
  `fix` field left `None` this slice.
  Rationale: `NodeRef(kind, text)` carries no source position and cannot express
  the `path:line:col` the renderers need; keeping it would create two competing
  span notions. `Fix` is unused until roadmap 2.2.2 and is re-introduced there
  with the real edit model (design §"Fix and edit model"). W4 removes both from
  `diagnostics.py` and rewrites
  `test_diagnostic_preserves_code_and_message` to construct the new `Diagnostic`
  (with a `path` and resolved location) rather than a `NodeRef` span. If any
  other module imports `NodeRef`/`Fix`, W4 sweeps them first (none do today:
  verified — only `tests/test_package_skeleton_units.py` references `NodeRef`).
  Date/Author: 2026-07-04 (round 4), planning agent. Closes review advisory
  "fate of `NodeRef`/`Fix`".
- Decision (round 4): `RendererRegistry` keeps a no-argument constructor and a
  `default_format` attribute (default `"text"`) in addition to gaining
  `render(diagnostics, output_format)`.
  Rationale: Preserving the no-arg construction and `default_format` keeps
  `test_engine_skeleton_dataclasses_preserve_their_fields` meaningful (updated,
  not deleted) and matches the design's "default is text" contract (RFC 0003 §11).
  W4 updates that test to also assert the new `render` behaviour. Date/Author:
  2026-07-04 (round 4). Closes part of review defect 2.
- Decision (round 4): The user-facing `path` in both `text` and `json` output is
  the target path **as supplied on the command line, normalized to POSIX
  separators**, not an absolute or `resolve()`d path. For discovered files it is
  the path relative to the invocation directory (the join of the target argument
  and the walk-relative sub-path); for an explicitly named file it is that
  argument verbatim (POSIX-normalized); for stdin it is the `--stdin-filename`
  value or `<stdin>`.
  Rationale: Absolute paths churn snapshots and leak the runner's home directory;
  CWD-relative POSIX paths are stable, reproducible across machines, and match how
  Ruff reports. Internally, discovery still de-duplicates and orders by the
  resolved path (W3), but the *reported* path is the CWD-relative form. Tests pin
  this form directly (not only via snapshot redaction), closing review advisory
  "pin the JSON `path` form". Date/Author: 2026-07-04 (round 4).
- Decision (round 4): `--output-format` accepts only `text` and `json` via
  `argparse` `choices`; `sarif` (named v1 in RFC 0003 §11) is deferred. When a
  user passes `--output-format sarif`, argparse's `choices` error is augmented by
  a custom message stating that `sarif` is planned but not yet available in this
  slice, so the rejection is explicit rather than a bare "invalid choice".
  Rationale: Promising an unimplemented format is worse than an honest, signposted
  deferral; roadmap 2.2.1 requires only text/json. The deferral is recorded in the
  W7 user guide. Date/Author: 2026-07-04 (round 4). Closes review advisory
  "`sarif` rejected by choices".
- Decision (round 4): A single `--config VALUE` is disambiguated as an **inline
  override** when `VALUE` contains an `=` and does not name an existing file;
  otherwise it is treated as a **config file path** (which must exist, or exit
  `2`). Multiple `--config` values compose in the RFC 0003 §5 precedence order
  (inline `"key = value"` overrides rank above an explicitly named file).
  Rationale: RFC §5 lists inline overrides and explicit file paths as distinct
  precedence tiers but shares one flag spelling; the `=`-plus-not-a-file
  heuristic is unambiguous for the realistic inputs and is the same rule Ruff
  uses. Tests in W2 pin both interpretations and the "file must exist" error.
  Date/Author:
  2026-07-04 (round 4). Closes review advisory "`--config` disambiguation".
- Decision (round 4): Every consumer of `document.ir` guards `ir is None`.
  `map_ir_errors` returns `[]` when `document.ir is None` or lacks an `errors`
  array; the offset→location helper falls back to `line=1, column=1` when no
  `line_index` is available. Rationale: `Document.ir` is typed `Mapping | None`
  (`python/stilyagi/model/document.py`); a `None` IR must degrade gracefully, not
  raise. Tests cover the `None` path. Date/Author: 2026-07-04 (round 4). Closes
  review advisory "`Document.ir` is `Mapping | None`".
- Decision (round 4): Per-file I/O and decode failures map to exit `2`.
  Rationale: The design's exit-code contract (RFC 0003 §12) reserves `2` for
  invalid usage and internal error; a file that cannot be read or UTF-8 decoded
  is an operational failure, not a lint violation, so it must not silently
  become exit `0` nor be miscounted as an exit-`1` violation. W5 maps
  `UnicodeDecodeError`/`PermissionError`/`FileNotFoundError`/`IsADirectoryError`
  to an actionable stderr message and exit `2`; W3 does not follow symlinked
  directories, so recursion cannot loop. Date/Author: 2026-07-04 (round 4). Closes
  review advisory "file failure modes unspecified".

## Outcomes & retrospective

Completed the documentation pass for the Markdown `check` slice. The user
guide now explains `stilyagi check` for Markdown repositories, the developer
guide no longer describes it as future work, and the roadmap item is marked
complete. No implementation or test behaviour changed in this work item.

## Plan of work

The work proceeds bottom-up: configuration, then discovery, then the diagnostic
model and renderers, then the command that composes them, then stdin, then
documentation. Each work item is independently committable and must pass the
commit gates before the next begins. Each ends with its own validation.

### W1 — Configuration schema and same-directory TOML loading

Documents to read first: [RFC 0003](../rfcs/0003-stilyagi-cli-contract.md)
§§4, 6; [Stilyagi design](../stilyagi-design.md) §4 "Config file schema" and
§7.3; [ADR 003](../adr-003-v1-contract-scope.md) for v1 contract scope.
Skills to load: `python-router` (then the smaller skills it routes to, e.g.
`python-data-shapes`, `python-types-and-apis`, `python-errors-and-logging`),
`python-verification` then `hypothesis`, `leta` for navigation, `en-gb-oxendict`.

Convert `python/stilyagi/config.py` into a package `python/stilyagi/config/`:

- `python/stilyagi/config/__init__.py` re-exports the public surface:
  `StilyagiConfig`, `InvalidCacheDirError`, the new `InvalidConfigError`,
  `LintConfig`, `MarkdownExtractConfig`, and the
  loader/resolver functions added in W2. Preserve the existing `StilyagiConfig()`
  default and `InvalidCacheDirError` behaviour.
- `python/stilyagi/config/schema.py` defines frozen dataclasses for the **whole
  RFC 0003 §6 v1 baseline**, not a Markdown-only subset, so that a user copying
  the documented baseline (or a repo already carrying a matching
  `[tool.stilyagi]` block) parses cleanly instead of tripping exit `2`. Two
  tiers of keys, both accepted:
  - *Consumed this slice* (drive `check` behaviour now): top-level `cache-dir`,
    `respect-gitignore`, `plugins`; `[lint]` `select`, `ignore`, `preview`;
    `[extract.markdown]` `gfm`, `frontmatter`, `mdx`.
  - *Reserved for later slices* (accepted-and-preserved, validated for basic
    type shape but not acted upon here): top-level `line-length`; `[lint]`
    `fixable`, `unfixable`; `[lint.per-file-ignores]`; `[nlp]` (`model`,
    `sentence-provider`); and `[rule.<CODE>]` per-rule tables (for example
    `[rule.PUN201] min_items`). These land in 2.2.2/2.3.1/later NLP slices;
    rejecting them now would break the RFC's own §6 baseline and CI parity, so
    the loader retains them on the resolved config object (a `reserved: Mapping`
    field) and threads them through untouched.

  TOML keys in §6 are **kebab-case** (`cache-dir`, `respect-gitignore`,
  `line-length`, `sentence-provider`); the loader maps kebab-case TOML keys to
  the snake-case dataclass fields explicitly (a fixed key map, not a blanket
  `replace("-", "_")`), so the documented baseline binds to the schema. Rejection
  is **narrowed**: `InvalidConfigError` (subclass of `ValueError`, naming the
  file and offending key) is raised only for a key that is neither consumed nor
  in the reserved v1 set above — i.e. genuinely outside the RFC 0003 §6 contract.
  The invented `[lint] extend-select` key from the round-1 draft is **removed**:
  `--extend-select` is a CLI flag per RFC §§3.1/8, not a config key; likewise the
  invented `[discovery] include` table is **removed** from the schema. Discovery
  scope in this slice is a fixed Markdown extension set (`.md`, `.markdown`)
  owned by W3, not a user-configurable schema key, so no key absent from RFC
  §6/§7 is introduced. Keep each module under 400 lines.
- `python/stilyagi/config/load.py` implements `load_config_file(path)` reading a
  single TOML file with `tomllib`, applying the `[tool.stilyagi]` prefix for
  `pyproject.toml` and the bare prefix for `stilyagi.toml`/`.stilyagi.toml`, and
  `discover_same_directory_config(directory)` implementing RFC 0003 §4
  precedence (`.stilyagi.toml` > `stilyagi.toml` > `pyproject.toml`).

Tests (Red first):

- `tests/test_config_schema.py` (unit, pytest): default `StilyagiConfig()`
  round-trips; **the verbatim RFC 0003 §6 baseline config (including
  `line-length`, `[lint] fixable`/`unfixable`, `[lint.per-file-ignores]`,
  `[nlp]`, and `[rule.PUN201]`) parses without error and its consumed keys bind
  to the schema while its reserved keys are preserved** — this pins the
  accept-and-preserve contract that resolves round-1/round-2 blocking point 2
  and is copied directly from the RFC §6 code block so the two cannot drift; a
  key genuinely outside the §6 contract (for example `[lint] made-up-key`)
  raises `InvalidConfigError` naming the file/key; kebab-case TOML keys
  (`cache-dir`, `respect-gitignore`, `line-length`) bind to their snake-case
  dataclass fields; blank `cache_dir` still raises `InvalidCacheDirError`; each
  config-file kind parses under the correct prefix; same-directory precedence
  resolves in the documented order when several files coexist.
- `tests/test_config_schema_properties.py` (property, `hypothesis`): for any
  subset of the three recognized filenames present in a directory, the resolved
  file is always the highest-precedence present one (a total, deterministic
  choice). Use `python-verification` to confirm Hypothesis is the right adversary
  before writing.
- Update `tests/test_package_skeleton_units.py` where it constructs
  `StilyagiConfig` so imports and equality assertions still hold against the
  extended dataclass (add explicit defaults; keep `config.StilyagiConfig()`
  valid).

Acceptance: focused tests fail before implementation (Red) and pass after
(Green); `make check-fmt`, `make typecheck`, `make lint`, `make test` pass.

### W2 — Nearest-config discovery, `extend` chain, CLI overrides, `--isolated`

Documents to read first: [RFC 0003](../rfcs/0003-stilyagi-cli-contract.md) §5
(discovery and precedence); [Stilyagi design](../stilyagi-design.md) §4 "Config
file schema" (nearest-config, explicit `extend`, no user-level autoload).
Skills: `python-router` → `python-abstractions`, `python-errors-and-logging`;
`python-verification`; `leta`; `en-gb-oxendict`.

In `python/stilyagi/config/resolve.py` implement:

- `resolve_config_for_path(target, *, cli_overrides, explicit_config,
  isolated)`:
  1. if `isolated`, skip discovery and return defaults with CLI overrides
     applied;
  2. else discover the nearest supported config walking up the directory
     hierarchy from `target` (nearest wins; do **not** implicitly merge parent
     configs);
  3. follow any explicit `extend` chain (a list or string of paths), detecting
     cycles and raising `InvalidConfigError`;
  4. apply CLI precedence per RFC 0003 §5: dedicated flags, then
     `--config "key = value"` overrides, then an explicitly named
     `--config path`, then discovered nearest config, then defaults. A single
     `--config VALUE` is classified (round-4 Decision Log entry): if `VALUE`
     contains `=` and does not name an existing file it is an **inline override**
     (parsed as a one-line TOML fragment); otherwise it is a **file path** that
     must exist (missing file → `InvalidConfigError` → exit `2` in W5). Multiple
     `--config` values compose in the §5 order (inline above named file).
- A small in-run cache keyed by resolved directory so repeated lookups during a
  multi-file run are cheap and deterministic.

Tests (Red first):

- `tests/test_config_resolution.py` (unit): nearest-config wins over an
  ancestor; ancestors are **not** merged unless named by `extend`; `extend`
  chains compose in order and cycles raise; `--isolated` bypasses discovery;
  `--config path` overrides discovery; `--config "key = value"` overrides both;
  `--config VALUE` disambiguation is pinned in both directions — a value with `=`
  and no matching file is parsed as an inline override, a value naming an existing
  file loads that file, and a value naming a **non-existent** file raises the
  typed error (not silently treated as inline); a missing/invalid config raises
  the typed error (the exit-`2` path in W5).
- `tests/test_config_resolution.py::test_extend_precedence` asserts the exact
  precedence ladder using a temporary directory tree built by a fixture.

Acceptance: focused tests Red→Green; `make check-fmt`, `make typecheck`,
`make lint`, `make test` pass.

### W3 — Deterministic Markdown file discovery

Documents to read first: [RFC 0003](../rfcs/0003-stilyagi-cli-contract.md) §7
(file discovery); [Stilyagi design](../stilyagi-design.md) §4 system
requirements ("sort files by normalized path before execution") and §7.3.
Skills: `python-router` → `python-iterators-and-generators`,
`python-data-shapes`; `python-verification` → `hypothesis`; `leta`;
`en-gb-oxendict`.

Add `python/stilyagi/discovery.py`:

- A frozen dataclass `DiscoveredFile(reported_path: str, resolved_path:
  pathlib.Path)` is the single element type carried through discovery, rendering,
  and attribution: `reported_path` is the command-line-relative POSIX path used
  for diagnostic attribution and the pinned renderer `path` form (W4/W5), and
  `resolved_path` is the fully resolved filesystem path used for de-duplication
  and deterministic ordering. This is the one authoritative return element type;
  no variant returns bare `pathlib.Path`.
- `discover_markdown_files(targets, config) -> list[DiscoveredFile]`: for each
  target, if it is a file, include it when its suffix is `.md`/`.markdown`
  (explicitly named files are always analysed per RFC §7); if it is a directory,
  recurse, matching only the fixed Markdown extension set (`.md`/`.markdown`),
  skipping VCS/build noise directories (`.git`, `target`, `dist`, `build`,
  `.venv`, `node_modules`). Recursion **does not follow symlinked directories**,
  so a symlink cycle cannot loop the walk (review advisory "symlink cycles"); use
  `os.walk(..., followlinks=False)` or an equivalent `pathlib` walk that skips
  directory symlinks. The extension set is owned by W3, not a config key
  (RFC §6/§7 define no `[discovery]` table). De-duplicate by resolved path.
  Order internally by the resolved path so ordering is stable across platforms,
  but retain, for each file, the **command-line-relative POSIX path** used for
  reporting (per the round-4 Decision Log entry on the reported `path` form): the
  join of the target argument and the walk-relative sub-path, normalized to POSIX
  separators. `discover_markdown_files` returns a `list[DiscoveredFile]` whose
  elements each carry both `reported_path` and `resolved_path`, so W5 can report
  the stable relative form while de-duplicating/ordering on the resolved form.
  The list is sorted by `resolved_path`.
- Emit a verbose-mode log notice that `respect-gitignore` is accepted but not
  yet enforced in this slice (see Decision Log).

Tests (Red first):

- `tests/test_discovery.py` (unit): recursion finds nested `.md`; non-Markdown
  files are excluded; an explicitly named non-Markdown file passed directly is
  reported as an ignored/rejected target (documented behaviour, not silently
  linted); noise directories are skipped; ordering is the sorted normalized
  path order for a fixture tree; a symlinked directory that points back at an
  ancestor is **not** followed (no infinite recursion, no duplicate entries), and
  each returned file exposes both its resolved path and its command-line-relative
  POSIX reported path.
- `tests/test_discovery_properties.py` (property, `hypothesis`): for any set of
  generated relative Markdown paths materialized under a temporary root, the
  `resolved_path` values of the returned `list[DiscoveredFile]` equal the input
  set sorted by resolved path (total order, no duplicates, deterministic
  regardless of filesystem enumeration order), and each element's `reported_path`
  is the command-line-relative POSIX form of that file.

Acceptance: Red→Green; `make check-fmt`, `make typecheck`, `make lint`,
`make test` pass.

### W4 — Diagnostic model and `text`/`json` renderers; IR-error adapter seam

Documents to read first: [Stilyagi design](../stilyagi-design.md) §4
"Diagnostics output" and "Fix and edit model"; [RFC 0003](../rfcs/0003-stilyagi-cli-contract.md)
§§11, 12; [RFC 0001](../rfcs/0001-stilyagi-intermediate-representation.md) for
`line_index`, `regions`, and `errors` shape; [developers guide](../developers-guide.md)
§§7.1, 8. Skills: `python-router` → `python-data-shapes`,
`python-types-and-apis`; `python-verification` → `hypothesis`; `leta`;
`en-gb-oxendict`. Snapshot testing uses `syrupy` per AGENTS.md.

Extend `python/stilyagi/diagnostics.py` into the one internal diagnostic model
all renderers derive from (design §Diagnostics output): a frozen `Diagnostic`
carrying `path: str` (the command-line-relative POSIX reported path per the
round-4 Decision Log entry), `code: str`, `message: str`, `severity`
(an enum: `error`/`warning`), an optional source location
(`line: int`, `column: int`, both 1-based) resolved from byte offsets via the
IR `line_index`, and a `fix` applicability field left `None` in this slice.
Remove the placeholder `NodeRef` span and the unused `Fix` placeholder (round-4
Decision Log entry): `NodeRef` cannot express a source position, and `Fix`
returns in roadmap 2.2.2 with the real edit model. Before removing them, sweep
for importers with `leta refs` — only `tests/test_package_skeleton_units.py`
references `NodeRef` today (verified this worktree). Keep the module under 400
lines; if the offset→line/column helper grows, put it in
`python/stilyagi/diagnostics_location.py`.

Enumerated in-lockstep test edits (same commit as the reshape, so the W4 gate is
never left red — this closes Round-1 review defect 2):

- `tests/test_package_skeleton_units.py::test_diagnostic_preserves_code_and_message`
  (line 92): rewrite to construct the new `Diagnostic(path=..., code=...,
  message=..., line=..., column=...)` and drop the `NodeRef` span; assert the
  round-trip (`dc.replace`) equality still holds on the new shape.
- `tests/test_package_skeleton_units.py::test_engine_skeleton_dataclasses_preserve_their_fields`
  (line 115): keep the `engine.RendererRegistry().default_format == "text"`
  assertion (the round-4 decision retains no-arg construction and
  `default_format`) and extend it to assert the new `render(...)` surface exists.
  Do **not** delete the case; update it.
- Remove the `NodeRef` import usage from that test module if it becomes unused.

Add an IR-error adapter (in a new `python/stilyagi/engine/checker.py`),
`map_ir_errors(document, reported_path) -> list[Diagnostic]`: map each IR
`errors[]` entry for a file into a `Diagnostic` with a stable synthetic code (for
example `IR000`), the error message, and the resolved location when the error
carries an offset. It returns `[]` when `document.ir is None` or the mapping
lacks an `errors` array (round-4 Decision Log entry on `Document.ir is None`), so
a `None` IR degrades gracefully rather than raising. The offset→location helper
likewise falls back to `line=1, column=1` when no `line_index` is present.
This is a **forward-looking seam for roadmap 2.1.3** (non-fatal error emission);
it is **not** a content-reachable exit-`1` trigger in this slice, because the
real Markdown extractor never populates `errors[]` for user content
(`crates/stilyagi-markdown/src/tests/malformed.rs:47-49`; frontmatter snapshot
line 192 `"errors": []`). It is therefore verified against a hand-built IR
mapping and against the real extractor's empty Markdown `errors[]`, never by
fabricating a malformed-Markdown extraction that yields errors.

Rewrite `python/stilyagi/engine/renderers.py` so `RendererRegistry` produces:

- `text`: one line per diagnostic, `path:line:col: CODE message`, deterministic
  ordering (by path, then location, then code), plus a trailing summary line;
- `json`: a stable object with a top-level `diagnostics` array; each entry
  includes `path`, `code`, `message`, `severity`, `location`, and
  `fix_applicable` (always `false`/absent in this slice), matching the design's
  "JSON output includes fix applicability" requirement.

The reported `path` in both renderings is the command-line-relative POSIX form
(round-4 Decision Log entry), pinned directly by assertion, not only by snapshot
redaction. The `json` `path` is therefore reproducible across machines and does
not leak an absolute home directory.

Note: `sarif` is named in RFC 0003 §11 but is out of scope for 2.2.1. Expose
only `text` and `json` in the `--output-format` choices to avoid promising an
unimplemented format. When a user passes `--output-format sarif`, augment
argparse's bare "invalid choice" with an explicit message that `sarif` is planned
for a later slice but unavailable now (round-4 Decision Log entry); record the
`sarif` deferral in W7 docs.

Tests (Red first):

- `tests/test_diagnostics_location.py` (unit + property): offset→line/column
  mapping against a known `line_index`; the `None`/absent-`line_index` fallback
  returns `line=1, column=1`; property test asserts the mapping is
  monotonic non-decreasing and always within `[1, n_lines]` for arbitrary
  offsets within bounds (`hypothesis`).
- `tests/test_renderers.py` (unit + snapshot): given a fixed list of
  `Diagnostic`s, the `text` and `json` renderings are asserted semantically
  (fields present, ordering, and the exact command-line-relative POSIX `path`
  form) **and** pinned with `syrupy` snapshots. Because the `path` field is
  already the stable relative form, snapshots do not depend on redacting an
  absolute path; assert the `path` value directly so a real contract change
  (not a machine-specific prefix) is what breaks the snapshot. Keep snapshots
  focused on the stable output boundary and pair each with semantic assertions
  per AGENTS.md.
- `tests/test_ir_error_adapter.py` (unit): pins the adapter honestly against the
  real extractor and a synthetic IR mapping. (1) A hand-built IR `document`
  mapping carrying one synthetic `errors[]` entry maps to exactly one
  `Diagnostic` with code `IR000`, the entry's message, the passed `reported_path`,
  and the resolved location; an empty `errors[]` maps to none; a document with
  `ir is None` maps to none (no raise). (2) The real-extractor pin: for
  each real malformed Markdown fixture under
  `tests/fixtures/corpus/markdown/malformed/` — verified present this worktree as
  `unclosed-table.md`, `unbalanced-emphasis.md.fixture`, and
  `broken-reference-link.md.fixture` (note the mixed `.md`/`.md.fixture`
  extensions, so glob the directory contents rather than assuming `*.md`; the
  extension is irrelevant to extraction because `MARKDOWN` is passed
  explicitly) — `engine.extract_document(text, model.Syntax.MARKDOWN)` returns a
  document whose `ir["errors"]` is `[]`, so the
  adapter yields **zero** diagnostics — documenting that malformed Markdown
  recovers cleanly in this slice and does not drive exit `1`. This is the test
  that pins the Markdown behaviour against the real Markdown extractor per the
  design reviewer, replacing the round-2 `test_extraction_error_mapping.py` that
  wrongly assumed populated errors.

Acceptance: Red→Green; snapshots reviewed and stable on re-run;
`make check-fmt`, `make typecheck`, `make lint`, `make test` pass.

### W5 — `check` command, argparse CLI, exit codes, console entry point

Documents to read first: [RFC 0003](../rfcs/0003-stilyagi-cli-contract.md)
§§3.1, 5, 8, 10 (flags), 12 (exit codes), 16 (examples); [Stilyagi design](../stilyagi-design.md)
§4 "CLI" and "First run on a docs repository" user flow, §7.3. Skills:
`python-router` → `python-errors-and-logging`, `python-abstractions`;
`python-testing` (pytest-bdd); `python-verification`; `leta`; `en-gb-oxendict`.
Because this is CLI behaviour, add BDD and an end-to-end test per AGENTS.md
§"Python verification and testing".

Rewrite `python/stilyagi/cli.py` (splitting into a `python/stilyagi/cli/`
package — `__init__.py`, `parser.py`, `check.py` — if a single file would exceed
400 lines):

- `build_parser()` constructs an `argparse` parser with a `check` sub-command
  accepting `FILES...` (default `["."]`) and the v1-relevant options this slice
  supports: `--select`, `--ignore`, `--extend-select`, `--output-format`
  (choices `text`, `json`; default `text`), `--config`, `--isolated`,
  `--no-cache` (accepted, inert this slice), `--quiet`, `--verbose`, `--silent`.
  A global `-V`/`--version`. Flags reserved for later slices (`--fix`,
  `--unsafe-fixes`, `--diff`, and `--stdin-filename` until W6) are **not**
  defined, so passing them yields argparse's usage error → exit `2`.
- `main(argv: list[str] | None = None) -> int` parses `argv` (defaulting to
  `sys.argv[1:]`), dispatches `check`, and returns the exit code. Invalid CLI
  usage and invalid configuration return `2` with an actionable stderr message;
  a clean run returns `0`; remaining diagnostics return `1`.
- `run_check(args) -> int` composes W1–W4: resolve CLI overrides, discover
  Markdown files (W3), for each file resolve the nearest config (W2), read the
  file, call `engine.extract_document(text, model.Syntax.MARKDOWN)`, collect
  diagnostics from (a) the empty rule registry seam and (b) the IR-error adapter
  (W4, which returns `[]` for real Markdown in this slice, and `[]` when
  `document.ir is None`), attribute each diagnostic to the file's
  command-line-relative POSIX reported path (W3), render via the chosen
  format (W4), and compute the exit code via `compute_exit_code`. Wrap each
  per-file read/decode in a handler that maps `UnicodeDecodeError` (non-UTF-8),
  `PermissionError`, `FileNotFoundError` (a file removed mid-run), and
  `IsADirectoryError` to an actionable stderr message and `had_error=True` →
  exit `2` (round-4 Decision Log entry on file failure modes) — never `1`. If
  `engine.extract_document` raises (an internal parser panic or invalid span),
  catch it likewise, print an actionable stderr message, and return `2`
  ("internal error", RFC 0003 §12) — never `1`. Read files as UTF-8 text
  explicitly (`Path.read_text(encoding="utf-8")`) so the decode failure mode is
  deterministic rather than locale-dependent.
- `compute_exit_code(diagnostics, *, had_error) -> int` is the pure exit-code
  mapping: return `2` if `had_error` (invalid config/usage/internal error), else
  `1` if `diagnostics` is non-empty, else `0` (RFC 0003 §12). Keeping it a small
  pure function lets W5 unit-test the exit-`1` branch directly with a synthetic
  diagnostic, since no real Markdown content reaches it in this slice.
- Define the explicit empty rule-registry seam
  (`python/stilyagi/rules/registry.py`): `run_rules(document, config) -> list`
  returns `[]` today, documented as the extension point 2.3.1 fills. This keeps
  the check loop honest without introducing rules out of order.

Add `python/stilyagi/__main__.py` calling `raise SystemExit(cli.main())` so
`python -m stilyagi check ...` works for tests and users without relying on
`PATH`.

Add the console entry point in `pyproject.toml`:

```toml
[project.scripts]
stilyagi = "stilyagi.cli:main"
```

BDD (embed the feature in the plan and keep it synchronized):

Create `features/stilyagi_check_command.feature` and step definitions under
`tests/steps/` (create the directory; it is already referenced by the ruff
per-file-ignores in `pyproject.toml`). Feature outline:

```gherkin
Feature: stilyagi check for Markdown files

  Scenario: check reports clean Markdown with exit code zero
    Given a temporary tree with two well-formed Markdown files
    When I run "stilyagi check ." in that tree
    Then the exit code is 0
    And the text output lists no diagnostics

  Scenario: check visits Markdown files in deterministic path order
    Given a temporary tree with Markdown files "b.md", "a.md", and "sub/c.md"
    When I run "stilyagi check . --output-format json"
    Then the diagnostics and processed paths follow sorted normalized order

  Scenario: check recovers malformed Markdown cleanly in this slice
    Given a temporary tree containing malformed Markdown
    When I run "stilyagi check ."
    Then the exit code is 0
    And no diagnostics are reported

  Scenario: check fails with exit code 2 on invalid configuration
    Given a temporary tree with an invalid stilyagi.toml
    When I run "stilyagi check ."
    Then the exit code is 2
    And an actionable error is printed to standard error

  Scenario: isolated mode ignores discovered configuration
    Given a temporary tree with a stilyagi.toml and a Markdown file
    When I run "stilyagi check . --isolated"
    Then discovery is skipped and defaults are used
```

Tests (Red first):

- `tests/test_check_command.py` (unit): `main([...])` return codes for the
  clean (`0`) and usage/config-error (`2`) paths; default target is `.`;
  `--output-format json` emits parseable JSON. The exit-`1` "violations remain"
  branch is exercised two ways without fabricating extraction behaviour: (a)
  `compute_exit_code([<one synthetic Diagnostic>], had_error=False) == 1` and the
  boundary cases `[] → 0`, `had_error=True → 2`; and (b) a `run_check` test that
  monkeypatches the empty rule-registry seam
  `stilyagi.rules.registry.run_rules` to return a single synthetic `Diagnostic`,
  asserting the composed run returns `1` and renders that diagnostic. A separate
  case pins that a tree of real malformed Markdown exits `0` (recovers cleanly),
  matching the BDD scenario and the W4 real-extractor pin.
- `tests/test_cli_e2e.py` (end-to-end): invoke `python -m stilyagi check` as a
  subprocess against a temporary tree; assert exit code and stdout/stderr for the
  content-reachable codes `0` (clean tree, and a malformed-Markdown tree that
  recovers cleanly) and `2` (invalid config/usage). Exit `1` is **not** reachable
  by any real Markdown content in this slice, so it is not asserted through the
  subprocess boundary; it is covered by the `compute_exit_code` and stubbed-seam
  unit tests above. This is documented, not a silent gap. Covers the externally
  observable command boundary per AGENTS.md §e2e.
- Add `tests/test_check_files.py` (unit + e2e): a non-UTF-8 `.md` file, a
  permission-denied file (skip on platforms that cannot express it), and a target
  removed between discovery and read each yield exit `2` with an actionable
  stderr message — never `1`. A directory containing a symlink cycle completes
  (proves W3's non-following recursion) and exits `0`.
- Make **both** existing no-argument `cli.main()` tests hermetic in the same
  commit as the CLI rewrite so no gate is left failing (closes Round-1 review
  defect 3):
  - `tests/test_package_skeleton_units.py::test_cli_main_reports_placeholder_exit_code`:
    redefine to call `cli.main([...])` with an explicit `argv` against a
    `tmp_path` tree (or a usage-error argv), asserting `0` for a clean tree and
    `2` for a usage error. It must **not** call `cli.main()` with no arguments,
    because the default target `.` would recurse the test's current working
    directory.
  - `tests/test_round_trip_helpers.py::test_cli_placeholder_output_matches_snapshot`:
    this is a `syrupy` snapshot of `{exit_code, stdout, stderr}` whose stored
    artefact lives at
    `tests/__snapshots__/test_round_trip_helpers/test_cli_placeholder_output_matches_snapshot.json`.
    Either (preferred) **delete** the test and its stored snapshot file, since the
    W4 `tests/test_renderers.py` snapshots now pin the real `text`/`json` output
    on hermetic input; or redefine it to run `cli.main([...])` against a
    `tmp_path` tree and **regenerate** the stored snapshot (`pytest
    --snapshot-update` scoped to that test) so it captures the new deterministic
    output. Do not leave the stale placeholder snapshot on disk. Account for the
    artefact explicitly in the commit (deleted or regenerated), not implicitly.

Acceptance: the BDD scenarios fail before implementation and pass after; unit
and e2e tests Red→Green; the deterministic commit gates `make check-fmt`,
`make typecheck`, `make lint`, `make test` pass (`make check-fmt` runs
`ruff format --check` and `cargo fmt --check`; `make typecheck` runs `ty check`;
`make lint` runs `ruff check`, `pylint`, `clippy`, and Whitaker; `make test`
runs the pytest/BDD/e2e suites — AGENTS.md §"Rust specific guidance" and the
Validation section). Separately, `make release` (`release: release-artifact
smoke-release`, `Makefile:54`) must still succeed: it builds the release wheel
and runs `python -m stilyagi.smoke`, confirming the new `[project.scripts]`
console entry point and the wheel build survive. `make release` does **not** run
lint, typecheck, or the test suites, so it is an additional build-integrity
check, not the behavioural gate. (On this branch `make all` at `Makefile:38`
chains all four gates plus `make markdownlint`/`make nixie` but not the wheel
build, so run `make release` explicitly for the wheel/console check.)

### W6 — Standard-input support (`-` and `--stdin-filename`)

Documents to read first: [RFC 0003](../rfcs/0003-stilyagi-cli-contract.md) §3.1
(stdin and `--stdin-filename`). Skills: `python-router` →
`python-errors-and-logging`; `python-testing`; `leta`; `en-gb-oxendict`.

Extend the `check` parser and `run_check` so a single `-` target reads source
from standard input. Add `--stdin-filename` so Stilyagi can infer syntax and
report a plausible path; when reading stdin without a filename, default the
reported path to `<stdin>` and infer Markdown syntax (the only syntax this
slice supports). Reject mixing `-` with other file targets (usage error →
exit `2`).

Tests (Red first):

- `tests/test_check_stdin.py` (unit + e2e): piping Markdown via `-` with
  `--stdin-filename README.md` produces diagnostics attributed to that path;
  a clean stdin document exits `0`; mixing `-` with a path exits `2`.
- Add one BDD scenario to `features/stilyagi_check_command.feature` covering the
  stdin path and keep the step definitions in sync.

Acceptance: Red→Green; `make check-fmt`, `make typecheck`, `make lint`,
`make test` pass.

### W7 — Documentation and roadmap update

Documents to read/update: [docs/users-guide.md](../users-guide.md) (add a
"Checking Markdown with `stilyagi check`" section: usage, targets, output
formats, exit codes, `--isolated`, stdin); [docs/developers-guide.md](../developers-guide.md)
§§2, 3, 8 (record the new `config`, `discovery`, `diagnostics`, renderer, and
CLI boundaries and the empty rule-registry seam); [docs/roadmap.md](../roadmap.md)
(tick 2.2.1 and add a completion note referencing this ExecPlan, mirroring the
3.1.1 entry). Confirm no design-doc change is required; if the gitignore or
`sarif` deferrals need recording beyond this plan, add a short note to the
design doc §7.3, and if a deferral is a durable decision consider whether an
ADR is warranted (escalate rather than author an ADR unilaterally). Skills:
`scribe` for prose edits, `en-gb-oxendict`, `changelog` if a CHANGELOG entry is
expected.

Format only the Markdown files changed by this work item: run
`mdtablefix` then `markdownlint-cli2 --fix` on exactly the docs touched, then
run the repository Markdown gates below.

Tests: none new (docs-only). Validation is the Markdown gates.

Acceptance: `make markdownlint` and `make nixie` pass; the code gate suite
(`make check-fmt`, `make typecheck`, `make lint`, `make test`) remains green and
`make release` still builds and smoke-tests the wheel.

## Concrete steps

Run everything from the worktree root
`/home/leynos/Projects/stilyagi.worktrees/roadmap-2-2-1`.

For each work item, in order:

1. Write the failing test(s) named in that work item and run the focused suite
   to observe the Red failure for the intended reason, e.g.:

   ```bash
   .venv/bin/python -m pytest tests/test_config_schema.py -x -q
   ```

   Expect the new test to fail before implementation.

2. Implement the minimal production change to make the focused test pass
   (Green), then re-run the focused suite.

3. Refactor for clarity within the 400-line file limit, then run the commit
   gates and commit. Prefer delegating the full gate run to the `scrutineer`
   subagent, which runs gates sequentially and captures logs under `/tmp`.

Because gate output is truncated in this environment, when running gates
directly capture to a log:

```bash
make test 2>&1 | tee "/tmp/test-stilyagi-$(git branch --show-current).out"
```

Commit after each work item once its gates pass (use the `commit-message`
skill; end the message with the required `Co-Authored-By` trailer).

## Validation and acceptance

Per-work-item validation is stated above. The whole-change acceptance is:

- Behaviour: the BDD scenarios in
  `features/stilyagi_check_command.feature` fail before W5 and pass after; the
  end-to-end test in `tests/test_cli_e2e.py` drives `python -m stilyagi check`
  over a temporary Markdown tree and observes the content-reachable exit codes
  `0` (a clean tree, and a malformed-Markdown tree that recovers cleanly) and `2`
  (invalid config/usage). Exit `1` ("violations remain") is not reachable from
  Markdown content in this slice — the extractor never populates IR `errors[]`
  and no rules exist — so it is exercised at unit level via `compute_exit_code`
  and via `run_check` with the empty rule-registry seam stubbed to return a
  synthetic diagnostic (W5), and becomes content-reachable through the same seam
  when 2.3.1 adds rules.
- Determinism: `tests/test_discovery_properties.py` proves file ordering is the
  sorted normalized-path order for arbitrary inputs.
- Renderers: `tests/test_renderers.py` `syrupy` snapshots for `text` and `json`
  are stable on re-run and paired with semantic assertions.

Run the deterministic commit gates (path-safe; no handwritten file lists), in
the order the workflow host re-runs them. On this branch the gate targets are
distinct (verified against the worktree Makefile and AGENTS.md §"Rust specific
guidance"): `make check-fmt` runs `ruff format --check` and `cargo fmt --check`
(`Makefile:114`); `make typecheck` runs `ty check` (`Makefile:126`); `make lint`
runs `ruff check`, `pylint`, `clippy -D warnings`, and Whitaker (`Makefile:118`);
`make test` runs the workspace tests and the pytest/BDD/property/snapshot/e2e
suites (`Makefile:137`). Formatting is a **separate** gate from lint — do not
conflate them. Run all four explicitly, in order:

```bash
make check-fmt
make typecheck
make lint
make test
```

(On this branch `make all` at `Makefile:38` chains these four plus
`make markdownlint` and `make nixie`; the host nonetheless re-runs the four
deterministic gates individually, so a gates-green claim must be reproducible
target-by-target.)

Separately run `make release` to confirm the release wheel and the new console
entry point still build and smoke-test (build integrity only — `release:
release-artifact smoke-release`, `Makefile:54`; it runs no lint/typecheck/test
gate):

```bash
make release
```

For the documentation changes in W7 also run the Markdown gates:

```bash
make markdownlint
make nixie
```

Quality criteria for "done":

- Formatting: `make check-fmt` clean (apply with `make fmt` only against changed
  files; do not run a repo-global reformat that churns unrelated files).
- Typecheck: `make typecheck` (`ty check`) reports no violations.
- Lint: `make lint` (ruff, pylint, clippy, Whitaker) reports no violations.
- Tests: all unit, BDD, property, snapshot, and e2e tests pass under `make test`
  (not `make release`, which builds and smoke-tests the wheel but runs no tests).
- Markdown: `make markdownlint` and `make nixie` clean.

## Idempotence and recovery

Every step is re-runnable. Tests use temporary directories (`tmp_path`), so
reruns do not accumulate state. Converting `config.py` to a package is a
one-time move; if interrupted, re-running the move is safe because the public
re-exports are the contract. No destructive filesystem operations are involved.
If a gate fails, read the cited `/tmp` log, fix, and re-run that single gate
before proceeding.

## Interfaces and dependencies

Use only the standard library plus existing project code. No new runtime
dependency. Prescriptive end-state surfaces:

- `python/stilyagi/config/__init__.py` re-exports `StilyagiConfig`,
  `InvalidCacheDirError`, `InvalidConfigError`, `LintConfig`,
  `MarkdownExtractConfig`, `load_config_file`,
  `discover_same_directory_config`, and `resolve_config_for_path`.
- `python/stilyagi/discovery.py` defines the frozen dataclass
  `DiscoveredFile(reported_path: str, resolved_path: pathlib.Path)` and
  `discover_markdown_files(targets: cabc.Iterable[pathlib.Path], config:
  StilyagiConfig) -> list[DiscoveredFile]`. Each element carries the resolved
  path (for de-duplication and ordering) and the command-line-relative POSIX
  reported path (for diagnostic attribution and the renderer `path` form); no
  variant returns bare `pathlib.Path`.
- `python/stilyagi/diagnostics.py` defines the frozen `Diagnostic` and a
  `Severity` enum; offset→location logic lives here or in
  `python/stilyagi/diagnostics_location.py`.
- `python/stilyagi/engine/renderers.py` `RendererRegistry` exposes
  `render(diagnostics, output_format) -> str` for `text` and `json`.
- `python/stilyagi/engine/checker.py` defines
  `map_ir_errors(document, reported_path) -> list[Diagnostic]`, the
  forward-looking IR-error adapter seam (returns `[]` for real Markdown in this
  slice). The `reported_path` argument is the command-line-relative POSIX
  reported path (`DiscoveredFile.reported_path`) that each emitted `Diagnostic`
  carries as its `path`, matching W4's body and `tests/test_ir_error_adapter.py`.
- `python/stilyagi/rules/registry.py` defines
  `run_rules(document, config) -> list[Diagnostic]` returning `[]` (the 2.3.1
  seam).
- `python/stilyagi/cli.py` (or `cli/` package) defines
  `build_parser() -> argparse.ArgumentParser`,
  `main(argv: list[str] | None = None) -> int`, `run_check(args) -> int`, and the
  pure `compute_exit_code(diagnostics, *, had_error) -> int` (RFC 0003 §12
  mapping).
- `python/stilyagi/__main__.py` runs `raise SystemExit(cli.main())`.
- `pyproject.toml` gains `[project.scripts] stilyagi = "stilyagi.cli:main"`.

## Revision note

Round 1 draft (2026-07-04). Decomposes roadmap 2.2.1 into seven ordered,
independently committable work items (config schema, config resolution,
discovery, diagnostics/renderers, the `check` command, stdin, docs). Pins
`argparse` and `tomllib` (no new runtime dependency), records the extractor's
path-agnostic bridge signature as a Constraint, and scopes out rules (2.3.1),
fixes (2.2.2), other sub-commands (2.2.3), non-Markdown discovery (3.2.1), and
full `.gitignore` honouring (deferred, RFC SHOULD).

Round 2 (2026-07-04) — resolves the design reviewer's two blocking points:

1. **`make all` does not run the gates.** Verified against the worktree Makefile:
   `all: release` (`Makefile:38`) and `release: release-artifact smoke-release`
   (`Makefile:48`) — `make all` only builds the release wheel and runs
   `python -m stilyagi.smoke`; it never invokes `lint`, `typecheck`, or `test`
   (separate targets at `Makefile:112,120,131`). Every assertion that `make all`
   runs the gates was removed. Whole-change validation, the W5 and W7 acceptance
   lines, the W5 risk mitigation, and the "done" criteria now invoke the actual
   gate suite (`make lint`, `make typecheck`, `make test`) plus `make markdownlint`
   and `make nixie` for docs; `make all` is retained only as a wheel/console
   build-integrity check with that role stated explicitly.
2. **Strict schema rejected the RFC 0003 §6 baseline.** W1's schema now models
   the whole RFC 0003 §6 v1 baseline. Keys consumed this slice drive behaviour;
   keys reserved for later slices (`line-length`, `[lint] fixable`/`unfixable`,
   `[lint.per-file-ignores]`, `[nlp]`, `[rule.<CODE>]`) are accepted-and-preserved,
   not rejected, so copying the documented baseline (or a repo already carrying
   a matching `[tool.stilyagi]` block) no longer trips exit `2`. Kebab-case TOML
   keys map to snake-case fields via an explicit key map; `InvalidConfigError` is
   raised only for keys outside the §6 contract. A new `test_config_schema.py`
   case pins the verbatim §6 baseline as parseable, and the round-1 invented
   `[lint] extend-select`/`[discovery] include` keys are removed. See the
   Decision Log for both.

Round 3 (2026-07-04) — resolves the design reviewer's two blocking points:

1. **The extraction-error exit-`1` path was unimplementable.** Verified against
   the real Markdown extractor: `crates/stilyagi-markdown/src/tests/malformed.rs:47-49`
   asserts `document.errors.is_empty()` for all three malformed fixtures, and the
   frontmatter snapshot line 192 shows `"errors": []`. Malformed Markdown recovers
   to degraded regions and never populates IR `errors[]` in this slice (non-fatal
   error emission is roadmap 2.1.3; 2.2.1 requires only 2.1.1 and 1.2.3, so it
   cannot depend on 2.1.3). Applying the reviewer's option (a): the plan no longer
   claims real malformed Markdown yields exit `1`. The exit-`1` code path is
   exercised synthetically — a pure `compute_exit_code([<synthetic Diagnostic>])`
   unit test and a `run_check` test that stubs the empty rule-registry seam to
   return one synthetic diagnostic. The IR-error adapter is retained as a 2.1.3
   seam (`map_ir_errors`), tested against a hand-built IR mapping and pinned to
   the real extractor's empty Markdown `errors[]`. Real malformed Markdown now
   asserts exit `0`. Updated: Purpose, the Context IR bullet, a new Surprises
   entry, two Decision Log entries, W4 (renamed to "IR-error adapter seam", test
   renamed to `test_ir_error_adapter.py`), W5 (`compute_exit_code`, stubbed-seam
   and synthetic exit-`1` unit tests, internal-error→exit-`2` handling), the BDD
   scenario (now "recovers malformed Markdown cleanly", exit `0`), the e2e test
   (exit `1` explicitly unit-only, not asserted through the subprocess), the
   whole-change acceptance, and the interfaces list.
2. **Mis-applied cross-syntax snapshot claim.** The round-2 Context bullet cited
   "the malformed Python snapshot confirms `errors` is populated on malformed
   input" to justify Markdown behaviour. This is a Markdown-only slice
   (`model.Syntax.MARKDOWN`; Python extraction defers to 3.2.1), so the Python
   snapshot is not evidence for the Markdown path. That claim is removed; the
   Markdown behaviour is now pinned solely against the real Markdown extractor
   (`malformed.rs:47-49` and the frontmatter snapshot), and the W4 real-extractor
   test enforces `ir["errors"] == []` for real malformed Markdown fixtures.

Round 4 (2026-07-05) — closes the two Round-1 review defects earlier rounds left
open, plus the six advisories:

1. **Incomplete enumeration of tests broken by the W4 reshape (review defect 2).**
   Verified this worktree:
   `tests/test_package_skeleton_units.py::test_diagnostic_preserves_code_and_message`
   (line 92) constructs `Diagnostic(code, message, span=NodeRef(...))`, and
   `::test_engine_skeleton_dataclasses_preserve_their_fields` (line 115) asserts
   `RendererRegistry().default_format == "text"`. Both are now enumerated in W4
   as in-lockstep edits in the same commit as the reshape, with the fate of
   `NodeRef`/`Fix` (removed) and of `RendererRegistry`'s no-arg construction and
   `default_format` (retained) decided explicitly in the Decision Log, so the W4
   gate is never red.
2. **Mischaracterised, non-hermetic `cli.main()` snapshot test (review defect 3).**
   `tests/test_round_trip_helpers.py::test_cli_placeholder_output_matches_snapshot`
   is a `syrupy` snapshot (not a `== 2` assertion) with a stored artefact at
   `tests/__snapshots__/test_round_trip_helpers/test_cli_placeholder_output_matches_snapshot.json`.
   W5 now redefines **both** no-arg `cli.main()` tests to pass an explicit `argv`
   against a `tmp_path` tree (never the repo CWD) and explicitly deletes or
   regenerates the stored snapshot artefact.

Advisories landed: file failure modes (non-UTF-8/permission/removed/symlink cycle
→ exit `2` or non-following recursion, new `tests/test_check_files.py`);
`Document.ir is None` guarded in `map_ir_errors` and the location helper; the
reported `path` pinned to command-line-relative POSIX form and asserted directly;
`--output-format sarif` given an explicit "planned, not yet available" message;
`NodeRef`/`Fix` retired; `--config` inline-vs-path disambiguation specified and
tested. Updated: header, Context (three new/expanded bullets), Risks (two new),
Decision Log (seven round-4 entries), W2 (`--config` classification + test), W3
(symlink non-following + dual reported/resolved path), W4 (enumerated test edits,
`ir is None`, path-form assertions, `sarif` message), and W5 (file-failure
handler, hermetic test redefinition, snapshot-artefact handling).

Round 5 (2026-07-06) — corrects the validation/gate story after re-verifying the
worktree Makefile and AGENTS.md; no work-item mechanism changed:

1. **The `make all` "runs no gates" claim was stale.** Rounds 2-4 asserted, on
   the then-current `origin/main`, that `all: release` built only the wheel and
   ran no gates. The worktree Makefile has since advanced: `all: ## Run commit
   gates` (`Makefile:38-44`) chains `check-fmt`, `typecheck`, `lint`, `test`,
   `markdownlint`, and `nixie`; the wheel is built by `release: release-artifact
   smoke-release` (`Makefile:54`). Every sentence that conflated `make all` with
   the wheel build was corrected, and the wheel/console build-integrity check now
   invokes `make release`, not `make all`.
2. **`make check-fmt` promoted to its own gate.** AGENTS.md §"Rust specific
   guidance" (lines 156-186) shows `make check-fmt` (`ruff format --check` +
   `cargo fmt --check`) is distinct from `make lint` (ruff/pylint/clippy/
   Whitaker). The plan previously implied `make lint` ran the formatting check
   and omitted `check-fmt` from the per-work-item acceptance lines. The
   deterministic commit gates are now stated everywhere as the four targets the
   workflow host re-runs, in order: `make check-fmt`, `make typecheck`,
   `make lint`, `make test` (plus `make markdownlint`/`make nixie` for W7 docs).
   Updated: header, a new Decision Log correction, two new Surprises entries
   (Makefile change; git-tool unavailability with the branch-local re-verification
   that no 2.2.1 code is committed), the whole-change Validation block and command
   list, the W1-W7 acceptance lines, the W5 acceptance narrative, the W5 wheel
   risk mitigation, and a W4 note on the mixed-extension malformed fixtures
   (`unclosed-table.md`, `unbalanced-emphasis.md.fixture`,
   `broken-reference-link.md.fixture` — glob the directory, do not assume `*.md`).

Round 6 (2026-07-06) — reconciles the two fresh interface contradictions the
saved re-review raised, and durably commits the result:

1. **`discover_markdown_files` return type contradicted itself.** The Interfaces
   section declared `list[pathlib.Path]` while the W3/W5 bodies needed both a
   resolved path and a command-line-relative POSIX reported path. Resolved by
   declaring a single authoritative frozen `DiscoveredFile(reported_path: str,
   resolved_path: pathlib.Path)` element type everywhere (Interfaces, W3, W5,
   Decision Log), carrying both paths; no variant returns bare `pathlib.Path`.
2. **`map_ir_errors` arity was ambiguous.** The Interfaces entry now reads the
   two-argument `map_ir_errors(document, reported_path)` form the W4 body and
   `tests/test_ir_error_adapter.py` pin, and the stale
   `crates/stilyagi-pyext/src/tests.rs:14`/`:140` citations were corrected to the
   real `crates/stilyagi-pyext/src/tests/mod.rs:18`/`:144`.

No work-item mechanism changed in round 6. This revision also closes the
EXECPLAN DURABILITY blocking point: the round-6 body edits (and this note) are
committed on the task branch, so the durable committed ExecPlan is the source of
truth and the worktree is left clean.

Implementation and documentation update completed and committed.
