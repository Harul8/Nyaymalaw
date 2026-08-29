const H = require('./helpers');
const GATES = require('./gates.json');
const { d, h1, h2, h3, h4, p, bullet, num, table, callout, feature, spacer, SIGNAL, ACCENT } = H;
const { Paragraph, PageBreak } = d;

const out = [];
const A = (...x) => x.forEach((e) => Array.isArray(e) ? e.forEach((y) => out.push(y)) : out.push(e));

/* ============ PART 4 — RETRIEVAL AND GROUNDING ============ */
A(h1('Part 4 — Retrieval, grounding and the anti-hallucination stack'));

A(callout('**The reframe this whole part rests on: NM does not have a search problem, it has a RESOLUTION problem.** Search returns passages similar to a query, ranked. That is the web paradigm and it is the wrong one here. An advocate does not want ten ranked passages; they want the answer to a structured question — *which provision governs this cause of action, in this forum, on this date* — and that question usually has **one right answer, fixed by legal structure rather than by textual similarity.**'));

A(p('So: **resolve first, and search only for what resolution cannot determine.** Everything below follows from that inversion. The measured cost of getting it backwards is on record — the Limitation Act Article that governed a live matter came back at **rank 53 of 60**, and had NM said "I cannot find the governing Article" that would have read as honest disclosure and been a retrieval failure.'));

A(h2('4.1  Layer 0 — the corpus is a graph of versioned legal entities'));

A(p('Not a document collection with embeddings laid over it. **Entities:** Act · Section · sub-section, proviso, illustration · Schedule Article · Judgment · Paragraph · Court · Cause of action · Forum · Relief.'));

A(table(
  ['Relation', 'Why it carries weight'],
  [
    ['Section —*amends / repeals / substitutes*→ Section', 'Temporal validity. Which text was in force on the date of the conduct.'],
    ['Section —*corresponds to*→ Section', 'IPC↔BNS, CrPC↔BNSS, IEA↔BSA. **Case law is overwhelmingly pre-2024 and cites the old numbering.** Precedent on IPC §420 is the body of authority for a BNS §318 charge, and a system that searches only the new number retrieves almost nothing. The mapping makes old authority reachable without inventing an equivalence.'],
    ['**Cause of action —*governed by*→ Limitation Article**', 'The Article becomes a lookup rather than a ranking. This is the single highest-value edge in the graph.'],
    ['**Cause of action —*triable by*→ Forum**', 'Forum is derived, not searched.'],
    ['Judgment —*interprets*→ Section', 'Authority attaches to provisions, so *the authorities on this provision* is a lookup.'],
    ['Judgment —*treats(kind, scope)*→ Judgment', 'Treatment is an edge with a scope, not a label on a case.'],
    ['Act —*in force in / from / until*→ Jurisdiction, dates', 'Era and territory.'],
  ],
  [3200, 6160],
));

A(spacer(140));

A(callout('**G1 — every provision carries a validity window, and the date is always part of the question.** NM never retrieves "section 420". It retrieves **the provision in force on the date of the conduct**. This makes the era rule structural instead of a filter someone has to remember, and it is the only formulation that survives the IPC/BNS transition without a special case. *A query without a governing date is rejected, not defaulted to today.*'));

A(h3('The era rule, stated once'));

A(p('**BNS, BNSS and BSA commenced on 1 July 2024. Matters arising before that date are governed by the IPC, CrPC and the Evidence Act. The governing date is the date of the conduct or the cause of action — not the date of the advice, and not the date of filing.** This is the part that gets silently wrong: a matter advised on today may be governed throughout by the old codes, and an answer reaching for the current numbering because it is current is wrong on the whole file rather than in one citation.'));

A(p('Substantive and procedural provisions may not follow the same rule, and the savings provisions govern which does what. **NM resolves that from retrieved savings and repeal provisions — it is not asserted from this document and this paragraph is not authority for it.**'));

A(h2('4.2  Layer 1 — resolution: the query is the MATTER, not a sentence'));

A(p('**Retrieval\'s input is the matter\'s structured state, not a text string:** posture, cause of action, forum, dates, relief, jurisdiction. Given those, a large share of what NM needs is a **deterministic lookup returning an exact citation** — the limitation Article, the era-correct provision, the forum, the elements to be proved.'));

A(p('None of that is a similarity contest, and treating it as one is what puts a governing Article at rank 53.'));

A(callout('**The interface is what makes this real.** The core emits `EvidenceNeed { for, question, matter_state{cause_of_action, forum, date, jurisdiction, provision}, kind }`. A need carrying only a text string would silently degrade the whole design back to search-first, and nothing downstream would notice.'));

A(p('*Eval (class B):* where the graph can resolve a question, the answer is exact and carries a citation, and **no similarity score appears anywhere in its derivation.**'));

A(h3('The honest cost'));

A(p('The cause-of-action→Article and cause-of-action→Forum maps are **real curation work and are not free.** They are bounded, reusable, and they are the asset that makes this hard to copy — anyone can buy embeddings; the graph is the part that has to be earned. The resolution layer can itself be wrong, so it carries its own confidence and **falls back cleanly into search rather than asserting.**'));

A(h2('4.3  Layer 2 — search, scoped by law rather than by similarity'));

A(p('Plenty does not resolve: *is a WhatsApp message an acknowledgment in writing?*, *does the Rent Act reach manufacturing premises?* That is genuine search, and a hybrid of lexical and dense retrieval is right for it — lexical because section numbers and defined terms demand exact matching, dense because pleadings and judgments say the same thing in different words.'));

A(p('**Search runs inside a scope the resolution layer has already fixed** — this Act, these sections, this forum, this date. A scope derived from law is a far better filter than one derived from a summary embedding, because it is *reasoned* rather than guessed.'));

A(callout('**THE RULE THAT MATTERS MOST IN THIS LAYER: only structure may exclude. Similarity may only reorder.** A hard similarity gate converts a ranking wobble into a permanent miss, because nothing downstream can recover a document that was never fetched. Where the system is confident on **legal** grounds it may exclude. Where it is merely confident on **vector** grounds, it may only rank.', SIGNAL));

A(p('**The one exception, and it is narrow.** Similarity may exclude a **measured outlier** — a candidate demonstrated wrong by a wide, quantified margin, such as a kidnapping judgment offered for a commercial tenancy dispute. **A top-k cut discards candidates that might be right; an outlier rejection discards candidates measured to be wrong.** The bar is relative to the field and calibrated on measurement, never an absolute constant, and the measured gap that justifies it is recorded.'));

A(p('*Eval (class C):* no candidate is removed by a top-k or absolute-threshold cut. Any similarity exclusion is an outlier rejection with its measured gap recorded, and it names what it rejected.'));

A(h3('Summaries: what they may and may not do'));

A(table(
  ['Rule', 'Why'],
  [
    ['**A summary may REJECT. It may never SELECT.**', 'A summary is reliable on coarse negatives and unreliable on fine positives. It can say with confidence *this is a kidnapping case, not a tenancy case*. It cannot say which of eleven tenancy cases governs — that requires the text. The previous build used **one embedding standing in for an entire Act** — the Limitation Act\'s thirty-two sections and hundred-odd Schedule Articles compressed into a single vector — to *select* which Acts were searchable at all. That is a summary doing the one job it cannot do, at the one point where being wrong is unrecoverable.'],
    ['**A summary is never a source for a proposition.**', 'Propositions cite primary text. A summary is a lossy paraphrase, and citing one is inference-dressed-as-citation with the added danger that it *looks* like a citation, complete with a locator.'],
    ['**Two summaries, two jobs.** A *subject* summary answers what area of law this is — used for coarse rejection. A *holding* summary answers **what it decided, on what facts** — used for on-point-ness.', 'Conflating them is why weight beat on-point-ness. A system holding only subject summaries has **no representation of on-point-ness at all** and falls back on citation weight by default.'],
    ['**Summaries are produced at section level and judgment level.**', 'The granularity gap — one vector per Act, then one per sub-clause, nothing between — and the summary question are the same question. Advocates think in sections. Act-level summaries are for presentation, never for retrieval.'],
    ['**A summary whose source has changed is refused until regenerated.**', 'A stale summary reads fluently whatever it was built from, so its staleness is invisible in a way a stale index\'s is not.'],
  ],
  [3000, 6360],
));

A(spacer(140));

A(h3('The citation graph, and what citation count is not'));

A(callout('**Citation count is PROMINENCE. It is neither authority nor relevance.** Authority is court, date and the forum this matter sits in — a Supreme Court judgment cited twice binds; a High Court judgment cited five hundred times persuades. Relevance is on-point-ness — whether it decided this question on facts like these. **The measured failure is on record: a heavy, much-cited judgment about kidnapping was offered for a commercial tenancy lockout.**'));

A(
  bullet('**Citation count never determines whether an authority is used**, and never appears in a statement of authority. At most it breaks a tie between authorities already equal on bindingness and on point.'),
  bullet('**Absence of citation is not evidence and never demotes.** A judgment delivered last year has few citers *because it is recent*, and recency favours it on current law. Only affirmative evidence may demote.'),
  bullet('**The unit of value is the LINE of authority, not a single case.** The advocate wants the line as it stands today — the leading case, what followed it, what distinguished it and on what facts, and where the position now rests. A single case handed over without its line is a citation waiting to be answered in court by the case that qualified it.'),
  bullet('**An edge without a verbatim span is not an edge.** Every relation asserted into the graph — interprets, treats, corresponds-to, amends — carries the text that establishes it and its locator. An unevidenced edge is an invention with a schema around it.'),
);

A(h2('4.4  Layer 3 — verification: retrieval ends here, not in a ranked list'));

A(p('**Every retrieved item is checked before it may be used.** Five checks, and the fifth is the one nobody builds:'));

A(table(
  ['#', 'Check', 'Fails when'],
  [
    ['1', 'In force at the relevant date', 'The provision was repealed, amended or not yet commenced on the governing date.'],
    ['2', 'The court\'s own words', 'The paragraph is classified `arguments`, `facts` or `headnote`. **14.8% of retrievable case paragraphs are counsel\'s submission** — roughly one in seven is something a losing advocate said.'],
    ['3', 'Binding or persuasive **for this forum**', 'Bindingness is computed from court, year and this matter\'s forum — never from prominence.'],
    ['4', 'Treatment, and on what scope', 'A judgment overruled on limitation remains good authority on possession. A bare "overruled" flag costs the advocate an authority they could have won on.'],
    ['5', '**The span actually supports the proposition being made**', 'This is the entailment check. Without it, grounding is enforced by hope.'],
  ],
  [400, 3000, 5960],
));

A(spacer(140));

A(callout('**Verification is a gate, not a score.** `Finding.supports` is a boolean and it blocks. A confidence number the answer layer weighs is a soft failure, and grounding admits no soft failures. A proposition whose cited span does not support it **blocks the answer rather than being softened**.', SIGNAL));

A(h2('4.5  Layer 4 — coverage is a first-class answer'));

A(p('**Every query terminates in one of THREE states, never two.**'));

A(table(
  ['State', 'Meaning', 'What NM does'],
  [
    ['**ANSWERED**', 'Found and verified', 'Uses it.'],
    ['**NOT HELD**', 'The manifest says the corpus does not contain it', 'Declines, and **names what is missing** — this jurisdiction, these years, this Act.'],
    ['**HELD BUT NOT FOUND**', 'The manifest says it is there and retrieval returned nothing', '**A defect. It escalates.** It is never disclosed to the advocate as a corpus gap.'],
  ],
  [2200, 3400, 3760],
));

A(spacer(140));

A(p('**This is only possible because coverage is an object rather than an inference from zero hits.** "Not in the corpus" and "in the corpus and not retrieved" produce an identical signal — no relevant chunks — and telling them apart is what makes the refusal rule falsifiable at all.'));

A(h3('The manifest — a statement of intent, not a byproduct'));

A(table(
  ['Rule', 'Detail'],
  [
    ['**M1 — the manifest states INTENDED coverage, and is therefore curated**', 'This is the whole design and getting it backwards makes the manifest useless. **A manifest generated from what the index contains can only tell you what is there. It can never tell you what is missing**, because absence leaves no trace to enumerate. To detect a gap you need an independent assertion — *the Limitation Act 1963, all sections and the whole Schedule* — against which absence becomes visible.'],
    ['**M2 — granularity is whatever makes the three-state answer decidable, no finer**', 'Acts by section and Schedule-article range; judgments by court and year range. Enough to answer *should we have this?* A manifest so detailed it becomes a second corpus to maintain has failed differently.'],
    ['**M3 — the three-state answer is computed from the manifest, never inferred from hit counts**', 'Zero results means nothing on its own. Zero plus "we hold this Act" is a retrieval defect. Zero plus "we do not" is an honest refusal.'],
    ['**M4 — the manifest is what the disclosure actually discloses**', 'Without it, disclosure is a vague disclaimer. With it, it is specific and therefore actionable.'],
    ['**M5 — content is asserted; currency is checked**', 'The manifest names the corpus version it was last reconciled against, and a reconciliation older than the index is reported. **A drifted manifest is worse than none**, because it converts real gaps into confident refusals and real defects into disclosures — failing in both directions at once.'],
    ['**M6 — coverage is a UNION across stores and identifier conventions**', 'Added from measurement. The corpus holds the same Act under two identifier conventions at different completeness, and a third store disagrees with both. **A coverage figure from one store is refused, not reported.**'],
  ],
  [3100, 6260],
));

A(spacer(140));

A(h2('4.6  The output contract — retrieval returns FINDINGS, not chunks'));

A(callout('**Returning chunks pushes citation, binding status and paragraph kind downstream to a layer that then skips them — which is precisely how counsel\'s argument comes to be quoted as the holding. The interface is where these obligations are either enforced or lost. An obligation not represented in the type crossing the boundary is an obligation that will be dropped.**'));

A(table(
  ['Field', 'Holds', 'Enforces'],
  [
    ['`proposition`', 'What this Finding is cited **for**', 'A citation must identify the proposition the case decided, not merely a sentence it contains.'],
    ['`ref` + `span` + `locator`', 'The reference, the **verbatim** text, and where it sits', 'Every citation is readable back. A Finding without a locator and a span cannot be constructed.'],
    ['`validity {from, to}`', 'The window this text was in force', 'The era rule, structurally.'],
    ['`binding` + `binding_for`', 'Binding or persuasive, **relative to a named forum**', 'Bindingness is relative — the same judgment binds in one court and persuades in another. `binding_for` is a forum, not a boolean.'],
    ['`para_kind`', 'ratio · reasoning · order · arguments · facts · headnote · unknown', 'Counsel\'s submission can never be quoted as the holding.'],
    ['`treatment[]`', 'kind, **scope**, by, span, method', '"Overruled" without a scope cannot be represented.'],
    ['`supports`', 'Boolean, from the entailment check', 'The grounding gate.'],
    ['`origin`', 'resolved · searched', 'Makes the resolution/search split measurable rather than asserted.'],
  ],
  [1800, 3200, 4360],
));

A(spacer(140));
A(p('*Eval (class A):* **no consumer of retrieval can receive a passage without its binding status, validity window, paragraph kind and locator attached.** This is asserted at construction, so it cannot be bypassed by a caller.'));

A(new Paragraph({ children: [new PageBreak()] }));

/* ============ 4.7 THE ANTI-HALLUCINATION STACK ============ */
A(h1('Part 4A — The anti-hallucination stack'));

A(p('**Zero invention is the product\'s central promise, and no single control delivers it.** A materially incorrect statement does not merely weaken a case — it can kill it, and it is made in a forum where it cannot be quietly withdrawn. There is no acceptable rate of this.'));

A(p('Ten controls, in the order a claim passes through them. **Each is independent**, so a failure at one layer is caught at the next; and each names the failure it exists to stop.'));

A(h3('The distinction everything rests on'));

A(table(
  ['', 'Legal PROPOSITION', 'Legal INFERENCE'],
  [
    ['Example', '"s.138(c) gives fifteen days from receipt of the notice."', '"Your client is exposed, because the s.139 presumption runs against him and a cash-flow explanation does not rebut it."'],
    ['Standard', '**Must be cited to retrieved text. Zero tolerance.** Not paraphrased from memory, not reconstructed, not approximated.', 'Cannot carry a citation. It is NM\'s reasoning, and it is the value being bought.'],
    ['Requirement', 'Every proposition cited.', '**Every inference visibly marked as inference.**'],
  ],
  [1400, 3800, 4160],
));

A(spacer(140));
A(callout('**An inference dressed as a citation is the most dangerous output the system can produce**, because it carries the authority of a source it does not have. The advocate must be able to audit the chain: these are the facts, this is the retrieved law, this is what NM concludes from them, and here is where NM\'s judgement enters.', SIGNAL));

A(h2('The ten controls'));

const controls = [
  ['**H1 · No training-data recall, structurally**',
   'NM never advises from its own training data. Everything rests on two sources only: what the advocate supplies, and what is in the corpus.',
   'The analysis core has **no model call that can introduce a legal proposition**. Propositions enter only as `Finding`s from the evidence service. The core is a pure function of matter state and verified Findings, so there is no path by which recalled law reaches an answer.',
   'Class A — the analysis core has no import of a model client. A `layercheck` lint fails the build on any such import.'],
  ['**H2 · The query carries a date, always**',
   'A provision is never retrieved without the date it must be in force on.',
   '`EvidenceNeed.matter_state.date` is non-optional. A need without a governing date is **rejected, not defaulted to today**.',
   'Class A — a need constructed without a date raises. No default-to-today path exists.'],
  ['**H3 · Resolution before search**',
   'Determinate questions are answered by lookup against the graph, not by ranking.',
   'Where the graph resolves, the answer is exact and carries a citation, and **no similarity score appears in its derivation**. Where it does not resolve, it falls back to search carrying its own confidence rather than asserting.',
   'Class B — a resolved Finding has `origin: resolved` and no score in its provenance. Class C — resolution coverage on a sampled set of real matters is measured and reported.'],
  ['**H4 · Structure may exclude; similarity may only reorder**',
   'Nothing that might be right is discarded before it can be considered.',
   'No top-k or absolute-threshold cut. Any similarity exclusion is an **outlier rejection with a recorded, measured gap**, and it names what it rejected.',
   'Class C — the pipeline reports its exclusions per stage. A stage that cannot report its own exclusions makes a miss indistinguishable from an absence.'],
  ['**H5 · The entailment gate**',
   'The cited span must actually support the proposition it is cited for.',
   '`Finding.supports` is computed by an entailment check between the proposition and its span. It is a **boolean that blocks**, not a score the answer layer weighs.',
   'Class B, at runtime, on every served turn — a proposition whose span does not support it **gates the output**. Class D — sampled entailment judgements are reviewed by a second model and by a human.'],
  ['**H6 · Primary text only**',
   'A summary is never a source for a proposition.',
   'Every citation resolves to primary text — a section, sub-section, proviso, Schedule Article, or a judgment paragraph. **No cited span may resolve to a summary.**',
   'Class B — asserted at `Finding` construction. A Finding whose span resolves to a summary store cannot be built.'],
  ['**H7 · Attribution discipline**',
   'Counsel\'s submission is never quoted as the court\'s holding.',
   'A proposition attributed to a judgment resolves to a paragraph classified `ratio`, `reasoning` or `order`. An `unknown` paragraph may be **quoted with its status disclosed** and may not carry a proposition alone. Reliance on obiter is **labelled as obiter**.',
   'Class B — `para_kind` is non-optional on every Finding and is checked at use. Class C — the unclassified share (26.7%) is reported, and any classification pass reports its residual.'],
  ['**H8 · The three-state coverage answer**',
   'A refusal is only ever issued on material the corpus genuinely does not hold.',
   'ANSWERED / NOT HELD / **HELD BUT NOT FOUND**, computed from the curated manifest, union across every store and identifier convention. **A refusal on held material is a defect and is reported as one, never surfaced as honesty.**',
   'Class C — manifest reconciliation against the index, with the reconciliation date recorded. Class B — every refusal names the manifest entry it rests on.'],
  ['**H9 · Inference marking**',
   'The advocate can always see where retrieved law stops and NM\'s reasoning begins.',
   'Every inference is marked as an inference and **no inference carries a citation as though it were a proposition**. The answer renders the two differently, not only in the data model.',
   'Class B — every sentence making a legal claim is classified proposition or inference; a proposition without a Finding reference, or an inference with one, fails.'],
  ['**H10 · Derived-artefact identity**',
   'A stale index, embedding store, summary or citator can never quietly serve old law.',
   'Every derived artefact records the identity of what it was built from and is **refused on mismatch**, not used with a warning.',
   'Class C — on every ingest, each artefact\'s source identity is compared and a mismatch fails the build. The measured precedent: a native index served **411,797 documents against the source\'s 414,710**, silently, through every query.'],
];

controls.forEach((c) => H.anchor(
  c[0].replace(/\*\*/g, '').split('\u00b7')[0].trim(), 'control', c[1]));

A(table(
  ['Control', 'The promise', 'The mechanism', 'The eval'],
  controls,
  [1900, 2100, 3100, 2260],
));

A(spacer(160));

A(h2('What happens when a control fires'));

A(table(
  ['Failure', 'Response', 'Why this and not something else'],
  [
    ['**A grounding violation** — an uncited proposition, a span that does not support, an inference dressed as a citation', '**GATE THE OUTPUT.** The answer does not ship.', 'Priority 1: a wrong answer is worse than no answer. This is the only class of failure that produces confidently wrong output.'],
    ['Any other invariant violation', 'Record it in `TurnMetrics.violations` with the rule identifier, surface it, and **ship the answer**.', 'Fail loud by default. Everything else degrades the answer without falsifying it, and blocking on benign variation trains people to bypass the gate.'],
    ['An adapter failure — index, model or store unavailable', '**Fail the need, not the turn.** The gap becomes visible in the answer.', 'A turn that dies because one retrieval failed is a worse outcome than a turn that says what it could not establish.'],
    ['A stale derived artefact', '**Refuse the artefact.** Do not use it.', 'A stale summary reads fluently whatever it was built from.'],
    ['A programming error', 'Log at ERROR with a traceback. **Never swallowed by a broad except.**', 'A broad `except` once made a `NameError` look like a model failure and silently emptied a whole feature.'],
  ],
  [2800, 2900, 3660],
));

A(spacer(140));
A(callout('**Violations land in a store, not a log line. A test whose failures are not collected is not a test.**'));

A(new Paragraph({ children: [new PageBreak()] }));

/* ============ PART 5 — CONVERSATION ============ */
A(h1('Part 5 — The conversation'));

A(h2('5.1  A priority queue over gaps, not a machine over phases'));

A(p('**A senior does not run a script. They ask the question that matters most next.** So the design is not a state machine that advances through phases; it is a **priority queue over gaps, recomputed every turn across the whole file.**'));

A(table(
  ['Why a phase machine is the wrong shape', 'Consequence'],
  [
    ['It owns the sequence', 'It fights an advocate who wants to go elsewhere.'],
    ['It must always have a next step', 'It **manufactures questions** to stay in motion.'],
    ['Its phase boundaries are guesses', 'The order varies by matter, and the guess is wrong on the matters that matter.'],
  ],
  [4680, 4680],
));

A(spacer(140));

A(h3('The gates, and which two block'));

A(table(
  ['Gate', 'Blocking?', 'What it blocks'],
  [
    ['Posture resolved', '**YES**', 'The directive step for that thread. An unresolved posture makes everything downstream of it worthless, however interesting.'],
    ['Chronology sufficient to compute limitation', '**YES**', 'Merits work on that thread. Limitation precedes merits because it disposes of the matter regardless of merit.'],
    ['Governing provisions resolved', 'no', 'Ranks only.'],
    ['Elements established vs gapped', 'no', 'Ranks only.'],
    ['Theory stated', 'no', 'Ranks only.'],
    ['Adversarial pass run', 'no', 'Ranks only.'],
  ],
  [3400, 1400, 4560],
));

A(spacer(140));
A(p('**Blocking gates short-circuit, and that is both a correctness and a cost mechanism.** An unresolved posture means the thread\'s downstream derivations are **not computed at all** — it produces a question instead. Nothing wrong is generated, and nothing is paid for.'));

A(h3('How the next action is chosen'));

A(p('Each turn, NM selects the single highest-value next action across the whole file, ranked:'));

A(
  num('**Blocking gates** — an unresolved posture makes everything below it worthless.'),
  num('**Deadline urgency** — the nearest window leads.'),
  num('**Information value** — the one question that unblocks the most.'),
  num('**Consequence** — the magnitude of what is at stake.'),
);

A(h2('5.2  The question policy'));

A(table(
  ['Rule', 'Detail'],
  [
    ['**A question exists only because a gap blocks an action.**', 'There is no obligation to ask something in order to advance, because there is nothing to advance. This removes the manufactured question by construction rather than by prohibition. *Eval (class A): every question traces to a specific gap and to the action that gap blocks. A question that blocks nothing is a defect.*'],
    ['**Ask in batches, one thread at a time.**', 'A single batched question per thread, not an interrogation across all of them. Serial single questions make the advocate do the scheduling.'],
    ['**Never ask what a document already answers.**', 'Take in the documents, analyse them, and then ask only for what is genuinely missing.'],
    ['**Open before narrow.**', 'A leading question shapes what comes back and can manufacture the gap it assumed.'],
    ['**One guided re-ask, then accept.**', 'Each reply is assessed as sufficient / partial / off-target / nothing-further. One re-ask, then accept what was given and **record the gap**. NM does not keep pushing — a recorded gap is a first-class output.'],
    ['**Open gaps are always visible.**', '*"Still missing, and why it matters"* closes every consultation. It is what stops an assessment reading as more settled than it is.'],
  ],
  [2600, 6760],
));

A(spacer(140));

A(h2('5.3  The advocate navigates. The queue is advice, not a rail.'));

A(p('If the advocate asks about another thread, **NM answers on that thread in that turn.** It does not finish anything first and does not ask to come back. Where the queue\'s order was deadline-driven, NM says so **once** on departing — *"we can take the tenancy first; note the s.138 window closes in six days"* — then does as asked.'));

A(p('The deferred threads and their deadlines stay on the board, so the ordering survives as **state** even when it is not driving.'));

A(p('*Eval (class B, on every stage): did NM refuse to follow the advocate somewhere else? A build that passes its stages by railroading the advocate through them has failed.*'));

A(h2('5.4  A changed fact re-derives everything that rests on it'));

A(p('*"Actually the notice was served on 12 August, not 10."* That touches the chronology, the limitation date, the proof position, the recommendation, and possibly **advice from an earlier turn the advocate has already acted on.**'));

A(callout('**Architectural consequence: matter state is a derivation graph, not a pipeline.** Every computed value records what it depends on. A corrected fact invalidates its dependents and they recompute — **like a spreadsheet, not like a pipeline re-run.** A pipeline recomputes everything (so a trivial correction produces a full re-analysis) or nothing (so stale conclusions survive under corrected facts). A dependency graph recomputes exactly what changed and can say what changed and why.'));

A(p('**The rule:** when a material fact changes, every item derived from it is recomputed; each recomputed item whose value changed is **reported with what it was**; and where earlier advice is affected, that is said in terms, **including whether anything already done needs undoing.**'));

A(p('**The bound:** only *material* facts trigger the cascade, and where re-derivation changes nothing the answer is one line.'));

A(h2('5.5  Where NM stops — judgement, not decision'));

A(p('On questions that are ultimately the client\'s — settle or fight, which of several viable routes, commercial trade-offs — NM does not decide and does not merely survey. It sets out the alternatives actually available, gives a **brief** analysis of each, **states its own opinion on what the client should do**, and leaves the decision to the advocate and the client.'));

A(callout('**Options are permitted only when carried with a recommendation.** "Three routes; I would take the second; the first fails on limitation and the third costs more than it recovers" is advice. A balanced pros-and-cons table with no view is the failure mode already observed live, where the table was boilerplate and in part contradicted the analysis above it.'));

A(new Paragraph({ children: [new PageBreak()] }));

/* ============ PART 6 — INTERFACE ============ */
A(h1('Part 6 — The interface'));

A(p('**The problem this part solves is one the rest of the document creates.** The decisions above commit NM to producing fourteen distinct kinds of content — the mode statement, a theory per thread, the parties table, a recommendation, adverse findings with the move that answers them, proof gaps, the opposing case and our answer, cross-thread exposure, the "considered, not pursued" list, citations with binding status, treatment flags, inference labels, questions, and confirmation prompts.'));

A(callout('**Give each of those a heading and every turn becomes a document** — which is the 3,000-word wall already measured live. An answer nobody finishes reading is not an answer.', SIGNAL));

A(h2('6.1  Three surfaces, three jobs'));

A(table(
  ['Surface', 'Its job', 'What it holds', 'How it updates'],
  [
    ['**The boards** — matter list, then thread board (left pane)', '*Which file needs me?* then *where does each dispute in it stand?* — glanceable status, and the handles used to decide what to open. **Two surfaces, two arities** (§6.2A)', 'Matter list, per matter: matter · client · nearest deadline · what is blocked · last touched. Thread board, per thread: thread · our client is · against · forum · stage · next deadline', 'Overwritten in place, every turn'],
    ['**Case summary** (centre, on demand)', '*What is our worked position?* — the living case note', 'Per thread: theory · chronology with provenance · posture · proof position per element · issues with facets and dispositions including everything parked and why · the limitation computation with its inputs · authorities with binding status and treatment · the opponent\'s theory and likely attacks with our answers · recorded reservations · open gaps', 'Updated in place'],
    ['**Chat answer**', '*What changed, and what do we do now?*', 'The recommendation, the delta, what blocks', 'Written once, **never restated**'],
  ],
  [1900, 2200, 3600, 1660],
));

A(spacer(140));

A(callout('**The board holds no analysis.** Not the theory, not proof gaps, not reasoning. **The answer recites neither of the other two surfaces.** Most of the measured bloat was NM re-stating standing state every turn — the parties, the forum, the facts the advocate had just supplied. The harm is not verbosity: **an answer that repeats itself every turn teaches the advocate to skim, and skimming is how a flag we fought to surface gets missed.**'));

A(h3('The single source of the worked position'));

A(p('**The case summary is the single source.** The board derives its status fields from it; the answer derives its delta from it. **Neither holds anything the summary does not**, or they will disagree — and a board that disagrees with the answer is worse than either alone, because the advocate cannot tell which is stale. *Measured: the board cited Article 66 while the answer reasoned from Article 65.*'));

A(h2('6.2  The shape of an answer'));

A(p('**Length is bounded by content, not by a word count.** A word limit would be a scenario patch — a five-dispute file legitimately needs more than a one-question turn. The generalised bound: **every element of an answer must be one of exactly four things.**'));

A(table(
  ['Element kind', 'Example'],
  [
    ['**Action** — do X, by when', '"Move for anticipatory bail before the Sessions Judge tomorrow; the window on the s.138 notice closes in six days."'],
    ['**Finding that changes an action**', '"This fails on limitation, so run the summary possession suit instead." The *"considered, not pursued"* line is this kind — it records that an available action was weighed and rejected.'],
    ['**Question that blocks an action**', '"Whose side do we act on here? I cannot recommend a step until that is settled."'],
    ['**Ground** for one of the above', 'The citation, the proof position, the opposing argument.'],
  ],
  [2600, 6760],
));

A(spacer(140));

A(callout('**Anything that is none of these four is cut.** Restating facts the advocate supplied is not on the list. Restating the board is not on the list. Explaining the law for its own sake is not on the list. **This stops being a style rule and becomes a type: there is no way to put a recital of the brief into an Answer, because no element kind holds one.**'));

A(h3('Ordering and layout rules'));

A(
  bullet('**The recommendation comes first — unless something blocks it.** The first content element is an action, never background. If the recommendation is not at the top, the analysis was written toward a verdict and not toward a step.'),
  bullet('**A blocking question displaces it.** Where posture is unresolved or a document cannot be bound to a thread, the question comes first and the recommendation is withheld for that thread — **the block *is* the answer.**'),
  bullet('**Organised by thread**, because an advocate thinks matter by matter. Cross-thread exposure is the one thing that legitimately sits outside the threads, and it appears **once**, after them.'),
  bullet('**Progressive disclosure is allowed. Hiding a loud signal is not.** A limitation bar, an adverse treatment flag, an unresolved posture, a contradiction between instruction and document, or a cross-thread exposure is **never placed below the fold or inside collapsed content.** Otherwise "concise" becomes the mechanism that suppresses exactly the signals we fought to raise.'),
  bullet('**The shape scales with the mode.** A short question gets an answer, not a structure.'),
  bullet('**A turn that changes nothing says so, in a line, and stops.** Re-running the full analysis and producing a full-shape answer anyway trains the advocate to skim.'),
);

A(h2('6.2A  The boards — and there are TWO of them'));

A(callout('**A first draft of this document said "the board" and meant two different objects.** An advocate holds many **matters**; a matter holds many **threads**. The landing surface answers *which of my files needs me?* and the in-conversation surface answers *where does each dispute in this file stand?* Those are different questions, different rows, and different arity bounds — and giving them one name is how a board ends up scaling on the wrong axis.', SIGNAL));

A(table(
  ['', '**The MATTER LIST** (landing)', '**The THREAD BOARD** (in a matter, left pane)'],
  [
    ['Answers', '*Which of my files needs me, and why?*', '*Where does each dispute in this file stand?*'],
    ['One row per', '**Matter**', '**Thread**'],
    ['Fields', 'Matter name · client · **nearest deadline across all its threads** · what is blocked · last touched', 'Thread · our client is · against whom · forum · stage · next deadline'],
    ['Ordered by', '**Nearest deadline first**, then what is blocked, then recency. Never alphabetically and never by creation date', 'The deadline register (§D3). The nearest window leads regardless of which thread is legally the most interesting'],
    ['Bounded by', '**Matter count** — never by threads, turns or facts', '**Thread count** — never by turns, facts, issues or authorities'],
    ['Updated', 'Overwritten. Recomputed on entry and when a deadline changes category', 'Overwritten each turn'],
  ],
  [1300, 4000, 4060],
));

A(spacer(140));

A(p('**Both are projections of the case summary and hold nothing it does not.** Neither computes. If the two boards and the answer could disagree, the advocate cannot tell which is stale — which is why all three derive from one source.'));

A(h3('Board discipline — bounded by construction, not by trimming'));

A(p('Moving detail off the answer is worthless if it accumulates in the left pane instead.'));

A(
  bullet('**Fixed arity per row.** A fixed small set of fields. Board size scales with **row count only** — the matter list with matter count, the thread board with thread count — never with turns, facts, issues or authorities.'),
  bullet('**State, not history.** Overwritten each turn. Nothing is appended to it, ever. A field changes value; the board does not grow a line.'),
  bullet('**A line that is a conclusion, a reason, or a piece of reasoning does not belong on either board.** That is the test for status versus analysis, and it is applicable without judging importance.'),
  bullet('**Expansion is deliberate.** A thread opens to its full position in the case summary when the advocate chooses; it does not render expanded.'),
  bullet('**Deferred threads stay on the board with their deadlines.** When the advocate takes another thread first, the queue\'s ordering survives as **state** even when it is not driving. A deprioritised thread is never removed — nothing is capped away.'),
);

A(p('*Eval (class A): adding a turn never adds a board line. Board length is a function of row count alone — measurable directly, and **this is the regression to watch**.*'));

A(h3('What the board must show loudly, and what it must never show at all'));

A(p('The board is a status surface, which makes it the most tempting place to quietly lose a signal. Three rules stop that.'));

A(table(
  ['Situation', 'How the board renders it', 'The defect refused'],
  [
    ['**Posture unresolved on a thread**', 'The row renders **loudly**, with the side field showing `unknown` rather than empty. A conflicting posture prints a confirm-before-advising banner on the row.', 'An empty field reads as "not important yet". `unknown` is a value, and the board is where the advocate sees it without opening anything.'],
    ['**A gating screen could not run**', 'The row shows the screen as **`not assessed`** — never as clear, and never as an open item the advocate must action.', '**Both directions are defects.** Reporting `not_assessed` as clear is S1. Reporting a gate *that cannot apply to this matter* as an open item is the measured B-101 defect, and it trains the advocate to ignore board flags.'],
    ['**A deadline has passed**', 'Shown as **passed**, with the consequence, and never silently dropped or filed under "these will not wait".', 'An action due eight months ago listed as upcoming was measured live.'],
  ],
  [1900, 4200, 3260],
));

A(spacer(140));

A(h3('Board states — a board that cannot be built must not render as an empty one'));

A(table(
  ['State', 'What renders', 'Why it is specified'],
  [
    ['**No matters yet**', 'One invitation to brief. Not a form.', 'The first-run surface sets the register for everything after it.'],
    ['**Building**', 'The rows that are ready, with the rest marked pending. Never a spinner over the whole surface.', 'A five-thread file should not be unreadable because one thread is recomputing.'],
    ['**Stale**', 'The last committed projection, **marked as of when**. Never silently current.', 'A board that looks live and is not is worse than one that admits it is old.'],
    ['**Could not be built**', '**An explicit failure**, naming what could not be read.', '**A board that fails to load and renders empty tells the advocate they have no matters.** That is the single most repeated defect shape in this project, in its most visible possible form.'],
    ['**Blocked**', 'The row carries the block and what it blocks. The recommendation is visibly withheld, not absent.', 'The block *is* the answer, and it must be visible without opening the thread.'],
  ],
  [1500, 3900, 3960],
));

A(spacer(140));

A(p('*Evals:* **Class A** — a board that cannot be built raises rather than returning an empty projection; a `not_assessed` screen never renders as clear; an inapplicable gate never renders as an open item; a passed deadline is never absent. **Class B** — no board field contains a conclusion, a reason or a piece of reasoning; the matter list is ordered by nearest deadline.'));

A(h3('The case summary'));

A(
  bullet('**Updated in place. It is state, not a transcript.** A summary that accumulates turn by turn is a conversation log with a different name, and it stops being readable at exactly the point a five-thread file needs it most.'),
  bullet('**Every item carries its provenance and its fact dependencies.** This is what makes the correction cascade possible — a corrected fact can only re-derive what has recorded that it depends on that fact.'),
  bullet('**One prior value, not a history**, and only where the change altered a conclusion or advice already given. The advocate can see that the limitation date moved and why; they do not get an audit log of every intermediate computation.'),
  bullet('**It reads as a case note, not a debug dump.** This is the advocate\'s work product — the thing they would take into a conference. Internal identifiers, confidence scores and pipeline state belong in diagnostics. *Eval (class D): the summary can be read aloud to a client without translation.*'),
);

A(h2('6.3  Screens'));

A(table(
  ['Screen', 'Contains', 'The rule that governs it'],
  [
    ['**Sign in**', 'Advocate identity, enrolment, firm.', 'A failed credential discloses nothing about which matters exist.'],
    ['**Landing — no matters**', 'One invitation to brief.', 'Not a form.'],
    ['**Landing — matters exist**', '**The matter list**, ordered by nearest deadline. Deadlines that changed category surfaced above it.', 'One row per matter. Bounded by matter count. No analysis.'],
    ['**Inside a matter**', '**The thread board**, pinned left. Unresolved postures render loudly; blocked threads carry the block.', 'One row per thread, six fields. Bounded by thread count.'],
    ['**Board — degraded**', 'Building: ready rows plus pending. Stale: last projection, marked as of when. **Unbuildable: an explicit failure naming what could not be read.**', 'A board that cannot be built never renders as an empty one.'],
    ['**Conversation**', 'The chat answer, with the thread board pinned left and the case summary reachable per thread.', 'The answer recites neither of the other surfaces.'],
    ['**Case summary (per thread)**', 'The full worked position, as listed in §6.1.', 'Reads as a case note; updated in place; one prior value where a conclusion changed.'],
    ['**Document intake**', 'Upload, extraction preview, per-field confirmation with provenance, thread binding shown and correctable.', 'Inverting fields always confirmed. An unattached document contributes no facts.'],
    ['**Confirmation prompts**', 'Inline, specific, with the consequence of getting it wrong. "Confirm the date of service on page 4 — two days decide this matter."', 'No flag consists only of a general caveat.'],
    ['**Blocked state**', 'The blocking question, with what it blocks and why, and the recommendation visibly withheld.', 'The block is the answer, not an error.'],
    ['**Diagnostics** (internal)', 'Turn metrics, stage latencies, exclusions per stage, invariant violations, model mix.', 'Never contains a client\'s own words.'],
  ],
  [1800, 4200, 3360],
));

A(new Paragraph({ children: [new PageBreak()] }));

/* ============ PART 7 — ARCHITECTURE / NFR ============ */
A(h1('Part 7 — Architecture and non-functional requirements'));

A(h2('7.1  Six principles, each justified by a rule above'));

A(table(
  ['Principle', 'What it means', 'Why — and it is never taste'],
  [
    ['**P1 · Hexagonal: a pure core, adapters at the edges**', 'Analysis is a pure function of matter state and verified Findings. Retrieval, the model, storage, documents and presentation are adapters behind ports.', 'Class-A tests need no corpus and no model and run every commit in seconds. **That cadence is only available if the analysis core has no I/O.** The most load-bearing invariants — posture derivation, the limitation coverage check, disposition accounting, theory/adverse-fact set comparison — are all pure logic. Hexagonal structure is what converts them from aspirations into commit-time tests.'],
    ['**P2 · Deterministic shell, stochastic core**', 'Resolution (deterministic) → Search (stochastic) → Verification (deterministic gate).', 'A stochastic stage cannot be trusted to police itself, and **every measured failure in this system\'s history was a stochastic stage\'s output taken at face value** — a summary embedding gating an Act out, a scoring table displacing a governing Article, a model returning a vocabulary nobody validated. Determinism at the ends means the middle may be wrong without the system being wrong.'],
    ['**P3 · Dependencies run one way**', 'Analysis never calls retrieval; it consumes Findings. Drafting never retrieves. Presentation never computes.', 'Grounding holds only if there is exactly **one** audit chain. Two retrieval paths mean two grounding standards and no way to say which produced a citation.'],
    ['**P4 · Matter state is a derivation graph**', 'Every computed value records what it depends on; a corrected fact invalidates its dependents.', 'A pipeline recomputes everything or nothing. A graph recomputes exactly what changed and can say what changed and why.'],
    ['**P5 · Every gate declares its own response**', 'A condition that refuses something declares WHAT it refuses (turn, thread, step or evidence need) and HOW (withhold, block, or disclose). Those declarations live in one table — §7.1A, generated from `nm/domain/gates.py` — and no call site decides for itself.', 'The first draft of this document said the product *fails closed only on grounding* while nine conditions elsewhere in it blocked something. Both statements were written in good faith and they cannot both be true. **A prose rule about what happens when things go wrong will always drift from the code that handles it**, so the rule is now a table the code reads and the document renders.'],
    ['**P6 · Contracts carry obligations**', '`Finding` carries binding status, validity, paragraph kind and the entailment result. `DrafterBrief` carries provenance, ranked reliefs and what not to plead.', '**An obligation not represented in the type crossing the boundary is an obligation that will be dropped.**'],
  ],
  [2300, 3200, 3860],
));

A(spacer(140));

A(h2('7.2  Module boundaries, and the rule that is enforced rather than documented'));

A(table(
  ['Module', 'Owns', 'Must not'],
  [
    ['`core/`', 'Analysis, conversation, matter state, the derivation graph. **Pure — no I/O.**', 'Import an adapter, a client library, a database or an HTTP layer'],
    ['`ports/`', 'The interfaces the core declares: EvidencePort, DocumentPort, ModelPort, StorePort', 'Contain implementation'],
    ['`adapters/`', 'Evidence service, document intake, model gateway, storage', 'Contain analysis logic'],
    ['`knowledge/`', 'Offline: ingestion, graph build, indices, summaries, manifest', 'Be written to during a turn'],
    ['`edge/`', 'API, session, presentation projections', 'Compute anything the summary does not hold'],
    ['`drafting/`', 'Pleadings from a DrafterBrief, as a separate process', '**Retrieve**'],
    ['`obs/`', 'Metrics, diagnostics, invariant assertions', 'Be optional, or contain client words'],
  ],
  [1400, 4200, 3760],
));

A(spacer(140));

// P1-P6 become anchors so code may declare @implements against them.
['P1', 'P2', 'P3', 'P4', 'P5', 'P6'].forEach((id, i) => H.anchor(
  id, 'principle', ['Hexagonal: a pure core, adapters at the edges',
                    'Deterministic shell, stochastic core',
                    'Dependencies run one way',
                    'Matter state is a derivation graph',
                    'Every gate declares its own response',
                    'Contracts carry obligations'][i]));

A(spacer(200));
A(h2('7.1A  The gate matrix'));

A(p('**This table is generated from `nm/domain/gates.py`.** It is not a description of the code; it is the code\'s own registry rendered. A gate that appears here and is consulted nowhere fails `trace`, and a gate consulted in code and absent here cannot be constructed. That is deliberate: the previous draft of this section was prose, and prose about failure handling drifts from the handler within one slice.'));

A(p('**Read RESPONSE with SCOPE, never alone.** `withhold` on a NEED fails that need and leaves the turn standing; `withhold` on a TURN emits nothing at all. **The turn is withheld by exactly three gates — G-GROUND, G-ATTRIB and G-QUOTE, the grounding family — plus G-STALE, which is a concurrency re-derive and not a quality gate.** Everything else blocks a step or discloses a limit.'));

A(p('**RECOVERY names who may clear it.** A gate whose recovery is `human` may never be cleared by a model, and a gate cleared by an actor carries a THIRD state for the case where it could not be evaluated — `not_assessed`, `not_run`, `unrecorded`, `unresolved`, `ambiguous`, `not_measured`. A screen that could not run must never be indistinguishable from one that passed; that is the single most repeated defect in the previous build, and the constructor in `gates.py` refuses a gate that lacks the third state.'));

A(table(
  ['Gate', 'Fires when', 'States', 'Response · scope', 'Recovery', 'Built'],
  GATES.map((g) => [
    '**' + g.id + '**',
    g.condition,
    g.states.join(' · '),
    '**' + g.response.toUpperCase() + '** · ' + g.scope,
    g.recovery + ' · ' + g.persistence,
    g.built ? 'yes' : '**no**',
  ]),
  [1450, 2750, 1750, 1500, 1250, 660],
));

A(spacer(140));

A(h3('What the advocate sees'));

A(table(
  ['Gate', 'The visible response'],
  GATES.map((g) => ['**' + g.id + '**', g.visible]),
  [1450, 7910],
));

A(spacer(160));

A(callout('**A gate marked `built: no` is a gate whose condition NOTHING CURRENTLY EVALUATES.** It is listed because the alternative — leaving it out until it is built — is how a specification comes to describe a product that screens matters when the product does not. `G-UNSCREENED` exists precisely to make the unbuilt screens visible on every turn that proceeds without them.', SIGNAL));

A(spacer(200));

A(callout('**`core/` may import only `core/` and `ports/`. Any other import fails the build.** Why a lint rule and not a convention: P1\'s entire value is the class-A test cadence, and that is lost the first time one import sneaks in quietly, in a change that looks harmless. **A convention degrades; a build failure does not.**'));

A(h2('7.3  The turn — the runtime contract'));

A(callout('**Nearly every defect that reached a live session in the previous build lived here — not in a component, but in the seams between them.** A duty screen that ran after the advice it guards had been shown. A streamed turn that wrote its whole opinion and then died. Forty of forty offline tests passing while every served turn crashed. **A component that is right in isolation and wrong in the turn is wrong.** So this section states the turn as a contract, not as a list of steps.', SIGNAL));

A(h3('7.3.1  Three phases, and two boundaries that must not be crossed'));

A(p('A turn has three phases separated by two hard boundaries. **Every rule below exists to keep something on the correct side of one of them.**'));

A(table(
  ['Phase', 'What happens', 'What is true at the end of it'],
  [
    ['**ADMIT-A**', 'Authenticate · classify the route · minimal emergency triage on names and danger only · **names-only conflict screen** · competence, engagement and scope.', 'The matter is cleared to hold substance, or it is not. **Nothing substantive has been read, retained, or sent to a model provider.**'],
    ['**ADMIT-B**', 'Take in documents · extract · integrate facts · bind to threads.', 'Everything that may enter the file has entered, and everything that must not has been refused. **No derivation has run.**'],
    ['**DERIVE**', 'Invalidate dependents · recompute in dependency order · request and verify evidence · cross-file passes · the gap queue · assemble the Answer, board and summary · assert invariants.', 'A complete, screened, invariant-checked Answer object exists in memory. **Nothing has been shown and nothing has been persisted.**'],
    ['**EMIT**', 'Commit state and metrics · release bytes to the transport.', 'The advocate has the answer and the file records it. **After this point nothing can be unsaid.**'],
  ],
  [1100, 4700, 3560],
));

A(spacer(140));

A(table(
  ['Boundary', 'The rule', 'The defect it exists to refuse'],
  [
    ['**THE SCREEN BOUNDARY** — inside ADMIT, between A and B', 'No substance is READ, RETAINED, or SENT TO A PROVIDER on a matter whose screens have not returned. An **incomplete** screen is not a passed screen. Only tenet 6\'s protective steps cross it, and they carry no merits and retain nothing.', 'Substance merged onto a file no conflict check had cleared — and, in the first draft of this very section, document content extracted through a model provider before the matter was cleared to hold it.'],
    ['**THE BYTE BOUNDARY** — between DERIVE and EMIT', '**Not one byte of model-generated prose reaches the transport until every screen governing it has returned and every invariant has been asserted.**', 'The duty screen running after the advice it guards had been shown. The urgency lead printing unscreened model text first. Both times the type was structured — **a type constrains shape, not content, and it does not constrain ordering at all.**'],
  ],
  [1900, 3900, 3560],
));

A(spacer(140));

A(callout('**The byte boundary is asserted on the bytes, at the composition root — never in the module that composes the answer.** A guard that is right in the core and wrong at the edge is not a guard, and that is precisely where every defect the first external review found was living.'));

A(h3('7.3.2  The sequence, and what each step does when it fails'));

A(p('**A step\'s failure behaviour is part of its specification.** A sequence that says only what happens when everything works is the half of the contract that never mattered.'));

A(table(
  ['#', 'Phase', 'Step', 'On failure'],
  [
    ['1', 'ADMIT-A', 'Authenticate; resolve the advocate identity and firm.', 'Refuse the turn. Disclose nothing about which matters exist.'],
    ['2', 'ADMIT-A', '**Classify the route** — matter or non-matter — and infer the mode. State the reading in one line.', 'Ambiguity resolves to **matter**, because a full workup on a question is wasteful while a matter read as a greeting is negligent. The reading is stated so it can be corrected.'],
    ['3', 'ADMIT-A', '**Minimal emergency triage** — danger, liberty, an irreversible step. On NAMES AND THE DANGER ONLY.', 'Tenet 6 is prior to tenet 3: an advocate whose client is being arrested tonight is not told to wait for a conflict check. **Limited to naming the danger, the protective step, its owner and time, and a referral.** Merits, strategy and drafting are refused, and nothing substantive is retained.'],
    ['4', 'ADMIT-A', '**Names-only conflict screen** — parties, counterparties, related entities. Nothing else is read.', '**An incomplete screen never clears.** A registry unreadable in part produces `incomplete`, which blocks what it guards. An empty registry is reported as empty — a gate that has never refused is not evidence.'],
    ['5', 'ADMIT-A', 'Competence, engagement and scope screens.', 'Recorded on the matter and sticky. A limit released by a human keeps the finding visible.'],
    ['—', '', '**⟨ SCREEN BOUNDARY — nothing below runs, and NO PROVIDER CALL is made, until the screens have returned ⟩**', 'This is the boundary the first draft of this document got wrong: it extracted and bound documents BEFORE screening, which both retained substance on an uncleared file and sent privileged content to a model provider.'],
    ['6', 'ADMIT-B', 'Take in documents; extract; gate on confidence; always confirm dates, amounts, names and roles.', 'Extraction failure is a **visible gap**, never an empty result. An unreadable document contributes no facts and says so.'],
    ['7', 'ADMIT-B', 'Integrate facts — surface conflicts, detect corrections, mark materiality.', 'A conflict is never resolved to proceed. It is carried.'],
    ['8', 'ADMIT-B', 'Bind to threads. **Propose merges, never perform them.**', 'An unbindable document contributes no facts and never defaults to a thread.'],
    ['9', 'DERIVE', 'Invalidate the dependents of every changed material fact.', 'A dependency that cannot be resolved marks its dependents stale rather than leaving them confidently current.'],
    ['10', 'DERIVE', 'Recompute dirty derivations in dependency order. **Blocking gates short-circuit** — an unresolved posture means the thread\'s downstream derivations are not computed at all.', 'A short-circuit is a **question**, not a silent omission. Nothing wrong is generated and nothing is paid for.'],
    ['11', 'DERIVE', 'Emit `EvidenceNeed`s; receive verified `Finding`s. **Bounded rounds** (§7.3.5).', 'Adapter failure **fails the need, not the turn.** The gap is visible in the answer.'],
    ['12', 'DERIVE', 'Cross-file, serially: adversarial pass, cross-thread exposure, salvage, selection.', 'Cross-thread exposure is reported **or expressly returned as none**. Silence is not a pass.'],
    ['13', 'DERIVE', 'Gap queue → the single highest-value next action.', 'An empty queue is a valid outcome and produces a turn that says so in a line.'],
    ['14', 'DERIVE', 'Assemble the Answer, board projection and case summary — all three derived from the same state.', 'An element that is none of the four permitted kinds cannot be constructed.'],
    ['15', 'DERIVE', '**Assert invariants.** Class-B checks run here, on the assembled object.', 'A **grounding** violation gates the output. Every other violation is recorded in `TurnMetrics.violations` and the answer still ships.'],
    ['—', '', '**⟨ BYTE BOUNDARY ⟩**', 'Nothing above this line has been shown or saved. Nothing below can be undone.'],
    ['16', 'EMIT', '**Commit** — state and metrics, atomically (§7.3.4).', 'A failed commit fails the turn *before* anything is shown. The advocate never receives advice the file does not record.'],
    ['17', 'EMIT', 'Release to the transport.', 'A transport failure after commit is a delivery problem, not a state problem: the turn is recoverable on reconnect.'],
  ],
  [400, 900, 4600, 3460],
));

A(spacer(140));

A(p('**Per-thread recomputation in step 10 runs in parallel; everything cross-file in step 12 runs after it, serially**, because each cross-file pass needs every thread settled to be correct.'));

A(h3('7.3.3  Streaming, and why it does not move the byte boundary'));

A(p('Streaming is wanted — a three-minute turn that shows nothing for three minutes is a poor product. But **streaming is the mechanism by which every ordering guarantee in this document was previously lost**, so it is constrained rather than assumed.'));

A(table(
  ['Rule', 'Why'],
  [
    ['**What streams is the assembled Answer, never raw model output.**', 'The model produces content *into* the Answer; the Answer is what reaches the transport. A step that pipes provider tokens straight through has moved the byte boundary and is a defect however good it looks.'],
    ['**Nothing streams before the invariant assertion has completed for the elements being streamed.**', 'Progressive disclosure of *screened* content is fine. Disclosure of content whose screen has not returned is the exact measured defect.'],
    ['**Progress is not content.** While DERIVE runs, what may be shown is which stage is running — not what it is producing.', 'This gives the advocate the responsiveness streaming is for, without putting unscreened prose on the wire.'],
    ['**A streamed call is a call.** Tokens, cost and latency are recorded identically to a non-streamed one.', 'A streamed turn once recorded `llm_calls: 0`, which made an entire turn invisible to the cost baseline.'],
    ['**A stream that dies mid-flight leaves committed state**, because commit precedes emission.', 'A turn that wrote its whole opinion and then died on a context reset left the advocate with nothing and the file with nothing.'],
  ],
  [3400, 5960],
));

A(spacer(140));

A(h3('7.3.4  Atomicity, restart and idempotency'));

A(callout('**A turn commits once, in EMIT, or not at all.** There is no state in which half a turn has been applied — no thread created without its posture, no fact integrated without the derivations that depend on it marked stale, no urgency raised without its register entry.'));

A(
  bullet('**The commit point precedes emission.** The advocate never receives advice that the file does not record. This ordering is the opposite of the intuitive one and it is deliberate: it is better to fail before showing than to show and fail to save.'),
  bullet('**Restart resumes from the last commit, and every gate holds.** A process that dies during DERIVE loses that turn\'s work and loses nothing else. A screen that had returned `clear` before the crash is still `clear`; one that was `not_assessed` is still `not_assessed` and still blocking.'),
  bullet('**Turns are idempotent under retry.** A turn carries a client-supplied identifier; replaying it returns the committed result rather than applying it twice. Without this, a network retry duplicates facts, splits threads, and re-raises resolved urgencies — and the duplicate is invisible.'),
  bullet('**Metrics are written even when the turn fails.** A turn that crashed at step 9 must still leave `TurnMetrics` with its stages and its failure, or the most diagnostically valuable turns are the only ones with no record.'),
);

A(h3('7.3.5  Every bound is stated, and reaching one is a visible event'));

A(p('Three loops in a turn can run away. Each has a declared bound, and **reaching a bound is reported rather than absorbed** — an unbounded loop makes a turn unmeasurable, and a silently truncated one makes it wrong.'));

A(table(
  ['Bound', 'What it limits', 'What happens when it is reached'],
  [
    ['**Evidence rounds**', 'The need → fulfil → recompute cycle in steps 10–11.', 'Recomputation stops and **the unfulfilled needs become visible gaps in the answer**. It never proceeds as though the evidence had been found. The bound is a design constant with no measurement behind it yet, and it is tracked in the baseline as such rather than in prose.'],
    ['**Model calls per turn**', 'Total across all tiers.', 'Recorded and surfaced. The previous build measured 58 calls on a five-dispute file, and document intake, the adversarial pass and selection are all additive to that.'],
    ['**Context budget per call**', 'Declared per tier at the port (§7.4.4).', 'A typed error, never a truncation. **Silent truncation produces an answer that looks complete and was reasoned from a fraction of the material.**'],
  ],
  [1600, 3200, 4560],
));

A(spacer(140));

A(h3('7.3.6  Concurrency on one matter'));

A(p('An advocate can send a second message while the first turn is running, and a document upload can land mid-turn. **Two turns must never derive from the same matter state concurrently**, because the derivation graph would interleave invalidations and both answers would be computed from a state neither of them saw.'));

A(
  bullet('**Turns on a matter are serialised.** A second turn queues rather than racing, and the advocate is told it is queued rather than left waiting silently.'),
  bullet('**A commit is conditional on the state version it derived from.** If the matter moved underneath, the turn re-derives against the current state rather than overwriting — the same discipline the correction cascade uses.'),
  bullet('**A document arriving mid-turn is admitted to the next turn, not spliced into the running one.** Splicing it would put facts into a DERIVE phase that has already passed the screen boundary.'),
);

A(spacer(140));
A(p('*Evals for §7.3:* **Class A** — no substantive derivation is reachable on a matter with a `not_assessed` gating screen; a turn commits atomically or not at all; replaying a turn identifier returns the committed result rather than reapplying; reaching an evidence bound produces visible gaps. **Class B, on every served turn** — the first byte released is preceded by a completed invariant assertion, checked at the composition root on the bytes themselves; a streamed call records its tokens and cost. **Class D** — a killed process mid-DERIVE resumes with every gate at its pre-crash standing (portfolio journey JP-5).'));

A(h2('7.4  Model and cost policy'));

A(h3('7.4.1  Four tiers, not two'));

A(p('**Steps declare a TIER. They never name a model.** This is the whole of the model-agnostic design in one rule, and everything below follows from it.'));

A(callout('**A first draft of this section had two tiers, and two tiers cannot express two rules this document already commits to.** Tenet P4 says *the judge is never the model that produced the answer* — with only `routine` and `hard`, a judged run on a `hard` step would be graded by the model that wrote it, which is the correlated-failure case P4 exists to prevent. And embeddings are model calls with an entirely different lifecycle (§7.4.2). **Neither rule has a mechanism unless the tier is the thing that carries it**, so there are four.', SIGNAL));

A(table(
  ['Tier', 'Model today', 'Used for', 'The rule that governs it'],
  [
    ['**`routine`**', '**OpenAI `gpt-4o-mini-2024-07-18`**', 'Everything the product serves: extraction, classification, summarisation at ingest, treatment reading, the entailment first pass, question phrasing, the ordinary advising turn.', 'What a step gets unless a **measured** quality difference says otherwise. Today it is the only serving tier.'],
    ['**`hard`**', '**NOT CONFIGURED**', 'Reserved for genuinely complex reasoning — case theory formation, the adversarial pass at its strongest, salvage coordinate variation.', '**Deliberately absent, and that is the honest state.** Escalation is earned by measurement and nothing has earned it yet. Requesting this tier raises `TierUnavailable` **with that reason** rather than silently serving from `routine` — a silent downgrade is defect shape S1 wearing a performance optimisation.'],
    ['**`judge`**', '**OpenAI `gpt-5.1`**', 'Class-D judged evaluation only. Never on a serving path.', 'Genuinely different from the model under test, which is what makes P4 enforceable rather than aspirational. **Resolving `judge` to the same model as a serving tier is a configuration error that fails at startup**, not a warning.'],
    ['**`embed`**', 'The model the indices were **built with** — not a free choice at run time', 'Dense retrieval over the corpus.', 'Changing it invalidates every vector in the corpus. **It is not switchable by configuration.** See §7.4.2.'],
  ],
  [1100, 1900, 3200, 3160],
));

A(spacer(140));

A(callout('**The escalation must be earned, and the drift runs one way.** Every step will look like it deserves the stronger model, because the stronger model always reads better on a sample of one. **A step is promoted to `hard` only with a measurement attached, recorded in the baseline with the figure that justified it.** And demotion needs a cadence or it never happens: every `hard` step is re-measured on the quarterly review, and one whose advantage cannot be reproduced is demoted rather than grandfathered.'));

A(callout('**Three states, not two, at the tier level as everywhere else.** A tier is *configured*, *not configured*, or *configured wrong* — and the second is a legitimate state that must be distinguishable from the third. `hard` being absent is a real answer with a reason, surfaced as `TierUnavailable`; it is not the same thing as a missing environment variable, and neither is silently equivalent to serving from `routine`.'));

A(h3('7.4.2  Provider independence — a hard requirement, not a nicety'));

A(p('**The product must survive a change of model provider as an environment-variable change.** Access to other APIs is expected, and on the day it arrives the switch must not be a refactor.'));

A(table(
  ['Requirement', 'What it means concretely'],
  [
    ['**One `ModelPort`, declared by the core**', 'The core declares the interface; `adapters/model/` holds one implementation per provider — `openai.py`, `anthropic.py`, and whatever follows. The core never imports a provider client. The existing layering lint already fails the build on any such import.'],
    ['**Steps name a tier, never a model**', 'A step says `tier="routine"`. The mapping from tier to provider and model id lives in configuration, read from `.env`. **A model identifier appearing anywhere in `core/` is a defect**, checkable by grep and enforced as a class-A test.'],
    ['**The port contract is the INTERSECTION of what providers offer, not the shape of one of them**', 'This is where provider abstractions usually fail. If the port exposes OpenAI\'s parameter names, its function-calling JSON shape, or its `logprobs`, then the abstraction is OpenAI wearing an interface and the second adapter will not fit it. **The port speaks in the product\'s vocabulary — a prompt, a schema, a tier, a cacheable prefix — and each adapter translates.**'],
    ['**Structured output is abstracted at the port, not at the call site**', 'The hardest part of provider portability. Providers differ on JSON mode, tool use and schema enforcement. The port exposes a single `structured(prompt, schema, tier)` and each adapter maps it to whatever that provider does. **A call site that constructs a provider-specific tool definition has leaked the provider into the core.**'],
    ['**Prompt caching is a port concept with an adapter-specific implementation**', 'The port marks a cacheable prefix; an adapter that supports caching uses it, one that does not **no-ops silently and reports zero cache hits**. The product must not behave differently, only cost differently.'],
    ['**Token and cost accounting is normalised**', 'The port returns `{in, out, cost}` in one shape. Provider-native extras are carried opaquely for diagnostics and are never read by the core. Otherwise `TurnMetrics` becomes provider-shaped and the cost baseline stops being comparable across a switch.'],
    ['**Everything switchable lives in `.env`**', '`NM_MODEL_PROVIDER` · `NM_MODEL_ROUTINE` · `NM_MODEL_HARD` · `NM_MODEL_JUDGE` · `NM_MODEL_BASE_URL` · `NM_MODEL_API_KEY` · `NM_MODEL_PROVIDER_<TIER>` to point one tier at a different provider without moving the rest. **Each tier variable holds a pinned dated snapshot, never a floating alias** (§7.4.3). `NM_EMBED_MODEL` is present but is **read and verified against the indices, not chosen** (§7.4.2 carve-out). **No other file changes when the provider changes.**'],
    ['**Failure and rate-limit behaviour is normalised too**', 'Providers signal rate limits, context overflow and content refusals differently. The port raises the same small set of typed errors so the retry, degrade and fail-the-need-not-the-turn policies in §7.4.4 hold identically whichever adapter is live.'],
  ],
  [2700, 6660],
));

A(spacer(140));

A(callout('**THE EVAL THAT ACTUALLY PROVES THIS, and it is the only one that does: switch the provider and re-run the golden set.** An abstraction nobody has switched is an unexercised claim — the same shape as a guard with no production caller. So the requirement is not "there is a ModelPort"; it is that **a scripted adapter and at least one real adapter both pass the same port contract suite, and the golden set passes with `NM_MODEL_PROVIDER` flipped and nothing else changed.** Until that has run, provider independence is `decided`, never `tested`.'));

A(h4('The carve-out — and the claim above is false without it'));

A(p('**Embeddings do not switch by environment variable, and saying they do would be the most expensive kind of wrong.** The corpus indices are built *from* a specific embedding model. Query an index built with model A using model B\'s vectors and it does not error — **it returns plausible, confidently wrong neighbours**, which is the worst failure this system can have and the hardest to notice.'));

A(table(
  ['', 'Switching `routine`, `hard` or `judge`', 'Switching `embed`'],
  [
    ['Cost of the change', 'An environment variable', '**A full re-index of the corpus** — 22GB across `bareacts_v3`, `caselaws_v2`, the summary stores and BM25'],
    ['Time', 'Immediate', 'Hours to days, offline, on the knowledge plane'],
    ['Failure mode if done wrong', 'The adapter errors, loudly', '**Silent.** Retrieval quality degrades and every downstream answer is confidently wrong'],
    ['What protects it', 'The port contract suite', '**Defect-shape S11:** every index records the identity of the embedding model it was built from and is **REFUSED on mismatch**, never used with a warning'],
  ],
  [2100, 3600, 3660],
));

A(spacer(140));

A(p('So `embed` is configuration that is **read and verified, never chosen at run time**. A change to it is an ingest project with its own re-baselining, and it is planned as one.'));

A(h3('7.4.3  Reproducibility — an unpinned model makes the baseline meaningless'));

A(callout('**`gpt-4o-mini` is an alias, not a version.** Providers move aliases to new snapshots. If the model changes underneath the product, a metric that moved is indistinguishable from a regression you caused — and the entire measurement discipline in Part 8 rests on being able to tell those apart.', SIGNAL));

A(table(
  ['Rule', 'Detail'],
  [
    ['**Every tier pins a dated snapshot, never a floating alias**', 'Configuration holds the exact versioned identifier the provider offers, and the resolved identifier is recorded on every call in `TurnMetrics`. An alias in configuration fails the class-A check.'],
    ['**A snapshot change is a release, not an update**', 'Moving a pin re-baselines the quantities in §8.8 and is recorded with a stated reason, exactly like any other deliberate baseline move. **A snapshot that changed without anyone deciding it should is a defect to be reported**, not a fact to be absorbed.'],
    ['**Sampling parameters are fixed and recorded**', 'Temperature, top-p and seed where the provider supports them, declared per tier. Evaluation runs use the fixed values; a step that needs variation declares it.'],
    ['**Determinism is bounded honestly**', 'Even a pinned snapshot at temperature zero is not bit-reproducible across a provider\'s own infrastructure. So an eval that depends on exact output text is the wrong eval — **class-A and class-B checks assert structure and invariants, never string equality with a stored answer.**'],
    ['**Prices are configuration, versioned with the pin**', 'Cost is tokens × price, and price changes. A price table lives beside the pins so a cost figure in the baseline is auditable and comparable across time, rather than a number nobody can reconstruct.'],
  ],
  [2900, 6460],
));

A(spacer(140));

A(h3('7.4.4  Degradation — what happens when a tier is unavailable'));

A(p('A provider rate-limits, times out, or refuses. The question is what the product does next, and there is exactly one wrong answer.'));

A(callout('**A `hard` step must never silently fall back to `routine`.** That is defect shape S1 wearing a performance optimisation: the answer still appears, in the same shape, with no sign that the reasoning behind it was done by the cheaper model. **A tier downgrade is recorded in `TurnMetrics`, surfaced in diagnostics, and where it affected a case theory, an adversarial pass or a salvage route, it is stated in the answer.**', SIGNAL));

A(table(
  ['Situation', 'Response'],
  [
    ['Rate limit or transient failure', 'Bounded retry with backoff, inside the turn. Retries are counted in `TurnMetrics` — an invisible retry is an invisible cost.'],
    ['The tier remains unavailable', '**Fail the need, not the turn.** The gap becomes visible in the answer, exactly as an unavailable index does. A turn that dies because one model call failed is worse than a turn that says what it could not establish.'],
    ['A deliberate downgrade is configured', 'Permitted, and **never silent** — recorded, surfaced, and stated in the answer where it touched a judgement-tier output.'],
    ['Context overflow', 'A typed error, not a truncation. **Silent truncation is the same defect one layer down** — the answer looks complete and was reasoned from a fraction of the material.'],
    ['Structured output fails its schema', 'Bounded retry, then a typed failure. **Never best-effort parsed.** Lenient parsing is how an invented vocabulary once entered the system and emptied a charge map; an unrecognised value is treated as absent, never as valid.'],
    ['The provider refuses on content', 'Surfaced as itself, never reported as a legal finding. A refusal about a violent assault is a provider behaviour, not a fact about the matter.'],
  ],
  [2400, 6960],
));

A(spacer(140));

A(h4('The context budget belongs to the port, not to the provider'));

A(p('Providers differ by an order of magnitude in context window. **A prompt built to fill one provider\'s window does not port**, and discovering that at switch time defeats the whole design. So each tier declares a **context budget** in the port, chosen as what the smallest supported provider can hold, and steps are built to the budget. An adapter whose model cannot hold the declared budget fails the contract suite rather than truncating at run time.'));

A(h3('7.4.5  Provider choice is a confidentiality decision, not only a technical one'));

A(callout('**Every model call sends privileged client material to a third party.** This is a product for advocates, and tenet 1 puts confidentiality and privilege above tactical advantage. A provider switch is therefore never purely an engineering change.'));

A(
  bullet('**Permitted providers are an explicit allow-list**, not "whatever the environment variable says". An unlisted provider fails at startup rather than being used.'),
  bullet('**Data-retention posture is recorded per provider** — zero-retention endpoints where offered, training-opt-out confirmed, and the region the request is served from. This is recorded in configuration next to the pin, so it can be shown rather than remembered.'),
  bullet('**External judges see only synthetic or redacted matters**, which is already the §8.5 rule and belongs here too, because it constrains which provider may hold the `judge` tier.'),
  bullet('**A change of provider is disclosable.** The advocate is entitled to know which third parties process their client\'s material, so the current provider set is a fact the product can state, not an implementation detail buried in a `.env`.'),
);

A(spacer(140));

A(p('*Evals for §7.4 as a whole:* **Class A** — no model identifier or provider client in `core/`; every tier resolves to a pinned dated snapshot, never an alias; `judge` never resolves to the model under test; a tier downgrade is representable and recorded. **Class C** — the port contract suite passes against every registered adapter, including the declared context budget; every index records and matches its embedding-model identity. **Class D** — the golden set passes on a second provider with only environment variables changed, with cost and latency deltas recorded rather than assumed.'));

A(h3('7.4.6  The standing rules'));

A(table(
  ['Rule', 'Detail'],
  [
    ['**Python backend**', 'Fixed. It matches the existing corpus tooling and indices, and the knowledge plane is already Python.'],
    ['**Model choice is decided by measurement, not up front**', 'The cheap tier is the default. A step uses a stronger model only where a **measured** quality difference justifies it, recorded in the baseline. Model choice is a property of the step, declared where the step is defined, so the model mix is derivable without instrumentation scattered through the code.'],
    ['**No latency or cost ceiling — but nothing is free**', 'The objective is the best achievable speed and cost **while holding the quality of a first-rate advocate**. Quality is the constraint; speed and cost are what we minimise subject to it.'],
    ['**Every turn is instrumented**', 'Wall-clock latency, model call count, token cost, model mix, and per-stage latency. Streamed calls are recorded as calls — a streamed turn once logged `llm_calls: 0`.'],
    ['**A change that costs more must show what it bought**', 'In the same measurement. Cost without a demonstrated gain is a regression, not a trade-off.'],
    ['**One recorded baseline, updated deliberately**', '"Did this get worse" is not answerable when the answer is spread across a git log. One record holds the current figure for every measured quantity. It is updated with a stated reason — an improvement moves it, and a justified trade-off moves it with the justification recorded.'],
    ['**Exactly one component owns each prompt**', 'No prompt text is duplicated across two paths and no shared prefix is maintained in two places. A "global" style change once landed in one of two prompt systems and silently applied to half the product — **twice**. The fix is ownership, not discipline: a second path calls the owner rather than copying the text.'],
  ],
  [2600, 6760],
));

A(spacer(140));
A(p('**Known baseline for comparison, from the previous build:** a five-dispute file measured **58 model calls at three to four minutes**, of which retrieval was 13.9 seconds. Document intake, the adversarial pass and the selection stage are all additive to that.'));

A(h2('7.5  Security and confidentiality'));

A(
  bullet('**Matter state is encrypted at rest.** Keys live outside the repository. An unconfigured key is a **hard failure**, never a silent no-op that returns ciphertext as plaintext.'),
  bullet('**Every export is isolated by identity and permission**, never by heading or by convention.'),
  bullet('**No client words in metrics, diagnostics or logs.** The diagnostics whitelist validates values, not only field names.'),
  bullet('**Audit-trail write failures are surfaced**, never swallowed.'),
  bullet('**A permission is bounded at both ends** — matter and step, start and expiry. An authority for one matter never authorises a step on another, and a future-dated authority does not authorise immediately.'),
  bullet('**Document content is data, never instruction.** An uploaded file containing text addressed to the system is treated as content and quoted to the advocate, never acted on.'),
);

A(h2('7.6  The data lifecycle'));

A(p('Tenet 28 requires a matter to be accounted for, exported, and subjected to retention and destruction rules at closure. **Nothing above says what the product actually does with data over time**, and a legal product cannot leave that unstated.'));

A(table(
  ['Stage', 'Rule'],
  [
    ['**Quarantine**', 'Substance received before a conflict screen clears is held **separately from the file** and is released into it exactly once on recorded clearance, or returned/destroyed on refusal with that recorded. Quarantined material is never readable by analysis.'],
    ['**Live**', 'Matter state is encrypted at rest with keys outside the repository. Every derived item carries its provenance and its fact dependencies, so any statement can be walked back to a document page or a retrieved span.'],
    ['**Export**', 'An advocate can export the **usable file** — the case summary, the chronology with provenance, the authorities with binding status, the decision records — in a form another advocate could take the matter over from. **Export is isolated by identity and permission, never by heading.**'],
    ['**Closure**', 'A matter cannot close while an unexplained deadline, asset, original document, client fund or retention obligation remains open. Closure produces an accounting and a closure summary.'],
    ['**Retention**', 'A retention period is recorded per matter and is a **property of the matter, not a global default**, because the obligation varies. The clock starts at closure, and the date is on the file rather than computed from a constant somewhere.'],
    ['**Destruction**', '**Deletion is verified across every store, and reports what it examined.** A deletion that has looked at two stores of eight and reports success is the measured B-93 defect. Destruction is irreversible and therefore always confirmed before it runs.'],
    ['**Lessons**', 'A lessons record may be kept after destruction and **contains no client identifier**. This is the one artefact that outlives the matter, and it is the one most likely to leak.'],
  ],
  [1400, 7960],
));

A(spacer(140));

A(p('*Evals:* **Class A** — quarantined substance is unreachable from analysis and releases exactly once; closure is blocked while any of the five categories is open; a retention date is per-matter and never a global constant. **Class B** — a deletion reports the stores it examined, and a partial deletion is a failure rather than a success; a lessons record contains no client identifier.'));

A(new Paragraph({ children: [new PageBreak()] }));

/* ============ PART 8 — EVALUATION ============ */
A(h1('Part 8 — Evaluation'));

A(h2('8.1  What "done" means'));

A(callout('**A feature is not done because the code looks right, and not because a structural property holds.** The previous build had twelve mechanically-checked properties — persisted, survives restart, cannot be bypassed, has a production caller — and **every one of them passed** on a transcript where the product asked a client who had said *"yesterday"* for the date twice, dropped an assault into a possession cause, and analysed a twelve-year limitation on a trespass a day old. **The twelve measured the plumbing. The client drinks the water.**', SIGNAL));

A(p('So the definition of done has three steps, in order:'));

A(
  num('**The stage passes standalone** — the floor on every turn, plus that stage\'s own DOES, NEVER and PRODUCES checks, plus everything it must have inherited from earlier stages and still hold intact.'),
  num('**The journey portfolio passes end to end**, with **no hand-authored inter-stage state**: every stage receives what the preceding served interaction actually produced.'),
  num('**Only then does the next slice begin.**'),
);

A(p('Structural checks — layering, exception discipline, dead-guard detection — remain in CI as a **linter**. They are necessary, they are not the bar, and every one of them passed on the transcript that caused the rewrite.'));

A(h3('State discipline, stated precisely'));

A(p('**"No hand-authored inter-stage state" is not "no fixtures."** Controlled registries, clocks, corpora, scripted model responses and a real store are all legitimate and necessary. The rule is narrower and sharper: **no test may construct the file that a later stage begins from.** A hand-written provision span that read perfectly and parsed to nothing once hid an entire untestable advice path behind a green suite.'));

A(h2('8.2  The rubric — three layers'));

A(p('Every rubric item returns a **structured verdict**, never a hidden chain of thought: `{ item, verdict ∈ {pass, fail, not_applicable}, evidence (quoted transcript spans), rule (the PRD rule relied on), consequence (what this would do to a real matter), confidence }`.'));

A(callout('**`not_applicable` is a first-class verdict and its applicability is itself tested.** A bare legal question must not fail for creating no engagement record, no posture and no triage — it had no matter. But "not applicable" must be **earned**: each item declares the route it applies to, and a scenario asserts both that applicable items ran and that inapplicable ones were correctly skipped. Otherwise `not_applicable` becomes the hiding place every gate eventually finds.'));

A(h3('Layer 1 — the FLOOR, asserted per named element on every turn'));

A(table(
  ['ID', 'Asserted over', 'Fails when'],
  [
    ['F1.1', 'Each **material fact** stated by the advocate', 'The injury in *"beat him up, injuring his knee"* appears in no fact record'],
    ['F1.2', 'Each **cause of action** disclosed', 'The assault vanishes into a possession cause'],
    ['F1.3', 'Each **party** named', 'A named counterparty never reaches the conflict screen'],
    ['F1.4', 'Each **date** stated, in any form', '*"yesterday"* resolves to nothing; *"28th August 2026"* is stored as 1 January'],
    ['F2.1', 'Each **legal proposition** asserted', 'It is wrong on these facts'],
    ['F2.2', 'Each **computed threshold**', 'A 12-year clock is applied to a one-day-old trespass'],
    ['F3.1', 'Each **question NM asks**', 'It asks for something already given'],
    ['F3.2', 'Each **fact already on file**', 'It is contradicted without being flagged as a correction'],
    ['F4.1', 'Each **finding recorded earlier**', 'It is absent now, with no recorded resolution'],
    ['F4.2', 'Each **urgency raised earlier**', 'Its standing changed without a named resolver'],
    ['F5', 'Each **citation**', 'Its passage cannot be read back from the corpus'],
    ['F6', 'The **turn**', 'It contains neither a recommendation nor a blocking question'],
    ['F7', 'Each **element of the answer**', 'It is none of the four permitted kinds'],
    ['F8', 'Each **loud-signal item**', 'It appears below the fold or in collapsed content'],
    ['F9', 'The **turn**', 'Register is not senior counsel addressing an instructing advocate'],
    ['F10', 'The **turn**, where the advocate changed subject', 'NM refused to follow'],
  ],
  [700, 3200, 5460],
));

A(spacer(140));

A(h3('Layer 2 — stage items: DOES / CARRIES / NEVER'));

A(p('**A stage rubric that only tests its own stage is a weak rubric.** DOES asks what this stage must do; **CARRIES asks what it must have inherited from every earlier stage and still hold intact**; NEVER asks what it must not do. CARRIES is cumulative and explicit — worked example at the conflict screen, which is where the observed failure happened:'));

A(table(
  ['B3.CARRIES', ''],
  [
    ['← from B1', 'Thread identity, posture, every fact stated in the opening'],
    ['← from B2', 'Every urgency raised, at its recorded standing, owner and date — **and a live emergency still LEADS after the conflict screen runs**'],
  ],
  [1800, 7560],
));

A(spacer(140));
A(p('**That single item would have caught the transcript failure at the conflict screen\'s own gate.**'));

A(h3('Layer 3 — journey items, each of which no stage rubric can hold'));

A(table(
  ['ID', 'The question', 'Why it cannot live in a stage'],
  [
    ['**J1**', 'Did the advocate get what they came for?', 'The goal spans the journey'],
    ['**J2**', 'Does any turn contradict an earlier one without saying it is a correction?', 'A relation between two turns'],
    ['**J3**', 'Was anything established and then silently lost?', '**The sweep.** CARRIES names what to check; this quantifies over everything, including what nobody anticipated'],
    ['**J4**', 'Is answer length a function of live threads, not turn number?', 'A trend is invisible at a point'],
    ['**J5**', 'Would a senior advocate have done better, and how?', 'Judgement on the representation, not on a step'],
  ],
  [700, 4400, 4260],
));

A(spacer(140));

A(h3('Precedence, when items conflict'));

A(p('Stated, because two correct rules can demand opposite things and an unstated precedence is resolved differently by every judge.'));

A(
  num('**Safety and liberty outrank everything.** Where an urgency is material, it leads — over brevity, over route, over the advocate\'s chosen subject.'),
  num('**A duty refusal outranks helpfulness.** The block *is* the answer.'),
  num('**Route outranks completeness.** On the non-matter route, absent matter apparatus is `not_applicable`, never a failure.'),
  num('**Brevity outranks recitation, never signal.** A cleared screen that is asked about is answered; it is not repeated every turn unprompted.'),
  num('**A blocking question outranks a recommendation, and a material emergency outranks both.**'),
);

A(h2('8.3  The journey portfolio'));

A(p('One enormous A-to-Z transcript would create state no real matter ever has, and make a failure at turn 40 undiagnosable. The gold eval is therefore a **portfolio**: one canonical journey plus targeted journeys that can only be reached deliberately.'));

A(table(
  ['Journey', 'What it exists to reach'],
  [
    ['**JP-1 canonical**', 'The ordinary path, end to end, nothing exceptional'],
    ['**JP-2 outage**', 'Registry, model or store unavailable — every screen fails closed and says so'],
    ['**JP-3 conflict**', 'A registry hit, quarantine, human clearance, a single release'],
    ['**JP-4 emergency**', 'Urgency raised, carried across turns, resolved by a named person, not re-raised'],
    ['**JP-5 restart**', 'The process dies mid-matter and every gate holds'],
    ['**JP-6 non-matter**', 'Greetings, questions about NM, bare legal questions — **nothing written to any file**'],
    ['**JP-7 correction**', 'A material fact corrected at turn 7 re-derives everything and supersedes prior advice'],
    ['**JP-8 multi-thread**', 'Five disputes on one file, opposite postures, cross-thread exposure'],
  ],
  [2200, 7160],
));

A(spacer(140));

A(h2('8.4  The golden set'));

A(p('**Twenty-five conversations, each anchored on a real corpus judgement verified to exist, to be attributable, and to be readable back**, with every provision retrieved verbatim. **31 anchors verified, 42 provisions held.** All anchors are Andhra Pradesh High Court judgements, binding for a Telangana matter. The set lives in `docs/GOLDEN_SET.md`.'));

A(h3('The set is a filter, not a run'));

A(p('**Twenty-five scenarios are not twenty-five runs.** Each carries four tags, and a run is a query over them — which is what makes a large, diverse set affordable rather than a burden.'));

A(table(
  ['Tag', 'Values', 'What it decides'],
  [
    ['**`tier`**', '`smoke` · `standard` · `deep`', 'What it costs. `smoke` is one to three turns and needs no judge model. `deep` needs a class-D judged run, and therefore explicit approval.'],
    ['**`slice`**', 'S1 … S9', '**The earliest slice at which it can run at all.** A theory scenario run at S4 fails for the wrong reason and teaches nothing.'],
    ['**`area`**', 'bail · land · matrimonial · cheque · service · institutional · …', 'Practice-area diversity, so a principle is not only ever tested in one body of law.'],
    ['**`forces`**', 'the principles it exercises', 'What actually breaks if it fails.'],
  ],
  [1200, 3000, 5160],
));

A(spacer(140));

A(table(
  ['Suite', 'Contents', 'Run it'],
  [
    ['**`smoke`**', 'Route, refusal, injection and jurisdiction defences. Five scenarios, seconds, no judge.', '**Every commit.** Catches the cheapest and most embarrassing regressions.'],
    ['**`frame`**', 'Posture, threads, triage. Six scenarios.', 'When you touched posture, thread identity, gates or emergency triage.'],
    ['**`dates`**', 'Chronology, limitation, deadlines, the era rule. Five scenarios.', 'When you touched anything that computes a date.'],
    ['**`proof`**', 'Evidence, admissibility, elements, burden. Four scenarios.', 'When you touched the proof position.'],
    ['**`grounding`**', 'Retrieval, citation, coverage, the entailment gate. Five scenarios, drawn across suites.', 'When you touched the evidence path.'],
    ['**`theory`** · **`duty`**', 'Theory, adversarial, salvage · refusals, conflict, candour, drafting. Judged.', '**Approval required.** At a slice close and before a release.'],
    ['**`slice-N`**', 'Everything whose earliest slice is ≤ N.', '**At a slice close, before declaring it done.**'],
    ['**`full`**', 'All 25, judged.', 'Release candidates only. **Approval required.**'],
  ],
  [1500, 4400, 3460],
));

A(spacer(140));

A(callout('**The rule that keeps selection honest: a suite is a FILTER over the set, never a different set.** Adding a scenario to a suite is free. Writing a scenario that exists only inside one suite is how coverage quietly rots — so a class-A check asserts that every scenario is reachable from at least one suite and none is reachable from only one.'));

A(h3('Coverage is tracked, and thin coverage is named'));

A(p('`docs/GOLDEN_SET.md` §5 maps every principle to the scenarios that force it. **An empty row is a hole; a row with one mark is fragile.** Six principles are currently covered exactly once — the jurisdiction boundary, the second-cause catch, contradiction preservation, cross-thread exposure, putting the opposing case at strength, and custody with preservation. **Eleven further anchors are verified and unscripted**, held as a reserve pool so the next scenarios are a selection from measured candidates rather than a fresh search under time pressure.'));

A(spacer(140));

A(callout('**The golden set is sampled, never authored — and the encoded scenarios are not yet a sampled set.** They are anchored on verified authority, which makes them a far better starting point than composed scenarios on unverified authority, but the rule stands: **evaluation material for any extraction or judgement task is drawn by random sample from real matters and hand-vetted.** A composed example may illustrate; it may not support a measurement. **The gold set\'s provenance is recorded — sampling method, seed, size, and who vetted it.**'));

A(h2('8.5  Judge policy'));

A(table(
  ['Rule', 'Detail'],
  [
    ['**Two judges, and most assertions need neither**', 'Deterministic code judges state, dates, gate outcomes, persistence, citations readable back, ordering and forbidden output. A version-pinned model judges register, material omission, decisiveness, coherence and senior-advocate quality.'],
    ['**The judge is never the model that wrote the answer**', 'A model that produced a straw-man opposing case will judge that case strong. Same model, same blind spot, correlated failure — the evaluation returns a clean bill precisely where it is needed most.'],
    ['**Every model-judged item ships with an accepted counterexample**', 'A transcript it must reject. **An item that has never failed is not coverage** and is reported as uncovered.'],
    ['**Every judge run stores its own provenance**', 'Prompt, model, version, structured verdict, cited spans, latency and cost.'],
    ['**Agreement with human labels is measured before the number is used**', 'And re-measured periodically. Low-confidence verdicts are routed to a human rather than averaged away.'],
    ['**External judges see only synthetic or redacted matters**', 'Client material does not leave.'],
    ['**One approval covers a bounded batch, not each scenario**', 'And golden or end-to-end runs are never initiated without it.'],
  ],
  [3000, 6360],
));

A(spacer(140));

A(h2('8.6  The error-analysis loop — the actual job'));

A(p('Everything above is apparatus. **This loop is where the product is made, and it does not end.** It runs on a fixed cadence with a named owner, not when someone has time.'));

A(
  num('**Run** the golden set and any sampled live traffic through the real served path.'),
  num('**Open coding** — read every trace and write a free-form note on what is wrong. No categories yet, no fixing yet.'),
  num('**Axial coding** — group the notes into five to ten named failure modes.'),
  num('**Count** them. Now there are frequencies rather than impressions.'),
  num('**Diagnose the gulf** for the largest bucket — comprehension, specification or generalisation — before choosing a remedy.'),
  num('**Fix the largest bucket, and only that one.**'),
  num('**Re-run.** Did the number move? If not, the diagnosis was wrong and the loop restarts at step 5, not at step 6.'),
);

A(callout('**If you are not willing to look at traces manually on a regular cadence, the evaluation apparatus is decoration.** Automated metrics tell you *that* something changed. Only reading the output tells you *what* is wrong, and the taxonomy that comes out of reading is what every automated evaluator is then built from.'));

A(h2('8.7  Cumulative regression — the discipline that was missing'));

A(callout('**The previous build had no cumulative suite. Each fix was verified in isolation, so fix 14 silently broke fix 6 and nobody found out until a live session. This is the direct cause of the reported symptom that every piece of work introduced a new defect somewhere else.**', SIGNAL));

A(
  bullet('**Every slice\'s evals become permanent on the day the slice closes**, and run on every change thereafter.'),
  bullet('**Slice N is not done until slices 1..N all pass together.** Not "the new tests pass" — all of them, in one run.'),
  bullet('**Every defect found anywhere becomes a permanent case** in the stage it belongs to, and runs forever after.'),
  bullet('**A red suite blocks the merge.** Class A on every commit, class B at runtime on every turn, class C on every ingest, class D on approved batches.'),
  bullet('**A class-B half whose class-D partner has not run on its stated cadence is reported as unverified, not as passing.**'),
);

A(h2('8.8  The baseline record'));

A(p('One record holds the current figure for every measured quantity, so that *"did this get worse"* is answerable. It is **updated deliberately, with a stated reason** — an improvement moves it, a justified trade-off moves it with the justification recorded. Treating it as a freeze, where every change is scored as a regression, is the over-application failure.'));

A(table(
  ['Quantity', 'Why it is tracked'],
  [
    ['Turn latency, model calls, token cost, model mix', 'A change that costs more must show what it bought'],
    ['Retrieval recall@k on a sampled set of (matter, governing provision) pairs', 'The only measure of whether resolution and search are working'],
    ['Resolution coverage — share of needs answered structurally vs by search', 'Determines whether the graph curation is repaying its cost'],
    ['Grounding gate trigger rate', 'A rising rate means retrieval is degrading; a zero rate means the gate is not wired'],
    ['Flag rate per matter, and the share the advocate acts on', 'Miscalibrated flags are a defect in the flagging'],
    ['Answer length against live-thread count and turn number', '**The recitation-bloat regression metric**'],
    ['Issues spotted vs issues accounted for by disposition', 'The silent-drop metric. Measured at 20.1% loss in the previous build'],
    ['Judge agreement with human labels, per item, with version', 'Without it every class-D number is unfounded'],
    ['Corpus coverage per court, per Act, per store', 'Rebuilt on every ingest'],
  ],
  [4000, 5360],
));

A(new Paragraph({ children: [new PageBreak()] }));

/* ============ APPENDICES ============ */
A(h1('Appendix A — Defect shapes and the check that refuses each'));

A(p('**164 defects were reproduced in the previous build. They are not 164 different mistakes** — they are eleven shapes, each recurring across unrelated components. The register already listed its own recurring shapes at the top, in bold, and then **three of its own measured claims fell to the shape sitting first in that list.**'));

A(callout('**A shape that is written down is not a shape that is defended against. Only a check is.** Every shape below therefore carries a check that structurally refuses it, and a counterexample the check must reject.', SIGNAL));

A(table(
  ['Shape', 'The check that refuses it', 'The counterexample it must reject'],
  [
    ['**S1 · An absent input reads as success**\nThe most repeated defect, across four separate controls.', 'Three states everywhere — held, not held, **not assessed** — and the third is visible in the output, not merely representable in the type. `unknown` is a value, never a null and never a default.', 'A matter where the conflict registry was unreadable and the output says the screen is clear.'],
    ['**S2 · A guard with no production caller**\nCorrect in the type, consulted by nothing.', 'Every guard is proven by a test that drives the **served path on the wire**, not the module that defines it. A guard with no production caller fails the build.', 'A green suite on a build where the streaming entry point does not exist, so no test ever reached the advice path.'],
    ['**S3 · A zero result from the wrong index**', 'A zero result **names the index it came from**. Coverage is a **union across every store and identifier convention**, never a lookup in one.', 'A query for Specific Relief Act s.6 that returns nothing from the thin store and reports the remedy as unavailable.'],
    ['**S4 · State that dies with the turn or the process**', 'Anything the advocate can rely on **survives a process restart**, proven by a test that actually restarts the process.', 'An urgency raised at turn 1, still live, absent from the file after a restart.'],
    ['**S5 · Model prose escapes before the screen that guards it**\nBoth measured times the type was structured — **a type constrains shape, not content.**', 'No model-generated text reaches the transport before every screen governing it has returned. Ordering is asserted **on the bytes leaving the process**, not in the module that composes the answer.', 'A streamed turn whose first token is model prose and whose duty screen returns after it.'],
    ['**S6 · A clean verdict from an input known to be incomplete**', '**Incompleteness is contagious.** A verdict computed from an input marked incomplete inherits the mark. A component may never be its own witness.', 'A coverage report that passes because the step that produced it also decided it was complete.'],
    ['**S7 · A test pinned to behaviour instead of a rule**\nAbout fifteen were rewritten in one session, **including one that asserted the very defect it was meant to catch.**', 'A test states the **rule**, writable without naming the Act, section, case or phrase that exposed it, and ships with a counterexample it must reject.', 'A test that passes on the current output and would also pass on the output the rule forbids.'],
    ['**S8 · A patch wearing a fix\'s clothes**', 'State the fix **without naming the instance that exposed it**. Prove it by deleting the specific entry and re-measuring — if the number holds, the fix was general.', 'A treatment classifier that handles every phrasing on its list and misses *"we see no reason to depart from"*.'],
    ['**S9 · Two owners for one truth**', 'The question is never *where is the other copy* but **what makes a second copy impossible.** Exactly one component owns each prompt, each piece of state and each projection.', 'A change to shared instruction text that a grep finds in two files.'],
    ['**S10 · A broad `except` that hides a programming error**', 'Programming errors are caught **separately** and logged at ERROR with a traceback. Renames are swept with a checker that finds undefined and conditionally-defined names.', 'A `NameError` on a live call site that surfaces to the advocate as a degraded answer.'],
    ['**S11 · A derived artefact trusted without its source identity**', 'Every derived artefact records what it was built from and is **refused on mismatch**, not used with a warning.', 'An index whose document count differs from its source\'s and which still answers queries.'],
  ],
  [2400, 3600, 3360],
));

A(spacer(160));

A(h3('How a new control is designed'));

A(p('Before writing one, read the eleven headings. **A new control that has one of these shapes is not new.** Then state, in one line each: which shape it could take; what structurally refuses that shape — not what discipline avoids it; and the counterexample the control must reject, **written before the control**. If the second is a convention rather than a structure, the control is not finished.'));

A(new Paragraph({ children: [new PageBreak()] }));

A(h1('Appendix B — Measured corpus baseline'));

A(p('Measured 29 August 2026. Maintained in `docs/BASELINE.md`; **no claim about coverage is made without naming the store it came from.**'));

A(table(
  ['Quantity', 'Measured'],
  [
    ['Judgements', '33,791 — Supreme Court of India 29,510 (1950–2026); High Court of Andhra Pradesh 4,280 (**1954–2018**); one unnormalised duplicate court label'],
    ['Telangana High Court', '**0** judgements. The binding court for every matter, entirely absent'],
    ['AP judgements post-2018', '**0** — which is what makes the binding decision in §1.5.1 sound today, and `bind-1` necessary'],
    ['Case paragraphs', '1,015,780. Attributable to a court (`ratio` + `reasoning` + `order`): **451,553 = 44.5%**. Counsel\'s submission (`arguments`): **149,960 = 14.8%**. Unclassified: **271,020 = 26.7%**'],
    ['Bare-act chunks', '414,710 across **3,207** distinct act identifiers; `legal.db` holds 1,592 acts and 69,681 sections'],
    ['Limitation Act Schedule', '**137 Articles**, held as `schedule_article` atoms, **absent from the parents layer entirely**'],
    ['The duplicate-identifier problem', 'Specific Relief Act 1963: **13** sections under one identifier, **all 44** under another. BNSS 2023: 162 vs **531**. Muslim Women (Divorce) 1986: 1 vs **7**. `legal.db` declares counts that do not match its own rows'],
    ['Corrected archive claims', 'Three claims carried forward from the previous build were re-measured and did not hold, **all three the same shape** — an empty result from the wrong index, read as absence'],
    ['Judgement→section table', '`case_section_links` holds **0 rows**. *Which authorities interpret this provision* is not answerable from the graph today'],
  ],
  [2600, 6760],
));

A(spacer(160));

A(h1('Appendix C — Glossary'));

A(p('Terms used in this document with a specific meaning. **Where a word here differs from its ordinary use, that is the point** — the vocabulary is part of the design, and the previous build\'s worst naming defect was a label that built *this obstructs us* into a field that had to work both ways.'));

A(table(
  ['Term', 'Means, in this document'],
  [
    ['**Matter**', 'A file. One client, one engagement. **A matter routinely contains several unrelated disputes** — that is the normal case, not the edge case.'],
    ['**Thread**', 'One dispute inside a matter, carrying its own posture, provisions, limitation and urgency. Has a **stable id never derived from its label**.'],
    ['**Posture**', 'Who the parties are and which side the client is on, per thread. `role` is stored and forum-correct; `side` (moving or defending) is **derived from it**. `unknown` is a value that blocks.'],
    ['**Finding**', 'What retrieval returns — never a chunk. Carries proposition, verbatim span, locator, validity window, binding status relative to a named forum, paragraph kind, treatment with scope, and the entailment result.'],
    ['**Proposition vs inference**', 'A **proposition** is a statement of law and must be cited to retrieved primary text. An **inference** is NM\'s reasoning, cannot carry a citation, and must be visibly marked. An inference dressed as a citation is the most dangerous output the system can make.'],
    ['**Disposition**', 'What happens to a spotted issue: `run`, `parked(reason)`, `blocked(needs)`, `closed(reason)`. **There is no delete path** — deleting is silent, a disposition is visible.'],
    ['**Facet**', 'An attribute of an issue — kind, effect, proof, disposition, urgency — as opposed to a single exclusive `track`, which forces mutually-exclusive labels onto things that are not.'],
    ['**Case theory**', 'One sentence per thread: what happened and why we win. Not a menu. **A defending party\'s theory is not "we deny."**'],
    ['**Coverage state**', 'The three-state answer: `ANSWERED`, `NOT HELD`, or `HELD BUT NOT FOUND` — the third being a retrieval **defect** that escalates, never a corpus gap that is disclosed.'],
    ['**Manifest**', 'The **curated** statement of intended coverage. Asserted, not derived from the index — an index can only tell you what is there, never what is missing.'],
    ['**Attributable**', 'A judgment paragraph classified `ratio`, `reasoning` or `order` — the only kinds that may carry a proposition. `arguments` is counsel\'s submission; `unknown` cannot be vouched either way.'],
    ['**Tier**', 'What a step declares instead of a model: `routine`, `hard`, `judge` or `embed`. The tier-to-model mapping lives in configuration.'],
    ['**The screen boundary**', 'The line between ADMIT and DERIVE. No substantive derivation runs on a matter whose gating screens have not returned.'],
    ['**The byte boundary**', 'The line between DERIVE and EMIT. No model-generated prose reaches the transport before every screen has returned and every invariant has been asserted.'],
    ['**Class A / B / C / D**', 'Test classes by what they need: nothing · an answer · the corpus · a rubric and a judge. The class fixes the cadence.'],
    ['**Counterexample**', 'A concrete input a check must **reject**. A check that has never rejected anything is an unexercised claim, not evidence of health.'],
    ['**Suite**', 'A named filter over the golden set — `smoke`, `dates`, `slice-N`, `full`. **A filter over the set, never a different set.**'],
    ['**Defect shape**', 'One of the eleven recurring forms in Appendix A. A new control that has one of these shapes is not new.'],
  ],
  [1900, 7460],
));

A(spacer(200));

A(h1('Appendix D — Parking list'));

A(p('Behaviours that belong to the product and **cannot yet be stated with a runnable check.** They are here rather than in Part 3 precisely because the previous specification\'s failure was rules without runners. Each moves into Part 3 on the day its check can be written.'));

A(table(
  ['Item', 'What is missing'],
  [
    ['Fee estimation and cost against estimate as a live figure', 'No cost model exists in the product. Tenet 27 currently binds only to the extent cost affects advice.'],
    ['Cross-matter learning across a firm', 'Confidentiality boundaries between matters of the same firm are not yet specified, so the check cannot be written.'],
    ['Automatic detection of a positional conflict from the case theory', 'Tenet 30 covers party-based re-screening. Detecting that *the argument we are about to run contradicts one we ran for another client* needs a representation of firm-wide positions that does not exist.'],
    ['Language coverage beyond English', 'Tenet 2 records a translation requirement and moves it to an owner. Actually operating in another language needs corpus coverage that is not held.'],
    ['Quantified outcome prediction', 'Tenet 18 requires scenarios with a basis or an explicit uncertainty statement. A calibrated probability would need outcome data the corpus does not contain.'],
  ],
  [3200, 6160],
));

A(spacer(200));
A(p('*End of document. Version 1.0 · 29 August 2026 · Status: every feature `decided`, nothing built.*', { align: d.AlignmentType.CENTER }));

require('./schemas').render(A);

module.exports = out;
