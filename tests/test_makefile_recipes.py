"""Direct unit tests for Makefile recipe contracts."""

import dataclasses as dc
import os
import pathlib
import shutil
import tomllib
import typing as typ

import pytest
from cmd_mox import Invocation
from cmd_mox.command_runner import CommandRunner

from tests.support.assertions import assert_with_context

pytest_plugins = ("cmd_mox.pytest_plugin",)

if typ.TYPE_CHECKING:
    from cmd_mox import CmdMox

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
DF12_PYTHON_LINTS_COMMIT = "9c835f35b0f1690597ade799c9c6a30bc5922959"
DF12_PYTHON_LINTS_SOURCE = (
    f"git+https://github.com/leynos/df12-python-lints.git@{DF12_PYTHON_LINTS_COMMIT}"
)


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


def _df12_pylint_invocation_index(invocations: tuple[Invocation, ...]) -> int:
    """Return the df12 Pylint command's journal index."""
    return next(
        index
        for index, invocation in enumerate(invocations)
        if invocation.command == "uv"
        and invocation.args[:5] == ["run", "--group", "dev", "--python", "3.14"]
        and invocation.args[5] == "pylint"
    )


def _ambrleaks_invocation_index(invocations: tuple[Invocation, ...]) -> int:
    """Return the ambrleaks command's journal index."""
    return next(
        index
        for index, invocation in enumerate(invocations)
        if invocation.command == "uv"
        and invocation.args[:5] == ["run", "--group", "dev", "--python", "3.14"]
        and invocation.args[-2:] == ["ambrleaks", "tests"]
    )


def _cargo_lint_invocation_index(
    invocations: tuple[Invocation, ...], subcommand: str
) -> int:
    """Return a Cargo lint subcommand's journal index."""
    return next(
        index
        for index, invocation in enumerate(invocations)
        if invocation.command == "cargo" and invocation.args[0] == subcommand
    )


def _whitaker_invocation_index(invocations: tuple[Invocation, ...]) -> int:
    """Return the Whitaker command's journal index."""
    return next(
        index
        for index, invocation in enumerate(invocations)
        if invocation.command == "whitaker"
    )


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
                    "$(TY) --version",
                    "$(TY) check",
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
            f"{case.target}: missing header fragment {expected_header_fragment!r}",
        )
    for expected_recipe_fragment in case.expected_recipe_fragments:
        assert_with_context(
            expected_recipe_fragment in joined_recipe,
            f"{case.target}: missing recipe fragment {expected_recipe_fragment!r}",
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


def test_lint_recipe_executes_df12_tools_before_rust_checks(
    cmd_mox: CmdMox,
    tmp_path: pathlib.Path,
) -> None:
    """Run `make lint` hermetically and preserve its cross-language stage order."""
    for command in ("uv", "cargo", "rustfmt", "whitaker"):
        cmd_mox.spy(command).returns()

    shim_dir = cmd_mox.environment.shim_dir
    assert shim_dir is not None, "expected cmd-mox command shims"
    make = shutil.which("make")
    assert make is not None, "expected make executable"

    response = CommandRunner(cmd_mox.environment).run(
        Invocation(
            command=make,
            args=[
                "--directory",
                str(REPOSITORY_ROOT),
                "--no-print-directory",
                f"UV={shim_dir / 'uv'}",
                f"CARGO={shim_dir / 'cargo'}",
                f"WHITAKER={shim_dir / 'whitaker'}",
                "lint",
            ],
            stdin="",
            env={},
        ),
        dict(os.environ, HOME=str(tmp_path / "home")),
    )
    assert response.exit_code == 0, response.stderr

    invocations = tuple(cmd_mox.journal)
    df12_pylint = _df12_pylint_invocation_index(invocations)
    ambrleaks = _ambrleaks_invocation_index(invocations)
    rustdoc = _cargo_lint_invocation_index(invocations, "doc")
    clippy = _cargo_lint_invocation_index(invocations, "clippy")
    whitaker = _whitaker_invocation_index(invocations)

    assert df12_pylint < ambrleaks < min(rustdoc, clippy, whitaker), (
        "expected df12 Pylint and ambrleaks before every Rust lint stage"
    )


def test_df12_lint_tool_definitions_use_the_pinned_python_and_rules(
    makefile_text: str,
) -> None:
    """Pin the df12 tools, CPython version, targets, and enabled messages."""
    expected_messages = (
        "R9101,C9102,R9103,R9104,C9105,C9106,C9107,R9108,R9109,R9110,R9111,R9112,C9112"
    )
    expected_definitions = (
        "DF12_PYTHON ?= 3.14",
        f"DF12_PYLINT_MESSAGES = {expected_messages}",
        "DF12_PYLINT = $(UV_RUN) --python $(DF12_PYTHON) pylint",
        "--disable=all --load-plugins=df12_python_lints ",
        "--enable=$(DF12_PYLINT_MESSAGES)",
        "AMBRLEAKS = $(UV_RUN) --python $(DF12_PYTHON) ambrleaks",
    )

    for expected_definition in expected_definitions:
        assert_with_context(
            expected_definition in makefile_text,
            "expected df12 lint tool definition",
        )
    assert_with_context(
        "DF12_PYTHON_LINTS" not in makefile_text,
        "expected df12 source to be owned only by the locked development environment",
    )


def test_pypy_pylint_tool_definition_preserves_the_pinned_plugin_runner(
    makefile_text: str,
) -> None:
    """Keep the PyPy Pylint command pinned and plugin-compatible."""
    expected_definitions = (
        "PYLINT_PYTHON ?= pypy",
        "PYLINT_PYPY_SHIM_REF ?= 726d09f968b4d729ee4b29c71fc732e744854f3b",
        "PYLINT_PYPY_SHIM = git+https://github.com/leynos/pylint-pypy-shim.git@$(PYLINT_PYPY_SHIM_REF)",
        "PYLINT = $(UV_ENV) $(UV) tool run --python $(PYLINT_PYTHON) ",
        "--from '$(PYLINT_PYPY_SHIM)' pylint-pypy --load-plugins=",
    )

    for expected_definition in expected_definitions:
        assert_with_context(
            expected_definition in makefile_text,
            f"missing PyPy Pylint definition {expected_definition!r}",
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
        df12_package["source"]["git"]
        == "https://github.com/leynos/df12-python-lints.git"
        f"?rev={DF12_PYTHON_LINTS_COMMIT}#{DF12_PYTHON_LINTS_COMMIT}",
        "expected lockfile to record the immutable df12 Python lints commit",
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


def test_ty_typecheck_configuration_is_pinned(makefile_text: str) -> None:
    """Keep the type checker versioned and Python-3.14 aware."""
    pyproject_path = REPOSITORY_ROOT / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    assert_with_context(
        "TY_VERSION ?= 0.0.72" in makefile_text,
        "expected the latest ty release to be pinned in the Makefile",
    )
    assert_with_context(
        "TY = env $(UV_ENV) $(UV) tool run ty@$(TY_VERSION)" in makefile_text,
        "expected typecheck to use the pinned ty command",
    )
    assert_with_context(
        "pyright" not in pyproject["dependency-groups"]["dev"],
        "expected Pyright to be absent from the development dependency group",
    )
    assert_with_context(
        pyproject["tool"]["ty"]["environment"]["python-version"] == "3.14",
        "expected ty Python version 3.14",
    )
