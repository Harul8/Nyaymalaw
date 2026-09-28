/* The working word while a reply is prepared. No model text or private deliberation. */
'use strict';

(() => {
  const streams = new Set();
  const watchers = new Set();
  function stopAll() {
    streams.forEach((stream) => stream.close());
    streams.clear();
    [...watchers].forEach((watcher) => watcher.stop());
  }
  window.addEventListener('nm:session-ended', stopAll);
  window.addEventListener('nm:matter-changed', stopAll);

  // NO RECORDED-WORK PANEL (owner, 28 September 2026: "Remove, keep saved";
  // LB-139). 'Recorded work for this response' under replies and 'Other
  // recorded work progress' in History are gone; the saved stages stay sealed
  // with the matter and readable through the owned progress reads for review.
  // The stream below feeds only the working word.

  /* LB-82. WHILE A REPLY IS BEING PREPARED.
   *
   * Owner direction, 28 September 2026: in place of a fixed "Working on your
   * brief", show legal words from several languages, chosen by the stage the
   * recorded work has actually reached. The words are decoration and claim
   * nothing about the work. Later the same day: the word alone -- no language,
   * no meaning, no stage line -- and one word every thirty seconds. A stop is
   * shown as the server's own saved label in place of the word, never as more
   * rotating words. Screen readers hear one stable status, not every word.
   *
   * The language and meaning stay beside each word for whoever reviews the
   * list; they are never painted.
   *
   * THE SERVER'S LABELS ARE NAMED HERE VERBATIM. A label this table does not
   * know keeps the current words, and
   * tests/test_working_words_follow_every_recorded_stage.py fails the build
   * when the server can emit a label that is not listed below. */
  const WORDS = {
    reading: [
      ["Da mihi factum, dabo tibi jus", "Latin", "give me the facts, I will give you the law"],
      ["Vakalatnama", "Persian and Urdu", "the document that authorises an advocate to appear"],
      ["Arzi", "Urdu", "a petition; a written application"],
      ["Bayan", "Urdu", "a statement of what happened"],
      ["Locus standi", "Latin", "the standing to bring the matter"],
      ["Muqaddama", "Urdu", "a case; a lawsuit"],
      ["Factum", "Latin", "a fact; a thing done"],
      ["Vadi", "Sanskrit", "the one who brings the claim"],
    ],
    assessing: [
      ["Prima facie", "Latin", "at first sight"],
      ["Nyaya", "Sanskrit", "justice; also reasoned inquiry"],
      ["Ubi jus ibi remedium", "Latin", "where there is a right, there is a remedy"],
      ["Viveka", "Sanskrit", "discernment; sound judgment"],
      ["Bona fide", "Latin", "in good faith"],
      ["Consensus ad idem", "Latin", "a meeting of minds on the same thing"],
      ["Mens rea", "Latin", "a guilty mind"],
    ],
    checking: [
      ["Sakshya", "Sanskrit and Hindi", "evidence"],
      ["Onus probandi", "Latin", "the burden of proof"],
      ["Dastavez", "Urdu", "a document; a deed"],
      ["Saboot", "Urdu", "proof"],
      ["Gawah", "Urdu", "a witness"],
      ["Res ipsa loquitur", "Latin", "the thing speaks for itself"],
      ["Adharam", "Telugu", "the basis; supporting proof"],
      ["Affidavit", "Law Latin", "he has declared on oath"],
    ],
    statute: [
      ["Lex", "Latin", "law; a statute"],
      ["Vidhi", "Sanskrit and Hindi", "law; a rule"],
      ["Qanun", "Arabic and Urdu", "law; an enactment"],
      ["Adhiniyam", "Hindi", "an Act of the legislature"],
      ["Sanhita", "Sanskrit and Hindi", "a code"],
      ["Generalia specialibus non derogant", "Latin", "a general provision does not override a specific one"],
      ["Chattam", "Telugu", "law; an Act"],
    ],
    precedent: [
      ["Stare decisis", "Latin", "stand by what has been decided"],
      ["Ratio decidendi", "Latin", "the reason for the decision"],
      ["Obiter dictum", "Latin", "a remark in passing, not binding"],
      ["Per incuriam", "Latin", "decided in ignorance of binding law"],
      ["Faisla", "Urdu", "a judgment; a decision"],
      ["Tirpu", "Telugu", "a judgment; a verdict"],
      ["Jurisprudence constante", "French", "a settled line of decisions"],
    ],
    opposing: [
      ["Audi alteram partem", "Latin", "hear the other side"],
      ["Prativadi", "Sanskrit", "the one who resists the claim"],
      ["Jawab-dawa", "Urdu", "the written reply to a claim"],
      ["Exceptio", "Latin", "a defence raised against a claim"],
      ["Advocatus diaboli", "Latin", "the devil's advocate"],
      ["Contra proferentem", "Latin", "read against the one who drafted it"],
    ],
    finishing: [
      ["Satyameva jayate", "Sanskrit", "truth alone triumphs"],
      ["Fiat justitia", "Latin", "let justice be done"],
      ["Nota bene", "Latin", "note well"],
      ["Caveat", "Latin", "let them beware; a formal warning"],
      ["Insaf", "Urdu", "justice; fairness"],
      ["Nyayam", "Telugu", "justice"],
      ["Quod erat demonstrandum", "Latin", "which was to be shown"],
    ],
  };
  const STAGE_WORDS = new Map([
    ["Recorded work started.", "reading"],
    ["Assessing the recorded file.", "assessing"],
    ["An assessment was received; checks are still required.", "checking"],
    ["Checking the relevant material.", "checking"],
    ["A material check was recorded.", "checking"],
    ["Source-linked information needs were proposed for this dispute; their applicability has not been assessed.", "checking"],
    ["A provision was read; its application has not been assessed.", "statute"],
    ["An authority passage was read; its legal effect has not been assessed.", "precedent"],
    ["Authority candidates were found; none is yet legal support.", "precedent"],
    ["A source-linked opposition pass was recorded for this dispute; its conclusions have not been independently assessed.", "opposing"],
    ["Cross-dispute opposition work was recorded; its conclusions have not been independently assessed.", "opposing"],
    ["A draft was prepared; it has not been released as advice.", "finishing"],
    ["A question was prepared; checks are still required.", "finishing"],
    ["A conversational reply was prepared; it has not been released.", "finishing"],
  ]);
  // Shown as the label alone: work that failed or stopped is not decorated.
  const PLAIN_STAGES = new Set([
    "Part of the work could not complete.",
    "Work paused at its resource limit.",
    "Work was cancelled or its session ended.",
    "Work paused because further useful progress was not established.",
    "Work paused because a service was unavailable.",
    "Work was interrupted; completion has not been confirmed.",
    "Work stopped at a permission or quality boundary.",
    "Work paused because the checked file could not fit safely.",
    "Work ended; its completion has not been established.",
  ]);
  const CURSOR = /^[0-9]{1,9}\.[a-f0-9]{64}$/;
  // Owner, 28 September 2026: one word every thirty seconds.
  const WORD_EVERY_MS = 30000;
  // A repaint rebuilds the turn; its word, stage and clock carry on.
  const turnMemory = new Map();

  function shuffled(items) {
    const out = [...items];
    for (let i = out.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      [out[i], out[j]] = [out[j], out[i]];
    }
    return out;
  }

  function working(container, { matterId, turnId, read, isCurrent }) {
    container.classList.add('working');
    container.setAttribute('role', 'status');
    const said = document.createElement('span');
    said.className = 'sr-only';
    said.textContent = 'Working on your brief…';
    const word = document.createElement('p');
    word.className = 'working-word';
    word.setAttribute('aria-hidden', 'true');
    const stopLine = document.createElement('p');
    stopLine.className = 'working-stopped';
    stopLine.setAttribute('aria-hidden', 'true');
    container.append(said, word, stopLine);

    const memory = (turnId && turnMemory.get(turnId)) || {
      started: Date.now(), stage: 'reading', label: '', plain: false, seen: new Set(),
      shown: null, shownAt: 0,
    };
    if (turnId && !turnMemory.has(turnId)) {
      turnMemory.set(turnId, memory);
      if (turnMemory.size > 20) turnMemory.delete(turnMemory.keys().next().value);
    }
    const still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let bag = [];
    let bagStage = null;
    let stopped = false;
    let stream = null;
    let poll = null;
    let timer = null;
    let failures = 0;

    // The next word, from the stage the work has reached. A stage change
    // waits for the next thirty-second turn; it never swaps the word early.
    function next() {
      if (bagStage !== memory.stage || !bag.length) {
        bag = shuffled(WORDS[memory.stage] || WORDS.reading);
        bagStage = memory.stage;
        if (bag.length > 1 && bag[0] === memory.shown) bag.push(bag.shift());
      }
      memory.shown = bag.shift();
      memory.shownAt = Date.now();
      render();
      if (!still && !memory.plain) {
        word.classList.remove('fresh');
        void word.offsetWidth;
        word.classList.add('fresh');
      }
    }
    function render() {
      // Owner, 28 September 2026: the word alone, in the continuous whatever
      // its language -- "ing" on the word, nothing beside it.
      word.textContent = memory.shown ? `${memory.shown[0]}ing…` : '';
      word.hidden = memory.plain;
      stopLine.textContent = memory.plain ? memory.label : '';
      stopLine.hidden = !memory.plain;
    }
    function schedule() {
      const due = memory.shownAt + WORD_EVERY_MS - Date.now();
      timer = setTimeout(() => {
        timer = null;
        if (!alive()) { stop(); return; }
        if (!memory.plain) next();
        schedule();
      }, Math.max(0, due));
    }
    const alive = () => !stopped && container.isConnected && isCurrent();
    function closeStream() {
      if (stream) { stream.close(); streams.delete(stream); stream = null; }
    }
    function stop() {
      stopped = true;
      clearTimeout(timer);
      clearTimeout(poll);
      closeStream();
      watchers.delete(handle);
    }
    function apply(row) {
      if (!row || typeof row.label !== 'string' || row.working_not_advice !== true
          || typeof row.cursor !== 'string' || !CURSOR.test(row.cursor)
          || memory.seen.has(row.cursor)) return;
      memory.seen.add(row.cursor);
      memory.label = row.label;
      memory.plain = row.state === 'stopped' || PLAIN_STAGES.has(row.label);
      const staged = STAGE_WORDS.get(row.label);
      if (staged) memory.stage = staged;
      render();
    }
    const base = matterId && turnId
      ? `/api/matters/${encodeURIComponent(matterId)}/loops/${encodeURIComponent(turnId)}`
      : null;
    async function look() {
      poll = null;
      if (!alive() || !base) return;
      try {
        const record = await read(base);
        if (!alive()) return;
        if (!record || !Array.isArray(record.events)) throw new Error('unverified');
        failures = 0;
        record.events.forEach(apply);
        if (record.terminal || typeof record.cursor !== 'string') return;
        stream = new EventSource(`${base}/progress?after=${encodeURIComponent(record.cursor)}`,
                                 { withCredentials: true });
        streams.add(stream);
        stream.addEventListener('progress', (event) => {
          if (!alive()) { stop(); return; }
          try { apply(JSON.parse(event.data)); } catch { closeStream(); }
        });
        stream.onerror = () => {
          closeStream();
          if (alive()) poll = setTimeout(look, 1000);
        };
      } catch (error) {
        if (error?.obsolete || !alive()) return;
        // The work record appears once the loop starts; until then this is a
        // 404 and the words stay on the brief. Other failures stop following
        // after a few tries -- the words carry on at the stage last recorded.
        if (error?.status !== 404 && ++failures >= 3) return;
        poll = setTimeout(look, Date.now() - memory.started < 20000 ? 2000 : 5000);
      }
    }
    const handle = { stop };
    watchers.add(handle);
    // A repaint keeps the word already showing until its thirty seconds are up.
    if (memory.shown && Date.now() - memory.shownAt < WORD_EVERY_MS) render();
    else next();
    schedule();
    look();
    return handle;
  }

  window.NMLoopProgress = Object.freeze({ stopAll, working });
})();
