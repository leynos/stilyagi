//! Integration tests for corpus fixture path rejection.

#[rstest::rstest]
fn corpus_fixture_path_rejects_absolute_path() {
    let path = "/etc/passwd";
    let Err(error) = stilyagi_test_support::corpus_fixture_path(path) else {
        panic!("expected absolute path rejection");
    };
    assert_eq!(
        error.kind,
        stilyagi_test_support::FixturePathErrorKind::Absolute,
    );
}

fn assert_corpus_fixture_path_rejects(
    path: impl AsRef<std::path::Path>,
    expected_kind: stilyagi_test_support::FixturePathErrorKind,
) {
    let Err(error) = stilyagi_test_support::corpus_fixture_path(path) else {
        panic!("expected a FixturePathError with kind {expected_kind:?}");
    };
    assert_eq!(error.kind, expected_kind);
}

#[rstest::rstest]
fn corpus_fixture_path_rejects_parent_traversal() {
    assert_corpus_fixture_path_rejects(
        "../../etc/passwd",
        stilyagi_test_support::FixturePathErrorKind::ParentTraversal,
    );
}

#[rstest::rstest]
#[cfg(windows)]
fn corpus_fixture_path_rejects_drive_prefix() {
    assert_corpus_fixture_path_rejects(
        std::path::Path::new("C:\\windows\\system32"),
        stilyagi_test_support::FixturePathErrorKind::Prefix,
    );
}

#[rstest::rstest]
#[cfg(windows)]
fn corpus_fixture_path_rejects_root_relative() {
    assert_corpus_fixture_path_rejects(
        std::path::Path::new("\\etc"),
        stilyagi_test_support::FixturePathErrorKind::RootRelative,
    );
}
