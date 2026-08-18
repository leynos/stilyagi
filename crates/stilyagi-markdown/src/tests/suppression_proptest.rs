//! Proptest coverage for Markdown suppression directive parsing.

use proptest::prelude::*;

use super::super::suppression_support::{
    directive_codes_and_padding, expected_kind_from_token, whitespace_strategy,
};
use stilyagi_ir::suppression::{
    DirectiveError, DirectiveOutcome, DirectiveVerb, parse_comment_directive, verb_kind,
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

        let Some(expected_kind) = expected_kind_from_token(verb) else {
            panic!("unexpected verb token {verb:?}");
        };

        prop_assert_eq!(parsed.codes, codes);
        prop_assert_eq!(verb_kind(parsed.verb), expected_kind);
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
}
