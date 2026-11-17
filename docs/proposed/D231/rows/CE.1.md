# CE.1 - Layout

Row 45 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

CE.1

## Item

Layout

## Description

Current layout: nm/core_engine/, flat. turn.py orchestrates authenticated turns; conversation.py owns exact context, atomic saving and replay; calls.py owns turn accounting and shared correction. understanding.py interprets requests; citations.py and statute readback check identities; research.py and retrieval.py find held passages; response_writer.py, response_review.py and rendering/source-presentation owners prepare checked answers. The existing chat serves this development engine. Documents, summaries and later matter capabilities remain planned. Earlier M1 work stays private and inactive.

## Governs or depends on

P6, P9; E1, E2

## Status

Development core served; SEQ.1-4 quality and browser acceptance remain open.
