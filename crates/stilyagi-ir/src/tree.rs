//! Structural tree, node, source-span, and node-flag types for the IR.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

/// A structural tree represented inside an IR document.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IrTree {
    /// Stable tree identifier.
    pub id: String,
    /// Tree family, such as `mdast`.
    pub family: String,
    /// Source syntax represented by this tree.
    pub syntax: String,
    /// Root node identifier.
    pub root: String,
}

/// A structural source node represented inside an IR document.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IrNode {
    /// Stable node identifier.
    pub id: String,
    /// Containing tree identifier.
    pub tree: String,
    /// Parser-specific node kind.
    pub kind: String,
    /// Parent node identifier, if any.
    pub parent: Option<String>,
    /// Child node identifiers.
    pub children: Vec<String>,
    /// Named child fields.
    pub fields: BTreeMap<String, String>,
    /// Parser-specific deterministic properties.
    pub props: BTreeMap<String, serde_json::Value>,
    /// Source span covered by this node.
    pub span: SourceSpan,
    /// Node flags used by parser families.
    pub flags: NodeFlags,
}

/// Half-open source span expressed in UTF-8 byte offsets.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct SourceSpan {
    /// Inclusive start byte offset.
    pub byte_start: usize,
    /// Exclusive end byte offset.
    pub byte_end: usize,
}

impl SourceSpan {
    /// Create a source span without line or column derivation.
    ///
    /// Returns `None` when `byte_start` is greater than `byte_end`.
    #[must_use]
    pub const fn new(byte_start: usize, byte_end: usize) -> Option<Self> {
        Self::try_new(byte_start, byte_end)
    }

    /// Create a source span without line or column derivation.
    ///
    /// Returns `None` when `byte_start` is greater than `byte_end`.
    #[must_use]
    pub const fn try_new(byte_start: usize, byte_end: usize) -> Option<Self> {
        if byte_start > byte_end {
            return None;
        }
        Some(Self {
            byte_start,
            byte_end,
        })
    }
}

/// Flags attached to structural nodes.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[expect(
    clippy::struct_excessive_bools,
    reason = "the IR flags mirror RFC 0001 and tree-sitter-style node flags"
)]
pub struct NodeFlags {
    /// Whether the parser considers this a named node.
    pub named: bool,
    /// Whether this node represents a parse error.
    pub error: bool,
    /// Whether this node represents missing syntax.
    pub missing: bool,
    /// Whether this node was generated rather than source-backed.
    pub synthetic: bool,
}

impl NodeFlags {
    /// Return the default flags for a source-backed named node.
    #[must_use]
    pub const fn named_source() -> Self {
        Self {
            named: true,
            error: false,
            missing: false,
            synthetic: false,
        }
    }
}
