//! Markdown inline flattening into source-mapped IR region text.

use markdown::mdast::Node;
use stilyagi_ir::{IrSegment, SegmentOrigin, SourceSpan};

use crate::source_text::{
    SourceTextEvent, decoded_text_maps_to_source, source_line_ending_len, source_text_event,
    source_value_start,
};

pub(crate) struct FlattenedRegion<'source> {
    pub(crate) source: &'source str,
    pub(crate) text: String,
    pub(crate) segments: Vec<IrSegment>,
}

/// A slice of source text together with the byte offset of its origin in
/// the raw source buffer. Used only inside [`FlattenedRegion`].
struct PositionedChunk<'a> {
    value: &'a str,
    range: std::ops::Range<usize>,
    source_start: usize,
}

impl FlattenedRegion<'_> {
    fn emit_chunk_for_range(&mut self, chunk: PositionedChunk<'_>, node_id: &str) {
        let PositionedChunk {
            value,
            range,
            source_start,
        } = chunk;
        let Some(text) = value.get(range.clone()) else {
            return;
        };
        if text.is_empty() {
            return;
        }
        let span = SourceSpan::new(source_start + range.start, source_start + range.end);
        self.push_source_chunk(text, span, node_id);
    }

    fn push_source_text(&mut self, value: &str, source_start: usize, node_id: &str) {
        let mut chunk_start = 0;
        let mut chunk_source_start = source_start;
        let mut source_cursor = source_start;
        let mut byte_offset = 0;
        while byte_offset < value.len() {
            match source_text_event(value, byte_offset) {
                SourceTextEvent::LineEnding(line_ending_len) => {
                    self.emit_chunk_for_range(
                        PositionedChunk {
                            value,
                            range: chunk_start..byte_offset,
                            source_start: chunk_source_start - chunk_start,
                        },
                        node_id,
                    );
                    let Some(source_line_ending_len) =
                        source_line_ending_len(self.source, source_cursor, self.source.len())
                    else {
                        break;
                    };
                    source_cursor += source_line_ending_len;
                    byte_offset += line_ending_len;
                    chunk_start = byte_offset;
                    chunk_source_start = source_cursor;
                    self.push_source_chunk_before_break(
                        "",
                        SourceSpan::new(source_cursor, source_cursor),
                        node_id,
                    );
                }
                SourceTextEvent::Character(character_len) => {
                    source_cursor += character_len;
                    byte_offset += character_len;
                }
                SourceTextEvent::InvalidOffset => break,
            }
        }
        self.emit_chunk_for_range(
            PositionedChunk {
                value,
                range: chunk_start..value.len(),
                source_start: chunk_source_start - chunk_start,
            },
            node_id,
        );
    }

    fn push_source_chunk_before_break(&mut self, chunk: &str, span: SourceSpan, node_id: &str) {
        if !chunk.is_empty() {
            self.push_source_chunk(chunk, span, node_id);
        }
        self.push_synthetic(" ", "softbreak_space");
    }

    fn push_source_chunk(&mut self, chunk: &str, span: SourceSpan, node_id: &str) {
        let text_start = self.text.len();
        self.text.push_str(chunk);
        self.segments.push(IrSegment::new(
            text_start,
            chunk,
            SegmentOrigin::Source {
                span,
                node: node_id.to_owned(),
            },
        ));
    }

    fn push_synthetic(&mut self, text: &str, reason: &str) {
        let text_start = self.text.len();
        self.text.push_str(text);
        self.segments.push(IrSegment::new(
            text_start,
            text,
            SegmentOrigin::Synthetic {
                reason: reason.to_owned(),
            },
        ));
    }

    fn push_decoded_text(&mut self, text: &str) {
        if !text.is_empty() {
            self.push_synthetic(text, "decoded_text");
        }
    }
}

pub(crate) fn flatten_region<'source>(
    node: &Node,
    node_id: &str,
    source: &'source str,
) -> FlattenedRegion<'source> {
    let mut flattened = FlattenedRegion {
        source,
        text: String::new(),
        segments: Vec::new(),
    };
    flatten_inline(node, node_id, &mut flattened);
    flattened
}

fn flatten_inline(node: &Node, node_id: &str, flattened: &mut FlattenedRegion<'_>) {
    match node {
        Node::Text(text) => flatten_text_node(text, node_id, flattened),
        Node::Break(_) => flattened.push_synthetic(" ", "hardbreak_space"),
        Node::InlineCode(code) => flatten_inline_code_node(code, node_id, flattened),
        _ => flatten_children(node, node_id, flattened),
    }
}

fn flatten_text_node(
    text: &markdown::mdast::Text,
    node_id: &str,
    flattened: &mut FlattenedRegion<'_>,
) {
    if let Some(position) = text.position.as_ref() {
        let span = SourceSpan::new(position.start.offset, position.end.offset);
        if decoded_text_maps_to_source(flattened.source, span, &text.value) {
            flattened.push_source_text(&text.value, position.start.offset, node_id);
        } else {
            flattened.push_decoded_text(&text.value);
        }
    }
}

fn flatten_inline_code_node(
    code: &markdown::mdast::InlineCode,
    node_id: &str,
    flattened: &mut FlattenedRegion<'_>,
) {
    if let Some(position) = code.position.as_ref() {
        let span = SourceSpan::new(position.start.offset, position.end.offset);
        let source_start = source_value_start(flattened.source, span, &code.value);
        flattened.push_source_text(&code.value, source_start, node_id);
    }
}

fn flatten_children(node: &Node, node_id: &str, flattened: &mut FlattenedRegion<'_>) {
    if let Some(children) = node.children() {
        for child in children {
            flatten_inline(child, node_id, flattened);
        }
    }
}
