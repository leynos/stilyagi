//! Python bindings for the Stilyagi Rust extension crate.

use pyo3::exceptions::{PyNotImplementedError, PyRuntimeError, PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyCFunction, PyDict, PyList, PyModule, PyTuple};
use stilyagi_core::smoke_hello;
use stilyagi_extract::{
    ExtractDocument, ExtractError, ExtractRegion, ExtractSyntax,
    extract_document as extract_document_from_rust,
};
use stilyagi_ir::{IrRegion, RegionKind as IrRegionKind};

/// Return a simple Rust-side greeting for smoke-testing the extension bridge.
#[pyfunction]
#[expect(
    clippy::missing_const_for_fn,
    reason = "#[pyfunction] requires a normal fn for runtime bindings"
)]
fn hello() -> &'static str {
    smoke_hello()
}

/// Return the stable syntax spellings exported by the Rust bridge.
#[pyfunction(name = "supported_syntaxes")]
fn supported_syntaxes_py(py: Python<'_>) -> PyResult<Py<PyTuple>> {
    let syntax_items = ExtractSyntax::ALL
        .into_iter()
        .map(ExtractSyntax::as_str)
        .collect::<Vec<_>>();

    Ok(PyTuple::new(py, syntax_items)?.unbind())
}

/// Return the stable IR region-kind spellings exported by the Rust bridge.
#[pyfunction(name = "supported_region_kinds")]
fn supported_region_kinds_py(py: Python<'_>) -> PyResult<Py<PyTuple>> {
    let region_kind_items = IrRegionKind::ALL
        .iter()
        .copied()
        .map(IrRegionKind::as_str)
        .collect::<Vec<_>>();

    Ok(PyTuple::new(py, region_kind_items)?.unbind())
}

/// Return the minimal extraction payload through the `PyO3` extension boundary.
fn extract_document_py(py: Python<'_>, args: &Bound<'_, PyTuple>) -> PyResult<Py<PyDict>> {
    let request = ExtractDocumentRequest::from_args(args)?;
    let extract_syntax = ExtractSyntax::try_from(request.syntax.as_str())
        .map_err(|error| map_extract_error(&error))?;
    let source = request.source;
    let document = py
        .detach(|| extract_document_from_rust(&source, extract_syntax))
        .map_err(|error| map_extract_error(&error))?;
    let document_dict = PyDict::new(py);
    let region_items = region_items_for_document(py, &document)?;
    let region_list = PyList::new(py, region_items)?;

    document_dict.set_item("syntax", document.syntax().as_str())?;
    document_dict.set_item("regions", region_list)?;
    if let Some(ir) = document.ir() {
        let ir_json = ir
            .to_canonical_json()
            .map_err(|error| PyRuntimeError::new_err(error.to_string()))?;
        document_dict.set_item("ir_json", ir_json)?;
    }
    Ok(document_dict.unbind())
}

fn region_items_for_document(
    py: Python<'_>,
    document: &ExtractDocument,
) -> PyResult<Vec<Py<PyDict>>> {
    if let Some(ir) = document.ir() {
        return canonical_region_items(py, &ir.regions);
    }
    extract_region_items(py, document.regions())
}

fn canonical_region_items(py: Python<'_>, regions: &[IrRegion]) -> PyResult<Vec<Py<PyDict>>> {
    regions
        .iter()
        .map(|region| region_item(py, &region.kind, &region.text))
        .collect::<PyResult<Vec<_>>>()
}

fn extract_region_items(py: Python<'_>, regions: &[ExtractRegion]) -> PyResult<Vec<Py<PyDict>>> {
    regions
        .iter()
        .map(|region| region_item(py, region.kind(), region.text()))
        .collect::<PyResult<Vec<_>>>()
}

fn region_item(py: Python<'_>, kind: &str, text: &str) -> PyResult<Py<PyDict>> {
    let region_dict = PyDict::new(py);
    region_dict.set_item("kind", kind)?;
    region_dict.set_item("text", text)?;
    Ok(region_dict.unbind())
}

fn extract_document_function(py: Python<'_>) -> PyResult<Bound<'_, PyCFunction>> {
    PyCFunction::new_closure(
        py,
        Some(c"extract_document"),
        Some(c"Extract a source document into Stilyagi's bridge payload."),
        |args, kwargs| {
            if kwargs.is_some_and(|keyword_args| !keyword_args.is_empty()) {
                return Err(PyTypeError::new_err(
                    "extract_document() got unexpected keyword arguments",
                ));
            }
            extract_document_py(args.py(), args)
        },
    )
}

struct ExtractDocumentRequest {
    source: String,
    syntax: String,
}

impl ExtractDocumentRequest {
    fn from_args(args: &Bound<'_, PyTuple>) -> PyResult<Self> {
        if args.len() != 2 {
            return Err(PyTypeError::new_err(format!(
                "extract_document() expected 2 arguments, got {}",
                args.len()
            )));
        }

        Ok(Self {
            source: args.get_item(0)?.extract()?,
            syntax: args.get_item(1)?.extract()?,
        })
    }
}

fn map_extract_error(error: &ExtractError) -> PyErr {
    match error {
        ExtractError::UnsupportedSyntax(_) => PyNotImplementedError::new_err(error.to_string()),
        ExtractError::UnknownSyntax(_) => PyValueError::new_err(error.to_string()),
        ExtractError::MarkdownIr(_) => PyRuntimeError::new_err(error.to_string()),
    }
}

/// Initialize the `_stilyagi_rs` Python module and register exported functions.
#[pymodule]
fn _stilyagi_rs(py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(extract_document_function(py)?)?;
    m.add_function(wrap_pyfunction!(hello, m)?)?;
    m.add_function(wrap_pyfunction!(supported_region_kinds_py, m)?)?;
    m.add_function(wrap_pyfunction!(supported_syntaxes_py, m)?)?;
    Ok(())
}

#[cfg(test)]
mod bridge_bdd;

#[cfg(test)]
mod tests;
