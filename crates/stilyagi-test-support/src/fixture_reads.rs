use std::path::Path;

use crate::fixture_paths::{FixturePathError, corpus_fixture_path};

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
    let path = corpus_fixture_path(relative_path)?;
    Ok(std::fs::read_to_string(path)?)
}
