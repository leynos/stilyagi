//! Repository-relative fixture path validation and normalization helpers.
//! Callers must pass paths that name a fixture within the repository, without
//! absolute roots, platform prefixes, parent traversal, empty components, or
//! current-directory-only inputs. The functions in this module either return a
//! normalized repository-relative path or a typed rejection reason, so fixture
//! readers never silently escape the repository boundary.

use std::ffi::OsStr;
use std::path::{Component, Path, PathBuf};

/// Repository-relative path to the shared valid Markdown corpus fixture.
pub const SHARED_MARKDOWN_FIXTURE_PATH: &str =
    "tests/fixtures/corpus/markdown/valid/heading-table-link-suppression.md";

/// Failure raised when a fixture path is not repository-relative.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FixturePathError {
    /// Rejected path rendered for diagnostics.
    pub path: String,
    /// Validation rule that rejected the path.
    pub kind: FixturePathErrorKind,
}

impl FixturePathError {
    pub(crate) fn new(path: &Path, kind: FixturePathErrorKind) -> Self {
        Self {
            path: path.display().to_string(),
            kind,
        }
    }
}

impl std::fmt::Display for FixturePathError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self.kind {
            FixturePathErrorKind::Absolute => {
                write!(
                    formatter,
                    "fixture path must be repository-relative: {}",
                    self.path
                )
            }
            FixturePathErrorKind::ParentTraversal => write!(
                formatter,
                "fixture path must not contain parent-directory traversal: {}",
                self.path
            ),
            FixturePathErrorKind::Prefix => {
                write!(
                    formatter,
                    "fixture path must not contain a drive or path prefix: {}",
                    self.path
                )
            }
            FixturePathErrorKind::RootRelative => {
                write!(
                    formatter,
                    "fixture path must not be root-relative: {}",
                    self.path
                )
            }
            FixturePathErrorKind::EmptyComponent => write!(
                formatter,
                "fixture path must not contain empty, current, or parent path components: {}",
                self.path
            ),
        }
    }
}

impl std::error::Error for FixturePathError {}

/// Rejection reason for an invalid fixture path.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FixturePathErrorKind {
    /// Path is absolute.
    Absolute,
    /// Path contains `..`.
    ParentTraversal,
    /// Path contains a drive or other path prefix.
    Prefix,
    /// Path is root-relative.
    RootRelative,
    /// Path contains an invalid normal component after separator normalization.
    EmptyComponent,
}

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
/// # Errors
///
/// Returns an error when `relative_path` is absolute or contains traversal,
/// root, or prefix components.
pub fn corpus_fixture_path(relative_path: impl AsRef<Path>) -> Result<PathBuf, FixturePathError> {
    let path = relative_path.as_ref();
    validate_repository_path(path)?;
    Ok(repository_root().join(path))
}

/// Return a repository-relative path using `/` separators for snapshots.
///
/// # Errors
///
/// Returns an error when the path is absolute or contains traversal, root, or
/// prefix components.
pub fn normalize_repository_path(input_path: impl AsRef<Path>) -> Result<String, FixturePathError> {
    let repository_path = input_path.as_ref();
    validate_repository_path(repository_path)?;

    let parts = repository_path
        .components()
        .try_fold(Vec::new(), |mut parts, component| {
            match component {
                Component::Normal(path_part) => {
                    for normalized_part in path_part.to_string_lossy().split('\\') {
                        if matches!(normalized_part, "" | "." | "..") {
                            return Err(FixturePathError::new(
                                repository_path,
                                FixturePathErrorKind::EmptyComponent,
                            ));
                        }
                        parts.push(normalized_part.to_owned());
                    }
                }
                Component::CurDir => {}
                Component::ParentDir => {
                    return Err(FixturePathError::new(
                        repository_path,
                        FixturePathErrorKind::ParentTraversal,
                    ));
                }
                Component::RootDir => {
                    return Err(FixturePathError::new(
                        repository_path,
                        FixturePathErrorKind::RootRelative,
                    ));
                }
                Component::Prefix(_) => {
                    return Err(FixturePathError::new(
                        repository_path,
                        FixturePathErrorKind::Prefix,
                    ));
                }
            }
            Ok(parts)
        })?;
    if parts.is_empty() {
        return Err(FixturePathError::new(
            repository_path,
            FixturePathErrorKind::EmptyComponent,
        ));
    }

    Ok(parts.join("/"))
}

pub(crate) fn validate_repository_path(path: &Path) -> Result<(), FixturePathError> {
    if path.is_absolute() {
        return Err(FixturePathError::new(path, FixturePathErrorKind::Absolute));
    }
    for component in path.components() {
        match component {
            Component::ParentDir => {
                return Err(FixturePathError::new(
                    path,
                    FixturePathErrorKind::ParentTraversal,
                ));
            }
            Component::RootDir => {
                return Err(FixturePathError::new(
                    path,
                    FixturePathErrorKind::RootRelative,
                ));
            }
            Component::Prefix(_) => {
                return Err(FixturePathError::new(path, FixturePathErrorKind::Prefix));
            }
            Component::Normal(_) | Component::CurDir => {}
        }
    }
    Ok(())
}
