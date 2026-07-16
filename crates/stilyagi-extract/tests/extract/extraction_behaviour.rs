//! Integration tests for extraction behaviour and region contracts.

use rstest::rstest;
use stilyagi_extract::ExtractSyntax;
use stilyagi_test_support::read_corpus_fixture;

use crate::test_utils::{
    boundary, extracted_blank_markdown_documents, extracted_markdown, extracted_unicode_markdown,
    must_reject_syntax_name, shared_markdown_source, shared_python_source, shared_rust_source,
};

#[rstest]
fn extract_boundary_default_matches_another_default() {
    assert_eq!(boundary(), boundary());
}

#[rstest]
#[expect(
    clippy::default_constructed_unit_structs,
    reason = "this test explicitly exercises marker Default implementations"
)]
fn extract_boundary_accessors_expose_the_expected_markers() {
    let boundary = boundary();

    assert_eq!(
        boundary.markdown(),
        &stilyagi_markdown::MarkdownBoundary::default()
    );
    assert_eq!(
        boundary.tree_sitter(),
        &stilyagi_tree_sitter::TreeSitterBoundary::default()
    );
    assert_eq!(boundary.ir(), &stilyagi_ir::IrBoundary::default());
}

#[rstest]
fn extract_boundary_is_copy() {
    let original = boundary();
    let first = original;
    let second = original;

    assert_eq!(first, second);
    assert_eq!(first.markdown(), second.markdown());
    assert_eq!(first.tree_sitter(), second.tree_sitter());
    assert_eq!(first.ir(), second.ir());
}

#[rstest]
fn extract_boundary_debug_output_mentions_the_type_name() {
    assert!(format!("{:?}", boundary()).contains("ExtractBoundary"));
}

#[rstest]
fn markdown_extraction_reports_markdown_syntax(
    extracted_markdown: stilyagi_extract::ExtractDocument,
) {
    assert_eq!(extracted_markdown.syntax(), ExtractSyntax::Markdown);
}

#[rstest]
fn empty_markdown_extraction_yields_no_regions(
    extracted_blank_markdown_documents: Vec<stilyagi_extract::ExtractDocument>,
) {
    let document = extracted_blank_markdown_documents
        .first()
        .expect("expected empty Markdown fixture");

    assert!(document.regions().is_empty());
    assert!(document.ir().is_some());
}

#[rstest]
fn whitespace_markdown_extraction_yields_no_regions(
    extracted_blank_markdown_documents: Vec<stilyagi_extract::ExtractDocument>,
) {
    let document = extracted_blank_markdown_documents
        .get(1)
        .expect("expected whitespace Markdown fixture");

    assert!(document.regions().is_empty());
    assert!(document.ir().is_some());
}

#[rstest]
fn non_blank_markdown_extraction_yields_one_document_region(
    extracted_markdown: stilyagi_extract::ExtractDocument,
) {
    assert_eq!(extracted_markdown.regions().len(), 1);
    let first_region = extracted_markdown.regions().first();

    assert_eq!(
        first_region.and_then(stilyagi_extract::ExtractRegion::region_kind),
        Some(stilyagi_extract::RegionKind::Document)
    );
    assert_eq!(
        first_region.map(stilyagi_extract::ExtractRegion::kind),
        Some("document")
    );
    assert_eq!(
        first_region.map(stilyagi_extract::ExtractRegion::text),
        Some("# Heading")
    );
}

#[rstest]
fn markdown_extraction_preserves_unicode_text(
    extracted_unicode_markdown: stilyagi_extract::ExtractDocument,
) {
    let first_region = extracted_unicode_markdown.regions().first();

    assert_eq!(
        first_region.map(stilyagi_extract::ExtractRegion::text),
        Some("Zażółć gęślą jaźń 🫖")
    );
}

#[derive(Clone, Copy)]
struct ExtractionExpectation<'a> {
    syntax: stilyagi_extract::ExtractSyntax,
    region_count: Option<usize>,
    region_kind: stilyagi_extract::RegionKind,
    kind_str: &'static str,
    text: &'a str,
}

fn assert_shared_fixture_extraction(source: &str, expected: ExtractionExpectation<'_>) {
    let document = match stilyagi_extract::extract_document(source, expected.syntax) {
        Ok(document) => document,
        Err(error) => panic!("expected shared fixture extraction: {error}"),
    };
    let first_region = document.regions().first();

    assert_eq!(document.syntax(), expected.syntax);
    if let Some(count) = expected.region_count {
        assert_eq!(document.regions().len(), count);
    }
    assert_eq!(
        first_region.and_then(stilyagi_extract::ExtractRegion::region_kind),
        Some(expected.region_kind)
    );
    assert_eq!(
        first_region.map(stilyagi_extract::ExtractRegion::kind),
        Some(expected.kind_str)
    );
    assert_eq!(
        first_region.map(stilyagi_extract::ExtractRegion::text),
        Some(expected.text)
    );
}

#[rstest]
fn markdown_extraction_preserves_the_shared_markdown_fixture(shared_markdown_source: String) {
    assert_shared_fixture_extraction(
        shared_markdown_source.as_str(),
        ExtractionExpectation {
            syntax: ExtractSyntax::Markdown,
            region_count: None,
            region_kind: stilyagi_extract::RegionKind::Document,
            kind_str: "document",
            text: shared_markdown_source.as_str(),
        },
    );
}

#[rstest]
fn python_extraction_preserves_shared_fixture_docstrings(shared_python_source: String) {
    assert_shared_fixture_extraction(
        &shared_python_source,
        ExtractionExpectation {
            syntax: ExtractSyntax::PythonDocstring,
            region_count: Some(4),
            region_kind: stilyagi_extract::RegionKind::PythonDocstring,
            kind_str: "python_docstring",
            text: "Module docstring for the shared Stilyagi corpus.",
        },
    );
}

#[rstest]
fn rust_extraction_preserves_shared_fixture_doc_comments(shared_rust_source: String) {
    assert_shared_fixture_extraction(
        &shared_rust_source,
        ExtractionExpectation {
            syntax: ExtractSyntax::RustDocComment,
            region_count: Some(4),
            region_kind: stilyagi_extract::RegionKind::RustDocComment,
            kind_str: "rust_doc_comment",
            text: " Crate-level documentation comment for the shared Stilyagi corpus.",
        },
    );
}

#[rstest]
#[case("tests/fixtures/corpus/markdown/malformed/unclosed-table.md.fixture")]
#[case("tests/fixtures/corpus/python/malformed/unclosed-function.py.txt")]
#[case("tests/fixtures/corpus/rust/malformed/unclosed-item.rs")]
fn malformed_corpus_fixtures_are_readable_utf8_sources(#[case] relative_path: &str) {
    let source = read_corpus_fixture(relative_path)
        .expect("malformed corpus fixture should be readable UTF-8");

    assert!(!source.is_empty());
}

#[rstest]
fn rust_doc_comment_syntax_is_supported() {
    let document = stilyagi_extract::extract_document(
        "/// Rust doc comment\npub fn example() {}\n",
        ExtractSyntax::RustDocComment,
    )
    .expect("Rust doc-comment extraction should succeed");

    assert_eq!(document.syntax(), ExtractSyntax::RustDocComment);
    assert!(document.ir().is_some());
}

#[rstest]
#[case("totally_invalid")]
#[case("")]
#[case("MARKDOWN")]
fn try_from_str_rejects_unknown_syntax(#[case] input: &str) {
    let error = must_reject_syntax_name(input);
    assert!(matches!(
        error,
        stilyagi_extract::ExtractError::UnknownSyntax(_)
    ));
    assert!(error.to_string().contains(input) || input.is_empty());
}
