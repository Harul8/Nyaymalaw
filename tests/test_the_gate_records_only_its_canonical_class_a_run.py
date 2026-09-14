"""One canonical execution, not a second run or an inherited output lease."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from assurance.control_plane import evidence
from assurance.control_plane.evidence import CLASS_A_PYTEST_ARGS, ORDINARY_PYTEST_ARGS
from assurance.gate import check

pytestmark = pytest.mark.class_a


@pytest.fixture
def recorded(tmp_path, monkeypatch):
    target = tmp_path / 'canonical.json'
    monkeypatch.setattr(check, 'LOCAL_CLASS_A', target)
    monkeypatch.setenv('NM_CLASS_A_EVIDENCE_FILE', str(tmp_path / 'inherited.json'))
    return target


def test_canonical_step_removes_old_artifact_and_records_and_verifies_new_one(
    recorded, monkeypatch,
):
    recorded.write_text('old result', encoding='utf-8')
    calls = []

    def run(cmd, **kwargs):
        assert not recorded.exists()
        assert kwargs['env']['NM_CLASS_A_EVIDENCE_FILE'] == str(recorded)
        calls.append(cmd)
        recorded.write_text(json.dumps({'new': True}), encoding='utf-8')
        return subprocess.CompletedProcess(cmd, 0, 'one execution', '')

    verified = []
    monkeypatch.setattr(check.subprocess, 'run', run)
    monkeypatch.setattr(check, 'validate_class_a', lambda value: verified.append(value) or [])
    cmd = [sys.executable, '-m', 'pytest', *CLASS_A_PYTEST_ARGS]
    assert check.step('canonical', cmd) == (True, 'one execution')
    assert calls == [cmd]
    assert verified == [{'new': True}]


@pytest.mark.parametrize('tail', [list(ORDINARY_PYTEST_ARGS),
                                [*CLASS_A_PYTEST_ARGS, '-k', 'one_test']])
def test_other_selections_cannot_overwrite_the_canonical_artifact(
    recorded, monkeypatch, tail,
):
    recorded.write_text('preserve canonical result', encoding='utf-8')

    def run(cmd, **kwargs):
        assert 'NM_CLASS_A_EVIDENCE_FILE' not in kwargs['env']
        return subprocess.CompletedProcess(cmd, 0, 'ordinary', '')

    monkeypatch.setattr(check.subprocess, 'run', run)
    assert check.step('not canonical', [sys.executable, '-m', 'pytest', *tail])[0]
    assert recorded.read_text(encoding='utf-8') == 'preserve canonical result'


@pytest.mark.parametrize('failure', ['missing', 'partial', 'stale', 'failed node'])
def test_zero_exit_cannot_substitute_for_valid_canonical_evidence(
    recorded, monkeypatch, failure,
):
    def run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, 'claimed green', '')

    monkeypatch.setattr(check.subprocess, 'run', run)
    monkeypatch.setattr(check, 'validate_class_a', lambda value: [failure])
    ok, output = check.step('canonical', [sys.executable, '-m', 'pytest', *CLASS_A_PYTEST_ARGS])
    assert not ok
    assert f'ERROR: Class-A evidence: {failure}' in output


def test_failed_canonical_run_cannot_retain_an_old_pass(recorded, monkeypatch):
    recorded.write_text('old PASS', encoding='utf-8')
    monkeypatch.setattr(check.subprocess, 'run',
                        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 1, 'FAILED', ''))
    assert not check.step('canonical', [sys.executable, '-m', 'pytest', *CLASS_A_PYTEST_ARGS])[0]
    assert not recorded.exists()


def test_one_child_environment_owner_removes_only_the_canonical_selection_override(
    recorded, monkeypatch,
):
    monkeypatch.setenv('PYTEST_ADDOPTS', '-k only_one')
    monkeypatch.setenv('KEEP_THIS_SETTING', 'yes')
    canonical = evidence.child_environment(class_a_output=recorded)
    assert 'PYTEST_ADDOPTS' not in canonical
    assert canonical['NM_CLASS_A_EVIDENCE_FILE'] == str(recorded)
    assert canonical['KEEP_THIS_SETTING'] == 'yes'
    ordinary = evidence.child_environment()
    assert ordinary['PYTEST_ADDOPTS'] == '-k only_one'
    assert 'NM_CLASS_A_EVIDENCE_FILE' not in ordinary


def test_both_canonical_runners_use_the_real_shared_environment_owner(
    recorded, monkeypatch,
):
    monkeypatch.setenv('PYTEST_ADDOPTS', '--deselect tests/test_one.py::test_one')
    monkeypatch.setattr(evidence, 'LOCAL_CLASS_A', recorded)
    calls = []

    def run(cmd, **kwargs):
        assert 'PYTEST_ADDOPTS' not in kwargs['env']
        assert kwargs['env']['NM_CLASS_A_EVIDENCE_FILE'] == str(recorded)
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 1, 'failed fixture execution', '')

    monkeypatch.setattr(check.subprocess, 'run', run)
    assert not check.step('canonical', [sys.executable, '-m', 'pytest',
                                        *CLASS_A_PYTEST_ARGS])[0]
    assert evidence.run_class_a() == 1
    assert calls == [[sys.executable, '-m', 'pytest', *CLASS_A_PYTEST_ARGS]] * 2


@pytest.fixture
def actual_config(tmp_path, monkeypatch):
    """Parse real pytest configuration without collecting/running this repo.

    Config.fromdictargs disables addopts, so it would recreate the very blind
    spot being tested. Config.parse uses the normal environment/ini parser.
    No child pytest or model is started, and no fixture output is published.
    """
    from _pytest.config import get_config

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('PYTEST_DISABLE_PLUGIN_AUTOLOAD', '1')
    monkeypatch.delenv('PYTEST_ADDOPTS', raising=False)
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'test_one.py').write_text(
        'def test_one():\n    pass\n', encoding='utf-8')
    configs = []

    def parse(*, environment='', ini='-q', argv=CLASS_A_PYTEST_ARGS):
        monkeypatch.setenv('PYTEST_ADDOPTS', environment)
        (tmp_path / 'pytest.ini').write_text(
            '[pytest]\ntestpaths = tests\naddopts = ' + ini + '\n', encoding='utf-8')
        config = get_config(list(argv))
        configs.append(config)
        config.parse(list(argv))
        return config

    yield parse
    for config in reversed(configs):
        config._ensure_unconfigure()


def _isolated_recorder():
    """Meta-controls never install/reset the actual outer recorder's globals."""
    spec = importlib.util.spec_from_file_location(
        '_selection_recorder_fixture', Path(__file__).with_name('conftest.py'))
    recorder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recorder)
    return recorder


def _record_selection(config, target, monkeypatch):
    """Run the actual recorder over an explicitly simulated passed report.

    The passing outcome is fixture input, not an execution claim. This check
    concerns whether the real recorder can label that fixture as a complete
    run under actual narrowed pytest configuration.
    """
    # A separate module is essential: replacing the outer runner's globals
    # during this test would discard this test's own call-phase result before
    # monkeypatch restored them, shrinking the evidence being certified.
    recorder = _isolated_recorder()

    monkeypatch.setenv('NM_CLASS_A_EVIDENCE_FILE', str(target))
    monkeypatch.setattr(evidence, 'verification_fingerprint', lambda *args: 'fixture-tree')
    monkeypatch.setattr(evidence, 'git_identity', lambda: 'fixture-not-a-real-run')
    monkeypatch.setattr(recorder, '_ran', set())
    monkeypatch.setattr(recorder, '_class_a', {
        'tests/test_one.py::test_one': {'outcome': 'passed', 'duration_ms': 1},
    })
    monkeypatch.setattr(recorder, '_class_a_full_selection', False)
    monkeypatch.setattr(recorder, '_class_a_start_fingerprint', '')
    monkeypatch.setattr(recorder, '_class_a_selection_problems', [])
    recorder.pytest_configure(config)
    recorder.pytest_sessionfinish(SimpleNamespace(config=config), 0)
    return evidence.load_result(target)


def _report_to(recorder, *, when, duration):
    """Feed an explicitly synthetic report through the real hook wrapper."""
    item = SimpleNamespace(nodeid='tests/test_fixture.py::test_fixture',
                           get_closest_marker=lambda name: object() if name == 'class_a' else None)
    report = SimpleNamespace(when=when, duration=duration, passed=True, failed=False, skipped=False)
    hook = recorder.pytest_runtest_makereport(item, None)
    next(hook)
    with pytest.raises(StopIteration):
        hook.send(SimpleNamespace(get_result=lambda: report))


@pytest.mark.parametrize('mutation', ['remove', 'replace'])
def test_configured_output_lease_survives_application_environment_changes(
    actual_config, tmp_path, monkeypatch, mutation,
):
    """No missing call-phase result and no redirect to a later ambient path."""
    config = actual_config()
    recorder = _isolated_recorder()
    target, hijacked = tmp_path / 'configured.json', tmp_path / 'later-environment.json'
    monkeypatch.setenv('NM_CLASS_A_EVIDENCE_FILE', str(target))
    monkeypatch.setattr(evidence, 'verification_fingerprint', lambda *args: 'fixture-tree')
    monkeypatch.setattr(evidence, 'git_identity', lambda: 'fixture-not-a-real-run')
    recorder.pytest_configure(config)
    if mutation == 'remove':
        monkeypatch.delenv('NM_CLASS_A_EVIDENCE_FILE')
    else:
        monkeypatch.setenv('NM_CLASS_A_EVIDENCE_FILE', str(hijacked))
    for when, duration in [('setup', .1), ('call', .2), ('teardown', .3)]:
        _report_to(recorder, when=when, duration=duration)
    recorder.pytest_sessionfinish(SimpleNamespace(config=config), 0)
    assert target.is_file() and not hijacked.exists()
    result = evidence.load_result(target)
    assert result['complete'] is True and result['selection'] == 'full_class_a'
    assert result['tests'] == {
        'tests/test_fixture.py::test_fixture': {'outcome': 'passed', 'duration_ms': 600.0}}


def test_a_session_without_a_configured_lease_cannot_acquire_one_mid_run(
    actual_config, tmp_path, monkeypatch,
):
    config = actual_config()
    recorder = _isolated_recorder()
    monkeypatch.delenv('NM_CLASS_A_EVIDENCE_FILE', raising=False)
    recorder.pytest_configure(config)
    hijacked = tmp_path / 'not-owned.json'
    monkeypatch.setenv('NM_CLASS_A_EVIDENCE_FILE', str(hijacked))
    _report_to(recorder, when='call', duration=.2)
    recorder.pytest_sessionfinish(SimpleNamespace(config=config), 0)
    assert recorder._class_a == {} and not hijacked.exists()


@pytest.mark.parametrize(('source', 'options', 'diagnostic'), [
    ('environment', '-k test_one', 'keyword'),
    ('ini', '--deselect tests/test_one.py::test_one', 'deselect'),
    ('environment', '--ignore tests/test_one.py', 'ignore'),
    ('ini', '--ignore-glob tests/ignored*', 'ignore_glob'),
    ('environment', '--lf', 'lf'),
    ('ini', '--sw', 'stepwise'),
    ('environment', 'tests/test_one.py', 'collection roots'),
    ('ini', '-o testpaths=tests/test_one.py', 'testpaths'),
    ('environment', '-o python_files=test_one.py', 'python_files'),
    ('ini', '-o python_functions=test_one', 'python_functions'),
    ('environment', '-o norecursedirs=ignored', 'norecursedirs'),
])
def test_effective_narrowing_cannot_be_recorded_as_full_even_with_canonical_argv(
    actual_config, tmp_path, monkeypatch, source, options, diagnostic,
):
    config = actual_config(**{source: options})
    # This is the original false-green condition: original argv still agrees.
    assert tuple(config.invocation_params.args) == CLASS_A_PYTEST_ARGS
    problems = evidence.class_a_selection_problems(config)
    assert any(diagnostic in problem for problem in problems), problems
    result = _record_selection(config, tmp_path / 'partial.json', monkeypatch)
    assert result['tests'] and all(row['outcome'] == 'passed'
                                  for row in result['tests'].values())
    assert result['exit_code'] == 0
    assert result['selection'] == 'partial'
    assert result['complete'] is False
    assert result['selection_problems'] == problems
    assert any('narrowed selection' in problem
               for problem in evidence.validate_class_a(result))


def test_actual_canonical_configuration_keeps_the_positive_recording_path(
    actual_config, tmp_path, monkeypatch,
):
    config = actual_config()
    assert evidence.class_a_selection_problems(config) == []
    result = _record_selection(config, tmp_path / 'positive.json', monkeypatch)
    assert result['selection'] == 'full_class_a'
    assert result['complete'] is True
    assert result['selection_problems'] == []
    assert evidence.validate_class_a(result) == []


def test_effective_marker_override_is_not_the_class_a_population(actual_config):
    config = actual_config(argv=(*CLASS_A_PYTEST_ARGS, '-m', 'class_d'))
    assert config.getoption('markexpr') == 'class_d'
    assert any('effective marker' in problem
               for problem in evidence.class_a_selection_problems(config))


def test_the_actual_recorder_control_bites_when_its_effective_guard_is_bypassed(
    actual_config, tmp_path, monkeypatch,
):
    config = actual_config(environment='-k test_one')

    def require_refusal():
        result = _record_selection(config, tmp_path / 'mutation.json', monkeypatch)
        assert result['selection'] == 'partial', 'narrowed execution was labelled full'

    require_refusal()
    monkeypatch.setattr(evidence, 'class_a_selection_problems', lambda config: [])
    with pytest.raises(AssertionError, match='narrowed execution was labelled full'):
        require_refusal()
