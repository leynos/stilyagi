"""Unit and behaviour tests for the structural performance probe."""
import json
import pathlib
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- justified: using subprocess in test to run external benchmark tool; validated input/control
import sys
import typing as typ

from pytest_bdd import given, scenario, then, when
from syrupy.extensions.json import JSONSnapshotExtension
import pytest

from stilyagi import model
from tests.performance import structural_probe
from tests.support.assertions import assert_with_context

if typ.TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion


class ProbeState(typ.TypedDict):
    """Scenario state for structural probe BDD steps."""

    output_path: pathlib.Path
    completed: subprocess.CompletedProcess[str] | typ.Literal[False]


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
MARKDOWN_FIXTURE = REPOSITORY_ROOT / (
    "tests/fixtures/corpus/markdown/valid/heading-table-link-suppression.md"
)
STRUCTURAL_FIXTURES = (
    structural_probe.StructuralFixture(MARKDOWN_FIXTURE, model.Syntax.MARKDOWN),
    structural_probe.StructuralFixture(
        REPOSITORY_ROOT
        / "tests"
        / "fixtures"
        / "corpus"
        / "python"
        / "valid"
        / "module-class-function-docstrings.py",
        model.Syntax.PYTHON_DOCSTRING,
    ),
    structural_probe.StructuralFixture(
        REPOSITORY_ROOT
        / "tests"
        / "fixtures"
        / "corpus"
        / "rust"
        / "valid"
        / "item-doc-comments.rs",
        model.Syntax.RUST_DOC_COMMENT,
    ),
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
    probe_state["completed"] = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- justified: spawning own module under test with known sys.executable; no user input reaches argv
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
    assert_with_context(
        isinstance(completed, subprocess.CompletedProcess),
        "expected CompletedProcess after probe run",
    )
    output_path = probe_state["output_path"]

    assert completed.returncode == 0, completed.stderr
    assert output_path.is_file(), "expected output_path.is_file()"

    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert_with_context(
        report["probe"] == "structural-syntax",
        "expected report['probe'] == 'structural-syntax'",
    )
    assert_with_context(
        [(run["syntax"], run["mode"]) for run in report["runs"]]
        == [
            ("markdown", "cold"),
            ("markdown", "warm"),
            ("python_docstring", "cold"),
            ("python_docstring", "warm"),
            ("rust_doc_comment", "cold"),
            ("rust_doc_comment", "warm"),
        ],
        "expected one cold and warm run for every syntax",
    )
    assert_with_context(
        all(run["iterations"] == 1 for run in report["runs"]),
        "expected all((run['iterations'] == 1 for run in repo...",
    )
    assert_with_context(
        all(len(run["durations_ns"]) == 1 for run in report["runs"]),
        "expected all((len(run['durations_ns']) == 1 for run ...",
    )


def test_discovers_markdown_structural_fixture() -> None:
    """Discover the single Markdown fixture used for baseline probes."""
    fixtures = structural_probe.discover_structural_fixtures(REPOSITORY_ROOT)

    assert fixtures == STRUCTURAL_FIXTURES, "expected fixtures == STRUCTURAL_FIXTURES"


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
    assert_with_context(
        (structural_probe.normalise_repository_path(path, REPOSITORY_ROOT) == expected),
        "expected structural_probe.normalise_repository_path(...",
    )


def test_rejects_paths_outside_repository(tmp_path: pathlib.Path) -> None:
    """Reject non-repository paths instead of leaking machine-local paths."""
    with pytest.raises(ValueError, match="is not under repository root"):
        structural_probe.normalise_repository_path(tmp_path, REPOSITORY_ROOT)


def test_summarises_odd_and_even_duration_sets() -> None:
    """Summarise duration lists with deterministic integer medians."""
    assert_with_context(
        structural_probe.summarise_durations([9, 1, 5])
        == {
            "min": 1,
            "median": 5,
            "max": 9,
        },
        "expected structural_probe.summarise_durations([9, 1,...",
    )
    assert_with_context(
        structural_probe.summarise_durations([10, 2, 4, 20])
        == {
            "min": 2,
            "median": 7,
            "max": 20,
        },
        "expected structural_probe.summarise_durations([10, 2...",
    )


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
        fixtures=STRUCTURAL_FIXTURES,
        runs=[
            structural_probe.ProbeRun(
                mode="cold",
                syntax=model.Syntax.MARKDOWN,
                byte_count=10,
                durations_ns=(5, 9, 1),
            ),
            structural_probe.ProbeRun(
                mode="warm",
                syntax=model.Syntax.MARKDOWN,
                byte_count=10,
                durations_ns=(2, 4, 10),
            ),
        ],
    )

    assert report["schema_version"] == 1, "expected report['schema_version'] == 1"
    assert_with_context(
        report["probe"] == "structural-syntax",
        "expected report['probe'] == 'structural-syntax'",
    )
    assert_with_context(
        report["entrypoint"] == "stilyagi.engine.extract_document",
        "expected report['entrypoint'] == 'stilyagi.engine.ex...",
    )
    assert_with_context(
        list(report["corpus"])
        == ["fixture_paths", "file_count", "total_bytes", "per_syntax"],
        "expected report['corpus'] to include syntax and byte totals",
    )
    assert_with_context(
        [run["summary_ns"]["median"] for run in report["runs"]] == [5, 4],
        "expected [run['summary_ns']['median'] for run in rep...",
    )


def test_redacted_report_matches_json_snapshot(
    snapshot: SnapshotAssertion,
) -> None:
    """Pin the stable redacted report schema without timing noise."""
    report = structural_probe.build_report(
        repository_root=REPOSITORY_ROOT,
        fixtures=STRUCTURAL_FIXTURES,
        runs=[
            structural_probe.ProbeRun(
                mode="cold",
                syntax=model.Syntax.MARKDOWN,
                byte_count=10,
                durations_ns=(5, 9, 1),
            ),
            structural_probe.ProbeRun(
                mode="warm",
                syntax=model.Syntax.MARKDOWN,
                byte_count=10,
                durations_ns=(2, 4, 10),
            ),
        ],
    )

    assert_with_context(
        structural_probe.redact_report(report)
        == snapshot(
            extension_class=JSONSnapshotExtension,
        ),
        "expected structural_probe.redact_report(report) == s...",
    )


def test_redacted_report_contains_no_integer_timings() -> None:
    """Confirm that redaction removes all integer timing values."""
    report = structural_probe.build_report(
        repository_root=REPOSITORY_ROOT,
        fixtures=STRUCTURAL_FIXTURES,
        runs=[
            structural_probe.ProbeRun(
                mode="cold",
                syntax=model.Syntax.MARKDOWN,
                byte_count=10,
                durations_ns=(5, 9, 1),
            ),
            structural_probe.ProbeRun(
                mode="warm",
                syntax=model.Syntax.MARKDOWN,
                byte_count=10,
                durations_ns=(2, 4, 10),
            ),
        ],
    )
    redacted = structural_probe.redact_report(report)
    for run in redacted["runs"]:
        assert_with_context(
            run["durations_ns"] == "<redacted>",
            "expected run['durations_ns'] == '<redacted>'",
        )
        assert_with_context(
            all(v == "<redacted>" for v in run["summary_ns"].values()),
            "expected all((v == '<redacted>' for v in run['summar...",
        )
    assert_with_context(
        redacted["environment"]["platform"] == "<redacted>",
        "expected redacted['environment']['platform'] == '<re...",
    )
    assert_with_context(
        redacted["environment"]["python"] == "<redacted>",
        "expected redacted['environment']['python'] == '<reda...",
    )


def test_measure_probe_rejects_non_positive_iterations() -> None:
    """Reject iteration counts below 1 with a clear ValueError."""
    with pytest.raises(ValueError, match="iterations must be at least 1"):
        structural_probe.measure_probe(
            mode="warm",
            iterations=0,
            root=REPOSITORY_ROOT,
        )


def test_discover_structural_fixtures_raises_when_missing(
    tmp_path: pathlib.Path,
) -> None:
    """Raise FileNotFoundError when the fixture is absent from the root."""
    with pytest.raises(FileNotFoundError, match="structural fixture is missing"):
        structural_probe.discover_structural_fixtures(tmp_path)


def test_write_report_creates_parent_directories(
    tmp_path: pathlib.Path,
) -> None:
    """Create missing parent directories and write a valid JSON file."""
    output_path = tmp_path / "nested" / "dir" / "report.json"
    report = structural_probe.build_report(
        repository_root=REPOSITORY_ROOT,
        fixtures=STRUCTURAL_FIXTURES,
        runs=[
            structural_probe.ProbeRun(
                mode="warm",
                syntax=model.Syntax.MARKDOWN,
                byte_count=10,
                durations_ns=(1, 2, 3),
            ),
        ],
    )
    structural_probe.write_report(report, output_path)
    assert output_path.is_file(), "expected output_path.is_file()"
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["schema_version"] == 1, "expected written['schema_version'] == 1"


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
