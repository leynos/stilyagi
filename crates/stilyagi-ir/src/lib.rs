//! Intermediate representation (IR) domain types and shared helpers.
//!
//! The crate owns Stilyagi's stable, source-faithful IR vocabulary. Markdown
//! parsers, `PyO3` bridges, and Python models adapt to these types rather than
//! defining their own logical document contracts.

mod canonical_json;
mod source_identity;

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

pub use canonical_json::{content_hash_for, line_index_for};
pub use source_identity::SourceIdentity;

/// Current schema version for Stilyagi IR documents.
pub const SCHEMA_VERSION: &str = "1.0.0";

/// Marker type for the future IR crate boundary.
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct IrBoundary;

/// A complete IR document envelope for one source payload.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IrDocument {
    /// Semantic version of the IR schema.
    pub schema_version: String,
    /// Metadata about the source document.
    pub document: DocumentMetadata,
    /// Parsers and extractors that produced this payload.
    pub producers: Vec<ProducerMetadata>,
    /// UTF-8 byte offsets for each line start plus the document end.
    pub line_index: Vec<usize>,
    /// Structural trees represented in this document.
    pub trees: Vec<IrTree>,
    /// Shared node store for all trees.
    pub nodes: Vec<IrNode>,
    /// Extracted lintable prose regions.
    pub regions: Vec<IrRegion>,
    /// Source-level suppression directives discovered during extraction.
    pub suppressions: Vec<IrSuppression>,
    /// Non-fatal parse or extraction anomalies.
    pub errors: Vec<IrError>,
    /// Extensible deterministic metadata map.
    pub metadata: BTreeMap<String, serde_json::Value>,
}

impl IrDocument {
    /// Create an empty IR document envelope for a source payload.
    #[must_use]
    pub fn empty(
        document: DocumentMetadata,
        producers: Vec<ProducerMetadata>,
        source: &str,
    ) -> Self {
        Self {
            schema_version: SCHEMA_VERSION.to_owned(),
            document,
            producers,
            line_index: line_index_for(source),
            trees: Vec::new(),
            nodes: Vec::new(),
            regions: Vec::new(),
            suppressions: Vec::new(),
            errors: Vec::new(),
            metadata: BTreeMap::new(),
        }
    }

    /// Serialize this document as deterministic pretty JSON.
    ///
    /// # Errors
    ///
    /// Returns a serialization error if metadata contains a JSON value that
    /// cannot be emitted by `serde_json`.
    pub fn to_canonical_json(&self) -> Result<String, serde_json::Error> {
        let mut json = serde_json::to_string_pretty(self)?;
        json.push('\n');
        Ok(json)
    }
}

/// Metadata about the source document represented by an IR payload.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DocumentMetadata {
    /// Stable source URI when the caller provides one.
    pub uri: Option<String>,
    /// Repository-relative or display path when the caller provides one.
    pub path: Option<String>,
    /// Source syntax name, such as `markdown`.
    pub syntax: String,
    /// Optional dominant natural language, such as `en`.
    pub natural_language: Option<String>,
    /// Source encoding, currently `utf-8`.
    pub encoding: String,
    /// Stable content hash, prefixed with the hash algorithm.
    pub content_hash: String,
}

impl DocumentMetadata {
    /// Create document metadata for the supplied syntax and source text.
    #[must_use]
    pub fn new(
        syntax: impl Into<String>,
        path: Option<String>,
        uri: Option<String>,
        source: &str,
    ) -> Self {
        Self {
            uri,
            path,
            syntax: syntax.into(),
            natural_language: None,
            encoding: "utf-8".to_owned(),
            content_hash: content_hash_for(source),
        }
    }

    /// Create Markdown document metadata for the supplied source text.
    #[must_use]
    pub fn markdown(identity: SourceIdentity, source: &str) -> Self {
        Self::new("markdown", identity.path, identity.uri, source)
    }
}

/// Metadata about a parser or extractor that produced IR data.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProducerMetadata {
    /// Producer role or syntax family.
    pub kind: String,
    /// Human-readable producer name.
    pub name: String,
    /// Producer version.
    pub version: String,
    /// Relevant deterministic parse or extraction options.
    pub options: BTreeMap<String, serde_json::Value>,
}

/// Document metadata and producer list used to build an IR envelope.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct IrBuildContext {
    /// Metadata for the source document represented by this envelope.
    pub document: DocumentMetadata,
    /// Producers that contribute to this envelope.
    pub producers: Vec<ProducerMetadata>,
}

impl IrBuildContext {
    /// Create an IR build context from document and producer metadata.
    #[must_use]
    pub const fn new(document: DocumentMetadata, producers: Vec<ProducerMetadata>) -> Self {
        Self {
            document,
            producers,
        }
    }
}

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
    /// # Panics
    ///
    /// Panics when `byte_start` is greater than `byte_end`.
    #[must_use]
    pub const fn new(byte_start: usize, byte_end: usize) -> Self {
        assert!(byte_start <= byte_end);
        Self {
            byte_start,
            byte_end,
        }
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

/// A lintable prose region extracted from source structure.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IrRegion {
    /// Stable region identifier.
    pub id: String,
    /// Stable region kind.
    pub kind: String,
    /// Extensible analysis scope tags.
    pub scope: Vec<String>,
    /// Source syntax that produced this region.
    pub syntax: String,
    /// Optional prose locale for this region.
    pub natural_language: Option<String>,
    /// Flattened lint surface.
    pub text: String,
    /// Mappings from region text back to source bytes or synthetic text.
    pub segments: Vec<IrSegment>,
    /// Structural nodes that materially contributed to this region.
    pub origin_nodes: Vec<String>,
    /// Owning code entity for docstrings and comments.
    pub owner: Option<IrOwner>,
    /// Deterministic region attributes.
    pub attrs: BTreeMap<String, serde_json::Value>,
    /// Parent region identifier, if any.
    pub parent_region: Option<String>,
}

impl IrRegion {
    /// Reconstruct region text from its segment payloads.
    #[must_use]
    pub fn reconstructed_text(&self) -> String {
        let mut text = String::new();
        for segment in &self.segments {
            text.push_str(segment.text());
        }
        text
    }

    /// Return whether the segment payloads exactly reconstruct this region.
    #[must_use]
    pub fn segments_reconstruct_text(&self) -> bool {
        self.reconstructed_text() == self.text
    }
}

/// One mapping from flattened region text to source bytes or synthetic text.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IrSegment {
    /// Inclusive start offset in region text.
    pub text_start: usize,
    /// Exclusive end offset in region text.
    pub text_end: usize,
    /// Source bytes that produced this segment, when source-backed.
    pub source: Option<SourceSpan>,
    /// Synthetic insertion reason, when not source-backed.
    pub synthetic: Option<String>,
    /// Structural node that produced this segment, when known.
    pub node: Option<String>,
    /// Segment text used for invariant checking and round-trip tests.
    pub text: String,
}

/// Origin metadata for an IR segment.
pub enum SegmentOrigin {
    /// Segment text copied from a source span and structural node.
    Source {
        /// Source byte span backing this segment.
        span: SourceSpan,
        /// Structural node identifier that produced this segment.
        node: String,
    },
    /// Segment text synthesized during extraction.
    Synthetic {
        /// Stable reason for the synthetic insertion.
        reason: String,
    },
}

impl IrSegment {
    /// Build an IR segment from flattened text and its origin.
    #[must_use]
    pub fn new(text_start: usize, segment_text: impl Into<String>, origin: SegmentOrigin) -> Self {
        let text = segment_text.into();
        let (source, synthetic, node) = match origin {
            SegmentOrigin::Source { span, node } => (Some(span), None, Some(node)),
            SegmentOrigin::Synthetic { reason } => (None, Some(reason), None),
        };
        Self {
            text_start,
            text_end: text_start + text.len(),
            source,
            synthetic,
            node,
            text,
        }
    }

    /// Return the text represented by this segment.
    #[must_use]
    pub fn text(&self) -> &str {
        &self.text
    }
}

/// Owning code entity for a prose region.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IrOwner {
    /// Owner kind, such as `module`, `class`, `function`, or `item`.
    pub kind: String,
    /// Source-level owner name, if available.
    pub name: Option<String>,
    /// Source-level qualified owner name, if available.
    pub qualname: Option<String>,
}

/// Source-level suppression directive discovered during extraction.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IrSuppression {
    /// Stable suppression identifier.
    pub id: String,
    /// Source span covered by the directive.
    pub span: SourceSpan,
    /// Suppressed rule names or families.
    pub rules: Vec<String>,
    /// Optional directive reason.
    pub reason: Option<String>,
}

/// Non-fatal parser or extractor anomaly.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IrError {
    /// Stable error code.
    pub code: String,
    /// Human-readable error message.
    pub message: String,
    /// Source span associated with the error, if known.
    pub span: Option<SourceSpan>,
}

#[cfg(test)]
mod tests;
