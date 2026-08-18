//! Regression tests for Markdown IR segment origin and source-span contracts.

use std::path::Path;

use rstest::rstest;
use stilyagi_ir::{IrSegment, SourceSpan};

use super::source_identity;
use super::validation_support::{assert_validation_reports, validation_failure_for_first_segment};
use crate::markdown_ir_document;

/// Give a source-backed segment a synthetic reason as well, so it claims both
/// origins at once.
fn claim_both_origins(segment: &mut IrSegment) {
    segment.synthetic = Some("decoded_text".to_owned());
}

/// Strip the source span from a segment that has no synthetic reason, so it
/// claims no origin at all.
fn claim_no_origin(segment: &mut IrSegment) {
    segment.source = None;
}

#[rstest]
#[case::both_origins(
    claim_both_origins as fn(&mut IrSegment),
    &[
        "segment origin invalid",
        "source_present=true",
        "synthetic_present=true",
    ]
)]
#[case::no_origin(
    claim_no_origin as fn(&mut IrSegment),
    &[
        "segment origin invalid",
        "source_present=false",
        "synthetic_present=false",
    ]
)]
fn validate_ir_consistency_reports_invalid_segment_origins(
    #[case] mutate_segment: fn(&mut IrSegment),
    #[case] expected_reason_fragments: &[&str],
) {
    let failure = validation_failure_for_first_segment(mutate_segment)
        .expect("expected a segment origin validation failure");

    assert_validation_reports!(
        failure,
        "ir-segment-origin-invalid",
        expected_reason_fragments
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
