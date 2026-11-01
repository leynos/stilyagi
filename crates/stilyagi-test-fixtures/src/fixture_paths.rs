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

/// Repository-relative path to the shared valid Python docstring fixture.
pub const SHARED_PYTHON_FIXTURE_PATH: &str =
    "tests/fixtures/corpus/python/valid/module-class-function-docstrings.py";

/// Repository-relative path to the shared valid Rust doc-comment fixture.
pub const SHARED_RUST_FIXTURE_PATH: &str = "tests/fixtures/corpus/rust/valid/item-doc-comments.rs";

/// Repository-relative path to the Rust fixture that interleaves attributes and doc comments.
pub const ATTRIBUTE_RUST_FIXTURE_PATH: &str =
    "tests/fixtures/corpus/rust/valid/item-doc-comments-with-attributes.rs";

/// Repository-relative path to the malformed Python docstring fixture.
pub const MALFORMED_PYTHON_FIXTURE_PATH: &str =
    "tests/fixtures/corpus/python/malformed/unclosed-function.py.txt";

/// Repository-relative path to the malformed Rust doc-comment fixture.
pub const MALFORMED_RUST_FIXTURE_PATH: &str =
    "tests/fixtures/corpus/rust/malformed/unclosed-item.rs";

/// Repository-relative path to the nested-declarations Python docstring fixture.
pub const NESTED_PYTHON_FIXTURE_PATH: &str =
    "tests/fixtures/corpus/python/valid/nested-declarations.py";

/// Repository-relative path to the nested Rust doc-comment fixture.
pub const NESTED_RUST_FIXTURE_PATH: &str =
    "tests/fixtures/corpus/rust/valid/nested-modules-impls.rs";

/// Repository-relative path to the docstring edge-cases Python fixture.
pub const EDGE_CASE_PYTHON_FIXTURE_PATH: &str =
    "tests/fixtures/corpus/python/valid/docstring-edge-cases.py";

/// Repository-relative path to the multiline Rust doc-comment fixture.
pub const MULTILINE_RUST_FIXTURE_PATH: &str =
    "tests/fixtures/corpus/rust/valid/doc-comment-multiline.rs";

/// Failure raised when fixture paths or the fixture crate layout are invalid.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FixturePathError {
    /// Rejected path rendered for diagnostics.
    pub path: String,
    /// Validation rule that rejected the path.
    pub kind: FixturePathErrorKind,
}

impl FixturePathError {
    /// Build a typed fixture rejection while preserving the offending path.
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
            FixturePathErrorKind::RepositoryLayout => write!(
                formatter,
                "crate manifest directory must be nested under repository crates/: {}",
                self.path
            ),
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

/// Rejection reason for an invalid fixture path or crate layout.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FixturePathErrorKind {
    /// The crate manifest directory does not follow the repository layout.
    RepositoryLayout,
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
/// # Errors
///
/// Returns [`FixturePathErrorKind::RepositoryLayout`] when `CARGO_MANIFEST_DIR`
/// does not identify a crate directly under the repository's `crates/` directory.
///
/// # Examples
///
/// ```
/// let root = stilyagi_test_fixtures::repository_root()?;
/// assert!(root.is_absolute());
/// # Ok::<(), stilyagi_test_fixtures::FixturePathError>(())
/// ```
pub fn repository_root() -> Result<PathBuf, FixturePathError> {
    repository_root_from_manifest(Path::new(env!("CARGO_MANIFEST_DIR")))
}

/// Resolve the test-fixture repository layout without accessing the filesystem.
fn repository_root_from_manifest(manifest_dir: &Path) -> Result<PathBuf, FixturePathError> {
    manifest_dir
        .parent()
        .filter(|directory| directory.file_name() == Some(OsStr::new("crates")))
        .and_then(Path::parent)
        .map(Path::to_path_buf)
        .ok_or_else(|| FixturePathError::new(manifest_dir, FixturePathErrorKind::RepositoryLayout))
}

/// Return an absolute path for a repository-relative corpus fixture.
///
/// # Errors
///
/// Returns an error when `relative_path` is absolute or contains traversal,
/// root, or prefix components, or when the crate manifest directory violates
/// the repository layout.
pub fn corpus_fixture_path(relative_path: impl AsRef<Path>) -> Result<PathBuf, FixturePathError> {
    let path = relative_path.as_ref();
    validate_repository_path(path)?;
    Ok(repository_root()?.join(path))
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
                    push_normalized_path_parts(&mut parts, path_part, repository_path)?;
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

/// Append normalized components, rejecting empty or traversal segments.
fn push_normalized_path_parts(
    parts: &mut Vec<String>,
    path_part: &std::ffi::OsStr,
    repository_path: &Path,
) -> Result<(), FixturePathError> {
    for normalized_part in path_part.to_string_lossy().split('\\') {
        if matches!(normalized_part, "" | "." | "..") {
            return Err(FixturePathError::new(
                repository_path,
                FixturePathErrorKind::EmptyComponent,
            ));
        }
        parts.push(normalized_part.to_owned());
    }
    Ok(())
}

/// Reject absolute paths and components that can escape the repository.
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

#[cfg(test)]
mod tests {
    //! Verify the fixture manifest-layout boundary independently of Cargo.

    use super::{FixturePathErrorKind, repository_root_from_manifest};
    use std::path::Path;

    #[test]
    fn resolves_repository_from_a_direct_crates_child() {
        assert_eq!(
            repository_root_from_manifest(Path::new("repository/crates/fixture-package"))
                .expect("a direct crates child should resolve its repository"),
            Path::new("repository")
        );
    }

    #[test]
    fn rejects_manifest_directories_outside_the_crates_layout() {
        for manifest_dir in ["", "fixture-package", "repository/packages/fixture-package"] {
            let error = repository_root_from_manifest(Path::new(manifest_dir))
                .expect_err("an invalid manifest layout should return an error");
            assert_eq!(error.kind, FixturePathErrorKind::RepositoryLayout);
            assert_eq!(error.path, manifest_dir);
        }
    }
}
