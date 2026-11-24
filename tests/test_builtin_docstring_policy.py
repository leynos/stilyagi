"""Policy and surface boundaries of the documentation rules.

``DOC`` selection is not opt-in, so each rule needs its own validated flag;
shared selection, ignore, per-file globs, and the plugin gate still win. These
tests also pin the surfaces the rules never touch and the stability of
repeated runs. ``tests/test_builtin_owner_summary_rules.py`` holds the
owner-comparison behaviour.
"""

import pytest
from stilyagi import config, diagnostics, model
from stilyagi.config.rules import DocRuleConfig

from tests.support.assertions import assert_with_context
from tests.support.docstring_rule_fixtures import ALL_ENABLED, run_source
from tests.support.rule_fixtures import LintSetup, codes_of

pytest_plugins = ("tests.package_skeleton_support",)

pytestmark = pytest.mark.usefixtures("reset_extraction_state")


def _python(
    source: str | bytes,
    setup: LintSetup | None = None,
) -> list[diagnostics.Diagnostic]:
    """Run the documentation rules over a Python source."""
    return run_source(source, model.Syntax.PYTHON_DOCSTRING, setup)


def _rust(
    source: str | bytes,
    setup: LintSetup | None = None,
) -> list[diagnostics.Diagnostic]:
    """Run the documentation rules over a Rust source."""
    return run_source(source, model.Syntax.RUST_DOC_COMMENT, setup)


class TestOptIn:
    """``DOC`` selection is not opt-in; the per-rule flag is."""

    def test_default_prefix_without_config_reports_nothing(self) -> None:
        """Selection alone must not enable these rules."""
        setup = LintSetup(select=("DOC",), reported_path="doc.py")
        source = 'class Widget:\n    """Widget"""\n'

        assert_with_context(
            _python(source, setup) == [],
            "expected absent per-rule opt-in to keep the rules inert",
        )

    def test_explicit_false_opt_in_reports_nothing(self) -> None:
        """An explicit ``enabled = false`` is still inert."""
        setup = LintSetup(
            select=("DOC",),
            rules={code: {"enabled": False} for code in ALL_ENABLED},
            reported_path="doc.py",
        )
        source = 'class Widget:\n    """Widget"""\n'

        assert_with_context(
            _python(source, setup) == [],
            "expected explicit false opt-in to keep the rules inert",
        )

    def test_an_unselected_rule_does_not_run(self) -> None:
        """Opt-in does not override shared selection."""
        setup = LintSetup(select=(), rules=ALL_ENABLED, reported_path="doc.py")
        source = 'class Widget:\n    """Widget"""\n'

        assert _python(source, setup) == [], "expected an unselected rule not to run"

    @pytest.mark.parametrize(
        ("setup", "reason"),
        [
            pytest.param(
                LintSetup(
                    select=("DOC",),
                    ignore=("DOC",),
                    rules=ALL_ENABLED,
                    reported_path="doc.py",
                ),
                "expected lint.ignore to win",
                id="ignore",
            ),
            pytest.param(
                LintSetup(
                    select=("DOC",),
                    per_file_ignores={"*.py": ("DOC",)},
                    rules=ALL_ENABLED,
                    reported_path="doc.py",
                ),
                "expected the per-file glob to win",
                id="per-file-ignore",
            ),
            pytest.param(
                LintSetup(
                    select=("DOC",),
                    plugins=(),
                    rules=ALL_ENABLED,
                    reported_path="doc.py",
                ),
                "expected the plugin gate to win",
                id="plugin-disabled",
            ),
        ],
    )
    def test_shared_policy_removes_an_enabled_rule(
        self,
        setup: LintSetup,
        reason: str,
    ) -> None:
        """Ignore, per-file ignore, and the plugin gate all precede opt-in."""
        source = 'class Widget:\n    """Widget"""\n'

        assert _python(source, setup) == [], reason

    def test_a_malformed_flag_is_rejected_even_when_unselected(self) -> None:
        """An option error cannot hide behind selection."""
        setup = LintSetup(
            select=(),
            rules={"DOC001": {"enabled": "yes"}},
            reported_path="doc.py",
        )

        with pytest.raises(config.InvalidConfigError, match=r"rule\.DOC001\.enabled"):
            _python('def read():\n    """Read."""\n', setup)

    def test_an_unknown_option_is_rejected(self) -> None:
        """A misspelled option cannot leave the rule silently inert."""
        setup = LintSetup(
            select=("DOC",),
            rules={"DOC002": {"enable": True}},
            reported_path="doc.py",
        )

        with pytest.raises(config.InvalidConfigError, match=r"rule\.DOC002\.enable"):
            _python('def read():\n    """Read."""\n', setup)

    def test_the_config_record_defaults_to_disabled(self) -> None:
        """The frozen record documents the opt-in default."""
        assert_with_context(
            DocRuleConfig().enabled is False,
            "expected the documentation rule config to default to disabled",
        )


class TestSurfaceExclusions:
    """Markdown and ordinary comments never receive these codes."""

    def test_markdown_regions_are_not_checked(self) -> None:
        """A Markdown heading or paragraph is outside every rule target."""
        setup = LintSetup(select=("DOC",), rules=ALL_ENABLED, reported_path="doc.md")
        source = "# Widget\n\nRead records\n"

        assert_with_context(
            setup.run(source) == [],
            "expected a Markdown document to receive no documentation rule",
        )

    def test_an_ordinary_python_comment_is_not_checked(self) -> None:
        """Only docstrings are extracted as documentation regions."""
        source = "# Read records\ndef read():\n    return 1\n"

        assert _python(source) == [], "expected a plain comment to be ignored"

    def test_a_non_docstring_python_string_is_not_checked(self) -> None:
        """A string that is not the first statement is not a docstring."""
        source = 'value = """Read records"""\n'

        assert _python(source) == [], "expected a non-docstring string to be ignored"

    def test_an_ordinary_rust_comment_is_not_checked(self) -> None:
        """Only ``///`` and ``//!`` documentation comments are regions."""
        source = "// Read records\npub fn read() {}\n"

        assert _rust(source) == [], "expected a plain Rust comment to be ignored"


class TestDeterminism:
    """Repeated runs produce identical ordered findings."""

    def test_repeated_runs_agree(self) -> None:
        """The same source yields the same ordered diagnostics."""
        source = (
            'class Widget:\n    """Widget"""\n\n'
            'def read():\n    """Read records.\n    More detail.\n    """\n'
        )

        first = _python(source)
        second = _python(source)

        assert first == second, "expected repeated runs to agree exactly"

    def test_each_rule_can_be_enabled_independently(self) -> None:
        """Enabling one code does not activate its siblings."""
        setup = LintSetup(
            select=("DOC",),
            rules={"DOC002": {"enabled": True}},
            reported_path="doc.py",
        )
        source = 'class Widget:\n    """Widget"""\n'

        result = _python(source, setup)

        assert_with_context(
            codes_of(result) == ("DOC002",),
            f"expected only the enabled rule to report, got {codes_of(result)}",
        )
