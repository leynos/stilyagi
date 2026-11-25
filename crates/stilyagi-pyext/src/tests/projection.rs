//! Property coverage for the bridge payload projection.
//!
//! [`dictionary_json`] decides what every payload snapshot sees, so its
//! type-preservation contract is checked over generated payloads rather than
//! only over the literals the named tests happen to use. A projection that
//! flattened a boolean or an integer into a string would still render a
//! plausible snapshot for the literals; over generated values it fails at the
//! first case whose round trip changes type or value.

use proptest::prelude::*;
use pyo3::{
    exceptions::PyValueError,
    prelude::{Bound, PyResult, Python},
    types::{PyDict, PyDictMethods, PyFloat, PyList, PyListMethods},
};
use rstest::rstest;
use serde_json::Value;

use super::{dictionary_json, rendered_value};

/// Return a generated payload value.
///
/// Leaves cover the three primitive types the bridge carries: strings,
/// booleans, and `i64` integers. The recursive case wraps objects in arrays,
/// matching a region list, whose members may themselves hold any generated
/// value.
fn arbitrary_value() -> BoxedStrategy<Value> {
    let leaf = prop_oneof![
        "[a-z]{0,8}".prop_map(Value::String),
        any::<bool>().prop_map(Value::Bool),
        any::<i64>().prop_map(Value::from),
    ];
    leaf.prop_recursive(2, 12, 3, |nested| {
        proptest::collection::vec(
            proptest::collection::hash_map("[a-z]{1,4}", nested, 0..3).prop_map(object_of),
            0..3,
        )
        .prop_map(Value::Array)
    })
    .boxed()
}

/// Return a generated document-shaped payload: an object of generated values.
fn arbitrary_payload() -> BoxedStrategy<Value> {
    proptest::collection::hash_map("[a-z]{1,4}", arbitrary_value(), 0..4)
        .prop_map(object_of)
        .boxed()
}

/// Build a JSON object from generated members.
fn object_of(members: std::collections::HashMap<String, Value>) -> Value {
    Value::Object(members.into_iter().collect())
}

/// Insert one generated value into a Python dictionary under `key`.
fn insert_value(
    py: Python<'_>,
    dictionary: &Bound<'_, PyDict>,
    key: &str,
    value: &Value,
) -> PyResult<()> {
    match value {
        Value::String(text) => dictionary.set_item(key, text.as_str()),
        Value::Bool(flag) => dictionary.set_item(key, *flag),
        Value::Number(number) => {
            let count = number.as_i64().ok_or_else(|| {
                PyValueError::new_err("the strategy generates integer counts as i64")
            })?;
            dictionary.set_item(key, count)
        }
        Value::Array(items) => {
            let list = PyList::empty(py);
            for item in items {
                let nested = PyDict::new(py);
                insert_object(py, &nested, item)?;
                list.append(nested)?;
            }
            dictionary.set_item(key, list)
        }
        _ => Err(PyValueError::new_err(
            "the strategy generates only supported payload values",
        )),
    }
}

/// Insert a generated object's members into a Python dictionary.
fn insert_object(py: Python<'_>, dictionary: &Bound<'_, PyDict>, value: &Value) -> PyResult<()> {
    let Value::Object(members) = value else {
        return Err(PyValueError::new_err(
            "the strategy generates nested objects only as list members",
        ));
    };
    for (key, member) in members {
        insert_value(py, dictionary, key, member)?;
    }
    Ok(())
}

proptest! {
    /// Every generated payload must project back to exactly the same JSON.
    ///
    /// Equality covers type preservation as well as value: a boolean rendered
    /// as `1`, an integer rendered as `"7"`, or a list rendered as its `repr`
    /// would all differ from the generated value.
    #[test]
    fn dictionary_json_round_trips_generated_payloads(payload in arbitrary_payload()) {
        let projected = Python::attach(|py| -> PyResult<Value> {
            let dictionary = PyDict::new(py);
            insert_object(py, &dictionary, &payload)?;
            Ok(dictionary_json(&dictionary))
        })
        .expect("a payload built from supported types must project");

        prop_assert_eq!(
            projected,
            payload,
            "the projection must keep every JSON type and value"
        );
    }
}

/// A payload value the projection cannot represent must fail loudly.
///
/// Floats are valid Python and valid JSON, but the bridge never carries them,
/// so a projection that stringified one would hide a bridge change instead of
/// failing. `None` would take the same path.
#[rstest]
#[should_panic(expected = "payload value type is not supported by the projection")]
fn rendered_value_rejects_unsupported_types() {
    Python::attach(|py| {
        let unsupported = PyFloat::new(py, 1.5);
        let _rendered = rendered_value(unsupported.as_any());
    });
}
