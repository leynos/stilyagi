/// Outer module documentation comment for nested Rust extraction.
pub mod outer {
    //! Inner module documentation comment for the outer module.

    pub mod inner {
        /// Documented struct in a nested module.
        pub struct FixtureExample;

        pub trait FixtureTrait {
            type Alias;

            const VALUE: &'static str;

            fn documented_value(&self) -> &'static str;
        }

        impl FixtureTrait for FixtureExample {
            /// Documented associated const in a trait impl.
            const VALUE: &'static str = "value";

            /// Documented associated type in a trait impl.
            type Alias = &'static str;

            /// Documented method in a trait impl.
            fn documented_value(&self) -> &'static str {
                "documented"
            }
        }
    }
}
