//! Compile-fail UI test: `#[pymodule]` rejects extra function arguments.
//!
//! Validates that PyO3 macros reject a `#[pymodule]` function with more than
//! two parameters, catching arity-check drift in the proc-macro expansion.

use pyo3::prelude::*;
use pyo3::types::PyModule;

#[pymodule]
fn bad_module(
    _py: Python<'_>,
    _module: &Bound<'_, PyModule>,
    _extra: i32,
) -> PyResult<()> {
    Ok(())
}

fn main() {}
