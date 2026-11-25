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
//!
//! The probes derive their snapshot directory from a compiled-in path, so each
//! run addresses the same files and cannot be redirected to a private root
//! without an environment override the probes deliberately never read. One
//! driver therefore takes an exclusive cross-process lock over the staged root
//! for the whole reset-stage-run-read sequence, and the next waits for it. The
//! staged root is removed before the lock is released, so a later run never
//! inherits a half-written tree.
//!
//! The driver is Unix-only: it drives the repository's `make` recipe and its
//! cross-process guard is a POSIX advisory lock. The parent module declares it
//! under `cfg(unix)`, so nothing here needs a second platform story.

use std::{
    error::Error,
    path::{Path, PathBuf},
    process::Output,
    thread,
    time::{Duration, Instant},
};

use cap_std::{ambient_authority, fs::Dir};
use rstest::rstest;
use rustix::{
    fs::{FlockOperation, flock},
    io::Errno,
};
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

/// File name of the cross-process guard over the shared probe root.
const PROBE_ROOT_LOCK_FILE: &str = "snapshot_update_e2e.lock";

/// Longest a driver waits for another run to release the shared root.
const LOCK_WAIT: Duration = Duration::from_secs(600);

/// Pause between lock attempts while another driver owns the root.
const LOCK_POLL_INTERVAL: Duration = Duration::from_millis(100);

/// Exclusive cross-process guard over the shared probe root.
///
/// The lock lives on a descriptor opened through a directory handle, so it
/// follows the capability-based filesystem policy the test estate uses rather
/// than naming an ambient path. Holding the descriptor alive for the whole
/// sequence is what keeps a second driver out; closing it releases the lock.
/// The wait is bounded, so a driver that cannot take the root reports a
/// timeout instead of blocking a gate indefinitely.
struct ProbeRootLock {
    /// Locked file, held for as long as the guard lives.
    file: cap_std::fs::File,
}

impl ProbeRootLock {
    /// Wait up to [`LOCK_WAIT`] for exclusive ownership of the probe root.
    ///
    /// # Errors
    ///
    /// Returns an I/O error when the lock file cannot be opened, when the
    /// platform lock fails, or when the wait expires.
    fn acquire(repository: &Path) -> TestResult<Self> {
        let handle = Dir::open_ambient_dir(repository, ambient_authority())?;
        handle.create_dir_all("target/tmp")?;
        let mut options = cap_std::fs::OpenOptions::new();
        options.create(true).read(true).write(true);
        let file =
            handle.open_with(Path::new("target/tmp").join(PROBE_ROOT_LOCK_FILE), &options)?;
        wait_for_lock(&file)?;
        Ok(Self { file })
    }
}

impl Drop for ProbeRootLock {
    fn drop(&mut self) {
        // Best effort: closing the file releases the lock in any case, and a
        // `Drop` has no channel through which to report an unlock failure.
        let _released = flock(&self.file, FlockOperation::Unlock);
    }
}

/// Poll `file` until this run owns the exclusive lock or the wait expires.
///
/// `flock` reports a held lock as `EWOULDBLOCK`, and the operation is retried
/// after a short pause until the deadline. Any other error is a real failure
/// and is propagated rather than retried.
fn wait_for_lock(file: &cap_std::fs::File) -> TestResult<()> {
    let deadline = Instant::now() + LOCK_WAIT;
    loop {
        match flock(file, FlockOperation::NonBlockingLockExclusive) {
            Ok(()) => return Ok(()),
            Err(Errno::WOULDBLOCK) if Instant::now() >= deadline => {
                return Err(Box::new(std::io::Error::new(
                    std::io::ErrorKind::TimedOut,
                    "timed out waiting for another snapshot update driver",
                )));
            }
            Err(Errno::WOULDBLOCK) => thread::sleep(LOCK_POLL_INTERVAL),
            Err(error) => return Err(Box::new(std::io::Error::from(error))),
        }
    }
}

/// The staged probe root, the lock that owns it, and its cleanup.
///
/// Dropping the guard removes the staged root and then releases the lock, so
/// the next driver never inherits a half-written tree and an early `?` part-way
/// through the phases still cleans up.
struct StagedProbeRoot {
    /// Absolute path of the staged root.
    root: PathBuf,
    /// Repository the root lives under, needed to remove it.
    repository: PathBuf,
    /// Exclusive ownership of the root, released after the cleanup above.
    _lock: ProbeRootLock,
}

impl StagedProbeRoot {
    /// Take the lock and stage a stale snapshot for each crate.
    ///
    /// # Errors
    ///
    /// Returns an error when the lock cannot be acquired, the repository root
    /// cannot be resolved, or a staged snapshot cannot be written.
    fn create() -> TestResult<Self> {
        let repository = repository_root()?;
        let lock = ProbeRootLock::acquire(&repository)?;
        let root = stage_stale_snapshots(&repository)?;
        Ok(Self {
            root,
            repository,
            _lock: lock,
        })
    }

    /// Return the staged root's absolute path.
    fn root(&self) -> &Path { &self.root }

    /// Remove the staged root, leaving the lock held.
    fn remove_staged_root(&self) -> std::io::Result<()> {
        let relative = self
            .root
            .strip_prefix(&self.repository)
            .map_err(|error| std::io::Error::new(std::io::ErrorKind::InvalidInput, error))?;
        let target = Dir::open_ambient_dir(&self.repository, ambient_authority())?;
        target.remove_dir_all(relative)
    }
}

impl Drop for StagedProbeRoot {
    fn drop(&mut self) {
        // Best effort: a cleanup failure must not mask the driver's own result.
        let _cleanup = self.remove_staged_root();
    }
}

/// Stage a stale snapshot for each crate and return the scratch root.
fn stage_stale_snapshots(repository: &Path) -> TestResult<PathBuf> {
    let root = snapshot_probe_root()?;
    let relative = root.strip_prefix(repository)?;
    let target = Dir::open_ambient_dir(repository, ambient_authority())?;
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
    let staged = StagedProbeRoot::create()?;
    let mismatch = run_probes()?;
    let stale_snapshots = staged_snapshot_texts(staged.root())?;
    let update = run_update_target()?;
    let regenerated_snapshots = staged_snapshot_texts(staged.root())?;
    let accepted = run_probes()?;
    let evidence = SnapshotUpdateEvidence {
        mismatch,
        stale_snapshots,
        update,
        regenerated_snapshots,
        accepted,
    };
    // Remove the staged root while the lock is still held, so the next driver
    // starts from an absent tree rather than from this one's leftovers.
    drop(staged);
    Ok(evidence)
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
