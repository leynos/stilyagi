"""Parse raw config tables into typed configuration objects."""

import collections.abc as cabc
import dataclasses as dc
import pathlib
import typing as typ

from .schema import (
    InvalidConfigError,
    LintConfig,
    MarkdownExtractConfig,
    NlpConfig,
    StilyagiConfig,
)
from .validate import (
    ensure_bool,
    ensure_extend_value,
    ensure_int,
    ensure_mapping,
    ensure_string,
    ensure_string_sequence,
)


def _parse_lint_config(
    table: cabc.Mapping[str, object],
    *,
    path: pathlib.Path,
) -> LintConfig:
    """Parse the `[lint]` table into a typed config object."""
    unknown_keys = set(table) - {
        "select",
        "ignore",
        "preview",
        "fixable",
        "unfixable",
        "per-file-ignores",
    }
    if unknown_keys:
        key = f"lint.{min(unknown_keys)}"
        raise InvalidConfigError(path, key, "is not supported")

    per_file_ignores_raw = table.get("per-file-ignores", {})
    per_file_ignores_mapping = ensure_mapping(
        per_file_ignores_raw,
        path=path,
        key="lint.per-file-ignores",
    )
    per_file_ignores = {
        file_name: ensure_string_sequence(
            rule_codes,
            path=path,
            key=f"lint.per-file-ignores.{file_name}",
        )
        for file_name, rule_codes in per_file_ignores_mapping.items()
    }

    return LintConfig(
        select=ensure_string_sequence(
            table.get("select", ("MD", "DOC", "PUN", "STY", "PYDOC")),
            path=path,
            key="lint.select",
        ),
        ignore=ensure_string_sequence(
            table.get("ignore", ()), path=path, key="lint.ignore"
        ),
        preview=ensure_bool(table.get("preview", False), path=path, key="lint.preview"),
        fixable=ensure_string_sequence(
            table.get("fixable", ("ALL",)), path=path, key="lint.fixable"
        ),
        unfixable=ensure_string_sequence(
            table.get("unfixable", ()), path=path, key="lint.unfixable"
        ),
        per_file_ignores=per_file_ignores,
        reserved={
            "fixable": table.get("fixable", ["ALL"]),
            "unfixable": table.get("unfixable", []),
            "per-file-ignores": per_file_ignores_raw,
        },
    )


def _parse_extract_config(
    table: cabc.Mapping[str, object],
    *,
    path: pathlib.Path,
) -> MarkdownExtractConfig:
    """Parse the `[extract.markdown]` table into a typed config object."""
    unknown_keys = set(table) - {"markdown"}
    if unknown_keys:
        key = f"extract.{min(unknown_keys)}"
        raise InvalidConfigError(path, key, "is not supported")

    markdown = table.get("markdown", {})
    markdown_table = ensure_mapping(markdown, path=path, key="extract.markdown")
    markdown_unknown = set(markdown_table) - {"gfm", "frontmatter", "mdx"}
    if markdown_unknown:
        key = f"extract.markdown.{min(markdown_unknown)}"
        raise InvalidConfigError(path, key, "is not supported")

    return MarkdownExtractConfig(
        gfm=ensure_bool(
            markdown_table.get("gfm", True), path=path, key="extract.markdown.gfm"
        ),
        frontmatter=ensure_bool(
            markdown_table.get("frontmatter", True),
            path=path,
            key="extract.markdown.frontmatter",
        ),
        mdx=ensure_bool(
            markdown_table.get("mdx", False), path=path, key="extract.markdown.mdx"
        ),
    )


def _parse_nlp_config(
    table: cabc.Mapping[str, object],
    *,
    path: pathlib.Path,
) -> NlpConfig:
    """Parse the `[nlp]` table into a typed config object."""
    unknown_keys = set(table) - {"model", "sentence-provider"}
    if unknown_keys:
        key = f"nlp.{min(unknown_keys)}"
        raise InvalidConfigError(path, key, "is not supported")

    return NlpConfig(
        model=ensure_string(
            table.get("model", "en_core_web_sm"), path=path, key="nlp.model"
        ),
        sentence_provider=ensure_string(
            table.get("sentence-provider", "sentencizer"),
            path=path,
            key="nlp.sentence-provider",
        ),
        reserved=dict(table),
    )


def _parse_rule_tables(
    table: cabc.Mapping[str, object],
    *,
    path: pathlib.Path,
) -> dict[str, dict[str, object]]:
    """Preserve the raw per-rule tables from the config file."""
    rules: dict[str, dict[str, object]] = {}
    for rule_code, rule_table in table.items():
        if not isinstance(rule_table, cabc.Mapping):
            raise InvalidConfigError(path, f"rule.{rule_code}", "must be a mapping")
        rules[rule_code] = dict(typ.cast("cabc.Mapping[str, object]", rule_table))
    return rules


def parse_config_table(
    table: cabc.Mapping[str, object],
    *,
    path: pathlib.Path,
) -> StilyagiConfig:
    """Parse a selected config mapping into a resolved configuration.

    Parameters
    ----------
    table : collections.abc.Mapping[str, object]
        Selected Stilyagi configuration values from a supported TOML file.
    path : pathlib.Path
        Path used to identify invalid configuration values in diagnostics.

    Returns
    -------
    StilyagiConfig
        Parsed configuration with typed fields and preserved reserved values.

    Raises
    ------
    InvalidConfigError
        If the table contains unsupported keys or invalid field values.
    """
    unknown_keys = set(table) - {
        "cache-dir",
        "respect-gitignore",
        "line-length",
        "extend",
        "plugins",
        "lint",
        "extract",
        "nlp",
        "rule",
    }
    if unknown_keys:
        raise InvalidConfigError(path, min(unknown_keys), "is not supported")

    sections = _parse_config_sections(table, path=path)

    return StilyagiConfig(
        cache_dir=_parse_cache_dir(table, path=path),
        respect_gitignore=ensure_bool(
            table.get("respect-gitignore", True),
            path=path,
            key="respect-gitignore",
        ),
        line_length=ensure_int(
            table.get("line-length", 88), path=path, key="line-length"
        ),
        plugins=ensure_string_sequence(
            table.get("plugins", ("builtin",)), path=path, key="plugins"
        ),
        lint=sections.lint,
        extract=sections.extract,
        nlp=sections.nlp,
        rules=sections.rules,
        reserved=_build_reserved_table(table, sections, path=path),
    )


@dc.dataclass(frozen=True, slots=True)
class _ParsedSections:
    """The typed sub-tables parsed from one config namespace."""

    lint: LintConfig
    extract: MarkdownExtractConfig
    nlp: NlpConfig
    rules: dict[str, dict[str, object]]


def _parse_config_sections(
    table: cabc.Mapping[str, object],
    *,
    path: pathlib.Path,
) -> _ParsedSections:
    """Parse the typed sub-tables of one config namespace."""
    return _ParsedSections(
        lint=_parse_lint_config(
            ensure_mapping(table.get("lint", {}), path=path, key="lint"), path=path
        ),
        extract=_parse_extract_config(
            ensure_mapping(table.get("extract", {}), path=path, key="extract"),
            path=path,
        ),
        nlp=_parse_nlp_config(
            ensure_mapping(table.get("nlp", {}), path=path, key="nlp"), path=path
        ),
        rules=_parse_rule_tables(
            ensure_mapping(table.get("rule", {}), path=path, key="rule"),
            path=path,
        ),
    )


def _parse_cache_dir(
    table: cabc.Mapping[str, object],
    *,
    path: pathlib.Path,
) -> pathlib.Path:
    """Parse the `cache-dir` value into a path object."""
    value = table.get("cache-dir", pathlib.Path(".stilyagi_cache"))
    match value:
        case pathlib.Path():
            return value
        case str():
            return pathlib.Path(value)
        case _:
            raise InvalidConfigError(path, "cache-dir", "must be a path or string")


def _build_reserved_table(
    table: cabc.Mapping[str, object],
    sections: _ParsedSections,
    *,
    path: pathlib.Path,
) -> dict[str, object]:
    """Preserve raw values that later slices will interpret."""
    reserved: dict[str, object] = {
        "line-length": ensure_int(
            table.get("line-length", 88), path=path, key="line-length"
        ),
        "lint": sections.lint.reserved,
        "nlp": sections.nlp.reserved,
        "rule": sections.rules,
    }
    if "extend" in table:
        reserved["extend"] = ensure_extend_value(
            table["extend"], path=path, key="extend"
        )
    return reserved
