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

- `stilyagi.hello()` is a placeholder that exercises the embedded Rust bridge
  directly; it is not the canonical smoke check. See §1b for the supported
  package smoke check.
- `stilyagi.engine` is the future home for execution planning, fix planning,
  rendering, and runner orchestration. It now also exposes the first real
  extraction call:

  ```python
  from stilyagi import engine, model

  document = engine.extract_document("# Heading", model.Syntax.MARKDOWN)
  assert document.syntax is model.Syntax.MARKDOWN
  assert document.regions[0].kind == "heading"
  assert document.regions[0].text == "Heading"
  assert document.ir is not None
  assert document.ir["schema_version"] == "1.0.0"
  ```

  Query the current IR region-kind vocabulary before writing code that branches
  on region kinds:

  ```python
  from stilyagi import engine

  assert "heading" in engine.supported_region_kinds()
  assert "link_title" in engine.supported_region_kinds()
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

```shell
python -m stilyagi.smoke
```

The supported smoke-check entrypoint is `python -m stilyagi.smoke`. It exits
with status `0` when the embedded Rust extension is installed and reachable
from Python, and `1` on any smoke-check failure.

The same check is available as a public Python API:

```python
from stilyagi.smoke import SmokeCheckError, smoke_installed_package

try:
    smoke_installed_package()
except SmokeCheckError as err:
    print(f"Bridge check failed: {err}")
```

`stilyagi.pure` was a compatibility shim from the pre-workspace layout and is
no longer part of the supported package contract. Use
`smoke_installed_package()` when code needs to prove the installed package can
cross the Python-to-Rust bridge; it raises `SmokeCheckError` for bridge errors,
unexpected return types, and document validation failures.

The new extraction path is intentionally narrow in this slice:

- `stilyagi.engine.extract_document(...)` is the supported public API for the
  first real Rust extraction call.
- `model.Syntax.MARKDOWN` and `model.Syntax.PYTHON_DOCSTRING` are currently
  implemented for that API.
- `model.Syntax.RUST_DOC_COMMENT` remains part of the planned model vocabulary,
  but currently raises `NotImplementedError` when passed to
  `extract_document(...)`.
- Markdown documents and Python docstrings expose a parsed `document.ir`
  mapping containing the canonical IR envelope. That mapping includes schema
  metadata, `line_index`, tree nodes, region `segments`, and content hashes.
- Markdown IR regions currently include text-bearing `heading`, `paragraph`,
  and `table_cell` regions; structural `list_item` and `blockquote` container
  regions; source-backed whole-block `frontmatter`; and synthetic decoded
  `image_alt` and `link_title` regions.
- Python docstring extraction emits `python_docstring` regions for module,
  class, and function docstrings. Each region includes source-backed `segments`
  and `owner` metadata in `document.ir`, so later rules can tell whether the
  prose belongs to a module, class, method, or function without walking raw
  Python syntax nodes.
- `document.regions` exposes the same supported region-kind spellings as a
  compact typed Python view. Inspect `region.kind` and `region.text` for common
  workflows, and use `document.ir["regions"]` when byte spans, scopes, or
  segment origins are needed.
- When `document.ir["regions"]` contains an unknown future region kind, the
  Python adapter logs a warning and preserves the region in `document.ir`
  rather than rejecting the document.
- `list_item` and `blockquote` regions are containers. Their prose normally
  appears in child regions linked through `parent_region`.
- `image_alt` and `link_title` expose decoded lint text. They are inspection
  surfaces in `document.ir`, but their segments are synthetic until
  byte-accurate edit spans are implemented.
- `stilyagi._stilyagi_rs` remains an internal bridge module. User code should
  call `stilyagi.engine.extract_document(...)` rather than importing the raw
  bridge directly.

A minimal Python docstring extraction example:

```python
from stilyagi import engine, model

source = '''"""Module docs."""


class Example:
    """Class docs."""
'''

document = engine.extract_document(source, model.Syntax.PYTHON_DOCSTRING)
assert [region.kind for region in document.regions] == [
    "python_docstring",
    "python_docstring",
]
assert document.ir is not None
assert document.ir["regions"][1]["owner"] == {
    "kind": "class",
    "name": "Example",
    "qualname": "Example",
}
```

> **Bridge helpers:** `stilyagi_extract::RegionKind::ALL` and
> `RegionKind::ir_region_kind()` are Rust-internal bridge helpers and are not
> exposed across the Python boundary. Use `engine.supported_region_kinds()` as
> the Python-facing source of truth for supported region kinds. See the
> [RegionKind and typed ExtractRegion API](developers-guide.md#regionkind-and-typed-extractregion-api)
> for the Rust details.

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

### Checking Markdown with `stilyagi check`

The first command-line surface in v1 is `stilyagi check` for Markdown files.
It discovers Markdown targets recursively, resolves the nearest supported
configuration for each file, and renders deterministic diagnostics. The
command currently analyses Markdown files only (`*.md` and `*.markdown`).

#### Output formats

Use `--output-format text` (the default) for human-readable output: one line
per diagnostic followed by a summary line. Use `--output-format json` for
machine-readable output: a stable JSON document. `--output-format sarif` is
planned for a later slice and is not yet available; requesting it fails with
a message stating it is planned but not yet available.

#### Configuration

Pass `--config` with an explicit config file path or an inline TOML fragment
to supply configuration directly. Use `--isolated` to bypass configuration
discovery entirely.

#### Standard input

Pass `-` as the target to read Markdown from standard input instead of from
files on disk. Use `--stdin-filename PATH` to attribute diagnostics to PATH
rather than the default `<stdin>`. Combining `-` with file targets is a
usage error (exit code 2).

#### Exit codes

The command exits with one of three codes:

- `0` — no diagnostics found.
- `1` — one or more diagnostics found.
- `2` — error: a failed file read, invalid configuration, an extractor
  failure, or a usage error.

Examples:

```shell
stilyagi check .
stilyagi check docs/ --output-format json
stilyagi check README.md --isolated
stilyagi check - --stdin-filename README.md
```

## 4. Locale policy in v1

English is the only formally supported v1 locale. The design keeps locale and
natural-language metadata explicit so other locales can be added later, but v1
does not claim broader best-effort language support.[^4]

For users, that means any language-aware rule behaviour and performance
expectations in the first releases are defined around English only.

## 5. Current state of the product

Stilyagi is still in the roadmap phase where architectural contracts are being
ratified before feature-complete releases land.[^2][^3] The stable user-facing
surface is still the Python package API, but `stilyagi check` is now available
for Markdown repositories.

Use `engine.extract_document()` to extract Markdown through the public engine
boundary. Non-blank Markdown input returns typed `document.regions` for
source-backed regions such as `heading`, `paragraph`, and `table_cell`, plus
container and decoded-text region kinds when the source contains lists,
blockquotes, frontmatter, images, or link titles. Blank Markdown input returns
zero regions.

Markdown input also carries a canonical IR envelope on `Document.ir`, and
Python docstring plus Rust doc-comment inputs expose `python_docstring` and
`rust_doc_comment` regions with owner metadata through the same payload.
`engine.supported_region_kinds()` returns the region-kind vocabulary supported
by the installed package version.

The remaining CLI subcommands and fix workflows land in later roadmap slices,
so treat this guide as a record of the settled user-facing v1 contract rather
than as a complete operating manual.

## References

[^1]: [ADR 002: Ratify the packaging boundary](adr-002-packaging-boundary.md)
[^2]: [Developer's guide](developers-guide.md)
[^3]: [Roadmap](roadmap.md)
[^4]: [ADR 003: Ratify the v1 contract scope](adr-003-v1-contract-scope.md)
