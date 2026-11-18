// FILES FROM THE 'TELL NM ABOUT THESE' WINDOW (plan AN.48, D301; the owner, 18 Nov 2026: "this should also have an option to upload
// files, same formats NM supports"). The answers window - 'Tell NM about these' on a dispute and 'Answer what NM asked' - attaches
// files with a chooser of the message box's own kinds of file, through the one path that reads them; lists in the window the files
// the next message carries, as they are read, with their buttons; says there what the page says of them; and sends what is written
// with them. Closed, it stops listening and the files stay under the message box. The page's own functions are run on offline
// substitutes for the DOM, as the other page tests do; the window in a browser is the owner's check.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const here = dirname(fileURLToPath(import.meta.url));
const app = readFileSync(join(here, '..', '..', 'nm', 'app', 'app.js'), 'utf8');
const between = (start, end) => {
  const a = app.indexOf(start);
  const b = app.indexOf(end, a + start.length);
  if (a < 0 || b < 0 || b <= a) throw new Error(`boundary moved: ${start}`);
  return app.slice(a, b);
};

function el(tag) {
  return {
    tagName: tag.toUpperCase(), className: '', children: [], parent: null, _text: '', open: false, style: {}, hidden: false,
    attributes: {}, handlers: {}, type: '', value: '', id: '', clicked: 0,
    set textContent(v) { this._text = String(v); this.children = []; },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
    append(...kids) { for (const k of kids) this.appendChild(k); },
    appendChild(k) { k.parent = this; this.children.push(k); return k; },
    replaceChildren(...kids) { this.children = []; this._text = ''; this.append(...kids); },
    remove() { if (this.parent) this.parent.children = this.parent.children.filter((c) => c !== this); this.parent = null; },
    addEventListener(name, handler) { this.handlers[name] = handler; },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    getAttribute(name) { return name in this.attributes ? this.attributes[name] : null; },
    focus() {}, click() { this.clicked += 1; if (this.handlers.click) this.handlers.click(); },
    showModal() { this.open = true; }, close() { this.open = false; if (this.handlers.close) this.handlers.close(); },
  };
}
const all = (node) => [node, ...node.children.flatMap(all)];
const body = el('body');
const byId = new Map();
const page = (id) => { if (!byId.has(id)) byId.set(id, Object.assign(el('div'), { id })); return byId.get(id); };
// The message box's own chooser, as index.html declares it.
const boxChooser = Object.assign(page('attach-files'), { accept: '.pdf,.docx,.txt,.png,.jpg,.jpeg,.mp3,audio/*' });
boxChooser.setAttribute('aria-label', 'Choose documents, photos or recordings to attach');
const observers = [];
const chosen = [];
const sent = [];
const context = {
  document: {
    createElement: el, createTextNode: (t) => Object.assign(el('#text'), { _text: String(t) }), body,
    querySelectorAll: (selector) => {
      assert.equal(selector, '.need-attachments');
      return all(body).filter((node) => String(node.className).split(/\s+/).includes('need-attachments'));
    },
  },
  $: page,
  MutationObserver: class {
    constructor(callback) { this.callback = callback; this.watching = null; observers.push(this); }
    observe(target) { this.watching = target; }
    disconnect() { this.watching = null; }
  },
  attachments: [{ name: 'notice.pdf', status: 'ready', summary: { waiting_for_ai: 0 }, note: '' }],
  attachFile: (file) => { chosen.push(file.name); },
  chipStatus: (item) => item.status, paintSend() {}, releaseHeld() {}, readWaiting() {}, stopVoiceNote() {},
  usageUsedUp: () => false, attachmentsBlockSend: () => null, heldSend: null, activeDelivery: null, usage: null,
  state: { matterId: null }, repaint() {}, send: (message) => { sent.push(message); },
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(between('function openNeedAnswers(', '\n// WHAT NM ASKS WHILE IT WORKS') + '\n'
  + between('// The files of the next message are listed under the message box', '\nasync function attachFile('),
context, { filename: 'nm/app/app.js' });

const rows = [{ group: null, about: 'The returned cheque', text: 'The returned cheque — from the payee' },
  { group: null, about: 'The bank memo', text: 'The bank memo — from the bank' }];
const entry = {};
context.openNeedAnswers(entry, rows, {
  called: 'Tell NM about these', empty: 'Write about at least one of them.',
  compose: (answers) => answers.filter(Boolean).join(' | '),
});
const dialog = body.children.find((node) => node.tagName === 'DIALOG');
assert.ok(dialog && dialog.open, 'the window opens');
const inside = all(dialog);
const button = inside.find((node) => node.tagName === 'BUTTON' && node.textContent === 'Attach files');
const chooser = inside.find((node) => node.tagName === 'INPUT' && node.type === 'file');
const list = inside.find((node) => String(node.className).includes('need-attachments'));
const names = (host) => all(host).filter((node) => node.className === 'attachment-name').map((node) => node.textContent);

// The same kinds of file as the message box's chooser, several at once, and the chooser is the window's own (the page behind a
// modal window cannot be used).
assert.ok(button, "the window offers 'Attach files'");
assert.ok(chooser && chooser.multiple && chooser.hidden, 'a chooser of several files, not shown');
assert.equal(chooser.accept, boxChooser.accept, 'the same formats NM supports, from the one declaration');
assert.equal(chooser.getAttribute('aria-label'), boxChooser.getAttribute('aria-label'));

// The files the next message carries already are listed in the window as under the message box.
assert.deepEqual(names(list), ['notice.pdf']);
assert.deepEqual(names(page('attachments')), ['notice.pdf']);
assert.equal(list.hidden, false);

// 'Attach files' opens the window's chooser; what is chosen goes through the one path that reads files, and the chooser is emptied
// so the same file can be chosen again.
button.click();
assert.equal(chooser.clicked, 1);
assert.equal(boxChooser.clicked, 0);
chooser.files = [{ name: 'memo.jpg' }, { name: 'call.mp3' }];
chooser.value = 'C:\\fakepath\\memo.jpg';
chooser.handlers.change();
assert.deepEqual(chosen, ['memo.jpg', 'call.mp3']);
assert.equal(chooser.value, '');

// As files are read the window's list is drawn afresh with the message box's, each with its remove button, which works from here.
context.attachments.push({ name: 'memo.jpg', status: 'uploading', summary: null, note: '' });
context.renderAttachments();
assert.deepEqual(names(list), ['notice.pdf', 'memo.jpg']);
assert.deepEqual(names(page('attachments')), ['notice.pdf', 'memo.jpg']);
const remove = all(list).find((node) => node.attributes['aria-label'] === 'Remove memo.jpg from this message');
remove.click();
assert.deepEqual(context.attachments.map((item) => item.name), ['notice.pdf']);
assert.deepEqual(names(list), ['notice.pdf']);

// What the page says of the files (a limit reached) is said in the window too.
const echo = observers.find((observer) => observer.watching === page('attachments-status'));
assert.ok(echo, 'the window listens to what the page says of the files');
page('attachments-status').textContent = "You can't upload more than 10 documents at a time.";
echo.callback();
const said = all(dialog).find((node) => node.className === 'attachments-status');
assert.equal(said.textContent, "You can't upload more than 10 documents at a time.");

// What is written goes as the next message, with the files attached (send carries them); nothing written, nothing goes.
const send = all(dialog).find((node) => node.tagName === 'BUTTON' && node.textContent === 'Send answers');
send.click();
assert.deepEqual(sent, []);
const boxes = all(dialog).filter((node) => node.tagName === 'TEXTAREA');
boxes[0].value = 'The payee holds it.';
send.click();
assert.deepEqual(sent, ['The payee holds it.']);
assert.deepEqual(context.attachments.map((item) => item.name), ['notice.pdf'], 'the files are the message\'s, not dropped');

// Closed, the window is gone and listens no more; the files are listed under the message box only.
assert.equal(dialog.open, false);
assert.equal(dialog.parent, null);
assert.equal(echo.watching, null);
context.renderAttachments();
assert.deepEqual(names(page('attachments')), ['notice.pdf']);
assert.equal(context.document.querySelectorAll('.need-attachments').length, 0);

console.log('files go with what NM is told: ok');
