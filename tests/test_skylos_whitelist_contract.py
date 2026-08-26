"""Contract tests for the Skylos allow list in ``pyproject.toml``.

The allow list is pinned here so a suppression cannot be added silently. Every
entry needs a name, a non-empty explanation, and a reviewer willing to agree
the symbol really is reachable at runtime.
"""

import pathlib
import tomllib
import typing as typ

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
_REQUIRED_SKYLOS_WHITELIST_NAMES: typ.Final = frozenset((
    "InvalidSpacyModelError",
    "_coerce_path",
    "_coerce_string_to_string_tuple_map",
    "_copy_mapping",
    "_require_strict_int",
    "reset_extraction_state_for_tests",
    "extract_document",
    "FixPlanRequest",
    "_overlap_rejection",
    "_validate_candidates",
    "plan_fixes",
))


def _mapping(value: object, *, subject: str) -> dict[str, object]:
    """Return a mapping payload, failing with the subject when it is absent."""
    assert isinstance(value, dict), f"{subject} must be a table"
    return value


def _text_sequence(value: object, *, subject: str) -> tuple[str, ...]:
    """Return a tuple of strings, failing with the subject when malformed."""
    assert isinstance(value, list), f"{subject} must be an array"
    assert all(isinstance(entry, str) for entry in value), (
        f"{subject} must contain only strings"
    )
    return tuple(typ.cast("list[str]", value))


def test_skylos_configuration_requires_strict_documented_exceptions() -> None:
    """Skylos must enable strict mode and explain each named exception."""
    with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as configuration_file:
        configuration = tomllib.load(configuration_file)
    tool = _mapping(configuration.get("tool"), subject="tool configuration")
    skylos = _mapping(tool.get("skylos"), subject="Skylos configuration")
    gate = _mapping(skylos.get("gate"), subject="Skylos gate configuration")
    assert gate.get("strict") is True, (
        "Skylos gate configuration must enable strict mode"
    )
    whitelist = _mapping(skylos.get("whitelist"), subject="Skylos whitelist")
    names = _text_sequence(whitelist.get("names"), subject="Skylos whitelist names")
    documented = _mapping(
        whitelist.get("documented"), subject="Skylos documented whitelist"
    )
    assert set(names) == _REQUIRED_SKYLOS_WHITELIST_NAMES, (
        "Skylos must retain the verified non-empty allow list"
    )
    assert set(documented) == _REQUIRED_SKYLOS_WHITELIST_NAMES, (
        "Skylos must document every verified allow-list exception"
    )
    assert all(isinstance(reason, str) and reason for reason in documented.values()), (
        "Skylos documented whitelist reasons must be non-empty strings"
    )
