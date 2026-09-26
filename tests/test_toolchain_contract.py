"""Contract tests keeping the Makefile and CI detector pins in sync.

``make lint`` runs the duplication gate, which verifies the pinned ``nose``
detector at run time, and CI installs that detector with ``cargo-binstall``.
These tests assert that the three places declaring the pin -- the Makefile's
``NOSE_VERSION``, the workflow's ``NOSE_VERSION``, and ``[tool.nose] version``
in ``pyproject.toml`` -- agree, without asserting any particular version.
Bumping a pin is routine; letting the declarations drift produces a gate that
passes locally and fails in CI, or the reverse.

They also pin the parts of the detector's provisioning that carry a decision
rather than a value: that the install refuses to fall back to compiling from
source, and that the cached directory is the one the recipe installs into.
"""

import pathlib
import re
import typing as typ

import pytest

from tests.support.assertions import assert_with_context
from tests.support.workflow_files import read_text
from tests.support.workflows import load_workflow

REPOSITORY_ROOT: typ.Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[1]
MAKEFILE: typ.Final[pathlib.Path] = REPOSITORY_ROOT / "Makefile"
PYPROJECT: typ.Final[pathlib.Path] = REPOSITORY_ROOT / "pyproject.toml"
SMOKE_WORKFLOW: typ.Final[pathlib.Path] = (
    REPOSITORY_ROOT / ".github" / "workflows" / "smoke.yml"
)
NOSE_TOOL: typ.Final = "nose"
#: The detector install directory the workflow caches and the recipe writes to.
NOSE_TOOLS_DIR: typ.Final = ".tools/nose"
#: The strategies ``make install-nose`` must refuse, in cargo-binstall's spelling.
PROHIBITED_STRATEGIES: typ.Final = "compile,quick-install"

#: PEP 440-flavoured shape check, so an accidentally emptied pin fails loudly
#: rather than comparing two empty strings as equal.
VERSION_RE: typ.Final = re.compile(r"\d+(?:\.\d+)+(?:[a-zA-Z0-9.+-]*)")


def _makefile_text() -> str:
    """Return the Makefile source."""
    return read_text(MAKEFILE, reader="_makefile_text")


def _makefile_pin() -> str:
    """Return the detector version the Makefile pins.

    Returns
    -------
    str
        The value assigned to ``NOSE_VERSION``.
    """
    variable = f"{NOSE_TOOL.upper()}_VERSION"
    match = re.search(
        rf"^{re.escape(variable)}\s*\??=\s*(\S+)\s*$",
        _makefile_text(),
        flags=re.MULTILINE,
    )
    assert match is not None, f"{variable} is not defined in the Makefile"
    return match.group(1)


def _workflow_environment() -> dict[str, str]:
    """Return the smoke workflow's ``env:`` block.

    Returns
    -------
    dict
        The workflow-level environment variables.
    """
    parsed = load_workflow(read_text(SMOKE_WORKFLOW, reader="_workflow_environment"))
    environment = parsed["env"]
    assert isinstance(environment, dict), "expected isinstance(environment, dict)"
    return typ.cast("dict[str, str]", environment)


def _workflow_pin() -> str:
    """Return the detector version CI pins.

    Returns
    -------
    str
        The value of the workflow-level ``NOSE_VERSION``.
    """
    variable = f"{NOSE_TOOL.upper()}_VERSION"
    environment = _workflow_environment()
    assert variable in environment, f"smoke.yml does not declare {variable}"
    return environment[variable]


def _gate_pin() -> str:
    """Return the detector version the duplication gate verifies at run time.

    Returns
    -------
    str
        The ``[tool.nose] version`` the gate checks ``nose --version`` against.
    """
    text = read_text(PYPROJECT, reader="_gate_pin")
    match = re.search(
        r"^\[tool\.nose\]$.*?^version\s*=\s*\"([^\"]*)\"",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, "pyproject.toml does not set [tool.nose] version"
    return match.group(1)


def _nose_installation_step() -> str:
    """Return CI's complete nose-detector installation step.

    The step's ``run:`` body is returned as written; the release URL and the
    published digest are replaced with placeholders, so the contract does not
    have to be rewritten when cargo-binstall is bumped or when a platform's
    digest changes.

    Returns
    -------
    str
        The installation recipe, with the release URLs and digest normalised.

    Raises
    ------
    AssertionError
        If the workflow declares no such step, which means the contract is
        reading nothing rather than that the repository complies.
    """
    document = load_workflow(
        read_text(SMOKE_WORKFLOW, reader="_nose_installation_step")
    )
    jobs = typ.cast("dict[str, object]", document["jobs"])
    lint_test = typ.cast("dict[str, object]", jobs["lint-test"])
    steps = typ.cast("list[dict[str, str]]", lint_test["steps"])
    for step in steps:
        if step.get("name") == "Install nose duplication detector":
            return _normalized(step["run"])
    available = [step.get("name", "<unnamed>") for step in steps]
    msg = f"no detector installation step found; available steps: {available!r}"
    raise AssertionError(msg)


def _normalized(recipe: str) -> str:
    """Replace the values in one recipe that a routine bump may move."""
    return re.sub(
        r"https://github\.com/(?:cargo-bins/cargo-binstall|corca-ai/nose)\S*",
        lambda match: (
            "<cargo-binstall release>"
            if "cargo-bins" in match.group(0)
            else "<nose repository>"
        ),
        re.sub(
            r"(?<=BINSTALL_SHA256: \")[0-9a-f]{64}(?=\")",
            "<sha256>",
            recipe,
        ),
    )


class TestToolchainPins:
    """The three declarations of the detector pin."""

    def test_makefile_and_ci_pin_the_same_version(self) -> None:
        """The Makefile and the workflow must pin nose to one version."""
        makefile_version = _makefile_pin()
        workflow_version = _workflow_pin()
        assert_with_context(
            VERSION_RE.fullmatch(makefile_version),
            f"Makefile NOSE_VERSION does not look like a version: {makefile_version!r}",
        )
        assert_with_context(
            makefile_version == workflow_version,
            f"nose version drift: the Makefile pins {makefile_version} but "
            f"smoke.yml installs {workflow_version}",
        )

    def test_gate_verifies_the_pinned_detector_version(self) -> None:
        """The gate's ``[tool.nose]`` pin must match the installed detector."""
        makefile_version = _makefile_pin()
        gate_version = _gate_pin()
        assert_with_context(
            VERSION_RE.fullmatch(gate_version),
            f"[tool.nose] version does not look like a version: {gate_version!r}",
        )
        assert_with_context(
            makefile_version == gate_version,
            f"nose version drift: the Makefile pins {makefile_version} but the "
            f"gate verifies {gate_version}",
        )

    @pytest.mark.parametrize(
        "usage_re",
        [
            r"'nose-cli@\$\(NOSE_VERSION\)'",
            r'"nose \$\(NOSE_VERSION\)"',
        ],
        ids=["binstall-install", "version-check"],
    )
    def test_makefile_commands_use_the_pinned_version(self, usage_re: str) -> None:
        """The Makefile's detector commands must reference the pinned variable."""
        assert_with_context(
            re.search(usage_re, _makefile_text()) is not None,
            f"the Makefile defines NOSE_VERSION but its nose command does not "
            f"reference it (expected pattern {usage_re})",
        )

    def test_makefile_refuses_a_source_build(self) -> None:
        """A missing prebuilt detector must fail provisioning, not compile.

        ``cargo-binstall`` falls back to compiling the crate, and then to
        cargo-quickinstall, when the requested strategy is not excluded. Either
        would make a green gate depend on a successful Rust build and, through
        quick-install, on an unapproved third-party build service. The install
        is therefore asserted to prohibit both.
        """
        assert_with_context(
            f"--disable-strategies {PROHIBITED_STRATEGIES}" in _makefile_text(),
            "make install-nose must pass "
            f"`--disable-strategies {PROHIBITED_STRATEGIES}` so a missing "
            "prebuilt detector fails provisioning instead of starting a build",
        )


class TestCiDetectorProvisioning:
    """What CI's detector installation is allowed to depend on."""

    def test_ci_installs_through_the_makefile_target(self) -> None:
        """CI must install the detector through the target developers use.

        A workflow that assembled its own ``cargo-binstall`` invocation could
        drop the strategy exclusion above while the Makefile kept it, so the
        gate would be provisioned differently in CI than locally. The step is
        asserted to delegate to ``make install-nose``.
        """
        step = _nose_installation_step()
        assert_with_context(
            "make install-nose" in step,
            "CI must install the detector through `make install-nose` so the "
            "provisioning contract lives in one place",
        )

    def test_ci_verifies_the_installer_against_a_checksum(self) -> None:
        """The downloaded installer must be verified before it is executed."""
        step = _nose_installation_step()
        assert_with_context(
            "sha256sum -c -" in step,
            "CI must verify the downloaded cargo-binstall archive against the "
            "published digest before running it",
        )

    def test_ci_requires_the_pinned_version_after_installing(self) -> None:
        """The installed detector must report the pin before the gate runs."""
        assert_with_context(
            f"{NOSE_TOOLS_DIR}/{NOSE_TOOL} --version" in _nose_installation_step(),
            "CI must verify the installed detector's version so a cache miss "
            "that restored the wrong binary fails at provisioning",
        )


class TestCiDetectorCache:
    """The cache that keeps the detector between runs."""

    def _cache_step(self) -> str:
        """Return the detector cache step's YAML block."""
        text = read_text(SMOKE_WORKFLOW, reader="TestCiDetectorCache")
        start = text.index("      - name: Cache the pinned nose duplication detector")
        end = text.find("\n      - name:", start + 1)
        return text[start:] if end == -1 else text[start:end].rstrip()

    def test_cache_covers_the_detector_install_directory(self) -> None:
        """The cache must carry the directory the recipe installs into."""
        match = re.search(
            r"^\s*path:\s*(\S+)\s*$", self._cache_step(), flags=re.MULTILINE
        )
        assert match is not None, "the detector cache declares no path:"
        assert_with_context(
            match.group(1) == NOSE_TOOLS_DIR,
            "the detector cache must carry the install directory itself, not a "
            f"larger or mistyped path; got {match.group(1)!r}",
        )

    def test_cache_directory_matches_the_makefile_install_target(self) -> None:
        """The cached directory must be the one the recipe writes the binary to."""
        match = re.search(
            r"^NOSE_TOOLS_DIR\s*\??=\s*(\S+)\s*$",
            _makefile_text(),
            flags=re.MULTILINE,
        )
        assert match is not None, "NOSE_TOOLS_DIR is not defined in the Makefile"
        assert_with_context(
            match.group(1) == NOSE_TOOLS_DIR,
            f"these tests assert the cached path is {NOSE_TOOLS_DIR!r} but the "
            f"Makefile installs into {match.group(1)!r}; a cache of the wrong "
            "directory never hits",
        )

    def test_cache_key_carries_the_pinned_version(self) -> None:
        """A version bump must miss the cache and reinstall."""
        match = re.search(
            r"^\s*key:\s*(.+?)\s*$", self._cache_step(), flags=re.MULTILINE
        )
        assert match is not None, "the detector cache declares no key:"
        assert_with_context(
            "NOSE_VERSION" in match.group(1),
            "the detector cache key must carry the pinned version so bumping "
            f"the pin forces a reinstall; got {match.group(1)!r}",
        )
