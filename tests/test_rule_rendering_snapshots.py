"""Stable presentation snapshots for the builtin rule commands.

The snapshots record the complete text details, the text list, and both JSON
envelopes. Each test pairs its snapshot with a semantic assertion, so accepting
a snapshot cannot hide a contradictory value. Only stable output is captured:
no paths, hostnames, versions, timestamps, or terminal-dependent widths.
"""

import json
import typing as typ

import pytest
from syrupy.extensions.json import JSONSnapshotExtension

from tests.support.rule_command_support import detail_result, list_result

_CODES = ("MD001", "STY001", "TERM001")

if typ.TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion


def test_text_list_matches_snapshot(snapshot: SnapshotAssertion) -> None:
    """The complete text list is stable and semantically complete."""
    status, output, error = list_result()

    assert status == 0, "expected a successful list"
    assert not error, "expected no failure output"
    assert "TERM001" in output, "expected the opt-in rule in the list"
    assert output == snapshot, "expected the stable text list"


@pytest.mark.parametrize("code", _CODES)
def test_text_detail_matches_snapshot(
    snapshot: SnapshotAssertion,
    code: str,
) -> None:
    """Each complete text detail is stable and states its own code."""
    status, output, error = detail_result(code)

    assert status == 0, "expected a successful detail"
    assert not error, "expected no failure output"
    assert output.startswith(f"{code} "), "expected the code to begin the detail"
    assert output == snapshot, f"expected the stable {code} detail"


def test_json_list_matches_snapshot(snapshot: SnapshotAssertion) -> None:
    """The complete JSON list envelope is stable."""
    _status, output, _error = list_result(output_format="json")

    payload = json.loads(output)
    assert payload["schema_version"] == 1, "expected schema version 1"
    assert payload == snapshot(extension_class=JSONSnapshotExtension), (
        "expected the stable JSON list envelope"
    )


@pytest.mark.parametrize("code", _CODES)
def test_json_detail_matches_snapshot(
    snapshot: SnapshotAssertion,
    code: str,
) -> None:
    """Each complete JSON detail envelope is stable."""
    _status, output, _error = detail_result(code, "json")

    payload = json.loads(output)
    assert payload["rule"]["code"] == code, "expected the requested rule"
    assert payload == snapshot(extension_class=JSONSnapshotExtension), (
        f"expected the stable JSON detail for {code}"
    )
