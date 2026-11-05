"""Run and render the read-only configuration inspection command."""

import collections.abc as cabc
import json
import pathlib
import re
import sys
import tomllib
import typing as typ

from stilyagi import config
from stilyagi.cli_config import _build_rule_selection_overrides
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
        component if _BARE_KEY.match(component) else json.dumps(component)
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
) -> int:
    """Inspect and render effective config values without linting files.

    Parameters
    ----------
    options:
        Parsed options for one read-only config command.
    output, error:
        Optional streams used for the result and operational errors.

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
    out_stream = output if output is not None else sys.stdout
    error_stream = error if error is not None else sys.stderr
    target = _inspection_target(options.target, error_stream)
    if target is None:
        return 2
    try:
        inspection, selected_value, selected_origins = _load_inspection(
            options,
            target,
        )
    except config.ConfigError as exc:
        error_stream.write(f"stilyagi config: {exc}\n")
        return 2
    rendered = _render_inspection(
        options,
        inspection,
        selected_value,
        selected_origins,
    )
    out_stream.write(rendered)
    return 0


def _inspection_target(
    target_value: str,
    error: typ.TextIO,
) -> pathlib.Path | None:
    """Expand and validate the file or directory inspected by the command."""
    target = pathlib.Path(target_value).expanduser()
    if target.is_file():
        return target
    if target.is_dir():
        return target
    error.write(f"stilyagi config: target does not exist: {target}\n")
    return None


def _load_inspection(
    options: _ConfigInspectionOptions,
    target: pathlib.Path,
) -> tuple[_ConfigInspection, object, dict[_OriginPath, _ConfigOrigin]]:
    """Resolve the effective config and select its requested key and origins."""
    overrides = _build_rule_selection_overrides(
        select=options.select,
        ignore=options.ignore,
        extend_select=options.extend_select,
    )
    inspection = config.ConfigResolver()._inspect_config_for_path(
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
