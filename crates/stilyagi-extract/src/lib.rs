//! Placeholder crate for source extraction orchestration.

use stilyagi_ir::IrBoundary;
use stilyagi_markdown::MarkdownBoundary;
use stilyagi_tree_sitter::TreeSitterBoundary;

/// Marker type for the future extraction orchestration boundary.
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct ExtractBoundary {
    /// Placeholder for Markdown extraction support.
    pub markdown: MarkdownBoundary,
    /// Placeholder for tree-sitter extraction support.
    pub tree_sitter: TreeSitterBoundary,
    /// Placeholder for IR construction support.
    pub ir: IrBoundary,
}
