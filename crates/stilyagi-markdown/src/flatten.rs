//! Markdown inline flattening into source-mapped IR region text.

use markdown::mdast::Node;
use stilyagi_ir::{IrSegment, SegmentOrigin, SourceSpan, SyntheticReason};

use crate::source_text::{
    SourceTextEvent,
    decoded_text_maps_to_source,
    source_line_ending_len,
    source_text_event,
    source_value_start,
};

/// Flattened inline text for one region, with source-mapped segments.
pub(crate) struct FlattenedRegion<'source> {
    /// The Markdown source text that segment spans index into.
    pub(crate) source: &'source str,
    /// Concatenated flattened text.
    pub(crate) text: String,
    /// Segments mapping ranges of `text` back to their origin.
    pub(crate) segments: Vec<IrSegment>,
}

/// A slice of source text together with the byte offset of its origin in
/// the raw source buffer. Used only inside [`FlattenedRegion`].
struct PositionedChunk<'a> {
    /// The full text the chunk is sliced from.
    value: &'a str,
    /// Byte range of the chunk within `value`.
    range: std::ops::Range<usize>,
    /// Offset to add to a range position to obtain its source offset.
    source_start: usize,
}

/// Tracks progress while mapping decoded text back to source bytes.
struct SourceTextCursor {
    /// Byte offset in the decoded text where the current chunk starts.
    chunk_start: usize,
    /// Source offset corresponding to `chunk_start`.
    chunk_source_start: usize,
    /// Current byte offset in the source text.
    source_cursor: usize,
    /// Current byte offset in the decoded text.
    byte_offset: usize,
}

impl SourceTextCursor {
    /// Creates a cursor positioned at `source_start` with no decoded text
    /// consumed.
    const fn new(source_start: usize) -> Self {
        Self {
            chunk_start: 0,
            chunk_source_start: source_start,
            source_cursor: source_start,
            byte_offset: 0,
        }
    }

    /// Advances the cursor past a decoded character of `character_len` bytes.
    const fn advance_character(&mut self, character_len: usize) {
        self.source_cursor += character_len;
        self.byte_offset += character_len;
    }

    /// Advances past a line ending, starting a new chunk after it.
    const fn advance_line_ending(&mut self, source_line_ending_len: usize, line_ending_len: usize) {
        self.source_cursor += source_line_ending_len;
        self.byte_offset += line_ending_len;
        self.chunk_start = self.byte_offset;
        self.chunk_source_start = self.source_cursor;
    }

    /// Builds a chunk covering the decoded text consumed since the last chunk
    /// start.
    const fn positioned_chunk<'value>(&self, value: &'value str) -> PositionedChunk<'value> {
        PositionedChunk {
            value,
            range: self.chunk_start..self.byte_offset,
            source_start: self.chunk_source_start - self.chunk_start,
        }
    }

    /// Builds a chunk covering the remaining decoded text to the end of
    /// `value`.
    const fn final_chunk<'value>(&self, value: &'value str) -> PositionedChunk<'value> {
        PositionedChunk {
            value,
            range: self.chunk_start..value.len(),
            source_start: self.chunk_source_start - self.chunk_start,
        }
    }
}

/// A line ending encountered while flattening, with its source node.
#[derive(Debug, Clone, Copy)]
struct LineEnding<'value, 'node> {
    /// The text being flattened.
    value: &'value str,
    /// Identifier of the node the line ending belongs to.
    node_id: SourceNodeId<'node>,
    /// Length of the line ending in the decoded text, in bytes.
    len: usize,
}

/// Identifier of the source node that flattened segments originate from.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct SourceNodeId<'a>(&'a str);

impl<'a> SourceNodeId<'a> {
    /// Wraps a node identifier string.
    pub(crate) const fn new(value: &'a str) -> Self { Self(value) }

    /// Returns the wrapped node identifier.
    const fn as_str(self) -> &'a str { self.0 }
}

impl FlattenedRegion<'_> {
    /// Emits the chunk's text as a source-backed segment when the range is
    /// valid.
    fn emit_chunk_for_range(&mut self, chunk: PositionedChunk<'_>, node_id: SourceNodeId<'_>) {
        let PositionedChunk {
            value,
            range,
            source_start,
        } = chunk;
        let range_start = range.start;
        let range_end = range.end;
        let Some(text) = value.get(range_start..range_end) else {
            return;
        };
        if text.is_empty() {
            return;
        }
        let Some(span) = SourceSpan::new(source_start + range_start, source_start + range_end)
        else {
            return;
        };
        self.push_segment(
            text,
            SegmentOrigin::Source {
                span,
                node: node_id.as_str().to_owned(),
            },
        );
    }

    /// Emits `value` as source-backed segments, splitting at line endings.
    fn push_source_text(&mut self, value: &str, source_start: usize, node_id: SourceNodeId<'_>) {
        let mut cursor = SourceTextCursor::new(source_start);
        while cursor.byte_offset < value.len()
            && self.push_source_text_event(value, node_id, &mut cursor)
        {}
        self.emit_chunk_for_range(cursor.final_chunk(value), node_id);
    }

    /// Processes one decoded text event, returning whether iteration should
    /// continue.
    fn push_source_text_event(
        &mut self,
        value: &str,
        node_id: SourceNodeId<'_>,
        cursor: &mut SourceTextCursor,
    ) -> bool {
        match source_text_event(value, cursor.byte_offset) {
            SourceTextEvent::LineEnding(line_ending_len) => self
                .push_line_ending(
                    LineEnding {
                        value,
                        node_id,
                        len: line_ending_len,
                    },
                    cursor,
                )
                .is_some(),
            SourceTextEvent::Character(character_len) => {
                cursor.advance_character(character_len);
                true
            }
            SourceTextEvent::InvalidOffset => false,
        }
    }

    /// Emits the pending chunk, then a softbreak space for the line ending.
    fn push_line_ending(
        &mut self,
        line_ending: LineEnding<'_, '_>,
        cursor: &mut SourceTextCursor,
    ) -> Option<()> {
        let source_line_ending_len =
            source_line_ending_len(self.source, cursor.source_cursor, self.source.len())?;
        self.emit_chunk_for_range(
            cursor.positioned_chunk(line_ending.value),
            line_ending.node_id,
        );
        cursor.advance_line_ending(source_line_ending_len, line_ending.len);
        if let Some(source_span) = SourceSpan::new(cursor.source_cursor, cursor.source_cursor) {
            self.push_source_chunk_before_break("", source_span, line_ending.node_id);
        }
        Some(())
    }

    /// Emits a non-empty source chunk, then a synthetic softbreak space.
    fn push_source_chunk_before_break(
        &mut self,
        chunk: &str,
        span: SourceSpan,
        node_id: SourceNodeId<'_>,
    ) {
        if !chunk.is_empty() {
            self.push_segment(
                chunk,
                SegmentOrigin::Source {
                    span,
                    node: node_id.as_str().to_owned(),
                },
            );
        }
        self.push_synthetic_segment(" ", SyntheticReason::SoftbreakSpace);
    }

    /// Appends `text` to the flattened text and records its segment.
    fn push_segment(&mut self, text: &str, origin: SegmentOrigin) {
        let text_start = self.text.len();
        self.text.push_str(text);
        self.segments.push(IrSegment::new(text_start, text, origin));
    }

    /// Appends synthetic text with the given reason.
    fn push_synthetic_segment(&mut self, text: &str, reason: SyntheticReason) {
        self.push_segment(text, SegmentOrigin::Synthetic { reason });
    }

    /// Appends decoded text as a synthetic segment when it is non-empty.
    fn push_decoded_text(&mut self, text: &str) {
        if !text.is_empty() {
            self.push_synthetic_segment(text, SyntheticReason::DecodedText);
        }
    }
}

/// Flattens the inline content of `node` into a source-mapped region.
pub(crate) fn flatten_region<'source>(
    node: &Node,
    node_id: SourceNodeId<'_>,
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

/// Dispatches flattening for one inline node.
fn flatten_inline(node: &Node, node_id: SourceNodeId<'_>, flattened: &mut FlattenedRegion<'_>) {
    match node {
        Node::Text(text) => flatten_text_node(text, node_id, flattened),
        Node::Break(_) => {
            flattened.push_synthetic_segment(" ", SyntheticReason::HardbreakSpace);
        }
        Node::InlineCode(code) => flatten_inline_code_node(code, node_id, flattened),
        _ => flatten_children(node, node_id, flattened),
    }
}

/// Flattens a text node, preserving source mapping when the text matches the
/// source.
fn flatten_text_node(
    text: &markdown::mdast::Text,
    node_id: SourceNodeId<'_>,
    flattened: &mut FlattenedRegion<'_>,
) {
    let Some(position) = text.position.as_ref() else {
        flattened.push_decoded_text(&text.value);
        return;
    };

    let Some(span) = SourceSpan::new(position.start.offset, position.end.offset) else {
        flattened.push_decoded_text(&text.value);
        return;
    };
    if decoded_text_maps_to_source(flattened.source, span, &text.value) {
        flattened.push_source_text(&text.value, position.start.offset, node_id);
    } else {
        flattened.push_decoded_text(&text.value);
    }
}

/// Flattens inline code, preserving source mapping when the value matches the
/// source.
fn flatten_inline_code_node(
    code: &markdown::mdast::InlineCode,
    node_id: SourceNodeId<'_>,
    flattened: &mut FlattenedRegion<'_>,
) {
    let Some(position) = code.position.as_ref() else {
        flattened.push_decoded_text(&code.value);
        return;
    };

    let Some(span) = SourceSpan::new(position.start.offset, position.end.offset) else {
        flattened.push_decoded_text(&code.value);
        return;
    };
    let source_start = source_value_start(flattened.source, span, &code.value);
    let Some(source_end) = source_start.checked_add(code.value.len()) else {
        flattened.push_decoded_text(&code.value);
        return;
    };
    let Some(value_span) = SourceSpan::new(source_start, source_end) else {
        flattened.push_decoded_text(&code.value);
        return;
    };
    if !decoded_text_maps_to_source(flattened.source, value_span, &code.value) {
        flattened.push_decoded_text(&code.value);
        return;
    }
    flattened.push_source_text(&code.value, source_start, node_id);
}

/// Flattens each child of `node` in order.
fn flatten_children(node: &Node, node_id: SourceNodeId<'_>, flattened: &mut FlattenedRegion<'_>) {
    if let Some(children) = node.children() {
        for child in children {
            flatten_inline(child, node_id, flattened);
        }
    }
}
