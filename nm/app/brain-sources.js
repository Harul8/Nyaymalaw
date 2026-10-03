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

  async function open(answer, element, elementIndex, sourceIndex, opener) {
    close(false);
    const sources = Array.isArray(element.sources) ? element.sources : [element.source];
    const source = sources[sourceIndex];
    if (!source?.brain || !answer.turn_id || (!answer.matter_id && !answer.chat_id)) return;
    const owner = answer.matter_id
      ? `matters/${encodeURIComponent(answer.matter_id)}`
      : `chats/${encodeURIComponent(answer.chat_id)}`;
    const read = {generation, scope:JSON.stringify(scope()), opener};
    active = read;
    node('brain-source-title').textContent = source.label;
    node('brain-source-status').textContent = 'Reading the saved passage…';
    node('brain-source-reader').showModal();
    node('brain-source-close').focus();
    const owns = () => active === read && generation === read.generation
      && JSON.stringify(scope()) === read.scope;
    try {
      const saved = await request(`/api/${owner}/turns/${encodeURIComponent(answer.turn_id)}`
        + `/brain-sources/${elementIndex}/${sourceIndex}`);
      if (!owns()) return;
      if (saved.id !== source.id || saved.digest !== source.digest
          || saved.text !== source.text || saved.locator !== source.locator) {
        throw new Error('The saved passage could not be matched to this response.');
      }
      const locator = document.createElement('p');
      locator.className = 'hint'; locator.textContent = saved.locator;
      const qualification = document.createElement('p');
      qualification.className = 'hint'; qualification.textContent = saved.qualification;
      const passage = document.createElement('div');
      passage.className = 'brain-source-text'; passage.textContent = saved.text;
      node('brain-source-body').replaceChildren(locator, qualification, passage);
      node('brain-source-body').scrollTop = 0;
      node('brain-source-status').textContent = '';
    } catch (error) {
      if (owns()) node('brain-source-status').textContent =
        `The saved passage could not be read. ${error.message}`;
    }
  }

  node('brain-source-close').addEventListener('click', () => close());
  node('brain-source-reader').addEventListener('cancel', (event) => {
    event.preventDefault(); close();
  });
  node('brain-source-reader').addEventListener('close', () => {
    if (active && !node('brain-source-reader').open) close();
  });
  window.addEventListener('nm:matter-changed', () => close(false));
  return Object.freeze({configure, open, close});
})();
