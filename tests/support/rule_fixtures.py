"""Shared helpers for exercising the builtin rule pack.

The rule unit tests, the policy truth tables, and the property tests all need
the same two things: a real extracted document, and a run through the public
rule seam with a chosen configuration. Keeping that in one place means a test
states only the configuration and the source it cares about.
"""

import dataclasses as dc
import typing as typ

from stilyagi import config, diagnostics, engine, model
from stilyagi.config.schema import LintConfig
from stilyagi.rules.registry import RuleRunRequest, run_rules

if typ.TYPE_CHECKING:
    import collections.abc as cabc


@dc.dataclass(frozen=True, slots=True)
class LintSetup:
    """The configuration one rule run under test uses.

    Parameters
    ----------
    select:
        Rule prefixes the run selects.
    ignore:
        Rule prefixes the run ignores after selection.
    per_file_ignores:
        Per-path rule prefixes.
    plugins:
        Enabled config plugins. An empty tuple disables the builtin pack.
    rules:
        Per-rule option tables, keyed by code.
    reported_path:
        Path attributed to diagnostics.
    config_relative_path:
        Path per-file globs are matched against. Defaults to
        ``reported_path``.
    """

    select: tuple[str, ...] = ("MD", "STY", "TERM")
    ignore: tuple[str, ...] = ()
    per_file_ignores: dict[str, tuple[str, ...]] = dc.field(default_factory=dict)
    plugins: tuple[str, ...] = ("builtin",)
    rules: dict[str, dict[str, object]] = dc.field(default_factory=dict)
    reported_path: str = "doc.md"
    config_relative_path: str | None = None

    def build_config(self) -> config.StilyagiConfig:
        """Return the resolved configuration this setup describes."""
        return config.StilyagiConfig(
            plugins=self.plugins,
            lint=LintConfig(
                select=self.select,
                ignore=self.ignore,
                per_file_ignores=dict(self.per_file_ignores),
            ),
            rules={code: dict(values) for code, values in self.rules.items()},
        )

    def run(self, source: str | bytes) -> list[diagnostics.Diagnostic]:
        """Extract ``source`` and run the selected builtin rules over it."""
        text = source.decode("utf-8") if isinstance(source, bytes) else source
        document = engine.extract_document(text, model.Syntax.MARKDOWN)
        request = RuleRunRequest(
            config=self.build_config(),
            config_path=None,
            source_bytes=text.encode("utf-8"),
            reported_path=self.reported_path,
            document=document,
            config_relative_path=(
                self.config_relative_path
                if self.config_relative_path is not None
                else self.reported_path
            ),
        )
        return run_rules(request)

    def run_document(
        self,
        document: model.Document,
        source_bytes: bytes,
    ) -> list[diagnostics.Diagnostic]:
        """Run over an already-built document, for handwritten IR fixtures."""
        request = RuleRunRequest(
            config=self.build_config(),
            config_path=None,
            source_bytes=source_bytes,
            reported_path=self.reported_path,
            document=document,
            config_relative_path=self.reported_path,
        )
        return run_rules(request)


def codes_of(result: cabc.Sequence[diagnostics.Diagnostic]) -> tuple[str, ...]:
    """Return the diagnostic codes in order, for compact assertions."""
    return tuple(diagnostic.code for diagnostic in result)


def spans_of(
    result: cabc.Sequence[diagnostics.Diagnostic],
) -> tuple[tuple[int, int] | None, ...]:
    """Return each diagnostic's byte span as a pair, or ``None``."""
    return tuple(
        None
        if diagnostic.span is None
        else (diagnostic.span.byte_start, diagnostic.span.byte_end)
        for diagnostic in result
    )


def marked_span(source: bytes, result: cabc.Sequence[diagnostics.Diagnostic]) -> bytes:
    """Return the bytes every diagnostic's span addresses."""
    return b"|".join(
        b""
        if diagnostic.span is None
        else source[diagnostic.span.byte_start : diagnostic.span.byte_end]
        for diagnostic in result
    )
