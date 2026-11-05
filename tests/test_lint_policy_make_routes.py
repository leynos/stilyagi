"""Integration proof that the Make route applies the rustdoc policy.

`test_lint_policy_contract.py` pins the default in the `Makefile` text, and
`test_lint_policy_behaviour.py` compiles fixtures with that default expanded
by hand. Neither would notice a recipe that stopped passing `RUSTDOC_FLAGS`
to the compiler, or a second assignment that changed what the recipe sees.
These cases evaluate the route Make actually runs, with `--dry-run` against
the recording probes the build-standard suite already uses, so no compiler is
spawned and the rustdoc environment variable is read from the evaluated
recipe rather than from the file.

The environment variables the default depends on are always set explicitly,
including to `None` when the inherited value must not leak in, so a developer
shell exporting `RUSTDOC_FLAGS` cannot change what these cases assert.
"""

import typing as typ

import pytest

from tests.support.build_standard import (
    PROBE_CARGO,
    dry_run,
    make_available_tools,
    read_invocations,
)

if typ.TYPE_CHECKING:
    import pathlib

#: The gate target whose recipe compiles the crate's documentation.
DOC_TARGET: str = "lint"


@pytest.fixture(scope="module")
def probe_dir(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    """Return a directory of empty probe executables on which `command -v` works."""
    return make_available_tools(tmp_path_factory.mktemp("lint-policy-probes"))


def _rustdocflags(
    probe_dir: pathlib.Path,
    *,
    extra: str | None = None,
    override: str | None = None,
) -> str:
    """Return the `RUSTDOCFLAGS` the doc route evaluates, with the given inputs."""
    output = dry_run(
        DOC_TARGET,
        probe_dir,
        env={"RUSTDOC_FLAGS": override, "RUSTDOC_FLAGS_EXTRA": extra},
    )
    doc_routes = [
        invocation
        for invocation in read_invocations(output, (PROBE_CARGO,))
        if invocation.has_args("doc")
    ]
    assert len(doc_routes) == 1, (
        f"expected one doc route on `make {DOC_TARGET}`, found {len(doc_routes)}"
    )
    flags = doc_routes[0].env.get("RUSTDOCFLAGS")
    assert flags is not None, "the doc route did not assign RUSTDOCFLAGS"
    return flags


def test_the_route_defaults_to_docsrs_and_denied_warnings(
    probe_dir: pathlib.Path,
) -> None:
    """An unset environment lets the Makefile's default reach the compiler."""
    assert _rustdocflags(probe_dir).split() == ["--cfg", "docsrs", "-D", "warnings"], (
        "the doc route must compile with the docsrs cfg and denied warnings"
    )


def test_the_route_appends_the_extension_seam(probe_dir: pathlib.Path) -> None:
    """`RUSTDOC_FLAGS_EXTRA` from the environment reaches the compiler."""
    flags = _rustdocflags(probe_dir, extra="--cfg extra")
    assert flags.split() == ["--cfg", "docsrs", "-D", "warnings", "--cfg", "extra"], (
        f"the extension seam was not appended: {flags!r}"
    )


def test_the_route_passes_an_override_unchanged(probe_dir: pathlib.Path) -> None:
    """A full `RUSTDOC_FLAGS` override wins over the conditional default."""
    assert _rustdocflags(probe_dir, override="--cfg only") == "--cfg only", (
        "the route must pass an environment override through unchanged"
    )
