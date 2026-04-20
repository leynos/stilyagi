"""Unit tests for the mixed-package Python skeleton."""

from __future__ import annotations

import dataclasses as dc
import pathlib
import typing as typ

import pytest
import stilyagi
from stilyagi import cli, config, diagnostics, engine, model, nlp, plugins, rules
from stilyagi.nlp import spacy_provider


def test_public_package_re_exports_the_supported_boundaries() -> None:
    """Re-export the supported package boundaries from the public package."""
    assert stilyagi.__all__ == ["engine", "hello", "model"]
    assert stilyagi.engine is engine
    assert stilyagi.model is model


def test_engine_package_re_exports_the_engine_skeleton_types() -> None:
    """Re-export the engine boundary types from the engine package."""
    assert engine.__all__ == [
        "EngineRunner",
        "ExecutionPlan",
        "FixPlan",
        "RendererRegistry",
    ]


def test_model_package_re_exports_the_model_skeleton_types() -> None:
    """Re-export the model boundary types from the model package."""
    assert model.__all__ == ["Document", "Region", "Sentence", "Syntax", "Token"]


def test_nlp_package_re_exports_the_provider_contracts() -> None:
    """Re-export the NLP boundary types from the NLP package."""
    assert nlp.__all__ == ["NlpProvider", "SpacyProviderConfig"]


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
    with pytest.raises(config.InvalidCacheDirError):
        config.StilyagiConfig(cache_dir="   ")


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


def test_model_skeleton_dataclasses_preserve_defaults_and_children() -> None:
    """Keep the model placeholder dataclasses predictable."""
    region = model.Region(kind="paragraph", text="Hello")

    assert model.Document(syntax=model.Syntax.MARKDOWN).regions == ()
    assert model.Document(
        syntax=model.Syntax.MARKDOWN,
        regions=(region,),
    ).regions == (region,)
    assert model.Sentence(text="Hello world").text == "Hello world"
    assert model.Token(text="Hello").text == "Hello"


def test_spacy_provider_config_uses_the_default_model_name() -> None:
    """Apply the documented default spaCy model identifier."""
    assert nlp.SpacyProviderConfig().model == "en-core-web-sm"


def test_spacy_provider_config_rejects_a_blank_model_name() -> None:
    """Reject a blank spaCy model identifier because it is unusable."""
    with pytest.raises(spacy_provider.InvalidSpacyModelError):
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


def test_cli_main_reports_success_for_the_placeholder_path(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Return the documented non-zero status for the unimplemented CLI."""
    assert cli.main() == 2
    assert "CLI commands are not implemented yet." in capsys.readouterr().err
