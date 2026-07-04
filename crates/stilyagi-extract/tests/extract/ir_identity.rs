//! Integration tests for Markdown IR identity and snapshot contracts.

use rstest::rstest;
use stilyagi_extract::SourceIdentity;
use stilyagi_test_support::{
    MALFORMED_PYTHON_FIXTURE_PATH, MALFORMED_RUST_FIXTURE_PATH, SHARED_MARKDOWN_FIXTURE_PATH,
    SHARED_PYTHON_FIXTURE_PATH, SHARED_RUST_FIXTURE_PATH, golden_rust_ir_fixture,
};

use crate::test_utils::{
    extracted_markdown, markdown_extraction_with_identity, shared_markdown_source,
    shared_python_source, shared_rust_source,
};

#[rstest]
fn markdown_extraction_uses_anonymous_ir_identity_by_default(
    extracted_markdown: stilyagi_extract::ExtractDocument,
) {
    let ir = extracted_markdown
        .ir()
        .expect("expected Markdown IR payload");

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
    let ir = document.ir().expect("expected Markdown IR payload");

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
fn shared_python_fixture_has_a_golden_ir_snapshot() {
    let document = stilyagi_test_support::golden_python_ir_fixture(SHARED_PYTHON_FIXTURE_PATH)
        .unwrap_or_else(|error| panic!("expected shared Python golden IR: {error}"));

    insta::assert_snapshot!(
        "extraction_tests__shared_python_fixture_has_a_golden_ir_snapshot",
        document
            .to_canonical_json()
            .unwrap_or_else(|error| panic!("expected canonical Python IR JSON: {error}"))
    );
}

#[rstest]
fn malformed_python_fixture_has_a_golden_ir_snapshot() {
    let document = stilyagi_test_support::golden_python_ir_fixture(MALFORMED_PYTHON_FIXTURE_PATH)
        .unwrap_or_else(|error| panic!("expected malformed Python golden IR: {error}"));

    assert_eq!(document.regions.len(), 1);
    let region = document
        .regions
        .first()
        .expect("expected one malformed Python docstring region");
    assert_eq!(region.kind, "python_docstring");
    assert_eq!(
        region.text,
        "Module docstring before malformed Python source."
    );
    assert!(!document.errors.is_empty());

    insta::assert_snapshot!(
        "extraction_tests__malformed_python_fixture_has_a_golden_ir_snapshot",
        document
            .to_canonical_json()
            .unwrap_or_else(|error| panic!("expected canonical Python IR JSON: {error}"))
    );
}

#[rstest]
fn shared_rust_fixture_has_a_golden_ir_snapshot() {
    let document = golden_rust_ir_fixture(SHARED_RUST_FIXTURE_PATH)
        .unwrap_or_else(|error| panic!("expected shared Rust golden IR: {error}"));

    assert_eq!(document.document.syntax, "rust");
    assert_eq!(document.regions.len(), 4);
    assert!(document.regions.iter().all(|region| region.owner.is_some()));
    assert!(
        document
            .regions
            .iter()
            .all(stilyagi_ir::IrRegion::segments_reconstruct_text)
    );

    insta::assert_snapshot!(
        "extraction_tests__shared_rust_fixture_has_a_golden_ir_snapshot",
        document
            .to_canonical_json()
            .unwrap_or_else(|error| panic!("expected canonical Rust IR JSON: {error}"))
    );
}

#[rstest]
fn malformed_rust_fixture_has_a_golden_ir_snapshot() {
    let document = golden_rust_ir_fixture(MALFORMED_RUST_FIXTURE_PATH)
        .unwrap_or_else(|error| panic!("expected malformed Rust golden IR: {error}"));

    assert_eq!(document.document.syntax, "rust");
    assert_eq!(document.regions.len(), 1);
    let region = document
        .regions
        .first()
        .expect("expected one malformed Rust doc-comment region");
    assert_eq!(region.kind, "rust_doc_comment");
    assert_eq!(
        region.text,
        " Crate-level documentation before malformed Rust source."
    );
    assert!(!document.errors.is_empty());

    insta::assert_snapshot!(
        "extraction_tests__malformed_rust_fixture_has_a_golden_ir_snapshot",
        document
            .to_canonical_json()
            .unwrap_or_else(|error| panic!("expected canonical Rust IR JSON: {error}"))
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

#[rstest]
fn python_extraction_attaches_owner_aware_ir(shared_python_source: String) {
    let document = stilyagi_extract::extract_document(
        &shared_python_source,
        stilyagi_extract::ExtractSyntax::PythonDocstring,
    )
    .unwrap_or_else(|error| panic!("expected shared Python extraction: {error}"));
    let ir = document.ir().expect("expected Python IR payload");

    assert_eq!(ir.document.syntax, "python");
    assert!(!ir.regions.is_empty());
    assert!(ir.regions.iter().all(|region| region.owner.is_some()));
    assert!(
        ir.regions
            .iter()
            .all(stilyagi_ir::IrRegion::segments_reconstruct_text)
    );
}

#[rstest]
fn rust_extraction_attaches_owner_aware_ir(shared_rust_source: String) {
    let document = stilyagi_extract::extract_document(
        &shared_rust_source,
        stilyagi_extract::ExtractSyntax::RustDocComment,
    )
    .unwrap_or_else(|error| panic!("expected shared Rust extraction: {error}"));
    let ir = document.ir().expect("expected Rust IR payload");

    assert_eq!(ir.document.syntax, "rust");
    assert_eq!(ir.regions.len(), 4);
    assert!(ir.regions.iter().all(|region| region.owner.is_some()));
    assert!(
        ir.regions
            .iter()
            .all(stilyagi_ir::IrRegion::segments_reconstruct_text)
    );
}
