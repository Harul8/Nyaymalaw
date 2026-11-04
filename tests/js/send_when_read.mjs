// A message sent while its files are still being read waits for them and goes by itself (plan AN.40, D61-D64; owner, 4 Nov 2026: "if
// SEND button is clicked, then greyout SEND button and once file scanning / reading is done send them automatically"). Runs the actual
// send(), the attachments and the hold from nm/app/app.js against offline substitutes for the DOM, the server and delivery; not browser
// QA. The files are invented.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const app = readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
function between(from, to) {
  const a = app.indexOf(from);
  const b = app.indexOf(to, a + from.length);
  assert.ok(a >= 0 && b > a, `slice ${from} .. ${to}`);
  return app.slice(a, b);
}

class Element {
  constructor(tag) {
    this.tag = tag; this.children = []; this.attributes = {}; this.listeners = {}; this._text = ''; this.hidden = false;
    this.parentElement = null; this.value = ''; this.disabled = false;
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(''); }
  append(...nodes) { for (const node of nodes) this.appendChild(node); }
  appendChild(node) { this.children.push(node); node.parentElement = this; return node; }
  insertBefore(node, before) {
    this.children.splice(Math.max(0, this.children.indexOf(before)), 0, node); node.parentElement = this; return node;
  }
  remove() { if (this.parentElement) this.parentElement.children = this.parentElement.children.filter((n) => n !== this); this.parentElement = null; }
  replaceChildren(...nodes) { this._text = ''; this.children = []; this.append(...nodes); }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(event, handler) { this.listeners[event] = handler; }
  click() { if (this.listeners.click) this.listeners.click(); }
}

const summary = (name, changes = {}) => ({ document_ref: `doc_${name}`, name, format: 'pdf', state: 'read',
  check: { state: 'clear' }, pages_total: 1, pages_read: 1, pages_read_by_ai: 0, pages_partly_legible: 0, waiting_for_ai: 0,
  unread: [], failure: null, ...changes });
const tick = () => new Promise((done) => setImmediate(done));

function harness() {
  const elements = {};
  const get = (id) => (elements[id] ||= new Element('div'));
  const composer = new Element('form');
  composer.appendChild(get('send'));
  const replies = [];
  const delivered = [];
  const intent = { text: '', pending: [] };
  const context = vm.createContext({
    $: get, document: { createElement: (tag) => new Element(tag) }, encodeURIComponent, JSON, Set, Boolean, Math,
    setPlusMenu() {}, loadUsage() {}, sizeComposer() {}, repaint() {},
    setTimeout: (callback) => { callback(); return 0; },
    api: async () => { const reply = replies.shift(); if (reply instanceof Error) throw reply; return typeof reply === 'function' ? reply() : reply; },
    state: { matterId: null, matterReady: true, turns: [], intake: null, disputeFocus: null, matterVersion: 0, turnChoice: null },
    activeDelivery: null, activeIntent: intent, heldSend: null, holdCancel: null, usage: null,
    usageUsedUp: () => false, selectIntent() {}, snapshotIntent() {}, matchesIntake: () => true, newTurnId: () => 'turn_1',
    consumeComposer: (entry) => { if (get('message').value === entry.brief) get('message').value = ''; },
    deliver: async (entry) => { delivered.push(entry); },
  });
  context.ownsIntent = (owned) => owned === context.activeIntent;
  vm.runInContext(between('// DOCUMENTS WITH A MESSAGE', '// F-C-02. THE MIC'), context);
  vm.runInContext(between('// fromBox (plan AN.40, D62)', 'async function deliver(entry) {'), context);
  // A file whose scanned page the AI reads: uploaded, then a reading job that ends when the test says.
  const scanning = (name) => {
    let finish;
    const ended = new Promise((resolve) => { finish = resolve; });
    replies.push(summary(name, { waiting_for_ai: 1 }), () => ended);
    return (outcome) => finish(outcome instanceof Error ? Promise.reject(outcome)
      : { state: 'done', done: 1, total: 1, document: outcome || summary(name) });
  };
  const attach = (name) => context.uploadAttachment({ name, size: 1000 });
  const attached = () => vm.runInContext('attachments', context);
  return { context, get, delivered, intent, scanning, attach, replies, attached };
}
const cancelOf = (get) => get('send').parentElement.children.find((node) => node.textContent === 'Cancel');

// Send pressed while a page is read: Send greyed with Cancel, the line says so, and nothing goes yet. The words the box holds when the
// reading ends are what goes (D62), with the file, through the same send.
{
  const { context, get, delivered, scanning, attach, attached } = harness();
  const finish = scanning('deed.pdf');
  const uploading = attach('deed.pdf');
  await tick();
  assert.equal(attached()[0].status, 'reading_scans');
  get('message').value = 'Please review the deed.';
  await context.send(get('message').value, { fromBox: true });
  assert.equal(delivered.length, 0, 'nothing goes while the file is read');
  assert.equal(get('send').disabled, true);
  assert.equal(get('send').textContent, 'Sends when read…');
  assert.ok(cancelOf(get), 'Cancel beside the greyed Send');
  assert.equal(get('attachments-status').textContent, 'Your message will go as soon as the files are read.');
  // Pressed again: still one message waiting.
  await context.send(get('message').value, { fromBox: true });
  assert.equal(delivered.length, 0);
  get('message').value = 'Please review the deed and the map.';
  finish();
  await uploading;
  await tick();
  assert.equal(delivered.length, 1, 'it goes by itself once the file is read');
  assert.equal(delivered[0].brief, 'Please review the deed and the map.', 'what the box holds then');
  assert.equal(JSON.stringify(delivered[0].documents.map((d) => d.document_ref)), '["doc_deed.pdf"]');
  assert.equal(get('message').value, '', 'the box is taken, as a pressed Send takes it');
  assert.equal(attached().length, 0);
  assert.equal(get('send').disabled, false);
  assert.equal(get('send').textContent, 'Send');
  assert.equal(cancelOf(get), undefined, 'Cancel goes with the wait');
}

// A file that comes back not fully read (AI data sharing off): nothing goes, Send works again, and the line says which file and why.
{
  const { context, get, delivered, scanning, attach, attached } = harness();
  const finish = scanning('scan.pdf');
  const uploading = attach('scan.pdf');
  await tick();
  get('message').value = 'Read this.';
  await context.send(get('message').value, { fromBox: true });
  finish(Object.assign(new Error('Forbidden'), { status: 403 }));
  await uploading;
  await tick();
  assert.equal(delivered.length, 0);
  assert.equal(get('attachments-status').textContent,
    'Not sent: scan.pdf could not be fully read. Remove it or read it again, then press Send.');
  assert.equal(get('message').value, 'Read this.', 'the words stay');
  assert.equal(get('send').disabled, false);
  assert.equal(get('send').textContent, 'Send');
}

// A file already read when Send was pressed is as the advocate saw it; only what was read meanwhile can stop the message.
{
  const { context, get, delivered, scanning, attach, replies, attached } = harness();
  replies.push(summary('earlier.pdf', { state: 'read', waiting_for_ai: 0 }));
  await attach('earlier.pdf');
  const finish = scanning('later.pdf');
  const uploading = attach('later.pdf');
  await tick();
  attached()[0].note = 'one page was left for later';
  get('message').value = 'Both papers.';
  await context.send(get('message').value, { fromBox: true });
  finish();
  await uploading;
  await tick();
  assert.equal(delivered.length, 1);
  assert.equal(delivered[0].documents.length, 2);
}

// Cancel: nothing goes when the reading ends, and the words and files stay.
{
  const { context, get, delivered, scanning, attach, attached } = harness();
  const finish = scanning('deed.pdf');
  const uploading = attach('deed.pdf');
  await tick();
  get('message').value = 'Please review.';
  await context.send(get('message').value, { fromBox: true });
  cancelOf(get).click();
  assert.equal(get('attachments-status').textContent, 'Not sent. Your words and files are as they were.');
  assert.equal(get('send').disabled, false);
  finish();
  await uploading;
  await tick();
  assert.equal(delivered.length, 0);
  assert.equal(get('message').value, 'Please review.');
  assert.equal(attached().length, 1);
}

// Words sent another way (added while NM answered, or answers to NM's questions) wait too and go as they are; let go, they return to
// the box above what is typed there.
{
  const { context, get, delivered, scanning, attach, attached } = harness();
  const finish = scanning('deed.pdf');
  const uploading = attach('deed.pdf');
  await tick();
  get('message').value = 'Typed meanwhile.';
  await context.send('My answers.');
  finish();
  await uploading;
  await tick();
  assert.equal(delivered.length, 1);
  assert.equal(delivered[0].brief, 'My answers.');
  assert.equal(get('message').value, 'Typed meanwhile.', 'the box is not taken for words sent another way');
}
{
  const { context, get, delivered, scanning, attach, attached } = harness();
  scanning('deed.pdf');
  attach('deed.pdf');
  await tick();
  get('message').value = 'Typed meanwhile.';
  await context.send('My answers.');
  cancelOf(get).click();
  assert.equal(get('message').value, 'My answers.\n\nTyped meanwhile.');
  assert.equal(delivered.length, 0);
}

// Another conversation opened meanwhile: the message never goes there; its words go back to its own conversation's draft.
{
  const { context, get, delivered, intent, scanning, attach, attached } = harness();
  const finish = scanning('deed.pdf');
  const uploading = attach('deed.pdf');
  await tick();
  await context.send('My answers.');
  context.activeIntent = { text: 'another draft', pending: [] };
  get('message').value = 'another draft';
  finish();
  await uploading;
  await tick();
  assert.equal(delivered.length, 0);
  assert.equal(intent.text, 'My answers.');
  assert.equal(get('message').value, 'another draft');
  assert.equal(get('send').textContent, 'Send');
}

// A box emptied while waiting sends nothing; anything else that stops a pressed Send stops it, with today's words.
{
  const { context, get, delivered, scanning, attach, attached } = harness();
  const finish = scanning('deed.pdf');
  const uploading = attach('deed.pdf');
  await tick();
  get('message').value = 'Please review.';
  await context.send(get('message').value, { fromBox: true });
  get('message').value = '  ';
  finish();
  await uploading;
  await tick();
  assert.equal(delivered.length, 0);
  assert.equal(get('attachments-status').textContent, 'Not sent: the message box is empty.');
}
{
  const { context, get, delivered, attached } = harness();
  attached().push({ name: 'Voice note', status: 'recording', summary: null, note: '' });
  attached().push({ name: 'deed.pdf', status: 'uploading', summary: null, note: '' });
  get('message').value = 'Please review.';
  await context.send(get('message').value, { fromBox: true });
  assert.equal(delivered.length, 0);
  assert.equal(context.heldSend, null, 'a recording still running is not waited for');
  assert.equal(get('attachments-status').textContent, 'Stop the voice note recording before sending.');
}
console.log('send_when_read.mjs: ok');
