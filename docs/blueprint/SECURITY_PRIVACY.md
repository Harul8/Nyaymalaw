# NM security, privacy and operational trust

Design baseline: 10 September 2026. Scope: an India-only product for practising advocates. Initial verified legal coverage remains Telangana and Union law; India-only operation does not mean that every Indian jurisdiction is covered.

This is an implementation specification and acceptance guide, not a statement that these controls exist, a legal opinion, a certification, or a promise of invulnerability. Delivery status belongs to the existing backlog and evidence system. BK-81 records the blueprint; BK-85 owns the W0 key, processor-policy and security-operations foundation; BK-80 owns the outstanding release-profile enforcement work. BK-69 owns the W0 media admission boundary, BK-79 its later intake/attribution/deletion integration, and BK-42 the W7 deployed production assurance. None substitutes for the others. The numbered controls below are acceptance references within this document, not a second delivery-status registry. Section 3 maps them to registered criteria; [evaluations.json](evaluations.json) supplies concrete synthetic test specifications and independent review protocols.

BK-88 owns the enabled-path security integration: AC1 proves served copy/hold/deletion/restore behavior; AC2 proves actual processor, region, key and support enforcement; AC3 proves the scoped confidential pilot's recovery, incident and least-privilege evidence. It does not require every later product feature to be complete, but it requires every path enabled for that pilot to be covered. BK-85's policy foundation alone is not that proof.

The early strong-authentication criterion requested below is now registered as
BK-86 at W0. Pilot and production profiles name BK-85 and BK-86 explicitly;
BK-42 retains deployed integration assurance. This is planned work, not a
claim that the strong-authentication implementation has been delivered.

## 1. The outcome to build

An advocate can identify who can access a matter, what leaves NM, why it leaves, where copies live, what has changed, and how to revoke access or obtain help. A developer cannot silently turn a useful demo into permission to process privileged files. A model cannot enlarge its own permissions. A failed security dependency cannot be reported as a successful check.

Security includes confidentiality, integrity, availability, authenticity and accountability. Privacy also asks whether NM should collect or use the information at all. A perfectly encrypted unnecessary recording can still be a privacy failure. Legal privilege is a legal status affected by context and conduct; encryption and a “privileged” label do not establish it.

The target architecture is a Python modular monolith, PostgreSQL for authoritative records and transactions, encrypted object storage for originals and derivatives, managed keys, permissioned search projections, and durable outbox-driven workers. Keep these boundaries explicit even when one small deployment hosts several components. Do not introduce microservices merely to appear secure.

### Operating profiles

| Profile | Permitted material and audience | Gate before enabling |
|---|---|---|
| Synthetic demonstration | Invented identities, fabricated evidence and approved public corpus; clearly marked demo workspace | Isolated environment, no production secrets, deterministic reset, visible module/evidence state; no accidental real-data import |
| Restricted real-matter pilot | Specifically approved advocates, firms, matters, providers and enabled capabilities | All controls protecting that data path, including identity, isolation, encryption, processor approval, retention, recovery and incident response; legal/privacy owner approval |
| Production | Only approved customer population and feature manifest | Restricted-pilot gates plus capacity, recovery, independent security review, professional-quality evidence, support and release sign-off |

“Live validation” initially means using the actual interface and served path with synthetic data. It does not mean live client data. Disabled modules must be denied by the server, not simply hidden in the UI. Prototype exceptions do not survive a profile change. No profile may waive cross-firm isolation, unauthorized disclosure, required legal obligations, or authority to act.

For the procurement-free local build, use the catalog's `scripted_local` profile: invented data, no production credentials, no external provider requests, local no-send action sinks and scripted key/identity/model ports. Approved public-source component tests are a separately declared corpus-scoped population, not permission to copy the user's shared database into an ordinary demo. Local fake keys, factors and clocks can prove application control flow; they cannot satisfy managed-key, actual-device, statutory-response or deployment evidence.

## 2. Applicable law and international engineering benchmarks

Use Indian law as the regulatory baseline. International standards guide engineering and assurance; they do not create an “all global laws compliant” badge. These sources were checked on 10 September 2026. At release, the legal owner must recheck the actual instruments, amendments, commencement, exemptions, entity classification and contracts. Store the dated determination and sources with the release evidence.

| Source | What it contributes to NM | What it does not prove |
|---|---|---|
| [NIST CSF 2.0](https://www.nist.gov/news-events/news/2024/02/nist-releases-version-20-landmark-cybersecurity-framework) | Govern, Identify, Protect, Detect, Respond and Recover as a management-level coverage map | That a mapped control works or that NM is certified |
| [NIST SSDF 1.1, SP 800-218](https://csrc.nist.gov/pubs/sp/800/218/final) | Secure development, protected build environments, vulnerability response and supplier evidence | An automatic checklist pass; [SSDF 1.2 was an initial public draft](https://csrc.nist.gov/pubs/sp/800/218/r1/ipd), not the pinned final baseline |
| [NIST AI RMF and GenAI Profile](https://www.nist.gov/itl/ai-risk-management-framework) | AI-specific risk ownership, evaluation, monitoring and change control | Correct legal analysis or safe autonomous action |
| [NIST Privacy Framework](https://www.nist.gov/privacy-framework) | Purpose, data flows, privacy risk and individual impacts | Applicable statutory obligations; version 1.1 is presented as an initial public draft, so distinguish it from final 1.0 |
| [OWASP ASVS 5.0.0](https://owasp.org/www-project-application-security-verification-standard/) | Version-qualified application-security requirements; target applicable Level 2 requirements and risk-selected Level 3 requirements for high-impact paths | Certification by OWASP or permission to omit requirements without a reason |
| [OWASP GenAI LLM Top 10 2026](https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/) | A current AI attack-surface review alongside application controls; the resource is dated 3 August 2026 | Exhaustive threat coverage; keep mappings versioned because editions change |
| [CISA secure-by-design principles](https://www.cisa.gov/news-events/news/applying-secure-design-thinking-events-news) | Product ownership of customer security outcomes, transparency and leadership accountability | Making the advocate responsible for configuring away unsafe defaults |
| [ISO/IEC 27001:2022](https://www.iso.org/standard/27001) | A scoped information-security management system and, if commissioned, independent certification | Certification merely from implementing this plan; a certificate must cover the relevant organization, service and period |
| [AICPA SOC 2](https://www.aicpa-cima.com/topic/audit-assurance/audit-and-assurance-greater-than-soc-2/) | An independent examination and report on scoped service-organization controls | A statute, a product guarantee or an ISO-style certification; evaluate scope, period, exceptions and customer responsibilities |

### Indian applicability decisions required before real data

The dated, machine-checked counsel packet is
[INDIA_APPLICABILITY_REVIEW.md](INDIA_APPLICABILITY_REVIEW.md), generated from
[india_applicability_review.json](india_applicability_review.json). It owns the
current source, role, permission, retention, incident-clock, accountability and
reservation population for BK-85-AC3. It deliberately remains
`COUNSEL_REVIEW_REQUIRED`: neither this guide nor the generated packet is the
qualified review. Counsel must complete the generated template, evidence their
authority and place the signed, expiring record at the exact evidence path before
the criterion can pass. CHOICE-01, CHOICE-07, CHOICE-08 and CHOICE-10 remain later
exact-scope pilot/production decisions; they do not block packet construction.

1. **Record the legal roles by purpose.** The firm may determine purposes for matter processing; NM may have different responsibilities for account management or its own security operations. Do not copy one “processor” label over every activity. Record lawful basis or applicable permission, purpose, categories, recipients, retention and responsible organization.
2. **Respect phased DPDP commencement.** The notification dated 13 November 2025 provides immediate, one-year and eighteen-month tranches. Most substantive processing duties are in the last tranche; do not describe all provisions as already operative in September 2026. Have counsel confirm the exact operative dates from Gazette publication and subsequent instruments. [G.S.R. 843(E)](https://www.meity.gov.in/static/uploads/2025/11/c56ceae6c383460ca69577428d36828b.pdf).
3. **Build for the notified Rules now.** Rule 1 also stages commencement. Future requirements include security safeguards, breach communications and retention provisions in Rules 6 and 8. Do not hard-code immediate erasure or one universal retention period. Counsel must reconcile their scope with other duties, exemptions and legal holds. [DPDP Rules 2025, G.S.R. 846(E)](https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf), and the [MeitY rules/corrigendum entry](https://www.meity.gov.in/documents/act-and-policies/digital-personal-data-protection-rules-2025-gDOxUjMtQWa?pageTitle=Digital-Personal-Data-Protection-Rules-2025%C3%AF%C2%BF%C2%BC).
4. **Do not ignore transitional Indian obligations.** Obtain a current determination on the IT Act, SPDI Rules, professional confidentiality, client instructions, recording restrictions, evidence preservation, children’s data and applicable sector-specific requirements. The Government has separately described the existing SPDI protection regime; DPDP staging is not a security holiday. [MeitY parliamentary response, July 2025](https://www.pib.gov.in/PressReleaseIframePage.aspx?LID=1&PRID=2148944&RegID=3&lang=2&reg=48).
5. **Determine CERT-In coverage.** The 28 April 2022 Directions specify covered entities, incident reporting within six hours of notice, a designated contact, clock synchronization and secure rolling 180-day ICT logs. Scope the exact duties and reportable incidents; do not import separate cloud/VPS/VPN subscriber-record duties merely because NM uses a cloud provider. [Directions](https://www.cert-in.org.in/PDF/CERT-In_Directions_70B_28.04.2022.pdf?trk=public_post_comment-text). The FAQ permits initial reporting using available information with later supplementation. [CERT-In FAQ, question 30](https://www.cert-in.org.in/PDF/FAQs_on_CyberSecurityDirections_May2022.pdf).
6. **Choose India-region storage as the default product policy.** Include primary data, backups, search, telemetry and processing locations in that policy. This is a proposed confidentiality/residency choice, not a claim that DPDP universally localizes all data. No unapproved cross-border processor or failover. A new foreign nexus requires a specific legal review, not a global-compliance expansion of this build.

## 3. Ordered execution: build security into each module

Use the repository’s four stage guides. For each row below, write the failing example first, implement the shared mechanism, exercise every served entry point, then capture live proof. “Owner” means a named accountable person in the work record, not only a role printed here. One person can perform multiple roles in a small team; high-risk sign-off still needs an independent reviewer.

| Order and control | Implementation steps | Negative and live proof | Owner; earliest gate |
|---|---|---|---|
| 1. Scope and inventory | Record processing activities, assets, providers, jurisdiction, threats and data classes; pin the enabled-module manifest | Add an unapproved provider or unclassified dataset; real-data enablement refuses it and explains the missing approval | Product + privacy/legal; M00 before any real data |
| 2. Protected environments | Separate demo, development, staging and production identities, stores, keys and networks; deny public storage and production secrets in developer tools | Demo credentials cannot read production; seeded secret scanner fails the build; UI identifies the environment | Platform/security; M00 |
| 3. Identity and recovery | Build invitation/firm binding, strong authentication, authenticator lifecycle, rate limiting, session revocation and reviewed recovery | Stolen password alone fails the real-data profile; expired/replayed invitation and reused recovery code fail; competing recovery requests cannot both succeed | Identity/security; M01 |
| 4. Matter authorization | One policy service and database-enforced tenant boundary; explicit matter membership and ethical walls; deny by default | Two firms and a same-firm excluded advocate attempt every read/write/export/search/stream route; none sees even restricted titles | Application/data; M02 |
| 5. Cryptographic boundary | Use managed keys and encryption; bind ciphertext to identity/version; separate decryption from administrative access | Tampered blob, copied ciphertext in another matter and revoked key are refused; no plaintext fallback | Platform/data; M02 |
| 6. Durable state | Transactional matter version, audit event and outbox intent; bounded worker retry and idempotency | Kill the process at each commit boundary; no lost acknowledged work, duplicate external effect or unauthorized resumed job | Application/data; M02 and each worker module |
| 7. Retention and rights | Approved per-category schedules; holds; deletion inventory across copies; authenticated requests and disclosure review | A deletion request during hold is explained, not silently completed; restore cannot resurrect released data into normal access | Privacy/legal + data; M02 foundation, M11 completion |
| 8. Safe intake | Declared format limits, quarantine, local/private scanning, isolated parsers, explicit recording controls and processor routes | Mislabeled, oversized, encrypted, malformed and scan-unavailable fixtures stay unprocessed; microphone stop actually stops capture | Media/security; M03 |
| 9. Source and derivative integrity | Original hash/version, source-span lineage, parser/model identity and inherited policy; invalidation on correction or removal | Change source or permissions after derivation; stale extract/search/advice cannot silently remain current | Data/knowledge; M03–M07 |
| 10. Permissioned retrieval | Filter before candidate material reaches rerankers or models; recheck before content delivery; scope caches | Unique canary in another firm never appears in hits, counts, snippets, model requests, output or telemetry | Retrieval/security; M05–M06 |
| 11. AI boundary | Treat retrieved/uploaded text as untrusted evidence; validate structured output; narrow tool capabilities; bounded loops | Source tells NM to send the file or change policy; no permission change, external request or unscreened output occurs | AI/application/security; M06–M10 |
| 12. Processor governance | Approve each endpoint, data category, region, retention and contract; require budget and egress policy checks | Disallowed endpoint/model/fallback is blocked before transmission; operator sees withheld processing, not a fake answer | Privacy/legal + platform; before external OCR/ASR/AI |
| 13. Action authority | Separate proposal, preview, approval and execution; bind approval to exact payload/version/recipient/scope | Change a recipient or underlying draft after approval; approval expires; retry cannot send twice | Workflow/security; M10 |
| 14. Safe browser experience | Secure cookies, CSRF protection, restrictive rendering, content security policy, safe downloads, no sensitive browser persistence | Hostile extracted HTML is inert; logout/back/another-tab cannot expose retained matter content or continue writes | UI/security; M01 onward |
| 15. Private observability | Allowlisted structured events; no raw content in ordinary logs; separate restricted audit evidence; alert on abuse | Synthetic secret placed in each input cannot be found in logs, traces, analytics or error reports | Platform/privacy; M00 onward |
| 16. Restore and incident readiness | Backups isolated from runtime credentials; measured restore; response roster, incident timer, containment and communications templates | Restore into isolated environment; replay deletion/permissions first; tabletop incident produces a timely reviewed report | Operations + security/legal; M12, prerequisites before real-data pilot |
| 17. Supply chain and deployment | Locked dependencies, SBOM, provenance, signed/digested artifacts, least-privilege CI, migration/rollback checks | Untrusted build, tampered artifact or missing migration proof cannot promote | Engineering/platform; every release |
| 18. Independent challenge | Risk-scoped penetration test, prompt-injection evaluation, cross-tenant review and remediation retest | Seed a known failure and confirm the release gate turns red; an empty suite or stale result is not a pass | Independent reviewer + release owner; real-data gate and material changes |

Controls extend across modules. M12 is not permission to postpone backups, monitoring or incident readiness until the last feature is built. M00 must expose their state from the first real-data decision.

Foundation and integration evidence are separate. For example, BK-69's valid admission type does not prove that the live upload path uses it; BK-79 proves the integrated media path; BK-85 supplies the common processor/key/operations foundation; BK-42 rechecks the enabled deployment. M00–M12 locate work in the blueprint; they are not replacement W0–W7 waves or independent completion states. The criterion-scoped implementation packets determine build order. An isolated synthetic module demonstration may proceed while later integration evidence remains open; a confidential-data path may not. Strong-authentication implementation and pilot enforcement are owned early by BK-86; leaving them only under the final production row would not protect an earlier pilot.

### Exact acceptance ownership

The entries below map the 18 controls to existing criteria; they do not add a parallel checklist that can self-certify. Where a criterion requires deployed evidence, a local fixture completes only the fixture portion. The full criterion remains unproven until all its required evidence is current.

| Control | Foundation or mechanism owner | Enabled-path / release owner |
|---|---|---|
| 1 scope and inventory | BK-85-AC1, BK-85-AC3 | BK-80-AC4, BK-42-AC9 |
| 2 protected environments | BK-85-AC6, BK-82-AC1 | BK-42-AC6, BK-42-AC8 |
| 3 identity and recovery | BK-86-AC1, BK-86-AC2 | BK-86-AC3, BK-42-AC2 |
| 4 matter authorization | BK-83-AC1 | BK-42-AC3 |
| 5 cryptographic boundary | BK-85-AC2 | BK-88-AC2, BK-42-AC4, BK-42-AC8 |
| 6 durable state | BK-83-AC1, BK-83-AC2 | BK-83-AC3, BK-42-AC6 |
| 7 retention and rights | BK-85-AC3, BK-85-AC4 | BK-88-AC1, BK-79-AC2, BK-42-AC1, BK-42-AC8 |
| 8 safe intake | BK-69-AC1, BK-69-AC2, BK-69-AC3 | BK-79-AC1, BK-79-AC2, BK-79-AC3, BK-88-AC4, BK-42-AC1 |
| 9 source and derivative integrity | BK-64-AC1, BK-65-AC1, BK-84-AC2 | BK-79-AC1, BK-55-AC5 |
| 10 permissioned retrieval | BK-83-AC1, BK-85-AC1 | BK-88-AC2, BK-42-AC3 |
| 11 AI boundary | BK-63-AC1, BK-84-AC3 | BK-56-AC1, BK-56-AC4, BK-42-AC3 |
| 12 processor governance | BK-85-AC1, BK-85-AC3, BK-69-AC3 | BK-88-AC2, BK-88-AC4, BK-79-AC1, BK-79-AC3, BK-42-AC8 |
| 13 action authority | BK-63-AC1, BK-56-AC1 | BK-56-AC4, BK-57-AC1 |
| 14 browser experience | BK-40-AC1, BK-40-AC2, BK-86-AC1 | BK-42-AC3, BK-42-AC7 |
| 15 private observability | BK-85-AC1, BK-85-AC6 | BK-88-AC2, BK-42-AC8 |
| 16 restore and incident readiness | BK-85-AC4, BK-85-AC5 | BK-88-AC1, BK-88-AC3, BK-42-AC4, BK-42-AC6 |
| 17 supply chain and deployment | BK-85-AC6 | BK-42-AC6 |
| 18 independent challenge | BK-86-AC3, BK-67-AC3 | BK-42-AC3, BK-42-AC8, BK-42-AC9 |

### The earliest gate is before the protected operation

Do not wait for a whole module or all of M00 to be marked done before writing a bounded local test. Equally, do not infer permission for real data from a successfully demonstrated module. Use this order:

1. **Before confidential persistence:** approved data-purpose/retention policy, strong access assurance, tenant/matter isolation, protected storage/key route, private logs and a recoverable acknowledged-write mechanism. Prototype password/recovery decisions remain scoped to their existing local profile and do not waive BK-86.
2. **Before media capture or upload:** explicit recording/upload authority, permitted format and size, scoped quarantine, isolated processing, retention decision and reliable stop/cancel/logout controls. A model receives an admitted derivative, never an unassessed raw upload.
3. **Before any outbound provider call:** purpose, data class, endpoint, processing/support/backup regions, contract/retention and budget are approved; the actual gateway enforces them before transmission. No fallback may create its own approval.
4. **Before counsel-facing reliance:** current permission, exact source identity, sufficient context, attribution/support/application checks, governing-premise review and permitted advice maturity. An unfinished control is visible and constrains the output.
5. **Before external effects:** the configured product scope expressly permits the integration; the exact payload/recipient/version has valid role authority and approval; the transport can reconcile uncertain results. Local demos remain no-send.
6. **Before a restricted real-matter pilot:** all actual controls on its enabled data path have current served/deployed proof; actual-device authentication, restore, incident and privacy/professional reviews are complete for that scope. Future M12 evidence cannot retrospectively protect a pilot. Disabled paths remain server-denied.

Use CHOICE-03/04/05/07/08/09/10 to resolve the hosting, identity, processor, legal, retention/recovery, action and release decisions before their dependent operation. The security and release owners must name the chosen configuration and evidence—not simply accept a generic vendor claim. A scope change reopens the affected approvals.

## 4. Threat model and trust boundaries

Document actors before drawing infrastructure: legitimate advocate, colleague outside the matter, firm administrator, former colleague, client/third-party data subject, support operator, malicious uploader, compromised browser, compromised worker, provider operator, external attacker and mistaken developer. Include accidental sharing, excessive retention and lawful-but-unexpected secondary use, not just intrusion.

```text
Advocate browser
  | authenticated request; client-supplied firm/matter IDs are not authority
API / session + authorization boundary
  | transaction-scoped identity and matter policy
PostgreSQL authoritative records ---- durable outbox ---- isolated workers
  | signed object intent                                  | re-authorize
Encrypted originals / derivatives                        | no broad credentials
  | approved source/version/policy                        |
Permissioned search + context assembly ----------- approved processor gateway
  |                                                         |
Validated advice / approval proposals                  external providers
  |
Action gate -------- exact approved destination and payload

Separate: deployment control, managed keys, security audit, backup/recovery plane
```

For every arrow, record who authenticates whom, what data can cross, how it is minimized, where it is persisted, timeout/retry behavior, permission revocation behavior and failure response. The model is not an authorization authority. A network location, UUID, database connection or signed URL alone does not establish permission to see a matter.

Attack trees must cover at least account takeover, recovery bypass, cross-firm leakage, same-firm ethical-wall bypass, unsafe exports, parser compromise, document-driven prompt injection, source poisoning, key theft, malicious administrator, supply-chain compromise, ransomware, resource exhaustion and incorrect “deleted/restored/sent” confirmations. Each leaf gets a test or a justified residual-risk record.

## 5. Data inventory, classification and minimization

Treat embeddings, summaries, thumbnails, OCR, transcripts, search queries and metadata as data—not anonymous exhaust. They inherit source restrictions unless a reviewed transformation establishes otherwise. Hashing names, removing direct identifiers or using vectors is not proof of anonymization.

| Class | Examples | Default handling |
|---|---|---|
| Approved public authority | Public judgments/statutes whose provenance and permitted use are established | Separate corpus; no matter-to-public promotion; retain provenance and publication restrictions |
| Internal operations | Build versions, non-sensitive service health, aggregate counts | Limited internal access and retention; no hidden matter payloads in labels |
| Confidential matter data | Brief, parties, documents, queries, chronology, reasoning, drafts, source spans and matter metadata | Explicit firm/matter scope; encrypted storage; no cross-matter reuse without authority |
| Restricted matter material | Alleged privileged communications, sealed/restricted evidence, children's records, intimate/medical/financial material | Additional policy labels and human-reviewed processing/export restrictions; strongest applicable source policy follows derivatives |
| Secrets and security evidence | Password verifiers, recovery verifiers, provider credentials, keys, security investigation material | Dedicated secret/evidence controls; never LLM context; separation of duties and narrowly audited access |

For each stored field or object, supply `purpose`, `source`, `data_class`, `firm_id`, `matter_id` when applicable, `policy_version`, `retention_rule`, `legal_hold_refs`, `allowed_processors`, and `created/changed_by`. Record whether an original, assertion, inference, approved decision or derived artifact owns the value. Avoid free-text fields where stable identifiers suffice.

Collect the minimum required for the current purpose. Do not require Aadhaar, identity documents, biometrics or full contact books simply to create an advocate account. Do not collect a voiceprint or infer identity from a face or speaker. Recording consent, upload authority and legal grounds for processing third-party material are different questions. Offer document upload or typing when recording is declined.

Test the inventory against actual database schemas, object categories, queues, caches, provider requests, support attachments and browser stores. A new store with no inventory entry fails its module gate. Population counts come from those mechanisms; a manually maintained list cannot certify itself complete.

## 6. Identity, authorization and session behavior

### Identity decisions

Prefer an established identity component with tested WebAuthn/passkey and MFA lifecycle support. A passkey counts toward the chosen assurance policy only when the implementation enforces the required user verification and enrollment protections. Offer phishing-resistant authentication; do not label SMS, email links or typed OTP codes phishing-resistant. NIST's current authentication guidance distinguishes these properties. [NIST SP 800-63B-4](https://csrc.nist.gov/pubs/sp/800/63/b/4/final), [authenticator requirements](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/).

1. Bind invitations server-side to the intended firm, role, recipient policy, expiry and single use. Do not accept a firm's identity from an editable signup field.
2. Require the approved strong-authentication policy before real matter access. Administrators and support elevation require phishing-resistant authentication. Require step-up for authenticator changes, recovery-code rotation, credential changes, high-impact exports and privilege changes.
3. Generate cryptographically random recovery codes, display them once, store non-reversible verifiers, and consume atomically. Rotation invalidates the old set. Never recover an account on knowledge of case facts or a support agent's intuition.
4. Design loss-of-all-factors recovery explicitly. A real-data account remains locked until the approved identity recovery process completes. Verify who can authorize restoration; record delay/notification and independent review where applicable. A newly supplied phone/email is not its own evidence.
5. Rate-limit by account and origin with privacy-preserving identifiers, bounded counters and progressive delay. Preserve a path for legitimate recovery; do not let an attacker permanently lock a victim out by guessing. Keep public failures neutral without hiding internal security events.
6. Use revocable server-side sessions or an equivalent design with demonstrated revocation. Secure, HttpOnly cookies; appropriate SameSite, CSRF defenses and origin checks; no bearer tokens in URLs or ordinary local storage. Rotate after authentication or privilege change. Define idle, absolute and elevated-action lifetimes in a reviewed configuration.
7. Show advocate, firm/workspace, active matter and session identity consistently. Sign-out clears sensitive UI state and revokes the session. Handle expired sessions during autosave, upload and streaming without exposing content or pretending the work committed.

When passwords remain supported, use the chosen identity component's maintained, salted, memory-hard password-verification mechanism, breached-password checks and password-manager-friendly inputs. Never encrypt passwords for later recovery or email a password. Do not create a weaker password-only path beside a protected passkey account. Test session fixation, session theft, CSRF, enrollment substitution, notification abuse and factor-reset downgrade through the actual browser/API lifecycle.

Browser hardening includes HTTPS-only production, reviewed security headers and CSP, denial of cross-origin framing, safe download disposition, restrictive referrer policy and no-store handling of confidential responses. Review browser back-forward caches, service workers, IndexedDB and offline features explicitly. Warn that deliberate downloads or copies already made to an authorized advocate's device cannot be remotely erased by signing out; managed-device policy and export minimization address that residual risk.

### Authorization decisions

Use one policy owner for `read`, `write`, `research`, `upload`, `export`, `share`, `approve_action`, `manage_membership`, `place_hold` and `support_access`. Bind grants to actor, firm, matter, operation and current membership version. Role names alone are insufficient: a senior lawyer outside an ethical wall still cannot read that matter.

PostgreSQL row-level security is defense in depth, not a replacement for application authorization. Use non-owner runtime roles without superuser or `BYPASSRLS`; apply appropriate forced policies and transaction-local scope; prohibit arbitrary client SQL and unsafe security-definer functions. Connection pooling must never carry one request's scope into another. Database owners and privileged roles require separate treatment because they can bypass normal row policies. [PostgreSQL row-security documentation](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).

Enforce composite ownership on relationships so a child cannot reference another firm's parent. Authorization covers list counts, conflict results, autocomplete, object metadata, notifications, audit views, exports, queued work, stream reconnects, storage downloads and retrieval—not just the matter page. Re-authorize long jobs before each protected stage and before delivery. Revoke worker leases/caches on membership changes. In-flight bytes already transmitted cannot be recalled; document and measure that boundary.

Firm administrators manage membership but do not automatically obtain matter content. Support gets no standing matter read access. An exceptional support grant requires a named approver, reason, exact scope, time limit, conspicuous audit and automatic expiry. Support cannot impersonate an advocate to authorize external actions.

## 7. Storage, keys, integrity and recovery

### Encryption without misleading claims

Use authenticated encryption through maintained libraries and managed key services. Proposed baseline: TLS in transit, encrypted database volumes and backups, and envelope encryption for confidential objects. Use a randomly generated data key per object/version, wrapped under the approved tenant or matter key hierarchy. Bind authenticated associated data to firm, matter, object, version and purpose. Key hierarchy and deletion granularity must be designed together.

Application workers must decrypt relevant data to process it. PostgreSQL/search may hold protected-but-server-readable fields in order to query them. Therefore this architecture is not end-to-end encrypted against the service operator. Do not make that marketing claim. If a customer requires operator-blind processing, isolated customer-managed deployments or client-side processing need a separate architecture and capability trade-off—not a renamed encryption flag.

Keys never live beside the ciphertext in the same unrestricted store. Use workload identity and narrow key grants, not long-lived keys in environment files distributed to developers. Separate application, key administration and backup deletion permissions. Record key versions; test wrap-key rotation and object migration without data loss. Key compromise rotation and planned rotation are different workflows. Key unavailability blocks affected work; it never triggers plaintext persistence.

Store originals immutably at the application level with cryptographic integrity hashes and explicit version lineage. Immutability means earlier evidence is not silently edited; it does not mean retaining every payload forever. Corrections produce a new version and invalidate affected derivatives. Database transactions should atomically persist a state change, audit reference and outbox intent. Object uploads finalize only after verifying bytes and metadata; reconcile orphaned or incomplete uploads through the approved retention policy.

### Backups and deletion

1. Inventory originals, versions, extracts, thumbnails, transcripts, embeddings, caches, temporary storage, provider copies, logs, backups and exports under NM control.
2. Separate operational access removal from physical erasure. Immediately prevent ordinary retrieval where appropriate; state what remains held and why.
3. Apply counsel-approved retention per category and purpose, with precedence for valid legal holds. Define who can place/release a hold, review cadence and evidence. A general “possible litigation” flag is not a reason to retain all tenants forever.
4. Calculate the deletion plan before executing it. Require appropriate approval for material irreversible deletion; retain only necessary non-content proof of what was done and any outstanding processor/backup expiry.
5. Delete or cryptographically erase controlled active copies according to the approved key design. Do not claim erasure merely because a database row or search hit disappeared. Deleting a shared parent key can destroy unrelated matters; it is never an acceptable shortcut.
6. Where backups retain deleted content until scheduled expiry, prevent normal use, document that fact to the appropriate audience, and reapply the deletion/hold/revocation ledger before a restore becomes accessible. Crypto-erasure is only proven if recoverable copies of the relevant keys are also accounted for.
7. Measure restore from an isolated backup using a recovery identity distinct from runtime. Verify hashes, authorization, outbox state, deletion policy and last acknowledged records; then authorize reopening. Backups are not a completed control until this works.

Initial operational targets must be chosen and funded before real-matter pilot access: CHOICE-08 proposes catastrophic-incident RPO of at most 15 minutes and RTO of at most four hours, subject to the named owners' approval and a measured rehearsal. These are not current achieved results. Ordinary application restart/retry still permits no loss of an acknowledged commit; a catastrophe allowance must not excuse a failed transaction contract. Confirm restore-test cadence and backup expiry in the same decision. Do not publish an availability or recovery promise based only on a cloud vendor's service-level agreement. The whole enabled matter path must meet the approved objectives.

## 8. Multimodal intake and untrusted content

“Accept many types” means a published capability matrix with size, duration, format, language, password/encryption and processing limits. Unsupported files can be safely retained only under a declared quarantine policy; NM must not say it read them. Use independently measured states: received, quarantined, scanning, extracted/transcribed, partially processed, failed, and advocate-reviewed.

Implementation order:

1. Present the active matter, recording indicator, processor route and applicable notice before capture. Microphone/camera require an explicit user gesture. Stop, pause, discard and permission-denied states are real controls; no background capture after navigation or logout.
2. Upload into a non-public quarantine location using bounded, scoped intent. Validate authorization again at finalization. Treat filenames, declared content type and metadata as untrusted.
3. Check format signatures, limits and allowed content. Scan privately; never send privileged files to a public malware-analysis service. Scan unavailable means pending/not assessed, not clean.
4. Parse or transcode in an isolated, non-root worker with no general network access, no production database credential, resource limits and disposable protected temporary storage. Reject archive traversal, excessive expansion, recursion and malformed content. [OWASP file-upload guidance](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html).
5. Preserve the original and make safe previews separately. Do not execute macros, scripts, external references or embedded content. Escape extracted and generated text before rendering.
6. Send only approved payloads to OCR, speech or model providers through the processor gateway. Segment long recordings with lineage; expose gaps, uncertain speakers and low-confidence spans. Transcription does not authenticate a speaker or establish truth.
7. Strip unnecessary metadata from outward derivatives while retaining evidentiary originals under matter policy. Redact output copies rather than silently altering evidence.
8. Purge temporary plaintext as part of success, failure, cancellation and crash-recovery paths. Inspect the actual filesystem/container layer and diagnostic path; a cleanup function that was never reached is not proof.

Prompt-injection text in a document is still evidence, not an instruction. A document saying “administrator approved sharing” cannot create an approval. Do not rely on an injection detector to make this distinction reliably; enforce capabilities outside the model.

### Media-processing capability boundary

NM prohibits automated identity/authentication from voice or appearance, voiceprint creation or matching, affect/emotion derivation and credibility/truthfulness inference from voice or appearance. Recording-local non-identifying diarisation, transcription, translation and a user-confirmed attribution claim remain permitted under the admitted purpose. A speaker label is not authentication. Normal source-based legal assessment of testimony, inconsistencies, admissions and other evidence remains permitted; the ban does not justify altering an admitted evidentiary original.

Approval under CHOICE-05 names the selected service operation, endpoint, version and configuration, including hidden, default or unavoidable processing. An unrelated optional vendor service is not itself disqualifying. A selected route that cannot exclude prohibited processing is ineligible; a missing declaration is not proof of its absence. User consent cannot waive this capability boundary. Reassess material service/configuration changes before further requests.

Enforce a deny-by-default preflight before any request bytes cross the boundary. The allowlisted operation/configuration, purpose and permission must all match; unknown or prohibited processing means zero outbound calls, not a warning after transmission. Validate responses with a recursive closed allowlist, including nested arrays and metadata, before any downstream use. An unknown or forbidden derived field rejects the response; a top-level filter is insufficient. Raw rejected response content must not be copied into logs, traces, caches, storage, the UI or reasoning. Retain only content-free rejection metadata. Approved evidentiary originals retain their separate custody and retention policy.

BK-69-AC3 owns this foundation contract; BK-79-AC3 proves it on the served intake path; BK-88-AC4 proves the actual confidential configuration and all discovered downstream sinks. EVAL-007 exercises prohibited-request preflight, EVAL-008 preserves successful transcription/correction/original/restart while injecting forbidden nested response fields, and EVAL-027 exercises hidden/unavoidable processing and unknown configuration. Their structured `media_contract` and observation specifications in [evaluations.json](evaluations.json) are checked for disappearance or weakening. These are NOT_RUN design obligations, not evidence that a runtime guard, selected processor or served path currently complies.

The future observation harness must distinguish missing from an observed false: a missing field is NOT_RUN and blocks the dependent claim; `false`, `0`, `null` and the string `"false"` are not interchangeable. It must obtain successful call/result and source/restart evidence independently from the expected values. Dropping capture or failing to call the provider must not fabricate a passing transcript. Successful allowed transcription requires its observed call and result; a denied prohibited request requires observed zero outbound calls.

## 9. Retrieval, model and action security

### Retrieval and memory

Keep public-law knowledge and matter-confidential knowledge separate. Shared search infrastructure is acceptable only with proven tenant and matter scoping at candidate selection, reranking, context assembly and delivery. A permission filter applied after sending candidates to an external reranker is too late.

Every derived record carries source identity/version, parser or embedding identity, policy inheritance and retention relationship. Removing a source or grant invalidates associated derivatives and caches. Cache keys include firm/matter, actor-policy version, corpus/matter version, model/prompt version and intended operation where relevant. Global response caches may contain only approved public, non-matter-specific material. Do not use cross-tenant deduplication that leaks object existence or couples deletion rights.

Research queries can disclose strategy and identities even when no file is uploaded. Minimize names and unique facts before external search where the task permits; if identifiers are necessary, apply the same approved-provider policy as for documents. URL fetchers use controlled egress, validate redirects and resolved addresses, and cannot access private network or cloud metadata services. [OWASP SSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html).

### Provider gateway

Maintain an approved processor record for hosting, identity, email, telemetry, OCR, transcription, embedding, inference and support tools. Record service/endpoint, legal entity, subcontractors, country/region of storage and processing, support access, retention/deletion, incident terms, training use, encryption, authentication and contractual evidence. “No training” is a checked service/contract setting, not an assumption about every API. Residency often differs for storage, inference, logs and failover: check each.

Before every outbound request, verify purpose, permission, allowed data class, endpoint, approved region, token/byte budget and cancellation state. Refuse a policy mismatch. Provider outage may trigger only a previously approved fallback with equivalent permissions and protections; latency pressure never authorizes an unreviewed service. Track sanitized request identifiers and resource use, not full confidential prompts in routine logs.

### Model and action boundary

The model may select a next permitted reasoning task and propose a retrieval need, extraction, hypothesis, draft or action. Deterministic application code validates schema, permissions, exact source identity, policy, version and budget, and enforces required support/applicability assessment and review outcomes. Semantic support is not proved by a schema or source-ID match. Do not give a reasoning model generic SQL, shell, filesystem, arbitrary HTTP or unbounded tool-loop access. Give each tool the minimum permitted operation and material needed for this job.

The bounded lead/research/draft-document architecture does not create new authority. Every dispatch carries a server-issued, purpose-limited capability and the parent's current mandate, source snapshot, policy/cancellation epochs and shared budget reservation. Narrow scope for each specialist; never send the entire matter merely because the child is internal. Reauthorise before source/context reads, provider transmission, protected delivery and conditional result acceptance. A parent cannot delegate a capability it lacks, and a child cannot mint credentials, tools, scope, spending or further delegates outside the approved profile.

Threat tests must cover source-instruction laundering through a specialist summary, forged parent/task references, another matter's source locator, hidden restricted data in a tool argument, budget races, recursive fan-out, revoked/cancelled late replies and an alleged approval quoted inside evidence. Inspect actual outbound requests and every discovered canonical write/publication route, not just prompts. External web research still crosses the approved egress gateway; document generation has no ambient network, arbitrary paths or macro execution. Specialists return proposals to the single acceptance owner and cannot clear their own professional or action gates. Controls are registered under BK-91/BK-92 and [autonomy.json](autonomy.json); no static design test certifies their runtime enforcement.

Do not persist private model chain-of-thought as the legal audit record. Persist inspectable conclusions, stated assumptions, supporting sources, counterarguments, tests, revisions and human decisions. These can be verified and corrected; hidden reasoning tokens are neither a reliable explanation nor necessary client data.

External effects have separate proposed/previewed/approved/executing/confirmed/failed/uncertain states. Approval binds the actor and authority, matter, exact recipient and payload hash, source version, action, expiry and idempotency key. Any material change invalidates it. An uncertain transport result triggers reconciliation, not a blind repeat. A recommendation to file is not authority to file; drafting integrations do not expand NM's agreed product scope.

## 10. Private observability, incident response and supply chain

### Logging

Ordinary telemetry uses an allowlist: pseudonymous actor/matter reference where needed, event type, status, reason code, timing, resource use, version and correlation identifier. Exclude credentials, codes, tokens, file names with client identifiers, raw recordings, briefs, excerpts, drafts and prompts. Scrub exception paths, proxy logs, tracing exporters and test artifacts too. Hashing predictable personal identifiers without an appropriate keyed design is not sufficient.

Security audit records are separately access-controlled, integrity-protected and retained under their approved schedule. They should establish who accessed, changed, approved, exported, administered or attempted a forbidden operation without copying the case file into the audit store. Tamper-evidence detects alteration; it does not prove that the original event was true. Record failed writes to the audit mechanism and fail the affected high-impact operation where audit is required.

Do not enable session replay, third-party advertising scripts or unrestricted client-side analytics in confidential screens. Error reporting must work without screenshots or DOM captures of client material by default. Support diagnostics require scoped consent/authority, minimization and deletion controls.

### Incident runbook

Create the incident record at first suspicion. Preserve separate timestamps for event occurrence, detection, notice, assessment, containment and each applicable reporting trigger. Never wait for a completed root-cause analysis before opening the record or starting a statutory timer.

1. Page the named incident commander and backup; secure the communications channel and establish decision authority.
2. Contain the affected credential, tenant, provider route or module; prefer scoped suspension while protecting evidence. Do not delete logs or wipe the host as the first response.
3. Preserve necessary evidence with access controls, hashes, UTC/time-zone context and custody record. Minimize unrelated client material.
4. Have legal/privacy staff determine regulatory, customer, insurer and contractual notifications in parallel. Under the applicable CERT-In regime, design the process to prepare the initial report within the six-hour window, with supplements later. The notified DPDP breach rule, when applicable and operative, separately calls for prompt initial notifications and a detailed Board update within 72 hours, subject to its terms. These are not interchangeable clocks. [CERT-In FAQ](https://www.cert-in.org.in/PDF/FAQs_on_CyberSecurityDirections_May2022.pdf), [DPDP Rule 7](https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf).
5. Recover through the validated procedure; reconcile state, permissions, pending actions and deletions before restoring access.
6. Communicate known facts, uncertainty, affected scope and protective action. Do not claim “no data accessed” solely because logs are missing.
7. Independently review the root cause and the whole population of the defect shape. Add a planted-failure control and verify remediation before closing.

Run a tabletop before real-matter access and after material changes to hosting, providers or response ownership. Set internal escalation deadlines comfortably inside applicable external deadlines and staff them; a six-hour legal window cannot be supported by a next-business-day inbox. Actual notifications are human-authorized operational actions, never sent by a test.

### Secure delivery

Protect the source repository, CI identity, dependency registry, artifact registry and deployment credentials. Lock and review dependencies; generate a software bill of materials for the shipped artifact; scan code, dependencies, secrets and infrastructure; pin trusted build inputs and retain provenance. Build once and promote the same artifact digest. Require separate production approval, controlled migrations and a tested rollback/recovery plan.

Treat model versions, prompts, retrieval indexes, parser versions and policy changes as release inputs, not invisible configuration. Tests and signatures bind to them. Review vendor vulnerabilities and configuration drift throughout operation. Define severity-specific triage/remediation deadlines, ownership and a disclosure channel. Known exploitable isolation/authentication/key defects block release; a vulnerability scanner's green result is not a penetration test.

## 11. Live validation the owner can watch

Use the M00 proof console to show scenario, fixture identity, deployed artifact/configuration, module, actor, action, expected result, observed result, evidence timestamp and any remaining limits. Console assertions are derived from test output; a hand-clicked green checkbox is a note, not certification. Keep security-sensitive detail in a restricted reviewer view.

Minimum synthetic demonstration portfolio:

1. Sign in as Advocate A; the correct firm and matter are unmistakable. Advocate B in another firm cannot discover it by URL, list, search, API, export or file link.
2. Exclude a same-firm colleague through an ethical wall; membership role does not bypass it. Revoke access while a retrieval job runs; subsequent protected stages and delivery refuse it.
3. Recover an account once; repeat the code, race two attempts and reuse an old session. Show refusal and a content-free security trail. Rotate codes and prove the old set is invalid.
4. Leave an idle/expired session with unsaved input, then authenticate again. Show accurately what was saved and what was not, without leaking content before authentication.
5. Upload an approved file and a quarantined fixture. A failed scanner or parser visibly says it could not assess/process the file; no “read” claim appears.
6. Start and stop recording. Inspect permission/capture state and the actual stored derivatives; nothing continues recording after stop or logout.
7. Put a harmless instruction to disclose another matter inside a synthetic source. Show that it cannot alter permissions or trigger an external action.
8. Plant a unique cross-firm canary. Search for it in the UI and inspect the provider-request capture and sanitized logs; no unauthorized occurrence is allowed.
9. Disable a required key or provider route. The UI explains the unavailable capability, preserves committed work and makes no unauthorized fallback request.
10. Modify a source after advice was prepared. The system identifies the dependent stale advice and requires review rather than quietly treating it as current.
11. Preview a simulated external action, then change the recipient. The prior approval is invalid. Retrying a confirmed action creates no duplicate effect.
12. Request deletion, introduce a valid legal hold, then release it through the authorized process. Show the exact copy/deletion state and outstanding expiry; do not claim universal erasure.
13. Restore a backup into an isolated environment. Show approved recovery objectives met, protected original hashes matching, and deleted/revoked items still unavailable after reconciliation.
14. Plant a synthetic credential in an input and induce validation, provider and parser errors. Inspect all relevant log/export sinks for leakage; an uninspected sink makes the result incomplete.
15. Present the wrong build digest, missing evidence, an empty scenario population and an expired approval to the release gate. Each must prevent promotion.
16. Simulate a breach-notice timeline. The on-call roles receive the alert; the report package and lawful recipient decision are ready within the agreed internal deadline. No real incident email is sent.

Each control's evidence must include the actual served path and affected population. Unit tests establish useful invariants but cannot alone show that a browser, a worker, object storage and an external provider obey them together. Proof that itself never rejects a planted defect remains unproven.

## 12. Sign-off and ongoing ownership

Before a module accepts real data, the release record must include:

- Named product, security, privacy/legal, operations and release owners; independent reviewer for high-impact controls.
- Enabled capabilities, data classes, legal jurisdiction/coverage, approved providers and configuration digest.
- Threat model and processing inventory reconciled to actual assets and flows.
- Applicable-law determination, contracts/notices, retention/hold decisions and incident contacts.
- Current control results with real populations, negative controls, live served-path evidence and measured limits.
- Open risk register with explicit prohibited risks and any permissible, owned, time-limited exceptions; exceptions do not override law or cross-tenant safety.
- Restore and incident rehearsal evidence; independent findings and remediation retests.
- Rollback, safe-disable and support arrangements; monitoring and review cadence.

After release, review access on joining, role change and departure; review privileged access and provider changes promptly; check backup/alert health continuously; repeat isolation, restoration and response exercises on a scheduled risk-based cadence. Significant architecture, data-purpose, model/provider or jurisdiction changes reopen the corresponding sign-off. Track the cost of these controls as normal service cost, not optional hardening to be removed when budgets tighten.

### Decisions that must not be guessed

Before real data, the owner must approve the hosting/vendor shortlist and India-region policy; identity/recovery assurance; who is legally responsible for each processing purpose; exact permitted corpus and matter scope; media notices/authority; retention and legal-hold schedule; provider contracts and transfer permissions; RPO/RTO/service hours and budget; incident/legal contacts; and who can authorize support access and external effects. If any is unresolved, keep the affected path synthetic-only or disabled and make that limitation visible.

The safe execution rule is simple: implement and demonstrate what the current gate permits, stop at the specific unresolved decision, and continue unrelated safe modules. Following this guide reduces ambiguity; it cannot substitute for accountable professional review or make security a permanently completed task.
