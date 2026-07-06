"""Tests for the config schema and same-directory loading."""

from __future__ import annotations

import pathlib
import textwrap

import pytest
from stilyagi import config

RFC_0003_BASELINE = textwrap.dedent(
    """
    [tool.stilyagi]
    cache-dir = ".stilyagi_cache"
    respect-gitignore = true
    line-length = 88
    plugins = ["builtin"]

    [tool.stilyagi.lint]
    select = ["MD", "DOC", "PUN", "STY", "PYDOC"]
    ignore = []
    fixable = ["ALL"]
    unfixable = []
    preview = false

    [tool.stilyagi.lint.per-file-ignores]
    "CHANGELOG.md" = ["PUN201"]
    "tests/**" = ["PYDOC"]

    [tool.stilyagi.extract.markdown]
    gfm = true
    frontmatter = true
    mdx = false

    [tool.stilyagi.nlp]
    model = "en_core_web_sm"
    sentence-provider = "sentencizer"

    [tool.stilyagi.rule.PUN201]
    min_items = 3
    """
).strip()


@pytest.mark.parametrize(
    "filename",
    [
        "pyproject.toml",
        "stilyagi.toml",
        ".stilyagi.toml",
    ],
)
def test_config_file_kinds_parse_under_their_expected_prefix(
    tmp_path: pathlib.Path,
    filename: str,
) -> None:
    """Load every supported filename kind through the matching TOML prefix."""
    path = tmp_path / filename
    if filename == "pyproject.toml":
        path.write_text(
            textwrap.dedent(
                f"""
                [tool.stilyagi]
                cache-dir = "{pathlib.Path(".stilyagi_cache").as_posix()}"
                plugins = ["builtin"]
                """
            ).strip(),
            encoding="utf-8",
        )
    else:
        path.write_text(
            textwrap.dedent(
                """
                cache-dir = ".stilyagi_cache"
                plugins = ["builtin"]
                """
            ).strip(),
            encoding="utf-8",
        )

    parsed = config.load_config_file(path)

    assert parsed.cache_dir == pathlib.Path(".stilyagi_cache")
    assert parsed.plugins == ("builtin",)


def test_default_config_exposes_the_documented_defaults() -> None:
    """Pin the public default constructor to its documented field values."""
    defaults = config.StilyagiConfig()

    assert defaults.cache_dir == pathlib.Path(".stilyagi_cache")
    assert defaults.respect_gitignore is True
    assert defaults.line_length == 88
    assert defaults.plugins == ("builtin",)
    assert defaults.lint.select == ("MD", "DOC", "PUN", "STY", "PYDOC")
    assert not defaults.lint.ignore
    assert defaults.lint.preview is False
    assert defaults.lint.fixable == ("ALL",)
    assert defaults.extract.gfm is True
    assert defaults.extract.frontmatter is True
    assert defaults.extract.mdx is False
    assert defaults.nlp.model == "en_core_web_sm"
    assert defaults.nlp.sentence_provider == "sentencizer"
    assert not defaults.rules
    assert not defaults.reserved


def test_baseline_config_parses_and_preserves_reserved_values(
    tmp_path: pathlib.Path,
) -> None:
    """Accept the whole RFC baseline and preserve the reserved parts."""
    path = tmp_path / "pyproject.toml"
    path.write_text(RFC_0003_BASELINE, encoding="utf-8")

    parsed = config.load_config_file(path)

    assert parsed.cache_dir == pathlib.Path(".stilyagi_cache")
    assert parsed.respect_gitignore is True
    assert parsed.line_length == 88
    assert parsed.plugins == ("builtin",)
    assert parsed.lint.select == ("MD", "DOC", "PUN", "STY", "PYDOC")
    assert not parsed.lint.ignore
    assert parsed.lint.fixable == ("ALL",)
    assert not parsed.lint.unfixable
    assert parsed.lint.preview is False
    assert parsed.lint.per_file_ignores == {
        "CHANGELOG.md": ("PUN201",),
        "tests/**": ("PYDOC",),
    }
    assert parsed.extract == config.MarkdownExtractConfig()
    assert parsed.nlp.model == "en_core_web_sm"
    assert parsed.nlp.sentence_provider == "sentencizer"
    assert parsed.nlp.reserved == {
        "model": "en_core_web_sm",
        "sentence-provider": "sentencizer",
    }
    assert parsed.rules == {"PUN201": {"min_items": 3}}
    assert parsed.reserved["line-length"] == 88
    assert parsed.reserved["lint"] == {
        "fixable": ["ALL"],
        "unfixable": [],
        "per-file-ignores": {
            "CHANGELOG.md": ["PUN201"],
            "tests/**": ["PYDOC"],
        },
    }
    assert parsed.reserved["nlp"] == {
        "model": "en_core_web_sm",
        "sentence-provider": "sentencizer",
    }
    assert parsed.reserved["rule"] == {"PUN201": {"min_items": 3}}


def test_unknown_keys_raise_a_typed_config_error(
    tmp_path: pathlib.Path,
) -> None:
    """Reject keys outside the RFC baseline with a named error."""
    path = tmp_path / "stilyagi.toml"
    path.write_text(
        textwrap.dedent(
            """
            [lint]
            made-up-key = true
            """
        ).strip(),
        encoding="utf-8",
    )

    with pytest.raises(
        config.InvalidConfigError, match=r"stilyagi\.toml.*lint\.made-up-key"
    ):
        config.load_config_file(path)


def test_blank_cache_directory_is_rejected() -> None:
    """Keep the existing cache-directory guard in place."""
    with pytest.raises(config.InvalidCacheDirError, match=r"non-empty path"):
        config.StilyagiConfig(cache_dir=pathlib.Path("   "))


def test_same_directory_precedence_prefers_the_highest_ranked_file(
    tmp_path: pathlib.Path,
) -> None:
    """Choose the highest-precedence config file from one directory."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.stilyagi]\ncache-dir = ".pyproject"\n',
        encoding="utf-8",
    )
    (tmp_path / "stilyagi.toml").write_text(
        'cache-dir = ".stilyagi"\n',
        encoding="utf-8",
    )
    (tmp_path / ".stilyagi.toml").write_text(
        'cache-dir = ".dotstilyagi"\n',
        encoding="utf-8",
    )

    discovered = config.discover_same_directory_config(tmp_path)

    assert discovered is not None
    assert discovered.path.name == ".stilyagi.toml"
    assert discovered.config.cache_dir == pathlib.Path(".dotstilyagi")
