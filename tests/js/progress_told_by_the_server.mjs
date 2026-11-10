// The server tells the page (plan AN.48, piece 48f5; owner decision D167): while a step works the page listens to the server's
// stream of its progress instead of asking every 2 seconds; the stream's last word closes it; where the stream cannot be had the
// page asks as before. Runs the shipped watcher against an offline stand-in for the browser's EventSource and the server; the words
// are invented. Not browser QA.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app = fs.readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
const start = app.indexOf('const PROGRESS_EVERY_MS');
const end = app.indexOf('/* ------------------------------------------------------------------ wire --- */', start);
assert.ok(start >= 0 && end > start, 'the shipped watcher must be available');

class Source {
  constructor(url) { Source.made.push(this); this.url = url; this.closed = false; }
  close() { this.closed = true; }
  tell(seen) { this.onmessage({ data: JSON.stringify(seen) }); }
  fail() { this.onerror(); }
}

function page(replies = []) {
  Source.made = [];
  const queue = [];
  const asked = [];
  const context = vm.createContext({
    encodeURIComponent, EventSource: Source,
    setTimeout: (fn) => { queue.push(fn); return queue.length; }, clearTimeout: () => {},
    repaint: () => {}, showSoFar: () => {}, saveQueued: () => {}, openTurnQuestions: () => {},
    api: async (path) => { asked.push(path); return replies.shift(); },
  });
  vm.runInContext(app.slice(start, end), context);
  const run = async (limit = 10) => { while (queue.length && limit-- > 0) await queue.shift()(); };
  return { context, run, asked };
}

// Followed after a reload: told as it changes, and its last word ends the watch - nothing is asked.
{
  const { context, run, asked } = page();
  const finished = [];
  const entry = { turnId: 'turn a/1', chatId: 'c1' };
  context.watchProgress(entry, () => finished.push('fetched'));
  const [source] = Source.made;
  assert.equal(source.url, '/api/turn-events?turn_id=turn%20a%2F1&chat_id=c1');
  source.tell({ state: 'working', label: 'Searching the statutes and judgments' });
  assert.equal(entry.progress.label, 'Searching the statutes and judgments');
  source.tell({ state: 'finished', chat_id: 'c1' });
  await run();
  assert.deepEqual(finished, ['fetched']);
  assert.equal(source.closed, true, 'the last word closes the stream: the browser does not open it again');
  assert.deepEqual(asked, [], 'nothing asked: the server told it');
}

// While a message is sent: where the stream fails, the page asks every 2 seconds, as before.
{
  const { context, run, asked } = page([{ state: 'working', label: 'Writing the answer' }]);
  const entry = { turnId: 't2' };
  const watcher = context.watchProgress(entry);
  const [source] = Source.made;
  source.tell({ state: 'working', label: 'Reading your message' });
  assert.equal(entry.progress.label, 'Reading your message');
  source.fail();
  assert.equal(source.closed, true);
  await run(1);
  assert.deepEqual(asked, ['/api/turn-progress?turn_id=t2']);
  assert.equal(entry.progress.label, 'Writing the answer');
  watcher.stop();
}

// Stopped by the page, the stream is closed; a word that is not the server's is passed over.
{
  const { context } = page();
  const entry = { turnId: 't3' };
  const watcher = context.watchProgress(entry);
  const [source] = Source.made;
  source.onmessage({ data: 'not a word of the server' });
  assert.equal(entry.progress, undefined);
  watcher.stop();
  assert.equal(source.closed, true);
  source.tell({ state: 'working', label: 'Too late' });
  assert.equal(entry.progress, undefined, 'nothing taken once stopped');
}

// NM asking its questions, told by the server, opens the window once - and again only when a question is added (D87).
{
  const { context } = page();
  const opened = [];
  context.openTurnQuestions = (entry) => { opened.push(entry.turnId); entry.questionsSeen = true; entry.questionsSeenCount = 1; };
  const entry = { turnId: 't4' };
  context.watchProgress(entry);
  const [source] = Source.made;
  source.tell({ state: 'working', asking: true, asked: 1, label: 'Waiting for your answer' });
  source.tell({ state: 'working', asking: true, asked: 1, label: 'Waiting for your answer' });
  assert.deepEqual(opened, ['t4'], 'opened once by itself');
  source.tell({ state: 'working', asking: true, asked: 2, label: 'Waiting for your answer' });
  assert.deepEqual(opened, ['t4', 't4'], 'and again when a question is added');
}

console.log('progress told by the server: ok');
