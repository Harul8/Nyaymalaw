# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-B-01, column "Scenarios (Given / When / Then)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-B-01 Start a new matter from Home

  Scenario: Start a matter opens the intake form alone, under Home
    Given the page script
    And the page stylesheet
    Then Start a matter opens the intake form alone, with Home still the marked tab

  Scenario: Record and continue saves the matter before the chat opens
    Given the page script
    Then recording the intake saves the matter on the server with the form's parties before the chat opens
    And if the matter cannot be opened the form keeps its answers and says so

  Scenario: The server names a new matter from its parties and lists it at once
    When an advocate opens a matter for "Ramesh Traders" against "Kiran Steels" without a title
    Then the matter is saved as "Ramesh Traders v Kiran Steels" with both parties recorded
    And it is in My work's list straight away
