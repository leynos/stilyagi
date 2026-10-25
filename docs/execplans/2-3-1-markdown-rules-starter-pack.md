# Implement the starter pack of builtin Markdown rules (2.3.1)

This ExecPlan is a living design and delivery document. Its mandatory living
sections are `Constraints`, `Tolerances (exception triggers)`, `Risks`,
`Progress`, `Surprises & discoveries`, `Decision log`,
`Outcomes & retrospective`, `Conformance basis`, and `Verification plan`.

Status: DRAFT — implementation requires explicit user approval.

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
   existing conflict planner. Do not widen ADR 009's edit admissibility bound.
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
  contract in RFC 0002, RFC 0003, or ADR 009, stop and propose the smallest
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
- [ ] Await explicit approval before implementation begins.
- [ ] Implementation milestones M1–M3 remain unstarted and unapproved.

## Surprises & discoveries

- Observation: the rule runner is an intentionally empty seam, and the model
  and execution pipeline already inject it. Evidence:
  `python/stilyagi/rules/registry.py` and `python/stilyagi/check_execution.py`.
  Impact: implement rules at the existing private runner boundary and update
  callers atomically; no CLI composition redesign is proposed.
- Observation: Python diagnostics do not yet carry the span that RFC 0002
  expects. Evidence: `python/stilyagi/diagnostics.py` and
  `docs/rfcs/0002-stilyagi-python-rule-api.md` §8. Impact: diagnostics span
  support is an enabling part of this slice, not a property already present.
- Observation: RFC 0003 suppression parsing and IR support exist, but the
  check-rule pipeline does not filter rules through them. Evidence:
  `crates/stilyagi-ir/src/suppression.rs` and
  `docs/rfcs/0003-stilyagi-cli-contract.md` §9. Impact: implementation must
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

## Decision log

- Decision: propose three bounded rules: `MD001` heading-level increments,
  `STY001` adjacent repeated words, and opt-in `TERM001` configured banned
  terms. Defer list punctuation, weasel words, and wordy phrases. Rationale:
  these exercise structural IR, byte-backed lightweight text matching, policy
  configuration, and safe-fix applicability without NLP. Date/author:
  2026-10-25, planning agent; pending user approval.
- Decision: first heading may be any level; only a subsequent increase that
  skips one or more levels is reported. A frontmatter title does not imply a
  level-one heading. Suppressed headings still update the previous-heading
  state. Rationale: make the rule deterministic while avoiding hidden policy
  inferred from metadata. Date/author: 2026-10-25; pending user approval.
- Decision: `STY001` matches maximal exact, case-sensitive runs of Unicode
  alphabetic tokens (`str.isalpha`) within one verified prose segment,
  separated only by ASCII spaces or tabs. It reports the second token's span
  for a maximal repeated run and offers one unsafe edit from the end of the
  first token through the end of the last token. Rationale: identify the
  repeated occurrence while keeping run edits non-overlapping and byte-backed;
  do not conflate repetitions across markup or synthetic text. Date/author:
  2026-10-25; pending user approval.
- Decision: `TERM001` is disabled unless selected, accepts a typed list of
  alphabetic single-token terms (empty list means no matches; an explicit empty
  string or nonalphabetic term is invalid), compares with Unicode case-folding
  by default (optional exact-case mode), performs no Unicode normalization,
  coalesces duplicate terms under the selected comparison mode, reports the
  original token span, and never fixes. Rationale: users choose policy
  vocabulary; no universal banned list or locale claim is appropriate.
  Date/author: 2026-10-25; pending user approval.
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
  selection. Date/author: 2026-10-25; pending user approval.
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
  2026-10-25; pending user approval.

## Outcomes & retrospective

The expert review is complete and its corrections are incorporated; user
approval remains pending. No implementation or roadmap completion has started.
At implementation close, record the exact rule codes and configuration forms
shipped, verification and gate evidence, accepted deviations, and remaining
work before setting the plan to `COMPLETE`.

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
- `docs/rfcs/0002-stilyagi-python-rule-api.md`, §§4–12: rule declaration,
  `RegionTarget`, hook scheduling, diagnostic/fix shape, options and prefixes.
- `docs/rfcs/0003-stilyagi-cli-contract.md`, §§8–12: configuration,
  suppression, output, and exit-code contract.
- `docs/adr-009-safe-fix-planning-and-conflict-resolution.md`: edit
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
  `tests/test_builtin_markdown_rules.py`, plus
  `features/stilyagi_builtin_markdown_rules.feature` and its pytest-bdd steps.
  Use `tests/support/subprocess_env.py::python_module_environment` and the
  existing BDD binding/step patterns for fresh-process CLI checks. Non-vacuity:
  each truth-table row has a positive match witness; generated sequences must
  reach both active and inactive states and consume a next-unit directive on a
  finding-free region. The independent oracle is run over generated sequences
  with no filtering. Negative controls reverse select/ignore, prefix overlap,
  or suppression and must change findings.
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

Inspect `docs/stilyagi-design.md` §§3–5 and 7.2, RFC 0002, RFC 0003, ADR 009,
`python/stilyagi/rules/registry.py`, `python/stilyagi/engine/ir_view.py`,
`python/stilyagi/diagnostics.py`, `python/stilyagi/config/`, and the existing
fix planner and CLI tests. Verify where canonical IR contains region kind,
scope, attributes, segments, suppressions, and source line index. Confirm the
actual suppression target/unit algorithm and configuration origin behaviour.
Search for equivalent span and policy helpers before creating any abstraction.

Write the BDD scenario and the smallest rule tests first. Any mismatch between
the actual IR/config contract and the proposal returns to this plan's decision
log for reconciliation. Do not begin implementation while this plan is DRAFT.

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
2.3.1, ADR 009, V-1–V-4.

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

Conformance check: CLI behaviour matches RFC 0003; fixes pass ADR 009; docs
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
edit leaves the complete file untouched under ADR 009. If a milestone fails,
revert only its commit, preserve previous validated plateaus, inspect the gate
log, then retry after correcting the cause. Never delete shared Cargo caches or
interrupt other builds. Draft publication is independently repeatable only
after checking whether a PR already exists for the branch.

## References and skills

Primary repository contracts:

- `docs/roadmap.md` items 2.1.2, 2.2.1–2.2.2, and 2.3.1–2.3.3.
- `docs/stilyagi-design.md` §§3–5, 7.2, and 7.3.
- `docs/rfcs/0002-stilyagi-python-rule-api.md` and
  `docs/rfcs/0003-stilyagi-cli-contract.md`.
- `docs/adr-009-safe-fix-planning-and-conflict-resolution.md`.
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
