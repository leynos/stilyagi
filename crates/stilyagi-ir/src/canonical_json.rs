//! Canonical JSON formatting for golden IR snapshots.
//!
//! Here, canonical means deterministic field order, two-space indentation, and
//! explicit string escaping, including `\uXXXX` escapes for control characters.
//! The formatter is deliberately hand-written instead of using `serde` so
//! snapshot tests and future `dump-ir` output do not drift when serializer
//! defaults or dependency versions change. [`GoldenDocument`] owns the flat IR
//! test contract, while this module owns the stable textual form and the public
//! [`line_index_for`] helper used to build golden fixtures.

use std::fmt::Write as _;

use crate::{GoldenDocument, GoldenRegion, Segment};

pub(crate) fn document_to_json(document: &GoldenDocument) -> String {
    let mut json = String::new();
    push_json_object(&mut json, 0, |object_json, indent| {
        let fields = vec![
            JsonField::new("fixture", json_string(&document.fixture), false),
            JsonField::new("syntax", json_string(&document.syntax), false),
            JsonField::new("line_index", usize_array_json(&document.line_index), false),
            JsonField::new("regions", regions_json(&document.regions), false),
            JsonField::new(
                "diagnostics",
                string_array_json(&document.diagnostics),
                true,
            ),
        ];
        push_json_fields(object_json, indent, &fields);
    });
    json.push('\n');
    json
}

struct JsonField<'a> {
    name: &'a str,
    value: String,
    is_last: bool,
}

impl<'a> JsonField<'a> {
    const fn new(name: &'a str, value: String, is_last: bool) -> Self {
        Self {
            name,
            value,
            is_last,
        }
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
    for field in fields {
        push_indent(json, indent);
        json.push('"');
        json.push_str(field.name);
        json.push_str("\": ");
        json.push_str(&field.value);
        if !field.is_last {
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
            let fields = vec![
                JsonField::new("kind", json_string(&region.kind), false),
                JsonField::new("text", json_string(&region.text), false),
                JsonField::new("segments", segments_json(&region.segments), true),
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
                let fields = vec![
                    JsonField::new("kind", "\"source\"".to_owned(), false),
                    JsonField::new("start", span.start.to_string(), false),
                    JsonField::new("end", span.end.to_string(), false),
                    JsonField::new("text", json_string(text), true),
                ];
                push_json_fields(object_json, indent, &fields);
            }
            Segment::Synthetic { text } => {
                let fields = vec![
                    JsonField::new("kind", "\"synthetic\"".to_owned(), false),
                    JsonField::new("text", json_string(text), true),
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
    use super::{json_string, line_index_for};

    #[test]
    fn json_string_escapes_control_characters() {
        assert_eq!(
            json_string("\"\\\n\r\t\u{0008}"),
            "\"\\\"\\\\\\n\\r\\t\\u0008\""
        );
    }

    #[test]
    fn line_index_for_reports_byte_offsets_and_document_end() {
        assert_eq!(line_index_for("é\nx"), vec![0, 3, 4]);
    }
}
