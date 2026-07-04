//! Markdown suppression directive parsing helpers.

use stilyagi_ir::SuppressionKind;

/// Canonical suppression directive verbs recognised in Markdown comments.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum DirectiveVerb {
    /// Inline suppression for the next lintable unit.
    IgnoreNext,
    /// Range suppression that starts a suppressed span.
    Disable,
    /// Range suppression that ends a suppressed span.
    Enable,
    /// Whole-file suppression.
    IgnoreFile,
}

/// A successfully parsed directive body.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ParsedDirective {
    /// Directive verb.
    pub verb: DirectiveVerb,
    /// Named rule codes or prefixes.
    pub codes: Vec<String>,
}

/// Outcome of parsing a candidate Markdown HTML comment.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum DirectiveOutcome {
    /// The comment is not a Stilyagi directive.
    NotADirective,
    /// The comment is a recognised directive and has valid syntax.
    Parsed(ParsedDirective),
    /// The comment matches the canonical marker but violates a rule.
    Rejected(DirectiveError),
}

/// Parse errors for canonical suppression directives.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum DirectiveError {
    /// Inline or range directives named no code.
    BlanketForbidden,
    /// The verb token is not one of the recognised canonical verbs.
    UnknownVerb,
}

/// Parse the inner text of a Markdown HTML comment into a directive outcome.
///
/// The input should be the bytes between `<!--` and `-->`.
pub(crate) fn parse_comment_directive(inner: &str) -> DirectiveOutcome {
    let trimmed = inner.trim();
    let Some(directive_body) = trimmed.strip_prefix("stilyagi:") else {
        return DirectiveOutcome::NotADirective;
    };

    let directive_text = directive_body.trim_start();
    let mut parts = directive_text.splitn(2, char::is_whitespace);
    let verb_token = parts.next().unwrap_or_default();
    let remainder = parts.next().unwrap_or_default().trim();
    let verb = match verb_token {
        "ignore-next" => DirectiveVerb::IgnoreNext,
        "disable" => DirectiveVerb::Disable,
        "enable" => DirectiveVerb::Enable,
        "ignore-file" => DirectiveVerb::IgnoreFile,
        _ => return DirectiveOutcome::Rejected(DirectiveError::UnknownVerb),
    };

    let codes = parse_codes(remainder);
    if codes.is_empty() && !matches!(verb, DirectiveVerb::IgnoreFile) {
        return DirectiveOutcome::Rejected(DirectiveError::BlanketForbidden);
    }

    DirectiveOutcome::Parsed(ParsedDirective { verb, codes })
}

/// Map a directive verb onto the IR suppression kind.
pub(crate) const fn verb_kind(verb: DirectiveVerb) -> SuppressionKind {
    match verb {
        DirectiveVerb::IgnoreNext => SuppressionKind::Inline,
        DirectiveVerb::Disable | DirectiveVerb::Enable => SuppressionKind::Range,
        DirectiveVerb::IgnoreFile => SuppressionKind::File,
    }
}

fn parse_codes(remainder: &str) -> Vec<String> {
    remainder
        .split(',')
        .map(str::trim)
        .filter(|code| !code.is_empty())
        .map(ToOwned::to_owned)
        .collect()
}
