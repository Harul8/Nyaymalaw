// Send as a round up-arrow, a turning ring with a stop while NM works or a message waits for its files, and the arrow back when
// words are typed or a file attached meanwhile (plan AN.42, D74-D76; owner, 4 Nov 2026: "replace SEND button with an icon, like an
// up arrow , once it is clicked, instead of greying out, make it a radial button"). Runs the actual paintSend and the ring's press
// from nm/app/app.js against offline substitutes for the DOM and delivery, and reads the page's markup and style; not browser QA.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const app = readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
const html = readFileSync(new URL('../../nm/app/index.html', import.meta.url), 'utf8');
const css = readFileSync(new URL('../../nm/app/app.css', import.meta.url), 'utf8');
function between(from, to) {
  const a = app.indexOf(from);
  const b = app.indexOf(to, a + from.length);
  assert.ok(a >= 0 && b > a, `slice ${from} .. ${to}`);
  return app.slice(a, b);
}

class Element {
  constructor(tag) {
    this.tag = tag; this.children = []; this.attributes = {}; this.listeners = {}; this._text = ''; this.hidden = false;
    this.value = ''; this.disabled = false; this.dataset = {}; this.title = '';
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(''); }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(node) { this.children.push(node); return node; }
  replaceChildren(...nodes) { this._text = ''; this.children = nodes; }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(event, handler) { this.listeners[event] = handler; }
}

function harness() {
  const elements = {};
  const get = (id) => (elements[id] ||= new Element('div'));
  let queuedDrawn = 0;
  const asked = [];
  const context = vm.createContext({
    $: get, document: { createElement: (tag) => new Element(tag) }, encodeURIComponent,
    setPlusMenu() {}, loadUsage() {}, api: async (path, options) => { asked.push([path, options && options.body]); return {}; },
    state: { matterId: null, matterReady: true }, activeDelivery: null, heldSend: null, activeIntent: null, usage: null,
    usageUsedUp: () => false, renderQueued() { queuedDrawn += 1; }, ownsIntent: () => true, send() {},
  });
  vm.runInContext(between('// DOCUMENTS WITH A MESSAGE', '// F-C-02. THE MIC'), context);
  const looks = () => ({ state: get('send').dataset.state, label: get('send').attributes['aria-label'], disabled: get('send').disabled });
  return { context, get, looks, queuedDrawn: () => queuedDrawn, asked };
}
const pressed = () => {
  const event = { prevented: false, preventDefault() { this.prevented = true; } };
  return event;
};

// Nothing under way: the round arrow, Send.
{
  const { context, looks, queuedDrawn } = harness();
  context.paintSend();
  assert.deepEqual(looks(), { state: 'send', label: 'Send', disabled: false });
  assert.equal(queuedDrawn(), 1, 'what waits above the box is drawn with it');
}

// An answer being worked on: the turning ring with its stop. Pressed, it stops NM after the step in progress (D78): the page goes on
// waiting for the answer, which comes back stopped, with what was finished kept.
{
  const { context, get, looks, asked } = harness();
  let aborted = 0;
  const entry = { cancelled: false, turnId: 'turn-synthetic' };
  context.activeDelivery = { entry, controller: { abort() { aborted += 1; } } };
  context.paintSend();
  assert.deepEqual(looks(), { state: 'working', label: 'Stop this answer', disabled: false });
  const event = pressed();
  get('send').listeners.click(event);
  await Promise.resolve();
  assert.ok(event.prevented, 'the press is not a send');
  assert.equal(aborted, 0, 'the page does not stop waiting');
  assert.deepEqual(asked, [['/api/turn/stop', '{"turn_id":"turn-synthetic"}']]);
  assert.equal(get('attachments-status').textContent, 'Stopping after the step in progress…');
  get('send').listeners.click(pressed());
  assert.equal(asked.length, 1, 'pressed again, it is asked once');
  // Words typed meanwhile bring the arrow back, to queue them; cleared, the ring returns (D76).
  get('message').value = 'Also the second deed.';
  context.paintSend();
  assert.deepEqual(looks(), { state: 'send', label: 'Send: it waits until this answer is ready', disabled: false });
  const queue = pressed();
  get('send').listeners.click(queue);
  assert.equal(queue.prevented, false, 'pressed, the arrow sends: the message goes to the queue');
  assert.equal(asked.length, 1);
  get('message').value = '   ';
  context.paintSend();
  assert.equal(looks().state, 'working', 'no stop while the box holds words; cleared, it is back');
  // A file attached meanwhile brings the arrow back too.
  vm.runInContext('attachments.push({ name: "deed.pdf", status: "uploading", summary: null, note: "" })', context);
  context.paintSend();
  assert.equal(looks().state, 'send');
}

// A message waiting for its files: the same ring; pressed, the message is let go and the words and files stay (D75).
{
  const { context, get, looks } = harness();
  vm.runInContext('attachments.push({ name: "deed.pdf", status: "reading_scans", summary: null, note: "" })', context);
  context.heldSend = { intent: null, message: null, options: {}, seen: new Set() };
  get('message').value = 'Please review the deed.';
  context.paintSend();
  assert.deepEqual(looks(), { state: 'waiting', label: 'Do not send: keep the words and files', disabled: false });
  const event = pressed();
  get('send').listeners.click(event);
  assert.ok(event.prevented);
  assert.equal(context.heldSend, null);
  assert.equal(get('attachments-status').textContent, 'Not sent. Your words and files are as they were.');
  assert.equal(get('message').value, 'Please review the deed.');
  assert.equal(looks().state, 'send');
}

// The file still loading, and nothing left of the allowance: the arrow, greyed.
{
  const { context, looks } = harness();
  context.state.matterId = 'synthetic';
  context.state.matterReady = false;
  context.paintSend();
  assert.deepEqual(looks(), { state: 'send', label: 'Loading file…', disabled: true });
  context.state.matterReady = true;
  context.usageUsedUp = () => true;
  context.paintSend();
  assert.deepEqual(looks(), { state: 'send', label: 'Send', disabled: true });
}

// The page's own markup and style: a round button holding the arrow and the ring, no words; the queue just above the box.
{
  const composer = html.slice(html.indexOf('<form id="composer"'), html.indexOf('</form>', html.indexOf('<form id="composer"')));
  assert.match(composer, /<button type="submit" class="send-button" id="send" data-state="send" aria-label="Send" title="Send">/);
  assert.ok(composer.includes('class="send-arrow"') && composer.includes('class="send-ring"') && composer.includes('class="ring-stop"'));
  assert.ok(!/id="send"[^>]*>\s*Send\s*</.test(composer), 'no word on the button');
  assert.ok(composer.indexOf('id="queued"') < composer.indexOf('<textarea id="message"'), 'the queue is just above the box');
  assert.ok(css.includes('.send-button .send-ring { display: none; }'));
  assert.ok(css.includes('.send-button[data-state="working"] .send-ring, .send-button[data-state="waiting"] .send-ring { display: block; }'));
  assert.ok(css.includes('@keyframes send-ring-turn'));
  assert.ok(!app.includes("textContent = 'Working…'") && !app.includes("'Sends when read…'"), 'no words take the arrow\'s place');
}

console.log('send_ring_and_queue.mjs: ok');
