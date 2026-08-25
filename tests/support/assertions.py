"""Shared assertion helpers for test diagnostics evaluated on every test run.

Use ``assert_with_context`` when an assertion needs a contextual failure
message, for example ``assert_with_context(actual == expected, "values match")``.
"""


def assert_with_context(condition: object, message: str) -> None:
    """Raise an assertion error with the supplied context when needed.

    Parameters
    ----------
    condition
        Value whose truthiness determines whether the assertion succeeds.
    message
        Diagnostic context included in the assertion error.

    Raises
    ------
    AssertionError
        If ``condition`` is false.

    Examples
    --------
    >>> assert_with_context(2 + 2 == 4, "arithmetic should remain stable")
    """
    if condition:
        return
    raise AssertionError(message)
