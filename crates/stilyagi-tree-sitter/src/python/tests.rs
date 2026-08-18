//! Tests for Python docstring extraction.

use rstest::rstest;
use stilyagi_ir::SuppressionKind;
use stilyagi_test_fixtures::{
    EDGE_CASE_PYTHON_FIXTURE_PATH, MALFORMED_PYTHON_FIXTURE_PATH, NESTED_PYTHON_FIXTURE_PATH,
    SHARED_PYTHON_FIXTURE_PATH,
};
use tree_sitter::Node;

use super::support::parse_python;
use crate::test_support::{extract_python, python_fixture_document, region_owners};

const SHARED_PYTHON_FIXTURE: &str = SHARED_PYTHON_FIXTURE_PATH;
const NESTED_PYTHON_FIXTURE: &str = NESTED_PYTHON_FIXTURE_PATH;
const EDGE_CASE_PYTHON_FIXTURE: &str = EDGE_CASE_PYTHON_FIXTURE_PATH;
const MALFORMED_PYTHON_FIXTURE: &str = MALFORMED_PYTHON_FIXTURE_PATH;

fn first_comment(node: Node<'_>) -> Option<Node<'_>> {
    let mut pending = vec![node];
    while let Some(current) = pending.pop() {
        if current.kind() == "comment" {
            return Some(current);
        }
        let mut cursor = current.walk();
        let mut children = current.children(&mut cursor).collect::<Vec<_>>();
        children.reverse();
        pending.extend(children);
    }
    None
}

#[rstest]
fn shared_fixture_extracts_owner_metadata() {
    let document =
        python_fixture_document(SHARED_PYTHON_FIXTURE).expect("expected shared fixture IR");
    let owners = region_owners(&document).expect("expected docstring owner");

    assert_eq!(document.document.syntax, "python");
    assert_eq!(document.regions.len(), 4);
    assert_eq!(
        owners,
        vec![
            (
                "Module docstring for the shared Stilyagi corpus.",
                "module",
                None,
                None,
            ),
            (
                "Class docstring with prose for extraction tests.",
                "class",
                Some("FixtureExample"),
                Some("FixtureExample"),
            ),
            (
                "Return a documented value from a method docstring.",
                "function",
                Some("method"),
                Some("FixtureExample.method"),
            ),
            (
                "Use a function docstring for later Python extraction slices.",
                "function",
                Some("fixture_function"),
                Some("fixture_function"),
            ),
        ]
    );
    assert!(
        document
            .regions
            .iter()
            .all(stilyagi_ir::IrRegion::segments_reconstruct_text)
    );
}

#[rstest]
#[case(
    "ignore-next",
    SuppressionKind::Inline,
    vec!["PYDOC210"],
)]
#[case(
    "disable",
    SuppressionKind::Range,
    vec!["PYDOC210"],
)]
#[case(
    "enable",
    SuppressionKind::Range,
    vec!["PYDOC210"],
)]
#[case(
    "ignore-file",
    SuppressionKind::File,
    Vec::<&str>::new(),
)]
fn directive_comments_emit_source_backed_suppressions(
    #[case] verb: &str,
    #[case] kind: SuppressionKind,
    #[case] codes: Vec<&str>,
) {
    let source = format!("# stilyagi: {verb} {}\n", codes.join(", "));
    let document = extract_python(&source).expect("expected Python extraction");
    let comment = document
        .nodes
        .iter()
        .find(|node| node.kind == "comment")
        .expect("expected a source-backed comment node");
    let suppression = document
        .suppressions
        .first()
        .expect("expected one suppression");

    assert_eq!(document.suppressions.len(), 1);
    assert_eq!(document.errors, Vec::<stilyagi_ir::IrError>::new());
    assert_eq!(suppression.kind, kind);
    assert_eq!(
        suppression.codes,
        codes.into_iter().map(ToOwned::to_owned).collect::<Vec<_>>()
    );
    assert_eq!(suppression.origin, comment.id);
    assert_eq!(suppression.span, comment.span);
    assert!(
        document
            .nodes
            .iter()
            .any(|node| node.kind == "comment" && node.id == suppression.origin)
    );
}

#[rstest]
fn directive_comments_use_the_comment_node_kind() {
    let tree = parse_python("# stilyagi: disable PYDOC210\n")
        .expect("expected the Python grammar to parse directive comments");
    let comment = first_comment(tree.root_node()).expect("expected a comment node");

    assert_eq!(comment.kind(), "comment");
    assert_eq!(
        comment
            .utf8_text(b"# stilyagi: disable PYDOC210\n")
            .expect("expected directive comment text"),
        "# stilyagi: disable PYDOC210"
    );
}

#[rstest]
fn ordinary_comments_do_not_change_node_identity() {
    let baseline = extract_python("def f():\n    pass\n").expect("expected Python extraction");
    let with_comment = extract_python("# ordinary note\ndef f():\n    pass\n")
        .expect("expected Python extraction");

    let baseline_ids = baseline
        .nodes
        .iter()
        .map(|node| node.id.as_str())
        .collect::<Vec<_>>();
    let comment_ids = with_comment
        .nodes
        .iter()
        .map(|node| node.id.as_str())
        .collect::<Vec<_>>();

    assert_eq!(baseline.nodes.len(), with_comment.nodes.len());
    assert_eq!(baseline_ids, comment_ids);
    assert!(with_comment.suppressions.is_empty());
}

#[rstest]
fn blanket_directives_are_rejected_without_emitting_suppressions() {
    let document = extract_python("# stilyagi: disable\n").expect("expected Python extraction");

    assert!(document.suppressions.is_empty());
    assert_eq!(
        document
            .errors
            .iter()
            .map(|error| error.code.as_str())
            .collect::<Vec<_>>(),
        vec!["suppression-blanket-forbidden"]
    );
}

#[rstest]
fn nested_fixture_uses_python_qualname_semantics() {
    let document =
        python_fixture_document(NESTED_PYTHON_FIXTURE).expect("expected nested fixture IR");
    let qualnames = document
        .regions
        .iter()
        .filter_map(|region| region.owner.as_ref()?.qualname.as_deref())
        .collect::<Vec<_>>();

    assert!(qualnames.contains(&"outer_function.<locals>.inner_function"));
    assert!(qualnames.contains(&"outer_function.<locals>.LocalClass"));
    assert!(qualnames.contains(&"outer_function.<locals>.LocalClass.method"));
    assert!(qualnames.contains(&"DecoratedExample.from_value"));
    assert!(qualnames.contains(&"DecoratedExample.doubly_decorated"));
    assert!(qualnames.contains(&"async_function"));
    assert!(qualnames.contains(&"statement_nested.<locals>.inside_if"));
    assert!(qualnames.contains(&"statement_nested.<locals>.inside_for"));
    assert!(qualnames.contains(&"statement_nested.<locals>.inside_with"));
}

#[rstest]
fn edge_case_fixture_preserves_verbatim_content_and_rejects_non_docstrings() {
    let document =
        python_fixture_document(EDGE_CASE_PYTHON_FIXTURE).expect("expected edge-case fixture IR");
    let texts = document
        .regions
        .iter()
        .map(|region| region.text.as_str())
        .collect::<Vec<_>>();

    assert!(texts.contains(&"Line one.\n\n    Line two.\n    "));
    assert!(texts.contains(&r"Keep \n and \t escapes verbatim."));
    assert!(texts.contains(&r#"Mention "double quotes", 'single quotes', and a \\ backslash."#));
    assert!(texts.contains(&""));
    assert!(texts.contains(&"   "));
    assert!(!texts.iter().any(|text| text.contains("Not a v1 docstring")));
    // A leading byte-string literal (`b"""..."""`) is never a docstring, so its
    // ": bytes." marker must not appear in any extracted region.
    assert!(!texts.iter().any(|text| text.contains("bytes")));
}

#[rstest]
fn crlf_docstring_reconstructs_exactly() {
    let source = "def crlf():\r\n    \"\"\"line one\r\n    line two\"\"\"\r\n";
    let document = extract_python(source).expect("expected Python extraction");
    let region = document
        .regions
        .first()
        .expect("expected CR-LF docstring region");

    assert_eq!(region.text, "line one\r\n    line two");
    assert!(region.segments_reconstruct_text());
}

#[rstest]
fn malformed_fixture_yields_partial_ir_and_errors() {
    let document =
        python_fixture_document(MALFORMED_PYTHON_FIXTURE).expect("expected malformed fixture IR");

    assert_eq!(document.regions.len(), 1);
    assert_eq!(
        document.regions.first().map(|region| region.text.as_str()),
        Some("Module docstring before malformed Python source.")
    );
    assert!(!document.errors.is_empty());
}

#[rstest]
fn deeply_nested_source_stops_at_the_depth_limit_without_overflowing() {
    // Deeply nested parenthesised expressions build a tree far beyond the
    // traversal cap without needing quadratic source size. Extraction must
    // return partial IR with a recoverable depth-limit error instead of
    // overflowing the stack.
    let depth = 2_000;
    let source = format!("x = {}1{}\n", "(".repeat(depth), ")".repeat(depth));
    let document = extract_python(&source).expect("expected Python extraction");

    assert!(
        document
            .errors
            .iter()
            .any(|error| error.code == "python-traversal-depth-limit"),
        "expected a recoverable depth-limit error, got {:?}",
        document.errors
    );
}
