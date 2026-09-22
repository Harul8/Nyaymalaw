# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-B-02, column "Executable scenarios (Gherkin)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-B-02 The matter board beside the chat

  Scenario: The matter board is on the left and the chat on the right
    Given the page
    And the page stylesheet
    Then in an open matter the board is the left pane and the chat the right

  Scenario: The board shows this matter only, from the record My work lists
    Given the page script
    Then the board is filled from My work's row for this matter, with the same fields as the list
    And the board is read again after every message
    And a board that cannot be read says so rather than showing an empty one

  Scenario: The issues in the matter are on the board
    Given the page
    And the page script
    Then the issues recorded on the matter are listed on the board under its details
