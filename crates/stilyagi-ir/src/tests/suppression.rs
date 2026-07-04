//! Tests for suppression serde contracts.

use rstest::rstest;

use crate::{IrSuppression, SourceSpan, SuppressionKind};

#[rstest]
fn suppression_serialises_and_deserialises_with_the_rfc_shape() {
    let suppression = IrSuppression {
        id: "s0".to_owned(),
        kind: SuppressionKind::Inline,
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
