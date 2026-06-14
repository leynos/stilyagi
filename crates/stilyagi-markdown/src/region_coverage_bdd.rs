//! BDD coverage for promised Markdown IR region kinds.

use std::collections::BTreeSet;
use std::ffi::OsStr;
use std::path::Path;

use rstest::fixture;
use rstest_bdd_macros::{given, scenario, then, when};
use stilyagi_ir::{RegionKind, SourceIdentity};
use stilyagi_test_support::{fixture_paths_in, read_corpus_fixture};

use crate::markdown_ir_document;

struct RegionCoverageState {
    expected_kinds: BTreeSet<&'static str>,
    emitted_kinds: BTreeSet<String>,
}

#[fixture]
fn region_coverage_state() -> RegionCoverageState {
    RegionCoverageState {
        expected_kinds: BTreeSet::new(),
        emitted_kinds: BTreeSet::new(),
    }
}

#[given("the promised v1 Markdown region kind vocabulary")]
fn promised_v1_markdown_region_kind_vocabulary(region_coverage_state: &mut RegionCoverageState) {
    region_coverage_state.expected_kinds = promised_markdown_region_kinds();
}

#[when("the valid Markdown fixture corpus is extracted")]
fn valid_markdown_fixture_corpus_is_extracted(region_coverage_state: &mut RegionCoverageState) {
    region_coverage_state.emitted_kinds = valid_markdown_fixture_paths()
        .into_iter()
        .flat_map(|relative_path| {
            let source = must_read_fixture(&relative_path);
            let identity = SourceIdentity::new(
                Some(relative_path.clone()),
                Some(format!("file:///{relative_path}")),
            );
            let document = match markdown_ir_document(&source, identity) {
                Ok(document) => document,
                Err(error) => panic!("expected Markdown IR document: {error}"),
            };

            document
                .regions
                .into_iter()
                .map(|region| region.kind)
                .collect::<Vec<_>>()
        })
        .collect();
}

#[then("each promised v1 Markdown region kind is emitted at least once")]
fn each_promised_v1_markdown_region_kind_is_emitted(region_coverage_state: &RegionCoverageState) {
    for expected_kind in &region_coverage_state.expected_kinds {
        assert!(
            region_coverage_state.emitted_kinds.contains(*expected_kind),
            "valid Markdown corpus did not emit promised region kind {expected_kind}"
        );
    }
}

#[scenario(
    path = "tests/features/region_coverage.feature",
    name = "Valid Markdown corpus covers promised v1 region kinds"
)]
fn valid_markdown_corpus_covers_promised_v1_region_kinds(
    region_coverage_state: RegionCoverageState,
) {
    let _ = region_coverage_state;
}

fn promised_markdown_region_kinds() -> BTreeSet<&'static str> {
    [
        RegionKind::Heading.as_str(),
        RegionKind::Paragraph.as_str(),
        RegionKind::ListItem.as_str(),
        RegionKind::Blockquote.as_str(),
        RegionKind::TableCell.as_str(),
        RegionKind::Frontmatter.as_str(),
        RegionKind::ImageAlt.as_str(),
        RegionKind::LinkTitle.as_str(),
    ]
    .into_iter()
    .collect()
}

fn valid_markdown_fixture_paths() -> Vec<String> {
    let mut paths = must_list_fixture_paths("tests/fixtures/corpus/markdown/valid")
        .into_iter()
        .filter(|path| is_markdown_fixture(Path::new(path)))
        .collect::<Vec<_>>();
    paths.sort();
    paths
}

fn must_read_fixture(relative_path: &str) -> String {
    match read_corpus_fixture(relative_path) {
        Ok(source) => source,
        Err(error) => panic!("expected readable Markdown fixture: {error}"),
    }
}

fn must_list_fixture_paths(relative_dir: &str) -> Vec<String> {
    match fixture_paths_in(relative_dir) {
        Ok(paths) => paths,
        Err(error) => panic!("expected readable Markdown fixture directory: {error}"),
    }
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
