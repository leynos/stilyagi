//! Bridge region kinds and extracted-region values.

use core::fmt;

/// Stable kind names for extracted prose regions.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[non_exhaustive]
pub enum RegionKind {
    /// Whole-document prose extracted from a source file.
    Document,
    /// Python docstring prose extracted from source code.
    PythonDocstring,
    /// Rust doc-comment prose extracted from source code.
    RustDocComment,
}

impl RegionKind {
    /// All bridge region kinds, in canonical order.
    pub const ALL: &'static [Self] = &[Self::Document, Self::PythonDocstring, Self::RustDocComment];

    /// Return the canonical IR kind for bridge regions that share IR
    /// vocabulary.
    ///
    /// `Document` is a coarse bridge-only region and deliberately has no
    /// `stilyagi_ir` equivalent.
    ///
    /// # Examples
    ///
    /// ```
    /// use stilyagi_extract::RegionKind;
    ///
    /// assert_eq!(
    ///     RegionKind::PythonDocstring.ir_region_kind(),
    ///     Some(stilyagi_ir::RegionKind::PythonDocstring),
    /// );
    /// assert_eq!(RegionKind::Document.ir_region_kind(), None);
    /// ```
    #[must_use]
    pub const fn ir_region_kind(self) -> Option<stilyagi_ir::RegionKind> {
        match self {
            Self::Document => None,
            Self::PythonDocstring => Some(stilyagi_ir::RegionKind::PythonDocstring),
            Self::RustDocComment => Some(stilyagi_ir::RegionKind::RustDocComment),
        }
    }

    /// Return the stable bridge spelling for this region kind.
    ///
    /// # Examples
    ///
    /// ```
    /// use stilyagi_extract::RegionKind;
    ///
    /// assert_eq!(RegionKind::PythonDocstring.as_str(), "python_docstring");
    /// assert_eq!(RegionKind::Document.as_str(), "document");
    /// ```
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self.ir_region_kind() {
            Some(kind) => kind.as_str(),
            None => "document",
        }
    }
}

impl fmt::Display for RegionKind {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

impl TryFrom<&str> for RegionKind {
    type Error = String;

    fn try_from(value: &str) -> Result<Self, Self::Error> {
        if value == "document" {
            Ok(Self::Document)
        } else {
            Self::from_shared_ir_kind(value)
        }
    }
}

impl RegionKind {
    /// Converts shared Python and Rust prose spellings into bridge kinds.
    ///
    /// For example, `"python_docstring"` returns `Ok(Self::PythonDocstring)`,
    /// while the unrelated IR spelling `"heading"` returns
    /// `Err("heading".to_owned())`.
    fn from_shared_ir_kind(value: &str) -> Result<Self, String> {
        let ir_kind = stilyagi_ir::RegionKind::try_from(value).map_err(|_| value.to_owned())?;

        match ir_kind {
            stilyagi_ir::RegionKind::PythonDocstring => Ok(Self::PythonDocstring),
            stilyagi_ir::RegionKind::RustDocComment => Ok(Self::RustDocComment),
            _ => Err(value.to_owned()),
        }
    }
}

/// Minimal source-backed prose region for the first extraction bridge.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExtractRegion {
    kind: String,
    text: String,
}

impl ExtractRegion {
    /// Create a region with the supplied stable kind name and text.
    ///
    /// # Examples
    ///
    /// ```
    /// use stilyagi_extract::ExtractRegion;
    ///
    /// let region = ExtractRegion::new("custom", "Extracted prose.");
    ///
    /// assert_eq!(region.kind(), "custom");
    /// assert_eq!(region.text(), "Extracted prose.");
    /// ```
    #[must_use]
    pub fn new(kind: impl Into<String>, text: impl Into<String>) -> Self {
        Self {
            kind: kind.into(),
            text: text.into(),
        }
    }

    /// Create a region from the typed region kind and supplied text.
    ///
    /// # Examples
    ///
    /// ```
    /// use stilyagi_extract::{ExtractRegion, RegionKind};
    ///
    /// let region = ExtractRegion::new_typed(RegionKind::PythonDocstring, "Extracted prose.");
    ///
    /// assert_eq!(region.kind(), "python_docstring");
    /// ```
    #[must_use]
    pub fn new_typed(kind: RegionKind, text: impl Into<String>) -> Self {
        Self::new(kind.as_str(), text)
    }

    /// Return the stable region kind name.
    ///
    /// # Examples
    ///
    /// ```
    /// use stilyagi_extract::{ExtractRegion, RegionKind};
    ///
    /// let region = ExtractRegion::new_typed(RegionKind::RustDocComment, "Extracted prose.");
    ///
    /// assert_eq!(region.kind(), "rust_doc_comment");
    /// ```
    #[must_use]
    pub fn kind(&self) -> &str {
        &self.kind
    }

    /// Return the typed region kind when it is in the built-in vocabulary.
    ///
    /// # Examples
    ///
    /// ```
    /// use stilyagi_extract::{ExtractRegion, RegionKind};
    ///
    /// let built_in = ExtractRegion::new_typed(RegionKind::PythonDocstring, "Extracted prose.");
    /// let custom = ExtractRegion::new("custom", "Extracted prose.");
    ///
    /// assert_eq!(built_in.region_kind(), Some(RegionKind::PythonDocstring));
    /// assert_eq!(custom.region_kind(), None);
    /// ```
    #[must_use]
    pub fn region_kind(&self) -> Option<RegionKind> {
        RegionKind::try_from(self.kind()).ok()
    }

    /// Return the extracted region text.
    ///
    /// # Examples
    ///
    /// ```
    /// use stilyagi_extract::ExtractRegion;
    ///
    /// let region = ExtractRegion::new("custom", "Extracted prose.");
    ///
    /// assert_eq!(region.text(), "Extracted prose.");
    /// ```
    #[must_use]
    pub fn text(&self) -> &str {
        &self.text
    }
}
