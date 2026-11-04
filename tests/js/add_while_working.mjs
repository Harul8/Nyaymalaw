// Adding to a question while it is worked on (owner decision, 15 Oct 2026, as in
// Cursor): what is sent meanwhile waits on the question's conversation and goes next
// once the answer is saved; after a failure it returns to the message box.
// Plan AN.42 (D77, D80; owner, 4 Nov 2026): each waits as a line just above the message box with the files attached to it, and
// Edit (back into the box, above what is typed there, with its files) and Discard; what waits goes once, together.
// Offline substitutes for the DOM and delivery; not browser QA. The words and files are invented.
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

class Element {
  constructor(tag) {
    this.tag = tag; this.children = []; this.attributes = {}; this.listeners = {}; this._text = ''; this.hidden = false;
    this.value = ''; this.title = ''; this.focused = false;
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(''); }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(node) { this.children.push(node); return node; }
  replaceChildren(...nodes) { this._text = ''; this.children = nodes; }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(event, handler) { this.listeners[event] = handler; }
  click() { if (this.listeners.click) this.listeners.click(); }
  focus() { this.focused = true; }
}

function harness({ blocked = null } = {}) {
  const elements = {};
  const get = (id) => (elements[id] ||= new Element('div'));
  const sent = [];
  let drawn = 0;
  const context = vm.createContext({
    $: get, document: { createElement: (tag) => new Element(tag) },
    activeDelivery: null, activeIntent: null, heldSend: null, attachments: [], queuedFiles: new Set(),
    READING_STATES: ['converting', 'uploading', 'reading_scans'],
    sizeComposer() {}, renderAttachments() { drawn += 1; }, paintSend() {},
    ownsIntent: (intent) => intent === context.activeIntent, send: (text) => { sent.push({ text, files: [...context.attachments] }); },
    attachmentsBlockSend: () => blocked,
  });
  vm.runInContext(between('// ADD TO A QUESTION WHILE IT IS WORKED ON', '// WHAT A TURN IN PROGRESS IS DOING'), context);
  const box = get('message');
  const attached = () => vm.runInContext('attachments', context);
  return { context, get, box, sent, drawn: () => drawn, attached };
}
const file = (name, status = 'ready') => ({ name, status, summary: { document_ref: `doc_${name}` }, note: '' });
const texts = (node) => [node._text, ...(node.children || []).flatMap(texts)].filter(Boolean);
const button = (node, text) => (node._text === text ? node : (node.children || []).map((child) => button(child, text)).find(Boolean));

// Queued on the conversation of the question being worked on, with the files attached in the box; the box is cleared.
{
  const { context, box, attached } = harness();
  const intent = { text: 'typed' };
  context.activeIntent = intent;
  context.activeDelivery = { entry: { context: intent } };
  const deed = file('deed.pdf', 'reading_scans');
  context.attachments.push(deed);
  box.value = 'The appointment letter is dated 2 May.';
  context.queueAddition(box.value);
  context.queueAddition('   ');  // nothing to add
  assert.equal(intent.queued.length, 1);
  assert.equal(intent.queued[0].text, 'The appointment letter is dated 2 May.');
  assert.equal(intent.queued[0].files[0], deed, 'the file goes with the message');
  assert.equal(attached().length, 0, 'and leaves the box');
  assert.ok(context.queuedFiles.has(deed), 'its reading goes on');
  assert.equal(box.value, '');
  assert.equal(intent.text, '');
  // Once the answer is saved, what waited goes next as one message, with its files.
  context.queueAddition('Check leave encashment too.');
  context.activeDelivery = null;
  deed.status = 'ready';
  context.releaseQueued({ state: 'committed', context: intent });
}
{
  const { context, sent } = harness();
  const intent = {};
  context.activeIntent = intent;
  const deed = file('deed.pdf');
  intent.queued = [{ text: 'The appointment letter is dated 2 May.', files: [deed] },
    { text: 'Check leave encashment too.', files: [] }];
  context.queuedFiles.add(deed);
  context.releaseQueued({ state: 'committed', context: intent });
  assert.equal(sent.length, 1);
  assert.equal(sent[0].text, 'The appointment letter is dated 2 May.\n\nCheck leave encashment too.');
  assert.deepEqual(sent[0].files.map((item) => item.name), ['deed.pdf']);
  assert.equal(intent.queued.length, 0);
  assert.ok(!context.queuedFiles.has(deed));
}

// After a failure, what waited returns to the message box above anything typed since, its files with it.
{
  const { context, box, sent, attached } = harness();
  const intent = { queued: [{ text: 'First addition.', files: [file('map.pdf')] }] };
  context.activeIntent = intent;
  box.value = 'Typed since.';
  context.releaseQueued({ state: 'not_committed', context: intent });
  assert.equal(sent.length, 0);
  assert.equal(box.value, 'First addition.\n\nTyped since.');
  assert.equal(intent.text, box.value);
  assert.deepEqual(attached().map((item) => item.name), ['map.pdf']);
}

// Files already in the box when the answer is saved: what waited is not sent with files it was not given; it returns to the box.
{
  const { context, box, sent, attached } = harness();
  const intent = { queued: [{ text: 'Waited.', files: [] }] };
  context.activeIntent = intent;
  context.attachments.push(file('other.pdf'));
  context.releaseQueued({ state: 'committed', context: intent });
  assert.equal(sent.length, 0);
  assert.equal(box.value, 'Waited.');
  assert.equal(attached().length, 1);
}

// Another conversation is open when the answer is saved: what waited stays on its own conversation, unsent.
{
  const { context, box, sent } = harness();
  const intent = { queued: [{ text: 'Waited.', files: [] }] };
  context.activeIntent = { queued: [] };
  context.releaseQueued({ state: 'committed', context: intent });
  assert.equal(sent.length, 0);
  assert.equal(intent.queued.length, 1);
  assert.equal(box.value, '');
}

// A message that cannot carry its files is not queued; the line under the files says why.
{
  const { context, get, box } = harness({ blocked: 'Stop the voice note recording before sending.' });
  const intent = {};
  context.activeIntent = intent;
  context.activeDelivery = { entry: { context: intent } };
  box.value = 'With the recording.';
  context.queueAddition(box.value);
  assert.equal(intent.queued, undefined);
  assert.equal(box.value, 'With the recording.');
  assert.equal(get('attachments-status').textContent, 'Stop the voice note recording before sending.');
}

// What waits is drawn above the box, a line each, with what its files are doing, Edit and Discard.
{
  const { context, get, box, attached } = harness();
  const deed = file('deed.pdf', 'reading_scans');
  const map = file('map.pdf');
  const intent = { queued: [{ text: 'The deed is attached.', files: [deed, map] }, { text: 'And the map.', files: [file('bad.pdf', 'failed')] },
    { text: 'No files.', files: [] }] };
  intent.queued.forEach((item) => item.files.forEach((one) => context.queuedFiles.add(one)));
  context.activeIntent = intent;
  context.renderQueued();
  const host = get('queued');
  assert.equal(host.hidden, false);
  assert.equal(host.children.length, 3);
  assert.deepEqual(texts(host.children[0]), ['The deed is attached.', 'reading 1 file…', 'Edit', 'Discard']);
  assert.deepEqual(texts(host.children[1]), ['And the map.', '1 file could not be used', 'Edit', 'Discard']);
  assert.deepEqual(texts(host.children[2]), ['No files.', 'Edit', 'Discard']);
  assert.equal(host.children[0].children[0].title, 'The deed is attached.', 'the whole message on hover');
  // Edit: back into the box above what is typed there, with its files; it no longer waits.
  box.value = 'Typed now.';
  button(host.children[0], 'Edit').click();
  assert.equal(box.value, 'The deed is attached.\n\nTyped now.');
  assert.equal(intent.text, box.value);
  assert.deepEqual(attached().map((item) => item.name), ['deed.pdf', 'map.pdf']);
  assert.ok(!context.queuedFiles.has(deed));
  assert.equal(intent.queued.length, 2);
  assert.ok(box.focused);
  // Discard: gone, and its files with it.
  context.renderQueued();
  const bad = intent.queued[0].files[0];
  button(get('queued').children[0], 'Discard').click();
  assert.deepEqual(intent.queued.map((item) => item.text), ['No files.']);
  assert.ok(!context.queuedFiles.has(bad));
  assert.equal(attached().length, 2, 'a discarded message\'s files never reach the box');
  // Nothing waits: the list is hidden.
  intent.queued = [];
  context.renderQueued();
  assert.equal(get('queued').hidden, true);
}

console.log('add while working: ok');
