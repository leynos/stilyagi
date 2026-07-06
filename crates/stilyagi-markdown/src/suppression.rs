//! Markdown suppression directive parsing helpers.

use stilyagi_ir::{SourceSpan, SuppressionKind};

/// A comment slice found inside a Markdown HTML node.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct CommentSpan<'source> {
    /// Comment span relative to the scanned source slice.
    pub span: SourceSpan,
    /// Comment body between `<!--` and `-->`.
    pub inner: &'source str,
}

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

/// Return every HTML comment found in a Markdown node source slice.
pub(crate) fn scan_comment_spans(source: &str) -> Vec<CommentSpan<'_>> {
    let mut comments = Vec::new();
    let mut search_start = 0;

    while let Some(relative_start) = source
        .get(search_start..)
        .and_then(|slice| slice.find("<!--"))
    {
        let start = search_start + relative_start;
        let inner_start = start + 4;
        let Some(relative_end) = source
            .get(inner_start..)
            .and_then(|slice| slice.find("-->"))
        else {
            search_start = inner_start;
            continue;
        };

        let inner_end = inner_start + relative_end;
        let end = inner_end + 3;
        let Some(inner) = source.get(inner_start..inner_end) else {
            search_start = end;
            continue;
        };
        comments.push(CommentSpan {
            span: SourceSpan {
                byte_start: start,
                byte_end: end,
            },
            inner,
        });
        search_start = end;
    }

    comments
}

fn parse_codes(remainder: &str) -> Vec<String> {
    remainder
        .split(',')
        .map(str::trim)
        .filter(|code| !code.is_empty())
        .map(ToOwned::to_owned)
        .collect()
}
