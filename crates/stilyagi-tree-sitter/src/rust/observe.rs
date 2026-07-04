//! Observability hooks for Rust doc-comment extraction.

use stilyagi_ir::IrDocument;

/// Record a fatal Rust extraction error.
pub(super) fn record_fatal_error(error: super::RustExtractError) {
    metrics::counter!(
        "stilyagi_rust_extraction_fatal_errors_total",
        "category" => error.category()
    )
    .increment(1);
    tracing::error!(
        category = error.category(),
        error = %error,
        "rust doc-comment extraction failed before IR construction"
    );
}

/// Record the successful Rust extraction outcome.
pub(super) fn record_extraction_outcome(document: &IrDocument) {
    if !document.errors.is_empty() {
        metrics::counter!("stilyagi_rust_extraction_recovery_errors_total")
            .increment(document.errors.len() as u64);
        tracing::warn!(
            recovery_error_count = document.errors.len(),
            "rust doc-comment extraction recovered from parse anomalies"
        );
    }
    tracing::debug!(
        region_count = document.regions.len(),
        node_count = document.nodes.len(),
        "rust doc-comment extraction completed"
    );
}
