import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app = fs.readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
const start = app.indexOf('async function deliver(entry) {');
const end = app.indexOf('/* ------------------------------------------------------------------ wire --- */', start);
assert.ok(start >= 0 && end > start, 'The shipped delivery function must be available');

async function refused(code, expectedState, expectedReloads) {
  const nodes = new Map();
  const node = (id) => {
    if (!nodes.has(id)) nodes.set(id, {
      parentElement: {insertBefore() {}}, scrollHeight: 0,
      addEventListener() {}, remove() {},
    });
    return nodes.get(id);
  };
  const detail = {committed: 'not_committed', retryable: true};
  if (code !== undefined) detail.code = code;
  const friendly = 'The saved conversation could not be verified. No new message was saved.';
  let reloads = 0;
  const context = vm.createContext({
    // A browser always has timers; the progress watcher calls them directly.
    setTimeout: () => 0, clearTimeout: () => {},
    AbortController, activeDelivery: null,
    state: {sessionGeneration: 1, matterId: 'synthetic-matter'},
    ownsIntent: () => true, $: node,
    document: {createElement: () => node('cancel')},
    repaint() {}, updateWorkspace() {},
    saveProtectedDraft: async () => true,
    api: async () => { throw Object.assign(new Error(friendly), {status: 409, detail}); },
    showThreadBoard: async () => { reloads += 1; },
  });
  vm.runInContext(app.slice(start, end), context);
  const entry = {context: {}, envelope: '{}', request: {matter_id: 'synthetic-matter'}};
  await context.deliver(entry);
  assert.equal(entry.state, expectedState);
  assert.equal(reloads, expectedReloads);
  assert.equal(entry.error, friendly);
  assert.equal(entry.refusal, detail);
  assert.equal(context.activeDelivery, null);
  assert.equal(node('send').disabled, false);
}

await refused('brain_refused', 'not_committed', 0);
await refused('stale_version', 'stale', 1);
await refused(undefined, 'not_committed', 0);

// Run the shipped composer and send functions through their actual envelope
// construction. The DOM and delivery are offline substitutes, not browser QA.
const sendStart = app.indexOf('function newTurnId() {');
const wireStart = app.indexOf("$('composer').addEventListener('submit',");
const wireEnd = app.indexOf("$('message').addEventListener('keydown',", wireStart);
assert.ok(sendStart >= 0 && wireStart >= 0 && wireEnd > wireStart);

async function composed(text) {
  const handlers = new Map();
  const box = {value: text};
  const outgoing = [];
  const intent = {pending: [], text, chatId: null};
  const context = vm.createContext({
    window: {crypto: null}, activeDelivery: null, activeIntent: intent,
    state: {matterId: null, matterReady: false, disputeFocus: null,
      matterVersion: null, intake: {}, turns: []},
    $: (id) => id === 'message' ? box : {
      addEventListener: (event, handler) => handlers.set(event, handler),
    },
    snapshotIntent() {}, sizeComposer() {}, repaint() {},
    matchesIntake: () => true,
    deliver: async (entry) => { outgoing.push(entry); },
    attachments: [], attachmentsBlockSend: () => null, renderAttachments() {},
  });
  vm.runInContext(app.slice(sendStart, start) + app.slice(wireStart, wireEnd), context);
  handlers.get('submit')({preventDefault() {}});
  await Promise.resolve();
  if (!text.trim()) {
    assert.equal(outgoing.length, 0);
    assert.equal(box.value, text);
    return;
  }
  assert.equal(outgoing.length, 1);
  const entry = outgoing[0];
  assert.equal(entry.brief, text);
  assert.equal(JSON.parse(entry.envelope).message, text);
  assert.equal(box.value, '');
  assert.equal(intent.text, '');

  // Retrying the same unresolved request keeps both its identity and words.
  box.value = text;
  intent.text = text;
  entry.state = 'not_committed';
  const envelope = entry.envelope;
  await context.send(text);
  assert.equal(outgoing[1], entry);
  assert.equal(entry.envelope, envelope);

  // A different draft must not be consumed merely because trimming matches.
  box.value = text + ' ';
  intent.text = box.value;
  context.consumeComposer(entry);
  assert.equal(box.value, text + ' ');
  assert.equal(intent.text, text + ' ');
}

for (const text of ['', ' \t\r\n', '\u2003\u00a0',
  '\n  Hello.\t\r\n', '\u2003My note: ‘A’ and ‘B’ differ.\u00a0']) {
  await composed(text);
}

// THE AI ACCOUNT'S USAGE IS USED UP (owner decisions O18 and P51; plan AN.11 piece 4, AN.14): the
// owner's words as the server sent them, said plainly, then whether the message was saved and the
// way to send it again - never "I couldn't complete this message". Offline substitutes for the DOM.
{
  const el = (tag) => ({
    tagName: tag.toUpperCase(), className: '', children: [], handlers: {}, _text: '', type: '',
    set textContent(v) { this._text = String(v); }, get textContent() { return this._text; },
    append(...kids) { this.children.push(...kids); }, appendChild(kid) { this.children.push(kid); return kid; },
    addEventListener(name, fn) { this.handlers[name] = fn; },
  });
  const texts = (n) => [n._text, ...(n.children || []).flatMap(texts)].filter(Boolean);
  const find = (n, test) => (test(n) ? n : (n.children || []).map((c) => find(c, test)).find(Boolean));
  const renderStart = app.indexOf('function renderTurn(entry) {');
  const renderEnd = app.indexOf('function showConversationFromStart()', renderStart);
  assert.ok(renderStart >= 0 && renderEnd > renderStart, 'The shipped turn renderer must be available');
  const render = vm.createContext({document: {createElement: el}, Number, Math, Array,
    deliver() {}, openAiSharing() {}, repaint() {}});
  vm.runInContext(app.slice(renderStart, renderEnd), render);
  const why = 'You have run out of your usage limits. Please upgrade to continue accessing NM. '
    + 'Your saved conversation is unchanged.';
  const shown = render.renderTurn({brief: 'Question', turnId: 't1', state: 'not_committed', error: why,
    refusal: {code: 'usage_limit', why, committed: 'not_committed', retryable: true}});
  const box = find(shown, (n) => typeof n.className === 'string' && n.className.split(' ').includes('failure'));
  assert.equal(box.className, 'failure limit');
  const said = texts(box);
  assert.ok(said.includes(why), said.join(' | '));
  assert.ok(!said.some((text) => text.startsWith("I couldn't")), said.join(' | '));
  assert.ok(said.some((text) => text.startsWith('Your brief was NOT saved.')), said.join(' | '));
  assert.ok(said.includes('Send this brief again'), said.join(' | '));

  // Any other refusal still says it could not complete the message.
  const other = render.renderTurn({brief: 'Question', turnId: 't2', state: 'not_committed', error: 'The AI service did not respond.',
    refusal: {code: 'response_unavailable', why: 'The AI service did not respond.', committed: 'not_committed', retryable: true}});
  const plain = find(other, (n) => n.className === 'failure');
  assert.ok(texts(plain).some((text) => text.startsWith("I couldn't complete this message:")));
}
