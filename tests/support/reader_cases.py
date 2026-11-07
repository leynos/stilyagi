"""Shared assertions for the lint-policy reader failure cases.

The TOML and Makefile readers and the Cargo metadata reader live in different
modules, but their failure contract is the same: a `ReadingError` naming the
reader and the path it was given. These helpers keep that assertion in one
place so a new reader case cannot weaken it by accident.
"""

import typing as typ

import pytest

if typ.TYPE_CHECKING:
    import pathlib

    from tests.support.errors import ReadingError


def write_text(path: pathlib.Path, text: str) -> pathlib.Path:
    """Write `text` and return the path, for use as a reader argument."""
    path.write_text(text, encoding="utf-8")
    return path


def assert_names_reader_and_path(
    raised: pytest.ExceptionInfo[ReadingError], path: pathlib.Path
) -> None:
    """Assert the failure names the lint-policy reader and the requested path."""
    if raised.value.reader != "lint_policy":
        pytest.fail(f"expected the lint_policy reader, got {raised.value.reader!r}")
    if raised.value.path != str(path):
        pytest.fail(
            f"expected the requested path {str(path)!r}, got {raised.value.path!r}"
        )
