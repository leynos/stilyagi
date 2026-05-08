//! Integration tests for the public extraction crate surface.

use rstest::{fixture, rstest};
use stilyagi_extract::{
    ExtractBoundary, ExtractDocument, ExtractError, ExtractRegion, ExtractSyntax, RegionKind,
    extract_document,
};
use stilyagi_ir::IrBoundary;
use stilyagi_markdown::MarkdownBoundary;
use stilyagi_test_support::{SHARED_MARKDOWN_FIXTURE_PATH, read_corpus_fixture};
use stilyagi_tree_sitter::TreeSitterBoundary;

/// Keep the extraction boundary default stable and comparable.
#[test]
fn extract_boundary_default_matches_another_default() {
    assert_eq!(ExtractBoundary::default(), ExtractBoundary::default());
}

/// Keep the marker accessors wired to the corresponding boundary defaults.
#[test]
#[expect(
    clippy::default_constructed_unit_structs,
    reason = "this test explicitly exercises the marker Default implementations"
)]
fn extract_boundary_accessors_expose_the_expected_markers() {
    let boundary = ExtractBoundary::default();

    assert_eq!(boundary.markdown(), &MarkdownBoundary::default());
    assert_eq!(boundary.tree_sitter(), &TreeSitterBoundary::default());
    assert_eq!(boundary.ir(), &IrBoundary::default());
}

/// Keep the extraction boundary copy semantics available to callers.
#[test]
fn extract_boundary_is_copy() {
    let original = ExtractBoundary::default();
    let first = original;
    let second = original;

    assert_eq!(first, second);
    assert_eq!(first.markdown(), second.markdown());
    assert_eq!(first.tree_sitter(), second.tree_sitter());
    assert_eq!(first.ir(), second.ir());
}

/// Keep the extraction boundary debug output identifiable in failures.
#[test]
fn extract_boundary_debug_output_mentions_the_type_name() {
    assert!(format!("{:?}", ExtractBoundary::default()).contains("ExtractBoundary"));
}

#[expect(
    clippy::expect_used,
    reason = "test helper should fail loudly when a supported extraction path breaks"
)]
fn must_extract_document(source: &str, syntax: ExtractSyntax) -> ExtractDocument {
    extract_document(source, syntax).expect("expected successful extraction")
}

#[expect(
    clippy::expect_used,
    reason = "test helper should fail loudly when an unsupported extraction unexpectedly succeeds"
)]
fn must_reject_document(source: &str, syntax: ExtractSyntax) -> ExtractError {
    extract_document(source, syntax).expect_err("expected extraction failure")
}

#[expect(
    clippy::expect_used,
    reason = "test helper should fail loudly when invalid syntax conversion unexpectedly succeeds"
)]
fn must_reject_syntax_name(input: &str) -> ExtractError {
    ExtractSyntax::try_from(input).expect_err("expected unknown syntax error")
}

#[fixture]
fn extracted_markdown() -> ExtractDocument {
    must_extract_document("# Heading", ExtractSyntax::Markdown)
}

#[fixture]
fn extracted_blank_markdown_documents() -> Vec<ExtractDocument> {
    ["", "   \n\t"]
        .into_iter()
        .map(|source| must_extract_document(source, ExtractSyntax::Markdown))
        .collect()
}

#[fixture]
fn extracted_unicode_markdown() -> ExtractDocument {
    must_extract_document("Zażółć gęślą jaźń 🫖", ExtractSyntax::Markdown)
}

#[fixture]
fn shared_markdown_source() -> String {
    read_corpus_fixture(SHARED_MARKDOWN_FIXTURE_PATH).unwrap_or_else(|error| {
        panic!("expected shared Markdown corpus fixture to be readable: {error}")
    })
}

/// Keep the first extraction bridge pinned to Markdown for the initial
/// vertical slice.
#[rstest]
fn markdown_extraction_reports_markdown_syntax(extracted_markdown: ExtractDocument) {
    assert_eq!(extracted_markdown.syntax(), ExtractSyntax::Markdown);
}

/// Keep blank Markdown extraction honest instead of synthesizing placeholder
/// prose that does not exist in the source.
#[rstest]
fn blank_markdown_extraction_yields_no_regions(
    extracted_blank_markdown_documents: Vec<ExtractDocument>,
) {
    for document in extracted_blank_markdown_documents {
        assert!(document.regions().is_empty());
    }
}

/// Keep the first end-to-end bridge narrow by returning one source-faithful
/// region for non-empty Markdown.
#[rstest]
fn non_blank_markdown_extraction_yields_one_document_region(extracted_markdown: ExtractDocument) {
    assert_eq!(extracted_markdown.regions().len(), 1);
    let first_region = extracted_markdown.regions().first();

    assert_eq!(
        first_region.and_then(ExtractRegion::region_kind),
        Some(RegionKind::Document)
    );
    assert_eq!(first_region.map(ExtractRegion::kind), Some("document"));
    assert_eq!(first_region.map(ExtractRegion::text), Some("# Heading"));
}

/// Preserve Unicode content across the extraction boundary so later rule
/// layers can rely on source-faithful text.
#[rstest]
fn markdown_extraction_preserves_unicode_text(extracted_unicode_markdown: ExtractDocument) {
    let first_region = extracted_unicode_markdown.regions().first();

    assert_eq!(
        first_region.map(ExtractRegion::text),
        Some("Zażółć gęślą jaźń 🫖")
    );
}

/// Anchor Markdown extraction tests to the shared source corpus instead of
/// relying only on inline strings.
#[rstest]
fn markdown_extraction_preserves_the_shared_markdown_fixture(shared_markdown_source: String) {
    let document = must_extract_document(&shared_markdown_source, ExtractSyntax::Markdown);
    let first_region = document.regions().first();

    assert_eq!(document.syntax(), ExtractSyntax::Markdown);
    assert_eq!(
        first_region.and_then(ExtractRegion::region_kind),
        Some(RegionKind::Document)
    );
    assert_eq!(first_region.map(ExtractRegion::kind), Some("document"));
    assert_eq!(
        first_region.map(ExtractRegion::text),
        Some(shared_markdown_source.as_str()),
    );
}

/// Keep malformed corpus inputs loadable without promising parser recovery
/// semantics that belong to later extraction work.
#[rstest]
#[case("tests/fixtures/corpus/markdown/malformed/unclosed-table.md")]
#[case("tests/fixtures/corpus/python/malformed/unclosed-function.py.txt")]
#[case("tests/fixtures/corpus/rust/malformed/unclosed-item.rs")]
fn malformed_corpus_fixtures_are_readable_utf8_sources(#[case] relative_path: &str) {
    let source = read_corpus_fixture(relative_path)
        .unwrap_or_else(|error| panic!("expected readable fixture {relative_path}: {error}"));

    assert!(!source.is_empty());
}

/// Reject unsupported syntaxes explicitly so the Python layer can map the
/// failure to a user-facing `NotImplementedError`.
#[rstest]
#[case(ExtractSyntax::PythonDocstring)]
#[case(ExtractSyntax::RustDocComment)]
fn unsupported_syntaxes_are_rejected(#[case] syntax: ExtractSyntax) {
    let error = must_reject_document("example", syntax);

    assert_eq!(error, ExtractError::UnsupportedSyntax(syntax));
}

/// Keep the stable spelling of each syntax variant accessible to callers.
#[rstest]
#[case(ExtractSyntax::Markdown, "markdown")]
#[case(ExtractSyntax::PythonDocstring, "python_docstring")]
#[case(ExtractSyntax::RustDocComment, "rust_doc_comment")]
fn syntax_as_str_returns_the_expected_spelling(
    #[case] syntax: ExtractSyntax,
    #[case] expected: &str,
) {
    assert_eq!(syntax.as_str(), expected);
}

/// Keep the Display output for each syntax variant identical to `as_str`.
#[rstest]
#[case(ExtractSyntax::Markdown, "markdown")]
#[case(ExtractSyntax::PythonDocstring, "python_docstring")]
#[case(ExtractSyntax::RustDocComment, "rust_doc_comment")]
fn syntax_display_matches_as_str(#[case] syntax: ExtractSyntax, #[case] expected: &str) {
    assert_eq!(format!("{syntax}"), expected);
}

/// Keep the stable spelling of each region kind accessible to callers.
#[rstest]
#[case(RegionKind::Document, "document")]
fn region_kind_as_str_returns_the_expected_spelling(
    #[case] kind: RegionKind,
    #[case] expected: &str,
) {
    assert_eq!(kind.as_str(), expected);
}

/// Keep string parsing for each region kind aligned with `as_str`.
#[rstest]
#[case("document", RegionKind::Document)]
fn region_kind_try_from_accepts_the_expected_spelling(
    #[case] input: &str,
    #[case] expected: RegionKind,
) {
    assert_eq!(RegionKind::try_from(input), Ok(expected));
}

/// Keep the Display output for each region kind identical to `as_str`.
#[rstest]
#[case(RegionKind::Document, "document")]
fn region_kind_display_matches_as_str(#[case] kind: RegionKind, #[case] expected: &str) {
    assert_eq!(format!("{kind}"), expected);
}

/// Verify the format → parse round-trip: `as_str` output is accepted by
/// `TryFrom<&str>` and returns the original kind.
#[rstest]
#[case(RegionKind::Document)]
fn region_kind_as_str_round_trips_through_try_from(#[case] kind: RegionKind) {
    assert_eq!(RegionKind::try_from(kind.as_str()), Ok(kind));
}

/// Verify the parse → format round-trip: a valid `TryFrom<&str>` input is
/// returned verbatim by `as_str` on the parsed kind.
#[rstest]
#[case("document")]
fn region_kind_try_from_round_trips_through_as_str(#[case] spelling: &str) {
    let kind = RegionKind::try_from(spelling)
        .unwrap_or_else(|_| panic!("expected '{spelling}' to be a valid RegionKind"));
    assert_eq!(kind.as_str(), spelling);
}

/// Keep the Display output for each error variant informative and stable.
#[rstest]
#[case(
    ExtractError::UnsupportedSyntax(ExtractSyntax::PythonDocstring),
    "python_docstring extraction is not implemented yet."
)]
#[case(
    ExtractError::UnknownSyntax("bogus".to_owned()),
    "unknown syntax 'bogus'"
)]
fn extract_error_display_is_informative(#[case] error: ExtractError, #[case] expected: &str) {
    assert_eq!(format!("{error}"), expected);
}

/// Keep `TryFrom<&str>` honest by rejecting unrecognised syntax names.
#[rstest]
#[case("totally_invalid")]
#[case("")]
#[case("MARKDOWN")]
fn try_from_str_rejects_unknown_syntax(#[case] input: &str) {
    let error = must_reject_syntax_name(input);
    assert!(matches!(error, ExtractError::UnknownSyntax(_)));
    assert!(error.to_string().contains(input) || input.is_empty());
}

// ----- corpus_fixture_path path-validation panics -----

#[test]
#[should_panic(expected = "corpus fixture path must be repository-relative")]
fn corpus_fixture_path_rejects_absolute_path() {
    drop(stilyagi_test_support::corpus_fixture_path("/etc/passwd"));
}

#[test]
#[should_panic(expected = "corpus fixture path must not contain parent-directory traversal")]
fn corpus_fixture_path_rejects_parent_traversal() {
    drop(stilyagi_test_support::corpus_fixture_path(
        "../../etc/passwd",
    ));
}

#[test]
#[cfg(windows)]
#[should_panic(expected = "corpus fixture path must not contain a drive or path prefix")]
fn corpus_fixture_path_rejects_drive_prefix() {
    drop(stilyagi_test_support::corpus_fixture_path(
        std::path::Path::new("C:\\windows\\system32"),
    ));
}

#[test]
#[cfg(windows)]
#[should_panic(expected = "corpus fixture path must not be root-relative")]
fn corpus_fixture_path_rejects_root_relative() {
    drop(stilyagi_test_support::corpus_fixture_path(
        std::path::Path::new("\\etc"),
    ));
}
