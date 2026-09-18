# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-B-03, column "Scenarios (Given / When / Then)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-B-03 My work lists the matters, and opening one resumes it

  Scenario: My work is only the list of matters
    Given the page
    And the page script
    And the page stylesheet
    Then My work has no new-matter button and no welcome page
    And choosing the My work tab always shows the list of matters

  Scenario: Opening a matter from My work resumes it
    Given the page script
    Then opening a matter shows its board and restores its conversation, with My work still the marked tab
