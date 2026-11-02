"""Contracts for the df12 lint dependency and its project configuration."""

import pathlib
import tomllib

from tests.support.assertions import assert_with_context

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
DF12_PYTHON_LINTS_TAG = "v0.3.0"
DF12_PYTHON_LINTS_SOURCE = (
    f"git+https://github.com/leynos/df12-python-lints.git@{DF12_PYTHON_LINTS_TAG}"
)


def test_df12_lint_project_configuration_uses_python_314() -> None:
    """Keep the project dependency and Pylint configuration at Python 3.14."""
    pyproject_path = REPOSITORY_ROOT / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    assert_with_context(
        f"df12-python-lints @ {DF12_PYTHON_LINTS_SOURCE}"
        in pyproject["dependency-groups"]["dev"],
        "expected immutable df12 Python lints development dependency",
    )
    lock = tomllib.loads((REPOSITORY_ROOT / "uv.lock").read_text(encoding="utf-8"))
    df12_package = next(
        package for package in lock["package"] if package["name"] == "df12-python-lints"
    )
    assert_with_context(
        df12_package["source"]["git"].startswith(
            "https://github.com/leynos/df12-python-lints.git"
            f"?rev={DF12_PYTHON_LINTS_TAG}#"
        ),
        "expected lockfile to record the df12 Python lints release tag",
    )
    assert_with_context(
        pyproject["tool"]["pylint"]["main"]["py-version"] == "3.14",
        "expected Pylint Python version 3.14",
    )
    assert_with_context(
        pyproject["tool"]["pylint"]["messages control"]["disable"] == ["all"],
        "expected focused Pylint message configuration that still reports "
        "modules the interpreter cannot parse",
    )
