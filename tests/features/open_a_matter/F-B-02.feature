# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-B-02, column "Executable scenarios (Gherkin)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-B-02 The live matter board beside the conversation

  Scenario: The matter board is beside the conversation, not a tab
    Given the page
    And the page script
    Then the matter board comes before the conversation in the window and there are no Board, Documents or Research notes tabs

  Scenario: The board is read from the conversation's saved understanding and again after every answer
    Given the page script
    Then the board is read from the server for this conversation when it opens and after every answer
    And while NM works on a message the board says what NM is doing
    And a Board that cannot be read says so rather than showing an empty one

  Scenario: Each dispute shows what it needs, and a dispute or an item opens in the reading pane
    Given the page script
    Then each dispute shows its last days, how much is in hand and its items under Needed and Would strengthen with their marks
    And choosing a dispute or an item opens its details in the reading pane on the right

  Scenario: The files and research notes open from the Files button beside the board's title
    Given the page
    And the page script
    Then the Files button beside the board's title lists the files and the research notes in the reading pane
    And a document opens in the reading pane on the right

  Scenario: On a phone the board is behind a Matter board button
    Given the page
    And the page stylesheet
    Then at 820 px wide or narrower a Matter board button opens the board
