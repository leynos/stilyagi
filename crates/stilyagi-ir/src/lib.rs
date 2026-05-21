//! Test-only intermediate representation (IR) contracts for golden fixtures.
//!
//! This crate defines lightweight byte-span, segment, region, and document
//! shapes used by the internal snapshot tests. It keeps the data model flat so
//! `stilyagi-test-support` can build golden documents cheaply, while
//! `canonical_json` owns the stable textual form and the shared
//! [`line_index_for`] helper used during fixture construction.

mod canonical_json;

pub use canonical_json::line_index_for;

/// Marker type for the future IR crate boundary.
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct IrBoundary;

/// Half-open byte span into a source document.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ByteSpan {
    /// Inclusive start byte offset.
    pub start: usize,
    /// Exclusive end byte offset.
    pub end: usize,
}

/// Error returned when a byte span range is malformed.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SpanError {
    /// Inclusive start byte offset.
    pub start: usize,
    /// Exclusive end byte offset.
    pub end: usize,
}

impl ByteSpan {
    /// Create a byte span from an inclusive start and exclusive end.
    ///
    /// # Errors
    ///
    /// Returns an error when `start` is greater than `end`.
    pub const fn new(start: usize, end: usize) -> Result<Self, SpanError> {
        if start > end {
            return Err(SpanError { start, end });
        }
        Ok(Self { start, end })
    }

    /// Create a byte span without validating the range.
    ///
    /// This is only for tests and validation paths that need to carry malformed
    /// spans as error payloads.
    #[must_use]
    pub const fn new_unchecked(start: usize, end: usize) -> Self {
        Self { start, end }
    }
}

/// One mapping from flattened text back to source or synthetic text.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Segment {
    /// Text copied from an editable byte range in the source.
    Source {
        /// Span in the source document.
        span: ByteSpan,
        /// Text copied from that span.
        text: String,
    },
    /// Text inserted for analysis that has no editable source span.
    Synthetic {
        /// Synthetic text.
        text: String,
    },
}

impl Segment {
    /// Create a source-backed segment.
    #[must_use]
    pub fn source(span: ByteSpan, text: impl Into<String>) -> Self {
        Self::Source {
            span,
            text: text.into(),
        }
    }

    /// Create a synthetic segment.
    #[must_use]
    pub fn synthetic(text: impl Into<String>) -> Self {
        Self::Synthetic { text: text.into() }
    }
}

/// Minimal golden IR region used by internal contract tests.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GoldenRegion {
    /// Stable region kind name.
    pub kind: String,
    /// Flattened region text.
    pub text: String,
    /// Region text mapping back to source or synthetic text.
    pub segments: Vec<Segment>,
}

impl GoldenRegion {
    /// Create a golden IR region.
    #[must_use]
    pub fn new(kind: impl Into<String>, text: impl Into<String>, segments: Vec<Segment>) -> Self {
        Self {
            kind: kind.into(),
            text: text.into(),
            segments,
        }
    }
}

/// Analysis content of a [`GoldenDocument`]: line structure, regions, and diagnostics.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct GoldenBody {
    /// Byte offsets for each line start, including the end-of-document offset.
    pub line_index: Vec<usize>,
    /// Extracted regions.
    pub regions: Vec<GoldenRegion>,
    /// Diagnostic records for this early helper surface.
    pub diagnostics: Vec<String>,
}

/// Minimal golden IR document used by internal contract tests.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GoldenDocument {
    /// Repository-relative fixture path.
    pub fixture: String,
    /// Stable syntax name.
    pub syntax: String,
    /// Byte offsets for each line start, including the end-of-document offset.
    pub line_index: Vec<usize>,
    /// Extracted regions.
    pub regions: Vec<GoldenRegion>,
    /// Diagnostic records for this early helper surface.
    pub diagnostics: Vec<String>,
}

impl GoldenDocument {
    /// Create a golden IR document.
    #[must_use]
    pub fn new(fixture: impl Into<String>, syntax: impl Into<String>, body: GoldenBody) -> Self {
        Self {
            fixture: fixture.into(),
            syntax: syntax.into(),
            line_index: body.line_index,
            regions: body.regions,
            diagnostics: body.diagnostics,
        }
    }

    /// Serialize to stable, pretty JSON for snapshots and golden files.
    #[must_use]
    pub fn to_canonical_json(&self) -> String {
        canonical_json::document_to_json(self)
    }
}

#[cfg(test)]
mod tests {
    use super::{
        ByteSpan, GoldenBody, GoldenDocument, GoldenRegion, IrBoundary, Segment, SpanError,
    };

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

    /// Keep byte span construction checked for ordered ranges.
    #[test]
    fn byte_span_new_accepts_ordered_ranges() {
        assert_eq!(ByteSpan::new(3, 8), Ok(ByteSpan { start: 3, end: 8 }),);
    }

    /// Keep byte span construction from accepting inverted ranges.
    #[test]
    fn byte_span_new_rejects_inverted_ranges() {
        assert_eq!(ByteSpan::new(8, 3), Err(SpanError { start: 8, end: 3 }));
    }

    /// Keep canonical JSON stable enough for golden files.
    #[test]
    fn golden_document_serializes_as_canonical_json() {
        let document = GoldenDocument::new(
            "tests/fixtures/example.md",
            "markdown",
            GoldenBody {
                line_index: vec![0, 10],
                regions: vec![GoldenRegion::new(
                    "document",
                    "A \"quote\"\n",
                    vec![
                        Segment::source(ByteSpan::new_unchecked(0, 10), "A \"quote\"\n"),
                        Segment::synthetic(" "),
                    ],
                )],
                diagnostics: Vec::new(),
            },
        );

        insta::assert_snapshot!(document.to_canonical_json());
    }
}
