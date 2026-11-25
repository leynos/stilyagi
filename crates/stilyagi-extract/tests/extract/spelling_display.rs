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

/// One type's spelling contract: its documented spelling, pinned by snapshot,
/// and the `Display` text that must agree with it.
#[derive(Clone, Copy)]
struct SpellingContract<T> {
    /// The variant under test.
    value: T,
    /// Snapshot pinning the spelling `as_str` returns.
    as_str_snapshot: SnapshotName,
    /// Snapshot pinning the `Display` text.
    display_snapshot: SnapshotName,
    /// The spelling both must produce.
    expected: &'static str,
}

/// Pins both `as_str` and `Display` for every syntax variant.
#[rstest]
#[case::markdown(SpellingContract {
    value: ExtractSyntax::Markdown,
    as_str_snapshot: SnapshotName("syntax_as_str__markdown"),
    display_snapshot: SnapshotName("syntax_display__markdown"),
    expected: "markdown",
})]
#[case::python_docstring(SpellingContract {
    value: ExtractSyntax::PythonDocstring,
    as_str_snapshot: SnapshotName("syntax_as_str__python_docstring"),
    display_snapshot: SnapshotName("syntax_display__python_docstring"),
    expected: "python_docstring",
})]
#[case::rust_doc_comment(SpellingContract {
    value: ExtractSyntax::RustDocComment,
    as_str_snapshot: SnapshotName("syntax_as_str__rust_doc_comment"),
    display_snapshot: SnapshotName("syntax_display__rust_doc_comment"),
    expected: "rust_doc_comment",
})]
fn syntax_spelling_and_display_match_the_documented_contract(
    #[case] contract: SpellingContract<ExtractSyntax>,
) {
    let SpellingContract {
        value: syntax,
        as_str_snapshot,
        display_snapshot,
        expected,
    } = contract;

    assert_eq!(
        syntax.as_str(),
        expected,
        "syntax {syntax:?} must spell as {expected:?}"
    );
    insta::assert_snapshot!(as_str_snapshot.0, syntax.as_str());

    assert_eq!(
        format!("{syntax}"),
        syntax.as_str(),
        "Display for syntax {syntax:?} must agree with its as_str spelling"
    );
    insta::assert_snapshot!(display_snapshot.0, format!("{syntax}"));
}

/// Pins both `as_str` and `Display` for every region-kind variant.
#[rstest]
#[case::document(SpellingContract {
    value: RegionKind::Document,
    as_str_snapshot: SnapshotName("region_kind_as_str__document"),
    display_snapshot: SnapshotName("region_kind_display__document"),
    expected: "document",
})]
#[case::python_docstring(SpellingContract {
    value: RegionKind::PythonDocstring,
    as_str_snapshot: SnapshotName("region_kind_as_str__python_docstring"),
    display_snapshot: SnapshotName("region_kind_display__python_docstring"),
    expected: "python_docstring",
})]
#[case::rust_doc_comment(SpellingContract {
    value: RegionKind::RustDocComment,
    as_str_snapshot: SnapshotName("region_kind_as_str__rust_doc_comment"),
    display_snapshot: SnapshotName("region_kind_display__rust_doc_comment"),
    expected: "rust_doc_comment",
})]
fn region_kind_spelling_and_display_match_the_documented_contract(
    #[case] contract: SpellingContract<RegionKind>,
) {
    let SpellingContract {
        value: kind,
        as_str_snapshot,
        display_snapshot,
        expected,
    } = contract;

    assert_eq!(
        kind.as_str(),
        expected,
        "region kind {kind:?} must spell as {expected:?}"
    );
    insta::assert_snapshot!(as_str_snapshot.0, kind.as_str());

    assert_eq!(
        format!("{kind}"),
        kind.as_str(),
        "Display for region kind {kind:?} must agree with its as_str spelling"
    );
    insta::assert_snapshot!(display_snapshot.0, format!("{kind}"));
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
    assert_eq!(
        RegionKind::try_from(input),
        Ok(expected),
        "documented spelling {input:?} must parse as {expected:?}"
    );
}

/// Every variant's spelling must parse back to the same variant.
#[rstest]
#[case(RegionKind::Document)]
#[case(RegionKind::PythonDocstring)]
#[case(RegionKind::RustDocComment)]
fn region_kind_as_str_round_trips_through_try_from(#[case] kind: RegionKind) {
    assert_eq!(
        RegionKind::try_from(kind.as_str()),
        Ok(kind),
        "region kind {kind:?} must round-trip through its as_str spelling"
    );
}

/// Every documented spelling must render back to itself through `as_str`.
#[rstest]
#[case("document")]
#[case("python_docstring")]
#[case("rust_doc_comment")]
fn region_kind_try_from_round_trips_through_as_str(#[case] spelling: &str) {
    let kind = RegionKind::try_from(spelling).expect("known RegionKind spelling should parse");
    assert_eq!(
        kind.as_str(),
        spelling,
        "region kind {kind:?} must render back as the documented spelling {spelling:?}"
    );
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
