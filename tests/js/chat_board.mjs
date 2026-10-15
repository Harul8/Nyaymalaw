// The matter board as NM understood it, from the conversation's saved understanding
// (owner decision, 15 Oct 2026). Offline substitutes for the DOM; not browser QA.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app = fs.readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
const start = app.indexOf('const CERTAINTY = ');
const end = app.indexOf('// A REPLY ANSWERING SEVERAL DISPUTES', start);
assert.ok(start >= 0 && end > start, 'renderChatBoard moved');

const el = (tag) => ({
  tagName: tag.toUpperCase(), className: '', textContent: '', children: [],
  appendChild(kid) { this.children.push(kid); return kid; },
});
const text = (node) => [node.textContent, ...(node.children || []).map(text)].join('');
const context = vm.createContext({
  document: { createElement: el },
  stateBlock: (kind, message) => ({ stateKind: kind, textContent: message, children: [] }),
});
vm.runInContext(app.slice(start, end), context);

// Nothing researched yet: said plainly, never an error.
{
  const [only] = context.renderChatBoard({ state: 'empty' });
  assert.equal(only.stateKind, 'empty');
}

// A ready board: disputes with what research did, what is still needed, facts with
// the certainty they were given with, and the advocate's standing instructions.
{
  const nodes = context.renderChatBoard({
    state: 'ready',
    disputes: [{ name: 'Reported obstruction of access', between: ['The client', 'The neighbour'],
      questions: [{ question: 'Can the client establish an easement?', status: 'researched' },
                  { question: 'Could it be an offence?', status: 'search_failed' }],
      still_needed: ['The date meant by “yesterday”.'] }],
    related_points: [{ point: 'Any other access', why: 'It affects necessity.', dispute: 'Reported obstruction of access' }],
    facts: [{ fact: 'Ownership is disputed.', certainty: 'disputed', words: 'ownership is disputed' }],
    instructions: ['Do not send the appointment message.'],
  });
  const all = nodes.map(text).join('\n');
  assert.ok(all.includes('As NM understood this matter'));
  assert.ok(all.includes('Reported obstruction of access'));
  assert.ok(all.includes('The client · The neighbour'));
  assert.ok(all.includes('Can the client establish an easement? · researched'));
  assert.ok(all.includes('Could it be an offence? · search failed'));
  assert.ok(all.includes('Still needed'));
  assert.ok(all.includes('Any other access — It affects necessity.'));
  assert.ok(all.includes('Disputed Ownership is disputed.'));
  assert.ok(all.includes('Do not send the appointment message.'));
}

console.log('chat board: ok');
