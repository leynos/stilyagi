//! Tests for Markdown IR envelope construction and consistency validation.

use std::collections::BTreeSet;

use markdown::mdast::Node;
use rstest::rstest;
use stilyagi_ir::SourceSpan;

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
        source_identity("tests/fixtures/corpus/markdown/valid/example.md"),
    );

    assert!(matches!(&document, Ok(value) if value.document.syntax == "markdown"));
    if let Ok(value) = document {
        assert_eq!(value.schema_version, "1.0.0");
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
    let document = markdown_ir_document(source, source_identity("docs/example.md"))
        .unwrap_or_else(|error| panic!("expected Markdown IR document: {error}"));

    assert_eq!(
        document.document.content_hash,
        stilyagi_ir::content_hash_for(source)
    );
    assert_eq!(document.line_index, stilyagi_ir::line_index_for(source));
}

#[rstest]
fn validate_ir_consistency_reports_content_hash_mismatches() {
    let source = "# Heading\n\nBody";
    let mut document = markdown_ir_document(source, source_identity("docs/example.md"))
        .unwrap_or_else(|error| panic!("expected Markdown IR document: {error}"));
    document.document.content_hash = "sha256:bad".to_owned();
    let context = diagnostic_context();

    let result = validate_ir_consistency(&document, source, &context);

    assert!(matches!(
        result,
        Err(ref error)
            if error.source.as_ref() == "stilyagi-markdown"
                && error.rule_id.as_ref() == "ir-content-hash-mismatch"
                && error.reason.contains("phase=validate")
                && error.reason.contains("path=")
                && error.reason.contains("uri=")
                && error.reason.contains("content_hash mismatch")
    ));
}

#[rstest]
fn validate_ir_consistency_reports_line_index_mismatches() {
    let source = "# Heading\n\nBody";
    let mut document = markdown_ir_document(source, source_identity("docs/example.md"))
        .unwrap_or_else(|error| panic!("expected Markdown IR document: {error}"));
    document.line_index.push(usize::MAX);
    let context = diagnostic_context();

    let result = validate_ir_consistency(&document, source, &context);

    assert!(matches!(
        result,
        Err(ref error)
            if error.source.as_ref() == "stilyagi-markdown"
                && error.rule_id.as_ref() == "ir-line-index-mismatch"
                && error.reason.contains("phase=validate")
                && error.reason.contains("line_index mismatch")
    ));
}

#[rstest]
fn validate_ir_consistency_reports_region_text_mismatches() {
    let source = "# Heading\n\nBody";
    let mut document = markdown_ir_document(source, source_identity("docs/example.md"))
        .unwrap_or_else(|error| panic!("expected Markdown IR document: {error}"));
    let region = document
        .regions
        .first_mut()
        .unwrap_or_else(|| panic!("expected at least one Markdown IR region"));
    region.text.push_str(" drift");
    let context = diagnostic_context();

    let result = validate_ir_consistency(&document, source, &context);

    assert!(matches!(
        result,
        Err(ref error)
            if error.source.as_ref() == "stilyagi-markdown"
                && error.rule_id.as_ref() == "ir-region-text-mismatch"
                && error.reason.contains("phase=validate")
                && error.reason.contains("region text mismatch")
    ));
}

#[rstest]
fn markdown_ir_document_records_soft_breaks_as_synthetic_segments() {
    let source = "First line\nsecond line\n";
    let document = markdown_ir_document(source, source_identity("docs/example.md"));

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
    let document = markdown_ir_document("#\n", source_identity("docs/example.md"))
        .unwrap_or_else(|error| panic!("expected Markdown IR document: {error}"));

    assert!(document.regions.iter().any(|region| {
        region.kind == "heading"
            && region.text.is_empty()
            && region.segments.is_empty()
            && region.natural_language.is_none()
    }));
}

#[rstest]
fn markdown_ir_document_uses_synthetic_segment_for_decoded_text() {
    let document = markdown_ir_document("AT&amp;T", source_identity("docs/example.md"))
        .unwrap_or_else(|error| panic!("expected Markdown IR document: {error}"));
    let paragraph = document
        .regions
        .iter()
        .find(|region| region.kind == "paragraph")
        .unwrap_or_else(|| panic!("expected paragraph region"));

    assert_eq!(paragraph.text, "AT&T");
    assert!(paragraph.segments.iter().all(|segment| {
        segment.source.is_none() && segment.synthetic.as_deref() == Some("decoded_text")
    }));
}

#[rstest]
fn decoded_text_mapping_rejects_source_chunks_past_span_end() {
    let source = "abcd";
    let span = SourceSpan::new(0, 3)
        .unwrap_or_else(|| panic!("expected source span for rejected source chunk to be valid"));

    assert!(!decoded_text_maps_to_source(source, span, "abcd"));
}

#[rstest]
fn decoded_text_mapping_rejects_split_crlf_spans() {
    let source = "a\r\nb";
    let span = SourceSpan::new(0, 2)
        .unwrap_or_else(|| panic!("expected source span for split CRLF test to be valid"));

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
        .unwrap_or_else(|| panic!("expected a single synthetic fallback segment"));
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
        Err(ref error)
            if error.source.as_ref() == "stilyagi-markdown"
                && error.rule_id.as_ref() == "missing-node-span"
                && error.reason.contains("no source position")
    ));
}

fn region_kinds(regions: &[stilyagi_ir::IrRegion]) -> BTreeSet<&str> {
    regions.iter().map(|region| region.kind.as_str()).collect()
}
