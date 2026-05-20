//! Minimal intermediate representation (IR) test contracts.

use std::fmt::Write as _;

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

impl ByteSpan {
    /// Create a byte span from an inclusive start and exclusive end.
    #[must_use]
    pub const fn new(start: usize, end: usize) -> Self {
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
    pub fn new(
        fixture: impl Into<String>,
        syntax: impl Into<String>,
        line_index: Vec<usize>,
        regions: Vec<GoldenRegion>,
        diagnostics: Vec<String>,
    ) -> Self {
        Self {
            fixture: fixture.into(),
            syntax: syntax.into(),
            line_index,
            regions,
            diagnostics,
        }
    }

    /// Serialize to stable, pretty JSON for snapshots and golden files.
    #[must_use]
    pub fn to_canonical_json(&self) -> String {
        let mut json = String::from("{\n");
        push_json_property(&mut json, 1, "fixture", &json_string(&self.fixture), true);
        push_json_property(&mut json, 1, "syntax", &json_string(&self.syntax), true);
        push_json_property(
            &mut json,
            1,
            "line_index",
            &usize_array_json(&self.line_index),
            true,
        );
        push_json_property(&mut json, 1, "regions", &regions_json(&self.regions), true);
        push_json_property(
            &mut json,
            1,
            "diagnostics",
            &string_array_json(&self.diagnostics),
            false,
        );
        json.push_str("}\n");
        json
    }
}

fn push_json_property(
    json: &mut String,
    indent: usize,
    name: &str,
    value: &str,
    has_trailing_comma: bool,
) {
    push_indent(json, indent);
    json.push('"');
    json.push_str(name);
    json.push_str("\": ");
    json.push_str(value);
    if has_trailing_comma {
        json.push(',');
    }
    json.push('\n');
}

fn push_indent(json: &mut String, indent: usize) {
    for _ in 0..indent {
        json.push_str("  ");
    }
}

fn usize_array_json(values: &[usize]) -> String {
    let items = values
        .iter()
        .map(usize::to_string)
        .collect::<Vec<_>>()
        .join(", ");
    format!("[{items}]")
}

fn string_array_json(values: &[String]) -> String {
    let items = values
        .iter()
        .map(|value| json_string(value))
        .collect::<Vec<_>>()
        .join(", ");
    format!("[{items}]")
}

fn regions_json(regions: &[GoldenRegion]) -> String {
    if regions.is_empty() {
        return "[]".to_owned();
    }

    let mut json = String::from("[\n");
    for (index, region) in regions.iter().enumerate() {
        push_indent(&mut json, 2);
        json.push_str("{\n");
        push_json_property(&mut json, 3, "kind", &json_string(&region.kind), true);
        push_json_property(&mut json, 3, "text", &json_string(&region.text), true);
        push_json_property(
            &mut json,
            3,
            "segments",
            &segments_json(&region.segments),
            false,
        );
        push_indent(&mut json, 2);
        json.push('}');
        if index + 1 != regions.len() {
            json.push(',');
        }
        json.push('\n');
    }
    push_indent(&mut json, 1);
    json.push(']');
    json
}

fn segments_json(segments: &[Segment]) -> String {
    if segments.is_empty() {
        return "[]".to_owned();
    }

    let mut json = String::from("[\n");
    for (index, segment) in segments.iter().enumerate() {
        push_indent(&mut json, 4);
        json.push_str("{\n");
        match segment {
            Segment::Source { span, text } => {
                push_json_property(&mut json, 5, "kind", "\"source\"", true);
                push_json_property(&mut json, 5, "start", &span.start.to_string(), true);
                push_json_property(&mut json, 5, "end", &span.end.to_string(), true);
                push_json_property(&mut json, 5, "text", &json_string(text), false);
            }
            Segment::Synthetic { text } => {
                push_json_property(&mut json, 5, "kind", "\"synthetic\"", true);
                push_json_property(&mut json, 5, "text", &json_string(text), false);
            }
        }
        push_indent(&mut json, 4);
        json.push('}');
        if index + 1 != segments.len() {
            json.push(',');
        }
        json.push('\n');
    }
    push_indent(&mut json, 3);
    json.push(']');
    json
}

fn json_string(value: &str) -> String {
    let mut escaped = String::with_capacity(value.len() + 2);
    escaped.push('"');
    for character in value.chars() {
        match character {
            '"' => escaped.push_str("\\\""),
            '\\' => escaped.push_str("\\\\"),
            '\n' => escaped.push_str("\\n"),
            '\r' => escaped.push_str("\\r"),
            '\t' => escaped.push_str("\\t"),
            control if control.is_control() => {
                write_json_control_escape(&mut escaped, control);
            }
            other => escaped.push(other),
        }
    }
    escaped.push('"');
    escaped
}

fn write_json_control_escape(escaped: &mut String, control: char) {
    assert!(
        write!(escaped, "\\u{:04x}", u32::from(control)).is_ok(),
        "writing to String cannot fail"
    );
}

/// Return the byte offsets for each line start plus the end-of-document offset.
#[must_use]
pub fn line_index_for(source: &str) -> Vec<usize> {
    let mut offsets = vec![0];
    for (offset, byte) in source.bytes().enumerate() {
        if byte == b'\n' {
            offsets.push(offset + 1);
        }
    }
    if offsets.last().copied() != Some(source.len()) {
        offsets.push(source.len());
    }
    offsets
}

#[cfg(test)]
mod tests {
    use super::{
        ByteSpan, GoldenDocument, GoldenRegion, IrBoundary, Segment, json_string, line_index_for,
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

    /// Keep canonical JSON stable enough for golden files.
    #[test]
    fn golden_document_serializes_as_canonical_json() {
        let document = GoldenDocument::new(
            "tests/fixtures/example.md",
            "markdown",
            vec![0, 10],
            vec![GoldenRegion::new(
                "document",
                "A \"quote\"\n",
                vec![
                    Segment::source(ByteSpan::new(0, 10), "A \"quote\"\n"),
                    Segment::synthetic(" "),
                ],
            )],
            Vec::new(),
        );

        insta::assert_snapshot!(document.to_canonical_json());
    }

    /// Keep JSON escaping explicit because the helper avoids a runtime JSON
    /// dependency in this scaffolding slice.
    #[test]
    fn json_string_escapes_control_characters() {
        assert_eq!(
            json_string("\"\\\n\r\t\u{0008}"),
            "\"\\\"\\\\\\n\\r\\t\\u0008\""
        );
    }

    /// Keep line-index calculation byte-oriented for Unicode source text.
    #[test]
    fn line_index_for_reports_byte_offsets_and_document_end() {
        assert_eq!(line_index_for("é\nx"), vec![0, 3, 4]);
    }
}
