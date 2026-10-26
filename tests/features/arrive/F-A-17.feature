# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-A-17, column "Executable scenarios (Gherkin)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-A-17 The top bar and the person menu, the same on every page

  Scenario: The top bar carries the logo, a Home link, a new-matter button and the conversation history
    Given the page
    Then the top bar has the NM logo and Nyaymalaw, a Home link to the website, a New matter button and a Conversation history button
    And it names the signed-in advocate beside the person menu button

  Scenario: There are no top tabs
    Given the page
    And the page script
    Then no Home, My work, Legal library or Preparation tab is shown after a sign-in

  Scenario: The person menu holds the profile and the account's settings
    Given the page
    And the page script
    Then the person menu shows the name, email, active workspace, enrolment and practice, and professional approval
    And the person menu has Usage and plan, Signed-in devices, AI data sharing, Dictation and Sign out
    And the menu opens from its button and closes on Escape, on a click elsewhere, and when the session ends

  Scenario: The name shown is the account's own, and leaves with the session
    Given the page script
    Then the name shown is the account's own name, or its email when it has none
    And ending the session clears the name, the workspace and every profile detail

  Scenario: On a phone the top bar stays on one row
    Given the page stylesheet
    Then at 820 px wide or narrower the top bar hides the wordmark, shows Home as its house alone and keeps its buttons on one row
