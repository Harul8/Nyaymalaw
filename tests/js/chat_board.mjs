// The matter board as NM understood it, from the conversation's saved understanding
// (owner decisions, 15 and 16 Oct 2026): short dispute cards on the board, each
// opening its details in the board's own pane. Offline substitutes for the DOM; not
// browser QA.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app = fs.readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
const start = app.indexOf('const CERTAINTY = ');
const end = app.indexOf('// A TIME LIMIT\'S WORKING', start);
assert.ok(start >= 0 && end > start, 'renderChatBoard moved');

const el = (tag) => ({
  tagName: tag.toUpperCase(), className: '', textContent: '', children: [], attributes: {}, handlers: {},
  appendChild(kid) { this.children.push(kid); return kid; },
  append(...kids) { this.children.push(...kids); },
  setAttribute(name, value) { this.attributes[name] = String(value); },
  addEventListener(name, handler) { this.handlers[name] = handler; },
});
const text = (node) => [node.textContent, ...(node.children || []).map(text)].join('');
const opened = [];
const context = vm.createContext({
  document: { createElement: el },
  stateBlock: (kind, message) => ({ stateKind: kind, textContent: message, children: [] }),
  openBoardPane: (title, content, trigger) => opened.push({ title, content, trigger }),
});
vm.runInContext(app.slice(start, end), context);

// Nothing researched yet: said plainly, never an error.
{
  const [only] = context.renderChatBoard({ state: 'empty' });
  assert.equal(only.stateKind, 'empty');
}

const board = {
  state: 'ready', summary: 'Written before research; never shown.',
  disputes: [{ id: 'D1', name: 'Reported obstruction of access', between: ['The client', 'The neighbour'],
    why_it_matters: 'The client cannot reach the property without the path.',
    fact_ids: ['F1', 'F2'],
    questions: [{ question: 'Can the client establish an easement?', why: 'It decides the right of way.',
                  open: 'How long the path has been used.', status: 'researched' },
                { question: 'Could it be an offence?', why: 'The neighbour locked the gate.', open: '',
                  status: 'search_failed' }],
    rights_at_stake: ['A right of way'], relief_sought: ['An injunction'],
    still_needed: ['The date meant by “yesterday”.'] }],
  related_points: [{ point: 'Any other access', why: 'It affects necessity.', dispute_id: 'D1',
                     dispute: 'Reported obstruction of access' },
                   { point: 'A point for another dispute', why: '', dispute_id: 'D2', dispute: 'Other' }],
  facts: [{ id: 'F1', fact: 'Ownership is disputed.', certainty: 'disputed', words: 'ownership is disputed',
            from: 'advocate' },
          { id: 'F2', fact: 'The gate was locked.', certainty: 'reported', words: 'gate was locked',
            from: 'document', places: [{ document: 'photo.jpg', page: 1, read_by: 'ai' }] }],
  instructions: ['Do not send the appointment message.'],
};

// A ready board: short dispute cards, related points, facts with their certainty and the
// advocate's standing instructions; the understanding's own summary is not shown.
{
  const nodes = context.renderChatBoard(board);
  const all = nodes.map(text).join('\n');
  assert.ok(all.includes('As NM understood this matter'));
  assert.ok(!all.includes('Written before research'));
  assert.ok(all.includes('Reported obstruction of access'));
  assert.ok(all.includes('The client · The neighbour'));
  assert.ok(all.includes('The client cannot reach the property without the path.'));
  assert.ok(all.includes('2 legal questions · 1 researched · 1 search failed'));
  assert.ok(!all.includes('Can the client establish an easement?'), 'questions live in the dispute pane');
  assert.ok(all.includes('Any other access — It affects necessity.'));
  assert.ok(all.includes('Disputed Ownership is disputed.'));
  assert.ok(all.includes('From photo.jpg, page 1 (read by AI)'));
  assert.ok(all.includes('Do not send the appointment message.'));

  // Choosing the dispute opens its details in the board's own pane.
  // The dispute's name opens it (18 Oct 2026: its card also holds its checklist).
  const card = nodes[1].children.find((node) => node.className === 'board-card dispute-card')
    .children.find((node) => node.tagName === 'BUTTON');
  assert.equal(card.attributes['aria-pressed'], 'false');
  card.handlers.click();
  assert.equal(opened.length, 1);
  assert.equal(opened[0].title, 'Reported obstruction of access');
  assert.equal(opened[0].trigger, card);
  assert.equal(card.attributes['aria-pressed'], 'true');
  const detail = opened[0].content.map(text).join('\n');
  for (const part of ['Why it matters', 'The client cannot reach the property without the path.',
    'Where it was picked up from', 'ownership is disputed', 'From your messages', 'From photo.jpg, page 1 (read by AI)',
    'Between', 'Legal questions', 'Can the client establish an easement?', 'Research: researched',
    'Why it was asked: It decides the right of way.', 'Still open: How long the path has been used.',
    'Research: search failed', 'Rights at stake', 'A right of way', 'Relief sought', 'An injunction',
    'Still needed', 'Related points for your decision', 'Any other access — It affects necessity.']) {
    assert.ok(detail.includes(part), part);
  }
  assert.ok(!detail.includes('A point for another dispute'), 'only this dispute\'s related points');
}

// An earlier conversation's dispute has no "why it matters": none is shown or invented.
{
  const earlier = structuredClone(board);
  delete earlier.disputes[0].why_it_matters;
  const nodes = context.renderChatBoard(earlier);
  assert.ok(!nodes.map(text).join('\n').includes('without the path'));
  nodes[1].children.find((node) => node.className === 'board-card dispute-card')
    .children.find((node) => node.tagName === 'BUTTON').handlers.click();
  assert.ok(!opened.at(-1).content.map(text).join('\n').includes('Why it matters'));
}

console.log('chat board: ok');
