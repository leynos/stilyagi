"""Keep the recorded parser version honest about what it mirrors.

`dump-ir` reports each producer in the canonical IR, and the Markdown producer
carries a `version`. `markdown-rs` exposes no compile-time version, so
`crates/stilyagi-markdown/src/lib.rs` hardcodes `MARKDOWN_RS_VERSION` as a
mirror of the `markdown` dependency pin in the workspace `Cargo.toml`.

A mirror that nothing compares is a comment. Bump the dependency and the
recorded version silently disagrees with the crate that produced the IR, and
the only test that notices is a snapshot diff a reader has to interpret. These
contracts compare the two directly, so the mismatch is named for what it is.
They are not a substitute for the `dump-ir` snapshots; they say what the
snapshot's `producers[].version` means.

Run them with:

    make test

or, for this module alone:

    .venv/bin/python -m pytest tests/test_markdown_producer_version_contract.py
"""

import pathlib
import re
import tomllib

import pytest

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
_MARKDOWN_CRATE = "crates/stilyagi-markdown/src/lib.rs"

#: The constant that becomes `producers[].version` for Markdown documents.
_VERSION_CONST_RE = re.compile(
    r'const\s+MARKDOWN_RS_VERSION\s*:\s*&str\s*=\s*"(?P<version>[^"]+)"\s*;'
)

#: A caret requirement as the repository mandates, e.g. `^1.0.0` or `1.0.0`.
_CARET_REQUIREMENT_RE = re.compile(r"^\^?(?P<version>\d+\.\d+\.\d+)")


def _recorded_version() -> str:
    """Return the Markdown producer version the crate hardcodes.

    Returns
    -------
    str
        The value of `MARKDOWN_RS_VERSION`, as it will appear in the IR.
    """
    source = (REPOSITORY_ROOT / _MARKDOWN_CRATE).read_text(encoding="utf-8")
    match = _VERSION_CONST_RE.search(source)
    assert match is not None, (
        f"expected {_MARKDOWN_CRATE} to declare a string MARKDOWN_RS_VERSION"
    )
    return match.group("version")


def _declared_requirement() -> str:
    """Return the workspace's `markdown` dependency requirement.

    Returns
    -------
    str
        The requirement string exactly as `Cargo.toml` states it.
    """
    manifest = tomllib.loads(
        (REPOSITORY_ROOT / "Cargo.toml").read_text(encoding="utf-8")
    )
    requirement = manifest["workspace"]["dependencies"]["markdown"]
    if isinstance(requirement, dict):
        requirement = requirement["version"]
    assert isinstance(requirement, str), "expected a string markdown requirement"
    return requirement


def test_the_recorded_parser_version_matches_the_dependency_pin() -> None:
    """The IR's producer version names the crate version we actually depend on.

    `markdown-rs` cannot report its own version, so the constant is a
    hand-maintained mirror. This comparison is what makes the mirror a
    contract: raising the dependency without raising the constant fails here,
    naming both values, instead of surfacing as an unexplained snapshot diff.
    """
    requirement = _declared_requirement()
    match = _CARET_REQUIREMENT_RE.match(requirement)
    assert match is not None, (
        f"expected a caret requirement for markdown, found {requirement!r}"
    )

    recorded = _recorded_version()

    assert recorded == match.group("version"), (
        "the IR would report a parser version the workspace does not depend on: "
        f"MARKDOWN_RS_VERSION is {recorded!r} but Cargo.toml requires "
        f"{requirement!r}. Update both together."
    )


@pytest.mark.parametrize(
    ("requirement", "expected"),
    [
        pytest.param("^1.0.0", "1.0.0", id="caret"),
        pytest.param("1.0.0", "1.0.0", id="bare-caret-equivalent"),
        pytest.param("^1.2.3", "1.2.3", id="another-release"),
    ],
)
def test_the_requirement_reader_names_the_pinned_release(
    requirement: str,
    expected: str,
) -> None:
    """Read the release stem from the requirement forms the manifest may use.

    A bare `1.0.0` and `^1.0.0` are the same requirement in Cargo, and the
    repository mandates the caret form. The reader takes the leading release
    triple and ignores anything after it, so it compares versions rather than
    matching a substring -- a prerelease suffix cannot make two different
    releases look equal.
    """
    match = _CARET_REQUIREMENT_RE.match(requirement)

    assert match is not None, f"expected {requirement!r} to name a release"
    assert match.group("version") == expected, (
        f"expected {expected!r} from {requirement!r}, got {match.group('version')!r}"
    )
