//! Coverage tests for the promised Markdown IR region vocabulary.

use std::collections::BTreeSet;
use std::ffi::OsStr;
use std::path::{Path, PathBuf};

use markdown::message::Message;
use rstest::rstest;
use stilyagi_ir::{IrDocument, IrRegion, RegionKind, SyntheticReason};
use stilyagi_test_fixtures::ExpectValid;
use stilyagi_test_support::{FixtureReadError, fixture_paths_in, read_corpus_fixture};

use super::source_identity;
use crate::markdown_ir_document;

#[rstest]
fn valid_markdown_corpus_covers_promised_markdown_region_kinds() {
    let fixture_paths = valid_markdown_fixture_paths()
        .expect("expected readable Markdown corpus fixture directory");
    let mut emitted_kinds = BTreeSet::new();

    for relative_path in fixture_paths {
        let fixture_context = format!(
            "expected readable Markdown corpus fixture {}",
            relative_path.display()
        );
        let source = read_corpus_fixture(&relative_path).expect(&fixture_context);
        let document_context = format!("expected Markdown IR document {}", relative_path.display());
        let document = document_for(&relative_path, &source).expect(&document_context);
        emitted_kinds.extend(document.regions.into_iter().map(|region| region.kind));
    }

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
    let relative_path = Path::new("tests/fixtures/corpus/markdown/valid/lists.md.fixture");
    let fixture_context = format!(
        "expected readable Markdown corpus fixture {}",
        relative_path.display()
    );
    let source = read_corpus_fixture(relative_path).expect(&fixture_context);
    let document_context = format!("expected Markdown IR document {}", relative_path.display());
    let document = document_for(relative_path, &source).expect(&document_context);
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
    let relative_path = Path::new("tests/fixtures/corpus/markdown/valid/blockquotes.md.fixture");
    let fixture_context = format!(
        "expected readable Markdown corpus fixture {}",
        relative_path.display()
    );
    let source = read_corpus_fixture(relative_path).expect(&fixture_context);
    let document_context = format!("expected Markdown IR document {}", relative_path.display());
    let document = document_for(relative_path, &source).expect(&document_context);
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
    let fixture_context = format!(
        "expected readable Markdown corpus fixture {}",
        relative_path.display()
    );
    let source = read_corpus_fixture(relative_path).expect(&fixture_context);
    let document_context = format!("expected Markdown IR document {}", relative_path.display());
    let document = document_for(relative_path, &source).expect(&document_context);
    let frontmatter = single_region_of_kind(&document, RegionKind::Frontmatter);

    assert_frontmatter_source_backed(frontmatter, &source);
}

#[rstest]
fn image_alt_and_link_title_regions_are_synthetic_decoded_text() {
    let relative_path =
        Path::new("tests/fixtures/corpus/markdown/valid/links-and-images.md.fixture");
    let fixture_context = format!(
        "expected readable Markdown corpus fixture {}",
        relative_path.display()
    );
    let source = read_corpus_fixture(relative_path).expect(&fixture_context);
    let document_context = format!("expected Markdown IR document {}", relative_path.display());
    let document = document_for(relative_path, &source).expect(&document_context);
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

#[rstest]
fn empty_link_title_does_not_produce_a_region() {
    let relative_path =
        Path::new("tests/fixtures/corpus/markdown/valid/links-and-images.md.fixture");
    let fixture_context = format!(
        "expected readable Markdown corpus fixture {}",
        relative_path.display()
    );
    let source = read_corpus_fixture(relative_path).expect(&fixture_context);
    let document_context = format!("expected Markdown IR document {}", relative_path.display());
    let document = document_for(relative_path, &source).expect(&document_context);
    let link_titles = regions_of_kind(&document, RegionKind::LinkTitle);
    assert!(
        link_titles.iter().any(|region| !region.text.is_empty()),
        "fixture must emit at least one non-empty link_title region"
    );
    assert!(
        link_titles.iter().all(|region| !region.text.is_empty()),
        "every emitted link_title region must have non-empty text"
    );
}

#[rstest]
fn suppression_directive_fixture_emits_all_document_suppression_kinds() {
    let relative_path =
        Path::new("tests/fixtures/corpus/markdown/valid/suppression-directives.md.fixture");
    let fixture_context = format!(
        "expected readable Markdown corpus fixture {}",
        relative_path.display()
    );
    let source = read_corpus_fixture(relative_path).expect(&fixture_context);
    let document_context = format!("expected Markdown IR document {}", relative_path.display());
    let document = document_for(relative_path, &source).expect(&document_context);
    let kinds = document
        .suppressions
        .iter()
        .map(|suppression| suppression.kind)
        .collect::<Vec<_>>();

    assert_eq!(document.errors, Vec::new());
    assert!(kinds.contains(&stilyagi_ir::SuppressionKind::Inline));
    assert!(kinds.contains(&stilyagi_ir::SuppressionKind::Range));
    assert!(kinds.contains(&stilyagi_ir::SuppressionKind::File));
    assert!(document.suppressions.iter().all(|suppression| {
        source
            .get(suppression.span.byte_start..suppression.span.byte_end)
            .is_some()
    }));
}

fn valid_markdown_fixture_paths() -> Result<Vec<PathBuf>, FixtureReadError> {
    let mut paths = fixture_paths_in(Path::new("tests/fixtures/corpus/markdown/valid"))?
        .into_iter()
        .map(PathBuf::from)
        .filter(|path| is_markdown_fixture(path))
        .collect::<Vec<_>>();
    paths.sort();
    Ok(paths)
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

/// Build the IR document for one corpus fixture.
///
/// Arrangement is fallible, so this propagates instead of panicking; callers
/// unwrap in the test body, where a failure is the test verdict.
fn document_for(relative_path: &Path, source: &str) -> Result<IrDocument, Message> {
    markdown_ir_document(source, source_identity(relative_path))
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

#[track_caller]
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
        .expect_valid("frontmatter source segment");
    let span = segment
        .source
        .expect_valid("frontmatter segment source span");
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
