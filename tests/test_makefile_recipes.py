"""Direct unit tests for Makefile recipe contracts."""

import dataclasses as dc
import pathlib
import tomllib

import pytest

from tests.support.assertions import assert_with_context

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]


@dc.dataclass(frozen=True, slots=True)
class MakefileTargetCase:
    """Expected recipe contract for one Makefile target."""

    target: str
    expected_header_fragments: tuple[str, ...]
    expected_recipe_fragments: tuple[str, ...]
    should_include_pytest: bool


def _collect_recipe_lines(lines: list[str], start: int) -> tuple[str, ...]:
    """Return the tab-indented recipe lines immediately after position *start*."""
    recipe: list[str] = []
    for recipe_line in lines[start + 1 :]:
        if recipe_line.startswith("\t"):
            recipe.append(recipe_line.strip())
            continue
        if recipe_line:
            break
    return tuple(recipe)


def _make_target(makefile: str, target: str) -> tuple[str, tuple[str, ...]]:
    """Return a Makefile target header and its recipe lines."""
    lines = makefile.splitlines()
    for line_number, line in enumerate(lines):
        if line.startswith(f"{target}:"):
            return line, _collect_recipe_lines(lines, line_number)
    msg = f"target {target!r} not found"
    raise AssertionError(msg)


@pytest.fixture(scope="module")
def makefile_text() -> str:
    """Return the repository Makefile as text, loaded once per module."""
    return (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            MakefileTargetCase(
                target="all",
                expected_header_fragments=("## Run commit gates",),
                expected_recipe_fragments=(
                    "$(MAKE) check-fmt",
                    "$(MAKE) typecheck",
                    "$(MAKE) lint",
                    "$(MAKE) test",
                    "$(MAKE) markdownlint",
                    "$(MAKE) nixie",
                ),
                should_include_pytest=False,
            ),
            id="all",
        ),
        pytest.param(
            MakefileTargetCase(
                target="lint",
                expected_header_fragments=("tools-lint",),
                expected_recipe_fragments=(
                    "$(UV_RUN) ruff check",
                    "$(INTERROGATE) $(INTERROGATE_FLAGS) $(INTERROGATE_TARGETS)",
                    "$(PYLINT) $(PYLINT_TARGETS)",
                    "$(DF12_PYLINT) $(PYLINT_TARGETS)",
                    "$(AMBRLEAKS) tests",
                    (
                        'RUSTDOCFLAGS="$(RUSTDOC_FLAGS)" '
                        "$(CARGO_BUILD_ENV) $(CARGO) doc $(DOC_FLAGS)"
                    ),
                    "$(CARGO_BUILD_ENV) $(CARGO) clippy $(CLIPPY_FLAGS)",
                    (
                        'RUSTFLAGS="$(RUST_FLAGS)" '
                        "$(CARGO_BUILD_ENV) $(WHITAKER) --all -- $(CARGO_FLAGS)"
                    ),
                ),
                should_include_pytest=False,
            ),
            id="lint",
        ),
        pytest.param(
            MakefileTargetCase(
                target="typecheck",
                expected_header_fragments=("build", "tools-check"),
                expected_recipe_fragments=(
                    (
                        'RUSTFLAGS="$(RUST_FLAGS)" '
                        "$(CARGO_BUILD_ENV) $(CARGO) check $(CARGO_FLAGS)"
                    ),
                    "$(UV_RUN) ty --version",
                    "$(UV_RUN) ty check",
                ),
                should_include_pytest=False,
            ),
            id="typecheck",
        ),
        pytest.param(
            MakefileTargetCase(
                target="test",
                expected_header_fragments=("build", "tools-lint"),
                expected_recipe_fragments=(
                    (
                        "$(CARGO) fmt --manifest-path $(WORKSPACE_MANIFEST) "
                        "--all -- --check"
                    ),
                    "$(CARGO_BUILD_ENV) $(CARGO) clippy $(CLIPPY_FLAGS)",
                    "nextest run --profile default --no-tests pass",
                    "cargo-nextest not installed, falling back to cargo test",
                    "$(CARGO) test $(TEST_FLAGS) $(BUILD_JOBS)",
                    "$(CARGO) test $(TEST_FLAGS) --doc $(BUILD_JOBS)",
                    '"$$VENV_PYTHON" -m pytest -v',
                ),
                should_include_pytest=True,
            ),
            id="test",
        ),
        pytest.param(
            MakefileTargetCase(
                target="test-ci",
                expected_header_fragments=("build", "tools-lint"),
                expected_recipe_fragments=(
                    "nextest run --profile ci --no-tests pass",
                    "$(CARGO) test $(TEST_FLAGS) --doc $(BUILD_JOBS)",
                ),
                should_include_pytest=False,
            ),
            id="test-ci",
        ),
    ],
)
def test_makefile_targets_run_expected_recipes(
    makefile_text: str,
    case: MakefileTargetCase,
) -> None:
    """Makefile targets must keep their reviewed recipe contracts."""
    header, recipe = _make_target(makefile_text, case.target)
    joined_recipe = "\n".join(recipe)

    for expected_header_fragment in case.expected_header_fragments:
        assert_with_context(
            expected_header_fragment in header,
            "expected expected_header_fragment in header",
        )
    for expected_recipe_fragment in case.expected_recipe_fragments:
        assert_with_context(
            expected_recipe_fragment in joined_recipe,
            "expected expected_recipe_fragment in joined_recipe",
        )
    if case.should_include_pytest:
        assert_with_context(
            '"$$VENV_PYTHON" -m pytest -v' in recipe,
            "expected '\"$$VENV_PYTHON\" -m pytest -v' in recipe",
        )
    else:
        assert "pytest" not in joined_recipe, "expected 'pytest' not in joined_recipe"


def test_lint_recipe_runs_df12_tools_before_rust_checks(makefile_text: str) -> None:
    """Keep the layered Python lint tools ahead of the Rust lint commands."""
    _header, recipe = _make_target(makefile_text, "lint")
    df12_pylint = "$(DF12_PYLINT) $(PYLINT_TARGETS)"
    ambrleaks = "$(AMBRLEAKS) tests"
    rustdoc = (
        'RUSTDOCFLAGS="$(RUSTDOC_FLAGS)" $(CARGO_BUILD_ENV) $(CARGO) doc $(DOC_FLAGS)'
    )

    assert_with_context(df12_pylint in recipe, "expected df12 Pylint lint command")
    assert_with_context(ambrleaks in recipe, "expected ambrleaks lint command")
    assert_with_context(rustdoc in recipe, "expected Rustdoc lint command")
    assert_with_context(
        recipe.index(df12_pylint) < recipe.index(ambrleaks) < recipe.index(rustdoc),
        "expected df12 Pylint and ambrleaks before Rustdoc",
    )


def test_df12_lint_tool_definitions_use_the_pinned_python_and_rules(
    makefile_text: str,
) -> None:
    """Pin the df12 tools, CPython version, targets, and enabled messages."""
    expected_messages = (
        "R9101,C9102,R9103,R9104,C9105,C9106,C9107,R9108,R9109,R9110,R9111,R9112,C9112"
    )
    expected_definitions = (
        "DF12_PYTHON_LINTS_REF ?= v0.2.0",
        (
            "DF12_PYTHON_LINTS = "
            "git+https://github.com/leynos/df12-python-lints.git@"
            "$(DF12_PYTHON_LINTS_REF)"
        ),
        "DF12_PYTHON ?= 3.14",
        f"DF12_PYLINT_MESSAGES = {expected_messages}",
        "DF12_PYLINT = $(UV_ENV) $(UV) run --python $(DF12_PYTHON) pylint",
        "--disable=all --load-plugins=df12_python_lints ",
        "--enable=$(DF12_PYLINT_MESSAGES)",
        "AMBRLEAKS = $(UV_ENV) $(UV) tool run --python $(DF12_PYTHON)",
        "--from '$(DF12_PYTHON_LINTS)' ambrleaks",
    )

    for expected_definition in expected_definitions:
        assert_with_context(
            expected_definition in makefile_text,
            "expected df12 lint tool definition",
        )


def test_df12_lint_project_configuration_uses_python_314() -> None:
    """Keep the project dependency and Pylint configuration at Python 3.14."""
    pyproject_path = REPOSITORY_ROOT / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    assert_with_context(
        "df12-python-lints @ "
        "git+https://github.com/leynos/df12-python-lints.git@v0.2.0"
        in pyproject["dependency-groups"]["dev"],
        "expected pinned df12 Python lints development dependency",
    )
    assert_with_context(
        pyproject["tool"]["pylint"]["main"]["py-version"] == "3.14",
        "expected Pylint Python version 3.14",
    )
    assert_with_context(
        pyproject["tool"]["pylint"]["messages control"]["disable"]
        == ["all", "syntax-error"],
        "expected focused Pylint message configuration",
    )
