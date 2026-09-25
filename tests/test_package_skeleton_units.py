"""Unit tests for the mixed-package Python skeleton."""

import dataclasses as dc
import os
import pathlib
import subprocess  # ruff: ignore[suspicious-subprocess-import] - tests invoke a trusted local interpreter.
import sys

import pytest
import stilyagi
from pytest_bdd import scenarios
from stilyagi import config, diagnostics, engine, model, nlp, plugins, rules

from tests.support.assertions import assert_with_context

pytest_plugins = ("tests.steps.check_command", "tests.package_skeleton_support")
pytestmark = pytest.mark.usefixtures("reset_extraction_state")


scenarios("../features/stilyagi_check_command.feature")


def test_public_package_re_exports_the_supported_boundaries() -> None:
    """Re-export the supported package boundaries from the public package."""
    assert_with_context(
        stilyagi.__all__ == ["engine", "hello", "model"],
        "expected stilyagi.__all__ == ['engine', 'hello', 'mo...",
    )
    assert stilyagi.engine is engine, "expected stilyagi.engine is engine"
    assert stilyagi.model is model, "expected stilyagi.model is model"


@pytest.mark.parametrize(
    ("module", "expected"),
    [
        (
            engine,
            [
                "BridgeExtractionError",
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
    assert_with_context(
        plugins.RULE_ENTRY_POINT_GROUP == "stilyagi.rules",
        "expected plugins.RULE_ENTRY_POINT_GROUP == 'stilyagi...",
    )
    assert_with_context(
        plugins.CAPABILITY_ENTRY_POINT_GROUP == "stilyagi.capabilities",
        "expected plugins.CAPABILITY_ENTRY_POINT_GROUP == 'st...",
    )


def test_rules_package_re_exports_the_builtin_namespace() -> None:
    """Expose the built-in rule namespace from the rules package."""
    assert rules.__all__ == ["builtin"], "expected rules.__all__ == ['builtin']"
    assert_with_context(
        rules.builtin.__doc__ is not None,
        "expected rules.builtin.__doc__ is not None",
    )


def test_stilyagi_config_uses_the_default_cache_directory() -> None:
    """Apply the documented default cache directory."""
    assert_with_context(
        config.StilyagiConfig()
        == config.StilyagiConfig(
            cache_dir=pathlib.Path(".stilyagi_cache"),
            respect_gitignore=True,
            line_length=88,
            plugins=("builtin",),
            lint=config.LintConfig(),
            extract=config.MarkdownExtractConfig(),
            nlp=config.NlpConfig(),
            rules={},
            reserved={},
        ),
        "expected config.StilyagiConfig() == config.StilyagiC...",
    )


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

    assert_with_context(
        diagnostic == dc.replace(diagnostic),
        "expected diagnostic == dc.replace(diagnostic)",
    )


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
    assert_with_context(
        "stilyagi check:" in completed.stderr,
        "expected 'stilyagi check:' in completed.stderr",
    )
    assert_with_context(
        "toml" in completed.stderr.lower(),
        "expected 'toml' in completed.stderr.lower()",
    )
