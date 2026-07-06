"""Configuration schema objects for Stilyagi."""

from __future__ import annotations

import collections.abc as cabc
import dataclasses as dc
import pathlib
import typing as typ


def _coerce_path(value: object) -> pathlib.Path:
    """Normalise a cache-directory value to a path object."""
    if isinstance(value, pathlib.Path):
        return value
    if isinstance(value, str):
        return pathlib.Path(value)
    raise TypeError


def _coerce_string_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    """Normalise a sequence field to an immutable tuple of strings."""
    if isinstance(value, str) or not isinstance(value, cabc.Iterable):
        raise TypeError

    items = tuple(value)
    if any(not isinstance(item, str) for item in items):
        raise TypeError
    return typ.cast("tuple[str, ...]", items)


def _coerce_string_to_string_tuple_map(
    value: object,
    *,
    field_name: str,
) -> dict[str, tuple[str, ...]]:
    """Normalise a mapping of string lists into string tuples."""
    if not isinstance(value, cabc.Mapping):
        raise TypeError

    coerced: dict[str, tuple[str, ...]] = {}
    for key, items in value.items():
        if not isinstance(key, str):
            raise TypeError
        coerced[key] = _coerce_string_tuple(items, field_name=f"{field_name}[{key!r}]")
    return coerced


def _require_instance(
    value: object,
    expected: type | tuple[type, ...],
) -> None:
    """Raise ``TypeError`` when a field has an unexpected type."""
    if not isinstance(value, expected):
        raise TypeError


def _require_strict_int(value: object) -> None:
    """Raise ``TypeError`` unless a field is an integer (and not a bool)."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError


def _copy_mapping(value: object, *, field_name: str) -> dict[str, object]:
    """Copy a mapping into a plain dictionary with string keys."""
    if not isinstance(value, cabc.Mapping):
        raise TypeError
    mapping = typ.cast("cabc.Mapping[object, object]", value)
    return {str(key): item for key, item in mapping.items()}


class InvalidCacheDirError(ValueError):
    """Raised when the cache-directory setting is blank."""


class InvalidConfigError(ValueError):
    """Raised when a config file contains an unsupported key."""

    def __init__(self, path: pathlib.Path, key: str, detail: str) -> None:
        """Store the file path and key that failed validation."""
        self.path = path
        self.key = key
        self.detail = detail
        super().__init__(f"Invalid config in {path}: {key}: {detail}")


@dc.dataclass(frozen=True, slots=True)
class LintConfig:
    """Lint configuration carried through the schema layer.

    Parameters
    ----------
    select:
        Rule prefixes that are enabled by default.
    ignore:
        Rule prefixes that are disabled by default.
    preview:
        Whether preview rules are enabled.
    fixable:
        Reserved for later fix-planning slices.
    unfixable:
        Reserved for later fix-planning slices.
    per_file_ignores:
        Per-path rule exclusions.
    reserved:
        Preserved raw values for later slices.
    """

    select: tuple[str, ...] = ("MD", "DOC", "PUN", "STY", "PYDOC")
    ignore: tuple[str, ...] = ()
    preview: bool = False
    fixable: tuple[str, ...] = ("ALL",)
    unfixable: tuple[str, ...] = ()
    per_file_ignores: dict[str, tuple[str, ...]] = dc.field(default_factory=dict)
    reserved: dict[str, object] = dc.field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalise the sequence and mapping fields."""
        object.__setattr__(
            self, "select", _coerce_string_tuple(self.select, field_name="select")
        )
        object.__setattr__(
            self, "ignore", _coerce_string_tuple(self.ignore, field_name="ignore")
        )
        object.__setattr__(
            self, "fixable", _coerce_string_tuple(self.fixable, field_name="fixable")
        )
        object.__setattr__(
            self,
            "unfixable",
            _coerce_string_tuple(self.unfixable, field_name="unfixable"),
        )
        object.__setattr__(
            self,
            "per_file_ignores",
            _coerce_string_to_string_tuple_map(
                self.per_file_ignores,
                field_name="per_file_ignores",
            ),
        )
        object.__setattr__(
            self, "reserved", _copy_mapping(self.reserved, field_name="reserved")
        )
        _require_instance(self.preview, bool)


@dc.dataclass(frozen=True, slots=True)
class MarkdownExtractConfig:
    """Markdown extraction configuration carried through the schema layer."""

    gfm: bool = True
    frontmatter: bool = True
    mdx: bool = False

    def __post_init__(self) -> None:
        """Validate the booleans eagerly."""
        _require_instance(self.gfm, bool)
        _require_instance(self.frontmatter, bool)
        _require_instance(self.mdx, bool)


@dc.dataclass(frozen=True, slots=True)
class NlpConfig:
    """NLP configuration preserved from the RFC baseline."""

    model: str = "en_core_web_sm"
    sentence_provider: str = "sentencizer"
    reserved: dict[str, object] = dc.field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and normalise the preserved values."""
        _require_instance(self.model, str)
        _require_instance(self.sentence_provider, str)
        object.__setattr__(
            self, "reserved", _copy_mapping(self.reserved, field_name="reserved")
        )


@dc.dataclass(frozen=True, slots=True)
class StilyagiConfig:
    """Resolved configuration for the Stilyagi command surface.

    Parameters
    ----------
    cache_dir:
        Repository-relative cache directory for future engine slices.
    respect_gitignore:
        Whether discovery should honour Git ignore rules in later slices.
    line_length:
        Reserved baseline line length.
    plugins:
        Enabled config plugins.
    lint:
        Lint-specific configuration.
    extract:
        Extraction configuration.
    nlp:
        NLP configuration.
    rules:
        Per-rule configuration blocks.
    reserved:
        Raw preserved values from the config file.
    """

    cache_dir: pathlib.Path = pathlib.Path(".stilyagi_cache")
    respect_gitignore: bool = True
    line_length: int = 88
    plugins: tuple[str, ...] = ("builtin",)
    lint: LintConfig = dc.field(default_factory=LintConfig)
    extract: MarkdownExtractConfig = dc.field(default_factory=MarkdownExtractConfig)
    nlp: NlpConfig = dc.field(default_factory=NlpConfig)
    rules: dict[str, dict[str, object]] = dc.field(default_factory=dict)
    reserved: dict[str, object] = dc.field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalise and validate the config boundary values."""
        object.__setattr__(self, "cache_dir", _coerce_path(self.cache_dir))
        if not str(self.cache_dir).strip():
            message = (
                f"Invalid cache_dir: {self.cache_dir!r}. It must be a non-empty path."
            )
            raise InvalidCacheDirError(message) from None
        _require_instance(self.respect_gitignore, bool)
        _require_strict_int(self.line_length)
        object.__setattr__(
            self, "plugins", _coerce_string_tuple(self.plugins, field_name="plugins")
        )
        _require_instance(self.lint, LintConfig)
        _require_instance(self.extract, MarkdownExtractConfig)
        _require_instance(self.nlp, NlpConfig)
        _require_instance(self.rules, cabc.Mapping)
        object.__setattr__(
            self,
            "rules",
            {str(code): dict(values) for code, values in self.rules.items()},
        )
        object.__setattr__(
            self, "reserved", _copy_mapping(self.reserved, field_name="reserved")
        )
