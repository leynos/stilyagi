//! Owner metadata derivation for Python docstring regions.

use stilyagi_ir::IrOwner;

use super::types::NodeId;

const LOCAL_MARKER: &str = "<locals>";

/// Type of code entity that can own a Python docstring.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(super) enum OwnerKind {
    Class,
    Function,
}

impl OwnerKind {
    /// Return the stable IR spelling for this owner kind.
    pub(super) const fn as_str(self) -> &'static str {
        match self {
            Self::Class => "class",
            Self::Function => "function",
        }
    }
}

/// Traversal state for one Python definition that may own docstrings.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(super) struct OwnerFrame {
    /// Code entity kind represented by this stack frame.
    pub(super) kind: OwnerKind,
    /// Source-level definition name.
    pub(super) name: String,
    /// IR node id emitted for this definition, filled lazily during traversal.
    pub(super) emitted_node_id: Option<NodeId>,
}

impl OwnerFrame {
    /// Create a stack frame whose IR node has not been emitted yet.
    pub(super) const fn new(kind: OwnerKind, name: String) -> Self {
        Self {
            kind,
            name,
            emitted_node_id: None,
        }
    }
}

/// Derive IR owner metadata from the current owner stack.
///
/// An empty stack represents the module owner. Otherwise the innermost frame
/// supplies the owner kind and name, while the full stack supplies the Python
/// qualified name.
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
        name: Some(current.name.clone()),
        qualname: qualname_for(stack),
    }
}

/// Build a Python qualified name from owner frames.
///
/// Empty stacks have no qualified name. Function frames followed by another
/// frame receive Python's `<locals>` marker so nested definitions use the same
/// shape as `__qualname__`, such as `outer.<locals>.inner`.
pub(super) fn qualname_for(stack: &[OwnerFrame]) -> Option<String> {
    let mut parts = Vec::new();
    let mut frames = stack.iter().peekable();
    while let Some(frame) = frames.next() {
        parts.push(frame.name.clone());
        if matches!(frame.kind, OwnerKind::Function) && frames.peek().is_some() {
            // Python uses this marker for definitions nested inside functions,
            // for example `outer.<locals>.inner`.
            parts.push(LOCAL_MARKER.to_owned());
        }
    }
    (!parts.is_empty()).then(|| parts.join("."))
}

#[cfg(test)]
mod tests {
    use proptest::prelude::*;
    use rstest::rstest;

    use super::{LOCAL_MARKER, OwnerFrame, OwnerKind, owner_for, qualname_for};

    fn frame(kind: OwnerKind, name: &str) -> OwnerFrame {
        OwnerFrame::new(kind, name.to_owned())
    }

    fn expected_parts(stack: &[OwnerFrame]) -> Vec<String> {
        let mut parts = Vec::new();
        let mut frames = stack.iter().peekable();
        while let Some(frame) = frames.next() {
            parts.push(frame.name.clone());
            if matches!(frame.kind, OwnerKind::Function) && frames.peek().is_some() {
                parts.push(LOCAL_MARKER.to_owned());
            }
        }
        parts
    }

    fn is_generated_identifier(value: &str) -> bool {
        let mut chars = value.chars();
        let Some(first) = chars.next() else {
            return false;
        };
        (first == '_' || first.is_ascii_alphabetic())
            && chars.all(|char| char == '_' || char.is_ascii_alphanumeric())
    }

    #[rstest]
    #[case::module(Vec::new(), "module", None, None)]
    #[case::class(
        vec![frame(OwnerKind::Class, "Example")],
        "class",
        Some("Example"),
        Some("Example")
    )]
    #[case::method(
        vec![
            frame(OwnerKind::Class, "Example"),
            frame(OwnerKind::Function, "method")
        ],
        "function",
        Some("method"),
        Some("Example.method")
    )]
    #[case::function_local_class(
        vec![
            frame(OwnerKind::Function, "outer"),
            frame(OwnerKind::Class, "Inner")
        ],
        "class",
        Some("Inner"),
        Some("outer.<locals>.Inner")
    )]
    fn owner_metadata_matches_python_qualname_semantics(
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
                (prop_oneof![Just(OwnerKind::Class), Just(OwnerKind::Function)], "[A-Z_a-z][A-Z_a-z0-9]{0,8}"),
                0..8,
            )
        ) -> Vec<OwnerFrame> {
            frames
                .into_iter()
                .map(|(kind, name)| OwnerFrame::new(kind, name))
                .collect()
        }
    }

    proptest! {
        #[test]
        fn qualname_is_deterministic(stack in owner_stack()) {
            prop_assert_eq!(qualname_for(&stack), qualname_for(&stack));
        }

        #[test]
        fn qualname_preserves_frame_names_in_order(stack in owner_stack()) {
            let Some(qualname) = qualname_for(&stack) else {
                prop_assert!(stack.is_empty());
                return Ok(());
            };
            let frame_names = qualname
                .split('.')
                .filter(|part| *part != LOCAL_MARKER)
                .collect::<Vec<_>>();
            let expected_names = stack
                .iter()
                .map(|frame| frame.name.as_str())
                .collect::<Vec<_>>();

            prop_assert_eq!(frame_names, expected_names);
        }

        #[test]
        fn qualname_places_locals_markers_after_function_frames(stack in owner_stack()) {
            let Some(qualname) = qualname_for(&stack) else {
                prop_assert!(stack.is_empty());
                return Ok(());
            };
            let parts = qualname.split('.').collect::<Vec<_>>();
            let expected_parts = expected_parts(&stack);
            let expected = expected_parts
                .iter()
                .map(String::as_str)
                .collect::<Vec<_>>();

            prop_assert_eq!(&parts, &expected);
            for (index, part) in parts.iter().enumerate() {
                if *part == LOCAL_MARKER {
                    prop_assert!(index > 0);
                    prop_assert!(index + 1 < parts.len());
                }
            }
        }

        #[test]
        fn qualname_uses_valid_dotted_name_parts(stack in owner_stack()) {
            let Some(qualname) = qualname_for(&stack) else {
                prop_assert!(stack.is_empty());
                return Ok(());
            };

            prop_assert!(!qualname.starts_with('.'));
            prop_assert!(!qualname.ends_with('.'));
            prop_assert!(!qualname.contains(".."));
            for part in qualname.split('.') {
                prop_assert!(part == LOCAL_MARKER || is_generated_identifier(part));
            }
        }
    }
}
