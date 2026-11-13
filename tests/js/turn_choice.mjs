// The model and the effort for a message (plan AN.33, D23; piece 33n): the send box's lists filled from the server's own, 6 Luna and
// Medium each time a conversation opens, Terra and Sol said as a cost beside Luna's, the choice in the message only where it is
// not the default, and under a reply the model and the effort it ran with. Runs the page's own code from nm/app/app.js against a
// stub DOM; not browser QA.
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
  + '\n' + between('function replyFooter(', '// A RESEARCH NOTE');

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
const offered = {
  models: [{ id: 'gpt-6-luna', label: '6 Luna', cost: '' }, { id: 'gpt-6.1-terra', label: '6.1 Terra', cost: "about 8-10x Luna's cost" },
    { id: 'gpt-6.1-sol', label: '6.1 Sol', cost: "about 16-20x Luna's cost" }],
  efforts: [{ id: 'low', label: 'Low' }, { id: 'medium', label: 'Medium' }, { id: 'high', label: 'High' }, { id: 'max', label: 'Max' }],
  default: { model: 'gpt-6-luna', effort: 'medium' },
};
const context = {
  document: { createElement: el, createTextNode: (t) => Object.assign(el('#text'), { _text: String(t) }) },
  $: (id) => nodes[id], state: {},
  api: async (path) => { asked.push(path); return offered; },
  replyIconButton: () => el('button'), rateControl: () => el('span'), noteAvailable: () => false, noteControl: () => el('span'),
  answeredAt: () => null, navigator: {}, setTimeout,
};
vm.createContext(context);
vm.runInContext(source + '\nthis.exported = { resetTurnChoice, loadTurnChoices, replyFooter };', context);
const { resetTurnChoice, loadTurnChoices, replyFooter } = context.exported;

// The lists come from the server, each model with its cost beside Luna's, and the defaults it gives.
await loadTurnChoices();
assert.deepEqual(asked, ['/api/turn-choices']);
assert.deepEqual(nodes['turn-model'].children.map((option) => [option.value, option.textContent]), [
  ['gpt-6-luna', '6 Luna'], ['gpt-6.1-terra', "6.1 Terra · about 8-10x Luna's cost"], ['gpt-6.1-sol', "6.1 Sol · about 16-20x Luna's cost"]]);
assert.deepEqual(nodes['turn-effort'].children.map((option) => option.textContent), ['Low', 'Medium', 'High', 'Max']);
assert.equal(nodes['turn-model'].value, 'gpt-6-luna');
assert.equal(nodes['turn-effort'].value, 'medium');

// The defaults travel as nothing; a choice travels as itself, and Terra and Sol say their cost.
assert.deepEqual({ ...context.state.turnChoice }, {});
nodes['turn-model'].value = 'gpt-6.1-sol';
nodes['turn-model'].onchange();
assert.equal(nodes['turn-cost'].textContent, "about 16-20x Luna's cost");
assert.equal(nodes['turn-cost'].hidden, false);
nodes['turn-effort'].value = 'max';
nodes['turn-effort'].onchange();
assert.deepEqual({ ...context.state.turnChoice }, { model: 'gpt-6.1-sol', effort: 'max' });
assert.ok(app.includes('...(state.turnChoice || {}),'), 'the message carries what was chosen');

// A conversation opened starts again at 6 Luna and Medium.
assert.ok(between('function startMatter(', '// F-A-18,').includes('resetTurnChoice();'));
resetTurnChoice();
assert.equal(nodes['turn-model'].value, 'gpt-6-luna');
assert.equal(nodes['turn-effort'].value, 'medium');
assert.equal(nodes['turn-cost'].hidden, true);
assert.deepEqual({ ...context.state.turnChoice }, {});

// Under a reply, what it ran with, where the turn recorded it.
const foot = replyFooter({ answer: { metrics: { chosen: { model: 'gpt-6.1-terra', effort: 'high' } } } }, () => '');
assert.ok(foot.children.some((kid) => kid.className === 'reply-chosen' && kid.textContent === '6.1 Terra · High'));
const older = replyFooter({ answer: { metrics: {} } }, () => '');
assert.ok(!older.children.some((kid) => kid.className === 'reply-chosen'), 'an answer saved before says nothing');

// Plan AN.49 (D186): the foot of every answer that can be kept offers the note plainly, saying what it holds.
context.noteAvailable = () => true;
context.noteControl = (_answer, _status, called) => Object.assign(el('span'), { className: 'note-control', called });
const offering = replyFooter({ answer: { metrics: {} } }, () => '');
assert.equal(offering.children.find((kid) => kid.className === 'note-control').called, 'The full note, with every source:');

console.log('turn choice: ok');
