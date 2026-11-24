"""Behavioural coverage for the builtin documentation rules.

The scenarios live in ``features/builtin_docstring_rules.feature`` and drive
the real builtin pack through ``stilyagi check`` over a mixed Markdown,
Python, and Rust tree. They complement the unit matrix in
``tests/test_builtin_docstring_rules.py`` by proving the same contracts at the
command boundary, including per-rule opt-in, surface exclusion, and repeated
run stability.

Run them with:

    make test

or, for this module alone:

    .venv/bin/python -m pytest tests/test_builtin_docstring_rules_bdd.py
"""

import pytest
from pytest_bdd import scenarios

pytest_plugins = (
    "tests.steps.builtin_docstring_rules",
    "tests.package_skeleton_support",
)
pytestmark = pytest.mark.usefixtures("reset_extraction_state")

scenarios("../features/builtin_docstring_rules.feature")
