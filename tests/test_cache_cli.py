"""Real CLI wiring for the persistent extraction cache and its strict bypass.

Two boundaries are covered. The first is the production path: `cli.main`
constructs the extraction service itself, so the flag has only to reach a
service the command built. The second is an injected service, which is where
the flag can silently fail to apply -- a caller's service carries whatever
policy its own constructor was given, and `--no-cache` reaches it only if the
command boundary re-applies the request. Both are exercised because a test
that only drove `cli.main` would stay green while an embedding caller's cache
kept reading and writing storage under a flag that says not to.
"""

import io
import typing as typ

import pytest
from stilyagi import cli, cli_dump_ir
from stilyagi.cache.extraction import CacheExtractionService, CacheServiceConfig
from stilyagi.cache.model import CACHE_NAMESPACE_NAME
from stilyagi.cli_args import CheckOptions, DumpIrOptions

from tests.support.cache_extraction import (
    counting_extractor,
    forbidden_cache_callback,
)

if typ.TYPE_CHECKING:
    import pathlib

    from stilyagi.cache.extraction import (
        BuiltinSignatureFactory,
        CacheStoreFactory,
        NativeDigestFactory,
    )


#: The source every case runs over; one heading is enough to be cacheable.
SOURCE = "# Café\r\n"


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


def _forbidden_service(
    root: pathlib.Path,
    calls: list[str],
) -> CacheExtractionService:
    """Build a service whose cache-only collaborators fail if reached.

    Fingerprinting and store construction are exactly the work `--no-cache`
    promises not to do, so each is replaced with a collaborator that raises
    with the operation's name. A bypass that still reached one would fail at
    the operation rather than merely reporting a counter.

    Returns
    -------
    CacheExtractionService
        A real service that is free to extract but not to touch storage.
    """
    forbidden = forbidden_cache_callback(
        "a --no-cache run reached a persistent-cache-only collaborator"
    )
    return CacheExtractionService(
        CacheServiceConfig(
            invocation_cwd=root,
            package_version="test-version",
            extractor=counting_extractor(calls),
            native_digest_factory=typ.cast("NativeDigestFactory", forbidden),
            builtin_signature_factory=typ.cast("BuiltinSignatureFactory", forbidden),
            storage_factory=typ.cast("CacheStoreFactory", forbidden),
        )
    )


def _run_command(
    command: str,
    *,
    no_cache: bool,
    service: CacheExtractionService | None,
) -> int:
    """Run one command in-process, injecting `service` when it is supplied."""
    if command == "check":
        return cli.run_check(
            CheckOptions(targets=("notes.md",), no_cache=no_cache),
            collaborators=cli.CheckCollaborators(
                output=io.StringIO(),
                extraction_cache=service,
            ),
        )
    return cli_dump_ir.run_dump_ir(
        DumpIrOptions(targets=("notes.md",), no_cache=no_cache),
        collaborators=cli_dump_ir.DumpIrCollaborators(
            output=io.BytesIO(),
            cache=service,
        ),
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
    (tmp_path / "notes.md").write_bytes(SOURCE.encode())
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
    assert bypass_output.out == warm_output.out, (
        f"{command} output must not depend on cache selection"
    )


@pytest.mark.parametrize("command", ["check", "dump-ir"])
def test_an_injected_cache_honours_no_cache_on_a_cold_run(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    """Apply the flag to a supplied service, not only to one built here.

    The service below was constructed without the flag, so it can only stay off
    storage because the command boundary applied the request to it. Each
    cache-only collaborator raises, which makes the failure name the operation
    that ran: a boundary that forgot to pass the request on would fingerprint
    before it ever opened storage.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.md").write_bytes(SOURCE.encode())
    calls: list[str] = []

    status = _run_command(
        command,
        no_cache=True,
        service=_forbidden_service(tmp_path, calls),
    )

    assert status == 0, "a cold strict bypass must succeed through an injected cache"
    assert calls == [SOURCE], (
        f"expected the run to extract the source once, got {calls}"
    )
    assert not (tmp_path / ".stilyagi_cache").exists(), (
        "an injected service must not create cache storage under --no-cache"
    )


@pytest.mark.parametrize("command", ["check", "dump-ir"])
def test_an_injected_cache_leaves_a_warm_cache_untouched_under_no_cache(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    """Leave a warm entry byte-identical, and open no store to read it.

    The warm run goes through the production path so the entry is the one a
    user really has. The bypass run then supplies its own service, whose store
    factory raises: a read would have had to open storage first, so untouched
    bytes plus an unrun factory together rule out both halves of the traffic.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.md").write_bytes(SOURCE.encode())
    assert _run_command(command, no_cache=False, service=None) == 0, (
        "the warm-up run must succeed through the production cache"
    )
    namespace = tmp_path / ".stilyagi_cache" / CACHE_NAMESPACE_NAME
    before = _cache_state(namespace)
    assert before, "the warm-up run must populate the persistent cache"
    calls: list[str] = []

    status = _run_command(
        command,
        no_cache=True,
        service=_forbidden_service(tmp_path, calls),
    )

    assert status == 0, "a warm strict bypass must succeed through an injected cache"
    assert calls == [SOURCE], (
        f"expected the bypass to extract the source once, got {calls}"
    )
    assert _cache_state(namespace) == before, (
        "an injected service must leave a warm cache byte-for-byte untouched"
    )
