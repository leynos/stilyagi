//! Python snapshot serialization for the bounded check metrics recorder.

use std::{sync::atomic::Ordering, time::Duration};

use pyo3::{prelude::*, types::PyDict};

use super::{
    BUCKET_LABELS,
    CHECK_RUNS,
    CHECKED_FILES,
    DIAGNOSTIC_COUNTS,
    DIAGNOSTIC_SEVERITIES,
    DurationHistogram,
    EXTRACTION_DOCUMENTS,
    EXTRACTION_FATAL_ERRORS,
    EXTRACTION_RECOVERY_ERRORS,
    FAILURE_KINDS,
    OPERATIONAL_FAILURES,
    PHASE_DURATIONS,
    PHASES,
    PROJECTION_ANOMALIES,
    PROJECTION_ANOMALY_KINDS,
    RUN_OUTCOMES,
    SKIP_REASONS,
    SKIPPED_CANDIDATES,
    SYNTAXES,
    UNREADABLE_FILES,
};

/// Build a Python dict mapping each category name to its counter value.
fn category_snapshot<'py>(
    py: Python<'py>,
    categories: &[(&str, &std::sync::atomic::AtomicU64)],
) -> PyResult<Bound<'py, PyDict>> {
    let result = PyDict::new(py);
    for (name, count) in categories {
        result.set_item(name, count.load(Ordering::Relaxed))?;
    }
    Ok(result)
}

/// Load the counter at `index`, returning zero when the index is out of range.
fn counter_value(counters: &[std::sync::atomic::AtomicU64], index: usize) -> u64 {
    counters
        .get(index)
        .map_or(0, |counter| counter.load(Ordering::Relaxed))
}

/// Pair labels with counters starting at `offset`, for snapshot serialization.
fn counter_categories<'a>(
    labels: &'a [&'a str],
    counters: &'a [std::sync::atomic::AtomicU64],
    offset: usize,
) -> Vec<(&'a str, &'a std::sync::atomic::AtomicU64)> {
    labels
        .iter()
        .copied()
        .zip(counters.iter().skip(offset))
        .collect()
}

/// Build a Python dict of per-phase count, sum, and cumulative bucket values.
fn phase_snapshot<'py>(
    py: Python<'py>,
    phases: &[(&str, &DurationHistogram)],
) -> PyResult<Bound<'py, PyDict>> {
    let phase_metrics = PyDict::new(py);
    for (phase, histogram) in phases {
        let count = histogram.count.load(Ordering::Relaxed);
        let buckets = PyDict::new(py);
        let mut cumulative_count = 0;
        for (label, bucket) in BUCKET_LABELS.iter().zip(&histogram.buckets) {
            cumulative_count += bucket.load(Ordering::Relaxed);
            buckets.set_item(label, cumulative_count)?;
        }
        let distribution = PyDict::new(py);
        distribution.set_item("count", count)?;
        distribution.set_item(
            "sum_seconds",
            Duration::from_nanos(histogram.sum_nanoseconds.load(Ordering::Relaxed)).as_secs_f64(),
        )?;
        distribution.set_item("buckets", buckets)?;
        phase_metrics.set_item(phase, distribution)?;
    }
    Ok(phase_metrics)
}

/// Insert one category counter dict into `snapshot` under `key`.
fn set_categories<'py>(
    py: Python<'py>,
    snapshot: &Bound<'py, PyDict>,
    key: &str,
    categories: &[(&str, &std::sync::atomic::AtomicU64)],
) -> PyResult<()> {
    snapshot.set_item(key, category_snapshot(py, categories)?)
}

/// Insert the check-level counters into `snapshot`.
fn set_check_counters<'py>(py: Python<'py>, snapshot: &Bound<'py, PyDict>) -> PyResult<()> {
    set_run_counters(py, snapshot)?;
    set_failure_counters(py, snapshot)
}

/// Insert the run, file, diagnostic and skipped-candidate counters.
fn set_run_counters<'py>(py: Python<'py>, snapshot: &Bound<'py, PyDict>) -> PyResult<()> {
    set_categories(
        py,
        snapshot,
        "stilyagi_check_runs_total",
        &counter_categories(&RUN_OUTCOMES, &CHECK_RUNS, 0),
    )?;
    set_categories(
        py,
        snapshot,
        "stilyagi_check_files_total",
        &counter_categories(&SYNTAXES, &CHECKED_FILES, 0),
    )?;
    set_categories(
        py,
        snapshot,
        "stilyagi_check_diagnostics_total",
        &counter_categories(&DIAGNOSTIC_SEVERITIES, &DIAGNOSTIC_COUNTS, 0),
    )?;
    set_categories(
        py,
        snapshot,
        "stilyagi_check_skipped_candidates_total",
        &counter_categories(&SKIP_REASONS, &SKIPPED_CANDIDATES, 0),
    )
}

/// Insert the unreadable-file, operational-failure and projection-anomaly
/// counters.
fn set_failure_counters<'py>(py: Python<'py>, snapshot: &Bound<'py, PyDict>) -> PyResult<()> {
    snapshot.set_item(
        "stilyagi_check_unreadable_files_total",
        UNREADABLE_FILES.load(Ordering::Relaxed),
    )?;
    set_categories(
        py,
        snapshot,
        "stilyagi_check_operational_failures_total",
        &counter_categories(&FAILURE_KINDS, &OPERATIONAL_FAILURES, 0),
    )?;
    set_categories(
        py,
        snapshot,
        "stilyagi_check_projection_anomalies_total",
        &counter_categories(&PROJECTION_ANOMALY_KINDS, &PROJECTION_ANOMALIES, 0),
    )
}

/// Insert the extraction counters into `snapshot`.
fn set_extraction_counters<'py>(py: Python<'py>, snapshot: &Bound<'py, PyDict>) -> PyResult<()> {
    set_extraction_totals(snapshot)?;
    set_extraction_fatal_errors(py, snapshot)
}

/// Insert the extraction document and recovery-error counters.
fn set_extraction_totals(snapshot: &Bound<'_, PyDict>) -> PyResult<()> {
    snapshot.set_item(
        "stilyagi_python_extraction_documents_total",
        counter_value(&EXTRACTION_DOCUMENTS, 0),
    )?;
    snapshot.set_item(
        "stilyagi_rust_extraction_documents_total",
        counter_value(&EXTRACTION_DOCUMENTS, 1),
    )?;
    snapshot.set_item(
        "stilyagi_python_extraction_recovery_errors_total",
        counter_value(&EXTRACTION_RECOVERY_ERRORS, 0),
    )?;
    snapshot.set_item(
        "stilyagi_rust_extraction_recovery_errors_total",
        counter_value(&EXTRACTION_RECOVERY_ERRORS, 1),
    )
}

/// Insert the per-language extraction fatal-error counters.
fn set_extraction_fatal_errors<'py>(
    py: Python<'py>,
    snapshot: &Bound<'py, PyDict>,
) -> PyResult<()> {
    let kinds = ["grammar_load", "no_parse_tree"];
    set_categories(
        py,
        snapshot,
        "stilyagi_python_extraction_fatal_errors_total",
        &counter_categories(&kinds, &EXTRACTION_FATAL_ERRORS, 0),
    )?;
    set_categories(
        py,
        snapshot,
        "stilyagi_rust_extraction_fatal_errors_total",
        &counter_categories(&kinds, &EXTRACTION_FATAL_ERRORS, 2),
    )
}

/// Insert the per-phase duration histograms into `snapshot`.
fn set_phase_durations<'py>(py: Python<'py>, snapshot: &Bound<'py, PyDict>) -> PyResult<()> {
    let phases = PHASES
        .iter()
        .zip(&PHASE_DURATIONS)
        .map(|(phase, histogram)| (*phase, histogram))
        .collect::<Vec<_>>();
    snapshot.set_item(
        "stilyagi_check_phase_duration_seconds",
        phase_snapshot(py, &phases)?,
    )?;
    Ok(())
}

/// Python binding returning a snapshot of all check metrics as a dict.
#[pyfunction]
pub(crate) fn check_metrics_snapshot(py: Python<'_>) -> PyResult<Py<PyDict>> {
    let snapshot = PyDict::new(py);
    set_check_counters(py, &snapshot)?;
    set_extraction_counters(py, &snapshot)?;
    set_phase_durations(py, &snapshot)?;
    Ok(snapshot.unbind())
}
