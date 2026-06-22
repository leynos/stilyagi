//! Compile-pass UI test: well-formed `#[pymodule]` definition.
//!
//! Validates that a `#[pymodule]` function returning `PyResult<()>` and
//! registering `#[pyfunction]` exports compiles without error under the
//! project's PyO3 version.

use pyo3::prelude::*;
use pyo3::types::{PyModule, PyTuple};

#[pyfunction(name = "supported_syntaxes")]
fn supported_syntaxes_py(py: Python<'_>) -> PyResult<Py<PyTuple>> {
    Ok(PyTuple::new(py, ["markdown", "python_docstring"])?.unbind())
}

#[pyfunction(name = "supported_region_kinds")]
fn supported_region_kinds_py(py: Python<'_>) -> PyResult<Py<PyTuple>> {
    Ok(PyTuple::new(py, ["heading", "paragraph"])?.unbind())
}

#[pyfunction]
fn hello() -> &'static str {
    "hello from Rust"
}

#[pymodule]
fn compile_pass_module(_py: Python<'_>, module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(hello, module)?)?;
    module.add_function(wrap_pyfunction!(supported_region_kinds_py, module)?)?;
    module.add_function(wrap_pyfunction!(supported_syntaxes_py, module)?)?;
    Ok(())
}

fn main() {}
