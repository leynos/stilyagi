//! BDD fixtures that exercise `extract_document_py` and `hello` through `PyO3`.

use pyo3::{
    exceptions::PyKeyError,
    prelude::*,
    types::{PyDict, PyTuple},
};
use rstest::fixture;
use rstest_bdd_macros::{given, scenario, then, when};
use serde_json::Value;
use stilyagi_test_support::{SHARED_MARKDOWN_FIXTURE_PATH, read_corpus_fixture};

use super::{
    extract_document_py,
    hello,
    tests::payload::{dict_list, dict_string, list_dict_at, parse_ir_json, region_kind_and_text},
};

/// Unwrap an `Ok` inside a `then` step or assertion helper, panicking with
/// the caller's location. Not for `given`/`when` steps, which return `Err`.
macro_rules! must_ok {
    ($expression:expr, $($message:tt)+) => {
        match $expression {
            Ok(value) => value,
            Err(error) => panic!("{}: {error}", format_args!($($message)+)),
        }
    };
}

/// Unwrap a `Some` inside a `then` step or assertion helper, panicking with
/// the caller's location.
macro_rules! must_some {
    ($expression:expr, $($message:tt)+) => {
        match $expression {
            Some(value) => value,
            None => panic!("{}", format_args!($($message)+)),
        }
    };
}

type StepResult = Result<(), Box<dyn std::error::Error>>;

struct BridgeState {
    bridge_greeting: Option<&'static str>,
    core_greeting: Option<&'static str>,
    extracted_document: Option<Py<PyDict>>,
    expected_document_text: Option<String>,
}

#[fixture]
fn bridge_state() -> BridgeState {
    BridgeState {
        bridge_greeting: None,
        core_greeting: None,
        extracted_document: None,
        expected_document_text: None,
    }
}

fn perform_extraction(source: &str, syntax: &str, bridge_state: &mut BridgeState) -> PyResult<()> {
    let document = Python::attach(|py| {
        let args = PyTuple::new(py, [source, syntax])?;
        extract_document_py(py, &args)
    })?;
    bridge_state.extracted_document = Some(document);
    Ok(())
}

#[given("the bridge can call the shared smoke greeting")]
fn bridge_can_call_the_shared_smoke_greeting(bridge_state: &mut BridgeState) {
    bridge_state.core_greeting = Some(stilyagi_core::smoke_hello());
}

#[when("the bridge produces a hello greeting")]
fn bridge_produces_a_hello_greeting(bridge_state: &mut BridgeState) {
    bridge_state.bridge_greeting = Some(hello());
}

#[then("the greeting matches the core crate greeting")]
fn greeting_matches_the_core_crate_greeting(bridge_state: &BridgeState) {
    assert_eq!(bridge_state.bridge_greeting, bridge_state.core_greeting);
}

#[then("the greeting is not the legacy Python fallback")]
fn greeting_is_not_the_legacy_python_fallback(bridge_state: &BridgeState) {
    assert_ne!(bridge_state.bridge_greeting, Some("hello from Python"));
}

#[given("the bridge can call the Rust extraction entrypoint")]
fn bridge_can_call_the_rust_extraction_entrypoint() {}

#[when("the bridge extracts a Markdown document")]
fn bridge_extracts_a_markdown_document(bridge_state: &mut BridgeState) -> StepResult {
    perform_extraction("# Heading", "markdown", bridge_state)?;
    bridge_state.expected_document_text = Some("Heading".to_owned());
    Ok(())
}

#[when("the bridge extracts the shared Markdown fixture")]
fn bridge_extracts_the_shared_markdown_fixture(bridge_state: &mut BridgeState) -> StepResult {
    let source = read_corpus_fixture(SHARED_MARKDOWN_FIXTURE_PATH)?;

    perform_extraction(&source, "markdown", bridge_state)?;
    bridge_state.expected_document_text = Some("Fixture Heading".to_owned());
    Ok(())
}

#[when("the bridge extracts a blank Markdown document")]
fn bridge_extracts_a_blank_markdown_document(bridge_state: &mut BridgeState) -> StepResult {
    perform_extraction("   \n", "markdown", bridge_state)?;
    bridge_state.expected_document_text = Some("   \n".to_owned());
    Ok(())
}

#[then("the extracted document reports Markdown syntax")]
fn extracted_document_reports_markdown_syntax(bridge_state: &BridgeState) {
    let extracted_document = must_some!(
        bridge_state.extracted_document.as_ref(),
        "an extracted document should be present"
    );

    Python::attach(|py| {
        let document = extracted_document.bind(py);

        assert_eq!(
            must_ok!(dict_string(document, "syntax"), "missing syntax payload"),
            "markdown",
        );
    });
}

#[then("the extracted document preserves one source-backed region")]
fn extracted_document_preserves_one_source_backed_region(bridge_state: &BridgeState) {
    assert_expected_document_payload(bridge_state, assert_source_backed_region_payload);
}

fn assert_expected_document_payload(
    bridge_state: &BridgeState,
    assertion: impl FnOnce(Python<'_>, &Py<PyDict>, &str),
) {
    let extracted_document = must_some!(
        bridge_state.extracted_document.as_ref(),
        "an extracted document should be present"
    );
    let expected_text = must_some!(
        bridge_state.expected_document_text.as_deref(),
        "expected_document_text must be provided for this BDD scenario"
    );

    Python::attach(|py| assertion(py, extracted_document, expected_text));
}

#[then("the extracted document has no regions")]
fn extracted_document_has_no_regions(bridge_state: &BridgeState) {
    let extracted_document = must_some!(
        bridge_state.extracted_document.as_ref(),
        "an extracted document should be present"
    );

    Python::attach(|py| {
        let regions = must_ok!(
            dict_list(extracted_document.bind(py), "regions"),
            "missing regions payload"
        );

        assert_eq!(regions.len(), 0);
    });
}

fn assert_source_backed_region_payload(
    py: Python<'_>,
    extracted_document: &Py<PyDict>,
    expected_text: &str,
) {
    let document = extracted_document.bind(py);
    let regions = must_ok!(dict_list(document, "regions"), "missing regions payload");
    let first_region = must_ok!(list_dict_at(&regions, 0), "missing first region");

    assert_eq!(regions.len(), 1);
    assert_heading_region_payload(&first_region, expected_text);
    assert_canonical_ir_preserves_one_source_backed_heading(document, expected_text);
}

fn assert_heading_region_payload(region: &Bound<'_, PyDict>, expected_text: &str) {
    assert_eq!(
        must_ok!(region_kind_and_text(region), "expected region strings"),
        ("heading".to_owned(), expected_text.to_owned()),
    );
}

fn canonical_ir_regions(extracted_document: &Bound<'_, PyDict>) -> PyResult<Vec<Value>> {
    let parsed = parse_ir_json(&dict_string(extracted_document, "ir_json")?)?;
    parsed
        .get("regions")
        .and_then(Value::as_array)
        .cloned()
        .ok_or_else(|| PyKeyError::new_err("canonical IR regions array"))
}

fn assert_canonical_ir_preserves_one_source_backed_heading(
    extracted_document: &Bound<'_, PyDict>,
    expected_text: &str,
) {
    let regions = must_ok!(
        canonical_ir_regions(extracted_document),
        "expected canonical IR regions"
    );
    assert_eq!(regions.len(), 1);
    let region = must_some!(regions.first(), "expected first canonical region");
    assert_canonical_heading_region(region, expected_text);
    assert_single_source_backed_segment(region, expected_text);
}

fn assert_canonical_heading_region(region: &Value, expected_text: &str) {
    assert_eq!(
        region.get("kind"),
        Some(&Value::String("heading".to_owned()))
    );
    assert_eq!(
        region.get("text"),
        Some(&Value::String(expected_text.to_owned()))
    );
}

fn assert_single_source_backed_segment(region: &Value, expected_text: &str) {
    let segments = must_some!(
        region.get("segments").and_then(Value::as_array),
        "expected source-backed segment array"
    );
    assert_eq!(segments.len(), 1);
    let segment = must_some!(segments.first(), "expected first source-backed segment");
    assert_eq!(
        segment.get("text"),
        Some(&Value::String(expected_text.to_owned()))
    );
    assert!(
        segment.get("source").is_some_and(Value::is_object),
        "expected source-backed segment to include source span"
    );
    assert_eq!(segment.get("synthetic"), Some(&Value::Null));
}

fn assert_first_region_payload(
    py: Python<'_>,
    extracted_document: &Py<PyDict>,
    expected_text: &str,
) {
    let regions = must_ok!(
        dict_list(extracted_document.bind(py), "regions"),
        "missing regions payload"
    );
    assert_ne!(regions.len(), 0);
    let first_region = must_ok!(list_dict_at(&regions, 0), "missing first region");
    assert_heading_region_payload(&first_region, expected_text);
}

#[then("the extracted document preserves the shared Markdown fixture")]
fn extracted_document_preserves_the_shared_markdown_fixture(bridge_state: &BridgeState) {
    assert_expected_document_payload(bridge_state, assert_first_region_payload);
}

#[scenario(
    path = "tests/features/bridge_structure.feature",
    name = "Bridge delegates the smoke greeting to the core crate"
)]
fn bridge_delegates_the_smoke_greeting_to_the_core_crate(
    #[from(bridge_state)] _bridge_state: BridgeState,
) {
}

#[scenario(
    path = "tests/features/bridge_structure.feature",
    name = "Bridge greeting is not the legacy Python fallback"
)]
fn bridge_greeting_is_not_the_legacy_python_fallback(
    #[from(bridge_state)] _bridge_state: BridgeState,
) {
}

#[scenario(
    path = "tests/features/bridge_structure.feature",
    name = "Bridge extracts a Markdown document through the Rust boundary"
)]
fn bridge_extracts_a_markdown_document_through_the_rust_boundary(
    #[from(bridge_state)] _bridge_state: BridgeState,
) {
}

#[scenario(
    path = "tests/features/bridge_structure.feature",
    name = "Bridge extracts the shared Markdown fixture through the Rust boundary"
)]
fn bridge_extracts_the_shared_markdown_fixture_through_the_rust_boundary(
    #[from(bridge_state)] _bridge_state: BridgeState,
) {
}

#[scenario(
    path = "tests/features/bridge_structure.feature",
    name = "Bridge yields no regions for blank Markdown"
)]
fn bridge_yields_no_regions_for_blank_markdown(#[from(bridge_state)] _bridge_state: BridgeState) {}
