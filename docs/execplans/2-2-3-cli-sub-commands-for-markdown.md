# Deliver the Markdown inspection and cache commands

Status: IMPLEMENTATION IN FINAL REVIEW — R2 review findings are addressed and
all six local gates pass; committed-candidate review remains pending.

Roadmap item: **2.2.3**. Branch: `2-2-3-cli-sub-commands-for-markdown`.

This ExecPlan is a living document. Keep its constraints, tolerances, risks,
progress, discoveries, decisions, verification evidence and outcomes current.
Publishing or merging this planning PR does not authorize implementation.

## Purpose / big picture

A maintainer should be able to explain which configuration governs a Markdown
file, inspect the exact intermediate representation (IR) produced by Rust,
remove Stilyagi's disposable cache data, and force fresh extraction without
special scripts. IR means the structured document containing source byte spans,
regions, syntax trees, suppression directives and extraction errors.

Deliver `stilyagi config [KEY]`, `stilyagi clean`, and
`stilyagi dump-ir [FILES]...`, and make `check --no-cache` effective. This
includes `.md`, `.markdown` and `.mdc` files with YAML frontmatter preserved
verbatim, and one bounded Markdown extraction cache: analysis and fix planning
still run on every invocation. Independent analysis caching remains roadmap
3.3.1 work.

## Constraints

- Implementation is approved as recorded in Progress. Do not mark 2.2.3 done
  until all acceptance evidence passes. Then update this plan to COMPLETE only
  after conformance reconciliation.
- Preserve current `check`, mixed-source discovery, source-byte fidelity,
  diagnostics, fix/refusal streams and exit codes. Cache only Markdown in this
  slice; existing Python and Rust extraction continue uncached.
- Reuse Rust extraction and canonical serialization. Do not reconstruct an IR
  from flattened Python regions or change RFC 0001 fields or span meanings.
- Python owns CLI/configuration/application coordination and cache filesystem
  adapters. Rust owns parsing and source identity within canonical IR. Neither
  the Rust parser nor the pure IR model discovers configuration or opens caches.
- Never delete arbitrary configured directories. Cache data is disposable;
  source files, neighbouring files and targets outside the working tree are not.
- Treat `.mdc` as ordinary Markdown in recursive discovery, explicit paths and
  stdin filename inference for check and dump, including diff/fix workflows.
  YAML frontmatter must survive repairs byte-for-byte. YAML field parsing and
  parser robustness improvements are outside this task.
- Do not activate plugins, NLP models or new rules for an inspection command.
  Reserved configuration remains inspectable without pretending it is executed.
- No new production dependency is planned. Requested test dependencies are
  authorized: `rstest`, `rstest-bdd`, `googletest`, `pretty_assertions`,
  `insta`, `proptest`, `pytest`, `pytest-bdd`, `syrupy`, and `hypothesis`.
- Follow AGENTS.md, module/file size limits and documentation conventions. Use
  the shared Cargo cache and compiler admission. Never overlap quality gates.

## Tolerances (exception triggers)

Stop, record the proposed deviation and affected requirements, set BLOCKED and
seek explicit acceptance if implementation requires another runtime dependency,
changes the IR schema, adds analysis caching or plugin execution, expands
persistent caching beyond Markdown, or cannot implement safe filesystem cleanup
on a supported platform. Do the same if a milestone needs more than 20
production files, an existing public CLI behaviour must change beyond the
contracts below, or a gate still fails after three targeted repairs. There is
no elapsed-time limit. Queueing for compiler admission is not a failure.

## Risks

- High impact, medium likelihood: custom `cache-dir` points at source or a
  symlink. Mitigate with a dedicated owned namespace, descriptor-relative
  deletion, no symlink traversal and sentinel-file tests.
- High impact, medium likelihood: a cache hit restores stale or malformed spans.
  Mitigate with complete request identity, versioned data, validated hydration,
  content-hash checks and cold/warm/bypass equivalence tests.
- Medium impact, high likelihood: config origin tracking disagrees with merged
  values. Carry values and provenance through the same merge operation and test
  generated inheritance chains and overriding layers.
- Medium impact, medium likelihood: canonical JSON changes during Python
  serialization. Retain Rust's serialized string and frame it without rewriting
  the document. Compare bytes against the real bridge, including Unicode.
- Medium impact, medium likelihood: adding three commands expands the CLI into
  a large dispatch module. Keep command-specific options and use cases
  separate; share only existing discovery/read/config boundaries with
  demonstrated reuse.

## Progress

- [x] (2026-10-14) Read repository guidance and requested skills; verify
      baseline
  `90aaccf9b3baa19f41d09a9f69f172127cd051a2` and rename the local branch.
- [x] (2026-10-14) Wyvern reconnaissance verified prerequisite implementation,
  CLI gaps and current cache boundaries.
- [x] (2026-10-14) Research Ruff precedent and Python safe deletion interfaces.
- [x] (2026-10-14) Complete six-perspective community-of-experts review and
  reconcile hydration, storage safety, metrics and spool recommendations.
- [x] (2026-10-14) Pass planning-document formatting, Markdown/spelling and
  Mermaid gates.
- [x] (2026-10-14) Publish the reviewed draft in PR #226.
- [x] (2026-10-24) Verify whole-block frontmatter IR support and revise the plan
  for `.mdc`, verbatim repairs and frontmatter-aware cache integrity.
- [x] (2026-10-24) Validate and publish the frontmatter plan amendment with
      `make check-fmt`, `make markdownlint` and `make nixie`.
- [x] (2026-10-24) Obtain explicit implementation approval from the user.
- [x] (2026-10-24) Rebase PR #226 onto `main` at
      `765915e5f0ff47899184ed24c9a398c3bc9f2b90`; preserve main's nose ADR 010
      and renumber the Markdown CLI ADR to 011.
- [x] (2026-10-24) Publish the rebased documentation candidate with
      `--force-with-lease`; verify PR #226 still targets `main` and that local,
      tracking and remote heads match `12da6f72d0969bbc2b133eb3a45491c2ee2ec263`.
- [x] (2026-10-25) Complete M1 implementation gates on the corrected
      candidate at HEAD `39078353b0552fa9381ca19d03c79f5276a5fe46`:
      `make check-fmt`, `make lint`, `make typecheck`, `make test`,
      `make markdownlint` and `make nixie` all passed. Nextest passed 357/357;
      doctests and both pytest stages passed. The test run initially exposed a
      missing doctest import for `_ConfigInspectionOptions`; add the explicit
      import and rerun the full sequence. See the `-r9.out` gate logs under
      `/tmp`.
- [x] (2026-10-24) Start M1 test-first: establish missing-command and
      provenance failures, then implement the config command and pass its
      focused CLI, resolver and Hypothesis suites. Full M1 gates subsequently
      passed on 2026-10-25.
- [x] (2026-10-25) Pass M1 formatting, typechecking and lint. The first
      serialized test run reached 355/357, then its remaining UI test exceeded
      600 s while shared compiler admission was heavily queued. Increase the
      trybuild allowance to 900 s while retaining the 18 m whole-run allowance;
      a 19 m value violates the 1,800 s watchdog ordering after termination and
      cold-build reserves. Rerun all M1 gates.
- [x] (2026-10-25) Implement M1 configuration inspection and provenance.
      Correct the property-test oracle, Maturin wheel snapshot,
      runner-placement contract, recursive helper lint finding and the
      `_ConfigInspectionOptions` doctest import. The final full gate sequence
      passed without further timeout-budget changes.
- [x] M1: effective configuration inspection and provenance — complete after
      all six quality gates passed.
- [x] (2026-10-25) Start M2: trace canonical IR and source identity through
      the Rust extractor, PyO3 bridge and Python adapter. CodeGraph MCP is
      unavailable because its transport closes; Leta LSP is available for Rust
      navigation. Begin with red tests for bridge identity and dump framing.
- [x] (2026-10-25) Implement M2 bridge identity, `dump-ir`, `.mdc`
      classification and frontmatter-protected repairs. Focused Rust bridge
      and extractor tests passed, as did 142 focused Python tests; full gates
      subsequently passed on R25 and the exact M2 commit below.
- [x] (2026-10-25) Add typed Rust `hydrate_ir_json` through the PyO3 bridge and
      stream canonical dump documents through bounded spools. Full gate
      validation passed on R25 and was repeated at the exact M2 commit below.
- [x] (2026-10-25) Complete M2 after all six gates passed on R25: formatting,
      lint, typecheck, Nextest 365/365, Rust doctests, Python tests and doctests,
      Markdown lint and Mermaid validation. Repair the injected extractor mock,
      package export contract, wheel snapshot, frontmatter property strategy
      and raw-docstring newline examples exposed by sequential full runs.
- [x] (2026-10-25) Apply the M2 CodeRabbit corrections: detect short text
      writes, preserve raw unknown syntax names, parameterize hydration
      rejection cases, share frontmatter segment validation, and correct four
      Oxford spelling findings. All six gates passed on the R6 working tree,
      including Nextest 366/366.
- [x] (2026-10-25) Re-review the M2 correction commit `963a931` with CodeRabbit
      CLI 0.9.1 against `74bca310..963a931`; the prescribed cooldown completed
      and the review reported zero findings across all 10 changed files.
- [x] (2026-10-25) Re-run all six gates sequentially on exact committed HEAD
      `963a93148875b14132f251508e43bb3a0f35fa8e`. Nextest passed 366/366;
      doctests, Python and script tests, four snapshots, formatting, lint,
      typecheck, Markdown lint and Mermaid validation passed. Logs are
      `/tmp/{check-fmt,lint,typecheck,test,markdownlint,nixie}-49853f07-73ba-4ebd-8c88-844f84cdf038-2-2-3-cli-sub-commands-for-markdown-complete-1.out`.
- [x] (2026-10-25) Begin M3 implementation: add request identity, owned storage,
      checksummed Rust hydration, strict cache bypass, CLI wiring for check and
      dump, and descriptor-relative cleanup. Focused cache and affected CLI
      suites passed 141 tests; the full gates were completed at this milestone.
- [x] (2026-10-25) Complete M3 on the candidate at HEAD
      `7f5530a6d7a3dc10a68b0a9f20f19ec2f1406e17`. The six sequential gates
      passed: check-fmt, lint, typecheck, test, markdownlint and nixie. Nextest
      passed 366/366; Rust doctests, Python tests, duplication helpers and
      snapshots passed. The full test run exposed cache reuse in the extractor
      failure test, generated cache writes in source-tree assertions, and new
      packaged modules missing from the wheel snapshot. The tests now disable
      cache reuse, compare source files while excluding generated cache state,
      and include the new modules in the package snapshot. Gate logs end in
      `-r11.out` under `/tmp`.
- [x] M2: canonical Markdown IR inspection and bridge identity — complete after
      the follow-up CodeRabbit review and exact-head gates passed.
- [x] M3: extraction cache, strict bypass, and safe cleanup — complete after
      all six quality gates passed.
- [x] (2026-10-25) Start M4: add actual-process CLI acceptance for config,
      canonical IR, failure framing, cache bypass and cleanup; add CLI-level
      frontmatter repair evidence, reconcile docs and review property
      non-vacuity. The existing in-process and Rust fixture tests provide
      baseline evidence; the planned process-boundary cases remain open.
- [x] (2026-10-25) Add six process-boundary BDD scenarios for config
      provenance, multi-input IR, failure atomicity, cold/warm/bypass
      equivalence, frontmatter-only cache invalidation, and repeatable cache
      cleanup. Add CLI repair and refusal cases for all three Markdown suffixes
      and both fix applicability levels.
      Focused Python acceptance currently passes 28 tests; Rust frontmatter BDD
      validation and full candidate gates remain in progress.
- [x] (2026-10-25) Strengthen frontmatter cache properties with a longer
      multiline prefix, fixed-body mutations, current whole-source hash and
      source-span re-slicing assertions, plus stale-checksum tampering of the
      cached YAML format field. The focused Python suite passes; the remaining
      M4 docs, complexity review and final gates are open.
- [x] M4: end-to-end acceptance, documentation and roadmap completion —
      complete after acceptance, complexity review and final conformance.
- [x] (2026-10-25) Commit M4 process-boundary acceptance, frontmatter repair
      coverage, source-coordinate property checks and user/developer docs as
      `31bffbc`. All six sequential gates passed on the exact candidate,
      including Nextest 367/367 and Python 872/872; Markdown lint and Mermaid
      validation passed. ADR, design and roadmap reconciliation passed the
      R25 documentation gates.
- [x] (2026-10-25) Begin the separate CodeScene refactor commit. Extract the
      check and dump coordinators' phase work, split provenance merge helpers,
      narrow frontmatter IR traversal, and consolidate the PyO3 test request.
      Local `cs delta origin/main` clears the planned complexity findings;
      all six sequential R23 gates passed on the candidate. The R23 logs record
      Nextest 367/367 and Python 872/872. The current-head CodeRabbit review
      remains pending.
- [x] (2026-10-25) Accept ADR 011 and reconcile the design, documentation index
      and roadmap item 2.2.3. `make check-fmt`, `make markdownlint` and
      `make nixie` passed sequentially on the R25 candidate; all three gates
      passed without temporary-directory or storage errors.
- [x] (2026-10-25) Complete conformance review: no new runtime dependencies,
      IR schema changes, expanded persistent-cache scope or unsupported
      deviations were introduced. The proof inventory is not applicable: this
      implementation adds no formal proofs. Roadmap 3.3.1 remains separate.
- [x] (2026-10-25) Triage the final local CodeRabbit review of `040c9f5`: fix
      seven actionable findings covering FIFO blocking, cache-marker recovery,
      bridge `None` coverage, duplicated extraction test helpers, a stale module
      name, a redundant step-module future import, and compound-duration prose.
      The later review found that the `.rules/python-typing.md` exception does
      not cover `markdown_cli_inspection.py`; import `pathlib` at runtime under
      Python 3.14 so pytest-bdd can inspect its deferred annotations.
- [x] (2026-10-25) Run the six gates after those fixes on the review-follow-up
      working tree based on `040c9f5`: Nextest 368/368, pytest 876/876, and
      script tests 154/154 passed. Formatting, lint, typecheck, Markdown lint
      (76 files, zero issues) and Mermaid validation passed. R29 logs are
      `/tmp/{check-fmt,lint,typecheck,test,markdownlint,nixie}-49853f07-73ba-4ebd-8c88-844f84cdf038-2-2-3-cli-sub-commands-for-markdown-r29.out`.
- [x] (2026-10-25) Triage the eight CodeRabbit findings on `9c00d3a`: resolve
      pytest-bdd's runtime `pathlib` annotation import, trust the chosen cwd
      while refusing linked descendants, memoize construction failures per
      root, retain retries after read failures, correct roadmap evidence, add
      subprocess timeout coverage and reuse the shared counting extractor.
- [x] (2026-10-25) Add cache-root and retry regressions; the focused cache and
      Markdown CLI suite passed 55/55 tests.
- [x] (2026-10-25) Pass the R1 local gates: `make check-fmt`, `make lint`,
      `make typecheck`, `make test`, `make markdownlint` and `make nixie`. Test
      evidence: Nextest 368/368, pytest 879/879, 75 passed and 3 skipped in the
      second Python stage, and script tests 154/154 with four snapshots. The
      spelling correction was followed by successful check-fmt, Markdown lint
      and Mermaid gates. Logs use the `r1-retry-2.out` and `doc-fix-1.out`
      suffixes under `/tmp`.
- [x] (2026-10-25) Review committed R1 candidate
      `7ebeb90287b44d1fd95ffa056f4a79a816dda844` with CodeRabbit and triage its
      six findings. Normalize descriptor-relative filesystem errors at the
      cache boundary so unavailable storage falls back to fresh extraction;
      add the permission-failure regression; bound shared CLI subprocesses and
      close test services during fixture teardown; validate malformed
      frontmatter after recomputing the IR checksum. Split cache I/O primitives
      and storage-failure tests to respect the 400-line module limit.
- [x] (2026-10-25) Pass all six local gates on the R2 working tree based on
      `7ebeb90287b44d1fd95ffa056f4a79a816dda844`: `make check-fmt`, `make lint`,
      `make typecheck`, `make test`, `make markdownlint` and `make nixie`. Test
      evidence: Nextest 368/368, pytest 880/880 with 24 snapshots, pytest
      doctests 76 passed and 3 skipped, and script tests 154/154 with four
      snapshots. Markdown lint found zero issues and Mermaid validation passed.
      Logs are `/tmp/{check-fmt,lint,typecheck,test,markdownlint,nixie}-49853f07-73ba-4ebd-8c88-844f84cdf038-2-2-3-cli-sub-commands-for-markdown-r38.out`.
- [ ] Commit the R2 changes, review that exact committed candidate with
      CodeRabbit, reconcile any valid findings, then complete this plan and
      roadmap item.

## Surprises & discoveries

`CheckOptions.no_cache` is already parsed but its help explicitly describes a
no-op. No persistent cache manager exists. `ConfigResolver` has only per-run
in-memory discovery, raw-table and resolved-table caches; bridge vocabulary is
also memoized. A useful cache-control command therefore needs a real, bounded
persistent cache, rather than merely removing the no-op wording.

`ConfigResolver.resolve_config_for_path` returns values without provenance.
Provenance cannot be recovered accurately from the final dataclass. It must be
retained while following `extend` and applying override layers.

Nextest started both trybuild UI binaries together even though their nested
Cargo builds use one target-directory lock. A serial test group keeps the
second binary from spending its timeout waiting behind the active build.

`check_execution.check_one_file` currently extracts before resolving per-file
configuration. M3 must move configuration resolution before extraction to build
a configuration-sensitive key, preserving existing error classification and
phase measurements.

The rebase target added the nose duplication-gate ADR as ADR 010. The Markdown
CLI ADR is now ADR 011; the existing main entry and both design intents remain
in the documentation index.

The PyO3 bridge serializes canonical JSON but the Python adapter discards its
string after parsing. Rust already has `extract_document_with_source_identity`;
the bridge currently uses anonymous identity. Reuse that Rust entrypoint
instead of patching serialized JSON.

The 2026-10-24 source inspection confirms that Markdown enables frontmatter in
`crates/stilyagi-markdown/src/lib.rs`. The `frontmatter_region` function in
`region_emission.rs` retains the entire fenced block, its source segment and
`attrs.format = "yaml"`. ADR 005 and the frontmatter snapshots confirm this is
block-level IR support, not semantic parsing of individual YAML fields.
`frontmatter_field` remains reserved. The source baseline is still
`5eaa1f5abca13826c41e08998e7bed5e5fd0be23` at the time of that inspection; M2
runtime changes subsequently landed in `963a931`.

The hosted CodeScene gate fails on M2 head
`963a93148875b14132f251508e43bb3a0f35fa8e`. Local `cs delta origin/main`
reproduces new complexity findings in `config/provenance.py`,
`tests/test_config_provenance_properties.py`, `cli_config_command.py` and
`engine/fix_planning/frontmatter.py`, plus a small `check_execution.py`
degradation and PyO3 test duplication. M4's planned complexity review must
resolve these findings without disabling or suppressing the CodeScene rules.

## Decision log

The implementation decisions below were proposed on 2026-10-14 and approved
with this plan on 2026-10-24. They were implemented within the recorded scope.
[ADR 011](../adr-011-markdown-cli-inspection-and-cache.md) records the accepted
substantive framing and persistent-state choices.

Validation sequencing follows the installed scrutineer's fixed order:
`make check-fmt`, `make lint`, `make typecheck`, `make test`,
`make markdownlint` and `make nixie`. The gate set and acceptance criteria are
unchanged; every gate still runs sequentially against one candidate.

D1: implement extraction-only caching now, retaining every RFC 0003 key
dimension. Use explicit inactive signatures for unavailable rule-pack/NLP
systems, and always execute analysis. This creates meaningful bypass and
cleanup without prematurely delivering roadmap 3.3.1.

D2: emit one canonical IR object for exactly one successful input, and a JSON
array of canonical IR objects for zero or multiple inputs. Empty discovery emits
`[]` plus newline. Preserve Rust document bytes within the array framing. This
supports the plural FILES contract without inventing newline-delimited JSON or
claiming concatenated pretty documents form a JSON value.

D3: preserve the existing config precedence implementation. Effective values
and their origins follow one merge path. Do not opportunistically change
`--extend-select`, unknown-key handling, or explicit-file layering semantics.

D4: `--no-cache` means no persistent extraction-cache reads, writes, directory
creation or fingerprint I/O. Per-run config memoization and immutable bridge
vocabulary memoization remain enabled. Document this boundary explicitly; it
avoids changing resolution semantics merely to bypass disposable extraction.

D5: use a dedicated marked namespace inside each configured cache directory;
clean removes only that namespace, never the arbitrary configured parent.
Configuration such as `cache-dir = "."` therefore cannot delete the repository.

D6 (2026-10-24, maintainer amendment): add `.mdc` to Markdown classification
for all relevant commands. Preserve YAML frontmatter bytes during repair,
including delimiters, comments, quoting, whitespace and line endings. Existing
block-level IR support is sufficient to include frontmatter in cache integrity;
do not add YAML field parsing. Full-source lookup hashes continue to invalidate
on frontmatter-only edits, and the stored canonical IR checksum includes the
parsed frontmatter nodes and regions. Future configurable exclusion must be a
separate, versioned policy with fresh source identity and offset
reconstruction; never reuse stale whole-document spans by dropping frontmatter
from the hash.

## Outcomes & retrospective

The reviewed plan incorporates six expert perspectives and was approved for
implementation on 2026-10-24. M1–M4 each passed all six local quality gates. M4
added process-boundary acceptance and frontmatter integrity evidence; the
separate CodeScene refactor cleared the planned findings. ADR 011, the design,
documentation index and roadmap now record the accepted implementation. The
final documentation gates passed, and roadmap 3.3.1 remains separate. No
performance claim has been established.

## Context and orientation

Start with [documentation contents](../contents.md) and
[repository layout](../repository-layout.md). `python/stilyagi/cli_args.py`
registers `check`, `config`, `dump-ir` and `clean`;
`python/stilyagi/cli.py:main` dispatches those commands while preserving the
empty-argument default and version behaviour.

`python/stilyagi/config/{load,parse,resolve,schema,validate}.py` implement TOML
loading, schema defaults, nearest-config resolution, ordered explicit extends
and overrides. `python/stilyagi/cli_config.py` translates command flags.
`python/stilyagi/check_targets.py`, `discovery.py`, `check_inputs.py` and
`cli_io.py:read_source` own discovery, stdin and byte-preserving reads. Reuse
these boundaries, extracting only the minimal shared option interface needed by
both check and dump; update internal callers together, without compatibility
aliases.

`python/stilyagi/engine/extraction.py:extract_document` validates the bridge
payload and creates `model.Document`. `crates/stilyagi-pyext/src/lib.rs` calls
`crates/stilyagi-extract/src/lib.rs`; the latter already offers
`extract_document_with_source_identity`. `crates/stilyagi-ir/src/document.rs`
owns `IrDocument::to_canonical_json`, deterministic pretty JSON with a final
newline. It is project canonicalization, not an assertion of RFC 8785 support.

Existing tests include `tests/test_config_resolution.py`,
`tests/test_config_resolution_caching.py`, `tests/test_cli_args.py`,
`tests/test_check_command.py`, `tests/test_cli_e2e.py`, and
`tests/test_ir_view.py`. Reuse `tests/support/golden_ir.py`,
`tests/support/ir_identity.py`, `tests/support/round_trip.py` and the corpus in
`tests/fixtures/corpus/markdown/`. Rust bridge behaviour tests are in
`crates/stilyagi-pyext/src/bridge_bdd.rs`.

## Conformance basis

The original plan references were verified against the PR's then-current base,
commit `90aaccf9b3baa19f41d09a9f69f172127cd051a2`. The implementation baseline
is the rebased target, commit `765915e5f0ff47899184ed24c9a398c3bc9f2b90`;
revalidate source references against it. There is no separate task-specific
Terms of Reference. The governing documents are [the roadmap](../roadmap.md)
2.2.3, [the design](../stilyagi-design.md) §§4, 7.3 and 13,
[RFC 0003](../rfcs/0003-stilyagi-cli-contract.md) §§3.4–3.6, 5 and 13,
[RFC 0001](../rfcs/0001-stilyagi-intermediate-representation.md), and ADRs
[002][adr002], [003][adr003], [008][adr008] and [009][adr009]. Prerequisites
2.1.1 and 2.2.1 are checked in the roadmap and present in code.

Trace these requirements through delivery: C1 (effective config with origin,
RFC §3.4) goes to M1 and V1; C2 (canonical extraction visibility, §3.6) goes to
M2 and V2; C3 (real bypass and versioned cache identity, §13) goes to M3 and
V3; C4 (cwd-bounded cleanup, §3.5) goes to M3 and V4; C5 (preserved check/fix
behaviour and maintainable operation) goes to all milestones and V5. M4
reconciles these with documentation and observed end-to-end evidence. C6 (the
2026-10-24 maintainer amendment: `.mdc`, frontmatter preservation and cache
policy) goes to M2/M3 and V6. ADR 005 supplies the existing block-level scope.

Required reading includes [complexity and refactoring][complexity],
[Rust fixtures][fixtures], [doctest guidance][doctests],
[dependency injection][injection], [`rstest-bdd`][bdd], and
[documentation style][style].

Use `execplans`, `codegraph-mcp`, `hexagonal-architecture`, `rust-router` and
`python-router`. Route tests through `rust-unit-testing`/`python-testing` and
property obligations through `proptest`/`hypothesis` as needed; use
`rust-verification` before adding a proof kernel. Use `firecrawl-mcp` for
external documentation gaps. `scrutineer` exclusively runs full gates,
sequentially; use `context_pack` for source exchange between agents.

## Proposed command and storage contracts

### Configuration inspection

`config [KEY]` defaults to the working directory; add `--target PATH` to
inspect one existing file or directory without linting it. Accept repeated
`--config`, `--isolated`, `--select`, `--ignore` and `--extend-select` using
the same translation and resolver as check. Support
`--output-format text|json`, default text. No config writes or cache creation
occur.

Use TOML spellings for dotted keys, including `cache-dir`, `lint.select` and
`extract.markdown.gfm`. Without KEY, print all schema values, including
defaults and preserved settings; with KEY, print that leaf or table and its
origins. JSON without KEY is `{"values": {...}, "origins": {...}}`; JSON with
KEY is `{"key": "lint.select", "value": [...], "origins": {...}}`. Origins map
leaf paths to `kind`, `source_file` and `cli_overridden`. Kinds are `default`,
`file`, `inline` and `flag`; defaults have null source and false override. File
origins identify the actual defining file, including inherited values. Inline
and flag origins set `cli_overridden` true and retain the displaced file origin
when present, otherwise null. Tables report each descendant leaf; empty
containers have an origin of their own. Text renders the same facts
deterministically. Unknown KEY, missing target, invalid TOML and cyclic extends
exit 2 with a helpful stderr message and no stdout. Success exits 0. No
user-level fallback.

### IR inspection

`dump-ir [FILES]...` defaults to `.` and recurses for `.md`, `.markdown` and
`.mdc` only. Explicit unsupported files exit 2. Share existing ordering, ignore
rules, deduplication and explicit-file semantics; do not narrow mixed-source
check. Accept `-` once, requiring a Markdown `--stdin-filename`; reject mixed
stdin and file operands with exit 2. Accept config/isolated flags,
`--no-cache`, and `--output-format json` only. Do not accept fix or
rule-selection flags here.

Pass reported path identity through the existing Rust identity API. Keep URI
null unless existing identity helpers supply one consistently. Source bytes,
content hash, spans, ordering and errors come from Rust. An envelope containing
recoverable extraction errors is still useful debug output and exits 0; source
read/decoding failures, unsupported syntax, invalid config, absent IR or bridge
failure exit 2. Buffer serialized output in a spooled temporary stream with an
explicit 1 MiB memory threshold before copying to stdout, so a failure in any
input yields no partial JSON. Spool creation/write failures exit 2 with empty
stdout. A failure of stdout itself can occur after emission begins; report it
without promising rollback of a pipe. Normal output has one final newline.
Logging and errors use stderr only.

### Markdown extensions and YAML frontmatter

Add `"mdc": model.Syntax.MARKDOWN` to the shared extension classifier in
`python/stilyagi/discovery_targets.py`. Apply it to check and dump directory
walks, explicit filenames and `--stdin-filename`; preserve the existing suffix
case policy and ignore semantics. Do not introduce a separate MDC dialect or
change repository documentation-lint globs merely to support runtime inputs.

Reuse the Markdown parser's existing YAML frontmatter recognition and the
whole-block `frontmatter` region defined by ADR 005. A frontmatter-bearing file
must proceed through ordinary Markdown extraction and body repair without an
extra preprocessing script. Retain its existing node/region metadata in dump
output; do not claim a parsed YAML mapping or emit `frontmatter_field`.

For this slice, frontmatter is protected source during repair. In
`python/stilyagi/engine/fix_planning/admissibility.py`, reject edits
overlapping the fenced frontmatter span, including insertion at its opening
boundary or inside it. An insertion at its exclusive end is allowed only if the
complete fenced block remains recognized and byte-identical after
re-extraction; otherwise refuse that fix. Apply the same preservation check to
edits elsewhere that could change frontmatter recognition, such as removing its
closing-line separator. Refuse the whole fix bundle through the existing
non-rule refusal channel, using `fix-error/frontmatter-protected`, rather than
silently dropping one edit. Preserve the established file-atomic conflict
policy. Neither safe nor unsafe fixes may normalize or rewrite YAML in this
slice. Keep the trailing line-ending bytes of the closing fence protected as
part of the source prefix.

YAML robustness, validation of field semantics and a new YAML dependency are
out of scope. Use the existing recognizer's delimiter behaviour; retain
existing parse anomalies and conservative repair refusal for inputs it cannot
classify safely. Do not describe unrecognized malformed content as proven safe
to repair.

### Cache and bypass

Resolve per-file configuration before cached extraction. Default cache root is
`<invocation cwd>/.stilyagi_cache`; relative `cache-dir` values are relative to
the invocation cwd, consistently with the current repository-relative schema.
Absolute custom roots may be used for caching but clean never leaves cwd.

Store only canonical Markdown IR in `<cache-dir>/stilyagi-v1/`, alongside an
exact marker: `owner.json` containing `{"owner":"stilyagi","format":1}` plus a
newline. Entry names are 64 lowercase hexadecimal digits followed by `.json`;
temporary names are `.tmp-` followed by 32 lowercase hexadecimal digits. Use
one classifier shared by storage and cleanup. Refuse to adopt an existing
unmarked namespace; fall back to uncached extraction with a warning. Cache
identities contain format version, original UTF-8 byte hash, syntax, reported
source identity, effective configuration hash, installed native-extension
binary digest, package version, enabled built-in pack signature and inactive
NLP signature. Hash normalized config values, not provenance or incidental
mapping insertion order. Use `inactive` explicitly for systems that are not
executed, retaining configured values in the config hash. Hash the native
extension once per cached invocation; its binary digest invalidates development
rebuilds even without version bumps.

Include a SHA-256 checksum of the complete canonical IR bytes in the cache
entry. This checksum includes the parser's frontmatter node/region
representation (text, spans, segments and format metadata); it does not require
semantic YAML parsing. Compute it after fresh extraction and verify it before
hydration on a hit. Lookup remains based on the original full-source hash, so
frontmatter-only changes, including comments or layout, invalidate the entry
and refresh body spans and line indices. Do not parse the document just to
locate a cache entry.

Leave room for a future versioned frontmatter-inclusion policy in cache
identity, with inclusion fixed to enabled in this slice. Do not add a
configuration switch yet or reinterpret `extract.markdown.frontmatter` as cache
exclusion. Ignoring frontmatter could only reuse body data after reconstructing
the current document hash, prefix, offsets, line index and dump IR. Existing
block-level IR support means the proposed no-IR fallback (ignore
frontmatter-only changes) is not taken.

On hit, validate the outer format/key and canonical IR checksum in Python, then
deserialize canonical IR through a Rust bridge `hydrate_ir_json` using existing
`IrDocument` serde types. Reuse Rust's region-to-bridge conversion and Python's
typed payload adapter. Reject malformed known fields and inconsistent source
hash/syntax/identity; retain supported extensible metadata. This uses one
schema, rather than a second Python definition. Cache hydration must not
increment extraction-attempt or extraction-outcome metrics. Never use pickle.
Invalid, truncated or stale data is a miss with verbose evidence; unavailable
storage warns once per normalized root and runs uncached without changing lint
exit status. Later requests for that construction-failed root count as bypasses
without repeating the warning. Read and write failures discard the open store;
later requests may retry construction. Write through an exclusive temporary
file in the namespace and atomic replace; never follow a symlink for a marker,
cache entry or temporary path. For each directory-chain walk, open the
caller-selected invocation cwd once as the trusted descriptor anchor, then
refuse symlinks in cache-root components beneath it. Absolute cache roots
outside cwd retain a strict no-follow walk from the filesystem root. Cleanup
opens its selected cwd once and traverses descendants without following links.
Apply descriptor-relative safety to storage as well as cleanup. A removed
namespace during a write is a recoverable cache miss/write failure. This cache
is bounded in feature scope, not disk capacity: entries accumulate until clean.
Document that limitation and avoid adding eviction policy in this slice.
Disk-full cache writes fall back to uncached operation; a full development disk
or `/tmp` during implementation requires stopping and notifying the maintainer.

No-cache chooses the direct extraction path before constructing the disk-cache
adapter or hashing its native binary. It performs zero persistent-cache I/O,
including `stat`, marker reads or directory creation. Stdin always bypasses
persistent caching. Always execute current rule analysis and fix planning, and
keep post-fix verification extraction fresh so a hit cannot mask applied edits.
Expose hit, miss, invalid, bypass and write-failure events via existing logging
and bounded counters; never place file paths in metric labels or JSON stdout.

### Cleanup

`clean` has no target arguments: its boundary is invocation cwd. Traverse
without following symlinks, including ignored directories so ignored caches are
found, but prune `.git` metadata. Recognize `stilyagi-v1` by name and exact
marker, regardless of the configured parent name. Delete only recognized entry
files and cache temporary files, then marker/namespace only if no unrecognized
content remains. Never remove the configured parent. Unmarked lookalikes and
unknown files survive. Missing caches succeed. Report removed counts and
preserved unknown entries; report permission/unsupported-platform failures to
stderr and exit 2 after attempting other eligible namespaces. Success exits 0.

Use descriptor-relative traversal/deletion and refuse unsupported safe deletion
facilities, rather than checking a resolved path once and then trusting it. A
symlink inside a recognized namespace may be unlinked as a link but its target
must survive. Directory symlinks elsewhere are skipped. Concurrent writers may
repopulate caches; clean is idempotent best-effort cleanup, not a global lock
or a promise of permanent emptiness. No configuration or plugin loading is
needed.

## Interfaces and dependencies

Add small command modules `cli_config_command.py`, `cli_dump_ir.py` and
`cli_clean.py`; keep `cli.py:main` as dispatch. Introduce command-specific
immutable options and reuse config overrides without fabricating CheckOptions
for unrelated commands. Add `config/provenance.py` with typed origin and
resolved-result values. One resolution path produces values plus origins;
existing value-only calls consume its values, with no second resolver algorithm.

Expose a Python extraction result containing `document` and `canonical_json` in
`engine/extraction.py`, with `extract_document` delegating to the shared
adapter. Extend the PyO3 request parser and `_stilyagi_rs.pyi` to pass optional
source identity to the existing Rust extractor; update all internal callers and
tests. Add `hydrate_ir_json` to the PyO3 bridge/stub with Rust serde
deserialization and shared bridge conversion, tested with malformed known
fields and round trips. Do not create a second parser or change IR
serialization.

Define an application-owned narrow extraction callable/protocol for the check
and dump coordinators. Put request/key data and policy in `cache/model.py`,
coordination in `cache/extraction.py`, and filesystem operations in
`cache/storage.py` and `cache/clean.py`. The service takes an extraction
request (source, syntax, identity, effective config) and returns the extraction
result; the cache adapter exposes read/write of validated serialized artefacts,
not configuration discovery. Pure extraction must remain usable without a
cache. Sweep for equivalent helpers before adding each one; document the
ownership and reuse policy in the developer guide. Avoid speculative ports for
future NLP.

## Verification plan

V1: effective values equal check resolution under the same inputs; each leaf's
origin names its winning layer. Add `tests/test_config_inspection.py` with
pytest cases for defaults, same-directory precedence, nearest config, ordered
extends, cycles, inline and dedicated overrides, isolated mode and unknown
keys. Use Hypothesis in `tests/test_config_provenance_properties.py` to
generate acyclic chains and nested overrides, comparing against an independent
simple layer-fold oracle. Include empty tables, lists and overwritten inherited
leaves. A seeded reversed-precedence mutation must fail. Snapshot text/JSON
with syrupy, normalizing only temporary path prefixes. Discharge requires exact
values and origins, not merely snapshot agreement.

V2: dump preserves canonical bytes and source identity, source hashes and UTF-8
spans. Add pytest tests in `tests/test_dump_ir.py`, syrupy snapshots for one,
multiple and empty results, and real subprocess tests in
`tests/test_cli_e2e.py`. Use existing Unicode, CRLF, frontmatter, table and
suppression fixtures. Add `rstest` identity cases and `rstest-bdd` scenarios at
the PyO3 boundary; use `googletest` matchers for structured contracts,
`pretty_assertions` for equality diffs and `insta` only for stable canonical
output variants. Extend existing bridge test modules or split by feature to
remain below 400 lines. Generated Unicode sources and source identities in
proptest must preserve content hashes, line indices and region spans under
identity changes. A mutation dropping the last byte or changing CRLF to LF must
be detected. Compare single-file output to Rust's canonical serializer, not an
independently invented Python format.

V3: cold, warm and bypassed extraction produce identical IR and check outcomes;
changing each key dimension prevents reuse. Add
`tests/test_extraction_cache.py` and `tests/test_cache_properties.py`, using an
injected counting extractor, real temporary storage and Hypothesis sequences of
read, source/config/version changes, corruption, clean and bypass. Generate
valid Markdown plus empty and multibyte witnesses without heavy filtering.
Record hit/miss/bypass classifications. Assert cold=one Rust extraction,
warm=zero, bypass=one, with independent cache counters. A hit must skip actual
extraction; no-cache must make zero calls to a trap storage adapter and leave
real cache bytes and mtimes untouched. Cold no-cache creates nothing. Seed a
key mutation omitting content or config and prove the tests fail. Test every
remaining key dimension independently, truncated entries and interrupted
replace. This proves repository-owned selection and integration, not SHA-256
collision resistance.

V4: cleanup removes only owned disposable state beneath cwd and is repeatable.
Add `tests/test_cache_clean.py` with real directories, custom roots, ignored
roots, source sentinels, unmarked lookalikes, outside symlink targets, cwd as
cache-dir, missing roots and injected permission failures. Generate small trees
in Hypothesis and assert all non-owned bytes survive two clean operations. Seed
following a directory symlink or deleting the configured parent; the
outside/source sentinel must detect it. Also substitute a symlinked cache-root
ancestor or namespace during read/write and prove the outside sentinel and
namespace stay untouched by check. Inject replacement between discovery and
deletion to exercise descriptor-based safety. Filesystem race resistance also
depends on platform primitives; finite tests do not prove arbitrary kernel
schedules. Explicitly test refusal on unsupported safe-deletion platforms.

V5: unit, BDD and subprocess evidence must agree. Preserve existing check
summaries, diagnostic/fix streams, error codes, mixed syntax and post-fix
checks. Add `features/markdown_cli_inspection.feature` with pytest-bdd bindings
in `tests/test_markdown_cli_inspection_bdd.py`. Use the installed package
through `tests/support/subprocess_env.py` for subprocess tests, with actual
temporary files rather than mocks at the CLI boundary. Extend real bridge BDD
for the Rust identity seam. Do not add a second Rust CLI test harness.

V6: all three Markdown suffixes accept frontmatter, preserve it during repair
and expose its current representation in dump/cache data. Parameterize
discovery, CLI, stdin, diff and fix tests over `.md`, `.markdown` and `.mdc`.
Add `tests/test_frontmatter_cli.py` and focused Rust fixture/BDD cases using
existing frontmatter fixtures, LF/CRLF, Unicode, comments, quoted scalars and
multiline values. Use an injected body-fixing rule to prove a real body repair
occurred while the original fenced prefix, including its closing newline,
stayed exactly equal. Also inject frontmatter-targeting edits, cross-boundary
edits and boundary insertions; each unsafe proposal must be refused without
changing the prefix. Test both fix applicability levels and stdin output, never
writing stdin paths.

Extend V3 properties to generate frontmatter-only mutations with unchanged
bodies, including a longer prefix and more lines. Each mutation must miss the
cache; new dump spans must re-slice the current body and the whole-source hash
must match current bytes. Compare cached/uncached output. Corrupt only a
frontmatter field in the cached IR without updating its checksum and require a
miss. These are cache/repair properties, not a YAML fuzzing campaign: generate
recognized valid fenced blocks. A seeded mutation stripping frontmatter from
the lookup hash or permitting an edit to its prefix must fail. Snapshot
existing block metadata, not a nonexistent YAML field schema. Do not conflate a
content hash used for lookup with the canonical IR checksum used for
stored-data integrity.

Trusted assumptions are Rust's existing canonical serializer and extractor,
PyO3's documented conversion boundary, SHA-256 collision resistance, the Python
JSON/TOML interfaces, and the operating system's descriptor-relative filesystem
and atomic-replace semantics. Test repository composition against these real
interfaces, rather than attempting to prove third-party internals.

Frontmatter preservation is a new contractual repair policy (V6). Its
obligation is that every emitted or written repair retains the original
frontmatter prefix bytes and recognition. Enforce it with a mandatory final
candidate check in `python/stilyagi/engine/fix_pipeline.py`, after byte
splicing and before diff emission, stdin output or disk writes. Compare the
actual candidate prefix with the original and re-extract the candidate to check
the frontmatter boundary; refuse the candidate if either check fails.
Preliminary span rejection alone does not discharge this obligation.

A Rust proof kernel was considered. The existing repair/splice pipeline is
Python-owned; a detached proof of an interval model would not establish that
its actual output passes this boundary. This plan therefore uses exhaustive
checking of each concrete candidate's prefix bytes at runtime, plus V6's
properties, negative controls and real pipeline tests to establish wiring. This
is not a formal proof over all executions, parser behaviour or filesystem
races, and no such claim should be made. It adds no mathematical axiom. Do not
introduce a Rust extension merely to restate prefix equality as a theorem. If
implementation moves repair policy into Rust or introduces another lemma
requiring universal proof, revise the plan to include a substantive Verus proof
with inhabited assumptions and implementation correspondence. The explicitly
planned V6 policy itself is not an unplanned deviation or stop trigger.

## Behaviour specification

Implement the following specification in the named Python feature file, using
scenario outlines for the detailed partitions in V1–V6:

```gherkin
Feature: Inspect and maintain the Markdown CLI
  Scenario: Explain an overridden inherited value
    Given a Markdown project with an inherited lint selection
    When I inspect lint.select with an inline override as JSON
    Then the effective value matches check configuration
    And its origin reports a CLI override and the inherited file

  Scenario: Dump multiple documents without rewriting their source
    Given two Markdown files containing Unicode and CRLF lines
    When I dump their IR as JSON
    Then stdout is one array containing their canonical IR documents
    And the source bytes are unchanged

  Scenario: Failed extraction does not emit partial JSON
    Given one readable and one unreadable Markdown file
    When I dump their IR
    Then stdout is empty
    And the exit status is 2

  Scenario: Bypass a warm extraction cache
    Given a Markdown file with a populated extraction cache
    When I check the file with no-cache
    Then extraction runs again with identical diagnostics
    And no persistent cache is read or changed

  Scenario: Repair Markdown with YAML frontmatter
    Given an mdc file with YAML frontmatter and a fixable body diagnostic
    When I apply the body fix
    Then the body is repaired
    And the entire frontmatter prefix is byte-identical

  Scenario: Frontmatter-only edits refresh cached source coordinates
    Given a cached Markdown file with YAML frontmatter
    When I add a frontmatter line without changing the body
    Then the next check misses the extraction cache
    And dumped body spans match the current source bytes

  Scenario: Clean only owned cache data
    Given owned cache entries beside source files and an outside symlink
    When I clean twice from the project directory
    Then owned cache entries are absent
    And source files and the outside symlink target are unchanged
```

Rust bridge BDD must additionally specify: given Markdown and a reported path,
when extraction receives that identity, then canonical document metadata
carries it and every span/hash equals anonymous extraction. This tests the real
Rust boundary with `rstest-bdd`, not a Python-only surrogate.

## Milestones and plateaus

M1 delivers C1/V1: add red provenance and command tests, implement one shared
resolution-with-origin path and config command, then refactor and document it.
Update RFC §3.4 and the user guide with exact output/target/key contracts. End
with a usable config command and unchanged check results. Dump/cache remain
open. Recovery is reverting the complete milestone commit; no stored state
exists.

M2 delivers C2/V2 and C6/V6: add red identity/serialization/CLI tests, expose
source identity through PyO3, retain canonical JSON and implement dump
coordination. Add `.mdc` to shared discovery and stdin classification, and
enforce verbatim frontmatter preservation in fix planning. Amend RFC §§3.6 and
7, the design syntax list, ADR 008 and the user guide with extensions, framing,
stdin, frontmatter preservation and failures. Keep ADR 005 field parsing
deferred. End with usable uncached dump output; cache work remains open.
Recovery is reverting the whole milestone including bridge stub/callers; no
temporary compatibility layer.

M3 delivers C3/C4/C6 and V3/V4/V6: add red cache and cleanup tests, implement
the owned namespace, complete identity, validated hydration and injected
extraction service. Wire Markdown check/dump to it, preserve fresh post-fix
extraction, then implement strict bypass and safe cleanup. Include canonical IR
checksums and frontmatter-only invalidation evidence before declaring the cache
usable. Update RFC §13, design §7.3 and user/developer documentation in the
same coherent milestone. Cache, bypass and clean ship together: do not land
persistent writes without cleanup. Recovery is reverting the milestone; cache
data can be ignored or removed through the tested clean command. There is no
deployed predecessor format to migrate.

M4 closes C5/V5 and all trace links: run real CLI workflows, reconcile docs and
ADR status with approved decisions, review complexity and property non-vacuity,
then mark roadmap 2.2.3 done only after all required gates pass. Keep 3.3.1
open. Update `docs/contents.md`, `docs/users-guide.md`,
`docs/developers-guide.md`, `docs/repository-layout.md` and the design as
appropriate. The design document is the component architecture reference for
these new internal boundaries.

At every milestone, verify the assigned requirements, approved design, upstream
assumptions, interfaces, dependencies, trust boundaries and stored formats;
record evidence beside C1–C6/V1–V6. Update living sections before committing.
No compatibility shim is required for these internal/pre-1.0 source APIs.

## Concrete steps and validation

Work from the repository root. After approval, read this plan and AGENTS.md,
check branch/status and revalidate prerequisite symbols. Run focused tests
before production edits, save the expected missing-behaviour failure, implement
the minimum change, rerun, then refactor. Do not commit deliberately failing
tests. For Python, use the Makefile-selected virtualenv interpreter after
`make build`; for example
`.venv/bin/python -m pytest tests/test_config_inspection.py -v` when `.venv` is
the configured environment. Existing Makefile test/build targets are
authoritative if the environment differs. Rust focused tests use the workspace
Cargo configuration and compiler wrappers; select the actual added test names.

After **each major milestone**, delegate these commands to scrutineer in this
order, with shell `pipefail` and separate `/tmp` tee logs. The order matches
the installed scrutineer's required sequence:

```bash
set -o pipefail
make check-fmt 2>&1 | tee /tmp/check-fmt-stilyagi-2-2-3-cli-sub-commands-for-markdown.out
make lint 2>&1 | tee /tmp/lint-stilyagi-2-2-3-cli-sub-commands-for-markdown.out
make typecheck 2>&1 | tee /tmp/typecheck-stilyagi-2-2-3-cli-sub-commands-for-markdown.out
make test 2>&1 | tee /tmp/test-stilyagi-2-2-3-cli-sub-commands-for-markdown.out
make markdownlint 2>&1 | tee /tmp/markdownlint-stilyagi-2-2-3-cli-sub-commands-for-markdown.out
make nixie 2>&1 | tee /tmp/nixie-stilyagi-2-2-3-cli-sub-commands-for-markdown.out
```

Stop at the first failure, inspect the captured log, fix the cause and rerun
the affected gate before continuing sequentially. Run `make fmt` for
documentation changes; inspect its diff and preserve unrelated files. Never
hand-edit generated `typos.toml`. Documentation-only reconciliation uses the
formatting, spelling/Markdown and Mermaid gates; each implementation milestone
uses all six gates above.

Observable acceptance uses a disposable Markdown project with `notes.md`:

```bash
stilyagi config lint.select --target notes.md --output-format json
stilyagi dump-ir notes.md --output-format json
stilyagi check notes.md
stilyagi check notes.md --no-cache
stilyagi clean
stilyagi clean
```

Expect config JSON with effective selection and origins; one parseable
canonical IR document with correct path, hash and byte spans; identical
cold/warm/bypass check results; and two successful cleanup invocations that
preserve notes.md. Run check twice before bypass to demonstrate a real cache
hit using counting instrumentation and verbose events. Do not infer a hit
merely from timing. Capture text and JSON variants, partial failures and
post-fix verification in subprocess acceptance. Empty built-in rules currently
mean synthetic injected rules are needed for diagnostic/fix unit tests; do not
claim rule-engine delivery.

## Idempotence and recovery

Tests create isolated fixture directories and never clean the repository cache
as setup. Generated cache data is disposable and versioned; no migration or
source rewrite is performed. Repeat checks and clean safely. Concurrent writers
can create new disposable entries after cleanup. Preserve the approved plan and
evidence when reverting an implementation commit; use normal revert for shared
history and do not reset another agent's changes.

## Artefacts and notes

Wyvern evidence packs: `pk_sz72iah5` (CLI/config/cache boundaries); contract/IR
pack: `pk_lje4mvtx`; architecture review pack: `pk_hwyefwax`; root planning
pack: `pk_5kozxmci`. Packs are supporting evidence, not prerequisites for
executing this self-contained plan. CodeGraph workspace indexing timed out
after 300 seconds; source references were verified with bounded direct reads
instead. No service was restarted.

Planning validation on 2026-10-14: `make fmt`, `make check-fmt`,
`make markdownlint` (including spelling) and `make nixie` passed. Scrutineer
logs use `/tmp/ACTION-49853f07-73ba-4ebd-8c88-844f84cdf038-` followed by
`2-2-3-cli-sub-commands-for-markdown-planning.out`, where ACTION is `check-fmt`,
`markdownlint` or `nixie`. No generated spelling change occurred. Full code
gates are reserved for the implementation milestones specified above.

Expert review synthesis: Pandalump required Rust-owned cache hydration and
separate extraction metrics; Wafflecat endorsed staged extraction-only caching;
Telefono accepted explicit framing/provenance and persistent-only bypass;
Doggylump required descriptor-safe storage as well as deletion; Buzzy Bee
required an explicit spool threshold and honest disk-growth limits; Dinolump
required one owned-file classifier. All were incorporated. The key trade-off is
simpler manual cleanup rather than an eviction subsystem, with no analysis
cache yet.

Firecrawl research on 2026-10-14 confirmed that
[Ruff's CLI documentation](https://docs.astral.sh/ruff/configuration/)
describes recursive cleanup and `--no-cache` as disabling cache reads. This
plan deliberately specifies the stronger no-read/no-write contract for Stilyagi.
[Python 3.14 shutil documentation](https://docs.python.org/3.14/library/shutil.html)
limits symlink-resistant recursive removal to platforms with the required
file-descriptor primitives. The implementation must test and enforce that
boundary; path normalization alone does not supply it.

Revision note (2026-10-14): initial draft ties current source boundaries to
explicit command contracts, staged extraction caching and verification
evidence. All implementation work remains gated on approval.

Revision note (2026-10-14, expert review): specify Rust hydration, metric
ownership, descriptor-safe cache access, exact owned filenames, finite output
spooling and manual disk reclamation. These tighten M2/M3 acceptance without
authorizing execution.

[adr002]: ../adr-002-packaging-boundary.md
[adr003]: ../adr-003-v1-contract-scope.md
[adr008]: ../adr-008-v1-discovery-defaults.md
[adr009]: ../adr-009-safe-fix-planning-and-conflict-resolution.md
[complexity]: ../complexity-antipatterns-and-refactoring-strategies.md
[fixtures]: ../rust-testing-with-rstest-fixtures.md
[doctests]: ../rust-doctest-dry-guide.md
[injection]: ../reliable-testing-in-rust-via-dependency-injection.md
[bdd]: ../rstest-bdd-users-guide.md
[style]: ../documentation-style-guide.md

Revision note (2026-10-24): add `.mdc` across Markdown CLI inputs, protect YAML
frontmatter during repair and verify existing whole-block IR support. Retain
full-source cache invalidation and checksum the parsed IR representation; defer
configurable exclusion and YAML parser robustness. Extend M2/M3 and V6 without
approving implementation.

Revision note (2026-10-24): implementation approval was recorded before work.
Rebase onto `origin/main` preserved its ADR 010 and renumbered the cache ADR to
011; the resulting candidate was published to PR #226 with a verified lease.
Markdown gates pass. Three functional-suite attempts timed out waiting for the
shared Cargo package-cache lock in nested UI tests, so full implementation
gates remain pending. M1 has since started with red CLI and provenance tests;
its focused command, resolver and generated-chain tests pass, while the full
milestone gates remain pending.

Revision note (2026-10-25): M1 formatting, typecheck and lint pass. Its first
full test run reached 355/357, then both trybuild UI binaries timed out while
sharing one target lock. A serial Nextest test group now covers those binaries;
the full M1 gate sequence remains pending.

Revision note (2026-10-25): after serialization, the UI test
`sha2_0_11_digest_lowerhex_formatting_is_rejected` still exceeded its 600 s
allowance under a heavily queued host. Its nested check completed in 4m13s, but
the test timed out at 600s after repeated package-cache and compiler-admission
waits. Increase the trybuild allowance to 900s while retaining the 18m Nextest
whole-run budget. A focused timeout-contract run rejected 19m because 19m plus
the termination procedure and 10m cold-build allowance exceeds the 1,800s Cargo
watchdog. The delegated gate order now follows the installed scrutineer's fixed
sequence; all gates remain mandatory and sequential. Rerun the complete M1 gate
sequence before accepting the milestone.

Revision note (2026-10-25): the next full run passed 356/357 tests, but its
18-minute Nextest global timeout stopped the second serial UI test after about
603 seconds. With the first UI test taking about 477 seconds, the global budget
did not leave enough time for the second test's 900-second allowance. Increase
the global timeout to 26 minutes, the Cargo watchdog to 2,400 seconds, and the
coverage job ceiling to 75 minutes. The timeout contracts and developers' guide
now hold that ordering and the observed trybuild sequence. Rerun all M1 gates
before accepting the milestone.

Revision note (2026-10-25): the 26-minute run passed 356/357 tests. The final
`stilyagi-pyext::compile_tests::compile_time_ui` test reached its 900-second
limit while compiling `tests/ui/pass/pyo3_detach.rs`; its nested build spent
about 8 minutes compiling the dev profile. Raise the trybuild allowance to
1,500 seconds and the Nextest whole-run budget to 33 minutes. The Cargo
watchdog is now 2,700 seconds and both coverage job ceilings are 80 minutes.
Timeout contracts and the developers' guide reflect those values. Rerun all M1
gates before accepting the milestone.

Revision note (2026-10-25): the 33-minute candidate passed lint, typecheck,
Nextest (357/357), and Rust doctests. Its Python suite reported 757 passed and
three failures: the generated provenance oracle updated the wrong mapping
during recursion, the Maturin wheel snapshot omitted the new config command
module, and the runner-placement contract still expected 60-minute ceilings.
The UI tests passed in 143 s and 464 s. Correct those contracts and rerun the
full gate sequence.

Revision note (2026-10-25): the focused provenance, timeout, and placement
tests passed 36/36, and the refreshed Maturin wheel snapshot passed with all
three M1 modules in its package listing. The next full run passed
`make check-fmt` but `make lint` stopped at Pylint R0913 because the
independent oracle helper took five arguments. Its recursion now uses a local
helper that closes over the source and origin state. Rerun the sequential gates.

Revision note (2026-10-25; superseded by the successful run below): the next
full run passed `make check-fmt`, `make lint` and `make typecheck`, but
`make test` timed out after 1,500 seconds in
`stilyagi-pyext::compile_tests::compile_time_ui`, while compiling
`tests/ui/pass/pyo3_pymodule.rs`. Nextest reported 356/357 tests passed. The
captured log contains repeated package-cache lock messages and a long shared
compiler queue. The plan's three-repair tolerance is met, so M1 is BLOCKED
pending the user's acceptance of a next gate action; do not further increase
timeout budgets or begin M2 yet. The status update itself passed
`make check-fmt`, `make markdownlint` (0 issues), and `make nixie` (all
diagrams valid), followed by `make fmt` with no reported formatting changes.

Proposed deviation for user acceptance (superseded by the successful run
below): allow one final full gate run with the trybuild allowance raised from
1,500 s to 1,800 s, Nextest `global-timeout` raised from 33 m to 36 m, and
`RUN_RUST_CARGO_WAIT_TIMEOUT` raised from 2,700 s to 3,000 s. Keep the 80 m
workflow job ceiling unchanged. If `make test` fails again, leave M1 BLOCKED
without another budget change. This changes the M1 timeout contracts and their
tests/documentation, but keeps the existing acceptance requirement that the full
`make test` gate pass before M1 completes.

Revision note (2026-10-25): the doctest for `_run_config_inspection` failed
because `_ConfigInspectionOptions` was imported only under `TYPE_CHECKING`. Add
the concrete import to the example; its focused doctest passed. The corrected
candidate then passed the full sequential gate set: check-fmt, lint, typecheck,
test, markdownlint and nixie. Nextest passed 357/357, both Python test stages
passed (including 154 tests and 4 snapshots in the second stage), and all
workspace doctests passed. No timeout budget changes were needed.

Resolution note (2026-10-25): the successful rerun used the existing timeout
budgets after temporary disk pressure had been relieved. M1 is complete; the
proposed 1,800-second trybuild allowance and related budget changes were not
adopted.
