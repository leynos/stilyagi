//! Domain newtypes for Python tree-sitter extraction internals.

use std::fmt;

/// Stable IR node identifier used while building the Python docstring tree.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(super) struct NodeId(pub String);

impl NodeId {
    /// Return the identifier as a borrowed string slice.
    pub(super) fn as_str(&self) -> &str {
        self.0.as_str()
    }
}

impl fmt::Display for NodeId {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

impl From<NodeId> for String {
    fn from(node_id: NodeId) -> Self {
        node_id.0
    }
}

/// tree-sitter node kind discriminator used by Python extraction helpers.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(super) struct NodeKind(pub &'static str);

impl NodeKind {
    /// Return the tree-sitter kind spelling.
    pub(super) const fn as_str(self) -> &'static str {
        self.0
    }
}
