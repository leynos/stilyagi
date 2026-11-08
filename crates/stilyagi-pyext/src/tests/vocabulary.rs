//! Vocabulary tests pinning the bridge exports against the Rust constants.
//!
//! Each test pairs a semantic comparison with a snapshot: the comparison keeps
//! the relationship to the Rust vocabulary, and the snapshot pins the wire
//! spelling Python callers receive.

use pyo3::prelude::Python;
use rstest::rstest;
use serde_json::json;
use stilyagi_extract::ExtractSyntax;
use stilyagi_ir::{AUTHORED_DIRECTIVE_ERROR_CODES, RegionKind as IrRegionKind};

use super::{
    authored_directive_error_codes_py,
    payload::tuple_strings,
    supported_region_kinds_py,
    supported_syntaxes_py,
};

/// Collects the expected spellings for a vocabulary comparison.
fn expected_strings<'a>(values: impl IntoIterator<Item = &'a str>) -> Vec<String> {
    values.into_iter().map(str::to_owned).collect()
}

/// The bridge's supported syntaxes must mirror `ExtractSyntax::ALL`.
///
/// The snapshot pins the wire spelling, while the comparison beside it keeps
/// the relationship to the Rust vocabulary. Without that comparison a
/// vocabulary change the bridge did not export would still match the old
/// snapshot and pass.
#[rstest]
fn supported_syntaxes_follow_the_rust_extraction_vocabulary() {
    Python::attach(|py| {
        let expected = expected_strings(
            ExtractSyntax::ALL
                .iter()
                .copied()
                .map(ExtractSyntax::as_str),
        );
        let actual = tuple_strings(py, supported_syntaxes_py(py))
            .expect("supported_syntaxes should return a tuple of strings");

        assert_eq!(actual, expected);
        insta::assert_json_snapshot!("supported_syntaxes", json!(actual));
    });
}

/// The bridge's supported region kinds must mirror `IrRegionKind::ALL`.
///
/// See [`supported_syntaxes_follow_the_rust_extraction_vocabulary`] for why the
/// semantic comparison sits beside the snapshot.
#[rstest]
fn supported_region_kinds_follow_the_rust_ir_vocabulary() {
    Python::attach(|py| {
        let expected =
            expected_strings(IrRegionKind::ALL.iter().copied().map(IrRegionKind::as_str));
        let actual = tuple_strings(py, supported_region_kinds_py(py))
            .expect("supported_region_kinds should return a tuple of strings");

        assert_eq!(actual, expected);
        insta::assert_json_snapshot!("supported_region_kinds", json!(actual));
    });
}

/// The bridge's authored-directive error codes must mirror the Rust constants.
///
/// See [`supported_syntaxes_follow_the_rust_extraction_vocabulary`] for why the
/// semantic comparison sits beside the snapshot.
#[rstest]
fn authored_directive_error_codes_follow_the_rust_ir_vocabulary() {
    Python::attach(|py| {
        let expected = expected_strings(AUTHORED_DIRECTIVE_ERROR_CODES.iter().copied());
        let actual = tuple_strings(py, authored_directive_error_codes_py(py))
            .expect("authored_directive_error_codes should return a tuple of strings");

        assert_eq!(actual, expected);
        insta::assert_json_snapshot!("authored_directive_error_codes", json!(actual));
    });
}
