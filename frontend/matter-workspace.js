/* Served matter projections and explicit commands. No second matter store. */
'use strict';
(() => {
  const node = (tag, text, className) => {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (className) el.className = className;
    return el;
  };
  const named = value => typeof value === 'string' && value.trim() ? value : 'Not recorded';
  const human = value => named(value).replaceAll('_', ' ');
  const button = (text, action, className = 'ghost') => {
    const el = node('button', text, className);
    el.type = 'button';
    el.addEventListener('click', action);
    return el;
  };
  const toolbar = node('nav', undefined, 'matter-tools');
  toolbar.id = 'matter-tools';
  toolbar.setAttribute('aria-label', 'Matter records and instructions');
  toolbar.hidden = true;
  // F-B-04. IN THE MATTER'S HEADER, beside Case file and History -- not a bar of
  // its own above the chat.
  document.querySelector('#workspace-focus .workspace-actions').prepend(toolbar);
  const dialog = node('dialog', undefined, 'account-dialog matter-dialog');
  dialog.id = 'matter-workspace-dialog';
  dialog.setAttribute('aria-labelledby', 'matter-workspace-title');
  const heading = node('div', undefined, 'dialog-heading');
  const titles = node('div');
  const eyebrow = node('p', 'THE MATTER RECORD', 'eyebrow');
  const title = node('h2');
  title.id = 'matter-workspace-title';
  titles.append(eyebrow, title);
  heading.append(titles, button('Close', dismiss));
  const body = node('div', undefined, 'matter-dialog-body');
  const status = node('p', undefined, 'matter-action-status');
  status.setAttribute('role', 'status');
  dialog.append(heading, body, status);
  document.body.append(dialog);
  let generation = 0;
  let mutationView = null;
  // Unconfirmed declarations retain their key across dialog reopening in this
  // authenticated session. They never become a fresh exception on retry.
  const declarationAttempts = new Map();
  const urgencyAttempts = new Map();

  function dismiss() {
    generation += 1;
    if (dialog.open) dialog.close();
    body.replaceChildren();
    status.textContent = '';
    title.textContent = '';
  }
  dialog.addEventListener('cancel', event => { event.preventDefault(); dismiss(); });
  // A queued close from an earlier view must not wipe a newly opened view.
  dialog.addEventListener('close', () => { if (!dialog.open) dismiss(); });
  function context() {
    return { session: state.sessionGeneration, rail: state.railGeneration,
      matter: state.matterId, view: generation };
  }
  function current(token) {
    return dialog.open && !state.ended && !!state.advocate
      && token.session === state.sessionGeneration && token.rail === state.railGeneration
      && token.matter === state.matterId && token.view === generation;
  }
  function path(token, suffix) {
    return `/api/matters/${encodeURIComponent(token.matter)}/${suffix}`;
  }
  function checked(data, token) {
    if (!data || data.state !== 'ok' || data.matter_id !== token.matter) {
      throw new Error('This matter record could not be established. Reopen the matter and try again.');
    }
    return data;
  }
  function errorText(error) {
    if (typeof error.detail === 'string') return error.detail;
    if (error.detail) return 'The request was not accepted. Reopen the matter to check its current record.';
    return error.message || 'The record could not be loaded. Please try again.';
  }
  function section(label) {
    const el = node('section', undefined, 'matter-section');
    el.append(node('h3', label));
    return el;
  }
  function fields(parent, rows) {
    const list = node('dl', undefined, 'matter-fields');
    for (const [label, value] of rows) list.append(node('dt', label), node('dd', value));
    parent.append(list);
  }
  function list(parent, values, empty) {
    if (!Array.isArray(values)) throw new Error('Part of this record is unavailable. Reopen the matter to retry.');
    if (!values.length) { parent.append(node('p', empty, 'matter-muted')); return; }
    const ul = node('ul', undefined, 'matter-list');
    values.forEach(value => ul.append(node('li', named(value))));
    parent.append(ul);
  }
  async function open(kind) {
    if (!state.matterId || !state.advocate || state.ended || !state.matterReady) return;
    generation += 1;
    title.textContent = { cover: 'The matter cover', casefile: 'The attributed file', emergency: 'Protective handoff' }[kind];
    body.replaceChildren(node('p', 'Reading the saved matter…', 'matter-muted'));
    status.textContent = '';
    if (!dialog.open) dialog.showModal();
    const token = context();
    try {
      if (kind === 'cover') {
        const [cover, commission] = await Promise.all([
          api(path(token, 'cover')), api(path(token, 'commission'))]);
        if (!current(token)) return;
        checked(cover, token); checked(commission, token);
        if (!Number.isInteger(cover.version) || cover.version < 0 || commission.version !== cover.version
            || (cover.commission?.version ?? null) !== (commission.commission?.version ?? null)) {
          throw new Error('The instructions changed while this view loaded. Close and reopen the cover.');
        }
        renderCover(cover, commission, token);
      } else {
        const data = await api(path(token, kind));
        if (!current(token)) return;
        checked(data, token);
        if (kind === 'casefile') renderCasefile(data);
        else renderEmergency(data, token);
      }
    } catch (error) {
      if (!current(token)) return;
      body.replaceChildren(node('p', errorText(error), 'matter-warning'),
        button('Try again', () => open(kind)));
    }
  }
  function partySaid(party) {
    return party ? `${named(party.described_as)} · ${named(party.party_id)} · ${human(party.capacity)}` : 'Not recorded';
  }
  function commissionCard(commission) {
    const card = section(`Instructions · version ${commission.version}`);
    fields(card, [
      ['Objective', named(commission.objective)], ['Work product', human(commission.work_product)],
      ['Scope', named(commission.scope)], ['Instructing party', partySaid(commission.instructing)],
      ['Decision maker', partySaid(commission.deciding)], ['Forum', named(commission.forum)],
      ['Deadline', named(commission.deadline?.said)], ['Recorded by', named(commission.recorded_by)],
      ['Recorded at', named(commission.recorded_at)], ['Reason for this version', named(commission.because)]
    ]);
    card.append(node('h4', 'Excluded from the instructions'));
    list(card, commission.exclusions, 'No exclusions recorded; this does not establish unlimited scope.');
    card.append(node('h4', 'Constraints'));
    list(card, commission.constraints, 'No constraints recorded.');
    card.append(node('h4', 'Still to establish'));
    list(card, commission.unknowns, 'No mechanical instruction gaps reported. Professional review is still required.');
    return card;
  }
  function renderCover(cover, record, token) {
    const summary = section(named(cover.title));
    const postureSaid = { mixed: 'Different roles across disputes', partial: 'Partly established — see each dispute',
      conflicted: 'Conflicting recorded roles — clarification required', not_established: 'Not established' };
    fields(summary, [
      ['Client', cover.client_state === 'recorded' ? named(cover.client) : 'Not recorded'],
      ['Posture', cover.posture_state === 'recorded' ? human(cover.posture) : postureSaid[cover.posture_state] || 'Not established'],
      ['Stage', human(cover.stage)], ['Last activity', named(cover.last_activity)],
      ['Instruction deadline assessment', human(cover.deadline_assessment)], ['Instruction deadline', named(cover.deadline_said)],
      ['Saved file version', String(cover.version)]
    ]);
    body.replaceChildren(summary);
    if (Array.isArray(cover.postures) && cover.postures.length) {
      const postures = section('Position in each dispute');
      cover.postures.forEach(row => {
        const card = section(named(row.thread));
        fields(card, [['Recorded role', human(row.role)], ['Basis', human(row.basis)],
          ['Established', row.resolved === true ? 'Yes' : 'Not established']]);
        if (Array.isArray(row.conflicts)) list(card, row.conflicts.map(conflict =>
          `Recorded: ${human(conflict.on_record)}; later suggested: ${human(conflict.now_suggested)} — clarification required`), 'No posture conflicts recorded.');
        postures.append(card);
      });
      body.append(postures);
    }
    const deadlines = section('Case deadlines');
    const register = cover.case_deadlines;
    if (!register || !Array.isArray(register.deadline_entries)) {
      deadlines.append(node('p', 'Case deadline register unavailable. This is not an assessment that no deadline applies.', 'matter-warning'));
    } else {
      fields(deadlines, [['Register assessment', human(register.deadline_assessment)],
        ['Next live date', register.next_deadline || 'No dated live entry established']]);
      if (register.deadline_assessment !== 'assessed') deadlines.append(node('p',
        'The register is not fully assessed. The entries below are only what could be read from this file.', 'matter-warning'));
      if (!register.deadline_entries.length && register.deadline_assessment === 'assessed') {
        deadlines.append(node('p', 'The assessed case register contains no deadlines.', 'matter-muted'));
      }
      register.deadline_entries.forEach(row => {
        const entry = section(`${human(row.status)} · ${row.on || 'Date not established'}`);
        fields(entry, [['Action', named(row.action)], ['Owner', named(row.owner)], ['Source', named(row.source)],
          ['Consequence', named(row.consequence)], ['Dispute reference', named(row.thread)]]);
        deadlines.append(entry);
      });
      if (Array.isArray(register.deadline_unreadable) && register.deadline_unreadable.length) {
        list(deadlines, register.deadline_unreadable.map(row => `Unreadable saved entry: ${named(row.reason)}`), '');
      }
      if (Array.isArray(register.deadline_unassessed) && register.deadline_unassessed.length) {
        list(deadlines, register.deadline_unassessed.map(id => `Assessment not established for dispute ${id}`), '');
      }
    }
    body.append(deadlines);
    body.append(node('p', 'Recording who instructs or decides describes the instruction. It does not grant authority to concede, settle, waive or act externally.', 'matter-notice'));
    if (cover.commission) body.append(commissionCard(cover.commission));
    else body.append(node('p', 'No commission is recorded. The objective, work product, scope, parties, forum and deadline remain to be established.', 'matter-warning'));
    body.append(button(cover.commission ? 'Update the instructions' : 'Record the instructions', () => {
      if (current(token)) renderCommissionForm(cover.commission, cover.version, token);
    }, 'primary'));
    const history = section('Earlier instructions');
    if (!Array.isArray(record.history)) throw new Error('Instruction history is unavailable.');
    if (!record.history.length) history.append(node('p', 'No earlier versions recorded.', 'matter-muted'));
    record.history.forEach(commission => {
      const detail = node('details');
      detail.append(node('summary', `Version ${commission.version} · ${named(commission.recorded_at)}`), commissionCard(commission));
      history.append(detail);
    });
    body.append(history);
    const refusals = section('Recorded authority refusals');
    if (!Array.isArray(record.refusals)) throw new Error('The authority-refusal record is unavailable.');
    if (!record.refusals.length) refusals.append(node('p', 'No refusals recorded. This is not an authority grant.', 'matter-muted'));
    record.refusals.forEach(refusal => fields(refusals, [
      ['Person', named(refusal.actor_id)], ['Attempted act', human(refusal.act)],
      ['Standing', human(refusal.standing)], ['Reason', named(refusal.why)]
    ]));
    body.append(refusals);
  }
  function input(form, name, label, value = '', { type = 'text', options, required = false } = {}) {
    const wrap = node('label', undefined, 'matter-input');
    const control = node(options ? 'select' : type === 'textarea' ? 'textarea' : 'input');
    control.name = name; control.id = `mw-${name}`; control.required = required;
    if (options) options.forEach(([key, text]) => {
      const option = node('option', text); option.value = key; control.append(option);
    });
    else if (type === 'textarea') control.rows = 3;
    else control.type = type;
    control.value = value;
    wrap.append(node('span', label), control); form.append(wrap);
    return control;
  }
  function renderCommissionForm(previous, observedVersion, token) {
    const data = previous || {};
    const form = node('form', undefined, 'matter-form');
    form.autocomplete = 'off';
    form.append(node('p', 'Record only what is known. Missing instructions stay unknown. A named role describes the source of an instruction; it does not grant operational authority.', 'matter-notice'));
    input(form, 'objective', 'What should the work achieve?', data.objective, { type: 'textarea' });
    input(form, 'work_product', 'Work product', data.work_product || 'unstated', { options: [
      ['unstated', 'Not yet stated'], ['advice', 'Advice'], ['research', 'Research'], ['draft', 'Draft'],
      ['hearing', 'Hearing preparation'], ['negotiation', 'Negotiation'], ['protective_triage', 'Protective triage']
    ] });
    input(form, 'scope', 'Scope of the instruction', data.scope, { type: 'textarea' });
    input(form, 'exclusions', 'Exclusions · one per line', (data.exclusions || []).join('\n'), { type: 'textarea' });
    input(form, 'constraints', 'Constraints · one per line', (data.constraints || []).join('\n'), { type: 'textarea' });
    for (const [key, label] of [['instructing', 'Who gives the instructions?'], ['deciding', 'Who owns the decision?']]) {
      const group = node('fieldset'); group.append(node('legend', label));
      const party = data[key] || {};
      input(group, `${key}_id`, 'Party identifier', party.party_id);
      input(group, `${key}_description`, 'Name or description', party.described_as);
      input(group, `${key}_capacity`, 'Recorded capacity', party.capacity || 'unknown', { options: [
        ['unknown', 'Not established'], ['instructing', 'Instructing'], ['deciding', 'Deciding'],
        ['advising', 'Advising'], ['assisting', 'Assisting']
      ] });
      form.append(group);
    }
    input(form, 'forum', 'Forum', data.forum);
    const deadline = data.deadline || {};
    const kind = input(form, 'deadline_kind', 'Deadline assessment', deadline.kind || 'unknown', { options: [
      ['unknown', 'Not established'], ['date', 'A dated deadline'], ['none_applies', 'Assessed: none applies']
    ] });
    const date = input(form, 'deadline_on', 'Deadline date', deadline.on, { type: 'date' });
    const basis = input(form, 'deadline_basis', 'Provision or event supporting the date', deadline.basis, { type: 'textarea' });
    const reason = input(form, 'deadline_reason', 'Why it is unknown, or why none applies', deadline.reason, { type: 'textarea' });
    const deadlineFields = () => {
      const dated = kind.value === 'date';
      for (const control of [date, basis]) { control.required = dated; control.disabled = !dated; control.parentElement.hidden = !dated; }
      reason.required = !dated; reason.disabled = dated; reason.parentElement.hidden = dated;
    };
    kind.addEventListener('change', deadlineFields); deadlineFields();
    input(form, 'because', previous ? 'Reason for changing the instructions' : 'Reason for recording these instructions', '', { type: 'textarea', required: !!previous });
    const actions = node('div', undefined, 'matter-actions');
    const save = node('button', 'Record instructions', 'primary'); save.type = 'submit';
    actions.append(save, button('Back to cover', () => open('cover'))); form.append(actions);
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (!current(token) || save.disabled || !form.reportValidity()) return;
      const value = key => form.elements.namedItem(key).value.trim();
      const lines = key => value(key).split('\n').map(line => line.trim()).filter(Boolean);
      const payload = { expected_version: observedVersion, objective: value('objective'), work_product: value('work_product'), scope: value('scope'),
        exclusions: lines('exclusions'), constraints: lines('constraints'), forum: value('forum'), because: value('because'),
        deadline: kind.value === 'date' ? { kind: 'date', on: value('deadline_on'), basis: value('deadline_basis') }
          : { kind: kind.value, reason: value('deadline_reason') } };
      for (const key of ['instructing', 'deciding']) {
        const partyId = value(`${key}_id`), description = value(`${key}_description`), capacity = value(`${key}_capacity`);
        if (partyId || description || capacity !== 'unknown') {
          if (!partyId || !description) { status.textContent = 'Give both an identifier and a description for each named party.'; return; }
          payload[key] = { party_id: partyId, described_as: description, capacity };
        } else if (previous?.[key]) {
          status.textContent = 'This form cannot erase a recorded party. Name the replacement or keep the existing party.'; return;
        }
      }
      await write(token, 'commission', payload, save, 'commission_recorded', result => {
        if (typeof result.reopened !== 'boolean') throw new Error('The instruction-change outcome could not be confirmed.');
        return result.reopened
          ? 'Instructions recorded. Material changes reopened scope assessment; confirm it before substantive work.'
          : 'Instructions recorded. Any remaining unknowns still need attention.';
      });
    });
    body.replaceChildren(form); status.textContent = '';
  }
  function renderCasefile(data) {
    if (!Array.isArray(data.entries)) throw new Error('The attributed file is unavailable.');
    body.replaceChildren(node('p', 'These are the saved assertions and their sources, not new findings. Repetition is not documentation; reading quality is not human confirmation.', 'matter-notice'));
    const integrity = section('Checks on the saved file');
    integrity.append(node('h4', 'Documentary-status concerns'));
    list(integrity, data.repetition_upgrades, 'No documentary-status upgrades without a source were reported.');
    integrity.append(node('h4', 'Disputes split into separate answers'));
    list(integrity, data.split_disputes, 'No split-dispute concerns were reported.');
    body.append(integrity);
    if (!data.entries.length) body.append(node('p', 'No facts are recorded on this file yet. This does not establish that the facts are agreed.', 'matter-muted'));
    data.entries.forEach((entry, index) => {
      const card = section(`Recorded statement ${index + 1} · revision ${entry.version}`);
      if (entry.superseded_by) card.classList.add('matter-superseded');
      card.append(node('p', named(entry.statement), 'matter-statement'));
      const source = entry.attribution || {};
      fields(card, [['Record reference', named(entry.fact_id)],
        ['Certainty', human(entry.certainty)], ['Human confirmation', human(entry.confirmed)],
        ['Reading quality', human(source.read_quality)], ['Source', named(source.said)],
        ['Superseded by', entry.superseded_by ? named(entry.superseded_by) : 'Not superseded']]);
      card.append(node('h4', 'Contradictions linked to this entry'));
      list(card, entry.conflicts_with, 'No contradiction links recorded; this does not prove consistency.');
      if (source.document) card.append(node('p', 'Source location is recorded above. Opening the original is not available from this view.', 'matter-muted'));
      body.append(card);
    });
  }
  function emergencyCard(record, label) {
    const card = section(label);
    fields(card, [['Basis', named(record.basis)], ['Declared by', named(record.actor_id)],
      ['Declared at', named(record.declared_at)], ['Expires at', named(record.expires_at)],
      ['Permitted scope', named(record.permitted_scope)], ['Revoked at', record.revoked_at || 'Not revoked'],
      ['Revoked by', record.revoked_by || 'Not recorded']]);
    card.append(node('h4', 'Screens outstanding when declared'));
    list(card, record.outstanding, 'None recorded at declaration. This is not a current screening assessment.');
    return card;
  }
  function renderEmergency(data, token) {
    body.replaceChildren();
    renderUrgencies(data, token);
    body.append(node('p', 'For immediate protective or referral guidance only. A declaration does not clear any screen, authorise substantive advice or send a request.', 'matter-notice'));
    body.append(node('p', named(data.said), 'matter-warning'));
    if (data.governing) {
      body.append(emergencyCard(data.governing, 'The governing exception'));
      const requestForm = node('form', undefined, 'matter-form');
      requestForm.autocomplete = 'off';
      input(requestForm, 'protective_request', 'What immediate protective handoff do you need?', '', { type: 'textarea', required: true });
      requestForm.append(node('p', 'This asks for the limited protective handoff. It does not ask the model for analysis or establish new case facts.', 'matter-muted'));
      const request = node('button', 'Request protective handoff', 'primary'); request.type = 'submit';
      requestForm.append(request);
      requestForm.addEventListener('submit', async event => {
        event.preventDefault();
        if (!current(token) || request.disabled || !requestForm.reportValidity()) return;
        if (activeDelivery || mutationView === token.view || !state.matterReady) { status.textContent = 'Wait for the current request to finish before requesting a protective handoff.'; return; }
        request.disabled = true;
        try {
          // Re-read rather than treating a dialog left open as an unexpired grant.
          const latest = await api(path(token, 'emergency'));
          if (!current(token)) return;
          checked(latest, token);
          if (!latest.governing) { renderEmergency(latest, token); status.textContent = 'No live exception remains. Review the current record before declaring another.'; return; }
          if (activeDelivery || mutationView === token.view || !state.matterReady) { status.textContent = 'The workspace is busy. Try again when the current request finishes.'; return; }
          const message = requestForm.elements.namedItem('protective_request').value.trim();
          // send captures the request synchronously before this dialog is wiped.
          const delivered = send(message, { workProduct: 'protective_triage' });
          dismiss();
          await delivered;
        } catch (error) {
          if (current(token)) status.textContent = errorText(error);
        } finally { if (current(token)) request.disabled = false; }
      });
      body.append(requestForm);
      const revoke = button('End the protective exception', async () => {
        if (!current(token) || revoke.disabled) return;
        if (!Number.isInteger(data.version) || !/^[a-f0-9]{64}$/.test(data.governing_ref || '')) {
          status.textContent = 'The declaration identity is unavailable. Reopen this record before ending it.'; return;
        }
        await write(token, 'emergency', { revoke: true, expected_version: data.version,
          governing_ref: data.governing_ref }, revoke, 'emergency_revoked', result => {
          if (result.governing_ref !== data.governing_ref || result.version !== data.version + 1) {
            throw new Error('The declaration change could not be confirmed.');
          }
          return 'Protective exception ended. Its history remains on the matter.';
        });
      });
      body.append(revoke);
    }
    const form = node('form', undefined, 'matter-form'); form.autocomplete = 'off';
    form.append(node('h3', data.governing ? 'Record a new bounded declaration' : 'Declare a bounded exception'));
    input(form, 'basis', 'What immediate danger requires the exception?', '', { type: 'textarea', required: true });
    const hours = input(form, 'hours', 'Hours until review is required · 1–24', '1', { type: 'number', required: true });
    hours.min = '1'; hours.max = '24'; hours.step = '1';
    const declare = node('button', 'Record declaration only', 'primary'); declare.type = 'submit'; form.append(declare);
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (!current(token) || declare.disabled || !form.reportValidity()) return;
      const basis = form.elements.namedItem('basis').value.trim();
      const duration = Number(hours.value);
      const identity = JSON.stringify([token.session, token.matter, basis, duration]);
      if (!declarationAttempts.has(identity)) declarationAttempts.set(identity, crypto.randomUUID());
      const requestKey = declarationAttempts.get(identity);
      await write(token, 'emergency', { request_key: requestKey, basis, hours: duration }, declare, 'emergency_declared',
        result => {
          if (result.request_key !== requestKey || typeof result.replayed !== 'boolean') {
            throw new Error('The declaration receipt identity could not be confirmed.');
          }
          declarationAttempts.delete(identity);
          return result.replayed
            ? 'Earlier declaration receipt recovered; its original expiry was not renewed. Reopen Protective handoff to check whether it is still live.'
            : 'Declaration recorded; no handoff was requested. Open Protective handoff to inspect the expiry and request guidance.';
        });
    });
    body.append(form);
    const history = section('Declaration history');
    if (!Array.isArray(data.history)) throw new Error('The declaration history is unavailable.');
    if (!data.history.length) history.append(node('p', 'No declarations recorded.', 'matter-muted'));
    data.history.forEach(record => {
      const detail = node('details');
      detail.append(node('summary', `${human(record.state)} · ${named(record.declared_at)}`), emergencyCard(record, 'Recorded declaration'));
      history.append(detail);
    });
    body.append(history);
  }
  function renderUrgencies(data, token) {
    const register = data.urgency_register;
    const card = section('Recorded dangers and protective actions');
    if (!register || register.state !== 'ok' || !Array.isArray(register.entries)
        || !Array.isArray(register.classes) || !Number.isInteger(data.version)) {
      card.append(node('p', 'The urgency register is unavailable. No danger is cleared by its absence.', 'matter-warning'));
      body.append(card); return;
    }
    card.append(node('p', 'These are user-supplied, unverified records, not assessed legal advice. An unknown time is not a safe delay. Ending the protective permission never resolves a recorded danger.', 'matter-notice'));
    if (!register.entries.length) card.append(node('p', 'No dangers recorded. Applicable urgency classes remain not assessed; this is not an all-clear.', 'matter-warning'));
    for (const row of register.entries) {
      const item = section(`${human(row.state)} · ${human(row.class)}`);
      const supplied = key => row[key] === null ? `Unknown — ${named(row.unknowns?.[key])}` : named(row[key]);
      fields(item, [['Stated danger', named(row.basis)], ['Protective action · not performed', supplied('action')],
        ['Responsible person', supplied('owner')], ['Supplied due time', supplied('due')],
        ['Recorded by', named(row.raised_by)], ['Recorded at', named(row.raised_at)]]);
      if (row.state === 'live') item.append(button('Record explicit resolution', () => {
        if (current(token)) renderUrgencyForm(data, token, row);
      }));
      else fields(item, [['Resolved by', named(row.resolver)], ['Resolution basis', named(row.resolution_basis)], ['Resolved at', named(row.resolved_at)]]);
      card.append(item);
    }
    card.append(button('Record a danger manually', () => {
      if (current(token)) renderUrgencyForm(data, token);
    }, 'primary'));
    const coverage = node('details');
    coverage.append(node('summary', 'Classes not automatically assessed'));
    list(coverage, register.classes.map(row => `${human(row.class)} · ${human(row.assessment)}`), 'Class coverage is unavailable.');
    coverage.append(node('p', named(register.taxonomy_basis), 'matter-muted'));
    card.append(coverage); body.append(card);
  }
  function renderUrgencyForm(data, token, resolving = null) {
    const form = node('form', undefined, 'matter-form'); form.autocomplete = 'off';
    form.append(node('h3', resolving ? 'Explicitly resolve this danger' : 'Record a stated danger'));
    form.append(node('p', 'Record only what you know. Actions and due times are supplied by you, not independently verified or performed by NM.', 'matter-notice'));
    if (resolving) {
      form.append(node('p', `${human(resolving.class)} · ${named(resolving.basis)}`, 'matter-warning'));
      input(form, 'urgency-resolution', 'What established that this named danger is resolved?', '', {type: 'textarea', required: true});
    } else {
      input(form, 'urgency-class', 'Urgency class', '', {required: true,
        options: [['', 'Choose the applicable class'], ...data.urgency_register.classes.map(row => [row.class, row.label])]});
      input(form, 'urgency-basis', 'What danger has been reported?', '', {type: 'textarea', required: true});
      for (const [key, label, type] of [['action', 'Supplied protective action · not performed', 'textarea'],
        ['owner', 'Responsible person', 'text'], ['due', 'Supplied due time · your browser local time', 'datetime-local']]) {
        input(form, `urgency-${key}`, label, '', {type});
        input(form, `urgency-${key}-unknown`, `If ${key} is unknown, explain what is missing`);
      }
    }
    const save = node('button', resolving ? 'Record this resolution' : 'Record this danger', 'primary');
    save.type = 'submit'; form.append(save);
    form.append(button('Back to protective records', () => open('emergency')));
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (!current(token) || save.disabled || !form.reportValidity()) return;
      const value = name => form.elements.namedItem(name).value.trim();
      const command = resolving ? 'resolve' : 'raise';
      let payload;
      try {
        if (resolving) payload = {urgency_id: resolving.urgency_id, resolution_basis: value('urgency-resolution')};
        else {
          const urgency = {class: value('urgency-class'), basis: value('urgency-basis'), unknowns: {}};
          for (const key of ['action', 'owner', 'due']) {
            const supplied = value(`urgency-${key}`), unknown = value(`urgency-${key}-unknown`);
            if ((!supplied && !unknown) || (supplied && unknown)) throw new Error(`Supply ${key}, or explain why it is unknown — not both.`);
            urgency[key] = supplied ? (key === 'due' ? new Date(supplied).toISOString() : supplied) : null;
            if (!supplied) urgency.unknowns[key] = unknown;
          }
          payload = {urgency};
        }
      } catch (error) { status.textContent = errorText(error); return; }
      const identity = JSON.stringify([token.session, token.matter, command, payload]);
      if (!urgencyAttempts.has(identity)) urgencyAttempts.set(identity, {request_key: crypto.randomUUID(), expected_version: data.version});
      const attempt = urgencyAttempts.get(identity);
      await write(token, 'emergency', {urgency_command: command, ...payload, ...attempt}, save,
        resolving ? 'urgency_resolved' : 'urgency_recorded', result => {
          if (result.request_key !== attempt.request_key || result.version !== attempt.expected_version + 1
              || typeof result.replayed !== 'boolean' || !result.urgency_id
              || (resolving && result.urgency_id !== resolving.urgency_id)) throw new Error('The urgency receipt could not be confirmed.');
          urgencyAttempts.delete(identity);
          return result.replayed ? 'Earlier urgency change recovered. Reopen the record for its current state.'
            : 'Urgency record saved. Protective permission is unchanged; no action was performed.';
        }, error => {
          if ([400, 409, 422].includes(error.status)) urgencyAttempts.delete(identity);
        });
    });
    body.replaceChildren(form); status.textContent = '';
  }
  async function write(token, suffix, payload, control, expectedState, success, rejected = () => {}) {
    if (!current(token) || mutationView === token.view) return;
    mutationView = token.view;
    control.disabled = true; status.textContent = 'Recording the change…';
    try {
      const result = await api(path(token, suffix), { method: 'POST',
        headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) });
      if (!current(token)) return;
      if (!result || result.matter_id !== token.matter || result.state !== expectedState) {
        throw new Error('The change was not confirmed. Reopen the saved record before retrying.');
      }
      const message = success(result);
      dismiss();
      // A successful record change is not a fresh assessment of the advice
      // already displayed. The shared restore path preserves pending intent
      // while presenting committed answers as their historical read-back.
      const refreshedRail = state.railGeneration + 1;
      await showThreadBoard(token.matter, { restore: true, closeNavigator: false });
      if (token.session === state.sessionGeneration && token.matter === state.matterId
          && refreshedRail === state.railGeneration && !state.ended && state.matterReady) {
        document.getElementById('save-status').textContent = message;
      }
    } catch (error) {
      if (current(token)) rejected(error);
      if (current(token)) status.textContent = `${errorText(error)} Reopen the record before retrying if the response was lost.`;
    } finally {
      if (mutationView === token.view) mutationView = null;
      if (current(token)) control.disabled = false;
    }
  }
  function update() {
    dismiss();
    toolbar.hidden = !state.matterId || !state.advocate || state.ended;
    toolbar.querySelectorAll('button').forEach(control => { control.disabled = !state.matterReady; });
  }
  toolbar.append(button('Matter cover & instructions', () => open('cover')),
    button('Attributed file', () => open('casefile')),
    button('Protective handoff', () => open('emergency')));
  window.addEventListener('nm:matter-changed', update);
  window.addEventListener('nm:session-ended', () => { declarationAttempts.clear(); urgencyAttempts.clear(); update(); });
  update();
})();
