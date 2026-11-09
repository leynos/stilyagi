//! End-to-end coverage for the snapshot review workflow.
//!
//! `make update-snapshots` is deliberately absent from `test` and CI, so the
//! workflow it drives has three observable facts that must hold: a mismatch
//! fails without rewriting the committed snapshot, running insta in update
//! mode regenerates that snapshot, and the next ordinary run passes.
//!
//! The driver test proves all three in an isolated snapshot directory under
//! `CARGO_TARGET_TMPDIR`. It runs the probe in a child process of this test
//! binary, in that directory, rather than nesting a Cargo build, and sets the
//! child's `insta` environment explicitly. The child therefore runs in exactly
//! the mode the driver chooses even when the suite itself was started under
//! `INSTA_UPDATE=always`. That matters: `make update-snapshots` runs this
//! crate's tests with that variable set, and an in-process probe would silently
//! take the update path there.
//!
//! A third test runs the real `make update-snapshots` target with `CARGO`
//! replaced by a shell shim. The shim reports the update mode and the package
//! arguments the recipe supplies, then execs `cargo test` narrowed to the
//! isolated regeneration test, so the target's own environment drives a real
//! regeneration instead of the target recursively running this whole module.
//! A text contract on the Makefile and the hosted workflows then pins where
//! update mode may be enabled.
//!
//! Files are read through `cap_std` directory handles, matching the
//! capability-oriented filesystem policy the rest of the test estate follows.

use std::{path::PathBuf, process::Output};

use cap_std::{ambient_authority, fs::Dir};
use rstest::rstest;
use stilyagi_test_support::repository_root;

/// Scratch directory name for the isolated snapshot probe.
const SCRATCH_DIR: &str = "snapshot_workflow";

/// Scratch directory the update-mode regeneration test writes to.
const UPDATE_SCRATCH_DIR: &str = "snapshot_workflow_update";

/// Snapshot name used by the isolated workflow probe.
const PROBE_SNAPSHOT: &str = "workflow_probe";

/// Snapshot file the probe reads inside the scratch directory.
const PROBE_SNAPSHOT_FILE: &str = "workflow_probe.snap";

/// The value the probe asserts, and the spelling an accepted snapshot holds.
const ACCEPTED_TEXT: &str = "accepted spelling";

/// The stale value a committed snapshot holds before the mismatch.
const STALE_TEXT: &str = "stale spelling";

/// The assignment only the local `update-snapshots` recipe may carry.
const UPDATE_ASSIGNMENT: &str = "INSTA_UPDATE=always";

/// Exact name of the probe test the driver runs in a child process.
const PROBE_TEST: &str = "snapshot_workflow::probe_asserts_the_accepted_value";

/// Exact name of the isolated regeneration test the recipe shim runs.
const UPDATE_TEST: &str = "snapshot_workflow::update_mode_regenerates_the_isolated_snapshot";

/// Return an empty scratch directory named `name` for an isolated snapshot.
fn scratch_snapshot_dir(name: &str) -> std::io::Result<Dir> {
    let root = Dir::open_ambient_dir(env!("CARGO_TARGET_TMPDIR"), ambient_authority())?;
    root.remove_dir_all(name).or_else(|error| {
        if error.kind() == std::io::ErrorKind::NotFound {
            Ok(())
        } else {
            Err(error)
        }
    })?;
    root.create_dir_all(name)?;
    root.open_dir(name)
}

/// Return the absolute path of the isolated snapshot directory named `name`.
///
/// `insta` resolves its own paths, so the redirect is passed as a path rather
/// than as the directory handle used for the test's own reads and writes.
fn scratch_snapshot_path(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_TARGET_TMPDIR")).join(name)
}

/// Render a committed snapshot file holding `body` as its value.
fn committed_snapshot(body: &str) -> String {
    format!("---\nsource: tests/extract/snapshot_workflow.rs\n---\n{body}\n")
}

/// Run the ignored probe in a child process, optionally in insta's update mode.
///
/// The child's working directory is the scratch snapshot directory, which is
/// how the probe finds the snapshot to assert against. Its `insta` environment
/// is set here rather than inherited, so a suite started under
/// `INSTA_UPDATE=always` cannot turn the mismatch phase into an update, and an
/// inherited `INSTA_FORCE_PASS` cannot hide a failure.
fn run_probe(directory: &std::path::Path, update_mode: Option<&str>) -> std::io::Result<Output> {
    let mut command = std::process::Command::new(std::env::current_exe()?);
    command
        .arg("--exact")
        .arg(PROBE_TEST)
        .arg("--ignored")
        .current_dir(directory)
        .env_remove("INSTA_UPDATE")
        .env_remove("INSTA_FORCE_PASS")
        .env_remove("INSTA_OUTPUT");
    if let Some(mode) = update_mode {
        command.env("INSTA_UPDATE", mode);
    }
    command.output()
}

/// Return the committed probe snapshot's text.
fn probe_snapshot_text(snapshots: &Dir) -> std::io::Result<String> {
    snapshots.read_to_string(PROBE_SNAPSHOT_FILE)
}

/// Return a child's captured output as a failure message.
fn child_report(output: &Output) -> String {
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    format!(
        "status {}\nstdout:\n{stdout}\nstderr:\n{stderr}",
        output.status
    )
}

/// Assert the probe's value against the snapshot in the working directory.
///
/// Ignored so an ordinary suite run never asserts against a snapshot the driver
/// has not staged; the driver runs it in a child process because `insta`'s
/// update mode is process-wide, and picks the directory through that child's
/// working directory.
#[rstest]
#[ignore = "the snapshot workflow driver runs this in a child process"]
fn probe_asserts_the_accepted_value() {
    let directory = std::env::current_dir().expect("expected the probe working directory");
    let mut settings = insta::Settings::clone_current();
    settings.set_snapshot_path(directory);
    settings.set_prepend_module_to_snapshot(false);
    settings.bind(|| insta::assert_snapshot!(PROBE_SNAPSHOT, ACCEPTED_TEXT));
}

/// A mismatch must fail without rewriting the snapshot, insta's update mode
/// must regenerate it, and the next ordinary run must pass.
#[rstest]
fn snapshot_mismatch_fails_until_insta_updates_the_snapshot() {
    let snapshots =
        scratch_snapshot_dir(SCRATCH_DIR).expect("expected an isolated snapshot directory");
    snapshots
        .write(PROBE_SNAPSHOT_FILE, committed_snapshot(STALE_TEXT))
        .expect("expected the stale snapshot to be writable");
    let directory = scratch_snapshot_path(SCRATCH_DIR);

    let mismatch = run_probe(&directory, None).expect("expected the probe to run");
    assert!(
        !mismatch.status.success(),
        "expected the stale snapshot to fail the probe:\n{}",
        child_report(&mismatch)
    );
    assert_eq!(
        probe_snapshot_text(&snapshots).expect("expected the snapshot to be readable"),
        committed_snapshot(STALE_TEXT),
        "a failed run must leave the committed snapshot untouched"
    );

    let update = run_probe(&directory, Some("always")).expect("expected the probe to run");
    assert!(
        update.status.success(),
        "expected insta's update mode to accept the new value:\n{}",
        child_report(&update)
    );
    let regenerated =
        probe_snapshot_text(&snapshots).expect("expected the updated snapshot to be readable");
    assert!(
        regenerated.contains(ACCEPTED_TEXT) && !regenerated.contains(STALE_TEXT),
        "expected the update run to regenerate the snapshot, got:\n{regenerated}"
    );

    let accepted = run_probe(&directory, None).expect("expected the probe to run");
    assert!(
        accepted.status.success(),
        "expected the regenerated snapshot to pass every later run:\n{}",
        child_report(&accepted)
    );
}

/// `make update-snapshots` must regenerate a stale snapshot under its own
/// environment rather than relying on the driver to pass `INSTA_UPDATE`.
///
/// Ignored so the ordinary suite never shares this scratch directory with the
/// recipe shim, which runs this test in its own child process.
#[rstest]
#[ignore = "the update-snapshots shim runs this in a child process"]
fn update_mode_regenerates_the_isolated_snapshot() {
    let snapshots =
        scratch_snapshot_dir(UPDATE_SCRATCH_DIR).expect("expected an isolated snapshot directory");
    snapshots
        .write(PROBE_SNAPSHOT_FILE, committed_snapshot(STALE_TEXT))
        .expect("expected the stale snapshot to be writable");

    let update = run_probe(&scratch_snapshot_path(UPDATE_SCRATCH_DIR), Some("always"))
        .expect("expected the probe to run");
    assert!(
        update.status.success(),
        "expected insta's update mode to accept the new value:\n{}",
        child_report(&update)
    );
    let regenerated =
        probe_snapshot_text(&snapshots).expect("expected the updated snapshot to be readable");
    assert!(
        regenerated.contains(ACCEPTED_TEXT) && !regenerated.contains(STALE_TEXT),
        "expected the update run to regenerate the snapshot, got:\n{regenerated}"
    );
}

/// Build the `CARGO` override that lets the real recipe drive this crate's
/// isolated regeneration test.
///
/// The shim reports the environment the recipe supplies, then narrows the
/// recipe's own `cargo test` to one test in a temporary snapshot directory.
/// That proves the target's update mode end to end without letting it rewrite
/// any committed snapshot. `make` expands `$$` to `$`, so the inner shell sees
/// the variable references intact; the single quotes stop the outer shell from
/// expanding them first.
fn update_recipe_shim() -> String {
    format!(
        concat!(
            "sh -c 'echo shim_update=$${{INSTA_UPDATE}}; echo shim_args=$$*; ",
            "unset CARGO; exec cargo test -p stilyagi-extract ",
            "--test extract_integration -- --exact --ignored {}'"
        ),
        UPDATE_TEST
    )
}

/// The local recipe must reach both snapshot-bearing crates in update mode.
#[rstest]
fn make_update_snapshots_runs_both_crates_in_update_mode() {
    let repository = repository_root().expect("expected the repository root");
    let output = std::process::Command::new("make")
        .arg("-s")
        .arg("update-snapshots")
        .arg(format!("CARGO={}", update_recipe_shim()))
        .current_dir(repository)
        .env_remove("INSTA_UPDATE")
        .env_remove("INSTA_FORCE_PASS")
        .output()
        .expect("expected make update-snapshots to run");
    let stdout = String::from_utf8_lossy(&output.stdout);

    assert!(
        output.status.success(),
        "expected make update-snapshots to succeed:\n{}",
        child_report(&output)
    );
    assert!(
        stdout.contains("shim_update=always"),
        "expected the recipe to supply {UPDATE_ASSIGNMENT} to Cargo, got:\n{stdout}"
    );
    assert!(
        stdout.contains("shim_args=-p stilyagi-extract -p stilyagi-pyext"),
        "expected the recipe to regenerate snapshots for both crates, got:\n{stdout}"
    );
}

/// Return whether `name` names a hosted workflow file.
fn is_workflow_file(name: &str) -> bool {
    let Some(extension) = std::path::Path::new(name).extension() else {
        return false;
    };
    extension.eq_ignore_ascii_case("yml") || extension.eq_ignore_ascii_case("yaml")
}

/// Return every hosted workflow file name under `workflows`.
fn workflow_files(workflows: &Dir) -> std::io::Result<Vec<String>> {
    let mut names = workflows
        .read_dir(".")?
        .map(|entry| {
            entry.map(|directory_entry| directory_entry.file_name().to_string_lossy().into_owned())
        })
        .collect::<std::io::Result<Vec<_>>>()?;
    names.retain(|name| is_workflow_file(name));
    names.sort();
    Ok(names)
}

/// Return the target whose recipe holds the first line containing `needle`.
fn enclosing_target<'a>(makefile: &'a str, needle: &str) -> Option<&'a str> {
    let mut target = None;
    for line in makefile.lines() {
        if line.starts_with('\t') {
            if line.contains(needle) {
                return target;
            }
            continue;
        }
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        let Some((head, _)) = line.split_once(':') else {
            continue;
        };
        if !head.contains('=') {
            target = Some(head.trim());
        }
    }
    None
}

/// Only the local `update-snapshots` recipe may enable `insta` updates.
#[rstest]
fn insta_update_mode_is_confined_to_the_local_recipe() {
    let repository = Dir::open_ambient_dir(
        repository_root().expect("expected the repository root"),
        ambient_authority(),
    )
    .expect("expected the repository directory handle");
    let makefile = repository
        .read_to_string("Makefile")
        .expect("expected a readable Makefile");

    assert!(
        makefile.contains(UPDATE_ASSIGNMENT),
        "expected update-snapshots to accept snapshots with {UPDATE_ASSIGNMENT}"
    );
    assert_eq!(
        enclosing_target(&makefile, "INSTA_UPDATE"),
        Some("update-snapshots"),
        "{UPDATE_ASSIGNMENT} must stay in the local, reviewed recipe"
    );
    assert_eq!(
        makefile.matches("INSTA_UPDATE").count(),
        1,
        "no other Makefile recipe may enable insta updates"
    );

    let workflows = repository
        .open_dir(".github/workflows")
        .expect("expected the hosted workflow directory");
    for name in workflow_files(&workflows).expect("expected the hosted workflow files") {
        let contents = workflows
            .read_to_string(&name)
            .expect("expected a readable hosted workflow file");
        assert!(
            !contents.contains("INSTA_UPDATE="),
            ".github/workflows/{name} must not enable insta updates, so a mismatch fails the run"
        );
    }
}
