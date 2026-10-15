// Adding to a question while it is worked on (owner decision, 15 Oct 2026, as in
// Cursor): what is sent meanwhile waits on the question's conversation and goes next
// once the answer is saved; after a failure it returns to the message box.
// Offline substitutes for the DOM and delivery; not browser QA.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app = fs.readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
const between = (from, to) => {
  const a = app.indexOf(from);
  const b = app.indexOf(to, a + from.length);
  assert.ok(a >= 0 && b > a, `moved: ${from}`);
  return app.slice(a, b);
};

function harness() {
  const box = { value: '' };
  const sent = [];
  let repaints = 0;
  const context = vm.createContext({
    $: (id) => (id === 'message' ? box : {}),
    activeDelivery: null, sizeComposer() {}, repaint() { repaints += 1; },
    ownsIntent: () => true, send: (text) => { sent.push(text); },
    attachmentsBlockSend: () => null,
  });
  vm.runInContext(between('// ADD TO A QUESTION WHILE IT IS WORKED ON', '// WHAT A TURN IN PROGRESS IS DOING'), context);
  return { context, box, sent, repaints: () => repaints };
}

// Queued on the conversation of the question being worked on, and the box cleared.
{
  const { context, box, sent } = harness();
  const intent = { text: 'typed' };
  context.activeDelivery = { entry: { context: intent } };
  box.value = 'The appointment letter is dated 2 May.';
  context.queueAddition(box.value);
  context.queueAddition('   ');  // nothing to add
  assert.equal(JSON.stringify(intent.queued), '["The appointment letter is dated 2 May."]');
  assert.equal(box.value, '');
  assert.equal(intent.text, '');
  // Once the answer is saved, what waited goes next as one message.
  context.queueAddition('Check leave encashment too.');
  context.activeDelivery = null;
  context.releaseQueued({ state: 'committed', context: intent });
  assert.equal(JSON.stringify(sent), JSON.stringify(['The appointment letter is dated 2 May.\n\nCheck leave encashment too.']));
  assert.equal(intent.queued.length, 0);
}

// After a failure, what waited returns to the message box above anything typed since.
{
  const { context, box, sent } = harness();
  const intent = { queued: ['First addition.'] };
  box.value = 'Typed since.';
  context.releaseQueued({ state: 'not_committed', context: intent });
  assert.equal(sent.length, 0);
  assert.equal(box.value, 'First addition.\n\nTyped since.');
  assert.equal(intent.text, box.value);
}

// The waiting question lists what was added, each with Remove.
{
  const el = (tag) => ({
    tagName: tag.toUpperCase(), className: '', children: [], handlers: {}, _text: '', type: '',
    set textContent(v) { this._text = String(v); }, get textContent() { return this._text; },
    append(...kids) { this.children.push(...kids); }, appendChild(kid) { this.children.push(kid); return kid; },
    addEventListener(name, fn) { this.handlers[name] = fn; },
  });
  const texts = (n) => [n._text, ...(n.children || []).flatMap(texts)].filter(Boolean);
  let repaints = 0;
  const render = vm.createContext({ document: { createElement: el }, Number, Math, Array, repaint: () => { repaints += 1; } });
  vm.runInContext(between('function renderTurn(entry) {', 'function showConversationFromStart()'), render);
  const intent = { queued: ['The appointment letter is dated 2 May.'] };
  const shown = render.renderTurn({ brief: 'Question', turnId: 't1', context: intent });
  const all = texts(shown);
  assert.ok(all.includes('Added while working · sent as soon as this answer is ready'));
  assert.ok(all.includes('The appointment letter is dated 2 May.'));
  const find = (n) => (n._text === 'Remove' ? n : (n.children || []).map(find).find(Boolean));
  find(shown).handlers.click();
  assert.equal(intent.queued.length, 0);
  assert.equal(repaints, 1);
}

console.log('add while working: ok');
