"""The two network clients' stand-ins, and the dispatch a fake re-executes.

``release.yml`` reaches the network only through ``curl`` and ``gh``, so a test
of a publishing step replaces those two programs with these. Each keeps its
state in the directory the environment names: one file per GitHub Release
asset, one file per PyPI file, and a journal of argument vectors. Like the
services they stand in for, neither overwrites what it holds: a second upload
of an existing asset name fails, exactly as ``gh`` does without ``--clobber``,
and a download of a file PyPI does not list exits as ``curl --fail`` would.

Every fake starts with ``#!/bin/sh`` and re-executes this module's interpreter,
so the program that serves it is the one pytest runs under rather than whatever
``python3`` a caller's ``PATH`` happens to resolve. This module is
standard-library only precisely so that it can be that entry point: importing
pytest or a support helper here would cost every fake invocation the test
session's import graph.
"""

import hashlib
import json
import os
import pathlib
import shutil
import sys
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

#: The base URL the fake PyPI serves its files under. The index it renders
#: names every file with it, and ``curl`` strips it to find the file it holds.
FILES_URL: typ.Final = "https://files.example.test/packages/"

#: The tag the scripted runs release, so a step that names the tag resolves it.
RELEASE_TAG: typ.Final = "v0.2.0"


def _journal(args: cabc.Sequence[str]) -> None:
    """Append one invocation to the shared call journal."""
    record = json.dumps(list(args))
    with pathlib.Path(os.environ["FAKE_RELEASE_JOURNAL"]).open(
        "a", encoding="utf-8"
    ) as journal:
        journal.write(record + "\n")


def _directory(variable: str) -> pathlib.Path:
    """Return the state directory `variable` names, creating it if absent."""
    directory = pathlib.Path(os.environ[variable])
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _digest(path: pathlib.Path) -> str:
    """Return the SHA-256 hex digest of one file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assets_json() -> str:
    """Render the release's assets as ``gh release view --json assets`` does."""
    assets = [
        {"name": path.name, "digest": f"sha256:{_digest(path)}"}
        for path in sorted(_directory("FAKE_RELEASE_GITHUB").iterdir())
    ]
    return json.dumps({"assets": assets})


def _view() -> int:
    """Answer ``gh release view`` with the scripted exit status, then the list."""
    if os.environ.get("FAKE_RELEASE_VIEW_STATUS", "0") != "0":
        return int(os.environ["FAKE_RELEASE_VIEW_STATUS"])
    print(_assets_json())
    return 0


def _upload(args: cabc.Sequence[str]) -> int:
    """Attach the operands after the tag, refusing a name already held."""
    assets = _directory("FAKE_RELEASE_GITHUB")
    if "--clobber" in args:
        print("the fake release refuses --clobber", file=sys.stderr)
        return 1
    for name in _operands(args)[1:]:
        target = assets / pathlib.Path(name).name
        if target.exists():
            print(f"asset {target.name} already exists", file=sys.stderr)
            return 1
        shutil.copyfile(name, target)
    return 0


def _download(args: cabc.Sequence[str]) -> int:
    """Copy the asset ``--pattern`` names into ``--dir``."""
    pattern = args[args.index("--pattern") + 1]
    source = _directory("FAKE_RELEASE_GITHUB") / pattern
    if not source.exists():
        print(f"release asset {pattern} not found", file=sys.stderr)
        return 1
    target = pathlib.Path(args[args.index("--dir") + 1])
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target / pattern)
    return 0


#: The ``gh release`` options whose value is the next argument.
_VALUED: typ.Final = frozenset({
    "--dir",
    "--json",
    "--notes",
    "--notes-file",
    "--pattern",
    "--repo",
    "--target",
    "--title",
})


def _operands(args: cabc.Sequence[str]) -> list[str]:
    """Return the arguments that are neither an option nor an option's value.

    ``--flag=value`` counts as one option; a bare ``--flag`` takes the next
    argument with it. What remains is an operand such as the tag or a file.

    Returns
    -------
    list[str]
        The operands, in the order they were given.
    """
    operands: list[str] = []
    remaining = iter(args)
    for arg in remaining:
        if arg.startswith("-"):
            if arg not in _VALUED:
                continue
            next(remaining, None)
        else:
            operands.append(arg)
    return operands


def _create(args: cabc.Sequence[str]) -> int:
    """Answer ``gh release create``, refusing a tag that already has a release."""
    if os.environ.get("FAKE_RELEASE_CREATE_STATUS") == "1":
        print("release already exists", file=sys.stderr)
        return 1
    _directory("FAKE_RELEASE_GITHUB")
    # A created release is a draft until an ``edit`` publishes it, so record
    # what the arguments asked for exactly as the real command would.
    state = {
        "draft": "--draft" in args,
        "prerelease": "--prerelease" in args,
    }
    pathlib.Path(os.environ["FAKE_RELEASE_STATE"]).write_text(
        json.dumps(state), encoding="utf-8"
    )
    return 0


def _edit(args: cabc.Sequence[str]) -> int:
    """Answer ``gh release edit``, recording the state it leaves behind."""
    path = pathlib.Path(os.environ["FAKE_RELEASE_STATE"])
    if not path.exists():
        print("release not found", file=sys.stderr)
        return 1
    state = json.loads(path.read_text(encoding="utf-8"))
    for arg in args:
        for name in ("draft", "prerelease"):
            option = f"--{name}="
            if arg.startswith(option):
                state[name] = arg.removeprefix(option) == "true"
    path.write_text(json.dumps(state), encoding="utf-8")
    return 0


def gh(args: cabc.Sequence[str]) -> int:
    """Serve the ``gh release`` calls the release workflow makes."""
    command = args[1] if len(args) > 1 else ""
    if command == "view":
        return _view()
    if command in {"create", "edit"}:
        # The tag is an operand either way; only the options are read.
        return _create(args) if command == "create" else _edit(args)
    if command == "upload":
        return _upload(args[2:])
    if command == "download":
        return _download(args)
    return 0


def _next_status() -> str:
    """Return the next scripted index status; the last one repeats."""
    statuses = os.environ.get("FAKE_RELEASE_CURL_STATUSES", "200").split(",")
    counter = pathlib.Path(os.environ["FAKE_RELEASE_JOURNAL"]).with_suffix(
        ".index-count"
    )
    served = int(counter.read_text(encoding="utf-8")) if counter.exists() else 0
    counter.write_text(str(served + 1), encoding="utf-8")
    return statuses[min(served, len(statuses) - 1)]


def _index_json() -> str:
    """Render the PyPI state as a PEP 691 JSON simple index."""
    files = [
        {
            "filename": path.name,
            "url": f"{FILES_URL}{path.name}",
            "hashes": {"sha256": _digest(path)},
        }
        for path in sorted(_directory("FAKE_RELEASE_PYPI").iterdir())
    ]
    return json.dumps({"name": "stilyagi", "files": files})


def _output_path(args: cabc.Sequence[str]) -> pathlib.Path | None:
    """Return the file ``--output`` (or ``-o``) names, if either is given."""
    for option in ("--output", "-o"):
        if option in args:
            return pathlib.Path(args[args.index(option) + 1])
    return None


def curl(args: cabc.Sequence[str]) -> int:
    """Serve the index or one file, writing ``%{http_code}`` if asked."""
    url = args[-1]
    output = _output_path(args)
    if url.endswith("/simple/stilyagi/"):
        status = _next_status()
        if output is not None:
            output.write_text(
                _index_json() if status == "200" else "{}", encoding="utf-8"
            )
        if "--write-out" in args:
            print(status, end="")
        # curl exits non-zero, still writing ``000``, when nothing answered.
        return 7 if status == "000" else 0
    source = _directory("FAKE_RELEASE_PYPI") / url.removeprefix(FILES_URL)
    if not source.exists():
        return 22
    if output is None:
        print(source.read_text(encoding="utf-8"), end="")
        return 0
    shutil.copyfile(source, output)
    return 0


def main(argv: cabc.Sequence[str] | None = None) -> int:
    """Dispatch to the stand-in named by the first argument."""
    args = list(sys.argv[1:] if argv is None else argv)
    tool, rest = args[0], args[1:]
    _journal(args)
    return gh(rest) if tool == "gh" else curl(rest)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "FILES_URL",
    "RELEASE_TAG",
    "curl",
    "gh",
    "main",
]
