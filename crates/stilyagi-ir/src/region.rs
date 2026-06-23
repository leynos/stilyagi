//! Lintable prose region, segment, and owner types for the IR.

use std::{collections::BTreeMap, fmt};

use serde::{Deserialize, Serialize};

use crate::SourceSpan;

/// Stable vocabulary for lintable prose region kinds.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum RegionKind {
    /// Markdown heading text.
    Heading,
    /// Markdown paragraph text.
    Paragraph,
    /// Markdown list item structural region.
    ListItem,
    /// Markdown blockquote structural region.
    Blockquote,
    /// Markdown table cell text.
    TableCell,
    /// Markdown YAML or TOML frontmatter block.
    Frontmatter,
    /// Reserved field-level frontmatter region.
    FrontmatterField,
    /// Markdown image alternative text.
    ImageAlt,
    /// Markdown link title text.
    LinkTitle,
    /// Reserved Python docstring region.
    PythonDocstring,
    /// Reserved Rust documentation comment region.
    RustDocComment,
}

impl RegionKind {
    /// All stable v1 IR region kinds, in canonical order.
    pub const ALL: &'static [Self] = &[
        Self::Heading,
        Self::Paragraph,
        Self::ListItem,
        Self::Blockquote,
        Self::TableCell,
        Self::Frontmatter,
        Self::FrontmatterField,
        Self::ImageAlt,
        Self::LinkTitle,
        Self::PythonDocstring,
        Self::RustDocComment,
    ];

    /// Return the stable serialized spelling for this region kind.
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Heading => "heading",
            Self::Paragraph => "paragraph",
            Self::ListItem => "list_item",
            Self::Blockquote => "blockquote",
            Self::TableCell => "table_cell",
            Self::Frontmatter => "frontmatter",
            Self::FrontmatterField => "frontmatter_field",
            Self::ImageAlt => "image_alt",
            Self::LinkTitle => "link_title",
            Self::PythonDocstring => "python_docstring",
            Self::RustDocComment => "rust_doc_comment",
        }
    }
}

impl fmt::Display for RegionKind {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

/// Error returned when a string is not a known IR region kind.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InvalidRegionKind {
    value: String,
}

impl InvalidRegionKind {
    /// Return the rejected region kind spelling.
    #[must_use]
    pub fn value(&self) -> &str {
        &self.value
    }
}

impl fmt::Display for InvalidRegionKind {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "unknown IR region kind '{}'", self.value)
    }
}

impl std::error::Error for InvalidRegionKind {}

impl TryFrom<&str> for RegionKind {
    type Error = InvalidRegionKind;

    fn try_from(value: &str) -> Result<Self, Self::Error> {
        match value {
            "heading" => Ok(Self::Heading),
            "paragraph" => Ok(Self::Paragraph),
            "list_item" => Ok(Self::ListItem),
            "blockquote" => Ok(Self::Blockquote),
            "table_cell" => Ok(Self::TableCell),
            "frontmatter" => Ok(Self::Frontmatter),
            "frontmatter_field" => Ok(Self::FrontmatterField),
            "image_alt" => Ok(Self::ImageAlt),
            "link_title" => Ok(Self::LinkTitle),
            "python_docstring" => Ok(Self::PythonDocstring),
            "rust_doc_comment" => Ok(Self::RustDocComment),
            _ => Err(InvalidRegionKind {
                value: value.to_owned(),
            }),
        }
    }
}

/// Stable reasons for text synthesized during IR extraction.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum SyntheticReason {
    /// A Markdown soft line break represented as one lint-surface space.
    SoftbreakSpace,
    /// A Markdown hard line break represented as one lint-surface space.
    HardbreakSpace,
    /// Decoded text that cannot be byte-backed by one source slice.
    DecodedText,
}

impl SyntheticReason {
    /// All stable synthetic segment reasons, in canonical order.
    pub const ALL: &'static [Self] = &[
        Self::SoftbreakSpace,
        Self::HardbreakSpace,
        Self::DecodedText,
    ];

    /// Return the stable serialized spelling for this synthetic reason.
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::SoftbreakSpace => "softbreak_space",
            Self::HardbreakSpace => "hardbreak_space",
            Self::DecodedText => "decoded_text",
        }
    }
}

impl fmt::Display for SyntheticReason {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
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
        reason: SyntheticReason,
    },
}

impl IrSegment {
    /// Build an IR segment from flattened text and its origin.
    ///
    /// # Panics
    ///
    /// Panics when `text_start + segment_text.len()` would overflow `usize`.
    #[must_use]
    pub fn new(text_start: usize, segment_text: impl Into<String>, origin: SegmentOrigin) -> Self {
        let text = segment_text.into();
        let Some(text_end) = text_start.checked_add(text.len()) else {
            panic!("segment text range overflowed usize");
        };
        let (source, synthetic, node) = match origin {
            SegmentOrigin::Source { span, node } => (Some(span), None, Some(node)),
            SegmentOrigin::Synthetic { reason } => (None, Some(reason.as_str().to_owned()), None),
        };
        Self {
            text_start,
            text_end,
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
