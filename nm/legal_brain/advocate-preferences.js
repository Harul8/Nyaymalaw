/* Explicit account preferences. Transport and session/CSRF authority remain in app.js. */
(function (root, factory) {
  'use strict';
  const exported = factory();
  if (typeof module === 'object' && module.exports) module.exports = exported;
  else root.NMAdvocatePreferences = exported;
})(typeof globalThis === 'object' ? globalThis : this, function () {
  'use strict';
  const PATH = '/api/account/advocate-memory';
  const FIELDS = {
    advice_length: 'Advice length', authorities_position: 'Where authorities appear',
    advice_form: 'Advice format', draft_date_format: 'Dates in drafts',
    court_ids: 'Courts you usually appear in', standing_instructions: 'Working preferences',
  };
  const LABELS = {
    short: 'Short', standard: 'Standard', detailed: 'Detailed', inline: 'Alongside the advice',
    end: 'At the end', prose: 'Paragraphs', bullets: 'Bullet points', iso: 'Year-month-day',
    day_month_year: 'Day, month and year', explain_abbreviations: 'Explain abbreviations',
    show_action_owners: 'Show who owns each next step', include_short_summary: 'Include a short summary',
    supreme_court: 'Supreme Court of India', hc_telangana: 'High Court for the State of Telangana',
    hc_andhra_pradesh: 'High Court of Andhra Pradesh',
  };
  const LISTS = new Set(['court_ids', 'standing_instructions']);
  const VALUES = {
    advice_length: ['short', 'standard', 'detailed'], authorities_position: ['inline', 'end'],
    advice_form: ['prose', 'bullets'], draft_date_format: ['iso', 'day_month_year'],
    court_ids: ['supreme_court', 'hc_telangana', 'hc_andhra_pradesh'],
    standing_instructions: ['explain_abbreviations', 'show_action_owners', 'include_short_summary'],
  };
  const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const known = (table, key) => Object.prototype.hasOwnProperty.call(table, key);

  function checkedMemory(value) {
    if (!object(value) || !Number.isSafeInteger(value.version) || value.version < 0
        || !['empty', 'saved'].includes(value.state) || !object(value.settings)
        || !object(value.supported) || !object(value.courts) || typeof value.limits !== 'string'
        || value.limits.length > 1000 || Object.keys(value.supported).length !== Object.keys(FIELDS).length
        || Object.keys(value.settings).some(key => !known(FIELDS, key))) {
      throw new Error('The saved preferences could not be verified. Reload before changing them.');
    }
    for (const key of Object.keys(FIELDS)) {
      const choices = value.supported[key];
      if (!Array.isArray(choices) || !choices.length || choices.length > 8
          || new Set(choices).size !== choices.length
          || choices.some(choice => !VALUES[key].includes(choice))) {
        throw new Error('The supported preference choices could not be verified.');
      }
      if (!known(value.settings, key)) continue;
      const selected = value.settings[key];
      if (LISTS.has(key)) {
        if (!Array.isArray(selected) || selected.length > choices.length
            || new Set(selected).size !== selected.length || selected.some(item => !choices.includes(item))) {
          throw new Error('The saved preference choices could not be verified.');
        }
      } else if (typeof selected !== 'string' || !choices.includes(selected)) {
        throw new Error('The saved preference choices could not be verified.');
      }
    }
    if ((value.state === 'saved') !== Boolean(Object.keys(value.settings).length)
        || value.version === 0 && Object.keys(value.settings).length) {
      throw new Error('The saved preference state could not be verified.');
    }
    // Keep only the checked snapshot; arbitrary response extensions never enter UI state.
    return {version: value.version, state: value.state,
      settings: JSON.parse(JSON.stringify(value.settings)),
      supported: JSON.parse(JSON.stringify(value.supported)), limits: value.limits};
  }

  function create({document, api, session, menuClose = () => {}}) {
    const get = id => document.getElementById(id);
    const dialog = get('advocate-preferences-dialog');
    const fields = get('advocate-preferences-fields');
    const saved = get('advocate-preferences-saved');
    const status = get('advocate-preferences-status');
    const approve = get('advocate-preferences-approve');
    const save = get('advocate-preferences-save');
    const erase = get('advocate-preferences-delete');
    const controls = new Map();
    const controllers = new Set();
    let generation = 0;
    let view = null;
    let busy = false;
    let deleteButtons = [];

    function buttons() {
      save.disabled = busy || !view || !approve.checked;
      erase.disabled = busy || !view || !Object.keys(view.settings).length || !approve.checked;
      approve.disabled = busy || !view;
      for (const button of deleteButtons) button.disabled = busy || !view || !approve.checked;
      for (const inputs of controls.values()) for (const input of inputs) input.disabled = busy || !view;
    }
    function clear(close = true) {
      generation += 1;
      for (const controller of controllers) controller.abort();
      controllers.clear();
      view = null; busy = false; controls.clear(); deleteButtons = [];
      fields.replaceChildren(); saved.replaceChildren(); status.textContent = '';
      get('advocate-preferences-limits').textContent = '';
      approve.checked = false;
      buttons();
      if (close && dialog.open) dialog.close();
    }
    function element(tag, text, className) {
      const node = document.createElement(tag);
      if (text !== undefined) node.textContent = text;
      if (className) node.className = className;
      return node;
    }
    function changed() { approve.checked = false; buttons(); }
    function render(checked) {
      view = checked; controls.clear(); deleteButtons = [];
      fields.replaceChildren(); saved.replaceChildren(); approve.checked = false;
      get('advocate-preferences-limits').textContent = checked.limits;
      for (const [key, title] of Object.entries(FIELDS)) {
        const block = element('fieldset');
        block.appendChild(element('legend', title));
        const inputs = [];
        if (LISTS.has(key)) {
          for (const choice of checked.supported[key]) {
            const label = element('label', undefined, 'consent');
            const input = element('input'); input.type = 'checkbox'; input.value = choice;
            input.checked = (checked.settings[key] || []).includes(choice);
            input.addEventListener('change', changed);
            inputs.push(input); label.append(input, element('span', LABELS[choice])); block.appendChild(label);
          }
        } else {
          const input = element('select'); input.setAttribute('aria-label', title);
          const unset = element('option', 'Use defaults (not saved)'); unset.value = ''; input.appendChild(unset);
          for (const choice of checked.supported[key]) {
            const option = element('option', LABELS[choice]); option.value = choice; input.appendChild(option);
          }
          input.value = checked.settings[key] || '';
          input.addEventListener('change', changed); inputs.push(input); block.appendChild(input);
        }
        controls.set(key, inputs); fields.appendChild(block);
        if (known(checked.settings, key)) {
          const row = element('div', undefined, 'session-row');
          row.appendChild(element('strong', title));
          const values = LISTS.has(key) ? checked.settings[key] : [checked.settings[key]];
          row.appendChild(element('p', values.map(value => LABELS[value]).join(', ') || 'None selected'));
          const button = element('button', 'Delete this preference', 'ghost'); button.type = 'button';
          button.addEventListener('click', () => mutate('DELETE', key));
          deleteButtons.push(button); row.appendChild(button); saved.appendChild(row);
        }
      }
      if (!Object.keys(checked.settings).length) saved.appendChild(element('p', 'No preferences are saved. Conversations use defaults.'));
      buttons();
    }
    async function request(path, options) {
      const controller = new AbortController(); controllers.add(controller);
      try { return await api(path, {...options, signal: controller.signal,
                                  cache: 'no-store', credentials: 'same-origin'}); }
      finally { controllers.delete(controller); }
    }
    function owner() {
      const snapshot = session();
      return {account: snapshot.account, session: snapshot.generation, generation};
    }
    function current(token) {
      const now = session();
      return Boolean(token.account && token.account === now.account && token.session === now.generation
        && token.generation === generation && dialog.open);
    }
    async function open() {
      clear(false);
      if (!session().account) return;
      menuClose(); if (!dialog.open) dialog.showModal();
      const token = owner(); busy = true; status.textContent = 'Reading your saved preferences…'; buttons();
      try {
        const response = await request(PATH, {method: 'GET'});
        if (!current(token)) return;
        render(checkedMemory(response)); status.textContent = 'These preferences apply when a new conversation begins.';
      } catch (error) {
        if (!current(token) || error.obsolete) return;
        status.textContent = 'Could not read your preferences. Nothing has been loaded. Reload to try again.';
      } finally { if (current(token)) { busy = false; buttons(); } }
    }
    function selected() {
      const settings = {};
      for (const [key, inputs] of controls) {
        if (LISTS.has(key)) {
          const values = inputs.filter(input => input.checked).map(input => input.value);
          if (values.length) settings[key] = values;
        } else if (inputs[0].value) settings[key] = inputs[0].value;
      }
      return settings;
    }
    async function mutate(method, key = null) {
      if (busy || !view || !approve.checked || !session().account || !dialog.open) return;
      const token = owner(); const expected = view.version;
      const body = {approved: true, expected_version: expected};
      if (method === 'PUT') body.settings = selected();
      busy = true; buttons(); status.textContent = method === 'PUT' ? 'Saving approved preferences…' : 'Deleting approved preferences…';
      try {
        const response = await request(PATH + (key ? `/${encodeURIComponent(key)}` : ''),
          {method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
        if (!current(token)) return;
        const checked = checkedMemory(response);
        if (checked.version !== expected + 1) throw new Error('The saved version changed.');
        render(checked);
        status.textContent = method === 'PUT' ? 'Preferences saved for new conversations.' : 'Preference deletion confirmed.';
      } catch (error) {
        if (!current(token) || error.obsolete) return;
        view = null; fields.replaceChildren(); saved.replaceChildren(); controls.clear(); deleteButtons = [];
        approve.checked = false;
        status.textContent = 'The change was not confirmed. Reload your preferences before trying again.';
      } finally { if (current(token)) { busy = false; buttons(); } }
    }
    get('advocate-preferences').addEventListener('click', open);
    get('advocate-preferences-reload').addEventListener('click', open);
    get('advocate-preferences-close').addEventListener('click', () => clear());
    dialog.addEventListener('close', () => { if (!dialog.open) clear(false); });
    approve.addEventListener('change', buttons);
    save.addEventListener('click', () => mutate('PUT'));
    erase.addEventListener('click', () => mutate('DELETE'));
    buttons();
    return {open, clear, save: () => mutate('PUT'), deleteAll: () => mutate('DELETE'),
            deleteEntry: key => known(FIELDS, key) ? mutate('DELETE', key) : Promise.resolve()};
  }
  return {create, checkedMemory};
});
