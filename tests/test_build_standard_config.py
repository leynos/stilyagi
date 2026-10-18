"""Hold `.cargo/config.toml` to the build standard it claims to apply.

Cargo selects one `rustflags` source and never merges them, so a flag present
in `[build]` but missing from the Linux-scoped table silently disappears on
Linux. These contracts read the file the way Cargo does: every source carries
the parallel frontend, mold is scoped to Linux alone, the sources repeat
rather than inherit, the Make restatement agrees with the file, and the
toolchain pin supplies what the configuration needs.
"""

import re
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] - runs the pinned `make` to print one variable.
import sys
import typing as typ

import pytest

from tests.support.build_standard import (
    CARGO_CONFIG,
    LINUX_TARGET,
    MOLD_FLAG,
    REPOSITORY_ROOT,
    THREADS_FLAG,
    TOOLCHAIN_FILE,
    read_toml,
    rustflag_sources,
)
from tests.support.build_standard_backend import backend_faults, is_adopted

REQUIRED_COMPONENTS: typ.Final = frozenset({
    "clippy",
    "llvm-tools-preview",
    "rust-analyzer",
    "rustc-codegen-cranelift-preview",
    "rustfmt",
})
DATED_NIGHTLY: typ.Final = re.compile(r"^nightly-\d{4}-\d{2}-\d{2}$")


@pytest.fixture(scope="module")
def config() -> dict[str, object]:
    """Return the parsed Cargo configuration."""
    return read_toml(CARGO_CONFIG)


@pytest.fixture(scope="module")
def sources(config: dict[str, object]) -> dict[str, tuple[str, ...]]:
    """Return the configuration's `rustflags` sources."""
    return rustflag_sources(config)


def test_the_configuration_declares_the_expected_sources(
    sources: dict[str, tuple[str, ...]],
) -> None:
    """An empty reading is the reader failing, so the sources are named."""
    assert set(sources) == {"build", LINUX_TARGET}, (
        "expected set(sources) == {'build', LINUX_TARGET}"
    )


@pytest.mark.parametrize("source", ["build", LINUX_TARGET])
def test_every_source_carries_the_parallel_frontend(
    source: str, sources: dict[str, tuple[str, ...]]
) -> None:
    """A source without `-Zthreads=8` loses it wherever Cargo picks that source."""
    assert THREADS_FLAG in sources[source], "expected THREADS_FLAG in sources[source]"


def test_mold_is_scoped_to_linux_alone(
    sources: dict[str, tuple[str, ...]],
) -> None:
    """Only the Linux table names mold; `build` reaches every platform."""
    carriers = {name for name, flags in sources.items() if MOLD_FLAG in flags}
    assert carriers == {LINUX_TARGET}, (
        f"mold is named by {sorted(carriers)}, expected only the Linux table"
    )


def test_sources_repeat_rather_than_inherit(
    sources: dict[str, tuple[str, ...]],
) -> None:
    """The Linux source keeps every `[build]` flag and adds only mold."""
    assert set(sources[LINUX_TARGET]) == {*sources["build"], MOLD_FLAG}, (
        "expected set(sources[LINUX_TARGET]) == {*sources['build'], MOLD_FLAG}"
    )


def test_no_source_selects_a_backend_through_rustflags(
    sources: dict[str, tuple[str, ...]],
) -> None:
    """The backend is a per-profile key, so a rustflag cannot leak it to release."""
    assert not [
        flag
        for flags in sources.values()
        for flag in flags
        if "codegen-backend" in flag
    ], "expected not [flag for flags in sources.values() for flag in flags..."


def test_make_restates_the_flags_the_configuration_applies(
    sources: dict[str, tuple[str, ...]],
) -> None:
    """The Makefile's `STANDARD_RUSTFLAGS` equals the source Cargo picks here."""
    make = shutil.which("make")
    assert make is not None, "expected make on PATH"
    result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed argv: the pinned `make` and a fixed target.
        [
            make,
            "--directory",
            str(REPOSITORY_ROOT),
            "--no-print-directory",
            "--eval=print-standard: ; @echo $(STANDARD_RUSTFLAGS)",
            "print-standard",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    on_linux = sys.platform.startswith("linux")
    expected = sources[LINUX_TARGET] if on_linux else sources["build"]
    assert tuple(result.stdout.split()) == expected, (
        "expected tuple(result.stdout.split()) == expected"
    )


@pytest.fixture(scope="module")
def toolchain() -> dict[str, typ.Any]:
    """Return the `[toolchain]` table of `rust-toolchain.toml`."""
    table = read_toml(TOOLCHAIN_FILE)["toolchain"]
    assert isinstance(table, dict), "expected isinstance(table, dict)"
    return table


def test_the_toolchain_pins_a_dated_nightly(toolchain: dict[str, typ.Any]) -> None:
    """`-Zthreads` needs nightly, and the pin must be exact and dated."""
    assert DATED_NIGHTLY.match(toolchain["channel"]), (
        "expected DATED_NIGHTLY.match(toolchain['channel'])"
    )


def test_the_toolchain_carries_the_standard_components(
    toolchain: dict[str, typ.Any],
) -> None:
    """The components the standard, the IDE and coverage use are all pinned."""
    assert set(toolchain["components"]) >= REQUIRED_COMPONENTS, (
        "expected set(toolchain['components']) >= REQUIRED_COMPONENTS"
    )


def test_no_manifest_declares_an_msrv() -> None:
    """The only consumer is the Python wheel, so no `rust-version` is declared."""
    manifests = [
        REPOSITORY_ROOT / "Cargo.toml",
        *REPOSITORY_ROOT.glob("crates/*/Cargo.toml"),
    ]
    assert len(manifests) > 1, "expected the workspace members to be read"
    declaring = [
        str(path.relative_to(REPOSITORY_ROOT))
        for path in manifests
        if "rust-version" in path.read_text(encoding="utf-8")
    ]
    assert not declaring, "expected not declaring"


GUIDE: typ.Final = REPOSITORY_ROOT / "docs" / "developers-guide.md"
CHANNEL: typ.Final = "nightly-2026-10-18"
RECORDED_EXCEPTION: typ.Final = (
    "## 5a\n\n### Why Cranelift is not part of the standard\n\n"
    f"Reproduced on {CHANNEL}.\n\n## 6\n"
)
ADOPTED: typ.Final = {
    "unstable": {"codegen-backend": True},
    "profile": {"dev": {"codegen-backend": "cranelift"}},
}
TOOLCHAIN: typ.Final = {
    "channel": CHANNEL,
    "components": ["rustc-codegen-cranelift-preview"],
}


def test_the_real_repository_adopts_cranelift_or_records_the_exception(
    config: dict[str, object], toolchain: dict[str, typ.Any]
) -> None:
    """Adoption needs its key, switch and component; the exception names the pin."""
    guide = GUIDE.read_text(encoding="utf-8")
    assert not backend_faults(config, toolchain, guide), (
        "expected not backend_faults(config, toolchain, guide)"
    )
    assert not is_adopted(config), "update the contract if the backend is adopted"


type BackendCase = tuple[dict[str, object], dict[str, typ.Any], str, str | None]

BACKEND_CASES: typ.Final[dict[str, BackendCase]] = {
    "exception_recorded_and_current": ({}, TOOLCHAIN, RECORDED_EXCEPTION, None),
    "adopted_with_switch_and_component": (ADOPTED, TOOLCHAIN, "## Notes\n", None),
    "no_section": ({}, TOOLCHAIN, "## Notes\n", "no developer"),
    "channel_moved": (
        {},
        {**TOOLCHAIN, "channel": "nightly-2026-11-01"},
        RECORDED_EXCEPTION,
        "stale",
    ),
    "adopted_but_exception_remains": (
        ADOPTED,
        TOOLCHAIN,
        RECORDED_EXCEPTION,
        "still records an exception",
    ),
    "adopted_without_unstable": (
        {"profile": {"dev": {"codegen-backend": "cranelift"}}},
        TOOLCHAIN,
        "## Notes\n",
        "[unstable]",
    ),
    "adopted_without_component": (
        ADOPTED,
        {"channel": CHANNEL, "components": []},
        "## Notes\n",
        "lacks rustc-codegen",
    ),
    "backend_on_another_profile": (
        {"profile": {"release": {"codegen-backend": "cranelift"}}},
        TOOLCHAIN,
        RECORDED_EXCEPTION,
        "selects a backend",
    ),
}


@pytest.mark.parametrize("case_id", sorted(BACKEND_CASES))
def test_the_backend_judgement_discriminates(case_id: str) -> None:
    """Each way of recording the backend wrongly is a fault; right ones are not."""
    config, toolchain, guide, expected = BACKEND_CASES[case_id]
    faults = backend_faults(config, toolchain, guide)
    if expected is None:
        assert not faults, (case_id, faults)
    else:
        assert any(expected in fault for fault in faults), (case_id, faults)
