"""Contract tests for the pinned Rust toolchain and its build surfaces.

The repository pins a dated nightly in ``rust-toolchain.toml`` so that the
estate build standard's compiler parallelism (``-Zthreads=8``) is available.
These tests assert the shape of that configuration without pinning the night's
date: Dependabot advances the date, and the contract must survive every bump.

The Cranelift codegen backend is deliberately absent. ADR 0011 records its
rejection: a panic forced across the FFI boundary escaped ``catch_unwind`` in
the ``stilyagi-markdown`` suite under Cranelift and was contained under LLVM,
so every profile stays on the default backend.
"""

import pathlib
import re
import tomllib
import typing as typ

from tests.support.workflow_files import read_text
from tests.support.workflows import load_workflow, workflow_steps

REPOSITORY_ROOT: typ.Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[1]
TOOLCHAIN: typ.Final[pathlib.Path] = REPOSITORY_ROOT / "rust-toolchain.toml"
CARGO_CONFIG: typ.Final[pathlib.Path] = REPOSITORY_ROOT / ".cargo" / "config.toml"
MAKEFILE: typ.Final[pathlib.Path] = REPOSITORY_ROOT / "Makefile"
WORKFLOWS: typ.Final[pathlib.Path] = REPOSITORY_ROOT / ".github" / "workflows"

#: A dated nightly channel, as rustup and Dependabot both spell it.
NIGHTLY_CHANNEL_RE: typ.Final[re.Pattern[str]] = re.compile(
    r"nightly-\d{4}-\d{2}-\d{2}"
)
#: Components the repository needs whatever the compiler channel is.
BASE_COMPONENTS: typ.Final[frozenset[str]] = frozenset({"rustfmt", "clippy"})
#: The preview backend ADR 0011 rejected for this workspace.
CRANELIFT_COMPONENT: typ.Final[str] = "rustc-codegen-cranelift-preview"
#: The frontend-thread flag the build standard sets in ``RUSTFLAGS``.
THREAD_FLAG: typ.Final[str] = "-Zthreads=8"
#: The exact ``RUSTFLAGS`` value CI passes through ``setup-rust``.
CI_RUSTFLAGS: typ.Final[str] = f"-D warnings {THREAD_FLAG}"
SETUP_RUST_ACTION: typ.Final[str] = "leynos/shared-actions/.github/actions/setup-rust"


def _document(path: pathlib.Path, *, reader: str) -> dict[str, object]:
    """Return one TOML file as a mapping, naming the reading on failure."""
    return tomllib.loads(read_text(path, reader=reader))


def _toolchain() -> dict[str, object]:
    """Return the ``[toolchain]`` table from ``rust-toolchain.toml``."""
    document = _document(TOOLCHAIN, reader="rust toolchain contract")
    toolchain = document.get("toolchain")
    assert isinstance(toolchain, dict), "rust-toolchain.toml has no [toolchain]"
    return typ.cast("dict[str, object]", toolchain)


def _steps_using(action: str) -> list[dict[str, object]]:
    """Return every workflow step that invokes one action by full path."""
    steps: list[dict[str, object]] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        document = load_workflow(read_text(path, reader="rust toolchain contract"))
        steps.extend(
            step
            for step in workflow_steps(document)
            if str(step.get("uses", "")).partition("@")[0] == action
        )
    assert steps, f"no workflow step invokes {action}"
    return steps


def _mapping(value: object, *, field: str) -> dict[str, object]:
    """Return one step field that must be a mapping."""
    assert isinstance(value, dict), f"workflow step field {field} is not a mapping"
    return typ.cast("dict[str, object]", value)


def test_toolchain_channel_is_a_dated_nightly() -> None:
    """Pin the channel to a ``nightly-YYYY-MM-DD`` release, not a moving tag."""
    channel = _toolchain().get("channel")
    assert isinstance(channel, str), "rust-toolchain.toml has no channel"
    assert NIGHTLY_CHANNEL_RE.fullmatch(channel) is not None, (
        f"channel must be a dated nightly (nightly-YYYY-MM-DD), got {channel!r}"
    )


def test_toolchain_installs_the_required_components() -> None:
    """Install the formatting and lint components with the compiler only."""
    components = _toolchain().get("components")
    assert isinstance(components, list), "rust-toolchain.toml has no components"
    installed = {str(component) for component in components}
    assert installed >= BASE_COMPONENTS, (
        f"expected {sorted(BASE_COMPONENTS)} in the toolchain components, "
        f"got {sorted(installed)}"
    )
    assert CRANELIFT_COMPONENT not in installed, (
        f"{CRANELIFT_COMPONENT!r} must not be installed: ADR 0011 rejected the "
        "Cranelift backend for this workspace"
    )


def test_no_cargo_profile_selects_the_cranelift_backend() -> None:
    """Keep every profile on LLVM, as ADR 0011's rejection requires."""
    if not CARGO_CONFIG.is_file():
        return
    config = _document(CARGO_CONFIG, reader="rust toolchain contract")
    profiles = config.get("profile")
    if not isinstance(profiles, dict):
        return
    for name, profile in profiles.items():
        if isinstance(profile, dict):
            assert profile.get("codegen-backend") != "cranelift", (
                f"profile.{name} must not select the cranelift backend"
            )


def test_makefile_enables_frontend_threads_by_default() -> None:
    """Set ``-Zthreads=8`` in the Makefile's default ``RUST_FLAGS``."""
    makefile = read_text(MAKEFILE, reader="rust toolchain contract")
    pattern = re.compile(
        rf"^RUST_FLAGS := -D warnings {re.escape(THREAD_FLAG)}(?:\s|$)",
        flags=re.MULTILINE,
    )
    assert pattern.search(makefile) is not None, (
        f"Makefile RUST_FLAGS must default to '-D warnings {THREAD_FLAG}'"
    )


def test_ci_setup_rust_steps_pass_the_frontend_thread_flag() -> None:
    """Pass the same ``RUSTFLAGS`` through every ``setup-rust`` invocation."""
    for step in _steps_using(SETUP_RUST_ACTION):
        inputs = _mapping(step.get("with"), field="with")
        assert inputs.get("rustflags") == CI_RUSTFLAGS, (
            f"setup-rust in {step.get('name')!r} must pass "
            f"rustflags: {CI_RUSTFLAGS!r}, got {inputs.get('rustflags')!r}"
        )
