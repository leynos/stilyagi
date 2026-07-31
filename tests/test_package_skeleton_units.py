"""Unit tests for the mixed-package Python skeleton."""

import concurrent.futures
import dataclasses as dc
import json
import logging
import os
import pathlib
import subprocess  # noqa: S404 - tests invoke a trusted local interpreter.
import sys
import threading
import typing as typ

import pytest
import stilyagi
import stilyagi.engine.extraction as extraction_module
from pytest_bdd import scenarios
from stilyagi import config, diagnostics, engine, model, nlp, plugins, rules
from stilyagi.nlp import spacy_provider

type JSONType = dict[str, JSONType] | list[JSONType] | str | int | float | bool | None

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from syrupy.assertion import SnapshotAssertion


pytest_plugins = ("tests.steps.check_command",)


scenarios("../features/stilyagi_check_command.feature")


@pytest.fixture(autouse=True)
def reset_extraction_state() -> cabc.Iterator[None]:
    """Reset process-wide extraction adapter state around every test."""
    extraction_module._reset_extraction_state_for_tests()
    yield
    extraction_module._reset_extraction_state_for_tests()


def test_public_package_re_exports_the_supported_boundaries() -> None:
    """Re-export the supported package boundaries from the public package."""
    assert stilyagi.__all__ == ["engine", "hello", "model"], (
        "expected stilyagi.__all__ == ['engine', 'hello', 'mo..."
    )
    assert stilyagi.engine is engine, "expected stilyagi.engine is engine"
    assert stilyagi.model is model, "expected stilyagi.model is model"


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
                "supported_region_kinds",
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
    assert module.__all__ == expected, "expected module.__all__ == expected"


def test_plugin_entry_point_groups_match_the_documented_names() -> None:
    """Keep the plugin discovery constants stable."""
    assert plugins.RULE_ENTRY_POINT_GROUP == "stilyagi.rules", (
        "expected plugins.RULE_ENTRY_POINT_GROUP == 'stilyagi..."
    )
    assert plugins.CAPABILITY_ENTRY_POINT_GROUP == "stilyagi.capabilities", (
        "expected plugins.CAPABILITY_ENTRY_POINT_GROUP == 'st..."
    )


def test_rules_package_re_exports_the_builtin_namespace() -> None:
    """Expose the built-in rule namespace from the rules package."""
    assert rules.__all__ == ["builtin"], "expected rules.__all__ == ['builtin']"
    assert rules.builtin.__doc__ is not None, (
        "expected rules.builtin.__doc__ is not None"
    )


def test_stilyagi_config_uses_the_default_cache_directory() -> None:
    """Apply the documented default cache directory."""
    assert config.StilyagiConfig() == config.StilyagiConfig(
        cache_dir=pathlib.Path(".stilyagi_cache"),
        respect_gitignore=True,
        line_length=88,
        plugins=("builtin",),
        lint=config.LintConfig(),
        extract=config.MarkdownExtractConfig(),
        nlp=config.NlpConfig(),
        rules={},
        reserved={},
    ), "expected config.StilyagiConfig() == config.StilyagiC..."


def test_stilyagi_config_rejects_a_blank_cache_directory() -> None:
    """Reject an empty cache directory because it is not a usable boundary."""
    with pytest.raises(
        config.InvalidCacheDirError,
        match=r"^Invalid cache_dir: .*It must be a non-empty path\.$",
    ):
        config.StilyagiConfig(cache_dir=pathlib.Path("   "))


def test_diagnostic_preserves_code_and_message() -> None:
    """Store the diagnostic fields exactly as provided."""
    diagnostic = diagnostics.Diagnostic(
        path="docs/example.md",
        code="STY001",
        message="Example",
        severity=diagnostics.Severity.WARNING,
        line=3,
        column=5,
    )

    assert diagnostic == dc.replace(diagnostic), (
        "expected diagnostic == dc.replace(diagnostic)"
    )


def test_engine_skeleton_dataclasses_preserve_their_fields() -> None:
    """Keep the engine dataclasses predictable."""
    execution_plan = engine.ExecutionPlan(syntax="markdown")

    assert execution_plan.syntax == "markdown", (
        "expected execution_plan.syntax == 'markdown'"
    )
    assert engine.FixPlan(applicability="safe").applicability == "safe", (
        "expected engine.FixPlan(applicability='safe').applic..."
    )
    assert engine.RendererRegistry().default_format == "text", (
        "expected engine.RendererRegistry().default_format ==..."
    )
    assert engine.RendererRegistry().render([], "text") == "0 diagnostics found\n", (
        "expected engine.RendererRegistry().render([], 'text'..."
    )
    assert engine.EngineRunner(execution_plan=execution_plan).execution_plan is (
        execution_plan
    ), "expected engine.EngineRunner(execution_plan=executio..."


def test_engine_extract_document_returns_a_model_document() -> None:
    """Expose one typed extraction entrypoint from the engine package."""
    document = engine.extract_document("# Heading", model.Syntax.MARKDOWN)

    assert isinstance(document, model.Document), (
        "expected isinstance(document, model.Document)"
    )
    assert document.syntax is model.Syntax.MARKDOWN, (
        "expected document.syntax is model.Syntax.MARKDOWN"
    )
    assert document.ir is not None, "expected document.ir is not None"
    assert document.ir["schema_version"] == "1.1.0", (
        "expected document.ir['schema_version'] == '1.1.0'"
    )
    ir_document = typ.cast("dict[str, JSONType]", document.ir["document"])
    assert ir_document["path"] is None, "expected ir_document['path'] is None"
    assert ir_document["uri"] is None, "expected ir_document['uri'] is None"


def test_engine_extract_document_maps_regions_into_model_regions() -> None:
    """Adapt the bridge payload into the Python model surface."""
    document = engine.extract_document("# Heading", model.Syntax.MARKDOWN)

    assert document.regions == (model.Region(kind="heading", text="Heading"),), (
        "expected document.regions == (model.Region(kind='hea..."
    )


def test_engine_extract_document_drops_blank_markdown_region() -> None:
    """Emit no regions for whitespace-only Markdown at the public boundary."""
    document = engine.extract_document("   \n", model.Syntax.MARKDOWN)

    assert document.syntax is model.Syntax.MARKDOWN, (
        "expected document.syntax is model.Syntax.MARKDOWN"
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
    assert _normalize_ir_identity(document.ir) == _normalize_ir_identity(
        rust_snapshot
    ), "expected _normalize_ir_identity(document.ir) == _nor..."


def test_engine_extract_document_exposes_python_docstrings() -> None:
    """Expose supported Python docstring extraction through the typed adapter."""
    document = engine.extract_document(
        '"""Module docs."""\n\ndef example():\n    """Function docs."""\n',
        model.Syntax.PYTHON_DOCSTRING,
    )

    assert document.syntax is model.Syntax.PYTHON_DOCSTRING, (
        "expected document.syntax is model.Syntax.PYTHON_DOCS..."
    )
    assert [region.kind for region in document.regions] == [
        model.Syntax.PYTHON_DOCSTRING.value,
        model.Syntax.PYTHON_DOCSTRING.value,
    ], "expected [region.kind for region in document.regions..."
    assert [region.text for region in document.regions] == [
        "Module docs.",
        "Function docs.",
    ], "expected [region.text for region in document.regions..."
    assert document.ir is not None, "expected document.ir is not None"


def test_engine_bridge_syntax_spellings_match_the_python_enum() -> None:
    """Keep the Python enum and the Rust bridge syntax spellings aligned."""
    from stilyagi._stilyagi_rs import supported_syntaxes

    assert supported_syntaxes() == (
        model.Syntax.MARKDOWN.value,
        model.Syntax.PYTHON_DOCSTRING.value,
        model.Syntax.RUST_DOC_COMMENT.value,
    ), "expected supported_syntaxes() == (model.Syntax.MARKD..."


def test_engine_bridge_region_kind_spellings_match_the_rust_ir_vocab(
    snapshot: SnapshotAssertion,
) -> None:
    """Expose the canonical Rust IR region kind spellings to Python."""
    assert engine.supported_region_kinds() == snapshot, (
        "expected the bridge region vocabulary to match its r..."
    )


def test_extraction_state_reset_refreshes_region_kind_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refresh lazy region-kind caches when tests patch the Rust bridge."""
    with monkeypatch.context() as patch:
        patch.setattr(
            extraction_module,
            "bridge_supported_region_kinds",
            lambda: ("first_kind",),
        )
        extraction_module._reset_extraction_state_for_tests()
        assert extraction_module.supported_region_kinds() == ("first_kind",), (
            "expected extraction_module.supported_region_kinds() ..."
        )

        patch.setattr(
            extraction_module,
            "bridge_supported_region_kinds",
            lambda: ("second_kind",),
        )
        assert extraction_module.supported_region_kinds() == ("first_kind",), (
            "expected extraction_module.supported_region_kinds() ..."
        )

        extraction_module._reset_extraction_state_for_tests()
        assert extraction_module.supported_region_kinds() == ("second_kind",), (
            "expected extraction_module.supported_region_kinds() ..."
        )


def test_syntax_vocab_validation_is_resettable_for_bridge_tests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reset one-time syntax validation when tests patch bridge vocabularies."""
    supported = (
        model.Syntax.MARKDOWN.value,
        model.Syntax.PYTHON_DOCSTRING.value,
        model.Syntax.RUST_DOC_COMMENT.value,
    )

    with monkeypatch.context() as patch:
        patch.setattr(extraction_module, "bridge_supported_syntaxes", lambda: supported)
        extraction_module._reset_extraction_state_for_tests()
        extraction_module._validate_syntax_vocab_once()

        patch.setattr(
            extraction_module, "bridge_supported_syntaxes", lambda: ("drift",)
        )
        extraction_module._validate_syntax_vocab_once()

        extraction_module._reset_extraction_state_for_tests()
        with pytest.raises(
            RuntimeError, match="Python and Rust syntax spellings differ"
        ):
            extraction_module._validate_syntax_vocab_once()


def test_syntax_vocab_validation_is_shared_by_concurrent_callers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validate bridge syntax vocabulary once across concurrent callers."""
    call_count = 0
    call_count_lock = threading.Lock()
    supported = (
        model.Syntax.MARKDOWN.value,
        model.Syntax.PYTHON_DOCSTRING.value,
        model.Syntax.RUST_DOC_COMMENT.value,
    )

    def bridge_supported_syntaxes() -> tuple[str, ...]:
        """Return supported syntax spellings while counting bridge calls."""
        nonlocal call_count
        with call_count_lock:
            call_count += 1
        return supported

    monkeypatch.setattr(
        extraction_module, "bridge_supported_syntaxes", bridge_supported_syntaxes
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(extraction_module._validate_syntax_vocab_once)
            for _ in range(8)
        ]
        for future in futures:
            future.result()

    assert call_count == 1, "expected call_count == 1"


@pytest.mark.parametrize(
    ("extract_document", "expected_warning_args"),
    [
        pytest.param(
            engine.extract_document,
            ("stilyagi.engine.extract_document", 0, "future_kind"),
            id="public-engine-boundary",
        ),
        pytest.param(
            extraction_module.extract_document,
            None,
            id="read-only-extraction-adapter",
        ),
    ],
)
def test_extract_document_preserves_unknown_ir_region_kind(
    caplog: pytest.LogCaptureFixture,
    extract_document: cabc.Callable[[str, model.Syntax], model.Document],
    expected_warning_args: tuple[str, int, str] | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve unknown IR kinds and only warn at the public command boundary."""

    def bridge_payload(source: str, syntax: str) -> dict[str, object]:
        """Return a bridge payload with a future IR kind."""
        assert source == "Example", "expected source == 'Example'"
        assert syntax == model.Syntax.MARKDOWN.value, (
            "expected syntax == model.Syntax.MARKDOWN.value"
        )
        return {
            "syntax": syntax,
            "regions": [],
            "ir_json": json.dumps({
                "schema_version": "1.1.0",
                "regions": [{"kind": "future_kind", "text": "Example"}],
            }),
        }

    monkeypatch.setattr(extraction_module, "extract_document_bridge", bridge_payload)
    caplog.set_level(logging.WARNING, logger="stilyagi.engine.extraction")

    document = extract_document("Example", model.Syntax.MARKDOWN)

    assert document.ir is not None, "expected document.ir is not None"
    assert document.ir["regions"] == [{"kind": "future_kind", "text": "Example"}], (
        "expected document.ir['regions'] == [<'kind': 'future..."
    )
    records = [
        record
        for record in caplog.records
        if record.name == "stilyagi.engine.extraction"
    ]
    if expected_warning_args is None:
        assert records == [], "expected records == []"
    else:
        assert len(records) == 1, "expected len(records) == 1"
        assert records[0].message == (
            "Unknown IR region kind from Rust bridge during "
            "stilyagi.engine.extract_document: index=0 kind='future_kind'"
        ), 'expected records[0].message == "Unknown IR region ki...'
        assert records[0].args == expected_warning_args, (
            "expected records[0].args == expected_warning_args"
        )


def test_engine_extract_document_exposes_rust_doc_comments() -> None:
    """Expose supported Rust doc-comment extraction through the typed adapter."""
    document = engine.extract_document(
        "/// Rust doc comment\npub fn example() {}\n",
        model.Syntax.RUST_DOC_COMMENT,
    )

    assert document.syntax is model.Syntax.RUST_DOC_COMMENT, (
        "expected document.syntax is model.Syntax.RUST_DOC_CO..."
    )
    assert [region.kind for region in document.regions] == [
        model.Syntax.RUST_DOC_COMMENT.value,
    ], "expected [region.kind for region in document.regions..."
    assert [region.text for region in document.regions] == [
        " Rust doc comment",
    ], "expected [region.text for region in document.regions..."


def test_model_skeleton_dataclasses_preserve_defaults_and_children() -> None:
    """Keep the model placeholder dataclasses predictable."""
    region = model.Region(kind="paragraph", text="Hello")

    assert not model.Document(syntax=model.Syntax.MARKDOWN).regions, (
        "expected not model.Document(syntax=model.Syntax.MARK..."
    )
    assert model.Document(syntax=model.Syntax.MARKDOWN).ir is None, (
        "expected model.Document(syntax=model.Syntax.MARKDOWN..."
    )
    assert model.Document(
        syntax=model.Syntax.MARKDOWN,
        regions=(region,),
    ).regions == (region,), "expected model.Document(syntax=model.Syntax.MARKDOWN..."
    assert model.Sentence(text="Hello world").text == "Hello world", (
        "expected model.Sentence(text='Hello world').text == ..."
    )
    assert model.Token(text="Hello").text == "Hello", (
        "expected model.Token(text='Hello').text == 'Hello'"
    )


def test_spacy_provider_config_uses_the_default_model_name() -> None:
    """Apply the documented default spaCy model identifier."""
    assert nlp.SpacyProviderConfig().model == "en_core_web_sm", (
        "expected nlp.SpacyProviderConfig().model == 'en_core..."
    )


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
    assert isinstance(DummyProvider(), RuntimeCheckableNlpProvider), (
        "expected isinstance(DummyProvider(), RuntimeCheckabl..."
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


def test_python_module_entrypoint_reports_invalid_config(
    tmp_path: pathlib.Path,
) -> None:
    """Exercise the console entry point through `python -m stilyagi`."""
    (tmp_path / "stilyagi.toml").write_text("[lint\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("# Notes\n", encoding="utf-8")
    python_path = pathlib.Path(__file__).resolve().parents[1] / "python"
    env = dict(os.environ)
    env["PYTHONPATH"] = (
        f"{python_path}{os.pathsep}{env['PYTHONPATH']}"
        if env.get("PYTHONPATH")
        else str(python_path)
    )

    completed = subprocess.run(
        [sys.executable, "-m", "stilyagi"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 2, "expected completed.returncode == 2"
    assert "stilyagi check:" in completed.stderr, (
        "expected 'stilyagi check:' in completed.stderr"
    )
    assert "toml" in completed.stderr.lower(), (
        "expected 'toml' in completed.stderr.lower()"
    )
