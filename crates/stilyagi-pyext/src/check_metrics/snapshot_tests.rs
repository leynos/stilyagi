//! Tests for the Python snapshot boundary of the check metrics recorder.

use std::sync::atomic::Ordering;
use std::time::Duration;

use pyo3::{exceptions::PyRuntimeError, prelude::*, types::PyDict};
use rstest::rstest;
use stilyagi_extract::{
    ExtractError, ExtractSyntax, MarkdownIrFailure, PythonExtractError, RustExtractError,
};

use super::{
    CHECK_METRICS_TEST_LOCK, DurationHistogram, check_metrics_snapshot, record_check_run,
    record_checked_file, record_extraction_attempt, record_extraction_failure,
    record_extraction_outcome, record_operational_failure, record_phase_duration,
    record_skipped_candidates, record_unreadable_file, reset_metrics,
};

fn populated_snapshot() -> PyResult<Py<PyDict>> {
    let _guard = CHECK_METRICS_TEST_LOCK
        .lock()
        .map_err(|error| PyRuntimeError::new_err(error.to_string()))?;
    reset_metrics();

    for outcome in ["success", "diagnostic_error", "operational_error"] {
        record_check_run(outcome)?;
    }
    for syntax in ["markdown", "python", "rust"] {
        record_checked_file(syntax)?;
    }
    for reason in ["unregistered_candidate", "symlinked_directory_target"] {
        record_skipped_candidates(reason, 2)?;
    }
    record_unreadable_file();
    for kind in ["discovery", "read", "extract", "config", "rules", "render"] {
        record_operational_failure(kind)?;
    }

    for syntax in [
        ExtractSyntax::Markdown,
        ExtractSyntax::PythonDocstring,
        ExtractSyntax::RustDocComment,
    ] {
        record_extraction_attempt(syntax);
        record_extraction_outcome(syntax, 2);
    }
    for error in [
        ExtractError::PythonIr(PythonExtractError::GrammarLoad),
        ExtractError::PythonIr(PythonExtractError::NoParseTree),
        ExtractError::RustIr(RustExtractError::GrammarLoad),
        ExtractError::RustIr(RustExtractError::NoParseTree),
        ExtractError::UnsupportedSyntax(ExtractSyntax::Markdown),
        ExtractError::UnknownSyntax("unknown".to_owned()),
        ExtractError::MarkdownIr(MarkdownIrFailure::new("test", "rule", "reason")),
    ] {
        record_extraction_failure(&error);
    }

    for (phase, duration) in [
        ("discovery", Duration::from_micros(500)),
        ("read", Duration::from_millis(5)),
        ("extract", Duration::from_millis(50)),
        ("config", Duration::from_millis(500)),
        ("rules", Duration::from_secs(2)),
        ("render", Duration::from_secs(2)),
    ] {
        let nanoseconds = u64::try_from(duration.as_nanos())
            .map_err(|error| PyRuntimeError::new_err(error.to_string()))?;
        record_phase_duration(phase, nanoseconds)?;
    }

    Python::attach(check_metrics_snapshot)
}

fn dictionary<'py>(snapshot: &Bound<'py, PyDict>, key: &str) -> PyResult<Bound<'py, PyDict>> {
    Ok(snapshot
        .get_item(key)?
        .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(key.to_owned()))?
        .cast_into::<PyDict>()?)
}

fn integer(snapshot: &Bound<'_, PyDict>, key: &str) -> PyResult<u64> {
    snapshot
        .get_item(key)?
        .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(key.to_owned()))?
        .extract()
}

#[rstest]
fn initializes_duration_histogram_counters_to_zero() {
    let histogram = DurationHistogram::new();
    assert_eq!(histogram.count.load(Ordering::Relaxed), 0);
    assert_eq!(histogram.sum_nanoseconds.load(Ordering::Relaxed), 0);
    assert!(
        histogram
            .buckets
            .iter()
            .all(|bucket| bucket.load(Ordering::Relaxed) == 0),
        "a new histogram begins with empty buckets",
    );
}

#[rstest]
fn serializes_run_file_skip_and_operational_totals() {
    let snapshot = populated_snapshot().expect("bounded metrics serialize");
    Python::attach(|py| {
        let bound_snapshot = snapshot.bind(py);
        let runs = dictionary(bound_snapshot, "stilyagi_check_runs_total")
            .expect("run outcomes are present");
        assert_eq!(
            integer(&runs, "success").expect("success count is an integer"),
            1
        );
        assert_eq!(
            integer(&runs, "diagnostic_error").expect("diagnostic count is an integer"),
            1
        );
        assert_eq!(
            integer(&runs, "operational_error").expect("operational count is an integer"),
            1
        );
    });
}

#[rstest]
fn serializes_syntax_and_skip_reason_categories() {
    let snapshot = populated_snapshot().expect("bounded metrics serialize");
    Python::attach(|py| {
        let bound_snapshot = snapshot.bind(py);
        let files = dictionary(bound_snapshot, "stilyagi_check_files_total")
            .expect("syntax counts are present");
        assert_eq!(
            integer(&files, "markdown").expect("Markdown count is an integer"),
            1
        );
        assert_eq!(
            integer(&files, "python").expect("Python count is an integer"),
            1
        );
        assert_eq!(
            integer(&files, "rust").expect("Rust count is an integer"),
            1
        );
        let skipped = dictionary(bound_snapshot, "stilyagi_check_skipped_candidates_total")
            .expect("skip reasons are present");
        assert_eq!(
            integer(&skipped, "unregistered_candidate").expect("skip count is an integer"),
            2
        );
        assert_eq!(
            integer(&skipped, "symlinked_directory_target").expect("symlink count is an integer"),
            2
        );
    });
}

#[rstest]
fn serializes_unreadable_and_operational_failure_totals() {
    let snapshot = populated_snapshot().expect("bounded metrics serialize");
    Python::attach(|py| {
        let bound_snapshot = snapshot.bind(py);
        assert_eq!(
            integer(bound_snapshot, "stilyagi_check_unreadable_files_total")
                .expect("unreadable count is an integer"),
            1
        );
        let failures = dictionary(bound_snapshot, "stilyagi_check_operational_failures_total")
            .expect("failure kinds are present");
        assert_eq!(
            integer(&failures, "discovery").expect("failure count is an integer"),
            1
        );
        assert_eq!(
            integer(&failures, "read").expect("failure count is an integer"),
            1
        );
        assert_eq!(
            integer(&failures, "extract").expect("failure count is an integer"),
            1
        );
        assert_eq!(
            integer(&failures, "config").expect("failure count is an integer"),
            1
        );
        assert_eq!(
            integer(&failures, "rules").expect("failure count is an integer"),
            1
        );
        assert_eq!(
            integer(&failures, "render").expect("failure count is an integer"),
            1
        );
    });
}

#[rstest]
fn serializes_extraction_document_and_recovery_counts() {
    let snapshot = populated_snapshot().expect("bounded metrics serialize");
    Python::attach(|py| {
        let bound_snapshot = snapshot.bind(py);
        assert_eq!(
            integer(bound_snapshot, "stilyagi_python_extraction_documents_total")
                .expect("Python document count is an integer"),
            1
        );
        assert_eq!(
            integer(bound_snapshot, "stilyagi_rust_extraction_documents_total")
                .expect("Rust document count is an integer"),
            1
        );
        assert_eq!(
            integer(
                bound_snapshot,
                "stilyagi_python_extraction_recovery_errors_total"
            )
            .expect("Python recovery count is an integer"),
            2
        );
        assert_eq!(
            integer(
                bound_snapshot,
                "stilyagi_rust_extraction_recovery_errors_total"
            )
            .expect("Rust recovery count is an integer"),
            2
        );
    });
}

#[rstest]
fn serializes_fatal_extraction_error_categories() {
    let snapshot = populated_snapshot().expect("bounded metrics serialize");
    Python::attach(|py| {
        let bound_snapshot = snapshot.bind(py);
        let python = dictionary(
            bound_snapshot,
            "stilyagi_python_extraction_fatal_errors_total",
        )
        .expect("Python fatal errors are present");
        let rust = dictionary(
            bound_snapshot,
            "stilyagi_rust_extraction_fatal_errors_total",
        )
        .expect("Rust fatal errors are present");
        assert_eq!(
            integer(&python, "grammar_load").expect("grammar count is an integer"),
            1
        );
        assert_eq!(
            integer(&python, "no_parse_tree").expect("parse tree count is an integer"),
            1
        );
        assert_eq!(
            integer(&rust, "grammar_load").expect("grammar count is an integer"),
            1
        );
        assert_eq!(
            integer(&rust, "no_parse_tree").expect("parse tree count is an integer"),
            1
        );
    });
}

#[rstest]
fn serializes_duration_counts_sums_and_cumulative_buckets() {
    let snapshot = populated_snapshot().expect("bounded metrics serialize");
    Python::attach(|py| {
        let bound_snapshot = snapshot.bind(py);
        let phases = dictionary(bound_snapshot, "stilyagi_check_phase_duration_seconds")
            .expect("phase distributions are present");
        let discovery = dictionary(&phases, "discovery").expect("discovery phase is present");
        assert_eq!(
            integer(&discovery, "count").expect("duration count is an integer"),
            1
        );
        let sum = discovery
            .get_item("sum_seconds")
            .expect("sum lookup succeeds")
            .expect("duration sum is present")
            .extract::<f64>()
            .expect("duration sum is numeric");
        assert_eq!(
            sum.to_bits(),
            Duration::from_micros(500).as_secs_f64().to_bits()
        );
        let buckets = dictionary(&discovery, "buckets").expect("duration buckets are present");
        assert_eq!(integer(&buckets, "0.001").expect("bucket is an integer"), 1);
        assert_eq!(integer(&buckets, "0.01").expect("bucket is an integer"), 1);
        assert_eq!(integer(&buckets, "0.1").expect("bucket is an integer"), 1);
        assert_eq!(integer(&buckets, "1").expect("bucket is an integer"), 1);
        assert_eq!(integer(&buckets, "+Inf").expect("bucket is an integer"), 1);
    });
}
