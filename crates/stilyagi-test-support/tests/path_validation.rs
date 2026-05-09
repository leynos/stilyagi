//! Property and panic tests for corpus fixture path validation.

use proptest::prelude::*;
use std::path::PathBuf;
use stilyagi_test_support::corpus_fixture_path;

proptest! {
    /// A valid simple relative path is accepted without panicking.
    #[test]
    fn accepts_simple_relative_path(
        segment in "[a-z][a-z0-9_-]{0,15}",
        name in "[a-z][a-z0-9_-]{0,15}\\.(md|rs|py|txt)",
    ) {
        let path: PathBuf = [
            "tests", "fixtures", "corpus", segment.as_str(), name.as_str()
        ].iter().collect();
        // Must not panic; we don't care about I/O errors from the non-existent file.
        drop(corpus_fixture_path(path));
    }
}

#[test]
#[should_panic(expected = "corpus fixture path must be repository-relative")]
fn rejects_absolute_path_property() {
    let path = if cfg!(windows) {
        "C:\\tmp\\evil"
    } else {
        "/tmp/evil"
    };
    drop(corpus_fixture_path(path));
}

#[test]
#[should_panic(expected = "corpus fixture path must not contain parent-directory traversal")]
fn rejects_parent_dir_property() {
    drop(corpus_fixture_path("../../outside"));
}

#[test]
#[cfg(windows)]
#[should_panic(expected = "corpus fixture path must not contain a drive or path prefix")]
fn rejects_drive_prefix_property() {
    drop(corpus_fixture_path(std::path::Path::new("C:\\boot.ini")));
}

#[test]
#[cfg(windows)]
#[should_panic(expected = "corpus fixture path must not be root-relative")]
fn rejects_root_relative_property() {
    drop(corpus_fixture_path(std::path::Path::new("\\etc")));
}
