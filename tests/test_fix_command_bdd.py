"""Behavioural coverage for `stilyagi check --fix`.

The scenarios live in `features/stilyagi_fix_command.feature` and their steps in
`tests/steps/fix_command.py`. Keeping the binding separate from the step
definitions follows the existing check-command split, so the feature file, the
steps, and the module that runs them can be read independently.

Run them with:

    make test

or, for this module alone:

    .venv/bin/python -m pytest tests/test_fix_command_bdd.py
"""

import pytest
from pytest_bdd import scenarios

pytest_plugins = ("tests.steps.fix_command", "tests.package_skeleton_support")
pytestmark = pytest.mark.usefixtures("reset_extraction_state")

scenarios("../features/stilyagi_fix_command.feature")
