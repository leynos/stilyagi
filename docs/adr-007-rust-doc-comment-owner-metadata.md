# Architectural decision record (ADR) 007: Adopt Rust documentation-comment owner metadata

## Status

Accepted

## Date

2026-07-04

## Context and Problem Statement

Rust documentation-comment extraction now needs the same IR guarantees as
Python docstrings: stable owner metadata, exact source-backed text, deterministic
region ordering, and recoverable parse behaviour. The extractor must also
preserve Rust-specific semantics for inner versus outer doc comments, repeated
line-comment runs, and qualified names across nested modules and impl blocks.

How should Rust doc-comment regions expose owner identity and source text
without forcing rules to navigate the full tree-sitter concrete syntax tree?

## Decision outcome

In the context of Rust documentation-comment extraction for v1, facing owner
metadata, inner and outer attachment, and `::` qualified names, we decided for
explicit `owner` metadata, merged doc-comment regions, verbatim content
segments, and a bounded node store, and against raw CST navigation or
rustdoc-style normalisation, to achieve stable source-faithful IR and
recoverable parse behaviour, accepting the downside that crate-root module
owners stay anonymous and trait-impl method names use the implementor-type
prefix.

Rust doc-comment regions reuse the ADR 006 owner contract with Rust-specific
`kind`, optional `name`, and optional `qualname` fields. Outer doc comments
attach to the immediately following item; inner doc comments attach to the
enclosing item or crate root. Consecutive same-flavour line comments merge into
one `rust_doc_comment` region, with synthetic separators inserted between the
source-backed segments so the flattened prose still reconstructs exactly.

Rust `qualname` semantics use `::`-joined enclosing named items. Impl methods
use the implementor type as the prefix (`Type::method`), and trait-impl methods
follow the same implementor-type prefix in v1. Crate-root inner doc comments
emit anonymous module owners (`kind: "module"`, `name: null`,
`qualname: null`), and unrecognised item kinds fall back to `kind: "item"`.

## Options considered

<!-- markdownlint-disable MD060 -->
| Alternative                                                                      | Rationale                                 | Trade-offs                                                                    |
| -------------------------------------------------------------------------------- | ----------------------------------------- | ----------------------------------------------------------------------------- |
| Derive owner identity from raw CST traversal in rules                            | Keeps the extractor thinner.              | Couples rules to parser details and duplicates owner logic in every rule pack. |
| Normalise or clean doc comments during extraction                                | Produces rustdoc-style prose immediately. | Breaks the verbatim source contract and weakens segment reconstruction.        |
| Expose the full Rust tree-sitter tree as a stable v1 rule contract               | Gives rules maximum syntax access.        | Makes grammar upgrades much harder to absorb.                                  |
<!-- markdownlint-enable MD060 -->

## Consequences

- `rust_doc_comment` regions carry `owner.kind` values of `module`, `struct`,
  `enum`, `union`, `trait`, `function`, `const`, `static`, `type`, `macro`,
  `impl`, or `item`, with `name` and `qualname` populated when the syntax
  supplies stable owner names.
- The Rust producer metadata records `node_store: "bounded"` and
  `owner_qualname: "rust"`. Rules that need the full Rust CST, rustdoc
  cleaning, or package-qualified module names must plan a later contract
  expansion.
- The bounded node store only emits doc-comment-owning item nodes, plus the
  synthetic crate root and emitted doc-comment nodes. Undocumented enclosing
  items collapse to the nearest emitted owner, matching the Python extractor's
  bounded-store behaviour.
- Recoverable Rust parse anomalies stay in `IrError` entries rather than
  aborting extraction, so the bridge can surface partial IR alongside the
  surviving doc-comment regions. When tree-sitter collapses a malformed item
  into an `ERROR` subtree, the extractor keeps the crate-level and later
  surviving doc-comment regions, but docs absorbed into that `ERROR` subtree
  are not recovered as separate regions.
