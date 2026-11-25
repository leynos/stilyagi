"""Documentation records for the opt-in DOC001-DOC003 builtin rules.

These three rules share one summary analysis, so their catalogue prose lives
together and apart from the Markdown rules: the DOC family is the only one that
reads docstring regions, and its opt-in gate and Markdown exclusions are common
to all three. The records carry no command-line or JSON knowledge; the presenters
read them.
"""

from stilyagi.rules.builtin.shared_text import (
    REFERENCES,
    STATIC_ENABLEMENT_LIMIT,
)
from stilyagi.rules.description import (
    CAPABILITY_STRUCTURE,
    OptionVariant,
    RuleConfiguration,
    RuleDescription,
    RuleExample,
    RuleOption,
)


def _enable_toml(code: str) -> str:
    """Return the complete TOML that selects ``code`` and opts it in.

    One renderer for all three rules keeps the shared shape in one place: a
    `DOC` selection plus that rule's own `enabled` flag. Writing each snippet
    out separately would let the three drift apart.

    Returns
    -------
    str
        Complete TOML selecting the `DOC` prefix and enabling ``code``.
    """
    return (
        "[tool.stilyagi.lint]\n"
        'select = ["DOC"]\n'
        "\n"
        f"[tool.stilyagi.rule.{code}]\n"
        "enabled = true\n"
    )


_DOC_ENABLE_TOML = _enable_toml("DOC001")
_DOC_ENABLE_TOML_002 = _enable_toml("DOC002")
_DOC_ENABLE_TOML_003 = _enable_toml("DOC003")

_DOC_ENABLE_TOML = _enable_toml("DOC001")
_DOC_ENABLE_TOML_002 = _enable_toml("DOC002")
_DOC_ENABLE_TOML_003 = _enable_toml("DOC003")

_DOC001_TWO_LINE = 'def f() -> None:\n    """Do a thing.\n    More detail.\n    """\n'
_DOC001_SEPARATED = (
    'def f() -> None:\n    """Do a thing.\n\n    More detail.\n    """\n'
)
_DOC003_REPEATS = 'def load_config() -> None:\n    """load_config."""\n'
_DOC003_DESCRIBES = (
    'def load_config() -> None:\n    """Load the project configuration."""\n'
)
_DOC_ENABLED_OPTION = (
    RuleOption(
        name="enabled",
        type="boolean",
        default=False,
        description="Whether the rule may report for this configuration.",
        constraints=(
            "Must be a boolean.",
            "The rule stays inert, reporting nothing, until this is true.",
        ),
        variants=(
            OptionVariant(
                value=False,
                description="Keep the rule inert even though `DOC` selects it.",
            ),
            OptionVariant(
                value=True,
                description="Let the rule report on the regions it claims.",
            ),
        ),
    ),
)
_DOC_STATIC_ENABLEMENT = (
    "The `DOC` prefix is part of the default selection, so selection alone "
    "cannot express opt-in: each documentation rule stays inert until "
    "`enabled = true` is set under `[tool.stilyagi.rule.CODE]`. "
    "`lint.ignore`, a matching `lint.per-file-ignores` entry, or removing "
    "`builtin` from `plugins` removes the rule from the enabled set before it "
    "runs; a `stilyagi: disable` directive instead suppresses reported "
    "findings after evaluation."
)
_DOC_FIXES = (
    "The rule offers no fix. Rewriting a summary is editorial, so no edit is "
    "planned and `--fix` leaves the source unchanged."
)

_DOC001_EXPLANATION = (
    "A Python docstring's first content line is its summary. When a further "
    "line follows it with no blank line between them, the summary and the "
    "explanation run together, which most renderers show as one paragraph. "
    "Only Python docstrings are inspected; Rust documentation comments, "
    "Markdown, and ordinary comments are not."
)
_DOC001_LIMITATION_SCOPE = (
    "One-line docstrings, docstrings whose summary is the only content, and "
    "regions whose source span cannot be located are not reported."
)

DOC001_DESCRIPTION = RuleDescription(
    summary="Report a Python docstring summary with no blank separator line.",
    explanation=_DOC001_EXPLANATION,
    requires=(CAPABILITY_STRUCTURE,),
    fix_mode="none",
    enabled_by_default=False,
    configuration=RuleConfiguration(
        enablement=_DOC_STATIC_ENABLEMENT,
        toml=_DOC_ENABLE_TOML,
        options=_DOC_ENABLED_OPTION,
    ),
    fixes=_DOC_FIXES,
    examples=(
        RuleExample(
            title="The rule is inert until it is enabled",
            source='def f() -> None:\n    """Do a thing.\n    More detail.\n    """\n',
            expected_codes=(),
        ),
        RuleExample(
            title="An enabled rule reports the missing separator",
            source=_DOC001_TWO_LINE,
            configuration=_DOC_ENABLE_TOML,
            expected_codes=("DOC001",),
        ),
        RuleExample(
            title="A blank separator line satisfies the rule",
            source=_DOC001_SEPARATED,
            configuration=_DOC_ENABLE_TOML,
            expected_codes=(),
        ),
    ),
    limitations=(
        _DOC001_LIMITATION_SCOPE,
        STATIC_ENABLEMENT_LIMIT,
    ),
    references=REFERENCES,
)

_DOC002_EXPLANATION = (
    "A documentation summary reads as a complete sentence when it ends in "
    "`.`, `!`, or `?`. The rule reports a plain summary that ends in any other "
    "character. A summary carrying Markdown markup, or one whose line begins "
    "with markup, is skipped because punctuation inside such text is not "
    "reliably a sentence boundary."
)
_DOC002_LIMITATION_MARKUP = (
    "Summaries containing or beginning with Markdown markup are not judged, "
    "so a genuine missing full stop there goes unreported."
)

DOC002_DESCRIPTION = RuleDescription(
    summary="Report a documentation summary with no terminal punctuation.",
    explanation=_DOC002_EXPLANATION,
    requires=(CAPABILITY_STRUCTURE,),
    fix_mode="none",
    enabled_by_default=False,
    configuration=RuleConfiguration(
        enablement=_DOC_STATIC_ENABLEMENT,
        toml=_DOC_ENABLE_TOML_002,
        options=_DOC_ENABLED_OPTION,
    ),
    fixes=_DOC_FIXES,
    examples=(
        RuleExample(
            title="A summary without terminal punctuation is reported",
            source='def f() -> None:\n    """Do a thing"""\n',
            configuration=_DOC_ENABLE_TOML_002,
            expected_codes=("DOC002",),
        ),
        RuleExample(
            title="A summary ending in a full stop is accepted",
            source='def f() -> None:\n    """Do a thing."""\n',
            configuration=_DOC_ENABLE_TOML_002,
            expected_codes=(),
        ),
    ),
    limitations=(
        _DOC002_LIMITATION_MARKUP,
        STATIC_ENABLEMENT_LIMIT,
    ),
    references=REFERENCES,
)

_DOC003_EXPLANATION = (
    "A summary that only restates its owner's name says nothing about what the "
    "owner does. The rule reports a summary that is exactly the name, the name "
    "with a trailing `()` for a function, or either form followed by one final "
    "period. It inspects Python docstrings and Rust documentation comments "
    "whose owner is a named class, function, struct, enum, trait, or similar "
    "item; an owner the extractor cannot name is skipped."
)
_DOC003_LIMITATION_NAMES = (
    "Only the exact repetitions described above are reported, so a summary "
    "that restates its owner's name in other words is not."
)

DOC003_DESCRIPTION = RuleDescription(
    summary="Report a documentation summary that only repeats its owner name.",
    explanation=_DOC003_EXPLANATION,
    requires=(CAPABILITY_STRUCTURE,),
    fix_mode="none",
    enabled_by_default=False,
    configuration=RuleConfiguration(
        enablement=_DOC_STATIC_ENABLEMENT,
        toml=_DOC_ENABLE_TOML_003,
        options=_DOC_ENABLED_OPTION,
    ),
    fixes=_DOC_FIXES,
    examples=(
        RuleExample(
            title="A summary that repeats the owner name is reported",
            source=_DOC003_REPEATS,
            configuration=_DOC_ENABLE_TOML_003,
            expected_codes=("DOC003",),
        ),
        RuleExample(
            title="A summary that describes the owner is accepted",
            source=_DOC003_DESCRIBES,
            configuration=_DOC_ENABLE_TOML_003,
            expected_codes=(),
        ),
    ),
    limitations=(
        _DOC003_LIMITATION_NAMES,
        STATIC_ENABLEMENT_LIMIT,
    ),
    references=REFERENCES,
)

__all__ = [
    "DOC001_DESCRIPTION",
    "DOC002_DESCRIPTION",
    "DOC003_DESCRIPTION",
]
