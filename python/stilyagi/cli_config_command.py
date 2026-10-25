"""Run and render the read-only configuration inspection command."""

import collections.abc as cabc
import json
import pathlib
import sys
import typing as typ

from stilyagi import config
from stilyagi.cli_config import _build_rule_selection_overrides

if typ.TYPE_CHECKING:
    from stilyagi.cli_args import _ConfigInspectionOptions
    from stilyagi.config.inspection import _ConfigInspection
    from stilyagi.config.provenance import _ConfigOrigin


class _UnknownConfigKeyError(config.ConfigError):
    """Identify a requested config key absent from the resolved values."""

    def __init__(self, key: str) -> None:
        """Retain the missing key in the human-readable error."""
        super().__init__(f"unknown configuration key: {key}")


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
    target = pathlib.Path(options.target).expanduser()
    if not target.exists() or not (target.is_file() or target.is_dir()):
        error_stream.write(f"stilyagi config: target does not exist: {target}\n")
        return 2

    overrides = _build_rule_selection_overrides(
        select=options.select,
        ignore=options.ignore,
        extend_select=options.extend_select,
    )
    try:
        inspection = config.ConfigResolver()._inspect_config_for_path(
            target,
            cli_overrides=overrides or None,
            explicit_config=options.explicit_config or None,
            isolated=options.isolated,
        )
        selected_value, selected_origins = _select_inspection(
            inspection,
            options.key,
        )
    except config.ConfigError as exc:
        error_stream.write(f"stilyagi config: {exc}\n")
        return 2

    if options.output_format == "json":
        rendered = _render_json(options.key, selected_value, selected_origins)
    else:
        rendered = _render_text(selected_origins, inspection)
    out_stream.write(rendered)
    return 0


def _select_inspection(
    inspection: _ConfigInspection,
    key: str | None,
) -> tuple[object, dict[str, _ConfigOrigin]]:
    """Select one dotted key and the origins that describe its value."""
    if key is None:
        return inspection.values, inspection.origins

    value: object = inspection.values
    for component in key.split("."):
        if not isinstance(value, cabc.Mapping) or component not in value:
            raise _UnknownConfigKeyError(key)
        value = value[component]

    prefix = f"{key}."
    origins = {
        path: origin
        for path, origin in inspection.origins.items()
        if path == key or path.startswith(prefix)
    }
    return value, origins


def _render_json(
    key: str | None,
    value: object,
    origins: cabc.Mapping[str, _ConfigOrigin],
) -> str:
    """Render the selected values and origins as deterministic JSON."""
    rendered_origins = {
        path: {
            "kind": origin.kind,
            "source_file": (
                str(origin.source_file) if origin.source_file is not None else None
            ),
            "cli_overridden": origin.cli_overridden,
        }
        for path, origin in sorted(origins.items())
    }
    if key is None:
        payload = {"values": value, "origins": rendered_origins}
    else:
        payload = {"key": key, "value": value, "origins": rendered_origins}
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _render_text(
    origins: cabc.Mapping[str, _ConfigOrigin],
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
        lines.append(f"{path} = {encoded_value}  # {annotation}")
    return "\n".join(lines) + "\n"


def _value_at_path(values: cabc.Mapping[str, object], dotted_path: str) -> object:
    """Return a previously validated dotted value."""
    value: object = values
    for component in dotted_path.split("."):
        mapping = typ.cast("cabc.Mapping[str, object]", value)
        value = mapping[component]
    return value
