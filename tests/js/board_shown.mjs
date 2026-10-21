// THE BOARD ONLY WHEN IT HAS SOMETHING ON IT (owner decision P38, 21 Oct 2026): a new matter
// shows the conversation alone; the board appears once it holds what NM worked out, or says it
// could not be read. Offline substitutes for the DOM; not browser QA.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app = fs.readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
const start = app.indexOf('function renderBoardWaiting(');
const end = app.indexOf('// THE FILES (owner decisions 4 and 5', start);
assert.ok(start >= 0 && end > start, 'the board loading moved');

class Element {
  constructor() {
    this.children = []; this.dataset = {}; this.className = ''; this._text = '';
    this.classes = new Set();
    this.classList = { toggle: (name, on) => (on ? this.classes.add(name) : this.classes.delete(name)) };
  }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(''); }
  set textContent(value) { this._text = String(value); this.children = []; }
  replaceChildren(...children) { this._text = ''; this.children = children; }
}
const elements = new Map();
const $ = (id) => { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); };
const reads = [];
const context = vm.createContext({
  $, state: {}, activeIntent: null, toggles: [],
  stateBlock: (kind, text) => Object.assign(new Element(), { className: `state ${kind}`, _text: text }),
  api: (url) => new Promise((resolve, reject) => reads.push({ url, resolve, reject })),
  renderChatBoard: (board) => (board.state === 'ready'
    ? [Object.assign(new Element(), { className: 'board-disputes', _text: 'Dispute 1' })]
    : [Object.assign(new Element(), { className: 'state empty', _text: 'Nothing here yet' })]),
  toggleMatterBoard: (open) => context.toggles.push(open),
});
vm.runInContext(app.slice(start, end), context, { filename: 'nm/app/app.js' });
const shown = () => $('pane-advise').classes.has('has-board');

// A new matter: no conversation yet, so no board.
await context.loadChatBoard(null);
assert.equal(shown(), false, 'a new matter shows the conversation alone');

// A saved conversation: nothing while the board is first read; none while it holds nothing.
context.activeIntent = { chatId: 'chat-1' };
let loading = context.loadChatBoard('chat-1');
assert.equal(shown(), false, 'a board being read for the first time is not shown');
reads.at(-1).resolve({ state: 'empty' }); await loading;
assert.equal(shown(), false, 'a board with nothing on it is not shown');

// Once NM has worked something out, the board appears, and stays while it is read again.
loading = context.loadChatBoard('chat-1');
reads.at(-1).resolve({ state: 'ready' }); await loading;
assert.equal(shown(), true, 'a board with something on it is shown');
loading = context.loadChatBoard('chat-1');
assert.equal(shown(), true, 'a board shown stays while it is read again after an answer');
reads.at(-1).resolve({ state: 'ready' }); await loading;
assert.equal(shown(), true);

// A board that cannot be read says so; a failure is never hidden as an empty board.
context.activeIntent = { chatId: 'chat-2' };
loading = context.loadChatBoard('chat-2');
assert.equal(shown(), false);
reads.at(-1).reject(new Error('unavailable')); await loading;
assert.equal(shown(), true, 'a board that cannot be read is shown, saying so');
assert.match($('matter-board-body').textContent, /could not be read/);

// Leaving for a new matter takes the board away again.
context.renderBoardWaiting();
assert.equal(shown(), false);
assert.deepEqual(context.toggles, [], 'showing or hiding the board never closes it on a phone');
console.log('PASS the board only when it has something on it');
