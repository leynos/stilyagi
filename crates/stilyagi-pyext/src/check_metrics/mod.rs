//! Bounded in-process metrics for one Stilyagi check command.

mod recording_bindings;
mod snapshot;
pub(super) use recording_bindings::{
    record_check_run, record_checked_file, record_diagnostic_severity, record_operational_failure,
    record_phase_duration, record_projection_anomaly, record_skipped_candidates,
};
pub(super) use snapshot::check_metrics_snapshot;

#[cfg(test)]
static CHECK_METRICS_TEST_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

#[cfg(test)]
mod snapshot_tests;

use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use stilyagi_extract::{ExtractError, ExtractSyntax, PythonExtractError, RustExtractError};
use stilyagi_ir::{AUTHORED_DIRECTIVE_ERROR_CODES, IrError};

/// Per-outcome check run counts, indexed by `RUN_OUTCOMES`.
static CHECK_RUNS: [AtomicU64; 3] = [AtomicU64::new(0), AtomicU64::new(0), AtomicU64::new(0)];
/// Per-syntax checked file counts, indexed by `SYNTAXES`.
static CHECKED_FILES: [AtomicU64; 3] = [AtomicU64::new(0), AtomicU64::new(0), AtomicU64::new(0)];
/// Per-severity diagnostic counts, indexed by `DIAGNOSTIC_SEVERITIES`.
static DIAGNOSTIC_COUNTS: [AtomicU64; 2] = [AtomicU64::new(0), AtomicU64::new(0)];
/// Per-reason skipped candidate counts, indexed by `SKIP_REASONS`.
static SKIPPED_CANDIDATES: [AtomicU64; 3] =
    [AtomicU64::new(0), AtomicU64::new(0), AtomicU64::new(0)];
/// Count of candidate files that could not be read.
static UNREADABLE_FILES: AtomicU64 = AtomicU64::new(0);
/// Per-kind operational failure counts, indexed by `FAILURE_KINDS`.
static OPERATIONAL_FAILURES: [AtomicU64; 6] = [
    AtomicU64::new(0),
    AtomicU64::new(0),
    AtomicU64::new(0),
    AtomicU64::new(0),
    AtomicU64::new(0),
    AtomicU64::new(0),
];
/// Per-kind recoverable IR anomaly counts, indexed by `PROJECTION_ANOMALY_KINDS`.
static PROJECTION_ANOMALIES: [AtomicU64; 6] = [
    AtomicU64::new(0),
    AtomicU64::new(0),
    AtomicU64::new(0),
    AtomicU64::new(0),
    AtomicU64::new(0),
    AtomicU64::new(0),
];
/// Extraction attempt counts for Python (index 0) and Rust (index 1).
static EXTRACTION_DOCUMENTS: [AtomicU64; 2] = [AtomicU64::new(0), AtomicU64::new(0)];
/// Recovery error totals for Python (index 0) and Rust (index 1).
static EXTRACTION_RECOVERY_ERRORS: [AtomicU64; 2] = [AtomicU64::new(0), AtomicU64::new(0)];
/// Fatal extraction error counts: Python grammar load (0), Python no parse
/// tree (1), Rust grammar load (2), and Rust no parse tree (3).
static EXTRACTION_FATAL_ERRORS: [AtomicU64; 4] = [
    AtomicU64::new(0),
    AtomicU64::new(0),
    AtomicU64::new(0),
    AtomicU64::new(0),
];
/// Per-phase duration histograms, indexed by `PHASES`.
static PHASE_DURATIONS: [DurationHistogram; 7] = [
    DurationHistogram::new(),
    DurationHistogram::new(),
    DurationHistogram::new(),
    DurationHistogram::new(),
    DurationHistogram::new(),
    DurationHistogram::new(),
    DurationHistogram::new(),
];

/// Labels for `CHECK_RUNS`; the array index gives each counter meaning.
const RUN_OUTCOMES: [&str; 3] = ["success", "diagnostic_error", "operational_error"];
/// Labels for `CHECKED_FILES`; the array index gives each counter meaning.
const SYNTAXES: [&str; 3] = ["markdown", "python", "rust"];
/// Labels for `DIAGNOSTIC_COUNTS`; the array index gives each counter meaning.
const DIAGNOSTIC_SEVERITIES: [&str; 2] = ["error", "warning"];
/// Labels for `SKIPPED_CANDIDATES`; the array index gives each counter meaning.
const SKIP_REASONS: [&str; 3] = [
    "unregistered_candidate",
    "symlinked_directory_target",
    "unsupported_candidate_type",
];
/// Labels for `OPERATIONAL_FAILURES`; the array index gives each counter
/// meaning.
const FAILURE_KINDS: [&str; 6] = ["discovery", "read", "extract", "config", "rules", "render"];
/// Recoverable IR anomalies the rule projection tolerates, in label order.
const PROJECTION_ANOMALY_KINDS: [&str; 6] = [
    "malformed_node",
    "invalid_node_span",
    "malformed_region",
    "malformed_segment",
    "invalid_segment_span",
    "source_mismatch",
];
/// Labels for `PHASE_DURATIONS`; the array index gives each histogram meaning.
const PHASES: [&str; 7] = [
    "discovery",
    "read",
    "extract",
    "config",
    "rules",
    "render",
    "total",
];
/// Upper bounds, in ascending order, for the first four histogram buckets.
const BUCKET_LIMITS: [Duration; 4] = [
    Duration::from_micros(1_000),
    Duration::from_millis(10),
    Duration::from_millis(100),
    Duration::from_secs(1),
];
/// Prometheus-style bucket labels; the final `+Inf` bucket is unbounded.
const BUCKET_LABELS: [&str; 5] = ["0.001", "0.01", "0.1", "1", "+Inf"];

/// Fixed-bucket duration histogram; bucket counts are stored non-cumulatively
/// and summed when snapshotted.
struct DurationHistogram {
    /// Number of recorded observations.
    count: AtomicU64,
    /// Total observed duration in nanoseconds.
    sum_nanoseconds: AtomicU64,
    /// Per-bucket observation counts, indexed by `BUCKET_LIMITS` with a final
    /// overflow bucket.
    buckets: [AtomicU64; 5],
}

impl DurationHistogram {
    /// Create an empty histogram with every counter zeroed.
    const fn new() -> Self {
        Self {
            count: AtomicU64::new(0),
            sum_nanoseconds: AtomicU64::new(0),
            buckets: [
                AtomicU64::new(0),
                AtomicU64::new(0),
                AtomicU64::new(0),
                AtomicU64::new(0),
                AtomicU64::new(0),
            ],
        }
    }

    /// Record one observation in seconds, treating invalid or out-of-range
    /// values as `Duration::MAX`.
    fn record(&self, seconds: f64) {
        let duration = Duration::try_from_secs_f64(seconds).unwrap_or(Duration::MAX);
        let nanoseconds = u64::try_from(duration.as_nanos()).unwrap_or(u64::MAX);
        let bucket = BUCKET_LIMITS
            .iter()
            .position(|limit| duration <= *limit)
            .unwrap_or(BUCKET_LIMITS.len());
        self.count.fetch_add(1, Ordering::Relaxed);
        self.sum_nanoseconds
            .fetch_add(nanoseconds, Ordering::Relaxed);
        if let Some(bucket_count) = self.buckets.get(bucket) {
            bucket_count.fetch_add(1, Ordering::Relaxed);
        }
    }

    /// Reset every counter to zero.
    fn reset(&self) {
        self.count.store(0, Ordering::Relaxed);
        self.sum_nanoseconds.store(0, Ordering::Relaxed);
        for bucket in &self.buckets {
            bucket.store(0, Ordering::Relaxed);
        }
    }
}

/// Add `amount` to the counter whose label matches, ignoring unknown labels.
fn increment_counter(counters: &[AtomicU64], labels: &[&str], label: &str, amount: u64) {
    if let Some(counter) = labels
        .iter()
        .position(|candidate| *candidate == label)
        .and_then(|index| counters.get(index))
    {
        counter.fetch_add(amount, Ordering::Relaxed);
    }
}

/// Count an extraction attempt for the given syntax; Markdown is not tracked.
pub(super) fn record_extraction_attempt(syntax: ExtractSyntax) {
    match syntax {
        ExtractSyntax::PythonDocstring => {
            if let Some(counter) = EXTRACTION_DOCUMENTS.first() {
                counter.fetch_add(1, Ordering::Relaxed);
            }
        }
        ExtractSyntax::RustDocComment => {
            if let Some(counter) = EXTRACTION_DOCUMENTS.get(1) {
                counter.fetch_add(1, Ordering::Relaxed);
            }
        }
        ExtractSyntax::Markdown => {}
    }
}

/// Count IR errors that are not authored-directive errors.
pub(super) fn recovery_error_count(errors: &[IrError]) -> usize {
    errors
        .iter()
        .filter(|error| !AUTHORED_DIRECTIVE_ERROR_CODES.contains(&error.code.as_str()))
        .count()
}

/// Add the recovery error total for the given syntax; Markdown is not tracked.
pub(super) fn record_extraction_outcome(syntax: ExtractSyntax, recovery_errors: usize) {
    let recovery_error_count = u64::try_from(recovery_errors).unwrap_or(u64::MAX);
    let counters = match syntax {
        ExtractSyntax::PythonDocstring => EXTRACTION_RECOVERY_ERRORS.first(),
        ExtractSyntax::RustDocComment => EXTRACTION_RECOVERY_ERRORS.get(1),
        ExtractSyntax::Markdown => None,
    };
    if let Some(counter) = counters {
        counter.fetch_add(recovery_error_count, Ordering::Relaxed);
    }
}

/// Count a fatal extraction failure for the matching syntax and error kind;
/// other errors are ignored.
pub(super) fn record_extraction_failure(error: &ExtractError) {
    let failure_counter = match error {
        ExtractError::PythonIr(PythonExtractError::GrammarLoad) => EXTRACTION_FATAL_ERRORS.first(),
        ExtractError::PythonIr(PythonExtractError::NoParseTree) => EXTRACTION_FATAL_ERRORS.get(1),
        ExtractError::RustIr(RustExtractError::GrammarLoad) => EXTRACTION_FATAL_ERRORS.get(2),
        ExtractError::RustIr(RustExtractError::NoParseTree) => EXTRACTION_FATAL_ERRORS.get(3),
        ExtractError::UnsupportedSyntax(_)
        | ExtractError::UnknownSyntax(_)
        | ExtractError::MarkdownIr(_) => None,
    };
    if let Some(counter) = failure_counter {
        counter.fetch_add(1, Ordering::Relaxed);
    }
}

/// Return the canonical static label matching `value`, or a `ValueError`
/// naming `name`.
fn checked_label(value: &str, supported: &[&'static str], name: &str) -> PyResult<&'static str> {
    supported
        .iter()
        .copied()
        .find(|candidate| *candidate == value)
        .ok_or_else(|| PyValueError::new_err(format!("unsupported {name} metric label: {value}")))
}

/// Zero every counter and histogram; used by tests and the Python reset
/// binding.
fn reset_metrics() {
    for counter in CHECK_RUNS
        .iter()
        .chain(CHECKED_FILES.iter())
        .chain(DIAGNOSTIC_COUNTS.iter())
        .chain(SKIPPED_CANDIDATES.iter())
        .chain(OPERATIONAL_FAILURES.iter())
        .chain(PROJECTION_ANOMALIES.iter())
        .chain(EXTRACTION_DOCUMENTS.iter())
        .chain(EXTRACTION_RECOVERY_ERRORS.iter())
        .chain(EXTRACTION_FATAL_ERRORS.iter())
    {
        counter.store(0, Ordering::Relaxed);
    }
    UNREADABLE_FILES.store(0, Ordering::Relaxed);
    for histogram in &PHASE_DURATIONS {
        histogram.reset();
    }
}

/// Python binding that resets all check metrics to zero.
#[pyfunction]
pub(super) fn reset_check_metrics() {
    reset_metrics();
}

/// Python binding that counts one unreadable candidate file.
#[pyfunction]
pub(super) fn record_unreadable_file() {
    UNREADABLE_FILES.fetch_add(1, Ordering::Relaxed);
    metrics::counter!("stilyagi_check_unreadable_files_total").increment(1);
}

#[cfg(test)]
#[path = "recorder_tests.rs"]
mod tests;
