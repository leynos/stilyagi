//! Document envelope and producer/metadata types for the IR.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::{
    IrError, IrNode, IrRegion, IrSuppression, IrTree, SCHEMA_VERSION, SourceIdentity,
    content_hash_for, line_index_for,
};

/// A complete IR document envelope for one source payload.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IrDocument {
    /// Semantic version of the IR schema.
    pub schema_version: String,
    /// Metadata about the source document.
    pub document: DocumentMetadata,
    /// Parsers and extractors that produced this payload.
    pub producers: Vec<ProducerMetadata>,
    /// UTF-8 byte offsets for each line start plus the document end.
    pub line_index: Vec<usize>,
    /// Structural trees represented in this document.
    pub trees: Vec<IrTree>,
    /// Shared node store for all trees.
    pub nodes: Vec<IrNode>,
    /// Extracted lintable prose regions.
    pub regions: Vec<IrRegion>,
    /// Source-level suppression directives discovered during extraction.
    pub suppressions: Vec<IrSuppression>,
    /// Non-fatal parse or extraction anomalies.
    pub errors: Vec<IrError>,
    /// Extensible deterministic metadata map.
    pub metadata: BTreeMap<String, serde_json::Value>,
}

impl IrDocument {
    /// Create an empty IR document envelope for a source payload.
    #[must_use]
    pub fn empty(
        document: DocumentMetadata,
        producers: Vec<ProducerMetadata>,
        source: &str,
    ) -> Self {
        Self {
            schema_version: SCHEMA_VERSION.to_owned(),
            document,
            producers,
            line_index: line_index_for(source),
            trees: Vec::new(),
            nodes: Vec::new(),
            regions: Vec::new(),
            suppressions: Vec::new(),
            errors: Vec::new(),
            metadata: BTreeMap::new(),
        }
    }

    /// Serialize this document as deterministic pretty JSON.
    ///
    /// # Errors
    ///
    /// Returns a serialization error if metadata contains a JSON value that
    /// cannot be emitted by `serde_json`.
    pub fn to_canonical_json(&self) -> Result<String, serde_json::Error> {
        let mut json = serde_json::to_string_pretty(self)?;
        json.push('\n');
        Ok(json)
    }
}

/// Metadata about the source document represented by an IR payload.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DocumentMetadata {
    /// Stable source URI when the caller provides one.
    pub uri: Option<String>,
    /// Repository-relative or display path when the caller provides one.
    pub path: Option<String>,
    /// Source syntax name, such as `markdown`.
    pub syntax: String,
    /// Optional dominant natural language, such as `en`.
    pub natural_language: Option<String>,
    /// Source encoding, currently `utf-8`.
    pub encoding: String,
    /// Stable content hash, prefixed with the hash algorithm.
    pub content_hash: String,
}

impl DocumentMetadata {
    /// Create document metadata for the supplied syntax and source text.
    #[must_use]
    pub fn new(
        syntax: impl Into<String>,
        path: Option<String>,
        uri: Option<String>,
        source: &str,
    ) -> Self {
        Self {
            uri,
            path,
            syntax: syntax.into(),
            natural_language: None,
            encoding: "utf-8".to_owned(),
            content_hash: content_hash_for(source),
        }
    }

    /// Create Markdown document metadata for the supplied source text.
    #[must_use]
    pub fn markdown(identity: SourceIdentity, source: &str) -> Self {
        Self::new("markdown", identity.path, identity.uri, source)
    }
}

/// Metadata about a parser or extractor that produced IR data.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProducerMetadata {
    /// Producer role or syntax family.
    pub kind: String,
    /// Human-readable producer name.
    pub name: String,
    /// Producer version.
    pub version: String,
    /// Relevant deterministic parse or extraction options.
    pub options: BTreeMap<String, serde_json::Value>,
}

/// Document metadata and producer list used to build an IR envelope.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct IrBuildContext {
    /// Metadata for the source document represented by this envelope.
    pub document: DocumentMetadata,
    /// Producers that contribute to this envelope.
    pub producers: Vec<ProducerMetadata>,
}

impl IrBuildContext {
    /// Create an IR build context from document and producer metadata.
    #[must_use]
    pub const fn new(document: DocumentMetadata, producers: Vec<ProducerMetadata>) -> Self {
        Self {
            document,
            producers,
        }
    }
}
