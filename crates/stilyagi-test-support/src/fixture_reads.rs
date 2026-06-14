//! Fixture I/O helpers for reading repository test fixtures. This module
//! composes with [`crate::fixture_paths::corpus_fixture_path`] so all reads
//! validate repository-relative paths first and surface
//! [`crate::fixture_paths::FixturePathError`] through [`FixtureReadError`].

use std::path::{Path, PathBuf};

use cap_std::{ambient_authority, fs::Dir};

use crate::fixture_paths::{FixturePathError, normalize_repository_path};

/// Failure raised when reading a corpus fixture.
#[derive(Debug)]
pub enum FixtureReadError {
    /// The requested repository-relative path was invalid.
    InvalidPath(FixturePathError),
    /// The fixture could not be read from disk.
    Io(std::io::Error),
}

impl std::fmt::Display for FixtureReadError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidPath(error) => write!(formatter, "{error}"),
            Self::Io(error) => write!(formatter, "{error}"),
        }
    }
}

impl std::error::Error for FixtureReadError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::InvalidPath(error) => Some(error),
            Self::Io(error) => Some(error),
        }
    }
}

impl From<FixturePathError> for FixtureReadError {
    fn from(error: FixturePathError) -> Self {
        Self::InvalidPath(error)
    }
}

impl From<std::io::Error> for FixtureReadError {
    fn from(error: std::io::Error) -> Self {
        Self::Io(error)
    }
}

/// Read a repository-relative corpus fixture as UTF-8 text.
///
/// # Errors
///
/// Returns an error if the fixture path is invalid or cannot be read.
pub fn read_corpus_fixture(relative_path: impl AsRef<Path>) -> Result<String, FixtureReadError> {
    let path = normalize_repository_path(relative_path)?;
    let repository =
        Dir::open_ambient_dir(crate::fixture_paths::repository_root(), ambient_authority())?;
    Ok(repository.read_to_string(path)?)
}

/// Read a repository-relative corpus fixture as raw bytes.
///
/// # Errors
///
/// Returns an error if the fixture path is invalid or cannot be read.
pub fn read_corpus_fixture_bytes(
    relative_path: impl AsRef<Path>,
) -> Result<Vec<u8>, FixtureReadError> {
    let path = normalize_repository_path(relative_path)?;
    let repository =
        Dir::open_ambient_dir(crate::fixture_paths::repository_root(), ambient_authority())?;
    Ok(repository.read(path)?)
}

/// List entries in a repository-relative fixture directory.
///
/// # Errors
///
/// Returns an error if the directory path is invalid or cannot be read.
pub fn fixture_paths_in(relative_dir: impl AsRef<Path>) -> Result<Vec<String>, FixtureReadError> {
    let directory = normalize_repository_path(relative_dir)?;
    let repository =
        Dir::open_ambient_dir(crate::fixture_paths::repository_root(), ambient_authority())?;
    let mut paths = Vec::new();
    for entry_result in repository.read_dir(&directory)? {
        let entry = entry_result?;
        let mut path = PathBuf::from(&directory);
        path.push(entry.file_name());
        paths.push(normalize_repository_path(path)?);
    }
    Ok(paths)
}
