//! Bounded in-process metrics for one Stilyagi check command.

mod recording_bindings;
mod snapshot;
pub(super) use recording_bindings::{
    record_check_run, record_checked_file, record_diagnostic_severity, record_operational_failure,
    record_phase_duration, record_skipped_candidates,
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

static CHECK_RUNS: [AtomicU64; 3] = [AtomicU64::new(0), AtomicU64::new(0), AtomicU64::new(0)];
static CHECKED_FILES: [AtomicU64; 3] = [AtomicU64::new(0), AtomicU64::new(0), AtomicU64::new(0)];
static DIAGNOSTIC_COUNTS: [AtomicU64; 2] = [AtomicU64::new(0), AtomicU64::new(0)];
static SKIPPED_CANDIDATES: [AtomicU64; 3] =
    [AtomicU64::new(0), AtomicU64::new(0), AtomicU64::new(0)];
static UNREADABLE_FILES: AtomicU64 = AtomicU64::new(0);
static OPERATIONAL_FAILURES: [AtomicU64; 6] = [
    AtomicU64::new(0),
    AtomicU64::new(0),
    AtomicU64::new(0),
    AtomicU64::new(0),
    AtomicU64::new(0),
    AtomicU64::new(0),
];
static EXTRACTION_DOCUMENTS: [AtomicU64; 2] = [AtomicU64::new(0), AtomicU64::new(0)];
static EXTRACTION_RECOVERY_ERRORS: [AtomicU64; 2] = [AtomicU64::new(0), AtomicU64::new(0)];
static EXTRACTION_FATAL_ERRORS: [AtomicU64; 4] = [
    AtomicU64::new(0),
    AtomicU64::new(0),
    AtomicU64::new(0),
    AtomicU64::new(0),
];
static PHASE_DURATIONS: [DurationHistogram; 7] = [
    DurationHistogram::new(),
    DurationHistogram::new(),
    DurationHistogram::new(),
    DurationHistogram::new(),
    DurationHistogram::new(),
    DurationHistogram::new(),
    DurationHistogram::new(),
];

const RUN_OUTCOMES: [&str; 3] = ["success", "diagnostic_error", "operational_error"];
const SYNTAXES: [&str; 3] = ["markdown", "python", "rust"];
const DIAGNOSTIC_SEVERITIES: [&str; 2] = ["error", "warning"];
const SKIP_REASONS: [&str; 3] = [
    "unregistered_candidate",
    "symlinked_directory_target",
    "unsupported_candidate_type",
];
const FAILURE_KINDS: [&str; 6] = ["discovery", "read", "extract", "config", "rules", "render"];
const PHASES: [&str; 7] = [
    "discovery",
    "read",
    "extract",
    "config",
    "rules",
    "render",
    "total",
];
const BUCKET_LIMITS: [Duration; 4] = [
    Duration::from_micros(1_000),
    Duration::from_millis(10),
    Duration::from_millis(100),
    Duration::from_secs(1),
];
const BUCKET_LABELS: [&str; 5] = ["0.001", "0.01", "0.1", "1", "+Inf"];

struct DurationHistogram {
    count: AtomicU64,
    sum_nanoseconds: AtomicU64,
    buckets: [AtomicU64; 5],
}

impl DurationHistogram {
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

    fn reset(&self) {
        self.count.store(0, Ordering::Relaxed);
        self.sum_nanoseconds.store(0, Ordering::Relaxed);
        for bucket in &self.buckets {
            bucket.store(0, Ordering::Relaxed);
        }
    }
}

fn increment_counter(counters: &[AtomicU64], labels: &[&str], label: &str, amount: u64) {
    if let Some(counter) = labels
        .iter()
        .position(|candidate| *candidate == label)
        .and_then(|index| counters.get(index))
    {
        counter.fetch_add(amount, Ordering::Relaxed);
    }
}

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

pub(super) fn recovery_error_count(errors: &[IrError]) -> usize {
    errors
        .iter()
        .filter(|error| !AUTHORED_DIRECTIVE_ERROR_CODES.contains(&error.code.as_str()))
        .count()
}

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

fn checked_label(value: &str, supported: &[&'static str], name: &str) -> PyResult<&'static str> {
    supported
        .iter()
        .copied()
        .find(|candidate| *candidate == value)
        .ok_or_else(|| PyValueError::new_err(format!("unsupported {name} metric label: {value}")))
}

fn reset_metrics() {
    for counter in CHECK_RUNS
        .iter()
        .chain(CHECKED_FILES.iter())
        .chain(DIAGNOSTIC_COUNTS.iter())
        .chain(SKIPPED_CANDIDATES.iter())
        .chain(OPERATIONAL_FAILURES.iter())
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

#[pyfunction]
pub(super) fn reset_check_metrics() {
    reset_metrics();
}

#[pyfunction]
pub(super) fn record_unreadable_file() {
    UNREADABLE_FILES.fetch_add(1, Ordering::Relaxed);
    metrics::counter!("stilyagi_check_unreadable_files_total").increment(1);
}

#[cfg(test)]
#[path = "recorder_tests.rs"]
mod tests;
