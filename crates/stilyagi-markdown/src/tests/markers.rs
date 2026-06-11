//! Marker-type tests for the Markdown extraction boundary.

use crate::MarkdownBoundary;

/// Keep the marker type default stable and comparable.
#[test]
#[expect(
    clippy::default_constructed_unit_structs,
    reason = "this test explicitly exercises the Default implementation"
)]
fn markdown_boundary_default_matches_the_marker_value() {
    assert_eq!(MarkdownBoundary::default(), MarkdownBoundary);
}

/// Keep the marker type clone semantics trivial.
#[test]
fn markdown_boundary_clone_matches_the_original() {
    let boundary = MarkdownBoundary;

    assert_eq!(boundary.clone(), boundary);
}

/// Keep the marker type debug output identifiable in failures.
#[test]
fn markdown_boundary_debug_output_mentions_the_type_name() {
    assert!(format!("{MarkdownBoundary:?}").contains("MarkdownBoundary"));
}

/// Keep the marker type copy semantics available to callers.
#[test]
fn markdown_boundary_is_copy() {
    let original = MarkdownBoundary;
    let first = original;
    let second = original;

    assert_eq!(first, second);
    assert_eq!(first, original);
}
