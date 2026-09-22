# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-A-18, column "Executable scenarios (Gherkin)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-A-18 A clean home page with a short introduction and Start a matter

  Scenario: The home page is two lines and one button
    Given the page
    Then the home page says "Nyaymalaw is a legal research and matter workspace for advocates practising Telangana and Union of India law."
    And the home page says "Every answer shows the Act, section or judgment it rests on."
    And the home page has one button, "Start a matter", and nothing else

  Scenario: Start a matter starts a new matter under Home
    Given the page script
    Then the Start a matter button starts a new matter under Home

  Scenario: A sign-in lands on Home unless a brief was interrupted
    Given the page script
    Then a sign-in shows the Home page
    And a sign-in after a session ended part-way through a brief goes back to that brief in My work
