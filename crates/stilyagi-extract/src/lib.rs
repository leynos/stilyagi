//! Source extraction orchestration for the first Rust-to-Python bridge.

use core::fmt;
use stilyagi_ir::IrBoundary;
use stilyagi_markdown::MarkdownBoundary;
use stilyagi_tree_sitter::TreeSitterBoundary;

/// Supported source syntaxes for the initial extraction boundary.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExtractSyntax {
    /// Markdown prose extracted directly from `.md` sources.
    Markdown,
    /// Python docstring extraction, reserved for a later roadmap slice.
    PythonDocstring,
    /// Rust documentation-comment extraction, reserved for a later slice.
    RustDocComment,
}

impl ExtractSyntax {
    /// Ordered list of the stable syntax spellings exposed through the bridge.
    pub const ALL: [Self; 3] = [Self::Markdown, Self::PythonDocstring, Self::RustDocComment];

    /// Return the stable Python-facing syntax spelling.
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Markdown => "markdown",
            Self::PythonDocstring => "python_docstring",
            Self::RustDocComment => "rust_doc_comment",
        }
    }
}

impl fmt::Display for ExtractSyntax {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

/// Extraction failures surfaced by the narrow v1 bridge.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ExtractError {
    /// The requested syntax is part of the long-term model, but not yet
    /// implemented by the extractor.
    UnsupportedSyntax(ExtractSyntax),
    /// The caller provided a syntax name that is not part of the supported
    /// syntax vocabulary.
    UnknownSyntax(String),
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
        }
    }
}

impl std::error::Error for ExtractError {}

impl TryFrom<&str> for ExtractSyntax {
    type Error = ExtractError;

    fn try_from(value: &str) -> Result<Self, Self::Error> {
        match value {
            "markdown" => Ok(Self::Markdown),
            "python_docstring" => Ok(Self::PythonDocstring),
            "rust_doc_comment" => Ok(Self::RustDocComment),
            _ => Err(ExtractError::UnknownSyntax(value.to_owned())),
        }
    }
}

/// Stable kind names for extracted prose regions.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[non_exhaustive]
pub enum RegionKind {
    /// Whole-document prose extracted from a source file.
    Document,
}

impl RegionKind {
    /// Return the stable bridge spelling for this region kind.
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Document => "document",
        }
    }
}

impl fmt::Display for RegionKind {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

impl TryFrom<&str> for RegionKind {
    type Error = String;

    fn try_from(value: &str) -> Result<Self, Self::Error> {
        match value {
            "document" => Ok(Self::Document),
            _ => Err(value.to_owned()),
        }
    }
}

/// Minimal source-backed prose region for the first extraction bridge.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExtractRegion {
    kind: String,
    text: String,
}

impl ExtractRegion {
    /// Create a region with the supplied stable kind name and text.
    #[must_use]
    pub fn new(kind: impl Into<String>, text: impl Into<String>) -> Self {
        Self {
            kind: kind.into(),
            text: text.into(),
        }
    }

    /// Create a region from the typed region kind and supplied text.
    #[must_use]
    pub fn new_typed(kind: RegionKind, text: impl Into<String>) -> Self {
        Self::new(kind.as_str(), text)
    }

    /// Return the stable region kind name.
    #[must_use]
    pub fn kind(&self) -> &str {
        &self.kind
    }

    /// Return the typed region kind when it is in the built-in vocabulary.
    #[must_use]
    pub fn region_kind(&self) -> Option<RegionKind> {
        RegionKind::try_from(self.kind()).ok()
    }

    /// Return the extracted region text.
    #[must_use]
    pub fn text(&self) -> &str {
        &self.text
    }
}

/// Partial document payload returned by the first extraction slice.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExtractDocument {
    syntax: ExtractSyntax,
    regions: Vec<ExtractRegion>,
}

impl ExtractDocument {
    /// Create a partial document with the supplied syntax and regions.
    #[must_use]
    pub const fn new(syntax: ExtractSyntax, regions: Vec<ExtractRegion>) -> Self {
        Self { syntax, regions }
    }

    /// Return the syntax represented by the document.
    #[must_use]
    pub const fn syntax(&self) -> ExtractSyntax {
        self.syntax
    }

    /// Return the extracted prose regions.
    #[must_use]
    pub fn regions(&self) -> &[ExtractRegion] {
        &self.regions
    }
}

/// Marker type for the future extraction orchestration boundary.
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct ExtractBoundary {
    /// Placeholder for Markdown extraction support.
    markdown: MarkdownBoundary,
    /// Placeholder for tree-sitter extraction support.
    tree_sitter: TreeSitterBoundary,
    /// Placeholder for IR construction support.
    ir: IrBoundary,
}

impl ExtractBoundary {
    /// Return the placeholder Markdown extraction boundary.
    #[must_use]
    pub const fn markdown(&self) -> &MarkdownBoundary {
        &self.markdown
    }

    /// Return the placeholder tree-sitter extraction boundary.
    #[must_use]
    pub const fn tree_sitter(&self) -> &TreeSitterBoundary {
        &self.tree_sitter
    }

    /// Return the placeholder IR construction boundary.
    #[must_use]
    pub const fn ir(&self) -> &IrBoundary {
        &self.ir
    }
}

/// Extract a minimal document-shaped payload for the supported syntax.
///
/// # Errors
///
/// Returns [`ExtractError::UnsupportedSyntax`] when the syntax is part of the
/// current model vocabulary but not yet implemented. Returns
/// [`ExtractError::UnknownSyntax`] only when a caller first converts an
/// arbitrary string into [`ExtractSyntax`] via `TryFrom<&str>`.
pub fn extract_document(
    source: &str,
    syntax: ExtractSyntax,
) -> Result<ExtractDocument, ExtractError> {
    match syntax {
        ExtractSyntax::Markdown => Ok(extract_markdown_document(source)),
        ExtractSyntax::PythonDocstring | ExtractSyntax::RustDocComment => {
            Err(ExtractError::UnsupportedSyntax(syntax))
        }
    }
}

fn extract_markdown_document(source: &str) -> ExtractDocument {
    let regions = if source.trim().is_empty() {
        Vec::new()
    } else {
        vec![ExtractRegion::new_typed(RegionKind::Document, source)]
    };
    ExtractDocument::new(ExtractSyntax::Markdown, regions)
}
