# Deliver the Markdown inspection and cache commands

Status: DRAFT — implementation requires explicit maintainer approval.

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
includes one bounded Markdown extraction cache: analysis and fix planning still
run on every invocation. Independent analysis caching remains roadmap 3.3.1
work.

## Constraints

- This delivery is planning only until explicit approval. Do not mark 2.2.3 done
  in this PR. The implementor must mark it done after all acceptance evidence
  passes, and update this plan to COMPLETE only after conformance
  reconciliation.
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
- [ ] Commit and publish the reviewed draft for maintainer approval.
- [ ] Obtain explicit implementation approval.
- [ ] M1: effective configuration inspection and provenance.
- [ ] M2: canonical Markdown IR inspection and bridge identity.
- [ ] M3: extraction cache, strict bypass, and safe cleanup.
- [ ] M4: end-to-end acceptance, documentation and roadmap completion.

## Surprises & discoveries

`CheckOptions.no_cache` is already parsed but its help explicitly describes a
no-op. No persistent cache manager exists. `ConfigResolver` has only per-run
in-memory discovery, raw-table and resolved-table caches; bridge vocabulary is
also memoized. A useful cache-control command therefore needs a real, bounded
persistent cache, rather than merely removing the no-op wording.

`ConfigResolver.resolve_config_for_path` returns values without provenance.
Provenance cannot be recovered accurately from the final dataclass. It must be
retained while following `extend` and applying override layers.

`check_execution.check_one_file` currently extracts before resolving per-file
configuration. M3 must move configuration resolution before extraction to build
a configuration-sensitive key, preserving existing error classification and
phase measurements.

The PyO3 bridge serializes canonical JSON but the Python adapter discards its
string after parsing. Rust already has `extract_document_with_source_identity`;
the bridge currently uses anonymous identity. Reuse that Rust entrypoint
instead of patching serialized JSON.

## Decision log

All implementation decisions below are proposals for approval, recorded on
2026-10-14. [ADR 010](../adr-010-markdown-cli-inspection-and-cache.md) records
the substantive framing and persistent-state choices; it remains Proposed.

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

## Outcomes & retrospective

The reviewed plan and Proposed ADR are ready for maintainer review. The six
expert perspectives have been reconciled and documentation gates passed. No
feature code has been implemented, no performance claim has been established,
and approval remains outstanding. Record actual milestone results and any
undischarged obligations here during implementation.

## Context and orientation

Start with [documentation contents](../contents.md) and
[repository layout](../repository-layout.md). `python/stilyagi/cli_args.py`
registers only `check`; `python/stilyagi/cli.py:main` sends every parsed
command to `run_check`. Preserve the empty-argument default and version
behaviour while adding explicit dispatch.

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

The baseline for all local references is commit
`90aaccf9b3baa19f41d09a9f69f172127cd051a2`. There is no separate task-specific
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
reconciles all five with documentation and observed end-to-end evidence.

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

`dump-ir [FILES]...` defaults to `.` and recurses for `.md` and `.markdown`
only. Explicit unsupported files exit 2. Share existing ordering, ignore rules,
deduplication and explicit-file semantics; do not narrow mixed-source check.
Accept `-` once, requiring a Markdown `--stdin-filename`; reject mixed stdin
and file operands with exit 2. Accept config/isolated flags, `--no-cache`, and
`--output-format json` only. Do not accept fix or rule-selection flags here.

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

On hit, validate the outer format/key in Python, then deserialize canonical IR
through a Rust bridge `hydrate_ir_json` using existing `IrDocument` serde
types. Reuse Rust's region-to-bridge conversion and Python's typed payload
adapter. Reject malformed known fields and inconsistent source
hash/syntax/identity; retain supported extensible metadata. This uses one
schema, rather than a second Python definition. Cache hydration must not
increment extraction-attempt or extraction-outcome metrics. Never use pickle.
Invalid, truncated or stale data is a miss with verbose evidence; unavailable
storage warns and runs uncached without changing lint exit status. Write
through an exclusive temporary file in the namespace and atomic replace; never
follow a symlink for a marker, cache entry or temporary path. Open and anchor
every configured-root and namespace component without following symlinks; a
symlinked root/ancestor or replaced namespace triggers uncached fallback. Apply
descriptor-relative safety to storage as well as cleanup. A removed namespace
during a write is a recoverable cache miss/write failure. This cache is bounded
in feature scope, not disk capacity: entries accumulate until clean. Document
that limitation and avoid adding eviction policy in this slice. Disk-full cache
writes fall back to uncached operation; a full development disk or `/tmp`
during implementation requires stopping and notifying the maintainer.

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

Add small command modules `cli_inspect_config.py`, `cli_dump_ir.py` and
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

Trusted assumptions are Rust's existing canonical serializer and extractor,
PyO3's documented conversion boundary, SHA-256 collision resistance, the Python
JSON/TOML interfaces, and the operating system's descriptor-relative filesystem
and atomic-replace semantics. Test repository composition against these real
interfaces, rather than attempting to prove third-party internals.

No new mathematical axiom or pure business-rule kernel is proposed: precedence
is existing policy and the new cache is an optimization over unchanged
extraction. The introduced operational invariants above require properties and
real boundary tests. If implementation introduces new contractual business
logic or a lemma requiring universal proof, stop and revise the plan to prefer
a small Rust kernel and substantive Verus proof. State its inhabited
assumptions, implementation correspondence and trusted boundary; never assume
its conclusion or label finite testing an exhaustive proof.

## Behaviour specification

Implement the following specification in the named Python feature file, using
scenario outlines for the detailed partitions in V1–V5:

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

M2 delivers C2/V2: add red identity/serialization/CLI tests, expose source
identity through PyO3, retain canonical JSON and implement dump coordination.
Amend RFC §3.6 and the user guide with framing, stdin and failures. End with
usable uncached dump output; cache work remains open. Recovery is reverting the
whole milestone including bridge stub/callers; no temporary compatibility layer.

M3 delivers C3/C4 and V3/V4: add red cache and cleanup tests, implement the
owned namespace, complete identity, validated hydration and injected extraction
service. Wire Markdown check/dump to it, preserve fresh post-fix extraction,
then implement strict bypass and safe cleanup. Update RFC §13, design §7.3 and
user/developer documentation in the same coherent milestone. Cache, bypass and
clean ship together: do not land persistent writes without cleanup. Recovery is
reverting the milestone; cache data can be ignored or removed through the
tested clean command. There is no deployed predecessor format to migrate.

M4 closes C5/V5 and all trace links: run real CLI workflows, reconcile docs and
ADR status with approved decisions, review complexity and property non-vacuity,
then mark roadmap 2.2.3 done only after all required gates pass. Keep 3.3.1
open. Update `docs/contents.md`, `docs/users-guide.md`,
`docs/developers-guide.md`, `docs/repository-layout.md` and the design as
appropriate. The design document is the component architecture reference for
these new internal boundaries.

At every milestone, verify the assigned requirements, approved design, upstream
assumptions, interfaces, dependencies, trust boundaries and stored formats;
record evidence beside C1–C5/V1–V5. Update living sections before committing.
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
order, with shell `pipefail` and separate `/tmp` tee logs:

```bash
set -o pipefail
make check-fmt 2>&1 | tee /tmp/check-fmt-stilyagi-2-2-3-cli-sub-commands-for-markdown.out
make typecheck 2>&1 | tee /tmp/typecheck-stilyagi-2-2-3-cli-sub-commands-for-markdown.out
make lint 2>&1 | tee /tmp/lint-stilyagi-2-2-3-cli-sub-commands-for-markdown.out
make test 2>&1 | tee /tmp/test-stilyagi-2-2-3-cli-sub-commands-for-markdown.out
make markdownlint 2>&1 | tee /tmp/markdownlint-stilyagi-2-2-3-cli-sub-commands-for-markdown.out
make nixie 2>&1 | tee /tmp/nixie-stilyagi-2-2-3-cli-sub-commands-for-markdown.out
```

Stop at the first failure, inspect the captured log, fix the cause and rerun
the affected gate before continuing sequentially. Run `make fmt` for
documentation changes; inspect its diff and preserve unrelated files. Never
hand-edit generated `typos.toml`. For this documentation-only planning PR, use
the documentation formatting, spelling/Markdown and Mermaid gates; the four
implementation gates above remain mandatory for each implementation milestone.

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
