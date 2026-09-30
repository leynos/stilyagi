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


def _profile() -> dict[str, typ.Any]:
    """Return the parsed default profile."""
    with CONFIG_PATH.open("rb") as handle:
        return tomllib.load(handle)["profile"]["default"]


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
    """Their per-test budget is at least the cold-compile allowance."""
    slow = _trybuild_override()["slow-timeout"]
    budget = _seconds(slow["period"]) * slow["terminate-after"]

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
