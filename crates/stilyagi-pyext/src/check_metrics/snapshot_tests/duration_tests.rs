//! Duration histogram snapshot tests.

use std::sync::atomic::Ordering;
use std::time::Duration;

use pyo3::prelude::*;
use rstest::rstest;

use super::super::DurationHistogram;
use super::{assert_metric_categories, assert_metric_values, dictionary, populated_snapshot};

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
        let total = dictionary(&phases, "total").expect("total duration is present");
        assert_metric_values(&total, &[("count", 1)]).expect("total duration count is present");
        let total_sum = total
            .get_item("sum_seconds")
            .expect("total duration sum lookup succeeds")
            .expect("total duration sum is present")
            .extract::<f64>()
            .expect("total duration sum is numeric");
        assert_eq!(
            total_sum.to_bits(),
            Duration::from_secs(3).as_secs_f64().to_bits()
        );
        assert_metric_categories(
            &total,
            "buckets",
            &[("0.001", 0), ("0.01", 0), ("0.1", 0), ("1", 0), ("+Inf", 1)],
        )
        .expect("total duration buckets are cumulative");
    });
}
