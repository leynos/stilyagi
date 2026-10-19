"""Injected-dependency tests for the structural performance probe.

The probe reaches the clock, the process table, the platform, and the fixture
corpus through ports. These tests substitute each port, so the cold and warm
paths can be told apart, the child-process failure modes can be forced without
spawning an interpreter, and the report's environment section can be pinned.

Each test here would be impossible, or would need a real subprocess, if the
probe still called `time.perf_counter_ns`, `subprocess.run`, `platform`, or
`Path.read_text` directly. That is the evidence these tests exist to give.
"""

import json
import pathlib
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- justified: naming the failure a cold iteration must propagate
import typing as typ

import pytest
from stilyagi import model

from tests.performance import structural_probe as probe
from tests.performance import structural_probe_boundary as boundary
from tests.performance import structural_probe_execution as execution
from tests.performance.structural_probe_reporting import EnvironmentPayload
from tests.support.assertions import assert_with_context
from tests.support.structural_probe_stubs import (
    MARKDOWN_PATH,
    SYNTHETIC_SOURCE,
    StubRunner,
    markdown_fixture_request,
)

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]


class CountingClock:
    """A clock returning consecutive integers so durations are predictable.

    Examples
    --------
    >>> clock = CountingClock(first=10)
    >>> (clock(), clock())
    (10, 11)
    """

    def __init__(self, first: int = 0) -> None:
        """Start the tick sequence at ``first`` and count the reads."""
        self.ticks = iter(range(first, 1_000_000))
        self.calls = 0

    def __call__(self) -> int:
        """Return the next tick."""
        self.calls += 1
        return next(self.ticks)


def test_measure_run_cold_uses_subprocess_runner_only() -> None:
    """Measure the cold path through the injected runner and no clock.

    Cold timing belongs to the child process, so the parent must not read its
    own clock. A stub runner proves the child was launched, and a clock that
    fails loudly proves it was left alone.
    """
    runner = StubRunner()

    def forbidden_clock() -> int:
        """Fail the test if cold mode reads the parent clock."""
        msg = "cold mode must not read the parent clock"
        raise AssertionError(msg)

    dependencies = boundary.ProbeDependencies(
        clock=forbidden_clock,
        subprocess_runner=runner,
    )

    run = execution._measure_run(
        mode="cold",
        iterations=2,
        request=markdown_fixture_request(),
        dependencies=dependencies,
    )

    assert run.mode == "cold", "expected run.mode == 'cold'"
    assert run.durations_ns == (7, 7), "expected both iterations to report 7 ns"
    assert_with_context(
        len(runner.calls) == 2,
        "expected one child process per iteration",
    )


def test_measure_run_warm_uses_clock_only() -> None:
    """Measure the warm path through the injected clock and no subprocess.

    Warm timing happens in this interpreter, so the parent clock must be read
    twice per iteration, once before the extraction and once after, and no
    child may be spawned. Counting the reads is what stops a regression that
    drops a read, or adds an unaccounted one, from passing unnoticed.
    """
    clock = CountingClock()

    def forbidden_runner(*args: object, **kwargs: object) -> typ.NoReturn:
        """Fail the test if warm mode spawns a subprocess."""
        msg = "warm mode must not spawn a subprocess"
        raise AssertionError(msg)

    dependencies = boundary.ProbeDependencies(
        clock=clock,
        subprocess_runner=forbidden_runner,
    )

    run = execution._measure_run(
        mode="warm",
        iterations=3,
        request=markdown_fixture_request(),
        dependencies=dependencies,
    )

    assert run.mode == "warm", "expected run.mode == 'warm'"
    assert_with_context(
        run.durations_ns == (1, 1, 1),
        f"expected three unit durations, got {run.durations_ns}",
    )
    assert_with_context(
        clock.calls == 6,
        f"expected two clock reads per iteration, got {clock.calls} for 3 iterations",
    )


def test_measure_run_cold_and_warm_differ_under_stubs() -> None:
    """Prove the two modes reach for different dependencies.

    One dependency set drives both modes: the runner reports a fixed duration
    and the clock ticks by unit steps, so the measured values can only come
    from the mode's own port.
    """
    runner = StubRunner(stdout='{"duration_ns": 900}')
    dependencies = boundary.ProbeDependencies(
        clock=CountingClock(first=500),
        subprocess_runner=runner,
    )
    request = markdown_fixture_request()

    cold = execution._measure_run(
        mode="cold",
        iterations=1,
        request=request,
        dependencies=dependencies,
    )
    warm = execution._measure_run(
        mode="warm",
        iterations=1,
        request=request,
        dependencies=dependencies,
    )

    assert cold.durations_ns == (900,), "expected the child-reported duration"
    assert warm.durations_ns == (1,), "expected the clock-derived duration"
    assert_with_context(
        len(runner.calls) == 1,
        "expected the warm run to add no child process",
    )


def test_measure_cold_iteration_rejects_non_json_output() -> None:
    """Reject child output that is not JSON."""
    runner = StubRunner(stdout="not json at all")
    dependencies = boundary.ProbeDependencies(subprocess_runner=runner)

    with pytest.raises(json.JSONDecodeError):
        execution._measure_cold_iteration(
            markdown_fixture_request(),
            dependencies=dependencies,
        )


def test_measure_cold_iteration_rejects_non_integer_duration() -> None:
    """Reject a child-reported duration that is not an integer."""
    runner = StubRunner(stdout='{"duration_ns": "fast"}')
    dependencies = boundary.ProbeDependencies(subprocess_runner=runner)

    with pytest.raises(TypeError, match="did not return an integer duration"):
        execution._measure_cold_iteration(
            markdown_fixture_request(),
            dependencies=dependencies,
        )


def test_measure_cold_iteration_propagates_runner_failure() -> None:
    """Propagate a child-process failure rather than measuring it as zero."""
    failure = subprocess.CalledProcessError(1, ["python"], stderr="boom")
    runner = StubRunner(error=failure)
    dependencies = boundary.ProbeDependencies(subprocess_runner=runner)

    with pytest.raises(subprocess.CalledProcessError):
        execution._measure_cold_iteration(
            markdown_fixture_request(),
            dependencies=dependencies,
        )


def test_build_report_records_injected_environment() -> None:
    """Record the environment payload the injected provider returns."""
    pinned = EnvironmentPayload(platform="TestOS", python="3.99")

    def provider() -> EnvironmentPayload:
        """Report the pinned environment instead of the running one."""
        return pinned

    report = probe.build_report(
        corpus=boundary.read_probe_corpus(REPOSITORY_ROOT),
        runs=[],
        environment_provider=provider,
    )

    assert_with_context(
        report["environment"] == {"platform": "TestOS", "python": "3.99"},
        f"expected the injected environment, got {report['environment']}",
    )


def test_build_report_defaults_to_running_platform() -> None:
    """Record the running platform when no provider is injected."""
    report = probe.build_report(
        corpus=boundary.read_probe_corpus(REPOSITORY_ROOT),
        runs=[],
    )

    assert_with_context(
        report["environment"] == boundary.default_environment(),
        "expected the default provider to describe this machine",
    )


def test_measure_probe_uses_injected_source_without_file_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Measure supplied source text without reading any fixture.

    Every `Path.read_text` in the process is disabled, so the probe can only
    succeed by using the source text and byte count it was handed.
    """
    runner = StubRunner(stdout='{"duration_ns": 5}')

    def forbidden_read(*args: object, **kwargs: object) -> typ.NoReturn:
        """Fail the test if the probe reads any file."""
        msg = "measure_probe must not read files"
        raise AssertionError(msg)

    monkeypatch.setattr(pathlib.Path, "read_text", forbidden_read)

    dependencies = boundary.ProbeDependencies(subprocess_runner=runner)
    request = markdown_fixture_request()
    corpus = boundary.ProbeCorpus(root=REPOSITORY_ROOT, requests=(request,))

    report = execution.measure_probe(
        mode="cold",
        iterations=1,
        corpus=corpus,
        dependencies=dependencies,
    )

    assert report["probe"] == "structural-syntax", "expected the probe name"
    assert_with_context(
        report["corpus"]["total_bytes"] == request.byte_count,
        "expected the injected byte count in the corpus totals",
    )
    assert_with_context(
        report["runs"][0]["byte_count"] == request.byte_count,
        "expected the injected byte count in the run payload",
    )


def test_probe_corpus_reads_fixtures_once_up_front() -> None:
    """Read every fixture into memory when the corpus is built."""
    corpus = boundary.read_probe_corpus(REPOSITORY_ROOT)

    assert_with_context(
        [request.syntax.value for request in corpus.requests]
        == ["markdown", "python_docstring", "rust_doc_comment"],
        "expected one request per registered syntax",
    )
    assert_with_context(
        all(request.source for request in corpus.requests),
        "expected every request to carry its fixture text",
    )


def test_measure_probe_honours_caller_byte_count() -> None:
    """Report the caller's byte count rather than re-reading the fixture.

    The request claims one byte for a path whose file is far larger, so a probe
    that fell back to `Path.stat` would report the fixture's size instead.
    """
    runner = StubRunner(stdout='{"duration_ns": 5}')
    dependencies = boundary.ProbeDependencies(subprocess_runner=runner)
    request = boundary.ProbeRequest(
        path=MARKDOWN_PATH,
        source=SYNTHETIC_SOURCE,
        syntax=model.Syntax.MARKDOWN,
        byte_count=1,
    )
    corpus = boundary.ProbeCorpus(root=REPOSITORY_ROOT, requests=(request,))

    report = execution.measure_probe(
        mode="cold",
        iterations=1,
        corpus=corpus,
        dependencies=dependencies,
    )

    assert_with_context(
        report["corpus"]["total_bytes"] == 1,
        "expected the caller's byte count, not the fixture's size",
    )


def test_entry_point_measure_probe_takes_source_as_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accept a pre-read corpus and read no fixture from disk.

    The public entry point named in issue #17 must honour the caller's source
    text, not rediscover and read the fixtures. Every `Path.read_text` in the
    process is disabled, so the call can only succeed through the corpus.
    """
    runner = StubRunner(stdout='{"duration_ns": 5}')
    dependencies = boundary.ProbeDependencies(subprocess_runner=runner)

    def forbidden_read(*args: object, **kwargs: object) -> typ.NoReturn:
        """Fail the test if the entry point reads any file."""
        msg = "entry-point measure_probe must not read files"
        raise AssertionError(msg)

    monkeypatch.setattr(pathlib.Path, "read_text", forbidden_read)

    request = boundary.ProbeRequest(
        path=MARKDOWN_PATH,
        source=SYNTHETIC_SOURCE,
        syntax=model.Syntax.MARKDOWN,
        byte_count=len(SYNTHETIC_SOURCE.encode()),
    )
    corpus = boundary.ProbeCorpus(root=REPOSITORY_ROOT, requests=(request,))

    report = probe.measure_probe(
        mode="cold",
        iterations=1,
        corpus=corpus,
        dependencies=dependencies,
    )

    assert_with_context(
        report["corpus"]["total_bytes"] == request.byte_count,
        "expected the caller's byte count in the entry-point report",
    )
    assert_with_context(
        bool(runner.calls),
        "expected the injected runner to be used by the entry point",
    )
