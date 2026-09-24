"""What `make test-doc` actually runs, watched rather than read.

CI runs `make test-doc` instead of `make test`, because the coverage run
already executes the Rust and Python suites. `test_suite_runs_once`
asserts the recipe's text and its prerequisites. These tests run the target
with every tool pointed at a cmd-mox shim and take the journal as the
evidence: both doctest passes run, neither unit suite does, and a failing
Rust doctest ends the target before the Python pass.
"""

import os
import typing as typ

from cmd_mox.command_runner import CommandRunner

from tests.support.assertions import assert_with_context
from tests.test_make_test_execution import _make_test_invocation

pytest_plugins = ("cmd_mox.pytest_plugin",)

if typ.TYPE_CHECKING:
    import pathlib

    from cmd_mox import CmdMox, Invocation


def _is_rust_doctest(invocation: Invocation) -> bool:
    """Report whether a call is the Rust doctest pass."""
    return (
        invocation.command == "cargo"
        and "test" in invocation.args
        and "--doc" in invocation.args
    )


def _is_rust_suite(invocation: Invocation) -> bool:
    """Report whether a call runs the Rust suite rather than its doctests."""
    is_nextest = invocation.command == "cargo" and "nextest" in invocation.args
    is_plain_test = (
        invocation.command == "cargo"
        and "test" in invocation.args
        and "--doc" not in invocation.args
    )
    return is_nextest or is_plain_test


def _is_pytest(invocation: Invocation, *, doctest: bool) -> bool:
    """Report whether a call is a pytest pass, doctest or unit as asked."""
    return (
        invocation.command == "python"
        and invocation.args[:2] == ["-m", "pytest"]
        and ("--doctest-modules" in invocation.args) is doctest
    )


def _run_test_doc(cmd_mox: CmdMox, tmp_path: pathlib.Path) -> int:
    """Run `make test-doc` against the shims and return its exit code."""
    response = CommandRunner(cmd_mox.environment).run(
        _make_test_invocation(cmd_mox, target="test-doc"),
        dict(os.environ, HOME=str(tmp_path / "home")),
    )
    return response.exit_code


class TestMakeTestDocExecution:
    """What `make test-doc` invokes, and how a failure propagates."""

    def test_runs_both_doctest_passes_and_no_unit_suite(
        self,
        cmd_mox: CmdMox,
        tmp_path: pathlib.Path,
    ) -> None:
        """Both doctest passes run, in order, and neither unit suite does."""
        for command in ("uv", "cargo", "rustfmt", "whitaker", "python"):
            cmd_mox.spy(command).returns()

        assert_with_context(
            _run_test_doc(cmd_mox, tmp_path) == 0, "expected make test-doc to pass"
        )

        journal = tuple(cmd_mox.journal)
        rust = [i for i, call in enumerate(journal) if _is_rust_doctest(call)]
        python = [i for i, call in enumerate(journal) if _is_pytest(call, doctest=True)]
        assert_with_context(len(rust) == 1, "expected one Rust doctest pass")
        assert_with_context(len(python) == 1, "expected one Python doctest pass")
        assert_with_context(rust[0] < python[0], "expected Rust doctests first")
        assert_with_context(
            not any(_is_rust_suite(call) for call in journal),
            "expected no Rust unit suite in make test-doc",
        )
        assert_with_context(
            not any(_is_pytest(call, doctest=False) for call in journal),
            "expected no Python unit suite in make test-doc",
        )

    def test_a_failing_rust_doctest_stops_the_target(
        self,
        cmd_mox: CmdMox,
        tmp_path: pathlib.Path,
    ) -> None:
        """A failed Rust doctest pass ends the run before the Python pass.

        Only the doctest call fails, by argument, because `build` runs cargo
        first. A spy that failed every call would fail the build step instead
        and this test would pass for the wrong reason.
        """

        def fails_the_rust_doctests(invocation: Invocation) -> tuple[str, str, int]:
            """Fail only the Rust doctest pass."""
            failed = ("", "a doctest failed", 1)
            return failed if _is_rust_doctest(invocation) else ("", "", 0)

        for command in ("uv", "rustfmt", "whitaker", "python"):
            cmd_mox.spy(command).returns()
        cmd_mox.spy("cargo").runs(fails_the_rust_doctests)

        assert_with_context(
            _run_test_doc(cmd_mox, tmp_path) != 0,
            "expected make test-doc to fail when a Rust doctest fails",
        )
        assert_with_context(
            not any(_is_pytest(call, doctest=True) for call in cmd_mox.journal),
            "expected no Python doctest pass after a failed Rust doctest",
        )

    def test_a_failing_python_doctest_fails_the_target(
        self,
        cmd_mox: CmdMox,
        tmp_path: pathlib.Path,
    ) -> None:
        """A failed Python doctest pass is the target's verdict."""

        def fails_the_python_doctests(invocation: Invocation) -> tuple[str, str, int]:
            """Fail only the Python doctest pass."""
            failed = ("", "a doctest failed", 1)
            return failed if _is_pytest(invocation, doctest=True) else ("", "", 0)

        for command in ("uv", "cargo", "rustfmt", "whitaker"):
            cmd_mox.spy(command).returns()
        cmd_mox.spy("python").runs(fails_the_python_doctests)

        assert_with_context(
            _run_test_doc(cmd_mox, tmp_path) != 0,
            "expected make test-doc to fail when a Python doctest fails",
        )
