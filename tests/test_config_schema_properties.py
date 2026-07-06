"""Property tests for same-directory config discovery."""

from __future__ import annotations

import typing as typ

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from stilyagi import config

if typ.TYPE_CHECKING:
    import pathlib


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.tuples(st.booleans(), st.booleans(), st.booleans()))
def test_same_directory_precedence_is_deterministic(
    tmp_path: pathlib.Path,
    present: tuple[bool, bool, bool],
) -> None:
    """Always return the highest-precedence file that exists."""
    filenames = (".stilyagi.toml", "stilyagi.toml", "pyproject.toml")
    precedence = (".stilyagi.toml", "stilyagi.toml", "pyproject.toml")
    case_dir = tmp_path / "".join("1" if exists else "0" for exists in present)
    case_dir.mkdir()

    for filename, should_exist in zip(filenames, present, strict=True):
        if not should_exist:
            continue
        content = (
            '[tool.stilyagi]\ncache-dir = ".pyproject"\n'
            if filename == "pyproject.toml"
            else 'cache-dir = ".stilyagi"\n'
        )
        (case_dir / filename).write_text(content, encoding="utf-8")

    discovered = config.discover_same_directory_config(case_dir)

    expected_name = next(
        (name for name, exists in zip(precedence, present, strict=True) if exists), None
    )
    if expected_name is None:
        assert discovered is None
    else:
        assert discovered is not None
        assert discovered.path.name == expected_name
