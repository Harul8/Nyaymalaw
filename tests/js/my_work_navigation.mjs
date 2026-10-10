import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const app = readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
function between(start, end) {
  const first = app.indexOf(start);
  const last = app.indexOf(end, first);
  assert.ok(first >= 0 && last > first);
  return app.slice(first, last);
}
const source = between('async function restorePendingChat(', 'async function showMatterList(')
  + between('function selectMatterRow(', 'function requirementsFor(')
  + between('function closeOpenMatter()', 'async function restorePendingChat(')
  + between('function startMatter(', '// F-A-18,')
  + between('async function send(', 'async function deliver(');

class Element {
  constructor() {
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.classes = new Set();
    this.classList = { toggle: (name, on) => on ? this.classes.add(name) : this.classes.delete(name) };
    this._text = '';
  }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  set textContent(value) { this._text = String(value); this.children = []; }
  replaceChildren(...children) { this._text = ''; this.children = children; }
  append(...children) { this.children.push(...children); }
  prepend(...children) { this.children.unshift(...children); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  removeAttribute(name) { delete this.attributes[name]; }
  addEventListener() {}
  focus() {}
  querySelectorAll() { return this.children.filter(child => child.dataset.matterId); }
  querySelector() { return this.children.find(child => child.className === 'r-title'); }
}

function fixture() {
  const elements = new Map();
  const get = id => {
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  };
  const requests = [], starts = [], boardToggles = [], sent = [];
  const state = { railGeneration: 0, matterListGeneration: 0, sessionGeneration: 1,
    matterId: null, matterVersion: null, turns: [] };
  const context = { state, activeIntent: null, activeDelivery: null, $: get,
    document: { createElement: () => new Element() },
    window: { dispatchEvent() {} }, Event: class {},
    api: url => new Promise((resolve, reject) => requests.push({ url, resolve, reject })),
    stateBlock: (_kind, text) => { const block = new Element(); block.textContent = text; return block; },
    restoredTurn: turn => turn,
    reconcileIntent() {}, repaint() {}, closeDisputeReader() {},
    selectIntent: (matterId, { chatId = null } = {}) => {
      context.activeIntent = { matterId, chatId, pending: [] };
    },
    showTab() {}, showIntake() {}, snapshotIntent() {}, consumeComposer() {},
    matchesIntake: () => false, newTurnId: () => 'new-turn',
    deliver: async entry => { sent.push(JSON.parse(entry.envelope)); },
    toggleMatters() {}, toggleMatterBoard: open => boardToggles.push(open),
    setWorkView: view => { get('pane-advise').dataset.view = view; },
    updateWorkspace() {}, closeFilesMenu() {},
    restoreConversation: async matterId => { state.turns = [{ matterId }]; return true; },
    renderDisputeBoard: body => { body.textContent = 'Current dispute board'; },
  };
  vm.runInNewContext(source, context, { filename: 'nm/app/app.js' });
  const startMatter = context.startMatter;
  context.startMatter = (chatId = null) => { starts.push(chatId); startMatter(chatId); };
  return { context, state, get, requests, starts, boardToggles, sent };
}

const matter = { matter_id: 'matter-current', matter: 'Saved matter heading' };
const chats = ['chat-first', 'chat-latest'].map(chat_id => ({ chat_id, preview: chat_id, turn_count: 1 }));
function resolveList(f, offset, matters = [matter], pending = chats) {
  assert.equal(f.requests[offset].url, '/api/work');
  f.requests[offset].resolve({ state: 'ok', row_count: matters.length, matters,
    chat_count: pending.length, chats: pending });
}
function resolveChat(request, chatId, version = 3) {
  assert.equal(request.url, `/api/chats/${chatId}`);
  request.resolve({ state: 'ok', chat_id: chatId, matter_version: version,
    turns: [{ brief: chatId }] });
}
async function loaded() {
  const f = fixture();
  const pending = f.context.loadMatterList();
  resolveList(f, 0);
  await pending;
  return f;
}

{
  const f = await loaded();
  const [first, latest] = f.get('rail-body').children;
  const earlier = first.onclick();
  const current = latest.onclick();
  resolveChat(f.requests[2], 'chat-latest', 7);
  await current;
  resolveChat(f.requests[1], 'chat-first', 2);
  await earlier;
  assert.deepEqual(f.starts, ['chat-latest']);
  assert.equal(f.context.activeIntent.chatId, 'chat-latest');
  assert.equal(f.state.turns[0].brief, 'chat-latest');
  assert.equal(f.state.matterVersion, 7);
  await f.context.send('A follow-up on the reopened conversation.');
  assert.equal(f.sent[0].chat_id, 'chat-latest');
  assert.equal(f.sent[0].expected_version, 7);
  f.context.startMatter();
  assert.equal(f.state.matterVersion, null);
  assert.equal(f.context.activeIntent.chatId, null);
  await f.context.send('A new unrelated conversation.');
  assert.equal(f.sent[1].chat_id, null);
  assert.equal(f.sent[1].expected_version, null);
}

{
  const f = await loaded();
  const [chat, , row] = f.get('rail-body').children;
  const earlier = chat.onclick();
  const current = row.onclick();
  resolveChat(f.requests[1], 'chat-first');
  await earlier;
  assert.equal(f.state.matterId, matter.matter_id);
  assert.deepEqual(f.starts, []);
  assert.equal(f.requests[2].url, `/api/matters/${matter.matter_id}`);
  f.requests[2].resolve({ version: 1, title: matter.matter });
  await current;
  assert.equal(f.context.activeIntent.matterId, matter.matter_id);
  assert.equal(f.state.turns[0].matterId, matter.matter_id);
  assert.equal(f.state.matterVersion, 1);
  assert.equal(row.attributes['aria-pressed'], 'true');
  assert.equal(f.get('matter-heading').textContent, matter.matter);
  const toggles = f.boardToggles.length;
  const refresh = f.context.showThreadBoard(matter.matter_id, { restore: false, closeNavigator: false });
  f.requests[3].resolve({ version: 2, title: matter.matter });
  await refresh;
  assert.equal(f.boardToggles.length, toggles);
}

{
  const f = fixture();
  const pending = f.context.restorePendingChat('chat-first');
  f.state.sessionGeneration += 1;
  resolveChat(f.requests[0], 'chat-first');
  await pending;
  assert.deepEqual(f.starts, []);
  assert.equal(f.context.activeIntent, null);
  assert.equal(f.state.turns.length, 0);
  assert.equal(f.state.matterVersion, null);
}

for (const version of [null, -1, 1.5, '3']) {
  const f = fixture();
  f.context.startMatter('current-chat');
  f.state.matterVersion = 4;
  const pending = f.context.restorePendingChat('chat-first');
  resolveChat(f.requests[0], 'chat-first', version);
  await assert.rejects(pending, /conversation version could not be established/);
  assert.equal(f.context.activeIntent.chatId, 'current-chat');
  assert.equal(f.state.matterVersion, 4);
}

{
  const f = fixture();
  const pending = f.context.restorePendingChat('chat-first');
  f.requests[0].resolve({state:'ok', chat_id:'chat-first', turns:[]});
  await assert.rejects(pending, /conversation version could not be established/);
  assert.equal(f.context.activeIntent, null);
  assert.equal(f.state.matterVersion, null);
}

for (const failure of [false, true]) {
  const f = fixture();
  const earlier = f.context.loadMatterList();
  const current = f.context.loadMatterList();
  f.state.matterId = matter.matter_id;
  resolveList(f, 1, [matter], []);
  await current;
  if (failure) f.requests[0].reject(new Error('Earlier read failed'));
  else resolveList(f, 0, [{ matter_id: 'matter-old', matter: 'Obsolete heading' }], []);
  await earlier;
  assert.equal(f.get('rail-body').textContent, matter.matter);
  assert.equal(f.get('rail-body').children[0].attributes['aria-pressed'], 'true');
  assert.equal(f.get('rail-meta').textContent, '1 matter');
}

for (const failure of [false, true]) {
  const f = fixture();
  const pending = f.context.loadMatterList();
  f.state.sessionGeneration += 1;
  f.get('rail-body').replaceChildren();
  f.get('rail-meta').textContent = '';
  if (failure) f.requests[0].reject(new Error('Ended session read failed'));
  else resolveList(f, 0);
  await pending;
  assert.equal(f.get('rail-body').textContent, '');
  assert.equal(f.get('rail-meta').textContent, '');
}

for (const change of ['selection', 'session', 'list']) {
  const f = await loaded();
  assert.equal(f.requests.length, 1);
  const pending = f.get('rail-body').children[0].onclick();
  if (change === 'selection') f.state.railGeneration += 1;
  if (change === 'session') f.state.sessionGeneration += 1;
  if (change === 'list') f.state.matterListGeneration += 1;
  const before = f.get('rail-body').textContent;
  f.requests[1].reject(new Error('Earlier chat failed'));
  await pending;
  assert.equal(f.get('rail-body').textContent, before);
}

{
  const f = await loaded();
  const pending = f.get('rail-body').children[0].onclick();
  f.requests[1].reject(new Error('Current chat failed'));
  await pending;
  assert.match(f.get('rail-body').textContent, /The chat could not be read/);
  assert.match(f.get('rail-body').textContent, /Saved matter heading/);
}

console.log('PASS My work navigation ownership');
