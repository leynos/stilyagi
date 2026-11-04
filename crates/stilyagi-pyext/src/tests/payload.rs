//! Fallible lookups over the Python payloads that the bridge tests inspect.
//!
//! Every helper propagates failure as a `PyErr` so recognized test bodies can
//! attach context with `.expect(...)` and BDD `then` steps can panic at the
//! call site. Shared by the unit tests, the BDD steps, and the metrics
//! snapshot tests to keep payload navigation in one place.

use pyo3::{
    exceptions::{PyKeyError, PyRuntimeError},
    prelude::*,
    types::{PyDict, PyList, PyTuple},
};

/// Parse the canonical IR JSON string carried in an extracted payload.
pub(crate) fn parse_ir_json(ir_json: &str) -> PyResult<serde_json::Value> {
    serde_json::from_str(ir_json)
        .map_err(|error| PyRuntimeError::new_err(format!("IR JSON is not parseable: {error}")))
}

/// Fetch `key` from `dict`, treating an absent key as a `KeyError`.
pub(crate) fn dict_item<'py>(dict: &Bound<'py, PyDict>, key: &str) -> PyResult<Bound<'py, PyAny>> {
    dict.get_item(key)?
        .ok_or_else(|| PyKeyError::new_err(key.to_owned()))
}

/// Fetch `key` from `dict` as a string.
pub(crate) fn dict_string(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<String> {
    dict_item(dict, key)?.extract()
}

/// Fetch `key` from `dict` as a Python list.
pub(crate) fn dict_list<'py>(dict: &Bound<'py, PyDict>, key: &str) -> PyResult<Bound<'py, PyList>> {
    Ok(dict_item(dict, key)?.cast_into::<PyList>()?)
}

/// Fetch `key` from `dict` as a nested dictionary.
pub(crate) fn dict_dict<'py>(dict: &Bound<'py, PyDict>, key: &str) -> PyResult<Bound<'py, PyDict>> {
    Ok(dict_item(dict, key)?.cast_into::<PyDict>()?)
}

/// Fetch the dictionary stored at `index` in `list`.
pub(crate) fn list_dict_at<'py>(
    list: &Bound<'py, PyList>,
    index: usize,
) -> PyResult<Bound<'py, PyDict>> {
    Ok(list.get_item(index)?.cast_into::<PyDict>()?)
}

/// Read the `kind` and `text` fields of an extracted region payload.
pub(crate) fn region_kind_and_text(region: &Bound<'_, PyDict>) -> PyResult<(String, String)> {
    Ok((dict_string(region, "kind")?, dict_string(region, "text")?))
}

/// Collect a bridge-returned tuple of strings, propagating either failure.
pub(crate) fn tuple_strings(
    py: Python<'_>,
    tuple_result: PyResult<Py<PyTuple>>,
) -> PyResult<Vec<String>> {
    let tuple = tuple_result?;
    tuple
        .bind(py)
        .iter()
        .map(|item| item.extract::<String>())
        .collect()
}
