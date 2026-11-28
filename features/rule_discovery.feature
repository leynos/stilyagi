# markdownlint-disable MD041

Feature: Discover builtin rules without reading source

  Scenario: The catalogue includes an opt-in rule
    Given a directory with malformed Stilyagi configuration
    When the maintainer runs "stilyagi rules --output-format json"
    Then the command succeeds without reading configuration
    And the ordered codes are "DOC001,DOC002,DOC003,MD001,STY001,TERM001"
    And TERM001 is described as disabled by default

  Scenario: Inspect a configured policy variant
    Given the builtin TERM001 rule
    When the maintainer runs "stilyagi rule TERM001"
    Then both case_sensitive boolean variants are explained
    And the enablement example selects TERM001 and supplies terms
    And the documented example produces its expected finding

  Scenario: Manual guidance is not an editable fix
    Given the builtin rule catalogue
    When the maintainer runs "stilyagi rules --fixable yes"
    Then only STY001 is listed
    And its fix mode is unsafe

  Scenario: An unknown code is an actionable error
    Given the builtin rule catalogue
    When the maintainer runs "stilyagi rule UNKNOWN --output-format json"
    Then the exit status is 2
    And standard output is empty
    And standard error identifies the unknown code