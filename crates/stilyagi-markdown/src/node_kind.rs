//! Markdown AST node-kind spellings used in IR node metadata.

use markdown::mdast::Node;

pub(super) const fn node_kind(node: &Node) -> &'static str {
    match node {
        Node::Root(_) => "root",
        Node::Blockquote(_) => "blockquote",
        Node::FootnoteDefinition(_) => "footnoteDefinition",
        Node::MdxJsxFlowElement(_) => "mdxJsxFlowElement",
        Node::List(_) => "list",
        Node::MdxjsEsm(_) => "mdxjsEsm",
        Node::Toml(_) => "toml",
        Node::Yaml(_) => "yaml",
        Node::Break(_) => "break",
        Node::InlineCode(_) => "inlineCode",
        Node::InlineMath(_) => "inlineMath",
        Node::Delete(_) => "delete",
        Node::Emphasis(_) => "emphasis",
        Node::MdxTextExpression(_) => "mdxTextExpression",
        Node::FootnoteReference(_) => "footnoteReference",
        Node::Html(_) => "html",
        Node::Image(_) => "image",
        Node::ImageReference(_) => "imageReference",
        Node::MdxJsxTextElement(_) => "mdxJsxTextElement",
        Node::Link(_) => "link",
        Node::LinkReference(_) => "linkReference",
        Node::Strong(_) => "strong",
        Node::Text(_) => "text",
        Node::Code(_) => "code",
        Node::Math(_) => "math",
        Node::MdxFlowExpression(_) => "mdxFlowExpression",
        Node::Heading(_) => "heading",
        Node::Table(_) => "table",
        Node::ThematicBreak(_) => "thematicBreak",
        Node::TableRow(_) => "tableRow",
        Node::TableCell(_) => "tableCell",
        Node::ListItem(_) => "listItem",
        Node::Definition(_) => "definition",
        Node::Paragraph(_) => "paragraph",
    }
}
