//! Unit tests for IR domain invariants and canonical document helpers.

use std::collections::BTreeMap;

use proptest::prelude::*;
use rstest::rstest;

use super::{
    DocumentMetadata, IrBoundary, IrDocument, RegionKind, SourceIdentity, SyntheticReason,
    content_hash_for, line_index_for,
};

mod segment_properties;
mod suppression;

/// Keep the marker type default stable and comparable.
#[test]
#[expect(
    clippy::default_constructed_unit_structs,
    reason = "this test explicitly exercises the Default implementation"
)]
fn ir_boundary_default_matches_the_marker_value() {
    assert_eq!(IrBoundary::default(), IrBoundary);
}

/// Keep the marker type clone semantics trivial.
#[test]
fn ir_boundary_clone_matches_the_original() {
    let boundary = IrBoundary;

    assert_eq!(boundary.clone(), boundary);
}

/// Keep the marker type debug output identifiable in failures.
#[test]
fn ir_boundary_debug_output_mentions_the_type_name() {
    assert!(format!("{IrBoundary:?}").contains("IrBoundary"));
}

/// Keep the marker type copy semantics available to callers.
#[test]
fn ir_boundary_is_copy() {
    let original = IrBoundary;
    let first = original;
    let second = original;

    assert_eq!(first, second);
    assert_eq!(first, original);
}

#[rstest]
fn region_kind_vocabulary_matches_rfc_0001() {
    let expected = [
        "heading",
        "paragraph",
        "list_item",
        "blockquote",
        "table_cell",
        "frontmatter",
        "frontmatter_field",
        "image_alt",
        "link_title",
        "python_docstring",
        "rust_doc_comment",
    ];

    let actual = RegionKind::ALL
        .iter()
        .map(|kind| kind.as_str())
        .collect::<Vec<_>>();

    assert_eq!(actual, expected);
}

#[rstest]
#[case::heading(RegionKind::Heading)]
#[case::paragraph(RegionKind::Paragraph)]
#[case::list_item(RegionKind::ListItem)]
#[case::blockquote(RegionKind::Blockquote)]
#[case::table_cell(RegionKind::TableCell)]
#[case::frontmatter(RegionKind::Frontmatter)]
#[case::frontmatter_field(RegionKind::FrontmatterField)]
#[case::image_alt(RegionKind::ImageAlt)]
#[case::link_title(RegionKind::LinkTitle)]
#[case::python_docstring(RegionKind::PythonDocstring)]
#[case::rust_doc_comment(RegionKind::RustDocComment)]
fn region_kind_round_trips_through_stable_spelling(#[case] kind: RegionKind) {
    assert_eq!(RegionKind::try_from(kind.as_str()), Ok(kind));
}

#[rstest]
fn unknown_region_kind_preserves_rejected_value() {
    let Err(error) = RegionKind::try_from("unknown") else {
        panic!("unknown region kind should be rejected");
    };

    assert_eq!(error.value(), "unknown");
}

#[rstest]
fn synthetic_reason_vocabulary_matches_segment_contract() {
    let expected = ["softbreak_space", "hardbreak_space", "decoded_text"];
    let actual = SyntheticReason::ALL
        .iter()
        .map(|reason| reason.as_str())
        .collect::<Vec<_>>();

    assert_eq!(actual, expected);
}

#[rstest]
fn empty_document_uses_line_index_and_content_hash() {
    let source = "# Title\nBody";
    let document = IrDocument::empty(
        DocumentMetadata::markdown(
            SourceIdentity::new(
                Some("docs/example.md".to_owned()),
                Some("file:///repo/docs/example.md".to_owned()),
            ),
            source,
        ),
        Vec::new(),
        source,
    );

    assert_eq!(document.schema_version, "1.1.0");
    assert_eq!(document.line_index, vec![0, 8, 12]);
    assert!(document.document.content_hash.starts_with("sha256:"));
}

#[rstest]
fn empty_document_preserves_metadata_content_hash() {
    let document = IrDocument::empty(
        DocumentMetadata {
            uri: Some("file:///repo/docs/example.md".to_owned()),
            path: Some("docs/example.md".to_owned()),
            syntax: "markdown".to_owned(),
            natural_language: None,
            encoding: "utf-8".to_owned(),
            content_hash: "sha256:not-the-source".to_owned(),
        },
        Vec::new(),
        "# Title\nBody",
    );

    assert_eq!(document.document.content_hash, "sha256:not-the-source",);
}

#[rstest]
fn markdown_metadata_does_not_set_a_natural_language_policy() {
    let metadata = DocumentMetadata::markdown(SourceIdentity::anonymous(), "");

    assert!(metadata.natural_language.is_none());
}

#[rstest]
fn markdown_metadata_accepts_anonymous_source_identity() {
    let metadata = DocumentMetadata::markdown(SourceIdentity::anonymous(), "");

    assert_eq!(metadata.path, None);
    assert_eq!(metadata.uri, None);
}

#[rstest]
#[case("markdown")]
#[case("python-docstring")]
#[case("rust-doc-comment")]
fn syntax_neutral_metadata_builds_empty_ir_documents(#[case] syntax: &str) {
    let source = "First line\nsecond line";
    let document = IrDocument::empty(
        DocumentMetadata::new(
            syntax,
            Some(format!("fixtures/{syntax}.txt")),
            Some(format!("file:///repo/fixtures/{syntax}.txt")),
            source,
        ),
        Vec::new(),
        source,
    );

    assert_eq!(document.document.syntax, syntax);
    assert!(document.document.content_hash.starts_with("sha256:"));
    assert_eq!(document.line_index, vec![0, 11, 22]);
    assert!(document.document.natural_language.is_none());
}

#[rstest]
fn anonymous_source_identity_serializes_as_null_metadata_fields() {
    let document = IrDocument::empty(
        DocumentMetadata::markdown(SourceIdentity::anonymous(), ""),
        Vec::new(),
        "",
    );
    let json = document
        .to_canonical_json()
        .expect("expected canonical JSON");
    let parsed = serde_json::from_str::<serde_json::Value>(&json)
        .expect("expected parseable canonical JSON");
    let metadata = parsed
        .get("document")
        .and_then(serde_json::Value::as_object)
        .expect("expected document metadata object");

    assert_eq!(metadata.get("path"), Some(&serde_json::Value::Null));
    assert_eq!(metadata.get("uri"), Some(&serde_json::Value::Null));
}

proptest! {
    #[test]
    fn line_index_offsets_follow_source_line_boundaries(source in any::<String>()) {
        let offsets = line_index_for(&source);

        prop_assert_eq!(offsets.first().copied(), Some(0));
        prop_assert_eq!(offsets.last().copied(), Some(source.len()));
        prop_assert!(
            offsets
                .windows(2)
                .all(|window| matches!(window, [left, right] if left < right))
        );
        prop_assert!(offsets.iter().all(|offset| source.is_char_boundary(*offset)));
        prop_assert!(offsets.iter().copied().skip(1).take(offsets.len().saturating_sub(2)).all(
            |offset| source.as_bytes().get(offset - 1) == Some(&b'\n'),
        ));
    }

    #[test]
    fn content_hash_is_deterministic_and_well_formed(source in any::<String>()) {
        let hash = content_hash_for(&source);

        prop_assert_eq!(&hash, &content_hash_for(&source));
        prop_assert!(hash.starts_with("sha256:"));
        let suffix = hash.trim_start_matches("sha256:");
        prop_assert_eq!(suffix.len(), 64);
        let is_lowercase_hex = suffix.chars().all(|character| {
            character.is_ascii_digit() || ('a'..='f').contains(&character)
        });
        prop_assert!(is_lowercase_hex);
    }
}

#[rstest]
#[case("", "not empty")]
#[case("markdown", "Markdown")]
#[case("# Title\nBody", "# Title\nOther")]
fn content_hash_distinguishes_fixed_source_examples(#[case] left: &str, #[case] right: &str) {
    assert_ne!(content_hash_for(left), content_hash_for(right));
}

#[rstest]
fn canonical_json_orders_metadata_deterministically() {
    let mut metadata = BTreeMap::new();
    metadata.insert("zeta".to_owned(), serde_json::json!(true));
    metadata.insert("alpha".to_owned(), serde_json::json!(1));
    let mut document = IrDocument::empty(
        DocumentMetadata::markdown(SourceIdentity::anonymous(), ""),
        Vec::new(),
        "",
    );
    document.metadata = metadata;

    let json = document.to_canonical_json();

    assert!(matches!(
        json,
        Ok(ref value) if value.contains("\"alpha\"") && value.contains("\"zeta\"")
    ));
    if let Ok(value) = json {
        let alpha_position = value.find("\"alpha\"");
        let zeta_position = value.find("\"zeta\"");
        assert!(matches!(
            (alpha_position, zeta_position),
            (Some(alpha), Some(zeta)) if alpha < zeta
        ));
    }
}
