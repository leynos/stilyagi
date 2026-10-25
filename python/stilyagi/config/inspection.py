"""Build the complete, validated value view used by config inspection."""

import collections.abc as cabc
import dataclasses as dc
import datetime as dt
import math
import pathlib
import typing as typ

from .parse import parse_config_table
from .provenance import (
    _config_table_from_layer,
    _ConfigOrigin,
    _ConfigTableWithOrigins,
    _merge_config_tables_with_origins,
    _origin_paths,
)
from .schema import StilyagiConfig


@dc.dataclass(frozen=True, slots=True)
class _ConfigInspection:
    """Hold validated effective values and their source ledger."""

    values: dict[str, object]
    origins: dict[str, _ConfigOrigin]


def _non_finite_float_value(number: float) -> str:
    """Represent a TOML non-finite float without emitting invalid JSON."""
    if math.isnan(number):
        return "nan"
    return "inf" if number > 0 else "-inf"


def _json_value(value: object) -> object:
    """Convert schema values to JSON-compatible built-in objects."""
    converted: object
    match value:
        case pathlib.Path() as path:
            converted = str(path)
        case (dt.datetime() | dt.date() | dt.time()) as temporal:
            converted = temporal.isoformat()
        case float() as number if not math.isfinite(number):
            converted = _non_finite_float_value(number)
        case cabc.Mapping() as mapping:
            typed_mapping = typ.cast("cabc.Mapping[object, object]", mapping)
            converted = {
                str(key): _json_value(child) for key, child in typed_mapping.items()
            }
        case tuple() | list() as sequence:
            typed_sequence = typ.cast("cabc.Sequence[object]", sequence)
            converted = [_json_value(child) for child in typed_sequence]
        case _:
            converted = value
    return converted


def _config_table(config: StilyagiConfig) -> dict[str, object]:
    """Expose supported values, including preserved config fields."""
    lint_table = {
        **config.lint.reserved,
        "select": config.lint.select,
        "ignore": config.lint.ignore,
        "preview": config.lint.preview,
    }
    nlp_table = {
        **config.nlp.reserved,
        "model": config.nlp.model,
        "sentence-provider": config.nlp.sentence_provider,
    }
    table: dict[str, object] = {
        "cache-dir": config.cache_dir,
        "respect-gitignore": config.respect_gitignore,
        "line-length": config.reserved.get("line-length", 88),
        "plugins": config.plugins,
        "lint": lint_table,
        "extract": {
            "markdown": {
                "gfm": config.extract.gfm,
                "frontmatter": config.extract.frontmatter,
                "mdx": config.extract.mdx,
            }
        },
        "nlp": nlp_table,
        "rule": config.rules,
    }
    if "extend" in config.reserved:
        table["extend"] = config.reserved["extend"]
    return typ.cast("dict[str, object]", _json_value(table))


def _build_config_inspection(
    resolved: _ConfigTableWithOrigins,
    *,
    target: pathlib.Path,
) -> _ConfigInspection:
    """Validate effective values, fill defaults and return leaf provenance."""
    defaults = _config_table(StilyagiConfig())
    default_origin = _ConfigOrigin("default", None, cli_overridden=False)
    merged = _merge_config_tables_with_origins(
        _config_table_from_layer(defaults, default_origin),
        resolved,
    )
    parsed = parse_config_table(merged.values, path=target)
    values = _config_table(parsed)
    value_origins = _origin_paths(
        values,
        origin_for_path=lambda _path: default_origin,
    )
    for key, origin in value_origins.items():
        merged.origins.setdefault(key, origin)
    return _ConfigInspection(values=values, origins=merged.origins)
