//! Duration histogram snapshot tests.

use std::{sync::atomic::Ordering, time::Duration};

use pyo3::{prelude::*, types::PyDict};
use rstest::rstest;

use super::{super::DurationHistogram, assert_metric_values, dictionary, populated_snapshot};
use crate::tests::payload::dict_item;

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

fn sum_seconds(distribution: &Bound<'_, PyDict>) -> PyResult<f64> {
    dict_item(distribution, "sum_seconds")?.extract()
}

#[rstest]
fn serializes_duration_counts_sums_and_cumulative_buckets() {
    let snapshot = populated_snapshot().expect("bounded metrics serialize");
    Python::attach(|py| {
        let bound_snapshot = snapshot.bind(py);
        let phases = dictionary(bound_snapshot, "stilyagi_check_phase_duration_seconds")
            .expect("phase distributions are present");
        let discovery = dictionary(&phases, "discovery").expect("discovery phase is present");
        assert_metric_values(&discovery, &[("count", 1)]);
        assert_eq!(
            sum_seconds(&discovery)
                .expect("discovery duration sum is numeric")
                .to_bits(),
            Duration::from_micros(500).as_secs_f64().to_bits()
        );
        let discovery_buckets =
            dictionary(&discovery, "buckets").expect("discovery buckets are present");
        assert_metric_values(
            &discovery_buckets,
            &[("0.001", 1), ("0.01", 1), ("0.1", 1), ("1", 1), ("+Inf", 1)],
        );
        let total = dictionary(&phases, "total").expect("total duration is present");
        assert_metric_values(&total, &[("count", 1)]);
        assert_eq!(
            sum_seconds(&total)
                .expect("total duration sum is numeric")
                .to_bits(),
            Duration::from_secs(3).as_secs_f64().to_bits()
        );
        let total_buckets = dictionary(&total, "buckets").expect("total buckets are present");
        assert_metric_values(
            &total_buckets,
            &[("0.001", 0), ("0.01", 0), ("0.1", 0), ("1", 0), ("+Inf", 1)],
        );
    });
}
