"""Shared setup for the built-in documentation-summary rule tests.

The finite matrix and the owner-summary suite both need the same two things:
the all-rules-enabled configuration and a run over a real extracted Python or
Rust document. Keeping that here means each test states only the configuration
and the source it cares about, and the rules are exercised through the same
registry seam production uses.
"""

from stilyagi import diagnostics, model

from tests.support.rule_fixtures import LintSetup

#: Per-rule opt-in for every documentation rule, as a validated table set.
ALL_ENABLED: dict[str, dict[str, object]] = {
    "DOC001": {"enabled": True},
    "DOC002": {"enabled": True},
    "DOC003": {"enabled": True},
}


def doc_setup(path: str = "doc.py") -> LintSetup:
    """Return the default all-rules-enabled setup for one reported path.

    Parameters
    ----------
    path:
        Command-line-relative path attributed to diagnostics.

    Returns
    -------
    LintSetup
        A setup that selects ``DOC`` and opts every documentation rule in.

    Examples
    --------
    >>> setup = doc_setup("module.py")
    >>> setup.reported_path
    'module.py'
    """
    return LintSetup(select=("DOC",), rules=ALL_ENABLED, reported_path=path)


def run_python(
    source: str | bytes,
    setup: LintSetup | None = None,
) -> list[diagnostics.Diagnostic]:
    r"""Run the documentation rules over a Python source.

    Parameters
    ----------
    source:
        Python source text, or its UTF-8 bytes.
    setup:
        The configuration to run under; the all-enabled default when omitted.

    Returns
    -------
    list[diagnostics.Diagnostic]
        Diagnostics that survived selection and suppression.

    Examples
    --------
    >>> [item.code for item in run_python('def f():\\n    "Doc."\\n')]
    []
    """
    return (setup or doc_setup()).run(source, model.Syntax.PYTHON_DOCSTRING)


def run_rust(
    source: str | bytes,
    setup: LintSetup | None = None,
) -> list[diagnostics.Diagnostic]:
    r"""Run the documentation rules over a Rust source.

    Parameters
    ----------
    source:
        Rust source text, or its UTF-8 bytes.
    setup:
        The configuration to run under; the all-enabled default when omitted.

    Returns
    -------
    list[diagnostics.Diagnostic]
        Diagnostics that survived selection and suppression.

    Examples
    --------
    >>> [item.code for item in run_rust("/// Read records.\\npub fn f() {}\\n")]
    []
    """
    return (setup or doc_setup("doc.rs")).run(source, model.Syntax.RUST_DOC_COMMENT)
