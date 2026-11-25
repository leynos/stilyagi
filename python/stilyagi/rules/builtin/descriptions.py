"""Documentation records for the three shipped builtin rules.

This module is the single authored source of the catalogue's answers. The
typed option defaults are the same values the real parser enforces, and the
contract tests parse every documented TOML example and execute every example
source, so the prose cannot drift from behaviour.

Long prose lives in module constants rather than in implicit string
concatenation inside a collection literal: the constants read as prose, and a
collection entry is then a single name instead of a wrapped literal. The
content is data, not rendering, and holds no command-line or JSON knowledge.
"""

from stilyagi.rules.description import (
    CAPABILITY_STRUCTURE,
    CAPABILITY_TOKENS,
    OptionVariant,
    RuleConfiguration,
    RuleDescription,
    RuleExample,
    RuleOption,
)

_MD_TOML = '[tool.stilyagi.lint]\nselect = ["MD"]\n'
_STY_TOML = '[tool.stilyagi.lint]\nselect = ["STY"]\n'

_TERM_ENABLE_TOML = (
    "[tool.stilyagi.lint]\n"
    'select = ["MD", "STY", "TERM001"]\n'
    "\n"
    "[tool.stilyagi.rule.TERM001]\n"
    'terms = ["obviously"]\n'
    "case_sensitive = false\n"
)

_TERM_CASE_SENSITIVE_TOML = (
    "[tool.stilyagi.lint]\n"
    'select = ["TERM001"]\n'
    "\n"
    "[tool.stilyagi.rule.TERM001]\n"
    'terms = ["Obviously"]\n'
    "case_sensitive = true\n"
)

_TERM_UNICODE_TOML = (
    "[tool.stilyagi.lint]\n"
    'select = ["TERM001"]\n'
    "\n"
    "[tool.stilyagi.rule.TERM001]\n"
    'terms = ["straße"]\n'
    "case_sensitive = false\n"
)

_TERM_SELECTION_TOML = (
    "[tool.stilyagi.lint]\n"
    'select = ["TERM001"]\n'
    "\n"
    "[tool.stilyagi.rule.TERM001]\n"
    'terms = ["obviously"]\n'
)

_REFERENCES = (
    "docs/rfcs/rfc-0002-stilyagi-python-rule-api.md",
    "docs/stilyagi-design.md#72-python-rule-api",
    "docs/adrs/adr-0012-adopt-the-source-backed-builtin-rule-contract.md",
)

#: Shared limitation: static metadata cannot describe per-file enablement.
_STATIC_ENABLEMENT_LIMIT = (
    "Configuration, per-file ignores, and suppression directives can stop a "
    "finding; static metadata does not describe effective enablement for a "
    "particular file."
)

_MD001_EXPLANATION = (
    "The first heading may use any depth. A later heading may descend by any "
    "amount but may not increase by more than one level at a time, because a "
    "skipped level makes the document outline ambiguous for readers and "
    "assistive technology. The diagnostic covers the whole heading node, "
    "marker included."
)
_MD001_ENABLEMENT = (
    "Selected by default. `MD` selects this rule and `MD001` selects only it. "
    '`lint.ignore = ["MD001"]`, a matching `lint.per-file-ignores` entry, or '
    "removing `builtin` from `plugins` removes the rule from the enabled set "
    "before it runs. A `stilyagi: disable MD001` directive instead suppresses "
    "reported findings after evaluation, so a suppressed heading remains the "
    "depth the next heading compares against."
)
_MD001_FIXES = (
    "The rule reports a manual suggestion. The correct heading level is a "
    "prose decision, so no edit is applied automatically and neither `--fix` "
    "nor `--unsafe-fixes` changes the heading."
)
_MD001_LIMITATION_SPAN = (
    "Only headings with a locatable node span are reported; a heading the "
    "extractor cannot map to source bytes is skipped."
)
_MD001_LIMITATION_DEPTH = (
    "The rule compares depth only: it does not enforce a document outline or "
    "a maximum depth, and a document may begin at any level."
)

_STY001_EXPLANATION = (
    "Two or more identical alphabetic tokens separated only by spaces or tabs "
    "are reported as a repeated run. Comparison is exact, so `the the` is a "
    "run and `The the` is not. A run never crosses markup, a region boundary, "
    "a line break, or a synthetic region, and inline code is excluded. The "
    "`TOKENS` capability is supplied by the builtin pack's in-process "
    "tokenizer; no NLP model or external provider is loaded."
)
_STY001_ENABLEMENT = (
    "Selected by default. `STY` selects this rule and `STY001` selects only "
    'it. `lint.ignore = ["STY001"]`, a matching `lint.per-file-ignores` entry, '
    "or removing `builtin` from `plugins` removes the rule from the enabled "
    "set before it runs. A `stilyagi: disable STY001` directive instead "
    "suppresses reported findings after evaluation; the rule still evaluates "
    "over the document."
)
_STY001_FIXES = (
    "The rule may propose an unsafe edit that removes the repeated suffix. "
    "Apply it only with `stilyagi check --fix --unsafe-fixes`; `--fix` alone "
    "skips it, and the `lint.fixable` policy still decides whether the code "
    "may contribute an edit. Review the diff before applying it, because a "
    "deliberate repetition such as `had had` is removed just as an accidental "
    "one is."
)
_STY001_LIMITATION_ADJACENCY = (
    "Matching is exact and adjacent: `the the` is a run, but `the plan the "
    "plan` is not because other words intervene."
)
_STY001_LIMITATION_DELIBERATE = (
    "A deliberate repetition is reported the same way as an accidental one, "
    "and the unsafe edit cannot tell them apart."
)
_STY001_LIMITATION_TARGET = (
    "Only headings, paragraphs, and table cells are inspected; inline code, "
    "code blocks, and unsupported regions are not."
)
_STY001_LIMITATION_SYNTHETIC = (
    "Synthetic segment text that cannot be mapped to source bytes is not "
    "editable, so no edit is offered for it."
)

_TERM001_EXPLANATION = (
    "Every configured term is matched against whole alphabetic tokens, so "
    "`obviously` never matches inside `unobviously`. The `TOKENS` capability "
    "is supplied by the builtin pack's in-process tokenizer; no NLP model or "
    "external provider is loaded. When `case_sensitive` is "
    "false, which is the default, both the configured term and the token are "
    "compared with Unicode `casefold()`; when it is true, the exact spelling "
    "is compared. Duplicate terms coalesce under the chosen comparison. The "
    "rule is opt-in and does nothing until terms are configured."
)
_TERM001_ENABLEMENT = (
    "Disabled by default. Select `TERM001`, or the `TERM` prefix, and "
    "configure `terms` under `[tool.stilyagi.rule.TERM001]`. The builtin "
    "plugin gate still applies: `plugins = []` disables all builtin rules, and "
    "`lint.ignore`, per-file ignores, and suppression directives still apply. "
    "Without a nonempty `terms` list the rule is inactive even when selected."
)
_TERM001_FIXES = (
    "The rule offers no fix. Choosing a replacement for a banned term is "
    "editorial, so no edit is planned and `--fix` leaves the source unchanged."
)
_TERM001_LIMITATION_TARGET = (
    "Only headings, paragraphs, and table cells are inspected; code blocks, "
    "inline code, link destinations, and frontmatter are not."
)
_TERM001_LIMITATION_WHOLE_WORD = (
    "Matching is whole-token only, but hyphens, punctuation, and digits are "
    "token boundaries: a term can match one word inside a hyphenated or "
    "punctuated form. Use an exact context check when that is too broad."
)
_TERM001_LIMITATION_INVERSE = (
    "The opposite editorial policy, requiring a term rather than banning it, "
    "is not supported; no inverse rule or option exists in this slice."
)
_TERM001_LIMITATION_CASE = (
    "Neither case mode promises locale-aware matching or Unicode "
    "normalization; use `case_sensitive = true` when exact spelling matters."
)

_TERM_DESCRIPTION_TEXT = "Words to report when they appear as whole prose tokens."
_TERM_CASE_DESCRIPTION = (
    "Compare configured terms against tokens using exact case instead of "
    "Unicode case folding."
)
_TERM_WORD_CONSTRAINT = (
    "Each entry must be exactly one alphabetic word under `str.isalpha`; "
    "spaces, punctuation, numerals, and empty strings are rejected."
)
_TERM_TERM_CONSTRAINTS = (
    "Must be an array of strings.",
    _TERM_WORD_CONSTRAINT,
    "Duplicates coalesce after the configured comparison.",
)
_TERM_FALSE_VARIANT = (
    "Use Unicode `casefold()` for the configured term and the candidate "
    "token. This is the default."
)
_TERM_TRUE_VARIANT = (
    "Compare the configured spelling exactly. Neither mode promises Unicode "
    "normalization or locale-aware matching."
)

MD001_DESCRIPTION = RuleDescription(
    summary="Report heading depth jumps greater than one.",
    explanation=_MD001_EXPLANATION,
    requires=(CAPABILITY_STRUCTURE,),
    fix_mode="manual",
    enabled_by_default=True,
    configuration=RuleConfiguration(
        enablement=_MD001_ENABLEMENT,
        toml=_MD_TOML,
    ),
    fixes=_MD001_FIXES,
    examples=(
        RuleExample(
            title="A skipped level is reported",
            source="# Start\n### Detail\n",
            expected_codes=("MD001",),
        ),
        RuleExample(
            title="Consecutive levels are accepted",
            source="# Start\n## Detail\n### Example\n",
            expected_codes=(),
        ),
    ),
    limitations=(
        _MD001_LIMITATION_SPAN,
        _MD001_LIMITATION_DEPTH,
        _STATIC_ENABLEMENT_LIMIT,
    ),
    references=_REFERENCES,
)

STY001_DESCRIPTION = RuleDescription(
    summary="Report an immediately repeated word in prose.",
    explanation=_STY001_EXPLANATION,
    requires=(CAPABILITY_STRUCTURE, CAPABILITY_TOKENS),
    fix_mode="unsafe",
    enabled_by_default=True,
    configuration=RuleConfiguration(
        enablement=_STY001_ENABLEMENT,
        toml=_STY_TOML,
    ),
    fixes=_STY001_FIXES,
    examples=(
        RuleExample(
            title="An adjacent repeat is reported",
            source="the the plan is clear.\n",
            expected_codes=("STY001",),
        ),
        RuleExample(
            title="Exact spelling is required",
            source="The the plan is clear.\n",
            expected_codes=(),
        ),
        RuleExample(
            title="A line break ends the run",
            source="the\nthe\n",
            expected_codes=(),
        ),
    ),
    limitations=(
        _STY001_LIMITATION_ADJACENCY,
        _STY001_LIMITATION_DELIBERATE,
        _STY001_LIMITATION_TARGET,
        _STY001_LIMITATION_SYNTHETIC,
        _STATIC_ENABLEMENT_LIMIT,
    ),
    references=_REFERENCES,
)

_TERM_OPTIONS = (
    RuleOption(
        name="terms",
        type="array[string]",
        default=(),
        description=_TERM_DESCRIPTION_TEXT,
        constraints=_TERM_TERM_CONSTRAINTS,
    ),
    RuleOption(
        name="case_sensitive",
        type="boolean",
        default=False,
        description=_TERM_CASE_DESCRIPTION,
        constraints=("Must be a boolean.",),
        variants=(
            OptionVariant(value=False, description=_TERM_FALSE_VARIANT),
            OptionVariant(value=True, description=_TERM_TRUE_VARIANT),
        ),
    ),
)

TERM001_DESCRIPTION = RuleDescription(
    summary="Report configured banned terms in prose.",
    explanation=_TERM001_EXPLANATION,
    requires=(CAPABILITY_STRUCTURE, CAPABILITY_TOKENS),
    fix_mode="none",
    enabled_by_default=False,
    configuration=RuleConfiguration(
        enablement=_TERM001_ENABLEMENT,
        toml=_TERM_ENABLE_TOML,
        options=_TERM_OPTIONS,
    ),
    fixes=_TERM001_FIXES,
    examples=(
        RuleExample(
            title="The rule is inactive by default",
            source="This is obviously fine.\n",
            expected_codes=(),
        ),
        RuleExample(
            title="A selected and configured term is reported",
            source="This is obviously fine.\n",
            configuration=_TERM_ENABLE_TOML,
            expected_codes=("TERM001",),
        ),
        RuleExample(
            title="Case-insensitive matching folds case",
            source="Obviously, this is fine.\n",
            configuration=_TERM_SELECTION_TOML,
            expected_codes=("TERM001",),
        ),
        RuleExample(
            title="Case-sensitive matching requires the exact spelling",
            source="obviously fine.\n",
            configuration=_TERM_CASE_SENSITIVE_TOML,
            expected_codes=(),
        ),
        RuleExample(
            title="Hyphenated text is split into tokens",
            source="This is obviously-not fine.\n",
            configuration=_TERM_SELECTION_TOML,
            expected_codes=("TERM001",),
        ),
        RuleExample(
            title="Unicode case folding applies to whole tokens",
            source="STRASSE matters.\n",
            configuration=_TERM_UNICODE_TOML,
            expected_codes=("TERM001",),
        ),
    ),
    limitations=(
        _TERM001_LIMITATION_TARGET,
        _TERM001_LIMITATION_WHOLE_WORD,
        _TERM001_LIMITATION_INVERSE,
        _TERM001_LIMITATION_CASE,
        _STATIC_ENABLEMENT_LIMIT,
    ),
    references=_REFERENCES,
)

__all__ = [
    "MD001_DESCRIPTION",
    "STY001_DESCRIPTION",
    "TERM001_DESCRIPTION",
]
