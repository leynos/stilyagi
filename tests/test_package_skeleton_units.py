"""Unit tests for the mixed-package Python skeleton."""

import dataclasses as dc
import json
import pathlib
import typing as typ

import pytest
import stilyagi
from stilyagi import cli, config, diagnostics, engine, model, nlp, plugins, rules
from stilyagi.nlp import spacy_provider

type JSONType = dict[str, JSONType] | list[JSONType] | str | int | float | bool | None

if typ.TYPE_CHECKING:
    import collections.abc as cabc


def test_public_package_re_exports_the_supported_boundaries() -> None:
    """Re-export the supported package boundaries from the public package."""
    assert stilyagi.__all__ == ["engine", "hello", "model"]
    assert stilyagi.engine is engine
    assert stilyagi.model is model


@pytest.mark.parametrize(
    ("module", "expected"),
    [
        (
            engine,
            [
                "EngineRunner",
                "ExecutionPlan",
                "FixPlan",
                "RendererRegistry",
                "extract_document",
            ],
        ),
        (model, ["Document", "Region", "Sentence", "Syntax", "Token"]),
        (nlp, ["NlpProvider", "SpacyProviderConfig"]),
    ],
)
def test_package_boundaries_re_export_their_documented_types(
    module: object,
    expected: list[str],
) -> None:
    """Re-export the documented boundary types from each package surface."""
    assert module.__all__ == expected


def test_plugin_entry_point_groups_match_the_documented_names() -> None:
    """Keep the plugin discovery constants stable."""
    assert plugins.RULE_ENTRY_POINT_GROUP == "stilyagi.rules"
    assert plugins.CAPABILITY_ENTRY_POINT_GROUP == "stilyagi.capabilities"


def test_rules_package_re_exports_the_builtin_namespace() -> None:
    """Expose the built-in rule namespace from the rules package."""
    assert rules.__all__ == ["builtin"]
    assert rules.builtin.__doc__ is not None


def test_stilyagi_config_uses_the_default_cache_directory() -> None:
    """Apply the documented default cache directory."""
    assert config.StilyagiConfig() == config.StilyagiConfig(
        cache_dir=pathlib.Path(".stilyagi_cache")
    )


def test_stilyagi_config_rejects_a_blank_cache_directory() -> None:
    """Reject an empty cache directory because it is not a usable boundary."""
    with pytest.raises(
        config.InvalidCacheDirError,
        match=r"^Invalid cache_dir: .*It must be a non-empty path\.$",
    ):
        config.StilyagiConfig(cache_dir=pathlib.Path("   "))


def test_diagnostic_preserves_code_and_message() -> None:
    """Store the placeholder diagnostic fields exactly as provided."""
    span = diagnostics.NodeRef(kind="paragraph", text="Example")

    assert diagnostics.Diagnostic(
        code="STY001",
        message="Example",
        span=span,
    ) == dc.replace(
        diagnostics.Diagnostic(
            code="STY001",
            message="Example",
            span=span,
        )
    )


def test_engine_skeleton_dataclasses_preserve_their_fields() -> None:
    """Keep the engine placeholder dataclasses predictable."""
    execution_plan = engine.ExecutionPlan(syntax="markdown")

    assert execution_plan.syntax == "markdown"
    assert engine.FixPlan(applicability="safe").applicability == "safe"
    assert engine.RendererRegistry().default_format == "text"
    assert engine.EngineRunner(execution_plan=execution_plan).execution_plan is (
        execution_plan
    )


def test_engine_extract_document_returns_a_model_document() -> None:
    """Expose one typed extraction entrypoint from the engine package."""
    document = engine.extract_document("# Heading", model.Syntax.MARKDOWN)

    assert isinstance(document, model.Document)
    assert document.syntax is model.Syntax.MARKDOWN
    assert document.ir is not None
    assert document.ir["schema_version"] == "1.0.0"
    ir_document = typ.cast("dict[str, JSONType]", document.ir["document"])
    assert ir_document["path"] is None
    assert ir_document["uri"] is None


def test_engine_extract_document_maps_regions_into_model_regions() -> None:
    """Adapt the bridge payload into the Python model surface."""
    document = engine.extract_document("# Heading", model.Syntax.MARKDOWN)

    assert document.regions == (model.Region(kind="document", text="# Heading"),)


def test_engine_extract_document_drops_blank_markdown_region() -> None:
    """Emit no regions for whitespace-only Markdown at the public boundary."""
    document = engine.extract_document("   \n", model.Syntax.MARKDOWN)

    assert document.syntax is model.Syntax.MARKDOWN
    assert document.regions == ()
    assert document.ir is not None
    assert document.ir["regions"] == []


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

    assert document.ir is not None
    assert _normalize_ir_identity(document.ir) == _normalize_ir_identity(rust_snapshot)


def test_engine_bridge_syntax_spellings_match_the_python_enum() -> None:
    """Keep the Python enum and the Rust bridge syntax spellings aligned."""
    from stilyagi._stilyagi_rs import supported_syntaxes

    assert supported_syntaxes() == (
        model.Syntax.MARKDOWN.value,
        model.Syntax.PYTHON_DOCSTRING.value,
        model.Syntax.RUST_DOC_COMMENT.value,
    )


@pytest.mark.parametrize(
    "syntax",
    [model.Syntax.PYTHON_DOCSTRING, model.Syntax.RUST_DOC_COMMENT],
)
def test_engine_extract_document_rejects_unsupported_syntaxes(
    syntax: model.Syntax,
) -> None:
    """Reject syntaxes that the first Rust bridge does not implement yet."""
    with pytest.raises(
        NotImplementedError,
        match=rf"^{syntax.value} extraction is not implemented yet\.$",
    ):
        engine.extract_document("Example", syntax)


def test_model_skeleton_dataclasses_preserve_defaults_and_children() -> None:
    """Keep the model placeholder dataclasses predictable."""
    region = model.Region(kind="paragraph", text="Hello")

    assert not model.Document(syntax=model.Syntax.MARKDOWN).regions
    assert model.Document(syntax=model.Syntax.MARKDOWN).ir is None
    assert model.Document(
        syntax=model.Syntax.MARKDOWN,
        regions=(region,),
    ).regions == (region,)
    assert model.Sentence(text="Hello world").text == "Hello world"
    assert model.Token(text="Hello").text == "Hello"


def test_spacy_provider_config_uses_the_default_model_name() -> None:
    """Apply the documented default spaCy model identifier."""
    assert nlp.SpacyProviderConfig().model == "en_core_web_sm"


def test_spacy_provider_config_rejects_a_blank_model_name() -> None:
    """Reject a blank spaCy model identifier because it is unusable."""
    with pytest.raises(
        spacy_provider.InvalidSpacyModelError,
        match=r"^Invalid spaCy model: .*It must not be blank\.$",
    ):
        nlp.SpacyProviderConfig(model="")


@typ.runtime_checkable
class RuntimeCheckableNlpProvider(nlp.NlpProvider, typ.Protocol):
    """Runtime-checkable adapter for asserting the provider protocol shape."""


class DummyProvider:
    """Minimal object that satisfies the NLP provider protocol."""

    @property
    def provider_name(self) -> str:
        """Return the provider identifier."""
        return "dummy"


def test_nlp_provider_protocol_accepts_matching_provider_objects() -> None:
    """Accept objects that satisfy the NLP provider protocol."""
    assert isinstance(DummyProvider(), RuntimeCheckableNlpProvider)


def _load_insta_json_snapshot(path: pathlib.Path) -> dict[str, JSONType]:
    """Load the JSON payload stored after an insta snapshot metadata header."""
    _header, json_payload = path.read_text(encoding="utf-8").split(
        "\n---\n", maxsplit=1
    )
    parsed = json.loads(json_payload)
    assert isinstance(parsed, dict)
    return typ.cast("dict[str, JSONType]", parsed)


def _normalize_ir_identity(ir: cabc.Mapping[str, JSONType]) -> dict[str, JSONType]:
    """Remove adapter-specific source identity before parity comparison."""
    normalized = dict(ir)
    document = dict(typ.cast("dict[str, JSONType]", normalized["document"]))
    document["path"] = "<normalized>"
    document["uri"] = "<normalized>"
    normalized["document"] = document
    return normalized


def test_cli_main_reports_placeholder_exit_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Return the documented placeholder exit code for the unimplemented CLI."""
    assert cli.main() == 2
    assert "CLI commands are not implemented yet." in capsys.readouterr().err
