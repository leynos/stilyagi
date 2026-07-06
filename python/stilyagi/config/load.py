"""Config-file loading helpers for Stilyagi."""

from __future__ import annotations

import collections.abc as cabc
import dataclasses as dc
import pathlib
import tomllib
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

_SUPPORTED_DIRECTORY_FILENAMES = (
    ".stilyagi.toml",
    "stilyagi.toml",
    "pyproject.toml",
)


@dc.dataclass(frozen=True, slots=True)
class LoadedConfig:
    """A config file path together with its parsed configuration."""

    path: pathlib.Path
    config: StilyagiConfig


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
    if not isinstance(per_file_ignores_raw, cabc.Mapping):
        raise InvalidConfigError(path, "lint.per-file-ignores", "must be a mapping")

    per_file_ignores = {
        str(file_name): ensure_string_sequence(
            rule_codes,
            path=path,
            key=f"lint.per-file-ignores.{file_name}",
        )
        for file_name, rule_codes in per_file_ignores_raw.items()
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
    if not isinstance(markdown, cabc.Mapping):
        raise InvalidConfigError(path, "extract.markdown", "must be a mapping")

    markdown_unknown = set(markdown) - {"gfm", "frontmatter", "mdx"}
    if markdown_unknown:
        key = f"extract.markdown.{min(markdown_unknown)}"
        raise InvalidConfigError(path, key, "is not supported")

    return MarkdownExtractConfig(
        gfm=ensure_bool(
            markdown.get("gfm", True), path=path, key="extract.markdown.gfm"
        ),
        frontmatter=ensure_bool(
            markdown.get("frontmatter", True),
            path=path,
            key="extract.markdown.frontmatter",
        ),
        mdx=ensure_bool(
            markdown.get("mdx", False), path=path, key="extract.markdown.mdx"
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
        if not isinstance(rule_code, str):
            raise InvalidConfigError(path, "rule", "rule codes must be strings")
        if not isinstance(rule_table, cabc.Mapping):
            raise InvalidConfigError(path, f"rule.{rule_code}", "must be a mapping")
        rules[rule_code] = dict(typ.cast("cabc.Mapping[str, object]", rule_table))
    return rules


def _parse_config_table(
    table: cabc.Mapping[str, object],
    *,
    path: pathlib.Path,
) -> StilyagiConfig:
    """Parse one config namespace into a resolved configuration."""
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
    if isinstance(value, pathlib.Path):
        return value
    if isinstance(value, str):
        return pathlib.Path(value)
    raise InvalidConfigError(path, "cache-dir", "must be a string")


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


def _load_toml(path: pathlib.Path) -> cabc.Mapping[str, object]:
    """Load a TOML file into a mapping."""
    with path.open("rb") as handle:
        return typ.cast("cabc.Mapping[str, object]", tomllib.load(handle))


def _load_config_table(path: pathlib.Path) -> cabc.Mapping[str, object]:
    """Load and select the supported config table for one file."""
    try:
        raw_document = _load_toml(path)
    except FileNotFoundError as exc:
        raise InvalidConfigError(path, "config", "does not exist") from exc
    except tomllib.TOMLDecodeError as exc:
        raise InvalidConfigError(path, "toml", str(exc)) from exc
    return _select_config_table(raw_document, path=path)


def _select_config_table(
    raw_document: cabc.Mapping[str, object],
    *,
    path: pathlib.Path,
) -> cabc.Mapping[str, object]:
    """Select the Stilyagi namespace for the given file kind."""
    if path.name == "pyproject.toml":
        tool = raw_document.get("tool")
        if not isinstance(tool, cabc.Mapping):
            return {}
        stilyagi = tool.get("stilyagi")
        if not isinstance(stilyagi, cabc.Mapping):
            return {}
        return typ.cast("cabc.Mapping[str, object]", stilyagi)
    return raw_document


def _has_supported_content(
    raw_document: cabc.Mapping[str, object],
    *,
    path: pathlib.Path,
) -> bool:
    """Decide whether a candidate file should count as config."""
    if path.name == "pyproject.toml":
        tool = raw_document.get("tool")
        return isinstance(tool, cabc.Mapping) and isinstance(
            tool.get("stilyagi"), cabc.Mapping
        )
    return True


def load_config_file(path: pathlib.Path) -> StilyagiConfig:
    """Load a single supported config file."""
    config_table = _load_config_table(path)
    return _parse_config_table(config_table, path=path)


def discover_same_directory_config(directory: pathlib.Path) -> LoadedConfig | None:
    """Return the highest-precedence config file in a directory, if any."""
    for filename in _SUPPORTED_DIRECTORY_FILENAMES:
        candidate = directory / filename
        if not candidate.is_file():
            continue
        try:
            raw_document = _load_toml(candidate)
        except FileNotFoundError as exc:
            raise InvalidConfigError(candidate, "config", "does not exist") from exc
        except tomllib.TOMLDecodeError as exc:
            raise InvalidConfigError(candidate, "toml", str(exc)) from exc
        if not _has_supported_content(raw_document, path=candidate):
            continue
        return LoadedConfig(
            path=candidate,
            config=_parse_config_table(
                _select_config_table(raw_document, path=candidate), path=candidate
            ),
        )
    return None
