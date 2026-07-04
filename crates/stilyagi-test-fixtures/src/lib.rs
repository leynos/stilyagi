//! Dependency-free repository-relative fixture path and read helpers.
//!
//! This crate holds the low-level, syntax-agnostic fixture access used across
//! the workspace test suites: validated repository-relative paths, the shared
//! corpus path constants, and readers that never escape the repository
//! boundary. It deliberately depends on nothing from the extraction crates so
//! that extractor crates (for example `stilyagi-tree-sitter`) can consume it
//! from their tests without forming a dependency cycle through
//! `stilyagi-test-support`.

mod fixture_paths;
mod fixture_reads;

pub use fixture_paths::{
    EDGE_CASE_PYTHON_FIXTURE_PATH, FixturePathError, FixturePathErrorKind,
    MALFORMED_PYTHON_FIXTURE_PATH, MALFORMED_RUST_FIXTURE_PATH, MULTILINE_RUST_FIXTURE_PATH,
    NESTED_PYTHON_FIXTURE_PATH, NESTED_RUST_FIXTURE_PATH, SHARED_MARKDOWN_FIXTURE_PATH,
    SHARED_PYTHON_FIXTURE_PATH, SHARED_RUST_FIXTURE_PATH, corpus_fixture_path,
    normalize_repository_path, repository_root,
};
pub use fixture_reads::{
    FixtureReadError, fixture_paths_in, read_corpus_fixture, read_corpus_fixture_bytes,
};
