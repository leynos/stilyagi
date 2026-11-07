"""Raw configuration table primitives used by config resolution.

These helpers know nothing about caching or run state: they merge tables,
parse an inline `--config` fragment, split `--config` values into file paths and
fragments, and locate the directory from which nearest-config discovery should
start. :class:`stilyagi.config.resolve.ConfigResolver` composes them, and
keeping them separate lets that resolver stay a description of *when* each
primitive applies.
"""

import collections.abc as cabc
import pathlib
import tomllib
import typing as typ

from .load import discover_same_directory_config
from .path_resolution import expand_user
from .schema import InvalidConfigError
from .validate import ensure_extend_value

if typ.TYPE_CHECKING:  # pragma: no cover - typing only
    from .load import LoadedConfig


def merge_config_tables(
    base: cabc.Mapping[str, object],
    override: cabc.Mapping[str, object],
) -> dict[str, object]:
    """Merge two raw config tables with recursive mapping semantics.

    A key present in both tables merges recursively when both values are
    mappings; otherwise the override value replaces the base value wholesale.

    Parameters
    ----------
    base:
        The lower-precedence raw table, copied rather than mutated.
    override:
        The higher-precedence raw table.

    Returns
    -------
    dict[str, object]
        A new table whose nested mappings are themselves new dictionaries.

    Examples
    --------
    >>> merge_config_tables({"lint": {"select": ["A"]}}, {"lint": {"ignore": ["B"]}})
    {'lint': {'select': ['A'], 'ignore': ['B']}}
    >>> merge_config_tables({"lint": ["A"]}, {"lint": ["B"]})
    {'lint': ['B']}
    """
    merged = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, cabc.Mapping) and isinstance(value, cabc.Mapping):
            merged[key] = merge_config_tables(
                typ.cast("cabc.Mapping[str, object]", existing),
                typ.cast("cabc.Mapping[str, object]", value),
            )
            continue
        merged[key] = value
    return merged


def normalize_extend_values(
    value: object,
    *,
    path: pathlib.Path,
) -> tuple[str, ...]:
    """Normalize the raw `extend` value to an ordered tuple of strings.

    Parameters
    ----------
    value:
        The raw `extend` entry: ``None``, a single reference, or a sequence of
        references.
    path:
        Config file the value came from, used to locate a validation error.

    Returns
    -------
    tuple[str, ...]
        ``()`` for ``None``, a one-element tuple for a single string, or the
        validated sequence as a tuple. A malformed value propagates the
        :class:`~stilyagi.config.schema.InvalidConfigError` raised by
        :func:`~stilyagi.config.validate.ensure_extend_value`.

    Examples
    --------
    >>> normalize_extend_values(None, path=pathlib.Path("stilyagi.toml"))
    ()
    >>> normalize_extend_values("base.toml", path=pathlib.Path("stilyagi.toml"))
    ('base.toml',)
    >>> normalize_extend_values(
    ...     ["a.toml", "b.toml"], path=pathlib.Path("stilyagi.toml")
    ... )
    ('a.toml', 'b.toml')
    """
    if value is None:
        return ()
    validated = ensure_extend_value(value, path=path, key="extend")
    if isinstance(validated, str):
        return (validated,)
    return tuple(validated)


def load_inline_config(
    fragment: str,
    *,
    path: pathlib.Path,
) -> dict[str, object]:
    """Parse an inline `--config` fragment into a raw table.

    Parameters
    ----------
    fragment:
        TOML text supplied on the command line.
    path:
        Config path reported in a parse error.

    Returns
    -------
    dict[str, object]
        The parsed document as a raw table.

    Raises
    ------
    InvalidConfigError
        The fragment is not valid TOML.

    Examples
    --------
    >>> load_inline_config(
    ...     'lint.select = ["MD001"]', path=pathlib.Path("stilyagi.toml")
    ... )
    {'lint': {'select': ['MD001']}}
    """
    try:
        parsed = tomllib.loads(fragment)
    except tomllib.TOMLDecodeError as exc:
        raise InvalidConfigError(path, "config", str(exc)) from exc
    parsed_table: dict[str, object] = parsed
    return parsed_table


def resolve_config_reference(
    reference: str,
    *,
    base_directory: pathlib.Path,
    path: pathlib.Path,
) -> pathlib.Path:
    """Resolve one `extend` reference relative to its config file.

    Parameters
    ----------
    reference:
        The reference as written in `extend`; a leading ``~`` expands to the
        user's home directory.
    base_directory:
        Directory of the config file that names the reference.
    path:
        Config path reported when the reference cannot be resolved.

    Returns
    -------
    pathlib.Path
        The path of the referenced file.

    Raises
    ------
    InvalidConfigError
        No file exists at the resolved path.

    Examples
    --------
    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as tmp:
    ...     base = pathlib.Path(tmp)
    ...     (base / "shared.toml").touch()
    ...     resolved = resolve_config_reference(
    ...         "shared.toml",
    ...         base_directory=base,
    ...         path=base / "stilyagi.toml",
    ...     )
    ...     resolved == base / "shared.toml"
    True
    """
    candidate = expand_user(pathlib.Path(reference))
    if not candidate.is_absolute():
        candidate = base_directory / candidate
    if candidate.is_file():
        return candidate
    raise InvalidConfigError(path, "extend", f"missing config file: {reference}")


def target_directory(target: pathlib.Path) -> pathlib.Path:
    """Return the directory from which config discovery should start.

    Parameters
    ----------
    target:
        A directory, or a file whose parent directory governs discovery.

    Returns
    -------
    pathlib.Path
        The resolved directory: ``target`` itself for a directory, otherwise
        its resolved parent.

    Examples
    --------
    >>> target_directory(pathlib.Path("docs/users-guide.md")).name
    'docs'
    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as tmp:
    ...     target_directory(pathlib.Path(tmp)) == pathlib.Path(tmp).resolve()
    True
    """
    if target.is_dir():
        return expand_user(target).resolve()
    return expand_user(target).parent.resolve()


def search_ancestors_for_config(directory: pathlib.Path) -> LoadedConfig | None:
    """Walk from a directory to the filesystem root looking for config.

    Parameters
    ----------
    directory:
        The directory where the upward search starts.

    Returns
    -------
    LoadedConfig | None
        The nearest config at or above ``directory``, or ``None`` when no
        ancestor holds a supported config file.

    Examples
    --------
    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as tmp:
    ...     root = pathlib.Path(tmp)
    ...     nested = root / "a" / "b"
    ...     nested.mkdir(parents=True)
    ...     (root / "stilyagi.toml").touch()
    ...     found = search_ancestors_for_config(nested)
    ...     found is not None and found.path == root / "stilyagi.toml"
    True
    """
    current = directory
    while True:
        discovered = discover_same_directory_config(current)
        if discovered is not None:
            return discovered
        if current.parent == current:
            return None
        current = current.parent


def _classify_explicit_config(
    value: str | pathlib.Path,
) -> tuple[str, str | pathlib.Path]:
    """Classify one `--config` value as inline TOML or a file path."""
    if isinstance(value, pathlib.Path):
        return "path", value

    candidate = expand_user(pathlib.Path(value))
    if "=" in value and not candidate.exists():
        return "inline", value
    if candidate.exists():
        return "path", candidate
    raise InvalidConfigError(candidate, "config", "does not exist")


def split_explicit_config(
    explicit_config: cabc.Iterable[str | pathlib.Path] | None,
) -> tuple[list[pathlib.Path], list[str]]:
    """Split `--config` values into file paths and inline fragments.

    Parameters
    ----------
    explicit_config:
        Values supplied to `--config`, each a path or a TOML fragment.

    Returns
    -------
    tuple[list[pathlib.Path], list[str]]
        The file paths and the inline fragments, each in input order. A value
        that is neither an existing path nor an ``=``-bearing fragment
        propagates the :class:`~stilyagi.config.schema.InvalidConfigError`
        raised by :func:`_classify_explicit_config`.

    Examples
    --------
    >>> split_explicit_config(["lint.select = ['MD001']"])
    ([], ["lint.select = ['MD001']"])
    >>> split_explicit_config(None)
    ([], [])
    """
    explicit_paths: list[pathlib.Path] = []
    explicit_inline: list[str] = []
    for value in explicit_config or ():
        kind, payload = _classify_explicit_config(value)
        if kind == "path":
            explicit_paths.append(typ.cast("pathlib.Path", payload))
        else:
            explicit_inline.append(typ.cast("str", payload))
    return explicit_paths, explicit_inline
