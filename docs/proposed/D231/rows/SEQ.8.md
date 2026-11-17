# SEQ.8 - Voice notes and transcription

Row 165 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

SEQ.8

## Item

Voice notes and transcription

## Description

Implement E7/S7 with original-audio custody, provider permission, timestamped source text, uncertain speaker labels, playback, correction lineage and partial processing. Route the transcript through the existing matter/extraction and response checks. Measure transcription fidelity separately from legal-response quality.

## Governs or depends on

SEQ.6; E7/S7; D13; P17

## Status

Voice notes and dictation built (item 8, 15 Oct 2026) with gpt-transcribe; notes in G161 (SEQ.4). Open (round of 15 Oct, G164): live words while dictating (owner: build with OpenAI), transcription spend in the development ledger. | REFRESHED 26 Oct 2026 (checked in the code): both items listed open on 15 Oct are built - live words while dictating (the dictation socket in nm/app/api.py; LiveTranscription in nm/shared/model_openai_adapter.py) and the transcription spend on the development ledger (AudioCallBudget in nm/shared/model_call_budget.py), which AN.17 now also counts against each account.

## Notes

Voice is explicitly included. It follows document custody and grounded summaries so it does not distract from core legal accuracy.

## Column 7

2026-10-15 Built as item 8; its decisions, pieces and live check are recorded in G161 under 'ITEM 8'. Owner decision 15 Oct 2026: live words while dictating are built with OpenAI's live transcription (G164). | 2026-10-15 OWNER DECISION ON LIVE WORDS (refines the decision above): 'In the user settings, let's give them an option to select between GPT transcribe and GPT live transcribe. But by default, let us keep GPT transcribe selected and let us only use GPT transcribe. And if the users want live transcribe, they can go to their settings and enable live transcribe option. Otherwise, by default, there is no live transcribe.' So: each advocate's settings carry a choice of dictation model, gpt-transcribe (default, $0.0045 a minute) or gpt-live-transcribe ($0.017 a minute, official pricing page checked 15 Oct 2026); only an advocate who chooses live transcription has audio streamed while speaking; everyone else dictates as now. | 2026-10-17 A recording that could not be transcribed just now: the transcriber logs the provider failure (kind and message, no words heard) and the attachment offers 'Transcribe again'; decision recorded in G163.
