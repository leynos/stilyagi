//! Shared helpers for Markdown suppression tests.

use markdown::mdast::Node;
use proptest::prelude::*;
use proptest::string::string_regex;
use stilyagi_ir::SuppressionKind;

/// Return the canonical suppression kind for a directive token, or `None` when
/// the token is not a known directive verb.
pub(super) fn expected_kind_from_token(token: &str) -> Option<SuppressionKind> {
    match token {
        "ignore-next" => Some(SuppressionKind::Inline),
        "disable" | "enable" => Some(SuppressionKind::Range),
        "ignore-file" => Some(SuppressionKind::File),
        _ => None,
    }
}

/// Generate directive bodies and inter-code padding for property tests.
pub(super) fn directive_codes_and_padding() -> impl Strategy<Value = (Vec<String>, Vec<String>)> {
    prop::collection::vec(code_token_strategy(), 1..5).prop_flat_map(|codes| {
        let padding_len = codes.len().saturating_sub(1);
        (
            Just(codes),
            prop::collection::vec(space_padding_strategy(), padding_len),
        )
    })
}

/// Generate a comment code token.
pub(super) fn code_token_strategy() -> impl Strategy<Value = String> {
    regex_strategy("[A-Z][A-Z0-9]{0,7}")
}

/// Generate optional leading or trailing whitespace around a directive.
pub(super) fn whitespace_strategy() -> impl Strategy<Value = String> {
    regex_strategy("[ \t]{0,3}")
}

/// Generate optional padding after commas in a directive code list.
pub(super) fn space_padding_strategy() -> impl Strategy<Value = String> {
    regex_strategy("[ \t]{0,2}")
}

/// Compile a fixture regex pattern into a proptest strategy.
///
/// # Panics
///
/// This is a deliberate panic boundary: proptest's strategy pipeline requires
/// an infallible `impl Strategy` in argument position, so a fallible variant
/// could not be threaded through the generators below. Every caller passes a
/// `&'static str` compile-time constant, so an invalid pattern is a defect in
/// this module rather than a runtime condition.
fn regex_strategy(pattern: &'static str) -> impl Strategy<Value = String> {
    let Ok(strategy) = string_regex(pattern) else {
        panic!("fixture regex pattern {pattern:?} must compile");
    };
    strategy
}

/// Collect the IR node identifiers that correspond to HTML comments.
pub(super) fn html_node_ids(document: &stilyagi_ir::IrDocument) -> Vec<String> {
    document
        .nodes
        .iter()
        .filter(|node| node.kind == "html")
        .map(|node| node.id.clone())
        .collect()
}

/// Find the first HTML node in an AST.
pub(super) fn find_html_node(node: &Node) -> Option<&Node> {
    if matches!(node, Node::Html(_)) {
        return Some(node);
    }
    node.children()
        .and_then(|children| children.iter().find_map(find_html_node))
}

/// Collect all HTML nodes in an AST.
pub(super) fn html_nodes(node: &Node) -> Vec<&Node> {
    let mut nodes = Vec::new();
    if matches!(node, Node::Html(_)) {
        nodes.push(node);
    }
    if let Some(children) = node.children() {
        for child in children {
            nodes.extend(html_nodes(child));
        }
    }
    nodes
}
