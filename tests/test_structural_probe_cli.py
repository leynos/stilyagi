"""Command-line contract for the structural performance probe.

The probe has two modes. The maintainer-facing mode parses arguments, measures
every fixture, and writes a report. The child-run mode, launched by a cold
iteration, measures exactly one source text and prints its duration. Both are
exercised here through `main`, so the argument names and exit statuses that the
probe's own subprocess protocol depends on are pinned.
"""

import json
import pathlib
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- justified: constructing the CompletedProcess results a stub runner must return
import typing as typ

import pytest
from stilyagi import model

from tests.performance import structural_probe
from tests.performance import structural_probe_boundary as boundary
from tests.performance import structural_probe_execution as execution
from tests.support.assertions import assert_with_context

if typ.TYPE_CHECKING:
    import collections.abc as cabc

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
MARKDOWN_FIXTURE = REPOSITORY_ROOT / structural_probe.MARKDOWN_FIXTURE

#: Synthetic source that exists only in memory, so the protocol can be checked
#: without depending on the fixture's contents.
SYNTHETIC_SOURCE = "# Synthetic heading\n\nBody text.\n"


class RecordingRunner:
    """A subprocess runner that records its calls and returns canned output.

    Examples
    --------
    >>> RecordingRunner()(["python"]).returncode
    0
    """

    def __init__(self, stdout: str = '{"duration_ns": 7}') -> None:
        """Record the canned standard output the child reports."""
        self.stdout = stdout
        self.calls: list[tuple[list[str], dict[str, object]]] = []

    def __call__(
        self,
        argv: cabc.Sequence[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        """Record one invocation and return the canned result."""
        self.calls.append((list(argv), kwargs))
        return subprocess.CompletedProcess(list(argv), 0, stdout=self.stdout)


def markdown_fixture_request() -> boundary.ProbeRequest:
    """Return a Markdown request carrying synthetic, in-memory source.

    Returns
    -------
    boundary.ProbeRequest
        A request whose source never existed on disk.
    """
    return boundary.ProbeRequest(
        path=MARKDOWN_FIXTURE,
        source=SYNTHETIC_SOURCE,
        syntax=model.Syntax.MARKDOWN,
        byte_count=len(SYNTHETIC_SOURCE.encode()),
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
    runner = RecordingRunner()
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
        argv[argv.index(execution.SOURCE_FLAG) + 1] == str(MARKDOWN_FIXTURE),
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
    """
    runner = RecordingRunner()
    dependencies = boundary.ProbeDependencies(subprocess_runner=runner)

    execution._measure_cold_iteration(
        markdown_fixture_request(),
        dependencies=dependencies,
    )

    argv, _ = runner.calls[0]
    text_index = argv.index(execution.TEXT_FLAG) + 1
    assert_with_context(
        argv[text_index] == SYNTHETIC_SOURCE,
        f"expected the synthetic source on the command line, got {argv[text_index]!r}",
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
    """Reject an unrecognised --mode value."""
    parser = structural_probe._argument_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--mode", "unknown"])
    assert exc_info.value.code == 2, "expected exc_info.value.code == 2"


def test_main_child_run_emits_duration_ns(capsys: pytest.CaptureFixture[str]) -> None:
    """Emit a JSON payload with an integer duration_ns in child-run mode."""
    exit_code = structural_probe.main([
        "--child-run",
        "--source",
        str(MARKDOWN_FIXTURE),
    ])
    captured = capsys.readouterr()
    assert exit_code == 0, "expected exit_code == 0"
    payload = json.loads(captured.out)
    assert_with_context(
        isinstance(payload["duration_ns"], int),
        "expected isinstance(payload['duration_ns'], int)",
    )
    assert payload["duration_ns"] >= 0, "expected payload['duration_ns'] >= 0"


def test_child_run_reads_the_source_file_when_no_text_is_sent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Keep the documented manual reproduction working.

    The developers' guide tells a maintainer to reproduce a cold run by hand
    with `--child-run --source PATH`. That invocation sends no text, so the
    child must fall back to the file rather than measuring an empty string.
    """
    exit_code = structural_probe.main([
        "--child-run",
        "--source",
        str(MARKDOWN_FIXTURE),
        "--syntax",
        model.Syntax.MARKDOWN.value,
    ])

    assert exit_code == 0, f"expected exit_code == 0, got {exit_code}"
    payload = json.loads(capsys.readouterr().out)
    assert_with_context(
        isinstance(payload["duration_ns"], int),
        f"expected an integer duration_ns, got {payload['duration_ns']!r}",
    )
