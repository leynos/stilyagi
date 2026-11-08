# Implement builtin rule discovery commands (2.3.2)

This ExecPlan is a living design and delivery document. Keep its constraints,
progress, decisions, conformance basis, and verification evidence current.

Status: DRAFT — awaiting explicit approval before implementation.

Planning base: `48c24f9d18bbd340a893a4fce11bbb3c08ec47a2` (2026-11-08). Working
branch: `2-3-2-stilyagi-rule-code-and-stilyagi-rules`, tracking
`origin/2-3-2-stilyagi-rule-code-and-stilyagi-rules` after publication.

## Purpose / big picture

Maintainers will discover every shipped builtin rule through `stilyagi rules`
and inspect its policy, options, examples, and limitations through
`stilyagi rule CODE`. Both commands will offer deterministic text and JSON
(JavaScript Object Notation) output. A maintainer should be able to explain why
`TERM001` needs configuration and why `STY001` is not safely auto-fixable
without reading source code.

This is a planning-only change. Implementation and the roadmap completion
checkbox remain pending approval. The eventual implementation completes roadmap
2.3.2, not the broader documentation work in 2.3.3.

## Constraints

- Preserve the Rust extraction / Python policy boundary established by ADR 0002
  and ADR 0012. The catalogue is a Python query over builtin declarations; it
  must not parse documents, execute rules, load NLP (natural language
  processing) models, discover plugins, or alter source files.
- Preserve `check`, including empty-argument dispatch to `check`, current rule
  selection, suppression, severity, and safe-fix behaviour. No new rule or
  inverse lint policy is implemented by this task.
- Describe the shipped inventory, including disabled rules, independently of
  project configuration. Listing a rule does not assert that it will run in a
  particular document. Effective configuration inspection is separate work.
- Do not introduce a second registry, a plugin API, runtime dependencies,
  persistent cache, Rust extension, or compatibility shim. Extend private
  metadata and update affected callers together.
- Use the existing typed option parsers as the behavioural authority. Do not
  infer documentation from arbitrary runtime reflection or duplicate parsers.
- Keep every code file below 400 lines. Keep new data structures immutable and
  framework-free; command parsing, stream handling, and rendering stay outside
  the rule domain.
- Implement only after explicit approval. Mark roadmap 2.3.2 done only after
  implementation, documentation, and all acceptance gates succeed.

## Tolerances (exception triggers)

Stop implementation, set status to BLOCKED, and record alternatives for review
if a change requires a new runtime dependency, Rust/proof kernel, plugin
loading, effective-config evaluation, a changed lint/fix policy, or an
incompatible existing wire format. The new catalogue JSON contract below is in
scope; changing diagnostic JSON is not. Mechanical internal API changes need no
compatibility layer.

Escalate if more than 20 non-ExecPlan files or 1,500 net lines of code and
other documentation are required. Exclude ExecPlan files from both counts.
Escalate if a named gate still fails after three focused repair attempts. There
is no time limit. At any architectural deviation, record affected requirements,
options, downstream tests, and required design amendments; await acceptance
before continuing.

## Risks

- High impact, medium likelihood: metadata drifts from actual rule behaviour.
  Mitigate with one registry, typed defaults, parser contract tests, executable
  examples, and fix assertions against emitted diagnostics.
- Medium impact, high likelihood: users confuse declared fixability with a safe
  applicable edit. Expose separate fix mode and edit availability; explicitly
  document `MD001` manual guidance and `STY001` unsafe removal.
- Medium impact, medium likelihood: list filters accidentally reuse execution
  policy and hide opt-in rules. Query the complete inventory, independently of
  config, and test `TERM001` presence under defaults and a hostile config.
- Medium impact, medium likelihood: adding subcommands changes existing parser
  error or default-command behaviour. Preserve existing parser tests and add
  subprocess coverage for streams and exit codes.

## Progress

- [x] (2026-11-08) Rename the local branch and inspect the planning base.
- [x] (2026-11-08) Load requested skills and obtain two Wyvern reconnaissance
  reports through context pack `pk_hkqgel7a`.
- [x] (2026-11-08) Confirm roadmap 2.3.1 and its delivered builtin inventory.
- [x] (2026-11-08) Consult official Ruff documentation through Firecrawl for
  rule-inspection prior art.
- [x] (2026-11-08) Review with all six community expert perspectives; resolve
  findings and obtain follow-up confirmation of no remaining blockers.
- [x] (2026-11-08) Pass `make fmt`, `make check-fmt`, `make markdownlint`
  (including spelling), and `make nixie` for the planning document.
- [x] (2026-11-08) Publish the plan in [draft PR 276][planning-pr] and verify
  the remote head and named upstream.
- [ ] Obtain explicit approval to implement.
- [ ] M1: complete typed builtin descriptions and pure catalogue queries.
- [ ] M2: deliver text/JSON commands and behavioural coverage.
- [ ] M3: complete end-to-end evidence, documentation, and roadmap completion.

## Surprises & discoveries

`docs/roadmap.md` marks 2.3.1 complete. The current CLI exposes only `check`.
`RuleMetadata` already has code, name, target, default severity, and
`requires_nlp`, but does not contain the documentation needed by RFC 0003.
`builtin_metadata()` is the existing inventory query and should be extended,
not bypassed with another list of rule codes.

Default selection includes `MD` and `STY`, but not `TERM`. Therefore,
"disabled-by-default enablement" means explaining opt-in rules accurately; it
does not authorize disabling the entire starter pack. `TERM001` also defaults
to an empty term list, so selecting it alone produces no banned-term findings.

CodeGraph tools were unavailable during planning. Wyvern agents used repository
inspection, and source references were exchanged through the context-pack
server. Re-attempt CodeGraph discovery during implementation rather than
assuming that this session's tool availability persists.

## Decision log

- 2026-11-08: propose static catalogue queries, rather than resolved-policy
  reports. This makes help usable even in a repository with broken config and
  avoids overlapping the future `config` command.
- 2026-11-08: extend existing metadata with immutable typed documentation
  records. Keep serialization in an adapter and avoid a generic plugin schema
  framework for three builtin rules.
- 2026-11-08: use `--output-format text|json` on both commands. Ruff's official
  CLI documentation provides prior art for `rule` and output selection; the
  Stilyagi field contract remains governed by its own RFCs.
- 2026-11-08: use conventional tests and generated catalogue properties, not a
  speculative Rust verification kernel. This task presents existing policy; it
  does not introduce fix admissibility or new contractual lint logic.

## Outcomes & retrospective

The plan has passed architecture, contract, reliability, performance, and
maintainability review. No runtime behaviour has changed. Planning formatting,
Markdown, spelling, and Mermaid validation passed on 2026-11-08. The plan is
published in [draft PR 276][planning-pr]. Record implementation results
separately after approval. Do not describe a drafted test or proposed proof as
executed evidence.

## Context and orientation

Read `AGENTS.md`, `docs/contents.md`, and `docs/repository-layout.md` first.
`python/stilyagi/cli_args.py::build_parser` defines argparse command parsing.
`python/stilyagi/cli.py::main` currently constructs `CheckOptions` and invokes
`run_check`; it needs command-aware dispatch before constructing check options.
`python/stilyagi/rules/registry.py::builtin_metadata` queries
`python/stilyagi/rules/builtin/pack.py::inventory`.
`python/stilyagi/rules/base.py::RuleMetadata` carries common metadata.
`python/stilyagi/config/rules.py` owns `Md001Config`, `Sty001Config`, and
`Term001Config`; the first two accept no options. Rule execution selection
lives in `python/stilyagi/rules/policy.py`.

Existing test anchors are `tests/test_cli_args.py`, `tests/test_cli_e2e.py`,
`tests/test_builtin_markdown_rules.py`, and
`tests/test_builtin_markdown_rules_bdd.py`. Feature specifications live in
`features/`, and Syrupy snapshots in `tests/__snapshots__/`.

The shipped rules are `MD001` (heading depth, error), `STY001` (repeated word,
warning), and `TERM001` (banned term, error). `MD001` emits a manual suggestion
with no edits; `STY001` may emit an unsafe edit; `TERM001` emits no fix. Text
rules target headings, paragraphs, and table cells. Source-backed means that
text can be mapped faithfully to original file bytes; synthetic or unverifiable
text must not be described as editable.

## Conformance basis

The exact upstream revision for these local documents is the planning base
above. No separate task-specific terms of reference exists. The governing
sources are `docs/roadmap.md` 2.3.2; `docs/stilyagi-design.md` sections 3–5 and
7.2; `docs/rfcs/rfc-0002-stilyagi-python-rule-api.md` metadata and capability
sections; `docs/rfcs/rfc-0003-stilyagi-cli-contract.md` sections 3.2–3.3; and
ADRs 0002, 0003, 0009, and 0012 under `docs/adrs/`. The local RFC filenames
include the `rfc-` prefix; use those paths rather than the abbreviated links in
the brief.

Trace the requirements as follows:

- R1: discover all builtin rules and inspect one exact code (roadmap 2.3.2,
  RFC 0003). M1/M2; evidence E1 catalogue tests and E3 command tests.
- R2: truthful policy, capabilities, fixes, defaults, preview, examples,
  limitations, references, and typed variants (roadmap 2.3.2, RFC 0002). M1/M3;
  evidence E2 executable description contracts and E5 user walkthrough.
- R3: prefix, pack, severity, preview, and fixability filtering plus text/JSON
  (RFC 0003). M1/M2; evidence E1 generated properties and E3 snapshots/BDD.
- R4: preserve execution and architectural boundaries (ADRs 0002/0009/0012).
  All milestones; evidence E4 isolation/regression tests and full gates.
- R5: documented interfaces and completed roadmap after delivery (task brief).
  M3; evidence E5 guides/design review and E6 final sequential gates.

Use the requested `codegraph-mcp`, `hexagonal-architecture`, `rust-router`,
`python-router`, and `execplans` skills. The Python data-shapes and testing
routes apply to immutable records and test design. The Rust verification route
explains the proportional proof decision. Consult `firecrawl-mcp` for external
research, `logisphere-experts` for review, `commit-message` for commits, and
`pr-creation` for publication. Relevant local testing guidance includes
`docs/rust-testing-with-rstest-fixtures.md`, `docs/rust-doctest-dry-guide.md`,
`docs/reliable-testing-in-rust-via-dependency-injection.md`, and
`docs/rstest-bdd-users-guide.md`. Review
`docs/complexity-antipatterns-and-refactoring-strategies.md` before extracting
shared helpers.

## Behavioural contract and abstract model

Let C be the finite collection of shipped builtin descriptors, with unique
codes. Let F be optional catalogue filters. Define Q(C,F) independently as the
members of C satisfying every supplied filter, sorted by code. Exact lookup
D(C,c) returns the unique descriptor whose code equals c, or a missing-code
error. Neither operation takes a document, effective config, filesystem, or
provider as input. Rendering must preserve the selected descriptor identities
and values; presentation order is deterministic.

`stilyagi rule CODE` accepts one case-sensitive complete code. Prefixes,
unknown codes, and lower-case codes are errors, with exit 2, an actionable
stderr message, and empty stdout. `stilyagi rules` lists all three rules by
default, including opt-in rules. Success, including an empty filtered list,
exits 0. Invalid command arguments or enum values exit 2 through the existing
parser. Existing `--help`, `--version`, and no-argument behaviour remain
unchanged.

Both commands accept `--output-format text|json`, defaulting to text. List
filters are single-valued `--select PREFIX`, `--pack builtin`,
`--severity error|warning|info`, `--preview all|yes|no` (default `all`), and
`--fixable all|yes|no` (default `all`). Filters combine with logical AND.
Prefix matching is case-sensitive `code.startswith(prefix)`; an unknown
nonempty prefix or pack produces an empty result, not an error. Empty prefixes
are invalid. `--pack` accepts arbitrary nonempty strings, so unavailable packs
return an empty result without loading plugins. Repeated occurrences of the
same filter use the last value, matching argparse store semantics; conjunction
is across dimensions. Test this rule. Other multi-value/filter syntax is not
introduced. The prefix flag agrees with RFC 0003's `rules --select` example
without importing `check` selection semantics.

Fixable means capable of proposing actual edits, including unsafe edits. Thus
`--fixable yes` selects only `STY001`; `MD001` is not fixable despite its
manual fix object. JSON reports `fix_mode` as `manual`, `unsafe`, or `none`, and
`fixable` as false, true, or false respectively. Metadata describes potential
edits, never guarantees an applicable edit for an arbitrary finding. All
current rules have `preview: false`; test-only descriptors exercise preview
filtering without inventing a new shipped rule.

Text list output uses stable code/name/severity/fix-mode/default/preview
columns with a header, no terminal-width-dependent wrapping, and no ANSI
colours. An empty list prints `No builtin rules match the supplied filters.`
with a newline. Detail text begins with the code and name, followed by labelled
default severity, pack, enabled-by-default, preview, fixable, and fix-mode
values. Semantic tests must assert these values independently of snapshots. It
then has labelled sections for summary, explanation, targets, capabilities,
policy/enablement, fixes, options, examples, limitations, and references.
Sections remain visible when empty, with explicit `None` text. Output ends in
one newline. Errors are text on stderr even when JSON is chosen; JSON stdout is
reserved exclusively for successful machine-readable output.

The JSON envelope is `{"schema_version": 1, "rules": [...]}` for a list and
`{"schema_version": 1, "rule": {...}}` for detail. The descriptors are
identical in both commands. Their required keys are `code`, `name`, `pack`,
`summary`, `explanation`, `default_severity`, `targets`, `requires`,
`requires_nlp`, `fixable`, `fix_mode`, `enabled_by_default`, `preview`,
`configuration`, `examples`, `limitations`, and `references`. Empty collections
are arrays, not null; booleans are JSON booleans. Stable arrays and explicitly
constructed objects make output deterministic. Do not serialize Python class
names or private implementation fields.

The nested record shapes are fixed for schema version 1. `targets` is an array
of objects with `syntax: string`, `kinds: string[]`, and `scope_has: string[]`;
sort set-like arrays lexically. `requires` is a sorted array of capability-name
strings. `configuration` is an object with `enablement: string`,
`toml: string`, and `options: Option[]`. An Option has `name: string`,
`type: "boolean" | "array[string]"`, `default: boolean | string[]` matching its
type, `description: string`, `constraints: string[]`, and
`variants: Variant[]`. A Variant has `value: boolean` and
`description: string`; the array option has no variants, and the boolean option
has false then true. This intentionally models only shipped option types.
`examples` is an array of objects with `title: string`, `source: string`,
`configuration: string` (complete TOML, or empty for defaults), and
`expected_codes: string[]` (ordered observed diagnostics). `limitations` and
`references` are string arrays. Preserve authored order for prose, options,
examples, and references. All top-level identity/prose/severity/mode fields are
strings, and default/preview/NLP/fixability fields are booleans.

Store fix mode once and derive `fixable` from edit-capable modes (`safe` or
`unsafe`), rather than independently maintaining a boolean. The current shipped
modes remain manual/unsafe/none. Preserve the existing `requires_nlp` field and
validate capability declarations against it; do not invent a provider-planning
algorithm. A consistency test rejects contradictory metadata.

`targets` describe syntax, kinds, and required scope tags from the existing
`RegionTarget`. `requires` uses the RFC capability vocabulary: `STRUCTURE` for
all three rules and `TOKENS` additionally for the text rules. Explain that the
starter pack provides lightweight tokens internally, with no NLP model or
external provider required; this is descriptive metadata, not a new capability
planner. Keep `requires_nlp: false` truthful for every builtin.

`configuration` contains an enablement explanation, a complete TOML example,
and typed option descriptors. Options contain `name`, `type`, `default`,
`description`, `constraints`, and `variants`. MD001/STY001 expose empty option
arrays. TERM001 describes `terms` as an array of strings, default `[]`, and
`case_sensitive` as a boolean, default `false`. Document both false/true
variants and their matching consequences with executable examples. Explain that
the opposite editorial policy (requiring rather than banning a term) is not
supported; do not fabricate an inverse rule, option, or code. Include
parser-enforced validation constraints verbatim in meaning, not guessed from
the Python type alone. Each term must be exactly one alphabetic word under
`str.isalpha`; spaces, punctuation, and numerals are rejected. Matching uses
whole alphabetic tokens. False uses Unicode `casefold()`; true uses exact case.
Duplicates coalesce under the chosen comparison. Neither variant promises
locale-aware matching or Unicode normalization.

The enablement example selects TERM001 and configures a nonempty term list:

```toml
[tool.stilyagi.lint]
select = ["MD", "STY", "TERM001"]

[tool.stilyagi.rule.TERM001]
terms = ["obviously"]
case_sensitive = false
```

Explain `ignore`, per-file ignores, suppressions, the builtin plugin gate, and
fix-selection controls as reasons a declared/default rule may not run or edit.
The builtin gate defaults to `plugins = ["builtin"]` under `[tool.stilyagi]`;
`plugins = []` disables execution. Static metadata does not report effective
enablement for a file. Explain how `--unsafe-fixes` and fixability policy
interact for STY001 without promising safe correction. List unsupported
regions, source-backing limitations, and rule-specific false-positive risks.
Examples carry title, source, config, and expected codes; references are stable
documented URLs or repository paths.

## Verification plan

Specify obligations before implementation. No non-trivial new safety theorem,
state machine, or lint policy is introduced. The following are query and
representation contracts, verified through examples and generated tests; they
are not claims of exhaustive proof over Python execution.

E1 verifies inventory coverage, uniqueness, exact lookup, and Q(C,F). In
`tests/test_rule_catalogue.py`, use pytest parameter tables for all shipped
codes and filters. In `tests/test_rule_catalogue_properties.py`, use Hypothesis
to generate unique synthetic descriptors, permutations, filters, and missing
codes. Compare to an independent set-comprehension oracle and assert sorted,
unchanged descriptors, list/detail agreement, filter conjunction, and input
immutability. Generate empty/nonempty and matching/nonmatching cases directly;
classify these cases and reject excessive filtering or missing classes. A
removed match and reversed sorting are negative controls that must fail. The
representation relationship is one complete description per inventory entry,
never an independently maintained code list.

E2 verifies that displayed defaults, types, enablement, capabilities, and fix
claims agree with execution. In `tests/test_rule_catalogue_contracts.py`, use
pytest to parse documented TOML through the real configuration parser and run
all documented source examples through the real engine. Assert default MD/STY
selection, absent default TERM selection, empty-term inactivity, both boolean
variants, rejected invalid options, and actual manual/unsafe/absent fixes. Use
an explicit independent expected three-rule contract table; comparing two
projections of the same metadata is insufficient. A changed TERM default or
MD001 `fixable=true` must break a named test. Include false and true boolean
witnesses and Unicode term examples using the existing matching semantics.

E3 verifies command behaviour in `tests/test_rule_commands.py`,
`tests/test_rule_commands_bdd.py`, and `tests/test_rule_commands_e2e.py`. Use
pytest, pytest-bdd, and actual console entrypoint subprocesses. Assert exit
status, stdout/stderr ownership, exact lookup errors, all filter dimensions and
conjunctions, empty results, JSON schema/types, and preservation of `check`
dispatch. Use Syrupy snapshots for all three text details, the list, and both
JSON envelopes; pair them with semantic assertions. Snapshot only stable
output, excluding paths, hostnames, versions, timestamps, and
terminal-dependent data. Injecting stderr into JSON stdout or omitting a
required field must be detected independently of snapshot approval.

E4 verifies query isolation. In tests, replace config loading, document
extraction, rule execution, plugin discovery where present, and cache writes
with sentinels that fail if invoked, calling `cli.main` in-process with
injected streams. Monkeypatches do not cross subprocess boundaries. Separately
run real entrypoint subprocesses with a malformed nearby config and from an
empty directory. They must still succeed, must not require source input, and
must not modify the directory. Existing lint and safe-fix regressions remain
passing. A deliberately inserted call to config loading must fail the isolation
test. Importing existing immutable definitions is permitted; import-time config
reads, provider initialization, extraction, and cache writes are not. Test
sentinels must be installed before the relevant command imports where
initialization is lazy.

E5 is the documented maintainer walkthrough: list all shipped rules; inspect
TERM001; apply the printed TOML; lint its printed example and observe TERM001;
inspect STY001 and observe that its fix requires unsafe opt-in. All examples
must be executable, with the expected exit codes documented alongside them. E6
is the sequential full-gate record at each implementation milestone.

Assumptions are the documented argparse exit-2 contract, standard JSON scalar
semantics, the existing TOML/config parser interface, the real engine's
source-backed rule interface, and console-script packaging. Exercise these
boundaries directly; do not attempt to prove third-party internals. Hypothesis
samples inputs rather than proving unbounded correctness. Snapshot agreement is
evidence of presentation stability, not evidence of metadata truth.

Verus is not warranted for catalogue formatting, straightforward filtering, or
CLI integration. No Rust code or new lemma is planned. Existing proof and
safe-fix obligations remain unchanged. If implementation discovers substantive
contractual business logic requiring a Rust kernel, stop for a revised plan:
first state an independent abstract specification, pre/postconditions,
representation relation, and proposed semantic lemmas; then justify satisfiable
premises and negative witnesses. Only after approval add a Verus milestone with
the actual project verification command and ordinary gates. Never add `assume`,
`admit`, trusted bodies, or speculative proof scaffolding. Solver triggers and
auxiliary induction details belong to implementation, not this plan. Any
approved Rust changes require rstest unit tests, rstest-bdd behaviour,
googletest and pretty_assertions assertions, insta snapshots where meaningful,
and proptest or bounded checking for introduced invariants.

## Plan of work and milestones

### M1: typed descriptions and catalogue queries

M1 addresses R1/R2/R3 and preserves R4. First sweep the existing registry,
metadata, and config helpers for reusable equivalents. Add E1/E2 tests before
production changes and capture their intended missing-description/query
failures. Extend `RuleMetadata` and colocate builtin documentation with the
existing builtin declarations. Use small immutable records for option variants,
examples, and configuration guidance; do not introduce a generic schema
language. Proposed new `python/stilyagi/rules/catalogue.py` owns pure lookup
and filter queries. Reuse `builtin_metadata()` as the complete inventory
source. Update all affected constructors and callers atomically, with no
aliases.

The query interface should expose `get_rule(code: str) -> RuleMetadata` with a
semantic missing-rule exception and
`list_rules(filters: RuleFilters) -> tuple[RuleMetadata, ...]`. Tests can
supply a descriptor collection to a private pure query helper; production
queries use the registry. `RuleFilters` is immutable and represents the CLI
filter choices without importing argparse. Use frozen, slotted dataclasses and
precise literal/enum types consistent with the repository. Do not suppress
Skylos findings or add test-only entrypoint exceptions to make an unused
interim query pass. If M1 cannot form a legitimate runtime-owned plateau under
the existing dead-code gate, combine M1 and M2 into one atomic validated
milestone, recording that mechanical sequencing adjustment before proceeding;
the public contract and scope remain unchanged. Record the query reuse boundary
in the design and developer guides in this milestone.

Acceptance: E1/E2 pass, including real configuration/example execution, and E6
passes. The plateau offers a complete tested internal catalogue without a new
command. Remaining gap: CLI adapters. Conformance review checks R1–R4, inward
dependencies, unchanged runtime policy, and trace links. Recovery is a focused
repair or revert of the M1 commit; no persistent state needs migration.

### M2: command adapters and rendering

M2 completes R1/R3 and advances R2/R4. Add parser, BDD, and stream tests first.
Extend `cli_args.py::build_parser` and `cli.py::main` with explicit dispatch for
`rule` and `rules` before constructing `CheckOptions`. Keep check handling
unchanged. Put query command orchestration in proposed
`python/stilyagi/rule_commands.py` and text/JSON formatting in proposed
`python/stilyagi/rule_rendering.py`. Those adapters consume domain metadata;
the domain never imports them. Reuse existing stream injection/error
conventions without forcing catalogue output through diagnostic rendering.

Acceptance: E3/E4 pass with snapshots and actual entrypoint subprocesses; E6
passes. Update `docs/users-guide.md` with the new commands in the same commit,
so the plateau is usable even if final documentation work is postponed.
Conformance review checks exact filter/error contracts, preserved check tests,
absence of effective-config work, and no new dependency or wire-format drift.
Remaining gap: final independent walkthrough and documentation reconciliation.
Recovery is a focused repair or revert of M2; keep the tested M1 catalogue.

### M3: delivery evidence and documentation reconciliation

M3 closes R2/R4/R5. Complete E5 using the packaged CLI, review executable
examples and limitations, and reconcile `docs/stilyagi-design.md` section 7.2,
`docs/rfcs/rfc-0003-stilyagi-cli-contract.md` sections 3.2–3.3,
`docs/users-guide.md`, and `docs/developers-guide.md`. Document the JSON shape,
static-versus-effective distinction, catalogue reuse policy, and test workflow.
The design document is the component architecture reference for this boundary.
Use an ADR only if a substantive new architecture decision emerges; allocate
its number from the live ADR directory and link it from design and contents.
Update `docs/contents.md` for any added document.

Run E6 plus Markdown, spelling, and Mermaid gates. Record review findings and
all evidence, mark roadmap 2.3.2 done with `mapsplice` following its skill, and
leave 2.3.3 untouched. Reconcile upstream assumptions and all trace links
before marking the implementation COMPLETE. Commit this coherent delivery
plateau. Recovery is a focused documentation/test repair or revert; never
retain a done checkbox with missing acceptance evidence. No milestone needs
compatibility machinery because these are internal/pre-release interfaces, and
no stored format is being migrated.

## Behavioural specification

Add `features/rule_discovery.feature` and bind it in
`tests/test_rule_commands_bdd.py` using pytest-bdd. Expand the following core
scenarios with tables for filters and the three shipped rules:

```gherkin
Feature: Discover builtin rules without reading source
  Scenario: The catalogue includes an opt-in rule
    Given a directory with malformed Stilyagi configuration
    When the maintainer runs "stilyagi rules --output-format json"
    Then the command succeeds without reading configuration
    And the ordered codes are "MD001,STY001,TERM001"
    And TERM001 is described as disabled by default

  Scenario: Inspect a configured policy variant
    Given the builtin TERM001 rule
    When the maintainer runs "stilyagi rule TERM001"
    Then both case_sensitive boolean variants are explained
    And the enablement example selects TERM001 and supplies terms
    And the documented example produces its expected finding

  Scenario: Manual guidance is not an editable fix
    Given the builtin rule catalogue
    When the maintainer runs "stilyagi rules --fixable yes"
    Then only STY001 is listed
    And its fix mode is unsafe

  Scenario: An unknown code is an actionable error
    Given the builtin rule catalogue
    When the maintainer runs "stilyagi rule UNKNOWN --output-format json"
    Then the exit status is 2
    And standard output is empty
    And standard error identifies the unknown code
```

## Concrete steps and acceptance commands

Run commands at the repository root. For each milestone, use
Red-Green-Refactor: run the smallest new test before production edits, retain
the failure log and reason, implement the minimal change, rerun the same test,
then refactor and run wider gates. Do not commit expected failures or leave
xfail markers behind. Use the repository-built `.venv` so tests exercise its
installed Rust extension; if absent, establish it through `make build` before
focused tests.

```bash
.venv/bin/python -m pytest tests/test_rule_catalogue.py tests/test_rule_catalogue_properties.py
.venv/bin/python -m pytest tests/test_rule_catalogue_contracts.py
.venv/bin/python -m pytest tests/test_rule_commands.py tests/test_rule_commands_bdd.py tests/test_rule_commands_e2e.py
.venv/bin/stilyagi rules --output-format json
.venv/bin/stilyagi rule TERM001 --output-format json
.venv/bin/stilyagi rules --select MD --fixable yes
```

The first three commands must pass after their respective milestone. Before
implementation, failures must identify the missing query/command rather than an
unrelated dependency. The JSON list has schema version 1 and ordered codes
MD001, STY001, TERM001. The detail object has TERM001, default disabled, empty
term defaults, and two documented boolean variants. The final command exits 0
with the documented no-match text.

Delegate full candidate gates to the scrutineer agent. Run formatting, format
checking, typechecking, linting, and testing sequentially, never concurrently
for this worktree. Capture every command with `tee` and Bash `pipefail`; use
separate logs per milestone and gate, for example:

```bash
set -euo pipefail
make fmt 2>&1 | tee /tmp/stilyagi-232-M1-fmt.out
make check-fmt 2>&1 | tee /tmp/stilyagi-232-M1-check-fmt.out
make typecheck 2>&1 | tee /tmp/stilyagi-232-M1-typecheck.out
make lint 2>&1 | tee /tmp/stilyagi-232-M1-lint.out
make test 2>&1 | tee /tmp/stilyagi-232-M1-test.out
make markdownlint 2>&1 | tee /tmp/stilyagi-232-M1-markdownlint.out
make nixie 2>&1 | tee /tmp/stilyagi-232-M1-nixie.out
```

Stop the sequence at the first failure and inspect its log before repairing.
Repeat the sequence with M2/M3 log names at those boundaries. A gate passes
only on terminal exit 0 for the actual candidate. `markdownlint` includes the
spelling gate. Review generated `typos.toml` changes under AGENTS policy. Use
the shared Cargo cache and compiler admission; do not bypass wrappers, create
an isolated cache, or cancel unrelated processes. Record conformance and gate
evidence before each atomic commit. Planning-only publication uses the Markdown
gates plus formatting checks; code gates apply after implementation milestones.

## Idempotence and recovery

Queries are read-only and repeatable. Tests use temporary directories and
fixtures; never mutate the user's working files. Keep human-authored example
config independent of metadata builders. Review snapshots against semantic
assertions before accepting updates. Preserve unrelated worktree changes when
formatters touch files. Revert a failed logical change with a focused commit
rather than resetting shared history. Do not overwrite an existing remote
branch or force-push as part of this plan.

## Artefacts and notes

Planning research consulted [Ruff's official command documentation][ruff-cli]
on 2026-11-08 through Firecrawl. It confirms rule-inspection command and output
selection prior art, not Stilyagi's schema or policy semantics. Local source
inspection, not remote main, establishes the planning baseline.

The planning pull request must be draft, have title prefix `Plan:` and marker
`(2.3.2)`, link this document through the branch, and end with a References
section linking the Lody session. Push over SSH using the standard Git client,
verify identity `leynos`, refresh `origin` tracking with an explicit
destination refspec, set the named upstream, and read back the remote head and
PR status. Implementation approval remains separate from publication.

[ruff-cli]: https://docs.astral.sh/ruff/configuration/
[planning-pr]: https://github.com/leynos/stilyagi/pull/276

Revision note (2026-11-08): initial evidence-led draft defines catalogue
contracts and proportionate verification before implementation design. Expert
review tightened nested schemas, metadata derivation, text identity fields,
filter repetition, isolation test boundaries, and milestone gate coherence. All
six perspectives confirmed the revisions; planning validation remains pending.

Publication note (2026-11-08): draft PR 276 carries the reviewed plan; the
remote branch matches the local commit and tracks the requested origin branch.
Implementation approval remains outstanding.
