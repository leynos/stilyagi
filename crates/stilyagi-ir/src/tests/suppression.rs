//! Tests for suppression serde contracts.

use rstest::rstest;

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

    let json = serde_json::to_value(&suppression).expect("expected suppression JSON");
    let expected = serde_json::json!({
        "id": "s0",
        "kind": "inline",
        "codes": ["PUN201"],
        "span": {
            "byte_start": 3,
            "byte_end": 18,
        },
        "origin": "n7",
    });

    assert_eq!(json, expected);
    assert_eq!(
        serde_json::from_value::<IrSuppression>(json).expect("expected suppression round trip"),
        suppression
    );
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

    let json = serde_json::to_value(&suppression).expect("expected suppression JSON");
    let expected = serde_json::json!({
        "id": "s1",
        "kind": "range",
        "range_role": expected_role,
        "codes": ["PUN201"],
        "span": {
            "byte_start": 3,
            "byte_end": 18,
        },
        "origin": "n7",
    });

    assert_eq!(json, expected);
    assert_eq!(
        serde_json::from_value::<IrSuppression>(json).expect("expected suppression round trip"),
        suppression
    );
}
