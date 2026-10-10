"""LB-82. The words shown while a reply is prepared follow the recorded stages.

Owner direction, 28 September 2026: legal words from several languages in place
of a fixed "Working on your brief", chosen by the stage the recorded work has
actually reached. The page names the server's stage labels verbatim, so the rule
that keeps them honest is population equality: every label the progress
projection can emit is named by the page -- as a word stage or as a plain stop
-- and the page names no label the server cannot emit. A stage added to the
server tomorrow fails here, not silently in front of an advocate.
"""
import re
from pathlib import Path

from nm.Archives.legal_brain.communicate.loop_progress import label_states

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / 'nm' / 'Archives' / 'legal_brain' / 'communicate' / 'loop-progress.js').read_text(
    encoding='utf8')


def _block(name: str) -> str:
    start = SCRIPT.index(f'const {name} = ')
    end = SCRIPT.index('\n  ]);', start) if 'new ' in SCRIPT[start:start + 40] \
        else SCRIPT.index('\n  };', start)
    return SCRIPT[start:end]


def _staged() -> dict[str, str]:
    return dict(re.findall(r'\["([^"]+)", "(\w+)"\]', _block('STAGE_WORDS')))


def _plain() -> set[str]:
    return set(re.findall(r'^\s+"([^"]+)",$', _block('PLAIN_STAGES'), re.M))


def _words() -> dict[str, list[tuple[str, str, str]]]:
    block = _block('WORDS')
    sets = {}
    for name, body in re.findall(r'^\s{4}(\w+): \[(.*?)^\s{4}\],', block, re.M | re.S):
        sets[name] = re.findall(r'\["([^"]+)", "([^"]+)", "([^"]+)"\]', body)
    return sets


def test_every_label_the_server_can_emit_is_named_exactly_once_by_the_page():
    server = label_states()
    staged, plain = _staged(), _plain()
    assert not set(staged) & plain, 'a label is either decorated or plain, never both'
    assert set(server) == set(staged) | plain, (
        f'unnamed on the page: {sorted(set(server) - set(staged) - plain)}; '
        f'not emitted by the server: {sorted((set(staged) | plain) - set(server))}')


def test_a_stopped_stage_is_never_decorated_with_words():
    stopped = {label for label, state in label_states().items() if state == 'stopped'}
    assert stopped and stopped <= _plain()


def test_every_word_stage_has_words_with_a_language_and_a_meaning():
    words = _words()
    assert 'reading' in words, 'the words before any stage is recorded'
    for stage in set(_staged().values()) | {'reading'}:
        assert words.get(stage), f'no words for the {stage} stage'
    entries = [entry for group in words.values() for entry in group]
    assert all(all(part.strip() for part in entry) for entry in entries)
    assert len({entry[0] for entry in entries}) == len(entries), 'a word appears twice'


def test_the_word_changes_once_every_thirty_seconds():
    """Owner, 28 September 2026: one word every thirty seconds."""
    assert re.search(r'^\s+const WORD_EVERY_MS = 30000;$', SCRIPT, re.M)
    assert 'setInterval' not in SCRIPT[SCRIPT.index('function working('):], (
        'the word keeps its own thirty-second clock across repaints')


def test_screen_readers_hear_one_stable_status_not_every_word():
    assert "said.textContent = 'Working on your brief…'" in SCRIPT
    assert "word.setAttribute('aria-hidden', 'true')" in SCRIPT
    assert "prefers-reduced-motion: reduce" in SCRIPT
