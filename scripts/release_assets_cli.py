#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""Command-line entry point for the release-asset reconciliation commands.

``release.yml`` places ``scripts/`` on ``PYTHONPATH`` and runs this module from
the workspace root as ``python -m release_assets_cli``, under the Python 3.14
each job installs, with the standard library alone: it executes inside the
job that holds the PyPI publishing token, so it resolves no third-party code
(Cyclopts or Cuprum) at release time, and every network call stays in the
workflow's ``curl`` and ``gh`` steps. That is the documented exception to the
scripting standards' Cyclopts and Cuprum defaults. Each subcommand is one step
of ``release.yml``: ``carryover`` (``draft-release``), ``stage-pypi``
(``publish-pypi``), then ``stage-github``, ``check-fetched``,
``check-provenance``, ``bundles``, ``check-bundle``, and ``verify``
(``publish-release``). The reconciliation logic itself lives in
``scripts/release_assets.py``; this module only wires it to ``argparse`` and
the workflow's ``GITHUB_OUTPUT`` protocol.
"""

import argparse
import sys
import typing as typ
from pathlib import Path

from release_assets import (
    ReleaseAssetError,
    State,
    carryover,
    stage_pypi,
    write_output,
)
from release_bundles import check_release_bundle, held_bundles
from release_github_upload import (
    check_fetched,
    check_provenance,
    stage_github,
    verify,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc


def _parser() -> argparse.ArgumentParser:
    """Build the command-line interface the release workflow calls."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=_COMMANDS)
    parser.add_argument("--publish", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--index", type=Path)
    parser.add_argument("--github-files", type=Path)
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--bundles", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--pypi-published",
        action="store_true",
        help=(
            "this workflow already published to PyPI for this release, so an "
            "artefact the index does not list means the index is stale"
        ),
    )
    return parser


def _path(args: argparse.Namespace, option: str) -> Path:
    """Return a path option the chosen command requires."""
    value = getattr(args, option)
    if value is None:
        msg = f"--{option.replace('_', '-')} is required for {args.command}"
        raise ReleaseAssetError(msg)
    return value


def _carryover(state: State, args: argparse.Namespace) -> None:
    """Print the names to download from the GitHub Release, one per line."""
    del args
    for name in carryover(state):
        print(name)


def _stage_pypi(state: State, args: argparse.Namespace) -> None:
    """Stage PyPI's upload set and report whether anything remains."""
    github_files = _path(args, "github_files")
    remaining = stage_pypi(state, github_files, args.provenance)
    write_output("remaining", value=remaining)


def _stage_github(state: State, args: argparse.Namespace) -> None:
    """Stage GitHub's upload set and print PyPI's files as TSV rows."""
    output = _path(args, "output")
    fetch = stage_github(
        state,
        _path(args, "bundles"),
        output,
        pypi_published=args.pypi_published,
    )
    for name, url in fetch:
        print(f"{name}\t{url}")
    write_output("pending", value=bool(fetch) or any(output.iterdir()))


def _check_fetched(state: State, args: argparse.Namespace) -> None:
    """Check every fetched PyPI file against PyPI's digest."""
    check_fetched(state, _path(args, "output"))


def _check_provenance(state: State, args: argparse.Namespace) -> None:
    """Refuse an upload set any of whose files has no verified attestation."""
    del state
    check_provenance(_path(args, "output"), _path(args, "provenance"))


def _bundles(state: State, args: argparse.Namespace) -> None:
    """Print the Release's provenance bundle names, one per line."""
    del args
    for name in held_bundles(state):
        print(name)


def _check_bundle(state: State, args: argparse.Namespace) -> None:
    """Refuse a Release none of whose bundles attests as it now stands.

    Staging has already refused to attach a bundle that does not cover what it
    staged, so this is the check on the Release itself: it reads the bundles
    the Release holds and requires one of them to name every asset there. It
    is what catches a Release an upload from elsewhere has left unattested.
    """
    check_release_bundle(state, _path(args, "provenance"))


def _verify(state: State, args: argparse.Namespace) -> None:
    """Fail on any artefact the two destinations disagree on."""
    del args
    problems = verify(state)
    if problems:
        raise ReleaseAssetError("; ".join(problems))
    print("PyPI and the GitHub Release hold the same bytes for every artefact.")


_COMMANDS: dict[str, cabc.Callable[[State, argparse.Namespace], None]] = {
    "carryover": _carryover,
    "bundles": _bundles,
    "stage-pypi": _stage_pypi,
    "stage-github": _stage_github,
    "check-fetched": _check_fetched,
    "check-provenance": _check_provenance,
    "check-bundle": _check_bundle,
    "verify": _verify,
}


def main(argv: cabc.Sequence[str] | None = None) -> int:
    """Run one reconciliation command; report failures as annotations.

    Parameters
    ----------
    argv
        The argument vector, without the program name. Defaults to
        ``sys.argv[1:]``.

    Returns
    -------
    int
        ``0`` when the command completed, ``1`` when it rejected its
        inputs. The rejection is reported as a GitHub ``::error::``
        annotation so the failing step names the artefact.

    Examples
    --------
    A command that cannot read its inputs exits non-zero rather than
    raising, because the workflow needs a readable step failure:

    >>> main(
    ...     ["stage-pypi", "--publish", "/nonexistent", "--assets", "absent.json"]
    ... )
    1
    """
    args = _parser().parse_args(argv)
    try:
        state = State.load(args.publish, args.index, args.assets)
        _COMMANDS[args.command](state, args)
    except (ReleaseAssetError, OSError, KeyError, ValueError) as error:
        print(f"::error title=release-assets::{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
