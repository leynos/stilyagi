//! Markdown-specific extraction support.

mod flatten;
mod node_kind;
mod source_text;

use std::{any::Any, collections::BTreeMap, panic::catch_unwind};

use flatten::{SourceNodeId, flatten_region};
use markdown::{ParseOptions, mdast::Node, message::Message, to_mdast};
use node_kind::node_kind;
use stilyagi_ir::{
    DocumentMetadata, IrBuildContext, IrDocument, IrNode, IrRegion, IrTree, NodeFlags,
    ProducerMetadata, SourceIdentity, SourceSpan,
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
    parse_markdown_ast_with_context(
        source,
        &MarkdownDiagnosticContext {
            phase: "parse",
            path: "<unknown>",
            uri: "<unknown>",
        },
        |value| to_mdast(value, &markdown_parse_options()),
    )
}

#[cfg(test)]
fn parse_markdown_ast_with<F>(source: &str, parser: F) -> Result<Node, Message>
where
    F: FnOnce(&str) -> Result<Node, Message>,
{
    parse_markdown_ast_with_context(
        source,
        &MarkdownDiagnosticContext {
            phase: "parse",
            path: "<unknown>",
            uri: "<unknown>",
        },
        parser,
    )
}

fn parse_markdown_ast_with_context<F>(
    source: &str,
    context: &MarkdownDiagnosticContext<'_>,
    parser: F,
) -> Result<Node, Message>
where
    F: FnOnce(&str) -> Result<Node, Message>,
{
    catch_unwind(std::panic::AssertUnwindSafe(|| parser(source)))
        .unwrap_or_else(|payload| Err(parser_panic_message(payload.as_ref(), context)))
}

fn markdown_parse_options() -> ParseOptions {
    let mut options = ParseOptions::gfm();
    options.constructs.frontmatter = true;
    options
}

struct MarkdownDiagnosticContext<'a> {
    phase: &'a str,
    path: &'a str,
    uri: &'a str,
}

fn stilyagi_markdown_message(
    context: &MarkdownDiagnosticContext<'_>,
    rule_id: &'static str,
    detail: impl Into<String>,
) -> Message {
    Message {
        place: None,
        reason: format!(
            "phase={} path={} uri={} detail={}",
            context.phase,
            context.path,
            context.uri,
            detail.into(),
        ),
        rule_id: Box::new(rule_id.to_owned()),
        source: Box::new("stilyagi-markdown".to_owned()),
    }
}

fn parser_panic_message(
    payload: &(dyn Any + Send),
    context: &MarkdownDiagnosticContext<'_>,
) -> Message {
    let reason = payload.downcast_ref::<&str>().map_or_else(
        || {
            payload
                .downcast_ref::<String>()
                .cloned()
                .unwrap_or_else(|| "unknown panic payload".to_owned())
        },
        |message| (*message).to_owned(),
    );
    stilyagi_markdown_message(
        context,
        "parser-panic",
        format!("markdown parser panicked: {reason}"),
    )
}

/// Build a Markdown IR document envelope from source text and source identity.
///
/// # Errors
///
/// Returns the parser's structured message when `markdown-rs` cannot parse the
/// source with Stilyagi's Markdown options.
pub fn markdown_ir_document(source: &str, identity: SourceIdentity) -> Result<IrDocument, Message> {
    let source_path = identity
        .path
        .clone()
        .unwrap_or_else(|| "<anonymous>".to_owned());
    let source_uri = identity
        .uri
        .clone()
        .unwrap_or_else(|| "<anonymous>".to_owned());
    let context = IrBuildContext::new(
        DocumentMetadata::markdown(identity, source),
        vec![markdown_producer()],
    );

    let parse_context = MarkdownDiagnosticContext {
        phase: "parse",
        path: &source_path,
        uri: &source_uri,
    };
    let validation_context = MarkdownDiagnosticContext {
        phase: "validate",
        path: &source_path,
        uri: &source_uri,
    };
    markdown_ir_document_with_context(source, context, &parse_context, &validation_context)
}

fn markdown_ir_document_with_context(
    source: &str,
    context: IrBuildContext,
    parse_context: &MarkdownDiagnosticContext<'_>,
    validation_context: &MarkdownDiagnosticContext<'_>,
) -> Result<IrDocument, Message> {
    let ast = parse_markdown_ast_with_context(source, parse_context, |value| {
        to_mdast(value, &markdown_parse_options())
    })?;
    let mut document = IrDocument::empty(context.document, context.producers, source);
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

    validate_ir_consistency(&document, source, validation_context)?;
    Ok(document)
}

fn validate_ir_consistency(
    document: &IrDocument,
    source: &str,
    context: &MarkdownDiagnosticContext<'_>,
) -> Result<(), Message> {
    let expected_hash = stilyagi_ir::content_hash_for(source);
    if document.document.content_hash != expected_hash {
        return Err(stilyagi_markdown_message(
            context,
            "ir-content-hash-mismatch",
            format!(
                "content_hash mismatch expected={} actual={}",
                expected_hash, document.document.content_hash
            ),
        ));
    }

    let expected_line_index = stilyagi_ir::line_index_for(source);
    if document.line_index != expected_line_index {
        return Err(stilyagi_markdown_message(
            context,
            "ir-line-index-mismatch",
            format!(
                "line_index mismatch expected={:?} actual={:?}",
                expected_line_index, document.line_index
            ),
        ));
    }

    for region in &document.regions {
        if !region.segments_reconstruct_text() {
            return Err(stilyagi_markdown_message(
                context,
                "ir-region-text-mismatch",
                format!(
                    "region text mismatch id={} expected={} actual={}",
                    region.id,
                    region.reconstructed_text(),
                    region.text
                ),
            ));
        }
    }

    Ok(())
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
            let flattened = flatten_region(node, SourceNodeId::new(node_id), self.source);
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
