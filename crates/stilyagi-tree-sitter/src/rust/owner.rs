//! Owner metadata derivation for Rust doc-comment regions.

use stilyagi_ir::IrOwner;

use super::types::NodeId;

/// Type of code entity that can own a Rust documentation comment.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(super) enum OwnerKind {
    Module,
    Impl,
    Struct,
    Enum,
    Union,
    Trait,
    Function,
    Const,
    Static,
    Type,
    Macro,
    Item,
}

impl OwnerKind {
    /// Return the stable IR spelling for this owner kind.
    pub(super) const fn as_str(self) -> &'static str {
        match self {
            Self::Module => "module",
            Self::Impl => "impl",
            Self::Struct => "struct",
            Self::Enum => "enum",
            Self::Union => "union",
            Self::Trait => "trait",
            Self::Function => "function",
            Self::Const => "const",
            Self::Static => "static",
            Self::Type => "type",
            Self::Macro => "macro",
            Self::Item => "item",
        }
    }
}

/// Traversal state for one Rust item that may own doc comments.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(super) struct OwnerFrame {
    /// Code entity kind represented by this stack frame.
    pub(super) kind: OwnerKind,
    /// Source-level definition name or self type.
    pub(super) name: Option<String>,
    /// IR node id emitted for this definition, filled lazily during traversal.
    pub(super) emitted_node_id: Option<NodeId>,
}

impl OwnerFrame {
    /// Create a stack frame whose IR node has not been emitted yet.
    pub(super) const fn new(kind: OwnerKind, name: Option<String>) -> Self {
        Self {
            kind,
            name,
            emitted_node_id: None,
        }
    }
}

/// Derive IR owner metadata from the current owner stack.
pub(super) fn owner_for(stack: &[OwnerFrame]) -> IrOwner {
    let Some(current) = stack.last() else {
        return IrOwner {
            kind: "module".to_owned(),
            name: None,
            qualname: None,
        };
    };

    IrOwner {
        kind: current.kind.as_str().to_owned(),
        name: current.name.clone(),
        qualname: qualname_for(stack),
    }
}

/// Build a Rust qualified name from owner frames.
///
/// When the stack contains an `impl` frame, v1 uses the self type and any
/// nested item names from that frame onwards.
pub(super) fn qualname_for(stack: &[OwnerFrame]) -> Option<String> {
    let start_index = stack
        .iter()
        .rposition(|frame| matches!(frame.kind, OwnerKind::Impl))
        .unwrap_or(0);
    let parts = stack
        .get(start_index..)
        .unwrap_or(&[])
        .iter()
        .filter_map(|frame| frame.name.as_deref())
        .map(str::to_owned)
        .collect::<Vec<_>>();

    (!parts.is_empty()).then(|| parts.join("::"))
}

#[cfg(test)]
mod tests {
    //! Unit and property tests for Rust owner-frame qualified-name derivation.

    use proptest::prelude::*;
    use rstest::rstest;

    use super::{OwnerFrame, OwnerKind, owner_for, qualname_for};

    fn frame(kind: OwnerKind, name: Option<&str>) -> OwnerFrame {
        OwnerFrame::new(kind, name.map(str::to_owned))
    }

    #[rstest]
    #[case::module(Vec::new(), "module", None, None)]
    #[case::module_item(
        vec![frame(OwnerKind::Module, Some("outer"))],
        "module",
        Some("outer"),
        Some("outer")
    )]
    #[case::nested_module(
        vec![
            frame(OwnerKind::Module, Some("outer")),
            frame(OwnerKind::Module, Some("inner"))
        ],
        "module",
        Some("inner"),
        Some("outer::inner")
    )]
    #[case::struct_item(
        vec![frame(OwnerKind::Struct, Some("FixtureExample"))],
        "struct",
        Some("FixtureExample"),
        Some("FixtureExample")
    )]
    #[case::impl_block(
        vec![frame(OwnerKind::Impl, Some("FixtureExample"))],
        "impl",
        Some("FixtureExample"),
        Some("FixtureExample")
    )]
    #[case::impl_method(
        vec![
            frame(OwnerKind::Impl, Some("FixtureExample")),
            frame(OwnerKind::Function, Some("documented_value"))
        ],
        "function",
        Some("documented_value"),
        Some("FixtureExample::documented_value")
    )]
    fn owner_metadata_matches_rust_qualname_semantics(
        #[case] stack: Vec<OwnerFrame>,
        #[case] kind: &str,
        #[case] name: Option<&str>,
        #[case] qualname: Option<&str>,
    ) {
        let owner = owner_for(&stack);

        assert_eq!(owner.kind, kind);
        assert_eq!(owner.name.as_deref(), name);
        assert_eq!(owner.qualname.as_deref(), qualname);
    }

    prop_compose! {
        fn owner_stack()(
            frames in prop::collection::vec(
                prop_oneof![
                    Just(OwnerKind::Module),
                    Just(OwnerKind::Impl),
                    Just(OwnerKind::Struct),
                    Just(OwnerKind::Enum),
                    Just(OwnerKind::Union),
                    Just(OwnerKind::Trait),
                    Just(OwnerKind::Function),
                    Just(OwnerKind::Const),
                    Just(OwnerKind::Static),
                    Just(OwnerKind::Type),
                    Just(OwnerKind::Macro),
                    Just(OwnerKind::Item),
                ],
                0..8,
            ),
            names in prop::collection::vec("[A-Za-z_][A-Za-z0-9_]{0,8}", 0..8),
        ) -> Vec<OwnerFrame> {
            frames
                .into_iter()
                .enumerate()
                .map(|(index, kind)| OwnerFrame::new(kind, names.get(index).cloned()))
                .collect()
        }
    }

    proptest! {
        #[test]
        fn qualname_is_deterministic(stack in owner_stack()) {
            prop_assert_eq!(qualname_for(&stack), qualname_for(&stack));
        }

        #[test]
        fn qualname_contains_frame_names_in_order(stack in owner_stack()) {
            let start_index = stack
                .iter()
                .rposition(|frame| matches!(frame.kind, OwnerKind::Impl))
                .unwrap_or(0);
            let Some(qualname) = qualname_for(&stack) else {
                prop_assert!(stack
                    .get(start_index..)
                    .unwrap_or(&[])
                    .iter()
                    .all(|frame| frame.name.is_none()));
                return Ok(());
            };

            let expected = stack
                .iter()
                .skip(start_index)
                .filter_map(|frame| frame.name.as_deref())
                .collect::<Vec<_>>();
            let actual = qualname.split("::").collect::<Vec<_>>();

            prop_assert_eq!(actual, expected);
        }
    }
}
