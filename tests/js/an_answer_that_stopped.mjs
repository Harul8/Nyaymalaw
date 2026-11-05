// No work is ever lost (plan AN.41, D65-D73) and an answer stopped or steered while NM works (plan AN.42, D77-D79), on the page:
// an answer that stopped says so in red, with Continue and Discard there; the work is drawn as it finishes; NM working counts as
// activity; a conversation opened follows its turn being worked on, and NM continues by itself after a restart, once; Steer sends
// a waiting line into the answer; what waits is kept with the conversation. Runs the actual functions of nm/app/app.js against
// offline substitutes for the DOM and the server; the words are invented. Not browser QA.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const app = readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
// A top-level function of the page, from its first line to the brace that closes it at the start of a line.
function fn(name) {
  const starts = [`\nfunction ${name}(`, `\nasync function ${name}(`];
  const at = Math.min(...starts.map((start) => app.indexOf(start)).filter((index) => index >= 0));
  assert.ok(Number.isFinite(at), `the page has ${name}`);
  const end = app.indexOf('\n}\n', at);
  return app.slice(at, end + 3);
}
const constant = (name) => {
  const at = app.indexOf(`\nconst ${name} =`);
  assert.ok(at >= 0, name);
  return app.slice(at, app.indexOf(';\n', at) + 2);
};

class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.listeners = {}; this._text = ''; this.attributes = {}; this.hidden = false; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(''); }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(node) { this.children.push(node); return node; }
  replaceChildren(...nodes) { this._text = ''; this.children = nodes; }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(event, handler) { this.listeners[event] = handler; }
  click() { this.listeners.click && this.listeners.click(); }
}
// Values made inside the page's own realm are compared by their content.
const same = (actual, expected, message) => assert.equal(JSON.stringify(actual), JSON.stringify(expected), message);
const texts = (node) => [node._text, ...(node.children || []).flatMap(texts)].filter(Boolean);
const button = (node, text) => (node._text === text ? node : (node.children || []).map((child) => button(child, text)).find(Boolean));

// --- the red message (D69-D71) -------------------------------------------------------------------------------------------
{
  const done = [];
  const context = vm.createContext({ document: { createElement: (tag) => new Element(tag) }, activeDelivery: null,
    continueTurn: (entry) => done.push(['continue', entry.turnId]), discardTurn: (entry) => done.push(['discard', entry.turnId]),
    openAiSharing: () => done.push(['sharing']) });
  vm.runInContext(fn('renderStopped'), context);
  const entry = { turnId: 't1', stopped: { code: 'response_unavailable',
    why: 'The AI service could not be reached reliably part-way through this message.',
    finished: ['the disputes and legal questions', '1 of 2 sections of the answer'], unfinished: ['the section on Dispute 2'],
    needs: null } };
  const red = context.renderStopped(entry);
  assert.equal(red.className, 'failure stopped');
  assert.deepEqual(texts(red), [
    'NM stopped before finishing this answer. The AI service could not be reached reliably part-way through this message.',
    'Finished: the disputes and legal questions; 1 of 2 sections of the answer.', 'Not finished: the section on Dispute 2.',
    'Continue', 'Discard']);
  button(red, 'Continue').click();
  button(red, 'Discard').click();
  assert.deepEqual(done, [['continue', 't1'], ['discard', 't1']]);
  // What must be put right first is said, and where it is put right.
  const off = context.renderStopped({ turnId: 't2', stopped: { code: 'model_permission_required', why: 'AI data sharing is off.',
    finished: [], unfinished: ['the whole answer'], needs: 'Turn AI data sharing back on, then press Continue.' } });
  assert.ok(texts(off).includes('Turn AI data sharing back on, then press Continue.'));
  button(off, 'Review AI data sharing').click();
  assert.deepEqual(done.at(-1), ['sharing']);
  // While another answer is worked on, neither button can be pressed.
  context.activeDelivery = { entry: {} };
  assert.equal(button(context.renderStopped(entry), 'Continue').disabled, true);
}

// --- the work as it finishes (D68) -----------------------------------------------------------------------------------------
{
  const opened = [];
  const context = vm.createContext({ document: { createElement: (tag) => new Element(tag) },
    window: { NmBrainSources: { openPassage: (where, tag, opener, given) => opened.push([where.turn_id, tag, given.phrase]) } } });
  vm.runInContext(constant('PART_SAID') + constant('LAW_SHOWN') + fn('renderWork'), context);
  assert.equal(context.renderWork(null, {}), null);
  assert.equal(context.renderWork({ understood: false }, {}), null, 'nothing before the disputes are found');
  const work = { understood: true, checked_across: false, disputes: [
    { id: 'D1', name: 'Possession of the shop', questions: ['Is the tenant protected?'], researched: true,
      law: [{ kind: 'provision', act: 'Rent Control Act', section: '10', tag: 'provision:p10' },
        { kind: 'judgment', title: 'A v B', tag: 'judgment:j1' }] },
    { id: 'D2', name: 'Arrears of rent', questions: ['Are the arrears due?'], researched: false, law: [] }],
    sections: [{ part: 's1', dispute_id: 'D1', done: false }, { part: 's2', dispute_id: 'D2', done: false }] };
  const drawn = context.renderWork(work, { s1: { state: 'rewriting', corrections: 3 }, s2: { state: 'checking' } });
  assert.deepEqual(texts(drawn), [
    'Possession of the shop', ' · Is the tenant protected?', 'Law chosen: ', 's. 10, Rent Control Act', '; ', 'A v B',
    'The check asked for 3 corrections - rewriting',
    'Arrears of rent', ' · Are the arrears due?', 'Section written - being checked']);
  // With the answer it belongs to, each law opens in the reading pane, as the board's does (D68).
  const linked = context.renderWork(work, {}, { chat_id: 'c1', turn_id: 't1' });
  button(linked, 's. 10, Rent Control Act').click();
  button(linked, 'A v B').click();
  same(opened, [['t1', 'provision:p10', 'Chosen by the research for Possession of the shop'],
    ['t1', 'judgment:j1', 'Chosen by the research for Possession of the shop']]);
  // A long list stays a short line: the sections first, then the judgments, the first few and the rest behind 'and N more'.
  const many = { understood: true, checked_across: false, sections: [], disputes: [{ id: 'D3', name: 'Title', questions: [],
    researched: true, law: [{ kind: 'judgment', title: 'C v D' }, ...[1, 2, 3, 4, 5].map((n) => ({ kind: 'provision',
      act: 'Transfer of Property Act', section: String(n) }))] }] };
  const folded = context.renderWork(many, {});
  assert.deepEqual(texts(folded).slice(1), ['Law chosen: ', 's. 1, Transfer of Property Act', '; ', 's. 2, Transfer of Property Act',
    '; ', 's. 3, Transfer of Property Act', '; ', 's. 4, Transfer of Property Act', ' ', 'and 2 more']);
  button(folded, 'and 2 more').click();
  assert.ok(texts(folded).includes('C v D') && !texts(folded).includes('and 2 more'));
  work.sections[0].done = true;
  work.checked_across = true;
  assert.ok(texts(context.renderWork(work, {})).includes('Section shown below'));
  assert.ok(texts(context.renderWork(work, {})).includes('The sections are checked against each other'));
}

// --- NM working counts as activity (D65) -----------------------------------------------------------------------------------
{
  let now = 1_000_000;
  const reports = [];
  let signedOut = 0;
  const warning = new Element('div');
  const context = vm.createContext({ Date: { now: () => now }, performance: { now: () => now },
    setTimeout: () => 1, clearTimeout: () => {}, $: () => warning, activeDelivery: null, state: { advocate: 'a', turns: [] },
    sendActivityReport: () => reports.push(now), idleSignOut: () => { signedOut += 1; }, showIdleWarning: () => {},
    sessionEnded: () => { signedOut += 100; } });
  vm.runInContext(`const IDLE_WARNING_MS = 120000; const IDLE_REPORT_MS = 60000;
    const idle = { limitMs: 30 * 60000, lastActivity: ${now}, lastReport: ${now}, timer: null, trailing: null,
      serverUntil: ${now + 12 * 3600000}, serverMonotonicUntil: ${now + 12 * 3600000} };
    ${fn('idleWatching')}${fn('nmWorking')}${fn('nmFinished')}${fn('accessWindowEnded')}${fn('checkIdle')}`, context);
  context.activeDelivery = { entry: {} };
  now += 45 * 60000;  // forty-five minutes of NM working, nothing touched
  context.checkIdle();
  assert.equal(signedOut, 0, 'not idle while NM works');
  assert.equal(reports.length, 1, 'the server is told the advocate is active');
  context.activeDelivery = null;
  context.nmFinished();
  now += 20 * 60000;
  context.checkIdle();
  assert.equal(signedOut, 0, 'the thirty minutes start once NM has finished');
  now += 11 * 60000;
  context.checkIdle();
  assert.equal(signedOut, 1);
  // A conversation opened on a turn being worked on counts too.
  assert.equal(vm.runInContext('state.turns = [{ following: true }]; nmWorking()', context), true);
}

// --- a conversation opened on its turn being worked on, or stopped (D66, D69, D73) ------------------------------------------
{
  const followed = [];
  const continued = [];
  const intent = { pending: [], chatId: 'c1' };
  const box = {};
  const watchers = [];
  const context = vm.createContext({ state: { turns: [] }, activeDelivery: null, checkIdle: () => {}, nmFinished: () => {},
    watchProgress: (entry, finished, stopped) => { followed.push(entry.turnId); watchers.push({ finished, stopped }); },
    restorePendingChat: () => {}, refreshStopped: () => {}, $: () => box, COMPOSER_WAITING: 'waits', COMPOSER_PROMPT: 'prompt',
    paintSend: () => {}, updateWorkspace: () => {},
    continueTurn: (entry, options) => continued.push([entry.turnId, options]) });
  vm.runInContext(fn('takePending') + fn('followAs') + fn('unfollow') + fn('followPending'), context);
  context.followPending(intent, { turn_id: 't1', message: 'Read the deed.', documents: [], elements: [], state: 'working',
    work: { understood: false } }, 'c1');
  const entry = vm.runInContext('state.turns[0]', context);
  assert.equal(entry.brief, 'Read the deed.');
  assert.equal(entry.following, true);
  assert.deepEqual(followed, ['t1']);
  assert.equal(intent.pending[0], entry, 'kept with the conversation\'s unsent work');
  // The page waits for it as for one it sent: the ring stops it, and what is written meanwhile waits for it (D76-D78).
  assert.equal(context.activeDelivery.entry, entry);
  assert.equal(box.placeholder, 'waits');
  watchers[0].stopped();
  assert.equal(context.activeDelivery, null, 'once it is no longer worked on');
  assert.equal(box.placeholder, 'prompt');
  context.followPending(intent, { turn_id: 't1', message: 'Read the deed.', documents: [], elements: [], state: 'stopped',
    stopped: { code: 'interrupted', by_itself: true } }, 'c1');
  assert.equal(vm.runInContext('state.turns.length', context), 1, 'one entry for the turn');
  assert.equal(entry.state, 'stopped');
  same(continued, [['t1', { byItself: true }]], 'after a restart NM continues by itself');
  context.followPending(intent, { turn_id: 't1', message: 'Read the deed.', documents: [], elements: [], state: 'stopped',
    stopped: { code: 'usage_limit', by_itself: false } }, 'c1');
  assert.equal(continued.length, 1, 'never by itself where something must be put right first');
}

// --- Continue: once by itself, with a line saying so (D70, D73) -------------------------------------------------------------
{
  const delivered = [];
  const context = vm.createContext({ activeDelivery: null, ownsIntent: () => true, deliver: (entry) => delivered.push(entry.envelope) });
  vm.runInContext(fn('continueTurn'), context);
  const entry = { turnId: 't1', context: { chatId: 'c1' }, stopped: { code: 'interrupted' } };
  context.continueTurn(entry, { byItself: true });
  context.continueTurn(entry, { byItself: true });
  assert.deepEqual(delivered, ['{"chat_id":"c1","turn_id":"t1"}']);
  assert.equal(entry.endpoint, '/api/turn/continue');
  assert.equal(entry.restartNote, 'NM was restarted while it worked on this message and continued by itself.');
  context.continueTurn(entry);  // pressed by the advocate: as often as they press
  assert.equal(delivered.length, 2);
}

// --- Steer and what waits kept with the conversation (D77, D79) --------------------------------------------------------------
{
  const asked = [];
  let reply = async () => ({ state: 'taken' });
  const status = new Element('div');
  const context = vm.createContext({ READING_STATES: ['converting', 'uploading', 'reading_scans'], queuedFiles: new Set(),
    $: () => status, repaint: () => {}, paintSend: () => {}, renderQueued: () => {}, encodeURIComponent,
    api: async (path, options) => { asked.push([path, JSON.parse(options.body)]); return reply(path); } });
  vm.runInContext(fn('unqueue') + fn('saveQueued') + fn('steerQueued'), context);
  const deed = { name: 'deed.pdf', status: 'ready', summary: { document_ref: 'doc_1', name: 'deed.pdf' } };
  const item = { text: 'Weigh the second deed too.', files: [deed] };
  const intent = { chatId: 'c1', queued: [item, { text: 'And the map.', files: [] }] };
  context.activeDelivery = { entry: { turnId: 't1', context: intent, steers: [] } };
  await context.steerQueued(intent, item);
  assert.deepEqual(asked[0], ['/api/turn/steer', { turn_id: 't1', message: 'Weigh the second deed too.', document_refs: ['doc_1'] }]);
  assert.deepEqual(asked[1], ['/api/chats/c1/queued', { queued: [{ text: 'And the map.', documents: [] }] }]);
  same(intent.queued.map((line) => line.text), ['And the map.']);
  same(context.activeDelivery.entry.steers, ['Weigh the second deed too.']);
  // The answer had finished: the line stays, to go as the next message, and the page says so.
  reply = async (path) => { if (path === '/api/turn/steer') throw Object.assign(new Error('finished'), { status: 409 }); return {}; };
  const late = intent.queued[0];
  await context.steerQueued(intent, late);
  same(intent.queued, [late]);
  assert.equal(status.textContent, 'NM had already finished this answer, so this message goes as the next one.');
  // A line whose file is still being read waits for it before it can be steered.
  const reading = { text: 'With the lease.', files: [{ name: 'lease.pdf', status: 'reading_scans', summary: null }] };
  intent.queued.push(reading);
  const before = asked.length;
  await context.steerQueued(intent, reading);
  assert.equal(asked.length, before);
}

console.log('an_answer_that_stopped.mjs: ok');
