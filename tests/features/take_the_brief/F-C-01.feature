# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-C-01, column "Executable scenarios (Gherkin)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-C-01 Add documents, media or a voice note from the plus button

  Scenario: A plus button under the brief offers documents, media and a voice note to keep
    Given the page
    And the page script
    Then under the brief a plus button opens Upload documents, Upload photos, audio or video, and Record a voice note to keep
    And each opens the original-material window, which keeps what it receives sealed and unread
    And there is no files bar above the chat
