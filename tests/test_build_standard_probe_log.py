"""Hold the probe log's two parsing modes to their different contracts.

A live run polls the log while a probe may be mid-write, so one torn trailing
line is expected and skipped. A completed run must account for every line: a
line that does not parse there means a record was lost, and silently dropping
it would let an assertion over the surviving records pass for the wrong
reason. The strict mode is therefore the default, and these cases pin both
modes plus the shapes that are rejected in either.
"""

import json
import typing as typ

import pytest

from tests.support.errors import ReadingError
from tests.support.probe_log import READER, identity, read_records

if typ.TYPE_CHECKING:
    import pathlib

START: typ.Final = {
    "program": "probe-cargo",
    "args": ["clippy", "--workspace"],
    "env": {"RUSTFLAGS": "-D warnings", "RUSTDOCFLAGS": None},
    "phase": "start",
}
DONE: typ.Final = {**START, "phase": "done"}


def _write(log: pathlib.Path, *lines: str) -> pathlib.Path:
    """Write raw log lines and return the path."""
    log.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return log


def _reject(log: pathlib.Path, *, live: bool) -> None:
    """Assert that reading the log is a finding naming it."""
    with pytest.raises(ReadingError) as raised:
        read_records(log, live=live)
    assert raised.value.reader == READER, f"expected reader {READER!r}"
    assert raised.value.path == str(log), f"expected path {log}"


def test_a_log_that_does_not_exist_holds_no_records(tmp_path: pathlib.Path) -> None:
    """A run whose probes never fired has an empty record, not a failure."""
    assert not read_records(tmp_path / "absent.log"), "an absent log must be empty"


def test_records_keep_their_order_and_their_phase(tmp_path: pathlib.Path) -> None:
    """Each line becomes one invocation, in log order, with its phase."""
    log = _write(tmp_path / "probe.log", json.dumps(START), json.dumps(DONE))

    first, second = read_records(log)

    assert identity(first) == "probe-cargo clippy --workspace", identity(first)
    assert first.rustflags == "-D warnings", first.rustflags
    assert (first.phase, second.phase) == ("start", "done"), (
        first.phase,
        second.phase,
    )


def test_a_record_without_a_phase_is_a_start(tmp_path: pathlib.Path) -> None:
    """A log written before phases existed still reads as start records."""
    line = json.dumps({key: value for key, value in START.items() if key != "phase"})

    (record,) = read_records(_write(tmp_path / "probe.log", line))

    assert record.phase == "start", record.phase


def test_a_live_read_skips_one_torn_trailing_line(tmp_path: pathlib.Path) -> None:
    """A probe mid-write leaves one incomplete line, which a live read drops."""
    log = _write(tmp_path / "probe.log", json.dumps(START), '{"program": "probe-whit')

    (record,) = read_records(log, live=True)

    assert record.program == "probe-cargo", record.program


def test_a_finished_read_rejects_a_torn_trailing_line(
    tmp_path: pathlib.Path,
) -> None:
    """Once Make has exited no probe can be writing, so a torn line is a loss."""
    log = _write(tmp_path / "probe.log", json.dumps(START), '{"program": "probe-whit')

    _reject(log, live=False)


@pytest.mark.parametrize("live", [True, False], ids=["live", "finished"])
def test_a_torn_line_in_the_middle_is_rejected_either_way(
    tmp_path: pathlib.Path, *, live: bool
) -> None:
    """Only the final line may be torn; an earlier one is always a finding."""
    log = _write(tmp_path / "probe.log", '{"program": "probe-whit', json.dumps(START))

    _reject(log, live=live)


@pytest.mark.parametrize(
    "line",
    [
        pytest.param("[]", id="not-an-object"),
        pytest.param('{"args": [], "env": {}}', id="no-program"),
        pytest.param('{"program": 7, "args": [], "env": {}}', id="program-not-text"),
        pytest.param('{"program": "p", "args": "x", "env": {}}', id="args-not-list"),
        pytest.param('{"program": "p", "args": [1], "env": {}}', id="arg-not-text"),
        pytest.param('{"program": "p", "args": [], "env": []}', id="env-not-object"),
        pytest.param(
            '{"program": "p", "args": [], "env": {}, "phase": 1}', id="phase-not-text"
        ),
    ],
)
@pytest.mark.parametrize("live", [True, False], ids=["live", "finished"])
def test_a_line_that_decodes_but_is_not_a_record_is_rejected(
    tmp_path: pathlib.Path, line: str, *, live: bool
) -> None:
    """JSON that is not a probe record is a reading finding, not a `KeyError`."""
    _reject(_write(tmp_path / "probe.log", line), live=live)
