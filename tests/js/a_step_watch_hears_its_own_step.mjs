// THE WATCH OF A STEP HEARS ITS OWN STEP (plan AN.48, D298; the owner: "ok", 18 Nov 2026). A go-ahead of a matter worked step by step
// continues the turn where it stopped, so the progress first says the step before's last word. The page took that "stopped" as the
// stream's last word, closed it, and showed only "Preparing a response…" for the whole step. The watch of a step just sent now takes
// no stop or finish before it has heard the turn at work, and lets the stream open again; a watch that follows a turn after a reload
// is unchanged. Runs the shipped watcher against offline stand-ins for the browser's EventSource and the server; words invented.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app = fs.readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
const start = app.indexOf('const PROGRESS_EVERY_MS');
const end = app.indexOf('/* ------------------------------------------------------------------ wire --- */', start);
assert.ok(start >= 0 && end > start, 'the shipped watcher must be available');

// The browser's EventSource as the page uses it: after the server ends a stream it opens it again (CONNECTING) and says so through
// onerror; a stream it cannot have it gives up (CLOSED).
class Source {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  constructor(url) { Source.made.push(this); this.url = url; this.closed = false; this.readyState = Source.OPEN; }
  close() { this.closed = true; this.readyState = Source.CLOSED; }
  tell(seen) { this.onmessage({ data: JSON.stringify(seen) }); }
  endedByServer() { this.readyState = Source.CONNECTING; this.onerror(); this.readyState = Source.OPEN; }
  failed() { this.readyState = Source.CLOSED; this.onerror(); }
}

function page(replies = [], { stream = true } = {}) {
  Source.made = [];
  const queue = [];
  const asked = [];
  const context = vm.createContext({
    encodeURIComponent, ...(stream ? { EventSource: Source } : {}),
    setTimeout: (fn) => { queue.push(fn); return queue.length; }, clearTimeout: () => {},
    repaint: () => {}, showSoFar: () => {}, saveQueued: () => {}, openTurnQuestions: () => {},
    api: async (path) => { asked.push(path); return replies.shift(); },
  });
  vm.runInContext(app.slice(start, end), context);
  const run = async (limit = 10) => { while (queue.length && limit-- > 0) await queue.shift()(); };
  return { context, run, asked, queue };
}

const BEFORE = { state: 'stopped', chat_id: 'c1', label: 'Waiting for you' };

// A step just sent: the step before's stop is not taken in, the stream is let open again, and the step is then heard at work to
// its own last word.
{
  const { context, queue, asked } = page();
  const entry = { turnId: 't1', chatId: 'c1' };
  const watcher = context.watchProgress(entry);
  const [source] = Source.made;
  source.tell(BEFORE);
  assert.equal(entry.progress, undefined, 'the step before\'s stop is not this step\'s');
  assert.equal(source.closed, false, 'the stream is not ended on it');
  source.endedByServer();
  assert.equal(source.closed, false, 'the browser opens it again');
  assert.equal(queue.length, 0, 'nothing is asked meanwhile');
  source.tell(BEFORE);  // opened again before the server has taken the go-ahead
  source.endedByServer();
  assert.equal(source.closed, false);
  source.tell({ state: 'working', label: 'Searching the held law' });
  assert.equal(entry.progress.label, 'Searching the held law');
  source.tell({ state: 'stopped', label: 'Waiting for you', chat_id: 'c1' });
  assert.equal(entry.progress.state, 'stopped', 'once at work, its own stop is taken in');
  assert.equal(source.closed, true, 'and is the stream\'s last word');
  assert.deepEqual(asked, []);
  watcher.stop();
}

// The step before's finish is passed over the same way.
{
  const { context } = page();
  const entry = { turnId: 't2', chatId: 'c1' };
  const watcher = context.watchProgress(entry);
  const [source] = Source.made;
  source.tell({ state: 'finished', chat_id: 'c1' });
  assert.equal(entry.progress, undefined);
  assert.equal(source.closed, false);
  watcher.stop();
  assert.equal(source.closed, true);
}

// A stream that cannot be had still falls back to asking: the browser giving up, or an error with no earlier word before it.
{
  const { context, run, asked } = page([BEFORE, { state: 'working', label: 'Writing the answer' }]);
  const entry = { turnId: 't3' };
  const watcher = context.watchProgress(entry);
  const [source] = Source.made;
  source.tell(BEFORE);
  source.failed();
  assert.equal(source.closed, true);
  await run(2);
  assert.deepEqual(asked, ['/api/turn-progress?turn_id=t3', '/api/turn-progress?turn_id=t3']);
  assert.equal(entry.progress.label, 'Writing the answer', 'asked: the step before\'s stop passed over, then the step at work');
  watcher.stop();
}
{
  const { context, run, asked } = page([{ state: 'working', label: 'Reading' }]);
  const entry = { turnId: 't4' };
  const watcher = context.watchProgress(entry);
  const [source] = Source.made;
  source.endedByServer();  // a network error, no earlier word heard: asked, as before
  assert.equal(source.closed, true);
  await run(1);
  assert.deepEqual(asked, ['/api/turn-progress?turn_id=t4']);
  watcher.stop();
}

// Asked every 2 seconds (no stream): the same - the step before's stop is passed over, and asking goes on.
{
  const { context, run } = page([BEFORE, BEFORE, { state: 'working', label: 'Reading your message' }], { stream: false });
  const entry = { turnId: 't5' };
  const watcher = context.watchProgress(entry);
  await run(1);
  assert.equal(entry.progress, undefined);
  await run(1);
  assert.equal(entry.progress, undefined);
  await run(1);
  assert.equal(entry.progress.label, 'Reading your message');
  watcher.stop();
}

// A turn followed after a reload (onFinished): its stop or finish ends the watch at once, as before.
{
  const { context } = page();
  const done = [];
  const entry = { turnId: 't6', chatId: 'c1' };
  context.watchProgress(entry, () => done.push('finished'), () => done.push('stopped'));
  const [source] = Source.made;
  source.tell(BEFORE);
  assert.deepEqual(done, ['stopped']);
  assert.equal(entry.progress.state, 'stopped');
  assert.equal(source.closed, true);
}

console.log('a step watch hears its own step: ok');
