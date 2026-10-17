// Documents attached to a message and the documents list (owner decisions, 15 and 16 Oct 2026):
// the chips report the server's states, scanned pages are read after upload, and a
// message cannot be sent while a document is being read, held or failed.
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
  constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; this.listeners = {}; this._text = ''; this.hidden = false; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(''); }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(node) { this.children.push(node); return node; }
  replaceChildren(...nodes) { this._text = ''; this.children = nodes; }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(event, handler) { this.listeners[event] = handler; }
  click() { if (this.listeners.click) this.listeners.click(); }
}

function harness(replies) {
  const elements = {};
  const get = (id) => (elements[id] ||= new Element('div'));
  const requests = [];
  const context = vm.createContext({
    $: get, document: { createElement: (tag) => new Element(tag) }, encodeURIComponent,
    setPlusMenu() {},
    api: async (url, options) => {
      requests.push({ url, options });
      const reply = replies.shift();
      if (reply instanceof Error) throw reply;
      return reply;
    },
  });
  vm.runInContext(between('// DOCUMENTS WITH A MESSAGE', '// F-C-02. THE MIC'), context);
  return { context, requests, get };
}

const summary = (changes = {}) => ({
  document_ref: 'doc_aaaaaaaaaaaaaaaaaaaaaaaa-' + 'b'.repeat(64), name: 'memo.pdf', format: 'pdf',
  state: 'read', check: { state: 'clear', reason: 'no threat found by ClamAV', checker: 'clamav' },
  pages_total: 2, pages_read: 2, pages_read_by_ai: 0, pages_partly_legible: 0, waiting_for_ai: 0,
  unread: [], failure: null, ...changes,
});
const file = (name = 'memo.pdf', size = 1000) => ({ name, size });
const chip = (get, index = 0) => get('attachments').children[index];

// A scanned page waits for the AI after upload, then the chip reports what was read.
{
  const scanned = summary({ state: 'partly_read', pages_read: 1, waiting_for_ai: 1,
    unread: [{ number: 2, reason: 'a scanned page with no text layer' }] });
  const { context, requests, get } = harness([scanned, summary({ pages_read_by_ai: 1, pages_partly_legible: 1 })]);
  const pending = context.attachFile(file());
  assert.match(chip(get).textContent, /Checking for malware and reading/);
  assert.equal(context.attachmentsBlockSend(), 'Wait until the attached documents have been read.');
  await pending;
  assert.equal(requests[0].url, '/api/documents');
  assert.equal(requests[0].options.headers['X-NM-Document-Name'], 'memo.pdf');
  assert.equal(requests[1].url, `/api/documents/${encodeURIComponent(scanned.document_ref)}/read`);
  assert.match(chip(get).textContent, /Read · 2 pages \(1 by AI\) · 1 page partly legible/);
  assert.equal(context.attachmentsBlockSend(), null);
}

// Without AI data sharing the scanned pages stay unread and the chip says why.
{
  const refused = Object.assign(new Error('Read the current AI data-sharing notice'), { status: 403 });
  const { context, get } = harness([summary({ state: 'not_read', pages_read: 0, waiting_for_ai: 1 }), refused]);
  await context.attachFile(file('scan.png'));
  assert.match(chip(get).textContent, /No page could be read\. Scanned pages were not read: accept AI data sharing/);
  assert.equal(context.attachmentsBlockSend(), null);
}

// The AI could not read the scan just now (17 Oct 2026): the chip says why and offers to
// read it again; reading again asks the same reader, and the button goes once all is read.
{
  const waiting = [1, 2].map((number) => ({ number, reason: 'the AI could not read this page just now; it can be read again' }));
  const { context, requests, get } = harness([
    summary({ state: 'not_read', pages_read: 0, waiting_for_ai: 2 }),
    summary({ state: 'not_read', pages_read: 0, waiting_for_ai: 2, unread: waiting }),
    summary({ pages_read_by_ai: 2 })]);
  await context.attachFile(file('fir-scan.pdf'));
  assert.equal(chip(get).textContent,
    'fir-scan.pdfNo page could be read: the AI could not read this page just now; it can be read againRead again×');
  assert.equal(context.attachmentsBlockSend(), null);
  const again = chip(get).children[2];
  assert.equal(again.attributes['aria-label'], 'Ask the AI to read the unread pages of fir-scan.pdf again');
  const pending = again.listeners.click();
  assert.match(chip(get).textContent, /Reading scanned pages with AI/);
  assert.equal(context.attachmentsBlockSend(), 'Wait until the attached documents have been read.');
  await pending;
  assert.equal(requests.length, 3);
  assert.equal(requests[2].url, requests[1].url);
  assert.equal(chip(get).textContent, 'fir-scan.pdfRead · 2 pages (2 by AI)×');
}

// A recording waiting to be transcribed offers to transcribe it again.
{
  const { context, get } = harness([summary({ recording: true, state: 'not_read', pages_read: 0, waiting_for_ai: 1 }),
    summary({ recording: true, state: 'not_read', pages_read: 0, waiting_for_ai: 1,
      unread: [{ number: 1, reason: 'the recording could not be transcribed just now; it can be tried again' }] })]);
  await context.attachFile(file('call.mp3'));
  assert.match(chip(get).textContent, /Not transcribed: the recording could not be transcribed just now/);
  assert.equal(chip(get).children[2].textContent, 'Transcribe again');
}

// A held or failed document blocks sending until it is removed; an oversized one is
// refused without any request.
{
  const held = summary({ state: 'held', pages_read: 0, pages_total: null,
    check: { state: 'held', reason: 'ClamAV reported a threat in this file', checker: 'clamav' } });
  const { context, requests, get } = harness([held, new Error('Only PDF, Word (.docx), plain text (.txt), PNG or JPEG files can be read.')]);
  await context.attachFile(file('bad.pdf'));
  await context.attachFile(file('tool.exe'));
  await context.attachFile(file('huge.pdf', 17 * 1024 * 1024));
  assert.equal(requests.length, 2);
  assert.match(chip(get, 0).textContent, /Held, not read: ClamAV reported a threat/);
  assert.match(chip(get, 1).textContent, /Not attached: Only PDF/);
  assert.match(chip(get, 2).textContent, /Not attached: a document can be at most 16 MB/);
  assert.equal(context.attachmentsBlockSend(), 'Remove the documents that could not be used before sending.');
  for (let i = 0; i < 3; i += 1) chip(get).children[2].click();
  assert.equal(get('attachments').hidden, true);
  assert.equal(context.attachmentsBlockSend(), null);
}

// The matter's files (owner decision 4, 17 Oct 2026): a plain list. Each name opens the
// file as sent, a note appears only when something needs attention, and "Read here" opens
// what NM read as one document (decision 5), each page marked where it begins.
{
  const context = vm.createContext({
    document: { createElement: (tag) => new Element(tag) },
    stateBlock: (_kind, text) => Object.assign(new Element('p'), { textContent: text }),
  });
  vm.runInContext(between("// THE MATTER'S FILES", 'const CERTAINTY = '), context);
  const [empty] = context.renderChatDocuments({ sent: [] }, () => {});
  assert.match(empty.textContent, /No files have been sent/);
  const received = '2026-10-17T04:20:00+00:00';
  const turn = { turn_id: 't1', message: 'Please look at the memo.',
    documents: [{ document_ref: 'doc_x', name: 'memo.pdf',
      file: { format: 'pdf', size: 12877, received_at: received, pages_total: 3, cleared: true },
      pages: [{ number: 1, text: 'Return memo.', read_by: 'local' },
              { number: 2, text: 'Notice [illegible]', read_by: 'ai', model: 'gpt-6-luna', legible: 'part',
                note: 'lower edge cut off' }],
      unread: [{ number: 3, reason: 'the AI could not make out this page' }] },
    { document_ref: 'doc_y', name: 'Police complaint.docx',
      file: { format: 'docx', size: 3347, received_at: received, pages_total: 1, cleared: true },
      pages: [{ number: 1, text: 'Complaint.', read_by: 'local' }], unread: [] }] };
  const opened = [];
  const [list] = context.renderChatDocuments({ sent: [turn] }, (doc, sent, opener) => opened.push([doc, sent, opener]));
  const [memo, word] = list.children;
  const [tile, body] = memo.children;
  assert.equal(tile.textContent, 'PDF');
  const [name, meta, attention, read] = body.children;
  assert.equal(name.textContent, 'memo.pdf');
  assert.equal(name.href, '/api/documents/doc_x/original');
  assert.equal(name.target, '_blank');
  assert.equal(meta.textContent, 'PDF · 13 KB · 17 Oct 2026 · read by AI');
  assert.equal(attention.textContent, '1 page could not be read · 1 page partly legible');
  assert.equal(memo.title, 'Sent with: “Please look at the memo.”');
  const wordBody = word.children[1];
  assert.equal(wordBody.children[0].attributes['aria-label'], 'Police complaint.docx, opens in Word');
  assert.equal(wordBody.children[1].textContent, 'Word · 3 KB · 17 Oct 2026');
  assert.equal(wordBody.children.length, 3, 'no note when nothing needs attention');
  read.click();
  assert.equal(opened.length, 1);
  assert.equal(opened[0][0].name, 'memo.pdf');
  assert.equal(opened[0][2], read);
  const shown = context.renderDocumentPages(opened[0][0], opened[0][1]);
  assert.equal(shown[0].textContent, 'Open the file as sent');
  assert.equal(shown[0].href, '/api/documents/doc_x/original');
  assert.equal(shown[1].textContent, 'Sent with: “Please look at the memo.”');
  assert.deepEqual(shown[2].children.map((node) => node.textContent), [
    'Page 1', 'Return memo.', 'Page 2 · read by AI, partly legible', 'lower edge cut off', 'Notice [illegible]',
    'Page 3', 'Not read: the AI could not make out this page']);
  // A file whose own record could not be read still lists what the conversation saved.
  const [bare] = context.renderChatDocuments({ sent: [{ ...turn, documents: [{ ...turn.documents[1], file: null }] }] },
    () => {}).map((node) => node.children[0]);
  assert.equal(bare.children[1].children[1].textContent, 'File');
}

console.log('attachments: ok');
