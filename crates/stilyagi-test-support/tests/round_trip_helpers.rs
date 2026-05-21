//! Tests for internal golden IR and edit round-trip helpers.

use proptest::prelude::*;
use rstest::rstest;
use stilyagi_ir::ByteSpan;
use stilyagi_test_support::{
    RoundTripEdit, RoundTripEditError, SHARED_MARKDOWN_FIXTURE_PATH, apply_round_trip_edits,
    golden_markdown_ir_fixture, normalize_repository_path,
};

#[rstest]
fn golden_markdown_ir_fixture_serializes_the_shared_fixture() {
    let document = golden_markdown_ir_fixture(SHARED_MARKDOWN_FIXTURE_PATH)
        .unwrap_or_else(|error| panic!("expected shared Markdown golden IR: {error}"));

    insta::assert_snapshot!(document.to_canonical_json());
}

#[rstest]
fn round_trip_edits_apply_source_backed_replacements() {
    let result = apply_round_trip_edits(
        "alpha beta gamma",
        &[
            RoundTripEdit::source(0, 5, "ALPHA"),
            RoundTripEdit::source(11, 16, "GAMMA"),
        ],
    )
    .unwrap_or_else(|error| panic!("expected source edits to apply: {error}"));

    assert_eq!(result.before, "alpha beta gamma");
    assert_eq!(result.after, "ALPHA beta GAMMA");
    assert_eq!(result.applied_edits.len(), 2);
}

#[rstest]
fn round_trip_edits_accept_adjacent_ranges() {
    let result = apply_round_trip_edits(
        "abcdef",
        &[
            RoundTripEdit::source(0, 3, "ABC"),
            RoundTripEdit::source(3, 6, "DEF"),
        ],
    )
    .unwrap_or_else(|error| panic!("expected adjacent edits to apply: {error}"));

    assert_eq!(result.after, "ABCDEF");
}

#[rstest]
fn round_trip_edits_reject_synthetic_spans() {
    let error = apply_round_trip_edits(
        "source",
        &[RoundTripEdit::synthetic(
            "inserted separator",
            "replacement",
        )],
    )
    .unwrap_err_or_else("expected synthetic edit rejection");

    assert_eq!(
        error,
        RoundTripEditError::SyntheticSpan {
            text: "inserted separator".to_owned()
        },
    );
}

#[rstest]
fn round_trip_edits_reject_overlapping_non_identical_ranges() {
    let error = apply_round_trip_edits(
        "abcdef",
        &[
            RoundTripEdit::source(1, 4, "BCD"),
            RoundTripEdit::source(3, 5, "DE"),
        ],
    )
    .unwrap_err_or_else("expected overlapping edit rejection");

    assert_eq!(
        error,
        RoundTripEditError::OverlappingEdits {
            previous: ByteSpan::new(1, 4),
            current: ByteSpan::new(3, 5),
        },
    );
}

#[rstest]
fn round_trip_edits_reject_start_after_end_spans() {
    let error = apply_round_trip_edits("abcdef", &[RoundTripEdit::source(4, 1, "x")])
        .unwrap_err_or_else("expected invalid edit span rejection");

    assert_eq!(
        error,
        RoundTripEditError::InvalidSpan {
            span: ByteSpan::new(4, 1),
            source_len: 6,
        },
    );
}

#[rstest]
fn round_trip_edits_reject_spans_past_source_end() {
    let error = apply_round_trip_edits("abcdef", &[RoundTripEdit::source(2, 9, "x")])
        .unwrap_err_or_else("expected invalid edit span rejection");

    assert_eq!(
        error,
        RoundTripEditError::InvalidSpan {
            span: ByteSpan::new(2, 9),
            source_len: 6,
        },
    );
}

#[rstest]
fn round_trip_edits_reject_non_utf8_start_boundaries() {
    let error = apply_round_trip_edits("é", &[RoundTripEdit::source(1, 2, "e")])
        .unwrap_err_or_else("expected non-UTF-8 boundary rejection");

    assert_eq!(
        error,
        RoundTripEditError::NonUtf8Boundary {
            span: ByteSpan::new(1, 2),
        },
    );
}

#[rstest]
fn round_trip_edits_reject_non_utf8_end_boundaries() {
    let error = apply_round_trip_edits("éx", &[RoundTripEdit::source(0, 1, "e")])
        .unwrap_err_or_else("expected non-UTF-8 boundary rejection");

    assert_eq!(
        error,
        RoundTripEditError::NonUtf8Boundary {
            span: ByteSpan::new(0, 1),
        },
    );
}

#[rstest]
fn round_trip_edits_accept_empty_edit_sets_as_noops() {
    let result = apply_round_trip_edits("some text", &[])
        .unwrap_or_else(|error| panic!("expected empty edit set to apply: {error}"));

    assert_eq!(result.before, "some text");
    assert_eq!(result.after, "some text");
    assert!(result.applied_edits.is_empty());
}

#[rstest]
fn round_trip_edits_preserve_untouched_ranges() {
    let result = apply_round_trip_edits(
        "before middle after",
        &[RoundTripEdit::source(7, 13, "CENTER")],
    )
    .unwrap_or_else(|error| panic!("expected edit to apply: {error}"));

    assert_eq!(result.after, "before CENTER after");
}

#[rstest]
fn normalize_repository_path_uses_posix_separators() {
    assert_eq!(
        normalize_repository_path(r"tests\fixtures\corpus\markdown\valid\example.md"),
        "tests/fixtures/corpus/markdown/valid/example.md",
    );
}

#[rstest]
#[should_panic(expected = "snapshot paths must be repository-relative")]
fn normalize_repository_path_rejects_absolute_paths() {
    drop(normalize_repository_path("/tmp/example.md"));
}

#[rstest]
#[should_panic(expected = "snapshot paths must be repository-relative")]
fn normalize_repository_path_rejects_parent_traversal() {
    drop(normalize_repository_path("tests/../example.md"));
}

proptest! {
    #[test]
    fn single_edit_preserves_prefix_and_suffix(
        prefix in "[a-z]{0,16}",
        replaced in "[a-z]{0,16}",
        suffix in "[a-z]{0,16}",
        replacement in "[A-Z]{0,16}",
    ) {
        let source = format!("{prefix}{replaced}{suffix}");
        let start = prefix.len();
        let end = start + replaced.len();

        let result = apply_round_trip_edits(
            &source,
            &[RoundTripEdit::source(start, end, replacement.clone())],
        )
        .unwrap_or_else(|error| panic!("expected generated edit to apply: {error}"));

        prop_assert_eq!(result.after, format!("{prefix}{replacement}{suffix}"));
    }
}

trait UnwrapErrOrElse<T, E> {
    fn unwrap_err_or_else(self, message: &str) -> E;
}

impl<T, E> UnwrapErrOrElse<T, E> for Result<T, E> {
    fn unwrap_err_or_else(self, message: &str) -> E {
        match self {
            Ok(_) => panic!("{message}"),
            Err(error) => error,
        }
    }
}
