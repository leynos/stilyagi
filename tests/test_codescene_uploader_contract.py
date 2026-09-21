"""Contract tests for the CodeScene uploader's deprecated checksum inputs.

At ``a5765019`` the shared uploader's committed ``cli-manifest.json`` is the
trust anchor for the CLI archive, and the action *rejects* a non-empty
``installer-checksum`` with a hard failure rather than ignoring it. A workflow
that still passes the input therefore breaks its coverage step outright, and
the ``CODESCENE_CLI_SHA256`` repository variable that fed it could only ever
repeat the digest the manifest already pins.

Four separate concerns are asserted, each in its own test so a failure names
the defect rather than a bundle:

* no workflow passes ``installer-checksum``;
* no workflow references the ``CODESCENE_CLI_SHA256`` variable that fed it;
* every uploader reference is pinned to one approved full SHA;
* the dispatch workflow that refreshed the variable is absent.

Each test asserts over a collection that is checked for content first. A
contract that ranges over an empty collection is satisfied by deleting the
thing it guards, which is the failure mode these tests exist to avoid.
"""

import pathlib
import re
import typing as typ

REPOSITORY_ROOT: typ.Final = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW_DIRECTORY: typ.Final = REPOSITORY_ROOT / ".github/workflows"

#: The uploader revision whose committed manifest is the trust anchor.
UPLOADER_PIN: typ.Final = "a5765019912a8ab6882b12db049c7cde635f3a85"

#: Every ``uses:`` reference to the shared uploader, with its ref captured.
#: Matched against raw text rather than a parsed document so a reference in a
#: comment, or in a step commented out, is caught as well.
UPLOADER_REFERENCE: typ.Final = re.compile(
    r"leynos/shared-actions/\.github/actions/upload-codescene-coverage@(\S+)"
)

DEPRECATED_INPUT: typ.Final = "installer-checksum"
DEPRECATED_VARIABLE: typ.Final = "CODESCENE_CLI_SHA256"
REFRESH_WORKFLOW: typ.Final = "get-codescene-sha.yml"

#: Both extensions GitHub accepts for a workflow. Reading only one would let a
#: workflow escape every contract below without failing a test.
WORKFLOW_SUFFIXES: typ.Final = ("*.yml", "*.yaml")


def _workflow_texts() -> dict[str, str]:
    """Return every workflow's text, keyed by repository-relative path.

    Returns
    -------
    dict[str, str]
        One entry per workflow file, in sorted order so a failure lists its
        offenders predictably.
    """
    paths = sorted(
        path for suffix in WORKFLOW_SUFFIXES for path in WORKFLOW_DIRECTORY.glob(suffix)
    )
    assert paths, (
        f"no workflow files were found under {WORKFLOW_DIRECTORY}, so every "
        "contract below would pass having read nothing"
    )
    return {
        path.relative_to(REPOSITORY_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in paths
    }


def test_no_workflow_passes_the_deprecated_installer_checksum() -> None:
    """The uploader rejects a non-empty value, so no workflow may pass it."""
    offenders = sorted(
        name for name, text in _workflow_texts().items() if DEPRECATED_INPUT in text
    )
    assert not offenders, (
        f"{DEPRECATED_INPUT} is deprecated and rejected outright by the "
        f"uploader at {UPLOADER_PIN}; remove it from {', '.join(offenders)}"
    )


def test_no_workflow_references_the_deprecated_checksum_variable() -> None:
    """The variable existed only to feed the rejected input, so it must go."""
    offenders = sorted(
        name for name, text in _workflow_texts().items() if DEPRECATED_VARIABLE in text
    )
    assert not offenders, (
        f"{DEPRECATED_VARIABLE} fed the deprecated installer checksum and has "
        f"no remaining consumer; remove it from {', '.join(offenders)}"
    )


def test_every_uploader_reference_is_pinned_to_the_approved_sha() -> None:
    """One approved SHA, asserted as an allowlist rather than as a floor.

    A floor would require ordering SHAs, which cannot be computed from a
    checkout. Naming the approved pin keeps the contract hermetic and fails
    closed on any other value, including a tag or a branch name.
    """
    references = {
        name: match.group(1)
        for name, text in _workflow_texts().items()
        for match in UPLOADER_REFERENCE.finditer(text)
    }
    assert references, (
        "no upload-codescene-coverage reference was found, so the pin "
        "assertion below would pass vacuously; this repository uploads "
        "coverage from main and checks it on pull requests"
    )
    wrong = {name: ref for name, ref in references.items() if ref != UPLOADER_PIN}
    assert not wrong, (
        "every upload-codescene-coverage reference must be pinned to "
        f"{UPLOADER_PIN}; found {wrong!r}"
    )


def test_the_checksum_refresh_workflow_is_absent() -> None:
    """Nothing consumes the variable it wrote, so the workflow is dead code."""
    refresh = WORKFLOW_DIRECTORY / REFRESH_WORKFLOW
    assert not refresh.exists(), (
        f"{REFRESH_WORKFLOW} refreshed {DEPRECATED_VARIABLE}, which no "
        "workflow reads any more; delete it rather than leave a dispatch that "
        "writes an unused repository variable"
    )
