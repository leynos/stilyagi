//! Integration tests for stable spelling and display contracts.
//!
//! `Display` output is the contract Python callers receive from the bridge, so
//! each variant's rendered spelling is pinned in a committed snapshot. The
//! surrounding assertions keep the round-trip and parse contracts; the
//! snapshots pin the text itself so a spelling change shows up as a reviewable
//! snapshot diff rather than a scattered `assert_eq!` edit.
//!
//! Snapshot names come from a fixed identity, never from `as_str()`. If one
//! variant's spelling collided with another's, a name derived from the
//! spelling would make the colliding case read the wrong variant's snapshot
//! and pass; the explicit assertion beside each snapshot turns that collision
//! into a failure. The name is a [`SnapshotName`] rather than a bare `&str`
//! because `CodeScene`'s `String Heavy Function Arguments` advisory counts
//! every string parameter, including one that only names a snapshot.

use rstest::rstest;
use stilyagi_extract::{ExtractError, ExtractSyntax, RegionKind};

/// A committed snapshot name, kept separate from the type under test.
#[derive(Clone, Copy)]
struct SnapshotName(&'static str);

/// Pins the spelling `as_str` returns for every syntax variant.
#[rstest]
#[case::markdown(
    ExtractSyntax::Markdown,
    SnapshotName("syntax_as_str__markdown"),
    "markdown"
)]
#[case::python_docstring(
    ExtractSyntax::PythonDocstring,
    SnapshotName("syntax_as_str__python_docstring"),
    "python_docstring"
)]
#[case::rust_doc_comment(
    ExtractSyntax::RustDocComment,
    SnapshotName("syntax_as_str__rust_doc_comment"),
    "rust_doc_comment"
)]
fn syntax_as_str_returns_the_expected_spelling(
    #[case] syntax: ExtractSyntax,
    #[case] snapshot_name: SnapshotName,
    #[case] expected: &str,
) {
    assert_eq!(syntax.as_str(), expected);
    insta::assert_snapshot!(snapshot_name.0, syntax.as_str());
}

/// Pins `Display` for every syntax variant and checks it matches `as_str`.
#[rstest]
#[case::markdown(ExtractSyntax::Markdown, SnapshotName("syntax_display__markdown"))]
#[case::python_docstring(
    ExtractSyntax::PythonDocstring,
    SnapshotName("syntax_display__python_docstring")
)]
#[case::rust_doc_comment(
    ExtractSyntax::RustDocComment,
    SnapshotName("syntax_display__rust_doc_comment")
)]
fn syntax_display_matches_as_str(
    #[case] syntax: ExtractSyntax,
    #[case] snapshot_name: SnapshotName,
) {
    assert_eq!(format!("{syntax}"), syntax.as_str());
    insta::assert_snapshot!(snapshot_name.0, format!("{syntax}"));
}

/// Pins the spelling `as_str` returns for every region-kind variant.
#[rstest]
#[case::document(
    RegionKind::Document,
    SnapshotName("region_kind_as_str__document"),
    "document"
)]
#[case::python_docstring(
    RegionKind::PythonDocstring,
    SnapshotName("region_kind_as_str__python_docstring"),
    "python_docstring"
)]
#[case::rust_doc_comment(
    RegionKind::RustDocComment,
    SnapshotName("region_kind_as_str__rust_doc_comment"),
    "rust_doc_comment"
)]
fn region_kind_as_str_returns_the_expected_spelling(
    #[case] kind: RegionKind,
    #[case] snapshot_name: SnapshotName,
    #[case] expected: &str,
) {
    assert_eq!(kind.as_str(), expected);
    insta::assert_snapshot!(snapshot_name.0, kind.as_str());
}

/// Every documented region-kind spelling must parse back to its variant.
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

/// Pins `Display` for every region-kind variant and checks it matches
/// `as_str`.
#[rstest]
#[case::document(RegionKind::Document, SnapshotName("region_kind_display__document"))]
#[case::python_docstring(
    RegionKind::PythonDocstring,
    SnapshotName("region_kind_display__python_docstring")
)]
#[case::rust_doc_comment(
    RegionKind::RustDocComment,
    SnapshotName("region_kind_display__rust_doc_comment")
)]
fn region_kind_display_matches_as_str(
    #[case] kind: RegionKind,
    #[case] snapshot_name: SnapshotName,
) {
    assert_eq!(format!("{kind}"), kind.as_str());
    insta::assert_snapshot!(snapshot_name.0, format!("{kind}"));
}

/// Every variant's spelling must parse back to the same variant.
#[rstest]
#[case(RegionKind::Document)]
#[case(RegionKind::PythonDocstring)]
#[case(RegionKind::RustDocComment)]
fn region_kind_as_str_round_trips_through_try_from(#[case] kind: RegionKind) {
    assert_eq!(RegionKind::try_from(kind.as_str()), Ok(kind));
}

/// Every documented spelling must render back to itself through `as_str`.
#[rstest]
#[case("document")]
#[case("python_docstring")]
#[case("rust_doc_comment")]
fn region_kind_try_from_round_trips_through_as_str(#[case] spelling: &str) {
    let kind = RegionKind::try_from(spelling).expect("known RegionKind spelling should parse");
    assert_eq!(kind.as_str(), spelling);
}

/// Pins the rendered text callers see for each representative error.
///
/// Every case names its own snapshot. A lookup that derived the name from the
/// error would need a catch-all arm, so a newly added `ExtractError` variant
/// could silently reuse an existing case's snapshot instead of failing.
#[rstest]
#[case::unsupported_rust_doc_comment(
    ExtractError::UnsupportedSyntax(ExtractSyntax::RustDocComment),
    SnapshotName("extract_error_display__unsupported_rust_doc_comment")
)]
#[case::unknown_syntax(
    ExtractError::UnknownSyntax("bogus".to_owned()),
    SnapshotName("extract_error_display__unknown_syntax_bogus")
)]
fn extract_error_display_is_informative(
    #[case] error: ExtractError,
    #[case] snapshot_name: SnapshotName,
) {
    insta::assert_snapshot!(snapshot_name.0, format!("{error}"));
}
