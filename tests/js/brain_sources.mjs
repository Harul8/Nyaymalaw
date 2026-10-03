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
assert.ok(nodes.get('brain-source-body').textContent.includes(checkedBoard.verification.support_excerpt));
assert.ok(nodes.get('brain-source-body').textContent.includes(checkedBoard.verification.scope_excerpt));
reads.at(-1).resolve(saved); await pendingResponseRead;
assert.equal(nodes.get('brain-source-title').textContent, checkedBoard.title);
assert.equal(nodes.get('brain-source-body').children.at(-1).textContent, checkedBoard.text);
assert.equal(reader.openRecordSource({...checkedBoard, text:'Wrong source text'}, opener), false);
assert.equal(nodes.get('brain-source-body').children.at(-1).textContent, checkedBoard.text);
reader.close();
assert.equal(boardOpener.focused, true);

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
