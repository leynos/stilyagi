# User's guide

This guide is for people who use Stilyagi rather than modify its internals. It
currently records the user-visible v1 promises that are already settled, even
while the linter itself is still under construction.

## 1. Packaging model

Stilyagi's v1 packaging boundary is a single Python-distributed application
with an embedded Rust extension module. Users should expect one installable
Python package, not a Python wrapper that shells out to a separately managed
Rust helper binary.[^1][^2]

For users, that means:

- installation and environment selection happen through the Python package
  surface;
- the Rust extraction engine is part of that package's runtime, not a second
  tool to locate or configure separately; and
- normal execution does not depend on launching a helper process for every
  extraction call.

In editable development installs, the embedded extension now lives under the
package as `stilyagi._stilyagi_rs` rather than as a separate top-level module.
That relocation is an internal packaging detail. User code should still import
the public `stilyagi` package rather than importing the extension module
directly.

## 1a. Current import surface and migration notes

The mixed-package skeleton already exposes a small, concrete import surface
that later roadmap slices will extend in place:

```python
import stilyagi
from stilyagi import engine, model
from stilyagi.config import StilyagiConfig
from stilyagi.diagnostics import Diagnostic
from stilyagi.nlp import SpacyProviderConfig
```

The current placeholder modules are intentionally narrow, but each one already
owns a long-lived architectural role:

- `stilyagi.hello()` exercises the embedded Rust bridge and is the current
  smoke path for the package skeleton.
- `stilyagi.engine` is the future home for execution planning, fix planning,
  rendering, and runner orchestration. It now also exposes the first real
  extraction call:

  ```python
  from stilyagi import engine, model

  document = engine.extract_document("# Heading", model.Syntax.MARKDOWN)
  assert document.syntax is model.Syntax.MARKDOWN
  assert document.regions[0].text == "# Heading"
  ```

- `stilyagi.model` is the future home for document, region, sentence, and
  token runtime objects.
- `stilyagi.config.StilyagiConfig` is the Python-side configuration boundary.
- `stilyagi.diagnostics.Diagnostic` is the Python-side diagnostic boundary.
- `stilyagi.nlp` is the future natural-language-processing (NLP) provider and
  provider-configuration boundary.
- `stilyagi.plugins` defines the entry-point group names that future external
  rule and capability packages will use.
- `stilyagi.rules` and `stilyagi.rules.builtin` reserve the bundled-rule and
  third-party-rule namespace layout.

Users migrating from the provisional repository layout should also note one
removal:

```python
# Old provisional import path
from stilyagi.pure import hello

# Supported mixed-package skeleton path
import stilyagi

stilyagi.hello()
```

`stilyagi.pure` was a compatibility shim from the pre-workspace layout and is
no longer part of the supported package contract.

The new extraction path is intentionally narrow in this slice:

- `stilyagi.engine.extract_document(...)` is the supported public API for the
  first real Rust extraction call.
- `model.Syntax.MARKDOWN` is the only currently implemented syntax for that
  API.
- `model.Syntax.PYTHON_DOCSTRING` and `model.Syntax.RUST_DOC_COMMENT` are part
  of the planned model vocabulary, but they currently raise
  `NotImplementedError` when passed to `extract_document(...)`.
- `stilyagi._stilyagi_rs` remains an internal bridge module. User code should
  call `stilyagi.engine.extract_document(...)` rather than importing the raw
  bridge directly.

## 1b. Package smoke check

Stilyagi ships a built-in smoke check that confirms the embedded Rust extension
module is correctly installed and reachable from Python. It is available as a
CLI entrypoint:

```shell
python -m stilyagi.smoke
```

The command exits with status `0` when the bridge is healthy and `1` on any
failure, making it suitable for Makefile targets and CI steps.

The same check is also callable programmatically:

```python
from stilyagi.smoke import SmokeCheckError, smoke_installed_package

try:
    smoke_installed_package()
except SmokeCheckError as err:
    print(f"Bridge check failed: {err}")
```

`smoke_installed_package()` accepts an optional `extract_fn` keyword argument
for testing purposes; in normal use the default `engine.extract_document` is
used. `SmokeCheckError` is a `RuntimeError` subclass raised for any failure,
including bridge errors, unexpected return types, and document validation
failures.

## 2. What this does and does not promise

The accepted v1 contract is narrower than the architecture's long-term
ambitions. Stilyagi is intentionally fixing a small, explicit day-one promise
before broader syntax and locale work lands.

It does promise:

- one package-oriented installation story for v1;
- one in-process runtime boundary between Python orchestration and Rust
  extraction;
- no mandatory helper-binary management in normal use;
- a global `-V` / `--version` flag alongside the `version` subcommand;
- a `--no-cache` option for `stilyagi check`;
- stable support for Markdown documents, Python docstrings, and Rust
  documentation comments; and
- English as the only formally supported v1 locale.[^1][^4]

It also promises that `dump-ir` and related debugging or fixture workflows will
use canonical JSON output, even though the in-process runtime may use a more
efficient transport internally.[^4]

It does not yet promise:

- the final end-user command set;
- full Markdown with JSX (MDX) support as part of the stable v1 syntax matrix;
- support for locales beyond English;
- the final release channels or installation instructions for each platform; or
- the exact debugging and diagnostic workflows, which land in later roadmap
  slices.[^3]

## 3. Supported surfaces in v1

The stable v1 support matrix currently covers these prose surfaces:

- Markdown files;
- Python docstrings; and
- Rust documentation comments.[^4]

MDX remains preview-only. That means the architecture may continue to explore
it, but users should not yet depend on MDX behaviour as part of Stilyagi's
stable v1 contract.[^4]

When the command-line interface (CLI) discovery contract lands, the stable
default recursive file set will cover `*.md`, `*.py`, and `*.rs`. MDX stays
outside that default set until preview behaviour graduates into the stable
support matrix.

## 4. Locale policy in v1

English is the only formally supported v1 locale. The design keeps locale and
natural-language metadata explicit so other locales can be added later, but v1
does not claim broader best-effort language support.[^4]

For users, that means any language-aware rule behaviour and performance
expectations in the first releases are defined around English only.

## 5. Current state of the product

The repository already uses `maturin` to build and develop the embedded
extension from the `python/` plus `crates/` mixed-package skeleton, but
Stilyagi is still in the roadmap phase where architectural contracts are being
ratified before feature-complete releases land.[^2][^3]

For day-to-day users, the mixed-package skeleton changes three practical things:

- the installation model is still one Python package, even though the
  repository now has explicit `python/` and `crates/` source roots;
- editable installations compile the embedded Rust extension into the Python
  package namespace as `stilyagi._stilyagi_rs`; and
- the placeholder engine, model, NLP, diagnostic, plugin, and rule modules now
  exist as stable import locations for later feature slices, so users should
  expect future releases to extend those modules rather than moving them again.
- source checkouts use `make build` for development installs and
  `make release` for release wheel builds; both workflows run the same package
  smoke check through the public Python engine API and embedded Rust extension.

The first implemented extractor proof now crosses the embedded Rust boundary
without shelling out to a helper binary. Today that proof is deliberately
small: non-blank Markdown input returns a document with one `document` region,
blank Markdown input returns zero regions, and later roadmap items will refine
that payload into the fuller IR contract.

Until the command-line interface (CLI) and feature slices are implemented,
treat this guide as a record of the stable user-facing v1 contract rather than
as a complete operating manual.

## References

[^1]: [ADR 002: Ratify the packaging boundary](adr-002-packaging-boundary.md)
[^2]: [Developer's guide](developers-guide.md)
[^3]: [Roadmap](roadmap.md)
[^4]: [ADR 003: Ratify the v1 contract scope](adr-003-v1-contract-scope.md)
