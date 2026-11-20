//! End-to-end coverage for the `make update-snapshots` target itself.
//!
//! The target is deliberately absent from `test` and CI, so nothing else would
//! notice if it stopped reaching one of the two snapshot-bearing crates. This
//! driver stages a stale snapshot for each crate in an isolated scratch root,
//! runs the real recipe with real Cargo, and checks that both probes
//! regenerated their staged snapshot and that the next ordinary run passes.
//!
//! Recursion is the hazard: the driver runs inside the suite the recipe
//! invokes. The recipe receives `SNAPSHOT_UPDATE_ARGS`, which narrows the run
//! to the two ignored lib probes, so the target cannot select this integration
//! test again. A developer's real `make update-snapshots` does run this driver,
//! and its own narrowed run then completes normally beside it.
//!
//! The probes assert against the repository's untracked `target/tmp`
//! directory, so no tracked snapshot is touched. The nested Cargo runs inherit
//! this process's environment, including any `RUSTFLAGS` and
//! `CARGO_TARGET_DIR`, so they reuse the parent build instead of starting a
//! parallel one.

use std::{
    error::Error,
    path::{Path, PathBuf},
    process::Output,
};

use cap_std::{ambient_authority, fs::Dir};
use rstest::rstest;
use stilyagi_test_support::{
    repository_root,
    snapshot_update::{
        EXTRACT_PROBE_ACCEPTED,
        EXTRACT_PROBE_DIR,
        EXTRACT_PROBE_SNAPSHOT,
        PYEXT_PROBE_ACCEPTED,
        PYEXT_PROBE_DIR,
        PYEXT_PROBE_SNAPSHOT,
        SNAPSHOT_PROBE_FILTER,
        SNAPSHOT_PROBE_STALE,
        snapshot_probe_root,
    },
};

use super::test_utils::child_report;

/// Fallible driver step, propagated to the test body with `?`.
type TestResult<T = ()> = Result<T, Box<dyn Error>>;

/// One crate's staged probe: where it lives and what it must produce.
#[derive(Clone, Copy)]
struct StagedProbe {
    directory: &'static str,
    snapshot: &'static str,
    accepted: &'static str,
}

/// The two staged probes, in the order the driver stages and reads them.
const STAGED_PROBES: [StagedProbe; 2] = [
    StagedProbe {
        directory: EXTRACT_PROBE_DIR,
        snapshot: EXTRACT_PROBE_SNAPSHOT,
        accepted: EXTRACT_PROBE_ACCEPTED,
    },
    StagedProbe {
        directory: PYEXT_PROBE_DIR,
        snapshot: PYEXT_PROBE_SNAPSHOT,
        accepted: PYEXT_PROBE_ACCEPTED,
    },
];

/// Stage a stale snapshot for each crate and return the scratch root.
fn stage_stale_snapshots() -> TestResult<PathBuf> {
    let repository = repository_root()?;
    let root = snapshot_probe_root()?;
    let relative = root.strip_prefix(&repository)?;
    let target = Dir::open_ambient_dir(&repository, ambient_authority())?;
    target.remove_dir_all(relative).or_else(ignore_missing)?;
    for probe in STAGED_PROBES {
        let staged = relative.join(probe.directory);
        target.create_dir_all(&staged)?;
        target.open_dir(&staged)?.write(
            format!("{}.snap", probe.snapshot),
            stale_snapshot(probe.snapshot),
        )?;
    }
    Ok(root)
}

/// Treat an absent scratch directory as already removed.
fn ignore_missing(error: std::io::Error) -> std::io::Result<()> {
    if error.kind() == std::io::ErrorKind::NotFound {
        Ok(())
    } else {
        Err(error)
    }
}

/// Render the stale snapshot file `insta` must replace.
fn stale_snapshot(snapshot: &str) -> String {
    format!("---\nsource: {snapshot}.rs\n---\n{SNAPSHOT_PROBE_STALE}\n")
}

/// Run both probes through Cargo without insta's update mode.
fn run_probes() -> TestResult<Output> {
    let mut command = std::process::Command::new("cargo");
    command
        .arg("test")
        .arg("--lib")
        .args(["-p", "stilyagi-extract", "-p", "stilyagi-pyext"])
        .arg("--")
        .args(["--ignored", SNAPSHOT_PROBE_FILTER])
        .current_dir(repository_root()?);
    remove_insta_overrides(&mut command);
    Ok(command.output()?)
}

/// Run the real `make update-snapshots` recipe, narrowed to the probes.
fn run_update_target() -> TestResult<Output> {
    let mut command = std::process::Command::new("make");
    command
        .arg("-s")
        .arg("update-snapshots")
        .arg(format!(
            "SNAPSHOT_UPDATE_ARGS=--lib -- --ignored {SNAPSHOT_PROBE_FILTER}"
        ))
        .current_dir(repository_root()?);
    remove_insta_overrides(&mut command);
    Ok(command.output()?)
}

/// Strip insta's ambient overrides so each phase chooses its own mode.
fn remove_insta_overrides(command: &mut std::process::Command) {
    command
        .env_remove("INSTA_UPDATE")
        .env_remove("INSTA_FORCE_PASS")
        .env_remove("INSTA_OUTPUT");
}

/// Return a staged snapshot's text.
fn staged_snapshot_text(root: &Path, directory: &str, snapshot: &str) -> TestResult<String> {
    let staged = Dir::open_ambient_dir(root, ambient_authority())?;
    Ok(staged.read_to_string(Path::new(directory).join(format!("{snapshot}.snap")))?)
}

/// Return both crates' staged snapshot texts, in staging order.
fn staged_snapshot_texts(root: &Path) -> TestResult<Vec<String>> {
    STAGED_PROBES
        .iter()
        .map(|probe| staged_snapshot_text(root, probe.directory, probe.snapshot))
        .collect()
}

/// Facts one driver run produces, asserted by the test afterwards.
struct SnapshotUpdateEvidence {
    mismatch: Output,
    stale_snapshots: Vec<String>,
    update: Output,
    regenerated_snapshots: Vec<String>,
    accepted: Output,
}

/// Run the three driver phases and collect what they produced.
///
/// Kept free of assertions so the failure reporting can live in plain
/// functions: a function that returns `Result` must report a problem by
/// returning it, and an assertion there would panic past the caller's `?`.
fn run_snapshot_update_phases() -> TestResult<SnapshotUpdateEvidence> {
    let root = stage_stale_snapshots()?;
    let mismatch = run_probes()?;
    let stale_snapshots = staged_snapshot_texts(&root)?;
    let update = run_update_target()?;
    let regenerated_snapshots = staged_snapshot_texts(&root)?;
    let accepted = run_probes()?;
    Ok(SnapshotUpdateEvidence {
        mismatch,
        stale_snapshots,
        update,
        regenerated_snapshots,
        accepted,
    })
}

/// Assert the stale snapshots failed the ordinary run and stayed untouched.
fn assert_stale_run_failed(evidence: &SnapshotUpdateEvidence) {
    assert!(
        !evidence.mismatch.status.success(),
        "expected the stale snapshots to fail an ordinary run:\n{}",
        child_report(&evidence.mismatch)
    );
    for (probe, staged) in STAGED_PROBES.iter().zip(&evidence.stale_snapshots) {
        assert!(
            staged.contains(SNAPSHOT_PROBE_STALE),
            "a failing probe must leave {}'s snapshot untouched, got:\n{staged}",
            probe.directory
        );
    }
}

/// Assert the target succeeded and rewrote both staged snapshots.
fn assert_target_regenerated_snapshots(evidence: &SnapshotUpdateEvidence) {
    assert!(
        evidence.update.status.success(),
        "expected make update-snapshots to succeed:\n{}",
        child_report(&evidence.update)
    );
    for (probe, staged) in STAGED_PROBES.iter().zip(&evidence.regenerated_snapshots) {
        assert!(
            staged.contains(probe.accepted) && !staged.contains(SNAPSHOT_PROBE_STALE),
            "the target must regenerate {}'s snapshot, got:\n{staged}",
            probe.directory
        );
    }
}

/// Assert the regenerated snapshots pass an ordinary run.
fn assert_probes_pass_after_update(evidence: &SnapshotUpdateEvidence) {
    assert!(
        evidence.accepted.status.success(),
        "expected the regenerated snapshots to pass an ordinary run:\n{}",
        child_report(&evidence.accepted)
    );
}

/// The target must regenerate a stale snapshot for both crates with real Cargo.
#[rstest]
fn make_update_snapshots_regenerates_stale_snapshots_for_both_crates() -> TestResult {
    let evidence = run_snapshot_update_phases()?;
    assert_stale_run_failed(&evidence);
    assert_target_regenerated_snapshots(&evidence);
    assert_probes_pass_after_update(&evidence);
    Ok(())
}
