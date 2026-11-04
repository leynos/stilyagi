//! Source-text byte mapping helpers for Markdown flattened regions.

use stilyagi_ir::SourceSpan;

/// Classification of the next unit at a byte offset in decoded text.
pub(super) enum SourceTextEvent {
    /// A line ending of the given byte length: one for `\n`, two for `\r\n`.
    LineEnding(usize),
    /// A non-line-ending character of the given UTF-8 byte length.
    Character(usize),
    /// The offset is out of range or not on a character boundary.
    InvalidOffset,
}

/// Classifies the next unit at `byte_offset` in `value`.
///
/// Returns [`SourceTextEvent::InvalidOffset`] when the offset is out of range
/// or not on a character boundary.
pub(super) fn source_text_event(value: &str, byte_offset: usize) -> SourceTextEvent {
    let Some(tail) = value.get(byte_offset..) else {
        return SourceTextEvent::InvalidOffset;
    };
    if tail.starts_with("\r\n") {
        SourceTextEvent::LineEnding(2)
    } else if tail.starts_with('\n') {
        SourceTextEvent::LineEnding(1)
    } else {
        tail.chars()
            .next()
            .map_or(SourceTextEvent::InvalidOffset, |character| {
                SourceTextEvent::Character(character.len_utf8())
            })
    }
}

/// Returns the byte length of the line ending at `offset`, bounded by
/// `span_end`, or `None` when the text there is not a line ending.
pub(super) fn source_line_ending_len(
    source: &str,
    offset: usize,
    span_end: usize,
) -> Option<usize> {
    let tail = source.get(offset..span_end)?;
    if tail.starts_with("\r\n") {
        Some(2)
    } else if tail.starts_with('\n') {
        Some(1)
    } else {
        None
    }
}

/// A source slice and byte bounds used to match a decoded text chunk.
#[derive(Debug, Clone, Copy)]
struct SourceMatchWindow<'a> {
    /// The full source text being matched against.
    source: &'a str,
    /// Byte offset at which the chunk must begin.
    start: usize,
    /// Exclusive byte bound that the chunk must not exceed.
    span_end: usize,
}

impl<'a> SourceMatchWindow<'a> {
    /// Creates a match window over `source` from `start` up to `span_end`.
    const fn new(source: &'a str, start: usize, span_end: usize) -> Self {
        Self {
            source,
            start,
            span_end,
        }
    }
}

/// Reports whether decoded `value` maps onto `source` within `span`.
///
/// Line endings in `value` are matched against the source's own line endings,
/// so decoded text may differ from the raw source only in line-ending form.
pub(super) fn decoded_text_maps_to_source(source: &str, span: SourceSpan, value: &str) -> bool {
    let mut chunk_start = 0;
    let mut source_cursor = span.byte_start;
    let mut byte_offset = 0;
    while byte_offset < value.len() {
        match source_text_event(value, byte_offset) {
            SourceTextEvent::LineEnding(line_ending_len) => {
                if !source_chunk_matches(
                    value,
                    chunk_start..byte_offset,
                    SourceMatchWindow::new(source, source_cursor, span.byte_end),
                ) {
                    return false;
                }
                source_cursor += byte_offset - chunk_start;
                let Some(source_line_ending_len) =
                    source_line_ending_len(source, source_cursor, span.byte_end)
                else {
                    return false;
                };
                source_cursor += source_line_ending_len;
                byte_offset += line_ending_len;
                chunk_start = byte_offset;
            }
            SourceTextEvent::Character(character_len) => {
                byte_offset += character_len;
            }
            SourceTextEvent::InvalidOffset => return false,
        }
    }
    source_chunk_matches(
        value,
        chunk_start..value.len(),
        SourceMatchWindow::new(source, source_cursor, span.byte_end),
    )
}

/// Reports whether `value[range]` equals the source text at the window's
/// start, without running past its end.
fn source_chunk_matches(
    value: &str,
    range: std::ops::Range<usize>,
    window: SourceMatchWindow<'_>,
) -> bool {
    let Some(chunk) = value.get(range) else {
        return false;
    };
    let Some(source_end) = window.start.checked_add(chunk.len()) else {
        return false;
    };
    if source_end > window.span_end {
        return false;
    }
    window.source.get(window.start..source_end) == Some(chunk)
}

/// Returns the byte offset of the first occurrence of `value` within `span`,
/// falling back to the span start when it is absent or the span is invalid.
pub(super) fn source_value_start(source: &str, span: SourceSpan, value: &str) -> usize {
    source
        .get(span.byte_start..span.byte_end)
        .and_then(|source_slice| source_slice.find(value))
        .map_or(span.byte_start, |relative_offset| {
            span.byte_start + relative_offset
        })
}
