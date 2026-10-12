//! Tests for the Python snapshot boundary of the check metrics recorder.

use std::sync::atomic::Ordering;
use std::time::Duration;

use pyo3::{
    exceptions::{PyAssertionError, PyRuntimeError},
    prelude::*,
    types::{PyDict, PyTuple},
};
use rstest::rstest;
use stilyagi_extract::{
    ExtractError, ExtractSyntax, MarkdownIrFailure, PythonExtractError, RustExtractError,
};

use super::{
    CHECK_METRICS_TEST_LOCK, DurationHistogram, EXTRACTION_RECOVERY_ERRORS, check_metrics_snapshot,
    record_check_run, record_checked_file, record_diagnostic_severity, record_extraction_attempt,
    record_extraction_failure, record_extraction_outcome, record_operational_failure,
    record_phase_duration, record_skipped_candidates, record_unreadable_file, reset_metrics,
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
    record_diagnostic_severity("error", 2)?;
    record_diagnostic_severity("warning", 3)?;
    for reason in [
        "unregistered_candidate",
        "symlinked_directory_target",
        "unsupported_candidate_type",
    ] {
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

fn assert_metric_values(metrics: &Bound<'_, PyDict>, expected: &[(&str, u64)]) -> PyResult<()> {
    for (name, expected_value) in expected {
        let actual_value = integer(metrics, name)?;
        if actual_value != *expected_value {
            return Err(PyAssertionError::new_err(format!(
                "metric counter `{name}`: expected {expected_value}, got {actual_value}"
            )));
        }
    }
    Ok(())
}

fn assert_metric_categories(
    snapshot: &Bound<'_, PyDict>,
    category: &str,
    expected: &[(&str, u64)],
) -> PyResult<()> {
    let metrics = dictionary(snapshot, category)?;
    assert_metric_values(&metrics, expected)
}

fn bridge_recovery_count(
    source: &str,
    syntax: ExtractSyntax,
    counter_index: usize,
) -> PyResult<u64> {
    reset_metrics();
    Python::attach(|py| -> PyResult<()> {
        let args = PyTuple::new(py, [source, syntax.as_str()])?;
        crate::extract_document_py(py, &args)?;
        Ok(())
    })?;
    EXTRACTION_RECOVERY_ERRORS
        .get(counter_index)
        .map(|counter| counter.load(Ordering::Relaxed))
        .ok_or_else(|| {
            PyRuntimeError::new_err(format!(
                "extraction syntax counter index {counter_index} is out of range"
            ))
        })
}

struct RecoveryMetricFixture {
    syntax: ExtractSyntax,
    counter_index: usize,
    authored_only_source: &'static str,
    recovery_only_source: &'static str,
    mixed_source: &'static str,
}

struct RecoveryMetricCounts {
    authored_only: u64,
    recovery_only: u64,
    mixed: u64,
}

fn recovery_metric_counts(fixture: &RecoveryMetricFixture) -> PyResult<RecoveryMetricCounts> {
    let _guard = CHECK_METRICS_TEST_LOCK
        .lock()
        .map_err(|error| PyRuntimeError::new_err(error.to_string()))?;
    Ok(RecoveryMetricCounts {
        authored_only: bridge_recovery_count(
            fixture.authored_only_source,
            fixture.syntax,
            fixture.counter_index,
        )?,
        recovery_only: bridge_recovery_count(
            fixture.recovery_only_source,
            fixture.syntax,
            fixture.counter_index,
        )?,
        mixed: bridge_recovery_count(fixture.mixed_source, fixture.syntax, fixture.counter_index)?,
    })
}

fn assert_authored_suppression_errors_are_excluded(
    syntax: ExtractSyntax,
    counts: &RecoveryMetricCounts,
) {
    assert_eq!(
        counts.authored_only, 0,
        "{syntax} authored-only errors are not parser recovery",
    );
    assert!(
        counts.recovery_only > 0,
        "{syntax} parser recovery remains counted",
    );
    assert_eq!(
        counts.mixed, counts.recovery_only,
        "{syntax} authored errors do not inflate recovery",
    );
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
fn serializes_syntax_skip_and_diagnostic_categories() {
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
        assert_eq!(
            integer(&skipped, "unsupported_candidate_type")
                .expect("unsupported candidate count is an integer"),
            2
        );
        assert_metric_categories(
            bound_snapshot,
            "stilyagi_check_diagnostics_total",
            &[("error", 2), ("warning", 3)],
        )
        .expect("diagnostic counts contain only fixed severity categories");
    });
}

#[rstest]
fn check_metrics_exclude_authored_python_suppression_errors() {
    let fixture = RecoveryMetricFixture {
        syntax: ExtractSyntax::PythonDocstring,
        counter_index: 0,
        authored_only_source: "# stilyagi: disable\nvalue = 1\n",
        recovery_only_source: "value = \"unterminated\n",
        mixed_source: "# stilyagi: disable\nvalue = \"unterminated\n",
    };
    let counts = recovery_metric_counts(&fixture).expect("Python recovery fixtures extract");
    assert_authored_suppression_errors_are_excluded(fixture.syntax, &counts);
}

#[rstest]
fn check_metrics_exclude_authored_rust_suppression_errors() {
    let fixture = RecoveryMetricFixture {
        syntax: ExtractSyntax::RustDocComment,
        counter_index: 1,
        authored_only_source: "pub fn stable() {\n    // stilyagi: disable\n}\n",
        recovery_only_source: "pub fn broken() { let value = \"unterminated; }\n",
        mixed_source: concat!(
            "pub fn stable() {\n",
            "    // stilyagi: disable\n",
            "}\n",
            "pub fn broken() { let value = \"unterminated; }\n",
        ),
    };
    let counts = recovery_metric_counts(&fixture).expect("Rust recovery fixtures extract");
    assert_authored_suppression_errors_are_excluded(fixture.syntax, &counts);
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
        assert_metric_categories(
            bound_snapshot,
            "stilyagi_check_operational_failures_total",
            &[
                ("discovery", 1),
                ("read", 1),
                ("extract", 1),
                ("config", 1),
                ("rules", 1),
                ("render", 1),
            ],
        )
        .expect("operational failure counts match their categories");
    });
}

#[rstest]
fn serializes_extraction_document_and_recovery_counts() {
    let snapshot = populated_snapshot().expect("bounded metrics serialize");
    Python::attach(|py| {
        let bound_snapshot = snapshot.bind(py);
        assert_metric_values(
            bound_snapshot,
            &[
                ("stilyagi_python_extraction_documents_total", 1),
                ("stilyagi_rust_extraction_documents_total", 1),
                ("stilyagi_python_extraction_recovery_errors_total", 2),
                ("stilyagi_rust_extraction_recovery_errors_total", 2),
            ],
        )
        .expect("document and recovery counts match each extraction syntax");
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
        assert_metric_values(&python, &[("grammar_load", 1), ("no_parse_tree", 1)])
            .expect("Python fatal error counts match their categories");
        assert_metric_values(&rust, &[("grammar_load", 1), ("no_parse_tree", 1)])
            .expect("Rust fatal error counts match their categories");
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
        assert_metric_values(&discovery, &[("count", 1)])
            .expect("discovery duration count is present");
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
        assert_metric_categories(
            &discovery,
            "buckets",
            &[("0.001", 1), ("0.01", 1), ("0.1", 1), ("1", 1), ("+Inf", 1)],
        )
        .expect("discovery duration buckets are cumulative");
    });
}
