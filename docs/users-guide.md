# User's guide

This guide is for people who use Stilyagi rather than modify its internals. It
currently records the user-visible packaging and installation promises that are
already settled for v1, even while the linter itself is still under
construction.

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

This packaging decision settles the runtime boundary, not the full user
workflow.

It does promise:

- one package-oriented installation story for v1;
- one in-process runtime boundary between Python orchestration and Rust
  extraction; and
- no mandatory helper-binary management in normal use.[^1]

It does not yet promise:

- the final end-user command set;
- the final supported syntax matrix;
- the final release channels or installation instructions for each platform; or
- the exact debugging and diagnostic workflows, which land in later roadmap
  slices.[^3]

## 3. Current state of the product

The repository already uses `maturin` to build and develop the embedded
extension, but Stilyagi is still in the roadmap phase where architectural
contracts are being ratified before feature-complete releases land.[^2][^3]

Until the CLI and feature slices are implemented, treat this guide as a record
of the stable user-facing packaging promise rather than as a complete operating
manual.

## References

[^1]: [ADR 002: Ratify the packaging boundary](adr-002-packaging-boundary.md)
[^2]: [Developer's guide](developers-guide.md)
[^3]: [Roadmap](roadmap.md)
