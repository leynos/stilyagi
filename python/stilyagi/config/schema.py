"""Configuration schema objects for Stilyagi."""

import collections.abc as cabc
import dataclasses as dc
import pathlib
import typing as typ


def _coerce_path(value: object, *, field_name: str) -> pathlib.Path:
    """Normalise a cache-directory value to a path object."""
    match value:
        case pathlib.Path():
            return value
        case str():
            return pathlib.Path(value)
        case _:
            message = f"{field_name} must be a path or string"
            raise TypeError(message)


def _coerce_string_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    """Normalise a sequence field to an immutable tuple of strings."""
    if isinstance(value, str) or not isinstance(value, cabc.Iterable):
        message = f"{field_name} must be a sequence of strings"
        raise TypeError(message)

    items = tuple(value)
    if any(not isinstance(item, str) for item in items):
        message = f"{field_name} must contain only strings"
        raise TypeError(message)
    return typ.cast("tuple[str, ...]", items)


def _coerce_string_to_string_tuple_map(
    value: object,
    *,
    field_name: str,
) -> dict[str, tuple[str, ...]]:
    """Normalise a mapping of string lists into string tuples."""
    if not isinstance(value, cabc.Mapping):
        message = f"{field_name} must be a mapping"
        raise TypeError(message)

    coerced: dict[str, tuple[str, ...]] = {}
    for key, items in value.items():
        if not isinstance(key, str):
            message = f"{field_name} keys must be strings"
            raise TypeError(message)
        coerced[key] = _coerce_string_tuple(items, field_name=f"{field_name}[{key!r}]")
    return coerced


def _require_instance(
    value: object,
    expected: type | tuple[type, ...],
    *,
    field_name: str,
) -> None:
    """Raise ``TypeError`` when a field has an unexpected type."""
    if not isinstance(value, expected):
        message = f"{field_name} has an unexpected type: {type(value).__name__}"
        raise TypeError(message)


def _require_strict_int(value: object, *, field_name: str) -> None:
    """Raise ``TypeError`` unless a field is an integer (and not a bool)."""
    if not isinstance(value, int) or isinstance(value, bool):
        message = f"{field_name} must be an int"
        raise TypeError(message)


def _copy_mapping(value: object, *, field_name: str) -> dict[str, object]:
    """Copy a mapping into a plain dictionary with string keys."""
    if not isinstance(value, cabc.Mapping):
        message = f"{field_name} must be a mapping"
        raise TypeError(message)
    mapping = typ.cast("cabc.Mapping[object, object]", value)
    return {str(key): item for key, item in mapping.items()}


class ConfigError(ValueError):
    """Base class for all Stilyagi configuration errors.

    Subclassing a single base lets callers catch every config-related failure
    with one ``except`` clause while still distinguishing specific causes.
    """


class InvalidCacheDirError(ConfigError):
    """Raised when the cache-directory setting is blank."""


class InvalidConfigError(ConfigError):
    """Raised when a config file contains an unsupported or malformed value.

    Parameters
    ----------
    path:
        Path of the config file (or resolution target) that failed validation.
    key:
        The offending config key, or a category such as ``"toml"`` or
        ``"config"`` when the failure is not tied to a single key.
    detail:
        Human-readable explanation of why the value was rejected.
    """

    def __init__(self, path: pathlib.Path, key: str, detail: str) -> None:
        """Store the file path and key that failed validation."""
        self.path = path
        self.key = key
        self.detail = detail
        message = f"Invalid config in {path}: {key}: {detail}"
        super().__init__(message)


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
        _require_instance(self.preview, bool, field_name="preview")


@dc.dataclass(frozen=True, slots=True)
class MarkdownExtractConfig:
    """Markdown extraction configuration carried through the schema layer.

    Parameters
    ----------
    gfm:
        Whether GitHub Flavoured Markdown extensions are enabled.
    frontmatter:
        Whether YAML frontmatter is extracted.
    mdx:
        Whether MDX syntax is enabled.
    """

    gfm: bool = True
    frontmatter: bool = True
    mdx: bool = False

    def __post_init__(self) -> None:
        """Validate the booleans eagerly."""
        _require_instance(self.gfm, bool, field_name="gfm")
        _require_instance(self.frontmatter, bool, field_name="frontmatter")
        _require_instance(self.mdx, bool, field_name="mdx")


@dc.dataclass(frozen=True, slots=True)
class NlpConfig:
    """NLP configuration preserved from the RFC baseline.

    Parameters
    ----------
    model:
        Name of the language model used by later NLP slices.
    sentence_provider:
        Identifier of the sentence-segmentation provider.
    reserved:
        Preserved raw values for later slices.
    """

    model: str = "en_core_web_sm"
    sentence_provider: str = "sentencizer"
    reserved: dict[str, object] = dc.field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and normalise the preserved values."""
        _require_instance(self.model, str, field_name="model")
        _require_instance(self.sentence_provider, str, field_name="sentence_provider")
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
        object.__setattr__(
            self, "cache_dir", _coerce_path(self.cache_dir, field_name="cache_dir")
        )
        if not str(self.cache_dir).strip():
            message = (
                f"Invalid cache_dir: {self.cache_dir!r}. It must be a non-empty path."
            )
            raise InvalidCacheDirError(message) from None
        _require_instance(self.respect_gitignore, bool, field_name="respect_gitignore")
        _require_strict_int(self.line_length, field_name="line_length")
        object.__setattr__(
            self, "plugins", _coerce_string_tuple(self.plugins, field_name="plugins")
        )
        _require_instance(self.lint, LintConfig, field_name="lint")
        _require_instance(self.extract, MarkdownExtractConfig, field_name="extract")
        _require_instance(self.nlp, NlpConfig, field_name="nlp")
        _require_instance(self.rules, cabc.Mapping, field_name="rules")
        object.__setattr__(
            self,
            "rules",
            {str(code): dict(values) for code, values in self.rules.items()},
        )
        object.__setattr__(
            self, "reserved", _copy_mapping(self.reserved, field_name="reserved")
        )
