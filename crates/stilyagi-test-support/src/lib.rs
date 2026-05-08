//! Shared helpers for Rust tests that need repository-local fixtures.

use std::ffi::OsStr;
use std::path::{Component, Path, PathBuf};

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
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let crates_dir = manifest_dir
        .parent()
        .expect("failed to determine crate parent from CARGO_MANIFEST_DIR");
    assert_eq!(
        crates_dir.file_name(),
        Some(OsStr::new("crates")),
        "CARGO_MANIFEST_DIR layout drift: expected crate to be nested directly under repository crates/ directory"
    );
    crates_dir
        .parent()
        .expect("failed to determine repository root from CARGO_MANIFEST_DIR")
        .to_path_buf()
}

/// Return an absolute path for a repository-relative corpus fixture.
///
/// # Panics
///
/// Panics if `CARGO_MANIFEST_DIR` does not resolve to a crate nested directly
/// under the repository's `crates/` directory (i.e. when `repository_root`
/// panics).
#[must_use]
pub fn corpus_fixture_path(relative_path: impl AsRef<Path>) -> PathBuf {
    let path = relative_path.as_ref();
    assert!(
        !path.is_absolute(),
        "corpus fixture path must be repository-relative"
    );
    assert!(
        !path
            .components()
            .any(|component| component == Component::ParentDir),
        "corpus fixture path must not contain parent-directory traversal"
    );
    assert!(
        !path
            .components()
            .any(|component| matches!(component, Component::Prefix(_))),
        "corpus fixture path must not contain a drive or path prefix"
    );
    repository_root().join(path)
}

/// Read a repository-relative corpus fixture as UTF-8 text.
///
/// # Errors
///
/// Returns the filesystem error if the fixture cannot be read.
pub fn read_corpus_fixture(relative_path: impl AsRef<Path>) -> Result<String, std::io::Error> {
    std::fs::read_to_string(corpus_fixture_path(relative_path))
}
