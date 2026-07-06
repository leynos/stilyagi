# Stilyagi roadmap

This roadmap translates the current design and RFC set into an outcome-oriented
delivery sequence. It does not promise dates. Each phase carries one testable
idea at the GIST level. The steps underneath that phase work toward validating
or falsifying the idea, answering specific sequencing questions, and leaving
behind usable functionality rather than another horizontal layer.

The roadmap follows the recommended order in
[Stilyagi design](stilyagi-design.md) §§5-13: build the structural core first,
ship Markdown value early, extend the same end-to-end loop into source trees,
then add richer language features and ecosystem surfaces.

## 1. Foundational contracts and build spine

Idea: if Stilyagi settles its core contracts, packaging boundary, and build
spine before feature work starts, later slices can converge on one coherent v1
architecture instead of repeatedly reworking interfaces and test scaffolding.

This phase removes the open questions that would otherwise churn every later
slice. It also establishes the smallest mixed Rust and Python build spine that
can support the vertical slices that follow.

### 1.1. Ratify the v1 contracts that would otherwise force rework

This step answers what Stilyagi v1 will and will not promise. Its outcome
informs the repository layout, the public interfaces, and the first release
scope. See [Stilyagi design](stilyagi-design.md) §§7, 12-13 and
[`rfcs/`](rfcs/).

- [x] 1.1.1. Record the packaging-boundary decision as an Architecture
  Decision Record (ADR). See Stilyagi design (stilyagi-design.md) §7.1.
  - Decide between the recommended PyO3 plus `maturin` extension path and any
    alternative helper-binary transport.
  - Success: one accepted ADR defines the build and runtime boundary for all
    later work.
- [x] 1.1.2. Record the v1 syntax-scope, intermediate-representation (IR)
  transport, and locale-policy decisions. See Stilyagi design
  (stilyagi-design.md) §7.1.
  - Requires 1.1.1.
  - Confirm whether Markdown with JSX (MDX) stays preview-only, whether JSON is
    canonical debug output rather than the only in-process transport, and
    whether English-only support is the formal v1 policy.
  - Success: the v1 promises match [Stilyagi design](stilyagi-design.md)
    §12.
- [x] 1.1.3. Amend RFC 0001, RFC 0002, RFC 0003, and RFC 0005 so the design
  and the narrower contracts agree. See Stilyagi design (stilyagi-design.md)
  §§7.1-7.3.
  - Requires 1.1.1 and 1.1.2.
  - Align the RFCs with the design's narrowed terminology and scope, including
    `syntax` naming, `RegionTarget` primacy, trimmed v1 discovery support, and
    the staged grammar-node plan.
  - Success: maintainers can implement from one coherent contract set.

### 1.2. Establish the mixed-package skeleton and PyO3 bridge

This step answers whether the recommended layout in
[Stilyagi design](stilyagi-design.md) §10 can support a reproducible local
development loop and a release build without compatibility shims.

- [x] 1.2.1. Create the Python package and Rust crate structure described in
  [Stilyagi design](stilyagi-design.md) §10. See Stilyagi design
  (stilyagi-design.md) §7.1.
  - Requires 1.1.3.
  - Include the PyO3 bridge crate, the Python source root, and the initial
    engine or model package boundaries.
  - Success: the repository shape matches the intended long-lived architecture.
- [x] 1.2.2. Expose a minimal Rust-to-Python extraction call through the PyO3
  extension. See Stilyagi design (stilyagi-design.md) §7.1.
  - Requires 1.2.1.
  - The first bridge may return a trivial or partial IR payload, but it must
    exercise the real extension boundary.
  - Success: Python can call into Rust without shelling out to an external
    helper.
- [x] 1.2.3. Wire the Makefile and continuous integration (CI) smoke path to
  the new mixed-package structure. See Stilyagi design (stilyagi-design.md) §10.
  - Requires 1.2.1 and 1.2.2.
  - Keep `make build` and `make release` as the canonical workflows.
  - Success: development installs and release artefacts exercise the same
    boundary.

### 1.3. Build the shared validation corpus and contract-test scaffolding

This step answers which artefacts and checks must exist before the first
meaningful feature slice can be trusted. See
[Stilyagi design](stilyagi-design.md) §11 and
[RFC 0004](rfcs/0004-stilyagi-rule-testing-framework.md).

- [x] 1.3.1. Assemble representative Markdown, Python, and Rust fixtures,
  including malformed-input cases. See Stilyagi design (stilyagi-design.md)
  §7.1.
  - Requires 1.1.3.
  - Cover headings, tables, links, docstrings, documentation comments,
    suppressions, and error recovery cases.
  - Success: every later slice can anchor its tests in shared fixtures rather
    than ad hoc strings.
- [x] 1.3.2. Add golden IR, CLI snapshot, and fix round-trip test helpers. See
  Stilyagi design (stilyagi-design.md) §7.1.
  - Requires 1.2.2 and 1.3.1.
  - Keep the helpers internal at first; the public pytest plugin comes later.
  - Success: spans, `segments`, diagnostics, and edits can be regression-tested
    cheaply.
- [x] 1.3.3. Add baseline performance probes for cold and warm structural runs.
  See Stilyagi design (stilyagi-design.md) §7.1.
  - Requires 1.2.3 and 1.3.1.
  - Record the current repository-local measurement method before richer
    natural language processing (NLP) features land.
  - Success: later steps can prove that they preserved the structural fast path.

## 2. Vertical slice 1: Markdown linting with real spans and safe fixes

Idea: if the first vertical slice can lint Markdown with trustworthy spans,
conservative fixes, and inspectable IR output, Stilyagi will already solve a
real repository problem before docstrings, plugins, or heavier NLP-backed work
land.

This phase delivers the first usable Stilyagi product: lint Markdown files,
report source-faithful diagnostics, apply conservative fixes, and inspect the
underlying IR when behaviour looks wrong.

### 2.1. Prove that Markdown can be flattened into a trustworthy IR

This step answers whether Markdown-specific structure, flattening, and
suppression handling are sufficient for v1. The result informs rule design, fix
planning, and cache keys. See [Stilyagi design](stilyagi-design.md) §§6-7.1, 11
and [RFC 0001](rfcs/0001-stilyagi-intermediate-representation.md).

- [x] 2.1.1. Implement the Markdown IR envelope, `line_index`, region text, and
  `segments` mappings. See Stilyagi design (stilyagi-design.md) §7.1.
  - Requires 1.1.3, 1.2.2, and 1.3.1.
  - Include source-backed positions, synthetic insertions, and content hashes.
  - Success: canonical IR JSON round-trips representative Markdown fixtures
    without span drift.
- [x] 2.1.2. Cover headings, lists, blockquotes, tables, links, frontmatter,
  inline markup, and malformed Markdown with golden fixtures. See Stilyagi
  design (stilyagi-design.md) §7.1.
  - Requires 2.1.1.
  - Success: every promised v1 Markdown region kind is exercised by at least
    one fixture.
  - Current status: complete.
- [x] 2.1.3. Parse Markdown suppression directives into the IR. See Stilyagi
  design (stilyagi-design.md) §7.1.
  - Requires 2.1.1.
  - Do not let later rules infer suppression state ad hoc.
  - Success: `dump-ir` exposes suppressions and later steps can trust one
    source of truth.
- [x] 2.1.3.1. Harden Markdown suppression parsing against coalesced or
  adjacent HTML comment nodes.
  - Addendum (from review:2.1.3; low). Split multi-comment HTML nodes or scan
    for multiple canonical directives within one node so no directive is lost.
    Lightweight addendum pass.
- [x] 2.1.3.2. Add coverage for inline suppression directives in paragraphs.
  - Addendum (from review:2.1.3; low). Exercise within-paragraph HTML
    comments so verb-driven classification stays pinned. Lightweight addendum
    pass.
- [x] 2.1.4. Preserve range-suppression polarity in the IR.
  - Requires 2.1.3.
  - Encode the open/close role in the suppression contract so downstream
    stages do not need to re-scan comment bytes to resolve range boundaries.
  - Success: range suppressions are fully resolvable from the IR alone and the
    canonical contract can drive later rule application without ad hoc comment
    inspection.

### 2.2. Deliver the day-one Markdown CLI loop

This step answers whether the v1 CLI contract is already strong enough to
support normal repository linting and debugging for Markdown-only users. See
[Stilyagi design](stilyagi-design.md) §§4, 7.3, 13 and
[RFC 0003](rfcs/0003-stilyagi-cli-contract.md).

- [ ] 2.2.1. Implement `stilyagi check` for Markdown files with nearest-config
  discovery, deterministic file order, and JSON or text diagnostics. See
  Stilyagi design (stilyagi-design.md) §7.3.
  - Requires 2.1.1 and 1.2.3.
  - Keep discovery scope limited to Markdown in this slice.
  - Success: `stilyagi check .` is useful on documentation repositories.
- [ ] 2.2.2. Implement safe-fix planning, conflict resolution, `--diff`, and
  `--fix` for Markdown-only source-backed edits. See Stilyagi design
  (stilyagi-design.md) §7.3.
  - Requires 2.1.1 and 2.2.1.
  - Reject edits against synthetic spans and overlapping non-identical edits.
  - Success: safe fixes are conservative and auditable.
- [ ] 2.2.3. Implement `stilyagi config`, `clean`, `dump-ir`, and `--no-cache`
  for the Markdown slice. See Stilyagi design (stilyagi-design.md) §7.3.
  - Requires 2.1.1 and 2.2.1.
  - Success: maintainers can inspect effective config, clear caches, and debug
    extraction without special scripts.

### 2.3. Ship the first builtin rules that make the slice worth adopting

This step answers which non-NLP rules provide immediate value while exercising
the rule engine, diagnostics model, and safe-fix machinery. See
[Stilyagi design](stilyagi-design.md) §§3-5, 7.2 and
[RFC 0002](rfcs/0002-stilyagi-python-rule-api.md).

- [ ] 2.3.1. Implement a starter pack of builtin Markdown rules. See Stilyagi
  design (stilyagi-design.md) §7.2.
  - Requires 2.1.2 and 2.2.1.
  - Prioritize structural and lightweight text rules such as heading depth,
    list punctuation, or other policy checks that do not require spaCy.
  - Success: the slice solves real documentation linting problems on day one.
- [ ] 2.3.2. Implement `stilyagi rule CODE` and `stilyagi rules` for builtin
  rules. See Stilyagi design (stilyagi-design.md) §7.2.
  - Requires 2.3.1.
  - Include metadata, fixability, examples, and machine-readable output where
    practical.
  - Success: maintainers can discover and debug the shipped rules without
    reading source.
- [ ] 2.3.3. Document the Markdown slice in the user's and developer's guides.
  See Stilyagi design (stilyagi-design.md) §7.2.
  - Requires 2.2.3 and 2.3.2.
  - Success: the first supported workflow is described as a supported product
    surface rather than a design aspiration.

## 3. Vertical slice 2: Docstrings and documentation comments in source trees

Idea: if the same extraction and analysis loop can extend cleanly from Markdown
into Python and Rust documentation surfaces, Stilyagi will prove that its
architecture scales by domain rather than by piling on syntax-specific side
paths.

This phase extends the same extractor, IR, rule, and fix loop into mixed code
repositories so Stilyagi becomes a prose linter for source trees, not just for
standalone Markdown.

### 3.1. Prove owner-aware extraction for Python and Rust

This step answers whether the extractor can recover the owner metadata and
source maps that docstring rules need across Python and Rust. See
[Stilyagi design](stilyagi-design.md) §§4, 7.1, 11 and
[RFC 0001](rfcs/0001-stilyagi-intermediate-representation.md).

- [x] 3.1.1. Implement Python docstring extraction with owner metadata for
  modules, classes, and functions. See Stilyagi design (stilyagi-design.md)
  §7.1.
  - Requires 2.1.1 and 1.3.1.
  - Cover nested declarations, decorators, and malformed files.
  - Success: IR fixtures identify both the prose region and its owning symbol.
  - Completed with validation evidence in
    [the Python docstring extraction execplan](execplans/3-1-1-python-docstring-extraction.md);
    see [ADR 006](adr-006-docstring-owner-metadata.md) for owner metadata
    decisions.
- [x] 3.1.2. Implement Rust documentation-comment extraction with equivalent
  owner metadata. See Stilyagi design (stilyagi-design.md) §7.1.
  - Requires 2.1.1 and 1.3.1.
  - Cover module, type, function, and item-level documentation comments.
  - Success: Rust doc comments participate in the same IR contract as Markdown
    prose and Python docstrings.
  - Completed with validation evidence in
    [the roadmap 3.1.2 execplan](execplans/roadmap-3-1-2.md);
    see [ADR 007](adr-007-rust-doc-comment-owner-metadata.md) for owner
    metadata decisions.
  - [x] 3.1.2.1. Make Rust impl-member qualified names module-rooted, or record
    a formal v1 limitation before owner-aware rules depend on them.
    - Requires 3.1.2.
    - Success: impl-associated items are globally resolvable across modules, or
      the limitation is documented and covered by tests.
  - [x] 3.1.2.2. Decide and test Rust doc-comment attachment across intervening
    non-doc `//` comments.
    - Requires 3.1.2.
    - Success: the extractor either matches Rust attachment semantics for this
      case or documents the limitation with a regression fixture.
  - [x] 3.1.2.3. Harden Rust doc-comment extraction for CR-LF, empty doc lines,
    and mixed whitespace.
    - Requires 3.1.2.
    - Success: source-byte oracle coverage includes line-ending and whitespace
      edge cases without span drift.
  - [x] 3.1.2.4. Improve diagnostics or recovery for doc comments absorbed into
    tree-sitter `ERROR` subtrees.
    - Requires 3.1.2.
    - Success: malformed Rust input either preserves recoverable doc comments
      inside error spans or emits an explicit diagnostic explaining the drop.
- [x] 3.1.3. Extend suppression parsing to Python and Rust syntax-native
  comments. See Stilyagi design (stilyagi-design.md) §7.1.
  - Requires 3.1.1 and 3.1.2.
  - Success: suppression state is extracted once and applied consistently
    across all v1 source syntaxes.

### 3.2. Reuse the Markdown rule loop inside mixed repositories

This step answers how much of the first slice survives unchanged once the
extractor surface grows. See [Stilyagi design](stilyagi-design.md) §§3-4, 7.2,
13 and [RFC 0002](rfcs/0002-stilyagi-python-rule-api.md).

- [ ] 3.2.1. Expand discovery defaults to `*.md`, `*.py`, and `*.rs`. See
  Stilyagi design (stilyagi-design.md) §7.3.
  - Requires 2.2.1.
  - Success: `stilyagi check .` works on mixed documentation and source trees.
- [ ] 3.2.2. Add builtin docstring and documentation-comment rules that reuse
  the shared region-oriented API. See Stilyagi design (stilyagi-design.md) §7.2.
  - Requires 3.1.1, 3.1.2, and 2.3.1.
  - Focus on summary-line, punctuation, and owner-aware rules that benefit from
    the new metadata.
  - Success: the second slice provides new value instead of merely exposing IR.
- [ ] 3.2.3. Extend `dump-ir`, diagnostics, and fixes so mixed-source output is
  still deterministic and source-faithful. See Stilyagi design
  (stilyagi-design.md) §7.1.
  - Requires 3.1.3, 3.2.1, and 2.2.2.
  - Success: debugging a docstring false positive follows the same workflow as
    debugging Markdown.

### 3.3. Harden cache, fix, and correctness behaviour for mixed-source runs

This step answers which correctness and invalidation rules must hold once more
than one extractor family exists. See [Stilyagi design](stilyagi-design.md)
§§5, 8, 11.

- [ ] 3.3.1. Separate extraction and analysis cache keys by syntax, extractor
  version, config, rule-pack version, and NLP profile. See Stilyagi design
  (stilyagi-design.md) §7.1.
  - Requires 3.2.1 and 2.2.3.
  - Success: cache invalidation is explainable and testable.
- [ ] 3.3.2. Add mixed-source fix safety tests for source-backed edits and
  conflict resolution. See Stilyagi design (stilyagi-design.md) §7.1.
  - Requires 3.2.3.
  - Success: docstring fixes remain conservative even when markup or comments
    were flattened during analysis.
- [ ] 3.3.3. Measure mixed-source performance and error recovery against the
  design targets. See Stilyagi design (stilyagi-design.md) §7.1.
  - Requires 3.3.1 and 3.3.2.
  - Success: the second slice remains fast enough for normal use and degrades
    gracefully on malformed input.

## 4. Vertical slice 3: Capability-planned language-aware rules

Idea: if optional language enrichment can be planned precisely and paid for
only when rules demand it, Stilyagi can offer smarter editorial analysis
without destroying the structural fast path that makes the earlier slices
usable in CI and local workflows.

This phase adds smarter rules without sacrificing the structural fast path. The
goal is not "add spaCy everywhere", but "prove that optional enrichment can be
planned, paid for selectively, and hidden behind a stable rule API". RFC 0005
defines the target grammar-capability surface for this phase.

### 4.1. Validate the cheapest useful capability planner

This step answers whether capability declarations are sufficient to select the
minimum enrichment plan per run. See [Stilyagi design](stilyagi-design.md) §§4,
6, 7.2, 8, [RFC 0002](rfcs/0002-stilyagi-python-rule-api.md), and
[RFC 0005](rfcs/0005-grammar-capability-and-syntactic-api-extensions.md).

- [ ] 4.1.1. Implement rule-declared capabilities and planner union logic. See
  Stilyagi design (stilyagi-design.md) §7.2.
  - Requires 3.2.2 and 3.3.1.
  - Success: the engine can explain why a provider was or was not selected.
- [ ] 4.1.2. Add the first sentence and token provider path for English text.
  See Stilyagi design (stilyagi-design.md) §7.2.
  - Requires 4.1.1.
  - Prefer the lightest provider that satisfies the active rules.
  - Success: sentence-aware rules can run without paying for dependency parses
    when they are unnecessary, and the provider can expose `SentenceNode` and
    `TokenNode` wrappers without leaking backend classes.
- [ ] 4.1.3. Prove that structural-only runs still avoid NLP startup entirely.
  See Stilyagi design (stilyagi-design.md) §7.2.
  - Requires 2.3.1 and 3.2.2.
  - Success: the structural fast path remains intact after capability planning
    lands.

### 4.2. Add richer rule APIs and showcase language-aware rules

This step answers what the stable public rule surface should look like once
language-aware features exist. See [Stilyagi design](stilyagi-design.md) §§7.2,
8, [RFC 0002](rfcs/0002-stilyagi-python-rule-api.md), and
[RFC 0005](rfcs/0005-grammar-capability-and-syntactic-api-extensions.md).

- [ ] 4.2.1. Add `UPos`, `Dep`, `MorphFeatures`, `SentenceNode`, and
  `TokenNode` to the rule API as the first grammar-capability wave. See
  Stilyagi design (stilyagi-design.md) §7.2.
  - Requires 4.1.2.
  - Keep backend escape hatches explicitly unstable.
  - Success: common rule authors do not need direct spaCy objects to be
    productive.
- [ ] 4.2.2. Add noun-phrase, clause, and coordination helpers plus token and
  dependency pattern support as the second grammar-capability wave. See
  Stilyagi design (stilyagi-design.md) §7.2.
  - Requires 4.1.2.
  - Success: richer rules can request higher-order syntax helpers without
    rebuilding them from raw dependency edges.
- [ ] 4.2.3. Implement a small set of showcase language-aware rules that prove
  the model. See Stilyagi design (stilyagi-design.md) §7.2.
  - Requires 4.2.1 and 4.2.2.
  - Include at least one POS-only rule, one morphology-plus-dependency rule,
    and one higher-order coordination or clause rule from RFC 0005.
  - Success: the slice ships at least one sentence-level rule and one
    syntax-aware editorial rule that would be awkward in the structural-only
    model.

### 4.3. Stabilize performance and debugging for enriched runs

This step answers what batching, logging, and profiling surfaces must exist
before language-aware rules are safe to recommend broadly. See
[Stilyagi design](stilyagi-design.md) §§4, 8, 11.

- [ ] 4.3.1. Batch enriched analysis by regions rather than concatenating whole
  repositories into one giant document. See Stilyagi design
  (stilyagi-design.md) §7.2.
  - Requires 4.1.2.
  - Success: memory use scales with batches, not repository size.
- [ ] 4.3.2. Expose verbose debugging for provider selection, cache hits, and
  extraction anomalies. See Stilyagi design (stilyagi-design.md) §7.2.
  - Requires 4.1.1 and 3.2.3.
  - Include `dump-ir --include-grammar` or an equivalent grammar-debug view.
  - Success: maintainers can explain slow or surprising enriched runs.
- [ ] 4.3.3. Capture structural-versus-enriched performance baselines and guard
  rails. See Stilyagi design (stilyagi-design.md) §7.2.
  - Requires 4.2.3 and 4.3.1.
  - Success: regressions are visible before users experience them in CI.

### 4.4. Add dictionary-based spelling as a sibling provider capability

This step answers whether Stilyagi can add a first-party spelling capability
without turning grammar support and dictionary checks into one tangled provider
surface. See
[ADR 001](adr-001-spell-checking-provider.md), [Stilyagi design](stilyagi-design.md)
§§4, 6-8, 11, and
[RFC 0005](rfcs/0005-grammar-capability-and-syntactic-api-extensions.md).

- [ ] 4.4.1. Build the Rust-side `spellbook` spike described in ADR 001. See
  Stilyagi design (stilyagi-design.md) §7.2.
  - Requires 4.1.1, 3.1.1, 3.1.2, and 3.2.3.
  - Prove dictionary loading, region-scoped checking, and source-backed span
    mapping for Markdown, Python docstrings, and Rust documentation comments.
  - Success: the proposed provider works end to end without leaking backend
    types into the public rule API and operates fully offline, with no network
    access, runtime auto-downloads, or reliance on system package managers.
- [ ] 4.4.2. Add a diagnostic-only spelling capability behind the provider
  planner. See ADR 001 (adr-001-spell-checking-provider.md). See
  stilyagi-design.md §7.2.
  - Requires 4.4.1.
  - Include repo-local personal-dictionary support and keep suggestions out of
    scope for the first wave.
  - Success: builtin spelling checks behave like other Stilyagi diagnostics,
    preserve the structural fast path when disabled, and continue to run fully
    offline with no network access, runtime auto-downloads, or system package
    manager dependencies.
- [ ] 4.4.3. Accept `spellbook` or switch to the `zspell` fallback using the
  ADR 001 gate criteria. See ADR 001 (adr-001-spell-checking-provider.md). See
  stilyagi-design.md §11.
  - Requires 4.4.2 and 4.3.3.
  - Measure correctness, performance, and offset fidelity before freezing the
    provider choice. Treat the offline constraint as part of the ADR 001 gate:
    no network access, no runtime auto-downloads, and no reliance on system
    package managers.
  - Success: the spelling capability lands behind one documented provider
    decision rather than an open-ended experiment, and the accepted provider
    clears the offline gate alongside the other ADR 001 acceptance criteria.

## 5. Vertical slice 4: Team adoption and extension ecosystem

Idea: if Stilyagi exposes a deliberate extension surface, a real rule-author
test workflow, and CI-friendly machine interfaces, it can graduate from a
useful core tool into something teams can adopt and extend without treating it
as an internal prototype.

This phase turns Stilyagi from a useful core tool into something teams can
adopt in CI, extend safely, and test against the real product surface.

### 5.1. Expose third-party rule packs and capability providers

This step answers whether the extension surface is stable enough for external
consumers and safe enough for teams to adopt deliberately. See
[Stilyagi design](stilyagi-design.md) §§4, 6, 8, 11 and
[RFC 0002](rfcs/0002-stilyagi-python-rule-api.md).

- [ ] 5.1.1. Implement entry-point-based discovery for rule packs and
  capability providers. See Stilyagi design (stilyagi-design.md) §7.2.
  - Requires 4.2.1 and 2.3.2.
  - Success: installed but unconfigured packs remain inert by default.
- [ ] 5.1.2. Reject duplicate pack names, duplicate rule codes, and invalid
  provider metadata at startup. See Stilyagi design (stilyagi-design.md) §7.2.
  - Requires 5.1.1.
  - Success: extension failures are explicit and deterministic.
- [ ] 5.1.3. Add synthetic external-pack integration tests to CI. See Stilyagi
  design (stilyagi-design.md) §7.2.
  - Requires 5.1.2.
  - Success: the public extension story is verified against the real packaging
    path.

### 5.2. Ship the rule-author testing and documentation workflow

This step answers whether RFC 0004 can make rule-pack development ergonomic
without inventing a second test-only universe. See
[RFC 0004](rfcs/0004-stilyagi-rule-testing-framework.md) and
[Stilyagi design](stilyagi-design.md) §11.

- [ ] 5.2.1. Implement the `stilyagi_path` pytest fixture and subprocess-backed
  runner contract. See Stilyagi design (stilyagi-design.md) §7.2.
  - Requires 5.1.1 and 3.2.3.
  - Success: tests can create isolated temporary projects and run the real CLI.
- [ ] 5.2.2. Expose typed result objects and common assertion helpers for
  diagnostics, fixes, and IR output. See Stilyagi design (stilyagi-design.md)
  §7.2.
  - Requires 5.2.1.
  - Success: rule-pack tests stop copy-pasting JSON parsing and path
    normalization code.
- [ ] 5.2.3. Document the rule-author workflow, plugin trust model, and stable
  v1 API surface. See Stilyagi design (stilyagi-design.md) §7.2.
  - Requires 5.1.2 and 5.2.2.
  - Success: external pack authors know what is supported and what is unstable.

### 5.3. Harden reporting, CI adoption, and release readiness

This step answers what must be true before the first release candidate is worth
publishing. See [Stilyagi design](stilyagi-design.md) §§5, 8, 11, 13 and
[RFC 0003](rfcs/0003-stilyagi-cli-contract.md).

- [ ] 5.3.1. Implement Static Analysis Results Interchange Format (SARIF)
  rendering from the shared diagnostic model. See Stilyagi design
  (stilyagi-design.md) §7.3.
  - Requires 3.2.3.
  - Success: JSON and SARIF stay consistent because they derive from the same
    facts.
- [ ] 5.3.2. Add Linux, macOS, and Windows wheel smoke tests plus installation
  checks to CI. See Stilyagi design (stilyagi-design.md) §7.3.
  - Requires 1.2.3 and 5.1.3.
  - Success: mixed Rust and Python packaging works on every supported platform.
- [ ] 5.3.3. Define release-candidate criteria for the first meaningful v1
  release. See Stilyagi design (stilyagi-design.md) §7.3.
  - Requires 2.3.3, 3.3.3, 4.3.3, 5.1.3, 5.2.3, and 5.3.2.
  - Include required commands, supported syntaxes, rule discoverability, debug
    surfaces, and fix safety guarantees.
  - Success: the project can decide objectively when the core v1 promise has
    been met.

## 6. Deferred extensions after the core v1 promise

Idea: if the core v1 promise is already trustworthy and boring to operate, the
project can evaluate broader extractor, semantic, and editor-facing extensions
on their product value instead of letting them destabilize the main release.

These items matter, but they should not block the first meaningful release.
They stay on the roadmap precisely so the v1 scope stays disciplined.

### 6.1. Evaluate MDX support and extractor plugins deliberately

- [ ] 6.1.1. Decide whether MDX graduates from preview-only support. See
  Stilyagi design (stilyagi-design.md) §7.1.
  - Requires 5.3.3.
- [ ] 6.1.2. Prototype extractor-plugin boundaries against the settled IR and
  cache contracts. See Stilyagi design (stilyagi-design.md) §7.1.
  - Requires 5.1.1 and 6.1.1.

### 6.2. Explore cross-file and semantic policy after single-file trust exists

- [ ] 6.2.1. Prototype cross-file terminology and acronym inference. See
  Stilyagi design (stilyagi-design.md) §7.2.
  - Requires 5.3.3.
- [ ] 6.2.2. Prototype vector-backed or semantic-similarity rules behind an
  explicit preview gate. See Stilyagi design (stilyagi-design.md) §7.2.
  - Requires 4.2.3 and 6.2.1.

### 6.3. Revisit daemon-mode and editor protocol work after the CLI stabilizes

- [ ] 6.3.1. Draft an RFC for daemon mode and incremental update semantics.
  See Stilyagi design (stilyagi-design.md) §7.3.
  - Requires 5.3.3.
- [ ] 6.3.2. Prototype an editor-facing transport on top of the settled CLI and
  IR contracts. See Stilyagi design (stilyagi-design.md) §7.3.
  - Requires 6.3.1 and 5.3.3.

### 6.4. Keep the region vocabulary aligned across crates

This step answers whether the IR crate and the extractor crate can keep a
single region-kind vocabulary without silently diverging as more region kinds
land.

- [ ] 6.4.1. Unify the region-kind vocabulary across `stilyagi-ir` and
  `stilyagi-extract`. See Stilyagi design (stilyagi-design.md) §7.1.
  - Requires 3.1.1 and 3.1.2.
  - Keep the shared vocabulary as the single source of truth or add a
    cross-checking test that fails on drift.
  - Success: the two crates cannot silently diverge on region names or
    meanings.
