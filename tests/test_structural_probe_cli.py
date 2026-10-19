"""Command-line contract for the structural performance probe.

The probe has two modes. The maintainer-facing mode parses arguments, measures
every fixture, and writes a report. The child-run mode, launched by a cold
iteration, measures exactly one source text and prints its duration. Both are
exercised here through `main`, so the argument names and exit statuses that the
probe's own subprocess protocol depends on are pinned.
"""

import json
import pathlib

import pytest
from stilyagi import model

from tests.performance import structural_probe
from tests.performance import structural_probe_boundary as boundary
from tests.performance import structural_probe_execution as execution
from tests.support.assertions import assert_with_context
from tests.support.structural_probe_stubs import (
    MARKDOWN_PATH,
    SYNTHETIC_SOURCE,
    StubRunner,
    markdown_fixture_request,
)


def test_argument_parser_defaults() -> None:
    """Verify default argument values for the structural probe CLI."""
    parser = structural_probe._argument_parser()
    args = parser.parse_args([])
    assert args.mode == "both", "expected args.mode == 'both'"
    assert_with_context(
        args.iterations == structural_probe.DEFAULT_ITERATIONS,
        "expected args.iterations == structural_probe.DEFAULT...",
    )
    assert_with_context(
        args.output == pathlib.Path("build/performance/structural-baseline.json"),
        "expected args.output == pathlib.Path('build/performa...",
    )
    assert args.child_run is False, "expected args.child_run is False"


def test_argument_parser_accepts_source_text() -> None:
    """Accept the hidden text argument the cold protocol sends.

    The text is suppressed from help because it is an internal protocol, not a
    maintainer option. It must still parse, or every cold iteration fails.
    """
    parser = structural_probe._argument_parser()
    args = parser.parse_args(["--child-run", "--text", "# Heading"])

    assert_with_context(
        args.text == "# Heading",
        f"expected the text argument to parse, got {args.text!r}",
    )


def test_measure_cold_iteration_builds_child_argv() -> None:
    """Invoke the child interpreter with the child-run and source arguments."""
    runner = StubRunner()
    dependencies = boundary.ProbeDependencies(subprocess_runner=runner)

    execution._measure_cold_iteration(
        markdown_fixture_request(),
        dependencies=dependencies,
    )

    argv, kwargs = runner.calls[0]
    assert_with_context(
        execution.CHILD_RUN_FLAG in argv,
        f"expected {execution.CHILD_RUN_FLAG} in {argv}",
    )
    assert_with_context(
        execution.SOURCE_FLAG in argv,
        f"expected {execution.SOURCE_FLAG} in {argv}",
    )
    assert_with_context(
        argv[argv.index(execution.SOURCE_FLAG) + 1] == str(MARKDOWN_PATH),
        "expected the fixture path to follow the source flag",
    )
    assert_with_context(
        argv[-1] == model.Syntax.MARKDOWN.value,
        "expected the syntax value to be the final argument",
    )
    assert_with_context(
        kwargs.get("check") is True,
        "expected the child to be run with check=True",
    )


def test_measure_cold_iteration_transmits_the_request_source() -> None:
    """Send the request's own text, not merely the path to it.

    A request may carry source that differs from the file at ``path``. If the
    child reopened the path it would measure the wrong text, so the argv must
    carry the source verbatim and the child must treat it as authoritative.

    The text is bound to its flag as one ``--text=<value>`` element, so the
    child's `argparse` cannot mistake a leading hyphen for an option. A
    separate element would also put the text one position later, so this
    pins the binding as well as the payload.
    """
    runner = StubRunner()
    dependencies = boundary.ProbeDependencies(subprocess_runner=runner)

    execution._measure_cold_iteration(
        markdown_fixture_request(),
        dependencies=dependencies,
    )

    argv, _ = runner.calls[0]
    text_prefix = f"{execution.TEXT_FLAG}="
    text_element = next(
        (argument for argument in argv if argument.startswith(text_prefix)),
        None,
    )
    assert_with_context(
        text_element is not None,
        f"expected a {text_prefix}<source> argument in {argv}",
    )
    assert_with_context(
        text_element.removeprefix(text_prefix) == SYNTHETIC_SOURCE,
        f"expected the synthetic source on the command line, got {text_element!r}",
    )


@pytest.mark.parametrize(
    "source",
    ["-item", "--", "--syntax", "-x=y"],
    ids=["list-item", "double-dash", "option-prefix", "short-option-with-equals"],
)
def test_child_run_accepts_source_text_that_looks_like_an_option(
    capsys: pytest.CaptureFixture[str],
    source: str,
) -> None:
    """Accept transmitted text that `argparse` would read as an option.

    Markdown may legitimately begin with a hyphen, and the cold protocol
    cannot escape it for the child. Binding the text to its flag as one
    ``--text=<value>`` argument is what keeps it a value; sent separately,
    every one of these sources makes the child exit 2 with "expected one
    argument" before it measures anything.
    """
    exit_code = structural_probe.main([
        "--child-run",
        "--source",
        str(MARKDOWN_PATH),
        f"{execution.TEXT_FLAG}={source}",
        "--syntax",
        model.Syntax.MARKDOWN.value,
    ])

    assert exit_code == 0, f"expected exit_code == 0, got {exit_code}"
    payload = json.loads(capsys.readouterr().out)
    assert_with_context(
        isinstance(payload["duration_ns"], int) and payload["duration_ns"] >= 0,
        f"expected a non-negative integer duration_ns, got {payload['duration_ns']!r}",
    )


def test_child_run_prefers_transmitted_text_over_the_file(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Measure the transmitted text even when the path names another file.

    The path names a file that cannot be read, so a child that reopened it
    would fail. Succeeding proves the transmitted text was used instead.
    """
    code = structural_probe.main(
        [
            "--child-run",
            "--source",
            str(pathlib.Path("/nonexistent/fixture.md")),
            "--text",
            SYNTHETIC_SOURCE,
            "--syntax",
            model.Syntax.MARKDOWN.value,
        ],
    )

    assert code == 0, f"expected exit code 0, got {code}"
    payload = json.loads(capsys.readouterr().out)
    assert_with_context(
        isinstance(payload["duration_ns"], int),
        f"expected an integer duration_ns, got {payload['duration_ns']!r}",
    )


def test_argument_parser_rejects_unknown_mode() -> None:
    """Reject an unrecognized --mode value."""
    parser = structural_probe._argument_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--mode", "unknown"])
    assert exc_info.value.code == 2, "expected exc_info.value.code == 2"


@pytest.mark.parametrize(
    "extra_args",
    [[], ["--syntax", model.Syntax.MARKDOWN.value]],
    ids=["default-syntax", "explicit-syntax"],
)
def test_child_run_reads_the_source_file_when_no_text_is_sent(
    capsys: pytest.CaptureFixture[str],
    extra_args: list[str],
) -> None:
    """Read the named file when the parent sends no text.

    The developers' guide tells a maintainer to reproduce a cold run by hand
    with `--child-run --source PATH`. That invocation sends no text, so the
    child must fall back to the file rather than measuring an empty string.
    The syntax argument is exercised both omitted and named, because the
    default has to stay the Markdown syntax the manual command relies on.
    """
    exit_code = structural_probe.main([
        "--child-run",
        "--source",
        str(MARKDOWN_PATH),
        *extra_args,
    ])

    assert exit_code == 0, f"expected exit_code == 0, got {exit_code}"
    payload = json.loads(capsys.readouterr().out)
    assert_with_context(
        isinstance(payload["duration_ns"], int) and payload["duration_ns"] >= 0,
        f"expected a non-negative integer duration_ns, got {payload['duration_ns']!r}",
    )
