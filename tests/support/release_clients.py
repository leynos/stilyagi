"""The ``gh release`` and ``curl`` stand-ins a publishing step runs against.

``release.yml`` reaches the network only through those two programs, so a test
of a publishing step replaces them for the duration. Each keeps its state in
the directory the environment names: one file per GitHub Release asset, one
file per PyPI file, and a journal of the argument vectors that were run. Like
the services they stand in for, neither overwrites what it holds: a second
upload of an existing asset name fails, exactly as ``gh`` does without
``--clobber``, and a download of a file PyPI does not list exits as
``curl --fail`` would.

``gh attestation`` is the third program the workflow runs, and its stand-in
lives in ``tests/support/release_attestations.py``: its policy flags and record
shape are a subject of their own. Both modules are standard-library only, and
neither imports the other, so the entry point that wires them together
(``tests/support/release_fake.py``) is the only place they are combined.
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

#: The repository and ref the scripted runs release from, as GitHub reports
#: them. The attestation policy names both, so the fake checks both.
RELEASE_REPO: typ.Final = "leynos/stilyagi"
RELEASE_REF: typ.Final = f"refs/tags/{RELEASE_TAG}"
RELEASE_WORKFLOW: typ.Final = "/.github/workflows/release.yml"


def journal(args: cabc.Sequence[str]) -> None:
    """Append one program invocation to the shared call journal.

    The vector is recorded whole, the program name first, exactly as the
    stand-in received it: a test reads this file to learn which commands ran,
    and a test over the journal must be able to check that too.
    """
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


#: The ``gh`` options whose value is the next argument.
_VALUED: typ.Final = frozenset({
    "--bundle",
    "--cert-identity",
    "--cert-identity-regex",
    "--cert-oidc-issuer",
    "--custom-trusted-root",
    "--digest-alg",
    "--dir",
    "--format",
    "--hostname",
    "--jq",
    "--json",
    "--limit",
    "--notes",
    "--notes-file",
    "--owner",
    "--pattern",
    "--predicate-type",
    "--repo",
    "--signer-digest",
    "--signer-repo",
    "--signer-workflow",
    "--source-digest",
    "--source-ref",
    "--target",
    "--template",
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
            # The real flag accepts only these two spellings and rejects the
            # rest, so the fake must too. ``release.yml`` passes
            # ``--prerelease="${IS_PRERELEASE}"``, whose value comes from a
            # script output; an empty one would otherwise record a final
            # release here and fail only on a real tag run.
            if not arg.startswith(option):
                continue
            value = arg.removeprefix(option)
            if value not in {"true", "false"}:
                print(f"invalid boolean for --{name}: {value!r}", file=sys.stderr)
                return 1
            state[name] = value == "true"
    path.write_text(json.dumps(state), encoding="utf-8")
    return 0


def gh(args: cabc.Sequence[str]) -> int:
    """Serve the ``gh release`` calls the release workflow makes.

    Parameters
    ----------
    args
        The argument vector after the program name, so ``args[0]`` is the
        top-level command and ``args[1]`` its subcommand.

    Returns
    -------
    int
        The exit status the real command would have.
    """
    command = args[0] if args else ""
    if command == "release":
        return _release(args[1:])
    return 0


def _release(args: cabc.Sequence[str]) -> int:
    """Serve the ``gh release`` subcommands the workflow calls."""
    command = args[0] if args else ""
    if command == "view":
        return _view()
    if command in {"create", "edit"}:
        # The tag is an operand either way; only the options are read.
        return _create(args) if command == "create" else _edit(args)
    if command == "upload":
        return _upload(args[1:])
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


__all__ = [
    "FILES_URL",
    "RELEASE_REF",
    "RELEASE_REPO",
    "RELEASE_TAG",
    "RELEASE_WORKFLOW",
    "curl",
    "gh",
    "journal",
]
