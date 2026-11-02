//! Coverage tests for the promised Markdown IR region vocabulary.

use std::collections::BTreeSet;
use std::ffi::OsStr;
use std::fmt;
use std::path::{Path, PathBuf};

use markdown::message::Message;
use rstest::rstest;
use stilyagi_ir::{IrDocument, IrRegion, RegionKind, SourceSpan, SyntheticReason};
use stilyagi_test_support::FixtureReadError;

use super::source_identity;
use crate::markdown_ir_document;

/// Failure modes encountered while loading a Markdown corpus fixture.
#[derive(Debug)]
enum FixtureError {
    /// The fixture could not be read from the corpus.
    Read(FixtureReadError),
    /// The fixture could not be parsed into a Markdown IR document.
    Parse(Box<Message>),
}

impl fmt::Display for FixtureError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Read(error) => write!(formatter, "expected readable Markdown fixture: {error}"),
            Self::Parse(error) => write!(formatter, "expected Markdown IR document: {error}"),
        }
    }
}

impl From<FixtureReadError> for FixtureError {
    fn from(error: FixtureReadError) -> Self {
        Self::Read(error)
    }
}

impl From<Message> for FixtureError {
    fn from(error: Message) -> Self {
        Self::Parse(Box::new(error))
    }
}

/// Assert that every region in `regions` is a thin structural parent.
macro_rules! assert_thin_structural_regions {
    ($regions:expr, $kind_name:expr $(,)?) => {{
        let regions = &$regions;
        let kind_name = $kind_name;
        assert!(
            !regions.is_empty(),
            "expected at least one {kind_name} region"
        );
        assert!(
            regions
                .iter()
                .all(|region| is_thin_structural_region(region)),
            "{kind_name} regions must be thin structural (no text, segments, or owner)"
        );
    }};
}

/// Assert that a paragraph scoped to `scope_name` links to one of `parents`.
macro_rules! assert_paragraph_children_linked_to {
    ($document:expr, $parents:expr, $scope_name:expr $(,)?) => {{
        let scope_name = $scope_name;
        assert!(
            has_paragraph_child_linked_to(&$document, &$parents, scope_name),
            "expected a paragraph scoped to {scope_name:?} linked to a parent region"
        );
    }};
}

/// Assert that `regions` hold a decoded-text region with `expected_text` and
/// that every region in the set is synthetic decoded text.
macro_rules! assert_decoded_text_regions_contain {
    ($regions:expr, $expected_text:expr $(,)?) => {{
        let regions = &$regions;
        let expected_text = $expected_text;
        assert!(
            regions.iter().any(|region| region.text == expected_text),
            "expected a decoded-text region with text {expected_text:?}"
        );
        assert!(
            regions
                .iter()
                .all(|region| is_decoded_synthetic_region(region)),
            "all decoded-text regions must be synthetic with reason 'decoded_text'"
        );
    }};
}

#[rstest]
fn valid_markdown_corpus_covers_promised_markdown_region_kinds() {
    let emitted_kinds = emitted_region_kinds_for_valid_markdown_corpus()
        .expect("expected region kinds from the valid Markdown corpus");
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
    ))
    .expect("expected the lists fixture document");
    let list_items = regions_of_kind(&document, RegionKind::ListItem);

    assert_thin_structural_regions!(list_items, "list_item");
    assert!(list_items.iter().any(|region| {
        region.attrs.get("ordered") == Some(&serde_json::json!(true))
            && region.attrs.get("start") == Some(&serde_json::json!(3))
    }));
    assert!(
        list_items
            .iter()
            .any(|region| { region.attrs.get("checked") == Some(&serde_json::json!(true)) })
    );
    assert_paragraph_children_linked_to!(document, list_items, "list_item");
}

#[rstest]
fn blockquote_regions_are_thin_structural_parents() {
    let document = document_for(Path::new(
        "tests/fixtures/corpus/markdown/valid/blockquotes.md.fixture",
    ))
    .expect("expected the blockquotes fixture document");
    let blockquotes = regions_of_kind(&document, RegionKind::Blockquote);

    assert_thin_structural_regions!(blockquotes, "blockquote");
    assert!(
        blockquotes
            .iter()
            .any(|region| { region.attrs.get("depth") == Some(&serde_json::json!(2)) })
    );
    assert_paragraph_children_linked_to!(document, blockquotes, "blockquote");
}

#[rstest]
fn frontmatter_region_is_source_backed_over_the_fenced_block() {
    let relative_path = Path::new("tests/fixtures/corpus/markdown/valid/frontmatter.md.fixture");
    let source = fixture_source(relative_path).expect("expected the frontmatter fixture source");
    let document =
        ir_document_for(&source, relative_path).expect("expected the frontmatter fixture document");
    let frontmatter_regions = regions_of_kind(&document, RegionKind::Frontmatter);

    assert_eq!(frontmatter_regions.len(), 1);
    let frontmatter = frontmatter_regions
        .first()
        .copied()
        .expect("expected one region of kind frontmatter");
    assert!(
        frontmatter.text.starts_with("---\n"),
        "frontmatter text must start with '---\\n'"
    );
    assert!(
        frontmatter.text.ends_with("---"),
        "frontmatter text must end with '---'"
    );
    assert_eq!(
        frontmatter.attrs.get("format"),
        Some(&serde_json::json!("yaml")),
        "frontmatter format attribute must be 'yaml'"
    );
    assert_eq!(
        frontmatter.segments.len(),
        1,
        "frontmatter must have exactly one segment"
    );
    let span = first_segment_source_span(frontmatter)
        .expect("expected frontmatter to be source-backed by its first segment");
    assert_eq!(
        source.get(span.byte_start..span.byte_end),
        Some(frontmatter.text.as_str()),
        "frontmatter source span must match region text"
    );
}

#[rstest]
fn image_alt_and_link_title_regions_are_synthetic_decoded_text() {
    let document = document_for(Path::new(
        "tests/fixtures/corpus/markdown/valid/links-and-images.md.fixture",
    ))
    .expect("expected the links-and-images fixture document");
    let image_alt = regions_of_kind(&document, RegionKind::ImageAlt);
    let link_title = regions_of_kind(&document, RegionKind::LinkTitle);

    assert_decoded_text_regions_contain!(image_alt, "plain alt");
    assert_decoded_text_regions_contain!(image_alt, "AT&T");
    assert_decoded_text_regions_contain!(link_title, "Inline title");
    assert!(
        link_title.iter().all(|region| !region.text.is_empty()),
        "empty link titles must not emit link_title regions"
    );
}

#[rstest]
fn empty_link_title_does_not_produce_a_region() {
    let document = document_for(Path::new(
        "tests/fixtures/corpus/markdown/valid/links-and-images.md.fixture",
    ))
    .expect("expected the links-and-images fixture document");
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
    let source = fixture_source(relative_path).expect("expected the suppression fixture source");
    let document =
        ir_document_for(&source, relative_path).expect("expected the suppression fixture document");
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

fn emitted_region_kinds_for_valid_markdown_corpus() -> Result<BTreeSet<String>, FixtureError> {
    let mut kinds = BTreeSet::new();
    for relative_path in valid_markdown_fixture_paths()? {
        let document = document_for(&relative_path)?;
        kinds.extend(document.regions.into_iter().map(|region| region.kind));
    }
    Ok(kinds)
}

fn valid_markdown_fixture_paths() -> Result<Vec<PathBuf>, FixtureReadError> {
    let mut paths =
        stilyagi_test_support::fixture_paths_in(Path::new("tests/fixtures/corpus/markdown/valid"))?
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

/// Read a repository-relative Markdown corpus fixture.
fn fixture_source(relative_path: &Path) -> Result<String, FixtureReadError> {
    stilyagi_test_support::read_corpus_fixture(relative_path)
}

/// Build the Markdown IR document for already-read fixture source.
fn ir_document_for(source: &str, relative_path: &Path) -> Result<IrDocument, Message> {
    markdown_ir_document(source, source_identity(relative_path))
}

/// Read and parse a Markdown corpus fixture in one step.
fn document_for(relative_path: &Path) -> Result<IrDocument, FixtureError> {
    let source = fixture_source(relative_path)?;
    Ok(ir_document_for(&source, relative_path)?)
}

fn regions_of_kind(document: &IrDocument, kind: RegionKind) -> Vec<&IrRegion> {
    document
        .regions
        .iter()
        .filter(|region| region.kind == kind.as_str())
        .collect()
}

fn first_segment_source_span(region: &IrRegion) -> Option<SourceSpan> {
    region.segments.first().and_then(|segment| segment.source)
}

fn is_thin_structural_region(region: &IrRegion) -> bool {
    region.text.is_empty() && region.segments.is_empty() && region.owner.is_none()
}

fn is_decoded_synthetic_region(region: &IrRegion) -> bool {
    region.attrs.get("source_backed") == Some(&serde_json::json!(false))
        && region.segments.len() == 1
        && region.segments.iter().all(|segment| {
            segment.source.is_none()
                && segment.synthetic.as_deref() == Some(SyntheticReason::DecodedText.as_str())
        })
}

fn has_paragraph_child_linked_to(
    document: &IrDocument,
    parents: &[&IrRegion],
    scope_name: &str,
) -> bool {
    document.regions.iter().any(|region| {
        region.kind == RegionKind::Paragraph.as_str()
            && region.scope.iter().any(|scope| scope == scope_name)
            && region
                .parent_region
                .as_deref()
                .is_some_and(|parent| parents.iter().any(|candidate| candidate.id == parent))
    })
}
