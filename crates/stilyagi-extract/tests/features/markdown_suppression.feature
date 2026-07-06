# Markdown suppression directives surface in the IR

Feature: Markdown suppression directives surface in the IR

  Scenario: A canonical ignore-next directive becomes a suppression
    Given a Markdown document with a "stilyagi: ignore-next PUN201" comment
    When the document is extracted
    Then the IR suppressions contain one inline entry naming PUN201
    And the suppression span re-slices to the directive comment

  Scenario: An inline directive within a paragraph becomes a suppression
    Given a paragraph contains an inline "stilyagi: ignore-next PUN201" comment
    When the document is extracted
    Then the IR suppressions contain one inline entry naming PUN201
    And the suppression span re-slices to the directive comment

  Scenario: A blanket directive is refused
    Given a Markdown document with a "stilyagi: disable" comment naming no code
    When the document is extracted
    Then the IR suppressions are empty
    And the IR errors contain a blanket-forbidden entry

  Scenario: A range disable and enable pair record open and close polarity
    Given a Markdown document with a "stilyagi: disable STY"/"enable STY" pair
    When the document is extracted
    Then the first IR suppression records the disable as a range open
    And the second IR suppression records the enable as a range close

  Scenario: A same-line coalesced directive node becomes two suppressions
    Given a Markdown document with two same-line suppression comments
    When the document is extracted
    Then the IR suppressions contain two range entries naming STY
    And the suppression spans re-slice to the coalesced comments

  Scenario: A mixed same-line suppression and blanket comment
    Given a Markdown document with a same-line suppression and a blanket comment
    When the document is extracted
    Then the IR suppressions contain one range entry naming STY
    And the suppression span re-slices to the first coalesced comment
    And the IR errors contain a blanket-forbidden entry for the second comment
    And the blanket error span re-slices to the second coalesced comment
