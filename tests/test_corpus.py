"""Unit and behaviour tests for the shared validation corpus."""

import dataclasses as dc
import pathlib
import typing as typ

import pytest
from pytest_bdd import given, scenario, then, when
from stilyagi import engine, model
from syrupy.extensions.json import JSONSnapshotExtension

from tests.support.assertions import assert_with_context

if typ.TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
CORPUS_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "corpus"
SYNTAX_EXTENSIONS: dict[str, str | tuple[str, ...]] = {
    "markdown": (".md", ".md.fixture"),
    "python": ".py",
    "rust": ".rs",
}
MALFORMED_PYTHON_EXTENSION = ".py.txt"
VALID_CATEGORIES = frozenset({"valid", "malformed"})
VALID_MARKDOWN_FIXTURE_NAME = "heading-table-link-suppression.md"
_SYNTAX_MODELS = {
    "markdown": model.Syntax.MARKDOWN,
    "python": model.Syntax.PYTHON_DOCSTRING,
    "rust": model.Syntax.RUST_DOC_COMMENT,
}
_EXPECTED_REGION_COUNTS = {
    "markdown/malformed/broken-reference-link.md.fixture": 2,
    "markdown/malformed/unbalanced-emphasis.md.fixture": 2,
    "markdown/malformed/unclosed-table.md.fixture": 7,
    "markdown/valid/blockquote-crlf.md.fixture": 2,
    "markdown/valid/blockquotes.md.fixture": 4,
    "markdown/valid/deep-blockquote.md.fixture": 9,
    "markdown/valid/empty-list-item.md.fixture": 1,
    "markdown/valid/frontmatter.md.fixture": 2,
    "markdown/valid/heading-table-link-suppression.md": 6,
    "markdown/valid/headings.md.fixture": 2,
    "markdown/valid/links-and-images.md.fixture": 5,
    "markdown/valid/list-crlf.md.fixture": 4,
    "markdown/valid/lists.md.fixture": 10,
    "markdown/valid/paragraph-inline-markup.md.fixture": 1,
    "markdown/valid/paragraph-soft-break-crlf.md.fixture": 1,
    "markdown/valid/paragraph-soft-break.md.fixture": 1,
    "markdown/valid/suppression-directives.md.fixture": 3,
    "markdown/valid/table.md.fixture": 4,
    "markdown/valid/yaml-frontmatter.md.fixture": 2,
    "python/malformed/unclosed-function.py.txt": 1,
    "python/valid/docstring-edge-cases.py": 6,
    "python/valid/module-class-function-docstrings.py": 4,
    "python/valid/nested-declarations.py": 13,
    "rust/malformed/unclosed-item.rs": 1,
    "rust/valid/doc-comment-multiline.rs": 2,
    "rust/valid/item-doc-comments-with-attributes.rs": 1,
    "rust/valid/item-doc-comments.rs": 4,
    "rust/valid/nested-modules-impls.rs": 6,
}


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
    all_files = sorted(path for path in category_dir.iterdir() if path.is_file())
    unexpected = tuple(
        path for path in all_files if not _has_allowed_suffix(path, extensions)
    )
    if unexpected:
        unexpected_names = ", ".join(
            str(path.relative_to(REPOSITORY_ROOT)) for path in unexpected
        )
        msg = f"unexpected corpus fixture suffix: {unexpected_names}"
        raise ValueError(msg)
    return tuple(
        CorpusFixture(
            syntax=syntax,
            category=category,
            name=path.name,
            path=path,
            text=path.read_text(encoding="utf-8"),
        )
        for path in all_files
        if _has_allowed_suffix(path, extensions)
    )


def _extensions_for_syntax_category(syntax: str, category: str) -> tuple[str, ...]:
    """Return accepted source extensions for a corpus syntax and category."""
    try:
        configured_extensions = SYNTAX_EXTENSIONS[syntax]
    except KeyError as error:
        msg = f"unknown corpus syntax: {syntax}"
        raise ValueError(msg) from error
    if syntax == "python" and category == "malformed":
        return (MALFORMED_PYTHON_EXTENSION,)
    if isinstance(configured_extensions, tuple):
        return configured_extensions
    return (configured_extensions,)


def _has_allowed_suffix(path: pathlib.Path, extensions: tuple[str, ...]) -> bool:
    """Return whether a path uses one of the accepted corpus suffixes."""
    return any(path.name.endswith(extension) for extension in extensions)


@pytest.fixture(scope="session")
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

    assert_with_context(
        categories == {"valid", "malformed"},
        "expected categories == <'valid', 'malformed'>",
    )


def test_corpus_covers_required_source_shapes(snapshot: SnapshotAssertion) -> None:
    """The first corpus covers source shapes required by roadmap item 1.3.1."""
    markdown = corpus_fixture(
        "markdown",
        "valid",
        VALID_MARKDOWN_FIXTURE_NAME,
    )
    python = corpus_fixture(
        "python",
        "valid",
        "module-class-function-docstrings.py",
    )
    rust = corpus_fixture("rust", "valid", "item-doc-comments.rs")

    expected_fragments = {
        "markdown": (
            "# Fixture Heading",
            "Term",
            "Meaning",
            "Intermediate representation",
            "[Stilyagi design]",
            "stilyagi-disable-next-line",
        ),
        "python": (
            '"""Module docstring',
            '"""Class docstring',
            '"""Use a function docstring',
            "stilyagi: ignore-next",
        ),
        "rust": (
            "/// Item-level documentation comment",
            "//! Crate-level documentation comment",
            "stilyagi: ignore-next",
        ),
    }
    fixture_text = {"markdown": markdown.text, "python": python.text, "rust": rust.text}
    observed_fragments = {
        syntax: {fragment: fragment in fixture_text[syntax] for fragment in fragments}
        for syntax, fragments in expected_fragments.items()
    }
    assert_with_context(
        observed_fragments == snapshot(extension_class=JSONSnapshotExtension),
        "expected every required source-shape fragment to be ...",
    )


def test_malformed_fixtures_remain_readable_sources(
    all_corpus_fixtures: tuple[CorpusFixture, ...],
) -> None:
    """Malformed corpus cases are still UTF-8 source files readers can load."""
    malformed_fixtures = [
        fixture for fixture in all_corpus_fixtures if fixture.category == "malformed"
    ]

    assert_with_context(
        {fixture.syntax for fixture in malformed_fixtures}
        == {
            "markdown",
            "python",
            "rust",
        },
        "expected <fixture.syntax for fixture in malformed_fi...",
    )
    assert_with_context(
        all(fixture.text for fixture in malformed_fixtures),
        "expected all((fixture.text for fixture in malformed_...",
    )

    for fixture in malformed_fixtures:
        if fixture.syntax == "python":
            assert_with_context(
                fixture.path.name.endswith(MALFORMED_PYTHON_EXTENSION),
                "expected fixture.path.name.endswith(MALFORMED_PYTHON...",
            )
            assert_with_context(
                fixture.path.suffixes[-2:] == [".py", ".txt"],
                "expected fixture.path.suffixes[-2:] == ['.py', '.txt']",
            )
        else:
            expected_suffixes = _extensions_for_syntax_category(
                fixture.syntax,
                fixture.category,
            )
            assert_with_context(
                _has_allowed_suffix(fixture.path, expected_suffixes),
                "expected _has_allowed_suffix(fixture.path, expected_...",
            )


def test_malformed_python_fixtures_require_text_extension() -> None:
    """Malformed Python fixtures use the explicit source-as-text convention."""
    assert_with_context(
        _extensions_for_syntax_category("python", "malformed") == (".py.txt",),
        "expected _extensions_for_syntax_category('python', '...",
    )


@pytest.mark.parametrize(
    "fixture",
    corpus_fixtures(),
    ids=lambda item: f"{item.syntax}/{item.category}/{item.name}",
)
def test_corpus_region_counts_guard_against_silent_grammar_regressions(
    fixture: CorpusFixture,
) -> None:
    """Pin extractable-region coverage for one shared syntax fixture."""
    key = f"{fixture.syntax}/{fixture.category}/{fixture.name}"
    expected = _EXPECTED_REGION_COUNTS.get(key)
    assert expected is not None, (
        f"record an expected region count for the new fixture {key!r}"
    )

    observed = len(
        engine.extract_document(fixture.text, _SYNTAX_MODELS[fixture.syntax]).regions
    )

    assert_with_context(
        observed == expected,
        f"expected {key!r} to have {expected} region(s), extracted {observed}",
    )


def test_every_recorded_region_count_matches_a_corpus_fixture() -> None:
    """Reject stale entries left behind when a fixture is renamed or removed."""
    known = {f"{item.syntax}/{item.category}/{item.name}" for item in corpus_fixtures()}
    stale = sorted(set(_EXPECTED_REGION_COUNTS) - known)
    assert not stale, f"remove stale expected region counts: {stale}"


class CorpusState(typ.TypedDict, total=False):
    """State shared between corpus BDD steps."""

    fixtures: tuple[CorpusFixture, ...]


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
        assert_with_context(
            categories == {"valid", "malformed"},
            "expected categories == <'valid', 'malformed'>",
        )


@then("malformed fixtures can be read without executing them")
def malformed_fixtures_can_be_read_without_executing_them(
    corpus_state: CorpusState,
) -> None:
    """Confirm malformed files are source text, not imported or compiled code."""
    fixtures = _state_fixtures(corpus_state)
    malformed_paths = [
        fixture.path for fixture in fixtures if fixture.category == "malformed"
    ]

    assert_with_context(
        all(isinstance(path, pathlib.Path) for path in malformed_paths),
        "expected all((isinstance(path, pathlib.Path) for pat...",
    )
    assert_with_context(
        all(path.exists() for path in malformed_paths),
        "expected all((path.exists() for path in malformed_pa...",
    )


def _state_fixtures(corpus_state: CorpusState) -> tuple[CorpusFixture, ...]:
    """Return loaded fixtures from scenario state."""
    assert "fixtures" in corpus_state, "expected 'fixtures' in corpus_state"
    return typ.cast("tuple[CorpusFixture, ...]", corpus_state["fixtures"])
