# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-A-17, column "Executable scenarios (Gherkin)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-A-17 The top ribbon, the same on every page

  Scenario: The ribbon's first row carries the logo, the advocate and the workspace
    Given the page
    Then the ribbon's first row has the NM logo and Nyaymalaw on the left
    And on its right the advocate's name, the active workspace and a person menu button, in that order

  Scenario: The ribbon has exactly four tabs
    Given the page
    Then the ribbon's tabs are exactly Home, My work, Legal library and Preparation

  Scenario: The ribbon stays at the top of every page
    Given the page
    And the page script
    And the page stylesheet
    Then the ribbon is outside every page, and every page scrolls inside itself below it
    And moving between pages never hides the ribbon; only the sign-in gate does

  Scenario: The person menu holds the profile, signed-in devices and sign out
    Given the page
    And the page script
    Then the person menu shows the name, email, active workspace, enrolment and practice, and professional approval
    And the person menu has Signed-in devices and Sign out
    And the menu opens from its button and closes on Escape, on a click elsewhere, and when the session ends

  Scenario: Case file and History open from inside an open matter
    Given the page
    And the page script
    Then Case file and History are not tabs
    And an open matter offers Case file and History while it is open
    And they open on that matter, with the matter's own tab still marked

  Scenario: The Legal library page says whether the library can be read
    Given the page
    Then the library availability line is on the Legal library page and not in the ribbon

  Scenario: On a phone the ribbon keeps the logo and the person menu
    Given the page
    And the page stylesheet
    Then at 820 px wide or narrower the name and workspace move into the person menu
    And the tabs stay on one row that scrolls inside the ribbon
    And the Matters button is inside My work

  Scenario: The ribbon shows only the signed-in account
    Given the page script
    Then the name shown is the account's own name, or its email when it has none
    And ending the session clears the name, the workspace and every profile detail
