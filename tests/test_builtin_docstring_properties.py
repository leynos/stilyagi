"""Property tests for the documentation-summary rules.

The finite matrix in ``test_builtin_docstring_rules`` pins named examples. These
properties generate owner names, summary text, and rule-selection orders to
check that the rules' promises hold beyond the examples: a finding appears
exactly when the documented predicate holds, its anchor addresses the expected
source character even across multibyte text and synthetic Rust line breaks, and
the reported order does not depend on how the configuration was assembled.

Every property builds a real Python or Rust fixture and runs it through the
real extractor and registry. A property that never produced a finding would
prove nothing, so each one asserts a matching witness exists.
"""

import collections.abc as cabc
import itertools
import keyword
import string

import hypothesis as hyp
import hypothesis.strategies as st
import pytest
from stilyagi import diagnostics, model

from tests.support.rule_fixtures import LintSetup, marked_span

pytest_plugins = ("tests.package_skeleton_support",)

pytestmark = pytest.mark.usefixtures("reset_extraction_state")

ALL_ENABLED: dict[str, dict[str, object]] = {
    "DOC001": {"enabled": True},
    "DOC002": {"enabled": True},
    "DOC003": {"enabled": True},
}

_NAME_ALPHABET = string.ascii_letters + "_"
_IDENTIFIERS = st.text(alphabet=_NAME_ALPHABET, min_size=1, max_size=10).filter(
    str.isidentifier
)
_PLAIN_TEXT = st.text(
    alphabet=string.ascii_letters + string.digits + " ",
    min_size=0,
    max_size=20,
)
_TERMINALS = st.sampled_from([".", "!", "?", ",", ";", "9", "…"])
_WORDS = st.text(alphabet=string.ascii_letters, min_size=1, max_size=10)
_NON_ASCII_LETTERS = st.sampled_from(["é", "ß", "λ", "字", "🧭"])


def _python(source: str) -> list[diagnostics.Diagnostic]:
    """Run the enabled documentation rules over one Python source."""
    return LintSetup(select=("DOC",), rules=ALL_ENABLED, reported_path="doc.py").run(
        source, model.Syntax.PYTHON_DOCSTRING
    )


def _rust(source: str) -> list[diagnostics.Diagnostic]:
    """Run the enabled documentation rules over one Rust source."""
    return LintSetup(select=("DOC",), rules=ALL_ENABLED, reported_path="doc.rs").run(
        source, model.Syntax.RUST_DOC_COMMENT
    )


def _codes(result: list[diagnostics.Diagnostic]) -> tuple[str, ...]:
    """Return the diagnostic codes in order."""
    return tuple(diagnostic.code for diagnostic in result)


@hyp.given(name=_IDENTIFIERS, other=_IDENTIFIERS)
def test_doc003_reports_only_the_matching_owner(name: str, other: str) -> None:
    """DOC003 fires exactly when the summary repeats the owner's own name."""
    hyp.assume(not keyword.iskeyword(name))
    hyp.assume(not keyword.iskeyword(other))
    hyp.assume(other != name)
    source = f'class {name}:\n    """{name}."""\n\nclass {other}:\n    """{name}."""\n'

    result = _python(source)

    assert _codes(result) == ("DOC003",), (
        f"expected one DOC003 for {name!r}, got {_codes(result)}"
    )
    assert marked_span(source.encode(), result) == name[0].encode(), (
        "expected the anchor to be the documented name's first character"
    )
    assert result[0].line == 2, (
        f"expected the finding on the matching class, got line {result[0].line}"
    )


@hyp.given(body=_PLAIN_TEXT, terminal=_TERMINALS)
def test_doc002_presence_follows_terminal_punctuation(
    body: str,
    terminal: str,
) -> None:
    """DOC002 reports exactly when the trimmed summary lacks ``.``, ``!``, ``?``."""
    source = f'def read():\n    """{body}{terminal}"""\n'

    codes = _codes(_python(source))

    if terminal in ".!?":
        assert "DOC002" not in codes, (
            f"expected {terminal!r} to be accepted, got {codes}"
        )
    else:
        assert codes.count("DOC002") == 1, (
            f"expected one DOC002 for terminal {terminal!r}, got {codes}"
        )


@hyp.given(character=_NON_ASCII_LETTERS)
def test_doc001_anchor_covers_one_complete_character(character: str) -> None:
    """A multibyte anchor is reported as its whole UTF-8 sequence."""
    source = f'def read():\n    """Read records.\n    {character} continues.\n    """\n'

    result = _python(source)

    assert _codes(result) == ("DOC001",), f"expected one DOC001, got {_codes(result)}"
    assert marked_span(source.encode(), result) == character.encode(), (
        "expected the anchor to decode to the first character of line two"
    )
    span = result[0].span
    assert span is not None, "expected the finding to carry a span"
    assert span.byte_end - span.byte_start == len(character.encode()), (
        "expected the span to cover exactly one character's bytes"
    )


@hyp.given(word=_WORDS, character=_NON_ASCII_LETTERS)
def test_doc002_rust_anchor_survives_synthetic_line_breaks(
    word: str,
    character: str,
) -> None:
    """Merged Rust comment lines keep their own source offsets."""
    hyp.assume(character.isalpha())
    source = f"/// Read {word}{character}\npub fn read() {{}}\n"

    result = _rust(source)

    assert _codes(result) == ("DOC002",), f"expected one DOC002, got {_codes(result)}"
    assert marked_span(source.encode(), result) == character.encode(), (
        "expected the anchor to be the word's final character"
    )
    span = result[0].span
    assert span is not None, "expected the finding to carry a span"
    assert span.byte_start >= 4, "expected the anchor to sit after the comment marker"


@hyp.given(order=st.permutations(("DOC001", "DOC002", "DOC003")))
def test_rule_order_does_not_depend_on_configuration_order(
    order: cabc.Sequence[str],
) -> None:
    """Assembly order of the per-rule tables cannot change the report order."""
    rules: dict[str, dict[str, object]] = {code: {"enabled": True} for code in order}
    setup = LintSetup(select=("DOC",), rules=rules, reported_path="doc.py")
    source = 'class Widget:\n    """Widget"""\n'

    result = setup.run(source, model.Syntax.PYTHON_DOCSTRING)

    assert _codes(result) == ("DOC002", "DOC003"), (
        f"expected inventory order regardless of table order {order}, "
        f"got {_codes(result)}"
    )


def test_the_order_permutations_are_distinct() -> None:
    """Guard the property above: it must actually exercise every order."""
    permutations = list(itertools.permutations(("DOC001", "DOC002", "DOC003")))

    assert len(permutations) == 6, (
        f"expected six rule-table orders, got {len(permutations)}"
    )
    assert len(set(permutations)) == 6, (
        "expected the permutation strategy to yield distinct orders"
    )
