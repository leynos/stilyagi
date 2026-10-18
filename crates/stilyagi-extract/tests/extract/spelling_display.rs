//! Integration tests for stable spelling and display contracts.
//!
//! `Display` output is the contract Python callers receive from the bridge, so
//! each variant's rendered spelling is pinned in a committed snapshot. The
//! surrounding assertions keep the round-trip and parse contracts; the
//! snapshots pin the text itself so a spelling change shows up as a reviewable
//! snapshot diff rather than a scattered `assert_eq!` edit.
//!
//! Snapshot names are composed inside the macro from the value under test
//! rather than passed as a case parameter. A second `&str` parameter on every
//! case would trip the `CodeScene` `String Heavy Function Arguments` advisory
//! on this module, even though the strings only name snapshots.

use rstest::rstest;

use stilyagi_extract::{ExtractError, ExtractSyntax, RegionKind};

#[rstest]
#[case::markdown(ExtractSyntax::Markdown)]
#[case::python_docstring(ExtractSyntax::PythonDocstring)]
#[case::rust_doc_comment(ExtractSyntax::RustDocComment)]
fn syntax_as_str_returns_the_expected_spelling(#[case] syntax: ExtractSyntax) {
    insta::assert_snapshot!(
        format!("syntax_as_str__{}", syntax.as_str()),
        syntax.as_str()
    );
}

#[rstest]
#[case::markdown(ExtractSyntax::Markdown)]
#[case::python_docstring(ExtractSyntax::PythonDocstring)]
#[case::rust_doc_comment(ExtractSyntax::RustDocComment)]
fn syntax_display_matches_as_str(#[case] syntax: ExtractSyntax) {
    insta::assert_snapshot!(
        format!("syntax_display__{}", syntax.as_str()),
        format!("{syntax}")
    );
}

#[rstest]
#[case::document(RegionKind::Document)]
#[case::python_docstring(RegionKind::PythonDocstring)]
#[case::rust_doc_comment(RegionKind::RustDocComment)]
fn region_kind_as_str_returns_the_expected_spelling(#[case] kind: RegionKind) {
    insta::assert_snapshot!(
        format!("region_kind_as_str__{}", kind.as_str()),
        kind.as_str()
    );
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
#[case::document(RegionKind::Document)]
#[case::python_docstring(RegionKind::PythonDocstring)]
#[case::rust_doc_comment(RegionKind::RustDocComment)]
fn region_kind_display_matches_as_str(#[case] kind: RegionKind) {
    insta::assert_snapshot!(
        format!("region_kind_display__{}", kind.as_str()),
        format!("{kind}")
    );
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

const fn extract_error_snapshot_suffix(error: &ExtractError) -> &'static str {
    match error {
        ExtractError::UnsupportedSyntax(ExtractSyntax::RustDocComment) => {
            "unsupported_rust_doc_comment"
        }
        ExtractError::UnknownSyntax(_) => "unknown_syntax_bogus",
        _ => "other",
    }
}

#[rstest]
#[case(ExtractError::UnsupportedSyntax(ExtractSyntax::RustDocComment))]
#[case(ExtractError::UnknownSyntax("bogus".to_owned()))]
fn extract_error_display_is_informative(#[case] error: ExtractError) {
    insta::assert_snapshot!(
        format!(
            "extract_error_display__{}",
            extract_error_snapshot_suffix(&error)
        ),
        format!("{error}")
    );
}
