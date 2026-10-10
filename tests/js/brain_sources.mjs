import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

class Node {
  constructor(tag = 'div') {
    this.tagName = tag.toUpperCase(); this.children = []; this.handlers = new Map();
    this.attributes = new Map(); this.open = false; this._text = ''; this.isConnected = true;
  }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  set textContent(value) { this._text = String(value); this.children = []; }
  addEventListener(name, callback) { this.handlers.set(name, callback); }
  replaceChildren(...children) { this.children = children; this._text = ''; }
  appendChild(child) { this.children.push(child); return child; }
  append(...children) { this.children.push(...children); }
  setAttribute(name, value) { this.attributes.set(name, value); }
  showModal() { this.open = true; }
  close() { this.open = false; }
  focus() { this.focused = true; }
}
const nodes = new Map(['brain-source-reader', 'brain-source-title', 'brain-source-close',
  'brain-source-status', 'brain-source-body'].map(id => [id, new Node()]));
const events = new Map();
const window = {addEventListener:(name, callback) => events.set(name, callback)};
const document = {getElementById:id => nodes.get(id), createElement:tag => new Node(tag),
  createTextNode:text => { const node = new Node('#text'); node.textContent = text; return node; }};
vm.runInNewContext(fs.readFileSync('nm/app/brain-sources.js', 'utf8'), {window, document});
const reader = window.NmBrainSources;
const reads = [];
let session = 1;
reader.configure({scope:() => ({session}), request:url => new Promise((resolve, reject) => {
  reads.push({url, resolve, reject});
})});
const source = {brain:true, id:'saved-1', digest:'digest-1', text:'Exact saved words',
  label:'Saved passage', locator:'source-turn'};
const element = {source, sources:[source]};
const answer = {chat_id:'pending-chat', matter_id:null, turn_id:'source-turn'};
const saved = {...source, qualification:'Reported account, not proof'};
const opener = new Node(); opener.isConnected = true;

const opened = reader.open(answer, element, 2, 0, opener);
assert.equal(reads[0].url, '/api/chats/pending-chat/turns/source-turn/brain-sources/2/0');
reads[0].resolve(saved); await opened;
assert.equal(nodes.get('brain-source-body').children.at(-1).textContent, source.text);
assert.equal(nodes.get('brain-source-reader').open, true);
reader.close();
assert.equal(opener.focused, true);
assert.equal(nodes.get('brain-source-body').children.length, 0);

const stale = reader.open(answer, element, 0, 0, opener);
const current = reader.open({...answer, matter_id:'saved-matter'}, element, 1, 0, opener);
nodes.get('brain-source-reader').handlers.get('close')();
assert.equal(nodes.get('brain-source-reader').open, true);
assert.equal(reads[2].url, '/api/matters/saved-matter/turns/source-turn/brain-sources/1/0');
reads[2].resolve(saved); await current;
reads[1].resolve({...saved, text:'Old selection'}); await stale;
assert.equal(nodes.get('brain-source-body').children.at(-1).textContent, source.text);

const mismatch = reader.open(answer, element, 0, 0, opener);
reads[3].resolve({...saved, digest:'different'}); await mismatch;
assert.equal(nodes.get('brain-source-body').children.length, 0);
assert.match(nodes.get('brain-source-status').textContent, /could not be matched/);

const ended = reader.open(answer, element, 0, 0, opener);
session += 1; reader.close(false);
reads[4].resolve(saved); await ended;
assert.equal(nodes.get('brain-source-reader').open, false);
assert.equal(nodes.get('brain-source-body').children.length, 0);

const changed = reader.open(answer, element, 0, 0, opener);
events.get('nm:matter-changed')();
reads[5].reject(new Error('late failure')); await changed;
assert.equal(nodes.get('brain-source-status').textContent, '');
assert.equal(nodes.get('brain-source-reader').open, false);
console.log('PASS saved brain source reader ownership');

function descendants(host, tag) {
  return host.children.flatMap(child => [
    ...(child.tagName === tag.toUpperCase() ? [child] : []), ...descendants(child, tag),
  ]);
}
const legalSource = {brain:true, id:'legal-7', kind:'provision', label:'Example Act, 2025',
  locator:'Section 7', text:'Where the stated condition is met, the stated requirement applies.',
  digest:'legal-digest-7', qualification:'Exact saved legal passage, applicability remains open.'};
const conversationSource = {...source, kind:'conversation', label:'Your saved words'};
const recordSource = {...source, id:'record-1', kind:'record', label:'Saved gathering item',
  locator:'requirement-1', text:'Determine whether the stated condition is met.', digest:'record-digest'};
const repeatedLegal = {...legalSource, id:'different-checked-use'};
const bodyElement = {text:'Read Example Act, 2025 · Section 7 and Example Act, 2025. '
  + 'The longer word Section 70 is plain.',
  refs:[recordSource.locator, conversationSource.locator, legalSource.locator],
  source:recordSource, sources:[recordSource, conversationSource, legalSource, repeatedLegal]};
const bodyAnswer = {...answer, elements:[{text:'Earlier block'}, bodyElement]};
const body = new Node('p');
assert.equal(reader.appendBody(body, bodyAnswer, bodyElement), 2);
assert.equal(body.textContent, bodyElement.text);
assert.deepEqual(descendants(body, 'button').map(button => button.textContent),
  ['Example Act, 2025 · Section 7', 'Example Act, 2025']);
const bodyLink = descendants(body, 'button')[0];
const inlineRead = bodyLink.handlers.get('click')();
assert.equal(reads[6].url, '/api/chats/pending-chat/turns/source-turn/brain-sources/1/2');
reads[6].resolve(legalSource); await inlineRead;
assert.equal(nodes.get('brain-source-body').children.at(-1).textContent, legalSource.text);
assert.equal(bodyElement.sources.length, 4);
assert.equal(bodyElement.sources[3].id, repeatedLegal.id);

assert.equal(reader.labelFor(legalSource), 'Example Act, 2025 · Section 7');
assert.equal(reader.labelFor({title:'Example Decision', locator:'Example Decision, paragraph 9'}),
  'Example Decision, paragraph 9');
assert.equal(reader.labelFor({label:'Saved display title', title:'Other title',
  locator:'Saved display title, section 4'}), 'Saved display title, section 4');
assert.equal(reader.labelFor({title:'Example Decision', locator:'Different title, paragraph 9'}),
  'Example Decision · Different title, paragraph 9');
assert.equal(reader.labelFor({title:'Example Decision', locator:'example Decision, paragraph 9'}),
  'Example Decision · example Decision, paragraph 9');
assert.equal(reader.labelFor({title:'Example Decision'}), 'Example Decision');
assert.equal(reader.labelFor({locator:'Paragraph 9'}), 'Paragraph 9');
const fullLocatorSource = {...legalSource, locator:'Example Act, 2025, section 7'};
const secondParagraph = {...legalSource, id:'legal-8', kind:'judgment', label:'Example Decision',
  locator:'Paragraph 8', text:'A different exact court passage.', digest:'legal-digest-8'};
const firstParagraph = {...secondParagraph, id:'legal-3', locator:'Paragraph 3',
  text:'The earlier exact court passage.', digest:'legal-digest-3'};
const multiPassage = {text:'Example Decision is cited in Example Decision · Paragraph 8.',
  sources:[firstParagraph, secondParagraph], refs:['Paragraph 3', 'Paragraph 8']};
const multiAnswer = {...answer, elements:[multiPassage]};
const multiBody = new Node('p');
assert.equal(reader.appendBody(multiBody, multiAnswer, multiPassage), 1);
assert.equal(multiBody.textContent, multiPassage.text);
assert.equal(descendants(multiBody, 'button')[0].textContent, 'Example Decision · Paragraph 8');
const paragraphRead = descendants(multiBody, 'button')[0].handlers.get('click')();
assert.match(reads[7].url, /brain-sources\/0\/1$/);
reads[7].resolve(secondParagraph); await paragraphRead;
assert.equal(nodes.get('brain-source-body').children.at(-1).textContent, secondParagraph.text);

for (const other of [
  {...legalSource, id:'same-locator-other-text', text:'Different exact words', digest:'other-digest'},
  {...legalSource, id:'same-words-other-digest', digest:'other-digest'},
]) {
  const ambiguous = {text:'Example Act, 2025 · Section 7',
    sources:[legalSource, other], refs:[legalSource.locator]};
  const ambiguousAnswer = {...answer, elements:[ambiguous]};
  const ambiguousBody = new Node('p');
  assert.equal(reader.appendBody(ambiguousBody, ambiguousAnswer, ambiguous), 0);
  assert.equal(ambiguousBody.textContent, ambiguous.text);
}

for (const [unownedAnswer, unownedElement] of [
  [{...bodyAnswer, turn_id:''}, bodyElement],
  [bodyAnswer, {...bodyElement}],
  [bodyAnswer, {...bodyElement, refs:[]}],
]) {
  const unownedBody = new Node('p');
  assert.equal(reader.appendBody(unownedBody, unownedAnswer, unownedElement), 0);
  assert.equal(unownedBody.textContent, unownedElement.text);
}

const nonlegal = {text:'Your saved words contain <b>text</b>.',
  source:conversationSource, sources:[conversationSource], refs:[conversationSource.locator]};
const nonlegalBody = new Node('p');
assert.equal(reader.appendBody(nonlegalBody, {...answer, elements:[nonlegal]}, nonlegal), 0);
assert.equal(nonlegalBody.textContent, nonlegal.text);
assert.equal(descendants(nonlegalBody, 'b').length, 0);

const phraseElement = {text:'The condition must be established before proceeding.',
  sources:[conversationSource, legalSource], refs:[conversationSource.locator, legalSource.locator],
  inline_citations:[{text:'The condition', source_id:legalSource.id, source_index:1}]};
const phraseAnswer = {...answer, elements:[phraseElement]};
const phraseBody = new Node('p');
assert.equal(reader.appendBody(phraseBody, phraseAnswer, phraseElement), 1);
assert.equal(phraseBody.textContent, phraseElement.text);
assert.equal(descendants(phraseBody, 'button')[0].textContent, 'The condition');
assert.equal(reader.appendReferences, undefined);
for (const invalid of [
  {...phraseElement, inline_citations:[{text:'absent words', source_id:legalSource.id, source_index:1}]},
  {...phraseElement, inline_citations:[{text:'The condition', source_id:'unowned', source_index:1}]},
  {...phraseElement, inline_citations:[{text:'The condition', source_id:legalSource.id, source_index:0}]},
  {...phraseElement, text:'The condition repeats The condition.'},
]) {
  const invalidBody = new Node('p');
  assert.equal(reader.appendBody(invalidBody, {...answer, elements:[invalid]}, invalid), 0);
  assert.equal(invalidBody.textContent, invalid.text);
}

const checkedBoard = {id:'A1', kind:'provision', title:'Example Act, 2025', locator:'Section 7',
  text:legalSource.text, verification:{support_excerpt:'the stated requirement applies',
    scope_excerpt:'Where the stated condition is met', scope_status:'conditional',
    reason:'The passage supports this gathering item only under its stated condition.'}};
assert.equal(reader.isReadableRecordSource(checkedBoard), true);
assert.equal(reader.isReadableRecordSource({...checkedBoard, verification:{
  ...checkedBoard.verification, scope_excerpt:'a condition that is not in the passage'}}), false);
assert.equal(reader.isReadableRecordSource({...checkedBoard, verification:{
  ...checkedBoard.verification, support_excerpt:'invented supporting words'}}), false);
assert.equal(reader.isReadableRecordSource({...checkedBoard, id:''}), false);
assert.equal(reader.isReadableRecordSource({...checkedBoard, verification:null}), false);
assert.equal(reader.isReadableRecordSource({...checkedBoard, verification:{
  ...checkedBoard.verification, scope_excerpt:'', scope_status:'conditional'}}), false);
assert.equal(reader.isReadableRecordSource({...checkedBoard, verification:{
  ...checkedBoard.verification, scope_excerpt:'', scope_status:'no_special_condition'}}), true);

const pendingResponseRead = reader.open(answer, element, 0, 0, opener);
const requestsBeforeBoard = reads.length;
const boardOpener = new Node('button');
assert.equal(reader.openRecordSource(checkedBoard, boardOpener), true);
assert.equal(reads.length, requestsBeforeBoard);
assert.equal(nodes.get('brain-source-title').textContent, checkedBoard.title);
assert.equal(nodes.get('brain-source-body').children.at(-1).textContent, checkedBoard.text);
assert.match(nodes.get('brain-source-body').textContent, /Saved with this dispute's legal requirements/);
assert.match(nodes.get('brain-source-body').textContent, /historical check predates/);
assert.ok(nodes.get('brain-source-body').textContent.includes(checkedBoard.verification.support_excerpt));
assert.ok(nodes.get('brain-source-body').textContent.includes(checkedBoard.verification.scope_excerpt));
reads.at(-1).resolve(saved); await pendingResponseRead;
assert.equal(nodes.get('brain-source-title').textContent, checkedBoard.title);
assert.equal(nodes.get('brain-source-body').children.at(-1).textContent, checkedBoard.text);
assert.equal(reader.openRecordSource({...checkedBoard, text:'Wrong source text'}, opener), false);
assert.equal(nodes.get('brain-source-body').children.at(-1).textContent, checkedBoard.text);
reader.close();
assert.equal(boardOpener.focused, true);

reader.openRecordSource(checkedBoard, boardOpener, {reviewPending:false});
assert.doesNotMatch(nodes.get('brain-source-body').textContent, /historical check predates/);

reader.openRecordSource(checkedBoard, boardOpener);
const afterBoardRead = reader.open(answer, element, 0, 0, opener);
assert.equal(nodes.get('brain-source-body').children.length, 0);
reads.at(-1).resolve(saved); await afterBoardRead;
assert.equal(nodes.get('brain-source-body').children.at(-1).textContent, source.text);
assert.doesNotMatch(nodes.get('brain-source-body').textContent, /Supporting words/);

const changedMetadata = reader.open(bodyAnswer, bodyElement, 1, 2, opener);
reads.at(-1).resolve({...legalSource, label:'Different saved label'}); await changedMetadata;
assert.equal(nodes.get('brain-source-body').children.length, 0);
assert.match(nodes.get('brain-source-status').textContent, /could not be matched/);
reader.openRecordSource(checkedBoard, boardOpener);
events.get('nm:matter-changed')();
assert.equal(nodes.get('brain-source-reader').open, false);
assert.equal(nodes.get('brain-source-body').children.length, 0);
for (const treatment of ['adopted', 'rejected']) {
  const excerpt = `The applicant submitted a proposition. The court ${treatment} it.`;
  const labeled = {id:'labeled-decision', kind:'judgment', title:'Synthetic decision',
    locator:'Paragraph 2', text:excerpt, verification:{contract:'research_support_v3',
      assertion_role:'court_conclusion', assertion_statement:`The court ${treatment} the submission.`,
      owner_label:'The deciding court', support_excerpt:`The court ${treatment} it.`,
      owner_excerpt:`The court ${treatment} it.`, treatment_excerpt:`The court ${treatment} it.`,
      source_treatment:'adopted', scope_excerpt:'', scope_status:'no_special_condition',
      reason:'The court states its conclusion.', context_statements:[{
        assertion_role:'party_submission', assertion_statement:'The applicant advanced the proposition.',
        owner_label:'The applicant', source_treatment:treatment,
        support_excerpt:'The applicant submitted a proposition.',
        owner_excerpt:'The applicant submitted a proposition.',
        treatment_excerpt:`The court ${treatment} it.`,
      }]}};
  assert.equal(reader.openRecordSource(labeled, boardOpener), true);
  assert.match(nodes.get('brain-source-body').textContent,
    new RegExp(`Party submission · Court ${treatment}`));
  assert.match(nodes.get('brain-source-body').textContent, /Speaker: The applicant/);
}
console.log('PASS exact inline legal links and checked dispute-source reading');

// Related passages stay inside the reader and each selection reads its own saved row.
const submissionSource = {...firstParagraph, id:'submission-source', digest:'submission-digest',
  text:'Counsel submitted a proposition.', qualification:'Party submission.', verification:{
    assertion_role:'party_submission', source_role:'party_submission', owner_label:'Respondent',
    assertion_statement:'The court rejected this submission.', support_excerpt:'Counsel submitted a proposition.',
    source_treatment:'rejected', treatment_excerpt:'The court rejected the submission.'}};
const treatmentSource = {...secondParagraph, id:'treatment-source', digest:'treatment-digest',
  text:'The court rejected the submission.', qualification:'Passage selected for court treatment.',
  verification:{assertion_role:'unclear', source_role:'treatment_support',
    assertion_statement:'The court rejected the submission.', support_excerpt:'The court rejected the submission.',
    source_treatment:'not applicable'}};
const relatedElement = {text:'The court rejected the submission; the statutory exception remains material.',
  source:submissionSource, sources:[submissionSource, treatmentSource, legalSource],
  refs:[submissionSource.locator, treatmentSource.locator, legalSource.locator],
  inline_citations:[{text:'The court rejected the submission', source_id:submissionSource.id, source_index:0}]};
const relatedAnswer = {...answer, elements:[relatedElement]};
const relatedOpener = new Node('button');
const unchangedRelated = JSON.stringify(relatedElement);
const titleNode = nodes.get('brain-source-title');
const closeNode = nodes.get('brain-source-close');

async function openRelated() {
  const opening = reader.open(relatedAnswer, relatedElement, 0, 0, relatedOpener);
  reads.at(-1).resolve(submissionSource); await opening;
  const nav = descendants(nodes.get('brain-source-body'), 'nav');
  assert.equal(nav.length, 1);
  assert.equal(nav[0].attributes.get('aria-label'), 'Sources supporting this response paragraph');
  return descendants(nav[0], 'button');
}

let choices = await openRelated();
assert.equal(choices.length, 3);
assert.equal(choices[0].disabled, true);
assert.equal(choices[0].attributes.get('aria-current'), 'true');
assert.equal(choices[1].disabled, false);
assert.match(nodes.get('brain-source-body').textContent, /Court rejected/);
const beforeCurrentClick = reads.length;
choices[0].handlers.get('click')();
assert.equal(reads.length, beforeCurrentClick);
const readTreatment = choices[1].handlers.get('click')();
assert.match(reads.at(-1).url, /brain-sources\/0\/1$/);
assert.equal(nodes.get('brain-source-body').children.length, 0,
  'Client-side related text is not displayed while the saved read is pending');
const afterTreatmentClick = reads.length;
choices[2].handlers.get('click')();
assert.equal(reads.length, afterTreatmentClick, 'A superseded selector cannot start a new read');
reads.at(-1).resolve(treatmentSource); await readTreatment;
assert.equal(nodes.get('brain-source-body').children.at(-1).textContent, treatmentSource.text);
assert.match(nodes.get('brain-source-body').textContent, /Passage used to assess court treatment/);
assert.match(nodes.get('brain-source-body').textContent, /Not applicable/);
choices = descendants(descendants(nodes.get('brain-source-body'), 'nav')[0], 'button');
assert.equal(choices[1].disabled, true);
const readStatute = choices[2].handlers.get('click')();
assert.match(reads.at(-1).url, /brain-sources\/0\/2$/);
reads.at(-1).resolve(legalSource); await readStatute;
assert.equal(nodes.get('brain-source-body').children.at(-1).textContent, legalSource.text);
assert.equal(nodes.get('brain-source-title'), titleNode);
assert.equal(nodes.get('brain-source-close'), closeNode);
assert.equal(JSON.stringify(relatedElement), unchangedRelated);
reader.close();
assert.equal(relatedOpener.focused, true, 'Closing after a switch restores the original citation focus');

for (const field of ['id', 'digest', 'text', 'locator', 'label', 'kind']) {
  choices = await openRelated();
  const pending = choices[1].handlers.get('click')();
  reads.at(-1).resolve({...treatmentSource, [field]:`changed-${field}`}); await pending;
  assert.equal(nodes.get('brain-source-body').children.length, 0);
  assert.match(nodes.get('brain-source-status').textContent, /could not be matched/);
}

choices = await openRelated();
const beforeScopeChange = reads.length;
session += 1;
choices[1].handlers.get('click')();
assert.equal(reads.length, beforeScopeChange, 'A selector from another session cannot read a source');
reader.close(false);
choices = await openRelated();
const lateRelated = choices[1].handlers.get('click')();
events.get('nm:matter-changed')();
reads.at(-1).resolve(treatmentSource); await lateRelated;
assert.equal(nodes.get('brain-source-reader').open, false);
assert.equal(nodes.get('brain-source-body').children.length, 0);
assert.equal(nodes.get('brain-source-status').textContent, '');
const beforeClosedClick = reads.length;
choices[2].handlers.get('click')();
assert.equal(reads.length, beforeClosedClick);

const incompleteRefs = {...relatedElement, refs:[submissionSource.locator]};
const incompleteAnswer = {...answer, elements:[incompleteRefs]};
const incompleteOpen = reader.open(incompleteAnswer, incompleteRefs, 0, 0, relatedOpener);
reads.at(-1).resolve(submissionSource); await incompleteOpen;
assert.equal(descendants(nodes.get('brain-source-body'), 'nav').length, 0,
  'Unbound related references never become selectable');

for (const [role, label] of [
  ['contract', 'Quoted contract terms'], ['original_account', 'Original account'],
  ['opposing_account', 'Opposing account'],
]) {
  const labeled = {...checkedBoard, verification:{...checkedBoard.verification,
    assertion_role:role, source_role:role, source_treatment:'not_shown'}};
  assert.equal(reader.openRecordSource(labeled, boardOpener), true);
  assert.ok(nodes.get('brain-source-body').textContent.includes(`Statement role: ${label}`));
  assert.match(nodes.get('brain-source-body').textContent, /Treatment in the source: Not shown/);
}
const crossKindRelated = {...checkedBoard, verification:{...checkedBoard.verification,
  context_statements:[{assertion_role:'party_submission', assertion_statement:'A related submission.',
    source_treatment:'qualified', treatment_excerpt:'The court limited that submission.'}]}};
reader.openRecordSource(crossKindRelated, boardOpener);
assert.match(nodes.get('brain-source-body').textContent, /Party submission · Court qualified/);
console.log('PASS related saved-source selection, identity checks, invalidation and readable roles');

const authorityView = (selected, changes = {}) => ({contract:'core_source_authority_view_v1',
  activity_contract:'core_turn_v2', unit_id:'source-turn:b1', source_id:selected.id,
  state:'recorded', reason:null, case_checks:[], provision_checks:[], provision_mentions:[],
  limits:[], ...changes});
async function inspectAuthority(selected, inspection, clientInspection = null) {
  const canonical = {...selected, ...(clientInspection ? {authority_inspection:clientInspection} : {})};
  const item = {text:'The supported response.', source:canonical, sources:[canonical], refs:[selected.locator]};
  const response = {...answer, elements:[item]};
  const before = JSON.stringify(item);
  const pending = reader.open(response, item, 0, 0, opener);
  assert.equal(nodes.get('brain-source-body').children.length, 0);
  reads.at(-1).resolve({...selected, authority_inspection:inspection}); await pending;
  assert.equal(nodes.get('brain-source-body').children.at(-1).textContent, selected.text);
  assert.equal(JSON.stringify(item), before, 'Display evidence must not mutate canonical response sources');
  assert.equal(nodes.get('brain-source-title'), titleNode);
  assert.equal(nodes.get('brain-source-close'), closeNode);
  return nodes.get('brain-source-body').textContent;
}

const caseEvidence = {citation_id:'c1', text:'(2000) 1 SCC 10', lookup:'found',
  name_given:'First Party v Second Party', name_check:'matches_recorded_name',
  judgments:[{case_id:'case-1', title:'First Party v Second Party', court:'Example Court', decided_on:'2000-01-02'}],
  association:'matched', matching_source_ids:[secondParagraph.id], selected_support_mentions:[],
  association_scope:'Identity comparison only; speaker, reliance and legal effect require review',
  legal_validity:'not_assessed', quotes:[{quote:'<em>Exact reported words</em>', result:'not_found',
    detail:'These words are not in the held text.', attribution:'single_candidate'}]};
let authorityText = await inspectAuthority(secondParagraph,
  authorityView(secondParagraph, {case_checks:[caseEvidence]}));
assert.match(authorityText, /Citation lookup: Found in the held corpus/);
assert.match(authorityText, /Name comparison: Matches the recorded name/);
assert.match(authorityText, /Citation resolves to this passage’s judgment/);
assert.match(authorityText, /Quotation wording: Words not found in the held judgment text/);
assert.match(authorityText, /Legal validity: Not assessed/);
assert.ok(authorityText.includes('<em>Exact reported words</em>'));
assert.equal(descendants(nodes.get('brain-source-body'), 'em').length, 0);
assert.equal(descendants(nodes.get('brain-source-body'), 'section').length, 1);
assert.equal(descendants(nodes.get('brain-source-body'), 'section')[0].attributes.get('aria-label'),
  'Saved source checks');
assert.doesNotMatch(authorityText, /Source checks: Found|Verified authority|Citation verified/);

for (const [lookup, label] of [['ambiguous','More than one held judgment'],
  ['unavailable','Could not be checked'], ['not_held','Not held by Nyaymalaw'], ['future_state','Not assessed']]) {
  authorityText = await inspectAuthority(secondParagraph, authorityView(secondParagraph,
    {case_checks:[{...caseEvidence, lookup, name_check:null, quotes:[], association:'unresolved_association'}]}));
  assert.ok(authorityText.includes(`Citation lookup: ${label}`));
  assert.match(authorityText, /Name comparison: Not assessed/);
  assert.match(authorityText, /Quotation check: Not assessed/);
}

authorityText = await inspectAuthority(secondParagraph, authorityView(secondParagraph, {
  case_checks:[{...caseEvidence, association:'different_used_identity', name_check:'not_given',
    selected_support_mentions:[{source_id:secondParagraph.id, text:'(2000) 1 SCC 10',
      source_role_proposal:'quoted_authority'}], quotes:[{quote:'Exact reported words', result:'found',
      attribution:'unresolved', detail:'These words occur in the held text; read their context.'}]}]}));
assert.match(authorityText, /Citation resolves to a different judgment from the passage used/);
assert.match(authorityText, /Citation mentioned in this passage: \(2000\) 1 SCC 10/);
assert.match(authorityText, /Quotation wording: Words found in the held judgment text/);
assert.match(authorityText, /Quotation association: Candidate judgment unresolved/);
assert.match(authorityText, /Name comparison: No name supplied/);
assert.doesNotMatch(authorityText, /False citation|Court adopted/);

authorityText = await inspectAuthority(secondParagraph, authorityView(secondParagraph,
  {case_checks:[{...caseEvidence, matching_source_ids:['other-used-source']}]}));
assert.match(authorityText, /Citation resolves to another judgment used in this response paragraph/);
assert.doesNotMatch(authorityText, /Citation resolves to this passage’s judgment/);

for (const [state, label] of [['matched','Matches the selected saved passage'],
  ['different_snapshot','Readback differs from the selected saved passage'],
  ['unavailable','Could not be checked'], ['ambiguous','More than one provision matches'],
  ['not_held','Not held under the selected Act and reference'], ['future_state','Not assessed']]) {
  authorityText = await inspectAuthority(legalSource, authorityView(legalSource,
    {provision_checks:[{source_id:legalSource.id, state, reason:'Saved exact readback detail.',
                       legal_version:'not_assessed'}],
     provision_mentions:[{text:'Section 7', act_name_association:'not_assessed',
                          reason:'The wording alone does not resolve which Act is meant.'}]}));
  assert.ok(authorityText.includes(`Provision readback: ${label}`));
  assert.match(authorityText, /Legal version and applicability: Not assessed/);
  assert.match(authorityText, /Act-name association: Not assessed/);
  assert.doesNotMatch(authorityText, /Citation lookup:/);
}

for (const evidence of [undefined, {contract:'future_view'},
  authorityView(legalSource, {source_id:'another-source'}),
  authorityView(legalSource, {activity_contract:'future_turn'}),
  authorityView(legalSource, {provision_checks:undefined})]) {
  authorityText = await inspectAuthority(legalSource, evidence,
    authorityView(legalSource, {provision_checks:[{state:'matched'}]}));
  assert.match(authorityText, /Source checks: Not assessed/);
  assert.doesNotMatch(authorityText, /Provision readback: Matches/,
    'Unconfirmed client evidence cannot replace missing saved evidence');
}
authorityText = await inspectAuthority(legalSource, authorityView(legalSource,
  {activity_contract:'core_turn_v1', state:'not_assessed',
   reason:'Authority checks were not recorded for this earlier response.'}));
assert.match(authorityText, /Source checks: Not assessed/);
assert.match(authorityText, /earlier response/);

authorityText = await inspectAuthority(conversationSource, authorityView(conversationSource,
  {case_checks:[caseEvidence]}));
assert.doesNotMatch(authorityText, /Saved source checks|Citation lookup|Legal validity/,
  'An account passage must not acquire a legal-status panel');
reader.openRecordSource({...checkedBoard, authority_inspection:authorityView(checkedBoard,
  {case_checks:[caseEvidence]})}, boardOpener);
assert.match(nodes.get('brain-source-body').textContent, /Source checks: Not assessed/);
assert.doesNotMatch(nodes.get('brain-source-body').textContent, /Citation lookup: Found/,
  'Historical direct record metadata is not an authenticated authority read receipt');
console.log('PASS separate saved authority checks, unresolved neighbors, legacy and exact passage preservation');
