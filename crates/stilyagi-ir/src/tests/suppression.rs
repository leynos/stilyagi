//! Tests for suppression serde contracts.

use std::collections::BTreeSet;

use proptest::prelude::*;
use rstest::rstest;

use super::assert_json_round_trip;
use crate::suppression::{
    DirectiveError, DirectiveOutcome, DirectiveVerb, SuppressionCandidate,
    SuppressionValidationError, parse_comment_directive, suppressions_from_candidates,
    validate_suppressions, verb_kind,
};
use crate::{IrSuppression, RangeRole, SourceSpan, SuppressionKind};

#[rstest]
fn suppression_serialises_and_deserialises_with_the_rfc_shape() {
    let suppression = IrSuppression {
        id: "s0".to_owned(),
        kind: SuppressionKind::Inline,
        range_role: None,
        codes: vec!["PUN201".to_owned()],
        span: SourceSpan::new(3, 18).expect("expected valid span"),
        origin: "n7".to_owned(),
    };

    assert_json_round_trip(
        &suppression,
        &serde_json::json!({
            "id": "s0",
            "kind": "inline",
            "codes": ["PUN201"],
            "span": {
                "byte_start": 3,
                "byte_end": 18,
            },
            "origin": "n7",
        }),
    );
}

#[rstest]
fn suppressions_from_candidates_assembles_directives_and_ignores_non_directives() {
    let candidates = [
        SuppressionCandidate {
            origin: "n0".to_owned(),
            span: SourceSpan::new(0, 37).expect("expected valid span"),
            body: "stilyagi: ignore-next PUN201".to_owned(),
        },
        SuppressionCandidate {
            origin: "n1".to_owned(),
            span: SourceSpan::new(38, 66).expect("expected valid span"),
            body: "<!-- comment -->".to_owned(),
        },
        SuppressionCandidate {
            origin: "n2".to_owned(),
            span: SourceSpan::new(67, 95).expect("expected valid span"),
            body: "stilyagi: ignore-file".to_owned(),
        },
        SuppressionCandidate {
            origin: "n3".to_owned(),
            span: SourceSpan::new(96, 124).expect("expected valid span"),
            body: "stilyagi: disable".to_owned(),
        },
    ];

    let (suppressions, errors) = suppressions_from_candidates(candidates);

    assert_eq!(suppressions.len(), 2);
    assert_eq!(
        suppressions
            .first()
            .expect("expected first assembled suppression")
            .origin,
        "n0"
    );
    assert_eq!(
        suppressions
            .first()
            .expect("expected first assembled suppression")
            .codes,
        vec!["PUN201"]
    );
    assert_eq!(
        suppressions
            .get(1)
            .expect("expected second assembled suppression")
            .origin,
        "n2"
    );
    assert_eq!(
        suppressions
            .get(1)
            .expect("expected second assembled suppression")
            .codes,
        Vec::<String>::new(),
    );
    assert_eq!(errors.len(), 1);
    assert_eq!(
        errors
            .first()
            .expect("expected blanket suppression error")
            .code,
        "suppression-blanket-forbidden"
    );
    assert_eq!(
        errors
            .first()
            .expect("expected blanket suppression error")
            .span,
        Some(SourceSpan::new(96, 124).expect("expected valid span"))
    );
}

#[rstest]
fn suppressions_from_candidates_preserves_authored_error_order() {
    let candidates = [
        SuppressionCandidate {
            origin: "n0".to_owned(),
            span: SourceSpan::new(0, 17).expect("expected valid span"),
            body: "stilyagi: disable".to_owned(),
        },
        SuppressionCandidate {
            origin: "n1".to_owned(),
            span: SourceSpan::new(18, 48).expect("expected valid span"),
            body: "stilyagi: invalid-verb RUST210".to_owned(),
        },
    ];

    let (suppressions, errors) = suppressions_from_candidates(candidates);

    assert_eq!(suppressions, Vec::<IrSuppression>::new());
    assert_eq!(errors.len(), 2);
    assert_eq!(
        errors
            .iter()
            .map(|error| error.code.as_str())
            .collect::<Vec<_>>(),
        ["suppression-blanket-forbidden", "suppression-unknown-verb"]
    );
    assert_eq!(
        errors.iter().map(|error| error.span).collect::<Vec<_>>(),
        [
            Some(SourceSpan::new(0, 17).expect("expected valid span")),
            Some(SourceSpan::new(18, 48).expect("expected valid span")),
        ]
    );
}

#[rstest]
fn validate_suppressions_accepts_known_origins_and_in_bounds_spans() {
    let suppressions = vec![IrSuppression {
        id: "s0".to_owned(),
        kind: SuppressionKind::Inline,
        range_role: None,
        codes: vec!["PUN201".to_owned()],
        span: SourceSpan::new(0, 37).expect("expected valid span"),
        origin: "n0".to_owned(),
    }];
    let node_ids = BTreeSet::from(["n0"]);

    assert_eq!(
        validate_suppressions(
            &suppressions,
            "<!-- stilyagi: ignore-next PUN201 -->",
            &node_ids,
        ),
        Ok(())
    );
}

#[rstest]
fn validate_suppressions_rejects_unresolved_origin_nodes() {
    let suppressions = vec![IrSuppression {
        id: "s0".to_owned(),
        kind: SuppressionKind::Inline,
        range_role: None,
        codes: vec!["PUN201".to_owned()],
        span: SourceSpan::new(0, 37).expect("expected valid span"),
        origin: "n9".to_owned(),
    }];
    let node_ids = BTreeSet::from(["n0"]);

    let Err(error) = validate_suppressions(
        &suppressions,
        "<!-- stilyagi: ignore-next PUN201 -->",
        &node_ids,
    ) else {
        panic!("expected unresolved origin to fail validation");
    };

    assert_eq!(
        error,
        SuppressionValidationError::OriginUnresolved {
            suppression_id: "s0".to_owned(),
            origin: "n9".to_owned(),
        }
    );
}

#[rstest]
fn validate_suppressions_rejects_out_of_bounds_spans() {
    let suppressions = vec![IrSuppression {
        id: "s0".to_owned(),
        kind: SuppressionKind::Inline,
        range_role: None,
        codes: vec!["PUN201".to_owned()],
        span: SourceSpan::new(0, 99).expect("expected valid span"),
        origin: "n0".to_owned(),
    }];
    let node_ids = BTreeSet::from(["n0"]);

    let Err(error) = validate_suppressions(
        &suppressions,
        "<!-- stilyagi: ignore-next PUN201 -->",
        &node_ids,
    ) else {
        panic!("expected invalid span to fail validation");
    };

    assert_eq!(
        error,
        SuppressionValidationError::SpanInvalid {
            suppression_id: "s0".to_owned(),
            origin: "n0".to_owned(),
            span: SourceSpan::new(0, 99).expect("expected valid span"),
        }
    );
}

#[rstest]
#[case(
    "stilyagi: ignore-next PUN201",
    DirectiveVerb::IgnoreNext,
    &["PUN201"],
    SuppressionKind::Inline,
)]
#[case("stilyagi: disable STY", DirectiveVerb::Disable, &["STY"], SuppressionKind::Range)]
#[case("stilyagi: enable STY", DirectiveVerb::Enable, &["STY"], SuppressionKind::Range)]
#[case(
    "stilyagi: ignore-file MD,DOC",
    DirectiveVerb::IgnoreFile,
    &["MD", "DOC"],
    SuppressionKind::File,
)]
fn parse_comment_directive_parses_canonical_verbs(
    #[case] inner: &str,
    #[case] expected_verb: DirectiveVerb,
    #[case] expected_codes: &[&str],
    #[case] expected_kind: SuppressionKind,
) {
    let DirectiveOutcome::Parsed(parsed) = parse_comment_directive(inner) else {
        panic!("expected parsed directive for {inner:?}");
    };

    assert_eq!(parsed.verb, expected_verb);
    assert_eq!(
        parsed.codes,
        expected_codes
            .iter()
            .map(|code| (*code).to_owned())
            .collect::<Vec<_>>()
    );
    assert_eq!(verb_kind(parsed.verb), expected_kind);
}

#[rstest]
#[case("stilyagi: ignore-next")]
#[case("stilyagi: disable")]
#[case("stilyagi: enable")]
fn parse_comment_directive_rejects_blanket_inline_and_range_directives(#[case] inner: &str) {
    let DirectiveOutcome::Rejected(error) = parse_comment_directive(inner) else {
        panic!("expected blanket rejection for {inner:?}");
    };

    assert_eq!(error, DirectiveError::BlanketForbidden);
}

#[rstest]
#[case("stilyagi: ignore-file")]
#[case("stilyagi-disable-next-line terminology")]
#[case("<!-- comment -->")]
fn parse_comment_directive_accepts_file_blankets_or_ignores_non_directives(#[case] inner: &str) {
    match parse_comment_directive(inner) {
        DirectiveOutcome::Parsed(parsed) => {
            assert_eq!(parsed.verb, DirectiveVerb::IgnoreFile);
            assert_eq!(parsed.codes, Vec::<String>::new());
        }
        DirectiveOutcome::NotADirective => {}
        DirectiveOutcome::Rejected(error) => {
            panic!("unexpected directive outcome: {error:?}")
        }
    }
}

/// Return the canonical suppression kind for a directive token, or `None` when
/// the token is not a known directive verb.
fn expected_kind_from_token(token: &str) -> Option<SuppressionKind> {
    match token {
        "ignore-next" => Some(SuppressionKind::Inline),
        "disable" | "enable" => Some(SuppressionKind::Range),
        "ignore-file" => Some(SuppressionKind::File),
        _ => None,
    }
}

fn directive_codes_and_padding() -> impl Strategy<Value = (Vec<String>, Vec<String>)> {
    prop::collection::vec(code_token_strategy(), 1..5).prop_flat_map(|codes| {
        let padding_len = codes.len().saturating_sub(1);
        (
            Just(codes),
            prop::collection::vec(space_padding_strategy(), padding_len),
        )
    })
}

fn code_token_strategy() -> impl Strategy<Value = String> {
    (
        b'A'..=b'Z',
        prop::collection::vec(prop_oneof![b'A'..=b'Z', b'0'..=b'9'], 0..8),
    )
        .prop_map(|(first, rest)| std::iter::once(first).chain(rest).map(char::from).collect())
}

/// Generate optional leading or trailing whitespace around a directive.
fn whitespace_strategy() -> impl Strategy<Value = String> {
    prop::collection::vec(prop::sample::select(vec![' ', '\t']), 0..4)
        .prop_map(|characters| characters.into_iter().collect())
}

/// Generate optional padding after commas in a directive code list.
fn space_padding_strategy() -> impl Strategy<Value = String> {
    prop::collection::vec(prop::sample::select(vec![' ', '\t']), 0..3)
        .prop_map(|characters| characters.into_iter().collect())
}

#[rstest]
#[case(RangeRole::Open, "open")]
#[case(RangeRole::Close, "close")]
fn range_suppression_serialises_with_its_role(
    #[case] range_role: RangeRole,
    #[case] expected_role: &str,
) {
    let suppression = IrSuppression {
        id: "s1".to_owned(),
        kind: SuppressionKind::Range,
        range_role: Some(range_role),
        codes: vec!["PUN201".to_owned()],
        span: SourceSpan::new(3, 18).expect("expected valid span"),
        origin: "n7".to_owned(),
    };

    assert_json_round_trip(
        &suppression,
        &serde_json::json!({
            "id": "s1",
            "kind": "range",
            "range_role": expected_role,
            "codes": ["PUN201"],
            "span": {
                "byte_start": 3,
                "byte_end": 18,
            },
            "origin": "n7",
        }),
    );
}

#[path = "suppression_proptest.rs"]
mod suppression_proptest;
