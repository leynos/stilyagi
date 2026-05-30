"""Unit and behaviour tests for the structural performance probe."""

import json
import pathlib
import subprocess  # noqa: S404 -- justified: using subprocess in test to run external benchmark tool; validated input/control
import sys
import typing as typ

import pytest
from pytest_bdd import given, scenario, then, when
from syrupy.extensions.json import JSONSnapshotExtension

from tests.performance import structural_probe

if typ.TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion


class ProbeState(typ.TypedDict):
    """Scenario state for structural probe BDD steps."""

    output_path: pathlib.Path
    completed: subprocess.CompletedProcess[str] | typ.Literal[False]


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
MARKDOWN_FIXTURE = (
    REPOSITORY_ROOT
    / "tests"
    / "fixtures"
    / "corpus"
    / "markdown"
    / "valid"
    / "heading-table-link-suppression.md"
)


@scenario(
    "../features/stilyagi_structural_performance_probe.feature",
    "Maintainers can record cold and warm structural timings",
)
def test_maintainers_can_record_structural_timings() -> None:
    """Run the structural performance probe BDD scenario."""


@pytest.fixture
def probe_state(tmp_path: pathlib.Path) -> ProbeState:
    """Return scenario state for structural probe BDD steps."""
    return ProbeState(
        output_path=tmp_path / "structural-baseline.json",
        completed=False,
    )


@given("the shared Markdown structural fixture is available")
def shared_markdown_structural_fixture_is_available() -> None:
    """Assert that the fixture used by the probe exists."""
    assert MARKDOWN_FIXTURE.is_file(), f"expected fixture at {MARKDOWN_FIXTURE}"


@when("I run the structural performance probe for cold and warm modes")
def run_structural_performance_probe(probe_state: ProbeState) -> None:
    """Run the maintainer-facing probe module as a subprocess."""
    output_path = probe_state["output_path"]
    probe_state["completed"] = subprocess.run(  # noqa: S603 -- justified: spawning own module under test with known sys.executable; no user input reaches argv
        [
            sys.executable,
            "-m",
            "tests.performance.structural_probe",
            "--mode",
            "both",
            "--iterations",
            "1",
            "--output",
            str(output_path),
        ],
        check=False,
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
    )


@then("the probe writes a JSON report with cold and warm runs")
def probe_writes_json_report_with_cold_and_warm_runs(
    probe_state: ProbeState,
) -> None:
    """Assert the scenario-visible probe result."""
    completed = probe_state["completed"]
    assert isinstance(completed, subprocess.CompletedProcess), (
        "expected CompletedProcess after probe run"
    )
    output_path = probe_state["output_path"]

    assert completed.returncode == 0, completed.stderr
    assert output_path.is_file()

    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["probe"] == "structural-markdown"
    assert [run["mode"] for run in report["runs"]] == ["cold", "warm"]
    assert all(run["iterations"] == 1 for run in report["runs"])
    assert all(len(run["durations_ns"]) == 1 for run in report["runs"])


def test_discovers_markdown_structural_fixture() -> None:
    """Discover the single Markdown fixture used for baseline probes."""
    fixtures = structural_probe.discover_structural_fixtures(REPOSITORY_ROOT)

    assert fixtures == (MARKDOWN_FIXTURE,)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (
            MARKDOWN_FIXTURE,
            "tests/fixtures/corpus/markdown/valid/heading-table-link-suppression.md",
        ),
        (REPOSITORY_ROOT / "build" / "performance", "build/performance"),
    ],
)
def test_normalises_repository_paths(path: pathlib.Path, expected: str) -> None:
    """Normalise repository-local paths for portable JSON reports."""
    assert structural_probe.normalise_repository_path(path, REPOSITORY_ROOT) == expected


def test_rejects_paths_outside_repository(tmp_path: pathlib.Path) -> None:
    """Reject non-repository paths instead of leaking machine-local paths."""
    with pytest.raises(ValueError, match="is not under repository root"):
        structural_probe.normalise_repository_path(tmp_path, REPOSITORY_ROOT)


def test_summarises_odd_and_even_duration_sets() -> None:
    """Summarise duration lists with deterministic integer medians."""
    assert structural_probe.summarise_durations([9, 1, 5]) == {
        "min": 1,
        "median": 5,
        "max": 9,
    }
    assert structural_probe.summarise_durations([10, 2, 4, 20]) == {
        "min": 2,
        "median": 7,
        "max": 20,
    }


def test_summarise_durations_rejects_empty_sequence() -> None:
    """Reject empty duration sequences with a clear failure."""
    with pytest.raises(
        ValueError,
        match="cannot summarise an empty duration sequence",
    ):
        structural_probe.summarise_durations([])


def test_builds_structural_report_shape() -> None:
    """Build the stable report shape from measured run data."""
    report = structural_probe.build_report(
        repository_root=REPOSITORY_ROOT,
        fixture_paths=(MARKDOWN_FIXTURE,),
        runs=[
            structural_probe.ProbeRun(mode="cold", durations_ns=(5, 9, 1)),
            structural_probe.ProbeRun(mode="warm", durations_ns=(2, 4, 10)),
        ],
    )

    assert report["schema_version"] == 1
    assert report["probe"] == "structural-markdown"
    assert report["entrypoint"] == "stilyagi.engine.extract_document"
    assert report["corpus"] == {
        "fixture_paths": [
            "tests/fixtures/corpus/markdown/valid/heading-table-link-suppression.md",
        ],
        "file_count": 1,
    }
    assert [run["summary_ns"]["median"] for run in report["runs"]] == [5, 4]


def test_redacted_report_matches_json_snapshot(
    snapshot: SnapshotAssertion,
) -> None:
    """Pin the stable redacted report schema without timing noise."""
    report = structural_probe.build_report(
        repository_root=REPOSITORY_ROOT,
        fixture_paths=(MARKDOWN_FIXTURE,),
        runs=[
            structural_probe.ProbeRun(mode="cold", durations_ns=(5, 9, 1)),
            structural_probe.ProbeRun(mode="warm", durations_ns=(2, 4, 10)),
        ],
    )

    assert structural_probe.redact_report(report) == snapshot(
        extension_class=JSONSnapshotExtension,
    )
