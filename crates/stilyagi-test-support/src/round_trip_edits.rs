//! Round-trip edit helpers for applying source-backed replacements in tests.
//! [`RoundTripEdit`] accepts byte-oriented [`ByteSpan`] ranges for
//! source-backed edits and rejects synthetic edits, malformed spans, non-UTF-8
//! boundaries, and overlaps through [`apply_round_trip_edits`]. Callers pass
//! source text plus candidate edits and consume the returned
//! [`RoundTripEditResult`] to compare before/after text and applied edit order.

use crate::golden_ir::ByteSpan;

/// One edit used by the internal round-trip test helper.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RoundTripEdit {
    /// Replace a source-backed byte span with new text.
    Source {
        /// Editable byte range.
        span: ByteSpan,
        /// Replacement text.
        replacement: String,
    },
    /// Attempt to replace synthetic text, which must always be rejected.
    Synthetic {
        /// Synthetic text label for diagnostics.
        text: String,
        /// Replacement text requested by the caller.
        replacement: String,
    },
}

impl RoundTripEdit {
    /// Create a source-backed edit.
    #[must_use]
    pub fn source(start: usize, end: usize, replacement: impl Into<String>) -> Self {
        Self::Source {
            span: ByteSpan::new_unchecked(start, end),
            replacement: replacement.into(),
        }
    }

    /// Create a synthetic edit.
    #[must_use]
    pub fn synthetic(text: impl Into<String>, replacement: impl Into<String>) -> Self {
        Self::Synthetic {
            text: text.into(),
            replacement: replacement.into(),
        }
    }
}

/// Failure raised by the internal edit round-trip helper.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RoundTripEditError {
    /// A source edit range is malformed or outside the source length.
    InvalidSpan {
        /// Invalid span.
        span: ByteSpan,
        /// Source byte length.
        source_len: usize,
    },
    /// An edit targets synthetic text that has no source span.
    SyntheticSpan {
        /// Synthetic text label.
        text: String,
    },
    /// Two source edits overlap and would make the final text ambiguous.
    OverlappingEdits {
        /// Earlier edit span after stable sorting.
        previous: ByteSpan,
        /// Later edit span after stable sorting.
        current: ByteSpan,
    },
    /// A source edit does not begin and end on valid UTF-8 boundaries.
    NonUtf8Boundary {
        /// Invalid span.
        span: ByteSpan,
    },
}

impl std::fmt::Display for RoundTripEditError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidSpan { span, source_len } => write!(
                formatter,
                "invalid edit span {}..{} for source length {source_len}",
                span.start(),
                span.end()
            ),
            Self::SyntheticSpan { text } => {
                write!(formatter, "cannot edit synthetic segment {text:?}")
            }
            Self::OverlappingEdits { previous, current } => write!(
                formatter,
                "overlapping edit spans {}..{} and {}..{}",
                previous.start(),
                previous.end(),
                current.start(),
                current.end()
            ),
            Self::NonUtf8Boundary { span } => {
                write!(
                    formatter,
                    "edit span {}..{} is not UTF-8 aligned",
                    span.start(),
                    span.end()
                )
            }
        }
    }
}

impl std::error::Error for RoundTripEditError {}

/// Successful result from applying round-trip edits.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RoundTripEditResult {
    /// Source before edits.
    pub before: String,
    /// Source after edits.
    pub after: String,
    /// Source-backed edits in application order.
    pub applied_edits: Vec<RoundTripEdit>,
}

/// Apply source-backed edits while preserving all untouched source ranges.
///
/// # Errors
///
/// Returns an error when an edit targets synthetic text, uses an invalid byte
/// span, uses a non-UTF-8 boundary, or overlaps another edit.
pub fn apply_round_trip_edits(
    source: &str,
    edits: &[RoundTripEdit],
) -> Result<RoundTripEditResult, RoundTripEditError> {
    let source_edits = sorted_source_edits(source, edits)?;
    let after = apply_source_edits(source, &source_edits)?;
    let applied_edits = round_trip_edits(source_edits);

    Ok(RoundTripEditResult {
        before: source.to_owned(),
        after,
        applied_edits,
    })
}

fn sorted_source_edits(
    source: &str,
    edits: &[RoundTripEdit],
) -> Result<Vec<(ByteSpan, String)>, RoundTripEditError> {
    let mut source_edits = Vec::new();
    for edit in edits {
        match edit {
            RoundTripEdit::Source { span, replacement } => {
                validate_source_span(source, *span)?;
                source_edits.push((*span, replacement.clone()));
            }
            RoundTripEdit::Synthetic { text, .. } => {
                return Err(RoundTripEditError::SyntheticSpan { text: text.clone() });
            }
        }
    }

    source_edits.sort_by_key(|(span, _replacement)| (span.start(), span.end()));
    reject_overlaps(&source_edits)?;
    Ok(source_edits)
}

fn apply_source_edits(
    source: &str,
    source_edits: &[(ByteSpan, String)],
) -> Result<String, RoundTripEditError> {
    let mut after = String::new();
    let mut cursor = 0;
    for (span, replacement) in source_edits {
        after.push_str(utf8_slice(source, cursor, span.start())?);
        after.push_str(replacement);
        cursor = span.end();
    }
    after.push_str(utf8_slice(source, cursor, source.len())?);
    Ok(after)
}

fn round_trip_edits(source_edits: Vec<(ByteSpan, String)>) -> Vec<RoundTripEdit> {
    source_edits
        .into_iter()
        .map(|(span, replacement)| RoundTripEdit::Source { span, replacement })
        .collect()
}

fn utf8_slice(source: &str, start: usize, end: usize) -> Result<&str, RoundTripEditError> {
    let span = ByteSpan::new_unchecked(start, end);
    source
        .get(start..end)
        .ok_or(RoundTripEditError::NonUtf8Boundary { span })
}

fn validate_source_span(source: &str, span: ByteSpan) -> Result<(), RoundTripEditError> {
    if span.start() > span.end() || span.end() > source.len() {
        return Err(RoundTripEditError::InvalidSpan {
            span,
            source_len: source.len(),
        });
    }
    if !source.is_char_boundary(span.start()) || !source.is_char_boundary(span.end()) {
        return Err(RoundTripEditError::NonUtf8Boundary { span });
    }
    Ok(())
}

fn reject_overlaps(edits: &[(ByteSpan, String)]) -> Result<(), RoundTripEditError> {
    for pair in edits.windows(2) {
        let Some((previous, current)) = pair.first().zip(pair.get(1)) else {
            continue;
        };
        if previous.0.end() > current.0.start() {
            return Err(RoundTripEditError::OverlappingEdits {
                previous: previous.0,
                current: current.0,
            });
        }
    }
    Ok(())
}
