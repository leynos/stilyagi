"""Measure cold and warm structural extraction runs.

Each measurement reaches the outside world through a port supplied by
:class:`~tests.performance.structural_probe_boundary.ProbeDependencies`, so a
test can drive the cold path with a stub runner and the warm path with a stub
clock. Source text arrives in the request rather than being read here, so a
test can measure text that was never written to disk.
"""

import json
import sys

from stilyagi import engine, model

from tests.performance import structural_probe as probe

#: Argument that switches a child process into single-extraction mode.
CHILD_RUN_FLAG = "--child-run"
#: Argument naming the file to measure, used only to locate the source text.
SOURCE_FLAG = "--source"
#: Argument carrying the source text itself, so the child measures what the
#: request carries rather than reopening the path.
TEXT_FLAG = "--text"


def measure_probe(
    *,
    mode: str,
    iterations: int,
    corpus: probe.ProbeCorpus,
    dependencies: probe.ProbeDependencies = probe.DEFAULT_DEPENDENCIES,
) -> probe.ReportPayload:
    """Measure the requested structural probe mode and return a report.

    Parameters
    ----------
    mode:
        Either ``"cold"``, ``"warm"``, or ``"both"``.
    iterations:
        Measurements per mode. Must be at least 1.
    corpus:
        Fixtures already read into memory, with the root they came from.
    dependencies:
        The clock, subprocess runner, and environment provider to measure
        through.

    Returns
    -------
    probe.ReportPayload
        The structural probe report covering every fixture and requested mode.

    Raises
    ------
    ValueError
        ``iterations`` is below 1, or ``mode`` is not a known probe mode.

    Examples
    --------
    >>> report = measure_probe(
    ...     mode="warm",
    ...     iterations=1,
    ...     corpus=probe.read_probe_corpus(probe.repository_root()),
    ... )
    >>> report["probe"]
    'structural-syntax'
    """
    if iterations < 1:
        msg = "iterations must be at least 1"
        raise ValueError(msg)

    modes = _modes(mode)
    runs = [
        _measure_run(
            mode=run_mode,
            iterations=iterations,
            request=request,
            dependencies=dependencies,
        )
        for request in corpus.requests
        for run_mode in modes
    ]
    return probe.build_report(
        corpus=corpus,
        runs=runs,
        environment_provider=dependencies.environment_provider,
    )


def measure_extraction(
    source: str,
    syntax: model.Syntax,
    *,
    clock: probe.ClockFn = probe.DEFAULT_DEPENDENCIES.clock,
) -> int:
    """Measure one structural extraction in nanoseconds.

    Parameters
    ----------
    source:
        Source text to extract.
    syntax:
        The extractor syntax applied to ``source``.
    clock:
        Reads the nanosecond counter. Defaults to the production monotonic
        clock; a test substitutes a counter it controls.

    Returns
    -------
    int
        Elapsed nanoseconds across the extraction.

    Examples
    --------
    >>> measure_extraction("# Title", model.Syntax.MARKDOWN) >= 0
    True
    """
    started_ns = clock()
    engine.extract_document(source, syntax)
    return clock() - started_ns


def _modes(mode: str) -> tuple[probe.ProbeMode, ...]:
    """Return the concrete run modes requested by the command line."""
    match mode:
        case "cold":
            return ("cold",)
        case "warm":
            return ("warm",)
        case "both":
            return ("cold", "warm")
        case _:
            msg = f"unknown probe mode: {mode}"
            raise ValueError(msg)


def _measure_run(
    *,
    mode: probe.ProbeMode,
    iterations: int,
    request: probe.ProbeRequest,
    dependencies: probe.ProbeDependencies = probe.DEFAULT_DEPENDENCIES,
) -> probe.ProbeRun:
    """Measure one concrete structural probe mode for one request.

    Cold mode measures each iteration in a fresh interpreter through the
    injected subprocess runner and never reads the clock here; the child process
    reports its own elapsed time. Warm mode primes the extractor once, then
    times each iteration through the injected clock in this interpreter.

    Parameters
    ----------
    mode:
        The run mode to measure.
    iterations:
        Measured iterations to perform.
    request:
        Source text, syntax, and byte count to measure.
    dependencies:
        The clock and subprocess runner to measure through.

    Returns
    -------
    probe.ProbeRun
        The mode, syntax, byte count, and measured nanosecond durations.
    """
    if mode == "cold":
        durations = tuple(
            _measure_cold_iteration(request, dependencies=dependencies)
            for _ in range(iterations)
        )
    else:
        engine.extract_document(request.source, request.syntax)
        durations = tuple(
            measure_extraction(
                request.source,
                request.syntax,
                clock=dependencies.clock,
            )
            for _ in range(iterations)
        )
    return probe.ProbeRun(
        mode=mode,
        syntax=request.syntax,
        byte_count=request.byte_count,
        durations_ns=durations,
    )


def _measure_cold_iteration(
    request: probe.ProbeRequest,
    *,
    dependencies: probe.ProbeDependencies = probe.DEFAULT_DEPENDENCIES,
) -> int:
    """Measure one syntax extraction in a fresh Python interpreter.

    Parameters
    ----------
    request:
        The fixture to measure. Its path, syntax, and source text all reach the
        child, so an in-memory request is measured as its own text.
    dependencies:
        Supplies the subprocess runner.

    Returns
    -------
    int
        Elapsed nanoseconds reported by the child process.

    Raises
    ------
    TypeError
        The child process reported a non-integer duration. A non-zero child
        exit and unparseable child output propagate from the injected runner
        and from ``json.loads`` respectively.
    """
    root = probe.repository_root()
    completed = dependencies.subprocess_runner(
        _child_command(request),
        check=True,
        cwd=root,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    duration_ns = payload["duration_ns"]
    if not isinstance(duration_ns, int):
        msg = "child probe did not return an integer duration"
        raise TypeError(msg)
    return duration_ns


def _child_command(request: probe.ProbeRequest) -> list[str]:
    """Return the argv that measures one request in a fresh interpreter.

    The source text travels on the command line rather than being reopened by
    the child. ``path`` still travels so error messages name the fixture, and
    so an operator can reproduce a cold run by hand.

    The argv is built as a list, so the text is passed as one argument whatever
    it contains; no shell re-parses it. A repository fixture is small enough for
    the platform's argument limit, and a request that is not would fail loudly
    with ``OSError`` from the runner rather than silently measuring the file.

    Returns
    -------
    list[str]
        Arguments for the child interpreter, including the source text.
    """
    return [
        sys.executable,
        "-m",
        "tests.performance.structural_probe",
        CHILD_RUN_FLAG,
        SOURCE_FLAG,
        str(request.path),
        TEXT_FLAG,
        request.source,
        "--syntax",
        request.syntax.value,
    ]
