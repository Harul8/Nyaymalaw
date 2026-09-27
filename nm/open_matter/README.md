# Open matter

Intake, engagement/capacity/conflict screens and the arrival of supplied words, uploads and dictated material. Upload custody, quarantine, readable derivatives and admission remain distinct states.

Key files:

- [intake.py](intake.py) — Coordinates supplied information against the native opening and intake contracts.
- [uploads_api.py](uploads_api.py) — Owns the HTTP-facing sealed/resumable upload service.
- [documents_api.py](documents_api.py) — Binds document reads to custody, quarantine and derivative owners.
- [document_permission.py](document_permission.py) — Composition-owned configuration of the document checker; missing configuration is not clearance.

## Current file index

This index follows the shipped [source-layout manifest](../source_layout.json). The semantic roles below retain the existing dependency boundary; the journey folder is not a permission or acceptance claim.

### Composition and configuration

- [document_permission.py](document_permission.py)

### Services and native owners

- [conflict.py](conflict.py)
- [intake.py](intake.py)
- [quarantine.py](quarantine.py)
- [screens.py](screens.py)

### Contracts and package

- [__init__.py](__init__.py)
- [binding_contracts.py](binding_contracts.py)
- [capacity_contracts.py](capacity_contracts.py)
- [commission_contracts.py](commission_contracts.py)
- [dictation_contracts.py](dictation_contracts.py)
- [emergency_contracts.py](emergency_contracts.py)
- [engagement_contracts.py](engagement_contracts.py)
- [intake_contracts.py](intake_contracts.py)
- [media_contracts.py](media_contracts.py)
- [media_policy_contracts.py](media_policy_contracts.py)
- [opening_contracts.py](opening_contracts.py)

### Ports

- [document_text_port.py](document_text_port.py)
- [matter_documents_port.py](matter_documents_port.py)
- [transcription_port.py](transcription_port.py)
- [upload_port.py](upload_port.py)

### Adapters

- [document_isolation.py](document_isolation.py)
- [document_local.py](document_local.py)
- [speech_local_whisper.py](speech_local_whisper.py)
- [speech_vosk_live.py](speech_vosk_live.py)

### HTTP and rendering boundary

- [document_reading_api.py](document_reading_api.py)
- [documents_api.py](documents_api.py)
- [transcripts_api.py](transcripts_api.py)
- [uploads_api.py](uploads_api.py)

### Browser assets

- [dictation-worklet.js](dictation-worklet.js)
- [intake-materials.css](intake-materials.css)
- [intake-materials.js](intake-materials.js)

Only the exact declared `/static/<name>` URLs are public; Python and private files in the same folders are never a static population.
