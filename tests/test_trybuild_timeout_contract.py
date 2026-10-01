"""The trybuild UI binaries get a per-test budget beyond the default.

`generate-coverage` writes a 180 s per-test budget when the repository has no
`.config/nextest.toml`. `stilyagi-ir`'s `ui` binary and `stilyagi-pyext`'s
`compile_tests` binary drive trybuild, which builds a scratch crate per case,
and on a cold instrumented runner they outlast 180 s: both were terminated at
180 s in the `Generate coverage` step of a pull request whose workflow change
left the Cargo cache cold. The configuration must therefore carry an override
naming both binaries with a budget well beyond the default, and that budget
must stay under the whole-run budget.
"""

import re
import tomllib
import typing as typ
from pathlib import Path

import pytest

from tests.support.nextest_config import largest_test_allowance

REPOSITORY_ROOT: typ.Final = Path(__file__).resolve().parents[1]
CONFIG_PATH: typ.Final = REPOSITORY_ROOT / ".config" / "nextest.toml"
DEFAULT_PER_TEST_SECONDS: typ.Final = 180
MINIMUM_TRYBUILD_SECONDS: typ.Final = 600
TRYBUILD_BINARIES: typ.Final = (
    "package(stilyagi-ir) & binary(ui)",
    "package(stilyagi-pyext) & binary(compile_tests)",
)


def _seconds(duration: str) -> int:
    """Return a nextest duration such as `600s` or `20m` in seconds."""
    units = {"s": 1, "m": 60, "h": 3600}
    return int(duration[:-1]) * units[duration[-1]]


def read_config_text(path: Path) -> str:
    """Return the nextest configuration's text, failing clearly if unreadable.

    This is the one place the contract touches the filesystem, so a missing or
    unreadable file is reported as that rather than as a bare `OSError` from
    deep inside an assertion.

    Parameters
    ----------
    path
        The configuration file to read.

    Returns
    -------
    str
        The file's text.

    Raises
    ------
    AssertionError
        If the file cannot be read.

    Examples
    --------
    >>> read_config_text(Path("/nonexistent/nextest.toml"))
    Traceback (most recent call last):
    ...
    AssertionError: cannot read the nextest configuration /nonexistent/nextest.toml
    """
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        message = f"cannot read the nextest configuration {path}"
        raise AssertionError(message) from error


def default_profile(config_text: str) -> dict[str, typ.Any]:
    r"""Return the `default` profile table parsed from `config_text`.

    Parameters
    ----------
    config_text
        The configuration's TOML text.

    Returns
    -------
    dict[str, typing.Any]
        The `[profile.default]` table.

    Raises
    ------
    AssertionError
        If the text is not valid TOML or has no default profile.

    Examples
    --------
    >>> text = '[profile.default]\nglobal-timeout = "1m"'
    >>> default_profile(text)["global-timeout"]
    '1m'
    """
    try:
        document = tomllib.loads(config_text)
    except tomllib.TOMLDecodeError as error:
        message = f"the nextest configuration is not valid TOML: {error}"
        raise AssertionError(message) from error
    profile = document.get("profile", {}).get("default")
    assert isinstance(profile, dict), "the configuration has no [profile.default]"
    return profile


def _profile() -> dict[str, typ.Any]:
    """Return the repository's default profile."""
    return default_profile(read_config_text(CONFIG_PATH))


def _trybuild_override() -> dict[str, typ.Any]:
    """Return the sole override that names the trybuild binaries."""
    matches = [
        entry
        for entry in _profile().get("overrides", [])
        if all(binary in entry["filter"] for binary in TRYBUILD_BINARIES)
    ]
    assert len(matches) == 1, (
        f"expected one override naming both trybuild binaries, found {len(matches)}"
    )
    return matches[0]


def test_the_trybuild_binaries_outlast_the_default_budget() -> None:
    """Their per-test budget is at least the cold-compile allowance.

    The override's own budget is checked here, and the repository's shared
    reading, which takes the largest allowance the file grants, must agree.
    """
    slow = _trybuild_override()["slow-timeout"]
    budget = _seconds(slow["period"]) * slow["terminate-after"]
    assert largest_test_allowance(read_config_text(CONFIG_PATH)) == budget, (
        "the shared nextest reading must see the override as the largest allowance"
    )

    assert budget >= MINIMUM_TRYBUILD_SECONDS, (
        f"trybuild budget is {budget} s; a cold instrumented compile needs at "
        f"least {MINIMUM_TRYBUILD_SECONDS} s, well past the "
        f"{DEFAULT_PER_TEST_SECONDS} s default"
    )


def test_the_trybuild_budget_stays_below_the_whole_run_budget() -> None:
    """A per-test budget at or above `global-timeout` would never be reached."""
    slow = _trybuild_override()["slow-timeout"]
    budget = _seconds(slow["period"]) * slow["terminate-after"]

    assert budget < _seconds(_profile()["global-timeout"]), (
        "the trybuild budget must sit below the global-timeout"
    )


def test_every_other_test_keeps_the_default_budget() -> None:
    """Only the trybuild binaries are widened; the profile default is unchanged."""
    slow = _profile()["slow-timeout"]

    assert (
        _seconds(slow["period"]) * slow["terminate-after"] == DEFAULT_PER_TEST_SECONDS
    ), "widening every test would hide a hang as a slow test"


def test_the_widened_budget_is_scoped_to_the_two_binaries_only() -> None:
    """The override filter names only package-and-binary terms, never a wildcard.

    A filter such as `all()` or `test(/./)` would widen the 600 s budget to
    every test and hide a hang as a slow test.
    """
    override = _trybuild_override()
    terms = [term.strip() for term in re.split(r"\|", override["filter"])]

    assert len(terms) == len(TRYBUILD_BINARIES), (
        f"expected one term per trybuild binary, got {terms}"
    )
    for term in terms:
        assert re.fullmatch(r"\(?package\([\w-]+\) & binary\(\w+\)\)?", term), (
            f"override term {term!r} is not a package-and-binary pair"
        )


def test_the_trybuild_override_is_the_only_override() -> None:
    """No second override may exist, whatever its filter or budget.

    A second entry such as `filter = "all()"` at the same 600 s would leave the
    matching override unique and the shared reading unchanged, yet widen the
    budget to every test. Requiring exactly one override closes that.
    """
    overrides = _profile().get("overrides", [])

    assert len(overrides) == 1, (
        f"expected exactly the trybuild override, found {len(overrides)} overrides"
    )


def test_a_missing_configuration_file_is_reported_as_unreadable(
    tmp_path: Path,
) -> None:
    """`read_config_text` names the path instead of leaking a bare `OSError`."""
    missing = tmp_path / "nextest.toml"

    with pytest.raises(AssertionError, match="cannot read the nextest configuration"):
        read_config_text(missing)


def test_invalid_toml_is_reported_as_such() -> None:
    """`default_profile` refuses text that is not TOML."""
    with pytest.raises(AssertionError, match="not valid TOML"):
        default_profile("[profile.default\nglobal-timeout = ")


def test_a_configuration_without_a_default_profile_is_refused() -> None:
    """`default_profile` refuses a document with no `[profile.default]`."""
    with pytest.raises(AssertionError, match=re.escape("no [profile.default]")):
        default_profile('[profile.ci]\nglobal-timeout = "1m"')
