"""The scripted release state a publishing step runs against.

A release step is a shell script that reaches the network only through
``curl`` and ``gh``, so a test replaces those two programs with the stand-ins
in ``tests/support/release_clients.py`` and gives them state it controls: one
file per GitHub Release asset, one file per PyPI file, and a journal of the
argument vectors that were run. A step then runs unchanged, without a network
or a token, against bytes the test can seed, inspect and compare.

This module supplies that state and installs the stand-ins. The deviation from
the scripting standards is deliberate and narrow. The standards ask for
``cmd-mox``, and ``tests/support/build_tools_harness`` uses it to drive
``scripts/build_tools.py``. A release step, however, is a shell script whose
arguments include ``gh``'s output on standard output, and ``cmd-mox``'s Python
handlers are a poor fit for a script that is not being driven from Python.
These stand-ins are therefore small executables written into a temporary
``PATH``, which is the same mechanism ``cmd-mox`` uses, minus the Python
dispatch.

A no-op ``sleep`` sits beside them, because the index lookup retries on a
delay a test must not pay.
"""

import dataclasses as dc
import hashlib
import json
import os
import pathlib
import stat
import sys
import typing as typ

from tests.support.release_clients import (
    FILES_URL,
    RELEASE_REF,
    RELEASE_REPO,
    RELEASE_TAG,
    RELEASE_WORKFLOW,
)

#: The recorded invocation of one fake program.
type Call = tuple[str, ...]

#: The commit the scripted runs are attested from.
BUILD_COMMIT: typ.Final = "a40898789a80e1ead3537cdab070fa87a80afced"


@dc.dataclass(frozen=True, slots=True)
class Attested:
    """The signing identity one attestation records.

    These are the fields ``gh attestation verify`` reads from the signing
    certificate and matches against its policy flags. A test overrides one of
    them to write an attestation that the workflow's policy must reject.
    """

    commit: str = BUILD_COMMIT
    repository: str = RELEASE_REPO
    ref: str = RELEASE_REF
    workflow: str = RELEASE_WORKFLOW
    runner: str = "github-hosted"


#: The identity this repository's release workflow signs with on a tag.
SIGNED_BY_RELEASE: typ.Final = Attested()


#: The repository root, which the generated stand-ins put on ``PYTHONPATH`` so
#: that the entry point can import its siblings as package modules.
_REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]

#: The entry point every fake re-executes; it dispatches on its first argument.
#: It wires the two stand-in modules together and is standard-library only
#: precisely so that it can be that entry point: importing pytest or a support
#: helper there would cost every fake invocation the test session's import
#: graph.
_DISPATCH = pathlib.Path(__file__).with_name("release_fake.py")


@dc.dataclass(frozen=True, slots=True)
class FakeRelease:
    """Directories standing in for the GitHub Release and PyPI, plus a journal."""

    root: pathlib.Path

    @property
    def github(self) -> pathlib.Path:
        """The directory holding one file per GitHub Release asset."""
        return self.root / "github-assets"

    @property
    def pypi(self) -> pathlib.Path:
        """The directory holding one file per PyPI file."""
        return self.root / "pypi-files"

    @property
    def journal(self) -> pathlib.Path:
        """The file each invocation appends its argument vector to."""
        return self.root / "calls.jsonl"

    @property
    def attestations(self) -> pathlib.Path:
        """The directory standing in for the repository's attestation store."""
        return self.root / "attestations"

    def attest(
        self, subjects: dict[str, bytes], *, as_: Attested = SIGNED_BY_RELEASE
    ) -> None:
        """Record one attestation in the store covering `subjects`.

        The store is queried by a file's digest, as GitHub's is, so a record
        answers for the bytes it names however the file reached the run. Like
        a real attestation, one record may bind several artefacts at once.

        Parameters
        ----------
        subjects
            Each artefact name and the bytes it was signed over.
        as_
            The signing identity to record. The default is this repository's
            release workflow at the tag, on a GitHub-hosted runner.
        """
        record: list[dict[str, object]] = [
            {
                "verificationResult": {
                    "statement": {
                        "subject": [
                            {
                                "name": name,
                                "digest": {
                                    "sha256": hashlib.sha256(payload).hexdigest()
                                },
                            }
                            for name, payload in subjects.items()
                        ]
                    },
                    "verifiedIdentity": {
                        "sourceRepositoryURI": (f"https://github.com/{as_.repository}"),
                        "sourceRepositoryRef": as_.ref,
                        "sourceRepositoryDigest": as_.commit,
                        "subjectAlternativeName": (
                            f"https://github.com/{as_.repository}"
                            f"{as_.workflow}@{as_.ref}"
                        ),
                        "runnerEnvironment": as_.runner,
                    },
                }
            }
        ]
        self.attestations.mkdir(parents=True, exist_ok=True)
        _write_record(self.attestations, record)

    def calls(self, program: str) -> list[Call]:
        """Return the invocations of one fake program, oldest first.

        Parameters
        ----------
        program
            The program name, ``curl`` or ``gh``.

        Returns
        -------
        list[Call]
            Each recorded argument vector, without the program name.
        """
        if not self.journal.exists():
            return []
        records = [
            json.loads(line)
            for line in self.journal.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return [tuple(record[1:]) for record in records if record[0] == program]

    def environ(self, **overrides: str) -> dict[str, str]:
        """Return an environment that resolves the fakes ahead of the host.

        Parameters
        ----------
        **overrides
            Variables to set or replace in the returned environment.

        Returns
        -------
        dict[str, str]
            The current process environment, with the fake tools first on
            ``PATH`` and then the system default path so that the steps'
            ``find``, ``xargs``, ``cp`` and ``ls`` still resolve; GH_TOKEN and
            GITHUB_TOKEN removed so no real credential can be used; exported
            shell functions removed, because a ``BASH_FUNC_gh%%`` entry would
            otherwise shadow the fake ``gh`` on ``PATH``; ``BASH_ENV``
            removed, because a non-interactive ``bash -c`` sources the file it
            names before running a step, and this host's names a startup
            script that defines a real-credential ``gh`` wrapper; the release
            context GitHub injects, so a step that names the tag resolves it;
            and `overrides` applied last.
        """
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in {"GH_TOKEN", "GITHUB_TOKEN", "GIT_SSH_COMMAND", "BASH_ENV"}
            and not key.startswith("BASH_FUNC_")
        }
        env["PATH"] = os.pathsep.join([str(self.root / "tools"), os.defpath])
        env["FAKE_RELEASE_JOURNAL"] = str(self.journal)
        env["FAKE_RELEASE_GITHUB"] = str(self.github)
        env["FAKE_RELEASE_PYPI"] = str(self.pypi)
        env["FAKE_RELEASE_STATE"] = str(self.root / "release-state.json")
        env["FAKE_RELEASE_ATTESTATIONS"] = str(self.attestations)
        env["GITHUB_OUTPUT"] = str(self.root / "github-output")
        env["GITHUB_REF_NAME"] = RELEASE_TAG
        # The runner context and the job-level `env:` the workflow derives from
        # it. GitHub resolves those expressions before the step runs; the fakes
        # stand in for that resolution, so a step reads the same variables here
        # as it does on a runner.
        env["GITHUB_REF"] = RELEASE_REF
        env["GITHUB_SHA"] = BUILD_COMMIT
        env["GH_REPO"] = RELEASE_REPO
        env["GITHUB_RUN_ID"] = "7"
        env["GITHUB_RUN_ATTEMPT"] = "1"
        env.update(overrides)
        return env


def _write_record(directory: pathlib.Path, record: list[dict[str, object]]) -> None:
    """Write one attestation beside the records already in `directory`."""
    taken = {path.stem for path in directory.iterdir()}
    index = 0
    while f"record-{index}" in taken:
        index += 1
    (directory / f"record-{index}.json").write_text(
        json.dumps(record), encoding="utf-8"
    )


def _write_tool(tools: pathlib.Path, name: str, body: str) -> None:
    """Write an executable ``/bin/sh`` stand-in called `name` into `tools`."""
    tools.mkdir(parents=True, exist_ok=True)
    tool = tools / name
    tool.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR)


def fake_release(root: pathlib.Path) -> FakeRelease:
    """Create a scripted release state and recording fakes under `root`.

    The layout the publishing jobs build for themselves is reproduced: a
    ``github-assets`` directory holding one file per release asset, a
    ``pypi-files`` directory holding one file per published file, and a
    ``tools`` directory on ``PATH`` holding ``gh``, ``curl``, ``python3`` and a
    no-op ``sleep``.

    Parameters
    ----------
    root
        A temporary directory, normally pytest's ``tmp_path``.

    Returns
    -------
    FakeRelease
        The fake, with both state directories created empty.
    """
    tools = root / "tools"
    for tool in ("gh", "curl"):
        # The entry point is a module of the `tests` package, so the repository
        # root has to be importable when it runs as a script: the interpreter
        # would otherwise put only the support directory on `sys.path`.
        body = (
            f'PYTHONPATH="{_REPOSITORY_ROOT}" '
            f'exec "{sys.executable}" "{_DISPATCH}" {tool} "$@"'
        )
        _write_tool(tools, tool, body)
    _write_tool(tools, "python3", f'exec "{sys.executable}" "$@"')
    # The index lookup sleeps between retries; a test must not pay for it.
    _write_tool(tools, "sleep", ":")
    fake = FakeRelease(root)
    fake.github.mkdir(parents=True, exist_ok=True)
    fake.pypi.mkdir(parents=True, exist_ok=True)
    fake.attestations.mkdir(parents=True, exist_ok=True)
    return fake


__all__ = [
    "BUILD_COMMIT",
    "FILES_URL",
    "RELEASE_TAG",
    "SIGNED_BY_RELEASE",
    "Attested",
    "Call",
    "FakeRelease",
    "fake_release",
]
