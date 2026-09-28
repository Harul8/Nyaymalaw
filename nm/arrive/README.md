# 01 — Arrive

Account registration, authentication, sessions, account mail and professional-access state. Account access, professional qualification and permission to act on a client file remain separate contracts.

Key files:

- [advocate_contracts.py](advocate_contracts.py) — Account, consent and session state and transition rules.
- [store_directory.py](store_directory.py) — Native account/session and professional-approval storage adapter.
- [professional_access.py](professional_access.py) — Failure-closed reading of professional status through its supplied owner.
- [draft-vault.js](draft-vault.js) — Encrypted browser draft storage; a saved draft does not establish admission or advice.

## Current file index

This index follows the shipped [source-layout manifest](../source_layout.json). The semantic roles below retain the existing dependency boundary; the journey folder is not a permission or acceptance claim.

### Services and native owners

- [professional_access.py](professional_access.py) — Reads professional-approval status through its port and handles unavailable records safely.

### Contracts and package

- [__init__.py](__init__.py) — Account arrival: registration, sign-in, recovery, sessions and private drafts.
- [account_confirmation_contracts.py](account_confirmation_contracts.py) — Mailbox proof is bounded account activation, never professional approval.
- [advocate_contracts.py](advocate_contracts.py) — Defines the advocate identity referenced by later records.
- [attempts_contracts.py](attempts_contracts.py) — Defines bounded failed-attempt and lockout rules.
- [mail_contracts.py](mail_contracts.py) — Account mail: what the product writes to an advocate's email address.
- [professional_access_contracts.py](professional_access_contracts.py) — Operator-reviewed professional profile, separate from account and matter access.

### Ports

- [directory_port.py](directory_port.py) — Defines account and session directory operations.
- [mail_port.py](mail_port.py) — Defines how account confirmation and recovery messages are delivered.

### Adapters

- [mail_gmail.py](mail_gmail.py) — Gmail account-mail transport, disabled until separately authorised.
- [mail_outbox.py](mail_outbox.py) — Stores account messages in the sealed local test outbox without sending email.
- [store_directory.py](store_directory.py) — Stores sealed accounts, sessions and professional status.
- [store_pending_accounts.py](store_pending_accounts.py) — Sealed pending account records, with one transactional owner of code limits.

### Browser assets

- [draft-vault.js](draft-vault.js) — Keeps encrypted unsent drafts on the same device.

Only the exact declared `/static/<name>` URLs are public; Python and private files in the same folders are never a static population.
