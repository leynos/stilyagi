//! Shared helpers for Rust tests that need repository-local fixtures.

use std::path::{Path, PathBuf};

/// Repository-relative path to the shared valid Markdown corpus fixture.
pub const SHARED_MARKDOWN_FIXTURE_PATH: &str =
    "tests/fixtures/corpus/markdown/valid/heading-table-link-suppression.md";

/// Return the repository root for workspace tests.
///
/// # Panics
///
/// Panics if `CARGO_MANIFEST_DIR` does not resolve to a crate nested directly
/// under the repository's `crates/` directory.
#[must_use]
#[expect(
    clippy::expect_used,
    reason = "test helper should fail loudly when crate layout assumptions break"
)]
pub fn repository_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .expect("failed to determine repository root from CARGO_MANIFEST_DIR")
        .to_path_buf()
}

/// Return an absolute path for a repository-relative corpus fixture.
#[must_use]
pub fn corpus_fixture_path(relative_path: impl AsRef<Path>) -> PathBuf {
    repository_root().join(relative_path)
}

/// Read a repository-relative corpus fixture as UTF-8 text.
///
/// # Errors
///
/// Returns the filesystem error if the fixture cannot be read.
pub fn read_corpus_fixture(relative_path: impl AsRef<Path>) -> Result<String, std::io::Error> {
    std::fs::read_to_string(corpus_fixture_path(relative_path))
}
