//! Source extraction orchestration for the first Rust-to-Python bridge.

use core::fmt;
mod error;
mod region;

pub use error::{ExtractError, MarkdownIrFailure};
pub use region::{ExtractRegion, RegionKind};
pub use stilyagi_ir::SourceIdentity;
use stilyagi_ir::{IrBoundary, IrDocument};
use stilyagi_markdown::{MarkdownBoundary, markdown_ir_document};
pub use stilyagi_tree_sitter::{PythonExtractError, RustExtractError};
use stilyagi_tree_sitter::{
    TreeSitterBoundary, python_docstring_ir_document, rust_doc_comment_ir_document,
};

/// Supported source syntaxes for the initial extraction boundary.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExtractSyntax {
    /// Markdown prose extracted directly from `.md` sources.
    Markdown,
    /// Python docstring prose extracted with owner metadata.
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

/// Partial document payload returned by the first extraction slice.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExtractDocument {
    syntax: ExtractSyntax,
    regions: Vec<ExtractRegion>,
    ir: Option<IrDocument>,
}

impl ExtractDocument {
    /// Create a partial document with the supplied syntax and regions.
    #[must_use]
    pub const fn new(syntax: ExtractSyntax, regions: Vec<ExtractRegion>) -> Self {
        Self {
            syntax,
            regions,
            ir: None,
        }
    }

    /// Attach the full IR document envelope to this extraction payload.
    #[must_use]
    pub fn with_ir(mut self, ir: IrDocument) -> Self {
        self.ir = Some(ir);
        self
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

    /// Return the full IR document envelope when this syntax provides one.
    #[must_use]
    pub const fn ir(&self) -> Option<&IrDocument> {
        self.ir.as_ref()
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
/// [`ExtractError::MarkdownIr`] when Markdown parsing or IR construction fails.
/// Returns [`ExtractError::PythonIr`] when Python parsing or IR construction
/// fails fatally.
/// Returns [`ExtractError::UnknownSyntax`] only when a caller first converts an
/// arbitrary string into [`ExtractSyntax`] via `TryFrom<&str>`.
pub fn extract_document(
    source: &str,
    syntax: ExtractSyntax,
) -> Result<ExtractDocument, ExtractError> {
    extract_document_with_source_identity(source, syntax, SourceIdentity::anonymous())
}

/// Extract a minimal document-shaped payload with explicit source identity.
///
/// # Errors
///
/// Returns [`ExtractError::UnsupportedSyntax`] when the syntax is part of the
/// current model vocabulary but not yet implemented. Returns
/// [`ExtractError::MarkdownIr`] when Markdown parsing or IR construction fails.
/// Returns [`ExtractError::PythonIr`] when Python parsing or IR construction
/// fails fatally.
/// Returns [`ExtractError::UnknownSyntax`] only when a caller first converts an
/// arbitrary string into [`ExtractSyntax`] via `TryFrom<&str>`.
pub fn extract_document_with_source_identity(
    source: &str,
    syntax: ExtractSyntax,
    identity: SourceIdentity,
) -> Result<ExtractDocument, ExtractError> {
    match syntax {
        ExtractSyntax::Markdown => extract_markdown_document(source, identity),
        ExtractSyntax::PythonDocstring => extract_python_document(source, identity),
        ExtractSyntax::RustDocComment => extract_rust_document(source, identity),
    }
}

/// Extracts a Markdown document and returns its regions and canonical IR.
fn extract_markdown_document(
    source: &str,
    identity: SourceIdentity,
) -> Result<ExtractDocument, ExtractError> {
    extract_markdown_document_with(source, |markdown_source| {
        markdown_ir_document(markdown_source, identity)
    })
}

/// Builds a Markdown document with the supplied IR builder and returns its regions and IR.
fn extract_markdown_document_with<E>(
    source: &str,
    build_ir: impl FnOnce(&str) -> Result<IrDocument, E>,
) -> Result<ExtractDocument, ExtractError>
where
    E: Into<MarkdownIrFailure>,
{
    let ir = build_ir(source).map_err(|error| ExtractError::MarkdownIr(error.into()))?;
    let regions = if source.trim().is_empty() {
        Vec::new()
    } else {
        vec![ExtractRegion::new_typed(RegionKind::Document, source)]
    };
    Ok(ExtractDocument::new(ExtractSyntax::Markdown, regions).with_ir(ir))
}

/// Builds an extraction document from a syntax-specific canonical IR.
#[expect(
    clippy::too_many_arguments,
    reason = "the private helper's five parameters are its extraction boundary"
)]
fn extract_document_from_ir<E>(
    source: &str,
    identity: SourceIdentity,
    syntax: ExtractSyntax,
    build_ir: impl FnOnce(&str, SourceIdentity) -> Result<IrDocument, E>,
    map_err: impl FnOnce(E) -> ExtractError,
) -> Result<ExtractDocument, ExtractError> {
    let ir = build_ir(source, identity).map_err(map_err)?;
    let regions = ir
        .regions
        .iter()
        .map(|region| ExtractRegion::new(region.kind.clone(), region.text.clone()))
        .collect();

    Ok(ExtractDocument::new(syntax, regions).with_ir(ir))
}

/// Extracts Python docstrings and returns their regions and canonical IR.
fn extract_python_document(
    source: &str,
    identity: SourceIdentity,
) -> Result<ExtractDocument, ExtractError> {
    extract_document_from_ir(
        source,
        identity,
        ExtractSyntax::PythonDocstring,
        python_docstring_ir_document,
        ExtractError::PythonIr,
    )
}

/// Extracts Rust doc comments and returns their regions and canonical IR.
fn extract_rust_document(
    source: &str,
    identity: SourceIdentity,
) -> Result<ExtractDocument, ExtractError> {
    extract_document_from_ir(
        source,
        identity,
        ExtractSyntax::RustDocComment,
        rust_doc_comment_ir_document,
        ExtractError::RustIr,
    )
}

#[cfg(test)]
mod tests;
