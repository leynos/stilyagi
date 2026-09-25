"""Tests for ConfigResolver's per-instance discovery and table caches."""

import pathlib
from concurrent import futures

from stilyagi import config

from tests.config_resolution_support import (
    _make_markdown_target,
    _write_discovered_cache_dir,
)
from tests.support.assertions import assert_with_context

type _ResolverCase = tuple[pathlib.Path, pathlib.Path]


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
    assert_with_context(
        _resolve_discovered(resolver, target).cache_dir == pathlib.Path(".first"),
        "expected _resolve_discovered(resolver, target).cache...",
    )

    # Mutate the discovered config on disk part-way through the run.
    _write_discovered_cache_dir(tmp_path, ".second")

    # The same resolver keeps its cached table; the edit is intentionally unseen.
    assert_with_context(
        _resolve_discovered(resolver, target).cache_dir == pathlib.Path(".first"),
        "expected _resolve_discovered(resolver, target).cache...",
    )

    # A fresh resolver starts with empty caches and reads the updated file.
    refreshed = config.ConfigResolver()
    assert_with_context(
        _resolve_discovered(refreshed, target).cache_dir == pathlib.Path(".second"),
        "expected _resolve_discovered(refreshed, target).cach...",
    )


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
    assert_with_context(
        first.cache_dir == pathlib.Path(".first"),
        "expected first.cache_dir == pathlib.Path('.first')",
    )

    _write_discovered_cache_dir(tmp_path, ".second")

    # A distinct resolver built after the edit sees the new value.
    second_resolver = config.ConfigResolver()
    second = _resolve_discovered(second_resolver, target)
    assert_with_context(
        second.cache_dir == pathlib.Path(".second"),
        "expected second.cache_dir == pathlib.Path('.second')",
    )

    # The first resolver still holds its own cached ``.first``, proving the two
    # caches are independent rather than shared through process-wide state.
    reused = _resolve_discovered(first_resolver, target)
    assert_with_context(
        reused.cache_dir == pathlib.Path(".first"),
        "expected reused.cache_dir == pathlib.Path('.first')",
    )


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
    assert_with_context(
        first.cache_dir == pathlib.Path(".shared"),
        "expected first.cache_dir == pathlib.Path('.shared')",
    )

    # Edit the shared config between resolving the two targets.
    _write_discovered_cache_dir(tmp_path, ".changed")

    # The second target reuses the table cached during the first resolution.
    second = _resolve_discovered(resolver, second_target)
    assert_with_context(
        second.cache_dir == pathlib.Path(".shared"),
        "expected second.cache_dir == pathlib.Path('.shared')",
    )


def test_config_resolver_reports_cache_hit_and_miss_counts(
    tmp_path: pathlib.Path,
) -> None:
    """`cache_stats` tracks discovery and resolved-table hits and misses."""
    _write_discovered_cache_dir(tmp_path, ".x")
    target = _make_markdown_target(tmp_path)
    resolver = config.ConfigResolver()

    # A fresh resolver records no cache activity yet.
    assert resolver.cache_stats == {}, "expected resolver.cache_stats == <>"

    _resolve_discovered(resolver, target)
    after_first = resolver.cache_stats
    assert_with_context(
        after_first["discovery_misses"] == 1,
        "expected after_first['discovery_misses'] == 1",
    )
    assert_with_context(
        after_first["resolved_table_misses"] == 1,
        "expected after_first['resolved_table_misses'] == 1",
    )
    assert_with_context(
        after_first.get("discovery_hits", 0) == 0,
        "expected after_first.get('discovery_hits', 0) == 0",
    )
    assert_with_context(
        after_first.get("resolved_table_hits", 0) == 0,
        "expected after_first.get('resolved_table_hits', 0) == 0",
    )

    # Resolving the same directory again hits both caches without new misses.
    _resolve_discovered(resolver, target)
    after_second = resolver.cache_stats
    assert_with_context(
        after_second["discovery_hits"] == 1,
        "expected after_second['discovery_hits'] == 1",
    )
    assert_with_context(
        after_second["resolved_table_hits"] == 1,
        "expected after_second['resolved_table_hits'] == 1",
    )
    assert_with_context(
        after_second["discovery_misses"] == 1,
        "expected after_second['discovery_misses'] == 1",
    )
    assert_with_context(
        after_second["resolved_table_misses"] == 1,
        "expected after_second['resolved_table_misses'] == 1",
    )


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
        assert actual == expected, "expected actual == expected"


# ConfigResolver is deliberately not safe to share across threads: its caches
# are plain dicts mutated without synchronization (see the class docstring in
# `config/resolve.py`). The supported model is one resolver per thread/run, so
# these tests keep every resolver single-threaded rather than asserting a
# thread-safety guarantee the type does not make.
