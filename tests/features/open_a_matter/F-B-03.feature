# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-B-03, column "Executable scenarios (Gherkin)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-B-03 Conversation history, and the conversation window it opens

  Scenario: Conversation history lists every saved conversation and says when it cannot be read
    Given the page script
    Then the conversation history is read from the server and lists every saved conversation
    And a list that cannot be read says so rather than looking empty

  Scenario: Opening a conversation from the history shows the same window as a live one
    Given the page script
    Then choosing a conversation in the history restores it with its board beside it

  Scenario: Every link opens in one reading pane on the right
    Given the page
    And the page stylesheet
    Then the reading pane is part of the conversation window and opens beside the conversation without covering it
    And the reading pane closes on Close or Escape
