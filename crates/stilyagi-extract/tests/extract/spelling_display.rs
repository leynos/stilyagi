//! Integration tests for stable spelling and display contracts.
//!
//! `Display` output is the contract Python callers receive from the bridge, so
//! each variant's rendered spelling is pinned in a committed snapshot. The
//! surrounding assertions keep the round-trip and parse contracts; the
//! snapshots pin the text itself so a spelling change shows up as a reviewable
//! snapshot diff rather than a scattered `assert_eq!` edit.

use rstest::rstest;

use stilyagi_extract::{ExtractError, ExtractSyntax, RegionKind};

#[rstest]
#[case::markdown(ExtractSyntax::Markdown, "syntax_as_str__markdown")]
#[case::python_docstring(ExtractSyntax::PythonDocstring, "syntax_as_str__python_docstring")]
#[case::rust_doc_comment(ExtractSyntax::RustDocComment, "syntax_as_str__rust_doc_comment")]
fn syntax_as_str_returns_the_expected_spelling(
    #[case] syntax: ExtractSyntax,
    #[case] snapshot_name: &str,
) {
    insta::assert_snapshot!(snapshot_name, syntax.as_str());
}

#[rstest]
#[case::markdown(ExtractSyntax::Markdown, "syntax_display__markdown")]
#[case::python_docstring(ExtractSyntax::PythonDocstring, "syntax_display__python_docstring")]
#[case::rust_doc_comment(ExtractSyntax::RustDocComment, "syntax_display__rust_doc_comment")]
fn syntax_display_matches_as_str(#[case] syntax: ExtractSyntax, #[case] snapshot_name: &str) {
    insta::assert_snapshot!(snapshot_name, format!("{syntax}"));
}

#[rstest]
#[case::document(RegionKind::Document, "region_kind_as_str__document")]
#[case::python_docstring(RegionKind::PythonDocstring, "region_kind_as_str__python_docstring")]
#[case::rust_doc_comment(RegionKind::RustDocComment, "region_kind_as_str__rust_doc_comment")]
fn region_kind_as_str_returns_the_expected_spelling(
    #[case] kind: RegionKind,
    #[case] snapshot_name: &str,
) {
    insta::assert_snapshot!(snapshot_name, kind.as_str());
}

#[rstest]
#[case("document", RegionKind::Document)]
#[case("python_docstring", RegionKind::PythonDocstring)]
#[case("rust_doc_comment", RegionKind::RustDocComment)]
fn region_kind_try_from_accepts_the_expected_spelling(
    #[case] input: &str,
    #[case] expected: RegionKind,
) {
    assert_eq!(RegionKind::try_from(input), Ok(expected));
}

#[rstest]
#[case(RegionKind::Document, "region_kind_display__document")]
#[case(RegionKind::PythonDocstring, "region_kind_display__python_docstring")]
#[case(RegionKind::RustDocComment, "region_kind_display__rust_doc_comment")]
fn region_kind_display_matches_as_str(#[case] kind: RegionKind, #[case] snapshot_name: &str) {
    insta::assert_snapshot!(snapshot_name, format!("{kind}"));
}

#[rstest]
#[case(RegionKind::Document)]
#[case(RegionKind::PythonDocstring)]
#[case(RegionKind::RustDocComment)]
fn region_kind_as_str_round_trips_through_try_from(#[case] kind: RegionKind) {
    assert_eq!(RegionKind::try_from(kind.as_str()), Ok(kind));
}

#[rstest]
#[case("document")]
#[case("python_docstring")]
#[case("rust_doc_comment")]
fn region_kind_try_from_round_trips_through_as_str(#[case] spelling: &str) {
    let kind = RegionKind::try_from(spelling).expect("known RegionKind spelling should parse");
    assert_eq!(kind.as_str(), spelling);
}

#[rstest]
#[case(
    ExtractError::UnsupportedSyntax(ExtractSyntax::RustDocComment),
    "extract_error_display__unsupported_rust_doc_comment"
)]
#[case(
    ExtractError::UnknownSyntax("bogus".to_owned()),
    "extract_error_display__unknown_syntax_bogus"
)]
fn extract_error_display_is_informative(#[case] error: ExtractError, #[case] snapshot_name: &str) {
    insta::assert_snapshot!(snapshot_name, format!("{error}"));
}
