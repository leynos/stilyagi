//! End-to-end coverage for the snapshot review workflow.
//!
//! `make update-snapshots` is deliberately absent from `test` and CI, so the
//! workflow it drives has three observable facts that must hold: a mismatch
//! fails without rewriting the committed snapshot, an accepted value replaces
//! that snapshot, and the next run passes. This module proves all three in an
//! isolated snapshot directory under `CARGO_TARGET_TMPDIR`, using the same
//! `insta` machinery that `INSTA_UPDATE=always` drives, rather than nesting a
//! second Cargo build inside a test. A text contract on the Makefile and the
//! hosted workflows then pins where that update mode may be enabled.
//!
//! Files are read through `cap_std` directory handles, matching the
//! capability-oriented filesystem policy the rest of the test estate follows.

use std::{any::Any, panic::catch_unwind, path::PathBuf};

use cap_std::{ambient_authority, fs::Dir};
use rstest::rstest;
use stilyagi_test_support::repository_root;

/// Scratch directory name for the isolated snapshot probe.
const SCRATCH_DIR: &str = "snapshot_workflow";

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

/// Return an empty scratch directory for the isolated snapshot probe.
fn scratch_snapshot_dir() -> std::io::Result<Dir> {
    let root = Dir::open_ambient_dir(env!("CARGO_TARGET_TMPDIR"), ambient_authority())?;
    root.remove_dir_all(SCRATCH_DIR).or_else(|error| {
        if error.kind() == std::io::ErrorKind::NotFound {
            Ok(())
        } else {
            Err(error)
        }
    })?;
    root.create_dir_all(SCRATCH_DIR)?;
    root.open_dir(SCRATCH_DIR)
}

/// Return the absolute path of the isolated snapshot directory.
///
/// `insta` resolves its own paths, so the redirect is passed as a path rather
/// than as the directory handle used for the test's own reads and writes.
fn scratch_snapshot_path() -> PathBuf {
    PathBuf::from(env!("CARGO_TARGET_TMPDIR")).join(SCRATCH_DIR)
}

/// Render a committed snapshot file holding `body` as its value.
fn committed_snapshot(body: &str) -> String {
    format!("---\nsource: tests/extract/snapshot_workflow.rs\n---\n{body}\n")
}

/// Return a caught panic payload as text.
fn panic_text(payload: &(dyn Any + Send)) -> String {
    if let Some(text) = payload.downcast_ref::<String>() {
        return text.clone();
    }
    if let Some(text) = payload.downcast_ref::<&str>() {
        return (*text).to_owned();
    }
    "non-string panic payload".to_owned()
}

/// Assert the probe's value against the snapshots in `snapshot_path`.
///
/// The committed snapshots live under the scratch directory rather than beside
/// this module, so a failing probe cannot disturb the tracked snapshots.
fn assert_probe(snapshot_path: &std::path::Path) -> Result<(), String> {
    let mut settings = insta::Settings::clone_current();
    settings.set_snapshot_path(snapshot_path);
    settings.set_prepend_module_to_snapshot(false);
    settings.bind(|| {
        catch_unwind(|| insta::assert_snapshot!(PROBE_SNAPSHOT, ACCEPTED_TEXT))
            .map_err(|payload| panic_text(&*payload))
    })
}

/// A mismatch must fail without rewriting the snapshot, and accepting the new
/// value must make the next run pass.
#[rstest]
fn snapshot_mismatch_fails_until_the_accepted_value_is_committed() {
    let snapshots = scratch_snapshot_dir().expect("expected an isolated snapshot directory");
    snapshots
        .write(PROBE_SNAPSHOT_FILE, committed_snapshot(STALE_TEXT))
        .expect("expected the stale snapshot to be writable");

    let failure = assert_probe(&scratch_snapshot_path())
        .expect_err("expected the stale snapshot to fail the probe");
    assert!(
        failure.contains("snapshot assertion"),
        "expected a snapshot mismatch report, got: {failure}"
    );
    assert_eq!(
        snapshots
            .read_to_string(PROBE_SNAPSHOT_FILE)
            .expect("expected the snapshot to be readable"),
        committed_snapshot(STALE_TEXT),
        "a failed run must leave the committed snapshot untouched"
    );

    snapshots
        .write(PROBE_SNAPSHOT_FILE, committed_snapshot(ACCEPTED_TEXT))
        .expect("expected the accepted snapshot to be writable");
    assert_probe(&scratch_snapshot_path()).expect("expected the accepted snapshot to pass");
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
