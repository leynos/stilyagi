//! Compile-pass UI test: Rust work can run outside the Python attachment.
//!
//! Validates the `py.detach(...)` pattern used by the Stilyagi extraction
//! bridge before converting the result back into Python-owned objects.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyModule};

fn extract_document_from_rust(source: &str) -> usize {
    source.len()
}

#[pyfunction(name = "extract_document")]
fn extract_document_py(py: Python<'_>, source: &str) -> PyResult<Py<PyDict>> {
    let length = py.detach(|| extract_document_from_rust(source));
    let document_dict = PyDict::new(py);
    document_dict.set_item("length", length)?;
    Ok(document_dict.unbind())
}

#[pymodule]
fn compile_pass_detach(_py: Python<'_>, module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(extract_document_py, module)?)?;
    Ok(())
}

fn main() {}
