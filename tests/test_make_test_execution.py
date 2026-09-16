"""What `make test` actually runs, watched rather than read.

`test_makefile_recipes` asserts the recipe's text, and text is not
execution: a phase can be present in the file and unreachable in the
run, behind a prerequisite that fails or a conditional that never takes
its branch. These two run the target with every tool pointed at a
cmd-mox shim and take the journal as the evidence.

The doctest phase is what this exists for. It was added to this recipe
rather than given a lane of its own, so the only thing making it run is
its position after `&&` in a recipe whose earlier half is a full test
suite, and the only thing propagating a failure is that same `&&`.
"""

import os
import pathlib
import shutil
import typing as typ

from cmd_mox import Invocation
from cmd_mox.command_runner import CommandRunner

from tests.support.assertions import assert_with_context

pytest_plugins = ("cmd_mox.pytest_plugin",)

if typ.TYPE_CHECKING:
    from cmd_mox import CmdMox

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _pytest_phase_indices(
    invocations: tuple[Invocation, ...],
) -> tuple[int | None, int | None]:
    """Return the journal indices of the unit and doctest pytest phases."""
    phases = [
        (index, "--doctest-modules" in invocation.args)
        for index, invocation in enumerate(invocations)
        if invocation.command == "python" and invocation.args[:2] == ["-m", "pytest"]
    ]
    unit = next((index for index, doctest in phases if not doctest), None)
    doctest = next((index for index, doctest in phases if doctest), None)
    return unit, doctest


def _make_test_invocation(
    cmd_mox: CmdMox, *, extra: tuple[str, ...] = ()
) -> Invocation:
    """Return the `make test` invocation with every tool pointed at a shim."""
    shim_dir = cmd_mox.environment.shim_dir
    assert_with_context(shim_dir is not None, "expected cmd-mox command shims")
    make = shutil.which("make")
    assert_with_context(make is not None, "expected make executable")
    return Invocation(
        command=typ.cast("str", make),
        args=[
            "--directory",
            str(REPOSITORY_ROOT),
            "--no-print-directory",
            f"UV={shim_dir / 'uv'}",
            f"CARGO={shim_dir / 'cargo'}",
            f"WHITAKER={shim_dir / 'whitaker'}",
            # The recipe resolves its interpreter in shell rather than
            # through a Make variable, so the resolution itself is what
            # has to be overridden to reach a shim.
            f"RESOLVE_VENV_PYTHON=VENV_PYTHON={shim_dir / 'python'}",
            *extra,
            "test",
        ],
        stdin="",
        env={},
    )


def test_the_test_recipe_runs_both_pytest_phases(
    cmd_mox: CmdMox,
    tmp_path: pathlib.Path,
) -> None:
    """Run `make test` hermetically and watch both phases execute.

    The recipe's text is asserted above, and text is not execution: a
    phase can be present in the file and unreachable in the run, behind
    a prerequisite that fails or a conditional that never takes its
    branch. Nothing here reads the Makefile; the journal is the
    evidence, and it records what the shell actually invoked.

    The doctest phase is the one this matters for. It was added to this
    recipe rather than to a lane of its own, so the only thing making it
    run is its position after `&&` in a recipe whose earlier half is a
    full test suite.
    """
    for command in ("uv", "cargo", "rustfmt", "whitaker", "python"):
        cmd_mox.spy(command).returns()

    response = CommandRunner(cmd_mox.environment).run(
        _make_test_invocation(cmd_mox),
        dict(os.environ, HOME=str(tmp_path / "home")),
    )
    assert_with_context(response.exit_code == 0, response.stderr)

    unit, doctest = _pytest_phase_indices(tuple(cmd_mox.journal))
    assert_with_context(unit is not None, "expected the unit pytest phase to run")
    assert_with_context(doctest is not None, "expected the doctest pytest phase to run")
    assert_with_context(
        typ.cast("int", unit) < typ.cast("int", doctest),
        "expected the unit phase before the doctest phase",
    )
    doctest_invocation = tuple(cmd_mox.journal)[typ.cast("int", doctest)]
    assert_with_context(
        doctest_invocation.args[-2:] == ["python/stilyagi", "tests/support"],
        f"expected the doctest phase to name both paths, got {doctest_invocation.args}",
    )


def test_a_failing_unit_phase_stops_the_recipe(
    cmd_mox: CmdMox,
    tmp_path: pathlib.Path,
) -> None:
    """A failing first phase must end the run, not be run past.

    The two phases are joined by `&&`, and that is the whole of the
    propagation: written as two recipe lines, or joined by `;`, a failed
    unit suite would be followed by a doctest run and the target's
    verdict would come from whichever finished last. Asserting that the
    recipe contains `&&` would not show it, because the `&&` could be
    there and the failure still swallowed by a preceding `-` or by a
    subshell.

    Only the unit phase is failed, by argument, because the same
    interpreter runs the smoke check that `build` performs first. A spy
    that failed every call would fail that instead and this test would
    pass for the wrong reason.
    """

    def fails_the_unit_phase(invocation: Invocation) -> tuple[str, str, int]:
        """Fail only the unit phase, leaving every other call alone."""
        is_unit_phase = (
            invocation.args[:2] == ["-m", "pytest"]
            and "--doctest-modules" not in invocation.args
        )
        return ("", "the unit suite failed", 1) if is_unit_phase else ("", "", 0)

    for command in ("uv", "cargo", "rustfmt", "whitaker"):
        cmd_mox.spy(command).returns()
    cmd_mox.spy("python").runs(fails_the_unit_phase)

    response = CommandRunner(cmd_mox.environment).run(
        _make_test_invocation(cmd_mox),
        dict(os.environ, HOME=str(tmp_path / "home")),
    )
    assert_with_context(
        response.exit_code != 0,
        "expected `make test` to fail when the unit suite fails",
    )

    unit, doctest = _pytest_phase_indices(tuple(cmd_mox.journal))
    assert_with_context(unit is not None, "expected the unit phase to have run")
    assert_with_context(
        doctest is None,
        "expected no doctest phase after a failing unit suite; the failure was "
        "run past rather than propagated",
    )
