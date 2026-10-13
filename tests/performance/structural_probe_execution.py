"""Measure cold and warm structural extraction runs."""

import json
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- justified: invoking this test module in a fresh interpreter with validated arguments
import sys
import time
import typing as typ

from stilyagi import engine, model

from tests.performance import structural_probe as probe

if typ.TYPE_CHECKING:
    import pathlib


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

    fixtures = probe.discover_structural_fixtures(root)
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
    if mode == "cold":
        durations = tuple(_measure_cold_iteration(fixture) for _ in range(iterations))
    else:
        engine.extract_document(source, fixture.syntax)
        durations = tuple(
            measure_extraction(source, fixture.syntax) for _ in range(iterations)
        )
    return probe.ProbeRun(
        mode=mode,
        syntax=fixture.syntax,
        byte_count=fixture.path.stat().st_size,
        durations_ns=durations,
    )


def _measure_cold_iteration(fixture: probe.StructuralFixture) -> int:
    """Measure one syntax extraction in a fresh Python interpreter."""
    root = probe.repository_root()
    completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- justified: spawning own module under test with known sys.executable; no user input reaches argv
        [
            sys.executable,
            "-m",
            "tests.performance.structural_probe",
            "--child-run",
            "--source",
            str(fixture.path),
            "--syntax",
            fixture.syntax.value,
        ],
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
