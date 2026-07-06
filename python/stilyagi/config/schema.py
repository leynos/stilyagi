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
        if not isinstance(self.preview, bool):
            raise TypeError


@dc.dataclass(frozen=True, slots=True)
class MarkdownExtractConfig:
    """Markdown extraction configuration carried through the schema layer."""

    gfm: bool = True
    frontmatter: bool = True
    mdx: bool = False

    def __post_init__(self) -> None:
        """Validate the booleans eagerly."""
        if not isinstance(self.gfm, bool):
            raise TypeError
        if not isinstance(self.frontmatter, bool):
            raise TypeError
        if not isinstance(self.mdx, bool):
            raise TypeError


@dc.dataclass(frozen=True, slots=True)
class NlpConfig:
    """NLP configuration preserved from the RFC baseline."""

    model: str = "en_core_web_sm"
    sentence_provider: str = "sentencizer"
    reserved: dict[str, object] = dc.field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and normalise the preserved values."""
        if not isinstance(self.model, str):
            raise TypeError
        if not isinstance(self.sentence_provider, str):
            raise TypeError
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
        if not isinstance(self.respect_gitignore, bool):
            raise TypeError
        if not isinstance(self.line_length, int) or isinstance(self.line_length, bool):
            raise TypeError
        object.__setattr__(
            self, "plugins", _coerce_string_tuple(self.plugins, field_name="plugins")
        )
        if not isinstance(self.lint, LintConfig):
            raise TypeError
        if not isinstance(self.extract, MarkdownExtractConfig):
            raise TypeError
        if not isinstance(self.nlp, NlpConfig):
            raise TypeError
        if not isinstance(self.rules, cabc.Mapping):
            raise TypeError
        object.__setattr__(
            self,
            "rules",
            {str(code): dict(values) for code, values in self.rules.items()},
        )
        object.__setattr__(
            self, "reserved", _copy_mapping(self.reserved, field_name="reserved")
        )
