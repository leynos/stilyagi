//! Structured logs and metrics for the Python docstring extraction boundary.
//!
//! The extractor is a library, so it only emits `tracing` events and `metrics`
//! counters; installing subscribers or recorders is left to the host binary.

use stilyagi_ir::{AUTHORED_DIRECTIVE_ERROR_CODES, IrDocument, IrError};

use super::PythonExtractError;

/// Emit a log and metric for a fatal extraction failure at the parse boundary.
pub(super) fn record_fatal_error(error: PythonExtractError) {
    metrics::counter!(
        "stilyagi_python_extraction_fatal_errors_total",
        "category" => error.category()
    )
    .increment(1);
    tracing::error!(
        category = error.category(),
        error = %error,
        "python docstring extraction failed before IR construction"
    );
}

/// Emit logs and metrics summarising a completed extraction, including any
/// recoverable parse anomalies surfaced through the IR `errors` list.
pub(super) fn record_extraction_outcome(document: &IrDocument) {
    let recovery_error_count = recovery_error_count(&document.errors);
    if recovery_error_count > 0 {
        metrics::counter!("stilyagi_python_extraction_recovery_errors_total")
            .increment(recovery_error_count as u64);
        tracing::warn!(
            recovery_error_count,
            "python docstring extraction recovered from parse anomalies"
        );
    }
    tracing::debug!(
        region_count = document.regions.len(),
        node_count = document.nodes.len(),
        "python docstring extraction completed"
    );
}

fn recovery_error_count(errors: &[IrError]) -> usize {
    errors
        .iter()
        .filter(|error| !AUTHORED_DIRECTIVE_ERROR_CODES.contains(&error.code.as_str()))
        .count()
}

#[cfg(test)]
mod tests {
    //! Tests for authored-directive exclusion from parser recovery metrics.

    use stilyagi_ir::{AUTHORED_DIRECTIVE_ERROR_CODES, IrError};

    use super::recovery_error_count;

    fn error(code: &str) -> IrError {
        IrError {
            code: code.to_owned(),
            message: String::new(),
            span: None,
        }
    }

    #[test]
    fn authored_only_errors_do_not_count_as_recovery() {
        let errors = AUTHORED_DIRECTIVE_ERROR_CODES
            .iter()
            .map(|code| error(code))
            .collect::<Vec<_>>();

        assert_eq!(recovery_error_count(&errors), 0);
    }

    #[test]
    fn extraction_anomalies_count_as_recovery() {
        let errors = [error("python-parse-recovery")];

        assert_eq!(recovery_error_count(&errors), 1);
    }

    #[test]
    fn mixed_errors_count_only_extraction_anomalies() {
        let errors = [
            error("suppression-blanket-forbidden"),
            error("python-parse-recovery"),
        ];

        assert_eq!(recovery_error_count(&errors), 1);
    }
}
