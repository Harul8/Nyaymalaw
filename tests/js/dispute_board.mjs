import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const here = dirname(fileURLToPath(import.meta.url));
const app = readFileSync(join(here, '..', '..', 'nm', 'app', 'app.js'), 'utf8');
const html = readFileSync(join(here, '..', '..', 'nm', 'app', 'index.html'), 'utf8');
assert.ok(!html.includes('id="matter-board"'));
assert.ok(!app.includes('function renderMatterBoard('));
const start = app.indexOf('function requirementsFor(');
const end = app.indexOf('// F-B-17.', start);
assert.ok(start >= 0 && end > start);
const boardLoad = app.slice(app.indexOf('async function showThreadBoard('), start);
assert.ok(boardLoad.includes('await api(`/api/matters/${matterId}`)'));
assert.ok(!boardLoad.includes("api('/api/matters')"));
assert.ok(boardLoad.includes("if (deferBoard) showMatterStatus('building'"));
assert.ok(boardLoad.includes("setWorkView('matter');"));

class Element {
  constructor(tag) {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.dataset = {};
    this.listeners = new Map();
    this.open = false;
    this.isConnected = true;
    this._text = '';
  }
  get textContent() {
    return this._text + this.children.map(child => child.textContent).join('');
  }
  set textContent(value) {
    this._text = String(value);
    this.children = [];
  }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren(...children) { this._text = ''; this.children = children; }
  setAttribute(key, value) { this[key] = value; }
  addEventListener(name, callback) {
    if (!this.listeners.has(name)) this.listeners.set(name, []);
    this.listeners.get(name).push(callback);
  }
  fire(name, event = {}) {
    for (const callback of this.listeners.get(name) || []) callback(event);
  }
  showModal() { this.open = true; }
  close() { this.open = false; this.fire('close'); }
  focus() { document.activeElement = this; }
}

const elements = new Map();
const document = {
  activeElement: null,
  createElement: tag => new Element(tag),
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, new Element('div'));
    return elements.get(id);
  },
};
const state = { matterId: 'matter-a', disputeFocus: null };
const context = {
  document, state,
  $: id => document.getElementById(id),
  stateBlock: (_kind, message) => {
    const block = new Element('p'); block.textContent = message; return block;
  },
  renderRequirements: (host, row) => {
    const record = new Element('p');
    record.textContent = row.requirements?.map(need => need.need).join(', ') || '';
    host.appendChild(record);
  },
};
vm.createContext(context);
vm.runInContext(app.slice(start, end), context, { filename: 'nm/app/app.js' });

const body = new Element('div');
context.renderDisputeBoard(body, { disputes: [] }, { state: 'ok', rows: [] });
assert.equal(body.textContent, 'No disputes identified yet.');

const worked = {
  thread_id: 'thread-1', label: 'Boundary obstruction',
  status: 'needs_information', next_need: 'Ask about access.',
  requirements_state: 'established', requirements: [{ need: 'Gate photographs' }],
};

const rows = [
  {
    id: 'dispute-1', label: 'Refund refusal', identification: 'identified',
    statement: 'Whether the supplier refused a contractually due refund.',
    quoted: 'The supplier refused to refund me.',
    why_material: 'The refusal affects the available remedy.',
    source_turn_id: 'turn-1', prior_references: [
      { role: 'advocate', quoted: 'I asked for a refund.', turn_id: 'turn-0' },
    ],
  },
  {
    id: 'dispute-2', label: 'Notice of termination', identification: 'needs_clarification',
    statement: 'Whether the termination notice was ever served.',
    quoted: 'I do not recall receiving notice.',
    why_material: 'Service may affect the effective date.',
    clarification: 'Was notice sent to you or your representative?',
    source_turn_id: 'turn-2', prior_references: [],
  },
  {
    statement: 'An older saved dispute without identification metadata.',
    quoted: 'An older saved dispute', why_material: '',
    source_turn_id: 'turn-3', prior_references: [],
  },
];
const materialRecord = {
  state: 'ok',
  by_dispute: {
    'dispute-1': [
      {
        kind: 'event', statement: 'The supplier declined the requested refund.',
        quoted: 'They told me the refund was denied.', source_turn_id: 'turn-4',
        basis: 'stated', why_material: 'May affect the remedy.', relation: 'new',
        prior_references: [],
      },
      {
        kind: 'evidence', statement: 'The advocate describes a receipt.',
        quoted: 'I have the receipt.', source_turn_id: 'turn-5',
        basis: 'described_record', why_material: 'May document payment.',
        relation: 'adds', prior_references: [
          { role: 'advocate', quoted: 'I bought it last week.', turn_id: 'turn-1' },
        ],
      },
    ],
    'dispute-2': [{ kind: 'procedure', statement: 'Service of notice is uncertain.',
      quoted: 'I do not recall receiving notice.', source_turn_id: 'turn-2',
      basis: 'uncertain', relation: 'new', prior_references: [],
      why_material: 'May affect timing.' }],
  },
  matter: [{
    kind: 'evidence', statement: 'The advocate says relevant records are available.',
    quoted: 'I have the documents.', source_turn_id: 'turn-6',
    basis: 'described_record', relation: 'new', prior_references: [],
    why_material: 'The records may need examination.',
  }],
  unresolved: [{
    kind: 'event', statement: 'The date of an incident remains unassigned.',
    quoted: 'Something happened in July.', source_turn_id: 'turn-7',
    basis: 'uncertain', relation: 'new', prior_references: [],
    why_material: 'The date may affect timing.',
  }],
  history: [], problems: [],
};
const requirementsRecord = {
  state: 'incomplete',
  status_by_dispute: {
    'thread-1': 'unassessed', 'dispute-1': 'ok', 'dispute-2': 'unavailable',
  },
  by_dispute: {
    'dispute-1': [
      { label: 'Refund obligation', need: 'Establish the condition for repayment.',
        why: 'The requested remedy depends on that condition.', force: 'required',
        record_status: 'mentioned', sources: [{ kind: 'statute', title: 'Source A',
          locator: 'A:12', text: 'Exact passage governing repayment.',
          verification: { support_excerpt: 'Exact passage governing repayment.',
            scope_excerpt: '', scope_status: 'no_special_condition',
            reason: 'The passage supports the item.' } }] },
      { label: 'Notice evidence', need: 'Check whether notice was sent.',
        why: 'It may strengthen the account.', force: 'strengthening',
        record_status: 'not_mentioned', sources: [{ kind: 'judgment', title: 'Source B',
          locator: 'B:8', text: 'Exact passage about notice when a request was sent.',
          verification: { support_excerpt: 'Exact passage about notice',
            scope_excerpt: 'when a request was sent',
            scope_status: 'asked_to_establish',
            reason: 'The passage supports checking the request.' } }] },
    ],
  },
};
context.renderDisputeBoard(body, { disputes: [worked] },
  { state: 'ok', rows }, materialRecord, requirementsRecord);
const list = body.children.find(child => child.tagName === 'UL');
assert.ok(list);
assert.equal(list.children.length, 4);
assert.equal(body.children.filter(child => child.tagName === 'H3').length, 1);
assert.ok(body.textContent.includes('Boundary obstruction'));
assert.ok(body.textContent.includes('Refund refusal'));
assert.ok(body.textContent.includes('Notice of termination'));
assert.ok(body.textContent.includes('Refund obligation'));
assert.ok(body.textContent.includes('Notice evidence'));
assert.ok(!body.textContent.includes('Establish the condition for repayment.'));
assert.ok(!body.textContent.includes('The requested remedy depends on that condition.'));
assert.ok(!body.textContent.includes('Exact passage governing repayment.'));
assert.ok(!body.textContent.includes('Supporting words:'));
assert.ok(!body.textContent.includes('Limiting condition:'));
assert.equal((body.textContent.match(/Provisional/g) || []).length, 1);
assert.ok(body.textContent.includes('Not assessed'));
assert.ok(!body.textContent.includes('supplier refused to refund'));
assert.ok(!body.textContent.includes('Why identified'));
assert.ok(!body.textContent.includes('Ask about access'));
assert.ok(!body.textContent.includes('Gate photographs'));
assert.ok(!body.textContent.includes('Needs information'));
assert.ok(!body.textContent.includes('The supplier declined the requested refund.'));
assert.ok(!body.textContent.includes('I have the receipt.'));
assert.ok(!body.textContent.includes('I have the documents.'));
assert.ok(!body.textContent.includes('Something happened in July.'));
assert.ok(!list.children[0].className.includes('uncertain'));
assert.ok(!list.children[1].className.includes('uncertain'));
assert.ok(list.children[2].className.includes('uncertain'));
assert.ok(!list.children[3].className.includes('uncertain'));

const workedButton = list.children[0].children[0];
const identified = list.children[1].children[0];
const uncertain = list.children[2].children[0];
const dialog = document.getElementById('dispute-reader');
workedButton.fire('pointerdown', { pointerType: 'mouse' });
workedButton.fire('click', { detail: 1 });
assert.equal(state.disputeFocus, null);
assert.equal(workedButton['aria-pressed'], 'false');
workedButton.fire('click', { detail: 2 });
workedButton.fire('dblclick');
assert.equal(dialog.open, true);
assert.equal(state.disputeFocus, null);
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('Current work'));
assert.ok(document.getElementById('dispute-reader-body').textContent
  .includes('Legal requirements have not been assessed for this dispute yet.'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('Gate photographs'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('No identification reason or source passage'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('Matter-wide material'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('Unassigned material (1)'));
assert.ok(!document.getElementById('dispute-reader-body').textContent.includes('The supplier declined the requested refund.'));
const focusAction = document.getElementById('dispute-reader-body').children
  .find(child => child.tagName === 'BUTTON');
focusAction.fire('click');
assert.equal(state.disputeFocus, 'thread-1');
assert.equal(workedButton['aria-pressed'], 'true');
assert.equal(dialog.open, false);
assert.equal(document.activeElement, workedButton);

identified.fire('click', { detail: 1 });
assert.equal(dialog.open, false);
identified.fire('dblclick');
assert.equal(dialog.open, true);
assert.ok(document.getElementById('dispute-reader-body').textContent.includes(rows[0].quoted));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes(rows[0].why_material));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('Why listed:'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('Legal requirements'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('What is needed: Establish the condition for repayment.'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('Why it matters: The requested remedy depends on that condition.'));
assert.ok(document.getElementById('dispute-reader-body').textContent
  .includes('Legal force: Required if cited law applies'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('Legal force: Strengthening'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('Related material was mentioned; it has not been examined.'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('No related material is linked in the current conversation record.'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('Source A · statute · A:12'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('Exact passage governing repayment.'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('Supporting words: “Exact passage governing repayment.”'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('Limiting condition: “when a request was sent”'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('I asked for a refund.'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('Material from the conversation'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('not findings'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('The supplier declined the requested refund.'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('They told me the refund was denied.'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('Described record; not examined'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('I bought it last week.'));
assert.ok(!document.getElementById('dispute-reader-body').textContent.includes('Service of notice is uncertain.'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('Matter-wide material'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('not specifically linked to this dispute'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('I have the documents.'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('Unassigned material (1)'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('have not been assigned to a dispute'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('Something happened in July.'));
const materialSections = document.getElementById('dispute-reader-body').children
  .filter(child => child.className === 'dispute-reader-material');
assert.equal(materialSections.length, 3);
assert.ok(materialSections[0].textContent.includes('The supplier declined the requested refund.'));
assert.ok(!materialSections[0].textContent.includes('I have the documents.'));
assert.ok(materialSections[1].textContent.includes('I have the documents.'));
assert.ok(!materialSections[1].textContent.includes('The supplier declined the requested refund.'));
assert.ok(!document.getElementById('dispute-reader-body').textContent.includes('Provisional'));
document.getElementById('dispute-reader-close').fire('click');
assert.equal(dialog.open, false);
assert.equal(document.activeElement, identified);

uncertain.fire('click', { detail: 0 });
assert.equal(dialog.open, true);
assert.ok(document.getElementById('dispute-reader-body').textContent.includes(rows[1].clarification));
assert.ok(document.getElementById('dispute-reader-body').textContent
  .includes('Legal requirements could not be read for this dispute right now.'));
assert.ok(document.getElementById('dispute-reader-body').textContent.includes('Service of notice is uncertain.'));
assert.ok(!document.getElementById('dispute-reader-body').textContent.includes('The supplier declined the requested refund.'));
assert.ok(!document.getElementById('dispute-reader-body').textContent.includes('Exact passage governing repayment.'));
context.closeDisputeReader(false);
assert.equal(dialog.open, false);
assert.equal(document.getElementById('dispute-reader-body').textContent, '');

const legacy = list.children[3].children[0];
legacy.fire('click', { detail: 0 });
assert.equal(dialog.open, true);
assert.ok(document.getElementById('dispute-reader-body').textContent
  .includes('Identification has not been assessed.'));
context.closeDisputeReader(false);

uncertain.fire('pointerdown', { pointerType: 'touch' });
uncertain.fire('click', { detail: 1 });
assert.equal(dialog.open, true);
state.matterId = 'matter-b';
context.closeDisputeReader(false);
assert.equal(dialog.open, false);
assert.equal(document.activeElement, document.getElementById('dispute-reader-close'));

const partialRequirements = {
  ...requirementsRecord,
  status_by_dispute: { 'dispute-1': 'partial' },
  diagnostics_by_dispute: { 'dispute-1': ['judgment search unavailable'] },
};
context.renderDisputeBoard(body, { disputes: [] }, { state: 'ok', rows: [rows[0]] },
  materialRecord, partialRequirements);
assert.ok(body.textContent.includes('Refund obligation'));
assert.ok(body.textContent.includes('Legal research incomplete; see details.'));
assert.ok(!body.textContent.includes('judgment search unavailable'));
body.children.find(child => child.tagName === 'UL').children[0].children[0].fire('dblclick');
assert.ok(document.getElementById('dispute-reader-body').textContent
  .includes('Legal research is incomplete.'));
assert.ok(document.getElementById('dispute-reader-body').textContent
  .includes('judgment search unavailable'));
assert.ok(document.getElementById('dispute-reader-body').textContent
  .includes('Supporting words:'));
context.closeDisputeReader(false);

context.renderDisputeBoard(body, { disputes: [] }, { state: 'ok', rows: [rows[0]] },
  materialRecord, { state: 'unavailable', by_dispute: {}, diagnostics: ['retrieval failed'] });
assert.ok(!body.textContent.includes('No legal requirements'));
body.children.find(child => child.tagName === 'UL').children[0].children[0].fire('dblclick');
assert.ok(document.getElementById('dispute-reader-body').textContent
  .includes('Legal requirements could not be read for this dispute right now.'));
assert.ok(document.getElementById('dispute-reader-body').textContent
  .includes('This does not establish that no law applies.'));
assert.ok(!document.getElementById('dispute-reader-body').textContent.includes('retrieval failed'));
