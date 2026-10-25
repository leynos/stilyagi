//! Python docstring extraction contracts across the `PyO3` bridge.

use pyo3::prelude::Python;
use rstest::rstest;
use stilyagi_extract::ExtractSyntax;

use super::payload::{dict_list, dict_string, list_dict_at, parse_ir_json, region_kind_and_text};
use super::{BridgeExtractRequest, assert_ir_json_contract, bridge_extract_document};

#[rstest]
fn extract_document_py_exposes_python_docstrings() {
    let source = "\"\"\"Module docs.\"\"\"\n\ndef example():\n    \"\"\"Function docs.\"\"\"\n";
    let document = bridge_extract_document(&BridgeExtractRequest {
        source,
        syntax: "python_docstring",
        source_path: None,
    })
    .expect("Python docstring extraction should succeed");

    Python::attach(|py| {
        let document_dict = document.bind(py);
        let regions = dict_list(document_dict, "regions").expect("Python regions should be a list");

        assert_eq!(
            dict_string(document_dict, "syntax").expect("syntax payload should be a string"),
            ExtractSyntax::PythonDocstring.as_str(),
        );
        assert_eq!(regions.len(), 2);
        let module_doc = list_dict_at(&regions, 0).expect("module doc should be a dict");
        let function_doc = list_dict_at(&regions, 1).expect("function doc should be a dict");
        assert_eq!(
            region_kind_and_text(&module_doc).expect("module doc should expose region fields"),
            ("python_docstring".to_owned(), "Module docs.".to_owned()),
        );
        assert_eq!(
            region_kind_and_text(&function_doc).expect("function doc should expose region fields"),
            ("python_docstring".to_owned(), "Function docs.".to_owned()),
        );

        let ir_json = dict_string(document_dict, "ir_json").expect("IR payload should be a string");
        let parsed_ir = parse_ir_json(&ir_json).expect("expected parseable IR JSON");
        assert_ir_json_contract(&parsed_ir);
    });
}
