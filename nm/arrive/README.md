# Arrive

Account registration, authentication, sessions, account mail and professional-access state. Account access, professional qualification and permission to act on a client file remain separate contracts.

Key files:

- [advocate_contracts.py](advocate_contracts.py) — Account, consent and session state and transition rules.
- [store_directory.py](store_directory.py) — Native account/session and professional-approval storage adapter.
- [professional_access.py](professional_access.py) — Failure-closed reading of professional status through its supplied owner.
- [draft-vault.js](draft-vault.js) — Encrypted browser draft storage; a saved draft does not establish admission or advice.

## Current file index

This index follows the shipped [source-layout manifest](../source_layout.json). The semantic roles below retain the existing dependency boundary; the journey folder is not a permission or acceptance claim.

### Services and native owners

- [professional_access.py](professional_access.py)

### Contracts and package

- [__init__.py](__init__.py)
- [account_confirmation_contracts.py](account_confirmation_contracts.py)
- [advocate_contracts.py](advocate_contracts.py)
- [attempts_contracts.py](attempts_contracts.py)
- [mail_contracts.py](mail_contracts.py)
- [professional_access_contracts.py](professional_access_contracts.py)

### Ports

- [directory_port.py](directory_port.py)
- [mail_port.py](mail_port.py)

### Adapters

- [mail_gmail.py](mail_gmail.py)
- [mail_outbox.py](mail_outbox.py)
- [store_directory.py](store_directory.py)
- [store_pending_accounts.py](store_pending_accounts.py)

### Browser assets

- [draft-vault.js](draft-vault.js)

Only the exact declared `/static/<name>` URLs are public; Python and private files in the same folders are never a static population.
