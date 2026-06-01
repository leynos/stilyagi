//! Markdown-specific extraction support.

use std::collections::BTreeMap;

use markdown::{ParseOptions, mdast::Node, message::Message, to_mdast};
use stilyagi_ir::{
    DocumentMetadata, IrDocument, IrNode, IrRegion, IrSegment, IrTree, NodeFlags, ProducerMetadata,
    SourceSpan,
};

/// Marker type for the future Markdown extraction boundary.
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct MarkdownBoundary;

/// Parse Markdown into an mdast tree using the workspace parser choice.
///
/// # Errors
///
/// Returns the parser's structured message when the input cannot be parsed
/// with the configured `markdown-rs` options.
pub fn parse_markdown_ast(source: &str) -> Result<Node, Message> {
    to_mdast(source, &ParseOptions::gfm())
}

/// Build a Markdown IR document envelope from source text and source identity.
///
/// # Errors
///
/// Returns the parser's structured message when `markdown-rs` cannot parse the
/// source with Stilyagi's Markdown options.
pub fn markdown_ir_document(
    source: &str,
    path: impl Into<String>,
    uri: impl Into<String>,
) -> Result<IrDocument, Message> {
    let ast = parse_markdown_ast(source)?;
    let mut document = IrDocument::empty(
        DocumentMetadata::markdown(path, uri, source),
        vec![markdown_producer()],
        source,
    );
    document.trees.push(IrTree {
        id: "t0".to_owned(),
        family: "mdast".to_owned(),
        syntax: "markdown".to_owned(),
        root: "n0".to_owned(),
    });

    let mut builder = MarkdownIrBuilder::default();
    let _root_id = builder.push_node(&ast, None);
    document.nodes = builder.nodes;
    document.regions = builder.regions;

    Ok(document)
}

fn markdown_producer() -> ProducerMetadata {
    let mut options = BTreeMap::new();
    options.insert("gfm".to_owned(), serde_json::json!(true));
    ProducerMetadata {
        kind: "markdown".to_owned(),
        name: "markdown-rs".to_owned(),
        version: "1.0.0".to_owned(),
        options,
    }
}

#[derive(Default)]
struct MarkdownIrBuilder {
    next_node: usize,
    next_region: usize,
    nodes: Vec<IrNode>,
    regions: Vec<IrRegion>,
}

impl MarkdownIrBuilder {
    fn push_node(&mut self, node: &Node, parent: Option<&str>) -> String {
        let node_id = self.next_node_id();
        let node_index = self.nodes.len();
        self.nodes.push(IrNode {
            id: node_id.clone(),
            tree: "t0".to_owned(),
            kind: node_kind(node).to_owned(),
            parent: parent.map(str::to_owned),
            children: Vec::new(),
            fields: BTreeMap::new(),
            props: node_props(node),
            span: source_span(node),
            flags: NodeFlags::named_source(),
        });

        let mut child_ids = Vec::new();
        if let Some(children) = node.children() {
            for child in children {
                child_ids.push(self.push_node(child, Some(&node_id)));
            }
        }

        if let Some(stored_node) = self.nodes.get_mut(node_index) {
            stored_node.children = child_ids;
        }
        self.push_region_for_node(node, &node_id);
        node_id
    }

    fn next_node_id(&mut self) -> String {
        let id = format!("n{}", self.next_node);
        self.next_node += 1;
        id
    }

    fn next_region_id(&mut self) -> String {
        let id = format!("r{}", self.next_region);
        self.next_region += 1;
        id
    }

    fn push_region_for_node(&mut self, node: &Node, node_id: &str) {
        let region_kind = match node {
            Node::Heading(_) => Some("heading"),
            Node::Paragraph(_) => Some("paragraph"),
            Node::TableCell(_) => Some("table_cell"),
            _ => None,
        };
        if let Some(kind) = region_kind {
            let flattened = flatten_region(node, node_id);
            if flattened.text.is_empty() {
                return;
            }
            let mut attrs = BTreeMap::new();
            if let Node::Heading(heading) = node {
                attrs.insert("depth".to_owned(), serde_json::json!(heading.depth));
            }
            let region_id = self.next_region_id();
            self.regions.push(IrRegion {
                id: region_id,
                kind: kind.to_owned(),
                scope: scope_for(kind, node),
                syntax: "markdown".to_owned(),
                natural_language: Some("en".to_owned()),
                text: flattened.text,
                segments: flattened.segments,
                origin_nodes: vec![node_id.to_owned()],
                owner: None,
                attrs,
                parent_region: None,
            });
        }
    }
}

struct FlattenedRegion {
    text: String,
    segments: Vec<IrSegment>,
}

impl FlattenedRegion {
    fn push_source_text(&mut self, value: &str, source_start: usize, node_id: &str) {
        let mut chunk_start = 0;
        for (byte_offset, character) in value.char_indices() {
            if character == '\n' {
                self.push_source_chunk(value, chunk_start, byte_offset, source_start, node_id);
                self.push_synthetic(" ", "softbreak_space");
                chunk_start = byte_offset + character.len_utf8();
            }
        }
        self.push_source_chunk(value, chunk_start, value.len(), source_start, node_id);
    }

    fn push_source_chunk(
        &mut self,
        value: &str,
        chunk_start: usize,
        chunk_end: usize,
        source_start: usize,
        node_id: &str,
    ) {
        let Some(chunk) = value.get(chunk_start..chunk_end) else {
            return;
        };
        if chunk.is_empty() {
            return;
        }
        let text_start = self.text.len();
        self.text.push_str(chunk);
        self.segments.push(IrSegment::source(
            text_start,
            chunk,
            SourceSpan::new(source_start + chunk_start, source_start + chunk_end),
            node_id,
        ));
    }

    fn push_synthetic(&mut self, text: &str, reason: &str) {
        let text_start = self.text.len();
        self.text.push_str(text);
        self.segments
            .push(IrSegment::synthetic(text_start, text, reason));
    }
}

fn flatten_region(node: &Node, node_id: &str) -> FlattenedRegion {
    let mut flattened = FlattenedRegion {
        text: String::new(),
        segments: Vec::new(),
    };
    flatten_inline(node, node_id, &mut flattened);
    flattened
}

fn flatten_inline(node: &Node, node_id: &str, flattened: &mut FlattenedRegion) {
    match node {
        Node::Text(text) => {
            if let Some(position) = text.position.as_ref() {
                flattened.push_source_text(&text.value, position.start.offset, node_id);
            }
        }
        Node::Break(_) => flattened.push_synthetic(" ", "hardbreak_space"),
        Node::InlineCode(code) => {
            if let Some(position) = code.position.as_ref() {
                flattened.push_source_text(&code.value, position.start.offset, node_id);
            }
        }
        _ => {
            if let Some(children) = node.children() {
                for child in children {
                    flatten_inline(child, node_id, flattened);
                }
            }
        }
    }
}

fn scope_for(kind: &str, node: &Node) -> Vec<String> {
    let mut scope = vec!["markdown".to_owned(), kind.to_owned()];
    if let Node::Heading(heading) = node {
        scope.push(format!("h{}", heading.depth));
    }
    scope
}

fn source_span(node: &Node) -> SourceSpan {
    node.position().map_or_else(
        || SourceSpan::new(0, 0),
        |position| SourceSpan::new(position.start.offset, position.end.offset),
    )
}

fn node_props(node: &Node) -> BTreeMap<String, serde_json::Value> {
    let mut props = BTreeMap::new();
    if let Node::Heading(heading) = node {
        props.insert("depth".to_owned(), serde_json::json!(heading.depth));
    }
    props
}

const fn node_kind(node: &Node) -> &'static str {
    match node {
        Node::Root(_) => "root",
        Node::Blockquote(_) => "blockquote",
        Node::FootnoteDefinition(_) => "footnoteDefinition",
        Node::MdxJsxFlowElement(_) => "mdxJsxFlowElement",
        Node::List(_) => "list",
        Node::MdxjsEsm(_) => "mdxjsEsm",
        Node::Toml(_) => "toml",
        Node::Yaml(_) => "yaml",
        Node::Break(_) => "break",
        Node::InlineCode(_) => "inlineCode",
        Node::InlineMath(_) => "inlineMath",
        Node::Delete(_) => "delete",
        Node::Emphasis(_) => "emphasis",
        Node::MdxTextExpression(_) => "mdxTextExpression",
        Node::FootnoteReference(_) => "footnoteReference",
        Node::Html(_) => "html",
        Node::Image(_) => "image",
        Node::ImageReference(_) => "imageReference",
        Node::MdxJsxTextElement(_) => "mdxJsxTextElement",
        Node::Link(_) => "link",
        Node::LinkReference(_) => "linkReference",
        Node::Strong(_) => "strong",
        Node::Text(_) => "text",
        Node::Code(_) => "code",
        Node::Math(_) => "math",
        Node::MdxFlowExpression(_) => "mdxFlowExpression",
        Node::Heading(_) => "heading",
        Node::Table(_) => "table",
        Node::ThematicBreak(_) => "thematicBreak",
        Node::TableRow(_) => "tableRow",
        Node::TableCell(_) => "tableCell",
        Node::ListItem(_) => "listItem",
        Node::Definition(_) => "definition",
        Node::Paragraph(_) => "paragraph",
    }
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeSet;

    use markdown::mdast::Node;
    use rstest::rstest;
    use stilyagi_ir::{IrDocument, SourceSpan};
    use stilyagi_test_support::{SHARED_MARKDOWN_FIXTURE_PATH, read_corpus_fixture};

    use super::{MarkdownBoundary, markdown_ir_document, parse_markdown_ast};

    /// Keep the marker type default stable and comparable.
    #[test]
    #[expect(
        clippy::default_constructed_unit_structs,
        reason = "this test explicitly exercises the Default implementation"
    )]
    fn markdown_boundary_default_matches_the_marker_value() {
        assert_eq!(MarkdownBoundary::default(), MarkdownBoundary);
    }

    /// Keep the marker type clone semantics trivial.
    #[test]
    fn markdown_boundary_clone_matches_the_original() {
        let boundary = MarkdownBoundary;

        assert_eq!(boundary.clone(), boundary);
    }

    /// Keep the marker type debug output identifiable in failures.
    #[test]
    fn markdown_boundary_debug_output_mentions_the_type_name() {
        assert!(format!("{MarkdownBoundary:?}").contains("MarkdownBoundary"));
    }

    /// Keep the marker type copy semantics available to callers.
    #[test]
    fn markdown_boundary_is_copy() {
        let original = MarkdownBoundary;
        let first = original;
        let second = original;

        assert_eq!(first, second);
        assert_eq!(first, original);
    }

    #[rstest]
    fn markdown_parser_reports_positions_for_representative_blocks() {
        let source = "# Heading\n\nA paragraph with [a link](https://example.com).\n";
        let tree = parse_markdown_ast(source);

        assert!(matches!(tree, Ok(Node::Root(_))));
        if let Ok(root) = tree {
            assert_node_start(&root, 0);
            assert_node_has_non_empty_span(&root);
            assert!(find_kind(&root, NodeKind::Heading).is_some());
            assert!(find_kind(&root, NodeKind::Paragraph).is_some());
            if let Some(heading) = find_kind(&root, NodeKind::Heading) {
                assert_node_start(heading, 0);
                assert_node_has_non_empty_span(heading);
            }
            if let Some(paragraph) = find_kind(&root, NodeKind::Paragraph) {
                assert_node_start(paragraph, 11);
                assert_node_has_non_empty_span(paragraph);
            }
        }
    }

    #[derive(Clone, Copy)]
    enum NodeKind {
        Heading,
        Paragraph,
    }

    fn find_kind(node: &Node, kind: NodeKind) -> Option<&Node> {
        if matches_kind(node, kind) {
            return Some(node);
        }
        if let Some(children) = node.children() {
            for child in children {
                if let Some(found) = find_kind(child, kind) {
                    return Some(found);
                }
            }
        }
        None
    }

    fn matches_kind(node: &Node, kind: NodeKind) -> bool {
        matches!(
            (node, kind),
            (Node::Heading(_), NodeKind::Heading) | (Node::Paragraph(_), NodeKind::Paragraph)
        )
    }

    fn assert_node_start(node: &Node, start: usize) {
        let position = node.position();
        assert!(matches!(
            position,
            Some(value) if value.start.offset == start
        ));
    }

    fn assert_node_has_non_empty_span(node: &Node) {
        let position = node.position();
        assert!(matches!(
            position,
            Some(value) if value.start.offset < value.end.offset
        ));
    }

    #[rstest]
    fn markdown_ir_document_emits_envelope_nodes_and_regions() {
        let source = "# Fixture Heading\n\nThis paragraph links to the\n[Stilyagi design](../../../../../docs/stilyagi-design.md).\n\n| Term | Meaning |\n| ---- | ------- |\n| IR   | Intermediate representation |\n";
        let document = markdown_ir_document(
            source,
            "tests/fixtures/corpus/markdown/valid/example.md",
            "file:///repo/tests/fixtures/corpus/markdown/valid/example.md",
        );

        assert!(matches!(document, Ok(ref value) if value.document.syntax == "markdown"));
        if let Ok(value) = document {
            assert_eq!(value.schema_version, "1.0.0");
            assert!(value.document.content_hash.starts_with("sha256:"));
            assert_eq!(value.line_index.first().copied(), Some(0));
            assert!(!value.nodes.is_empty());
            assert!(
                value
                    .regions
                    .iter()
                    .all(stilyagi_ir::IrRegion::segments_reconstruct_text)
            );
            assert!(region_kinds(&value.regions).contains("heading"));
            assert!(region_kinds(&value.regions).contains("paragraph"));
            assert!(region_kinds(&value.regions).contains("table_cell"));
        }
    }

    #[rstest]
    fn markdown_ir_document_records_soft_breaks_as_synthetic_segments() {
        let source = "First line\nsecond line\n";
        let document =
            markdown_ir_document(source, "docs/example.md", "file:///repo/docs/example.md");

        assert!(matches!(document, Ok(ref value) if value.regions.len() == 1));
        if let Ok(value) = document {
            let paragraph = value.regions.first();
            assert_eq!(
                paragraph.map(|region| region.text.as_str()),
                Some("First line second line")
            );
            assert!(matches!(
                paragraph,
                Some(region) if region.segments.iter().any(|segment| segment.synthetic.as_deref() == Some("softbreak_space"))
            ));
        }
    }

    fn region_kinds(regions: &[stilyagi_ir::IrRegion]) -> BTreeSet<&str> {
        regions.iter().map(|region| region.kind.as_str()).collect()
    }

    #[rstest]
    fn shared_markdown_ir_json_round_trips_without_span_drift() {
        let source = read_corpus_fixture(SHARED_MARKDOWN_FIXTURE_PATH)
            .unwrap_or_else(|error| panic!("expected shared Markdown fixture: {error}"));
        let document = markdown_ir_document(
            &source,
            SHARED_MARKDOWN_FIXTURE_PATH,
            "file:///repo/tests/fixtures/corpus/markdown/valid/heading-table-link-suppression.md",
        )
        .unwrap_or_else(|error| panic!("expected shared Markdown IR document: {error}"));
        let json = document
            .to_canonical_json()
            .unwrap_or_else(|error| panic!("expected canonical JSON: {error}"));
        let parsed = serde_json::from_str::<IrDocument>(&json)
            .unwrap_or_else(|error| panic!("expected IR JSON round-trip: {error}"));

        assert_eq!(parsed, document);
        assert!(
            parsed
                .regions
                .iter()
                .all(stilyagi_ir::IrRegion::segments_reconstruct_text)
        );
        assert!(source_backed_segments_match_source(&parsed, &source));
        insta::assert_snapshot!(json);
    }

    fn source_backed_segments_match_source(document: &IrDocument, source: &str) -> bool {
        document.regions.iter().all(|region| {
            region.segments.iter().all(|segment| {
                segment.source.map_or_else(
                    || segment.synthetic.is_some(),
                    |span| source_segment_matches(span, source, &segment.text),
                )
            })
        })
    }

    fn source_segment_matches(span: SourceSpan, source: &str, expected: &str) -> bool {
        source.get(span.byte_start..span.byte_end) == Some(expected)
    }
}
