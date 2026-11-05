"""Direct unit tests for Makefile recipe contracts."""

import os
import pathlib
import re
import shutil
import tomllib
import typing as typ

import pytest
from cmd_mox import Invocation
from cmd_mox.command_runner import CommandRunner

from tests.support.assertions import assert_with_context
from tests.support.makefile_target_cases import (
    MAKEFILE_TARGET_CASES,
    MakefileTargetCase,
)

pytest_plugins = ("cmd_mox.pytest_plugin",)

if typ.TYPE_CHECKING:
    from cmd_mox import CmdMox

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]


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


def _prerequisites(header: str) -> tuple[str, ...]:
    """Return a target header's prerequisites, without its help comment."""
    _, _, rest = header.partition(":")
    return tuple(rest.split("##", 1)[0].split())


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
        and invocation.args[-3:] == ["ambrleaks", "tests", "scripts"]
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


#: The reviewed cases, each keeping its own target name as the test id.
TARGET_CASES: typ.Final = [
    pytest.param(case, id=case.target) for case in MAKEFILE_TARGET_CASES
]


@pytest.mark.parametrize("case", TARGET_CASES)
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
        # One contiguous fragment, not two memberships. Separate checks
        # are satisfied by an intervening line: `true || \\` between them
        # makes the effective expression `(pytest && true) || doctest`,
        # so a failing suite is followed by a passing doctest run and the
        # failure never reaches the recipe's exit status. The two
        # commands and the `&&` that joins them have to be adjacent.
        expected_pytest_recipe = (
            '"$$VENV_PYTHON" -m pytest -v && \\\n'
            '"$$VENV_PYTHON" -m pytest -v --doctest-modules $(PY_DOCTEST_PATHS)'
        )
        assert_with_context(
            expected_pytest_recipe in "\n".join(recipe),
            "expected the pytest suite and doctest commands adjacent, joined by &&",
        )
    else:
        assert "pytest" not in joined_recipe, "expected 'pytest' not in joined_recipe"


def test_lint_composes_the_two_stages_and_whitaker_requires_clippy(
    makefile_text: str,
) -> None:
    """The prerequisite, not the recipe line order, sequences Whitaker."""
    lint_header, lint_recipe = _make_target(makefile_text, "lint")
    assert _prerequisites(lint_header) == ("lint-clippy", "lint-whitaker")
    assert not lint_recipe, "expected lint to hold no recipe of its own"

    whitaker_header, _ = _make_target(makefile_text, "lint-whitaker")
    assert _prerequisites(whitaker_header) == ("lint-clippy",)


def test_lint_recipe_runs_df12_tools_before_rust_checks(makefile_text: str) -> None:
    """Keep the layered Python lint tools ahead of the Rust lint commands."""
    _header, recipe = _make_target(makefile_text, "lint-clippy")
    df12_pylint = "$(DF12_PYLINT) $(PYLINT_TARGETS)"
    ambrleaks = "$(AMBRLEAKS) $(AMBRLEAKS_TARGETS)"
    rustdoc = (
        'RUSTDOCFLAGS="$(RUSTDOC_FLAGS)" RUSTFLAGS="$(RUST_FLAGS)" '
        "$(CARGO_BUILD_ENV) $(CARGO) doc $(DOC_FLAGS)"
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
    for command in ("uv", "cargo", "rustfmt", "whitaker", "cargo-binstall"):
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
        "AMBRLEAKS_TARGETS ?= tests scripts",
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


def test_focused_pylint_tool_definition_pins_the_runner(
    makefile_text: str,
) -> None:
    """Pin focused Pylint to one release on the CPython 3.14 source baseline."""
    expected_definitions = (
        "PYLINT_PYTHON ?= 3.14",
        "PYLINT_VERSION ?= 4.0.9",
        "PYLINT = $(UV_ENV) $(UV) tool run --managed-python --python $(PYLINT_PYTHON) ",
        "--from 'pylint==$(PYLINT_VERSION)' pylint --load-plugins=",
    )

    for expected_definition in expected_definitions:
        assert_with_context(
            expected_definition in makefile_text,
            f"missing focused Pylint definition {expected_definition!r}",
        )


def test_ty_typecheck_configuration_is_pinned(makefile_text: str) -> None:
    """Keep the type checker pinned and Python-3.14 aware."""
    pyproject_path = REPOSITORY_ROOT / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    assert_with_context(
        re.search(r"^TY_VERSION \?= \S+$", makefile_text, flags=re.MULTILINE)
        is not None,
        "expected ty to be pinned in the Makefile",
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
