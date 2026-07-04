//! Structured logs and metrics for the Python docstring extraction boundary.
//!
//! The extractor is a library, so it only emits `tracing` events and `metrics`
//! counters; installing subscribers or recorders is left to the host binary.

use stilyagi_ir::IrDocument;

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
    if !document.errors.is_empty() {
        metrics::counter!("stilyagi_python_extraction_recovery_errors_total")
            .increment(document.errors.len() as u64);
        tracing::warn!(
            recovery_error_count = document.errors.len(),
            "python docstring extraction recovered from parse anomalies"
        );
    }
    tracing::debug!(
        region_count = document.regions.len(),
        node_count = document.nodes.len(),
        "python docstring extraction completed"
    );
}
