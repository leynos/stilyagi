//! Tests for the Python extension bridge payload and error mapping.
//!
//! The payload assertions snapshot a canonical, stable rendering of each
//! `PyDict` rather than `Bound`'s `repr()`, which can change with the
//! interpreter and with any object whose repr embeds an address. Projections
//! omit the canonical IR JSON where a structural assertion already covers it;
//! see the snapshot workflow in the developers' guide.

mod errors;
pub(crate) mod payload;
mod rust_doc_comment;
mod vocabulary;

use payload::{dict_list, dict_string, list_dict_at, parse_ir_json, region_kind_and_text};
use pyo3::{
    exceptions::PyTypeError,
    prelude::{Bound, Py, PyResult, Python},
    types::{
        PyAny,
        PyAnyMethods,
        PyBool,
        PyBoolMethods,
        PyDict,
        PyDictMethods,
        PyInt,
        PyList,
        PyListMethods,
        PyTuple,
        PyTypeMethods,
    },
};
use rstest::rstest;
use serde_json::json;
use stilyagi_extract::{
    ExtractError,
    ExtractSyntax,
    MarkdownIrFailure,
    PythonExtractError,
    RustExtractError,
};

use super::{
    authored_directive_error_codes_py,
    extract_document_function,
    extract_document_py,
    hello,
    map_extract_error,
    supported_region_kinds_py,
    supported_syntaxes_py,
};
use crate::check_metrics::with_metrics_test_lock;

/// Renders one payload value with its primitive type preserved.
///
/// Strings, booleans, and integers map to the matching JSON types, and a list
/// of region dicts becomes a JSON array. Order matters: Python's `bool` is a
/// subclass of `int`, so the boolean check must come before the exact-integer
/// one. An unsupported type panics rather than being stringified, so a bridge
/// field that changes from the integer `1` to a list (or any other unsupported
/// type) fails here instead of passing a snapshot that renders both alike.
fn rendered_value(value: &Bound<'_, PyAny>) -> serde_json::Value {
    if let Ok(text) = value.extract::<String>() {
        return serde_json::Value::String(text);
    }
    if let Ok(flag) = value.cast::<PyBool>() {
        return serde_json::Value::Bool(flag.is_true());
    }
    if value.is_exact_instance_of::<PyInt>() {
        let number = value
            .extract::<i64>()
            .expect("expected payload integers to fit in i64");
        return serde_json::Value::from(number);
    }
    if let Ok(list) = value.cast::<PyList>() {
        return list_json(list);
    }

    let rendered_type = value
        .get_type()
        .name()
        .map_or_else(|_| "<unavailable>".to_owned(), |name| name.to_string());
    panic!("payload value type is not supported by the projection: {rendered_type}");
}

/// Renders one `PyDict` as a stable JSON object.
///
/// Members keep their primitive JSON type through [`rendered_value`]: strings
/// stay strings, booleans and integers stay booleans and integers, and lists
/// of region dicts become arrays of objects. An unsupported value type panics,
/// so the projection cannot quietly flatten a type change into a string.
fn dictionary_json(dictionary: &Bound<'_, PyDict>) -> serde_json::Value {
    let mut rendered = serde_json::Map::new();
    for (key, value) in dictionary.iter() {
        let rendered_key = key
            .extract::<String>()
            .expect("expected payload keys to be strings");
        rendered.insert(rendered_key, rendered_value(&value));
    }
    serde_json::Value::Object(rendered)
}

/// Renders a list of region dictionaries as a JSON array.
fn list_json(list: &Bound<'_, PyList>) -> serde_json::Value {
    let items = list
        .iter()
        .map(|item| {
            let region = item
                .cast::<PyDict>()
                .expect("expected list items to be region dicts");
            dictionary_json(region)
        })
        .collect::<Vec<_>>();
    serde_json::Value::Array(items)
}

/// Returns the bridge document payload as a stable, snapshot-friendly value.
///
/// The canonical IR JSON is dropped without being parsed: it records the full
/// document, so snapshotting it here would duplicate an existing golden-IR
/// snapshot and bury the bridge shape in hundreds of lines of IR. A caller
/// that needs the IR keeps a structural assertion beside the snapshot.
pub(super) fn document_payload(payload: &Bound<'_, PyDict>) -> serde_json::Value {
    let mut rendered = dictionary_json(payload);
    if let serde_json::Value::Object(ref mut map) = rendered {
        map.remove("ir_json");
    }
    rendered
}

/// Returns the whole bridge payload with its canonical IR JSON parsed.
///
/// Unlike [`document_payload`], this keeps `ir_json` and replaces the
/// transported string with structured JSON. A string serde cannot parse is a
/// bridge contract violation, so the projection panics with the parser's
/// error instead of snapshotting a silently different shape.
pub(super) fn document_payload_with_ir(payload: &Bound<'_, PyDict>) -> serde_json::Value {
    let mut rendered = dictionary_json(payload);
    let Some(map) = rendered.as_object_mut() else {
        return rendered;
    };
    let Some(serde_json::Value::String(ir_json)) = map.get("ir_json").cloned() else {
        return rendered;
    };
    let parsed = match serde_json::from_str::<serde_json::Value>(&ir_json) {
        Ok(parsed) => parsed,
        Err(error) => panic!("bridge ir_json is not valid JSON: {error}"),
    };
    map.insert("ir_json".to_owned(), parsed);
    rendered
}

/// Extracts a document through the `PyO3` entrypoint with Python attached.
fn bridge_extract_document(source: &str, syntax: &str) -> PyResult<Py<PyDict>> {
    with_metrics_test_lock(|| {
        Python::attach(|py| {
            let args = PyTuple::new(py, [source, syntax])?;
            extract_document_py(py, &args)
        })
    })
}

/// Name every violated clause of the canonical IR JSON envelope contract.
fn ir_contract_violations(parsed: &serde_json::Value) -> Vec<&'static str> {
    let has_schema_version = parsed.get("schema_version") == Some(&serde_json::json!("1.1.0"));
    let has_document_object = parsed
        .get("document")
        .is_some_and(serde_json::Value::is_object);
    let line_index_starts_at_zero = parsed
        .get("line_index")
        .and_then(serde_json::Value::as_array)
        .and_then(|line_index| line_index.first())
        == Some(&serde_json::json!(0));
    let has_regions_array = parsed
        .get("regions")
        .is_some_and(serde_json::Value::is_array);

    [
        (has_schema_version, "schema_version must be 1.1.0"),
        (has_document_object, "document must be an object"),
        (line_index_starts_at_zero, "line_index must start at 0"),
        (has_regions_array, "regions must be an array"),
    ]
    .into_iter()
    .filter_map(|(is_satisfied, clause)| (!is_satisfied).then_some(clause))
    .collect()
}

/// Asserts the minimum envelope every canonical IR payload must carry.
///
/// This stays outside the snapshots so a missing or renamed key fails on its
/// own terms rather than being masked by a snapshot update.
#[track_caller]
fn assert_ir_json_contract(parsed: &serde_json::Value) {
    assert_eq!(
        ir_contract_violations(parsed),
        [] as [&str; 0],
        "IR JSON contract"
    );
}

/// The bridge greeting must be the same value the core crate exposes.
#[rstest]
fn hello_delegates_to_the_core_smoke_greeting() {
    assert_eq!(hello(), stilyagi_core::smoke_hello());
}

/// A stale Python implementation must not shadow the Rust greeting.
#[rstest]
#[case("hello from Python")]
fn hello_is_not_the_legacy_python_fallback(#[case] legacy_fallback: &str) {
    assert_ne!(hello(), legacy_fallback);
}

/// The exported function must reject keyword arguments it does not accept.
#[rstest]
fn extract_document_function_rejects_unexpected_kwargs() {
    Python::attach(|py| {
        let function =
            extract_document_function(py).expect("expected extract_document function construction");
        let args = PyTuple::new(py, ["# Heading", "markdown"]).expect("expected argument tuple");
        let kwargs = PyDict::new(py);
        kwargs
            .set_item("unexpected", true)
            .expect("expected kwargs setup to succeed");
        let error = function
            .call(args, Some(&kwargs))
            .expect_err("expected unexpected keyword argument to fail");

        assert!(error.is_instance_of::<PyTypeError>(py));
    });
}

/// A Markdown extraction must expose the documented bridge payload shape.
#[rstest]
fn extract_document_py_exposes_markdown_document() {
    with_metrics_test_lock(|| {
        Python::attach(|py| {
            let args =
                PyTuple::new(py, ["# Heading", "markdown"]).expect("expected argument tuple");
            let extracted =
                extract_document_py(py, &args).expect("Markdown extraction should succeed");
            let document = extracted.bind(py);
            let regions =
                dict_list(document, "regions").expect("Markdown regions should be a list");
            let first_region =
                list_dict_at(&regions, 0).expect("first Markdown region should be a dict");

            insta::assert_json_snapshot!(
                "extract_document_py__markdown_payload",
                document_payload(document)
            );

            assert_eq!(
                dict_string(document, "syntax").expect("syntax payload should be a string"),
                ExtractSyntax::Markdown.as_str(),
            );
            assert_eq!(regions.len(), 1);
            assert_eq!(
                region_kind_and_text(&first_region).expect("region should carry kind and text"),
                ("heading".to_owned(), "Heading".to_owned()),
            );
            let ir_json = dict_string(document, "ir_json").expect("IR payload should be a string");
            let parsed = parse_ir_json(&ir_json).expect("expected parseable IR JSON");
            assert_ir_json_contract(&parsed);
        });
    });
}

/// Python docstring extraction must preserve both the module and function
/// regions.
#[rstest]
fn extract_document_py_exposes_python_docstrings() {
    let source = "\"\"\"Module docs.\"\"\"\n\ndef example():\n    \"\"\"Function docs.\"\"\"\n";
    let document = bridge_extract_document(source, "python_docstring")
        .expect("Python docstring extraction should succeed");

    Python::attach(|py| {
        let document_dict = document.bind(py);
        let regions = dict_list(document_dict, "regions").expect("Python regions should be a list");
        let region_summaries = (0..regions.len())
            .map(|index| {
                let region = list_dict_at(&regions, index).expect("region should be a dict");
                region_kind_and_text(&region).expect("region should carry kind and text")
            })
            .collect::<Vec<_>>();

        insta::assert_json_snapshot!(
            "extract_document_py__python_docstring_payload",
            document_payload(document_dict)
        );

        assert_eq!(
            dict_string(document_dict, "syntax").expect("syntax payload should be a string"),
            ExtractSyntax::PythonDocstring.as_str(),
        );
        assert_eq!(
            region_summaries,
            [
                ("python_docstring".to_owned(), "Module docs.".to_owned()),
                ("python_docstring".to_owned(), "Function docs.".to_owned()),
            ],
        );

        let ir_json = dict_string(document_dict, "ir_json").expect("IR payload should be a string");
        let parsed = parse_ir_json(&ir_json).expect("expected parseable IR JSON");
        assert_ir_json_contract(&parsed);
    });
}

/// Keep rejection behaviour stable for both unsupported and unknown syntax
/// strings.
#[rstest]
#[case(
    "not_a_syntax",
    "extract_document_py__invalid_syntax_error",
    "not_a_syntax"
)]
fn extract_document_py_rejects_invalid_syntaxes(
    #[case] syntax: &str,
    #[case] snapshot_name: &str,
    #[case] expected_fragment: &str,
) {
    let err = bridge_extract_document("Example", syntax)
        .expect_err(&format!("expected an error for syntax {syntax:?}"));
    assert!(
        err.to_string().contains(expected_fragment),
        "error message {err:?} did not contain {expected_fragment:?}"
    );
    insta::assert_snapshot!(snapshot_name, format!("{err}"));
}

/// The projection must not flatten booleans and integers into strings.
#[rstest]
fn rendered_value_preserves_primitive_types() {
    Python::attach(|py| {
        let value = PyDict::new(py);
        value
            .set_item("flag", true)
            .expect("expected a boolean item");
        value
            .set_item("count", 7)
            .expect("expected an integer item");

        assert_eq!(dictionary_json(&value), json!({ "flag": true, "count": 7 }));
    });
}

/// A malformed IR string must fail the projection rather than snapshot the raw
/// string as a silently different shape.
#[rstest]
#[should_panic(expected = "bridge ir_json is not valid JSON")]
fn document_payload_with_ir_rejects_malformed_ir_json() {
    Python::attach(|py| {
        let payload = PyDict::new(py);
        payload
            .set_item("ir_json", "not json")
            .expect("expected IR payload setup");

        let _ = document_payload_with_ir(&payload);
    });
}
