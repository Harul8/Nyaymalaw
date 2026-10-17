'use strict';

window.NmBrainSources = (() => {
  let request;
  let scope;
  let generation = 0;
  let active = null;
  // BACK BETWEEN THINGS OPENED (owner decision, 17 Oct 2026): what was open before,
  // newest last, and how to show again what is open now.
  let trail = [];
  let current = null;
  const node = (id) => document.getElementById(id);

  function configure(options) {
    request = options.request;
    scope = options.scope;
  }

  function showBack() {
    const back = node('brain-source-back');
    if (back) back.hidden = trail.length === 0;
  }

  function remember(entry, viaBack) {
    if (!viaBack && current) trail.push(current);
    current = entry;
    showBack();
  }

  // Empty the pane for what opens next; the pane, its trail and its opener stay.
  function clear() {
    generation += 1;
    active = null;
    node('brain-source-title').textContent = '';
    node('brain-source-status').textContent = '';
    node('brain-source-body').replaceChildren();
  }

  // THE READING PANE ON THE RIGHT (owner, 16 Oct 2026): one pane for every link,
  // opened beside the conversation rather than over it, so the answer and its
  // source can be read together. The window makes room for it while it is open.
  function close(restoreFocus = true) {
    const opener = active?.opener;
    clear();
    trail = [];
    current = null;
    showBack();
    const dialog = node('brain-source-reader');
    if (dialog.open) dialog.close();
    node('pane-advise').classList.remove('reading');
    if (restoreFocus && opener?.isConnected) opener.focus();
  }

  function begin(label, opener, status = '') {
    clear();
    const read = {generation, scope:JSON.stringify(scope()), opener};
    active = read;
    node('brain-source-title').textContent = label;
    node('brain-source-status').textContent = status;
    node('pane-advise').classList.add('reading');
    const dialog = node('brain-source-reader');
    if (!dialog.open) dialog.show();
    node('brain-source-close').focus();
    return read;
  }

  // Anything else a link opens - a document as it was read - in the same pane.
  function showContent(label, content, opener, viaBack = false) {
    remember({show: (back) => showContent(label, content, opener, back)}, viaBack);
    begin(label, opener);
    node('brain-source-body').replaceChildren(...content);
    node('brain-source-body').scrollTop = 0;
  }

  function coreInspection(source, inspection) {
    return source?.brain === true && legal(source)
      && inspection?.contract === 'core_source_authority_view_v1'
      && ['core_turn_v1', 'core_turn_v2', 'core_turn_v3', 'core_turn_v4', 'core_turn_v5']
        .includes(inspection.activity_contract)
      && inspection.source_id === source.id
      && ['recorded', 'not_assessed'].includes(inspection.state)
      && ['case_checks', 'provision_checks', 'provision_mentions']
        .every(key => Array.isArray(inspection[key]));
  }

  // A check on this source that did not come out clean (17 Oct 2026): said above the
  // fold, as a disclosure is never folded away; its detail stays in the checks below.
  function needsAttention(source, inspection) {
    if (!coreInspection(source, inspection)) return false;
    return (inspection.case_checks || []).some((check) => ['not_held', 'ambiguous', 'unavailable'].includes(check.lookup)
        || check.association === 'different_used_identity'
        || (check.quotes || []).some((quote) => quote.result === 'not_found'))
      || (inspection.provision_checks || []).some((check) => check.state !== 'matched');
  }

  function authorityDetails(source, inspection) {
    if (!legal(source)) return [];
    const section = document.createElement('section');
    section.setAttribute('aria-label', 'Saved source checks');
    const heading = document.createElement('p');
    heading.className = 'hint'; heading.textContent = 'Saved source checks';
    section.appendChild(heading);
    const line = (label, text) => {
      if (!words(text)) return;
      const detail = document.createElement('p');
      detail.className = 'brain-source-excerpt'; detail.textContent = `${label}: ${text}`;
      section.appendChild(detail);
    };
    if (!coreInspection(source, inspection)) {
      line('Source checks', 'Not assessed — saved check evidence is unavailable for this passage.');
      return [section];
    }
    if (inspection.state === 'not_assessed') {
      line('Source checks', 'Not assessed');
      line('Scope', inspection.reason);
    }
    for (const check of inspection.case_checks || []) {
      line('Citation', check.text);
      line('Citation lookup', ({found:'Found in the held corpus', not_held:'Not held by Nyaymalaw',
        ambiguous:'More than one held judgment — identity unresolved',
        unavailable:'Could not be checked'})[check.lookup] || 'Not assessed');
      line('Name in the response', check.name_given);
      line('Name comparison', ({matches_recorded_name:'Matches the recorded name',
        not_given:'No name supplied beside this citation'})[check.name_check] || 'Not assessed');
      for (const judgment of check.judgments || []) {
        line('Held record', [judgment.title, judgment.court, judgment.decided_on].filter(words).join(' · '));
      }
      line('Relation to this passage', ({matched:check.matching_source_ids?.includes(source.id)
          ? 'Citation resolves to this passage’s judgment'
          : 'Citation resolves to another judgment used in this response paragraph',
        different_used_identity:'Citation resolves to a different judgment from the passage used',
        unresolved_association:'Not resolved'})[check.association] || 'Not assessed');
      for (const mention of check.selected_support_mentions || []) {
        line('Citation mentioned in this passage', mention.text);
      }
      line('Identity-check scope', check.association_scope);
      if (!check.quotes?.length) line('Quotation check', 'Not assessed — no quotation check is recorded.');
      for (const quote of check.quotes || []) {
        line('Quotation', quote.quote);
        line('Quotation wording', ({found:'Words found in the held judgment text',
          not_found:'Words not found in the held judgment text'})[quote.result] || 'Not assessed');
        line('Quotation association', quote.attribution === 'single_candidate'
          ? 'One candidate judgment; the speaker and legal effect require context'
          : 'Candidate judgment unresolved');
        line('Quotation-check scope', quote.detail);
      }
      line('Legal validity', 'Not assessed by these identity and wording checks');
    }
    for (const check of inspection.provision_checks || []) {
      line('Provision readback', ({matched:'Matches the selected saved passage',
        different_snapshot:'Readback differs from the selected saved passage',
        not_held:'Not held under the selected Act and reference',
        ambiguous:'More than one provision matches — reference unresolved',
        unavailable:'Could not be checked'})[check.state] || 'Not assessed');
      line('Readback detail', check.reason);
      line('Legal version and applicability', 'Not assessed by this source-identity check');
    }
    for (const mention of inspection.provision_mentions || []) {
      line('Provision reference in the response', mention.text);
      line('Act-name association', 'Not assessed');
      line('Reference detail', mention.reason);
    }
    return [section];
  }

  const ROLES = {legislative_text:'Legislative text', court_conclusion:'Court conclusion',
    court_reasoning:'Court reasoning', party_submission:'Party submission',
    quoted_authority:'Quoted authority', case_background:'Case background', unclear:'Unclear',
    contract:'Quoted contract terms', original_account:'Original account',
    opposing_account:'Opposing account', treatment_support:'Passage used to assess court treatment',
    supplied_document:'Document the advocate sent'};
  const roleLabel = (statement) => ROLES[statement?.source_role] || ROLES[statement?.assertion_role];
  const treatmentLabel = (statement) => {
    if (statement?.source_role === 'supplied_document') return '';
    const treatment = statement?.source_treatment;
    if (statement?.assertion_role === 'party_submission'
        && ['adopted', 'rejected', 'qualified'].includes(treatment)) return `Court ${treatment}`;
    return ({not_shown:'Not shown', 'not shown':'Not shown',
      not_applicable:'Not applicable', 'not applicable':'Not applicable'})[treatment] || treatment;
  };

  // Where a passage comes from, in the advocate's words: a document's page, a statute's
  // section, a judgment's paragraph (the store's part number is not shown).
  function whereFrom(source) {
    const kind = source.kind === 'document' ? 'Document you sent'
      : source.kind === 'judgment' ? 'Held judgment' : source.kind === 'provision' ? 'Held law' : '';
    const locator = words(source.locator) ? source.locator : '';
    const paragraph = /^(\d+)(?:_\d+)?$/.exec(locator);
    return [kind, paragraph ? `paragraph ${paragraph[1]}` : locator].filter(words).join(' · ');
  }

  // The supporting words with a little of what surrounds them, cut at a sentence or a
  // line where one is near. None when the words cannot be placed, or are the whole text.
  function excerptWindow(text, excerpt, reach = 240) {
    const at = words(excerpt) && words(text) ? text.indexOf(excerpt) : -1;
    if (at < 0 || (at === 0 && excerpt.length === text.length)) return null;
    let start = Math.max(0, at - reach);
    let end = Math.min(text.length, at + excerpt.length + reach);
    const lead = text.slice(start, at);
    const cut = Math.max(lead.lastIndexOf('. '), lead.lastIndexOf('\n'));
    if (start > 0 && cut >= 0) start += cut + 1;
    const tail = text.slice(at + excerpt.length, end);
    const stop = tail.search(/[.!?]\s|\n/);
    if (end < text.length && stop >= 0) end = at + excerpt.length + stop + 1;
    if (start === 0 && end === text.length) return null;
    return {lead:`${start > 0 ? '…' : ''}${text.slice(start, at).trimStart()}`, excerpt,
      tail:`${text.slice(at + excerpt.length, end).trimEnd()}${end < text.length ? '…' : ''}`};
  }

  // Text into host with the supporting words marked where they stand.
  function marked(host, text, excerpt) {
    const at = words(excerpt) ? text.indexOf(excerpt) : -1;
    if (at < 0) { host.textContent = text; return host; }
    const mark = document.createElement('mark');
    mark.textContent = excerpt;
    host.append(document.createTextNode(text.slice(0, at)), mark,
      document.createTextNode(text.slice(at + excerpt.length)));
    return host;
  }

  // A document as one (owner decision 5, 17 Oct 2026): every page in order, a small mark
  // where each begins, the cited page's supporting words marked.
  function documentFlow(document_, number, excerpt) {
    const make = (tag, className, text) => {
      const item = document.createElement(tag);
      item.className = className;
      if (text !== undefined) item.textContent = text;
      return item;
    };
    const entries = [...document_.pages.map((page) => ({number:page.number, page})),
      ...document_.unread.map((unread) => ({number:unread.number, unread}))]
      .sort((left, right) => left.number - right.number);
    const flow = [];
    for (const entry of entries) {
      if (entries.length > 1) flow.push(make('div', 'page-mark', `Page ${entry.number}`));
      if (entry.unread) { flow.push(make('p', 'document-unread', `Not read: ${entry.unread.reason}`)); continue; }
      const text = make('div', 'document-text');
      flow.push(entry.number === number ? marked(text, entry.page.text, excerpt) : Object.assign(text,
        {textContent:entry.page.text}));
    }
    return flow;
  }

  // The whole document a cited page belongs to, from this conversation's saved files.
  async function wholeDocument(answer, source, read, host, button) {
    const place = /^(.*):d(\d+)p(\d+)$/.exec(source.id || '');
    const owns = () => active === read && generation === read.generation;
    if (!place || !answer.chat_id) { host.hidden = false; button.hidden = true; return; }
    button.disabled = true;
    button.textContent = 'Opening the whole document…';
    try {
      const listing = await request(`/api/chats/${encodeURIComponent(answer.chat_id)}/documents`);
      if (!owns()) return;
      const turn = (listing?.sent || []).find((row) => row.turn_id === place[1]);
      const document_ = turn && turn.documents[Number(place[2]) - 1];
      if (!document_) throw new Error('not found');
      host.replaceChildren(...documentFlow(document_, Number(place[3]), source.verification?.support_excerpt));
      host.hidden = false;
      button.hidden = true;
    } catch {
      if (!owns()) return;
      host.hidden = false;
      button.disabled = true;
      button.textContent = 'The whole document could not be opened; this page is shown below';
    }
  }

  // THE PASSAGE FIRST (owner decisions, 17 Oct 2026): where it is from, what it is, the
  // supporting words marked in place, the whole passage or document a click away, and
  // every saved check folded under "How NM checked this".
  function populate(source, choices = null, inspection = null, responseText = null, answer = null) {
    const coreResponse = coreInspection(source, inspection) && words(responseText);
    const make = (tag, className, text) => {
      const item = document.createElement(tag);
      if (className) item.className = className;
      if (text !== undefined) item.textContent = text;
      return item;
    };
    const shown = [make('p', 'source-where', whereFrom(source))];
    const role = roleLabel(source.verification);
    const treatment = treatmentLabel(source.verification);
    if (legal(source) && words(role)) {
      shown.push(make('p', 'source-role', `${role}${words(treatment) ? ` · ${treatment}` : ''}`));
    }
    if (words(source.qualification)) shown.push(make('p', 'hint', source.qualification));
    if (needsAttention(source, inspection)) {
      shown.push(make('p', 'source-attention',
        'One of NM\u2019s checks on this source did not come out clean: see How NM checked this.'));
    }
    const excerpt = source.verification?.support_excerpt;
    const full = marked(make('div', 'brain-source-text'), source.text, excerpt);
    const view = excerptWindow(source.text, excerpt);
    if (view) {
      const window_ = make('div', 'brain-source-window');
      const mark = make('mark', '', view.excerpt);
      window_.append(document.createTextNode(view.lead), mark, document.createTextNode(view.tail));
      const expand = make('button', 'ghost source-expand',
        source.kind === 'document' ? 'Show the whole document' : 'Show the whole passage');
      expand.type = 'button';
      full.hidden = true;
      const read = active;
      expand.addEventListener('click', () => {
        if (source.kind === 'document' && answer) return wholeDocument(answer, source, read, full, expand);
        full.hidden = !full.hidden;
        expand.textContent = full.hidden ? 'Show the whole passage' : 'Hide the whole passage';
      });
      shown.push(window_, expand);
    } else if (source.kind === 'document' && answer && /:d\d+p\d+$/.test(source.id || '')) {
      const expand = make('button', 'ghost source-expand', 'Show the whole document');
      expand.type = 'button';
      const read = active;
      const page = full;
      const whole = make('div', 'document-flow');
      whole.hidden = true;
      expand.addEventListener('click', () => wholeDocument(answer, source, read, whole, expand));
      shown.push(page, expand, whole);
    }
    if (!shown.includes(full)) shown.push(full);
    if (choices) shown.push(choices);
    const checks = make('details', 'how-checked');
    checks.appendChild(make('summary', '', 'How NM checked this'));
    if (coreResponse) {
      checks.append(make('p', 'brain-source-excerpt', `NM response: ${responseText}`),
        make('p', 'hint', 'Selected source passage'));
    }
    checks.append(make('p', 'hint', source.locator), ...authorityDetails(source, inspection));
    if (source.provenance_status === 'not_recorded') {
      checks.appendChild(make('p', 'hint', 'Statement-role labels were not recorded for this saved response.'));
    }
    for (const [label, text] of [
      ...(coreResponse ? [] : [['Statement used', source.verification?.assertion_statement]]),
      [coreResponse ? 'Source passage role' : 'Statement role', role],
      ['Support check', source.verification?.reason],
      [coreResponse ? 'Supporting source words' : 'Supporting words', source.verification?.support_excerpt],
      ['Limiting condition', source.verification?.scope_excerpt],
      ['Who states the proposition', source.verification?.owner_label],
      ['Attribution words', source.verification?.owner_excerpt],
      ['Treatment in the source', treatment],
      ['Treatment words', source.verification?.treatment_excerpt],
    ]) {
      // A document page has no court treatment, and its author is whoever it shows.
      if (!text || (source.kind === 'document' && [
        'Who states the proposition', 'Treatment in the source', 'Treatment words'].includes(label))) continue;
      checks.appendChild(make('p', 'brain-source-excerpt', `${label}: ${text}`));
    }
    for (const statement of source.verification?.context_statements || []) {
      const related = roleLabel(statement) || 'Related statement';
      const handled = treatmentLabel(statement);
      for (const [label, text] of [
        ...(coreResponse
          ? [['Related source passage', [statement.title, statement.locator].filter(words).join(' · ')],
             ['Related source role', `${related}${handled ? ` · ${handled}` : ''}`]]
          : [['Related statement', `${related}${handled ? ` · ${handled}` : ''}: ${statement.assertion_statement}`]]),
        ['Speaker', statement.owner_label === 'document' ? '' : statement.owner_label],
        [coreResponse ? 'Related source words' : 'Statement words', statement.support_excerpt],
        ['Attribution words', statement.owner_excerpt], ['Treatment words', statement.treatment_excerpt],
      ]) {
        if (!text) continue;
        checks.appendChild(make('p', 'brain-source-excerpt', `${label}: ${text}`));
      }
    }
    shown.push(checks);
    node('brain-source-body').replaceChildren(...shown);
    node('brain-source-body').scrollTop = 0;
    node('brain-source-status').textContent = '';
  }

  async function open(answer, element, elementIndex, sourceIndex, opener, viaBack = false) {
    const sources = Array.isArray(element.sources) ? element.sources : [element.source];
    const source = sources[sourceIndex];
    if (!source?.brain || !answer.turn_id || (!answer.matter_id && !answer.chat_id)) return;
    const owner = answer.matter_id
      ? `matters/${encodeURIComponent(answer.matter_id)}`
      : `chats/${encodeURIComponent(answer.chat_id)}`;
    remember({show: (back) => open(answer, element, elementIndex, sourceIndex, opener, back)}, viaBack);
    const read = begin(source.label, opener, 'Reading the saved passage…');
    const owns = () => active === read && generation === read.generation
      && JSON.stringify(scope()) === read.scope;
    try {
      const saved = await request(`/api/${owner}/turns/${encodeURIComponent(answer.turn_id)}`
        + `/brain-sources/${elementIndex}/${sourceIndex}`);
      if (!owns()) return;
      if (saved.id !== source.id || saved.digest !== source.digest
          || saved.text !== source.text || saved.locator !== source.locator
          || saved.label !== source.label || saved.kind !== source.kind) {
        throw new Error('The saved passage could not be matched to this response.');
      }
      populate({...saved, qualification: saved.qualification
        + (saved.verification_current === false
          ? ' This historical check predates the current source review.' : '')},
        sourceChoices(answer, element, elementIndex, sourceIndex, opener, owns),
        saved.authority_inspection, element.text, answer);
    } catch (error) {
      if (owns()) node('brain-source-status').textContent =
        `The saved passage could not be read. ${error.message}`;
    }
  }

  const legal = (source) => source?.kind === 'provision' || source?.kind === 'judgment';
  // A page of a document the advocate sent is cited and opened like a passage of law
  // (rendering v7, 15 Oct 2026); only law carries citation identity checks.
  const cited = (source) => legal(source) || source?.kind === 'document';
  const words = (value) => typeof value === 'string' && Boolean(value.trim());
  const passageKey = (source) => JSON.stringify([
    source.kind, source.label, source.locator, source.text, source.digest,
  ]);

  function labelFor(source) {
    const title = words(source?.label) ? source.label : words(source?.title) ? source.title : '';
    const locator = words(source?.locator) ? source.locator : '';
    return title && locator.startsWith(title) ? locator : [title, locator].filter(words).join(' · ');
  }

  function entries(element) {
    const sources = Array.isArray(element.sources) ? element.sources : [element.source];
    const seen = new Set();
    return sources.flatMap((source, index) => {
      if (!source) return [];
      const key = passageKey(source);
      if (seen.has(key)) return [];
      seen.add(key);
      return [{source, index, key}];
    });
  }

  function bound(answer, element, source) {
    return source.brain === true && words(source.id) && words(source.digest)
      && words(source.label) && words(source.locator) && words(source.text)
      && answer.turn_id && (answer.matter_id || answer.chat_id)
      && Array.isArray(answer.elements) && answer.elements.indexOf(element) >= 0
      && Array.isArray(element.refs) && element.refs.includes(source.locator);
  }

  function sourceChoices(answer, element, elementIndex, sourceIndex, opener, owns) {
    const sources = Array.isArray(element.sources) ? element.sources : [element.source];
    const choices = sources.flatMap((source, index) => cited(source) && bound(answer, element, source)
      ? [{source, index}] : []);
    if (choices.length < 2) return null;
    const nav = document.createElement('nav');
    nav.className = 'brain-source-links';
    nav.setAttribute('aria-label', 'Sources supporting this response paragraph');
    const heading = document.createElement('p');
    heading.className = 'hint'; heading.textContent = 'Supporting passages';
    nav.appendChild(heading);
    for (const [offset, entry] of choices.entries()) {
      if (offset) nav.appendChild(document.createTextNode(' · '));
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'citation-link';
      button.textContent = labelFor(entry.source);
      button.disabled = entry.index === sourceIndex;
      button.setAttribute('aria-current', entry.index === sourceIndex ? 'true' : 'false');
      button.setAttribute('aria-label', `Open saved passage: ${labelFor(entry.source)}`);
      button.addEventListener('click', () => {
        if (!owns() || entry.index === sourceIndex) return;
        // Re-enter the saved-source boundary; related client metadata is not a read receipt.
        return open(answer, element, elementIndex, entry.index, opener);
      });
      nav.appendChild(button);
    }
    return nav;
  }

  function responseLink(answer, element, entry, label) {
    const link = document.createElement('button');
    link.type = 'button'; link.className = 'citation-link'; link.textContent = label;
    link.setAttribute('aria-label', `Open saved passage: ${label}`);
    link.addEventListener('click', () => open(answer, element,
      answer.elements.indexOf(element), entry.index, link));
    return link;
  }

  // Rendering v4 to v10: each used source the paragraph does not name follows it as a
  // marker that opens the same saved passage. From 17 Oct 2026 (owner decision 6) an
  // earlier answer keeps its markers folded under one "Sources" control; from v11 a
  // source sits on the words it supports and no marker follows. An opened fold stays
  // open across the thread's redraws; the saved paragraph itself is the key.
  const openSources = new WeakSet();
  function appendMarkers(host, answer, element, sources) {
    if (!Array.isArray(element.citation_markers)) return 0;
    const chips = [];
    for (const marker of element.citation_markers) {
      const index = marker?.source_index;
      const source = Number.isInteger(index) ? sources[index] : null;
      if (!cited(source) || source.id !== marker?.source_id || !bound(answer, element, source)) continue;
      const chip = responseLink(answer, element, {source, index}, labelFor(source));
      chip.className = 'citation-link citation-marker';
      chips.push(chip);
    }
    if (!chips.length) return 0;
    const fold = document.createElement('span');
    fold.className = 'citation-fold';
    fold.hidden = !openSources.has(element);
    for (const [offset, chip] of chips.entries()) {
      if (offset) fold.appendChild(document.createTextNode(' '));
      fold.appendChild(chip);
    }
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'citation-link citation-sources';
    toggle.textContent = `Sources (${chips.length})`;
    toggle.setAttribute('aria-expanded', String(!fold.hidden));
    toggle.addEventListener('click', () => {
      fold.hidden = !fold.hidden;
      if (fold.hidden) openSources.delete(element);
      else openSources.add(element);
      toggle.setAttribute('aria-expanded', String(!fold.hidden));
    });
    host.appendChild(document.createTextNode(' '));
    host.appendChild(toggle);
    host.appendChild(document.createTextNode(' '));
    host.appendChild(fold);
    return chips.length;
  }

  function appendBody(host, answer, element) {
    const text = typeof element.text === 'string' ? element.text : '';
    if (Array.isArray(element.inline_citations)) {
      const sources = Array.isArray(element.sources) ? element.sources : [element.source];
      const anchors = [];
      for (const citation of element.inline_citations) {
        const phrase = citation?.text;
        const index = citation?.source_index;
        const source = Number.isInteger(index) ? sources[index] : null;
        // Rendering v4 places each link at its exact saved offsets; earlier
        // versions name a phrase that must occur once in the paragraph.
        const placed = Number.isInteger(citation?.start) && Number.isInteger(citation?.end);
        const start = !words(phrase) ? -1 : placed
          ? (text.slice(citation.start, citation.end) === phrase ? citation.start : -1)
          : text.indexOf(phrase);
        if (start < 0 || (!placed && text.indexOf(phrase, start + 1) >= 0) || !cited(source)
            || source.id !== citation.source_id || !bound(answer, element, source)) continue;
        anchors.push({start, end:start + phrase.length, phrase, source, index});
      }
      anchors.sort((left, right) => left.start - right.start);
      let offset = 0;
      let linked = 0;
      for (const anchor of anchors) {
        if (anchor.start < offset) continue;
        host.appendChild(document.createTextNode(text.slice(offset, anchor.start)));
        host.appendChild(responseLink(answer, element, anchor, anchor.phrase));
        offset = anchor.end; linked += 1;
      }
      host.appendChild(document.createTextNode(text.slice(offset)));
      return linked + appendMarkers(host, answer, element, sources);
    }
    const tokens = new Map();
    for (const entry of entries(element).filter(({source}) => legal(source))) {
      const {source} = entry;
      if (!words(source.label) || !words(source.locator)) continue;
      for (const token of new Set([source.label, source.locator,
        `${source.label} · ${source.locator}`])) {
        if (!tokens.has(token)) tokens.set(token, []);
        tokens.get(token).push(entry);
      }
    }
    const word = (value) => Boolean(value) && /[\p{L}\p{N}_]/u.test(value);
    let offset = 0;
    let links = 0;
    while (offset < text.length) {
      let next = null;
      for (const [token, candidates] of tokens) {
        let start = text.indexOf(token, offset);
        while (start >= 0 && ((word(token[0]) && word(text[start - 1]))
            || (word(token.at(-1)) && word(text[start + token.length])))) {
          start = text.indexOf(token, start + 1);
        }
        if (start >= 0 && (!next || start < next.start
            || (start === next.start && token.length > next.token.length))) {
          next = {start, token, candidates};
        }
      }
      if (!next) { host.appendChild(document.createTextNode(text.slice(offset))); break; }
      if (next.start > offset) {
        host.appendChild(document.createTextNode(text.slice(offset, next.start)));
      }
      const entry = next.candidates.length === 1 ? next.candidates[0] : null;
      if (entry && bound(answer, element, entry.source)) {
        host.appendChild(responseLink(answer, element, entry, next.token)); links += 1;
      } else host.appendChild(document.createTextNode(next.token));
      offset = next.start + next.token.length;
    }
    return links;
  }

  function isReadableRecordSource(source) {
    if (!source || !legal(source)
        || !['id', 'title', 'locator', 'text'].every(key => words(source[key]))) return false;
    const checked = source.verification;
    return Boolean(checked && words(checked.reason) && words(checked.support_excerpt)
      && source.text.includes(checked.support_excerpt)
      && typeof checked.scope_excerpt === 'string'
      && (!checked.scope_excerpt || (words(checked.scope_excerpt)
        && source.text.includes(checked.scope_excerpt)))
      && ['established', 'asked_to_establish', 'conditional', 'no_special_condition']
        .includes(checked.scope_status)
      && (checked.scope_status === 'no_special_condition') === !checked.scope_excerpt);
  }

  function openRecordSource(source, opener, {reviewPending = true} = {}, viaBack = false) {
    if (!isReadableRecordSource(source)) return false;
    remember({show: (back) => openRecordSource(source, opener, {reviewPending}, back)}, viaBack);
    begin(source.title, opener);
    populate({...source, qualification:
      "Saved with this dispute's legal requirements. Support was checked for that item; "
      + (reviewPending ? 'this historical check predates the current source review. ' : '')
      + 'this does not establish applicability, binding force, or the complete source.'});
    return true;
  }

  node('brain-source-close').addEventListener('click', () => close());
  node('brain-source-back')?.addEventListener('click', () => {
    const previous = trail.pop();
    if (previous) previous.show(true);
  });
  node('brain-source-reader').addEventListener('cancel', (event) => {
    event.preventDefault(); close();
  });
  node('brain-source-reader').addEventListener('close', () => {
    if (active && !node('brain-source-reader').open) close();
  });
  // A pane beside the page has no dialog Escape of its own; Escape closes it unless
  // the board's own pane, which closes first, holds the focus.
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape' || event.defaultPrevented || !node('brain-source-reader').open) return;
    if (node('board-pane')?.contains(document.activeElement)) return;
    event.preventDefault();
    close();
  });
  window.addEventListener('nm:matter-changed', () => close(false));
  return Object.freeze({configure, open, close, showContent, appendBody,
    openRecordSource, isReadableRecordSource, labelFor});
})();
