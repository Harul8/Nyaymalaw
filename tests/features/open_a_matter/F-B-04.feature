# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-B-04, column "Executable scenarios (Gherkin)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-B-04 The matter's own tools sit in its header

  Scenario: The matter's own tools sit in its header
    Given the page
    And the page script
    Then the open matter's header holds only the file icon
    And the file icon lists every file held on the matter, including audio, video and voice notes
    And the matter's own records open from the same icon
