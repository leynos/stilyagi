//! Property tests for corpus fixture path validation.

use proptest::prelude::*;
use std::path::PathBuf;
use stilyagi_test_support::{FixturePathErrorKind, corpus_fixture_path};

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
        prop_assert!(corpus_fixture_path(path).is_ok());
    }
}

#[test]
fn rejects_absolute_path_property() {
    let path = if cfg!(windows) {
        "C:\\tmp\\evil"
    } else {
        "/tmp/evil"
    };
    let Err(error) = corpus_fixture_path(path) else {
        panic!("expected absolute path rejection");
    };
    assert_eq!(error.kind, FixturePathErrorKind::Absolute);
}

#[test]
fn rejects_parent_dir_property() {
    let Err(error) = corpus_fixture_path("../../outside") else {
        panic!("expected parent traversal rejection");
    };
    assert_eq!(error.kind, FixturePathErrorKind::ParentTraversal);
}

#[test]
#[cfg(windows)]
fn rejects_drive_prefix_property() {
    let Err(error) = corpus_fixture_path(std::path::Path::new("C:\\boot.ini")) else {
        panic!("expected drive prefix rejection");
    };
    assert_eq!(error.kind, FixturePathErrorKind::Prefix);
}

#[test]
#[cfg(windows)]
fn rejects_root_relative_property() {
    let Err(error) = corpus_fixture_path(std::path::Path::new("\\etc")) else {
        panic!("expected root-relative rejection");
    };
    assert_eq!(error.kind, FixturePathErrorKind::RootRelative);
}
