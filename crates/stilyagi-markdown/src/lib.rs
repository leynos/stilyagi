//! Markdown-specific extraction support.

mod builder;
mod flatten;
mod node_kind;
mod region_emission;
mod source_text;

use std::{
    any::Any,
    collections::{BTreeMap, BTreeSet},
    panic::catch_unwind,
};

use builder::MarkdownIrBuilder;
use markdown::{ParseOptions, mdast::Node, message::Message, to_mdast};
use stilyagi_ir::{
    DocumentMetadata, IrBuildContext, IrDocument, IrRegion, IrSegment, IrTree, ProducerMetadata,
    SourceIdentity, SourceSpan,
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
        root: String::new(),
    });

    let mut builder = MarkdownIrBuilder::new(source);
    let root_id = builder.push_node(&ast, None, parse_context)?;
    if let Some(tree) = document.trees.first_mut() {
        tree.root = root_id;
    }
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
    validate_document_metadata(document, source, context)?;

    if let Some(duplicate_id) =
        first_duplicate_id(document.nodes.iter().map(|node| node.id.as_str()))
    {
        return Err(stilyagi_markdown_message(
            context,
            "ir-node-id-duplicate",
            format!("duplicate node id {duplicate_id}"),
        ));
    }
    if let Some(duplicate_id) =
        first_duplicate_id(document.regions.iter().map(|region| region.id.as_str()))
    {
        return Err(stilyagi_markdown_message(
            context,
            "ir-region-id-duplicate",
            format!("duplicate region id {duplicate_id}"),
        ));
    }

    let node_ids = document
        .nodes
        .iter()
        .map(|node| node.id.as_str())
        .collect::<BTreeSet<_>>();
    let region_ids = document
        .regions
        .iter()
        .map(|region| region.id.as_str())
        .collect::<BTreeSet<_>>();

    let refs = IrValidationRefs {
        source,
        context,
        node_ids: &node_ids,
        region_ids: &region_ids,
    };

    for region in &document.regions {
        validate_region_consistency(region, &refs)?;
    }

    Ok(())
}

fn first_duplicate_id<'id>(ids: impl IntoIterator<Item = &'id str>) -> Option<&'id str> {
    let mut seen = BTreeSet::new();
    ids.into_iter().find(|id| !seen.insert(*id))
}

fn validate_document_metadata(
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

    Ok(())
}

struct IrValidationRefs<'a, 'context> {
    source: &'a str,
    context: &'a MarkdownDiagnosticContext<'context>,
    node_ids: &'a BTreeSet<&'a str>,
    region_ids: &'a BTreeSet<&'a str>,
}

fn validate_region_consistency(
    region: &IrRegion,
    refs: &IrValidationRefs<'_, '_>,
) -> Result<(), Message> {
    validate_region_text(region, refs.context)?;
    validate_parent_region(region, refs.context, refs.region_ids)?;
    validate_origin_nodes(region, refs.context, refs.node_ids)?;
    validate_source_segments(region, refs)?;
    Ok(())
}

fn validate_region_text(
    region: &IrRegion,
    context: &MarkdownDiagnosticContext<'_>,
) -> Result<(), Message> {
    if region.segments_reconstruct_text() {
        return Ok(());
    }
    Err(stilyagi_markdown_message(
        context,
        "ir-region-text-mismatch",
        format!(
            "region text mismatch id={} expected={} actual={}",
            region.id,
            region.reconstructed_text(),
            region.text
        ),
    ))
}

fn validate_parent_region(
    region: &IrRegion,
    context: &MarkdownDiagnosticContext<'_>,
    region_ids: &BTreeSet<&str>,
) -> Result<(), Message> {
    if region
        .parent_region
        .as_deref()
        .is_none_or(|parent_region| region_ids.contains(parent_region))
    {
        return Ok(());
    }
    let parent_region = region.parent_region.as_deref().unwrap_or_default();
    Err(stilyagi_markdown_message(
        context,
        "ir-parent-region-unresolved",
        format!(
            "region id={} parent_region={} does not resolve",
            region.id, parent_region
        ),
    ))
}

fn validate_origin_nodes(
    region: &IrRegion,
    context: &MarkdownDiagnosticContext<'_>,
    node_ids: &BTreeSet<&str>,
) -> Result<(), Message> {
    if region.origin_nodes.is_empty() {
        return Err(stilyagi_markdown_message(
            context,
            "ir-origin-nodes-invalid",
            format!("region id={} origin_nodes is empty", region.id),
        ));
    }
    for origin_node in &region.origin_nodes {
        if !node_ids.contains(origin_node.as_str()) {
            return Err(stilyagi_markdown_message(
                context,
                "ir-origin-nodes-invalid",
                format!(
                    "region id={} origin_nodes contains unknown node {}",
                    region.id, origin_node
                ),
            ));
        }
    }
    Ok(())
}

fn validate_source_segments(
    region: &IrRegion,
    refs: &IrValidationRefs<'_, '_>,
) -> Result<(), Message> {
    for segment in &region.segments {
        if let Some(span) = segment.source {
            validate_source_segment(region, segment, span, refs)?;
        }
    }
    Ok(())
}

fn validate_source_segment(
    region: &IrRegion,
    segment: &IrSegment,
    span: SourceSpan,
    refs: &IrValidationRefs<'_, '_>,
) -> Result<(), Message> {
    let actual = refs.source.get(span.byte_start..span.byte_end);
    if actual == Some(segment.text.as_str()) {
        return Ok(());
    }
    Err(stilyagi_markdown_message(
        refs.context,
        "ir-segment-source-mismatch",
        format!(
            "source segment mismatch region id={} segment text={} span={:?} actual={:?}",
            region.id, segment.text, span, actual
        ),
    ))
}

/// Version of the `markdown-rs` parser recorded as the IR producer version.
///
/// `markdown-rs` does not expose its own version at compile time, so this
/// mirrors the `markdown` dependency pinned in the workspace `Cargo.toml`.
/// Update both together when the parser is upgraded.
const MARKDOWN_RS_VERSION: &str = "1.0.0";

fn markdown_producer() -> ProducerMetadata {
    let mut options = BTreeMap::new();
    options.insert("gfm".to_owned(), serde_json::json!(true));
    options.insert("frontmatter".to_owned(), serde_json::json!(true));
    ProducerMetadata {
        kind: "markdown".to_owned(),
        name: "markdown-rs".to_owned(),
        version: MARKDOWN_RS_VERSION.to_owned(),
        options,
    }
}

fn source_span(
    node: &Node,
    context: &MarkdownDiagnosticContext<'_>,
) -> Result<SourceSpan, Message> {
    let Some(position) = node.position() else {
        return Err(stilyagi_markdown_message(
            context,
            "missing-node-span",
            "node has no source position",
        ));
    };
    let Some(source_span) = SourceSpan::new(position.start.offset, position.end.offset) else {
        return Err(stilyagi_markdown_message(
            context,
            "invalid-node-span",
            "node position start was greater than end",
        ));
    };

    Ok(source_span)
}

#[cfg(test)]
mod region_coverage_bdd;
#[cfg(test)]
mod tests;
