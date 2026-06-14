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
#[must_use]
pub fn content_hash_for(source: &str) -> String {
    let digest = Sha256::digest(source.as_bytes());
    format!("sha256:{digest:x}")
}

#[cfg(test)]
mod tests {
    //! Tests for canonical byte metadata and JSON helper behaviour.

    use super::{content_hash_for, line_index_for};

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
}
