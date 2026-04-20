# RFC 0001: Stilyagi Intermediate Representation

## Preamble

- RFC: 0001
- Status: Proposed
- Created: 2026-04-14
- Target: Stilyagi 0.1
- Depends on: None

## 1. Summary

Stilyagi SHALL use a versioned intermediate representation, “Stilyagi IR”, as
the contract between the Rust extraction frontend and the Python analysis
engine.

The IR SHALL preserve two things at once:

1. structural syntax, for rules that care about headings, lists, frontmatter,
   docstrings, comment blocks, and host-language syntax, and
2. lintable regions, for rules that care about human-facing prose as text.

The IR SHALL treat source offsets as the ground truth. Every diagnostic and
every fix SHALL ultimately anchor to original source bytes, not to
reconstructed prose alone.

## 2. Goals

The IR exists to solve four problems.

First, it needs to carry Markdown structure in a form close enough to mdast
that Stilyagi can inherit a mature vocabulary instead of inventing seventeen
fresh synonyms for “paragraph.” mdast already defines the core node taxonomy,
including structural and extension nodes such as `root`, `paragraph`,
`listItem`, `image` with `alt`, and YAML frontmatter. `markdown-rs` already
exposes `to_mdast()`, advertises positional fidelity, and supports the relevant
Markdown extensions.[^1][^2]

Second, it needs to carry code-adjacent structure for docstrings and comments.
tree-sitter is a sensible substrate because it builds concrete syntax trees,
updates incrementally, stays useful under syntax errors, and supports a query
language with field constraints and error nodes.[^3]

Third, it needs to expose lintable prose as regions rather than force every
rule to re-flatten AST nodes into text.

Fourth, it needs to remain boring enough to serialize, diff, debug, and cache
reliably.

## 3. Non-goals

This RFC does not define natural language processing (NLP) annotations such as
tokens, lemmas, parts of speech (POS) tags, dependencies, or vectors. RFC 0002
defines those as runtime capabilities layered on top of the IR.

This RFC does not require Stilyagi to persist full spaCy `Doc` objects. spaCy’s
runtime objects depend on which components are loaded, and `Token` and `Span`
are views over a parent `Doc`, not a transport format.[^4]

This RFC does not require cross-file repository graphs in v1. One IR document
corresponds to one source file or one standard input (stdin) payload.

## 4. Top-level document envelope

A Stilyagi IR document SHALL contain these top-level fields:

- `schema_version`: semantic version string for the IR schema, for example
  `1.0.0`.
- `document`: metadata about the source document.
- `producers`: the parsers and extractors that produced the IR.
- `line_index`: monotonically increasing UTF-8 byte offsets for line starts.
- `trees`: the structural trees contained in the document.
- `nodes`: the node store for those trees.
- `regions`: extracted lintable prose regions.
- `suppressions`: source-level suppression directives discovered by the
  frontend.
- `errors`: non-fatal parse and extraction anomalies.
- `metadata`: extensible map for future additions.

`document` SHALL include at least:

- `uri`
- `path`
- `syntax`
- `encoding`
- `content_hash`

`document` MAY also include `natural_language` when the source document's
dominant human language is known. `syntax` identifies the source format, such
as Markdown, Python, or Rust. It MUST NOT be overloaded to mean the prose
locale inside the extracted regions.

In v1, `natural_language` formally supports only the `en` locale. Broader
locale or multilingual guarantees are deferred to later roadmap slices and the
tests that will justify them.

`producers` SHALL record the toolchain used to create the IR, including parser
names, versions, and relevant parse options. This requirement exists so that
cache keys and bug reports stay honest.

A minimal envelope looks like this. The example shows the smallest complete IR
document, including document metadata, one producer record, and the top-level
collections that later sections populate in more detail:

```json
{
  "schema_version": "1.0.0",
  "document": {
    "uri": "file:///repo/docs/guide.md",
    "path": "docs/guide.md",
    "syntax": "markdown",
    "natural_language": "en",
    "encoding": "utf-8",
    "content_hash": "sha256:..."
  },
  "producers": [
    {
      "kind": "markdown",
      "name": "markdown-rs",
      "version": "1.0.0",
      "options": {
        "gfm": true,
        "frontmatter": true,
        "mdx": false
      }
    }
  ],
  "line_index": [0, 12, 37],
  "trees": [],
  "nodes": [],
  "regions": [],
  "suppressions": [],
  "errors": [],
  "metadata": {}
}
```

## 5. Trees and nodes

The IR SHALL support multiple structural trees in one document. A Markdown file
may only need one mdast tree. A source file may only need one tree-sitter tree.
A mixed-format file MAY expose more than one tree later.

Each tree SHALL contain:

- `id`
- `family`, one of `mdast`, `tree-sitter`, or `synthetic`
- `syntax`
- `root`

Each node SHALL contain:

- `id`
- `tree`
- `kind`
- `parent`
- `children`
- `fields`
- `props`
- `span`
- `flags`

`span` SHALL use UTF-8 byte offsets as the canonical source coordinates:

```json
{
  "byte_start": 128,
  "byte_end": 167,
  "line_start": 10,
  "column_start": 1,
  "line_end": 10,
  "column_end": 40
}
```

`flags` SHOULD support at least:

- `named`
- `error`
- `missing`
- `synthetic`

For mdast-backed trees, `kind` and `props` SHOULD preserve mdast naming where
practical. That means `kind: "paragraph"` stays `paragraph`, `kind: "listItem"`
stays `listItem`, image nodes keep `alt`, code blocks keep `lang` and `meta`,
and YAML frontmatter keeps its literal value. That choice buys interoperation
with mdast-shaped tooling and keeps the frontend honest about what it actually
parsed.[^2]

For tree-sitter-backed trees, `kind` SHOULD preserve the grammar node type
verbatim, `fields` SHOULD preserve grammar field names, and `flags.error` /
`flags.missing` SHOULD reflect syntax recovery state. tree-sitter’s query
language already treats fields and error nodes as first-class concepts, so the
IR should not throw that information away.[^5]

For v1, Markdown trees are part of the stable debug and analysis contract.
Tree-sitter-backed source trees MAY appear in `dump-ir` output or internal
transport, but Stilyagi does not promise a stable full-node public surface for
non-Markdown syntaxes in v1. Rules that need Python or Rust context SHALL rely
on regions plus explicit owner metadata instead of binding to raw source-tree
shapes.

## 6. Regions

A region is the actual unit of prose analysis.

Nodes model structure. Regions model lintable surfaces.

Each region SHALL contain:

- `id`
- `kind`
- `scope`
- `syntax`
- optional `natural_language`
- `text`
- `segments`
- `origin_nodes`
- `owner`
- `attrs`
- `parent_region`

`kind` SHALL come from a stable, small vocabulary. v1 SHALL define at least
these kinds:

- `heading`
- `paragraph`
- `list_item`
- `blockquote`
- `table_cell`
- `frontmatter`
- `frontmatter_field`
- `image_alt`
- `link_title`
- `python_docstring`
- `rust_doc_comment`

`summary_line` is a derived analysis view, not an extractor-level region kind
in v1. Rules that care about summary lines SHALL derive them from a docstring
or paragraph region, or request an analysis-layer helper from the Python rule
API.

`scope` SHALL be an extensible list of tags, for example:

```json
["markdown", "heading", "h2"]
["python", "docstring", "function"]
["markdown", "table", "cell", "header"]
```

`text` SHALL be the lint surface, not necessarily a contiguous raw source
slice. In Markdown, that means markup delimiters disappear and prose becomes
inspectable as prose. When the frontend inserts a synthetic character, such as
a space for a soft line break, `segments` SHALL record that fact.

Regions use `syntax` for the source surface that produced the text and
`natural_language` for the prose locale when known. These fields SHALL stay
separate so rules can distinguish source format from editorial language. For
v1, consumers SHOULD expect `natural_language` to be `en` when it is present.
Broader locale support is out of scope until later slices and their test corpus
ratify it.

Each `segments` entry SHALL map a span of region text back to original source
bytes or declare it synthetic. For example:

```json
{
  "text_start": 12,
  "text_end": 13,
  "source": null,
  "synthetic": "softbreak_space",
  "node": "n42"
}
```

This rule is the heart of the design. It lets Stilyagi analyse rendered prose
while still issuing byte-accurate diagnostics and edits against the underlying
file.

`owner` SHALL be `null` for regions with no meaningful enclosing owner. For
docstrings and documentation comments, `owner` SHALL capture the owning code
entity so rules do not need to reconstruct it from raw syntax trees. v1 owner
objects SHALL include at least:

- `kind`, such as `module`, `class`, `function`, or `item`
- optional `name` when the source syntax supplies a stable owner name
- optional `qualname` when the source syntax supplies a stable qualified name

`owner` is a code-entity contract in v1 and MUST NOT be repurposed for Markdown
section context or other non-code ancestry. If a region needs heading or
debugging context, that information SHOULD live in `attrs` or in a separate
dedicated field rather than overloading `owner`.

## 7. Region invariants

Stilyagi IR SHALL uphold these invariants:

1. The concatenation implied by `segments` MUST reconstruct `text` exactly.
2. `origin_nodes` MUST list every structural node that materially contributes
   to the region.
3. If a region corresponds to a source-contiguous slice, `segments` MAY
   collapse to one entry.
4. If a region spans markup elision or inserted whitespace, `segments` MUST
   make that explicit.
5. A diagnostic span MUST always resolve to source bytes, even if the
   triggering condition came from region-relative analysis.
6. A fix MUST apply only to source-backed spans, never to synthetic spans.

## 8. Suppressions and parse anomalies

The frontend SHALL emit suppression directives into `suppressions`, rather than
forcing every rule to rediscover them.

Each suppression SHALL contain:

- `id`
- `kind` (`inline`, `range`, `file`, `config`)
- `codes`
- `span`
- `origin`

The frontend SHALL also emit recoverable parse anomalies into `errors`. In a
tree-sitter-backed tree, the frontend SHOULD preserve recovered syntax as nodes
and additionally record anomalies in `errors`. tree-sitter explicitly exposes
`ERROR` and `MISSING` nodes, and Stilyagi should use that rather than
pretending malformed files do not exist.[^5]

## 9. Serialization and compatibility

v1 SHALL define a canonical JSON serialization for the IR.

`dump-ir`, golden fixtures, and compatibility review SHALL use that JSON form.
The Rust frontend MAY use MessagePack or another representation for the
in-process Rust-to-Python boundary so long as it preserves the same logical IR
content. `markdown-rs` already supports optional `serde` serialization for
abstract syntax trees (ASTs) and configuration, which makes canonical JSON a
pragmatic serialized and debug contract without forcing it as the only hot-path
transport.[^1]

Compatibility rules:

- Consumers MUST reject unknown major versions.
- Consumers SHOULD ignore unknown fields within the same major version.
- Producers MUST NOT change field meaning within a major version.
- Optional fields MAY be added in minor versions.

## 10. Example

This example shows a Markdown-backed IR document after extraction, with one
mdast tree, one heading region, and source-backed span metadata that ties the
region text back to original bytes:

```json
{
  "schema_version": "1.0.0",
  "document": {
    "uri": "file:///repo/docs/guide.md",
    "path": "docs/guide.md",
    "syntax": "markdown",
    "natural_language": "en",
    "encoding": "utf-8",
    "content_hash": "sha256:abc123"
  },
  "producers": [
    {
      "kind": "markdown",
      "name": "markdown-rs",
      "version": "1.0.0",
      "options": {"gfm": true, "frontmatter": true}
    }
  ],
  "line_index": [0, 17, 38, 75],
  "trees": [
    {"id": "t1", "family": "mdast", "syntax": "markdown", "root": "n0"}
  ],
  "nodes": [
    {
      "id": "n0",
      "tree": "t1",
      "kind": "root",
      "parent": null,
      "children": ["n1", "n2"],
      "fields": {},
      "props": {},
      "span": {"byte_start": 0, "byte_end": 75},
      "flags": {"named": true, "error": false, "missing": false, "synthetic": false}
    },
    {
      "id": "n1",
      "tree": "t1",
      "kind": "heading",
      "parent": "n0",
      "children": ["n3"],
      "fields": {},
      "props": {"depth": 2},
      "span": {"byte_start": 0, "byte_end": 16},
      "flags": {"named": true, "error": false, "missing": false, "synthetic": false}
    }
  ],
  "regions": [
    {
      "id": "r1",
      "kind": "heading",
      "scope": ["markdown", "heading", "h2"],
      "syntax": "markdown",
      "natural_language": "en",
      "text": "How Stilyagi Works",
      "segments": [
        {
          "text_start": 0,
          "text_end": 18,
          "source": {"byte_start": 3, "byte_end": 21},
          "synthetic": null,
          "node": "n1"
        }
      ],
      "origin_nodes": ["n1"],
      "owner": null,
      "attrs": {"depth": 2},
      "parent_region": null
    }
  ],
  "suppressions": [],
  "errors": [],
  "metadata": {}
}
```

## 11. Rationale

A flat “regions only” format would simplify v1 and punish every interesting
rule forever after. Structural rules such as heading-depth jumps, frontmatter
policy, table-cell checks, or docstring-placement rules need tree context.
mdast and tree-sitter already provide that context; Stilyagi should keep
it.[^2][^3]

A pure “AST only” format would force every text-oriented rule to reassemble
prose from structural nodes, which would duplicate logic, burn central
processing unit (CPU) time, and produce divergent behaviour across rule packs.

Persisting spaCy documents in the IR would also age badly. spaCy’s capabilities
depend on which components ran, components can be enabled or disabled, and
custom metadata or hooks belong to runtime processing rather than to a stable
interchange contract.[^4]

[^1]: <https://docs.rs/markdown/>
[^2]: <https://github.com/syntax-tree/mdast>
[^3]: <https://github.com/tree-sitter/tree-sitter>
[^4]: <https://spacy.io/usage/processing-pipelines>
[^5]: <https://tree-sitter.github.io/tree-sitter/using-parsers/queries/1-syntax.html>
