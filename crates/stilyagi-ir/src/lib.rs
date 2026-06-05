//! Intermediate representation (IR) domain types and shared helpers.
//!
//! The crate owns Stilyagi's stable, source-faithful IR vocabulary. Markdown
//! parsers, `PyO3` bridges, and Python models adapt to these types rather than
//! defining their own logical document contracts.

mod canonical_json;

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

pub use canonical_json::{content_hash_for, line_index_for};

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
    /// Stable source URI, or a synthetic URI for stdin.
    pub uri: String,
    /// Repository-relative or display path.
    pub path: String,
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
    /// Create Markdown document metadata for the supplied source text.
    #[must_use]
    pub fn markdown(path: impl Into<String>, uri: impl Into<String>, source: &str) -> Self {
        Self {
            uri: uri.into(),
            path: path.into(),
            syntax: "markdown".to_owned(),
            natural_language: Some("en".to_owned()),
            encoding: "utf-8".to_owned(),
            content_hash: content_hash_for(source),
        }
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
    #[must_use]
    pub const fn new(byte_start: usize, byte_end: usize) -> Self {
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

enum SegmentOrigin {
    Source { span: SourceSpan, node: String },
    Synthetic { reason: String },
}

impl IrSegment {
    fn new(text_start: usize, segment_text: impl Into<String>, origin: SegmentOrigin) -> Self {
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

    /// Create a source-backed segment.
    #[must_use]
    pub fn source(
        text_start: usize,
        segment_text: impl Into<String>,
        source: SourceSpan,
        node: impl Into<String>,
    ) -> Self {
        Self::new(
            text_start,
            segment_text,
            SegmentOrigin::Source {
                span: source,
                node: node.into(),
            },
        )
    }

    /// Create a synthetic segment.
    #[must_use]
    pub fn synthetic(
        text_start: usize,
        segment_text: impl Into<String>,
        reason: impl Into<String>,
    ) -> Self {
        Self::new(
            text_start,
            segment_text,
            SegmentOrigin::Synthetic {
                reason: reason.into(),
            },
        )
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
mod tests {
    use std::collections::BTreeMap;

    use proptest::prelude::*;
    use rstest::rstest;

    use super::{DocumentMetadata, IrBoundary, IrDocument, IrRegion, IrSegment, SourceSpan};

    /// Keep the marker type default stable and comparable.
    #[test]
    #[expect(
        clippy::default_constructed_unit_structs,
        reason = "this test explicitly exercises the Default implementation"
    )]
    fn ir_boundary_default_matches_the_marker_value() {
        assert_eq!(IrBoundary::default(), IrBoundary);
    }

    /// Keep the marker type clone semantics trivial.
    #[test]
    fn ir_boundary_clone_matches_the_original() {
        let boundary = IrBoundary;

        assert_eq!(boundary.clone(), boundary);
    }

    /// Keep the marker type debug output identifiable in failures.
    #[test]
    fn ir_boundary_debug_output_mentions_the_type_name() {
        assert!(format!("{IrBoundary:?}").contains("IrBoundary"));
    }

    /// Keep the marker type copy semantics available to callers.
    #[test]
    fn ir_boundary_is_copy() {
        let original = IrBoundary;
        let first = original;
        let second = original;

        assert_eq!(first, second);
        assert_eq!(first, original);
    }

    #[rstest]
    fn empty_document_uses_line_index_and_content_hash() {
        let source = "# Title\nBody";
        let document = IrDocument::empty(
            DocumentMetadata::markdown("docs/example.md", "file:///repo/docs/example.md", source),
            Vec::new(),
            source,
        );

        assert_eq!(document.schema_version, "1.0.0");
        assert_eq!(document.line_index, vec![0, 8, 12]);
        assert!(document.document.content_hash.starts_with("sha256:"));
    }

    #[rstest]
    fn canonical_json_orders_metadata_deterministically() {
        let mut metadata = BTreeMap::new();
        metadata.insert("zeta".to_owned(), serde_json::json!(true));
        metadata.insert("alpha".to_owned(), serde_json::json!(1));
        let mut document = IrDocument::empty(
            DocumentMetadata::markdown("docs/example.md", "file:///repo/docs/example.md", ""),
            Vec::new(),
            "",
        );
        document.metadata = metadata;

        let json = document.to_canonical_json();

        assert!(matches!(
            json,
            Ok(ref value) if value.contains("\"alpha\"") && value.contains("\"zeta\"")
        ));
        if let Ok(value) = json {
            let alpha_position = value.find("\"alpha\"");
            let zeta_position = value.find("\"zeta\"");
            assert!(matches!(
                (alpha_position, zeta_position),
                (Some(alpha), Some(zeta)) if alpha < zeta
            ));
        }
    }

    #[derive(Debug, Clone)]
    enum SegmentSpec {
        Source(String),
        Synthetic(&'static str),
    }

    fn segment_spec() -> impl Strategy<Value = SegmentSpec> {
        prop_oneof![
            "[a-z]{1,8}".prop_map(SegmentSpec::Source),
            prop_oneof![Just("softbreak_space"), Just("hardbreak_space")]
                .prop_map(SegmentSpec::Synthetic),
        ]
    }

    proptest! {
        #[test]
        fn generated_segments_preserve_layout_and_source_invariants(
            specs in prop::collection::vec(segment_spec(), 1..12),
        ) {
            let (region, source) = region_from_specs(&specs);

            prop_assert!(region.segments_reconstruct_text());
            prop_assert!(segments_are_contiguous(&region));
            prop_assert!(source_backed_segments_match_source(&region, &source));
            prop_assert!(synthetic_segments_use_known_reasons(&region));
        }
    }

    fn region_from_specs(specs: &[SegmentSpec]) -> (IrRegion, String) {
        let mut source = String::new();
        let mut region_text = String::new();
        let mut segments = Vec::new();
        for spec in specs {
            match spec {
                SegmentSpec::Source(text) => {
                    let text_start = region_text.len();
                    let source_start = source.len();
                    source.push_str(text);
                    region_text.push_str(text);
                    segments.push(IrSegment::source(
                        text_start,
                        text.clone(),
                        SourceSpan::new(source_start, source.len()),
                        "n1",
                    ));
                }
                SegmentSpec::Synthetic(reason) => {
                    let text_start = region_text.len();
                    region_text.push(' ');
                    segments.push(IrSegment::synthetic(text_start, " ", *reason));
                }
            }
        }
        (
            IrRegion {
                id: "r1".to_owned(),
                kind: "paragraph".to_owned(),
                scope: vec!["markdown".to_owned(), "paragraph".to_owned()],
                syntax: "markdown".to_owned(),
                natural_language: Some("en".to_owned()),
                text: region_text,
                segments,
                origin_nodes: vec!["n1".to_owned()],
                owner: None,
                attrs: BTreeMap::new(),
                parent_region: None,
            },
            source,
        )
    }

    fn segments_are_contiguous(region: &IrRegion) -> bool {
        let mut expected_start = 0;
        for segment in &region.segments {
            if segment.text_start != expected_start || segment.text_end < segment.text_start {
                return false;
            }
            expected_start = segment.text_end;
        }
        expected_start == region.text.len()
    }

    fn source_backed_segments_match_source(region: &IrRegion, source: &str) -> bool {
        region.segments.iter().all(|segment| {
            segment.source.map_or_else(
                || segment.synthetic.is_some() && segment.node.is_none(),
                |span| {
                    segment.synthetic.is_none()
                        && segment.node.as_deref() == Some("n1")
                        && source.get(span.byte_start..span.byte_end) == Some(segment.text.as_str())
                },
            )
        })
    }

    fn synthetic_segments_use_known_reasons(region: &IrRegion) -> bool {
        region.segments.iter().all(|segment| {
            segment
                .synthetic
                .as_deref()
                .is_none_or(|reason| matches!(reason, "softbreak_space" | "hardbreak_space"))
        })
    }
}
