# Expose the first Rust-to-Python extraction call through the PyO3 (Rust-to-Python bindings) bridge

This ExecPlan (execution plan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work
proceeds.

Status: COMPLETE

Approval gate: approved by the user on 2026-04-22 before implementation began.

## Purpose / big picture

Roadmap item 1.2.2 exists to replace the current `hello()`-only smoke path with
the first real extraction call that crosses the embedded PyO3 boundary. After
this work, Python code should be able to call into Rust through the installed
`stilyagi._stilyagi_rs` extension and receive a minimal document-shaped result
without shelling out to a helper binary.

The change is intentionally narrow. It does not implement the full
intermediate-representation (IR) contract from roadmap item 2.1.1, and it does
not widen syntax support beyond the first Markdown bridge. Its job is to prove
that the accepted packaging boundary from
[docs/adr-002-packaging-boundary.md](../adr-002-packaging-boundary.md) is real
for extraction, not just for a greeting string.

The observable outcome is straightforward. After `make build`, a maintainer
should be able to run a small Python snippet that imports `stilyagi.engine`,
calls a Markdown extraction function, and receives a `stilyagi.model.Document`
value backed by Rust-owned extraction code. The same path should also reject
unsupported syntaxes cleanly from Python without silently falling back to a
subprocess helper or a pure-Python parser.

## Orientation

Roadmap item 1.2.1 has already created the long-lived repository shape. The
current tree has:

- `crates/stilyagi-extract/` as a placeholder extraction crate;
- `crates/stilyagi-pyext/` as the `_stilyagi_rs` extension module;
- `python/stilyagi/model/` with placeholder `Document`, `Region`, and `Syntax`
  types; and
- `python/stilyagi/engine/` as the future orchestration boundary.

Today, however, the only real Rust-to-Python behaviour is
`stilyagi.hello() -> "hello from Rust"`. The extraction crate has marker
boundaries but no callable extraction function. The PyO3 bridge exports no
document-shaped payload. The Python engine package exposes no extraction
entrypoint.

This plan keeps the next slice narrow by adding one minimal Markdown-only
bridge that can later be replaced or expanded in place. The plan does not
attempt to deliver the full IR envelope, line index, segments, owner metadata,
or debug JSON contract promised by later roadmap items. Those remain future
work, and this slice must not freeze them accidentally.

## Documentation and skill signposts

The implementer should keep these documents open while executing the plan:

- [docs/roadmap.md](../roadmap.md) for the exact scope and the rule that item
  1.2.2 is complete only when Python can call Rust extraction without an
  external helper.
- [docs/stilyagi-design.md](../stilyagi-design.md), especially sections 4, 7.1,
  10, 11, and 13, for the Rust-versus-Python ownership split, the warning that
  JSON is canonical debug output rather than the mandatory hot-path transport,
  the target repository shape, and the long-term validation classes.
- [docs/adr-002-packaging-boundary.md](../adr-002-packaging-boundary.md) for
  the accepted PyO3 plus `maturin` runtime model and the rejection of helper
  binaries for normal execution.
- [docs/adr-003-v1-contract-scope.md](../adr-003-v1-contract-scope.md) for the
  accepted v1 syntax and transport boundaries that later slices will build on.
- [docs/developers-guide.md](../developers-guide.md) and
  [docs/users-guide.md](../users-guide.md) for the maintainer-facing and
  user-facing guidance that must be updated once the bridge exists.
- [docs/rfcs/0001-stilyagi-intermediate-representation.md](
  ../rfcs/0001-stilyagi-intermediate-representation.md) for the future IR
  destination, even though this slice must stay narrower than that RFC's full
  contract.
- [docs/rust-testing-with-rstest-fixtures.md](
  ../rust-testing-with-rstest-fixtures.md),
  [docs/rstest-bdd-users-guide.md](../rstest-bdd-users-guide.md), and
  [docs/reliable-testing-in-rust-via-dependency-injection.md]( ../reliable-testing-in-rust-via-dependency-injection.md).
- [docs/rust-doctest-dry-guide.md](../rust-doctest-dry-guide.md) for the Rust
  testing and API-documentation expectations named in the task.
- [docs/complexity-antipatterns-and-refactoring-strategies.md](
  ../complexity-antipatterns-and-refactoring-strategies.md) to keep this first
  bridge deliberately small and to avoid prematurely baking future IR
  complexity into the new API.

The relevant skills for the implementer are:

- `execplans` to keep this plan current during implementation.
- `leta` for symbol-aware inspection and refactoring.
- `rust-router` first, then `arch-crate-design` for deciding where the first
  extraction result types should live.
- `rust-types-and-apis` for the Rust result-shape and PyO3 conversion boundary.

## Constraints

- This slice is roadmap item 1.2.2. Keep it narrower than roadmap items 2.1.x,
  2.2.x, and 3.1.x. Do not implement the full IR envelope, rule engine,
  suppression parsing, CLI, or non-Markdown extraction under the cover of this
  first bridge.
- The real extraction function must live on the Rust side of the boundary, in
  the extraction stack rooted at `crates/stilyagi-extract/`. Python may
  orchestrate and adapt the result, but it must not parse Markdown or invent
  the extracted document payload itself.
- The hot-path Python-to-Rust boundary must stay in-process through
  `stilyagi._stilyagi_rs`. Do not introduce a subprocess helper, command
  invocation shim, or JSON-over-stdio transport to make the tests pass.
- Preserve the package name `stilyagi` and the extension module name
  `_stilyagi_rs`.
- Keep the current `hello()` smoke path unless repository-local evidence proves
  it blocks the new bridge. The new extraction call is additive in this slice;
  removing the smoke path would broaden the user-facing change without helping
  roadmap item 1.2.2 succeed.
- The Python-facing surface must stay small and future-compatible. Expose one
  narrow extraction function from `python/stilyagi/engine/` rather than
  scattering bridge helpers across the package root.
- The returned payload may be partial, but it must still be document-shaped and
  honest. It must not claim fields such as `line_index`, `segments`, or owner
  metadata that this slice does not really compute.
- Follow red-green-refactor. Add or update tests first so they fail for the
  right reason before the bridge exists.
- Update the design document with any design decisions this slice takes. Update
  the user and developer guides with the new behaviour before the roadmap item
  is marked done.
- Mark roadmap item 1.2.2 as done only after the code, docs, and validation
  gates all pass.

## Tolerances (exception triggers)

- Scope: if the implementation needs more than eighteen files or more than
  roughly 500 net new lines, stop and explain why. This is intended to be a
  narrow bridge slice, not a stealth IR or CLI milestone.
- Interface: if the proposed Python-facing surface needs more than one new
  public extraction function or requires a root-level package re-export, stop
  and confirm the broader API change first.
- Syntax breadth: if satisfying the task appears to require implementing Python
  docstring or Rust documentation-comment extraction now, stop. Those belong to
  roadmap item 3.1.
- Dependencies: if any new third-party Rust or Python dependency appears
  necessary, stop and justify it. The existing workspace and package should be
  sufficient for a minimal bridge.
- Transport: if PyO3 cannot return the chosen minimal payload without forcing a
  broader transport redesign, stop and surface the exact limitation rather than
  improvising a JSON-string public API that freezes the wrong contract.
- Iterations: if the targeted failing tests still do not pass after two focused
  correction rounds, stop and collect the failing logs for review.
- Time: if the slice cannot be completed and fully validated in one focused
  session, stop and document the blocker rather than padding the change with
  unrelated cleanup.
- Ambiguity: if the design, the current placeholder Python model, and the
  narrowest useful public API no longer line up, stop and present the competing
  options with trade-offs before implementing.

## Risks

- Risk: the first bridge could accidentally freeze the wrong transport by
  making JSON strings or opaque dictionaries the public Python API instead of a
  typed package surface. Severity: high Likelihood: medium Mitigation: keep
  JSON and raw bridge payloads internal, and make the user-facing function
  return `stilyagi.model.Document`.

- Risk: the slice could overreach into the full IR contract and start adding
  `line_index`, `segments`, or owner metadata before the extractor really owns
  them. Severity: high Likelihood: medium Mitigation: use a deliberately named
  partial result type and record in the design document that this bridge is
  intentionally narrower than roadmap item 2.1.1.

- Risk: the new extraction function could be parked in the wrong crate, such as
  `stilyagi-core`, which would blur the long-term responsibility boundary
  between shared utilities and extraction. Severity: medium Likelihood: medium
  Mitigation: root the extraction implementation in `crates/stilyagi-extract/`
  and let `crates/stilyagi-pyext/` remain a thin adapter.

- Risk: the tests could prove only that Python can call Python, not that Python
  can call Rust extraction. Severity: high Likelihood: medium Mitigation: write
  Rust-side unit and BDD tests around the PyO3 bridge itself, and write Python
  package tests that call the public engine function and assert Rust-owned
  behaviour.

- Risk: the empty-input and unsupported-syntax semantics could remain implicit,
  creating awkward test churn in later slices. Severity: medium Likelihood:
  medium Mitigation: decide them explicitly in this slice, document them, and
  cover them in both unit and behaviour tests.

- Risk: documentation will become misleading if it still says `hello()` is the
  only bridge surface after the new extraction path lands. Severity: medium
  Likelihood: high Mitigation: update the design document, developer's guide,
  and user's guide in the same change before the roadmap checkbox moves.

## Proposed implementation shape

The narrowest future-compatible public Python surface is:

```python
from stilyagi import engine, model

document = engine.extract_document("# Heading", model.Syntax.MARKDOWN)
```

The plan deliberately keeps `hello()` as an existing smoke path, but it stops
being the only meaningful bridge proof. The new public Python function should:

1. accept `source: str` and `syntax: model.Syntax`;
2. support `model.Syntax.MARKDOWN` immediately;
3. raise `NotImplementedError` for other current enum members; and
4. return `model.Document` with zero or more `model.Region` values.

The narrowest honest Rust behaviour for this slice is:

- `crates/stilyagi-extract/` exports a minimal Markdown extraction function
  that returns a partial document result;
- the partial result reports `syntax = "markdown"` and a `regions` list;
- blank input returns an empty region list;
- non-blank input returns one region with a temporary kind such as
  `"document"` and the source text preserved verbatim; and
- Unicode text is preserved unchanged.

This shape is intentionally not the final IR. It is a bridge proof with a
document-shaped payload that later roadmap items can refine in place.

## Milestone 1: create the failing tests first

Start by writing the tests that describe the desired bridge before adding any
new implementation.

Update or add these test surfaces:

- `crates/stilyagi-extract/src/lib.rs`
  - add `rstest` unit tests that define the minimal extraction semantics:
    Markdown syntax is reported, blank input yields zero regions, non-blank
    input yields one region, and Unicode text round-trips unchanged.
- `crates/stilyagi-pyext/src/lib.rs`
  - replace or extend the current bridge tests so they assert PyO3 delegates to
    the extraction crate rather than only to the smoke greeting.
  - add `rstest-bdd` scenarios for a successful Markdown extraction and for the
    empty-input edge case.
- `crates/stilyagi-pyext/tests/features/bridge_structure.feature`
  - either replace the greeting scenarios or add new extraction scenarios. If
    `hello()` remains, keep its existing scenarios and add extraction scenarios
    beside them so the bridge file proves both the legacy smoke path and the
    first real extraction path.
- `tests/test_package_skeleton_units.py`
  - update the engine package expectations to include the new extraction
    function and add unit tests for:
    - returning `model.Document` on the happy path;
    - mapping regions into `model.Region`;
    - blank input returning an empty region tuple; and
    - unsupported syntaxes raising `NotImplementedError`.
- `tests/test_package_structure_bdd.py` and
  `features/stilyagi_package_structure.feature`
  - replace the subprocess assertion that only prints `hello()` with one that
    exercises the public extraction function and serializes the resulting
    document shape.

Run the smallest relevant tests and confirm they fail for the right reason
before implementation:

```bash
BRANCH_SLUG=$(git branch --show | tr / -)
cargo test --manifest-path Cargo.toml -p stilyagi-extract \
  |& tee /tmp/test-stilyagi-extract-"$BRANCH_SLUG".out
cargo test --manifest-path Cargo.toml -p stilyagi-pyext \
  |& tee /tmp/test-stilyagi-pyext-"$BRANCH_SLUG".out
.venv/bin/python -m pytest -q \
  tests/test_package_skeleton_units.py tests/test_package_structure_bdd.py \
  |& tee /tmp/pytest-stilyagi-bridge-"$BRANCH_SLUG".out
```

Expected red-state evidence:

- Rust tests fail because the extraction function or result types do not exist
  yet.
- Python tests fail because `stilyagi.engine` does not yet expose the new
  extraction function.

## Milestone 2: implement the minimal Rust extraction result

Add the smallest extraction result type that can prove the boundary without
pretending to be the final IR.

Use `crates/stilyagi-extract/src/lib.rs` for the first implementation. The
recommended shape is a pair of simple structs such as `PartialDocument` and
`PartialRegion`, plus a syntax-aware function such as
`extract_document(source: &str, syntax: ExtractSyntax)` returning
`Result<ExtractDocument, ExtractError>`.

Implementation rules for this milestone:

- Keep the types explicit and concrete.
- Do not move them into `crates/stilyagi-ir/` yet. That crate should remain
  reserved for the fuller IR contract from later roadmap work.
- Keep the extraction logic boring and honest. For this slice, a one-region
  mirror of non-blank input is enough.
- If the type names include `partial` or `probe`, preserve that wording in the
  Rust docs and the design update so later maintainers can see that this is a
  transitional contract.

When this milestone is complete, `cargo test -p stilyagi-extract` should pass
and the result type should be narrow enough that roadmap item 2.1.1 can still
replace it cleanly.

## Milestone 3: bridge the Rust result through PyO3 and wrap it in Python

Once the extraction crate owns a real result, wire it through the extension and
adapt it into the Python package model.

Expected code changes:

- `crates/stilyagi-pyext/Cargo.toml`
  - add a dependency on `stilyagi-extract`.
- `crates/stilyagi-pyext/src/lib.rs`
  - keep `hello()` unchanged unless doing so blocks the new bridge;
  - add a PyO3 function `extract_document(source: &str, syntax: &str)` that
    delegates straight to `stilyagi_extract::extract_document`;
  - convert the Rust result into plain Python-owned values inside the bridge.
    Prefer a small `PyDict` / `PyList` or a hand-built tuple structure over a
    JSON string.
- `python/stilyagi/_stilyagi_rs.pyi`
  - add the typing stub for the new extension function.
- `python/stilyagi/engine/extraction.py`
  - add a new module that owns the Python-visible extraction API.
- `python/stilyagi/engine/__init__.py`
  - re-export `extract_document`.

The Python wrapper should:

- accept `source: str` and `syntax: model.Syntax`;
- forward `syntax.value` from every `model.Syntax` member to
  `_stilyagi_rs.extract_document(source, syntax.value)`;
- adapt the internal bridge payload into `model.Document` and
  `model.Region`;
- surface `NotImplementedError` or `ValueError` from the bridge for
  unsupported syntax requests; and
- avoid exposing the bridge payload shape as part of the public package
  contract.

When this milestone is complete, the Python unit and behaviour tests should
prove that the public package surface returns model objects that came from the
real extension boundary.

## Milestone 4: record the design decisions and user-visible behaviour

Do the documentation work in the same change, not afterward.

Update these documents:

- `docs/stilyagi-design.md`
  - record that roadmap item 1.2.2 chooses a partial Markdown-only bridge
    payload that proves the PyO3 extraction boundary without freezing the full
    IR contract from roadmap item 2.1.1.
- `docs/developers-guide.md`
  - document the new extraction call path:
    `python/stilyagi/engine/extraction.py` ->
    `stilyagi._stilyagi_rs.extract_document(source, syntax)` ->
    `crates/stilyagi-extract/`.
  - state explicitly that the Python package owns dispatch and adaptation while
    Rust owns extraction.
- `docs/users-guide.md`
  - add the first real extraction example and the current limitation that only
    Markdown is implemented through this bridge for now.
  - clarify that `hello()` remains a smoke helper, while the new extraction
    function is the first document-shaped bridge surface.
- `docs/roadmap.md`
  - mark item 1.2.2 done only after all code and validation steps pass.

If the implementation reveals any new boundary decision that later slices need
to assume, record it in the design document rather than leaving it trapped in
test names or commit messages.

## Milestone 5: validate the slice end-to-end and capture evidence

After the targeted tests pass, run the full repository gates sequentially. Do
not run them in parallel. Pipe each one through `tee` so the full logs remain
available for review.

Use this sequence:

```bash
BRANCH_SLUG=$(git branch --show | tr / -)
make fmt |& tee /tmp/fmt-stilyagi-"$BRANCH_SLUG".out
make check-fmt |& tee /tmp/check-fmt-stilyagi-"$BRANCH_SLUG".out
make lint |& tee /tmp/lint-stilyagi-"$BRANCH_SLUG".out
make typecheck |& tee /tmp/typecheck-stilyagi-"$BRANCH_SLUG".out
make test |& tee /tmp/test-stilyagi-"$BRANCH_SLUG".out
make markdownlint |& tee /tmp/markdownlint-stilyagi-"$BRANCH_SLUG".out
make nixie |& tee /tmp/nixie-stilyagi-"$BRANCH_SLUG".out
```

Capture one short observable proof for the final review:

```bash
.venv/bin/python - <<'PY'
from stilyagi import engine, model

document = engine.extract_document("# Heading", model.Syntax.MARKDOWN)
print(document)
PY
```

Expected green-state behaviour:

- the command succeeds without invoking any external helper binary;
- the printed object is a `Document` with
  `syntax=<Syntax.MARKDOWN: 'markdown'>`; and
- the document contains at least one region for non-blank input.

## Acceptance criteria

The feature is complete when all of the following are true:

- Python can call a real extraction function through `stilyagi._stilyagi_rs`
  without shelling out to an external helper.
- The public Python surface exposes one narrow extraction entrypoint through
  `stilyagi.engine`.
- The returned value is `stilyagi.model.Document`, not a raw JSON string.
- Markdown input works on the happy path.
- Blank Markdown input is handled explicitly and tested.
- Unsupported syntaxes fail explicitly and tested from Python.
- Rust-side unit tests use `rstest`, and Rust-side behaviour tests use
  `rstest-bdd` where the bridge path is best expressed as a scenario.
- The design document, developer's guide, user's guide, and roadmap are all
  updated consistently.
- `make check-fmt`, `make lint`, `make typecheck`, `make test`,
  `make markdownlint`, and `make nixie` all pass.

## Progress

- [x] 2026-04-22 16:35 CEST: Reviewed roadmap item 1.2.2, the accepted
  packaging and v1 contract ADRs, the current `hello()` bridge, the placeholder
  extraction crate, the current Python model and engine skeleton, and the Rust
  testing guidance needed to draft this plan.
- [x] 2026-04-22 16:35 CEST: Drafted this ExecPlan and wrote it to
  `docs/execplans/1-2-2-rust-to-python-extraction-call-through-pyo3.md`.
- [x] 2026-04-22 17:08 CEST: Received explicit user approval to proceed with
  implementation.
- [x] 2026-04-22 17:34 CEST: Added the red-state Rust and Python tests for the
  extraction bridge and confirmed they failed because the extraction types and
  engine entrypoint did not exist yet.
- [x] 2026-04-22 17:56 CEST: Implemented the minimal extraction result in
  `crates/stilyagi-extract/`.
- [x] 2026-04-22 18:07 CEST: Exposed the result through
  `crates/stilyagi-pyext/` and wrapped it in `python/stilyagi/engine/`.
- [x] 2026-04-22 18:18 CEST: Updated the design document and the user and
  developer guides to describe the real extraction path and its current
  limitations.
- [x] 2026-04-22 18:43 CEST: Marked roadmap item 1.2.2 as done in
  `docs/roadmap.md`.
- [x] 2026-04-22 18:41 CEST: Ran the sequential validation gates and captured
  final evidence.
- [x] 2026-04-22 20:56 CEST: Addressed review feedback by removing the extra
  Rust bridge result layer, centralizing syntax-spelling checks through the
  extension boundary, tightening Python payload validation, and updating this
  ExecPlan to define `PyO3` on first use.

## Surprises & Discoveries

- The current repository is already close to the right seam for this slice:
  `crates/stilyagi-extract/` exists, `python/stilyagi/model/` already has
  placeholder `Document` and `Region` dataclasses, and the missing piece is the
  actual bridge between them.
- The current public Python package does not yet expose any extraction function,
  so the red-state test should be clean and obvious.
- The existing Rust BDD feature file in `crates/stilyagi-pyext/tests/features/`
  already proves bridge structure and can be extended rather than replaced from
  scratch.
- `cargo test` for the PyO3 crate initially failed to link while the workspace
  still enabled `pyo3/extension-module`. Modern PyO3 guidance for current
  `maturin` releases is to let the build backend control extension-module build
  mode so Rust test binaries can still link.
- Follow-up review feedback showed that the first implementation was still
  carrying an avoidable internal Rust `BridgeDocument` layer. The bridge now
  maps directly from `ExtractDocument` into Python objects, and the Python
  adapter owns the runtime payload validation.

## Decision Log

- 2026-04-22: This plan proposes one public Python-facing entrypoint named
  `extract_document` under `stilyagi.engine`. Rationale: it keeps the package
  root narrow and aligns with the existing engine boundary. It also leaves room
  to extend dispatch for Python and Rust source syntaxes later without forcing
  another public move.

- 2026-04-22: This plan keeps `hello()` in place while adding the first real
  extraction bridge. Rationale: roadmap item 1.2.2 requires a real extraction
  call, but it does not require removing the existing smoke helper. Keeping
  `hello()` reduces churn and avoids turning this bridge proof into a broader
  compatibility cleanup.

- 2026-04-22: This plan routes the first extraction implementation through
  `crates/stilyagi-extract/` instead of `crates/stilyagi-core/`. Rationale: the
  design already reserves `stilyagi-extract` as the extraction seam. Parking
  the first extraction result in `stilyagi-core` would blur the long-term crate
  responsibilities.

- 2026-04-22: This plan recommends a partial document result and explicitly
  avoids moving that result into `crates/stilyagi-ir/` yet. Rationale: roadmap
  item 1.2.2 proves the boundary; roadmap item 2.1.1 settles the fuller IR
  contract. Keeping the first bridge payload narrow avoids freezing the wrong
  shape too early.

- 2026-04-22: The implemented PyO3 function is named `extract_document` and
  accepts `source` plus the stable syntax string (for example `"markdown"`).
  Rationale: this keeps the extension boundary syntax-neutral while still
  letting the public Python package expose one typed function under
  `stilyagi.engine`.

- 2026-04-22: The raw PyO3 payload remains an internal Python dictionary that
  `python/stilyagi/engine/extraction.py` immediately adapts into
  `stilyagi.model.Document`. Rationale: the roadmap only needs a real
  in-process bridge proof here, and keeping the raw payload internal avoids
  freezing the wrong public transport before the fuller IR contract lands.

- 2026-04-22: The workspace now enables `pyo3` with `auto-initialize` instead
  of the shared `extension-module` feature. Rationale: local `maturin` builds
  still succeed, and Rust-side `cargo test` for the PyO3 crate now links and
  runs without the unresolved Python symbols caused by `extension-module`.

- 2026-04-22: Review follow-up work removed the internal Rust `BridgeRegion` and
  `BridgeDocument` types, and the PyO3 tests now inspect the real Python-shaped
  payload returned by `extract_document_py`. Rationale: this keeps the bridge
  surface closer to the shipped API and reduces representation drift inside the
  Rust crate.

- 2026-04-22: Review follow-up work exposed `supported_syntaxes()` from the
  extension and validates that its Rust-owned spellings match `model.Syntax`.
  Rationale: the bridge still crosses a string-based boundary, so the next-best
  single source of truth is to have Python verify that it is consuming the Rust
  extractor's declared syntax vocabulary instead of assuming the enum values
  always stay aligned by accident.

## Outcomes & Retrospective

- Shipped:
  - `crates/stilyagi-extract/` now owns a minimal `extract_document(...)`
    function, `ExtractSyntax`, `ExtractDocument`, `ExtractRegion`, and explicit
    unsupported-syntax errors.
  - `crates/stilyagi-pyext/` now exposes a real `extract_document` PyO3
    function that delegates to `stilyagi-extract` and keeps `hello()` as the
    additive smoke helper.
  - `python/stilyagi/engine/extraction.py` now adapts the raw bridge payload
    into `stilyagi.model.Document`, and `stilyagi.engine.extract_document(...)`
    is the supported public Python entrypoint.
  - The Rust and Python tests now prove happy paths, blank-input behaviour, and
    unsupported-syntax failures across the real in-process extension boundary.
  - The design document, developer's guide, user's guide, and roadmap now all
    describe the shipped bridge accurately.

- Exact validation evidence:
  - `make lint`
  - `make typecheck`
  - `make test`
  - `make markdownlint`
  - `make nixie`
  - Focused red-state evidence was captured before implementation with:
    `cargo test --manifest-path crates/stilyagi-extract/Cargo.toml` and
    `.venv/bin/python -m pytest -v tests/test_package_skeleton_units.py -k extract_document`.

- Observable success proof:

  ```python
  from stilyagi import engine, model

  document = engine.extract_document("# Heading", model.Syntax.MARKDOWN)
  assert document.syntax is model.Syntax.MARKDOWN
  assert document.regions == (model.Region(kind="document", text="# Heading"),)
  ```

- Materialized risk and handling:
  - The PyO3 crate initially failed to link under `cargo test` while the
    workspace still enabled `pyo3/extension-module`. The implementation adopted
    current PyO3 guidance for modern `maturin` builds by removing that shared
    feature flag and relying on `auto-initialize` for test execution.

- Deviations from the draft:
  - The extension function shipped as syntax-neutral `extract_document(source,
    syntax)` rather than a Markdown-specific function name. This stayed within
    the plan's tolerances and better matched the Python model's existing syntax
    enum without broadening the public surface.

- Lesson for later roadmap items:
  - The `stilyagi-extract` -> `stilyagi-pyext` -> `stilyagi.engine` layering is
    viable, so later IR expansion should refine the partial payload in place
    rather than inventing a second bridge surface.
