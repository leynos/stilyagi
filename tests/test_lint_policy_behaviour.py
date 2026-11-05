"""Behavioural proof that the lint policy rejects code.

`test_lint_policy_contract.py` proves the policy is declared; this module
proves it is effective. It writes a scratch crate whose `[lints]` tables are
copied from the workspace manifest, compiles one violating fixture per enabled
entry, and asserts the expected diagnostic is reported. Without it, a table
naming a lint that does not exist, or a `clippy.toml` restriction that never
matches, would pass every gate in this repository.

Diagnostics are asserted by lint code rather than by a verbatim `.stderr`
snapshot: rustc's wording changes between releases, and the project guidance
rejects snapshots that churn on toolchain bumps. The lint code is the stable
contract.

The scratch crates live under `target/`, which Cargo ignores and Git does not
track, and each declares an empty `[workspace]` so it does not join the
repository workspace. Clippy is pointed at the repository root with
`CLIPPY_CONF_DIR`, so the `disallowed-methods` restrictions under test are the
real ones.

There are two crates because a binary links its package's library, so a library
that violates `missing_docs` would mask every binary's own diagnostic. The
first crate therefore carries a documentation-clean library beside the binary
fixtures, and the undocumented library under test lives alone in the second.
"""

import dataclasses
import json
import os
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] - runs the pinned `cargo` over a scratch crate only.
import typing as typ

import pytest

from tests.support.lint_policy import (
    REPOSITORY_ROOT,
    RUSTDOC_FLAGS_EXTRA,
    rustdoc_default,
    workspace_lints,
)

if typ.TYPE_CHECKING:
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

SCRATCH_ROOT: typ.Final = REPOSITORY_ROOT / "target" / "lint-policy-fixtures"
CRATE_NAME: typ.Final = "lint-policy-fixtures"
UNDOCUMENTED_ROOT: typ.Final = (
    REPOSITORY_ROOT / "target" / "lint-policy-fixtures-undocumented"
)
UNDOCUMENTED_NAME: typ.Final = "lint-policy-fixtures-undocumented"
DENIED_ROOT: typ.Final = REPOSITORY_ROOT / "target" / "lint-policy-fixtures-denied"
DENIED_NAME: typ.Final = "lint-policy-fixtures-denied"
WARN_ROOT: typ.Final = REPOSITORY_ROOT / "target" / "lint-policy-fixtures-warn"
WARN_NAME: typ.Final = "lint-policy-fixtures-warn"

ENVIRONMENT_SEAM_SOURCE: typ.Final = (
    '/// Entry point.\nfn main() {\n    drop(std::env::var("HOME"));\n}\n'
)
ASSERT_WITHOUT_MESSAGE_SOURCE: typ.Final = (
    "/// Entry point.\nfn main() {\n"
    "    let count = std::env::args().count();\n"
    "    assert!(count > 0);\n}\n"
)
PRIVATE_ITEM_WITHOUT_DOCS_SOURCE: typ.Final = (
    "/// Entry point.\nfn main() {\n    undocumented();\n}\n\nfn undocumented() {}\n"
)
UNSAFE_BLOCK_SOURCE: typ.Final = (
    "/// Entry point.\nfn main() {\n"
    "    let pointer: *const u8 = std::ptr::null();\n"
    "    let _ = unsafe { *pointer };\n}\n"
)

#: One violating binary per Clippy entry, with the diagnostic it must produce.
CLIPPY_FIXTURES: typ.Final[dict[str, tuple[str, str]]] = {
    "environment_seam": (
        ENVIRONMENT_SEAM_SOURCE,
        "clippy::disallowed_methods",
    ),
    "assert_without_message": (
        ASSERT_WITHOUT_MESSAGE_SOURCE,
        "clippy::missing_assert_message",
    ),
    "private_item_without_docs": (
        PRIVATE_ITEM_WITHOUT_DOCS_SOURCE,
        "clippy::missing_docs_in_private_items",
    ),
    "unsafe_block": (UNSAFE_BLOCK_SOURCE, "unsafe_code"),
}

#: The shared library the binaries link. It satisfies every denied entry on
#: purpose, so it cannot mask a binary's own diagnostic.
LIBRARY_SOURCE: typ.Final = (
    "//! Probe crate.\n\n/// Documented.\npub const fn documented() {}\n"
)

#: The library in the second crate, which carries the `missing_docs` violation.
UNDOCUMENTED_LIBRARY_SOURCE: typ.Final = (
    "//! Probe crate.\n\npub fn undocumented() {}\n"
)

#: The library in the third and fourth crates. It is fully documented, so the
#: broken intra-doc link is the only violation. The third crate carries the
#: full rustdoc table, which denies the link with no flags at all; the fourth
#: omits that entry, so the lint stays at rustdoc's default `warn` and only
#: `-D warnings` can escalate it.
BROKEN_LINK_LIBRARY_SOURCE: typ.Final = (
    "//! Probe crate.\n\n/// See [Nothing] for details.\npub fn documented() {}\n"
)

#: A binary whose broken intra-doc link exists only under `--cfg docsrs`.
DOCSRS_SOURCE: typ.Final = (
    "/// Entry point.\nfn main() {}\n\n"
    "#[cfg(docsrs)]\n/// See [Nothing] for details.\npub fn documented() {}\n"
)


@dataclasses.dataclass(frozen=True, slots=True)
class Outcome:
    """The result of one compiler invocation."""

    returncode: int
    lint_codes: frozenset[str]
    output: str


def _render_value(value: object) -> str:
    """Render one lint entry as TOML, in both the string and table forms."""
    match value:
        case str():
            return f'"{value}"'
        case bool():
            return "true" if value else "false"
        case int():
            return str(value)
        case dict():
            pairs = ", ".join(
                f"{key} = {_render_value(item)}" for key, item in value.items()
            )
            return f"{{ {pairs} }}"
        case _:
            message = f"unexpected lint entry {value!r}"
            raise TypeError(message)


def _manifest(name: str, *, omit_rustdoc: frozenset[str] = frozenset()) -> str:
    """Render a scratch manifest copying the workspace lint tables.

    `omit_rustdoc` drops named rustdoc entries. A fixture proving `-D
    warnings` bites must omit the entry rather than set it to `warn`: an
    explicit level beats the `warnings` group, so a manifest `warn` survives
    the flag and would make the case pass for the wrong reason.

    Returns
    -------
    str
        The manifest text to write.
    """
    lines = [
        "[package]",
        f'name = "{name}"',
        'version = "0.0.0"',
        'edition = "2024"',
        "publish = false",
        "",
        "# Detach from the repository workspace; the tables are copied below so",
        "# the fixtures compile under the same policy the members inherit.",
        "[workspace]",
        "",
    ]
    for namespace, entries in workspace_lints().items():
        rendered = [
            (lint, value)
            for lint, value in entries.items()
            if not (namespace == "rustdoc" and lint in omit_rustdoc)
        ]
        if not rendered:
            continue
        lines.append(f"[lints.{namespace}]")
        lines.extend(f"{lint} = {_render_value(value)}" for lint, value in rendered)
        lines.append("")
    return "\n".join(lines)


def _write_binary(name: str, source: str) -> None:
    """Write one binary fixture, with the docs the policy requires."""
    path = SCRATCH_ROOT / "src" / "bin" / f"{name}.rs"
    path.write_text(f"//! Probe fixture.\n\n{source}", encoding="utf-8")


def _write_scratch_crate() -> pathlib.Path:
    """Write both scratch crates and return the shared one's directory."""
    (SCRATCH_ROOT / "src" / "bin").mkdir(parents=True, exist_ok=True)
    (SCRATCH_ROOT / "Cargo.toml").write_text(_manifest(CRATE_NAME), encoding="utf-8")
    (SCRATCH_ROOT / "src" / "lib.rs").write_text(LIBRARY_SOURCE, encoding="utf-8")
    for name, (source, _) in CLIPPY_FIXTURES.items():
        _write_binary(name, source)
    _write_binary("docsrs_link", DOCSRS_SOURCE)

    (UNDOCUMENTED_ROOT / "src").mkdir(parents=True, exist_ok=True)
    (UNDOCUMENTED_ROOT / "Cargo.toml").write_text(
        _manifest(UNDOCUMENTED_NAME), encoding="utf-8"
    )
    (UNDOCUMENTED_ROOT / "src" / "lib.rs").write_text(
        UNDOCUMENTED_LIBRARY_SOURCE, encoding="utf-8"
    )

    (DENIED_ROOT / "src").mkdir(parents=True, exist_ok=True)
    (DENIED_ROOT / "Cargo.toml").write_text(_manifest(DENIED_NAME), encoding="utf-8")
    (DENIED_ROOT / "src" / "lib.rs").write_text(
        BROKEN_LINK_LIBRARY_SOURCE, encoding="utf-8"
    )

    (WARN_ROOT / "src").mkdir(parents=True, exist_ok=True)
    (WARN_ROOT / "Cargo.toml").write_text(
        _manifest(WARN_NAME, omit_rustdoc=frozenset({"broken_intra_doc_links"})),
        encoding="utf-8",
    )
    (WARN_ROOT / "src" / "lib.rs").write_text(
        BROKEN_LINK_LIBRARY_SOURCE, encoding="utf-8"
    )
    return SCRATCH_ROOT


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
def scratch_crate() -> pathlib.Path:
    """Write the scratch crate once for the whole module."""
    return _write_scratch_crate()


def test_scratch_crates_carry_the_workspace_tables(
    scratch_crate: pathlib.Path,
) -> None:
    """Both scratch manifests copy every workspace lint table."""
    missing = [
        f"{crate.name}: {namespace}"
        for crate in (scratch_crate, UNDOCUMENTED_ROOT, DENIED_ROOT, WARN_ROOT)
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
    scratch_crate: pathlib.Path, name: str, expected: str
) -> None:
    """Each enabled Clippy entry rejects a fixture that violates it."""
    outcome = _run_cargo(scratch_crate, "clippy", "--bin", name)
    assert outcome.returncode != 0, f"{name} compiled despite {expected}"
    assert expected in outcome.lint_codes, (
        f"expected {expected} for {name}, saw {sorted(outcome.lint_codes)}"
    )


def test_rustc_rejects_undocumented_public_items(
    scratch_crate: pathlib.Path,
) -> None:
    """`missing_docs` rejects a public item without documentation."""
    outcome = _run_cargo(UNDOCUMENTED_ROOT, "clippy", "--lib")
    assert outcome.returncode != 0, "the library compiled despite missing_docs"
    assert "missing_docs" in outcome.lint_codes, (
        f"expected missing_docs, saw {sorted(outcome.lint_codes)}"
    )


def test_rustdoc_rejects_a_broken_link_under_the_default_flags(
    scratch_crate: pathlib.Path,
) -> None:
    """The Makefile's rustdoc default surfaces a docsrs-gated broken link."""
    outcome = _run_cargo(
        scratch_crate,
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
    scratch_crate: pathlib.Path,
) -> None:
    """The workspace rustdoc table denies a broken link with no flags at all."""
    outcome = _run_cargo(DENIED_ROOT, "doc", "--lib", "--no-deps", rustdocflags="")
    assert outcome.returncode != 0, "the table's denial did not bite"
    assert "rustdoc::broken_intra_doc_links" in outcome.lint_codes, (
        f"expected a broken intra-doc link, saw {sorted(outcome.lint_codes)}"
    )


def test_rustdoc_default_flags_deny_warnings(scratch_crate: pathlib.Path) -> None:
    """`-D warnings` escalates a warning the manifest does not already deny."""
    outcome = _run_cargo(
        WARN_ROOT,
        "doc",
        "--lib",
        "--no-deps",
        rustdocflags=_rustdoc_default(),
    )
    assert outcome.returncode != 0, "the broken link stayed a warning"
    assert "rustdoc::broken_intra_doc_links" in outcome.lint_codes, (
        f"expected a broken intra-doc link, saw {sorted(outcome.lint_codes)}"
    )


def test_rustdoc_default_is_overridable(scratch_crate: pathlib.Path) -> None:
    """An empty `RUSTDOCFLAGS` override leaves the same link a warning."""
    outcome = _run_cargo(WARN_ROOT, "doc", "--lib", "--no-deps", rustdocflags="")
    assert outcome.returncode == 0, outcome.output
