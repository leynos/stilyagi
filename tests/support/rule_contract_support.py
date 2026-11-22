"""Shared execution helpers for the builtin catalogue contract tests.

The catalogue's claims are split across two test modules: one checks defaults,
options, and examples, and the other checks executable fix claims and cited
references. Both need the same real configuration parse and rule run, so those
helpers live here rather than being restated with small differences.
"""

import pathlib
import textwrap
import typing as typ

from stilyagi import config, engine, model
from stilyagi.rules.registry import RuleRunRequest, run_rules

if typ.TYPE_CHECKING:
    from stilyagi.config.schema import StilyagiConfig
    from stilyagi.diagnostics import Diagnostic
    from stilyagi.rules.base import RuleMetadata

#: Repository root, used to resolve documented repository-relative references.
REPOSITORY_ROOT: typ.Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]


def resolved_config(tmp_path: pathlib.Path, toml_text: str) -> StilyagiConfig:
    """Resolve one documented TOML document through the production pipeline.

    Every documented example is written in `pyproject.toml` spelling, with the
    `[tool.stilyagi]` prefix, because that is the file a user actually pastes
    it into.

    Returns
    -------
    StilyagiConfig
        The effective configuration the real resolver produced.
    """
    path = tmp_path / "pyproject.toml"
    path.write_text(textwrap.dedent(toml_text).strip() + "\n", encoding="utf-8")
    return config.ConfigResolver().resolve_config_for_path(
        path,
        cli_overrides=None,
        explicit_config=None,
        isolated=False,
    )


def lint(config_value: StilyagiConfig, source: str) -> list[Diagnostic]:
    """Lint one Markdown source through the production rule boundary.

    Returns
    -------
    list[Diagnostic]
        The diagnostics that survived selection and suppression.
    """
    return run_rules(
        RuleRunRequest(
            config=config_value,
            config_path=None,
            source_bytes=source.encode("utf-8"),
            reported_path="example.md",
            document=engine.extract_document(source, model.Syntax.MARKDOWN),
        )
    )


def config_selecting(code: str) -> StilyagiConfig:
    """Return a configuration that selects exactly one builtin rule."""
    return config.StilyagiConfig(
        lint=config.LintConfig(select=(code,)),
        rules={"TERM001": {"terms": ["obviously"]}},
    )


def first_example_source(rule: RuleMetadata) -> str:
    """Return the first documented example that reports the rule.

    Returns
    -------
    str
        The example source the rule documents for its own finding.

    Raises
    ------
    ValueError
        The rule documents no reporting example.
    """
    example = next(
        (
            item
            for item in rule.description.examples
            if rule.code in item.expected_codes
        ),
        None,
    )
    if example is None:
        message = f"{rule.code} documents no reporting example"
        raise ValueError(message)
    return example.source


__all__ = [
    "REPOSITORY_ROOT",
    "config_selecting",
    "first_example_source",
    "lint",
    "resolved_config",
]
