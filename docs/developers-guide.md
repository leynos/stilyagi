# Developer's guide

This guide is for maintainers working on Stilyagi itself. It documents the
current development environment, the Rust and Python split, the build and
verification workflow, and the boundaries that keep the implementation aligned
with the normative design.

The primary design reference is [Stilyagi design](stilyagi-design.md). The
narrower contracts live in:

- [ADR 002](adr-002-packaging-boundary.md) for the accepted build and runtime
  boundary between the Python package and the embedded Rust engine
- [ADR 003](adr-003-v1-contract-scope.md) for the accepted v1 syntax scope, IR
  transport policy, and locale support boundary
- [RFC 0001](rfcs/0001-stilyagi-intermediate-representation.md) for the
  intermediate representation (IR)
- [RFC 0002](rfcs/0002-stilyagi-python-rule-api.md) for the Python rule API
- [RFC 0003](rfcs/0003-stilyagi-cli-contract.md) for the command-line
  interface (CLI)
- [RFC 0004](rfcs/0004-stilyagi-rule-testing-framework.md) for the
  rule-testing framework
- [RFC 0005](rfcs/0005-grammar-capability-and-syntactic-api-extensions.md) for
  the grammar layer, grammar-node model, and syntax-aware rule extensions
- [Roadmap](roadmap.md) for the ordered implementation sequence across the six
  phases, including which architectural questions should be settled before
  later slices are expanded

Documentation changes in this repository must also follow the
[documentation style guide](documentation-style-guide.md).

## 1. Environment setup

The repository targets Python 3.14 and Rust 2024. The development toolchain is
centred on `uv` for Python environments and dependency management, `maturin`
for building the PyO3 extension, and Cargo for Rust formatting, linting, and
tests.

The minimum local setup is:

- Python 3.14 available to `uv`
- Rust toolchain with `cargo`, `rustfmt`, and `clippy`
- `uv`
- `maturin` 1.9.4 or newer
- `whitaker`
- `markdownlint-cli2`
- `nixie`

The repository-local virtual environment and dev dependencies are created by
the standard build target:

```bash
make build
```

That target performs three steps:

1. Recreate `.venv`
2. Sync the `dev` dependency group with `uv`
3. Run `maturin develop` against `crates/stilyagi-pyext/Cargo.toml`
4. Run the installed-package smoke check through `python -m stilyagi.smoke`

Developers should prefer the Makefile targets over ad hoc command sequences so
the PyO3 build flags and tool invocation paths stay consistent across local
development and continuous integration (CI).

## 2. Repository responsibilities and boundaries

Stilyagi is a mixed Rust and Python codebase with a strict boundary between
extraction and analysis.

The accepted packaging boundary is a Python-distributed application with an
embedded PyO3 extension built through `maturin`. Stilyagi does not use a
separate helper binary for normal v1 execution; the Rust extractor lives inside
the Python runtime as `stilyagi._stilyagi_rs`.[^1]

The accepted v1 contract scope is narrower than the architecture's long-term
extension points. Stable v1 syntax support covers Markdown, Python docstrings,
and Rust documentation comments. Markdown with JSX (MDX) remains preview-only,
canonical JSON remains required for `dump-ir`, fixtures, and compatibility
review, and English is the only formally supported v1 locale.[^2]

- Rust owns source-oriented work:
  - file-format-aware parsing
  - Markdown and host-language extraction
  - byte spans, line mapping, and source fidelity
  - construction of the IR passed into Python
  - the PyO3 bridge surface exported to Python
- Python owns analysis-oriented work:
  - configuration discovery and override handling
  - rule registration and plugin loading
  - capability planning
  - optional spaCy-backed enrichment
  - diagnostics, fixes, and output rendering

This boundary is deliberate. Rules should never parse source files for
themselves, and the Rust layer should not absorb policy decisions that belong
in the rule engine.

## 2a. Shared validation corpus

Shared source fixtures live under `tests/fixtures/corpus/`. The corpus is the
common input set for Rust and Python tests, so new extractor, rule, and bridge
tests should prefer these files over inline source strings when the same shape
is useful across languages.

The corpus is grouped by syntax and validity:

```plaintext
tests/fixtures/corpus/
├── markdown/
│   ├── valid/
│   └── malformed/
├── python/
│   ├── valid/
│   └── malformed/
└── rust/
    ├── valid/
    └── malformed/
```

Fixture names should describe the source shape, not the current implementation
limitation. For example, use names like `heading-table-link-suppression.md`,
`module-class-function-docstrings.py`, or `item-doc-comments.rs`. Invalid
Python syntax that repository formatters must not parse can use a `.py.txt`
suffix under `python/malformed/`. Each malformed fixture must remain readable
UTF-8 source text and must not need to be imported, compiled, or executed by
tests.

Python tests should load corpus files through focused `pathlib.Path` helpers
like the ones in `tests/test_corpus.py`. Rust tests should resolve
repository-relative paths from `CARGO_MANIFEST_DIR` and read fixture contents
as UTF-8 source. Until the Python docstring and Rust documentation-comment
extractors are implemented, tests may assert that those fixtures are loadable
and that extraction still reports the current unsupported-syntax error.

## 3. Roadmap-aligned implementation boundaries

The [roadmap](roadmap.md) is the maintainer view of build order. It is not just
a delivery checklist. It records the architectural questions that each phase is
supposed to settle before the later ones rely on them.

The six phases currently break down into:

- Phase 1: ratify v1 contracts, packaging, repository layout, and shared test
  scaffolding
- Phase 2: deliver the first Markdown slice with real spans, suppression
  handling, and conservative fixes
- Phase 3: extend the same loop into Python docstrings and Rust documentation
  comments
- Phase 4: add capability-planned language-aware enrichment without breaking
  the structural fast path
- Phase 5: stabilize extension, testing, CI, and release-facing surfaces for
  team adoption
- Phase 6: evaluate Markdown with JSX (MDX), semantic, and editor-facing
  extensions only after the core v1 promise is already stable

For the near-term phases, developers should preserve four boundaries in
particular.

- Syntax and locale scope
  - Stable v1 syntax support covers Markdown, Python docstrings, and Rust
    documentation comments.
  - MDX remains preview-only until later evidence upgrades it into the stable
    support matrix.
  - English is the only formally supported locale in v1. Architecture may stay
    locale-aware, but maintainers must not imply broader support before the
    product earns it through later slices and tests.

- IR structure
  - The near-term extractor contract is a stable, region-oriented IR with
    canonical JSON debug output, `line_index`, `content_hash`, `segments`,
    owner metadata, and explicit extraction errors or suppressions where they
    exist.
  - The current RFC 0001 field names are `document.syntax`, `tree.syntax`, and
    `region.syntax`. `region.host_language` is gone, `region.natural_language`
    is now optional, and `region.owner` is now required even when its value is
    `null`.
  - Region kinds `comment_block` and `jsdoc_block` are no longer part of the
    stable extractor vocabulary, and `summary_line` is now a derived
    analysis-layer view rather than an extractor-level region kind.
  - When maintainers update fixtures, adapters, or runtime wrappers, they
    should treat the field migration explicitly. The minimal before or after
    mapping is:

    ```python
    # Before RFC 0001 alignment
    document.language
    tree.language
    region.language
    region.host_language

    # After RFC 0001 alignment
    document.syntax
    tree.syntax
    region.syntax
    region.natural_language  # optional
    region.owner  # required, may be None
    ```

  - The in-process Rust to Python boundary may become more efficient than JSON,
    but JSON remains the canonical debug and test form for `dump-ir`, golden
    fixtures, and contract review.
  - `RegionTarget` is the primary stable v1 rule-targeting surface. Markdown
    node traversal remains supported, but non-Markdown `NodeRef` and
    `NodeTarget` usage should stay narrow and debug-oriented until later slices
    prove a broader node contract.
- Rule API surface
  - RFC 0002 now treats `syntaxes` as the rule-metadata field for source
    formats. `locales` is the new optional companion field for prose-locale
    constraints.
  - `RegionTarget` now accepts `kind`, `scope_has`, `syntax`,
    `natural_language`, and `owner_kind`. `RuleContext.regions(...)` should use
    the same filter names: `kind`, `syntax`, `natural_language`, and
    `owner_kind`.
  - `Region` runtime objects must carry at minimum `syntax`,
    `natural_language`, and `owner`, plus the convenience accessors
    `owner_kind` and `owner_name`.
  - Stable v1 `NodeRef` and `NodeTarget` usage is Markdown-only. Non-Markdown
    node traversal remains a debug or preview surface and should not be the
    basis of shipped rule-pack contracts.
  - Maintainers updating rules or examples should use the post-alignment
    surface directly. The minimal before or after migration looks like:

    ```python
    # Before RFC 0002 alignment
    class ExampleRule(Rule):
        languages = {"markdown"}
        targets = [RegionTarget(kind={"heading"}, language={"markdown"})]

    ctx.regions(kind={"heading"}, language={"markdown"})

    # After RFC 0002 alignment
    class ExampleRule(Rule):
        syntaxes = {"markdown"}
        locales = {"en"}
        targets = [
            RegionTarget(
                kind={"heading"},
                syntax={"markdown"},
                natural_language={"en"},
                owner_kind=None,
            )
        ]

    ctx.regions(
        kind={"heading"},
        syntax={"markdown"},
        natural_language={"en"},
        owner_kind=None,
    )
    ```

- Suppression semantics
  - Suppression state is extracted once and carried in the IR rather than
    inferred ad hoc by individual rules.
  - V1 suppression remains syntax-native and deliberately narrow: configuration
    ignores, file-level directives, and named inline or range directives in
    host-language comments. Blanket inline suppression remains out of scope.
- Safe-fix planning
  - Fix planning stays source-faithful and conservative. Safe fixes may target
    only source-backed spans, must reject overlapping non-identical edits, and
    must not mutate synthetic spans introduced during flattening.
  - The CLI surfaces for this work are `check --fix`, `check --diff`, and
    `dump-ir`, because maintainers need both mutation and inspection paths
    while the core slices are still settling.
- Capability planning
  - Language-aware rules declare capabilities up front, and the runtime plans
    the cheapest provider set that satisfies the active rules.
  - Structural-only runs must continue to avoid natural language processing
    (NLP) startup entirely. Sentence and token enrichment should land before
    heavier part-of-speech, lemma, or dependency features, and backend escape
    hatches remain explicitly unstable.

When implementation work crosses one of those boundaries, update the design,
the relevant RFC, and the roadmap together. The roadmap is part of the current
maintainer contract, not a disposable planning artefact.

## 4. Rust and PyO3 integration

The Rust code now lives in a root Cargo workspace declared by `Cargo.toml`,
with the PyO3 bridge in `crates/stilyagi-pyext/` and the first shared library
boundary in `crates/stilyagi-core/`. The Python package source root lives under
`python/stilyagi/`.

The bridge crate builds as the package-scoped `stilyagi._stilyagi_rs` extension
module. PyO3 provides the binding layer, while `maturin` handles development
installs and wheel builds.

The current integration contract is intentionally small:

- Rust exports Python-callable functions through the `stilyagi._stilyagi_rs`
  module.
- Python package code imports and orchestrates the extension rather than
  duplicating Rust-owned logic.
- Rust tests cover Rust-only behaviour, while Python tests cover package-level
  integration and user-facing behaviour.

The first real extraction path is now:

```plaintext
python/stilyagi/engine/extraction.py
  -> stilyagi._stilyagi_rs.extract_document(source, syntax)
  -> crates/stilyagi-pyext/src/lib.rs
  -> crates/stilyagi-extract/src/lib.rs
```

That split is deliberate. `crates/stilyagi-extract/` owns the partial
document-shaped extraction result and the syntax gate. `crates/stilyagi-pyext/`
translates between Rust types and a Python-owned bridge payload. The public
Python surface then adapts that payload into `stilyagi.model.Document` and
`stilyagi.model.Region`.

Changes to the FFI boundary should stay narrow. A good boundary exports
source-fidelity primitives, extraction results, and other stable engine
building blocks. A bad boundary exports policy-heavy convenience wrappers that
would force rule-engine churn into the extension crate.

The repository should also resist any drift toward a subprocess helper model
unless a later ADR explicitly reopens that question. The accepted v1 boundary
is in-process, and later roadmap steps may assume that constraint.[^1]

For local testing, the workspace intentionally no longer enables
`pyo3/extension-module` through the shared dependency declaration. Current PyO3
guidance for modern `maturin` releases is to let the build backend manage the
extension-module build mode so `cargo test` can still link and execute the Rust
test binaries.[^3] Because this now relies on the packaging backend exporting
`PYO3_BUILD_EXTENSION_MODULE`, the repository requires `maturin` 1.9.4 or newer
in both the build-system and dev-tooling dependencies.

### 4.1 Current mixed-package skeleton

The general architecture above now maps to concrete repository modules and
crates. Maintainers should use these names when discussing or extending the
current skeleton:

- `crates/stilyagi-pyext`
  - PyO3 bridge crate that builds the package-scoped
    `stilyagi._stilyagi_rs` extension module
  - should stay thin and delegate executable logic into library crates
- `crates/stilyagi-core`
  - smallest shared Rust library boundary used by the bridge today
  - current home of the Rust-backed smoke behaviour
- `crates/stilyagi-ir`
  - reserved home for the stable intermediate representation (IR) types and
    adapters described by RFC 0001
- `crates/stilyagi-markdown`
  - reserved home for Markdown-specific extraction and flattening logic
- `crates/stilyagi-tree-sitter`
  - reserved home for tree-sitter integration and syntax-tree helpers
- `crates/stilyagi-extract`
  - home for cross-syntax extraction orchestration that composes the lower-level
    crates
  - now owns the first minimal `extract_document(...)` proof used by the PyO3
    bridge
- `python/stilyagi/__init__.py`
  - public Python package surface that re-exports the supported package
    boundaries and imports the embedded Rust extension
- `python/stilyagi/cli.py`
  - command-line entrypoint placeholder for the future CLI contract from
    RFC 0003
- `python/stilyagi/config.py`
  - configuration boundary for Python-side runtime settings and validation
- `python/stilyagi/diagnostics.py`
  - diagnostic object boundary for future reporting and fix planning
- `python/stilyagi/engine/`
  - future execution planner, runner, fix-planning, and renderer surfaces
- `python/stilyagi/model/`
  - future document, region, sentence, and token runtime types
- `python/stilyagi/nlp/`
  - future NLP provider protocols and provider-specific configuration surfaces
- `python/stilyagi/plugins.py`
  - source of truth for Python entry-point group names such as
    `stilyagi.rules` and `stilyagi.capabilities`
- `python/stilyagi/rules/`
  - rule namespace root for bundled and third-party rules

Those boundaries deliberately mirror the ownership split in section 2. When a
change belongs to extraction fidelity, syntax parsing, or source mapping, it
should usually start in one of the Rust crates. When a change belongs to
configuration discovery, diagnostics, plugin registration, capability planning,
or rule orchestration, it should usually start in one of the Python modules
above.

There are also two concrete cross-boundary rules worth preserving:

- Python package code should import the embedded extension through
  `stilyagi._stilyagi_rs` and then expose user-facing orchestration from the
  `stilyagi` package surface, rather than letting callers bind to a second
  top-level module.
- The Rust workspace should not depend on Python package modules for policy or
  plugin decisions. Python owns orchestration and registration; Rust owns
  extraction and source fidelity.

## 5. Build workflow

The standard development and release workflows are:

```bash
make build
make release
```

`make build` is the development path. It recreates the virtual environment,
installs the editable Python package plus the compiled extension, and leaves
the repository ready for local linting and tests. It finishes by running
`make smoke`, which calls `python -m stilyagi.smoke` through `.venv/bin/python`
and verifies that the public Python engine API crosses into the embedded Rust
extension.

`make release` is the release artefact path. It first runs:

```bash
uv run --group dev maturin build --release --manifest-path crates/stilyagi-pyext/Cargo.toml --out dist
```

That command produces Python wheel artefacts in `dist/`, which is the expected
distribution surface for the mixed package. The target then runs
`make smoke-release`, installs the built wheel into `.venv-release-smoke`, and
executes `python -m stilyagi.smoke` from `/tmp` so the proof uses the wheel
artefact rather than the repository source tree.

The `build-release` target exists as a compatibility alias and should remain
behaviourally identical to `release`.

The `.github/workflows/smoke.yml` workflow is the bounded CI smoke path for
this repository. Its Ubuntu `lint-test` job installs Python, Rust, `uv`, and
the support tools required by the checked targets, then runs `make check-fmt`,
`make markdownlint`, `make nixie`, `make lint`, and `make test`. Its
`release-smoke` matrix builds and smoke-tests release wheels on Ubuntu, macOS,
and Windows. The workflow is not release publishing automation; it proves that
local development installs and release wheels exercise the same PyO3 boundary.

## 6. Lint, typecheck, and test workflow

The Makefile is the canonical workflow entrypoint. The current checks are:

- `make fmt`
- `make check-fmt`
- `make markdownlint`
- `make nixie`
- `make lint`
- `make typecheck`
- `make test`

Their responsibilities are:

- `make fmt`
  - format Python with Ruff
  - fix import ordering with Ruff
  - format Markdown with `mdformat-all`
  - format Rust with `cargo fmt`
- `make check-fmt`
  - verify Python formatting with Ruff
  - verify Rust formatting with `cargo fmt --check`
- `make markdownlint`
  - lint all Markdown files in the repository
- `make nixie`
  - validate Mermaid diagrams in Markdown files
- `make lint`
  - run Ruff checks through `uv`
  - run `cargo clippy` with warnings denied
  - run Whitaker from `crates/stilyagi-pyext/`
- `make typecheck`
  - rebuilds the editable environment if needed
  - runs `ty check` through `uv`
- `make test`
  - verify Rust formatting
  - rerun `cargo clippy`
  - run Rust tests with `cargo-nextest` when available, otherwise `cargo test`
  - run Python tests through `.venv/bin/python -m pytest -v`
- `make smoke`
  - run `python -m stilyagi.smoke` against the development install
- `make smoke-release`
  - rebuild the release wheel if needed
  - install it into `.venv-release-smoke`
  - run `python -m stilyagi.smoke` from outside the repository tree

The Python tools are intentionally run through `uv run --group dev` so the
repository uses the locked dev toolchain instead of whatever happens to be on
the host `PATH`.

## 7. Development responsibilities

Maintainer responsibilities in this repository are stricter than a normal
single-language package.

- Keep the Rust and Python boundary narrow and explicit.
- Preserve source-fidelity guarantees when changing extraction or span logic.
- Update the design or RFC documents when implementation decisions materially
  change the architecture or public contracts.
- Keep Makefile targets honest; do not let local convenience diverge from
  documented or CI behaviour.
- Treat third-party plugins as trusted code. The repository should never imply
  sandboxing that does not exist.
- Keep documentation current when toolchain, workflow, or ownership boundaries
  change.

## References

[^1]: [ADR 002: Ratify the packaging boundary](adr-002-packaging-boundary.md)
[^2]: [ADR 003: Ratify the v1 contract scope](adr-003-v1-contract-scope.md)
[^3]: [PyO3 FAQ: linker issues with `cargo test`](https://pyo3.rs/main/faq)

Substantial architecture changes should update both the code and the documents
that define the current contracts. Stale documentation is treated as a defect,
not as optional follow-up work.

## 8. API boundaries

The most important API boundaries are:

- Rust extractor API
  - should expose stable primitives for extraction, spans, and source mapping
  - should avoid embedding lint-policy decisions
- Python runtime API
  - should expose rule-facing objects and orchestration surfaces
  - should not bypass the Rust extractor for source parsing
- Rule and plugin API
  - should remain stable enough for third-party rule packs
  - should make required capabilities explicit
- CLI and output contracts
  - should remain aligned with the CLI RFC and machine-readable output
    guarantees

When a change crosses one of these boundaries, the change should be treated as
contract work rather than a local refactor. That usually means tests,
documentation, and compatibility review all need to move together.

## 9. Grammar layer and capability planning

RFC 0005 extends the narrower rule API contract with a grammar layer for
sentence-aware and syntax-aware rules. Maintainers should treat this as an
analysis-layer extension, not as an extractor-level replacement for the
region-oriented IR.

The grammar layer has six maintainer-facing pieces that should move together:
the `GrammarNode` hierarchy, normalized enums, morphology access, pattern
objects, capability planning, and visitor hooks.

### 9.1 GrammarNode hierarchy

`GrammarNode` is the shared source-backed base for derived grammar objects:

```python
class GrammarNode:
    span: SourceSpan
    text: str
    region: RegionNode
    document: DocumentNode

    def walk(self) -> Iterable["GrammarNode"]: ...
    def nearest(self, kind: type[T]) -> T | None: ...
```

`TokenNode` and `SentenceNode` are the first compatibility wave and should land
before higher-order helpers such as `NounPhraseNode`, `ClauseNode`, and
`CoordinationNode`.

```python
class TokenNode(GrammarNode):
    index: int

    lemma: str | None
    pos: UPos | None
    fine_pos: str | None
    morph: MorphFeatures

    dep: Dep | None
    raw_dep: str | None

    head: TokenNode | None
    children: tuple[TokenNode, ...]

    prev: TokenNode | None
    next: TokenNode | None

    confidence: float | None
    provider: str

    def ancestors(self) -> tuple[TokenNode, ...]: ...
    def descendants(self) -> tuple[TokenNode, ...]: ...
    def subtree(self) -> SpanNode: ...
    def next_content(self) -> TokenNode | None: ...
    def prev_content(self) -> TokenNode | None: ...
    def children_with_dep(self, *deps: Dep) -> tuple[TokenNode, ...]: ...
    def has_child(
        self,
        *,
        dep: Dep | None = None,
        pos: UPos | None = None,
    ) -> bool: ...
    def subject(self) -> TokenNode | None: ...
    def object(self) -> TokenNode | None: ...
    def governing_verb(self) -> TokenNode | None: ...
    def is_finite_verb(self) -> bool: ...
    def is_content(self) -> bool: ...
    def is_coordinated(self) -> bool: ...


class SentenceNode(GrammarNode):
    tokens: tuple[TokenNode, ...]

    def content_tokens(self) -> tuple[TokenNode, ...]: ...
    def first_content_token(self) -> TokenNode | None: ...
    def roots(self) -> tuple[TokenNode, ...]: ...
    def verbs(self) -> tuple[TokenNode, ...]: ...
    def finite_verbs(self) -> tuple[TokenNode, ...]: ...
```

The six `SentenceNode` helpers removed above are reserved for a later grammar
wave: `noun_phrases()`, `clauses()`, `coordinations()`, `main_clause()`,
`leading_modifier_clause()`, and `fronted_subordinate_clauses()` MAY return as
later-wave or preview surface once the layer-one token and sentence model has
proven stable.

Maintainers should preserve three behavioural points from RFC 0005:

- `next_content()` and `prev_content()` skip non-content tokens according to
  `is_content()` and must not cross sentence boundaries.
- `is_coordinated()` is the published guard for tokens participating in
  coordination structures that agreement-sensitive rules should treat as
  syntactically plural or multi-headed.
- Higher-order nodes are analysis-layer views derived from token and dependency
  data, not extractor-owned base facts persisted into the IR by default.

### 9.2 Canonical enums and morphology

`UPos` and `Dep` are the normalized enums that make the public grammar API
backend-neutral. `UPos` represents canonical universal part-of-speech tags,
while `Dep` represents normalized dependency relations. Rules should match on
these enums rather than on backend-owned labels. Raw backend labels still
matter, but they stay in `fine_pos` and `raw_dep` for debugging and provider
escape hatches.

`MorphFeatures` is the normalized morphology wrapper that preserves raw feature
data while exposing typed accessors for common cases:

```python
class MorphFeatures:
    raw: Mapping[str, tuple[str, ...]]

    @property
    def number(self) -> str | None: ...

    @property
    def person(self) -> str | None: ...

    @property
    def tense(self) -> str | None: ...

    @property
    def verb_form(self) -> str | None: ...

    @property
    def voice(self) -> str | None: ...

    def has(self, feature: str, value: str) -> bool: ...
    def has_any(self, feature: str, values: set[str]) -> bool: ...
```

When maintainers add provider support, they should normalize onto these fields
instead of re-exporting backend morphology objects directly.

### 9.3 Pattern APIs

RFC 0005 defines two Stilyagi-owned pattern layers:

- `TokenPattern`
  - matches linear token sequences against normalized token fields
  - example shape:

    ```python
    TokenPattern([
        {"POS": UPos.ADV, "LEMMA": {"IN": {"very", "really"}}},
        {"POS": UPos.ADJ},
    ])
    ```

- `DependencyPattern`
  - matches syntactic relations anchored on normalized dependency data
  - example shape:

    ```python
    DependencyPattern(
        anchor={"POS": UPos.VERB},
        children=[
            {"DEP": Dep.NSUBJ_PASS},
            {"DEP": Dep.AUX_PASS, "OPTIONAL": True},
        ],
    )
    ```

Providers may compile these patterns into backend matchers internally, but the
rule-facing contract stays Stilyagi-owned.

### 9.4 Capability enum and provider protocol

RFC 0005's grammar capability model currently defines the following public
names:

```python
class Capability(Enum):
    # Layer-one compatibility wave
    SENTENCES = "sentences"
    TOKENS = "tokens"
    POS = "pos"
    FINE_POS = "fine_pos"
    LEMMA = "lemma"
    MORPH = "morph"
    DEPENDENCY = "dependency"

    # Later wave / preview surface
    NOUN_PHRASES = "noun_phrases"
    CLAUSES = "clauses"
    COORDINATION = "coordination"
    COREFERENCE = "coreference"  # reserved for later wave / preview
    SEMANTIC_LEXICON = "semantic_lexicon"
```

The normative planner relationships are:

- `POS` implies `TOKENS`.
- `FINE_POS` implies `POS`.
- `DEPENDENCY` implies `TOKENS` and `SENTENCES`.
- `NOUN_PHRASES`, `CLAUSES`, and `COORDINATION` require `DEPENDENCY` or a
  provider-specific equivalent.
- `MORPH` may imply `POS` for some providers, but rules must still declare both
  when they need both.

The planner must reject a rule when the configured provider cannot satisfy its
declared capabilities. RFC 0002 remains the current canonical planner
vocabulary until implementation and RFC wording converge, so maintainers should
avoid shipping parallel public constant sets.

The `GrammarProvider` protocol should remain narrow:

```python
class GrammarProvider(Protocol):
    name: str
    capabilities: frozenset[Capability]

    def annotate(
        self,
        regions: Sequence[RegionNode],
        required: set[Capability],
    ) -> GrammarDocument:
        ...
```

Providers annotate extracted regions after capability planning has decided what
enrichment is required. Backend-owned objects such as spaCy tokens may exist
behind explicit unstable escape hatches, but they are not the public maintainer
contract.

### 9.5 Visitor hook signatures

Rules may implement the following grammar-aware hooks:

```python
# Layer-one hooks
def visit_token(self, ctx, token: TokenNode): ...
def visit_sentence(self, ctx, sentence: SentenceNode): ...

# Later-wave hooks
def visit_noun_phrase(self, ctx, noun_phrase: NounPhraseNode): ...
def visit_clause(self, ctx, clause: ClauseNode): ...
def visit_coordination(self, ctx, coordination: CoordinationNode): ...
```

These hooks extend, rather than replace, the base visitor surface from RFC 0002:

- `prepare(ctx, document)`
- `visit_document(ctx, document)`
- `visit_region(ctx, region)`
- `visit_node(ctx, node)`
- `visit_sentence(ctx, sentence)`
- `visit_token(ctx, token)`
- `finalize(ctx, document)`

The runtime should only invoke hooks whose required capabilities were
materialized for the current run. New hook types should be treated as public
rule-API work and reviewed with the same care as new CLI or IR fields.

### 9.6 Debug surfaces and maintainer rule

`dump-ir` remains the canonical extractor debug view. Grammar-aware debugging
should be additive, for example `dump-ir --include-grammar`, rather than by
baking provider-owned grammar objects into the base IR schema.

The practical rule for maintainers is simple: extracted regions and source
spans come first, provider-backed grammar objects come second, and rule hooks
sit on top of both. If a change tries to invert that order, it is almost
certainly crossing the wrong boundary.

## 10. Debugging and verification workflow

When behaviour looks wrong, debugging should start at the boundary most likely
to be at fault.

- Suspected span or extraction bug:
  - inspect the Rust extractor and its tests first
  - confirm the source offsets before touching rule logic
- Suspected rule or capability-planning bug:
  - inspect the Python runtime and rule-selection flow
  - verify whether the required enrichment was actually requested
- Suspected packaging or import bug:
  - rerun `make build`
  - verify that the editable install still points at the `maturin develop`
    extension rather than a stale wheel

For verification, prefer the Makefile targets over ad hoc tool runs. The
targets encode the repository's intended order of operations and catch
cross-language regressions that isolated commands can miss.

## 11. Release expectations

Release work should assume wheel artefacts are the primary distributable output
of the mixed package.

- Use `make release` for release builds.
- Use `make smoke-release` when you need to rerun only the release-wheel smoke
  proof after a release artefact has been built.
- Keep the Python package metadata and the Rust extension build path in sync.
- Treat release-affecting changes to the Makefile, `pyproject.toml`, or
  `crates/stilyagi-pyext/Cargo.toml` as coupled changes that need end-to-end
  verification.

If release packaging changes, this guide, the design document, and the relevant
RFCs should be reviewed together so the documented contract remains accurate.
