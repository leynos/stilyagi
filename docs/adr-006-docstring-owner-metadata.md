# Architectural decision record (ADR) 006: Adopt docstring owner metadata

## Status

Accepted

## Date

2026-06-15

## Context and Problem Statement

Owner-aware Python docstring extraction for Stilyagi's stable intermediate
representation (IR) needs to identify whether each extracted prose region comes
from a module, class, or function. Later docstring rules need that owner
identity, but the v1 rule contract should not require rule authors to navigate
raw tree-sitter concrete syntax trees.

The extractor must also preserve source-faithful text and spans. Decoding
escapes, dedenting, or cleaning docstrings during extraction would make the
lint surface less directly tied to source bytes and would move Python docstring
policy into the Rust extractor before the rule layer exists.

How should Python docstring regions expose owner identity and source text
without binding v1 rules to the full Python tree-sitter syntax tree?

## Decision outcome

Adopt explicit `owner` metadata with `kind`, optional `name`, and optional
`qualname`. Python class and function owners use Python `__qualname__`
semantics, including `<locals>` markers for definitions nested inside function
bodies. Module owners remain anonymous in v1.

Python docstring text is emitted verbatim from tree-sitter `string_content`
source spans. The Python producer exposes a bounded node store rather than the
full concrete syntax tree.

## Options considered

| Alternative                                                                                      | Rationale                                    | Trade-offs                                                                        |
| ------------------------------------------------------------------------------------------------ | -------------------------------------------- | --------------------------------------------------------------------------------- |
| Derive owner identity from raw tree traversal in Python rules                                    | Avoids adding owner policy to the extractor. | Couples rules to parser details and recreates extractor logic in every rule pack. |
| Decode, dedent, or apply [PEP 257](https://peps.python.org/pep-0257/) cleaning during extraction | May be useful for later rule analysis.       | Weakens the source-backed segment contract at the extraction layer.               |
| Expose the full Python tree-sitter tree as a stable v1 rule contract                             | Gives rules maximum syntax access.           | Makes future grammar upgrades much harder to absorb.                              |

Table: Python docstring owner metadata alternatives.

## Consequences

- Python `python_docstring` regions carry `owner.kind` values of `module`,
  `class`, or `function`; class and function owners include `name` and
  `qualname`, while module owners emit `name: null` and `qualname: null`
  because string-only extraction has no package-resolution context.
- Python qualified names follow Python's `__qualname__` shape, including
  `<locals>` after function frames when another class or function is declared
  inside the function body.
- The tree-sitter producer metadata records `node_store: "bounded"` and
  `owner_qualname: "python"`. Rules that need decorators, signatures, base
  classes, or package-qualified module names must plan a later full-tree or
  richer-owner migration instead of inferring those facts from the v1 bounded
  node store.

## Architectural Rationale

Explicit owner metadata keeps the v1 rule contract centred on stable IR facts
rather than parser navigation. Rules can ask whether a region belongs to a
module, class, or function without knowing tree-sitter node names, decorator
wrappers, or traversal details. That makes the Python slice useful now while
leaving room for Rust documentation-comment extraction to reuse the same owner
field with Rust-specific owner kinds and qualified-name semantics.

The bounded node store also preserves the source-backed segment contract.
Regions still point back to concrete source spans and contributing nodes, but
the API does not promise full concrete syntax tree access. That boundary keeps
future parser and grammar upgrades manageable, avoids premature coupling to
Python CST details, and lets later slices deliberately expand syntax metadata
only when rule requirements justify it.

## Follow-on work

- Rust documentation-comment extraction should reuse the same `owner` field
  contract while defining Rust-specific owner kinds and qualified-name
  semantics in a separate implementation slice.
- A future package-aware extraction entrypoint may migrate module owners from
  anonymous `null` names to package-qualified module names once the caller can
  supply trustworthy package context.
