"""Unit tests for `stilyagi check` operational metrics."""

import json
import typing as typ

import pytest
from stilyagi import cli, config, diagnostics, engine
from syrupy.extensions.json import JSONSnapshotExtension

from tests.support.assertions import assert_with_context
from tests.support.check_metric_fixtures import (
    metric_lines,
    metric_payload,
    recorded_metrics,
    write_markdown,
)

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


def _run_verbose_mixed_source_check(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, str]:
    """Run a fixed mixed-source check with one skipped symlink target."""
    write_markdown(tmp_path / "docs" / "notes.md", "Notes")
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
    return exit_code, captured.out, captured.err


def test_verbose_mixed_source_check_keeps_summary_on_stdout(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Keep the summary on stdout and emit one path-free metrics record."""
    result = _run_verbose_mixed_source_check(tmp_path, monkeypatch, capsys)
    exit_code, stdout, stderr = result

    assert exit_code == 0, "expected a warning-free mixed-source run"
    assert stdout == (
        "checked 3 files (2 skipped, 0 unreadable); 0 errors, 0 warnings\n"
    ), "normal command output remains the run summary on stdout"
    records = metric_lines(stderr)
    assert len(records) == 1, "verbose mode emits one metrics snapshot"
    assert str(tmp_path) not in records[0], "metrics do not expose source paths"


def test_verbose_emits_bounded_metrics_to_stderr(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    snapshot: SnapshotAssertion,
) -> None:
    """Expose stable, low-cardinality command metrics outside normal output."""
    result = _run_verbose_mixed_source_check(tmp_path, monkeypatch, capsys)
    _exit_code, _stdout, stderr = result

    records = metric_lines(stderr)
    assert len(records) == 1, "verbose mode emits one metrics snapshot"
    metrics_payload = metric_payload(records)
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
    assert observed_contract["phase_counts"]["total"] == 1, (
        "expected one whole-run duration observation"
    )


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
    write_markdown(tmp_path / "notes.md", "Notes")
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
        lambda _request: diagnostics_list,
    )

    actual_exit_code = cli.main(["check", ".", "--verbose", "--output-format", "json"])
    captured = capsys.readouterr()
    metrics_payload = recorded_metrics(captured.err)
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
    assert (
        metrics_payload["stilyagi_check_phase_duration_seconds"]["total"]["count"] == 1
    ), "each diagnostic run records one total duration"


def test_verbose_metrics_record_unreadable_inputs_as_operational_failures(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Count a failed read without turning it into a normal diagnostic."""
    write_markdown(tmp_path / "notes.md", "Notes")
    monkeypatch.chdir(tmp_path)
    # The stub stands in for a read that reported its own failure, so it takes
    # the run whose reporter the real function would have called. Returning
    # `None` is the signal `check_one_file` acts on, and that is the branch
    # under test; driving a real unreadable file instead would test the read
    # boundary, which `tests/test_check_read_failures.py` already owns.
    monkeypatch.setattr(
        "stilyagi.check_execution._read_source",
        lambda _check_input, _run: None,
    )

    exit_code = cli.main(["check", ".", "--verbose"])
    captured = capsys.readouterr()
    metrics_payload = recorded_metrics(captured.err)

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
    assert (
        metrics_payload["stilyagi_check_phase_duration_seconds"]["total"]["count"] == 1
    ), "an unreadable run records one total duration"


def test_verbose_metrics_record_total_duration_for_config_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Measure a handled configuration failure before rendering metrics."""

    def fail_discovery(*_args: object) -> typ.NoReturn:
        """Raise a configuration error before discovery returns inputs."""
        raise config.InvalidConfigError(tmp_path / "stilyagi.toml", "rules", "invalid")

    monkeypatch.setattr(cli, "discover_targets", fail_discovery)

    exit_code = cli.run_check(cli.CheckOptions(targets=(".",), verbose=True))
    captured = capsys.readouterr()
    metrics_payload = recorded_metrics(captured.err)

    assert exit_code == 2, "a configuration failure remains an operational error"
    assert (
        metrics_payload["stilyagi_check_phase_duration_seconds"]["total"]["count"] == 1
    ), "an early operational return records one total duration"


def test_unexpected_discovery_failure_records_an_operational_outcome(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Count unexpected discovery exceptions before preserving their propagation."""

    def fail_discovery(*_args: object) -> typ.NoReturn:
        """Raise a deliberate unexpected discovery error."""
        raise RuntimeError("failure")

    monkeypatch.setattr(cli, "discover_targets", fail_discovery)

    with pytest.raises(RuntimeError, match="failure"):
        cli.run_check(cli.CheckOptions(targets=(".",), verbose=True))

    captured = capsys.readouterr()
    metrics_payload = recorded_metrics(captured.err)

    assert not captured.out, "an unexpected discovery failure emits no run summary"
    assert metrics_payload["stilyagi_check_runs_total"]["operational_error"] == 1, (
        "expected an operational-error check outcome"
    )
    assert (
        metrics_payload["stilyagi_check_operational_failures_total"]["discovery"] == 1
    ), "expected one discovery failure"
    assert (
        metrics_payload["stilyagi_check_phase_duration_seconds"]["total"]["count"] == 1
    ), "a propagated discovery exception records one total duration"


@pytest.mark.parametrize("failure_phase", ["extract", "rules"])
def test_unexpected_file_check_failures_record_one_total_duration(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure_phase: str,
) -> None:
    """Finalize once when extraction or rules failures propagate to the CLI."""
    write_markdown(tmp_path / "notes.md", "Notes")
    monkeypatch.chdir(tmp_path)
    if failure_phase == "extract":
        monkeypatch.setattr(engine, "extract_document", _raise_check_failure)
    else:
        monkeypatch.setattr("stilyagi.rules.registry.run_rules", _raise_check_failure)

    with pytest.raises(_UnexpectedCheckFailureError):
        cli.run_check(cli.CheckOptions(targets=(".",), verbose=True))

    captured = capsys.readouterr()
    metrics_payload = recorded_metrics(captured.err)

    assert metrics_payload["stilyagi_check_runs_total"]["operational_error"] == 1, (
        "a propagated file-check failure records one operational outcome"
    )
    assert (
        metrics_payload["stilyagi_check_phase_duration_seconds"]["total"]["count"] == 1
    ), "a propagated file-check failure records exactly one total duration"


def test_stdout_write_failure_is_measured_as_render_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Include stdout writing in the render phase and failure accounting."""
    write_markdown(tmp_path / "notes.md", "Notes")
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
    metrics_payload = metric_payload(printed_lines)

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
    assert (
        metrics_payload["stilyagi_check_phase_duration_seconds"]["total"]["count"] == 1
    ), "a propagated render exception records one total duration"


def _raise_check_failure(*_args: object) -> typ.NoReturn:
    """Raise one unexpected error from the selected file-check boundary."""
    raise _UnexpectedCheckFailureError


class _UnexpectedCheckFailureError(Exception):
    """Identify a deliberate unexpected file-check error in the metrics tests."""
