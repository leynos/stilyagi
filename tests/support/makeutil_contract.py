"""Assertions for how a workflow provisions makeutil.

CI installs makeutil through the shared prebuilt `install-makeutil` action and
smoke-tests it straight away. These assertions hold both halves in one place so
the workflow contract that calls them stays under the module size limit.
"""

import re
import typing as typ

from tests.support.assertions import assert_with_context

INSTALL_ACTION: typ.Final = (
    "leynos/shared-actions/.github/actions/install-makeutil"
    "@d57cb19b82281236088108f2ffb7e13bc00fc2f8"
)

_VERSION_CHECK: typ.Final = (
    'test "$(makeutil --version)" = "makeutil ${INSTALLED_VERSION}"'
)


def assert_installation(step: dict[str, object], *, contract: str) -> None:
    """Assert that `step` runs the pinned prebuilt install action, defaults only.

    A `run` key would mean a from-source install had crept back, and a `with`
    key would move the version off the action's own default and digest table.
    """
    assert_with_context(
        step.get("uses") == INSTALL_ACTION,
        f"{contract} must use the pinned install-makeutil action",
    )
    assert_with_context(
        "run" not in step,
        f"{contract} must not also run an install command",
    )
    assert_with_context(
        "with" not in step,
        f"{contract} must take the action's default version",
    )


def assert_verification(
    install_step: dict[str, object],
    verify_step: dict[str, object],
    *,
    contract: str,
) -> None:
    """Assert the smoke step that proves the installed binary is usable.

    The install step needs an id so the verify step can read the version the
    action reports; the verify step must compare the binary's own version with
    it and require a complete parse of the repository Makefile.
    """
    assert_with_context(
        install_step.get("id") == "makeutil",
        f"{contract} install step needs id",
    )
    environment = verify_step.get("env")
    assert_with_context(
        isinstance(environment, dict),
        f"{contract} verify step needs an env",
    )
    assert_with_context(
        environment.get("INSTALLED_VERSION")
        == ("${{ steps.makeutil.outputs.version }}"),
        f"{contract} must read the version the install action reports",
    )
    script = verify_step.get("run")
    assert_with_context(
        isinstance(script, str),
        f"{contract} must run a verification script",
    )
    assert_with_context(
        _VERSION_CHECK in script,
        f"{contract} must compare the binary's version with the installed one",
    )
    assert_with_context(
        "makeutil parse Makefile" in script,
        f"{contract} must parse the repository Makefile",
    )
    assert_with_context(
        '["parse"]["status"] == "complete"' in script,
        f"{contract} must require a complete parse",
    )
    assert_with_context(
        not re.search(r"\d+\.\d+\.\d+", script),
        f"{contract} must compare versions, never name one",
    )


def assert_verification_follows_install(
    steps: list[dict[str, object]], *, contract: str
) -> None:
    """Assert the verify step directly follows the install step."""
    names = [step.get("name") for step in steps]
    position = names.index("Install makeutil")
    assert_with_context(
        names[position + 1] == "Verify makeutil",
        f"{contract} must verify makeutil right after installing it",
    )
