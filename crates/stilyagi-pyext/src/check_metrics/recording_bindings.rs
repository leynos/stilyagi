//! `PyO3` bindings for check-level metric recording.

#![expect(
    clippy::too_many_arguments,
    reason = "PyO3 generates five-argument fastcall wrappers for Python functions with parameters."
)]

use std::time::Duration;

use pyo3::prelude::*;

use super::{
    CHECK_RUNS, CHECKED_FILES, DIAGNOSTIC_COUNTS, DIAGNOSTIC_SEVERITIES, FAILURE_KINDS,
    OPERATIONAL_FAILURES, PHASE_DURATIONS, PHASES, RUN_OUTCOMES, SKIP_REASONS, SKIPPED_CANDIDATES,
    SYNTAXES, checked_label, increment_counter,
};

#[pyfunction]
pub(crate) fn record_check_run(outcome: &str) -> PyResult<()> {
    let checked_outcome = checked_label(outcome, &RUN_OUTCOMES, "run outcome")?;
    increment_counter(&CHECK_RUNS, &RUN_OUTCOMES, checked_outcome, 1);
    metrics::counter!("stilyagi_check_runs_total", "outcome" => checked_outcome).increment(1);
    Ok(())
}

#[pyfunction]
pub(crate) fn record_checked_file(syntax: &str) -> PyResult<()> {
    let checked_syntax = checked_label(syntax, &SYNTAXES, "syntax")?;
    increment_counter(&CHECKED_FILES, &SYNTAXES, checked_syntax, 1);
    metrics::counter!("stilyagi_check_files_total", "syntax" => checked_syntax).increment(1);
    Ok(())
}

#[pyfunction]
pub(crate) fn record_diagnostic_severity(severity: &str, count: u64) -> PyResult<()> {
    let checked_severity = checked_label(severity, &DIAGNOSTIC_SEVERITIES, "diagnostic severity")?;
    increment_counter(
        &DIAGNOSTIC_COUNTS,
        &DIAGNOSTIC_SEVERITIES,
        checked_severity,
        count,
    );
    metrics::counter!("stilyagi_check_diagnostics_total", "severity" => checked_severity)
        .increment(count);
    Ok(())
}

#[pyfunction]
pub(crate) fn record_skipped_candidates(reason: &str, count: u64) -> PyResult<()> {
    let checked_reason = checked_label(reason, &SKIP_REASONS, "skip reason")?;
    increment_counter(&SKIPPED_CANDIDATES, &SKIP_REASONS, checked_reason, count);
    metrics::counter!("stilyagi_check_skipped_candidates_total", "reason" => checked_reason)
        .increment(count);
    Ok(())
}

#[pyfunction]
pub(crate) fn record_operational_failure(kind: &str) -> PyResult<()> {
    let checked_kind = checked_label(kind, &FAILURE_KINDS, "failure kind")?;
    increment_counter(&OPERATIONAL_FAILURES, &FAILURE_KINDS, checked_kind, 1);
    metrics::counter!("stilyagi_check_operational_failures_total", "kind" => checked_kind)
        .increment(1);
    Ok(())
}

#[pyfunction]
pub(crate) fn record_phase_duration(phase: &str, duration_nanoseconds: u64) -> PyResult<()> {
    let checked_phase = checked_label(phase, &PHASES, "phase")?;
    let duration = Duration::from_nanos(duration_nanoseconds).as_secs_f64();
    if let Some(index) = PHASES
        .iter()
        .position(|candidate| *candidate == checked_phase)
        && let Some(histogram) = PHASE_DURATIONS.get(index)
    {
        histogram.record(duration);
    }
    metrics::histogram!("stilyagi_check_phase_duration_seconds", "phase" => checked_phase)
        .record(duration);
    Ok(())
}
