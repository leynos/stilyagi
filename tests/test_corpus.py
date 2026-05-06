"""Unit and behaviour tests for the shared validation corpus."""

import dataclasses as dc
import pathlib

import pytest
from pytest_bdd import given, scenario, then, when

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
CORPUS_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "corpus"
SYNTAX_EXTENSIONS = {
    "markdown": ".md",
    "python": ".py",
    "rust": ".rs",
}
MALFORMED_PYTHON_EXTENSION = ".py.txt"
VALID_CATEGORIES = frozenset({"valid", "malformed"})


@dc.dataclass(frozen=True, slots=True)
class CorpusFixture:
    """One checked-in source fixture from the shared corpus."""

    syntax: str
    category: str
    name: str
    path: pathlib.Path
    text: str


@scenario(
    "../features/stilyagi_fixture_corpus.feature",
    "Shared validation corpus covers every v1 syntax",
)
def test_shared_validation_corpus_covers_every_v1_syntax() -> None:
    """Run the corpus BDD scenario."""


def corpus_fixture(syntax: str, category: str, name: str) -> CorpusFixture:
    """Read one corpus fixture by syntax, category, and file name."""
    extensions = _extensions_for_syntax_category(syntax, category)
    if category not in VALID_CATEGORIES:
        msg = f"unknown corpus category: {category}"
        raise ValueError(msg)

    path = CORPUS_ROOT / syntax / category / name
    if not _has_allowed_suffix(path, extensions):
        msg = f"fixture {name!r} does not use one of {extensions!r}"
        raise ValueError(msg)
    return CorpusFixture(
        syntax=syntax,
        category=category,
        name=name,
        path=path,
        text=path.read_text(encoding="utf-8"),
    )


def corpus_fixtures() -> tuple[CorpusFixture, ...]:
    """Return every shared corpus fixture in stable path order."""
    fixtures: list[CorpusFixture] = []
    for syntax in sorted(SYNTAX_EXTENSIONS):
        for category in sorted(VALID_CATEGORIES):
            category_dir = CORPUS_ROOT / syntax / category
            extensions = _extensions_for_syntax_category(syntax, category)
            fixtures.extend(
                _corpus_fixtures_for_category(
                    syntax=syntax,
                    category=category,
                    category_dir=category_dir,
                    extensions=extensions,
                )
            )
    return tuple(fixtures)


def _corpus_fixtures_for_category(
    *,
    syntax: str,
    category: str,
    category_dir: pathlib.Path,
    extensions: tuple[str, ...],
) -> tuple[CorpusFixture, ...]:
    """Return validated corpus fixtures from one syntax/category directory."""
    _assert_allowed_fixture_suffixes(category_dir, extensions)
    return tuple(
        CorpusFixture(
            syntax=syntax,
            category=category,
            name=path.name,
            path=path,
            text=path.read_text(encoding="utf-8"),
        )
        for path in sorted(category_dir.iterdir())
        if path.is_file() and _has_allowed_suffix(path, extensions)
    )


def _assert_allowed_fixture_suffixes(
    category_dir: pathlib.Path,
    extensions: tuple[str, ...],
) -> None:
    """Raise if a fixture directory contains files with unsupported suffixes."""
    unexpected_paths = _unexpected_fixture_paths(category_dir, extensions)
    if not unexpected_paths:
        return

    unexpected_names = ", ".join(
        str(path.relative_to(REPOSITORY_ROOT)) for path in unexpected_paths
    )
    msg = f"unexpected corpus fixture suffix: {unexpected_names}"
    raise ValueError(msg)


def _unexpected_fixture_paths(
    category_dir: pathlib.Path,
    extensions: tuple[str, ...],
) -> tuple[pathlib.Path, ...]:
    """Return regular files that do not use the expected fixture suffixes."""
    return tuple(
        path
        for path in sorted(category_dir.iterdir())
        if path.is_file() and not _has_allowed_suffix(path, extensions)
    )


def _extensions_for_syntax_category(syntax: str, category: str) -> tuple[str, ...]:
    """Return accepted source extensions for a corpus syntax and category."""
    try:
        extension = SYNTAX_EXTENSIONS[syntax]
    except KeyError as error:
        msg = f"unknown corpus syntax: {syntax}"
        raise ValueError(msg) from error
    if syntax == "python" and category == "malformed":
        return (extension, MALFORMED_PYTHON_EXTENSION)
    return (extension,)


def _has_allowed_suffix(path: pathlib.Path, extensions: tuple[str, ...]) -> bool:
    """Return whether a path uses one of the accepted corpus suffixes."""
    return any(path.name.endswith(extension) for extension in extensions)


@pytest.fixture
def all_corpus_fixtures() -> tuple[CorpusFixture, ...]:
    """Return the full shared corpus for unit tests."""
    return corpus_fixtures()


@pytest.mark.parametrize("syntax", ["markdown", "python", "rust"])
def test_each_syntax_has_valid_and_malformed_fixtures(
    all_corpus_fixtures: tuple[CorpusFixture, ...],
    syntax: str,
) -> None:
    """Every v1 syntax has at least one valid and malformed source fixture."""
    categories = {
        fixture.category
        for fixture in all_corpus_fixtures
        if fixture.syntax == syntax and fixture.text
    }

    assert categories == {"valid", "malformed"}


def test_corpus_covers_required_source_shapes() -> None:
    """The first corpus covers source shapes required by roadmap item 1.3.1."""
    markdown = corpus_fixture(
        "markdown",
        "valid",
        "heading-table-link-suppression.md",
    )
    python = corpus_fixture(
        "python",
        "valid",
        "module-class-function-docstrings.py",
    )
    rust = corpus_fixture("rust", "valid", "item-doc-comments.rs")

    assert "# Fixture Heading" in markdown.text
    assert "Term" in markdown.text
    assert "Meaning" in markdown.text
    assert "Intermediate representation" in markdown.text
    assert "[Stilyagi design]" in markdown.text
    assert "stilyagi-disable-next-line" in markdown.text
    assert '"""Module docstring' in python.text
    assert '"""Class docstring' in python.text
    assert '"""Use a function docstring' in python.text
    assert "stilyagi-disable-next-line" in python.text
    assert "/// Item-level documentation comment" in rust.text
    assert "//! Crate-level documentation comment" in rust.text
    assert "stilyagi-disable-next-line" in rust.text


def test_malformed_fixtures_remain_readable_sources(
    all_corpus_fixtures: tuple[CorpusFixture, ...],
) -> None:
    """Malformed corpus cases are still UTF-8 source files readers can load."""
    malformed_fixtures = [
        fixture for fixture in all_corpus_fixtures if fixture.category == "malformed"
    ]

    assert {fixture.syntax for fixture in malformed_fixtures} == {
        "markdown",
        "python",
        "rust",
    }
    assert all(fixture.text for fixture in malformed_fixtures)


CorpusState = dict[str, object]


@given("the shared validation corpus is available", target_fixture="corpus_state")
def corpus_state() -> CorpusState:
    """Return empty corpus scenario state."""
    return {}


@when("I inspect the fixture corpus")
def inspect_fixture_corpus(corpus_state: CorpusState) -> None:
    """Load the corpus through the shared Python test helper."""
    corpus_state["fixtures"] = corpus_fixtures()


@then("every v1 syntax has valid and malformed fixtures")
def every_v1_syntax_has_valid_and_malformed_fixtures(
    corpus_state: CorpusState,
) -> None:
    """Confirm the corpus is present for each planned v1 syntax."""
    fixtures = _state_fixtures(corpus_state)

    for syntax in ("markdown", "python", "rust"):
        categories = {
            fixture.category for fixture in fixtures if fixture.syntax == syntax
        }
        assert categories == {"valid", "malformed"}


@then("malformed fixtures can be read without executing them")
def malformed_fixtures_can_be_read_without_executing_them(
    corpus_state: CorpusState,
) -> None:
    """Confirm malformed files are source text, not imported or compiled code."""
    fixtures = _state_fixtures(corpus_state)
    malformed_paths = [
        fixture.path for fixture in fixtures if fixture.category == "malformed"
    ]

    assert all(isinstance(path, pathlib.Path) for path in malformed_paths)
    assert all(path.exists() for path in malformed_paths)


def _state_fixtures(corpus_state: CorpusState) -> tuple[CorpusFixture, ...]:
    """Return loaded fixtures from scenario state."""
    fixtures = corpus_state.get("fixtures")
    assert isinstance(fixtures, tuple)
    assert all(isinstance(fixture, CorpusFixture) for fixture in fixtures)
    return fixtures
