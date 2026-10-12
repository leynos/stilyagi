"""Unit tests for `stilyagi check` operational metrics."""

import json
import typing as typ

import pytest
from stilyagi import cli, diagnostics
from syrupy.extensions.json import JSONSnapshotExtension

from tests.support.assertions import assert_with_context

if typ.TYPE_CHECKING:
    import pathlib

    from syrupy.assertion import SnapshotAssertion


class _DiagnosticMetricCase(typ.NamedTuple):
    """Expected command outcomes for one diagnostic-severity mix."""

    severities: tuple[diagnostics.Severity, ...]
    exit_code: int
    run_outcome: str
    errors: int
    warnings: int


def test_verbose_emits_bounded_metrics_to_stderr(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    snapshot: SnapshotAssertion,
) -> None:
    """Expose stable, low-cardinality command metrics outside normal output."""
    _write_markdown(tmp_path / "docs" / "notes.md", "Notes")
    python_source = tmp_path / "src" / "app.py"
    python_source.parent.mkdir(parents=True)
    python_source.write_text('"""Module docs."""\n', encoding="utf-8")
    (tmp_path / "src" / "lib.rs").write_text("//! Crate docs.\n", encoding="utf-8")
    (tmp_path / "src" / "metadata.json").write_text("{}\n", encoding="utf-8")
    linked_source = tmp_path / "linked-source"
    linked_source.symlink_to(tmp_path / "src", target_is_directory=True)
    monkeypatch.chdir(tmp_path)

    exit_code = cli.main(["check", ".", linked_source.name, "--verbose"])
    captured = capsys.readouterr()

    assert exit_code == 0, "expected a warning-free mixed-source run"
    assert captured.out == (
        "checked 3 files (2 skipped, 0 unreadable); 0 errors, 0 warnings\n"
    ), "normal command output remains the run summary on stdout"
    metric_lines = [
        line
        for line in captured.err.splitlines()
        if line.startswith("stilyagi check metrics: ")
    ]
    assert len(metric_lines) == 1, "verbose mode emits one metrics snapshot"
    metrics_payload = json.loads(
        metric_lines[0].removeprefix("stilyagi check metrics: ")
    )
    phase_counts = {
        phase: duration["count"]
        for phase, duration in metrics_payload[
            "stilyagi_check_phase_duration_seconds"
        ].items()
    }
    observed_contract = {
        "check_runs": metrics_payload["stilyagi_check_runs_total"],
        "checked_files": metrics_payload["stilyagi_check_files_total"],
        "diagnostics": metrics_payload["stilyagi_check_diagnostics_total"],
        "phase_counts": phase_counts,
        "python_documents": metrics_payload[
            "stilyagi_python_extraction_documents_total"
        ],
        "rust_documents": metrics_payload["stilyagi_rust_extraction_documents_total"],
        "skipped_candidates": metrics_payload[
            "stilyagi_check_skipped_candidates_total"
        ],
    }
    assert_with_context(
        observed_contract == snapshot(extension_class=JSONSnapshotExtension),
        "expected the bounded metrics contract to match its snapshot",
    )
    assert observed_contract["check_runs"]["success"] == 1, (
        "expected one successful check run"
    )
    assert observed_contract["checked_files"]["python"] == 1, (
        "expected one checked Python file"
    )
    assert observed_contract["checked_files"]["rust"] == 1, (
        "expected one checked Rust file"
    )
    assert observed_contract["phase_counts"]["discovery"] == 1, (
        "expected one discovery phase"
    )
    assert str(tmp_path) not in metric_lines[0], "metrics do not expose source paths"


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            _DiagnosticMetricCase((diagnostics.Severity.WARNING,), 0, "success", 0, 1),
            id="warning-only-run",
        ),
        pytest.param(
            _DiagnosticMetricCase(
                (
                    diagnostics.Severity.ERROR,
                    diagnostics.Severity.WARNING,
                ),
                1,
                "diagnostic_error",
                1,
                1,
            ),
            id="mixed-severity-failing-run",
        ),
    ],
)
def test_verbose_metrics_record_diagnostic_counts_by_severity(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    case: _DiagnosticMetricCase,
) -> None:
    """Count warning and error diagnostics with bounded severity labels."""
    _write_markdown(tmp_path / "notes.md", "Notes")
    monkeypatch.chdir(tmp_path)
    diagnostics_list = [
        diagnostics.Diagnostic(
            path="notes.md",
            code=f"STY{index:03}",
            message=f"Synthetic {severity.value}",
            severity=severity,
        )
        for index, severity in enumerate(case.severities, start=1)
    ]
    monkeypatch.setattr(
        "stilyagi.rules.registry.run_rules",
        lambda _document, _config: diagnostics_list,
    )

    actual_exit_code = cli.main(["check", ".", "--verbose", "--output-format", "json"])
    captured = capsys.readouterr()
    metric_line = next(
        line
        for line in captured.err.splitlines()
        if line.startswith("stilyagi check metrics: ")
    )
    metrics_payload = json.loads(metric_line.removeprefix("stilyagi check metrics: "))
    output_payload = json.loads(captured.out)

    assert actual_exit_code == case.exit_code, (
        "diagnostic severity preserves the exit outcome"
    )
    assert output_payload["summary"]["errors"] == case.errors, (
        "the renderer retains its error summary"
    )
    assert output_payload["summary"]["warnings"] == case.warnings, (
        "the renderer retains its warning summary"
    )
    assert metrics_payload["stilyagi_check_diagnostics_total"] == {
        "error": case.errors,
        "warning": case.warnings,
    }, "metrics expose diagnostic totals by fixed severity"
    assert metrics_payload["stilyagi_check_runs_total"][case.run_outcome] == 1, (
        "the check outcome agrees with the diagnostic severities"
    )


def test_verbose_metrics_record_unreadable_inputs_as_operational_failures(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Count a failed read without turning it into a normal diagnostic."""
    _write_markdown(tmp_path / "notes.md", "Notes")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "stilyagi.check_execution._read_source",
        lambda _check_input: None,
    )

    exit_code = cli.main(["check", ".", "--verbose"])
    captured = capsys.readouterr()
    metric_line = next(
        line
        for line in captured.err.splitlines()
        if line.startswith("stilyagi check metrics: ")
    )
    metrics_payload = json.loads(metric_line.removeprefix("stilyagi check metrics: "))

    assert exit_code == 2, "an unreadable input remains an operational failure"
    assert captured.out == (
        "checked 1 files (0 skipped, 1 unreadable); 0 errors, 0 warnings\n"
    ), "the normal summary reports the unreadable file"
    assert metrics_payload["stilyagi_check_runs_total"]["operational_error"] == 1, (
        "expected an operational-error check outcome"
    )
    assert metrics_payload["stilyagi_check_unreadable_files_total"] == 1, (
        "expected one unreadable file"
    )
    assert metrics_payload["stilyagi_check_operational_failures_total"]["read"] == 1, (
        "expected one read failure"
    )


def test_unexpected_discovery_failure_records_an_operational_outcome(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Count unexpected discovery exceptions before preserving their propagation."""

    def fail_discovery(*_args: object) -> typ.NoReturn:
        """Raise a deliberate unexpected discovery error."""
        raise RuntimeError("failure")

    monkeypatch.setattr(cli, "_discover_targets", fail_discovery)

    with pytest.raises(RuntimeError, match="failure"):
        cli.run_check(cli.CheckOptions(targets=(".",), verbose=True))

    captured = capsys.readouterr()
    metric_line = next(
        line
        for line in captured.err.splitlines()
        if line.startswith("stilyagi check metrics: ")
    )
    metrics_payload = json.loads(metric_line.removeprefix("stilyagi check metrics: "))

    assert not captured.out, "an unexpected discovery failure emits no run summary"
    assert metrics_payload["stilyagi_check_runs_total"]["operational_error"] == 1, (
        "expected an operational-error check outcome"
    )
    assert (
        metrics_payload["stilyagi_check_operational_failures_total"]["discovery"] == 1
    ), "expected one discovery failure"


def test_stdout_write_failure_is_measured_as_render_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Include stdout writing in the render phase and failure accounting."""
    _write_markdown(tmp_path / "notes.md", "Notes")
    monkeypatch.chdir(tmp_path)
    printed_lines: list[str] = []

    def fail_first_print(message: str, **_kwargs: object) -> None:
        """Fail the command output write, then retain the metrics snapshot."""
        if not printed_lines:
            printed_lines.append("stdout write attempted")
            raise OSError("closed")
        printed_lines.append(message)

    monkeypatch.setattr("builtins.print", fail_first_print)

    with pytest.raises(OSError, match="closed"):
        cli.main(["check", ".", "--verbose"])

    captured = capsys.readouterr()
    metric_line = next(
        line for line in printed_lines if line.startswith("stilyagi check metrics: ")
    )
    metrics_payload = json.loads(metric_line.removeprefix("stilyagi check metrics: "))

    assert not captured.out, "the failed stdout write emits no command output"
    assert metrics_payload["stilyagi_check_runs_total"]["operational_error"] == 1, (
        "expected an operational-error check outcome"
    )
    assert (
        metrics_payload["stilyagi_check_operational_failures_total"]["render"] == 1
    ), "expected one render failure"
    assert (
        metrics_payload["stilyagi_check_phase_duration_seconds"]["render"]["count"] == 1
    ), "expected the failed render phase to be timed"


def _write_markdown(path: pathlib.Path, title: str) -> None:
    """Write one tiny Markdown file for the metrics tests."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n", encoding="utf-8")
