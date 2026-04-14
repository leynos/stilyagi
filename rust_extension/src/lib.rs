//! Python bindings for the Stilyagi Rust extension crate.

use pyo3::prelude::*;
use pyo3::types::PyModule;

/// Return a simple Rust-side greeting for smoke-testing the extension bridge.
#[pyfunction]
fn hello() -> &'static str {
    "hello from Rust"
}

/// Initialize the `_stilyagi_rs` Python module and register exported functions.
#[pymodule]
fn _stilyagi_rs(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(hello, m)?)?;
    Ok(())
}
