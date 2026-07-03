//! Regression tests for Markdown IR segment origin and source-span contracts.

use std::path::Path;

use rstest::rstest;
use stilyagi_ir::{IrDocument, SourceSpan};

use super::source_identity;
use crate::{MarkdownDiagnosticContext, markdown_ir_document, validate_ir_consistency};

const fn diagnostic_context() -> MarkdownDiagnosticContext<'static> {
    MarkdownDiagnosticContext {
        phase: "validate",
        path: "docs/example.md",
        uri: "file:///repo/docs/example.md",
    }
}

fn assert_validation_reports(
    mutate: impl FnOnce(&mut IrDocument),
    expected_rule_id: &str,
    expected_reason_fragments: &[&str],
) {
    let source = "# Heading\n\nBody";
    let mut document = markdown_ir_document(source, source_identity(Path::new("docs/example.md")))
        .expect("expected Markdown IR document");
    mutate(&mut document);
    let context = diagnostic_context();

    let result = validate_ir_consistency(&document, source, &context);

    let Err(error) = result else {
        panic!("expected validation failure for rule {expected_rule_id}");
    };
    assert_eq!(error.rule_id.as_ref(), expected_rule_id);
    for fragment in expected_reason_fragments {
        assert!(
            error.reason.contains(fragment),
            "reason {:?} is missing fragment {fragment:?}",
            error.reason
        );
    }
}

#[rstest]
fn validate_ir_consistency_reports_segments_with_both_origins() {
    assert_validation_reports(
        |document| {
            let segment = document
                .regions
                .first_mut()
                .and_then(|region| region.segments.first_mut())
                .expect("expected at least one source-backed segment");
            segment.synthetic = Some("decoded_text".to_owned());
        },
        "ir-segment-origin-invalid",
        &[
            "segment origin invalid",
            "source_present=true",
            "synthetic_present=true",
        ],
    );
}

#[rstest]
fn validate_ir_consistency_reports_segments_without_an_origin() {
    assert_validation_reports(
        |document| {
            let segment = document
                .regions
                .first_mut()
                .and_then(|region| region.segments.first_mut())
                .expect("expected at least one source-backed segment");
            segment.source = None;
        },
        "ir-segment-origin-invalid",
        &[
            "segment origin invalid",
            "source_present=false",
            "synthetic_present=false",
        ],
    );
}

#[rstest]
fn markdown_ir_document_source_backs_inline_code_without_delimiters() {
    let source = "Before `code` after";
    let document = markdown_ir_document(source, source_identity(Path::new("docs/example.md")))
        .expect("expected Markdown IR document");
    let paragraph = document
        .regions
        .iter()
        .find(|region| region.kind == "paragraph")
        .expect("expected paragraph region");
    let code_segment = paragraph
        .segments
        .iter()
        .find(|segment| segment.text == "code")
        .expect("expected source-backed inline code segment");

    assert_eq!(code_segment.source, SourceSpan::new(8, 12));
    assert_eq!(source.get(8..12), Some("code"));
}
