//! Golden fixture builders for the test-support crate. These helpers read
//! corpus fixtures, normalize their repository-relative names, compute line
//! indexes with [`stilyagi_ir::line_index_for`], and assemble
//! [`GoldenDocument`], [`GoldenBody`], [`GoldenRegion`], and [`Segment`]
//! values for snapshot and contract tests.

use std::path::Path;

use stilyagi_ir::line_index_for;

use crate::fixture_paths::normalize_repository_path;
use crate::fixture_reads::{FixtureReadError, read_corpus_fixture};
use crate::golden_ir::{ByteSpan, GoldenBody, GoldenDocument, GoldenRegion, Segment};

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
