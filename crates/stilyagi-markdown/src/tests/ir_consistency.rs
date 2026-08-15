//! Tests for Markdown IR envelope construction and consistency validation.

use std::collections::BTreeSet;
use std::path::Path;

use markdown::mdast::Node;
use rstest::rstest;
use stilyagi_ir::{IrDocument, IrRegion, SourceSpan};

use super::source_identity;
use crate::source_text::decoded_text_maps_to_source;
use crate::{
    MarkdownDiagnosticContext, markdown_ir_document, source_span, validate_ir_consistency,
};

const fn diagnostic_context() -> MarkdownDiagnosticContext<'static> {
    MarkdownDiagnosticContext {
        phase: "validate",
        path: "docs/example.md",
        uri: "file:///repo/docs/example.md",
    }
}

#[rstest]
fn markdown_ir_document_emits_envelope_nodes_and_regions() {
    let source = "# Fixture Heading\n\nThis paragraph links to the\n[Stilyagi design](../../../../../docs/stilyagi-design.md).\n\n| Term | Meaning |\n| ---- | ------- |\n| IR   | Intermediate representation |\n";
    let document = markdown_ir_document(
        source,
        source_identity(Path::new("tests/fixtures/corpus/markdown/valid/example.md")),
    );

    assert!(matches!(&document, Ok(value) if value.document.syntax == "markdown"));
    if let Ok(value) = document {
        assert_eq!(value.schema_version, "1.1.0");
        assert!(
            value
                .producers
                .iter()
                .any(|producer| { producer.kind == "markdown" && producer.name == "markdown-rs" })
        );
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
fn markdown_ir_document_preserves_canonical_source_identity_helpers() {
    let source = "# Heading\n\nBody";
    let document = markdown_ir_document(source, source_identity(Path::new("docs/example.md")))
        .expect("expected Markdown IR document");

    assert_eq!(
        document.document.content_hash,
        stilyagi_ir::content_hash_for(source)
    );
    assert_eq!(document.line_index, stilyagi_ir::line_index_for(source));
}

/// Build a valid Markdown IR document, corrupt it with `mutate`, and assert
/// that `validate_ir_consistency` reports `expected_rule_id` with every fragment
/// in `expected_reason_fragments` (plus the shared `phase=validate` context).
fn assert_validation_reports(
    mutate: impl FnOnce(&mut IrDocument),
    expected_rule_id: &str,
    expected_reason_fragments: &[&str],
) {
    let source = "# Heading\n\nBody";
    let mut document =
        match markdown_ir_document(source, source_identity(Path::new("docs/example.md"))) {
            Ok(document) => document,
            Err(error) => panic!("expected Markdown IR document: {error}"),
        };
    mutate(&mut document);
    let context = diagnostic_context();

    let result = validate_ir_consistency(&document, source, &context);

    let Err(error) = result else {
        panic!("expected validation failure for rule {expected_rule_id}");
    };
    assert_eq!(error.source.as_ref(), "stilyagi-markdown");
    assert_eq!(error.rule_id.as_ref(), expected_rule_id);
    assert!(error.reason.contains("phase=validate"));
    for fragment in expected_reason_fragments {
        assert!(
            error.reason.contains(fragment),
            "reason {:?} is missing fragment {fragment:?}",
            error.reason
        );
    }
}

fn assert_validation_reports_on_first_region(
    mutate_region: impl FnOnce(&mut IrRegion),
    expected_rule_id: &str,
    expected_reason_fragments: &[&str],
) {
    assert_validation_reports(
        |document| {
            let Some(region) = document.regions.first_mut() else {
                panic!("expected at least one Markdown IR region");
            };
            mutate_region(region);
        },
        expected_rule_id,
        expected_reason_fragments,
    );
}

#[rstest]
fn validate_ir_consistency_reports_content_hash_mismatches() {
    assert_validation_reports(
        |document| document.document.content_hash = "sha256:bad".to_owned(),
        "ir-content-hash-mismatch",
        &["path=", "uri=", "content_hash mismatch"],
    );
}

#[rstest]
fn validate_ir_consistency_reports_line_index_mismatches() {
    assert_validation_reports(
        |document| document.line_index.push(usize::MAX),
        "ir-line-index-mismatch",
        &["line_index mismatch"],
    );
}

#[rstest]
fn validate_ir_consistency_reports_duplicate_node_ids() {
    assert_validation_reports(
        |document| {
            if let Some(node) = document.nodes.first().cloned() {
                document.nodes.push(node);
            }
        },
        "ir-duplicate-node-id",
        &["duplicate node id"],
    );
}

#[rstest]
fn validate_ir_consistency_reports_duplicate_region_ids() {
    assert_validation_reports(
        |document| {
            if let Some(region) = document.regions.first().cloned() {
                document.regions.push(region);
            }
        },
        "ir-duplicate-region-id",
        &["duplicate region id"],
    );
}

#[rstest]
fn validate_ir_consistency_reports_region_text_mismatches() {
    assert_validation_reports_on_first_region(
        |region| region.text.push_str(" drift"),
        "ir-region-text-mismatch",
        &["region text mismatch"],
    );
}

#[rstest]
fn validate_ir_consistency_reports_source_span_mismatches() {
    assert_validation_reports(
        |document| {
            let segment = document
                .regions
                .first_mut()
                .and_then(|region| region.segments.first_mut())
                .expect("expected at least one source-backed segment");
            segment.source = SourceSpan::new(0, segment.text.len());
        },
        "ir-segment-source-mismatch",
        &["source segment mismatch", "region id=", "segment text="],
    );
}

#[rstest]
fn validate_ir_consistency_reports_unresolved_parent_regions() {
    assert_validation_reports_on_first_region(
        |region| region.parent_region = Some("missing-region".to_owned()),
        "ir-parent-region-unresolved",
        &["parent_region", "missing-region"],
    );
}

#[rstest]
fn validate_ir_consistency_reports_invalid_origin_nodes() {
    assert_validation_reports_on_first_region(
        |region| region.origin_nodes.clear(),
        "ir-origin-nodes-invalid",
        &["origin_nodes", "empty"],
    );
}

#[rstest]
fn markdown_ir_document_records_soft_breaks_as_synthetic_segments() {
    let source = "First line\nsecond line\n";
    let document = markdown_ir_document(source, source_identity(Path::new("docs/example.md")));

    assert!(matches!(&document, Ok(value) if value.regions.len() == 1));
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

#[rstest]
fn markdown_ir_document_keeps_empty_heading_regions() {
    let document = markdown_ir_document("#\n", source_identity(Path::new("docs/example.md")))
        .expect("expected Markdown IR document");

    assert!(document.regions.iter().any(|region| {
        region.kind == "heading"
            && region.text.is_empty()
            && region.segments.is_empty()
            && region.natural_language.is_none()
    }));
}

#[rstest]
fn markdown_ir_document_uses_synthetic_segment_for_decoded_text() {
    let document = markdown_ir_document("AT&amp;T", source_identity(Path::new("docs/example.md")))
        .expect("expected Markdown IR document");
    let paragraph = document
        .regions
        .iter()
        .find(|region| region.kind == "paragraph")
        .expect("expected paragraph region");

    assert_eq!(paragraph.text, "AT&T");
    assert!(paragraph.segments.iter().all(|segment| {
        segment.source.is_none() && segment.synthetic.as_deref() == Some("decoded_text")
    }));
}

#[rstest]
fn markdown_ir_document_uses_synthetic_segment_for_normalized_multiline_code_span() {
    use markdown::mdast::InlineCode;
    use markdown::unist::Position;

    use crate::flatten::{SourceNodeId, flatten_region};

    let node = Node::InlineCode(InlineCode {
        value: "first second".to_owned(),
        position: Some(Position::new(1, 1, 0, 2, 8, 14)),
    });

    let region = flatten_region(&node, SourceNodeId::new("n0"), "`first\nsecond`");

    assert_eq!(region.text, "first second");
    assert_eq!(region.segments.len(), 1);
    let segment = region
        .segments
        .first()
        .expect("expected normalized inline code fallback segment");
    assert_eq!(segment.source, None);
    assert_eq!(segment.synthetic.as_deref(), Some("decoded_text"));
}

#[rstest]
fn decoded_text_mapping_rejects_source_chunks_past_span_end() {
    let source = "abcd";
    let span =
        SourceSpan::new(0, 3).expect("expected source span for rejected source chunk to be valid");

    assert!(!decoded_text_maps_to_source(source, span, "abcd"));
}

#[rstest]
fn decoded_text_mapping_rejects_split_crlf_spans() {
    let source = "a\r\nb";
    let span = SourceSpan::new(0, 2).expect("expected source span for split CRLF test to be valid");

    assert!(!decoded_text_maps_to_source(source, span, "a\r\n"));
}

#[rstest]
fn flatten_inline_code_with_inverted_span_falls_back_to_decoded_text() {
    use markdown::mdast::InlineCode;
    use markdown::unist::Position;

    use crate::flatten::{SourceNodeId, flatten_region};

    // markdown-rs never emits an inverted span, but the inline-code fallback
    // must still surface the code text instead of dropping it when
    // `SourceSpan::new` rejects a start offset greater than the end offset.
    let node = Node::InlineCode(InlineCode {
        value: "code".to_owned(),
        position: Some(Position::new(1, 5, 4, 1, 1, 0)),
    });

    let region = flatten_region(&node, SourceNodeId::new("n0"), "`code`");

    assert_eq!(region.text, "code");
    assert_eq!(region.segments.len(), 1);
    let segment = region
        .segments
        .first()
        .expect("expected a single synthetic fallback segment");
    assert_eq!(segment.text, "code");
    assert_eq!((segment.text_start, segment.text_end), (0, 4));
    assert_eq!(segment.synthetic.as_deref(), Some("decoded_text"));
    assert_eq!(segment.source, None);
    assert_eq!(segment.node, None);
}

#[rstest]
fn source_span_rejects_nodes_without_a_position() {
    use markdown::mdast::InlineCode;

    // markdown-rs anchors every parsed node, but a node that arrives without a
    // position must be reported rather than fabricated as a `0..0` span that
    // would misanchor it to the document start.
    let node = Node::InlineCode(InlineCode {
        value: "code".to_owned(),
        position: None,
    });
    let context = diagnostic_context();

    let result = source_span(&node, &context);

    assert!(matches!(
        result,
        Err(ref error) if is_missing_node_span_error(error)
    ));
}

fn is_missing_node_span_error(error: &markdown::message::Message) -> bool {
    error.source.as_ref() == "stilyagi-markdown"
        && error.rule_id.as_ref() == "missing-node-span"
        && error.reason.contains("no source position")
}

fn region_kinds(regions: &[stilyagi_ir::IrRegion]) -> BTreeSet<&str> {
    regions.iter().map(|region| region.kind.as_str()).collect()
}
