"""Behavioural coverage for the builtin Markdown rules.

The scenarios live in `features/stilyagi_builtin_markdown_rules.feature` and
run the real builtin pack through `stilyagi check`. They complement the unit
tests in `tests/test_builtin_markdown_rules.py` by proving the same contracts
at the command boundary, including the safe/unsafe fix split.

Run them with:

    make test

or, for this module alone:

    .venv/bin/python -m pytest tests/test_builtin_markdown_rules_bdd.py
"""

import pytest
from pytest_bdd import scenarios

pytest_plugins = (
    "tests.steps.builtin_markdown_rules",
    "tests.steps.builtin_markdown_rules_cli",
    "tests.package_skeleton_support",
)
pytestmark = pytest.mark.usefixtures("reset_extraction_state")

scenarios("../features/stilyagi_builtin_markdown_rules.feature")
