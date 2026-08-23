//! Shared canonical IR helpers for byte-oriented source metadata.

use sha2::{Digest, Sha256};

/// Return the byte offsets for each line start plus the end-of-document offset.
#[must_use]
pub fn line_index_for(source: &str) -> Vec<usize> {
    let mut offsets = vec![0];
    for (offset, byte) in source.bytes().enumerate() {
        if byte == b'\n' {
            offsets.push(offset + 1);
        }
    }
    if offsets.last().copied() != Some(source.len()) {
        offsets.push(source.len());
    }
    offsets
}

/// Return the stable SHA-256 content hash spelling used in IR documents.
///
/// The digest suffix is rendered explicitly rather than with the `{:x}`
/// format specifier, because `sha2` 0.11 returns `hybrid_array::Array<u8, _>`
/// from `digest`, which does not implement `LowerHex`. The rendering stays
/// lowercase and zero-padded so existing IR hashes remain valid.
#[must_use]
pub fn content_hash_for(source: &str) -> String {
    format!(
        "sha256:{}",
        to_lower_hex(&Sha256::digest(source.as_bytes()))
    )
}

/// Encode `bytes` as a lowercase hexadecimal string.
///
/// Every byte renders as exactly two digits, including leading zeroes, so the
/// output is always twice the input length.
#[must_use]
fn to_lower_hex(bytes: &[u8]) -> String {
    let mut hex = String::with_capacity(bytes.len() * 2);
    let byte_iter = bytes.iter();
    for byte in byte_iter {
        hex.push(digit_for_nibble(*byte >> 4));
        hex.push(digit_for_nibble(*byte & 0x0f));
    }
    hex
}

/// Map a `0..=15` nibble to its lowercase hexadecimal ASCII digit.
#[must_use]
fn digit_for_nibble(nibble: u8) -> char {
    debug_assert!(nibble <= 0x0f);

    char::from(if nibble < 10 {
        b'0' + nibble
    } else {
        b'a' + nibble - 10
    })
}

#[cfg(test)]
mod tests {
    //! Tests for canonical byte metadata and JSON helper behaviour.

    use proptest::prelude::*;

    use super::{content_hash_for, line_index_for, to_lower_hex};

    #[test]
    fn line_index_for_reports_byte_offsets_and_document_end() {
        assert_eq!(line_index_for("é\nx"), vec![0, 3, 4]);
    }

    #[test]
    fn content_hash_for_uses_documented_sha256_prefix() {
        assert_eq!(
            content_hash_for(""),
            "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
    }

    #[test]
    fn to_lower_hex_renders_fixed_patterns_with_two_digits_per_byte() {
        assert_eq!(to_lower_hex(&[0x00, 0x0f, 0xff, 0xa0]), "000fffa0");
    }

    #[test]
    fn to_lower_hex_renders_an_empty_input_as_an_empty_string() {
        assert_eq!(to_lower_hex(&[]), "");
    }

    #[test]
    fn every_u8_value_renders_as_two_lowercase_round_tripping_digits() {
        for byte in u8::MIN..=u8::MAX {
            let rendered = to_lower_hex(&[byte]);
            assert_eq!(rendered.len(), 2, "byte {byte:#04x} must render two digits");
            assert!(
                rendered
                    .bytes()
                    .all(|character| character.is_ascii_digit()
                        || (b'a'..=b'f').contains(&character)),
                "byte {byte:#04x} rendered non-lowercase-hex output {rendered:?}",
            );
            let parsed = u8::from_str_radix(&rendered, 16).expect("two hex digits parse as a byte");
            assert_eq!(parsed, byte, "round-trip mismatch for byte {byte:#04x}");
        }
    }

    proptest! {
        #[test]
        fn every_byte_renders_as_two_lowercase_round_tripping_digits(byte in any::<u8>()) {
            let rendered = to_lower_hex(&[byte]);
            prop_assert_eq!(rendered.len(), 2, "byte {:#04x} must render two digits", byte);
            prop_assert!(
                rendered
                    .bytes()
                    .all(|character| character.is_ascii_digit()
                        || (b'a'..=b'f').contains(&character)),
                "byte {byte:#04x} rendered non-lowercase-hex output {rendered:?}",
            );
            let parsed = u8::from_str_radix(&rendered, 16).expect("two hex digits parse as a byte");
            prop_assert_eq!(parsed, byte, "round-trip mismatch for byte {:#04x}", byte);
        }
    }
}
