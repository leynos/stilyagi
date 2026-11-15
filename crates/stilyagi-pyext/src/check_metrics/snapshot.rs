//! Python snapshot serialization for the bounded check metrics recorder.

use std::{
    sync::atomic::{AtomicU64, Ordering},
    time::Duration,
};

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

/// Labels shared by the Python and Rust fatal extraction error groups.
const FATAL_ERROR_LABELS: [&str; 2] = ["grammar_load", "no_parse_tree"];

/// The check-level counter groups, each paired with its snapshot key.
///
/// The groups are data rather than a run of calls so the snapshot key and the
/// labels it reports cannot drift apart, and so adding a group needs no new
/// statement in [`set_check_counters`].
const fn check_counter_groups() -> [(&'static str, &'static [&'static str], &'static [AtomicU64]); 6]
{
    [
        ("stilyagi_check_runs_total", &RUN_OUTCOMES, &CHECK_RUNS),
        ("stilyagi_check_files_total", &SYNTAXES, &CHECKED_FILES),
        (
            "stilyagi_check_diagnostics_total",
            &DIAGNOSTIC_SEVERITIES,
            &DIAGNOSTIC_COUNTS,
        ),
        (
            "stilyagi_check_skipped_candidates_total",
            &SKIP_REASONS,
            &SKIPPED_CANDIDATES,
        ),
        (
            "stilyagi_check_operational_failures_total",
            &FAILURE_KINDS,
            &OPERATIONAL_FAILURES,
        ),
        (
            "stilyagi_check_projection_anomalies_total",
            &PROJECTION_ANOMALY_KINDS,
            &PROJECTION_ANOMALIES,
        ),
    ]
}

/// Insert the check-level counters into `snapshot`.
fn set_check_counters<'py>(py: Python<'py>, snapshot: &Bound<'py, PyDict>) -> PyResult<()> {
    for (key, labels, counters) in check_counter_groups() {
        let categories = counter_categories(labels, counters, 0);
        snapshot.set_item(key, category_snapshot(py, &categories)?)?;
    }
    snapshot.set_item(
        "stilyagi_check_unreadable_files_total",
        UNREADABLE_FILES.load(Ordering::Relaxed),
    )?;
    Ok(())
}

/// Insert the per-syntax extraction totals into `snapshot`.
fn set_extraction_totals(snapshot: &Bound<'_, PyDict>) -> PyResult<()> {
    let totals = [
        (
            "stilyagi_python_extraction_documents_total",
            &EXTRACTION_DOCUMENTS,
            0,
        ),
        (
            "stilyagi_rust_extraction_documents_total",
            &EXTRACTION_DOCUMENTS,
            1,
        ),
        (
            "stilyagi_python_extraction_recovery_errors_total",
            &EXTRACTION_RECOVERY_ERRORS,
            0,
        ),
        (
            "stilyagi_rust_extraction_recovery_errors_total",
            &EXTRACTION_RECOVERY_ERRORS,
            1,
        ),
    ];
    for (key, counters, index) in totals {
        snapshot.set_item(key, counter_value(counters, index))?;
    }
    Ok(())
}

/// Insert the per-syntax fatal extraction error counts into `snapshot`.
fn set_extraction_fatal_errors(py: Python<'_>, snapshot: &Bound<'_, PyDict>) -> PyResult<()> {
    let groups = [
        ("stilyagi_python_extraction_fatal_errors_total", 0),
        ("stilyagi_rust_extraction_fatal_errors_total", 2),
    ];
    for (key, offset) in groups {
        let categories = counter_categories(&FATAL_ERROR_LABELS, &EXTRACTION_FATAL_ERRORS, offset);
        snapshot.set_item(key, category_snapshot(py, &categories)?)?;
    }
    Ok(())
}

/// Insert the extraction counters into `snapshot`.
fn set_extraction_counters<'py>(py: Python<'py>, snapshot: &Bound<'py, PyDict>) -> PyResult<()> {
    set_extraction_totals(snapshot)?;
    set_extraction_fatal_errors(py, snapshot)
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
