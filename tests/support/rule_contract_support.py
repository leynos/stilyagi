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
    from stilyagi.rules.description import RuleExample

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


def lint(
    config_value: StilyagiConfig,
    source: str,
    syntax: model.Syntax = model.Syntax.MARKDOWN,
) -> list[Diagnostic]:
    """Lint one source through the production rule boundary.

    The catalogue now spans Markdown and documentation rules, so the syntax is
    a parameter: a documentation example must be extracted as Python or Rust,
    exactly as a real run on such a file would be.

    Parameters
    ----------
    config_value:
        The effective configuration to run under.
    source:
        The example source text.
    syntax:
        The source syntax to extract the example as.

    Returns
    -------
    list[Diagnostic]
        The diagnostics that survived selection and suppression.
    """
    suffix = {model.Syntax.MARKDOWN: ".md", model.Syntax.PYTHON_DOCSTRING: ".py"}.get(
        syntax, ".md"
    )
    return run_rules(
        RuleRunRequest(
            config=config_value,
            config_path=None,
            source_bytes=source.encode("utf-8"),
            reported_path=f"example{suffix}",
            document=engine.extract_document(source, syntax),
        )
    )


def config_selecting(code: str) -> StilyagiConfig:
    """Return a configuration that selects exactly one builtin rule.

    A documentation rule is also opted in, because selecting a `DOC` code does
    not make it report. An option that needs a value the example does not
    supply is left at its documented default.

    Returns
    -------
    StilyagiConfig
        A configuration selecting, and if needed opting in, that one rule.
    """
    rules: dict[str, dict[str, object]] = {"TERM001": {"terms": ["obviously"]}}
    if code.startswith("DOC"):
        rules[code] = {"enabled": True}
    return config.StilyagiConfig(
        lint=config.LintConfig(select=(code,)),
        rules=rules,
    )


def first_reporting_example(rule: RuleMetadata) -> RuleExample:
    """Return the first documented example that reports the rule.

    Returns
    -------
    RuleExample
        The example the rule documents for its own finding.

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
    return example


def example_syntax(rule: RuleMetadata) -> model.Syntax:
    """Return the syntax a rule's examples must be extracted as.

    Returns
    -------
    model.Syntax
        The syntax the rule's target declares for its example sources.

    Raises
    ------
    ValueError
        The rule's target names no syntax this helper can extract.
    """
    syntaxes = rule.target.syntaxes
    if syntaxes == ("markdown",):
        return model.Syntax.MARKDOWN
    if "python" in syntaxes:
        return model.Syntax.PYTHON_DOCSTRING
    message = f"no documented example syntax for {rule.code}: {syntaxes}"
    raise ValueError(message)


__all__ = [
    "REPOSITORY_ROOT",
    "config_selecting",
    "example_syntax",
    "first_reporting_example",
    "lint",
    "resolved_config",
]
