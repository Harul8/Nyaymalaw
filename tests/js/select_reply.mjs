// Select words in the conversation and reply to them (owner decision, 15 Oct 2026).
// Offline substitutes for the selection and the message box; not browser QA.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app = fs.readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
const start = app.indexOf('const REPLY_QUOTE_LIMIT');
const end = app.indexOf('let replySync', start);
assert.ok(start >= 0 && end > start, 'select-and-reply helpers moved');
const context = vm.createContext({});
vm.runInContext(app.slice(start, end), context);

const inside = { inThread: true };
const thread = { contains: (node) => Boolean(node && node.inThread) };
const selection = (text, node = inside) => ({
  isCollapsed: !text, rangeCount: text ? 1 : 0, toString: () => text,
  getRangeAt: () => ({ commonAncestorContainer: node, getBoundingClientRect: () => ({ left: 10, bottom: 20 }) }),
});

// Words selected in the conversation count, with their spacing tidied.
assert.equal(context.selectedThreadText(selection('section  138\n notice'), thread).text, 'section 138 notice');
// Nothing selected, a selection elsewhere, one letter or a whole page do not.
assert.equal(context.selectedThreadText(selection(''), thread), null);
assert.equal(context.selectedThreadText(selection('elsewhere', { inThread: false }), thread), null);
assert.equal(context.selectedThreadText(selection('a'), thread), null);
assert.equal(context.selectedThreadText(selection('x'.repeat(601)), thread), null);

// The quote goes into the message box above anything already typed.
const box = { value: '' };
context.quoteIntoMessage(box, 'within thirty days');
assert.equal(box.value, 'Regarding “within thirty days”:\n');
box.value = 'Is that from the memo date?';
context.quoteIntoMessage(box, 'within thirty days');
assert.equal(box.value, 'Regarding “within thirty days”:\nIs that from the memo date?');

console.log('select and reply: ok');
