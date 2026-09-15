# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-A-10, column "Scenarios (Given / When / Then)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-A-10 Show or hide the password on the sign-in card

  Scenario: The sign-in card has a show-password button that never sends the form
    Given the sign-in page
    Then the sign-in password field has an eye button beside it, labelled "Show password"
    And every eye button on the page is a plain button that cannot send its form

  Scenario: The password is put away whenever it could be left showing
    Given the page script
    Then a sign-in that succeeds and one that is refused both clear and mask the password
    And leaving the sign-in card clears and masks the password
    And every card puts its passwords away the same way
