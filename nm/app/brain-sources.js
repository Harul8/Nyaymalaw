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

  function populate(source) {
    const locator = document.createElement('p');
    locator.className = 'hint'; locator.textContent = source.locator;
    const qualification = document.createElement('p');
    qualification.className = 'hint'; qualification.textContent = source.qualification;
    const details = [locator, qualification];
    for (const [label, text] of [
      ['Support check', source.verification?.reason],
      ['Supporting words', source.verification?.support_excerpt],
      ['Limiting condition', source.verification?.scope_excerpt],
    ]) {
      if (!text) continue;
      const detail = document.createElement('p');
      detail.className = 'brain-source-excerpt'; detail.textContent = `${label}: ${text}`;
      details.push(detail);
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
      populate(saved);
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

  function appendReferences(host, answer, element) {
    const sources = entries(element);
    for (const isLegal of [true, false]) {
      const selected = sources.filter(({source}) => legal(source) === isLegal);
      if (!selected.length) continue;
      const group = document.createElement(isLegal ? 'div' : 'details');
      group.className = `brain-source-links ${isLegal
        ? 'brain-legal-source-links' : 'brain-attributed-source-links'}`;
      const heading = document.createElement(isLegal ? 'span' : 'summary');
      heading.textContent = isLegal ? 'Legal sources: ' : `Attributed record (${selected.length})`;
      group.appendChild(heading);
      const list = document.createElement(isLegal ? 'span' : 'ul');
      selected.forEach((entry, position) => {
        const {source} = entry;
        const item = document.createElement(isLegal ? 'span' : 'li');
        const label = isLegal ? labelFor(source) : source.label;
        if (bound(answer, element, source)) {
          item.appendChild(responseLink(answer, element, entry, label));
        } else item.textContent = `${label || 'Saved reference'} — inspection unavailable`;
        if (isLegal && position) list.appendChild(document.createTextNode(' · '));
        list.appendChild(item);
      });
      group.appendChild(list); host.appendChild(group);
    }
    return sources.length;
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

  function openRecordSource(source, opener) {
    if (!isReadableRecordSource(source)) return false;
    begin(source.title, opener);
    populate({...source, qualification:
      "Saved with this dispute's legal requirements. Support was checked for that item; "
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
  return Object.freeze({configure, open, close, appendBody, appendReferences,
    openRecordSource, isReadableRecordSource, labelFor});
})();
