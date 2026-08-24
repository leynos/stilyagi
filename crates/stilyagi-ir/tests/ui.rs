//! Compile-fail guard for the `sha2` 0.11 digest-formatting break.

#[test]
fn sha2_0_11_digest_lowerhex_formatting_is_rejected() {
    let cases = trybuild::TestCases::new();
    cases.compile_fail("tests/ui/sha2_digest_lower_hex.rs");
}
