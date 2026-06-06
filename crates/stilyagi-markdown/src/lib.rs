//! Markdown-specific extraction support.

mod node_kind;
mod source_text;

use std::{any::Any, collections::BTreeMap, panic::catch_unwind};

use markdown::{ParseOptions, mdast::Node, message::Message, to_mdast};
use node_kind::node_kind;
use source_text::{
    SourceTextEvent, decoded_text_maps_to_source, source_line_ending_len, source_text_event,
    source_value_start,
};
use stilyagi_ir::{
    DocumentMetadata, IrDocument, IrNode, IrRegion, IrSegment, IrTree, NodeFlags, ProducerMetadata,
    SegmentOrigin, SourceSpan,
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
    parse_markdown_ast_with(source, |value| to_mdast(value, &markdown_parse_options()))
}

fn parse_markdown_ast_with<F>(source: &str, parser: F) -> Result<Node, Message>
where
    F: FnOnce(&str) -> Result<Node, Message>,
{
    catch_unwind(std::panic::AssertUnwindSafe(|| parser(source)))
        .unwrap_or_else(|payload| Err(parser_panic_message(payload.as_ref())))
}

fn markdown_parse_options() -> ParseOptions {
    let mut options = ParseOptions::gfm();
    options.constructs.frontmatter = true;
    options
}

fn parser_panic_message(payload: &(dyn Any + Send)) -> Message {
    let reason = payload.downcast_ref::<&str>().map_or_else(
        || {
            payload
                .downcast_ref::<String>()
                .cloned()
                .unwrap_or_else(|| "unknown panic payload".to_owned())
        },
        |message| (*message).to_owned(),
    );
    Message {
        place: None,
        reason: format!("markdown parser panicked: {reason}"),
        rule_id: Box::new("parser-panic".to_owned()),
        source: Box::new("stilyagi-markdown".to_owned()),
    }
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

    let mut builder = MarkdownIrBuilder::new(source);
    let _root_id = builder.push_node(&ast, None);
    document.nodes = builder.nodes;
    document.regions = builder.regions;

    Ok(document)
}

fn markdown_producer() -> ProducerMetadata {
    let mut options = BTreeMap::new();
    options.insert("gfm".to_owned(), serde_json::json!(true));
    options.insert("frontmatter".to_owned(), serde_json::json!(true));
    ProducerMetadata {
        kind: "markdown".to_owned(),
        name: "markdown-rs".to_owned(),
        version: "1.0.0".to_owned(),
        options,
    }
}

struct MarkdownIrBuilder<'source> {
    source: &'source str,
    next_node: usize,
    next_region: usize,
    nodes: Vec<IrNode>,
    regions: Vec<IrRegion>,
}

impl<'source> MarkdownIrBuilder<'source> {
    const fn new(source: &'source str) -> Self {
        Self {
            source,
            next_node: 0,
            next_region: 0,
            nodes: Vec::new(),
            regions: Vec::new(),
        }
    }

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
            let flattened = flatten_region(node, node_id, self.source);
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
                natural_language: None,
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

struct FlattenedRegion<'source> {
    source: &'source str,
    text: String,
    segments: Vec<IrSegment>,
}

/// A slice of source text together with the byte offset of its origin in
/// the raw source buffer. Used only inside [`FlattenedRegion`].
struct PositionedChunk<'a> {
    value: &'a str,
    range: std::ops::Range<usize>,
    source_start: usize,
}

impl FlattenedRegion<'_> {
    fn emit_chunk_for_range(&mut self, chunk: PositionedChunk<'_>, node_id: &str) {
        let PositionedChunk {
            value,
            range,
            source_start,
        } = chunk;
        let Some(text) = value.get(range.clone()) else {
            return;
        };
        if text.is_empty() {
            return;
        }
        let span = SourceSpan::new(source_start + range.start, source_start + range.end);
        self.push_source_chunk(text, span, node_id);
    }

    fn push_source_text(&mut self, value: &str, source_start: usize, node_id: &str) {
        let mut chunk_start = 0;
        let mut chunk_source_start = source_start;
        let mut source_cursor = source_start;
        let mut byte_offset = 0;
        while byte_offset < value.len() {
            match source_text_event(value, byte_offset) {
                SourceTextEvent::LineEnding(line_ending_len) => {
                    self.emit_chunk_for_range(
                        PositionedChunk {
                            value,
                            range: chunk_start..byte_offset,
                            source_start: chunk_source_start - chunk_start,
                        },
                        node_id,
                    );
                    source_cursor += source_line_ending_len(self.source, source_cursor);
                    byte_offset += line_ending_len;
                    chunk_start = byte_offset;
                    chunk_source_start = source_cursor;
                    self.push_source_chunk_before_break(
                        "",
                        SourceSpan::new(source_cursor, source_cursor),
                        node_id,
                    );
                }
                SourceTextEvent::Character(character_len) => {
                    source_cursor += character_len;
                    byte_offset += character_len;
                }
                SourceTextEvent::InvalidOffset => break,
            }
        }
        self.emit_chunk_for_range(
            PositionedChunk {
                value,
                range: chunk_start..value.len(),
                source_start: chunk_source_start - chunk_start,
            },
            node_id,
        );
    }

    fn push_source_chunk_before_break(&mut self, chunk: &str, span: SourceSpan, node_id: &str) {
        if !chunk.is_empty() {
            self.push_source_chunk(chunk, span, node_id);
        }
        self.push_synthetic(" ", "softbreak_space");
    }

    fn push_source_chunk(&mut self, chunk: &str, span: SourceSpan, node_id: &str) {
        let text_start = self.text.len();
        self.text.push_str(chunk);
        self.segments.push(IrSegment::new(
            text_start,
            chunk,
            SegmentOrigin::Source {
                span,
                node: node_id.to_owned(),
            },
        ));
    }

    fn push_synthetic(&mut self, text: &str, reason: &str) {
        let text_start = self.text.len();
        self.text.push_str(text);
        self.segments.push(IrSegment::new(
            text_start,
            text,
            SegmentOrigin::Synthetic {
                reason: reason.to_owned(),
            },
        ));
    }

    fn push_decoded_text(&mut self, text: &str) {
        if !text.is_empty() {
            self.push_synthetic(text, "decoded_text");
        }
    }
}

fn flatten_region<'source>(
    node: &Node,
    node_id: &str,
    source: &'source str,
) -> FlattenedRegion<'source> {
    let mut flattened = FlattenedRegion {
        source,
        text: String::new(),
        segments: Vec::new(),
    };
    flatten_inline(node, node_id, &mut flattened);
    flattened
}

fn flatten_inline(node: &Node, node_id: &str, flattened: &mut FlattenedRegion<'_>) {
    match node {
        Node::Text(text) => flatten_text_node(text, node_id, flattened),
        Node::Break(_) => flattened.push_synthetic(" ", "hardbreak_space"),
        Node::InlineCode(code) => flatten_inline_code_node(code, node_id, flattened),
        _ => flatten_children(node, node_id, flattened),
    }
}

fn flatten_text_node(
    text: &markdown::mdast::Text,
    node_id: &str,
    flattened: &mut FlattenedRegion<'_>,
) {
    if let Some(position) = text.position.as_ref() {
        let span = SourceSpan::new(position.start.offset, position.end.offset);
        if decoded_text_maps_to_source(flattened.source, span, &text.value) {
            flattened.push_source_text(&text.value, position.start.offset, node_id);
        } else {
            flattened.push_decoded_text(&text.value);
        }
    }
}

fn flatten_inline_code_node(
    code: &markdown::mdast::InlineCode,
    node_id: &str,
    flattened: &mut FlattenedRegion<'_>,
) {
    if let Some(position) = code.position.as_ref() {
        let span = SourceSpan::new(position.start.offset, position.end.offset);
        let source_start = source_value_start(flattened.source, span, &code.value);
        flattened.push_source_text(&code.value, source_start, node_id);
    }
}

fn flatten_children(node: &Node, node_id: &str, flattened: &mut FlattenedRegion<'_>) {
    if let Some(children) = node.children() {
        for child in children {
            flatten_inline(child, node_id, flattened);
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

#[cfg(test)]
mod tests;
