# Stilyagi roadmap

This roadmap translates the current design and RFC set into an outcome-oriented
delivery sequence. It does not promise dates. Phase 1 establishes the minimum
shared foundations. From Phase 2 onward, each step is framed as a testable
idea: a hypothesis to validate, a question to answer, and an increment that
leaves behind usable functionality rather than another horizontal layer.

The roadmap follows the recommended order in
[Stilyagi design](stilyagi-design.md) §§5-13: build the structural core first,
ship Markdown value early, extend the same end-to-end loop into source trees,
then add richer language features and ecosystem surfaces.

## 1. Foundational contracts and build spine

This phase removes the open questions that would otherwise churn every later
slice. It also establishes the smallest mixed Rust and Python build spine that
can support the vertical slices that follow.

### 1.1. Ratify the v1 contracts that would otherwise force rework

Idea: if the project resolves the packaging, syntax-scope, transport, and
locale-policy questions up front, later implementation can converge on one v1
contract instead of repeatedly rewriting interfaces and tests.

This step answers what Stilyagi v1 will and will not promise. Its outcome
informs the repository layout, the public interfaces, and the first release
scope. See [Stilyagi design](stilyagi-design.md) §§7, 12-13 and
[`docs/rfcs/`](rfcs/).

- [ ] 1.1.1. Record the packaging-boundary decision as an ADR.
  - Decide between the recommended PyO3 plus `maturin` extension path and any
    alternative helper-binary transport.
  - Success: one accepted ADR defines the build and runtime boundary for all
    later work.
- [ ] 1.1.2. Record the v1 syntax-scope, IR-transport, and locale-policy
  decisions.
  - Requires 1.1.1.
  - Confirm whether MDX stays preview-only, whether JSON is canonical debug
    output rather than the only in-process transport, and whether English-only
    support is the formal v1 policy.
  - Success: the v1 promises match [Stilyagi design](stilyagi-design.md)
    §12.
- [ ] 1.1.3. Amend RFC 0001, RFC 0002, and RFC 0003 so the design and the
  narrower contracts agree.
  - Requires 1.1.1 and 1.1.2.
  - Align the RFCs with the design's narrowed terminology and scope, including
    `syntax` naming, `RegionTarget` primacy, and trimmed v1 discovery support.
  - Success: maintainers can implement from one coherent contract set.

### 1.2. Establish the mixed-package skeleton and PyO3 bridge

Idea: if the repository adopts the target Python and Rust layout early, later
features can accrete around a stable ownership boundary instead of reworking
paths, packaging, and imports mid-stream.

This step answers whether the recommended layout in
[Stilyagi design](stilyagi-design.md) §10 can support a reproducible local
development loop and a release build without compatibility shims.

- [ ] 1.2.1. Create the Python package and Rust crate structure described in
  [Stilyagi design](stilyagi-design.md) §10.
  - Requires 1.1.3.
  - Include the PyO3 bridge crate, the Python source root, and the initial
    engine or model package boundaries.
  - Success: the repository shape matches the intended long-lived architecture.
- [ ] 1.2.2. Expose a minimal Rust-to-Python extraction call through the PyO3
  extension.
  - Requires 1.2.1.
  - The first bridge may return a trivial or partial IR payload, but it must
    exercise the real extension boundary.
  - Success: Python can call into Rust without shelling out to an external
    helper.
- [ ] 1.2.3. Wire the Makefile and continuous integration (CI) smoke path to
  the new mixed-package structure.
  - Requires 1.2.1 and 1.2.2.
  - Keep `make build` and `make release` as the canonical workflows.
  - Success: development installs and release artefacts exercise the same
    boundary.

### 1.3. Build the shared validation corpus and contract-test scaffolding

Idea: if the project invests early in fixtures and contract tests, later slices
can move quickly without losing trust in spans, output schemas, or packaging.

This step answers which artefacts and checks must exist before the first
meaningful feature slice can be trusted. See
[Stilyagi design](stilyagi-design.md) §11 and
[RFC 0004](rfcs/0004-stilyagi-rule-testing-framework.md).

- [ ] 1.3.1. Assemble representative Markdown, Python, and Rust fixtures,
  including malformed-input cases.
  - Requires 1.1.3.
  - Cover headings, tables, links, docstrings, documentation comments,
    suppressions, and error recovery cases.
  - Success: every later slice can anchor its tests in shared fixtures rather
    than ad hoc strings.
- [ ] 1.3.2. Add golden IR, CLI snapshot, and fix round-trip test helpers.
  - Requires 1.2.2 and 1.3.1.
  - Keep the helpers internal at first; the public pytest plugin comes later.
  - Success: spans, `segments`, diagnostics, and edits can be regression-tested
    cheaply.
- [ ] 1.3.3. Add baseline performance probes for cold and warm structural runs.
  - Requires 1.2.3 and 1.3.1.
  - Record the current repository-local measurement method before richer NLP
    features land.
  - Success: later steps can prove that they preserved the structural fast path.

## 2. Vertical slice 1: Markdown linting with real spans and safe fixes

This phase delivers the first usable Stilyagi product: lint Markdown files,
report source-faithful diagnostics, apply conservative fixes, and inspect the
underlying IR when behaviour looks wrong.

### 2.1. Prove that Markdown can be flattened into a trustworthy IR

Idea: if Markdown extraction can produce stable regions and `segments` for real
documents, the rest of the engine can treat the IR as the sole analysis
substrate rather than letting rules parse Markdown for themselves.

This step answers whether Markdown-specific structure, flattening, and
suppression handling are sufficient for v1. The result informs rule design, fix
planning, and cache keys. See [Stilyagi design](stilyagi-design.md) §§6-7.1, 11
and [RFC 0001](rfcs/0001-stilyagi-intermediate-representation.md).

- [ ] 2.1.1. Implement the Markdown IR envelope, `line_index`, region text, and
  `segments` mappings.
  - Requires steps 1.1-1.3.
  - Include source-backed positions, synthetic insertions, and content hashes.
  - Success: canonical IR JSON round-trips representative Markdown fixtures
    without span drift.
- [ ] 2.1.2. Cover headings, lists, blockquotes, tables, links, frontmatter,
  inline markup, and malformed Markdown with golden fixtures.
  - Requires 2.1.1.
  - Success: every promised v1 Markdown region kind is exercised by at least
    one fixture.
- [ ] 2.1.3. Parse Markdown suppression directives into the IR.
  - Requires 2.1.1.
  - Do not let later rules infer suppression state ad hoc.
  - Success: `dump-ir` exposes suppressions and later steps can trust one
    source of truth.

### 2.2. Deliver the day-one Markdown CLI loop

Idea: if Markdown linting, config discovery, fixes, and debug output work
end-to-end from the main CLI, Stilyagi becomes useful before docstrings,
plugins, or heavy NLP land.

This step answers whether the v1 CLI contract is already strong enough to
support normal repository linting and debugging for Markdown-only users. See
[Stilyagi design](stilyagi-design.md) §§4, 7.3, 13 and
[RFC 0003](rfcs/0003-stilyagi-cli-contract.md).

- [ ] 2.2.1. Implement `stilyagi check` for Markdown files with nearest-config
  discovery, deterministic file order, and JSON or text diagnostics.
  - Requires 2.1.1 and 1.2.3.
  - Keep discovery scope limited to Markdown in this slice.
  - Success: `stilyagi check .` is useful on documentation repositories.
- [ ] 2.2.2. Implement safe-fix planning, conflict resolution, `--diff`, and
  `--fix` for Markdown-only source-backed edits.
  - Requires 2.1.1 and 2.2.1.
  - Reject edits against synthetic spans and overlapping non-identical edits.
  - Success: safe fixes are conservative and auditable.
- [ ] 2.2.3. Implement `stilyagi config`, `clean`, `dump-ir`, and `--no-cache`
  for the Markdown slice.
  - Requires 2.1.1 and 2.2.1.
  - Success: maintainers can inspect effective config, clear caches, and debug
    extraction without special scripts.

### 2.3. Ship the first builtin rules that make the slice worth adopting

Idea: if the first slice ships a small set of structural and lightweight text
rules with clear docs, teams can adopt Stilyagi before the rule API or NLP
surfaces become broad.

This step answers which non-NLP rules provide immediate value while exercising
the rule engine, diagnostics model, and safe-fix machinery. See
[Stilyagi design](stilyagi-design.md) §§3-5, 7.2 and
[RFC 0002](rfcs/0002-stilyagi-python-rule-api.md).

- [ ] 2.3.1. Implement a starter pack of builtin Markdown rules.
  - Requires 2.1.2 and 2.2.1.
  - Prioritize structural and lightweight text rules such as heading depth,
    list punctuation, or other policy checks that do not require spaCy.
  - Success: the slice solves real documentation linting problems on day one.
- [ ] 2.3.2. Implement `stilyagi rule CODE` and `stilyagi rules` for builtin
  rules.
  - Requires 2.3.1.
  - Include metadata, fixability, examples, and machine-readable output where
    practical.
  - Success: maintainers can discover and debug the shipped rules without
    reading source.
- [ ] 2.3.3. Document the Markdown slice in the user's and developer's guides.
  - Requires 2.2.3 and 2.3.2.
  - Success: the first supported workflow is described as a supported product
    surface rather than a design aspiration.

## 3. Vertical slice 2: Docstrings and documentation comments in source trees

This phase extends the same extractor, IR, rule, and fix loop into mixed code
repositories so Stilyagi becomes a prose linter for source trees, not just for
standalone Markdown.

### 3.1. Prove owner-aware extraction for Python and Rust

Idea: if tree-sitter-backed extraction can attach docstrings and documentation
comments to stable owners, doc-focused rules can stay structural and avoid
re-parsing source code.

This step answers whether the extractor can recover the owner metadata and
source maps that docstring rules need across Python and Rust. See
[Stilyagi design](stilyagi-design.md) §§4, 7.1, 11 and
[RFC 0001](rfcs/0001-stilyagi-intermediate-representation.md).

- [ ] 3.1.1. Implement Python docstring extraction with owner metadata for
  modules, classes, and functions.
  - Requires 2.1.1 and 1.3.1.
  - Cover nested declarations, decorators, and malformed files.
  - Success: IR fixtures identify both the prose region and its owning symbol.
- [ ] 3.1.2. Implement Rust documentation-comment extraction with equivalent
  owner metadata.
  - Requires 2.1.1 and 1.3.1.
  - Cover module, type, function, and item-level documentation comments.
  - Success: Rust doc comments participate in the same IR contract as Markdown
    prose and Python docstrings.
- [ ] 3.1.3. Extend suppression parsing to Python and Rust syntax-native
  comments.
  - Requires 3.1.1 and 3.1.2.
  - Success: suppression state is extracted once and applied consistently
    across all v1 source syntaxes.

### 3.2. Reuse the Markdown rule loop inside mixed repositories

Idea: if the same CLI and rule engine can lint Markdown, Python docstrings, and
Rust documentation comments, Stilyagi proves that its main boundary is between
extraction and analysis rather than between file types.

This step answers how much of the first slice survives unchanged once the
extractor surface grows. See [Stilyagi design](stilyagi-design.md) §§3-4, 7.2,
13 and [RFC 0002](rfcs/0002-stilyagi-python-rule-api.md).

- [ ] 3.2.1. Expand discovery defaults to `*.md`, `*.py`, and `*.rs`.
  - Requires 2.2.1.
  - Success: `stilyagi check .` works on mixed documentation and source trees.
- [ ] 3.2.2. Add builtin docstring and documentation-comment rules that reuse
  the shared region-oriented API.
  - Requires 3.1.1, 3.1.2, and 2.3.1.
  - Focus on summary-line, punctuation, and owner-aware rules that benefit from
    the new metadata.
  - Success: the second slice provides new value instead of merely exposing IR.
- [ ] 3.2.3. Extend `dump-ir`, diagnostics, and fixes so mixed-source output is
  still deterministic and source-faithful.
  - Requires 3.1.3, 3.2.1, and 2.2.2.
  - Success: debugging a docstring false positive follows the same workflow as
    debugging Markdown.

### 3.3. Harden cache, fix, and correctness behaviour for mixed-source runs

Idea: if mixed-source runs can remain deterministic and cache-correct, Stilyagi
can grow into normal repository workflows without hiding correctness problems
behind stale artefacts or syntax-specific edge cases.

This step answers which correctness and invalidation rules must hold once more
than one extractor family exists. See [Stilyagi design](stilyagi-design.md)
§§5, 8, 11.

- [ ] 3.3.1. Separate extraction and analysis cache keys by syntax, extractor
  version, config, rule-pack version, and NLP profile.
  - Requires 3.2.1 and 2.2.3.
  - Success: cache invalidation is explainable and testable.
- [ ] 3.3.2. Add mixed-source fix safety tests for source-backed edits and
  conflict resolution.
  - Requires 3.2.3.
  - Success: docstring fixes remain conservative even when markup or comments
    were flattened during analysis.
- [ ] 3.3.3. Measure mixed-source performance and error recovery against the
  design targets.
  - Requires 3.3.1 and 3.3.2.
  - Success: the second slice remains fast enough for normal use and degrades
    gracefully on malformed input.

## 4. Vertical slice 3: Capability-planned language-aware rules

This phase adds smarter rules without sacrificing the structural fast path. The
goal is not "add spaCy everywhere", but "prove that optional enrichment can be
planned, paid for selectively, and hidden behind a stable rule API".

### 4.1. Validate the cheapest useful capability planner

Idea: if Stilyagi can satisfy sentence and token needs with the lightest viable
provider, structural runs can stay fast while richer rules remain possible.

This step answers whether capability declarations are sufficient to select the
minimum enrichment plan per run. See [Stilyagi design](stilyagi-design.md) §§4,
6, 7.2, 8 and [RFC 0002](rfcs/0002-stilyagi-python-rule-api.md).

- [ ] 4.1.1. Implement rule-declared capabilities and planner union logic.
  - Requires 3.2.2 and 3.3.1.
  - Success: the engine can explain why a provider was or was not selected.
- [ ] 4.1.2. Add the first sentence and token provider path for English text.
  - Requires 4.1.1.
  - Prefer the lightest provider that satisfies the active rules.
  - Success: sentence-aware rules can run without paying for dependency parses
    when they are unnecessary.
- [ ] 4.1.3. Prove that structural-only runs still avoid NLP startup entirely.
  - Requires 2.3.1 and 3.2.2.
  - Success: the structural fast path remains intact after capability planning
    lands.

### 4.2. Add richer rule APIs and showcase language-aware rules

Idea: if the rule API can expose stable sentence and token abstractions without
leaking backend internals, Stilyagi can support meaningful editorial policy
checks without freezing itself to one NLP engine forever.

This step answers what the stable public rule surface should look like once
language-aware features exist. See [Stilyagi design](stilyagi-design.md) §§7.2,
8 and [RFC 0002](rfcs/0002-stilyagi-python-rule-api.md).

- [ ] 4.2.1. Add sentence, token, and locale-aware convenience wrappers to the
  rule API.
  - Requires 4.1.2.
  - Keep backend escape hatches explicitly unstable.
  - Success: common rule authors do not need direct spaCy objects to be
    productive.
- [ ] 4.2.2. Add part-of-speech, lemma, and dependency capabilities behind the
  planner.
  - Requires 4.1.2.
  - Success: richer rules can request only the annotations they truly need.
- [ ] 4.2.3. Implement a small set of showcase language-aware rules that prove
  the model.
  - Requires 4.2.1 and 4.2.2.
  - Success: the slice ships at least one sentence-level rule and one
    syntax-aware editorial rule that would be awkward in the structural-only
    model.

### 4.3. Stabilize performance and debugging for enriched runs

Idea: if enriched runs stay observable and bounded, teams can opt into smarter
rules without treating them as a black-box performance gamble.

This step answers what batching, logging, and profiling surfaces must exist
before language-aware rules are safe to recommend broadly. See
[Stilyagi design](stilyagi-design.md) §§4, 8, 11.

- [ ] 4.3.1. Batch enriched analysis by regions rather than concatenating whole
  repositories into one giant document.
  - Requires 4.1.2.
  - Success: memory use scales with batches, not repository size.
- [ ] 4.3.2. Expose verbose debugging for provider selection, cache hits, and
  extraction anomalies.
  - Requires 4.1.1 and 3.2.3.
  - Success: maintainers can explain slow or surprising enriched runs.
- [ ] 4.3.3. Capture structural-versus-enriched performance baselines and guard
  rails.
  - Requires 4.2.3 and 4.3.1.
  - Success: regressions are visible before users experience them in CI.

## 5. Vertical slice 4: Team adoption and extension ecosystem

This phase turns Stilyagi from a useful core tool into something teams can
adopt in CI, extend safely, and test against the real product surface.

### 5.1. Expose third-party rule packs and capability providers

Idea: if installed packs remain inert until configured and startup rejects bad
metadata loudly, Stilyagi can be extensible without becoming operationally
chaotic.

This step answers whether the extension surface is stable enough for external
consumers and safe enough for teams to adopt deliberately. See
[Stilyagi design](stilyagi-design.md) §§4, 6, 8, 11 and
[RFC 0002](rfcs/0002-stilyagi-python-rule-api.md).

- [ ] 5.1.1. Implement entry-point-based discovery for rule packs and
  capability providers.
  - Requires 4.2.1 and 2.3.2.
  - Success: installed but unconfigured packs remain inert by default.
- [ ] 5.1.2. Reject duplicate pack names, duplicate rule codes, and invalid
  provider metadata at startup.
  - Requires 5.1.1.
  - Success: extension failures are explicit and deterministic.
- [ ] 5.1.3. Add synthetic external-pack integration tests to CI.
  - Requires 5.1.2.
  - Success: the public extension story is verified against the real packaging
    path.

### 5.2. Ship the rule-author testing and documentation workflow

Idea: if rule authors can test against the real engine with a thin pytest
fixture and typed result model, the extension story becomes practical instead
of ceremonial.

This step answers whether RFC 0004 can make rule-pack development ergonomic
without inventing a second test-only universe. See
[RFC 0004](rfcs/0004-stilyagi-rule-testing-framework.md) and
[Stilyagi design](stilyagi-design.md) §11.

- [ ] 5.2.1. Implement the `stilyagi_path` pytest fixture and subprocess-backed
  runner contract.
  - Requires 5.1.1 and 3.2.3.
  - Success: tests can create isolated temporary projects and run the real CLI.
- [ ] 5.2.2. Expose typed result objects and common assertion helpers for
  diagnostics, fixes, and IR output.
  - Requires 5.2.1.
  - Success: rule-pack tests stop copy-pasting JSON parsing and path
    normalization code.
- [ ] 5.2.3. Document the rule-author workflow, plugin trust model, and stable
  v1 API surface.
  - Requires 5.1.2 and 5.2.2.
  - Success: external pack authors know what is supported and what is unstable.

### 5.3. Harden reporting, CI adoption, and release readiness

Idea: if Stilyagi can emit the right machine-readable output and install
cleanly across supported platforms, teams can adopt it as CI infrastructure
rather than as a local experiment.

This step answers what must be true before the first release candidate is worth
publishing. See [Stilyagi design](stilyagi-design.md) §§5, 8, 11, 13 and
[RFC 0003](rfcs/0003-stilyagi-cli-contract.md).

- [ ] 5.3.1. Implement Static Analysis Results Interchange Format (SARIF)
  rendering from the shared diagnostic model.
  - Requires 3.2.3.
  - Success: JSON and SARIF stay consistent because they derive from the same
    facts.
- [ ] 5.3.2. Add Linux, macOS, and Windows wheel smoke tests plus installation
  checks to CI.
  - Requires 1.2.3 and 5.1.3.
  - Success: mixed Rust and Python packaging works on every supported platform.
- [ ] 5.3.3. Define release-candidate criteria for the first meaningful v1
  release.
  - Requires phase 2 through phase 5 task completion evidence.
  - Include required commands, supported syntaxes, rule discoverability, debug
    surfaces, and fix safety guarantees.
  - Success: the project can decide objectively when the core v1 promise has
    been met.

## 6. Deferred extensions after the core v1 promise

These items matter, but they should not block the first meaningful release.
They stay on the roadmap precisely so the v1 scope stays disciplined.

### 6.1. Evaluate MDX support and extractor plugins deliberately

Idea: if the Markdown, Python, and Rust extractors are already trustworthy,
then MDX and extractor-plugin work can be assessed against a stable baseline
instead of being used as an excuse to delay v1.

- [ ] 6.1.1. Decide whether MDX graduates from preview-only support.
  - Requires 5.3.3.
- [ ] 6.1.2. Prototype extractor-plugin boundaries against the settled IR and
  cache contracts.
  - Requires 5.1.1 and 6.1.1.

### 6.2. Explore cross-file and semantic policy after single-file trust exists

Idea: if single-file diagnostics are already trustworthy, then cross-file
terminology and semantic-similarity rules can be evaluated on product value
rather than mistaken for core correctness work.

- [ ] 6.2.1. Prototype cross-file terminology and acronym inference.
  - Requires 5.3.3.
- [ ] 6.2.2. Prototype vector-backed or semantic-similarity rules behind an
  explicit preview gate.
  - Requires 4.2.3 and 6.2.1.

### 6.3. Revisit daemon-mode and editor protocol work after the CLI stabilizes

Idea: if the CLI, IR, caches, and provider planning are already stable, then a
daemon or Language Server Protocol (LSP) surface can reuse proven contracts
instead of inventing new ones under pressure.

- [ ] 6.3.1. Draft an RFC for daemon mode and incremental update semantics.
  - Requires 5.3.3.
- [ ] 6.3.2. Prototype an editor-facing transport on top of the settled CLI and
  IR contracts.
  - Requires 6.3.1 and 5.3.3.
