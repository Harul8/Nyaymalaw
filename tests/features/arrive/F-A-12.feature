# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-A-12, column "Executable scenarios (Gherkin)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-A-12 Sign out after 30 minutes without activity

  Scenario: A session left untouched for 30 minutes stops working
    Given an advocate who is signed in
    When nothing uses the session for 30 minutes
    Then the session is refused

  Scenario: Using the app starts the 30 minutes again
    Given an advocate who is signed in
    When they use the app every 29 minutes for two hours
    Then the session still works

  Scenario: However busy, a session ends 12 hours after signing in
    Given an advocate who is signed in
    When they use the app every 29 minutes until 12 hours after signing in
    Then the session is refused

  Scenario: The page signs out after 30 untouched minutes and keeps the draft
    Given the page script
    Then typing, pointing, touching, scrolling and coming back to the tab all count as activity
    And the 30 minutes come from the server and are not written in the page
    And activity in one open tab counts for every open tab
    And a warning appears 2 minutes before the sign-out
    And activity after the 30 minutes signs out instead of starting them again
    And the idle sign-out keeps the unsent draft and ends the session on the server
