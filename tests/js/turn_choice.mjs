// The model and the effort for a message (plan AN.33, D23; piece 33n): the send box's lists filled from the server's own, 6 Luna and
// Standard each time a conversation opens, Terra said as a cost beside Luna's, the choice in the message only where it is not the
// default, and under a reply the model, how thorough (plan AN.58, D288) and who reviewed it (plan AN.51, D289). Runs the page's own
// code from nm/app/app.js against a stub DOM; not browser QA.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const here = dirname(fileURLToPath(import.meta.url));
const app = readFileSync(join(here, '..', '..', 'nm', 'app', 'app.js'), 'utf8');
const between = (start, end) => {
  const a = app.indexOf(start);
  const b = app.indexOf(end, a + start.length);
  if (a < 0 || b < 0 || b <= a) throw new Error(`page code boundary moved: ${start}`);
  return app.slice(a, b);
};
const source = between('// THE MODEL AND THE EFFORT FOR A MESSAGE', '// F-A-18,')
  + '\n' + between('function replyFooter(', '// A RESEARCH NOTE')
  + '\n' + between('function restoredTurn(turn) {', '// LB-83. WHEN THE ANSWER WAS SAVED');

function el(tag) {
  return {
    tagName: tag.toUpperCase(), className: '', children: [], _text: '', value: '', hidden: false, attributes: {}, dataset: {},
    set textContent(v) { this._text = String(v); this.children = []; },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
    append(...kids) { this.children.push(...kids); },
    appendChild(k) { this.children.push(k); return k; },
    replaceChildren(...kids) { this.children = kids; },
    addEventListener() {},
    setAttribute(name, value) { this.attributes[name] = String(value); },
  };
}
const nodes = { 'turn-model': el('select'), 'turn-effort': el('select'), 'turn-cost': el('span') };
Object.assign(nodes['turn-model'], { value: 'gpt-6-luna', dataset: { default: 'gpt-6-luna' } });
Object.assign(nodes['turn-effort'], { value: 'medium', dataset: { default: 'medium' } });
const asked = [];
// The server's lists as /api/turn-choices gives them (tests/test_the_send_box_offers_the_servers_models_and_efforts.py).
const offered = {
  models: [{ id: 'gpt-6-luna', label: '6 Luna (routine work)', cost: '' },
    { id: 'gpt-6.1-terra', label: '6.1 Terra (complex matters)', cost: "about 8-10x Luna's cost" }],
  efforts: [{ id: 'low', label: 'Quick' }, { id: 'medium', label: 'Standard' }, { id: 'high', label: 'Thorough' },
    { id: 'max', label: 'Most thorough' }],
  default: { model: 'gpt-6-luna', effort: 'medium' },
};
const context = {
  document: { createElement: el, createTextNode: (t) => Object.assign(el('#text'), { _text: String(t) }) },
  $: (id) => nodes[id], state: {},
  api: async (path) => { asked.push(path); return offered; },
  replyIconButton: () => el('button'), rateControl: () => el('span'), noteAvailable: () => false, noteControl: () => el('span'),
  searchSaid: () => null,  // plan AN.51 (51e): the search's limits, drawn by its own piece (tests/js/search_said.mjs)
  answeredAt: () => null, navigator: {}, setTimeout,
};
vm.createContext(context);
vm.runInContext(source + '\nthis.exported = { resetTurnChoice, loadTurnChoices, replyFooter, restoredTurn };', context);
const { resetTurnChoice, loadTurnChoices, replyFooter, restoredTurn } = context.exported;

// The lists come from the server, each model with its cost beside Luna's, and the defaults it gives.
await loadTurnChoices();
assert.deepEqual(asked, ['/api/turn-choices']);
assert.deepEqual(nodes['turn-model'].children.map((option) => [option.value, option.textContent]), [
  ['gpt-6-luna', '6 Luna (routine work)'], ['gpt-6.1-terra', "6.1 Terra (complex matters) · about 8-10x Luna's cost"]]);
assert.deepEqual(nodes['turn-effort'].children.map((option) => option.textContent), ['Quick', 'Standard', 'Thorough', 'Most thorough']);
assert.equal(nodes['turn-model'].value, 'gpt-6-luna');
assert.equal(nodes['turn-effort'].value, 'medium');

// The defaults travel as nothing; a choice travels as itself, and Terra says its cost.
assert.deepEqual({ ...context.state.turnChoice }, {});
nodes['turn-model'].value = 'gpt-6.1-terra';
nodes['turn-model'].onchange();
assert.equal(nodes['turn-cost'].textContent, "about 8-10x Luna's cost");
assert.equal(nodes['turn-cost'].hidden, false);
nodes['turn-effort'].value = 'max';
nodes['turn-effort'].onchange();
assert.deepEqual({ ...context.state.turnChoice }, { model: 'gpt-6.1-terra', effort: 'max' });
assert.ok(app.includes('...(state.turnChoice || {}),'), 'the message carries what was chosen');

// A conversation opened starts again at 6 Luna and Medium.
assert.ok(between('function startMatter(', '// F-A-18,').includes('resetTurnChoice();'));
resetTurnChoice();
assert.equal(nodes['turn-model'].value, 'gpt-6-luna');
assert.equal(nodes['turn-effort'].value, 'medium');
assert.equal(nodes['turn-cost'].hidden, true);
assert.deepEqual({ ...context.state.turnChoice }, {});

// Under a reply, what it ran with, where the turn recorded it: the model, how thorough in the send box's word, and who reviewed it
// - read from the turn's own record of its review calls, so that an answer saved before says the model that reviewed it then.
const said = (answer) => replyFooter({ answer }, () => '').children.find((kid) => kid.className === 'reply-chosen').textContent;
assert.equal(said({ metrics: { chosen: { model: 'gpt-6.1-terra', effort: 'high' } } }), '6.1 Terra · Thorough');
const calls = [{ operation: 'core_response_writer', model: 'gpt-6-luna' }, { operation: 'core_response_review', model: 'gpt-6.1-terra' },
  { operation: 'core_response_cross_check', model: 'gpt-6.1-terra' }];
assert.equal(said({ metrics: { chosen: { model: 'gpt-6-luna', effort: 'medium' }, calls } }), '6 Luna · Standard · reviewed by 6.1 Terra');
assert.equal(said({ metrics: { chosen: { model: 'gpt-6-luna', effort: 'low' },
  calls: [{ operation: 'core_response_review', model: 'gpt-6-luna' }] } }), '6 Luna · Quick · reviewed by 6 Luna');
assert.equal(said({ metrics: { chosen: { model: 'auto', effort: 'max' }, calls: [...calls,
  { operation: 'core_response_review', model: 'gpt-6-luna' }] } }), 'Auto · Most thorough · reviewed by 6.1 Terra and 6 Luna');
const older = replyFooter({ answer: { metrics: {} } }, () => '');
assert.ok(!older.children.some((kid) => kid.className === 'reply-chosen'), 'an answer saved before says nothing');
// Plan AN.79 (D337): an answer reopened from history says the same line as when it was given, from the saved turn's own record -
// and carries nothing else of that record (no costs or counts).
{
  const saved = { committed: true, release_state: 'released', chat_id: 'c', turn_id: 't', elements: [], message: 'Asked.',
    metrics: { chosen: { model: 'gpt-6-luna', effort: 'medium' }, cost_usd: 0.309, estimate: { usd: 0.232 },
      calls: [{ operation: 'core_response_review', model: 'gpt-6-luna', cost_usd: 0.01, tokens_in: 900 }] } };
  const reopened = restoredTurn(saved).answer;
  assert.equal(said(reopened), '6 Luna · Standard · reviewed by 6 Luna');
  assert.equal(JSON.stringify(reopened.metrics), JSON.stringify({ chosen: { model: 'gpt-6-luna', effort: 'medium' },
    calls: [{ operation: 'core_response_review', model: 'gpt-6-luna' }] }));
  assert.equal(restoredTurn({ ...saved, metrics: { cost_usd: 1 } }).answer.metrics, null, 'a turn saved before says nothing');
  assert.equal(restoredTurn({ ...saved, metrics: undefined }).answer.metrics, null);
}

// Plan AN.49 (D186): the foot of every answer that can be kept offers the note plainly, saying what it holds.
context.noteAvailable = () => true;
context.noteControl = (_answer, _status, called) => Object.assign(el('span'), { className: 'note-control', called });
const offering = replyFooter({ answer: { metrics: {} } }, () => '');
assert.equal(offering.children.find((kid) => kid.className === 'note-control').called, 'The full note, with every source:');

console.log('turn choice: ok');
