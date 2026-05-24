//! Dev-only helpers providing centralised repository-relative fixture access for
//! `stilyagi-extract` and `stilyagi-pyext` tests via [`repository_root`],
//! [`corpus_fixture_path`], [`read_corpus_fixture`],
//! [`golden_markdown_ir_fixture`], [`apply_round_trip_edits`], and
//! [`SHARED_MARKDOWN_FIXTURE_PATH`].

mod golden_ir;

use std::ffi::OsStr;
use std::path::{Component, Path, PathBuf};

use stilyagi_ir::line_index_for;

pub use golden_ir::{ByteSpan, GoldenBody, GoldenDocument, GoldenRegion, Segment, SpanError};

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
    fn new(path: &Path, kind: FixturePathErrorKind) -> Self {
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

/// Read a repository-relative corpus fixture as UTF-8 text.
///
/// # Errors
///
/// Returns an error if the fixture path is invalid or cannot be read.
pub fn read_corpus_fixture(relative_path: impl AsRef<Path>) -> Result<String, FixtureReadError> {
    let path = corpus_fixture_path(relative_path)?;
    Ok(std::fs::read_to_string(path)?)
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

/// Return a repository-relative path using `/` separators for snapshots.
///
/// # Errors
///
/// Returns an error when the path is absolute or contains traversal, root, or
/// prefix components.
pub fn normalize_repository_path(input_path: impl AsRef<Path>) -> Result<String, FixturePathError> {
    let repository_path = input_path.as_ref();
    validate_repository_path(repository_path)?;

    let normalized = repository_path
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
        })?
        .join("/");

    Ok(normalized)
}

fn validate_repository_path(path: &Path) -> Result<(), FixturePathError> {
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

/// One edit used by the internal round-trip test helper.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RoundTripEdit {
    /// Replace a source-backed byte span with new text.
    Source {
        /// Editable byte range.
        span: ByteSpan,
        /// Replacement text.
        replacement: String,
    },
    /// Attempt to replace synthetic text, which must always be rejected.
    Synthetic {
        /// Synthetic text label for diagnostics.
        text: String,
        /// Replacement text requested by the caller.
        replacement: String,
    },
}

impl RoundTripEdit {
    /// Create a source-backed edit.
    #[must_use]
    pub fn source(start: usize, end: usize, replacement: impl Into<String>) -> Self {
        Self::Source {
            span: ByteSpan::new_unchecked(start, end),
            replacement: replacement.into(),
        }
    }

    /// Create a synthetic edit.
    #[must_use]
    pub fn synthetic(text: impl Into<String>, replacement: impl Into<String>) -> Self {
        Self::Synthetic {
            text: text.into(),
            replacement: replacement.into(),
        }
    }
}

/// Failure raised by the internal edit round-trip helper.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RoundTripEditError {
    /// A source edit range is malformed or outside the source length.
    InvalidSpan {
        /// Invalid span.
        span: ByteSpan,
        /// Source byte length.
        source_len: usize,
    },
    /// An edit targets synthetic text that has no source span.
    SyntheticSpan {
        /// Synthetic text label.
        text: String,
    },
    /// Two source edits overlap and would make the final text ambiguous.
    OverlappingEdits {
        /// Earlier edit span after stable sorting.
        previous: ByteSpan,
        /// Later edit span after stable sorting.
        current: ByteSpan,
    },
    /// A source edit does not begin and end on valid UTF-8 boundaries.
    NonUtf8Boundary {
        /// Invalid span.
        span: ByteSpan,
    },
}

impl std::fmt::Display for RoundTripEditError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidSpan { span, source_len } => write!(
                formatter,
                "invalid edit span {}..{} for source length {source_len}",
                span.start(),
                span.end()
            ),
            Self::SyntheticSpan { text } => {
                write!(formatter, "cannot edit synthetic segment {text:?}")
            }
            Self::OverlappingEdits { previous, current } => write!(
                formatter,
                "overlapping edit spans {}..{} and {}..{}",
                previous.start(),
                previous.end(),
                current.start(),
                current.end()
            ),
            Self::NonUtf8Boundary { span } => {
                write!(
                    formatter,
                    "edit span {}..{} is not UTF-8 aligned",
                    span.start(),
                    span.end()
                )
            }
        }
    }
}

impl std::error::Error for RoundTripEditError {}

/// Successful result from applying round-trip edits.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RoundTripEditResult {
    /// Source before edits.
    pub before: String,
    /// Source after edits.
    pub after: String,
    /// Source-backed edits in application order.
    pub applied_edits: Vec<RoundTripEdit>,
}

/// Apply source-backed edits while preserving all untouched source ranges.
///
/// # Errors
///
/// Returns an error when an edit targets synthetic text, uses an invalid byte
/// span, uses a non-UTF-8 boundary, or overlaps another edit.
pub fn apply_round_trip_edits(
    source: &str,
    edits: &[RoundTripEdit],
) -> Result<RoundTripEditResult, RoundTripEditError> {
    let source_edits = sorted_source_edits(source, edits)?;
    let after = apply_source_edits(source, &source_edits)?;
    let applied_edits = round_trip_edits(source_edits);

    Ok(RoundTripEditResult {
        before: source.to_owned(),
        after,
        applied_edits,
    })
}

fn sorted_source_edits(
    source: &str,
    edits: &[RoundTripEdit],
) -> Result<Vec<(ByteSpan, String)>, RoundTripEditError> {
    let mut source_edits = Vec::new();
    for edit in edits {
        match edit {
            RoundTripEdit::Source { span, replacement } => {
                validate_source_span(source, *span)?;
                source_edits.push((*span, replacement.clone()));
            }
            RoundTripEdit::Synthetic { text, .. } => {
                return Err(RoundTripEditError::SyntheticSpan { text: text.clone() });
            }
        }
    }

    source_edits.sort_by_key(|(span, _replacement)| (span.start(), span.end()));
    reject_overlaps(&source_edits)?;
    Ok(source_edits)
}

fn apply_source_edits(
    source: &str,
    source_edits: &[(ByteSpan, String)],
) -> Result<String, RoundTripEditError> {
    let mut after = String::new();
    let mut cursor = 0;
    for (span, replacement) in source_edits {
        after.push_str(utf8_slice(source, cursor, span.start())?);
        after.push_str(replacement);
        cursor = span.end();
    }
    after.push_str(utf8_slice(source, cursor, source.len())?);
    Ok(after)
}

fn round_trip_edits(source_edits: Vec<(ByteSpan, String)>) -> Vec<RoundTripEdit> {
    source_edits
        .into_iter()
        .map(|(span, replacement)| RoundTripEdit::Source { span, replacement })
        .collect()
}

fn utf8_slice(source: &str, start: usize, end: usize) -> Result<&str, RoundTripEditError> {
    let span = ByteSpan::new_unchecked(start, end);
    source
        .get(start..end)
        .ok_or(RoundTripEditError::NonUtf8Boundary { span })
}

fn validate_source_span(source: &str, span: ByteSpan) -> Result<(), RoundTripEditError> {
    if span.start() > span.end() || span.end() > source.len() {
        return Err(RoundTripEditError::InvalidSpan {
            span,
            source_len: source.len(),
        });
    }
    if !source.is_char_boundary(span.start()) || !source.is_char_boundary(span.end()) {
        return Err(RoundTripEditError::NonUtf8Boundary { span });
    }
    Ok(())
}

fn reject_overlaps(edits: &[(ByteSpan, String)]) -> Result<(), RoundTripEditError> {
    for pair in edits.windows(2) {
        let Some((previous, current)) = pair.first().zip(pair.get(1)) else {
            continue;
        };
        if previous.0.end() > current.0.start() {
            return Err(RoundTripEditError::OverlappingEdits {
                previous: previous.0,
                current: current.0,
            });
        }
    }
    Ok(())
}
