"""Observability contract for the fix planner's per-file decision event.

The planner reports each decision once, at INFO, with the counters a later
stage consumes and cannot recover. These tests pin the event's field names and
its outcome vocabulary, because a log consumer keys on both: a renamed field or
a new outcome value is a breaking change to anyone reconstructing a run from
the log, and neither shows up as a failure anywhere else.
"""

import logging

import pytest
from stilyagi import diagnostics, model
from stilyagi.config import LintConfig
from stilyagi.engine.fix_planning.plan import FixPlanRequest, plan_fixes
from stilyagi.fixes import Applicability, Fix, FixLevel, TextEdit

from tests.support.assertions import assert_with_context
from tests.support.fix_fixtures import find_source_span

_LOGGER_NAME = "stilyagi.engine.fix_planning.plan"

#: Every field the event must carry, and the type a consumer may rely on.
_REQUIRED_FIELDS = frozenset({
    "operation",
    "outcome",
    "candidate_count",
    "accepted_count",
    "coalesced_count",
    "rejection_count",
    "rejection_category",
    "conflict_state",
    "source_backed_spans",
    "patch_byte_count",
})


def _planner_record(caplog: pytest.LogCaptureFixture) -> logging.LogRecord:
    """Return the planner's single record from the captured ones.

    The capture is filtered on the planner's logger by name, so a record a
    neighbouring module emitted during the same call cannot satisfy an
    assertion here by accident. Asserting there is exactly one also pins the
    "one decision, one event" property the contract rests on.

    Returns
    -------
    logging.LogRecord
        The one record the planner emitted for this call.
    """
    records = [record for record in caplog.records if record.name == _LOGGER_NAME]
    assert_with_context(
        len(records) == 1,
        f"expected exactly one planner record, got "
        f"{[record.getMessage() for record in records]!r}",
    )
    return records[0]


def _source_with_one_span(source: str) -> tuple[model.Document, object]:
    """Return a one-segment document and the span covering its whole text."""
    document = model.Document(
        model.Syntax.MARKDOWN,
        ir={
            "regions": [
                {
                    "segments": [
                        {
                            "text": source,
                            "source": {"byte_start": 0, "byte_end": len(source)},
                        }
                    ]
                }
            ]
        },
    )
    return document, find_source_span(document, source)


def _request(
    source: str,
    document: model.Document,
    diagnostics_list: tuple[diagnostics.Diagnostic, ...] = (),
    *,
    level: FixLevel = FixLevel.SAFE,
) -> FixPlanRequest:
    """Build a planner request over one source string."""
    return FixPlanRequest(
        source.encode(),
        document,
        diagnostics_list,
        level,
        LintConfig(),
    )


def _replacement(edit: TextEdit) -> diagnostics.Diagnostic:
    """Return the one candidate diagnostic a case plans over."""
    return diagnostics.Diagnostic(
        "docs/example.md",
        "PUN201",
        "example",
        fix=Fix("Replace", Applicability.SAFE, (edit,)),
    )


def test_planner_emits_one_event_naming_every_counter(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Report a planned rewrite with the full counter set on one record."""
    source = "Hello world"
    document, span = _source_with_one_span(source)
    candidate = _replacement(TextEdit.replace(span, "earth"))

    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        plan = plan_fixes(_request(source, document, (candidate,)))

    record = _planner_record(caplog)
    assert_with_context(
        record.getMessage() == "fix plan decided",
        f"expected the decided event, got {record.getMessage()!r}",
    )
    assert_with_context(record.levelno == logging.INFO, "expected an INFO record")
    assert_with_context(
        set(vars(record)) >= _REQUIRED_FIELDS,
        f"expected the event to carry every field, missing "
        f"{sorted(_REQUIRED_FIELDS - set(vars(record)))}",
    )
    assert_with_context(
        (
            record.operation,
            record.outcome,
            record.candidate_count,
            record.accepted_count,
            record.rejection_count,
            record.patch_byte_count,
        )
        == ("plan_fixes", "fixed", 1, 1, 0, len(plan.fixed_bytes or b"")),
        "expected the fixed outcome to count its candidate, edit and patch bytes",
    )


@pytest.mark.parametrize(
    ("case", "expected_outcome"),
    [
        pytest.param("no-diagnostics", "unchanged", id="unchanged"),
        pytest.param("refused", "refused", id="refused"),
        pytest.param("fixed", "fixed", id="fixed"),
    ],
)
def test_planner_names_which_terminal_path_produced_the_plan(
    caplog: pytest.LogCaptureFixture,
    case: str,
    expected_outcome: str,
) -> None:
    """Distinguish a quiet file, a refused file and a rewritten file.

    The three are the planner's only terminal paths, and they call for
    different operator responses: "unchanged" is a file with nothing to do,
    "refused" is a file the configuration or the IR rejected, and "fixed" is a
    write. Collapsing them into one value would make a run that silently
    refused every edit look identical to a run with nothing to fix.
    """
    source = "Hello world"
    document, span = _source_with_one_span(source)
    match case:
        case "refused":
            # An edit reaching past the source bytes is refused, not planned.
            past_the_end = TextEdit(span.byte_start, len(source.encode()) + 1, "x")
            diagnostics_list = (_replacement(past_the_end),)
        case "fixed":
            diagnostics_list = (_replacement(TextEdit.replace(span, "earth")),)
        case _:
            diagnostics_list = ()

    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        plan_fixes(_request(source, document, diagnostics_list))

    assert_with_context(
        _planner_record(caplog).outcome == expected_outcome,
        f"expected the {case!r} case to report {expected_outcome!r}",
    )


def test_planner_reports_a_refusal_category_and_conflict_state(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Name the rejection family, and separate a conflict from a refusal."""
    source = "Hello world"
    document, span = _source_with_one_span(source)
    past_the_end = TextEdit(span.byte_start, len(source.encode()) + 1, "x")

    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        plan_fixes(_request(source, document, (_replacement(past_the_end),)))

    record = _planner_record(caplog)
    assert_with_context(
        record.rejection_category == "fix-error/invalid-span",
        "expected the event to name the rejection family",
    )
    assert_with_context(
        record.conflict_state is False,
        "expected a plain refusal not to be reported as a conflict",
    )


def test_planner_distinguishes_a_conflict_from_an_ordinary_refusal(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Flag an overlap, which needs a different operator response to a refusal.

    An ordinary refusal means one edit could not be trusted; an overlap means
    two rules disagreed about the same bytes. The second is a rule-authoring
    problem the operator has to resolve, so it is reported separately rather
    than as one more rejection family.
    """
    source = "Hello world"
    document, span = _source_with_one_span(source)
    competing = tuple(
        _replacement(TextEdit.replace(span, text)) for text in ("earth", "mars")
    )

    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        plan = plan_fixes(_request(source, document, competing))

    record = _planner_record(caplog)
    assert_with_context(
        plan.fixed_bytes is None, "expected competing edits to abort the mutation"
    )
    assert_with_context(
        record.rejection_category == "fix-error/overlapping-edits",
        "expected the conflict to be named as such",
    )
    assert_with_context(
        record.conflict_state is True,
        "expected a rule disagreement to be flagged as a conflict",
    )


def test_planner_defaults_a_quiet_file_to_zero_counters(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Report a file with nothing to plan without inventing counts."""
    source = "Hello world"
    document, _span = _source_with_one_span(source)

    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        plan_fixes(_request(source, document))

    record = _planner_record(caplog)
    assert_with_context(
        (
            record.outcome,
            record.candidate_count,
            record.accepted_count,
            record.rejection_count,
            record.rejection_category,
            record.patch_byte_count,
        )
        == ("unchanged", 0, 0, 0, None, 0),
        "expected a quiet file to report zeroes and no rejection category",
    )
    assert_with_context(
        record.source_backed_spans == 1,
        "expected the span denominator to be reported even when nothing was planned",
    )
