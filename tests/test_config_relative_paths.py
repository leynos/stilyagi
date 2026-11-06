"""Tests for the pure config-relative spelling used by per-file ignore globs.

The spelling function deliberately answers from the two paths it is given: it
resolves nothing, reads no working directory, and touches no filesystem. These
tests pin that purity, because it is what lets the check boundary report a
resolution failure against the file being checked instead of surfacing later as
an unexplained rules-phase error.
"""

import pathlib
import typing as typ

from stilyagi.config.paths import config_relative_path

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import pytest

_DIFFERENT_DRIVES = "different drives"


def _forbid_filesystem_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Make every path operation that reads the environment fail loudly."""
    forbidden = ("cwd", "resolve", "expanduser", "stat", "exists", "is_dir")

    def refuse(name: str) -> cabc.Callable[..., typ.NoReturn]:
        """Return a replacement for one forbidden ``Path`` operation."""

        def raiser(*_args: object, **_kwargs: object) -> typ.NoReturn:
            """Fail the test if the spelling function makes this call."""
            message = f"config_relative_path must not call Path.{name}"
            raise AssertionError(message)

        return raiser

    for name in forbidden:
        monkeypatch.setattr(pathlib.Path, name, refuse(name))


def test_target_inside_anchor_is_a_plain_relative_path() -> None:
    """A target below the anchor needs no walk-up segments."""
    anchor = pathlib.Path("/work/docs")

    assert config_relative_path(anchor / "a.md", anchor) == "a.md", (
        "expected a target beside the anchor to be named by its basename"
    )
    assert config_relative_path(anchor / "sub" / "b.md", anchor) == "sub/b.md", (
        "expected a nested target to keep its anchor-relative path"
    )


def test_target_outside_anchor_walks_up() -> None:
    """A target in a sibling tree is spelled with ``../`` segments."""
    anchor = pathlib.Path("/work/docs")

    result = config_relative_path(pathlib.Path("/work/notes/c.md"), anchor)

    assert result == "../notes/c.md", (
        f"expected a target outside the anchor to walk up, got {result}"
    )


def test_the_spelling_reads_neither_the_filesystem_nor_the_working_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The answer comes from the two arguments alone, so it cannot fail."""
    _forbid_filesystem_access(monkeypatch)

    result = config_relative_path(
        pathlib.Path("/work/docs/sub/b.md"), pathlib.Path("/work/docs")
    )

    assert result == "sub/b.md", (
        "expected the pure spelling to answer without resolving either path"
    )


def test_target_without_a_relative_spelling_falls_back_to_absolute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A target on another Windows drive cannot be related to the anchor."""
    anchor = pathlib.Path("/work/docs")
    target = pathlib.Path("C:/elsewhere/e.md")

    def raiser(
        self: pathlib.Path,
        other: pathlib.Path,
        *,
        walk_up: bool = False,
    ) -> pathlib.Path:
        """Match the builtin that pathlib raises for unrelated roots."""
        del self, other, walk_up
        raise ValueError(_DIFFERENT_DRIVES)

    monkeypatch.setattr(pathlib.Path, "relative_to", raiser)

    assert config_relative_path(target, anchor) == "C:/elsewhere/e.md", (
        "expected an unrelated anchor to fall back to the absolute POSIX path"
    )
