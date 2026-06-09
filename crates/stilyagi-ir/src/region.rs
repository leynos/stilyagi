//! Lintable prose region, segment, and owner types for the IR.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::SourceSpan;

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
        let mut expected_start = 0;
        let mut reconstructed = String::new();
        for segment in &self.segments {
            let Some(expected_end) = segment.text_start.checked_add(segment.text.len()) else {
                return false;
            };
            if segment.text_start != expected_start || segment.text_end != expected_end {
                return false;
            }
            reconstructed.push_str(segment.text());
            expected_start = segment.text_end;
        }
        expected_start == self.text.len() && reconstructed == self.text
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
