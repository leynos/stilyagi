# Architectural decision record (ADR) 005: Scope Markdown region vocabulary

## Status

Accepted.

## Date

2026-06-14.

## Context and problem statement

RFC 0001 names the v1 IR region vocabulary, including Markdown structural
containers, frontmatter, image alternative text, and link titles. Roadmap item
2.1.2 turns that vocabulary into executable golden fixture coverage. During
implementation, three source-fidelity constraints became load-bearing:

- `list_item` and `blockquote` own child block prose rather than inline prose.
- `markdown-rs` exposes image alt text and link titles as decoded strings
  without sub-positioned source spans.
- `frontmatter` carries a positioned fenced block, but field-level YAML/TOML
  source spans require an additional parser and dependency.

The immediate question is therefore:

How should Stilyagi emit the promised Markdown region kinds without creating
ambiguous fix targets or plausible-but-wrong source spans?

## Y-Statement

In the context of Markdown IR region emission for v1 golden fixtures, facing
source-span fidelity, child-prose ownership, and dependency-scope concerns, we
decided for thin structural `list_item` and `blockquote` regions plus
source-backed whole-block `frontmatter` and synthetic decoded `image_alt` /
`link_title` regions, and against prose-bearing container regions, guessed
alt/title source spans, and field-level frontmatter parsing in this slice, to
achieve deterministic region coverage whose segments can be validated by
re-slicing source bytes, accepting that `frontmatter_field` remains reserved
and later work is needed for byte-accurate alt/title and field spans.

## Decision outcome

`list_item` and `blockquote` regions are thin structural regions. They carry no
prose text and no segments. Their child paragraph, table, or other prose
regions use `parent_region`, `scope`, and `attrs` to expose the structural
context.

`frontmatter` regions are source-backed over the whole fenced YAML or TOML
block. `frontmatter_field` remains a reserved vocabulary item and is not
emitted until a later slice can parse field-level source spans without guessing.

`image_alt` and `link_title` regions use synthetic `decoded_text` segments in
this slice. They are explicit lint surfaces, but they do not claim editable
source bytes until a later implementation can prove byte-accurate spans.

## Consequences

- Golden fixture coverage can require every emitted Markdown region kind to
  satisfy reconstruction, parent, origin-node, and source re-slice invariants.
- Rules that need list-item or blockquote context can navigate through
  `parent_region` rather than receiving duplicated prose bytes.
- Field-level frontmatter rules and byte-accurate alt/title fixes remain
  future work and must not be inferred from guessed source positions.
