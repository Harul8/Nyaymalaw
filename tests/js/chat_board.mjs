// The matter board as NM understood it, from the conversation's saved understanding
// (owner decisions, 15 and 16 Oct 2026): each dispute on the board opening its details in
// the reading pane on the right (the readability design, 18 Oct 2026). Offline
// substitutes for the DOM; not browser QA.
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
  window: { NmBrainSources: { showContent: (title, content, trigger, back, kind) =>
    opened.push({ title, content: Array.from(content), trigger, kind }) } },
});
vm.runInContext(app.slice(start, end), context);
const slice = (from, to) => app.slice(app.indexOf(from), app.indexOf(to, app.indexOf(from)));
vm.runInContext(slice('function timeLimitStanding(rows) {', '// What is left of a time limit'), context);
vm.runInContext(slice('function fileDate(iso) {', 'function fileAttention('), context);

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
  assert.ok(!all.includes('The client · The neighbour'), 'who it is between is in its details');
  assert.ok(all.includes('The client cannot reach the property without the path.'));
  assert.ok(all.includes('2 legal questions · 1 researched · 1 search failed'));
  assert.ok(!all.includes('Can the client establish an easement?'), 'questions live in the dispute pane');
  assert.ok(all.includes('Any other access — It affects necessity.'));
  assert.ok(all.includes('Disputed Ownership is disputed.'));
  assert.ok(all.includes('From photo.jpg, page 1 (read by AI)'));
  assert.ok(all.includes('Do not send the appointment message.'));

  // The dispute's name opens its details in the reading pane (18 Oct 2026). Before
  // checklists there is no legend: the disputes come first.
  const card = nodes[0].children.find((node) => node.className === 'dispute')
    .children.find((node) => node.tagName === 'BUTTON');
  assert.equal(card.className, 'dtitle');
  card.handlers.click();
  assert.equal(opened.length, 1);
  assert.equal(opened[0].title, 'Reported obstruction of access');
  assert.equal(opened[0].kind, 'Dispute');
  assert.equal(opened[0].trigger, card);
  const detail = opened[0].content.map(text).join('\n');
  for (const part of ['Between The client · The neighbour', 'The client cannot reach the property without the path.',
    'Where it was picked up from', 'ownership is disputed', 'From your messages', 'From photo.jpg, page 1 (read by AI)',
    'Legal questions', 'Can the client establish an easement?', 'Research: researched',
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
  nodes[0].children.find((node) => node.className === 'dispute')
    .children.find((node) => node.tagName === 'BUTTON').handlers.click();
  assert.ok(!opened.at(-1).content.map(text).join('\n').includes('without the path'));
}

// A dispute's details give each of its time limits in full (18 Oct 2026): the board's card
// shows only the last days.
{
  const listed = structuredClone(board);
  listed.disputes[0].checklist = { name: 'Reported obstruction of access', answered_at: '2026-10-18T05:00:00+00:00',
    in_hand: 0, items: [], time_limits: [
      { what: 'Last day to file the suit', rows: [['Last day', '10 January 2027 (Sunday)'],
        ['As of', '18 October 2026 (Sunday)'], ['Result', 'Open'], ['Days left', '84']] },
      { what: 'Last day to answer the notice', rows: [['Not assessed', 'the notice date is not given']] }] };
  const nodes = context.renderChatBoard(listed);
  nodes[0].children.find((node) => node.className === 'dispute')
    .children.find((node) => node.tagName === 'BUTTON').handlers.click();
  const detail = opened.at(-1).content.map(text).join('\n');
  for (const part of ['By 10 January 2027 (Sunday)', 'Last day not worked out', 'Time limits',
    'Last day to file the suit',
    'Last day 10 January 2027 (Sunday) · Open · 84 days left · as of 18 October 2026 (Sunday)',
    'Last day to answer the notice', 'Not assessed: the notice date is not given']) {
    assert.ok(detail.includes(part), part);
  }
}

// What has not been assessed is said so (plan AN.27, P7): a dispute NM set no legal questions for does not read as "0 legal
// questions", and a board whose own check was not satisfied says so, with the points the check raised folded under it.
{
  const why = 'NM has not researched the law for this dispute, so what the law requires of it has not been assessed.';
  const unassessed = { ...structuredClone(board.disputes[0]), questions: [], law: { state: 'not_assessed', why } };
  const shown = context.renderChatBoard({ ...structuredClone(board), disputes: [unassessed], understanding: {
    confirmed: false, open_points: ['The understanding does not set out the chronology.'] } });
  const all = shown.map(text).join('\n');
  assert.ok(all.includes(`What the law requires: not yet assessed. ${why}`));
  assert.ok(!all.includes('0 legal questions'), 'no count that reads as though the law had been looked at');
  assert.equal(shown[0].className, 'board-lede');
  assert.ok(shown[0].textContent.includes('NM’s own check of this understanding was not satisfied'));
  assert.ok(all.includes('Points NM’s own check raised (1)') && all.includes('The understanding does not set out the chronology.'));
  const section = shown.find((node) => node.className === 'board-disputes');
  section.children[0].children.find((node) => node.tagName === 'BUTTON').handlers.click();
  const pane = opened.at(-1).content.map(text).join('\n');
  assert.ok(pane.includes('What the law requires') && pane.includes(`Not yet assessed. ${why}`));

  // Questions set but not finished: the note and the count both stand.
  const unfinished = { ...structuredClone(board.disputes[0]), law: { state: 'not_assessed',
    why: 'NM’s research of the law for this dispute did not finish, so what the law requires of it has not been assessed.' } };
  const again = context.renderChatBoard({ ...structuredClone(board), disputes: [unfinished] }).map(text).join('\n');
  assert.ok(again.includes('What the law requires: not yet assessed. NM’s research of the law for this dispute did not finish'));
  assert.ok(again.includes('2 legal questions · 1 researched · 1 search failed'));

  // A confirmed board, an assessed dispute and a board without the server's word say nothing of the kind.
  for (const quiet of [{ ...structuredClone(board), understanding: { confirmed: true, open_points: [] } },
    { ...structuredClone(board), disputes: [{ ...structuredClone(board.disputes[0]), law: { state: 'researched', why: '' } }] },
    structuredClone(board)]) {
    const said = context.renderChatBoard(quiet).map(text).join('\n');
    assert.ok(!said.includes('not yet assessed') && !said.includes('was not satisfied') && !said.includes('own check raised'));
  }
}

console.log('chat board: ok');
