//! Probe proving `make update-snapshots` regenerates this crate's snapshots.
//!
//! The target is deliberately absent from `test` and CI, so a real run is the
//! only thing that proves it still reaches this crate. The end-to-end test in
//! `tests/extract/snapshot_update_e2e.rs` stages a stale snapshot in a scratch
//! directory and narrows the target to this probe through
//! `SNAPSHOT_UPDATE_ARGS`. The probe is ignored because the ordinary suite
//! never stages that directory.

use rstest::rstest;
use stilyagi_test_support::snapshot_update::{
    EXTRACT_PROBE_ACCEPTED,
    EXTRACT_PROBE_DIR,
    EXTRACT_PROBE_SNAPSHOT,
    snapshot_probe_root,
};

/// Assert the staged snapshot, which the update target regenerates.
#[rstest]
#[ignore = "the update-snapshots end-to-end test runs this in a child process"]
fn snapshot_update_probe() {
    let directory = snapshot_probe_root()
        .expect("expected the repository layout")
        .join(EXTRACT_PROBE_DIR);
    let mut settings = insta::Settings::clone_current();
    settings.set_snapshot_path(directory);
    settings.set_prepend_module_to_snapshot(false);
    settings.bind(|| insta::assert_snapshot!(EXTRACT_PROBE_SNAPSHOT, EXTRACT_PROBE_ACCEPTED));
}
