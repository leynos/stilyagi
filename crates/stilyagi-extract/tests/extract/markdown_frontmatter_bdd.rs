//! BDD coverage for whole-block Markdown YAML frontmatter IR.

use rstest::fixture;
use rstest_bdd_macros::{given, scenario, then, when};
use stilyagi_extract::{ExtractDocument, ExtractSyntax, extract_document};
use stilyagi_ir::{IrDocument, IrRegion};
use stilyagi_test_support::read_corpus_fixture;

const YAML_FRONTMATTER_FIXTURE_PATH: &str =
    "tests/fixtures/corpus/markdown/valid/yaml-frontmatter.md.fixture";

#[derive(Default)]
struct MarkdownFrontmatterState {
    source: Option<String>,
    document: Option<ExtractDocument>,
}

#[fixture]
fn markdown_frontmatter_state() -> MarkdownFrontmatterState {
    MarkdownFrontmatterState::default()
}

#[given("the YAML frontmatter Markdown fixture")]
fn the_yaml_frontmatter_markdown_fixture(
    markdown_frontmatter_state: &mut MarkdownFrontmatterState,
) {
    markdown_frontmatter_state.source =
        Some(match read_corpus_fixture(YAML_FRONTMATTER_FIXTURE_PATH) {
            Ok(source) => source,
            Err(error) => panic!("expected the YAML frontmatter fixture to be readable: {error}"),
        });
}

#[when("the Markdown fixture is extracted")]
fn the_markdown_fixture_is_extracted(markdown_frontmatter_state: &mut MarkdownFrontmatterState) {
    let Some(source) = markdown_frontmatter_state.source.as_deref() else {
        panic!("expected the Markdown fixture source");
    };
    markdown_frontmatter_state.document =
        Some(match extract_document(source, ExtractSyntax::Markdown) {
            Ok(document) => document,
            Err(error) => panic!("expected the YAML frontmatter fixture to extract: {error}"),
        });
}

#[then("the frontmatter IR region is source-backed as YAML")]
fn the_frontmatter_ir_region_is_source_backed_as_yaml(
    markdown_frontmatter_state: &MarkdownFrontmatterState,
) {
    let Some(source) = markdown_frontmatter_state.source.as_deref() else {
        panic!("expected the Markdown fixture source");
    };
    let Some(document) = markdown_frontmatter_state.document.as_ref() else {
        panic!("expected the extracted Markdown document");
    };
    let Some(ir) = document.ir() else {
        panic!("expected the Markdown IR envelope");
    };
    let frontmatter = frontmatter_region(ir);
    let Some(segment) = frontmatter.segments.first() else {
        panic!("expected one source-backed frontmatter segment");
    };
    let Some(span) = segment.source else {
        panic!("expected frontmatter source byte coordinates");
    };

    assert!(
        frontmatter
            .attrs
            .get("format")
            .is_some_and(|format| format.as_str() == Some("yaml")),
        "expected the frontmatter format attribute to be YAML"
    );
    assert_eq!(frontmatter.segments.len(), 1);
    assert_eq!(
        source.get(span.byte_start..span.byte_end),
        Some(frontmatter.text.as_str()),
        "expected the segment to retain the complete fenced block"
    );
    assert_eq!(frontmatter.text, "---\ntitle: Fixture title\n---");
    assert!(
        source
            .get(span.byte_end..)
            .is_some_and(|suffix| suffix.starts_with("\n\n")),
        "expected the closing fence line ending and paragraph separator outside the block"
    );
}

fn frontmatter_region(ir: &IrDocument) -> &IrRegion {
    let Some(region) = ir
        .regions
        .iter()
        .find(|region| region.kind == "frontmatter")
    else {
        panic!("expected a whole-block frontmatter IR region");
    };
    region
}

#[scenario(
    path = "tests/features/markdown_frontmatter.feature",
    name = "YAML frontmatter is represented by its complete fenced block"
)]
fn yaml_frontmatter_is_represented_by_its_complete_fenced_block(
    #[from(markdown_frontmatter_state)] _state: MarkdownFrontmatterState,
) {
}
