"""Run and render the read-only configuration inspection command."""

import collections.abc as cabc
import json
import pathlib
import re
import tomllib
import typing as typ

from stilyagi import config
from stilyagi.cli_command_shell import command_streams, write_command_failure
from stilyagi.cli_config import _build_rule_selection_overrides
from stilyagi.config.path_resolution import PathResolutionError, expand_user
from stilyagi.config.provenance import _is_within

if typ.TYPE_CHECKING:
    from stilyagi.cli_args import _ConfigInspectionOptions
    from stilyagi.config.inspection import _ConfigInspection
    from stilyagi.config.provenance import _ConfigOrigin, _OriginPath

_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+\Z")
_KEY_COMPONENT = re.compile(r'"(?:[^"\\]|\\.)*"|\'[^\']*\'|[A-Za-z0-9_-]+')


class _UnknownConfigKeyError(config.ConfigError):
    """Identify a requested config key absent from the resolved values."""

    def __init__(self, key: str) -> None:
        """Retain the missing key in the human-readable error."""
        super().__init__(f"unknown configuration key: {key}")


class _InspectionTargetError(config.ConfigError):
    """Identify an inspection target that cannot be expanded or found.

    A target naming no existing file or directory is an operational error of
    this command, not a configuration failure. It still travels as a
    `ConfigError` so the command boundary reports every expected failure
    through one path and one exit status.

    The reason is chosen from a closed set rather than supplied as prose, so
    the sentence the user reads is stated once here. Every message names the
    target that failed.
    """

    def __init__(
        self, reason: typ.Literal["expand", "missing"], target: object
    ) -> None:
        """Render the named reason around the target it concerns."""
        detail = (
            f"cannot expand target: {target}"
            if reason == "expand"
            else f"target does not exist: {target}"
        )
        super().__init__(detail)


def _spell_origin_path(path: _OriginPath) -> str:
    """Render one origin path as the TOML dotted key that selects it.

    Components that are not bare keys are quoted, because a component may
    itself contain dots — a `per-file-ignores` glob such as `*.md` is the
    common case. Quoting keeps the rendered key unambiguous and parseable by
    `_parse_origin_path`, so a key printed by this command can be passed back
    to it unchanged.

    Returns
    -------
    str
        The dotted key spelling, with non-bare components quoted.
    """
    return ".".join(
        component
        if _BARE_KEY.match(component)
        # `ensure_ascii=False` is not cosmetic here. The escaped form of an
        # astral-plane character is a surrogate pair, and TOML forbids
        # surrogate code points in `\u` escapes, so `_decode_key_component`
        # would reject the very key this command just printed.
        else json.dumps(component, ensure_ascii=False)
        for component in path
    )


def _split_dotted_key(key: str) -> list[str]:
    """Split a TOML dotted key into its components, keeping quoted ones whole."""
    components = _KEY_COMPONENT.findall(key)
    if ".".join(components) != key:
        raise _UnknownConfigKeyError(key)
    return components


def _decode_key_component(component: str, key: str) -> str:
    """Decode one dotted-key component, rejecting any non-key syntax."""
    if not component.startswith(('"', "'")):
        return component
    try:
        decoded = tomllib.loads(f"k = {component}")["k"]
    except tomllib.TOMLDecodeError as error:
        raise _UnknownConfigKeyError(key) from error
    if not isinstance(decoded, str):
        raise _UnknownConfigKeyError(key)
    return decoded


def _parse_origin_path(key: str) -> _OriginPath:
    """Parse a TOML dotted key into the key components it selects."""
    return tuple(
        _decode_key_component(component, key) for component in _split_dotted_key(key)
    )


def _run_config_inspection(
    options: _ConfigInspectionOptions,
    *,
    output: typ.TextIO | None = None,
    error: typ.TextIO | None = None,
    resolver: config.ConfigResolver | None = None,
) -> int:
    """Inspect and render effective config values without linting files.

    Parameters
    ----------
    options:
        Parsed options for one read-only config command.
    output, error:
        Optional streams used for the result and operational errors.
    resolver:
        Resolver to query, or ``None`` to build a single-use one. Supplying it
        lets a caller observe the resolution through `cache_stats` and drive
        the query with a double.

    Returns
    -------
    int
        Zero on success or two when the target or configuration is invalid.

    Examples
    --------
    >>> from io import StringIO
    >>> from stilyagi.cli_args import _ConfigInspectionOptions
    >>> options = _ConfigInspectionOptions(
    ...     key="cache-dir", target=".", output_format="json",
    ...     explicit_config=(), isolated=False, select=(), ignore=(),
    ...     extend_select=(),
    ... )
    >>> _run_config_inspection(options, output=StringIO(), error=StringIO())
    0
    """
    streams = command_streams(output, error)
    try:
        target = _inspection_target(options.target)
        inspection, selected_value, selected_origins = _load_inspection(
            options,
            target,
            resolver if resolver is not None else config.ConfigResolver(),
        )
    except config.ConfigError as exc:
        return write_command_failure(streams.error, command="config", failure=exc)
    rendered = _render_inspection(
        options,
        inspection,
        selected_value,
        selected_origins,
    )
    streams.output.write(rendered)
    return 0


def _inspection_target(target_value: str) -> pathlib.Path:
    """Expand and validate the file or directory the command inspects.

    The expansion goes through `path_resolution.expand_user` rather than
    `Path.expanduser` so an unresolvable home directory becomes the named
    `PathResolutionError` this command reports, instead of a bare `RuntimeError`
    escaping as a traceback. Every other `RuntimeError` still propagates: only
    the environmental failure is this command's operational error to absorb.

    Returns
    -------
    pathlib.Path
        The target, which names an existing file or directory.

    Raises
    ------
    _InspectionTargetError
        The target cannot be expanded, or names no existing file or directory.
        The reason is the sentence the command boundary reports.
    """
    try:
        target = expand_user(pathlib.Path(target_value))
    except PathResolutionError as exc:
        raise _InspectionTargetError("expand", exc) from exc
    if target.is_file() or target.is_dir():
        return target
    raise _InspectionTargetError("missing", target)


def _load_inspection(
    options: _ConfigInspectionOptions,
    target: pathlib.Path,
    resolver: config.ConfigResolver,
) -> tuple[_ConfigInspection, object, dict[_OriginPath, _ConfigOrigin]]:
    """Resolve the effective config and select its requested key and origins.

    The resolver arrives from the caller rather than being constructed here, so
    this read-only query can be driven by a test double and inspected through
    its accumulated `cache_stats` without touching the filesystem.

    Returns
    -------
    tuple
        The full inspection, the selected key's value, and its per-leaf
        origins.
    """
    overrides = _build_rule_selection_overrides(
        select=options.select,
        ignore=options.ignore,
        extend_select=options.extend_select,
    )
    inspection = resolver._inspect_config_for_path(
        target,
        cli_overrides=overrides or None,
        explicit_config=options.explicit_config or None,
        isolated=options.isolated,
    )
    selected_value, selected_origins = _select_inspection(inspection, options.key)
    return inspection, selected_value, selected_origins


def _render_inspection(
    options: _ConfigInspectionOptions,
    inspection: _ConfigInspection,
    selected_value: object,
    selected_origins: dict[_OriginPath, _ConfigOrigin],
) -> str:
    """Render the selected inspection in the requested stable format."""
    if options.output_format == "json":
        return _render_json(options.key, selected_value, selected_origins)
    return _render_text(selected_origins, inspection)


def _select_inspection(
    inspection: _ConfigInspection,
    key: str | None,
) -> tuple[object, dict[_OriginPath, _ConfigOrigin]]:
    """Select one key and the origins that describe its value."""
    if key is None:
        return inspection.values, inspection.origins

    path = _parse_origin_path(key)
    value: object = inspection.values
    for component in path:
        if not isinstance(value, cabc.Mapping) or component not in value:
            raise _UnknownConfigKeyError(key)
        value = value[component]

    origins = {
        origin_path: origin
        for origin_path, origin in inspection.origins.items()
        if _is_within(origin_path, path)
    }
    return value, origins


def _render_origin(origin: _ConfigOrigin) -> dict[str, object]:
    """Render one origin as the stable JSON object the RFC specifies."""
    return {
        "kind": origin.kind,
        "source_file": (
            str(origin.source_file) if origin.source_file is not None else None
        ),
        "cli_overridden": origin.cli_overridden,
    }


def _render_json(
    key: str | None,
    value: object,
    origins: cabc.Mapping[_OriginPath, _ConfigOrigin],
) -> str:
    """Render the selected values and origins as deterministic JSON."""
    rendered_origins = {
        _spell_origin_path(path): _render_origin(origin)
        for path, origin in sorted(origins.items())
    }
    if key is None:
        payload = {"values": value, "origins": rendered_origins}
    else:
        payload = {"key": key, "value": value, "origins": rendered_origins}
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _render_text(
    origins: cabc.Mapping[_OriginPath, _ConfigOrigin],
    inspection: _ConfigInspection,
) -> str:
    """Render flattened values with deterministic source annotations."""
    lines: list[str] = []
    for path in sorted(origins):
        value = _value_at_path(inspection.values, path)
        source = origins[path]
        annotation = source.kind
        if source.source_file is not None:
            annotation = f"{annotation} from {source.source_file}"
        if source.cli_overridden:
            annotation = f"{annotation} (CLI override)"
        encoded_value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        lines.append(f"{_spell_origin_path(path)} = {encoded_value}  # {annotation}")
    return "\n".join(lines) + "\n"


def _value_at_path(values: cabc.Mapping[str, object], path: _OriginPath) -> object:
    """Return a previously validated value at one key-component path."""
    value: object = values
    for component in path:
        mapping = typ.cast("cabc.Mapping[str, object]", value)
        value = mapping[component]
    return value
