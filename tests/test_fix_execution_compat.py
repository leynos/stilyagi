"""Compatibility surface for the fix execution module's declared exports."""

from stilyagi.fix_execution import summarise_fix_errors, summarize_fix_errors

from tests.support.assertions import assert_with_context as check


def test_pre_oxford_export_name_remains_importable() -> None:
    """The rename must not break an existing import of the old export name."""
    check(
        summarise_fix_errors is summarize_fix_errors,
        "the pre-Oxford alias must resolve to the renamed export",
    )
