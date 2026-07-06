//! Source-level suppression and non-fatal error types for the IR.

use serde::{Deserialize, Serialize};

use crate::SourceSpan;

/// Directive stratum recorded in the IR.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SuppressionKind {
    /// Inline suppression that applies to the next lintable unit.
    Inline,
    /// Range suppression that brackets a span of source text.
    Range,
    /// File suppression that applies to the entire document.
    File,
    /// Configuration-originated suppression.
    Config,
}

/// Polarity carried by a range suppression.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RangeRole {
    /// Directive that opens a suppressed span.
    Open,
    /// Directive that closes a suppressed span.
    Close,
}

/// Source-level suppression directive discovered during extraction.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IrSuppression {
    /// Stable suppression identifier.
    pub id: String,
    /// Directive stratum recorded by the frontend.
    pub kind: SuppressionKind,
    /// Role carried by range suppressions.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub range_role: Option<RangeRole>,
    /// Rule codes or prefixes named by the directive.
    ///
    /// File-scope directives may intentionally carry an empty list.
    pub codes: Vec<String>,
    /// Source span covered by the directive.
    pub span: SourceSpan,
    /// IR node id of the comment node that produced this directive.
    pub origin: String,
}

/// Non-fatal parser or extractor anomaly.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IrError {
    /// Stable error code.
    pub code: String,
    /// Human-readable error message.
    pub message: String,
    /// Source span associated with the error, if known.
    pub span: Option<SourceSpan>,
}
