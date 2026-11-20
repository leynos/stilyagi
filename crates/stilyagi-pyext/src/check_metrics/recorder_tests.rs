//! Unit tests for bounded check metrics and host-recorder forwarding.

use std::sync::{
    Arc,
    atomic::{AtomicU64, Ordering},
};

use rstest::rstest;

use super::{
    CHECK_RUNS,
    CHECKED_FILES,
    DIAGNOSTIC_COUNTS,
    OPERATIONAL_FAILURES,
    PHASE_DURATIONS,
    PROJECTION_ANOMALIES,
    SKIPPED_CANDIDATES,
    UNREADABLE_FILES,
    record_check_run,
    record_checked_file,
    record_diagnostic_severity,
    record_operational_failure,
    record_phase_duration,
    record_projection_anomaly,
    record_skipped_candidates,
    record_unreadable_file,
    reset_metrics,
    with_metrics_test_lock,
};

static HOST_METRIC: AtomicU64 = AtomicU64::new(0);
static HOST_CHECK_METRIC: AtomicU64 = AtomicU64::new(0);
static HOST_DIAGNOSTIC_METRIC: AtomicU64 = AtomicU64::new(0);
static HOST_DURATION_METRIC: AtomicU64 = AtomicU64::new(0);

struct HostRecorder;
struct HostCounter(&'static AtomicU64);
struct HostHistogram(&'static AtomicU64);

impl metrics::CounterFn for HostCounter {
    fn increment(&self, value: u64) { self.0.fetch_add(value, Ordering::Relaxed); }
    fn absolute(&self, value: u64) { self.0.store(value, Ordering::Relaxed); }
}

impl metrics::HistogramFn for HostHistogram {
    fn record(&self, _value: f64) { self.0.fetch_add(1, Ordering::Relaxed); }
}

impl metrics::Recorder for HostRecorder {
    fn describe_counter(
        &self,
        _key: metrics::KeyName,
        _unit: Option<metrics::Unit>,
        _description: metrics::SharedString,
    ) {
    }
    fn describe_gauge(
        &self,
        _key: metrics::KeyName,
        _unit: Option<metrics::Unit>,
        _description: metrics::SharedString,
    ) {
    }
    fn describe_histogram(
        &self,
        _key: metrics::KeyName,
        _unit: Option<metrics::Unit>,
        _description: metrics::SharedString,
    ) {
    }

    fn register_counter(
        &self,
        key: &metrics::Key,
        _metadata: &metrics::Metadata<'_>,
    ) -> metrics::Counter {
        match key.name() {
            "test_host_unrelated_metric" => {
                metrics::Counter::from_arc(Arc::new(HostCounter(&HOST_METRIC)))
            }
            "stilyagi_check_runs_total" => {
                metrics::Counter::from_arc(Arc::new(HostCounter(&HOST_CHECK_METRIC)))
            }
            "stilyagi_check_diagnostics_total" => {
                metrics::Counter::from_arc(Arc::new(HostCounter(&HOST_DIAGNOSTIC_METRIC)))
            }
            _ => metrics::Counter::noop(),
        }
    }

    fn register_gauge(
        &self,
        _key: &metrics::Key,
        _metadata: &metrics::Metadata<'_>,
    ) -> metrics::Gauge {
        metrics::Gauge::noop()
    }

    fn register_histogram(
        &self,
        key: &metrics::Key,
        _metadata: &metrics::Metadata<'_>,
    ) -> metrics::Histogram {
        match key.name() {
            "stilyagi_check_phase_duration_seconds" => {
                metrics::Histogram::from_arc(Arc::new(HostHistogram(&HOST_DURATION_METRIC)))
            }
            _ => metrics::Histogram::noop(),
        }
    }
}

#[rstest]
fn records_bounded_check_metrics_and_rejects_unbounded_labels() {
    with_metrics_test_lock(|| {
        record_every_bounded_metric();
        assert_check_and_file_counts();
        assert_failure_and_duration_counts();
        assert_unbounded_labels_are_rejected();
    });
}

/// Records one of every metric kind the recorder accepts.
fn record_every_bounded_metric() {
    reset_metrics();
    record_check_run("success").expect("success is a bounded outcome");
    record_checked_file("python").expect("Python is a registered syntax");
    record_diagnostic_severity("warning", 2).expect("warning is a bounded severity");
    record_skipped_candidates("unregistered_candidate", 2).expect("skip reason is fixed");
    record_unreadable_file();
    record_operational_failure("read").expect("read is a fixed failure kind");
    record_projection_anomaly("source_mismatch", 3).expect("anomaly kind is fixed");
    record_phase_duration("extract", 5_000_000).expect("extract is a fixed phase");
}

/// Asserts the recorded run, file, diagnostic, and skip counts.
fn assert_check_and_file_counts() {
    assert_eq!(
        CHECK_RUNS
            .first()
            .map(|counter| counter.load(Ordering::Relaxed)),
        Some(1),
        "one success must increment the first run-outcome slot"
    );
    assert_eq!(
        CHECKED_FILES
            .get(1)
            .map(|counter| counter.load(Ordering::Relaxed)),
        Some(1),
        "one Python file must increment the Python syntax slot"
    );
    assert_eq!(
        DIAGNOSTIC_COUNTS
            .get(1)
            .map(|counter| counter.load(Ordering::Relaxed)),
        Some(2),
        "two warnings must increment the warning severity slot"
    );
    assert_eq!(
        SKIPPED_CANDIDATES
            .first()
            .map(|counter| counter.load(Ordering::Relaxed)),
        Some(2),
        "two candidates must increment the unregistered skip slot"
    );
}

/// Asserts the recorded unreadable, failure, duration, and anomaly counts.
fn assert_failure_and_duration_counts() {
    assert_eq!(
        UNREADABLE_FILES.load(Ordering::Relaxed),
        1,
        "one unreadable file must be counted"
    );
    assert_eq!(
        OPERATIONAL_FAILURES
            .get(1)
            .map(|counter| counter.load(Ordering::Relaxed)),
        Some(1),
        "one read failure must increment the read failure slot"
    );
    assert_eq!(
        PHASE_DURATIONS
            .get(2)
            .map(|histogram| histogram.count.load(Ordering::Relaxed)),
        Some(1),
        "one extract duration must increment the extract phase count"
    );
    assert_eq!(
        PROJECTION_ANOMALIES
            .get(5)
            .map(|counter| counter.load(Ordering::Relaxed)),
        Some(3),
        "three anomalies must increment the source-mismatch slot"
    );
}

/// Asserts the recorder rejects labels outside its fixed vocabularies.
fn assert_unbounded_labels_are_rejected() {
    assert!(
        record_check_run("/tmp/private-source.py").is_err(),
        "an unregistered run outcome must be rejected"
    );
    assert!(
        record_diagnostic_severity("/tmp/private-source.py", 1).is_err(),
        "an unbounded diagnostic severity label must be rejected"
    );
    assert!(
        record_projection_anomaly("/tmp/private-source.py", 1).is_err(),
        "an unbounded anomaly label must be rejected"
    );
    assert!(
        record_projection_anomaly("malformed_node", 1).is_ok(),
        "every documented anomaly category is a fixed label"
    );
}

#[rstest]
fn leaves_global_recorder_ownership_to_the_host() {
    with_metrics_test_lock(|| {
        reset_metrics();
        assert!(
            metrics::set_global_recorder(HostRecorder).is_ok(),
            "check metrics leave the global recorder available to the host"
        );
        record_check_run("success").expect("success is a bounded outcome");
        record_diagnostic_severity("warning", 1).expect("warning is a bounded diagnostic severity");
        record_phase_duration("total", 7_000_000).expect("total is a bounded duration label");
        metrics::counter!("test_host_unrelated_metric").increment(1);
        assert_eq!(HOST_CHECK_METRIC.load(Ordering::Relaxed), 1);
        assert_eq!(HOST_DIAGNOSTIC_METRIC.load(Ordering::Relaxed), 1);
        assert_eq!(HOST_DURATION_METRIC.load(Ordering::Relaxed), 1);
        assert_eq!(HOST_METRIC.load(Ordering::Relaxed), 1);
    });
}
