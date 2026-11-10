// Steps as jobs (plan AN.48, piece 48f1; owner decision D167), on the page: a step the server says is still working is read once it
// is done - its answer taken as the request's own, its refusal said as the request's would be - a moment without the network is
// waited out, and where the server no longer holds the step the page follows the conversation as after a restart (D73). Runs the
// shipped delivery against offline substitutes for the DOM and the server; the words are invented. Not browser QA.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app = fs.readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
const start = app.indexOf('async function deliver(entry) {');
const end = app.indexOf('/* ------------------------------------------------------------------ wire --- */', start);
assert.ok(start >= 0 && end > start, 'The shipped delivery function must be available');

const WORKING = { working: true, turn_id: 't1', chat_id: 'c1' };
const ANSWER = { turn_id: 't1', chat_id: 'c1', matter_id: null, replayed: false, elements: [] };
const refusal = (status, detail) => Object.assign(new Error(detail.why || 'refused'), { status, detail });

async function delivered(replies) {
  const asked = [];
  const reconnects = [];
  let reloads = 0;
  const nodes = new Map();
  const node = (id) => {
    if (!nodes.has(id)) nodes.set(id, { parentElement: { insertBefore() {} }, scrollHeight: 0, addEventListener() {}, remove() {} });
    return nodes.get(id);
  };
  const context = vm.createContext({
    // A browser always has timers; the progress watcher's are not run here.
    setTimeout: () => 0, clearTimeout: () => {},
    AbortController, activeDelivery: null, intentContexts: new Map(),
    state: { sessionGeneration: 1, matterId: null },
    ownsIntent: () => true, $: node,
    document: { createElement: () => node('cancel') },
    repaint() {}, updateWorkspace() {}, paintSend() {}, loadUsage() {}, checkIdle() {}, nmFinished() {},
    snapshotIntent() {}, restoreIntent() {}, matchesIntake: () => false, intentKey: (matter, chat) => `${matter}|${chat}`,
    loadChatBoard() {}, refreshTitle() {},
    saveProtectedDraft: async () => true,
    showThreadBoard: async () => { reloads += 1; },
    api: async (path) => {
      asked.push(path);
      const next = replies.shift();
      if (next instanceof Error) throw next;
      return next;
    },
  });
  vm.runInContext(app.slice(start, end), context);
  context.pauseFor = async () => {};  // the page's pause between readings, taken at once here
  context.reconnect = (entry) => { reconnects.push(entry.turnId); };
  const entry = { turnId: 't1', context: { pending: [], key: 'k' }, envelope: '{}', request: { matter_id: null } };
  await context.deliver(entry);
  return { entry, asked, reconnects, reloads, left: replies.length };
}

// The request's wait ended while the step worked: its answer is read once it is done, as the request's own.
{
  const { entry, asked, left } = await delivered([WORKING, { working: true, turn_id: 't1' }, ANSWER]);
  assert.equal(entry.state, 'committed');
  assert.equal(entry.answer.chat_id, 'c1');
  assert.equal(entry.context.chatId, 'c1');
  assert.deepEqual(asked.slice(1), ['/api/turn/outcome?turn_id=t1', '/api/turn/outcome?turn_id=t1']);
  assert.equal(left, 0);
}

// A refusal after it went on is said as the request's would have been: here, the conversation had moved on.
{
  const { entry, reloads } = await delivered([WORKING, refusal(409, { code: 'stale_version', committed: 'not_committed',
    why: 'The conversation changed meanwhile.' })]);
  assert.equal(entry.state, 'stale');
  assert.equal(entry.error, 'The conversation changed meanwhile.');
  assert.equal(entry.refusal.code, 'stale_version');
  assert.equal(reloads, 0, 'no matter is open here');
}

// A step that stopped part-way, its work kept, is the red message read from the conversation (D69), as the request's would be.
{
  const { entry } = await delivered([WORKING, refusal(409, { code: 'waiting', kept: true, committed: 'not_committed',
    why: 'NM is waiting for your go-ahead.' })]);
  assert.equal(entry.state, 'stopped');
  assert.equal(entry.error, null);
}

// A moment without the network is waited out.
{
  const { entry, left } = await delivered([WORKING, new Error('Failed to fetch'), ANSWER]);
  assert.equal(entry.state, 'committed');
  assert.equal(left, 0);
}

// The server no longer holds the step - it was restarted: the page follows the conversation as it does after a restart (D73).
{
  const { entry, reconnects } = await delivered([WORKING, refusal(404, { code: 'no_step', why: 'NM holds no step of this message now.' })]);
  assert.equal(entry.state, 'reconnecting');
  assert.deepEqual(reconnects, ['t1']);
}

// An answer within the wait is taken at once, as before: nothing more is asked.
{
  const { entry, asked } = await delivered([ANSWER]);
  assert.equal(entry.state, 'committed');
  assert.deepEqual(asked, ['/api/turn']);
}

console.log('steps run as jobs: ok');
