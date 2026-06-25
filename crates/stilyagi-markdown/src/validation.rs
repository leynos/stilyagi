//! Build-time validation for Markdown IR consistency.

use std::collections::BTreeSet;

use markdown::message::Message;
use stilyagi_ir::{IrDocument, IrRegion, IrSegment, SourceSpan};

use crate::{MarkdownDiagnosticContext, stilyagi_markdown_message};

pub(crate) fn validate_ir_consistency(
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
            "ir-duplicate-node-id",
            format!("duplicate node id {duplicate_id}"),
        ));
    }
    if let Some(duplicate_id) =
        first_duplicate_id(document.regions.iter().map(|region| region.id.as_str()))
    {
        return Err(stilyagi_markdown_message(
            context,
            "ir-duplicate-region-id",
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
        validate_segment_origin(region, segment, refs.context)?;
        if let Some(span) = segment.source {
            validate_source_segment(region, segment, span, refs)?;
        }
    }
    Ok(())
}

fn validate_segment_origin(
    region: &IrRegion,
    segment: &IrSegment,
    context: &MarkdownDiagnosticContext<'_>,
) -> Result<(), Message> {
    if segment.source.is_some() ^ segment.synthetic.is_some() {
        return Ok(());
    }
    Err(stilyagi_markdown_message(
        context,
        "ir-segment-origin-invalid",
        format!(
            "segment origin invalid region id={} segment text={} source_present={} synthetic_present={}",
            region.id,
            segment.text,
            segment.source.is_some(),
            segment.synthetic.is_some()
        ),
    ))
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
