//! Dev-only helpers providing centralised repository-relative fixture access for
//! `stilyagi-extract` and `stilyagi-pyext` tests via [`repository_root`],
//! [`corpus_fixture_path`], [`read_corpus_fixture`],
//! [`golden_markdown_ir_fixture`], [`apply_round_trip_edits`], and
//! [`SHARED_MARKDOWN_FIXTURE_PATH`].

use std::ffi::OsStr;
use std::path::{Component, Path, PathBuf};

use stilyagi_ir::{ByteSpan, GoldenBody, GoldenDocument, GoldenRegion, Segment, line_index_for};

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
/// Panics if any of the following conditions hold:
///
/// - `relative_path` is absolute (`is_absolute()` returns `true`).
/// - `relative_path` contains a parent-directory component (`..`).
/// - `relative_path` contains a drive or path prefix (Windows `C:` etc.).
/// - `relative_path` is root-relative (starts with `\` on Windows without a
///   drive letter, i.e. contains [`Component::RootDir`]).
/// - `CARGO_MANIFEST_DIR` does not resolve to a crate nested directly under the
///   repository's `crates/` directory (i.e. [`repository_root`] panics).
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
    assert!(
        !path
            .components()
            .any(|component| component == Component::RootDir),
        "corpus fixture path must not be root-relative"
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

/// Build the private golden IR shape for a supported Markdown corpus fixture.
///
/// # Errors
///
/// Returns the filesystem error if the fixture cannot be read.
pub fn golden_markdown_ir_fixture(
    relative_path: impl AsRef<Path>,
) -> Result<GoldenDocument, std::io::Error> {
    let path = relative_path.as_ref();
    let source = read_corpus_fixture(path)?;
    let fixture = normalize_repository_path(path);
    let regions = if source.trim().is_empty() {
        Vec::new()
    } else {
        vec![GoldenRegion::new(
            "document",
            source.clone(),
            vec![Segment::source(
                ByteSpan::new(0, source.len()),
                source.clone(),
            )],
        )]
    };

    Ok(GoldenDocument::new(
        fixture,
        "markdown",
        GoldenBody {
            line_index: line_index_for(&source),
            regions,
            diagnostics: Vec::new(),
        },
    ))
}

/// Return a repository-relative path using `/` separators for snapshots.
#[must_use]
pub fn normalize_repository_path(path: impl AsRef<Path>) -> String {
    path.as_ref()
        .components()
        .filter_map(|component| match component {
            Component::Normal(part) => Some(part.to_string_lossy().into_owned()),
            Component::CurDir
            | Component::Prefix(_)
            | Component::RootDir
            | Component::ParentDir => None,
        })
        .collect::<Vec<_>>()
        .join("/")
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
            span: ByteSpan::new(start, end),
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
                span.start, span.end
            ),
            Self::SyntheticSpan { text } => {
                write!(formatter, "cannot edit synthetic segment {text:?}")
            }
            Self::OverlappingEdits { previous, current } => write!(
                formatter,
                "overlapping edit spans {}..{} and {}..{}",
                previous.start, previous.end, current.start, current.end
            ),
            Self::NonUtf8Boundary { span } => {
                write!(
                    formatter,
                    "edit span {}..{} is not UTF-8 aligned",
                    span.start, span.end
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

    source_edits.sort_by_key(|(span, _replacement)| (span.start, span.end));
    reject_overlaps(&source_edits)?;

    let mut after = String::new();
    let mut cursor = 0;
    for (span, replacement) in &source_edits {
        after.push_str(utf8_slice(source, cursor, span.start)?);
        after.push_str(replacement);
        cursor = span.end;
    }
    after.push_str(utf8_slice(source, cursor, source.len())?);

    let applied_edits = source_edits
        .into_iter()
        .map(|(span, replacement)| RoundTripEdit::Source { span, replacement })
        .collect();

    Ok(RoundTripEditResult {
        before: source.to_owned(),
        after,
        applied_edits,
    })
}

fn utf8_slice(source: &str, start: usize, end: usize) -> Result<&str, RoundTripEditError> {
    let span = ByteSpan::new(start, end);
    source
        .get(start..end)
        .ok_or(RoundTripEditError::NonUtf8Boundary { span })
}

fn validate_source_span(source: &str, span: ByteSpan) -> Result<(), RoundTripEditError> {
    if span.start > span.end || span.end > source.len() {
        return Err(RoundTripEditError::InvalidSpan {
            span,
            source_len: source.len(),
        });
    }
    if !source.is_char_boundary(span.start) || !source.is_char_boundary(span.end) {
        return Err(RoundTripEditError::NonUtf8Boundary { span });
    }
    Ok(())
}

fn reject_overlaps(edits: &[(ByteSpan, String)]) -> Result<(), RoundTripEditError> {
    for pair in edits.windows(2) {
        let Some((previous, current)) = pair.first().zip(pair.get(1)) else {
            continue;
        };
        if previous.0.end > current.0.start {
            return Err(RoundTripEditError::OverlappingEdits {
                previous: previous.0,
                current: current.0,
            });
        }
    }
    Ok(())
}
