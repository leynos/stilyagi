//! Integration tests for extraction behaviour and region contracts.

use rstest::rstest;
use stilyagi_extract::{ExtractDocument, ExtractError, ExtractSyntax};
use stilyagi_test_support::read_corpus_fixture;

use crate::test_utils::{
    FixtureSource,
    boundary,
    extracted_blank_markdown_documents,
    extracted_markdown,
    extracted_unicode_markdown,
    shared_markdown_source,
    shared_python_source,
    shared_rust_source,
    syntax_name_rejection,
};

#[rstest]
fn extract_boundary_default_exposes_the_expected_markers() {
    let boundary = boundary();

    assert_eq!(boundary.markdown(), &stilyagi_markdown::MarkdownBoundary);
    assert_eq!(
        boundary.tree_sitter(),
        &stilyagi_tree_sitter::TreeSitterBoundary
    );
    assert_eq!(boundary.ir(), &stilyagi_ir::IrBoundary);
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
    extracted_markdown: Result<ExtractDocument, ExtractError>,
) {
    let document = extracted_markdown.expect("extracted_markdown fixture should extract");

    assert_eq!(document.syntax(), ExtractSyntax::Markdown);
}

#[rstest]
fn empty_markdown_extraction_yields_no_regions(
    extracted_blank_markdown_documents: Result<Vec<ExtractDocument>, ExtractError>,
) {
    let documents = extracted_blank_markdown_documents
        .expect("extracted_blank_markdown_documents fixture should extract");
    let document = documents.first().expect("expected empty Markdown fixture");

    assert_eq!(document.regions(), []);
    assert!(document.ir().is_some());
}

#[rstest]
fn whitespace_markdown_extraction_yields_no_regions(
    extracted_blank_markdown_documents: Result<Vec<ExtractDocument>, ExtractError>,
) {
    let documents = extracted_blank_markdown_documents
        .expect("extracted_blank_markdown_documents fixture should extract");
    let document = documents
        .get(1)
        .expect("expected whitespace Markdown fixture");

    assert_eq!(document.regions(), []);
    assert!(document.ir().is_some());
}

#[rstest]
fn non_blank_markdown_extraction_yields_one_document_region(
    extracted_markdown: Result<ExtractDocument, ExtractError>,
) {
    let document = extracted_markdown.expect("extracted_markdown fixture should extract");
    assert_eq!(document.regions().len(), 1);
    let first_region = document.regions().first();
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
    extracted_unicode_markdown: Result<ExtractDocument, ExtractError>,
) {
    let document =
        extracted_unicode_markdown.expect("extracted_unicode_markdown fixture should extract");
    let first_region = document.regions().first();

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

#[track_caller]
fn assert_shared_fixture_extraction(
    document: &ExtractDocument,
    expected: ExtractionExpectation<'_>,
) {
    let first_region = document.regions().first();

    assert_eq!(
        document.syntax(),
        expected.syntax,
        "document syntax should match the fixture expectation"
    );
    if let Some(count) = expected.region_count {
        assert_eq!(
            document.regions().len(),
            count,
            "region count should match the fixture expectation"
        );
    }
    assert_eq!(
        first_region.and_then(stilyagi_extract::ExtractRegion::region_kind),
        Some(expected.region_kind),
        "first region kind should match the fixture expectation"
    );
    assert_eq!(
        first_region.map(stilyagi_extract::ExtractRegion::kind),
        Some(expected.kind_str),
        "first region kind name should match the fixture expectation"
    );
    assert_eq!(
        first_region.map(stilyagi_extract::ExtractRegion::text),
        Some(expected.text),
        "first region text should match the fixture expectation"
    );
}

#[rstest]
fn markdown_extraction_preserves_the_shared_markdown_fixture(
    shared_markdown_source: FixtureSource,
) {
    let source = shared_markdown_source.expect("shared Markdown corpus fixture should be readable");
    let document = stilyagi_extract::extract_document(&source, ExtractSyntax::Markdown)
        .expect("shared Markdown fixture should extract");

    assert_shared_fixture_extraction(
        &document,
        ExtractionExpectation {
            syntax: ExtractSyntax::Markdown,
            region_count: None,
            region_kind: stilyagi_extract::RegionKind::Document,
            kind_str: "document",
            text: source.as_str(),
        },
    );
}

#[rstest]
fn python_extraction_preserves_shared_fixture_docstrings(shared_python_source: FixtureSource) {
    let source = shared_python_source.expect("shared Python corpus fixture should be readable");
    let document = stilyagi_extract::extract_document(&source, ExtractSyntax::PythonDocstring)
        .expect("shared Python fixture should extract");

    assert_shared_fixture_extraction(
        &document,
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
fn rust_extraction_preserves_shared_fixture_doc_comments(shared_rust_source: FixtureSource) {
    let source = shared_rust_source.expect("shared Rust corpus fixture should be readable");
    let document = stilyagi_extract::extract_document(&source, ExtractSyntax::RustDocComment)
        .expect("shared Rust fixture should extract");

    assert_shared_fixture_extraction(
        &document,
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

    assert_ne!(source, "");
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
    let error = syntax_name_rejection(input).expect("unknown syntax name should be rejected");
    assert!(matches!(
        error,
        stilyagi_extract::ExtractError::UnknownSyntax(_)
    ));
    assert!(error.to_string().contains(input) || input.is_empty());
}
