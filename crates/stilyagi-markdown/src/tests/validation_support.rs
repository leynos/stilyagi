//! Shared helpers for `validate_ir_consistency` regression tests.
//!
//! Both the IR consistency and segment validation suites build the same tiny
//! Markdown document, corrupt it, and inspect the resulting diagnostic. The
//! fallible builders here perform the command half of that shape and return the
//! extracted diagnostic data; the [`assert_validation_reports`] macro performs
//! the query half so panic line numbers point at the calling test.

use std::fmt;
use std::path::Path;

use markdown::message::Message;
use stilyagi_ir::{IrDocument, IrRegion, IrSegment};

use super::source_identity;
use crate::{MarkdownDiagnosticContext, markdown_ir_document, validate_ir_consistency};

/// Markdown source shared by every validation regression test.
const VALIDATION_SOURCE: &str = "# Heading\n\nBody";

/// Diagnostic context shared by the validation regression tests.
pub(super) const fn diagnostic_context() -> MarkdownDiagnosticContext<'static> {
    MarkdownDiagnosticContext {
        phase: "validate",
        path: "docs/example.md",
        uri: "file:///repo/docs/example.md",
    }
}

/// Failure modes encountered while preparing a validation regression case.
#[derive(Debug)]
pub(super) enum ValidationSupportFailure {
    /// The pristine Markdown document could not be built.
    Document(Box<Message>),
    /// The document held no region to corrupt.
    MissingRegion,
    /// The first region held no segment to corrupt.
    MissingSegment,
    /// Validation unexpectedly accepted the corrupted document.
    UnexpectedSuccess,
}

impl fmt::Display for ValidationSupportFailure {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Document(error) => write!(formatter, "expected Markdown IR document: {error}"),
            Self::MissingRegion => formatter.write_str("expected at least one Markdown IR region"),
            Self::MissingSegment => {
                formatter.write_str("expected at least one source-backed segment")
            }
            Self::UnexpectedSuccess => formatter.write_str("expected a validation failure"),
        }
    }
}

/// Diagnostic data extracted from a rejected Markdown IR document.
#[derive(Debug)]
pub(super) struct ValidationFailure {
    /// Diagnostic source component.
    pub source: String,
    /// Diagnostic rule identifier.
    pub rule_id: String,
    /// Human-readable diagnostic reason.
    pub reason: String,
}

/// Build a valid Markdown IR document, corrupt it with `mutate`, and return the
/// diagnostic that `validate_ir_consistency` produced.
pub(super) fn validation_failure_for(
    mutate: impl FnOnce(&mut IrDocument),
) -> Result<ValidationFailure, ValidationSupportFailure> {
    validation_failure_for_fallible(|document| {
        mutate(document);
        Ok(())
    })
}

/// Corrupt the first region of an otherwise valid document and return the
/// resulting diagnostic.
pub(super) fn validation_failure_for_first_region(
    mutate_region: impl FnOnce(&mut IrRegion),
) -> Result<ValidationFailure, ValidationSupportFailure> {
    validation_failure_for_fallible(|document| {
        let region = document
            .regions
            .first_mut()
            .ok_or(ValidationSupportFailure::MissingRegion)?;
        mutate_region(region);
        Ok(())
    })
}

/// Corrupt the first segment of the first region and return the resulting
/// diagnostic.
pub(super) fn validation_failure_for_first_segment(
    mutate_segment: impl FnOnce(&mut IrSegment),
) -> Result<ValidationFailure, ValidationSupportFailure> {
    validation_failure_for_fallible(|document| {
        let segment = document
            .regions
            .first_mut()
            .and_then(|region| region.segments.first_mut())
            .ok_or(ValidationSupportFailure::MissingSegment)?;
        mutate_segment(segment);
        Ok(())
    })
}

fn validation_failure_for_fallible(
    mutate: impl FnOnce(&mut IrDocument) -> Result<(), ValidationSupportFailure>,
) -> Result<ValidationFailure, ValidationSupportFailure> {
    let mut document = markdown_ir_document(
        VALIDATION_SOURCE,
        source_identity(Path::new("docs/example.md")),
    )
    .map_err(|error| ValidationSupportFailure::Document(Box::new(error)))?;
    mutate(&mut document)?;
    let context = diagnostic_context();

    let result = validate_ir_consistency(&document, VALIDATION_SOURCE, &context);

    let Err(error) = result else {
        return Err(ValidationSupportFailure::UnexpectedSuccess);
    };
    Ok(ValidationFailure {
        source: error.source.as_ref().to_owned(),
        rule_id: error.rule_id.as_ref().to_owned(),
        reason: error.reason,
    })
}

/// Assert that a [`ValidationFailure`] names `expected_rule_id` and mentions
/// every fragment in `expected_reason_fragments`, plus the shared
/// `phase=validate` context.
macro_rules! assert_validation_reports {
    ($failure:expr, $expected_rule_id:expr, $expected_reason_fragments:expr $(,)?) => {{
        let failure = &$failure;
        assert_eq!(failure.source, "stilyagi-markdown");
        assert_eq!(failure.rule_id, $expected_rule_id);
        assert!(
            failure.reason.contains("phase=validate"),
            "reason {:?} is missing the validate phase context",
            failure.reason
        );
        for fragment in $expected_reason_fragments {
            assert!(
                failure.reason.contains(fragment),
                "reason {:?} is missing fragment {fragment:?}",
                failure.reason
            );
        }
    }};
}

pub(super) use assert_validation_reports;
