# 02 — Open matter

Intake, engagement/capacity/conflict screens and the arrival of supplied words, uploads and dictated material. Upload custody, quarantine, readable derivatives and admission remain distinct states.

Key files:

- [intake.py](intake.py) — Coordinates supplied information against the native opening and intake contracts.
- [uploads_api.py](uploads_api.py) — Owns the HTTP-facing sealed/resumable upload service.
- [documents_api.py](documents_api.py) — Binds document reads to custody, quarantine and derivative owners.
- [document_permission.py](document_permission.py) — Composition-owned configuration of the document checker; missing configuration is not clearance.

## Current file index

This index follows the shipped [source-layout manifest](../source_layout.json). The semantic roles below retain the existing dependency boundary; the journey folder is not a permission or acceptance claim.

### Composition and configuration

- [document_permission.py](document_permission.py) — Pairs a configured quarantine checker with its permitted document destination.

### Services and native owners

- [conflict.py](conflict.py) — Screens parties against the advocate's held matters.
- [intake.py](intake.py) — Coordinates document intake and permitted extraction.
- [quarantine.py](quarantine.py) — Quarantines untrusted uploads before any admitted reading.
- [screens.py](screens.py) — Runs opening conflict, capacity, scope and emergency checks.

### Contracts and package

- [__init__.py](__init__.py) — Matter opening: the recorded brief, authority screens and admitted material.
- [binding_contracts.py](binding_contracts.py) — Types the explicit link between admitted material and a dispute.
- [capacity_contracts.py](capacity_contracts.py) — Human capacity assessment on the record, not inferred from account or role.
- [commission_contracts.py](commission_contracts.py) — What this advocate was actually instructed to do.
- [dictation_contracts.py](dictation_contracts.py) — Dictating a brief: speech in, words out, nothing kept.
- [emergency_contracts.py](emergency_contracts.py) — Types emergency triage with a recorded basis and expiry.
- [engagement_contracts.py](engagement_contracts.py) — Types client identity and the recorded scope of engagement.
- [intake_contracts.py](intake_contracts.py) — Receiving material, and never claiming to have read it.
- [media_contracts.py](media_contracts.py) — Types media custody and admission before legal reasoning may use its contents.
- [media_policy_contracts.py](media_policy_contracts.py) — Types allowed media-processing requests and responses.
- [opening_contracts.py](opening_contracts.py) — Types the bounded instructions recorded when a matter is opened.

### Ports

- [document_text_port.py](document_text_port.py) — Local reading of admitted original bytes, never admission or legal fact creation.
- [matter_documents_port.py](matter_documents_port.py) — Owned, admitted matter-document text, separate from public legal authority.
- [transcription_port.py](transcription_port.py) — Defines speech-to-text requests and results for dictating a brief.
- [upload_port.py](upload_port.py) — Defines storage of immutable original upload bytes.

### Adapters

- [document_isolation.py](document_isolation.py) — Hard process memory bounds for untrusted local document parsers.
- [document_local.py](document_local.py) — Read admitted document bytes locally in a hard-bounded disposable process.
- [speech_local_whisper.py](speech_local_whisper.py) — Dictation transcribed on this machine by an open-source Whisper model.
- [speech_vosk_live.py](speech_vosk_live.py) — Live dictation words, from a small model on this machine's processor.

### HTTP and rendering boundary

- [document_reading_api.py](document_reading_api.py) — Owned local document requests; neither upload nor model output grants analysis.
- [documents_api.py](documents_api.py) — Trusted local document reading, with one receipt authority and no model consent.
- [transcripts_api.py](transcripts_api.py) — Browser readback is an authorised projection, never the raw diagnostic archive.
- [uploads_api.py](uploads_api.py) — Intake-boundary original receipt, never a legal reasoning pipeline.

### Browser assets

- [dictation-worklet.js](dictation-worklet.js) — Captures microphone audio for local live dictation.
- [intake-materials.css](intake-materials.css) — Intake media controls, upload progress and permission-state presentation.
- [intake-materials.js](intake-materials.js) — Original receipt is not permission to read, and never establishes a fact.

Only the exact declared `/static/<name>` URLs are public; Python and private files in the same folders are never a static population.
