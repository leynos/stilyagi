"""Type-validation helpers for config-file parsing.

These helpers check raw TOML values at the config boundary and raise
`InvalidConfigError` with the offending file path and key.

Example
-------
>>> import pathlib
>>> _ensure_bool(True, path=pathlib.Path("stilyagi.toml"), key="lint.preview")
True
"""

import collections.abc as cabc
import typing as typ

from .schema import InvalidConfigError

if typ.TYPE_CHECKING:
    import pathlib


def _ensure_mapping(
    value: object, *, path: pathlib.Path, key: str
) -> cabc.Mapping[str, object]:
    """Validate that a config value is a mapping."""
    if not isinstance(value, cabc.Mapping):
        raise InvalidConfigError(path, key, "must be a mapping")
    return typ.cast("cabc.Mapping[str, object]", value)


def _ensure_bool(value: object, *, path: pathlib.Path, key: str) -> bool:
    """Validate that a config value is a boolean."""
    if not isinstance(value, bool):
        raise InvalidConfigError(path, key, "must be a bool")
    return value


def _ensure_int(value: object, *, path: pathlib.Path, key: str) -> int:
    """Validate that a config value is an integer."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise InvalidConfigError(path, key, "must be an int")
    return value


def _ensure_string(value: object, *, path: pathlib.Path, key: str) -> str:
    """Validate that a config value is a string."""
    if not isinstance(value, str):
        raise InvalidConfigError(path, key, "must be a string")
    return value


def _ensure_all_strings(
    items: tuple[object, ...],
    *,
    path: pathlib.Path,
    key: str,
) -> tuple[str, ...]:
    """Validate that every item in a tuple is a string."""
    if any(not isinstance(item, str) for item in items):
        raise InvalidConfigError(path, key, "must contain strings only")
    return typ.cast("tuple[str, ...]", items)


def _ensure_string_sequence(
    value: object,
    *,
    path: pathlib.Path,
    key: str,
) -> tuple[str, ...]:
    """Validate that a config value is a sequence of strings."""
    if not isinstance(value, cabc.Iterable) or isinstance(value, str):
        raise InvalidConfigError(path, key, "must be a sequence of strings")
    return _ensure_all_strings(tuple(value), path=path, key=key)


def _ensure_extend_value(
    value: object,
    *,
    path: pathlib.Path,
    key: str,
) -> str | cabc.Sequence[str]:
    """Validate the raw `extend` value without changing its shape."""
    match value:
        case str():
            return value
        case bytes() | bytearray():
            raise InvalidConfigError(
                path, key, "must be a string or a sequence of strings"
            )
        case cabc.Sequence():
            _ensure_all_strings(tuple(value), path=path, key=key)
            return typ.cast("cabc.Sequence[str]", value)
        case _:
            raise InvalidConfigError(
                path, key, "must be a string or a sequence of strings"
            )
