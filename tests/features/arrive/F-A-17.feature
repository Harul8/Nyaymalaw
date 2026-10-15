# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-A-17, column "Executable scenarios (Gherkin)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-A-17 The sidebar and the person menu, the same on every page

  Scenario: The sidebar carries the logo, a new-matter button and the list of matters
    Given the page
    Then the sidebar has the NM logo and Nyaymalaw, a New matter button and the list of matters
    And it names the signed-in advocate beside the person menu button

  Scenario: There are no top tabs
    Given the page
    And the page script
    Then no Home, My work, Legal library or Preparation tab is shown after a sign-in

  Scenario: The person menu holds the profile and the account's settings
    Given the page
    And the page script
    Then the person menu shows the name, email, active workspace, enrolment and practice, and professional approval
    And the person menu has Signed-in devices, AI data sharing, Dictation and Sign out
    And the menu opens from its button and closes on Escape, on a click elsewhere, and when the session ends

  Scenario: The name shown is the account's own, and leaves with the session
    Given the page script
    Then the name shown is the account's own name, or its email when it has none
    And ending the session clears the name, the workspace and every profile detail

  Scenario: On a phone a Matters button opens the list
    Given the page
    And the page stylesheet
    Then at 820 px wide or narrower a Matters button opens the list of matters
