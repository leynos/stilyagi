//! Dev-only helpers providing centralised repository-relative fixture access for
//! `stilyagi-extract` and `stilyagi-pyext` tests via [`repository_root`],
//! [`corpus_fixture_path`], [`read_corpus_fixture`], [`fixture_paths_in`],
//! [`golden_markdown_ir_fixture`], [`golden_python_ir_fixture`],
//! [`apply_round_trip_edits`], and [`SHARED_MARKDOWN_FIXTURE_PATH`].

mod golden_fixture_builder;
mod golden_ir;
mod round_trip_edits;

pub use golden_fixture_builder::{
    GoldenPythonFixtureError, GoldenRustFixtureError, golden_markdown_ir_fixture,
    golden_python_ir_fixture, golden_rust_ir_fixture,
};
pub use golden_ir::{ByteSpan, GoldenBody, GoldenDocument, GoldenRegion, Segment, SpanError};
pub use round_trip_edits::{
    RoundTripEdit, RoundTripEditError, RoundTripEditResult, apply_round_trip_edits,
};
pub use stilyagi_test_fixtures::{
    ATTRIBUTE_RUST_FIXTURE_PATH, EDGE_CASE_PYTHON_FIXTURE_PATH, FixturePathError,
    FixturePathErrorKind, FixtureReadError, MALFORMED_PYTHON_FIXTURE_PATH,
    MALFORMED_RUST_FIXTURE_PATH, MULTILINE_RUST_FIXTURE_PATH, NESTED_PYTHON_FIXTURE_PATH,
    NESTED_RUST_FIXTURE_PATH, SHARED_MARKDOWN_FIXTURE_PATH, SHARED_PYTHON_FIXTURE_PATH,
    SHARED_RUST_FIXTURE_PATH, corpus_fixture_path, fixture_paths_in, normalize_repository_path,
    read_corpus_fixture, read_corpus_fixture_bytes, repository_root,
};
