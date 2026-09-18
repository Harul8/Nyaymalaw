# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-C-02, column "Scenarios (Given / When / Then)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-C-02 Dictate the brief with the mic, transcribed on this installation

  Scenario: The mic sits beside the plus and puts what was said into the brief for checking
    Given the page
    And the page script
    Then beside the plus button there is a mic button that starts recording and stops on a second press
    And the words come back into the brief box to be checked, and nothing is sent by itself

  Scenario: Speech is turned into text on this installation and the recording is not kept
    Given the dictation service
    When an advocate sends a short recording to be transcribed
    Then the words come back and the recording is not stored anywhere
    And it went through the recorded local speech processor

  Scenario: Dictation that is not set up says so
    When the local speech model is not installed and an advocate dictates
    Then dictation is refused, saying the local speech model is not installed

  Scenario: The words come back in English
    Then dictation asks the speech model for English unless the installation sets another language
