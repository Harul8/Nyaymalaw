// A research note from the browser (owner decisions, 15 Oct 2026): Word downloads the
// server's file under its own name; PDF prints the server's note; only a saved chat
// answer offers either.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const app = readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
const from = app.indexOf('// A RESEARCH NOTE');
const to = app.indexOf('// LB-90.', from);
assert.ok(from >= 0 && to > from);

class Node {
  constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; this.listeners = {}; this._text = ''; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(''); }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(node) { this.children.push(node); return node; }
  remove() { this.removed = true; }
  click() { this.clicked = true; if (this.listeners.click) this.listeners.click(); }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(event, handler) { this.listeners[event] = handler; }
}
const documentStub = () => ({ head: new Node('head'), body: new Node('body'), title: '',
  createElement: (tag) => new Node(tag) });

function harness(fetchReply, apiReply) {
  const page = documentStub();
  const created = [];
  const context = vm.createContext({
    document: page, encodeURIComponent, decodeURIComponent, setTimeout: () => 0,
    URL: { createObjectURL: () => 'blob:note', revokeObjectURL() {} },
    fetch: async (url) => { created.push(url); return fetchReply; },
    api: async (url) => { created.push(url); if (apiReply instanceof Error) throw apiReply; return apiReply; },
  });
  vm.runInContext(app.slice(from, to), context);
  return { context, page, created };
}

const answer = { chat_id: 'chat 1', turn_id: 't/1', blocked: false,
  elements: [{ kind: 'HEADING', text: 'Dispute' }, { kind: 'LAW', text: 'Held law.' }] };
const note = { title: 'Research note', file_name: 'Research note 2026-10-15 - Was it filed',
  prepared_for: 'A. Advocate', prepared_at: '15 October 2026, 4:57 PM IST', question: 'Was it filed?',
  documents: [{ name: 'memo.pdf', pages_read: 2, pages_unread: 1 }],
  blocks: [{ kind: 'heading', text: 'Dispute' }, { kind: 'paragraph', text: 'Held law.', refs: [1, 2] }],
  sources: [{ number: 1, heading: '[1] Act · s.138 — Statute', passages: ['First words.', 'Second words.'] },
            { number: 2, heading: '[2] memo.pdf · page 1 — Document you sent (read by AI from a scan)', passages: ['Memo'] }],
  provenance: 'Prepared by Nyaymalaw from the answer saved on 15 October 2026.' };

// Only a saved chat answer with something in it offers a note.
{
  const { context } = harness();
  assert.equal(context.noteAvailable(answer), true);
  for (const other of [{ ...answer, chat_id: null }, { ...answer, blocked: true },
    { ...answer, elements: [{ kind: 'HEADING', text: 'Only a heading' }] }, null]) {
    assert.equal(context.noteAvailable(other), false);
  }
  assert.equal(context.noteUrl(answer), '/api/chats/chat%201/turns/t%2F1/note');
  assert.equal(context.noteFileName("attachment; filename=\"Research note.docx\"; filename*=UTF-8''Research%20note%20%E0%A4%A.docx"),
    'Research note.docx');
  assert.equal(context.noteFileName("attachment; filename*=UTF-8''Note%20%E2%80%94%20memo.docx"), 'Note — memo.docx');
}

// Word: the server's file is saved under the server's name.
{
  const reply = { ok: true, status: 200, blob: async () => 'bytes',
    headers: { get: () => "attachment; filename=\"Research note.docx\"; filename*=UTF-8''Research%20note%20%E2%80%94%20A.docx" } };
  const { context, page, created } = harness(reply);
  const status = new Node('span');
  await context.downloadNoteWord(answer, status);
  assert.equal(created[0], '/api/chats/chat%201/turns/t%2F1/note.docx');
  const link = page.body.children[0];
  assert.equal(link.download, 'Research note — A.docx');
  assert.ok(link.clicked && link.removed);
  assert.equal(status.textContent, 'Research note saved as a Word file');
}

// A refused note says why, without saving anything.
{
  const reply = { ok: false, status: 404, json: async () => ({ detail: { why: 'This answer has nothing to keep.' } }) };
  const { context, page } = harness(reply);
  const status = new Node('span');
  await context.downloadNoteWord(answer, status);
  assert.equal(page.body.children.length, 0);
  assert.equal(status.textContent, 'The research note could not be prepared: This answer has nothing to keep.');
}

// PDF: the printed page holds the note as the server gave it.
{
  const { context } = harness();
  const doc = documentStub();
  context.noteDocument(doc, note);
  assert.equal(doc.title, note.file_name);
  const text = doc.body.children.map((node) => `${node.tag}:${node.textContent}`);
  assert.deepEqual(text, [
    'h1:Research note', 'p:Prepared for A. Advocate · 15 October 2026, 4:57 PM IST', 'h2:Question',
    'blockquote:Was it filed?', 'h3:Documents sent with it', 'p:• memo.pdf — 2 pages read, 1 not read',
    'h2:Answer', 'h3:Dispute', 'p:Held law. [1, 2]', 'h2:Sources', 'p:[1] Act · s.138 — Statute',
    'blockquote:First words.', 'blockquote:Second words.',
    'p:[2] memo.pdf · page 1 — Document you sent (read by AI from a scan)', 'blockquote:Memo',
    'p:Prepared by Nyaymalaw from the answer saved on 15 October 2026.']);
}

// A note the server refuses is not printed.
{
  const { context, page } = harness(null, new Error('Saved answer not available.'));
  const status = new Node('span');
  await context.printNote(answer, status);
  assert.equal(page.body.children.length, 0);
  assert.equal(status.textContent, 'The research note could not be prepared: Saved answer not available.');
}

console.log('research note: ok');
