"""Tests for nearest-config resolution and CLI precedence."""

from __future__ import annotations

import pathlib
import textwrap
from concurrent import futures

import pytest
from stilyagi import config

type _ResolverCase = tuple[pathlib.Path, pathlib.Path]


def _write_config(path: pathlib.Path, body: str) -> None:
    """Write a TOML config file with a trailing newline."""
    path.write_text(textwrap.dedent(body).strip() + "\n", encoding="utf-8")


def _write_discovered_cache_dir(tmp_path: pathlib.Path, cache_dir: str) -> None:
    """Write a discoverable pyproject config that sets one cache-dir."""
    _write_config(
        tmp_path / "pyproject.toml",
        f"""
        [tool.stilyagi]
        cache-dir = "{cache_dir}"
        """,
    )


def _make_markdown_target(directory: pathlib.Path) -> pathlib.Path:
    """Create one Markdown target file for config resolution."""
    target = directory / "note.md"
    target.write_text("# note\n", encoding="utf-8")
    return target


def test_nearest_config_wins_without_ancestor_merging(tmp_path: pathlib.Path) -> None:
    """The nearest config should win, without inheriting unrelated ancestors."""
    _write_config(
        tmp_path / "pyproject.toml",
        """
        [tool.stilyagi]
        cache-dir = ".root"

        [tool.stilyagi.lint]
        preview = true
        """,
    )

    nested = tmp_path / "docs"
    nested.mkdir()
    _write_config(
        nested / "stilyagi.toml",
        """
        cache-dir = ".child"
        """,
    )

    target = _make_markdown_target(nested)

    resolved = config.resolve_config_for_path(
        target,
        cli_overrides=None,
        explicit_config=None,
        isolated=False,
    )

    assert resolved.cache_dir == pathlib.Path(".child")
    assert resolved.lint.preview is False


def test_extend_chain_composes_in_order(tmp_path: pathlib.Path) -> None:
    """Explicit `extend` chains should layer in the declared order."""
    base_one = tmp_path / "base-one.toml"
    _write_config(
        base_one,
        """
        cache-dir = ".base-one"

        [lint]
        preview = true
        """,
    )

    base_two = tmp_path / "base=two.toml"
    _write_config(
        base_two,
        """
        cache-dir = ".base-two"

        [lint]
        preview = false
        """,
    )

    child_dir = tmp_path / "child"
    child_dir.mkdir()
    _write_config(
        child_dir / "stilyagi.toml",
        f"""
        extend = ["{base_one}", "{base_two}"]
        """,
    )

    target = child_dir / "file.md"
    target.write_text("# note\n", encoding="utf-8")

    resolved = config.resolve_config_for_path(
        target,
        cli_overrides=None,
        explicit_config=None,
        isolated=False,
    )

    assert resolved.cache_dir == pathlib.Path(".base-two")
    assert resolved.lint.preview is False


def test_extend_cycle_raises_a_typed_error(tmp_path: pathlib.Path) -> None:
    """Cycle detection should fail with the typed config error."""
    first = tmp_path / "first.toml"
    second = tmp_path / "second.toml"
    _write_config(
        first,
        f"""
        extend = "{second}"
        """,
    )
    _write_config(
        second,
        f"""
        extend = "{first}"
        """,
    )

    target = _make_markdown_target(tmp_path)

    with pytest.raises(config.InvalidConfigError, match=r"extend.*cycle detected"):
        config.resolve_config_for_path(
            target,
            cli_overrides=None,
            explicit_config=[first],
            isolated=True,
        )


def test_isolated_bypasses_discovery(tmp_path: pathlib.Path) -> None:
    """`--isolated` should ignore discovered config files and keep overrides."""
    _write_discovered_cache_dir(tmp_path, ".discovered")

    target = _make_markdown_target(tmp_path)

    resolved = config.resolve_config_for_path(
        target,
        cli_overrides={"cache-dir": ".cli"},
        explicit_config=None,
        isolated=True,
    )

    assert resolved.cache_dir == pathlib.Path(".cli")
    assert resolved.lint.preview is False


def test_explicit_config_path_and_inline_override_precedence(
    tmp_path: pathlib.Path,
) -> None:
    """Inline `--config` fragments should outrank named config files."""
    _write_discovered_cache_dir(tmp_path, ".discovered")

    named_config = tmp_path / "named=override.toml"
    _write_config(
        named_config,
        """
        cache-dir = ".file"
        """,
    )

    target = _make_markdown_target(tmp_path)

    resolved = config.resolve_config_for_path(
        target,
        cli_overrides=None,
        explicit_config=['cache-dir = ".inline"', str(named_config)],
        isolated=False,
    )

    assert resolved.cache_dir == pathlib.Path(".inline")


def test_cli_overrides_win_over_every_config_source(
    tmp_path: pathlib.Path,
) -> None:
    """Dedicated CLI flags should take precedence over every config source."""
    _write_discovered_cache_dir(tmp_path, ".discovered")

    explicit_config = tmp_path / "explicit.toml"
    _write_config(
        explicit_config,
        """
        cache-dir = ".explicit"
        """,
    )

    target = _make_markdown_target(tmp_path)

    resolved = config.resolve_config_for_path(
        target,
        cli_overrides={"cache-dir": ".cli"},
        explicit_config=[explicit_config, 'cache-dir = ".inline"'],
        isolated=False,
    )

    assert resolved.cache_dir == pathlib.Path(".cli")


@pytest.mark.parametrize(
    ("filename", "content", "match"),
    [
        pytest.param("missing.toml", None, r"missing\.toml.*config", id="missing"),
        pytest.param("broken.toml", "[lint\n", r"broken\.toml.*toml", id="malformed"),
    ],
)
def test_bad_explicit_config_raises_a_typed_error(
    tmp_path: pathlib.Path,
    filename: str,
    content: str | None,
    match: str,
) -> None:
    """Missing or malformed explicit config files should fail typed."""
    explicit_config = tmp_path / filename
    if content is not None:
        explicit_config.write_text(content, encoding="utf-8")

    target = _make_markdown_target(tmp_path)

    with pytest.raises(config.InvalidConfigError, match=match):
        config.resolve_config_for_path(
            target,
            cli_overrides=None,
            explicit_config=[str(explicit_config)],
            isolated=True,
        )


def _resolve_discovered(
    resolver: config.ConfigResolver,
    target: pathlib.Path,
) -> config.StilyagiConfig:
    """Resolve one target through a resolver using nearest-config discovery."""
    return resolver.resolve_config_for_path(
        target,
        cli_overrides=None,
        explicit_config=None,
        isolated=False,
    )


def test_config_resolver_caches_within_a_run_and_a_fresh_resolver_sees_edits(
    tmp_path: pathlib.Path,
) -> None:
    """Pin the ConfigResolver cache contract across an on-disk config edit.

    A resolver owns its caches, so within one run it treats config files as
    stable: the parsed table is reused and a mid-run edit is not observed. There
    is deliberately no in-run invalidation hook, because a single ``stilyagi
    check`` invocation reads each config once; observing the edit requires a new
    resolver with its own empty caches.
    """
    _write_discovered_cache_dir(tmp_path, ".first")
    target = _make_markdown_target(tmp_path)

    resolver = config.ConfigResolver()
    assert _resolve_discovered(resolver, target).cache_dir == pathlib.Path(".first")

    # Mutate the discovered config on disk part-way through the run.
    _write_discovered_cache_dir(tmp_path, ".second")

    # The same resolver keeps its cached table; the edit is intentionally unseen.
    assert _resolve_discovered(resolver, target).cache_dir == pathlib.Path(".first")

    # A fresh resolver starts with empty caches and reads the updated file.
    refreshed = config.ConfigResolver()
    assert _resolve_discovered(refreshed, target).cache_dir == pathlib.Path(".second")


def test_config_resolver_instances_do_not_leak_cache_state(
    tmp_path: pathlib.Path,
) -> None:
    """Separate resolvers must not share cache state.

    This guards against the previous module-level caches: resolving with one
    resolver must not populate state that an independently constructed resolver
    would read. Against the old design the second resolver would wrongly return
    ``.first`` from the shared cache.
    """
    _write_discovered_cache_dir(tmp_path, ".first")
    target = _make_markdown_target(tmp_path)

    first_resolver = config.ConfigResolver()
    first = _resolve_discovered(first_resolver, target)
    assert first.cache_dir == pathlib.Path(".first")

    _write_discovered_cache_dir(tmp_path, ".second")

    # A distinct resolver built after the edit sees the new value.
    second_resolver = config.ConfigResolver()
    second = _resolve_discovered(second_resolver, target)
    assert second.cache_dir == pathlib.Path(".second")

    # The first resolver still holds its own cached ``.first``, proving the two
    # caches are independent rather than shared through process-wide state.
    reused = _resolve_discovered(first_resolver, target)
    assert reused.cache_dir == pathlib.Path(".first")


def test_config_resolver_reuses_its_caches_across_targets_in_one_run(
    tmp_path: pathlib.Path,
) -> None:
    """One resolver reuses its per-run caches across several targets.

    Two Markdown targets in the same directory share the discovered config. An
    on-disk edit made between the two resolutions is not observed by the second
    target, which makes the intended per-run reuse of the discovery and
    parsed-table caches explicit: config is read once per run, not once per
    target.
    """
    _write_discovered_cache_dir(tmp_path, ".shared")
    first_target = tmp_path / "a.md"
    first_target.write_text("# a\n", encoding="utf-8")
    second_target = tmp_path / "b.md"
    second_target.write_text("# b\n", encoding="utf-8")

    resolver = config.ConfigResolver()
    first = _resolve_discovered(resolver, first_target)
    assert first.cache_dir == pathlib.Path(".shared")

    # Edit the shared config between resolving the two targets.
    _write_discovered_cache_dir(tmp_path, ".changed")

    # The second target reuses the table cached during the first resolution.
    second = _resolve_discovered(resolver, second_target)
    assert second.cache_dir == pathlib.Path(".shared")


def test_config_resolver_reports_cache_hit_and_miss_counts(
    tmp_path: pathlib.Path,
) -> None:
    """`cache_stats` tracks discovery and resolved-table hits and misses."""
    _write_discovered_cache_dir(tmp_path, ".x")
    target = _make_markdown_target(tmp_path)
    resolver = config.ConfigResolver()

    # A fresh resolver records no cache activity yet.
    assert resolver.cache_stats == {}

    _resolve_discovered(resolver, target)
    after_first = resolver.cache_stats
    assert after_first["discovery_misses"] == 1
    assert after_first["resolved_table_misses"] == 1
    assert after_first.get("discovery_hits", 0) == 0
    assert after_first.get("resolved_table_hits", 0) == 0

    # Resolving the same directory again hits both caches without new misses.
    _resolve_discovered(resolver, target)
    after_second = resolver.cache_stats
    assert after_second["discovery_hits"] == 1
    assert after_second["resolved_table_hits"] == 1
    assert after_second["discovery_misses"] == 1
    assert after_second["resolved_table_misses"] == 1


def test_config_resolver_instances_stay_isolated_under_concurrency(
    tmp_path: pathlib.Path,
) -> None:
    """Per-thread resolvers over changing configs keep isolated caches.

    Each worker constructs its own resolver over its own project directory, so
    there is no shared mutable state and the outcome is deterministic. This
    exercises interleaved resolver use without asserting a thread-safety
    guarantee for a single shared instance, which the type does not provide.
    """
    cases: list[_ResolverCase] = []
    for index in range(8):
        project_dir = tmp_path / f"project-{index}"
        project_dir.mkdir()
        _write_discovered_cache_dir(project_dir, f".cache-{index}")
        target = _make_markdown_target(project_dir)
        cases.append((target, pathlib.Path(f".cache-{index}")))

    def resolve_one(case: _ResolverCase) -> _ResolverCase:
        """Resolve one project with its own single-use resolver."""
        target, expected = case
        resolved = _resolve_discovered(config.ConfigResolver(), target)
        return resolved.cache_dir, expected

    with futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(resolve_one, cases))

    for actual, expected in results:
        assert actual == expected


# ConfigResolver is deliberately not safe to share across threads: its caches
# are plain dicts mutated without synchronization (see the class docstring in
# `config/resolve.py`). The supported model is one resolver per thread/run, so
# these tests keep every resolver single-threaded rather than asserting a
# thread-safety guarantee the type does not make.
