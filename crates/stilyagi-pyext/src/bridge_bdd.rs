//! BDD fixtures that exercise `extract_document_py` and `hello` through `PyO3`.

use std::path::Path;

use super::{extract_document_py, hello};
use pyo3::prelude::{Bound, Py, Python};
use pyo3::types::{PyAnyMethods, PyDict, PyList, PyTuple};
use rstest::fixture;
use rstest_bdd_macros::{given, scenario, then, when};
use serde_json::Value;
use stilyagi_test_support::{SHARED_MARKDOWN_FIXTURE_PATH, read_corpus_fixture};

macro_rules! must_ok {
    ($expression:expr, $($message:tt)+) => {
        match $expression {
            Ok(value) => value,
            Err(error) => panic!("{}: {error}", format_args!($($message)+)),
        }
    };
}

macro_rules! must_some {
    ($expression:expr, $($message:tt)+) => {
        match $expression {
            Some(value) => value,
            None => panic!("{}", format_args!($($message)+)),
        }
    };
}

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

fn read_shared_corpus_fixture(relative_path: impl AsRef<Path>) -> String {
    must_ok!(
        read_corpus_fixture(relative_path),
        "expected shared corpus fixture to be readable"
    )
}

fn perform_extraction(source: &str, syntax: &str, bridge_state: &mut BridgeState) {
    Python::attach(|py| {
        let args = must_ok!(
            PyTuple::new(py, [source, syntax]),
            "expected argument tuple"
        );
        let result = extract_document_py(py, &args);
        bridge_state.extracted_document = Some(match result {
            Ok(document) => document,
            Err(error) => panic!("unexpected extraction failure: {error}"),
        });
    });
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
fn bridge_can_call_the_rust_extraction_entrypoint(bridge_state: &mut BridgeState) {
    let _ = bridge_state;
}

#[when("the bridge extracts a Markdown document")]
fn bridge_extracts_a_markdown_document(bridge_state: &mut BridgeState) {
    perform_extraction("# Heading", "markdown", bridge_state);
    bridge_state.expected_document_text = Some("Heading".to_owned());
}

#[when("the bridge extracts the shared Markdown fixture")]
fn bridge_extracts_the_shared_markdown_fixture(bridge_state: &mut BridgeState) {
    let source = read_shared_corpus_fixture(SHARED_MARKDOWN_FIXTURE_PATH);

    perform_extraction(&source, "markdown", bridge_state);
    bridge_state.expected_document_text = Some("Fixture Heading".to_owned());
}

#[when("the bridge extracts a blank Markdown document")]
fn bridge_extracts_a_blank_markdown_document(bridge_state: &mut BridgeState) {
    perform_extraction("   \n", "markdown", bridge_state);
    bridge_state.expected_document_text = Some("   \n".to_owned());
}

#[then("the extracted document reports Markdown syntax")]
fn extracted_document_reports_markdown_syntax(bridge_state: &BridgeState) {
    let extracted_document = must_some!(
        bridge_state.extracted_document.as_ref(),
        "an extracted document should be present"
    );

    Python::attach(|py| {
        let extracted_document_bound = extracted_document.bind(py);
        let extracted_document_dict =
            must_ok!(extracted_document_bound.cast::<PyDict>(), "expected PyDict");

        assert_eq!(
            must_ok!(
                must_ok!(
                    extracted_document_dict.get_item("syntax"),
                    "missing syntax payload"
                )
                .extract::<&str>(),
                "expected syntax string"
            ),
            "markdown",
        );
    });
}

#[then("the extracted document preserves one source-backed region")]
fn extracted_document_preserves_one_source_backed_region(bridge_state: &BridgeState) {
    let extracted_document = must_some!(
        bridge_state.extracted_document.as_ref(),
        "an extracted document should be present"
    );

    Python::attach(|py| {
        assert_source_backed_region_payload(
            py,
            extracted_document,
            must_some!(
                bridge_state.expected_document_text.as_deref(),
                "expected_document_text must be provided for this BDD scenario"
            ),
        );
    });
}

#[then("the extracted document has no regions")]
fn extracted_document_has_no_regions(bridge_state: &BridgeState) {
    let extracted_document = must_some!(
        bridge_state.extracted_document.as_ref(),
        "an extracted document should be present"
    );

    Python::attach(|py| {
        let extracted_document_bound = extracted_document.bind(py);
        let extracted_document_dict =
            must_ok!(extracted_document_bound.cast::<PyDict>(), "expected PyDict");
        let regions_any = must_ok!(
            extracted_document_dict.get_item("regions"),
            "missing regions payload"
        );
        let regions = must_ok!(regions_any.cast::<PyList>(), "expected PyList");

        assert_eq!(must_ok!(regions.len(), "expected list length"), 0);
    });
}

fn assert_source_backed_region_payload(
    py: Python<'_>,
    extracted_document: &Py<PyDict>,
    expected_text: &str,
) {
    let extracted_document_bound = extracted_document.bind(py);
    let extracted_document_dict =
        must_ok!(extracted_document_bound.cast::<PyDict>(), "expected PyDict");
    let regions_any = must_ok!(
        extracted_document_dict.get_item("regions"),
        "missing regions payload"
    );
    let regions = must_ok!(regions_any.cast::<PyList>(), "expected PyList");
    let first_region_any = must_ok!(regions.get_item(0), "missing first region");
    let first_region = must_ok!(first_region_any.cast::<PyDict>(), "expected PyDict");

    assert_has_regions(regions);
    assert_region_field(first_region, "kind", "heading");
    assert_region_field(first_region, "text", expected_text);
    assert_canonical_ir_preserves_one_source_backed_heading(extracted_document_dict, expected_text);
}

fn assert_has_regions(regions: &Bound<'_, PyList>) {
    assert_eq!(must_ok!(regions.len(), "expected list length"), 1);
}

fn assert_region_field(region: &Bound<'_, PyDict>, key: &str, expected: &str) {
    let item = must_ok!(region.get_item(key), "missing region payload");
    let value = must_ok!(item.extract::<&str>(), "expected region string");
    assert_eq!(value, expected);
}

fn canonical_ir_regions(extracted_document: &Bound<'_, PyDict>) -> Vec<Value> {
    let ir_json_any = must_ok!(
        extracted_document.get_item("ir_json"),
        "missing canonical IR payload"
    );
    let ir_json = must_ok!(ir_json_any.extract::<&str>(), "expected IR JSON string");
    let parsed = must_ok!(
        serde_json::from_str::<Value>(ir_json),
        "expected parseable IR JSON"
    );
    let regions = must_some!(
        parsed.get("regions").and_then(Value::as_array),
        "expected canonical IR regions array"
    );
    regions.clone()
}

fn assert_canonical_ir_preserves_one_source_backed_heading(
    extracted_document: &Bound<'_, PyDict>,
    expected_text: &str,
) {
    let regions = canonical_ir_regions(extracted_document);
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
    let extracted_document_bound = extracted_document.bind(py);
    let extracted_document_dict =
        must_ok!(extracted_document_bound.cast::<PyDict>(), "expected PyDict");
    let regions_any = must_ok!(
        extracted_document_dict.get_item("regions"),
        "missing regions payload"
    );
    let regions = must_ok!(regions_any.cast::<PyList>(), "expected PyList");
    assert_ne!(must_ok!(regions.len(), "expected list length"), 0);
    let first_region_any = must_ok!(regions.get_item(0), "missing first region");
    let first_region = must_ok!(first_region_any.cast::<PyDict>(), "expected PyDict");
    assert_region_field(first_region, "kind", "heading");
    assert_region_field(first_region, "text", expected_text);
}

#[then("the extracted document preserves the shared Markdown fixture")]
fn extracted_document_preserves_the_shared_markdown_fixture(bridge_state: &BridgeState) {
    let extracted_document = must_some!(
        bridge_state.extracted_document.as_ref(),
        "an extracted document should be present"
    );

    Python::attach(|py| {
        assert_first_region_payload(
            py,
            extracted_document,
            must_some!(
                bridge_state.expected_document_text.as_deref(),
                "expected_document_text must be provided for this BDD scenario"
            ),
        );
    });
}

#[scenario(
    path = "tests/features/bridge_structure.feature",
    name = "Bridge delegates the smoke greeting to the core crate"
)]
fn bridge_delegates_the_smoke_greeting_to_the_core_crate(bridge_state: BridgeState) {
    let _ = bridge_state;
}

#[scenario(
    path = "tests/features/bridge_structure.feature",
    name = "Bridge greeting is not the legacy Python fallback"
)]
fn bridge_greeting_is_not_the_legacy_python_fallback(bridge_state: BridgeState) {
    let _ = bridge_state;
}

#[scenario(
    path = "tests/features/bridge_structure.feature",
    name = "Bridge extracts a Markdown document through the Rust boundary"
)]
fn bridge_extracts_a_markdown_document_through_the_rust_boundary(bridge_state: BridgeState) {
    let _ = bridge_state;
}

#[scenario(
    path = "tests/features/bridge_structure.feature",
    name = "Bridge extracts the shared Markdown fixture through the Rust boundary"
)]
fn bridge_extracts_the_shared_markdown_fixture_through_the_rust_boundary(
    bridge_state: BridgeState,
) {
    let _ = bridge_state;
}

#[scenario(
    path = "tests/features/bridge_structure.feature",
    name = "Bridge yields no regions for blank Markdown"
)]
fn bridge_yields_no_regions_for_blank_markdown(bridge_state: BridgeState) {
    let _ = bridge_state;
}
