# Architectural decision record (ADR) 005: Scope Markdown region vocabulary

## Status

Accepted. Markdown v1 emits thin structural container regions, whole-block
frontmatter, and synthetic decoded alt/title regions; `frontmatter_field`
remains reserved.

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

The immediate question is how Stilyagi should emit the promised Markdown region
kinds without creating ambiguous fix targets or plausible-but-wrong source
spans.

## Decision drivers

- Source spans must be re-sliceable: a source-backed segment must satisfy
  `source[span] == segment.text`.
- Child prose ownership must stay unambiguous: structural Markdown containers
  should not duplicate prose already emitted by child regions.
- Dependency scope must stay bounded: field-level frontmatter spans require a
  YAML/TOML parser and should not be inferred by guessing.

## Options considered

- Emit prose-bearing `list_item` and `blockquote` regions that duplicate child
  paragraph text.
- Emit thin structural `list_item` and `blockquote` regions whose child prose
  regions point back through `parent_region`.
- Guess byte spans for decoded image alt text and link titles.
- Emit decoded image alt text and link titles as synthetic lint surfaces until
  byte-accurate spans can be proven.
- Parse YAML/TOML frontmatter fields in this slice.
- Reserve `frontmatter_field` until field-level source spans can be generated
  without guessing.

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

This gives deterministic region coverage whose segments can be validated by
re-slicing source bytes, while avoiding duplicated prose and guessed source
positions.

## Known risks and limitations

- Golden fixture coverage can require every emitted Markdown region kind to
  satisfy reconstruction, parent, origin-node, and source re-slice invariants.
- Rules that need list-item or blockquote context can navigate through
  `parent_region` rather than receiving duplicated prose bytes.
- Field-level frontmatter rules and byte-accurate alt/title fixes remain
  future work and must not be inferred from guessed source positions.
- `frontmatter_field` remains a reserved vocabulary item, not an emitted
  Markdown v1 region kind.
- Byte-accurate spans for decoded image alt text and link titles are future
  work.
