"""Unit tests for the engine's typed document extraction adapter."""

import json
import pathlib
import typing as typ

import pytest
from stilyagi import engine, model

from tests.support.assertions import assert_with_context

type JSONType = dict[str, JSONType] | list[JSONType] | str | int | float | bool | None

if typ.TYPE_CHECKING:
    import collections.abc as cabc

pytest_plugins = ("tests.package_skeleton_support",)
pytestmark = pytest.mark.usefixtures("reset_extraction_state")


def test_engine_skeleton_dataclasses_preserve_their_fields() -> None:
    """Keep the engine dataclasses predictable."""
    execution_plan = engine.ExecutionPlan(syntax="markdown")

    assert_with_context(
        execution_plan.syntax == "markdown",
        "expected execution_plan.syntax == 'markdown'",
    )
    assert_with_context(
        engine.FixPlan(applicability="safe").applicability == "safe",
        "expected engine.FixPlan(applicability='safe').applic...",
    )
    assert_with_context(
        engine.RendererRegistry().default_format == "text",
        "expected engine.RendererRegistry().default_format ==...",
    )
    assert_with_context(
        engine.RendererRegistry().render([], "text") == "0 diagnostics found\n",
        "expected engine.RendererRegistry().render([], 'text'...",
    )
    assert_with_context(
        engine.EngineRunner(execution_plan=execution_plan).execution_plan
        is (execution_plan),
        "expected engine.EngineRunner(execution_plan=executio...",
    )


def test_engine_extract_document_returns_a_model_document() -> None:
    """Expose one typed extraction entrypoint from the engine package."""
    document = engine.extract_document("# Heading", model.Syntax.MARKDOWN)

    assert_with_context(
        isinstance(document, model.Document),
        "expected isinstance(document, model.Document)",
    )
    assert_with_context(
        document.syntax is model.Syntax.MARKDOWN,
        "expected document.syntax is model.Syntax.MARKDOWN",
    )
    assert document.ir is not None, "expected document.ir is not None"
    assert_with_context(
        document.ir["schema_version"] == "1.1.0",
        "expected document.ir['schema_version'] == '1.1.0'",
    )
    ir_document = typ.cast("dict[str, JSONType]", document.ir["document"])
    assert ir_document["path"] is None, "expected ir_document['path'] is None"
    assert ir_document["uri"] is None, "expected ir_document['uri'] is None"


def test_engine_extract_document_maps_regions_into_model_regions() -> None:
    """Adapt the bridge payload into the Python model surface."""
    document = engine.extract_document("# Heading", model.Syntax.MARKDOWN)

    assert_with_context(
        document.regions == (model.Region(kind="heading", text="Heading"),),
        "expected document.regions == (model.Region(kind='hea...",
    )


def test_engine_extract_document_drops_blank_markdown_region() -> None:
    """Emit no regions for whitespace-only Markdown at the public boundary."""
    document = engine.extract_document("   \n", model.Syntax.MARKDOWN)

    assert_with_context(
        document.syntax is model.Syntax.MARKDOWN,
        "expected document.syntax is model.Syntax.MARKDOWN",
    )
    assert document.regions == (), "expected document.regions == ()"
    assert document.ir is not None, "expected document.ir is not None"
    assert document.ir["regions"] == [], "expected document.ir['regions'] == []"


def test_engine_extract_document_ir_matches_reviewed_rust_snapshot() -> None:
    """Keep Python IR adaptation aligned with the Rust canonical snapshot."""
    fixture_path = pathlib.Path(
        "tests/fixtures/corpus/markdown/valid/heading-table-link-suppression.md",
    )
    source = fixture_path.read_text(encoding="utf-8")
    document = engine.extract_document(source, model.Syntax.MARKDOWN)
    rust_snapshot = _load_insta_json_snapshot(
        pathlib.Path(
            "crates/stilyagi-markdown/src/snapshots/"
            "stilyagi_markdown__tests__shared_markdown_ir_json_round_trips_without_span_drift.snap",
        ),
    )

    assert document.ir is not None, "expected document.ir is not None"
    assert_with_context(
        _normalize_ir_identity(document.ir) == _normalize_ir_identity(rust_snapshot),
        "expected _normalize_ir_identity(document.ir) == _nor...",
    )


def test_engine_extract_document_exposes_python_docstrings() -> None:
    """Expose supported Python docstring extraction through the typed adapter."""
    document = engine.extract_document(
        '"""Module docs."""\n\ndef example():\n    """Function docs."""\n',
        model.Syntax.PYTHON_DOCSTRING,
    )

    assert_with_context(
        document.syntax is model.Syntax.PYTHON_DOCSTRING,
        "expected document.syntax is model.Syntax.PYTHON_DOCS...",
    )
    assert_with_context(
        [region.kind for region in document.regions]
        == [
            model.Syntax.PYTHON_DOCSTRING.value,
            model.Syntax.PYTHON_DOCSTRING.value,
        ],
        "expected [region.kind for region in document.regions...",
    )
    assert_with_context(
        [region.text for region in document.regions]
        == [
            "Module docs.",
            "Function docs.",
        ],
        "expected [region.text for region in document.regions...",
    )
    assert document.ir is not None, "expected document.ir is not None"


def test_engine_extract_document_exposes_rust_doc_comments() -> None:
    """Expose supported Rust doc-comment extraction through the typed adapter."""
    document = engine.extract_document(
        "/// Rust doc comment\npub fn example() {}\n",
        model.Syntax.RUST_DOC_COMMENT,
    )

    assert_with_context(
        document.syntax is model.Syntax.RUST_DOC_COMMENT,
        "expected document.syntax is model.Syntax.RUST_DOC_CO...",
    )
    assert_with_context(
        [region.kind for region in document.regions]
        == [
            model.Syntax.RUST_DOC_COMMENT.value,
        ],
        "expected [region.kind for region in document.regions...",
    )
    assert_with_context(
        [region.text for region in document.regions]
        == [
            " Rust doc comment",
        ],
        "expected [region.text for region in document.regions...",
    )


def _load_insta_json_snapshot(path: pathlib.Path) -> dict[str, JSONType]:
    """Load the JSON payload stored after an insta snapshot metadata header."""
    _header, json_payload = path.read_text(encoding="utf-8").split(
        "\n---\n", maxsplit=1
    )
    parsed = json.loads(json_payload)
    assert isinstance(parsed, dict), "expected isinstance(parsed, dict)"
    return typ.cast("dict[str, JSONType]", parsed)


def _normalize_ir_identity(ir: cabc.Mapping[str, JSONType]) -> dict[str, JSONType]:
    """Remove adapter-specific source identity before parity comparison."""
    normalized = dict(ir)
    document = dict(typ.cast("dict[str, JSONType]", normalized["document"]))
    document["path"] = "<normalized>"
    document["uri"] = "<normalized>"
    normalized["document"] = document
    return normalized
