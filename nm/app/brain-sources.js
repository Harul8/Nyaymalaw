'use strict';

window.NmBrainSources = (() => {
  let request;
  let scope;
  let generation = 0;
  let active = null;
  const node = (id) => document.getElementById(id);

  function configure(options) {
    request = options.request;
    scope = options.scope;
  }

  function close(restoreFocus = true) {
    generation += 1;
    const opener = active?.opener;
    active = null;
    const dialog = node('brain-source-reader');
    if (dialog.open) dialog.close();
    node('brain-source-title').textContent = '';
    node('brain-source-status').textContent = '';
    node('brain-source-body').replaceChildren();
    if (restoreFocus && opener?.isConnected) opener.focus();
  }

  function begin(label, opener, status = '') {
    close(false);
    const read = {generation, scope:JSON.stringify(scope()), opener};
    active = read;
    node('brain-source-title').textContent = label;
    node('brain-source-status').textContent = status;
    node('brain-source-reader').showModal();
    node('brain-source-close').focus();
    return read;
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
    if (inspection?.contract !== 'core_source_authority_view_v1'
        || !['core_turn_v1', 'core_turn_v2'].includes(inspection.activity_contract)
        || inspection.source_id !== source.id
        || !['recorded', 'not_assessed'].includes(inspection.state)
        || !['case_checks', 'provision_checks', 'provision_mentions']
          .every(key => Array.isArray(inspection[key]))) {
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

  function populate(source, choices = null, inspection = null) {
    const locator = document.createElement('p');
    locator.className = 'hint'; locator.textContent = source.locator;
    const qualification = document.createElement('p');
    qualification.className = 'hint'; qualification.textContent = source.qualification;
    const details = [...(choices ? [choices] : []), locator, qualification,
      ...authorityDetails(source, inspection)];
    const roles = {legislative_text:'Legislative text', court_conclusion:'Court conclusion',
      court_reasoning:'Court reasoning', party_submission:'Party submission',
      quoted_authority:'Quoted authority', case_background:'Case background', unclear:'Unclear',
      contract:'Quoted contract terms', original_account:'Original account',
      opposing_account:'Opposing account', treatment_support:'Passage used to assess court treatment'};
    const roleLabel = (statement) => roles[statement?.source_role] || roles[statement?.assertion_role];
    const treatmentLabel = (statement) => {
      const treatment = statement?.source_treatment;
      if (statement?.assertion_role === 'party_submission'
          && ['adopted', 'rejected', 'qualified'].includes(treatment)) return `Court ${treatment}`;
      return ({not_shown:'Not shown', 'not shown':'Not shown',
        not_applicable:'Not applicable', 'not applicable':'Not applicable'})[treatment] || treatment;
    };
    if (source.provenance_status === 'not_recorded') {
      const missing = document.createElement('p');
      missing.className = 'hint';
      missing.textContent = 'Statement-role labels were not recorded for this saved response.';
      details.push(missing);
    }
    for (const [label, text] of [
      ['Statement used', source.verification?.assertion_statement],
      ['Statement role', roleLabel(source.verification)],
      ['Support check', source.verification?.reason],
      ['Supporting words', source.verification?.support_excerpt],
      ['Limiting condition', source.verification?.scope_excerpt],
      ['Who states the proposition', source.verification?.owner_label],
      ['Attribution words', source.verification?.owner_excerpt],
      ['Treatment in the source', treatmentLabel(source.verification)],
      ['Treatment words', source.verification?.treatment_excerpt],
    ]) {
      if (!text) continue;
      const detail = document.createElement('p');
      detail.className = 'brain-source-excerpt'; detail.textContent = `${label}: ${text}`;
      details.push(detail);
    }
    for (const statement of source.verification?.context_statements || []) {
      const role = roleLabel(statement) || 'Related statement';
      const treatment = treatmentLabel(statement);
      for (const [label, text] of [
        ['Related statement', `${role}${treatment ? ` · ${treatment}` : ''}: ${statement.assertion_statement}`],
        ['Speaker', statement.owner_label], ['Statement words', statement.support_excerpt],
        ['Attribution words', statement.owner_excerpt], ['Treatment words', statement.treatment_excerpt],
      ]) {
        if (!text) continue;
        const detail = document.createElement('p');
        detail.className = 'brain-source-excerpt'; detail.textContent = `${label}: ${text}`;
        details.push(detail);
      }
    }
    const passage = document.createElement('div');
    passage.className = 'brain-source-text'; passage.textContent = source.text;
    node('brain-source-body').replaceChildren(...details, passage);
    node('brain-source-body').scrollTop = 0;
    node('brain-source-status').textContent = '';
  }

  async function open(answer, element, elementIndex, sourceIndex, opener) {
    const sources = Array.isArray(element.sources) ? element.sources : [element.source];
    const source = sources[sourceIndex];
    if (!source?.brain || !answer.turn_id || (!answer.matter_id && !answer.chat_id)) return;
    const owner = answer.matter_id
      ? `matters/${encodeURIComponent(answer.matter_id)}`
      : `chats/${encodeURIComponent(answer.chat_id)}`;
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
        saved.authority_inspection);
    } catch (error) {
      if (owns()) node('brain-source-status').textContent =
        `The saved passage could not be read. ${error.message}`;
    }
  }

  const legal = (source) => source?.kind === 'provision' || source?.kind === 'judgment';
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
    const choices = sources.flatMap((source, index) => legal(source) && bound(answer, element, source)
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

  function appendBody(host, answer, element) {
    const text = typeof element.text === 'string' ? element.text : '';
    if (Array.isArray(element.inline_citations)) {
      const sources = Array.isArray(element.sources) ? element.sources : [element.source];
      const anchors = [];
      for (const citation of element.inline_citations) {
        const phrase = citation?.text;
        const index = citation?.source_index;
        const source = Number.isInteger(index) ? sources[index] : null;
        const start = words(phrase) ? text.indexOf(phrase) : -1;
        if (start < 0 || text.indexOf(phrase, start + 1) >= 0 || !legal(source)
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
      return linked;
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

  function openRecordSource(source, opener, {reviewPending = true} = {}) {
    if (!isReadableRecordSource(source)) return false;
    begin(source.title, opener);
    populate({...source, qualification:
      "Saved with this dispute's legal requirements. Support was checked for that item; "
      + (reviewPending ? 'this historical check predates the current source review. ' : '')
      + 'this does not establish applicability, binding force, or the complete source.'});
    return true;
  }

  node('brain-source-close').addEventListener('click', () => close());
  node('brain-source-reader').addEventListener('cancel', (event) => {
    event.preventDefault(); close();
  });
  node('brain-source-reader').addEventListener('close', () => {
    if (active && !node('brain-source-reader').open) close();
  });
  window.addEventListener('nm:matter-changed', () => close(false));
  return Object.freeze({configure, open, close, appendBody,
    openRecordSource, isReadableRecordSource, labelFor});
})();
