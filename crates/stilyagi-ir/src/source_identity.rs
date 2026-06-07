//! Source identity value object for IR metadata construction.

/// Caller-supplied source identity for IR metadata.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SourceIdentity {
    /// Repository-relative or display path when available.
    pub path: Option<String>,
    /// Stable source URI when available.
    pub uri: Option<String>,
}

impl SourceIdentity {
    /// Create anonymous source identity for string-only extraction.
    #[must_use]
    pub const fn anonymous() -> Self {
        Self {
            path: None,
            uri: None,
        }
    }

    /// Create source identity from explicit optional components.
    #[must_use]
    pub const fn new(path: Option<String>, uri: Option<String>) -> Self {
        Self { path, uri }
    }
}
