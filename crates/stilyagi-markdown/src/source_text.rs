//! Source-text byte mapping helpers for Markdown flattened regions.

use stilyagi_ir::SourceSpan;

pub(super) enum SourceTextEvent {
    LineEnding(usize),
    Character(usize),
    InvalidOffset,
}

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

pub(super) fn decoded_text_maps_to_source(source: &str, span: SourceSpan, value: &str) -> bool {
    let mut chunk_start = 0;
    let mut source_cursor = span.byte_start;
    let mut byte_offset = 0;
    while byte_offset < value.len() {
        match source_text_event(value, byte_offset) {
            SourceTextEvent::LineEnding(line_ending_len) => {
                if !source_chunk_matches(value, chunk_start..byte_offset, source, source_cursor) {
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
    source_chunk_matches(value, chunk_start..value.len(), source, source_cursor)
}

fn source_chunk_matches(
    value: &str,
    range: std::ops::Range<usize>,
    source: &str,
    source_start: usize,
) -> bool {
    let Some(chunk) = value.get(range) else {
        return false;
    };
    source.get(source_start..source_start + chunk.len()) == Some(chunk)
}

pub(super) fn source_value_start(source: &str, span: SourceSpan, value: &str) -> usize {
    source
        .get(span.byte_start..span.byte_end)
        .and_then(|source_slice| source_slice.find(value))
        .map_or(span.byte_start, |relative_offset| {
            span.byte_start + relative_offset
        })
}
