"""Tests for normalizing the ``nose query --format json`` report.

The detector's JSON report is untrusted input: these tests pin the shape
validation, the ordering of normalized findings, and the float coercion that
the gate relies on.
"""

import copy
import re
import typing as typ

import pytest
from duplication_gate_test_support import (
    STUB_REPORT,
    detector,
    stub_runner,
    stub_settings,
)

if typ.TYPE_CHECKING:
    from collections import abc as cabc


class TestNormalizeFindings:
    """Report parsing and finding normalization."""

    def test_normalizes_a_stub_report(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A stub report becomes one ordered finding with both locations."""
        monkeypatch.setenv("NOSE_BIN", "/stub/nose")
        findings = detector.run_detector(stub_settings(), runner=stub_runner())
        assert len(findings) == 1, "The stub report contains one family."
        assert (
            findings[0].label
            == "python/stilyagi/a.py:1-20 ~ python/stilyagi/b.py:30-49"
        ), "Findings must report both spans."

    @pytest.mark.parametrize(
        ("families", "expected_values", "expected_labels"),
        [
            pytest.param(
                [
                    {
                        "witness": "copy-paste",
                        "value": 5.0,
                        "locations": [
                            {
                                "file": "python/stilyagi/z.py",
                                "start": 1,
                                "end": 2,
                                "name": None,
                            },
                            {
                                "file": "python/stilyagi/y.py",
                                "start": 1,
                                "end": 2,
                                "name": None,
                            },
                        ],
                    },
                    {
                        "witness": "exact",
                        "value": 9.0,
                        "locations": [
                            {
                                "file": "python/stilyagi/a.py",
                                "start": 1,
                                "end": 2,
                                "name": "run",
                            },
                            {
                                "file": "python/stilyagi/b.py",
                                "start": 1,
                                "end": 2,
                                "name": "run",
                            },
                        ],
                    },
                ],
                [9.0, 5.0],
                [
                    "python/stilyagi/a.py:1-2 run ~ python/stilyagi/b.py:1-2 run",
                    "python/stilyagi/z.py:1-2 ~ python/stilyagi/y.py:1-2",
                ],
                id="descending-value",
            ),
            pytest.param(
                [
                    {
                        "witness": "copy-paste",
                        "value": 5.0,
                        "locations": [
                            {
                                "file": "python/stilyagi/z.py",
                                "start": 1,
                                "end": 2,
                                "name": None,
                            },
                            {
                                "file": "python/stilyagi/y.py",
                                "start": 1,
                                "end": 2,
                                "name": None,
                            },
                        ],
                    },
                    {
                        "witness": "copy-paste",
                        "value": 5.0,
                        "locations": [
                            {
                                "file": "python/stilyagi/b.py",
                                "start": 1,
                                "end": 2,
                                "name": None,
                            },
                            {
                                "file": "python/stilyagi/a.py",
                                "start": 1,
                                "end": 2,
                                "name": None,
                            },
                        ],
                    },
                ],
                [5.0, 5.0],
                [
                    "python/stilyagi/b.py:1-2 ~ python/stilyagi/a.py:1-2",
                    "python/stilyagi/z.py:1-2 ~ python/stilyagi/y.py:1-2",
                ],
                id="location-label-tie-break",
            ),
        ],
    )
    def test_orders_findings(
        self,
        families: list[dict[str, object]],
        expected_values: list[float],
        expected_labels: list[str],
    ) -> None:
        """Findings sort by descending value, then by normalized location label."""
        findings = detector.normalize_findings({"families": families})

        assert [finding.value for finding in findings] == expected_values, (
            "Higher-value families must sort first."
        )
        assert [finding.label for finding in findings] == expected_labels, (
            "Equal values must order by normalized location label."
        )

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            pytest.param(7, 7.0, id="integer"),
            pytest.param(7.5, 7.5, id="float"),
        ],
    )
    def test_normalizes_numeric_values_to_float(
        self,
        value: float,
        expected: float,
    ) -> None:
        """Integer and floating-point family values both normalize to float."""
        report = copy.deepcopy(STUB_REPORT)
        typ.cast("dict[str, typ.Any]", report)["families"][0]["value"] = value
        findings = detector.normalize_findings(report)
        assert isinstance(findings[0].value, float), (
            "Normalization must coerce family values to float."
        )
        assert findings[0].value == expected, "Normalization must preserve the value."

    @pytest.mark.parametrize(
        ("mutate", "diagnostic"),
        [
            pytest.param(
                lambda report: report.__setitem__("families", {}),
                "families must be an array",
                id="families-object",
            ),
            pytest.param(
                lambda report: report["families"][0].__setitem__("value", "high"),
                "value must be a number",
                id="string-value",
            ),
            pytest.param(
                lambda report: report["families"][0].update({"value": True}),
                "value must be a number",
                id="boolean-value",
            ),
            pytest.param(
                lambda report: report["families"][0].pop("value"),
                "value must be a number",
                id="missing-value",
            ),
            pytest.param(
                lambda report: report["families"][0].__setitem__(
                    "locations", "python/stilyagi/a.py"
                ),
                "locations must be an array",
                id="string-locations",
            ),
            pytest.param(
                lambda report: report["families"][0].__setitem__(
                    "locations", b"python/stilyagi/a.py"
                ),
                "locations must be an array",
                id="bytes-locations",
            ),
            pytest.param(
                lambda report: report["families"][0].__setitem__("locations", []),
                "locations must not be empty",
                id="empty-locations",
            ),
            pytest.param(
                lambda report: report["families"][0]["locations"].__setitem__(
                    0, "python/stilyagi/a.py"
                ),
                "families[0].locations[0] must be a table",
                id="malformed-first-location",
            ),
            pytest.param(
                lambda report: report["families"][0]["locations"][0].__setitem__(
                    "start", 0
                ),
                "start must be a positive integer",
                id="zero-start",
            ),
            pytest.param(
                lambda report: report["families"][0]["locations"][0].__setitem__(
                    "end", 0
                ),
                "end must not precede start",
                id="inverted-span",
            ),
            pytest.param(
                lambda report: report["families"][0]["locations"][0].__setitem__(
                    "end", "last"
                ),
                "end must be an integer",
                id="non-integer-end",
            ),
            pytest.param(
                lambda report: report["families"][0]["locations"][0].pop("end"),
                "end must be an integer",
                id="missing-end",
            ),
            pytest.param(
                lambda report: report["families"][0]["locations"][0].__setitem__(
                    "name", ""
                ),
                "name must be a non-empty string or null",
                id="empty-name",
            ),
        ],
    )
    def test_rejects_malformed_reports(
        self,
        mutate: cabc.Callable[[dict[str, typ.Any]], None],
        diagnostic: str,
    ) -> None:
        """Schema violations fail at the detector boundary."""
        report = copy.deepcopy(STUB_REPORT)
        mutate(typ.cast("dict[str, typ.Any]", report))
        with pytest.raises(detector.GateConfigError, match=re.escape(diagnostic)):
            detector.normalize_findings(report)
