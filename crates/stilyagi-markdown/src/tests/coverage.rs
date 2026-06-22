//! Coverage tests for the promised Markdown IR region vocabulary.

use std::collections::BTreeSet;
use std::ffi::OsStr;
use std::path::{Path, PathBuf};

use rstest::rstest;
use stilyagi_ir::{IrDocument, IrRegion, RegionKind, SyntheticReason};

use super::source_identity;
use crate::markdown_ir_document;

#[rstest]
fn valid_markdown_corpus_covers_promised_markdown_region_kinds() {
    let emitted_kinds = emitted_region_kinds_for_valid_markdown_corpus();
    let promised_kinds = promised_markdown_region_kinds();

    for promised_kind in promised_kinds {
        assert!(
            emitted_kinds.contains(promised_kind),
            "valid Markdown corpus did not emit promised region kind {promised_kind}"
        );
    }
}

#[rstest]
fn list_item_regions_are_thin_structural_parents() {
    let document = document_for(Path::new(
        "tests/fixtures/corpus/markdown/valid/lists.md.fixture",
    ));
    let list_items = regions_of_kind(&document, RegionKind::ListItem);

    assert_thin_structural_regions(&list_items, "list_item");
    assert!(list_items.iter().any(|region| {
        region.attrs.get("ordered") == Some(&serde_json::json!(true))
            && region.attrs.get("start") == Some(&serde_json::json!(3))
    }));
    assert!(
        list_items
            .iter()
            .any(|region| { region.attrs.get("checked") == Some(&serde_json::json!(true)) })
    );
    assert_paragraph_children_linked_to(&document, &list_items, "list_item");
}

#[rstest]
fn blockquote_regions_are_thin_structural_parents() {
    let document = document_for(Path::new(
        "tests/fixtures/corpus/markdown/valid/blockquotes.md.fixture",
    ));
    let blockquotes = regions_of_kind(&document, RegionKind::Blockquote);

    assert_thin_structural_regions(&blockquotes, "blockquote");
    assert!(
        blockquotes
            .iter()
            .any(|region| { region.attrs.get("depth") == Some(&serde_json::json!(2)) })
    );
    assert_paragraph_children_linked_to(&document, &blockquotes, "blockquote");
}

#[rstest]
fn frontmatter_region_is_source_backed_over_the_fenced_block() {
    let relative_path = Path::new("tests/fixtures/corpus/markdown/valid/frontmatter.md.fixture");
    let source = must_read_fixture(relative_path);
    let document = must_markdown_ir_document(&source, relative_path);
    let frontmatter = single_region_of_kind(&document, RegionKind::Frontmatter);

    assert_frontmatter_source_backed(frontmatter, &source);
}

#[rstest]
fn image_alt_and_link_title_regions_are_synthetic_decoded_text() {
    let document = document_for(Path::new(
        "tests/fixtures/corpus/markdown/valid/links-and-images.md.fixture",
    ));
    let image_alt = regions_of_kind(&document, RegionKind::ImageAlt);
    let link_title = regions_of_kind(&document, RegionKind::LinkTitle);

    assert_decoded_text_regions_contain(&image_alt, "plain alt");
    assert_decoded_text_regions_contain(&image_alt, "AT&T");
    assert_decoded_text_regions_contain(&link_title, "Inline title");
    assert!(
        link_title.iter().all(|region| !region.text.is_empty()),
        "empty link titles must not emit link_title regions"
    );
}

fn emitted_region_kinds_for_valid_markdown_corpus() -> BTreeSet<String> {
    valid_markdown_fixture_paths()
        .into_iter()
        .flat_map(|relative_path| {
            let source = must_read_fixture(&relative_path);
            let document = must_markdown_ir_document(&source, &relative_path);

            document
                .regions
                .into_iter()
                .map(|region| region.kind)
                .collect::<Vec<_>>()
        })
        .collect()
}

fn valid_markdown_fixture_paths() -> Vec<PathBuf> {
    let mut paths = must_list_fixture_paths(Path::new("tests/fixtures/corpus/markdown/valid"))
        .into_iter()
        .map(PathBuf::from)
        .filter(|path| is_markdown_fixture(path))
        .collect::<Vec<_>>();
    paths.sort();
    paths
}

fn is_markdown_fixture(path: &Path) -> bool {
    path.extension().is_some_and(|extension| {
        extension.eq_ignore_ascii_case(OsStr::new("md"))
            || (extension.eq_ignore_ascii_case(OsStr::new("fixture"))
                && path
                    .file_stem()
                    .is_some_and(file_stem_has_markdown_extension))
    })
}

fn file_stem_has_markdown_extension(file_stem: &OsStr) -> bool {
    Path::new(file_stem)
        .extension()
        .is_some_and(|extension| extension.eq_ignore_ascii_case(OsStr::new("md")))
}

fn promised_markdown_region_kinds() -> Vec<&'static str> {
    vec![
        RegionKind::Heading.as_str(),
        RegionKind::Paragraph.as_str(),
        RegionKind::ListItem.as_str(),
        RegionKind::Blockquote.as_str(),
        RegionKind::TableCell.as_str(),
        RegionKind::Frontmatter.as_str(),
        RegionKind::ImageAlt.as_str(),
        RegionKind::LinkTitle.as_str(),
    ]
}

fn document_for(relative_path: &Path) -> IrDocument {
    let source = must_read_fixture(relative_path);
    must_markdown_ir_document(&source, relative_path)
}

fn regions_of_kind(document: &IrDocument, kind: RegionKind) -> Vec<&IrRegion> {
    document
        .regions
        .iter()
        .filter(|region| region.kind == kind.as_str())
        .collect()
}

fn single_region_of_kind(document: &IrDocument, kind: RegionKind) -> &IrRegion {
    let regions = regions_of_kind(document, kind);
    assert_eq!(regions.len(), 1);
    must_some!(
        regions.into_iter().next(),
        "expected one region of kind {kind}"
    )
}

fn must_read_fixture(relative_path: &Path) -> String {
    match stilyagi_test_support::read_corpus_fixture(relative_path) {
        Ok(source) => source,
        Err(error) => panic!("expected readable Markdown fixture: {error}"),
    }
}

fn must_markdown_ir_document(source: &str, relative_path: &Path) -> IrDocument {
    match markdown_ir_document(source, source_identity(relative_path)) {
        Ok(document) => document,
        Err(error) => panic!("expected Markdown IR document: {error}"),
    }
}

fn must_list_fixture_paths(relative_dir: &Path) -> Vec<String> {
    match stilyagi_test_support::fixture_paths_in(relative_dir) {
        Ok(paths) => paths,
        Err(error) => panic!("expected readable Markdown fixture directory: {error}"),
    }
}

fn is_decoded_synthetic_region(region: &IrRegion) -> bool {
    region.attrs.get("source_backed") == Some(&serde_json::json!(false))
        && region.segments.len() == 1
        && region.segments.iter().all(|segment| {
            segment.source.is_none()
                && segment.synthetic.as_deref() == Some(SyntheticReason::DecodedText.as_str())
        })
}

fn assert_thin_structural_regions(regions: &[&IrRegion], kind_name: &str) {
    assert!(
        !regions.is_empty(),
        "expected at least one {kind_name} region"
    );
    assert!(
        regions
            .iter()
            .all(|r| r.text.is_empty() && r.segments.is_empty() && r.owner.is_none()),
        "{kind_name} regions must be thin structural (no text, segments, or owner)"
    );
}

fn assert_paragraph_children_linked_to(
    document: &IrDocument,
    parents: &[&IrRegion],
    scope_name: &str,
) {
    assert!(
        document.regions.iter().any(|region| {
            region.kind == RegionKind::Paragraph.as_str()
                && region.scope.iter().any(|s| s == scope_name)
                && region
                    .parent_region
                    .as_deref()
                    .is_some_and(|parent| parents.iter().any(|p| p.id == parent))
        }),
        "expected a paragraph scoped to {scope_name:?} linked to a parent region"
    );
}

fn assert_frontmatter_source_backed(region: &IrRegion, source: &str) {
    assert!(
        region.text.starts_with("---\n"),
        "frontmatter text must start with '---\\n'"
    );
    assert!(
        region.text.ends_with("---"),
        "frontmatter text must end with '---'"
    );
    assert_eq!(
        region.attrs.get("format"),
        Some(&serde_json::json!("yaml")),
        "frontmatter format attribute must be 'yaml'"
    );
    assert_eq!(
        region.segments.len(),
        1,
        "frontmatter must have exactly one segment"
    );
    let segment = region
        .segments
        .first()
        .expect("expected frontmatter source segment");
    let span = segment
        .source
        .expect("expected frontmatter to be source-backed");
    assert_eq!(
        source.get(span.byte_start..span.byte_end),
        Some(region.text.as_str()),
        "frontmatter source span must match region text"
    );
}

fn assert_decoded_text_regions_contain(regions: &[&IrRegion], expected_text: &str) {
    assert!(
        regions.iter().any(|r| r.text == expected_text),
        "expected a decoded-text region with text {expected_text:?}"
    );
    assert!(
        regions.iter().all(|r| is_decoded_synthetic_region(r)),
        "all decoded-text regions must be synthetic with reason 'decoded_text'"
    );
}
