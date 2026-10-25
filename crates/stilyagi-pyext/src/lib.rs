//! Python bindings for the Stilyagi Rust extension crate.

mod check_metrics;

use pyo3::exceptions::{PyNotImplementedError, PyRuntimeError, PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyCFunction, PyDict, PyList, PyModule, PyTuple};
use stilyagi_core::smoke_hello;
use stilyagi_extract::{
    ExtractDocument, ExtractError, ExtractRegion, ExtractSyntax, SourceIdentity,
    extract_document_with_source_identity as extract_document_with_identity_from_rust,
    hydrate_ir_json as hydrate_ir_json_from_rust,
};
use stilyagi_ir::{AUTHORED_DIRECTIVE_ERROR_CODES, IrRegion, RegionKind as IrRegionKind};

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

/// Return authored-directive error codes exported by the Rust bridge.
#[pyfunction(name = "authored_directive_error_codes")]
fn authored_directive_error_codes_py(py: Python<'_>) -> PyResult<Py<PyTuple>> {
    Ok(PyTuple::new(py, AUTHORED_DIRECTIVE_ERROR_CODES)?.unbind())
}

/// Return the minimal extraction payload through the `PyO3` extension boundary.
fn extract_document_py(py: Python<'_>, args: &Bound<'_, PyTuple>) -> PyResult<Py<PyDict>> {
    let request = ExtractDocumentRequest::from_args(args)?;
    let extract_syntax = ExtractSyntax::try_from(request.syntax.as_str())
        .map_err(|error| map_extract_error(&error))?;
    let source = request.source;
    let source_identity = request
        .source_path
        .map_or_else(SourceIdentity::anonymous, |path| {
            SourceIdentity::new(Some(path), None)
        });
    check_metrics::record_extraction_attempt(extract_syntax);
    let document = match py.detach(|| {
        extract_document_with_identity_from_rust(&source, extract_syntax, source_identity)
    }) {
        Ok(document) => {
            let recovery_errors = document
                .ir()
                .map_or(0, |ir| check_metrics::recovery_error_count(&ir.errors));
            check_metrics::record_extraction_outcome(extract_syntax, recovery_errors);
            document
        }
        Err(error) => {
            check_metrics::record_extraction_failure(&error);
            return Err(map_extract_error(&error));
        }
    };
    document_payload(py, &document)
}

/// Restore a canonical IR document through the shared Rust model.
fn hydrate_ir_json_py(py: Python<'_>, canonical_json: &str) -> PyResult<Py<PyDict>> {
    let owned_json = canonical_json.to_owned();
    let document = py
        .detach(move || hydrate_ir_json_from_rust(&owned_json))
        .map_err(|error| PyValueError::new_err(error.to_string()))?;
    document_payload(py, &document)
}

/// Isolate callable construction for the positional-only IR hydration API.
fn hydrate_ir_json_function(py: Python<'_>) -> PyResult<Bound<'_, PyCFunction>> {
    PyCFunction::new_closure(
        py,
        Some(c"hydrate_ir_json"),
        Some(c"Restore a canonical IR document through Rust's schema."),
        |args, kwargs| {
            if kwargs.is_some_and(|keyword_args| !keyword_args.is_empty()) {
                return Err(PyTypeError::new_err(
                    "hydrate_ir_json() got unexpected keyword arguments",
                ));
            }
            if args.len() != 1 {
                return Err(PyTypeError::new_err(format!(
                    "hydrate_ir_json() expected 1 argument, got {}",
                    args.len()
                )));
            }
            let canonical_json = args.get_item(0)?.extract::<String>()?;
            hydrate_ir_json_py(args.py(), &canonical_json)
        },
    )
}

/// Convert an extraction or hydrated Rust document to the shared Python shape.
fn document_payload(py: Python<'_>, document: &ExtractDocument) -> PyResult<Py<PyDict>> {
    let document_dict = PyDict::new(py);
    let region_items = region_items_for_document(py, document)?;
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

/// Prefer canonical IR structure, retaining bridge regions for incomplete IR paths.
fn region_items_for_document(
    py: Python<'_>,
    document: &ExtractDocument,
) -> PyResult<Vec<Py<PyDict>>> {
    if let Some(ir) = document.ir() {
        return canonical_region_items(py, &ir.regions);
    }
    extract_region_items(py, document.regions())
}

/// Preserve canonical-region spelling and structure across the Python boundary.
fn canonical_region_items(py: Python<'_>, regions: &[IrRegion]) -> PyResult<Vec<Py<PyDict>>> {
    regions
        .iter()
        .map(|region| region_item(py, &region.kind, &region.text))
        .collect::<PyResult<Vec<_>>>()
}

/// Retain bridge extraction output when the syntax cannot construct canonical IR.
fn extract_region_items(py: Python<'_>, regions: &[ExtractRegion]) -> PyResult<Vec<Py<PyDict>>> {
    regions
        .iter()
        .map(|region| region_item(py, region.kind(), region.text()))
        .collect::<PyResult<Vec<_>>>()
}

/// Keep canonical and bridge regions interchangeable in the Python payload.
fn region_item(py: Python<'_>, kind: &str, text: &str) -> PyResult<Py<PyDict>> {
    let region_dict = PyDict::new(py);
    region_dict.set_item("kind", kind)?;
    region_dict.set_item("text", text)?;
    Ok(region_dict.unbind())
}

/// Isolate callable construction so module registration remains a thin boundary.
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
    source_path: Option<String>,
}

impl ExtractDocumentRequest {
    /// Validate the narrow positional boundary before invoking Rust extraction.
    fn from_args(args: &Bound<'_, PyTuple>) -> PyResult<Self> {
        if !(2..=3).contains(&args.len()) {
            return Err(PyTypeError::new_err(format!(
                "extract_document() expected 2 or 3 arguments, got {}",
                args.len()
            )));
        }

        Ok(Self {
            source: args.get_item(0)?.extract()?,
            syntax: args.get_item(1)?.extract()?,
            source_path: if args.len() == 3 {
                args.get_item(2)?.extract::<Option<String>>()?
            } else {
                None
            },
        })
    }
}

/// Distinguish unsupported, invalid, and failed extraction for Python callers.
///
/// Known unsupported syntaxes are `NotImplementedError`, unknown inputs are
/// `ValueError`, and parser or IR failures are `RuntimeError`.
fn map_extract_error(error: &ExtractError) -> PyErr {
    match error {
        ExtractError::UnsupportedSyntax(_) => PyNotImplementedError::new_err(error.to_string()),
        ExtractError::UnknownSyntax(_) => PyValueError::new_err(error.to_string()),
        ExtractError::MarkdownIr(_) | ExtractError::PythonIr(_) | ExtractError::RustIr(_) => {
            PyRuntimeError::new_err(error.to_string())
        }
    }
}

/// Initialize the `_stilyagi_rs` Python module and register exported functions.
#[pymodule]
fn _stilyagi_rs(py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(check_metrics::reset_check_metrics, m)?)?;
    m.add_function(wrap_pyfunction!(check_metrics::record_check_run, m)?)?;
    m.add_function(wrap_pyfunction!(check_metrics::record_checked_file, m)?)?;
    m.add_function(wrap_pyfunction!(
        check_metrics::record_diagnostic_severity,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        check_metrics::record_skipped_candidates,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(check_metrics::record_unreadable_file, m)?)?;
    m.add_function(wrap_pyfunction!(
        check_metrics::record_operational_failure,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(check_metrics::record_phase_duration, m)?)?;
    m.add_function(wrap_pyfunction!(check_metrics::check_metrics_snapshot, m)?)?;
    m.add_function(extract_document_function(py)?)?;
    m.add_function(hydrate_ir_json_function(py)?)?;
    m.add_function(wrap_pyfunction!(hello, m)?)?;
    m.add_function(wrap_pyfunction!(authored_directive_error_codes_py, m)?)?;
    m.add_function(wrap_pyfunction!(supported_region_kinds_py, m)?)?;
    m.add_function(wrap_pyfunction!(supported_syntaxes_py, m)?)?;
    Ok(())
}

#[cfg(test)]
mod bridge_bdd;

#[cfg(test)]
mod bridge_identity_bdd;

#[cfg(test)]
mod tests;
