//! Integration tests for extraction behaviour and region contracts.

use rstest::rstest;
use stilyagi_extract::ExtractSyntax;
use stilyagi_test_support::read_corpus_fixture;

use crate::test_utils::{
    boundary, extracted_blank_markdown_documents, extracted_markdown, extracted_unicode_markdown,
    must_reject_document, must_reject_syntax_name, shared_markdown_source, shared_python_source,
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

#[rstest]
fn markdown_extraction_preserves_the_shared_markdown_fixture(shared_markdown_source: String) {
    let document =
        stilyagi_extract::extract_document(&shared_markdown_source, ExtractSyntax::Markdown)
            .unwrap_or_else(|error| panic!("expected shared Markdown extraction: {error}"));
    let first_region = document.regions().first();

    assert_eq!(document.syntax(), ExtractSyntax::Markdown);
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
        Some(shared_markdown_source.as_str())
    );
}

fn python_extraction_preserves_shared_fixture_docstrings(shared_python_source: String) {
    let document =
        stilyagi_extract::extract_document(&shared_python_source, ExtractSyntax::PythonDocstring)
            .unwrap_or_else(|error| panic!("expected shared Python extraction: {error}"));
    let first_region = document.regions().first();

    assert_eq!(document.syntax(), ExtractSyntax::PythonDocstring);
    assert_eq!(document.regions().len(), 4);
    assert_eq!(
        first_region.and_then(stilyagi_extract::ExtractRegion::region_kind),
        Some(stilyagi_extract::RegionKind::PythonDocstring)
    );
    assert_eq!(
        first_region.map(stilyagi_extract::ExtractRegion::kind),
        Some("python_docstring")
    );
    assert_eq!(
        first_region.map(stilyagi_extract::ExtractRegion::text),
        Some("Module docstring for the shared Stilyagi corpus.")
    );
}
fn malformed_corpus_fixtures_are_readable_utf8_sources(#[case] relative_path: &str) {
    let source = read_corpus_fixture(relative_path)
        .unwrap_or_else(|error| panic!("expected readable fixture {relative_path}: {error}"));

    assert!(!source.is_empty());
}

#[rstest]
#[case(ExtractSyntax::RustDocComment)]
fn unsupported_syntaxes_are_rejected(#[case] syntax: ExtractSyntax) {
    let error = must_reject_document("example", syntax);

    assert_eq!(
        error,
        stilyagi_extract::ExtractError::UnsupportedSyntax(syntax)
    );
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
