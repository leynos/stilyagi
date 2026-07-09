"""Empty rule-registry seam for the initial check pipeline.

This module keeps the rule runner explicit before any built-in rules are
introduced. The command pipeline calls into this seam so roadmap 2.3.1 can
replace the empty list with real rule diagnostics without changing the
composition flow.
"""

import typing as typ

if typ.TYPE_CHECKING:
    from stilyagi import diagnostics, model
    from stilyagi.config import StilyagiConfig


def run_rules(
    _document: model.Document,
    _config: StilyagiConfig,
) -> list[diagnostics.Diagnostic]:
    """Return no diagnostics until the rule engine lands.

    Examples
    --------
    >>> from stilyagi import config, model
    >>> run_rules(model.Document(syntax=model.Syntax.MARKDOWN), config.StilyagiConfig())
    []
    """
    return []
