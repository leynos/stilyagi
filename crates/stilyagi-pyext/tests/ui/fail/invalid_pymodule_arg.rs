//! Compile-fail UI test: `#[pymodule]` rejects a non-Bound second argument.
//!
//! Validates that PyO3 macros reject a `#[pymodule]` function whose second
//! parameter is not `&Bound<'_, PyModule>` (here, a plain `i32`), catching
//! API drift in the module initialization signature.

use pyo3::prelude::*;

#[pymodule]
fn bad_module(_py: Python<'_>, _module: i32) -> PyResult<()> {
    Ok(())
}

fn main() {}
