//! Source-level suppression and non-fatal error types for the IR.

use serde::{Deserialize, Serialize};

use crate::SourceSpan;

/// Source-level suppression directive discovered during extraction.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IrSuppression {
    /// Stable suppression identifier.
    pub id: String,
    /// Source span covered by the directive.
    pub span: SourceSpan,
    /// Suppressed rule names or families.
    pub rules: Vec<String>,
    /// Optional directive reason.
    pub reason: Option<String>,
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
