"""Validation tests for the config schema dataclasses.

Each public config dataclass validates its fields in ``__post_init__``. The
loaders normally reject malformed TOML before construction, so these tests
construct the dataclasses directly to exercise the validators themselves.
"""

import typing as typ

import pytest
from stilyagi import config

if typ.TYPE_CHECKING:
    import collections.abc as cabc


def _lint_config_with(field: str, value: object) -> config.LintConfig:
    """Build a ``LintConfig`` with one field forced to a malformed value."""
    kwargs = typ.cast("dict[str, typ.Any]", {field: value})
    return config.LintConfig(**kwargs)


def _stilyagi_config_with(field: str, value: object) -> config.StilyagiConfig:
    """Build a ``StilyagiConfig`` with one field forced to a malformed value."""
    kwargs = typ.cast("dict[str, typ.Any]", {field: value})
    return config.StilyagiConfig(**kwargs)


@pytest.mark.parametrize(
    ("build", "message"),
    [
        pytest.param(
            lambda: _lint_config_with("select", 5),
            "select must be a sequence of strings",
            id="non-sequence-select",
        ),
        pytest.param(
            lambda: _lint_config_with("select", ["MD", 1]),
            "select must contain only strings",
            id="non-string-select-item",
        ),
        pytest.param(
            lambda: _lint_config_with("per_file_ignores", 5),
            "per_file_ignores must be a mapping",
            id="non-mapping-per-file-ignores",
        ),
        pytest.param(
            lambda: _lint_config_with("per_file_ignores", {1: ["E"]}),
            "per_file_ignores keys must be strings",
            id="non-string-per-file-ignore-key",
        ),
        pytest.param(
            lambda: _lint_config_with("preview", "yes"),
            "preview has an unexpected type",
            id="non-bool-preview",
        ),
        pytest.param(
            lambda: _lint_config_with("reserved", 5),
            "reserved must be a mapping",
            id="non-mapping-reserved",
        ),
        pytest.param(
            lambda: _stilyagi_config_with("cache_dir", 5),
            "cache_dir must be a path or string",
            id="non-path-cache-dir",
        ),
        pytest.param(
            lambda: _stilyagi_config_with("line_length", value=True),
            "line_length must be an int",
            id="bool-line-length",
        ),
    ],
)
def test_malformed_config_fields_are_rejected(
    build: cabc.Callable[[], object],
    message: str,
) -> None:
    """A field outside its documented type fails with a named error."""
    with pytest.raises(TypeError, match=message):
        build()
