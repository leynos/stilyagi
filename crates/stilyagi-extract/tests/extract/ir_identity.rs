//! Integration tests for Markdown IR identity and snapshot contracts.

use rstest::rstest;
use stilyagi_extract::SourceIdentity;
use stilyagi_test_support::SHARED_MARKDOWN_FIXTURE_PATH;

use crate::test_utils::{
    extracted_markdown, markdown_extraction_with_identity, shared_markdown_source,
};

#[rstest]
fn markdown_extraction_uses_anonymous_ir_identity_by_default(
    extracted_markdown: stilyagi_extract::ExtractDocument,
) {
    let ir = extracted_markdown
        .ir()
        .unwrap_or_else(|| panic!("expected Markdown IR payload"));

    assert_eq!(ir.document.path, None);
    assert_eq!(ir.document.uri, None);
}

#[rstest]
fn markdown_extraction_propagates_explicit_source_identity() {
    let document = markdown_extraction_with_identity(
        "# Heading",
        SourceIdentity::new(
            Some("docs/example.md".to_owned()),
            Some("file:///repo/docs/example.md".to_owned()),
        ),
    );
    let ir = document
        .ir()
        .unwrap_or_else(|| panic!("expected Markdown IR payload"));

    assert_eq!(ir.document.path.as_deref(), Some("docs/example.md"));
    assert_eq!(
        ir.document.uri.as_deref(),
        Some("file:///repo/docs/example.md")
    );
}

#[rstest]
fn shared_markdown_fixture_has_a_golden_ir_snapshot() {
    let document = stilyagi_test_support::golden_markdown_ir_fixture(SHARED_MARKDOWN_FIXTURE_PATH)
        .unwrap_or_else(|error| panic!("expected shared Markdown golden IR: {error}"));

    insta::assert_snapshot!(
        "extraction_tests__shared_markdown_fixture_has_a_golden_ir_snapshot",
        document.to_canonical_json()
    );
}

#[rstest]
fn markdown_extraction_attaches_markdown_ir(shared_markdown_source: String) {
    let document = stilyagi_extract::extract_document(
        &shared_markdown_source,
        stilyagi_extract::ExtractSyntax::Markdown,
    )
    .unwrap_or_else(|error| panic!("expected shared Markdown extraction: {error}"));
    let ir = document.ir();

    assert!(matches!(ir, Some(value) if value.document.syntax == "markdown"));
    assert!(matches!(
        ir,
        Some(value)
            if value.regions
                .iter()
                .all(stilyagi_ir::IrRegion::segments_reconstruct_text)
    ));
}
