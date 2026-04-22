//! Placeholder crate for source extraction orchestration.

use stilyagi_ir::IrBoundary;
use stilyagi_markdown::MarkdownBoundary;
use stilyagi_tree_sitter::TreeSitterBoundary;

/// Marker type for the future extraction orchestration boundary.
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct ExtractBoundary {
    /// Placeholder for Markdown extraction support.
    markdown: MarkdownBoundary,
    /// Placeholder for tree-sitter extraction support.
    tree_sitter: TreeSitterBoundary,
    /// Placeholder for IR construction support.
    ir: IrBoundary,
}

impl ExtractBoundary {
    /// Return the placeholder Markdown extraction boundary.
    #[must_use]
    pub const fn markdown(&self) -> &MarkdownBoundary {
        &self.markdown
    }

    /// Return the placeholder tree-sitter extraction boundary.
    #[must_use]
    pub const fn tree_sitter(&self) -> &TreeSitterBoundary {
        &self.tree_sitter
    }

    /// Return the placeholder IR construction boundary.
    #[must_use]
    pub const fn ir(&self) -> &IrBoundary {
        &self.ir
    }
}

#[cfg(test)]
mod tests {
    use super::ExtractBoundary;
    use stilyagi_ir::IrBoundary;
    use stilyagi_markdown::MarkdownBoundary;
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
}
