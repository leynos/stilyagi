"""Real CLI wiring for persistent extraction cache and strict bypass."""

import typing as typ

import pytest
from stilyagi import cli
from stilyagi.cache.model import CACHE_NAMESPACE_NAME

if typ.TYPE_CHECKING:
    import pathlib


def _cache_state(root: pathlib.Path) -> tuple[tuple[str, bytes, int], ...]:
    """Capture cache file bytes and modification times without directory noise."""
    if not root.exists():
        return ()
    return tuple(
        sorted(
            (
                path.relative_to(root).as_posix(),
                path.read_bytes(),
                path.stat().st_mtime_ns,
            )
            for path in root.rglob("*")
            if path.is_file()
        )
    )


@pytest.mark.parametrize("command", ["check", "dump-ir"])
def test_cli_no_cache_is_a_cold_and_warm_zero_write_bypass(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    """Keep cold bypass empty and leave a warm cache byte-for-byte untouched."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.md").write_bytes("# Café\r\n".encode())
    cache_parent = tmp_path / ".stilyagi_cache"

    assert cli.main([command, "--no-cache", "notes.md"]) == 0, (
        "a cold strict bypass must succeed"
    )
    cold_output = capsys.readouterr()
    assert not cold_output.err, "a successful cold bypass must not report an error"
    assert not cache_parent.exists(), "a cold bypass must not create cache storage"

    assert cli.main([command, "notes.md"]) == 0, (
        "the ordinary cacheable command must succeed"
    )
    warm_output = capsys.readouterr()
    before = _cache_state(cache_parent / CACHE_NAMESPACE_NAME)
    assert before, "the ordinary command must populate the persistent cache"

    assert cli.main([command, "--no-cache", "notes.md"]) == 0, (
        "a warm strict bypass must succeed"
    )
    bypass_output = capsys.readouterr()

    assert _cache_state(cache_parent / CACHE_NAMESPACE_NAME) == before, (
        "a warm bypass must not change cache bytes or modification times"
    )
    if command == "dump-ir":
        assert bypass_output.out == warm_output.out, (
            "dump-ir output must not depend on cache selection"
        )
    else:
        assert bypass_output.out == warm_output.out, (
            "check output must not depend on cache selection"
        )
