//! Placeholder crate for tree-sitter-backed source extraction.

/// Marker type for the future tree-sitter extraction boundary.
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct TreeSitterBoundary;

#[cfg(test)]
mod tests {
    use super::TreeSitterBoundary;

    /// Keep the marker type default stable and comparable.
    #[test]
    #[expect(
        clippy::default_constructed_unit_structs,
        reason = "this test explicitly exercises the Default implementation"
    )]
    fn tree_sitter_boundary_default_matches_the_marker_value() {
        assert_eq!(TreeSitterBoundary::default(), TreeSitterBoundary);
    }

    /// Keep the marker type clone semantics trivial.
    #[test]
    fn tree_sitter_boundary_clone_matches_the_original() {
        let boundary = TreeSitterBoundary;

        assert_eq!(boundary.clone(), boundary);
    }

    /// Keep the marker type debug output identifiable in failures.
    #[test]
    fn tree_sitter_boundary_debug_output_mentions_the_type_name() {
        assert!(format!("{TreeSitterBoundary:?}").contains("TreeSitterBoundary"));
    }

    /// Keep the marker type copy semantics available to callers.
    #[test]
    fn tree_sitter_boundary_is_copy() {
        let original = TreeSitterBoundary;
        let first = original;
        let second = original;

        assert_eq!(first, second);
        assert_eq!(first, original);
    }
}
