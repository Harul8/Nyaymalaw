# 02 — Open matter

The upload, document-text and media contracts and the local document reader the served app uses. Upload custody, isolation, readable derivatives and admission remain distinct states. The earlier intake, screens, quarantine and dictation modules were deleted on 19 Oct 2026 (P24).

## Current file index

This index follows the shipped [source-layout manifest](../source_layout.json). The semantic roles below retain the existing dependency boundary; the journey folder is not a permission or acceptance claim.

### Contracts and package

- [__init__.py](__init__.py) — Matter opening: the recorded brief, authority screens and admitted material.
- [intake_contracts.py](intake_contracts.py) — Receiving material, and never claiming to have read it.
- [media_contracts.py](media_contracts.py) — Types media custody and admission before legal reasoning may use its contents.
- [media_policy_contracts.py](media_policy_contracts.py) — Types allowed media-processing requests and responses.

### Ports

- [document_text_port.py](document_text_port.py) — Local reading of admitted original bytes, never admission or legal fact creation.
- [matter_documents_port.py](matter_documents_port.py) — Owned, admitted matter-document text, separate from public legal authority.
- [upload_port.py](upload_port.py) — Defines storage of immutable original upload bytes.

### Adapters

- [document_isolation.py](document_isolation.py) — Hard process memory bounds for untrusted local document parsers.
- [document_local.py](document_local.py) — Read admitted document bytes locally in a hard-bounded disposable process.

### Browser assets

- [dictation-worklet.js](dictation-worklet.js) — Captures microphone audio for local live dictation.
- [intake-materials.css](intake-materials.css) — Intake media controls, upload progress and permission-state presentation.
- [intake-materials.js](intake-materials.js) — Original receipt is not permission to read, and never establishes a fact.

Only the exact declared `/static/<name>` URLs are public; Python and private files in the same folders are never a static population.
