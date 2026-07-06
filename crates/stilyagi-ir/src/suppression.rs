//! Syntax-agnostic suppression directive parsing and validation helpers.

use std::collections::BTreeSet;

use crate::{IrError, IrSuppression, SourceSpan, SuppressionKind};

/// A candidate directive assembled by a syntax frontend.
///
/// The `body` should contain the comment text with the syntax-specific
/// delimiters removed.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SuppressionCandidate {
    /// Stable node identifier for the comment node that produced this candidate.
    pub origin: String,
    /// Source span covered by the directive comment.
    pub span: SourceSpan,
    /// Delimiter-stripped comment body to parse as a directive.
    pub body: String,
}

/// Canonical suppression directive verbs recognised in comment bodies.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DirectiveVerb {
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
pub struct ParsedDirective {
    /// Directive verb.
    pub verb: DirectiveVerb,
    /// Named rule codes or prefixes.
    pub codes: Vec<String>,
}

/// Outcome of parsing a candidate comment body.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DirectiveOutcome {
    /// The comment body is not a Stilyagi directive.
    NotADirective,
    /// The comment body is a recognised directive and has valid syntax.
    Parsed(ParsedDirective),
    /// The comment body matches the canonical marker but violates a rule.
    Rejected(DirectiveError),
}

/// Parse errors for canonical suppression directives.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DirectiveError {
    /// Inline or range directives named no code.
    BlanketForbidden,
    /// The verb token is not one of the recognised canonical verbs.
    UnknownVerb,
}

/// A comment slice found inside a larger HTML source span.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CommentSpan<'source> {
    /// Comment span relative to the scanned source slice.
    pub span: SourceSpan,
    /// Comment body between `<!--` and `-->`.
    pub inner: &'source str,
}

/// Validation errors produced while checking assembled suppressions.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SuppressionValidationError {
    /// The suppression does not resolve to a known origin node.
    OriginUnresolved {
        /// Stable suppression identifier.
        suppression_id: String,
        /// Origin node that could not be resolved.
        origin: String,
    },
    /// The suppression span does not resolve to source bytes.
    SpanInvalid {
        /// Stable suppression identifier.
        suppression_id: String,
        /// Origin node that produced the suppression.
        origin: String,
        /// Span that could not be resolved.
        span: SourceSpan,
    },
}

/// Return whether a comment body uses the canonical suppression marker.
#[must_use]
pub fn is_directive_marker(inner: &str) -> bool {
    inner.trim().starts_with("stilyagi:")
}

/// Return every HTML comment found in a source slice.
#[must_use]
pub fn scan_comment_spans(source: &str) -> Vec<CommentSpan<'_>> {
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

/// Parse the inner text of a comment into a directive outcome.
///
/// The input should be the bytes between the comment delimiters.
pub fn parse_comment_directive(inner: &str) -> DirectiveOutcome {
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
/// Assemble suppression IR from directive candidates.
///
/// # Examples
///
/// ```
/// use stilyagi_ir::suppression::{suppressions_from_candidates, SuppressionCandidate};
/// use stilyagi_ir::{SourceSpan, SuppressionKind};
///
/// let (suppressions, errors) = suppressions_from_candidates([SuppressionCandidate {
///     origin: "n1".to_owned(),
///     span: SourceSpan::new(0, 28).expect("valid span"),
///     body: "stilyagi: ignore-file".to_owned(),
/// }]);
///
/// assert!(errors.is_empty());
/// assert_eq!(suppressions.len(), 1);
/// assert_eq!(suppressions[0].kind, SuppressionKind::File);
/// ```
#[must_use]
pub fn suppressions_from_candidates(
    candidates: impl IntoIterator<Item = SuppressionCandidate>,
) -> (Vec<IrSuppression>, Vec<IrError>) {
    let mut suppressions = Vec::new();
    let mut errors = Vec::new();

    for candidate in candidates {
        match parse_comment_directive(&candidate.body) {
            DirectiveOutcome::NotADirective => {}
            DirectiveOutcome::Parsed(parsed) => {
                let suppression_id = suppressions.len();
                suppressions.push(IrSuppression {
                    id: format!("s{suppression_id}"),
                    kind: verb_kind(parsed.verb),
                    range_role: verb_range_role(parsed.verb),
                    codes: parsed.codes,
                    span: candidate.span,
                    origin: candidate.origin,
                });
            }
            DirectiveOutcome::Rejected(DirectiveError::BlanketForbidden) => {
                errors.push(IrError {
                    code: "suppression-blanket-forbidden".to_owned(),
                    message: "blanket suppression directives must name at least one code"
                        .to_owned(),
                    span: Some(candidate.span),
                });
            }
            DirectiveOutcome::Rejected(DirectiveError::UnknownVerb) => {
                errors.push(IrError {
                    code: "suppression-unknown-verb".to_owned(),
                    message: "suppression directive verb is not recognised".to_owned(),
                    span: Some(candidate.span),
                });
            }
        }
    }

    (suppressions, errors)
}

/// Validate suppression origins and spans against source-backed IR.
///
/// # Examples
///
/// ```
/// use std::collections::BTreeSet;
///
/// use stilyagi_ir::suppression::{validate_suppressions, SuppressionValidationError};
/// use stilyagi_ir::{IrSuppression, SourceSpan, SuppressionKind};
///
/// let suppressions = vec![IrSuppression {
///     id: "s0".to_owned(),
///     kind: SuppressionKind::Inline,
///     range_role: None,
///     codes: vec!["PUN201".to_owned()],
///     span: SourceSpan::new(0, 28).expect("valid span"),
///     origin: "n0".to_owned(),
/// }];
/// let node_ids = BTreeSet::from(["n0"]);
///
/// assert!(matches!(
///     validate_suppressions(&suppressions, "<!-- stilyagi: ignore-next PUN201 -->", &node_ids),
///     Ok(())
/// ));
///
/// let missing_origin = BTreeSet::from(["n1"]);
/// assert!(matches!(
///     validate_suppressions(&suppressions, "<!-- stilyagi: ignore-next PUN201 -->", &missing_origin),
///     Err(SuppressionValidationError::OriginUnresolved { .. })
/// ));
/// ```
///
/// # Errors
///
/// Returns the first unresolved origin node or out-of-bounds source span.
pub fn validate_suppressions<'source>(
    suppressions: &[IrSuppression],
    source: &'source str,
    node_ids: &BTreeSet<&'source str>,
) -> Result<(), SuppressionValidationError> {
    for suppression in suppressions {
        validate_suppression_origin(suppression, node_ids)?;
        validate_suppression_span(suppression, source)?;
    }
    Ok(())
}

/// Map a directive verb onto the IR suppression kind.
#[must_use]
pub const fn verb_kind(verb: DirectiveVerb) -> SuppressionKind {
    match verb {
        DirectiveVerb::IgnoreNext => SuppressionKind::Inline,
        DirectiveVerb::Disable | DirectiveVerb::Enable => SuppressionKind::Range,
        DirectiveVerb::IgnoreFile => SuppressionKind::File,
    }
}

/// Map a range directive verb onto its IR polarity.
#[must_use]
pub const fn verb_range_role(verb: DirectiveVerb) -> Option<crate::RangeRole> {
    match verb {
        DirectiveVerb::Disable => Some(crate::RangeRole::Open),
        DirectiveVerb::Enable => Some(crate::RangeRole::Close),
        DirectiveVerb::IgnoreNext | DirectiveVerb::IgnoreFile => None,
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

fn validate_suppression_origin(
    suppression: &IrSuppression,
    node_ids: &BTreeSet<&str>,
) -> Result<(), SuppressionValidationError> {
    if node_ids.contains(suppression.origin.as_str()) {
        return Ok(());
    }
    Err(SuppressionValidationError::OriginUnresolved {
        suppression_id: suppression.id.clone(),
        origin: suppression.origin.clone(),
    })
}

fn validate_suppression_span(
    suppression: &IrSuppression,
    source: &str,
) -> Result<(), SuppressionValidationError> {
    if source
        .get(suppression.span.byte_start..suppression.span.byte_end)
        .is_some()
    {
        return Ok(());
    }
    Err(SuppressionValidationError::SpanInvalid {
        suppression_id: suppression.id.clone(),
        origin: suppression.origin.clone(),
        span: suppression.span,
    })
}
