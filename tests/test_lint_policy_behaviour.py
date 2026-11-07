"""Behavioural proof that the lint policy rejects code.

`test_lint_policy_contract.py` proves the policy is declared; this module
proves it is effective. It writes scratch crates whose `[lints]` tables are
copied from the workspace manifest, compiles a selected violating fixture, and
asserts the expected diagnostic is reported. The selection is chosen to cover
each enabled entry whose effect a copied table could silently lose, plus the
rustdoc levels that only flags or the table itself can apply. Without it, a
table naming a lint that does not exist, or a `clippy.toml` restriction that
never matches, would pass every gate in this repository.

Diagnostics are asserted by lint code rather than by a verbatim `.stderr`
snapshot: rustc's wording changes between releases, and the project guidance
rejects snapshots that churn on toolchain bumps. The lint code is the stable
contract.

The scratch crates live in a directory unique to each run under `target/`, which
Cargo ignores and Git does not track, and each declares an empty `[workspace]`
so it does not join the repository workspace. The unique name keeps two runs in
the same worktree from sharing a crate, and the directory is removed when the
module finishes. Clippy is pointed at the repository root with `CLIPPY_CONF_DIR`,
so the `disallowed-methods` restrictions under test are the real ones.

Four scratch crates carry the fixtures, and each exists so one denial can be
read without another masking it. The first pairs the four binary fixtures — one
each for `disallowed_methods`, `missing_assert_message`,
`missing_docs_in_private_items` and `unsafe_code` — with a documentation-clean
library, because a binary links its package's library and a library that
violated a denied entry would mask every binary's own diagnostic. The second
holds the undocumented library alone, so `missing_docs` is the only violation
it reports. The third and fourth both hold a library with a broken intra-doc
link and differ in one table entry: the third denies that link in the rustdoc
table, which proves the table bites with no flags at all, and the fourth omits
the entry, so the link stays a warning unless `-D warnings` escalates it.
"""

import dataclasses
import json
import os
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] - runs the pinned `cargo` over a scratch crate only.
import typing as typ
import uuid

import pytest

from tests.support.lint_policy import (
    REPOSITORY_ROOT,
    RUSTDOC_FLAGS_EXTRA,
    rustdoc_default,
    workspace_lints,
)
from tests.support.lint_policy_fixtures import (
    CLIPPY_FIXTURES,
    ScratchCrates,
    write_scratch_crates,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

#: The cargo executable, resolved once so the subprocess call names an
#: absolute path rather than a bare command looked up on the current PATH.
CARGO: typ.Final = shutil.which("cargo") or "cargo"

#: How long one compiler invocation may take. A cold build has to wait for a
#: slot in the shared admission pool, so this is far above the compile time
#: itself; the marker below gives pytest room to report the subprocess result.
COMPILE_TIMEOUT_SECONDS: typ.Final = 240

pytestmark = [
    pytest.mark.skipif(shutil.which("cargo") is None, reason="cargo is not installed"),
    pytest.mark.timeout(COMPILE_TIMEOUT_SECONDS + 60),
]


@dataclasses.dataclass(frozen=True, slots=True)
class Outcome:
    """The result of one compiler invocation."""

    returncode: int
    lint_codes: frozenset[str]
    output: str


def _lint_codes(stdout: str) -> frozenset[str]:
    """Return the lint codes reported in a cargo JSON message stream."""
    codes: set[str] = set()
    for line in stdout.splitlines():
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        code = (message.get("message") or {}).get("code") or {}
        name = code.get("code")
        if isinstance(name, str):
            codes.add(name)
    return frozenset(codes)


def _run_cargo(
    crate_root: pathlib.Path, *args: str, rustdocflags: str | None = None
) -> Outcome:
    """Run one cargo command in a scratch crate and collect its diagnostics."""
    env = os.environ.copy()
    env["CLIPPY_CONF_DIR"] = str(REPOSITORY_ROOT)
    env["CARGO_TERM_COLOR"] = "never"
    if rustdocflags is None:
        env.pop("RUSTDOCFLAGS", None)
    else:
        env["RUSTDOCFLAGS"] = rustdocflags
    try:
        completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed argv over a local scratch crate.
            [CARGO, *args, "--message-format=json"],
            cwd=crate_root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=COMPILE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return Outcome(
            returncode=-1,
            lint_codes=frozenset(),
            output=f"cargo {args} timed out after {COMPILE_TIMEOUT_SECONDS} s",
        )
    return Outcome(
        returncode=completed.returncode,
        lint_codes=_lint_codes(completed.stdout),
        output=completed.stderr,
    )


def _rustdoc_default() -> str:
    """Return the Makefile's rustdoc default with its extension seam expanded."""
    _, _, value = rustdoc_default().partition("=")
    return value.replace(RUSTDOC_FLAGS_EXTRA, "").strip()


@pytest.fixture(scope="module")
def crates() -> cabc.Iterator[ScratchCrates]:
    """Write the scratch crates once, under a directory no other run shares."""
    base = (
        REPOSITORY_ROOT
        / "target"
        / (f"lint-policy-fixtures-{os.getpid()}-{uuid.uuid4().hex[:8]}")
    )
    try:
        yield write_scratch_crates(base)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_scratch_crates_carry_the_workspace_tables(crates: ScratchCrates) -> None:
    """Every scratch manifest copies every workspace lint table."""
    missing = [
        f"{crate.name}: {namespace}"
        for crate in (crates.scratch, crates.undocumented, crates.denied, crates.warn)
        for namespace in workspace_lints()
        if f"[lints.{namespace}]"
        not in (crate / "Cargo.toml").read_text(encoding="utf-8")
    ]
    assert missing == [], "scratch manifests omit tables: " + ", ".join(missing)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        pytest.param(name, expected, id=name)
        for name, (_, expected) in CLIPPY_FIXTURES.items()
    ],
)
def test_clippy_rejects_each_enabled_lint(
    crates: ScratchCrates, name: str, expected: str
) -> None:
    """Each enabled Clippy entry rejects a fixture that violates it."""
    outcome = _run_cargo(crates.scratch, "clippy", "--bin", name)
    assert outcome.returncode != 0, f"{name} compiled despite {expected}"
    assert expected in outcome.lint_codes, (
        f"expected {expected} for {name}, saw {sorted(outcome.lint_codes)}"
    )


def test_rustc_rejects_undocumented_public_items(crates: ScratchCrates) -> None:
    """`missing_docs` rejects a public item without documentation."""
    outcome = _run_cargo(crates.undocumented, "clippy", "--lib")
    assert outcome.returncode != 0, "the library compiled despite missing_docs"
    assert "missing_docs" in outcome.lint_codes, (
        f"expected missing_docs, saw {sorted(outcome.lint_codes)}"
    )


def test_rustdoc_rejects_a_broken_link_under_the_default_flags(
    crates: ScratchCrates,
) -> None:
    """The Makefile's rustdoc default surfaces a docsrs-gated broken link."""
    outcome = _run_cargo(
        crates.scratch,
        "doc",
        "--bin",
        "docsrs_link",
        "--no-deps",
        rustdocflags=_rustdoc_default(),
    )
    assert outcome.returncode != 0, "the docsrs-gated broken link was accepted"
    assert "rustdoc::broken_intra_doc_links" in outcome.lint_codes, (
        f"expected a broken intra-doc link, saw {sorted(outcome.lint_codes)}"
    )


def test_rustdoc_lint_table_denies_a_broken_link_without_flags(
    crates: ScratchCrates,
) -> None:
    """The workspace rustdoc table denies a broken link with no flags at all."""
    outcome = _run_cargo(crates.denied, "doc", "--lib", "--no-deps", rustdocflags="")
    assert outcome.returncode != 0, "the table's denial did not bite"
    assert "rustdoc::broken_intra_doc_links" in outcome.lint_codes, (
        f"expected a broken intra-doc link, saw {sorted(outcome.lint_codes)}"
    )


def test_rustdoc_default_flags_deny_warnings(crates: ScratchCrates) -> None:
    """`-D warnings` escalates a warning the manifest does not already deny."""
    outcome = _run_cargo(
        crates.warn,
        "doc",
        "--lib",
        "--no-deps",
        rustdocflags=_rustdoc_default(),
    )
    assert outcome.returncode != 0, "the broken link stayed a warning"
    assert "rustdoc::broken_intra_doc_links" in outcome.lint_codes, (
        f"expected a broken intra-doc link, saw {sorted(outcome.lint_codes)}"
    )


def test_rustdoc_default_is_overridable(crates: ScratchCrates) -> None:
    """An empty `RUSTDOCFLAGS` override leaves the same link a warning."""
    outcome = _run_cargo(crates.warn, "doc", "--lib", "--no-deps", rustdocflags="")
    assert outcome.returncode == 0, outcome.output
