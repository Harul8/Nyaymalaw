# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-C-03, column "Executable scenarios (Gherkin)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-C-03 Live words while the advocate speaks

  Scenario: Live words are off unless the advocate turns them on
    Given the page script
    Then dictation opens the live words socket only when the advocate's dictation setting is live
    And the dictation setting offers GPT Transcribe by default and GPT Live Transcribe

  Scenario: The words appear in the brief box as they are spoken
    Given the page
    And the page script
    Then the live words come from a socket and are written into the brief box as they arrive
    And the live words stop being written the moment the advocate edits them
    And the final live words replace the words they stood in for, or the recording is transcribed if they do not finish

  Scenario: The microphone reaches the live model as it wants it, and not the speakers
    Given the page script
    Then the audio is sent as 24 kHz mono frames of about a tenth of a second
    And the page does not play the advocate's own voice back

  Scenario: The live socket authenticates itself
    When a stranger opens the live dictation socket
    Then the socket is refused before any audio is read
    And a socket opened from another page is refused the same way

  Scenario: The live words arrive while the advocate is still speaking
    Given an advocate who turned live words on
    And the live dictation model
    When the page sends two frames of speech and then stops
    Then the words heard so far come back as they are heard
    And the final words come back when it stops
    And no audio is stored anywhere

  Scenario: An advocate who has not turned live words on is told so and the recording goes on
    When an advocate with live words off opens the live dictation socket
    Then the socket says the live words are off and the recording goes on
