// A turn in progress shows the stage it has reached, the time so far and the
// stages done; the poller follows it and, after a reload, fetches the saved
// answer when it finishes (owner decision, 14 Oct 2026). Offline substitutes
// for the DOM and the server; not browser QA.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app = fs.readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
const between = (start, end) => {
  const a = app.indexOf(start);
  const b = app.indexOf(end, a + start.length);
  assert.ok(a >= 0 && b > a, `boundary moved: ${start}`);
  return app.slice(a, b);
};

function el(tag) {
  return {
    tagName: tag.toUpperCase(), className: '', children: [], _text: '',
    set textContent(v) { this._text = String(v); this.children = []; },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
    append(...kids) { this.children.push(...kids); },
    appendChild(kid) { this.children.push(kid); return kid; },
    addEventListener() {},
  };
}
const texts = (node) => [node._text, ...node.children.flatMap(texts)].filter(Boolean);

// --- the waiting turn ------------------------------------------------------------
const render = vm.createContext({ document: { createElement: el }, Number, Math });
vm.runInContext(between('function renderTurn(entry) {', 'function showConversationFromStart()'), render);

const plain = render.renderTurn({ brief: 'What remedy is there?', turnId: 't1' });
assert.ok(texts(plain).includes('Preparing a response…'));

const working = render.renderTurn({ brief: 'What remedy is there?', turnId: 't1', progress: {
  state: 'working', label: 'Searching the statutes and judgments', detail: { done: 3, total: 12 },
  elapsed_seconds: 95, steps: [
    { label: 'Reading your message', seconds: 4 },
    { label: 'Working out the disputes and the legal questions', seconds: 31 },
    { label: 'Searching the statutes and judgments', seconds: 20 }] } });
const shown = texts(working);
assert.ok(shown.includes('Searching the statutes and judgments: question 4 of 12…'));
assert.ok(shown.includes('1 min 35 s so far. Most answers take a few minutes.'));
assert.ok(shown.includes('Reading your message · 4 s'));
assert.ok(shown.includes('Working out the disputes and the legal questions · 31 s'));
assert.ok(!shown.some((line) => line.startsWith('Searching the statutes and judgments ·')),
  'the current stage is shown once, not also as done');

const rounds = texts(render.renderTurn({ brief: 'x', turnId: 't1', progress: {
  state: 'working', label: 'Checking that understanding against the conversation', detail: { round: 2 },
  elapsed_seconds: 40, steps: [] } }));
assert.ok(rounds.includes('Checking that understanding against the conversation (round 2)…'));

// --- the poller --------------------------------------------------------------------
function poller(replies) {
  const queue = [];
  const asked = [];
  const context = vm.createContext({
    encodeURIComponent,
    // Like the browser's: called as anything's method it throws (found 15 Oct 2026).
    setTimeout: function (fn) {
      if (this !== undefined) throw new TypeError('Illegal invocation');
      queue.push(fn); return queue.length;
    },
    clearTimeout: function () { if (this !== undefined) throw new TypeError('Illegal invocation'); },
    repaint: () => {},
    api: async (path) => { asked.push(path); return replies.shift(); },
  });
  vm.runInContext(between('const PROGRESS_EVERY_MS', '/* ------------------------------------------------------------------ wire --- */'), context);
  // Run the scheduled polls, at most `limit` of them (a send keeps polling until stopped).
  const run = async (limit = 10) => { while (queue.length && limit-- > 0) await queue.shift()(); };
  return { context, run, asked };
}

// While sending, it follows the turn until the send stops it.
{
  const { context, run, asked } = poller([{ state: 'working', label: 'Reading your message' },
                                          { state: 'working', label: 'Writing the answer' }]);
  const entry = { turnId: 'turn a/1' };
  const watcher = context.watchProgress(entry);
  await run(2);
  assert.equal(asked[0], '/api/turn-progress?turn_id=turn%20a%2F1');
  assert.equal(entry.progress.label, 'Writing the answer');
  watcher.stop();
  await run(5);
  assert.equal(asked.length, 2, 'a stopped watcher polls no more');
}

// After a reload it fetches the saved answer once the turn finishes...
{
  const finished = [];
  const { context, run } = poller([{ state: 'working' }, { state: 'finished' }]);
  context.watchProgress({ turnId: 't2' }, () => finished.push('fetched'));
  await run();
  assert.deepEqual(finished, ['fetched']);
}

// ...and stops quietly when the server no longer knows the turn.
{
  const finished = [];
  const { context, run, asked } = poller([{ state: 'unknown' }, { state: 'finished' }]);
  context.watchProgress({ turnId: 't3' }, () => finished.push('fetched'));
  await run();
  assert.deepEqual(finished, []);
  assert.equal(asked.length, 1);
}

console.log('turn progress: ok');
