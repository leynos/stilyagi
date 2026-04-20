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

## 2. What this does and does not promise

The accepted v1 contract is narrower than the architecture's long-term
ambitions. Stilyagi is intentionally fixing a small, explicit day-one promise
before broader syntax and locale work lands.

It does promise:

- one package-oriented installation story for v1;
- one in-process runtime boundary between Python orchestration and Rust
  extraction;
- no mandatory helper-binary management in normal use;
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
extension, but Stilyagi is still in the roadmap phase where architectural
contracts are being ratified before feature-complete releases land.[^2][^3]

Until the command-line interface (CLI) and feature slices are implemented,
treat this guide as a record of the stable user-facing v1 contract rather than
as a complete operating manual.

## References

[^1]: [ADR 002: Ratify the packaging boundary](adr-002-packaging-boundary.md)
[^2]: [Developer's guide](developers-guide.md)
[^3]: [Roadmap](roadmap.md)
[^4]: [ADR 003: Ratify the v1 contract scope](adr-003-v1-contract-scope.md)
