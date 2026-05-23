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
            previous: ByteSpan::new_unchecked(1, 4),
            current: ByteSpan::new_unchecked(3, 5),
        },
    );
}

#[rstest]
#[case("abcdef", 4, 1, ByteSpan::new_unchecked(4, 1), 6)]
#[case("abcdef", 2, 9, ByteSpan::new_unchecked(2, 9), 6)]
fn round_trip_edits_reject_invalid_spans(
    #[case] source: &str,
    #[case] start: usize,
    #[case] end: usize,
    #[case] expected_span: ByteSpan,
    #[case] expected_source_len: usize,
) {
    let error = apply_round_trip_edits(source, &[RoundTripEdit::source(start, end, "x")])
        .unwrap_err_or_else("expected invalid edit span rejection");

    assert_eq!(
        error,
        RoundTripEditError::InvalidSpan {
            span: expected_span,
            source_len: expected_source_len,
        },
    );
}

#[rstest]
#[case("é", 1, 2, ByteSpan::new_unchecked(1, 2))]
#[case("éx", 0, 1, ByteSpan::new_unchecked(0, 1))]
fn round_trip_edits_reject_non_utf8_boundaries(
    #[case] source: &str,
    #[case] start: usize,
    #[case] end: usize,
    #[case] expected_span: ByteSpan,
) {
    let error = apply_round_trip_edits(source, &[RoundTripEdit::source(start, end, "e")])
        .unwrap_err_or_else("expected non-UTF-8 boundary rejection");

    assert_eq!(
        error,
        RoundTripEditError::NonUtf8Boundary {
            span: expected_span,
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

    #[test]
    fn multi_edit_ordering_preserves_unicode_chunks(
        chunk_replacements in prop::collection::vec((unicode_chunk(), unicode_chunk()), 2..6),
    ) {
        let edit_count = chunk_replacements.len();
        let source = chunk_replacements
            .iter()
            .map(|(chunk, _replacement)| chunk.as_str())
            .collect::<String>();
        let mut start = 0;
        let mut edits = Vec::with_capacity(edit_count);
        for (chunk, replacement) in &chunk_replacements {
            let end = start + chunk.len();
            edits.push(RoundTripEdit::source(start, end, replacement.clone()));
            start = end;
        }
        edits.reverse();

        let result = apply_round_trip_edits(&source, &edits)
            .unwrap_or_else(|error| panic!("expected generated edits to apply: {error}"));

        let expected = chunk_replacements
            .iter()
            .map(|(_chunk, replacement)| replacement.as_str())
            .collect::<String>();
        prop_assert_eq!(result.after, expected);
        prop_assert_eq!(result.applied_edits.len(), edit_count);
    }

    #[test]
    fn overlapping_generated_edits_are_rejected(
        prefix in unicode_chunk(),
        left in unicode_chunk(),
        shared in unicode_chunk(),
        right in unicode_chunk(),
        suffix in unicode_chunk(),
    ) {
        let source = format!("{prefix}{left}{shared}{right}{suffix}");
        let first = ByteSpan::new_unchecked(
            prefix.len(),
            prefix.len() + left.len() + shared.len(),
        );
        let second = ByteSpan::new_unchecked(
            prefix.len() + left.len(),
            prefix.len() + left.len() + shared.len() + right.len(),
        );

        let error = apply_round_trip_edits(
            &source,
            &[
                RoundTripEdit::source(second.start, second.end, "SECOND"),
                RoundTripEdit::source(first.start, first.end, "FIRST"),
            ],
        )
        .unwrap_err_or_else("expected generated overlapping edits to be rejected");

        prop_assert_eq!(
            error,
            RoundTripEditError::OverlappingEdits {
                previous: first,
                current: second,
            },
        );
    }

    #[test]
    fn generated_non_utf8_boundaries_are_rejected(
        prefix in unicode_chunk(),
        suffix in unicode_chunk(),
    ) {
        let source = format!("{prefix}é{suffix}");
        let start = prefix.len() + 1;
        let span = ByteSpan::new_unchecked(start, start + 1);

        let error = apply_round_trip_edits(
            &source,
            &[RoundTripEdit::source(span.start, span.end, "e")],
        )
        .unwrap_err_or_else("expected generated non-UTF-8 boundary to be rejected");

        prop_assert_eq!(error, RoundTripEditError::NonUtf8Boundary { span });
    }
}

fn unicode_chunk() -> impl Strategy<Value = String> {
    prop::collection::vec(
        prop_oneof![Just("é".to_owned()), Just("ß".to_owned()), "[a-z]{1,4}",],
        1..8,
    )
    .prop_map(|pieces| pieces.concat())
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
