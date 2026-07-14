//! Extraction error types and Markdown diagnostic conversion.

use core::fmt;

use crate::ExtractSyntax;
use stilyagi_tree_sitter::{PythonExtractError, RustExtractError};

/// Extraction failures surfaced by the narrow v1 bridge.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ExtractError {
    /// The requested syntax is part of the long-term model, but not yet
    /// implemented by the extractor.
    UnsupportedSyntax(ExtractSyntax),
    /// The caller provided a syntax name that is not part of the supported
    /// syntax vocabulary.
    UnknownSyntax(String),
    /// Markdown parsing or IR construction failed.
    MarkdownIr(MarkdownIrFailure),
    /// Python parsing or IR construction failed fatally.
    PythonIr(PythonExtractError),
    /// Rust parsing or IR construction failed fatally.
    RustIr(RustExtractError),
}

const EXTRACT_ERROR_SIZE_LIMIT_BYTES: usize = 128;
const _: () = assert!(core::mem::size_of::<ExtractError>() <= EXTRACT_ERROR_SIZE_LIMIT_BYTES);

/// Structured Markdown IR diagnostic preserved across extraction boundaries.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MarkdownIrFailure {
    /// Diagnostic namespace that emitted the failure.
    pub source: String,
    /// Stable diagnostic rule identifier.
    pub rule_id: String,
    /// Human-readable diagnostic reason.
    pub reason: String,
    /// Ordered lower-level causes, when a producer provides them.
    pub causes: Vec<String>,
}

impl MarkdownIrFailure {
    /// Create a Markdown IR diagnostic without nested causes.
    ///
    /// # Examples
    ///
    /// ```
    /// use stilyagi_extract::MarkdownIrFailure;
    ///
    /// let failure = MarkdownIrFailure::new("stilyagi-markdown", "invalid-heading", "bad heading");
    ///
    /// assert_eq!(failure.source, "stilyagi-markdown");
    /// assert_eq!(failure.rule_id, "invalid-heading");
    /// assert_eq!(failure.reason, "bad heading");
    /// assert!(failure.causes.is_empty());
    /// ```
    #[must_use]
    pub fn new(
        source: impl Into<String>,
        rule_id: impl Into<String>,
        reason: impl Into<String>,
    ) -> Self {
        Self {
            source: source.into(),
            rule_id: rule_id.into(),
            reason: reason.into(),
            causes: Vec::new(),
        }
    }
}

impl From<markdown::message::Message> for MarkdownIrFailure {
    fn from(message: markdown::message::Message) -> Self {
        Self {
            source: *message.source,
            rule_id: *message.rule_id,
            reason: message.reason,
            causes: Vec::new(),
        }
    }
}

impl fmt::Display for MarkdownIrFailure {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "{}:{}: {}",
            self.source, self.rule_id, self.reason
        )?;
        for cause in &self.causes {
            write!(formatter, "; caused by: {cause}")?;
        }
        Ok(())
    }
}

impl fmt::Display for ExtractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::UnsupportedSyntax(syntax) => {
                write!(formatter, "{syntax} extraction is not implemented yet.")
            }
            Self::UnknownSyntax(syntax) => {
                write!(formatter, "unknown syntax '{syntax}'")
            }
            Self::MarkdownIr(diagnostic) => {
                write!(formatter, "markdown IR extraction failed: {diagnostic}")
            }
            Self::PythonIr(error) => write!(formatter, "python IR extraction failed: {error}"),
            Self::RustIr(error) => write!(formatter, "rust IR extraction failed: {error}"),
        }
    }
}

impl std::error::Error for ExtractError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::PythonIr(error) => Some(error),
            Self::RustIr(error) => Some(error),
            _ => None,
        }
    }
}
