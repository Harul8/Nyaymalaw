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

// The timeline of the papers (plan AN.27, P10): the events in the order the server kept them, the dated first and the undated under
// their own heading, with the paper and page of each, and every paper with what NM could read of it. An event whose words the server
// could not locate says so; a long timeline shows its first events and folds the rest; a board without a timeline draws as before.
{
  const events = [
    { id: 'E1', date: '30-10-1985', dated: true, kind: 'transaction', what: 'A sale of Ac.1.18 guntas.', said_by: 'the deed',
      document: 'deed.pdf', pages: [1], words: 'Sale Deed No. 100', located: true },
    { id: 'E2', date: '17 August 2019', dated: true, kind: 'order', what: 'The revision was allowed.',
      said_by: 'the Joint Collector', document: 'order.pdf', pages: [1, 2], words: 'allowed the revision', located: true },
    { id: 'E3', date: '1 January 2020', dated: true, kind: 'filing', what: 'A petition was filed.', said_by: 'a party',
      document: 'order.pdf', pages: [], words: 'filed on a day the page lacks', located: false },
    { id: 'E4', date: 'undated', dated: false, kind: 'pending', what: 'Two suits are pending.', said_by: 'the order',
      document: 'order.pdf', pages: [2], words: 'Suits O.S. 891', located: true },
    { id: 'E5', date: '1 May 2020', dated: true, kind: 'other', what: 'The sum was agreed.', said_by: 'a caller',
      document: 'call.mp3', recording: true, pages: [1], words: 'we agreed the sum', located: true }];
  const documents = [
    { name: 'deed.pdf', pages_read: 2, events: 1, state: 'read', why: '' },
    { name: 'order.pdf', pages_read: 1, events: 3, state: 'partly_read', why: 'NM could not read page 3 of this paper.' },
    { name: 'scan.pdf', pages_read: 0, events: 0, state: 'not_read', why: 'NM could not read pages 1, 2 of this paper.' },
    { name: 'call.mp3', pages_read: 1, events: 1, state: 'read', why: '', recording: true }];
  const nodes = context.renderChatBoard({ ...structuredClone(board), timeline: { state: 'ready', events, documents } });
  const fold = nodes.find((node) => node.tagName === 'DETAILS' && text(node).startsWith('Timeline of your papers'));
  assert.ok(fold, 'a fold for the timeline');
  assert.equal(nodes.indexOf(fold), nodes.findIndex((node) => node.className === 'board-disputes') + 1, 'it follows the disputes');
  assert.equal(fold.children[0].textContent, 'Timeline of your papers (5 events) · 2 papers not fully read');
  const said = text(fold);
  for (const part of ['deed.pdf: 2 pages read, 1 event', 'order.pdf: 1 page read, 3 events', 'NM could not read page 3 of this paper.',
    'scan.pdf: 0 pages read, 0 events', 'NM could not read pages 1, 2 of this paper.', 'call.mp3: 1 part read, 1 event',
    '30-10-1985 A sale of Ac.1.18 guntas. · deed.pdf, page 1 · said by the deed',
    '17 August 2019 The revision was allowed. · order.pdf, pages 1, 2 · said by the Joint Collector',
    'call.mp3, part 1 · said by a caller', 'Not dated in the paper', 'Two suits are pending.Pending · order.pdf, page 2']) {
    assert.ok(said.includes(part), part);
  }
  // The order is the server's: the dated events as kept, and the undated after them under their own heading.
  const where = (part) => said.indexOf(part);
  assert.ok(where('A sale of') < where('The revision') && where('The revision') < where('A petition') && where('A petition') < where('The sum')
    && where('In date order') < where('A sale of') && where('The sum') < where('Not dated in the paper')
    && where('Not dated in the paper') < where('Two suits'), 'as the server kept them');
  // An event the server could not locate says so, and gives no page.
  assert.ok(said.includes('A petition was filed. · order.pdf · said by a party · NM could not find these words on the page; check the paper.'));
  assert.equal(said.split('NM could not find these words').length - 1, 1, 'only the one that was not located');
  // The exact words are there for a pointer.
  const spans = [];
  const walk = (node) => { spans.push(node); (node.children || []).forEach(walk); };
  walk(fold);
  assert.ok(spans.some((node) => node.title === 'Sale Deed No. 100'));

  // A long timeline shows its first events and folds the rest.
  const many = Array.from({ length: 15 }, (_, n) => ({ ...events[0], id: `E${n + 1}`, what: `Event number ${n + 1}.` }));
  const long = context.renderChatBoard({ ...structuredClone(board), timeline: { state: 'ready', events: many, documents } })
    .find((node) => node.tagName === 'DETAILS' && text(node).startsWith('Timeline of your papers'));
  const more = long.children.find((node) => node.className === 'board-more');
  assert.equal(more.children[0].textContent, 'Show the other 3 events');
  assert.ok(text(more).includes('Event number 13.') && text(more).includes('Event number 15.') && !text(more).includes('Event number 12.'));
  const shown = long.children.find((node) => node.className === 'board-list board-events');
  assert.ok(text(shown).includes('Event number 12.') && !text(shown).includes('Event number 13.'));
  const one = context.renderChatBoard({ ...structuredClone(board), timeline: { state: 'ready', events: many.slice(0, 13), documents } })
    .find((node) => node.tagName === 'DETAILS' && text(node).startsWith('Timeline of your papers'));
  assert.equal(one.children.find((node) => node.className === 'board-more').children[0].textContent, 'Show the other 1 event');

  // Papers with no event, and one paper not fully read, say so.
  const none = context.renderChatBoard({ ...structuredClone(board), timeline: { state: 'ready', events: [], documents: [documents[0]] } })
    .map(text).join('\n');
  assert.ok(none.includes('Timeline of your papers (0 events)') && none.includes('NM listed no events from these papers.'));
  assert.ok(!none.includes('not fully read') && !none.includes('In date order'));
  const partly = context.renderChatBoard({ ...structuredClone(board), timeline: { state: 'ready', events: [events[0]], documents: [documents[1]] } })
    .map(text).join('\n');
  assert.ok(partly.includes('Timeline of your papers (1 event) · 1 paper not fully read'));

  // An earlier conversation's board says none was made; a board with no papers, or no word on it, says nothing.
  const why = 'NM did not make a timeline of the papers when it answered this conversation, so there is none to show.';
  const earlier = context.renderChatBoard({ ...structuredClone(board), timeline: { state: 'not_made', why } });
  assert.ok(earlier.map(text).join('\n').includes(why) && !earlier.some((node) => text(node).startsWith('Timeline of your papers')));
  for (const quiet of [{ ...structuredClone(board), timeline: { state: 'none' } }, structuredClone(board)]) {
    const read = context.renderChatBoard(quiet).map(text).join('\n');
    assert.ok(!read.includes('Timeline of your papers') && !read.includes('timeline'));
  }
}

// An event that a copy of its page records again is listed once, with where else it is (plan AN.27, P22); nothing is said of it, and the
// lede does not mention it, where no event is repeated.
{
  const repeated = [
    { id: 'E1', date: '5-1-1980', dated: true, kind: 'transaction', what: 'A sale.', said_by: 'the deed', document: 'scan.pdf', pages: [1],
      words: 'Sale deed', located: true, also_in: [{ document: 'deed.pdf', pages: [3] }, { document: 'copy.pdf', pages: [1, 2] }] },
    { id: 'E2', date: '6-1-1980', dated: true, kind: 'order', what: 'An order.', said_by: 'the court', document: 'deed.pdf', pages: [4],
      words: 'Order', located: true }];
  const documents = [{ name: 'deed.pdf', pages_read: 4, events: 2, state: 'read', why: '' },
    { name: 'scan.pdf', pages_read: 1, events: 1, state: 'read', why: '' }];
  const foldOf = (events) => context.renderChatBoard({ ...structuredClone(board), timeline: { state: 'ready', events, documents } })
    .find((node) => node.tagName === 'DETAILS' && text(node).startsWith('Timeline of your papers'));
  const said = text(foldOf(repeated));
  assert.ok(said.includes('A sale. · scan.pdf, page 1 · said by the deed · also in deed.pdf, page 3; copy.pdf, pages 1, 2'));
  assert.ok(said.includes('An order. · deed.pdf, page 4 · said by the court') && !said.includes('said by the court · also in'));
  assert.equal(said.split('also in').length - 1, 1, 'only the event that is repeated names where else it is');
  assert.ok(said.includes('An event that more than one paper records, as a copy of a page does, is listed once, with the other papers named.'));
  assert.ok(text(foldOf(repeated)).includes('Timeline of your papers (2 events)'));
  assert.ok(!text(foldOf([repeated[1]])).includes('listed once'), 'nothing is said where no event is repeated');
  const emptied = text(foldOf([{ ...repeated[0], also_in: [] }]));
  assert.ok(!emptied.includes('listed once') && !emptied.includes('also in'), 'an empty list says nothing either');
}

// Figures two copies read differently (plan AN.27, P13): both readings and the words before them, never a choice; nothing where the
// board has none or says nothing of them.
{
  const copies = [
    { first: { document: 'deed.pdf', page: 3 }, second: { document: 'scan.pdf', page: 1 },
      figures: [{ first: '6.06', second: '6.16', after: 'an extent of' }] },
    { first: { document: 'a.pdf', page: 2 }, second: { document: 'b.pdf', page: 5 },
      figures: [{ first: '596/80', second: '596/89', after: 'deed number' }, { first: '1980', second: '1986', after: '' }] }];
  const nodes = context.renderChatBoard({ ...structuredClone(board), copies });
  const fold = nodes.find((node) => node.tagName === 'DETAILS' && text(node).startsWith('Figures two copies read differently'));
  assert.ok(fold, 'a fold for the copies');
  assert.equal(fold.children[0].textContent, 'Figures two copies read differently (2)');
  const said = text(fold);
  for (const part of ['NM has not chosen between them: check the originals.',
    'deed.pdf, page 3 and scan.pdf, page 1: “6.06” and “6.16” (after “an extent of”)',
    'a.pdf, page 2 and b.pdf, page 5: “596/80” and “596/89” (after “deed number”); “1980” and “1986”']) {
    assert.ok(said.includes(part), part);
  }
  assert.ok(!said.includes('1986 (after'), 'no words before: none given');
  // It follows the disputes and, where there is one, the timeline.
  assert.equal(nodes.indexOf(fold), nodes.findIndex((node) => node.className === 'board-disputes') + 1);
  const both = context.renderChatBoard({ ...structuredClone(board), copies, timeline: { state: 'ready', events: [], documents: [] } });
  const at = (start) => both.findIndex((node) => text(node).startsWith(start));
  assert.ok(at('Timeline of your papers') >= 0 && at('Timeline of your papers') < at('Figures two copies'));
  for (const quiet of [{ ...structuredClone(board), copies: [] }, structuredClone(board)]) {
    assert.ok(!context.renderChatBoard(quiet).map(text).join('\n').includes('Figures two copies'));
  }
}

// Transactions by property or account (plan AN.27, P13d and P20; AN.28, D7): the transactions found, giver by giver, each giver's figures
// added by the server's code and set against a stated whole - what it leaves if all of it was that giver's, or how far the figures go beyond
// it; what could not be read or is not added listed and never added; nothing where the board has none.
{
  const caveat = 'Extents are added as the papers state them, whoever states them, seller by seller.';
  const extents = [
    { parcel: 'Sy.No.487', sellers: [
      { names: ['Hari Prasad', 'Hari Prasaad'], transfers: [
        { ids: ['X1'], date: '30-10-1985', kind: 'sale', to: 'Kiran Rao', extent: 'Ac.1.18 guntas', as: '1 acre 18 guntas (Ac.1.18)',
          read_as: 'acres.guntas', also_read_as: ['Kiran Raao'], papers: [{ document: 'deed.pdf', pages: [1] }, { document: 'order.pdf', pages: [4, 5] }] },
        { ids: ['X2'], date: '2 January 1986', kind: 'sale', to: '', extent: 'Ac.1.00', as: '1 acre (Ac.1.00)',
          read_as: 'acres.guntas', papers: [{ document: 'deed.pdf', pages: [] }] }],
        not_added: [{ ids: ['X5'], date: '9-2-1974', kind: 'partition', to: 'Anil Kumar', extent: 'Ac.8.24', as: '8 acres 24 guntas (Ac.8.24)',
          read_as: 'acres.guntas', why: 'a partition allots a share; it is not a sale', papers: [{ document: 'order.pdf', pages: [6] }] }],
        added: '2 acres 18 guntas (Ac.2.18)' },
      { names: ['Anil Kumar'], transfers: [], not_added: [
        { ids: ['X7'], date: '9-2-1974', kind: 'partition', to: 'his sons', extent: 'equal shares', as: null,
          read_as: 'no extent in these words', why: 'a partition allots a share; it is not a sale', papers: [{ document: 'order.pdf', pages: [6] }] }],
        added: null },
      { names: [], transfers: [
        { ids: ['X6'], date: '3 March 1990', kind: 'sale', to: 'Mahesh Babu', extent: 'Ac.0.10', as: '10 guntas (Ac.0.10)',
          read_as: 'acres.guntas', papers: [{ document: 'order.pdf', pages: [7] }] }],
        not_added: [], added: null }],
      not_read: [{ id: 'X3', extent: 'part of the land', why: 'no extent in these words', document: 'deed.pdf', pages: [3] }],
      complete: false,
      totals: [{ text: 'Ac.8.24 guntas', measure: 'area', read_as: 'acres.guntas', as: '8 acres 24 guntas (Ac.8.24)', ids: ['X1'], by_seller: [] }],
      caveat },
    { parcel: 'Sy.No.487/A', sellers: [
      { names: ['Syed Alam'], transfers: [
        { ids: ['X4'], date: 'undated', kind: 'gift', to: 'Other', extent: 'Ac.0.29', as: '29 guntas (Ac.0.29)',
          read_as: 'acres.guntas', papers: [{ document: 'order.pdf', pages: [2] }] }],
        not_added: [], added: '29 guntas (Ac.0.29)' }],
      not_read: [], complete: true,
      totals: [
        { text: 'Ac.2.00', measure: 'area', read_as: 'acres.guntas', as: '2 acres (Ac.2.00)', ids: ['X4'],
          by_seller: [{ seller: 'Syed Alam', leaves: '1 acre 11 guntas (Ac.1.11)', exceeds: null }] },
        { text: 'Ac.0.20', measure: 'area', read_as: 'acres.guntas', as: '20 guntas (Ac.0.20)', ids: ['X4'],
          by_seller: [{ seller: 'Syed Alam', leaves: null, exceeds: '9 guntas (Ac.0.09)' }] },
        { text: 'the whole survey number', measure: null, read_as: 'no extent in these words', as: null, ids: ['X4'], by_seller: [] }],
      caveat },
    { parcel: 'Loan account 12', sellers: [
      { names: ['Bank of Somewhere'], transfers: [
        { ids: ['X8'], date: '1-1-2010', kind: 'loan', to: 'Ravi Teja', extent: 'Rs.2,00,000/-', as: 'Rs 2,00,000',
          read_as: 'rupees in figures', papers: [{ document: 'loan.pdf', pages: [1] }] }],
        not_added: [], added: 'Rs 2,00,000' },
      { names: ['Ravi Teja'], transfers: [
        { ids: ['X9'], date: '1-1-2011', kind: 'payment', to: 'Bank of Somewhere', extent: 'Rs.50,000', as: 'Rs 50,000',
          read_as: 'rupees in figures', papers: [{ document: 'loan.pdf', pages: [2] }] }],
        not_added: [], added: 'Rs 50,000' }],
      not_read: [], complete: true,
      totals: [{ text: 'Rs.2,00,000/-', measure: 'money', read_as: 'rupees in figures', as: 'Rs 2,00,000', ids: ['X8'],
                 by_seller: [{ seller: 'Bank of Somewhere', leaves: 'Rs 0', exceeds: null },
                             { seller: 'Ravi Teja', leaves: 'Rs 1,50,000', exceeds: null }] }],
      caveat }];
  const nodes = context.renderChatBoard({ ...structuredClone(board), extents });
  const fold = nodes.find((node) => node.tagName === 'DETAILS' && text(node).startsWith('Transactions by property'));
  assert.ok(fold, 'a fold for the extents');
  assert.equal(fold.children[0].textContent, 'Transactions by property or account (3)');
  const said = text(fold);
  for (const part of ['Added up by NM’s code from the transactions it found in your papers - areas with areas, sums of money with sums of '
    + 'money - as the papers state them and whoever states them. Rival or repeated accounts are added as if each were true, so a sum is a '
    + 'figure to check against the papers, not what anyone holds, owes or has paid.', 'Sy.No.487',
    'From: Hari Prasad / Hari Prasaad',
    '30-10-1985 sale: Ac.1.18 guntas (1 acre 18 guntas (Ac.1.18)) to Kiran Rao (also read as “Kiran Raao”) · deed.pdf, page 1; order.pdf, pages 4, 5',
    '2 January 1986 sale: Ac.1.00 (1 acre (Ac.1.00)) · deed.pdf',
    'Not added (a partition allots a share; it is not a sale): 9-2-1974 partition: Ac.8.24 (8 acres 24 guntas (Ac.8.24)) to Anil Kumar · order.pdf, page 6',
    'Added as stated: 2 acres 18 guntas (Ac.2.18) (a transaction could not be added, so the whole is more)',
    'From: Anil Kumar',
    'Not added (a partition allots a share; it is not a sale): 9-2-1974 partition: equal shares to his sons · order.pdf, page 6',
    'From: not named in the papers', '3 March 1990 sale: Ac.0.10 (10 guntas (Ac.0.10)) to Mahesh Babu · order.pdf, page 7',
    'Not added: “part of the land” (no extent in these words) · deed.pdf',
    'A paper states the whole as “Ac.8.24 guntas” (8 acres 24 guntas (Ac.8.24))',
    'No remainder is named, because a transaction could not be added.',
    'Sy.No.487/A', 'From: Syed Alam', 'undated gift: Ac.0.29 (29 guntas (Ac.0.29)) to Other · order.pdf, page 2',
    'Added as stated: 29 guntas (Ac.0.29)',
    'A paper states the whole as “Ac.2.00” (2 acres (Ac.2.00))',
    'If Syed Alam held all of it, what they transferred, as found, leaves 1 acre 11 guntas (Ac.1.11).',
    'What Syed Alam gave, as found, adds up to more than that whole, by 9 guntas (Ac.0.09): the papers cannot all be right.',
    'A paper states the whole as “the whole survey number”; not used (no extent in these words)',
    'Loan account 12', 'From: Bank of Somewhere', '1-1-2010 loan: Rs.2,00,000/- (Rs 2,00,000) to Ravi Teja · loan.pdf, page 1',
    'From: Ravi Teja', '1-1-2011 payment: Rs.50,000 (Rs 50,000) to Bank of Somewhere · loan.pdf, page 2',
    'Set against that sum, what Ravi Teja paid or lent, as found, leaves Rs 1,50,000.', caveat]) {
    assert.ok(said.includes(part), part);
  }
  assert.ok(!said.includes('Added as stated: 29 guntas (Ac.0.29) ('), 'a complete sum has no aside');
  assert.ok(!said.includes('Added as stated: null') && (said.match(/Added as stated:/g) || []).length === 4, 'a giver with no name is added to no one');
  assert.ok(!said.includes('null') && !said.includes('undefined'), 'an extent that could not be read is shown as the paper writes it, and no more');
  assert.ok(!said.includes('leaves undefined') && !said.includes('If Ravi Teja held all of it'), 'nothing is said where there is nothing to say, '
    + 'and a sum is not spoken of as land');
  assert.equal(nodes.indexOf(fold), nodes.findIndex((node) => node.className === 'board-disputes') + 1);
  const with_copies = context.renderChatBoard({ ...structuredClone(board), extents, copies: [{ first: { document: 'a.pdf', page: 1 },
    second: { document: 'b.pdf', page: 1 }, figures: [{ first: '6.06', second: '6.16', after: '' }] }] });
  const at = (start) => with_copies.findIndex((node) => text(node).startsWith(start));
  assert.ok(at('Figures two copies') >= 0 && at('Figures two copies') < at('Transactions by property or account'));
  for (const quiet of [{ ...structuredClone(board), extents: [] }, structuredClone(board)]) {
    assert.ok(!context.renderChatBoard(quiet).map(text).join('\n').includes('Transactions by property'));
  }
}

// Read side by side, and who is who (plan AN.28, pieces 3e and 3f): each point with the pages the server found its words on, one whose
// words were not found said so; where the client's people stand on the pages, a near spelling only a candidate; each party's part in
// each proceeding and each subject, with where their words are. Invented names.
{
  const together = { ...structuredClone(board),
    parties: [{ who: 'Leela Kulkarni', role: 'heir', client: true, parts: [{ proceeding: 'W.A. 6649 of 2016', part: 'respondent',
      from: 'document', places: [{ document: 'order.pdf', page: 1, read_by: 'local' }] }] }, { who: 'Navin Rastogi', role: 'buyer' }],
    subjects: [{ identifier: 'Sy.No.9061', what: 'the land sold', from: 'document', places: [{ document: 'deed.pdf', page: 2,
      read_by: 'ai' }] }],
    connections: [
      { id: 'C1', kind: 'client_appears', point: 'Leela Kulkarni is a respondent in a pending appeal.', why: 'She is a client.',
        anchored: true, places: [{ document: 'order.pdf', source: 't1:d1', page: 1 }] },
      { id: 'C2', kind: 'against_client', point: 'A finding against the heirs.', why: '', anchored: false, places: [] }],
    connections_failures: [],
    appearances: [{ name: 'Leela Kulkarni', places: [{ document: 'order.pdf', source: 't1:d1', page: 1 }],
      near: [{ as_written: 'Leela Kulkarny', document: 'deed.pdf', source: 't1:d2', page: 2 }] },
    { name: 'Sarala Kulkarni', places: [], near: [] }] };
  const nodes = context.renderChatBoard(together);
  const fold = nodes.find((node) => node.tagName === 'DETAILS' && text(node).startsWith('Read side by side'));
  assert.ok(fold, 'a fold for what the papers read together show');
  assert.equal(fold.children[0].textContent, 'Read side by side (2)');
  const said = text(fold);
  for (const part of ['Your client’s people elsewhere: Leela Kulkarni is a respondent in a pending appeal. — She is a client. · order.pdf, page 1',
    'Against your client: A finding against the heirs. · its words were not found on the pages, so it rests on nothing yet',
    'Where your client’s people appear', 'Leela Kulkarni: order.pdf, page 1',
    'Written “Leela Kulkarny” on deed.pdf, page 2: a near spelling, not taken to be the same person']) {
    assert.ok(said.includes(part), part);
  }
  assert.ok(!said.includes('Sarala Kulkarni'), 'a name found nowhere and offered nowhere is not listed');
  const understood = text(nodes[nodes.length - 1]);
  for (const part of ['Parts in proceedings (1)', 'Subjects in the papers (1)', 'Who is who in each proceeding',
    'Leela Kulkarni (your client’s side): respondent in W.A. 6649 of 2016 · From order.pdf, page 1',
    'Subjects the papers identify', 'Sy.No.9061 — the land sold · From deed.pdf, page 2 (read by AI)']) {
    assert.ok(understood.includes(part), part);
  }
  const failed = context.renderChatBoard({ ...structuredClone(board), connections: [], appearances: [],
    connections_failures: [{ reason: 'TooLongToReadTogether' }] }).map(text).join('\n');
  assert.ok(failed.includes('Your papers could not be read together this time'), 'a failure is said, never an empty success');
  assert.ok(!context.renderChatBoard(structuredClone(board)).map(text).join('\n').includes('Read side by side'), 'nothing where none');
}

console.log('chat board: ok');
