# The existing legal database: preserve, reconcile and republish

Inspection date: 10 September 2026. Status: bounded read-only assessment and proposed migration plan, owned by BK-84/M05 under the blueprint. No corpus rebuild, re-embedding, cleanup, checkpoint, content migration or legal-data deletion was performed.

The requested `legal/_database` path was not the present directory. The actual corpus used by the code is `C:/Users/rahul/Nyaymalaw/legal_database`. The user should not create a second similarly named corpus directory to follow this plan.

The directory is a Windows junction to `C:/Users/rahul/Agentified NM/legal_database`,
confirmed from filesystem metadata. It is shared source storage, not an
independent copy inside this repository. Inventory all consumers before a
cutover; never rebuild, move or delete through the junction as if only this
application could be affected. This assessment made no changes at either path.

## 1. Recommendation

**Keep the corpus as a valuable source collection, preserve its existing working retrieval, and build a governed canonical publication beside it. Do not delete it and start again, and do not treat the existing vector files as the authoritative legal brain.**

There are useful raw texts, structural chunks, lexical indexes, case identity work and live-source adapters. There are also several generations of derived copies with different purposes and incomplete visible lineage. The correct rebuild is a controlled data-engineering and legal-quality migration, not a change of database brand or a fresh embedding run.

Use the existing collection for discovery and migration input. Promote each source, identity, legal-time field and derivative into the new trusted publication only after the corresponding validation. A raw text labelled as a statute or judgment is not automatically an authenticated official original; a ranked chunk labelled `ratio` is not automatically an applicable holding.

## 2. What was actually inspected

The inspection used directory metadata, the small `VERSION` and BM25 parameter files, SQLite table/index definitions, the existing identity tables, one indexed source row of each of two document types, three bounded raw-text/header samples, the curated manifest header and the runtime composition/retrieval source. SQLite was opened with `mode=ro`, `PRAGMA query_only=ON`, short timeouts and bounded queries. No full table counts, integrity scan, vector deserialisation, model calls or corpus-wide quality sampling were run.

`chat_history` was observed by name but its contents were not opened. It must be treated as potentially private material, not part of the public-law corpus. File sizes below are observed bytes at inspection time. Embedded identity counts below are values recorded by earlier builders, not independently re-counted populations today.

### 2.1 Physical layout and purposes

| Observed location | What it contains or declares | Present interpretation |
|---|---|---|
| `legal_database/raw_data/BareActs/{Telangana,Union of India}` | Text source files; sampled statute text begins with third-party website/navigation material | Valuable source renditions needing provenance and boilerplate/structure validation |
| `legal_database/raw_data/CaseLaws/{Supreme Court,Telangana HC}` | Year-organised text files; sampled headers include court/date/reporter citations, some bench/party fields | Recoverable identity information; directory labels are not a legal applicability determination |
| `legal_database/raw_data/_duplicates_archived` | Duplicate-archive directory observed in the initial inventory | Preserve until duplicate/version reconciliation proves what can be retired |
| `legal_database/vector_store/chunks.db` | 3,743,100,928 bytes; table `chunks` plus indexes; document-type/position key and JSON blob | Current primary chunk lookup store for the evidence adapter; not a complete canonical source/version model |
| `chunks.db-wal`, `chunks.db-shm` | WAL 2,929,352 bytes and SHM 32,768 bytes at inspection | Treat the database as potentially active; do not copy/delete the main file in isolation |
| `bareacts_v3.index`, `caselaws_v2.index` | 1,698,652,205 and 4,160,892,973 bytes respectively | Legacy vector artifacts present; dimension/model/source compatibility was not verified |
| `bareacts_v3_bm25s`, `caselaws_bm25s` | Memory-mapped arrays, vocabulary and small parameter files | Existing lexical artifacts with recorded parameters; not proven current/complete by existence |
| `*_chunks.json`, `*_parents.json`, `*_bm25.json`, summaries and `.bak`/`.pre_dedup.bak` files | Multiple large derived and backup representations | Reconcile lineage; do not make every copy a runtime source of truth |
| `vector_store/legal.db` | 51,617,792 bytes; `acts`, `sections`, cross-references and case-section links | A legal-navigation/link projection with its own identity conventions |
| `vector_store/library.db` | 92,577,792 bytes; a `docs` table with browse/search fields | A library catalogue/read-pane projection, not a full authoritative text store |
| `vector_store/citator.json`, `citation_graph.json`, `contamination_denylist.json` | Citation/treatment and exclusion artifacts | Preserve as candidates with provenance; legal accuracy and current reconciliation require separate evaluation |
| `legal_database/succession_map.csv` | Old/new Act and section mappings, subject and a `verified` column | Candidate transition mapping; a label such as `high` is not a source or legal review record |
| `.nm/authority.db` | 1,097,412,608 bytes; FTS5 `paras` plus identity table | Runtime authority search index built by this repository |
| `.nm/identity.db` | 54,169,600 bytes; cases, citations, treatment, rejects and identity | Runtime case-identity/treatment projection built from raw case texts |
| `legal_database/chat_history` | Directory name only; deliberately not read | Separate private-data review and migration, never public corpus indexing |

This is not a fresh total-size or file-count census. It does not verify that all files are readable, safe, unique, legally current or licensed for the proposed use.

### 2.2 Recorded identities, with their limits

`vector_store/VERSION` reads `legacy-2026-08-27`. `pipeline/manifest.yaml` begins with `corpus_version: vector_store@2026-08-29` and a reconciliation date of 29 August 2026. These are different authored identifiers. That is an identity-reconciliation task; it does not, by itself, prove an index contains different bytes. The new publisher must give source release, extraction release and retrieval release explicit linked identities instead of relying on similarly dated strings.

The `.nm/authority.db` identity table records:

- Build time `2026-08-30T07:51:38` and source path pointing to the current `vector_store/chunks.db` location.
- Corpus version `legacy-2026-08-27`.
- 1,015,780 source case paragraphs; 451,548 indexed paragraphs; 564,232 excluded as not attributable; zero excluded by denylist at that build; `partial: no`.
- Included labels `ratio,reasoning,order`.

These numbers sum consistently inside the recorded manifest, but were not recounted. “Partial: no” means the builder completed its declared selection, not that the index holds all judgment content or all relevant law. A research-discovery path should eventually be able to inspect non-holding context while separately controlling whether it may support an attributed legal proposition.

The `.nm/identity.db` identity table records a build time `2026-08-30T09:18:08`, 34,037 source files/cases, 33,015 with a bench, 30,950 with citations, 13,625 with party data, 302,909 citation keys, 2,592 treatment records, 1,633 targets reached, 316 adverse targets and 26,744 rejects. These are **recorded builder measurements**, not current independent quality or coverage measurements. They differ from some historical prose examples in the repository; preserve the historical reports while making current measured evidence unambiguous.

The two BM25 parameter files declare 414,710 bare-Act documents and 1,015,780 case documents, `method: robertson`, `k1: 1.5`, `b: 0.75`, library version `0.3.9` and NumPy backend. This documents some build parameters but does not prove their arrays align with the current chunks or identify the vector embedding model. No existing FAISS file was loaded or queried in this inspection.

### 2.3 What the running source is configured to read

`backend/nm/bootstrap/composition.py` constructs the evidence adapter using the configured corpus directory or the repository's `legal_database/vector_store`, the curated manifest, the authority index and the identity index. Environment overrides can change these paths, so deployed health must report the effective values and identities.

The inspected `backend/nm/adapters/evidence/corpus.py` reads provisions from `chunks.db`, unions configured Act identifier patterns, uses the corpus citator and `.nm/identity.db`, and reads judgment search from `.nm/authority.db`. `backend/nm/adapters/search/authority.py` also uses that authority FTS index. Therefore the large legacy FAISS files are not evidence that these inspected runtime paths are performing dense retrieval. This is a bounded statement about the inspected composition and adapters, not an exhaustive assertion about every possible script or deployment.

The code has valuable safeguards: exact-source concepts, named searched stores, absent-versus-unavailable states, identity records, denylist handling and no silent authority fallback to a different whole-corpus scan. Preserve those contracts during migration.

There are also limitations worth deliberately replacing:

- Provision union lookup selects the longest candidate text when identifiers overlap. That repairs a known truncation problem but length is not legal authority, correct version or authenticity. Canonical version/locator selection must replace this heuristic after reconciliation.
- Some readiness properties check file existence. File presence alone does not establish readable schema, matching source identity, healthy indexes, fresh legal coverage or permission to use a source.
- The curated manifest contains `in_force_from` values at 1 January of enactment years in the sampled entries. Their legal accuracy/provenance was not established by this inspection. Audit every effective-date premise before using it as a legal-time gate; do not assume an enactment year proves commencement.
- The `chunks` relational columns do not carry a canonical immutable source version, byte hash, acquisition provenance or effective-time model. Such information might exist in individual blobs or other files; it is not enforced by the inspected table schema. The new publication must make those requirements explicit.
- The source's `ratio/reasoning/order` labels are used for selecting the authority index. Label-based selection is not an independent legal check of speaker, support, ratio boundary, treatment or applicability.

### 2.4 The samples show reasons to preserve and reasons to validate

One sampled raw statute file (`1872_1_The Indian Evidence Act, 1872.txt`) begins with third-party search/navigation boilerplate. This proves contamination in that sample, not a corpus-wide rate. Retain that original rendition, record its origin, and build a cleaned derivative whose removals can be checked against it. If official text is later obtained through a permitted source, preserve both with a verified equivalence/difference record.

The sampled Supreme Court case header (`SC_1950_AK_GOPALAN_VS_THE_STATE_OF_MADRASUNION_OF_INDIA.txt`) contains reporter citations, author/bench labels and party blocks. The sampled historical High Court header (`HC_1954_BADDURI_CHANDRA_REDDY_AND_ANR_VS_PAMMI_RAMI_REDDY_AND_ORS.txt`) contains date and parallel citations. This supports recovering metadata from raw texts rather than declaring fields absent because a chunk does not hold them. It does not establish these sources' authenticity, current precedential use or general extraction accuracy.

One indexed case chunk has a `ratio` label and begins mid-context. That is a reason to require source expansion and independent attribution/entailment review, not enough evidence to declare that specific label wrong. The sampled bare-Act chunk preserves structural fields such as `section_number`, `atom_type` and `parent_chain`; reuse that work where source alignment validates it.

## 3. What to retain, what to rebuild, what not to trust yet

| Decision | Assets | Conditions |
|---|---|---|
| Preserve as migration evidence | Raw texts, source folder structure, existing databases, manifests, aliases, succession candidates, denylist, current retrieval builders and test records | Preserve original paths/IDs in a migration map; protect any private content separately |
| Reuse after validation | Text extractions, paragraph/provision segmentation, recovered citations/bench data, lexical indexes and exact lookup adapters | Verify source alignment, identity, scope, completeness and legal interpretation relevant to use |
| Rebuild into a canonical publication | Source identity/provenance, legal valid-time, versioned canonical IDs, reviewed alias map, corpus coverage, paragraph attribution/treatment lineage and publication manifest | New immutable output beside the old; counsel-reviewed semantic fields; reproducible build |
| Rebuild derived search only when justified | Dense embeddings, fused retrieval, summaries, lexical projections | Compatible embedding identity; fixed relevance benchmark; measured quality/latency/cost advantage |
| Isolate from public-law migration | `chat_history` and any private matter-derived artifact | Separate authority, data protection, retention and deletion assessment |
| Retire only after explicit approval | Duplicate/backup artifacts proven redundant and unused | Verified backup/restore, consumer inventory, retention decision, reversible retirement window and no active readers |

Do not deserialise unknown legacy pickle/object payloads as an audit shortcut. Use verified formats or a restricted offline migration process. Do not use a claimed vector dimension alone as proof of compatibility: model, version, preprocessing, normalisation, distance metric, ID mapping and source generation must align.

## 4. The step-by-step rebuild and cutover

### Step 1 — Freeze scope and protect the source

Register BK-84 acceptance and identify the data owner, legal reviewer and migration operator. Record that this is an India-only corpus with a bounded initial Telangana/Union capability. Identify current writers/readers, the resolved junction target, free space and approved maintenance/backup window. No recursive move/delete should target the corpus junction or its parent.

Plan a consistent SQLite backup using its backup API or an approved quiesced process; do not make a casual copy of `chunks.db` while ignoring its WAL. The [SQLite WAL documentation](https://sqlite.org/wal.html) explains that committed transactions can reside in the WAL, and the [SQLite backup API](https://sqlite.org/backup.html) supports consistent database snapshots. Validate the resulting copy before treating it as recoverable. This plan did not run that backup.

Deliverable: protected snapshot plan, storage budget, owners and a restore rehearsal on a safe copy. Stop if a complete consistent recoverable snapshot cannot be made.

### Step 2 — Inventory consumers and source lineage

Build a bounded-first, then explicitly approved full inventory of files, hashes, formats, schemas, source links, ID conventions and runtime consumers. Use source original populations for coverage; do not infer absence from a derived store. Mark chat/private artifacts excluded. Account for every known store and every backup generation without adding them all to runtime retrieval.

Deliverable: machine-readable asset/consumer manifest with `original`, `rendition`, `projection`, `backup`, `private` or `unknown` classification. “Unknown” assets are retained and barred from trusted publication until resolved.

### Step 3 — Establish the canonical source register

For each source record acquisition origin, rights/access basis, byte hash, court/instrument identity, source version/date, language, parse state and locator scheme. Reconcile same-source copies and corrected versions without using longest text as the deciding rule. Resolve aliases through exact verified identities; quarantine collisions and retain the original IDs as migration aliases.

Deliverable: source registry and lossless legacy-ID map. Validate no old source locator silently points to a different instrument or case after migration.

### Step 4 — Re-extract only the required failing populations

Profile a representative stratified sample first: Acts with schedules/tables/provisos/amendments, historical and newer judgments, different languages, long files, duplicate identities, third-party boilerplate and suspected contamination. Measure defects and their populations. Re-extract affected types using one general mechanism; do not reprocess the whole corpus automatically if validated material is reusable.

Deliverable: aligned cleaned renditions, source-map and extraction report with rejected/partial populations. No label “clean” without a sample design and counterexamples.

### Step 5 — Repair legal semantics and effective time

Counsel review covers instrument identity, commencement/amendment/repeal/savings relationships, structured provision locators, court/bench/territorial relationships, speaker attribution, judgment context and proposition-level treatment. Use the succession CSV as a candidate map, never as sufficient legal proof. Preserve `not_assessed` where the evidence is absent.

Deliverable: reviewed rules and a legal metadata release whose supporting sources are inspectable. Newly encountered Indian states/courts or post-existing-cutoff decisions remain outside enabled capability until their relationship rules and sources are approved. The current corpus label is not permission for all-India advice.

### Step 6 — Publish one consistent search generation

Build the canonical relational/public-source records and lexical/dense projections from the same validated source release. Include all needed discovery context while keeping quotability/support restrictions separate. Generate a manifest containing source hashes, derived populations, exclusions, tool/model identities, review state and freshness. Test exact lookup and adverse/contextual retrieval on fixed independently labelled examples.

Deliverable: immutable candidate corpus release, no default runtime switch. Reject mismatches, empty populations, missing identity and unexplained candidate loss. Apply the [M05/M06 build contracts](LEGAL_BRAIN.md#9-module-task-packets-build-demonstrate-close).

### Step 7 — Shadow compare old and new

Run a separately approved bounded portfolio through old and new adapters with the same queries and declared scope. Compare exact identity, text/version, provenance, recall, adverse coverage, false absence, legal metadata and latency/cost. A changed answer requires explanation; neither old nor new output is assumed correct merely because it exists.

Deliverable: adjudicated differences and rollback eligibility. Keep existing legal safeguards and known-good regression scenarios; do not lower gates to permit the new data layout.

### Step 8 — Controlled cutover and revalidation

Switch a corpus manifest pointer for a synthetic environment first, then an authorised pilot. The running health report shows effective source/index generation and capability limits. Invalidate dependent retrieval packets/advice when semantics or versions change; preserve earlier issued advice's source record subject to retention/permissions. Rehearse fallback without restoring ineligible or revoked data.

Deliverable: served source readback, restart/rollback proof, scoped release approval and current baseline evidence. No “database rebuilt” claim until the live runtime actually uses and verifies the new publication.

### Step 9 — Retire duplication deliberately

Only after the new release is stable and recoverable, enumerate artifacts with no remaining consumer and determine retention. Prefer a reversible retirement/archive step within the approved storage policy. Delete nothing merely because its filename says `.bak`, `legacy` or `duplicate`; originals and unique metadata can hide there.

Deliverable: explicit approved retirement list, backup/restore reference, consumer-zero evidence and recovery window. Keep the historical project record without retaining unnecessary confidential data.

## 5. What can be concluded today

The collection is substantial and worth preserving. The existing runtime uses a more specific set of stores than the directory name “vector_store” suggests. There is useful identity and exact-retrieval engineering already in place. The largest gains are likely to come first from source/version governance, temporal/identity reconciliation, context-safe retrieval and legal metadata quality—not from buying a larger model or embedding everything again. That is a design inference from the bounded inspection, not a benchmark result.

The inspection does **not** certify corpus completeness, current Indian law, licensing, database integrity, all-India coverage, treatment correctness, FAISS compatibility or professional answer quality. The rebuild plan turns those unknowns into named acceptance work before they become claims in the product.
