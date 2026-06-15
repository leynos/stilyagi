//! Golden fixture builders for the test-support crate. These helpers read
//! corpus fixtures, normalize their repository-relative names, compute line
//! indexes with [`stilyagi_ir::line_index_for`], and assemble
//! [`GoldenDocument`], [`GoldenBody`], [`GoldenRegion`], and [`Segment`]
//! values for snapshot and contract tests.

use std::path::Path;

use stilyagi_ir::{IrDocument, SourceIdentity, line_index_for};
use stilyagi_tree_sitter::{PythonExtractError, python_docstring_ir_document};

use crate::fixture_paths::{FixturePathError, normalize_repository_path};
use crate::fixture_reads::{FixtureReadError, read_corpus_fixture};
use crate::golden_ir::{ByteSpan, GoldenBody, GoldenDocument, GoldenRegion, Segment};

/// Failure raised when building a production Python golden IR document.
#[derive(Debug)]
pub enum GoldenPythonFixtureError {
    /// The requested corpus fixture could not be read.
    Fixture(FixtureReadError),
    /// The Python extractor could not produce IR.
    Extract(PythonExtractError),
}

impl std::fmt::Display for GoldenPythonFixtureError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Fixture(error) => write!(formatter, "{error}"),
            Self::Extract(error) => write!(formatter, "{error}"),
        }
    }
}

impl std::error::Error for GoldenPythonFixtureError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Fixture(error) => Some(error),
            Self::Extract(error) => Some(error),
        }
    }
}

impl From<FixtureReadError> for GoldenPythonFixtureError {
    fn from(error: FixtureReadError) -> Self {
        Self::Fixture(error)
    }
}

impl From<FixturePathError> for GoldenPythonFixtureError {
    fn from(error: FixturePathError) -> Self {
        Self::Fixture(FixtureReadError::from(error))
    }
}

impl From<PythonExtractError> for GoldenPythonFixtureError {
    fn from(error: PythonExtractError) -> Self {
        Self::Extract(error)
    }
}

/// Build the private golden IR shape for a supported Markdown corpus fixture.
///
/// # Errors
///
/// Returns an error if the fixture path is invalid or cannot be read.
pub fn golden_markdown_ir_fixture(
    relative_path: impl AsRef<Path>,
) -> Result<GoldenDocument, FixtureReadError> {
    let path = relative_path.as_ref();
    let source = read_corpus_fixture(path)?;
    let fixture = normalize_repository_path(path)?;

    Ok(GoldenDocument::new(
        fixture,
        "markdown",
        GoldenBody {
            line_index: line_index_for(&source),
            regions: markdown_regions(&source),
            diagnostics: Vec::new(),
        },
    ))
}

/// Build production Python docstring IR for a corpus fixture.
///
/// # Errors
///
/// Returns an error if the fixture path is invalid, cannot be read, or cannot
/// be parsed by the Python extractor.
pub fn golden_python_ir_fixture(
    relative_path: impl AsRef<Path>,
) -> Result<IrDocument, GoldenPythonFixtureError> {
    let path = relative_path.as_ref();
    let source = read_corpus_fixture(path)?;
    let fixture = normalize_repository_path(path)?;

    Ok(python_docstring_ir_document(
        &source,
        SourceIdentity::new(Some(fixture), None),
    )?)
}

fn markdown_regions(source: &str) -> Vec<GoldenRegion> {
    if source.trim().is_empty() {
        Vec::new()
    } else {
        vec![GoldenRegion::new(
            "document",
            source,
            vec![Segment::source(
                ByteSpan::new_unchecked(0, source.len()),
                source,
            )],
        )]
    }
}
