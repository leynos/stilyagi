//! Dev-only helpers providing centralised repository-relative fixture access for
//! `stilyagi-extract` and `stilyagi-pyext` tests via [`repository_root`],
//! [`corpus_fixture_path`], [`read_corpus_fixture`], [`fixture_paths_in`],
//! [`golden_markdown_ir_fixture`], [`apply_round_trip_edits`], and
//! [`SHARED_MARKDOWN_FIXTURE_PATH`].

mod fixture_paths;
mod fixture_reads;
mod golden_fixture_builder;
mod golden_ir;
mod round_trip_edits;

pub use fixture_paths::{
    FixturePathError, FixturePathErrorKind, MALFORMED_PYTHON_FIXTURE_PATH,
    SHARED_MARKDOWN_FIXTURE_PATH, SHARED_PYTHON_FIXTURE_PATH, corpus_fixture_path,
    normalize_repository_path, repository_root,
};
pub use fixture_reads::{
    FixtureReadError, fixture_paths_in, read_corpus_fixture, read_corpus_fixture_bytes,
};
pub use golden_fixture_builder::{
    GoldenPythonFixtureError, golden_markdown_ir_fixture, golden_python_ir_fixture,
};
pub use golden_ir::{ByteSpan, GoldenBody, GoldenDocument, GoldenRegion, Segment, SpanError};
pub use round_trip_edits::{
    RoundTripEdit, RoundTripEditError, RoundTripEditResult, apply_round_trip_edits,
};
