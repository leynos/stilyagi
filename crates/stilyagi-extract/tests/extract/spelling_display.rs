//! Integration tests for stable spelling and display contracts.

use rstest::rstest;

use stilyagi_extract::{ExtractError, ExtractSyntax, RegionKind};

/// Names the closed set of stable string spellings under test.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ExpectedSpelling {
    Document,
    Markdown,
    PythonDocstring,
    RustDocComment,
    UnsupportedPythonDocstring,
    UnknownBogus,
}

impl AsRef<str> for ExpectedSpelling {
    fn as_ref(&self) -> &str {
        match self {
            Self::Document => "document",
            Self::Markdown => "markdown",
            Self::PythonDocstring => "python_docstring",
            Self::RustDocComment => "rust_doc_comment",
            Self::UnsupportedPythonDocstring => {
                "python_docstring extraction is not implemented yet."
            }
            Self::UnknownBogus => "unknown syntax 'bogus'",
        }
    }
}

#[rstest]
#[case(ExtractSyntax::Markdown, ExpectedSpelling::Markdown)]
#[case(ExtractSyntax::PythonDocstring, ExpectedSpelling::PythonDocstring)]
#[case(ExtractSyntax::RustDocComment, ExpectedSpelling::RustDocComment)]
fn syntax_as_str_returns_the_expected_spelling(
    #[case] syntax: ExtractSyntax,
    #[case] expected: ExpectedSpelling,
) {
    assert_eq!(syntax.as_str(), expected.as_ref());
}

#[rstest]
#[case(ExtractSyntax::Markdown, ExpectedSpelling::Markdown)]
#[case(ExtractSyntax::PythonDocstring, ExpectedSpelling::PythonDocstring)]
#[case(ExtractSyntax::RustDocComment, ExpectedSpelling::RustDocComment)]
fn syntax_display_matches_as_str(
    #[case] syntax: ExtractSyntax,
    #[case] expected: ExpectedSpelling,
) {
    assert_eq!(format!("{syntax}"), expected.as_ref());
}

#[rstest]
#[case(RegionKind::Document, ExpectedSpelling::Document)]
fn region_kind_as_str_returns_the_expected_spelling(
    #[case] kind: RegionKind,
    #[case] expected: ExpectedSpelling,
) {
    assert_eq!(kind.as_str(), expected.as_ref());
}

#[rstest]
#[case("document", RegionKind::Document)]
fn region_kind_try_from_accepts_the_expected_spelling(
    #[case] input: &str,
    #[case] expected: RegionKind,
) {
    assert_eq!(RegionKind::try_from(input), Ok(expected));
}

#[rstest]
#[case(RegionKind::Document, ExpectedSpelling::Document)]
fn region_kind_display_matches_as_str(
    #[case] kind: RegionKind,
    #[case] expected: ExpectedSpelling,
) {
    assert_eq!(format!("{kind}"), expected.as_ref());
}

#[rstest]
#[case(RegionKind::Document)]
fn region_kind_as_str_round_trips_through_try_from(#[case] kind: RegionKind) {
    assert_eq!(RegionKind::try_from(kind.as_str()), Ok(kind));
}

#[rstest]
#[case("document")]
fn region_kind_try_from_round_trips_through_as_str(#[case] spelling: &str) {
    let kind = RegionKind::try_from(spelling)
        .unwrap_or_else(|_| panic!("expected '{spelling}' to be a valid RegionKind"));
    assert_eq!(kind.as_str(), spelling);
}

#[rstest]
#[case(
    ExtractError::UnsupportedSyntax(ExtractSyntax::PythonDocstring),
    ExpectedSpelling::UnsupportedPythonDocstring
)]
#[case(ExtractError::UnknownSyntax("bogus".to_owned()), ExpectedSpelling::UnknownBogus)]
fn extract_error_display_is_informative(
    #[case] error: ExtractError,
    #[case] expected: ExpectedSpelling,
) {
    assert_eq!(format!("{error}"), expected.as_ref());
}
