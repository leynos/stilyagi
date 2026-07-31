"""Config-file loading helpers for Stilyagi."""

import collections.abc as cabc
import dataclasses as dc
import logging
import tomllib
import typing as typ

from .parse import _parse_config_table
from .schema import InvalidConfigError, StilyagiConfig

if typ.TYPE_CHECKING:
    import pathlib

_LOGGER = logging.getLogger(__name__)

_SUPPORTED_DIRECTORY_FILENAMES = (
    ".stilyagi.toml",
    "stilyagi.toml",
    "pyproject.toml",
)


@dc.dataclass(frozen=True, slots=True)
class LoadedConfig:
    """A config path with its parsed config and raw pre-parse table.

    ``raw_table`` lets a caller reuse the read from discovery, not re-read it.
    """

    path: pathlib.Path
    config: StilyagiConfig
    raw_table: cabc.Mapping[str, object] = dc.field(default_factory=dict)


def _load_toml(path: pathlib.Path) -> cabc.Mapping[str, object]:
    """Load a TOML file into a mapping.

    A missing file propagates as ``FileNotFoundError``; any other read failure
    (a directory, permission denied) becomes a typed ``InvalidConfigError``.

    Returns
    -------
    collections.abc.Mapping[str, object]
        The parsed TOML document.

    Raises
    ------
    FileNotFoundError
        The requested configuration file does not exist.
    InvalidConfigError
        The configuration path cannot be read.
    """
    try:
        with path.open("rb") as handle:
            return typ.cast("cabc.Mapping[str, object]", tomllib.load(handle))
    except FileNotFoundError:
        raise
    except OSError as exc:
        _LOGGER.warning("cannot read config file %s: %s", path, exc)
        raise InvalidConfigError(path, "config", f"cannot be read: {exc}") from exc


def _read_config_document(path: pathlib.Path) -> cabc.Mapping[str, object]:
    """Read one TOML config file, mapping load failures to typed errors."""
    _LOGGER.debug("reading config file %s", path)
    try:
        return _load_toml(path)
    except FileNotFoundError as exc:
        _LOGGER.warning("config file not found: %s", path)
        raise InvalidConfigError(path, "config", "does not exist") from exc
    except tomllib.TOMLDecodeError as exc:
        _LOGGER.warning("invalid TOML in config file %s: %s", path, exc)
        raise InvalidConfigError(path, "toml", str(exc)) from exc


def _load_config_table(path: pathlib.Path) -> cabc.Mapping[str, object]:
    """Load and select the supported config table for one file."""
    return _select_config_table(_read_config_document(path), path=path)


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
    """Load and parse a single supported config file.

    Parameters
    ----------
    path:
        Path to a ``.stilyagi.toml``, ``stilyagi.toml``, or ``pyproject.toml``
        file. The Stilyagi namespace is selected according to the file kind.

    Returns
    -------
    StilyagiConfig
        The parsed, validated configuration.
    """
    config_table = _load_config_table(path)
    return _parse_config_table(config_table, path=path)


def discover_same_directory_config(directory: pathlib.Path) -> LoadedConfig | None:
    """Return the highest-precedence config file in one directory, if any.

    Parameters
    ----------
    directory:
        Directory searched for the supported config filenames in precedence
        order (``.stilyagi.toml``, ``stilyagi.toml``, ``pyproject.toml``).

    Returns
    -------
    LoadedConfig | None
        The path and parsed config of the highest-precedence supported file
        present, or ``None`` when the directory holds no Stilyagi config.
    """
    for filename in _SUPPORTED_DIRECTORY_FILENAMES:
        candidate = directory / filename
        if not candidate.is_file():
            continue
        raw_document = _read_config_document(candidate)
        if not _has_supported_content(raw_document, path=candidate):
            continue
        selected = _select_config_table(raw_document, path=candidate)
        return LoadedConfig(
            path=candidate,
            config=_parse_config_table(selected, path=candidate),
            raw_table=selected,
        )
    return None
