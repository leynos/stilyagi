"""Measure cold and warm structural extraction runs."""

import json
import logging
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- justified: invoking this test module in a fresh interpreter with validated arguments
import sys
import time
import typing as typ

from stilyagi import engine, model

from tests.performance import structural_probe as probe

if typ.TYPE_CHECKING:
    import pathlib

logger = logging.getLogger(__name__)
# Without a handler, logging falls back to its last-resort stderr handler and
# duplicates the traceback of a failure we re-raise. A NullHandler keeps an
# unconfigured probe quiet while records still propagate to a configured root.
logger.addHandler(logging.NullHandler())


def measure_probe(
    *,
    mode: str,
    iterations: int,
    root: pathlib.Path,
) -> probe.ReportPayload:
    """Measure the requested structural probe mode and return a report."""
    if iterations < 1:
        msg = "iterations must be at least 1"
        raise ValueError(msg)

    fixtures = _discover_fixtures(root)
    runs = [
        _measure_run(
            run_mode,
            iterations,
            fixture.path.read_text(encoding="utf-8"),
            fixture,
        )
        for fixture in fixtures
        for run_mode in _modes(mode)
    ]
    return probe.build_report(repository_root=root, fixtures=fixtures, runs=runs)


def _discover_fixtures(root: pathlib.Path) -> tuple[probe.StructuralFixture, ...]:
    """Discover fixtures at the command boundary and log each resolved path."""
    try:
        fixtures = probe.discover_structural_fixtures(root)
    except FileNotFoundError:
        # Issue #19 asks for operational visibility of a probe that cannot start.
        logger.exception("structural fixture discovery failed")
        raise
    for fixture in fixtures:
        logger.debug("fixture discovered: path=%s", fixture.path)
    return fixtures


def measure_extraction(source: str, syntax: model.Syntax) -> int:
    """Measure one structural extraction in nanoseconds."""
    started_ns = time.perf_counter_ns()
    engine.extract_document(source, syntax)
    return time.perf_counter_ns() - started_ns


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
    mode: probe.ProbeMode,
    iterations: int,
    source: str,
    fixture: probe.StructuralFixture,
) -> probe.ProbeRun:
    """Measure one concrete structural probe mode for one source syntax."""
    logger.debug(
        "measurement run starting: mode=%s iterations=%d",
        mode,
        iterations,
    )
    if mode == "cold":
        durations = tuple(
            _measure_cold_iteration(fixture, mode, iteration_index)
            for iteration_index in range(iterations)
        )
    else:
        engine.extract_document(source, fixture.syntax)
        durations = tuple(
            measure_extraction(source, fixture.syntax) for _ in range(iterations)
        )
    logger.debug(
        "measurement run finished: mode=%s iterations=%d",
        mode,
        iterations,
    )
    return probe.ProbeRun(
        mode=mode,
        syntax=fixture.syntax,
        byte_count=fixture.path.stat().st_size,
        durations_ns=durations,
    )


def _measure_cold_iteration(
    fixture: probe.StructuralFixture,
    mode: probe.ProbeMode,
    iteration_index: int,
) -> int:
    """Measure one syntax extraction in a fresh Python interpreter."""
    root = probe.repository_root()
    command = [
        sys.executable,
        "-m",
        "tests.performance.structural_probe",
        "--child-run",
        "--source",
        str(fixture.path),
        "--syntax",
        fixture.syntax.value,
    ]
    logger.debug(
        "cold iteration subprocess: mode=%s iteration=%d command=%s",
        mode,
        iteration_index,
        command,
    )
    try:
        completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- justified: spawning own module under test with known sys.executable; no user input reaches argv
            command,
            check=True,
            cwd=root,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        # Issue #19 requires the child stderr at ERROR level, and
        # CalledProcessError.__str__ omits it, so log before re-raising.
        logger.exception(
            "cold iteration subprocess failed: mode=%s iteration=%d stderr=%s",
            mode,
            iteration_index,
            exc.stderr,
        )
        raise
    payload = json.loads(completed.stdout)
    duration_ns = payload["duration_ns"]
    if not isinstance(duration_ns, int):
        msg = "child probe did not return an integer duration"
        raise TypeError(msg)
    return duration_ns
