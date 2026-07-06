//! Tests for range suppression polarity in Markdown IR wiring.

use std::path::Path;

use rstest::rstest;
use stilyagi_ir::{
    RangeRole,
    suppression::{DirectiveVerb, verb_range_role},
};

use super::source_identity;
use crate::markdown_ir_document;

#[rstest]
#[case(DirectiveVerb::IgnoreNext, None)]
#[case(DirectiveVerb::Disable, Some(RangeRole::Open))]
#[case(DirectiveVerb::Enable, Some(RangeRole::Close))]
#[case(DirectiveVerb::IgnoreFile, None)]
fn verb_range_role_maps_range_verbs_to_polarity(
    #[case] verb: DirectiveVerb,
    #[case] expected_role: Option<RangeRole>,
) {
    assert_eq!(verb_range_role(verb), expected_role);
}

#[rstest]
fn range_directives_record_open_and_close_polarity() {
    let source = concat!(
        "# Suppression Fixture\n\n",
        "<!-- stilyagi: ignore-next PUN201 -->\n",
        "Apples, bananas and pears.\n\n",
        "<!-- stilyagi: disable STY -->\n",
        "A questionable section.\n",
        "<!-- stilyagi: enable STY -->\n\n",
        "<!-- stilyagi: ignore-file MD,DOC -->\n",
    );
    let document = markdown_ir_document(source, source_identity(Path::new("docs/example.md")))
        .expect("expected Markdown IR document");
    let suppressions = document.suppressions.as_slice();

    assert_eq!(suppressions.len(), 4);
    assert_eq!(
        suppressions
            .first()
            .expect("expected inline suppression")
            .range_role,
        None
    );
    assert_eq!(
        suppressions
            .get(1)
            .expect("expected range-opening suppression")
            .range_role,
        Some(RangeRole::Open)
    );
    assert_eq!(
        suppressions
            .get(2)
            .expect("expected range-closing suppression")
            .range_role,
        Some(RangeRole::Close)
    );
    assert_eq!(
        suppressions
            .get(3)
            .expect("expected file suppression")
            .range_role,
        None
    );
}

#[rstest]
fn range_directives_snapshot_their_polarity_json() {
    let source = concat!(
        "Before the pair.\n",
        "<!-- stilyagi: disable STY -->\n",
        "Between the pair.\n",
        "<!-- stilyagi: enable STY -->\n",
    );
    let document = markdown_ir_document(source, source_identity(Path::new("docs/example.md")))
        .expect("expected Markdown IR document");
    let json =
        serde_json::to_string_pretty(&document.suppressions).expect("expected suppression JSON");

    insta::assert_snapshot!(
        json,
        @r###"
[
  {
    "id": "s0",
    "kind": "range",
    "range_role": "open",
    "codes": [
      "STY"
    ],
    "span": {
      "byte_start": 17,
      "byte_end": 47
    },
    "origin": "n3"
  },
  {
    "id": "s1",
    "kind": "range",
    "range_role": "close",
    "codes": [
      "STY"
    ],
    "span": {
      "byte_start": 66,
      "byte_end": 95
    },
    "origin": "n6"
  }
]
"###
    );
}
