# Matter custody checkpoint — 27 September 2026

Scope: a generalised key-creation boundary, not a legal-brain completion claim.

## Implemented behaviour

- FileMatterStore permits key creation only after its locked version check
  establishes that this is the initial matter creation.
- Existing matter updates, recorded turns, originals and derivatives require
  the existing matter key. Missing or erased custody is a refusal, not authority
  to mint another key.
- PostgresMatterStore admits the unique initial row before permitting key
  creation. The provisional empty envelope is filled in the same transaction;
  a sealing refusal rolls back. A conflicting initial insert never seals or
  creates a key. Existing updates cannot create one.
- One population control scans the entire backend and requires all four
  sealing call sites to declare their key-creation authority explicitly.

## Verification

Final local run: **61 passed, zero failures/errors/skips, 22.40 seconds**.
Artifact: `.nm/evaluations/custody-checkpoint-20260927.xml`.

Named files:

- `tests/test_only_initial_matter_creation_can_mint_a_key.py`
- `tests/test_original_intake_is_sealed_resumable_and_unread.py`
- `tests/test_upload_containment_survives_path_resolution.py`

Existing upload containment and original-ciphertext assertions were retained.
Their setup now creates the actual matter before exercising derivative writers.
The new controls cover stable keys/readable envelopes, lost custody at every
derivative writer, key loss between load and commit, conflicting PostgreSQL
creation, rollback on sealing refusal, and the complete sealing population.

The PostgreSQL controls exercise the actual adapter with statement/transaction
boundary doubles; a reachable live PostgreSQL durability test was not available.
The earlier PostgreSQL cohort recorded 15 database-dependent skips. Those are
not passing durability evidence.

## Boundaries

This checkpoint does not refresh Class-A evidence, promote a gate, establish
qualified Indian legal-source data, complete production replay, prove live
response quality, or enable ordinary-client controlled-brain processing. Other
legal-brain work in the working tree is deliberately outside this commit.
