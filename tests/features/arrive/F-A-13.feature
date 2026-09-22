# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-A-13, column "Executable scenarios (Gherkin)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-A-13 The sign-in page works on desktop, tablet and phone

  Scenario: On a phone or portrait tablet the logo sits above the card
    Given the sign-in page
    And the page stylesheet
    Then at 820 px wide or narrower the sign-in page is one column
    And the left panel keeps only its logo and the logo is not hidden
    And the logo appears exactly once

  Scenario: On a landscape tablet the two columns narrow before the card does
    Given the page stylesheet
    Then between 821 and 1024 px wide the left panel and the gap beside it are narrower

  Scenario: A card taller than the screen can be scrolled to its top
    Given the page stylesheet
    Then the sign-in page centres its cards with auto margins, not by aligning to the middle of a scrolling area

  Scenario: No card needs sideways scrolling on a 360 px phone
    Given the page stylesheet
    Then the cards are at most 420 px wide and shrink with the screen
