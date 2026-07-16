//! Integration tests for Markdown IR identity and snapshot contracts.

use rstest::rstest;
use stilyagi_extract::{ExtractSyntax, SourceIdentity};
use stilyagi_ir::SuppressionKind;
use stilyagi_test_support::{
    MALFORMED_PYTHON_FIXTURE_PATH, MALFORMED_RUST_FIXTURE_PATH, NESTED_RUST_FIXTURE_PATH,
    SHARED_MARKDOWN_FIXTURE_PATH, SHARED_PYTHON_FIXTURE_PATH, SHARED_RUST_FIXTURE_PATH,
    golden_rust_ir_fixture,
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
#[case::markdown(
        "extraction_tests__shared_markdown_fixture_has_a_golden_ir_snapshot",
        || stilyagi_test_support::golden_markdown_ir_fixture(SHARED_MARKDOWN_FIXTURE_PATH)
            .expect("shared Markdown fixture should produce golden IR")
            .to_canonical_json()
    )]
#[case::python(
        "extraction_tests__shared_python_fixture_has_a_golden_ir_snapshot",
        || stilyagi_test_support::golden_python_ir_fixture(SHARED_PYTHON_FIXTURE_PATH)
            .expect("shared Python fixture should produce golden IR")
            .to_canonical_json()
            .expect("shared Python golden IR should serialize to canonical JSON")
    )]
fn shared_fixture_has_a_golden_ir_snapshot(#[case] name: &str, #[case] build: impl Fn() -> String) {
    insta::assert_snapshot!(name, build());
}

#[rstest]
fn malformed_python_fixture_has_a_golden_ir_snapshot() {
    let document = stilyagi_test_support::golden_python_ir_fixture(MALFORMED_PYTHON_FIXTURE_PATH)
        .expect("malformed Python fixture should produce golden IR");

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
            .expect("malformed Python golden IR should serialize to canonical JSON")
    );
}

#[rstest]
fn shared_rust_fixture_has_a_golden_ir_snapshot() {
    let document = golden_rust_ir_fixture(SHARED_RUST_FIXTURE_PATH)
        .expect("shared Rust fixture should produce golden IR");

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
            .expect("shared Rust golden IR should serialize to canonical JSON")
    );
}

#[rstest]
fn nested_rust_fixture_has_a_golden_ir_snapshot() {
    let document = golden_rust_ir_fixture(NESTED_RUST_FIXTURE_PATH)
        .expect("nested Rust fixture should produce golden IR");

    assert_eq!(document.document.syntax, "rust");
    assert!(document.regions.iter().all(|region| region.owner.is_some()));
    assert!(
        document
            .regions
            .iter()
            .all(stilyagi_ir::IrRegion::segments_reconstruct_text)
    );

    insta::assert_snapshot!(
        "extraction_tests__nested_rust_fixture_has_a_golden_ir_snapshot",
        document
            .to_canonical_json()
            .expect("nested Rust golden IR should serialize to canonical JSON")
    );
}

#[rstest]
fn malformed_rust_fixture_has_a_golden_ir_snapshot() {
    let document = golden_rust_ir_fixture(MALFORMED_RUST_FIXTURE_PATH)
        .expect("malformed Rust fixture should produce golden IR");

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
            .expect("malformed Rust golden IR should serialize to canonical JSON")
    );
}

#[rstest]
fn suppressions_are_shape_parity_across_the_v1_syntaxes() {
    let sources = [
        (ExtractSyntax::Markdown, "<!-- stilyagi: disable X001 -->\n"),
        (ExtractSyntax::PythonDocstring, "# stilyagi: disable X001\n"),
        (ExtractSyntax::RustDocComment, "// stilyagi: disable X001\n"),
    ];

    for (syntax, source) in sources {
        let document = stilyagi_extract::extract_document(source, syntax)
            .expect("supported syntax should extract successfully");
        let ir = document.ir().expect("expected IR payload");
        let suppression = ir
            .suppressions
            .first()
            .expect("expected a single suppression");

        assert_eq!(ir.suppressions.len(), 1);
        assert_eq!(suppression.kind, SuppressionKind::Range);
        assert_eq!(suppression.codes, vec!["X001".to_owned()]);
        assert_eq!(suppression.id, "s0");
    }
}

#[rstest]
fn markdown_extraction_attaches_markdown_ir(shared_markdown_source: String) {
    let document = stilyagi_extract::extract_document(
        &shared_markdown_source,
        stilyagi_extract::ExtractSyntax::Markdown,
    )
    .expect("shared Markdown source should extract successfully");
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
    .expect("shared Python source should extract successfully");
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
    .expect("shared Rust source should extract successfully");
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
