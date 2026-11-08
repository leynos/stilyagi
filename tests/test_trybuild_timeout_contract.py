"""The trybuild UI binaries get a per-test budget beyond the default.

`generate-coverage` writes a 180 s per-test budget when the repository has no
`.config/nextest.toml`. `stilyagi-ir`'s `ui` binary and `stilyagi-pyext`'s
`compile_tests` binary drive trybuild, which builds a scratch crate per case,
and on a cold instrumented runner they outlast 180 s: both were terminated at
180 s in the `Generate coverage` step of a pull request whose workflow change
left the Cargo cache cold. The configuration must therefore carry an override
naming both binaries with a budget well beyond the default, and that budget
must stay under the whole-run budget. Both binaries also share a serial test
group because their nested Cargo builds use the same trybuild target directory.
"""

import re
import tomllib
import typing as typ
from pathlib import Path

import pytest

from tests.support.nextest_config import global_timeout, largest_test_allowance

REPOSITORY_ROOT: typ.Final = Path(__file__).resolve().parents[1]
CONFIG_PATH: typ.Final = REPOSITORY_ROOT / ".config" / "nextest.toml"
DEFAULT_PER_TEST_SECONDS: typ.Final = 180
MINIMUM_TRYBUILD_SECONDS: typ.Final = 1500

#: Suite overhead and reporting once the last trybuild test has finished.
SUITE_OVERHEAD_SECONDS: typ.Final = 6 * 60

#: The whole-run budget, pinned as well as derived. The derivation below rises
#: with the trybuild allowance, so on its own it would accept any value above
#: its own requirement and let the number drift away from the guide's table.
MINIMUM_WHOLE_RUN_SECONDS: typ.Final = 56 * 60
TRYBUILD_BINARIES: typ.Final = (
    "package(stilyagi-ir) & binary(ui)",
    "package(stilyagi-pyext) & binary(compile_tests)",
)
TRYBUILD_TEST_GROUP: typ.Final = "trybuild"


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


def _trybuild_budget() -> int:
    """Return the per-test allowance the trybuild override grants, in seconds."""
    slow = _trybuild_override()["slow-timeout"]
    return _seconds(slow["period"]) * slow["terminate-after"]


def test_the_trybuild_binaries_outlast_the_default_budget() -> None:
    """Their per-test budget is at least the cold-compile allowance.

    The override's own budget is checked here, and the repository's shared
    reading, which takes the largest allowance the file grants, must agree.
    """
    budget = _trybuild_budget()
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
    assert _trybuild_budget() < _seconds(_profile()["global-timeout"]), (
        "the trybuild budget must sit below the global-timeout"
    )


def test_the_whole_run_budget_covers_the_serial_trybuild_sequence() -> None:
    """Both trybuild allowances, run one after the other, plus suite overhead.

    The two binaries share a serial test group, so a run that is slow for both
    spends two full allowances before either finishes, and a whole-run budget
    sized for one allowance plus an observed prefix can cancel the second while
    neither test has exceeded its own budget. A 2026-11-05 rebased run spent
    1,137 s on the first UI test and was cancelled 842 s into the second; the
    budget was 33 minutes then. Fifty minutes covers that prefix but not a pair
    at their full allowance, so the pair is what the budget is derived from
    rather than the one observed prefix.
    """
    config_text = read_config_text(CONFIG_PATH)
    whole_run = global_timeout(config_text)
    assert whole_run is not None, "the configuration must bound the whole run"

    pair = 2 * largest_test_allowance(config_text)
    assert whole_run >= pair + SUITE_OVERHEAD_SECONDS, (
        f"whole-run budget is {whole_run}s; two serial trybuild allowances are "
        f"{pair}s and suite overhead is {SUITE_OVERHEAD_SECONDS}s"
    )
    assert whole_run >= MINIMUM_WHOLE_RUN_SECONDS, (
        f"whole-run budget is {whole_run}s; the serial trybuild sequence needs "
        f"at least {MINIMUM_WHOLE_RUN_SECONDS}s"
    )


def test_trybuild_binaries_share_a_serial_test_group() -> None:
    """Serialize nested trybuild builds that share one target lock."""
    document = tomllib.loads(read_config_text(CONFIG_PATH))
    group = _trybuild_override().get("test-group")
    groups = document.get("test-groups", {})

    assert group == TRYBUILD_TEST_GROUP, (
        "expected both trybuild binaries to use the shared test group"
    )
    assert groups.get(TRYBUILD_TEST_GROUP, {}).get("max-threads") == 1, (
        "expected the trybuild test group to allow one active test"
    )


def test_every_other_test_keeps_the_default_budget() -> None:
    """Only the trybuild binaries are widened; the profile default is unchanged."""
    slow = _profile()["slow-timeout"]

    assert (
        _seconds(slow["period"]) * slow["terminate-after"] == DEFAULT_PER_TEST_SECONDS
    ), "widening every test would hide a hang as a slow test"


def test_the_widened_budget_is_scoped_to_the_two_binaries_only() -> None:
    """The override filter names only package-and-binary terms, never a wildcard.

    A filter such as `all()` or `test(/./)` would widen the 1,500 s budget to
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

    A second entry such as `filter = "all()"` at the same 1,500 s would leave the
    matching override unique and the shared reading unchanged, yet widen the
    budget to every test. The same holds under another profile, such as the
    `ci` profile `make test-ci` selects, which inherits the default. Requiring
    exactly one override across all profiles closes both.
    """
    profiles = tomllib.loads(read_config_text(CONFIG_PATH)).get("profile", {})
    found = {
        name: len(profile.get("overrides", []))
        for name, profile in profiles.items()
        if profile.get("overrides")
    }

    assert found == {"default": 1}, (
        "expected exactly the trybuild override, in the default profile only; "
        f"found overrides per profile: {found}"
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
