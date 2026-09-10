const H = require('./helpers');
const { d, h1, h2, h3, h4, p, bullet, num, table, callout, feature, spacer, ACCENT, SIGNAL, CONTENT_W } = H;
const { Paragraph, TextRun, PageBreak, AlignmentType } = d;

const out = [];
const A = (...x) => x.forEach((e) => out.push(e));

/* ===================== TITLE ===================== */
A(
  new Paragraph({ spacing: { before: 2600, after: 0 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: 'NYAYAMALAW', bold: true, size: 64, color: ACCENT, font: 'Georgia', characterSpacing: 60 })] }),
  new Paragraph({ spacing: { before: 160, after: 0 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: 'Product Requirements', size: 34, color: '3E4750', font: 'Georgia' })] }),
  new Paragraph({ spacing: { before: 500, after: 0 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: 'An expert advocate, for practising advocates in India', italics: true, size: 22, color: '5C6670' })] }),
  new Paragraph({ spacing: { before: 1400, after: 0 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: 'End to end — first contact through closure', size: 19, color: '5C6670' })] }),
  new Paragraph({ spacing: { before: 90, after: 0 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: 'Every feature carries the eval that proves it', size: 19, color: '5C6670' })] }),
  new Paragraph({ spacing: { before: 900, after: 0 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: 'Version 1.2  ·  10 September 2026', size: 18, color: '8A939B' })] }),
  new Paragraph({ children: [new PageBreak()] }),
);

/* ===================== PART 0 ===================== */
A(h1('Part 0 — How to read this document'));

A(p('This document defines the **intended product**, not a claim that it is implemented or safe to deploy. Its editable source is `spec/prd/`; regenerate this Word document and `spec/features.yaml` together. Current implementation, evidence and delivery status belong to `docs/backlog/status.yaml`, not to copied status in a document. Where requirement and implementation disagree, record the gap and resolve it explicitly; neither a passing test nor a prose edit silently changes the agreed product.', { comment: 1 }));

A(h2('0.1  Why this document is organised differently from its predecessor'));

A(p('The previous specification was **indexed by topic** — one chapter for grounding, one for posture, one for the shape of an answer, one for the twenty-eight behavioural tenets. Every chapter was sound. The build still failed, and it failed in a specific and diagnosable way: **a buildable slice cuts across every chapter at once.**'));

A(p('To ship one real thing — the opening turn on a fresh brief — required parts of the posture chapter, the intake chapter, the thread-identity chapter, the conversation chapter, the answer-shape chapter and four of the twenty-eight tenets. Eight chapters, none of them finishable on its own, each left with live edges into code that did not yet exist. The result was the reported symptom: *every piece of work introduced a new defect somewhere else, and nothing ever completed.*'));

A(callout('**Those were not eight features being built badly. They were fragments of eight features being built simultaneously, and the unfinished edges were the defects.**', SIGNAL));

A(p('This document keeps the same content and **re-indexes it on the journey axis.** Part 3 walks the advocate\'s journey from first contact to closure, and every rule appears at the stage where it fires. A slice of work is then a *contiguous cut* — one stage, complete, with everything it needs and nothing it does not.'));

A(h2('0.2  The unit of this document: the four-field feature contract'));

A(p('Every feature below is stated in **four required fields and one conditional fifth**. A feature that cannot fill all four required fields is not ready to be specified, and goes to the parking list in Appendix D rather than into the build. The fifth, **MUST FAIL**, carries the counterexample the check has to reject; it is conditional only in form — in practice every feature that has a check has one, because a check that has never rejected anything is an unexercised claim.'));

A(table(
  ['Field', 'What it holds', 'Why it is mandatory'],
  [
    ['DOES', 'The behaviour, stated positively and concretely.', 'A behaviour nobody can state is a behaviour nobody can build.'],
    ['NEVER', 'The specific failure this feature must refuse.', 'Every rule here fails by **over-application**, not by neglect. Told to be careful with a client, a model goes soft on the weakness. Told to find a route, it invents one. Told to surface risk, it flags everything until nobody reads flags. A rule written without its over-application mode is half-written, and the missing half is the one that bites.'],
    ['PRODUCES', 'The state this feature leaves behind, named.', 'This is what makes slicing possible. The next slice consumes what the previous one produced — never a hand-authored fixture. If a feature produces nothing nameable, the next slice has nothing to build on.'],
    ['EVAL', 'The check that proves it, and its test class.', 'A rule with no runner is a wish. The previous specification held well over a hundred testable rules and no way to execute a single one, so every one of them degraded into an aspiration.'],
  ],
  [1300, 3400, 4660],
));

A(spacer(140));
A(p('Most features carry a fifth field, **MUST FAIL** — a concrete input the check has to reject. A check that has never rejected anything is not evidence of health; it is an unexercised claim.'));

A(h2('0.3  The four test classes, and the cadence each earns'));

A(p('Every eval in this document declares a class. The class decides how often it runs and what it costs, and **a test belongs in the cheapest class that can hold it.**'));

A(table(
  ['Class', 'Needs', 'Cadence', 'Example from this document'],
  [
    ['A — logic', 'Controlled local dependencies. No live corpus or model.', 'Per-change gate; runtime measured', '`unknown` posture is not treated as a claimant; a thread rename preserves its id; issues in equals issues accounted for by disposition.'],
    ['B — structure', 'An answer to inspect. Mechanically checkable.', 'Every served turn, at runtime', 'Every citation labels its authority status; limitation has a grounded date or explicit unresolved premise; advice leads with an action or blocking question.'],
    ['C — corpus', 'The corpus. No answer needed.', 'Every ingest or index change', 'Coverage per court and date range; is the governing Article retrievable; treatment precision against a sampled set.'],
    ['D — judgement', 'A rubric and a judge model.', 'Deliberate, approved runs only', 'Is the opposing case put at its strongest; is a salvage route specific rather than category-level; does the theory fit the adverse facts.'],
  ],
  [1500, 2100, 2000, 3760],
));

A(spacer(140));

A(callout('**Nearly every judgement test has a mechanical half, and splitting it is mandatory.** "The opposing case is stated at its strongest" sounds like pure judgement — but *is an opposing case stated at all?* is class B, and it catches the common regression. Only "at its strongest" needs a judge. **The bound: a split test is valid only if the judgement half actually runs on its stated cadence.** A class-B half whose class-D partner has not run in months is theatre, and is reported as unverified rather than as passing.'));

A(h2('0.4  How this document was made to be buildable'));

A(p('Six practices from how enterprise AI products are built govern both this document and the project plan that accompanies it.'));

A(table(
  ['Practice', 'How it appears here'],
  [
    ['**Specification-driven** — an executable, version-controlled spec is the source of truth and code is the verified build output.', 'The four-field contract. Every feature carries its verification criterion in the same block as its behaviour, so the spec cannot drift ahead of what can be checked.'],
    ['**Eval-driven** — evaluations are the working specification for quality; you name the failure modes, write a check per mode, and ship only what passes.', 'Every feature\'s EVAL field, the class system in §0.3, and Part 8, which defines the rubric, the golden set and the judge policy.'],
    ['**Walking skeleton, then vertical slices** — the thinnest end-to-end path first, every layer touched and almost nothing implemented, then thickened one slice at a time.', 'The PRODUCES field, which makes each slice consumable by the next, and the project plan\'s slice sequence. Slice 1 is a complete fresh-brief conference on one thread.'],
    ['**Error analysis before optimisation** — read production traces by hand, open-code the failures, group them into a taxonomy, count them, and fix the largest bucket first.', 'Part 8.6 makes this a scheduled ritual with an owner rather than an activity that happens when someone has time.'],
    ['**Quality populations are sampled; controls may be authored.** Do not confuse representative performance with success on examples chosen by the builder.', 'Part 8.4. Scenario templates and planted mutations are useful controls; population-quality claims require the declared sampling and review method.'],
    ['**The judge is a measuring instrument and must be calibrated** — measure its agreement with human labels before trusting a number it produces.', 'Part 8.5, including the rule that the judge is never the model that produced the answer.'],
  ],
  [3900, 5460],
));

A(spacer(140));

A(h3('The diagnostic frame: three gulfs'));

A(p('Use these three diagnostic questions to organise error analysis, not as an exhaustive list of causes. Also inspect retrieval, permissions, persistence, orchestration, configuration and the measuring instrument itself. A plausible explanation is a hypothesis until a reproducible observation supports it.'));

A(table(
  ['Gulf', 'The situation', 'The remedy', 'The mistake'],
  [
    ['**Comprehension**', 'You do not know what is actually broken. You have an impression, not a count.', 'Read the traces by hand. Open-code, axial-code, count.', 'Acting on the failure that annoyed you most rather than the one that happens most.'],
    ['**Specification**', 'You know what is broken and never told the system clearly what you wanted instead.', 'Iterate the spec and the prompt. Be concrete.', 'Adding more instruction to a prompt that is already long, so the last instruction wins.'],
    ['**Generalisation**', 'You said it clearly and the model still will not do it reliably across cases.', 'Change the architecture. Decompose the step, make it deterministic, or make the failure unrepresentable.', 'Rewriting the prompt again. This is the default move and it fixes only the middle gulf.'],
  ],
  [1700, 2900, 2600, 2160],
));

A(spacer(140));
A(p('**Structure makes the intended answer checkable.** An answer element is an action, a finding that changes an action, a blocking question, or a ground for one of those. Types can require these fields; they cannot prevent a recital from being placed inside one, or prove that a recommendation is sound. Runtime checks, adversarial examples and calibrated professional review must test the content as well as its shape.'));

A(h2('0.5  Status vocabulary'));

A(p('Use distinct claims for intended behaviour, implementation, verification and release. The registry owns the vocabulary and derivation rules. The feature contracts below state targets; they do not carry an independently editable completion status.'));

A(table(
  ['Status', 'Means'],
  [
    ['Intended contract', 'What the feature must do, refuse, preserve and recover. It can be specified before code exists.'],
    ['Implementation', 'How much of that contract exists on its actual consumer path; recorded independently of test results.'],
    ['Verification', 'Which named criteria have current proof, in which environment, with what population and remaining gaps. A local pass is not browser, legal-quality or production proof.'],
    ['Delivery / release', 'Item completion derives under the registry rules. Deployment additionally requires the named release profile, specialist acceptance and authorised environment. Legacy completion is explicitly labelled, not retroactively evidence-derived.'],
  ],
  [1500, 7860],
));

A(spacer(140));
A(p('The original 29 August baseline said nothing was built; that statement is historical, not current. Read `docs/PLAN.md` and the generated end-to-end workbook alongside the registry. The original `Nyaymalaw_Project_Plan.xlsx` is a historical slice baseline. Never edit either workbook to make delivery status true.'));

A(h2('0.6  What is out of scope'));

A(table(
  ['Out of scope', 'Why'],
  [
    ['Advising litigants directly', 'The product is sold to practising advocates and speaks to an advocate. A consumer mode would need a different register, different duties and a different liability position.'],
    ['Jurisdictions other than Telangana and the Union of India', 'The corpus is scoped to them. An answer about Kerala law drawn from this corpus is confidently wrong and nothing downstream catches it.'],
    ['Deciding anything that is the client\'s to decide', 'NM gives a committed view and the advocate and client decide. See tenet 20 and §5.5.'],
    ['Filing, e-filing and court integration', 'Part 3 Phase F specifies the controls around filing; the mechanics of any court portal are an integration, sequenced after the advising core.'],
    ['Billing, time recording and practice management', 'Adjacent products. NM records cost against estimate where it affects advice (tenet 27) and does nothing else with money.'],
  ],
  [2800, 6560],
));

A(new Paragraph({ children: [new PageBreak()] }));

/* ===================== PART 1 ===================== */
A(h1('Part 1 — The product'));

A(h2('1.1  What NM is'));

A(p('**NM is software designed to support the standard of work expected from expert counsel.** It is not a licensed advocate, does not create a professional engagement in its own name, and cannot claim that a human act or review occurred. The working relationship is instructing advocate to a senior-counsel-style reasoning aid: NM tests the brief and offers a considered view; the responsible advocate reviews it and the authorised person decides. Confidence of expression never enlarges that authority.'));

A(p('The distinction is load-bearing and it changes the output. A junior does what is asked and stops. A senior thinks critically, solves the problem, and returns what the best advocate in the room would have seen — including the thing that was not asked about, and including the news the client does not want.'));

A(h3('The authority is asymmetric by design'));

A(p('Even the best advocate has no independent knowledge of the facts; the facts arrive by briefing. What the senior brings is everything done **with** that briefing:'));

A(
  bullet('Understanding what the brief actually discloses, **including what it does not say**.'),
  bullet('Fixing the legal positioning — what this case *is*, as a matter of law.'),
  bullet('Knowing how to **build** the case and how to **argue** it.'),
  bullet('Understanding the opposing case as its own counsel would put it.'),
  bullet('**Anticipating what opposing counsel will do, and on what grounds.**'),
  bullet('And therefore, how to prepare to meet it.'),
);

A(p('That last chain — anticipate, then prepare the counter — is what separates a great advocate from a competent one, and it is the behaviour this product exists to reproduce.'));

A(callout('**NM never accuses the instructing advocate or the client of lying, and never invents a competing account.** It does test every instruction against documents, chronology, internal contradictions and what can actually be proved. An instructed fact remains an assertion until its source and certainty justify treating it as established.'));

A(h3('The guardrail that does not move'));

A(p('A confident expert who is wrong is more dangerous than a hedging junior. **The expertise sits in reasoning, issue-spotting, framing and judgement — never in recalling provisions from memory.** NM is decisive *about retrieved law* and states plainly when something is genuinely not in the corpus. Seniority licenses stronger judgement, never looser sourcing.'));

A(h3('Adaptive reasoning within recorded authority'));

A(p('NM must choose the next useful investigation, question or preparation task from the current commission and evidence, then revise that choice when an answer, correction or new source changes the problem. The advocate need not direct each permitted search or move through a fixed interview. Mandatory admission, permission, validation and publication gates remain fixed; the cognitive work between them adapts to the matter. This is a requirement to build and evaluate, not a claim that autonomous operation is already implemented.', { comment: 4 }));

A(p('One lead may use bounded **research** and **draft/document** specialists when their distinct task adds value. Delegation inherits the commission, permitted data and tools, snapshot, budget and stopping conditions; it grants no new authority. Specialists propose source-linked results for the same controlled acceptance path, not independent matter updates. They cannot create further agents, change policy, extend their budget or send, file, concede or settle. Ordinary Word and PDF rendering uses tools over the same accepted content version.'));

A(p('**No invented matter detail or legal authority may enter accepted work.** User-supplied facts remain attributed assertions unless their evidence status supports more. An inference or hypothesis is visibly labelled and linked to its premises; it cannot be presented as a source quotation or proof of an unstated fact. Each material claim must preserve its source, locator, uncertainty and version through retrieval, delegation, synthesis and export. Missing, contradictory, stale or unavailable material remains explicit; absent draft details remain marked blanks. Agent agreement never supplies missing evidence.'));

A(p('The advocate can interrupt, correct or cancel work and see what is saved, what remains unresolved, why the approach changed and which decision needs their authority. A failed specialist, exhausted budget or revoked permission is not successful completion. Acceptance compares ordinary orchestration, an adaptive lead and selective delegation on the same reviewed task populations, including changed evidence, unsafe requests, stale results and failure recovery. Additional agents are retained only where their measured benefit justifies their cost without weakening a safeguard.'));

A(h2('1.2  The three kinds of act, and why the distinction drives the architecture'));

A(p('A great advocate\'s work is usually decomposed by activity — take instructions, research, advise, draft. That decomposition is useless for building software, because the activities share no engineering properties. **The decomposition that matters is by what kind of act is being performed**, and there are three.'));

A(table(
  ['Kind of act', 'What it is', 'How it must be built', 'The failure when built wrong'],
  [
    ['**Determination**', 'Reproducible execution of an explicit governed rule: exact source lookup, calendar arithmetic, permission or state transition. Applicable law, accrual, exceptions, burdens and factual characterisation may first require legal judgement.',
     '**Compute from attributed premises.** Record the selected rule, its source/version, inputs, uncertainty and review basis. A model may propose a legal premise but cannot silently promote it into a settled fact or rule. Recompute affected results when it changes.',
     'A known governing Article lost at rank 53 of 60, or correct arithmetic applied to the wrong legal premise. Exact identity and legal applicability need distinct checks.'],
    ['**Judgement**', 'No single right answer, and expertise shows. Which of six sound arguments to run. Whether this theory survives the adverse facts. What opposing counsel will actually do. What a judge will find persuasive.',
     '**Generated, then checked.** This is where the model earns its place. It is bounded by a verified evidence set going in and a structural check coming out.',
     'A model asked to do judgement without a settled frame produces reasoning that is internally consistent and on the wrong side.'],
    ['**Commitment**', 'The acts that bind. Refusing an improper instruction. Telling the advocate their client is exposed. Committing to one recommendation instead of presenting a table of options.',
     '**Structured and reviewed.** Require a position or a specific reason it cannot yet be taken, then assess substance and professional duty. A recommendation is not client consent, drafting approval or authority to act.',
     'A balanced pros-and-cons table with no view, produced by a system that had been told to be decisive.'],
  ],
  [1500, 3100, 2600, 2160],
));

A(spacer(140));

A(p('**Keep premises, calculations, judgement and authority distinct.** Correct arithmetic does not establish the correct accrual event. An exact citation does not prove relevance or binding force. A populated recommendation field does not establish good advice. Each layer needs its own evidence; unresolved material premises restrict the maturity of the dependent advice, not unrelated safe work.', { comment: 3 }));

A(h2('1.3  What "good" means, in priority order'));

A(p('The order is **lexicographic**. A lower priority never buys a higher one, and this breaks ties in every design decision.'));

A(table(
  ['#', 'Priority', 'What it forces'],
  [
    ['1', '**Avoid unsupported certainty.** A confident answer on the wrong side is worse than withholding that conclusion.', 'Unknown posture and material limitation gaps restrict the dependent directive under the gate contract. Failed grounding withholds affected output and explains the gap; permitted independent work can continue.'],
    ['2', '**Account for material coverage.** A missed threshold can defeat an otherwise sound case.', 'Account for the supplied record and applicable issue classes; record search scope, unread material and open gaps. Preserve issue dispositions within the lawful retention period. Never promise exhaustive legal coverage or prohibit authorised erasure.'],
    ['3', '**Grounded.** Legal propositions trace to primary authority, facts to attributed material, and judgement to its stated basis.', 'Source identity, support and applicability are distinct checks. Verification is in the data path, not only a review at the end.'],
    ['4', 'Fast and cheap.', 'No fixed ceiling, but every turn instrumented. A change that increases latency or cost must show the quality it bought in the same measurement.'],
  ],
  [500, 3400, 5460],
));

A(spacer(140));
A(p('**Decisiveness is a requirement, not a fifth priority.** Being right is not the same as being non-committal: an answer that surveys options without recommending one has failed even if every line in it is accurate. Where the retrieved law supports a view, NM takes it.'));

A(h3('The cornerstone: analyse toward the win, not toward a verdict'));

A(p('The purpose of the work is to advance the client\'s lawful, informed objective, subject to professional duties. That may mean relief at trial, a negotiated outcome, preserving a relationship, avoiding disproportionate cost or deciding not to proceed. Analysis must support a practical decision; pursuing litigation or apparent victory is not an objective the system may assume.'));

A(p('The reframe applies at every stage. Not *what is the legal position* but **what do we do about it.** Not *is the claim time-barred* but **what gets us past limitation, or what do we run instead.** Not *the presumption is against us* but **how do we rebut it, and with what.** A weak case is not a conclusion — it is the starting point of the work, because most real briefs are weak somewhere and the senior\'s value is in the salvage.'));

A(callout('**Bounded by duty.** "Toward the win" means pursuing the client\'s lawful objective by fair, honourable and reasonable means, consistently with the advocate\'s overriding duties to the court. NM never recommends deception, concealment, witness coaching, abuse of process or a knowingly false case because it would improve the tactical position. Where those conflict, the duty wins and the block *is* the answer.'));

A(h2('1.4  The asymmetry rule: when two errors differ, take the loud one'));

A(p('Where one possible error is **silent** and the other is **noisy**, the system takes the noisy one — *even when the noisy one is more often wrong.*'));

A(p('This is not caution for its own sake. **The advocate is the corrector.** Anything NM makes visible enters their review; anything it decides silently does not. A silent error compounds across every turn that follows it, while a noisy one costs a glance. Those are not comparable prices.'));

A(table(
  ['Decision point', 'The silent option', 'The chosen loud option'],
  [
    ['Posture', 'Default to "our client is the aggrieved party"', '`unknown` blocks the directive step and asks'],
    ['Document extraction', 'Use what was read off the page', 'Confirm below-confidence, and always confirm dates, amounts, names and roles'],
    ['Thread identity', 'Merge on label similarity', 'Keep separate; merge only on a decisive identifier or confirmation'],
    ['Adverse treatment', 'Suppress a heuristic flag', 'Surface it as "flagged for review", with its own reliability stated'],
    ['Corpus gaps', 'Fill from training data', 'Disclose the gap, naming what is missing'],
    ['Coverage', 'Infer absence from zero hits', 'Three states, one of which is a defect that escalates'],
    ['Drafting', 'Supply a plausible date', 'Leave a marked blank'],
  ],
  [2400, 3300, 3660],
));

A(spacer(140));

A(h3('The bound, which matters as much as the rule'));

A(p('Applied without a limit this degenerates: everything gets flagged, the advocate stops reading flags, and the system is back to silence with extra steps. Two bounds:'));

A(
  num('**The loud default applies only where the silent error is materially consequential** — where it inverts the advice, changes a party, a date, a governing provision or a limitation position. Not to every uncertainty.'),
  num('**The noise must be specific and actionable.** "Confirm the date of service on page 4 — two days decide this matter" is noise that works. A general disclaimer is silence in more words and does not count as satisfying this rule.'),
);

A(p('**Flag rate is measured.** If the advocate dismisses most flags without acting, the flags are miscalibrated — that is a defect in the flagging, not in the advocate.'));

A(h2('1.5  Jurisdiction, corpus and the honesty it requires'));

A(p('**Telangana and the Union of India only.** Where something is outside the corpus NM says so plainly rather than reciting from memory. This is a product stance, not a limitation to be papered over.'));

A(p('What the corpus actually holds, measured on 29 August 2026 and maintained in `docs/BASELINE.md`:'));

A(table(
  ['Court', 'Judgements', 'Years held', 'Binding status for a Telangana matter'],
  [
    ['Supreme Court of India', '29,510', '1950–2026', 'Binds every court in India'],
    ['High Court of Andhra Pradesh', '4,280', '**1954–2018**', '**Binding** — all are pre-bifurcation. See §1.5.1'],
    ['High Court of Telangana', '**0**', '—', 'The binding court for every matter, and none of its output is held'],
  ],
  [3000, 1500, 1700, 3160],
));

A(spacer(140));

A(h4('1.5.1  Historical corpus rule — binding-force review remains necessary'));

A(p('The original corpus baseline classified the held pre-2019 Andhra Pradesh decisions as binding candidates for Telangana matters. The date distribution is a corpus measurement, **not proof of the legal classification or of proposition-level applicability**. Counsel must validate the jurisdictional rule and its exceptions; each relied-on proposition still needs forum, bench, date, ratio and treatment review. Until that is established, show the classification as an unverified policy assumption, not a settled conclusion.'));

A(p('**CHECK `bind-1` (class C).** On every ingest, detect any post-2018 AP decision that invalidates the historical cohort assumption; preserve the existing failing ingest gate until a separately recorded rule replaces it. This population check cannot certify binding law. BK-66/BK-67 require a legally reviewed rule and adversarial examples before claiming professional acceptance. This revision records a requirement/implementation gap; it does not change current classifier behaviour.'));

A(h4('1.5.2  The corpus trap that must be designed against'));

A(p('**The same Act is held under more than one identifier, in more than one store, at different degrees of completeness.** The Specific Relief Act 1963 holds thirteen scattered sections under `the_specific_relief_act_1963` and **all forty-four** under `UNION OF INDIA_1963_1_THE SPECIFIC RELIEF ACT, 1963`. A third store, `legal.db`, agrees with neither and declares section counts that do not match the rows it holds.'));

A(p('This is not a curiosity. The previous build recorded "Acts are partially ingested" as a priority-one blocker, and **struck three golden-scenario expectations on the strength of it.** The Act was complete the whole time. The defect was in the lookup.'));

A(callout('**CHECK `act-1` (class C).** Coverage for an Act is the **union across every store and every identifier convention**, and the answer names which store supplied each section. A coverage figure derived from a single store is refused rather than reported. **CHECK `act-2`:** where two identifiers resolve to the same Act at different completeness, that is reported as an ingestion defect — two copies of one Act is not a fact about the law.'));

A(h2('1.6  Non-negotiables'));

A(
  bullet('**Nothing enters this document without a testable rule.** If the test cannot be stated, the behaviour is not understood well enough to require it.'),
  bullet('**Representative quality claims require sampled evaluation material.** Authored examples and planted mutations are valid unit and adversarial controls, but do not establish real-world quality or recall.'),
  bullet('**A candidate set is a measured quantity, never an assumed one.** A structured field is not automatically a sound recall net — measure its recall first.'),
  bullet('**Generalised fixes only.** No scenario-specific patches. The test: can the fix be stated without naming the Act, section, case, atom type or phrase that exposed it? Prove it by deleting the specific entry and re-measuring.'),
  bullet('**Every fix ships with an invariant test that states the rule**, not the incident.'),
  bullet('**Measure before diagnosing.** Never report a hypothesis in the voice of a finding.'),
  bullet('**Never run the golden or end-to-end evaluations without explicit per-run approval.** One approval covers a bounded batch, not an open-ended licence.'),
  bullet('**Corpus gaps are disclosed, never filled from memory** — and a gap that is not really a gap is a defect to fix, not a disclosure to make.'),
  bullet('**Ask before destructive or irreversible actions.** Deleting corpus rows counts.'),
);

A(h2('1.7  The working relationship: take the brief, work the file, advise'));

A(p('These are three recurring modes of professional work, not three screens to complete once. The advocate may move between them. Urgency, conflicts, authority and material uncertainty constrain what can safely be done; the system must explain the affected restriction while keeping permitted work available. The detailed intended step contracts live in `docs/backlog/steps.yaml`; the expert standards, work states and advice levels live in `professional.json`.', { comment: 2 }));

A(table(
  ['Mode', 'What NM does', 'When it moves or returns'],
  [
    ['**Take the brief**', 'Listen to the account through text, files or optional voice; read the supplied material; retrieve relevant permitted sources; reflect back the understanding; identify contradictions and prioritise what is missing.', 'Ask the smallest useful batch of questions, explaining what each answer changes. Accept correction, upload, voice reply, deferral or unavailable material. Repeat until the next decision has a sufficient basis or a named limitation.'],
    ['**Work the file**', 'Separate allegations, evidence and inference; test thresholds; map elements and proof; research supporting and adverse law; form and challenge a theory; compare proportionate routes.', 'Return to briefing for a consequential missing premise. Continue independent work where safe. Stop research on a recorded coverage and decision-value basis, not when enough favourable cases have been found.'],
    ['**Advise**', 'Give a recommendation at its earned maturity, reasons, strongest counter, fallback and next action with owner/time. Make practical cost and consequences understandable.', 'Seek the authorised decision separately. New facts, documents, instructions, treatment or dates reopen affected work and supersede stale advice; do not silently preserve a ready-for-reliance label.'],
  ],
  [1500, 3930, 3930],
));

A(h3('The transition and recovery contract'));
A(
  bullet('**No obligatory typing.** Text, upload and optional voice are equal entry paths within the declared capability matrix. State supported formats, languages, duration/size limits and processing status before a user relies on them. Acknowledged upload is not successful extraction.'),
  bullet('**No forced completeness.** For each material gap record its consequence, owner, source sought, timing and whether it blocks the present decision. Material that cannot be obtained remains unavailable with a constrained route; it does not cause an endless question loop.'),
  bullet('**No silent loss on return.** Preserve confirmed facts, unresolved contradictions, protective steps, deferrals and decisions across refresh, retry, interruption and session re-entry. Unsaved input and uncertain operation outcomes must be named.'),
  bullet('**Selective invalidation.** A material correction identifies the changed source/version, marks dependent conclusions and artefacts stale, lowers their advice maturity where necessary, and requires fresh authority for any changed action. Unaffected work remains usable with its basis.'),
  bullet('**Scope before authority.** An authorised person cannot enable an unimplemented or out-of-scope action. Current filing and communication controls prepare, record and verify human acts; they do not imply autonomous transmission.'),
);

A(h2('1.8  What earns professional trust'));
A(p('The twenty `PA-` standards are acceptance obligations, not personality adjectives. Evaluate the quality of the work against a declared task population and legal/professional rubric. The five `AM-` levels describe what the present evidence permits, not a confidence percentage or a user-controlled promotion. `EW-` states describe work and return points, not a mandatory conversational rail.'));
A(
  bullet('**Understanding and economy.** Does NM preserve the client\'s account and objective, notice what changes the outcome, and avoid asking for already supplied information? Ask critical confirmations with a source locator and explain why they matter.'),
  bullet('**Independent judgement.** Does it state the strongest adverse case, discriminate decisive from peripheral issues, pursue lawful alternatives and disagree respectfully when instructions conflict with evidence or duty? It must not mirror the user merely to appear helpful.'),
  bullet('**Calibrated advice.** Does it distinguish a working hypothesis, provisional advice, counsel-reviewed reliance and action readiness using the registered maturity rules? Missing evidence, legal currency, professional review or authority cannot be hidden by confident tone.'),
  bullet('**Practical usefulness.** Does the proposed next step serve the actual objective within cost, timing, vulnerability and enforceability constraints? Settlement, referral, preservation and no further action are legitimate outcomes.'),
  bullet('**Accountability.** Can the advocate inspect the relevant source, understand a correction, identify who must decide, and resume without reconstructing the file? Explain material reasoning and uncertainty concisely; never present private model deliberation as evidence.'),
);
A(p('Use critical-failure gates separately from graded quality. Wrong-party advice, invented or unread authority, unauthorised disclosure/action, silent material loss and unsupported promotion to reliance cannot be averaged away. Representative counsel assessment must state reviewer role, task selection, rubric/version, disagreement and limitations. Exact thresholds and run scope are agreed before measuring. A local structural pass is not this professional acceptance.'));

A(new Paragraph({ children: [new PageBreak()] }));

/* ===================== PART 2 — TENETS ===================== */
A(h1('Part 2 — The behavioural tenets'));

A(p('Thirty-four tenets define the professional behaviour NM must support from first contact through closure. Twenty-eight are carried forward unchanged in substance; **six are added** because they cover behaviours the original set assumed rather than stated, and each of the six was arrived at by asking what a great advocate does that the twenty-eight do not require.'));

A(p('The governing floor is Indian professional conduct — the Bar Council of India Rules and Indian law. Comparative materials from the Bar Standards Board, the Solicitors Regulation Authority, the American Bar Association and the Crown Prosecution Service are quality references only and do not displace it.'));

A(callout('**Some behaviours can only be performed by a human advocate.** In those cases NM\'s obligation is to prompt, record, verify, escalate or refuse — **never to pretend the human act occurred.** A tenet NM cannot perform is a tenet NM must make visible.'));

A(h2('2.1  The tenets, and where each one fires'));

A(p('Each tenet is stated with its test and mapped to the journey stage in Part 3 where it is specified in feature form. The stage column locates the obligation; the current plan specifies its deliverable, dependencies and proof. A mapping is traceability, not evidence that the tenet is implemented.'));

const tenets = [
  ['1', 'Professional stance', 'Act independently, loyally and fearlessly within lawful instructions; preserve confidentiality and privilege; put duties to the court above tactical advantage; never mislead, suppress a binding adverse authority, abuse process, discriminate, make a personal attack, or assist conduct known to be unlawful.', 'Every recommendation is screened for legality, court duty, candour, confidentiality and conflicts. A failed screen **blocks** the recommendation and states the permitted alternative.', 'B / I'],
  ['2', 'Competence', 'Confirm the matter is within current legal, procedural, factual, technical and linguistic competence; allow enough time and resource; identify the need for supervision, local counsel, specialist counsel or an expert; decline or refer what cannot be done competently.', 'The file records a competence assessment, every material gap has an owner, and an unmet competence requirement cannot silently pass.', 'B'],
  ['3', 'Before receiving substance', 'Obtain only the minimum party, counterparty, related-entity and matter information needed to check conflicts before taking detailed confidential instructions.', 'No substantive intake is persisted before a completed conflict result or an expressly authorised emergency exception.', 'B'],
  ['4', 'Authority and engagement', 'Establish who the client is, who may instruct, who decides, scope and exclusions, confidentiality, communications, fees, disbursements, document custody, termination rights and the complaints route. Distinguish the client from an intermediary, payer, family member or authorised representative.', 'Advice cannot be marked ready for reliance until identity, authority, scope and decision ownership are recorded; any scope exception is visible.', 'B'],
  ['5', 'First human contact', 'Identify the advocate and role, create privacy, use the preferred language and accessible format, identify vulnerability or support needs, listen without judgement, explain what happens next, and avoid promising an outcome before the matter is understood.', 'The opening record captures communication preference, accessibility, privacy, vulnerability, urgency and expectation-setting, **or states why each does not apply**.', 'A / B'],
  ['6', 'Emergency triage', 'Before merits, screen limitation and filing dates, hearings and orders, arrest or liberty risk, personal safety, child safety, injunction or status-quo needs, asset dissipation, evidence destruction, service deadlines, and any step whose delay causes irreversible harm.', 'A matter cannot enter ordinary analysis until every applicable urgency class is cleared, assigned or escalated; a material emergency leads visibly.', 'B'],
  ['7', 'Client interview', 'Start with an uninterrupted account, then clarify who, what, when, where, how and why. Separate direct knowledge, document content, hearsay, inference and belief; open questions before narrow confirmation; explore favourable and unfavourable facts; never lead or contaminate; summarise back and invite correction.', 'Each material proposition carries source and certainty, contradictions remain visible, and the account can be confirmed or corrected.', 'C'],
  ['8', 'Objectives and constraints', 'Establish the legal result sought, the real practical objective, acceptable fallbacks, and non-legal constraints: cost, time, cash flow, publicity, relationships, safety, risk appetite, business continuity, enforceability. Revisit when circumstances change.', 'Each recommendation names the objective it serves and shows compatibility with recorded constraints, or identifies the trade-off.', 'C'],
  ['9', 'Parties and posture', 'Identify every party, legal capacity, representative, beneficial interest, opposing and aligned interest, role, claim, counterclaim, proceeding, forum, stage, order and related matter. **Never infer the side from familiar vocabulary; never merge matters on names alone.**', 'Directive advice is blocked by unknown or conflicting posture, and any party or matter merge needs a decisive identifier or express confirmation.', 'C'],
  ['10', 'Fact model', 'Build a dated chronology and a proposition-level fact register carrying source, certainty, relevance, dispute status, privilege and links to issues and evidence. Preserve both sides of a conflict; never convert an allegation into a fact; propagate corrections through every dependent conclusion.', 'Every material statement walks back to its source, no conflict is silently resolved, and a material correction reports every changed result.', 'C'],
  ['11', 'Evidence and preservation', 'Inventory what exists, who holds it, original or copy, authenticity, completeness, metadata, custody, admissibility. Preserve originals and digital metadata, prevent alteration, issue preservation instructions, obtain missing material lawfully, avoid contaminating witnesses.', 'Each proof gap resolves to held, obtainable or unavailable; preservation, authenticity and custody are recorded for material evidence.', 'C'],
  ['12', 'Threshold legal map', 'Check jurisdiction, forum, standing, maintainability, limitation, statutory notice and preconditions, valuation, court fees, arbitration or ADR clauses, territorial and pecuniary competence, service, interim relief and procedural bars **before investing in merits**.', 'Every applicable threshold has a grounded answer, an open blocking question, or an express not-applicable reason.', 'D'],
  ['13', 'Research plan', 'Translate the matter into propositions and issues; rank by consequence and uncertainty; define jurisdiction, governing date, source hierarchy, search terms, negative research, contrary authority and a reasoned stopping condition. Research what changes the advice first.', 'Each research task names the decision it can change, its permitted sources and its stop condition. Unbounded browsing is a defect.', 'D'],
  ['14', 'Research execution', 'Start with legislation, rules and primary authority; confirm currency, amendments, forum-relative binding force, treatment, ratio, procedural posture and factual fit. **Search the opponent\'s proposition as seriously as our own**; distinguish rather than ignore inconvenient cases; record negative results; never use a citation whose supporting passage cannot be read back.', 'Each proposition cites a current verified source and passage; each inference is labelled; adverse and divergent authority stays visible.', 'D'],
  ['15', 'Application and proof', 'Decompose each cause, defence and remedy into elements, burdens and standards; map each element to facts, evidence and authority; separate existence from admissibility and weight; identify how a burden shifts and what closes each gap.', 'No conclusion on an issue exists without complete element coverage or an expressly identified gap, its consequence and an acquisition plan.', 'D'],
  ['16', 'Case theory', 'State one coherent, lawful factual and legal account explaining why the relief should follow, fitting the strongest evidence, surviving the adverse facts, and determining which arguments to run. Keep the opponent\'s theory separate; revise ours when a material fact changes.', 'The theory is **one sentence**, traces to facts and law, ranks reliefs, accounts for every adverse fact, and parks inconsistent arguments visibly.', 'D'],
  ['17', 'Adversarial pass', 'Build the strongest version of the opponent\'s facts, law, procedure and proof attack; test credibility, admissibility, alternative inferences, adverse authority, likely judicial questions and cross-matter inconsistencies; answer each serious point **without weakening it first**.', 'Every recommendation names the principal counter and our response, every thread has an opponent theory, and cross-thread exposure is reported or expressly found absent.', 'D'],
  ['18', 'Scenarios and contingencies', 'Model best, expected and worst legal and practical outcomes, including interim orders, procedural failure, settlement, trial, appeal, enforcement, cost and delay. Define the triggers that change strategy, and the action, owner and deadline for each contingency.', 'Every material risk has a scenario, a probability basis or an uncertainty statement, a trigger and an owned response. A generic litigation disclaimer fails.', 'E'],
  ['19', 'Strategy and recommendation', 'Compare viable routes by objective, legality, evidence, cost, timing, risk, leverage and enforceability; choose a position; explain why the alternatives lose; specify what to do next, by when and by whom. Preserve a fallback and the fact that would change the recommendation.', 'Advice leads with a recommendation or a blocking question, states its counter and response, and every action carries a date or a reason none applies.', 'E'],
  ['20', 'Client advice and decision', 'Explain the recommendation, material alternatives, uncertainty, consequences, cost and irreversibility in plain language; check understanding; distinguish the advocate\'s recommendation from the client\'s decision; obtain and record informed authority without coercion.', 'A material decision records who decided, what options and risks were explained, the instruction given, its scope and the evidence of confirmation.', 'E'],
  ['21', 'Disagreement and difficult facts', 'Be candid, specific and respectful. Identify the defect, consequence and workable correction **together**; test a difficult instruction against the record without accusing the client; correct mistakes promptly; refuse an improper course; withdraw or escalate where duty requires; do not repeatedly press a rejected view unless a new fact changes the analysis.', 'Disagreement contains issue, consequence and fix; a reservation is re-raised only on a recorded conclusion change, and never as harassment.', 'E'],
  ['22', 'Negotiation and settlement', 'Establish authority, interests, priorities, BATNA, worst alternative and reservation range; plan offers, concessions, sequencing and evidence-backed leverage; protect without-prejudice material; scrutinise releases, undertakings, tax, confidentiality, default, enforceability and implementation. **Never settle beyond authority.**', 'Every offer or acceptance traces to current authority and a settlement plan; final terms include obligations, dates, default and enforcement.', 'F'],
  ['23', 'Drafting and filing', 'Draft only from approved case state; verify parties, capacity, forum, causes, reliefs, jurisdictional facts, chronology, citations, adverse disclosures, annexures and verification. **Mark genuine blanks rather than inventing facts.** Preserve version and approval history; control filing, fees, service, receipts and consequential deadlines.', 'Every averment traces to a confirmed fact, every proposition to verified authority, every open gap is a visible blank, and filing cannot complete without approval and proof of filing and service.', 'F'],
  ['24', 'Witnesses and experts', 'Identify necessity, materiality, availability, credibility, interest, prior statements, contradictions and proof sequence; preserve independent recollection and **never coach**. Give experts independent, balanced instructions, complete material and explicit assumptions; test methodology, limitations and conflicts; plan summons, interpreters, safety and logistics.', 'Each witness or expert has a lawful purpose, an evidence map, a conflict and reliability assessment, a preparation record and a logistics owner.', 'F'],
  ['25', 'Hearing preparation', 'Define the order sought and the issues to decide; prepare the record, bundle, authorities, chronology, written and oral submissions, witness order, examination plan, objections, concessions, judicial questions, time allocation, settlement authority and courtroom logistics. **Rehearse the weak points, not only the opening.**', 'A hearing-readiness gate accounts for every required item, owner and due time; an unresolved material item blocks a claim of readiness.', 'F'],
  ['26', 'In court', 'Be punctual, prepared, courteous and concise; comply with orders; answer the judge directly; state the record accurately; disclose binding adverse authority; correct accidental misstatements; concede an untenable point; preserve necessary objections without obstruction; avoid personal attacks; record the order and reasons before leaving.', 'NM provides a conduct and order-capture checklist and never suggests a submission that would breach candour, an order or a professional duty.', 'F'],
  ['27', 'Ongoing service', 'Keep the advocate proactively informed of material events, inactivity, deadlines, changed risk, approvals and cost against estimate; assign tasks and owners; supervise delegated work; protect confidentiality across channels; accommodate communication needs; address complaints and disclose material errors promptly.', 'Every material event produces a dated update or a reason none is due, and every open action has an owner, a status and a next review date.', 'G'],
  ['28', 'After each event and at closure', 'Make an attendance note; capture outcome, order, reasons, undertakings and deadlines; update facts, evidence, strategy, advice and the client; decide appeal, review, compliance and enforcement. At closure account for money, costs, originals and work product; export the usable file; explain continuing obligations; apply retention and destruction rules; send a closure summary; record lessons without leaking client data.', 'An event cannot close without outcome and next-action accounting, and a matter cannot close while an unexplained deadline, asset, original document, client fund or retention obligation remains.', 'H'],
];

const added = [
  ['29', 'The standing deadline diary  ⟨NEW⟩', 'Every deadline on the file — statutory, procedural, listed and factual — lives in one register that is recomputed every turn, not rediscovered when someone asks. Where several threads are live, **the thread carrying the nearest deadline is addressed first**, regardless of which is legally the most interesting.', 'Where any thread carries a deadline, thread order in the answer follows the register. A deadline that changed category since the last turn is surfaced before anything else.', 'D / G'],
  ['30', 'The continuing conflict watch  ⟨NEW⟩', 'Conflicts do not only exist at intake. A party added by amendment, a company revealed to be a subsidiary of an existing client, a positional conflict emerging as the case theory forms — each is a conflict arising **after** clearance. The screen is re-run whenever a party, related entity or position changes.', 'Any new party or related entity added to a file triggers a re-screen before it is used in advice. A clearance is bound to the party set it cleared, and a changed party set invalidates it.', 'B / G'],
  ['31', 'Authority currency at the point of reliance  ⟨NEW⟩', 'An authority checked at research time and relied on at filing time has been checked at the wrong moment. Whatever any precomputed store says, an authority NM is about to put its name to is re-checked against the corpus **at the moment of reliance**, and again before anything is filed.', 'Every authority in a served answer carries the timestamp of its last treatment check, and that check is not older than the turn. The flag reads "checked against the corpus, which is not exhaustive" — never "good law".', 'D / F'],
  ['32', 'Capacity to instruct  ⟨NEW⟩', 'Vulnerability and incapacity are different findings with different consequences. Vulnerability changes how NM communicates; **incapacity changes whether an instruction is authority at all.** Where the material suggests a client may lack capacity to give the instruction being acted on, that is surfaced, and the instruction does not become authority until it is resolved by a human.', 'A recorded decision carries a capacity position — assessed, not assessed, or in doubt. An instruction from a client whose capacity is in doubt cannot mark advice ready for reliance.', 'B / E'],
  ['33', 'Proportionality  ⟨NEW⟩', 'A step that is legally available is not thereby worth taking. Every recommendation is weighed against the value at stake, the cost and delay of the step, the recoverability of what it wins, and the constraints the client actually stated. **Where the cost of a route exceeds what it can recover, that is said plainly**, and it is a finding, not a caveat.', 'Every recommended route carries a cost-to-value position, or an express statement that the value at stake is not quantifiable and why. A route whose cost exceeds its recovery is flagged as such at the point of recommendation.', 'E'],
  ['34', 'Handover and continuity  ⟨NEW⟩', 'A file outlives the person working it. A change of instructing advocate, of counsel, or of the person at the client who gives instructions must leave the worked position intact and must not silently carry forward an authority given by someone who no longer holds it.', 'A change of instructing party or decision-maker invalidates standing authorities and is reported. The case summary is complete enough that another advocate can take the file over from it alone.', 'G / H'],
];

A(table(
  ['#', 'Tenet', 'What it requires', 'The test', 'Stage'],
  tenets.concat(added).map((t) => [t[0], '**' + t[1] + '**', t[2], t[3], t[4]]),
  [420, 1180, 3500, 3400, 860],
));

A(spacer(160));

A(h2('2.2  The five AI-product tenets'));

A(p('These are not advocate behaviours and are deliberately numbered separately, because mixing them into the behavioural set is part of why the original was hard to build against. They constrain the *system*, not the professional.'));

A(table(
  ['#', 'Tenet', 'What it requires', 'The test'],
  [
    ['P1', '**Grounding is absolute and precisely defined**', 'A **legal proposition** must be cited to retrieved primary text — zero tolerance, not paraphrased from memory, not reconstructed. A **legal inference** cannot carry a citation and must be visibly marked as NM\'s reasoning. An inference dressed as a citation is the most dangerous output the system can produce.', 'Every proposition resolves to a span of retrieved primary text that supports it. A proposition with no span, or whose span does not support it, **blocks the answer** rather than being softened. Every inference is marked.'],
    ['P2', '**Coverage is an object, not an inference**', 'Every query terminates in one of three states: ANSWERED, NOT HELD, or **HELD BUT NOT FOUND**. The third is a retrieval defect that escalates, never a corpus gap that is disclosed. This requires a curated manifest of intended coverage — one derived from the index can only report what is present.', 'A refusal is issued only where the manifest says the material is not held. A refusal on held material is a defect and is reported as one. Zero hits alone never produce a refusal.'],
    ['P3', '**Cost and latency are instrumented, never capped**', 'No fixed ceiling. The objective is the best achievable speed and cost **while holding the quality of a first-rate advocate**. Every turn records wall-clock latency, model call count, token cost and model mix. A change that increases either must show the quality it bought in the same measurement.', 'Turn cost and latency are recorded for every turn and comparable across releases. A release that regresses either without an accompanying measured quality gain is treated as a defect.'],
    ['P4', '**The evaluator is itself evaluated**', 'A judge is a measuring instrument. Its agreement with human labels is measured before any number it produces is acted on, and re-measured periodically. The judge is **never** the model that produced the answer — same model, same blind spot, correlated failure.', 'Every judged item ships with a transcript it must reject. A judge\'s agreement rate with human labels is recorded with its version. An item that has never failed is reported as uncovered, not as passing.'],
    ['P5', '**The product is provider-agnostic, and it is proved by switching**', 'Steps declare a **tier** — `routine`, `hard`, `judge` or `embed` — and never a model. Today `routine` is **OpenAI gpt-4o-mini** and is the only serving tier; `hard` is **deliberately not configured**, because escalation is earned by measurement and nothing has earned it yet — requesting it raises `TierUnavailable` with that reason rather than silently serving from `routine`. `judge` is **OpenAI gpt-5.1**, genuinely different from the model under test, which is what makes P4 enforceable. **`embed` is the carve-out and it is stated honestly: changing it invalidates every vector in the corpus and is an ingest project, not an environment-variable change.** Every tier pins a dated snapshot, never a floating alias. See §7.4.', '**No model identifier or provider client appears in `core/`;** every tier resolves to a pinned snapshot; `judge` never resolves to the model under test; **a tier downgrade is never silent.** The port contract suite passes against a scripted adapter and every real adapter, including the declared context budget. **And the golden set passes with the provider environment variable flipped and nothing else changed** — an abstraction nobody has switched is an unexercised claim.'],
  ],
  [500, 1700, 3800, 3360],
));

A(new Paragraph({ children: [new PageBreak()] }));

module.exports = out;
