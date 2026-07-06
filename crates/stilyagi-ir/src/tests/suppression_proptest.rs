//! Property tests for suppression parsing and marker detection.

use proptest::prelude::*;

use super::{directive_codes_and_padding, expected_kind_from_token, whitespace_strategy};
use crate::suppression::{
    DirectiveError, DirectiveOutcome, DirectiveVerb, is_directive_marker, parse_comment_directive,
    verb_kind,
};

proptest! {
    #[test]
    fn parse_comment_directive_preserves_trimmed_codes(
        verb in prop_oneof![
            Just("ignore-next"),
            Just("disable"),
            Just("enable"),
            Just("ignore-file"),
        ],
        codes_and_padding in directive_codes_and_padding(),
        leading_ws in whitespace_strategy(),
        trailing_ws in whitespace_strategy(),
    ) {
        let (codes, padding) = codes_and_padding;
        let mut body = format!("{leading_ws}stilyagi: {verb}");
        if let Some(first_code) = codes.first() {
            body.push(' ');
            body.push_str(first_code);
            for (code, pad) in codes.iter().skip(1).zip(padding.iter()) {
                body.push(',');
                body.push_str(pad);
                body.push_str(code);
            }
        }
        body.push_str(&trailing_ws);

        let DirectiveOutcome::Parsed(parsed) = parse_comment_directive(&body) else {
            panic!("expected parsed directive for {body:?}");
        };

        prop_assert_eq!(parsed.codes, codes);
        prop_assert_eq!(verb_kind(parsed.verb), expected_kind_from_token(verb));
    }

    #[test]
    fn ignore_next_disable_and_enable_require_codes(
        verb in prop_oneof![Just("ignore-next"), Just("disable"), Just("enable")],
        leading_ws in whitespace_strategy(),
        trailing_ws in whitespace_strategy(),
    ) {
        let body = format!("{leading_ws}stilyagi: {verb}{trailing_ws}");
        let DirectiveOutcome::Rejected(error) = parse_comment_directive(&body) else {
            panic!("expected blanket rejection for {body:?}");
        };

        prop_assert_eq!(error, DirectiveError::BlanketForbidden);
    }

    #[test]
    fn ignore_file_allows_empty_codes(
        leading_ws in whitespace_strategy(),
        trailing_ws in whitespace_strategy(),
    ) {
        let body = format!("{leading_ws}stilyagi: ignore-file{trailing_ws}");
        let DirectiveOutcome::Parsed(parsed) = parse_comment_directive(&body) else {
            panic!("expected parsed ignore-file directive for {body:?}");
        };

        prop_assert_eq!(parsed.verb, DirectiveVerb::IgnoreFile);
        prop_assert!(parsed.codes.is_empty());
    }

    #[test]
    fn is_directive_marker_matches_parser_acceptance(
        case in prop_oneof![
            Just("stilyagi: ignore-next PUN201".to_owned()),
            Just("  stilyagi: disable PUN201  ".to_owned()),
            Just("stilyagi: ignore-file".to_owned()),
            Just("stilyagi: unknown PUN201".to_owned()),
            Just("stilyagi: disable".to_owned()),
            Just("see stilyagi: docs".to_owned()),
            Just("stilyagi-disable-next-line terminology".to_owned()),
            Just("   ".to_owned()),
        ]
    ) {
        let marker = is_directive_marker(&case);
        let parser_accepts = !matches!(parse_comment_directive(&case), DirectiveOutcome::NotADirective);

        prop_assert_eq!(marker, parser_accepts, "case={:?}", case);
    }
}
