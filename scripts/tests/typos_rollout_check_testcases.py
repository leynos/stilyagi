"""Test exact phrase-policy enforcement through its standalone runner."""

import importlib
import pathlib
import typing as typ

import pytest

if typ.TYPE_CHECKING:
    import types

    from cmd_mox import CmdMox

pytest_plugins = ("cmd_mox.pytest_plugin",)

SCRIPTS = pathlib.Path(__file__).resolve().parents[1]
PROHIBITED = "hand" + "-written"
TITLE_PROHIBITED = "Hand" + "-written"
FINDINGS_EXIT_CODE = 2


@pytest.fixture
def checker(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    """Import the standalone phrase checker from the scripts directory."""
    monkeypatch.syspath_prepend(str(SCRIPTS))
    importlib.invalidate_caches()
    return importlib.import_module("typos_rollout_check")


def initialize(path: pathlib.Path, files: dict[str, str]) -> None:
    """Create a small tracked-file fixture."""
    for relative, content in files.items():
        target = path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def expect_tracked_files(
    cmd_mox: CmdMox, repository: pathlib.Path, files: dict[str, str]
) -> None:
    """Expect Git to enumerate the fixture files as tracked paths."""
    output = "\0".join(sorted(files)) + "\0"
    cmd_mox.mock("git").with_args("-C", str(repository), "ls-files", "-z").returns(
        stdout=output
    )


def policy_files(*, local_phrase: str = "") -> dict[str, str]:
    """Return minimal generated, shared, and local policy documents."""
    return {
        "typos.toml": (
            f"# Policy for {PROHIBITED} corrections.\n"
            '[files]\nextend-exclude = ["*.md", "!README.md"]\n\n'
            '[default]\nextend-ignore-re = ["`[^`\\\\n]+`"]\n'
        ),
        ".typos-oxendict-base.toml": (
            f'[phrases.corrections]\n"{PROHIBITED}" = "handwritten"\n'
        ),
        "typos.local.toml": local_phrase,
    }


def test_load_policy_combines_shared_and_local_policy(
    checker: types.ModuleType, tmp_path: pathlib.Path
) -> None:
    """Load shared phrases and generated scan settings."""
    initialize(
        tmp_path,
        policy_files(
            local_phrase='[phrases.corrections]\n"fit-for-purpose" = "suitable"\n'
        ),
    )

    policy = checker.load_policy(tmp_path)

    assert policy.phrase_corrections == (  # noqa: S101 -- isolated test assertion.
        ("fit-for-purpose", "suitable"),
        (PROHIBITED, "handwritten"),
    )
    assert policy.ignore_patterns == (  # noqa: S101 -- isolated test assertion.
        r"`[^`\n]+`",
    )
    assert policy.excluded_files == (  # noqa: S101 -- isolated test assertion.
        "*.md",
        "!README.md",
    )


@pytest.mark.parametrize(
    ("invalid_policy", "message"),
    [
        pytest.param(
            (".typos-oxendict-base.toml", "phrases = []\n"),
            "'phrases' must be a table",
            id="shared-phrases-table",
        ),
        pytest.param(
            ("typos.local.toml", "[phrases]\ncorrections = []\n"),
            "'corrections' must be a table",
            id="local-corrections-table",
        ),
        pytest.param(
            (
                "typos.toml",
                "[files]\nextend-exclude = [1]\n[default]\nextend-ignore-re = []\n",
            ),
            "'extend-exclude' must be a list of strings",
            id="generated-exclusions-list",
        ),
    ],
)
def test_load_policy_rejects_malformed_shapes(
    checker: types.ModuleType,
    tmp_path: pathlib.Path,
    invalid_policy: tuple[str, str],
    message: str,
) -> None:
    """Reject malformed shared, local, and generated policy values."""
    relative, malformed = invalid_policy
    files = policy_files()
    files[relative] = malformed
    initialize(tmp_path, files)

    with pytest.raises(TypeError, match=message):
        checker.load_policy(tmp_path)


def test_checker_preserves_boundaries_masking_and_exclusions(
    checker: types.ModuleType, tmp_path: pathlib.Path, cmd_mox: CmdMox
) -> None:
    """Report phrases only when boundaries and policy allow them."""
    files = {
        "README.md": (
            f"{PROHIBITED}\n{TITLE_PROHIBITED} prose\n"
            "pre-hand"
            "-written\n"
            f"`{PROHIBITED}`\n"
        ),
        "skip.md": f"{PROHIBITED}\n",
        **policy_files(),
    }
    initialize(tmp_path, files)
    expect_tracked_files(cmd_mox, tmp_path, files)

    findings = checker.check_phrase_corrections(tmp_path, checker.load_policy(tmp_path))

    assert [  # noqa: S101 -- isolated test assertion.
        (item.line, item.phrase) for item in findings
    ] == [
        (1, PROHIBITED),
        (2, TITLE_PROHIBITED),
    ]


@pytest.mark.parametrize(
    ("text", "patterns"),
    [
        pytest.param("plain text", (), id="unmasked"),
        pytest.param("before `masked` after", (r"`[^`]+`",), id="single-line"),
        pytest.param(
            "before\n<!-- masked\nspan -->\nafter",
            (r"(?s)<!--.*?-->",),
            id="multiline",
        ),
    ],
)
def test_masking_preserves_offsets(
    checker: types.ModuleType, text: str, patterns: tuple[str, ...]
) -> None:
    """Mask ignored regions without changing source positions."""
    masked = checker._masked(text, patterns)

    assert len(masked) == len(text)  # noqa: S101 -- isolated test assertion.
    assert [  # noqa: S101 -- isolated test assertion.
        index for index, value in enumerate(masked) if value == "\n"
    ] == [index for index, value in enumerate(text) if value == "\n"]


def test_checker_surfaces_decode_errors(
    checker: types.ModuleType, tmp_path: pathlib.Path, cmd_mox: CmdMox
) -> None:
    """Fail when eligible tracked text is not valid UTF-8."""
    files = {"README.md": "placeholder\n", **policy_files()}
    initialize(tmp_path, files)
    expect_tracked_files(cmd_mox, tmp_path, files)
    (tmp_path / "README.md").write_bytes(b"\xff")

    with pytest.raises(UnicodeDecodeError):
        checker.check_phrase_corrections(tmp_path, checker.load_policy(tmp_path))


def test_checker_skips_indexed_path_absent_during_enumeration(
    checker: types.ModuleType, tmp_path: pathlib.Path, cmd_mox: CmdMox
) -> None:
    """Ignore an intentionally deleted path that remains in the Git index."""
    files = {"deleted.txt": f"Prefer {PROHIBITED}.\n", **policy_files()}
    initialize(tmp_path, files)
    (tmp_path / "deleted.txt").unlink()
    expect_tracked_files(cmd_mox, tmp_path, files)

    findings = checker.check_phrase_corrections(tmp_path, checker.load_policy(tmp_path))

    assert not findings  # noqa: S101 -- isolated test assertion.


def test_checker_surfaces_path_removed_after_enumeration(
    checker: types.ModuleType,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail closed when a previously enumerated path disappears before read."""
    files = {"README.md": f"Prefer {PROHIBITED}.\n", **policy_files()}
    initialize(tmp_path, files)

    def enumerate_then_remove(_: pathlib.Path) -> tuple[pathlib.Path, ...]:
        """Return the tracked path after simulating a post-enumeration removal."""
        (tmp_path / "README.md").unlink()
        return (pathlib.Path("README.md"),)

    monkeypatch.setattr(checker, "_tracked", enumerate_then_remove)

    with pytest.raises(FileNotFoundError):
        checker.check_phrase_corrections(tmp_path, checker.load_policy(tmp_path))


def test_main_reports_location_and_exit_two(
    checker: types.ModuleType,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    cmd_mox: CmdMox,
) -> None:
    """Return two and preserve the source diagnostic."""
    files = {"README.md": f"Prefer {PROHIBITED}.\n", **policy_files()}
    initialize(tmp_path, files)
    expect_tracked_files(cmd_mox, tmp_path, files)

    with pytest.raises(SystemExit) as exit_status:
        checker.app(["--repository", str(tmp_path)])

    assert (  # noqa: S101 -- isolated test assertion.
        exit_status.value.code == FINDINGS_EXIT_CODE
    )
    assert capsys.readouterr().out == (  # noqa: S101 -- isolated test assertion.
        f"README.md:1:8: {PROHIBITED} -> handwritten\n"
    )
