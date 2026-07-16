//! Property tests for Markdown-generated IR segment and parent invariants.

use proptest::prelude::*;
use stilyagi_ir::SourceIdentity;

use super::{
    parent_regions_reference_earlier_regions, region_segments_are_contiguous,
    regions_reconstruct_text, source_backed_segments_match_source,
    synthetic_segments_use_known_reasons,
};
use crate::markdown_ir_document;

#[derive(Debug, Clone)]
enum MarkdownConstruct {
    Link { text: String, title: String },
    Image { alt: String },
    List { first: String, second: String },
    Blockquote { text: String },
}

fn plain_text() -> impl Strategy<Value = String> {
    "[A-Za-z][A-Za-z0-9 ]{0,24}".prop_map(|text| text.trim().to_owned())
}

fn markdown_construct() -> impl Strategy<Value = MarkdownConstruct> {
    prop_oneof![
        (plain_text(), plain_text())
            .prop_map(|(text, title)| MarkdownConstruct::Link { text, title }),
        plain_text().prop_map(|alt| MarkdownConstruct::Image { alt }),
        (plain_text(), plain_text())
            .prop_map(|(first, second)| MarkdownConstruct::List { first, second }),
        plain_text().prop_map(|text| MarkdownConstruct::Blockquote { text }),
    ]
}

proptest! {
    #[test]
    fn generated_markdown_constructs_preserve_ir_invariants(
        constructs in prop::collection::vec(markdown_construct(), 1..8),
    ) {
        let source = markdown_source_for(&constructs);
        let document = markdown_ir_document(&source, SourceIdentity::anonymous())
            .expect("generated Markdown should parse");

        prop_assert!(regions_reconstruct_text(&document));
        prop_assert!(region_segments_are_contiguous(&document));
        prop_assert!(source_backed_segments_match_source(&document, &source));
        prop_assert!(synthetic_segments_use_known_reasons(&document));
        prop_assert!(parent_regions_reference_earlier_regions(&document));
    }
}

fn markdown_source_for(constructs: &[MarkdownConstruct]) -> String {
    constructs
        .iter()
        .map(markdown_block_for)
        .collect::<Vec<_>>()
        .join("\n\n")
}

fn markdown_block_for(construct: &MarkdownConstruct) -> String {
    match construct {
        MarkdownConstruct::Link { text, title } => {
            format!("[{text}](https://example.test \"{title}\")")
        }
        MarkdownConstruct::Image { alt } => {
            format!("![{alt}](https://example.test/image.png)")
        }
        MarkdownConstruct::List { first, second } => format!("- {first}\n- {second}"),
        MarkdownConstruct::Blockquote { text } => format!("> {text}"),
    }
}
