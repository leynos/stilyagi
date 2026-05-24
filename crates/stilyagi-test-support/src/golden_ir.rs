//! Test-only golden IR DTOs and canonical JSON formatting.
//!
//! These shapes are public from the dev-only `stilyagi-test-support` crate so
//! integration tests can assert error payloads and snapshots without exposing
//! the helper contract from `stilyagi-ir`.

use std::fmt::Write as _;

/// Half-open byte span into a source document.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ByteSpan {
    /// Inclusive start byte offset.
    start: usize,
    /// Exclusive end byte offset.
    end: usize,
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

    /// Create a byte span without validating the range for error payloads.
    pub(crate) const fn new_unchecked(start: usize, end: usize) -> Self {
        Self { start, end }
    }

    /// Return the inclusive start byte offset.
    #[must_use]
    pub const fn start(&self) -> usize {
        self.start
    }

    /// Return the exclusive end byte offset.
    #[must_use]
    pub const fn end(&self) -> usize {
        self.end
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
        document_to_json(self)
    }
}

fn document_to_json(document: &GoldenDocument) -> String {
    let mut json = String::new();
    push_json_object(&mut json, 0, |object_json, indent| {
        let fields = [
            JsonField::new("fixture", json_string(&document.fixture)),
            JsonField::new("syntax", json_string(&document.syntax)),
            JsonField::new("line_index", usize_array_json(&document.line_index)),
            JsonField::new("regions", regions_json(&document.regions)),
            JsonField::new("diagnostics", string_array_json(&document.diagnostics)),
        ];
        push_json_fields(object_json, indent, &fields);
    });
    json.push('\n');
    json
}

struct JsonField<'a> {
    name: &'a str,
    value: String,
}

impl<'a> JsonField<'a> {
    const fn new(name: &'a str, value: String) -> Self {
        Self { name, value }
    }
}

fn push_json_object<F>(json: &mut String, indent: usize, write_fields: F)
where
    F: FnOnce(&mut String, usize),
{
    json.push_str("{\n");
    write_fields(json, indent + 1);
    push_indent(json, indent);
    json.push('}');
}

fn push_json_fields(json: &mut String, indent: usize, fields: &[JsonField<'_>]) {
    for (index, field) in fields.iter().enumerate() {
        push_indent(json, indent);
        json.push('"');
        json.push_str(field.name);
        json.push_str("\": ");
        json.push_str(&field.value);
        if index + 1 != fields.len() {
            json.push(',');
        }
        json.push('\n');
    }
}

fn push_indent(json: &mut String, indent: usize) {
    for _ in 0..indent {
        json.push_str("  ");
    }
}

fn array_json<T, F>(values: &[T], serialize: F) -> String
where
    F: Fn(&T) -> String,
{
    let mut json = String::from("[");
    for (index, value) in values.iter().enumerate() {
        if index > 0 {
            json.push_str(", ");
        }
        json.push_str(&serialize(value));
    }
    json.push(']');
    json
}

fn usize_array_json(values: &[usize]) -> String {
    array_json(values, ToString::to_string)
}

fn string_array_json(values: &[String]) -> String {
    array_json(values, |value| json_string(value))
}

fn regions_json(regions: &[GoldenRegion]) -> String {
    if regions.is_empty() {
        return "[]".to_owned();
    }

    let mut json = String::from("[\n");
    for (index, region) in regions.iter().enumerate() {
        push_indent(&mut json, 2);
        push_json_object(&mut json, 2, |object_json, indent| {
            let fields = [
                JsonField::new("kind", json_string(&region.kind)),
                JsonField::new("text", json_string(&region.text)),
                JsonField::new("segments", segments_json(&region.segments)),
            ];
            push_json_fields(object_json, indent, &fields);
        });
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
        push_json_object(&mut json, 4, |object_json, indent| match segment {
            Segment::Source { span, text } => {
                let fields = [
                    JsonField::new("kind", "\"source\"".to_owned()),
                    JsonField::new("start", span.start().to_string()),
                    JsonField::new("end", span.end().to_string()),
                    JsonField::new("text", json_string(text)),
                ];
                push_json_fields(object_json, indent, &fields);
            }
            Segment::Synthetic { text } => {
                let fields = [
                    JsonField::new("kind", "\"synthetic\"".to_owned()),
                    JsonField::new("text", json_string(text)),
                ];
                push_json_fields(object_json, indent, &fields);
            }
        });
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

#[expect(
    clippy::let_underscore_must_use,
    reason = "fmt::Write for String is infallible"
)]
fn write_json_control_escape(escaped: &mut String, control: char) {
    let _ = write!(escaped, "\\u{:04x}", u32::from(control));
}

#[cfg(test)]
mod tests {
    use super::{
        ByteSpan, GoldenBody, GoldenDocument, GoldenRegion, Segment, SpanError, json_string,
    };

    /// Keep byte span construction checked for ordered ranges.
    #[test]
    fn byte_span_new_accepts_ordered_ranges() {
        assert_eq!(ByteSpan::new(3, 8), Ok(ByteSpan::new_unchecked(3, 8)),);
    }

    /// Keep byte span construction from accepting inverted ranges.
    #[test]
    fn byte_span_new_rejects_inverted_ranges() {
        assert_eq!(ByteSpan::new(8, 3), Err(SpanError { start: 8, end: 3 }));
    }

    #[test]
    fn json_string_escapes_control_characters() {
        assert_eq!(
            json_string("\"\\\n\r\t\u{0008}"),
            "\"\\\"\\\\\\n\\r\\t\\u0008\""
        );
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
