/**
 * APPENDIX E — the typed contracts, in full.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * An external review found nine PRODUCES clauses that could not hold what
 * their own DOES clause required. `WitnessPlan` was prose. `DrafterBrief` was
 * a pointer to a sentence. `ClosureRecord` had no fields at all. `CaseSummary`
 * was never defined anywhere, and TWO features derive from it.
 *
 * That is not a documentation gap. PRODUCES is the state a slice leaves for the
 * next one, so a field that is absent here is a field the next slice cannot
 * read — and the obligation it carried is dropped silently, which is exactly
 * what P6 says a contract exists to prevent.
 *
 * THE RULE THIS FILE IS HELD TO
 * ------------------------------
 * Every field carries WHY IT IS THERE, and the why must name the thing that
 * goes wrong without it. A field list without reasons is a shape, and shapes
 * are what the previous build's twelve mechanical checks measured while the
 * product asked a client who had said "yesterday" for the date twice.
 *
 * Three-state vocabularies appear throughout and are not stylistic. Every one
 * of them is a place where "could not be assessed" would otherwise be
 * indistinguishable from "assessed and fine".
 */
const H = require('./helpers');

// name, owner-feature, one-line purpose, [field, type, required, why]
const SCHEMAS = [

  ['Fact', 'C1',
   'A single proposition from the account, with everything needed to walk it back.',
   [
     ['id', 'FactId', true, 'Stable across corrections. A fact whose id changes cannot be superseded, only duplicated.'],
     ['statement', 'string', true, 'What was said, in the account\'s own terms.'],
     ['exact_words', 'string|null', false, '**The quotation, if one was recorded.** C1 forbids recording a paraphrase as a quotation, and that rule is unenforceable unless the claimed exact words are a separate field that can be checked back against the account.'],
     ['basis', 'enum {direct_knowledge, document, hearsay, inference, belief}', true, 'C1 requires the basis of every material proposition to be labelled. Without the field the labelling is a habit, and habits do not survive a busy turn.'],
     ['basis_source', 'string|null', true, 'Where the basis points — the document, the person, the inference\'s inputs. C1 forbids a source that points nowhere; `null` is permitted only where basis is `direct_knowledge` or `belief`.'],
     ['date', 'date|null', true, '`null` means UNDATED. It is never an estimate, and never today.'],
     ['certainty', 'enum {documented, asserted}', true, 'An assertion and a document are different evidential positions and must not merge on the board.'],
     ['provenance', 'Provenance', true, 'Non-optional by construction. An advocate who cannot audit the chain has to take the answer on trust.'],
     ['material', 'bool', true, 'Materiality drives what is confirmed and what is pleaded.'],
     ['weight', 'enum {favourable, unfavourable, neutral, not_assessed}', true, '**C1 requires unfavourable facts to be explored as hard as favourable ones.** With no field, nothing can check that they were — and the adverse-fact accounting in D6 has nothing to compare against.'],
     ['confirmed', 'bool|null', true, '`null` is NOT ASSESSED. Two states would make an unconfirmed fact look like a rejected one.'],
     ['confirmed_at', 'datetime|null', false, 'C1 requires summarising back and inviting correction. The time of confirmation is what makes a later contradiction datable.'],
     ['conflicts_with', 'FactId[]', true, 'A contradiction is CARRIED, never resolved silently. Both facts stay.'],
     ['superseded_by', 'FactId|null', true, 'A correction supersedes; it does not overwrite. The original stays readable.'],
   ]],

  ['Engagement', 'B5',
   'Who the client is, who may instruct, what is in scope, and whether advice is reliance-ready.',
   [
     ['client', 'PartyRef', true, 'The person or entity to whom the duty is owed.'],
     ['client_kind', 'enum {individual, company, firm, trust, society, government}', true, 'Authority to instruct is established differently for each.'],
     ['intermediary', 'PartyRef|null', true, '**B5 forbids treating an intermediary as the client.** A single `client` field with nowhere to put the intermediary is how the substitution happens.'],
     ['payer', 'PartyRef|null', true, 'The payer is not the client. Same reasoning, and it recurs most often in family and insurance matters.'],
     ['decision_maker', 'PartyRef', true, 'Who decides, as distinct from who instructs and who pays.'],
     ['may_instruct', 'PartyRef[]', true, 'The closed set. An instruction from outside it is not an instruction.'],
     ['scope', 'string[]', true, 'What the engagement covers.'],
     ['exclusions', 'string[]', true, 'What it expressly does not.'],
     ['scope_exceptions', '{step, accepted_by, at}[]', true, '**B5 permits out-of-scope work that is EXPRESSLY ACCEPTED.** With no field for the acceptance, the only representable outcomes are "in scope" and "blocked", and the acceptance happens off the record.'],
     ['confidentiality', 'string', true, 'Recorded terms, not assumed ones.'],
     ['communications', 'string', true, 'How and with whom NM and the advocate may communicate.'],
     ['fees', 'string', true, 'B5 requires fees to be recorded. Absent, every proportionality assessment in E3 is unanchored.'],
     ['disbursements', 'string', true, 'Likely disbursements, separately — they are the ones that surprise clients.'],
     ['custody', 'string', true, 'Document custody. H2 cannot close a matter without it.'],
     ['termination', 'string', true, 'Termination rights, both ways.'],
     ['complaints_route', 'string', true, 'Required by B5 and never derivable later.'],
     ['reliance', 'enum {ready, not_ready, not_assessed}', true, '**THREE states, not a bool.** `reliance_ready: false` cannot distinguish "we checked and it is not" from "nobody looked", and B5 forbids marking advice reliance-ready while identity, authority, scope or decision ownership is unrecorded.'],
     ['reliance_blockers', 'string[]', true, 'What specifically blocks reliance. A bare `not_ready` is a refusal with no route out.'],
     ['authorities', 'DecisionRecordId[]', true, 'The standing authorities given under this engagement, so G3 can invalidate them on a change of decision-maker.'],
   ]],

  ['EvidenceItem', 'C7',
   'One item of evidence, with existence, admissibility and weight kept apart.',
   [
     ['what', 'string', true, 'The item.'],
     ['fact', 'FactId[]', true, 'What it is capable of proving. An item proving nothing on the file is not evidence, it is paper.'],
     ['holder', 'enum {client, opponent, third_party, court, unknown}', true, 'Who has it decides how it is obtained and how long that takes.'],
     ['form', 'enum {original, certified_copy, photocopy, electronic, oral}', true, '**A photocopy is not the document.** One `form` string that does not distinguish them makes the s.65 secondary-evidence position invisible.'],
     ['existence', 'enum {held, obtainable, absent, not_assessed}', true, 'C7 requires existence, admissibility and weight to be THREE questions. This is the first.'],
     ['admissibility', 'enum {admissible_as_held, needs, inadmissible, not_assessed}', true, 'The second. **Having a thing is not being able to prove it** — a WhatsApp exchange exists; whether it goes in depends on the electronic-records certificate.'],
     ['admissibility_needs', 'string[]', true, 'What would make it admissible. `needs` with nothing named is a dead end.'],
     ['weight', 'enum {strong, moderate, weak, not_assessed}', true, '**The third, and it was missing entirely from the original contract.** Admissible and persuasive are different questions, and an advocate plans differently for each.'],
     ['weight_reason', 'string|null', true, 'Weight without a reason cannot be argued or challenged.'],
     ['authenticity', 'enum {established, disputed, not_assessed}', true, 'C7 requires authenticity to be inventoried. Disputed authenticity changes the proof sequence.'],
     ['completeness', 'enum {complete, partial, not_assessed}', true, 'A partial document read as whole is how a clause that kills the case stays unread.'],
     ['metadata', 'string|null', true, 'For electronic material, the metadata position is often the whole admissibility question.'],
     ['custody', '{holder, from, to}[]', true, 'The chain. A break is an attack the opponent will make and we should make first.'],
     ['preservation', '{owner, due, issued_at|null}', true, 'C7 requires a preservation instruction WITH A NAMED OWNER AND A DATE. An instruction with neither is a wish.'],
     ['lawful_source', 'bool', true, 'C7 forbids obtaining material unlawfully or suggesting a route that would. Without the field, nothing records that the question was asked.'],
   ]],

  ['DecisionRecord', 'E4',
   'A client decision, and the explanation it rests on.',
   [
     ['decided_by', 'PartyRef', true, 'The client decides; the advocate recommends. E4 turns on keeping those apart.'],
     ['capacity', 'CapacityPosition', true, 'B6. Any decision that becomes authority carries a capacity position.'],
     ['options_explained', 'string[]', true, 'The material alternatives, as put.'],
     ['risks_explained', 'string[]', true, 'The risks, as put.'],
     ['uncertainty_explained', 'string', true, '**E4 requires uncertainty to be explained and the original contract had nowhere to record it.** An option list with the uncertainty stripped out reads as a menu of certainties.'],
     ['consequences_explained', 'string', true, 'Likewise consequences.'],
     ['cost_explained', 'string', true, 'Likewise cost.'],
     ['irreversibility_explained', 'string', true, 'Likewise irreversibility — the one a client most often has not considered.'],
     ['plain_language_confirmed', 'bool', true, 'E4 requires understanding to be CHECKED, not assumed from delivery.'],
     ['instruction', 'string', true, 'What was actually instructed.'],
     ['scope', '{matter, threads[], steps[]}', true, '**E4 forbids an authority for one matter authorising a step on another.** A scope without thread and step granularity cannot refuse that.'],
     ['effective_from', 'datetime', true, '**E4 forbids a future-dated authority authorising immediately.** With no effective date the rule is unrepresentable, let alone enforceable.'],
     ['expires_at', 'datetime|null', true, 'A standing authority with no end is a standing risk.'],
     ['voluntariness', 'enum {free, pressured, not_assessed}', true, '**E4: a decision recorded under coercion is not authority.** Two states would force every unexamined decision into `free`.'],
     ['confirmed_at', 'datetime', true, 'When.'],
     ['confirmation_evidence', 'string', true, 'How it was confirmed — the thing that makes the record evidence rather than a note.'],
     ['superseded_by', 'DecisionRecordId|null', true, 'Authority is withdrawn by a later record, never by deletion.'],
   ]],

  ['FilingRecord', 'F4',
   'A filing, its approval, and the deadlines it creates.',
   [
     ['approved_by', 'DecisionRecordId', true, 'F4 forbids completing a filing without approval.'],
     ['approval_at', 'datetime', true, 'Approval before filing, demonstrably.'],
     ['authority_recheck', '{at, findings[], outcome ∈ {clean, changed, not_run}}', true, '**Tenet 31: every authority relied on is re-checked IMMEDIATELY BEFORE FILING.** The original contract had no field for it, so the rule could be stated, believed and never evidenced. `not_run` is a state because a recheck that could not run must not read as clean.'],
     ['filed_at', 'datetime|null', true, '`null` until filed. F4 forbids recording a filing complete without proof.'],
     ['forum', 'string', true, 'Which court. Consequential deadlines differ.'],
     ['fee', '{amount, receipt|null}', true, 'A fee paid without a receipt is a fee that will be disputed.'],
     ['service', '{mode, on[], proof|null, served_at|null}', true, 'F4 requires proof of service before completion.'],
     ['limitation', '{article: FindingId, computed_date, complied: bool}', true, 'The filing either was or was not within the window, and the Article it was computed from must be readable back. A filing record that cannot answer that is the one you need most in an appeal.'],
     ['consequential_deadlines', 'DeadlineId[]', true, 'Filing creates deadlines. Unrecorded, they are missed.'],
     ['complete', 'bool', true, 'Derived, never asserted: approval AND proof of filing AND proof of service.'],
     ['incomplete_because', 'string[]', true, 'What is missing. A bare `complete: false` gives the advocate nothing to do.'],
   ]],

  ['CaseSummary', 'A2 · G3',
   'THE FILE. Complete enough that another advocate can take it over from this alone.',
   [
     ['matter', 'MatterId', true, 'Which file.'],
     ['engagement', 'Engagement', true, 'Who the client is and what is in scope. A handover without it hands over work with no authority to do it.'],
     ['screens', '{conflict, competence, scope, capacity, urgency}', true, '**Each carries its own state, including `not_run`.** A2 forbids showing a `not_assessed` screen as clear, and that is only possible if the summary distinguishes them.'],
     ['threads', 'Thread[]', true, 'Every dispute on the file, including deferred ones.'],
     ['posture', '{thread: Posture}', true, 'Per thread, never per matter. Two disputes on one file can have opposite postures.'],
     ['chronology', '{thread: FactId[]}', true, 'Per thread, ordered, with certainty and provenance on each.'],
     ['issues', 'Issue[]', true, 'Including `parked` ones — D9 has no delete path.'],
     ['theory', '{thread: Theory}', true, 'The spine the issues hang off.'],
     ['proof', 'ProofPosition[]', true, 'Element, burden, standard, status.'],
     ['authorities', 'Finding[]', true, 'With binding status, validity window, paragraph kind and treatment. G3 must be able to invalidate them.'],
     ['deadlines', 'Deadline[]', true, 'Every one, passed included. A2 forbids dropping a passed deadline or filing it under upcoming.'],
     ['decisions', 'DecisionRecord[]', true, 'What the client decided and on what explanation.'],
     ['reservations', 'Reservation[]', true, 'E5. A disagreement the advocate overruled stays visible and reactivates on a changed fact.'],
     ['gaps', '{gap, blocks, owner}[]', true, 'What is not established. A summary that shows only what IS known reads as complete.'],
     ['handover_complete', 'bool', true, 'Derived. G3 requires the summary to stand alone, and the claim must be computed rather than assumed.'],
     ['handover_blockers', 'string[]', true, 'What stops it standing alone — the list a receiving advocate reads first.'],
   ]],

  ['ClosureRecord', 'H2',
   'The end of a matter, and everything that must not be open at it.',
   [
     ['matter', 'MatterId', true, 'Which file.'],
     ['closed_by', 'PartyRef', true, 'Closure is a decision, and it has an author.'],
     ['closed_at', 'datetime|null', true, '`null` while blocked. H2 forbids closing over an open obligation.'],
     ['money', '{client_funds, costs, disbursements, balance, returned_to, proof}', true, 'H2 requires money to be ACCOUNTED FOR. A closure record with no money fields cannot refuse a closure with client funds outstanding.'],
     ['originals', '{what, returned_to, at, proof}[]', true, 'Original documents are the most commonly stranded asset at closure.'],
     ['work_product', '{exported_at, format, location}', true, 'H2 requires the usable file to be exported, not merely offered.'],
     ['continuing_obligations', '{what, until, owner}[]', true, 'Obligations that outlive the matter. Unrecorded, they are breached by absence.'],
     ['retention', '{class, destroy_after, applied_at|null}', true, 'Retention and destruction rules, applied and dated.'],
     ['closure_summary_sent_at', 'datetime|null', true, 'The client is told the matter closed. Silence is not closure.'],
     ['lessons', '{text, client_identifiers_removed: bool}', true, '**H2 forbids client-identifying material in a lessons record.** A free-text lessons field with no such flag is where the leak happens.'],
     ['blockers', 'string[]', true, 'What is still open: a deadline, an asset, an original, a fund, a retention obligation. Non-empty means closure is refused.'],
   ]],

  ['WitnessPlan', 'F5',
   'One witness, why they are called, and what protects their independence.',
   [
     ['thread', 'ThreadId', true, 'Which dispute.'],
     ['witness', 'PartyRef', true, 'Who.'],
     ['necessity', 'string', true, 'Why this witness at all. F5 requires necessity to be assessed, not assumed from availability.'],
     ['materiality', 'FactId[]', true, 'Which facts they carry. A witness carrying no pleaded fact is a risk with no upside.'],
     ['availability', 'enum {confirmed, expected, doubtful, not_assessed}', true, 'A material witness who cannot attend changes the proof sequence, and finding out late is the whole problem.'],
     ['credibility', '{risks[], assessed_by}', true, 'Assessed before the opponent does it for us.'],
     ['interest', 'string', true, 'Their interest in the outcome. It will be put to them.'],
     ['prior_statements', '{where, when, gist}[]', true, 'Every prior statement is cross-examination material.'],
     ['contradictions', '{with_fact, nature}[]', true, 'Known contradictions, surfaced rather than discovered in the box.'],
     ['proof_sequence', 'int', true, 'Order of examination. Sequence is strategy, not administration.'],
     ['summons', '{needed: bool, filed_at|null}', true, 'A summons needed and not filed is a missed hearing.'],
     ['interpreter', '{language, arranged_by}|null', true, 'Language requirements are a competence issue (B4) as well as a logistics one.'],
     ['safety', 'string|null', true, 'Where a witness is at risk, that governs everything else.'],
     ['logistics_owner', 'PartyRef', true, 'F5 requires a NAMED owner. Unowned logistics fail on the day.'],
     ['contact_log', '{when, by, purpose, present[]}[]', true, '**F5 forbids coaching and requires independent recollection to be preserved.** The log is what makes that auditable rather than asserted — and it is the record that protects the advocate if it is alleged.'],
   ]],

  ['ExpertInstruction', 'F5',
   'An expert, instructed independently and testably.',
   [
     ['thread', 'ThreadId', true, 'Which dispute.'],
     ['expert', 'PartyRef', true, 'Who.'],
     ['discipline', 'string', true, 'The field, and therefore the limits of what they may speak to.'],
     ['purpose', 'string', true, 'The question put. An expert asked a leading question produces a leading answer.'],
     ['material_supplied', 'string[]', true, 'F5 requires a COMPLETE material set.'],
     ['material_withheld', '{what, reason}[]', true, 'Anything not supplied, with the reason. This is the field the opponent will probe, and an empty one is an answer.'],
     ['assumptions', 'string[]', true, 'Explicit assumptions. An unstated assumption is an opinion resting on air.'],
     ['instruction_balanced', 'bool', true, 'F5 forbids a partisan instruction.'],
     ['independence_statement', 'string', true, 'Recorded, not implied.'],
     ['methodology_tested', 'enum {tested, untested, not_assessed}', true, 'F5 requires methodology to be TESTED. Untested and untestable are different positions.'],
     ['limitations', 'string[]', true, 'What the opinion cannot support.'],
     ['conflicts', '{declared[], assessed_by}', true, 'An expert conflict surfaces in cross-examination if it does not surface here.'],
     ['report', '{received_at, conclusions[]}|null', true, '`null` until received.'],
   ]],

  ['DrafterBrief', 'F2',
   'The complete, lossless, structured hand-off to the drafting agent.',
   [
     ['cause_title', '{court, parties[], numbers{}}', true, 'The cause-title facts, so the drafter never re-derives them.'],
     ['theory_sentence', 'string', true, 'One sentence. A brief without a theory produces a pleading that is a list.'],
     ['material_facts', '{fact: FactId, date, provenance, weight}[]', true, 'In date order, with provenance. **F2 forbids re-extraction — that is where facts get invented.**'],
     ['provisions', '{finding: FindingId, verbatim_span, locator, binding}[]', true, 'With the span and the locator, so no lookup is repeated downstream.'],
     ['limitation', '{article: FindingId, computed_date, compliance_plea}', true, 'The Article, the computed date and the plea. A pleading that does not plead compliance invites the demurrer.'],
     ['reliefs', 'string[] (ranked)', true, '**Ranked.** An unranked relief list is a drafter\'s guess about what matters.'],
     ['authorities', '{finding: FindingId, binding, treatment, scope}[]', true, 'With binding status AND treatment scope — a case overruled on one point is good law on another.'],
     ['proof_positions', 'ProofPosition[]', true, 'Per element, so the pleading pleads what can be proved.'],
     ['facts_not_to_plead', '{fact: FactId, reason}[]', true, '**F2 forbids omitting this.** Advocates plead selectively; an omission is a decision, and a drafter not told what was excluded will helpfully restore it.'],
     ['arguments_parked', '{argument, reason}[]', true, 'Same reasoning, for arguments.'],
     ['open_gaps', '{gap, blocks}[]', true, 'What is unresolved. F3 turns these into marked blanks rather than confident prose.'],
     ['blanks_permitted', 'bool', true, 'A file with open gaps produces a draft WITH blanks. A draft without them, from a file with gaps, is the defect.'],
     ['lossless', 'bool', true, 'Derived: can a compliant pleading be drafted from this brief ALONE? **If not, the brief is the defect** — not the drafter.'],
   ]],
];

module.exports = { SCHEMAS, render };

function render(A) {
  A(H.h1('Appendix E — the typed contracts'));

  A(H.p('**PRODUCES is not a description. It is the state a slice leaves for the next one**, and a field that is absent here is a field the next slice cannot read. The obligation it carried is then dropped silently, which is precisely what principle P6 exists to prevent: *an obligation not represented in the type crossing the boundary is an obligation that will be dropped.*'));

  A(H.p('An external review found nine of these contracts unable to hold what their own DOES clause required. `WitnessPlan` was a sentence of prose; `DrafterBrief` was a pointer; `ClosureRecord` had no fields at all; and `CaseSummary` was never defined anywhere although two features derive from it. They are set out in full below, and `tools/speccheck.py` refuses a PRODUCES clause that contradicts one.'));

  A(H.callout('**Every field states WHY IT IS THERE, and the why names what goes wrong without it.** A field list with no reasons is a shape, and the previous build had twelve mechanically-checked shapes all passing on a transcript where the product asked a client who had said *"yesterday"* for the date twice.', H.SIGNAL));

  A(H.p('**The three-state vocabularies are not stylistic.** Each marks a place where *could not be assessed* would otherwise be indistinguishable from *assessed and fine* — defect shape S8, the single most repeated failure in the previous build.'));

  SCHEMAS.forEach(([name, owner, purpose, fields]) => {
    H.anchor(name, 'schema', purpose);
    A(H.spacer(200));
    A(H.h3(`${name}  ⟨${owner}⟩`));
    A(H.p(`*${purpose}*`));
    A(H.table(
      ['Field', 'Type', 'Req', 'Why it is there'],
      fields.map(([f, t, req, why]) => [
        '`' + f + '`', t, req ? 'yes' : 'opt', why,
      ]),
      [1750, 2150, 520, 4940],
    ));
  });
}
