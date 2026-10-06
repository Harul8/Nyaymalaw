#!/usr/bin/env python3
"""Package completed, frozen offline NM evidence; stdlib only, no tests or providers.

Required commands JSON records the actual expanded argv, cwd, NM_PARTIAL_RUN
and exit code for the subset and pressure invocations. Do not reconstruct a
historical command and label it captured. This script rejects stale/incomplete
inputs. Output must be a fresh directory under /tmp.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET


def fail(message):
    raise ValueError(message)


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def digest_file(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def json_digest(value):
    return digest_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                  separators=(',', ':')).encode())


def read_json(path):
    return json.loads(path.read_text())


def read_manifest(path):
    values = [line.strip() for line in path.read_text().splitlines() if line.strip()]
    if not values or len(values) != len(set(values)):
        fail(f'{path}: require nonempty distinct manifest entries')
    return values


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def junit_identity(node):
    # Pytest parameter IDs can contain ::; only the pre-parameter path
    # separates module/class/function owners.
    base, bracket, parameter = node.partition('[')
    parts = base.split('::')
    return (parts[0].removesuffix('.py').replace('/', '.') +
            ('.' + '.'.join(parts[1:-1]) if len(parts) > 2 else ''),
            parts[-1] + bracket + parameter)


def parse_junit(path, nodes, *, pressure=False):
    selected = set(nodes)
    identities = {}
    for node in nodes:
        key = junit_identity(node)
        if key in identities:
            fail('JUnit identity is ambiguous in the selected manifest')
        identities[key] = node
    outcomes, details = {}, []
    root = ET.parse(path).getroot()
    for case in root.iter('testcase'):
        props = [item.get('value') for item in case.findall('properties/property')
                 if item.get('name') == 'pressure_test_nodeid']
        if pressure:
            if len(props) != 1:
                fail(f'{path}: each pressure JUnit case needs one exact node owner')
            node = props[0]
        else:
            node = identities.get((case.get('classname'), case.get('name')))
        if node not in selected or node in outcomes:
            fail(f'{path}: missing, unselected, or duplicate JUnit node owner')
        errors, failures, skipped = (list(case.iter(tag)) for tag in ('error', 'failure', 'skipped'))
        if sum(bool(items) for items in (errors, failures, skipped)) > 1:
            fail(f'{path}: contradictory JUnit outcome for {node}')
        if errors:
            outcome, element = 'errored', errors[0]
        elif failures:
            outcome, element = 'failed', failures[0]
        elif skipped:
            if len(skipped) != 1:
                fail(f'{path}: duplicate skipped outcomes')
            element = skipped[0]
            outcome = 'xfailed' if element.get('type') == 'pytest.xfail' else 'skipped'
        else:
            outcome, element = 'passed', None
        outcomes[node] = outcome
        details.append({'test_nodeid': node, 'outcome': outcome,
                        'message': element.get('message', '') if element is not None else ''})
    if set(outcomes) != selected:
        fail(f'{path}: selected and executed nodes differ')
    return outcomes, details


def verify_commands(commands):
    # The root runner records one shared cwd/environment and expanded argv
    # arrays. Also support callers that store those fields per invocation.
    normalized = {}
    for label in ('subset', 'pressure'):
        row = commands.get(label)
        if isinstance(row, list):
            row = {'argv': row, 'cwd': commands.get('cwd'),
                   'env': commands.get('environment'),
                   'exit_code': commands.get(label + '_exit_code')}
        if (not isinstance(row, dict) or not isinstance(row.get('argv'), list)
                or not row['argv'] or any(not isinstance(value, str) for value in row['argv'])
                or not isinstance(row.get('cwd'), str) or not row['cwd']
                or not isinstance(row.get('env'), dict)
                or any(not isinstance(k, str) or not isinstance(v, str)
                       for k, v in row['env'].items())
                or row['env'].get('NM_PARTIAL_RUN') != '1'
                or type(row.get('exit_code')) is not int):
            fail(f'commands.{label}: require captured actual argv/cwd/env/exit_code')
        normalized[label] = row
    if normalized['pressure']['exit_code'] != 0:
        fail('The pressure runner did not finish successfully')
    return normalized


def verify_pinned_commit(repo, head, report, subset_audit):
    committed = subprocess.run(['git', 'rev-parse', head + '^{commit}'], cwd=repo,
                               text=True, capture_output=True, check=True).stdout.strip()
    if committed != head:
        fail('frozen-head must be the complete exact commit ID')
    pins = {}
    for group in ('production_source_hashes', 'test_source_hashes'):
        for relative, expected in report[group].items():
            if relative in pins and pins[relative] != expected:
                fail('Conflicting frozen source hash')
            pins[relative] = expected
    for relative, expected in subset_audit.get('selected_module_source_hashes', {}).items():
        if relative in pins and pins[relative] != expected:
            fail('Subset and pressure source hashes differ')
        pins[relative] = expected
    for relative, expected in pins.items():
        if not relative or relative.startswith('/') or '..' in Path(relative).parts:
            fail('A pinned source path is outside the repository')
        result = subprocess.run(['git', 'show', f'{head}:{relative}'], cwd=repo,
                                capture_output=True, check=True)
        if digest_bytes(result.stdout) != expected:
            fail(f'Frozen commit source differs from captured evidence: {relative}')
    return len(pins)


def package(args):
    destination = args.output.resolve()
    if not destination.is_relative_to(Path('/tmp')) or destination == Path('/tmp'):
        fail('Evidence package output must be a new directory under /tmp')
    if destination.exists():
        fail('Use a fresh package directory; completed artifacts are preserved')
    if not re.fullmatch(r'[0-9a-f]{40}', args.frozen_head):
        fail('frozen-head must be a complete lowercase 40-character commit ID')
    pressure_dir = args.pressure_output.resolve()
    observation_path = pressure_dir / 'observations.json'
    report = read_json(observation_path)
    prompt = read_json(args.prompt_inventory)
    audit = read_json(args.subset_audit)
    commands = read_json(args.commands_json)
    normalized_commands = verify_commands(commands)
    if commands.get('frozen_head', args.frozen_head) != args.frozen_head:
        fail('Captured command log belongs to another frozen head')
    for label, stamped in (('pressure', report.get('tested_head')),
                           ('subset', audit.get('tested_head')),
                           ('prompt inventory', prompt.get('current_head'))):
        if stamped != args.frozen_head:
            fail(f'{label} belongs to a different head; refresh it after freezing code')
    if report.get('live_model_calls') != 0 or report.get('browser_calls') != 0:
        fail('This package is restricted to offline, no-provider/no-browser evidence')
    if (digest_file(pressure_dir / 'nm_pressure_evidence_owner.py')
            != report.get('evidence_owner_sha256')):
        fail('The recorded pressure evidence owner plugin changed')
    modules = read_manifest(args.subset_modules)
    nodes = read_manifest(args.subset_nodeids)
    if any(not module.startswith('tests/') or not module.endswith('.py') for module in modules):
        fail('Only selected repository test modules belong in the subset manifest')
    if any(node.split('::')[0] not in modules or '::' not in node for node in nodes):
        fail('A collected subset node is outside the selected modules')
    if len(modules) != audit.get('selected_module_count'):
        fail('Subset module count differs from its frozen selection audit')
    if len(nodes) != audit.get('collected_node_count'):
        fail('Subset node count differs from its frozen collection audit')
    if digest_file(args.subset_modules) != audit.get('manifest_sha256'):
        fail('Subset module manifest changed after its frozen audit')
    if audit.get('source_drift_since_collection'):
        fail('Subset audit reports source drift after collection')
    subset_outcomes, subset_details = parse_junit(args.subset_xml, nodes)
    subset_counts = Counter(subset_outcomes.values())
    if subset_counts['skipped']:
        fail('Ordinary skipped subset tests must be qualified explicitly before packaging')
    required_exit = 1 if subset_counts['failed'] or subset_counts['errored'] else 0
    if normalized_commands['subset']['exit_code'] != required_exit:
        fail('Captured subset exit code differs from its completed JUnit outcomes')
    baseline = read_json(args.baseline_failures_json) if args.baseline_failures_json else []
    baseline_keys = {(row['class'], row['name']) for row in baseline}
    baseline_failed = [row for row in subset_details
                       if row['outcome'] in ('failed', 'errored')
                       and junit_identity(row['test_nodeid']) in baseline_keys]
    unresolved_failed = [row for row in subset_details
                         if row['outcome'] in ('failed', 'errored')
                         and junit_identity(row['test_nodeid']) not in baseline_keys]
    cases = report.get('cases')
    if not isinstance(cases, list) or not cases:
        fail('Pressure observations contain no paired cases')
    case_nodes = [row.get('test_nodeid') for row in cases]
    case_ids = [row.get('case_id') for row in cases]
    if (any(not isinstance(value, str) or not value for value in [*case_nodes, *case_ids])
            or len(set(case_nodes)) != len(case_nodes) or len(set(case_ids)) != len(case_ids)):
        fail('Pressure cases must have distinct nonempty case and executed node IDs')
    if len(cases) != report.get('distinct_cases') or len(cases) != report.get('distinct_tests'):
        fail('Pressure distinct counts differ from recorded case ownership')
    source_collection = (pressure_dir / 'collection.log').read_text().splitlines()
    collected_pressure = [line for line in source_collection
                          if any(line.startswith(path + '::')
                                 for path in report['selected_test_files'])]
    if set(collected_pressure) != set(case_nodes) or len(collected_pressure) != len(case_nodes):
        fail('Pressure collection and case ownership differ')
    rounds, per_round_outcomes, round_case_files = [], [], {}
    for entry in report.get('rounds', []):
        label = entry.get('round')
        if not isinstance(label, str) or not re.fullmatch(r'round-[1-9][0-9]*', label):
            fail('Invalid pressure round name')
        directory = pressure_dir / label
        xml_path, log_path = directory / 'results.xml', directory / 'pytest.log'
        if (digest_file(xml_path) != entry.get('junit_sha256')
                or digest_file(log_path) != entry.get('log_sha256')):
            fail(f'{label}: original XML/log differs from recorded pressure hashes')
        outcomes, details = parse_junit(xml_path, case_nodes, pressure=True)
        counts = Counter(outcomes.values())
        if any(counts[key] for key in ('failed', 'errored', 'skipped')):
            fail(f'{label}: pressure contains an ordinary failure/error/skip')
        qualified_counts = {'passed': counts['passed'], 'xfailed': counts['xfailed']}
        if qualified_counts != entry.get('pytest_outcome_counts'):
            fail(f'{label}: executed outcomes differ from reported counts')
        if entry.get('test_count') != len(cases) or entry.get('case_count') != len(cases):
            fail(f'{label}: test/case counts do not match exact selected owners')
        observed_ids = [row['case_id'] for row in entry.get('observed_cases', [])]
        if set(observed_ids) != set(case_ids) or len(observed_ids) != len(case_ids):
            fail(f'{label}: observed case summary ownership differs')
        stored = sorted((directory / 'cases').glob('*.json'))
        if len(stored) != len(cases):
            fail(f'{label}: raw paired case population differs')
        original = {row['case_id']: row for row in cases}
        raw_identities = []
        for path in stored:
            row = read_json(path)
            raw_identities.append(row.get('case_id'))
            if row.get('case_id') not in original:
                fail(f'{label}: raw case has an unowned identity')
            previous = original[row['case_id']]
            # Full public response/storage captures contain genuine timestamps.
            # Compare the same semantic evidence fields as the frozen runner;
            # retain every complete capture losslessly in a per-round archive.
            for field in ('test_nodeid', 'user_passage', 'fabricated_model_outputs',
                          'expected', 'observed', 'expectation_met', 'claim_scope',
                          'protection_status'):
                if row.get(field) != previous.get(field):
                    fail(f'{label}: order-dependent paired evidence field {field}')
        if set(raw_identities) != set(case_ids) or len(set(raw_identities)) != len(cases):
            fail(f'{label}: individual raw cases have missing or duplicate owners')
        for observed in entry['observed_cases']:
            previous = original[observed['case_id']]
            if (observed.get('observed') != previous['observed']
                    or observed.get('fabricated_dispatches') != len(previous['calls'])):
                fail(f'{label}: round observation summary differs from its original case')
        round_case_files[label] = stored
        per_round_outcomes.append(outcomes)
        rounds.append({key: value for key, value in entry.items()
                       if key not in ('cases', 'observed_cases')})
    if not rounds or len({row['round'] for row in rounds}) != len(rounds):
        fail('Require distinct completed pressure rounds')
    if any(outcomes != per_round_outcomes[0] for outcomes in per_round_outcomes[1:]):
        fail('Pressure test outcomes changed with execution order')
    open_cases, proposal_cases, manifest = [], [], []
    for row in cases:
        outcome = per_round_outcomes[0][row['test_nodeid']]
        if (type(row.get('expectation_met')) is not bool
                or row['expectation_met'] != (row.get('expected') == row.get('observed'))
                or not row.get('user_passage') or not row.get('fabricated_model_outputs')
                or row.get('live_model_calls') != 0):
            fail('A pressure case lacks actual paired inputs or truthful observed expectation')
        if outcome == 'xfailed':
            if (row.get('protection_status') != 'open_semantic_defect'
                    or row.get('claim_scope') != 'semantic_dependency' or row['expectation_met']):
                fail('Expected failure must remain an unmet typed semantic desired rule')
            qualification = 'open_semantic_desired_rule_xfail'
            open_cases.append(row['case_id'])
        elif row.get('protection_status') == 'gap_demonstrated':
            if row.get('claim_scope') != 'semantic_dependency' or not row['expectation_met']:
                fail('Proposal-only characterization must identify its semantic limitation')
            qualification = 'proposal_boundary_characterization_not_prevention'
            proposal_cases.append(row['case_id'])
        else:
            if not row['expectation_met'] or row.get('protection_status') == 'open_semantic_defect':
                fail('Passed cases cannot hide unmet semantic desired rules')
            qualification = 'passed_scoped_offline_check'
        manifest.append({
            **{key: row.get(key) for key in ('case_id', 'test_nodeid', 'boundary', 'scenario',
                'claim_scope', 'protection_status', 'expectation_met', 'notes')},
            'pytest_outcome': outcome, 'evidence_qualification': qualification,
            'fabricated_dispatches': len(row.get('calls', [])),
            **{key + '_sha256': json_digest(row[key]) for key in (
                'user_passage', 'fabricated_model_outputs', 'expected', 'observed')},
        })
    if len(open_cases) != args.expected_semantic_xfails:
        fail('Open semantic xfail population changed; review desired rules before updating expectation')
    if len(proposal_cases) != args.expected_proposal_characterizations:
        fail('Proposal-only characterization population changed; review claim qualification')
    distinct_counts = {'passed': len(cases) - len(open_cases), 'xfailed': len(open_cases)}
    total_counts = {key: value * len(rounds) for key, value in distinct_counts.items()}
    for field, expected in (
            ('distinct_pytest_outcome_counts', distinct_counts),
            ('total_pytest_outcome_counts', total_counts),
            ('total_test_executions', len(cases) * len(rounds)),
            ('scenario_counts', dict(Counter(row['scenario'] for row in cases))),
            ('claim_scope_counts', dict(Counter(row['claim_scope'] for row in cases))),
            ('protection_status_counts', dict(Counter(row['protection_status'] for row in cases)))):
        if report.get(field) != expected:
            fail(f'Pressure report count is inconsistent: {field}')
    pinned_count = verify_pinned_commit(args.repo.resolve(), args.frozen_head, report, audit)
    destination.mkdir(parents=True)
    artifacts = destination / 'artifacts'
    artifacts.mkdir()
    for source, name in ((args.subset_modules, 'subset-modules.txt'),
                         (args.subset_nodeids, 'subset-nodeids.txt'),
                         (args.subset_xml, 'subset-results.xml'),
                         (args.subset_log, 'subset-pytest.log'),
                         (args.subset_audit, 'subset-selection-audit.json'),
                         (args.prompt_inventory, 'prompt-inventory.json'),
                         (args.commands_json, 'commands.json'),
                         (Path(__file__).resolve(), 'evidence-packager.py'),
                         (pressure_dir / 'collection.log', 'pressure-collection.log'),
                         (pressure_dir / 'nm_pressure_evidence_owner.py', 'pressure-evidence-owner.py')):
        shutil.copyfile(source, artifacts / name)
    if args.baseline_failures_json:
        shutil.copyfile(args.baseline_failures_json, artifacts / 'baseline-failure-identities.json')
    for entry in rounds:
        label = entry['round']
        target = artifacts / label
        target.mkdir()
        for name in ('results.xml', 'pytest.log'):
            shutil.copyfile(pressure_dir / label / name, target / name)
        archive = target / 'cases.tar.gz'
        with archive.open('wb') as raw:
            with gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0,
                               compresslevel=9) as compressed_cases:
                with tarfile.open(fileobj=compressed_cases, mode='w|') as bundled:
                    for path in round_case_files[label]:
                        entry = tarfile.TarInfo(path.name)
                        entry.size, entry.mode, entry.mtime = path.stat().st_size, 0o644, 0
                        with path.open('rb') as body:
                            bundled.addfile(entry, body)
    compressed = artifacts / 'observations.json.gz'
    with observation_path.open('rb') as original, compressed.open('wb') as raw:
        with gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0, compresslevel=9) as output:
            shutil.copyfileobj(original, output, length=1024 * 1024)
    raw_digest, compressed_digest = digest_file(observation_path), digest_file(compressed)
    with gzip.open(compressed, 'rb') as original:
        if hashlib.file_digest(original, 'sha256').hexdigest() != raw_digest:
            fail('Compressed full observations do not restore the original bytes')
    summary = {
        'contract': 'nm_offline_evidence_package_v1', 'frozen_head': args.frozen_head,
        'packaged_utc': datetime.now(timezone.utc).isoformat(),
        'qualification_status': ('subset_has_failures' if required_exit else 'offline_checks_completed'),
        'subset': {'selected_modules': len(modules), 'collected_executed_nodes': len(nodes),
                   'pytest_outcome_counts': dict(subset_counts),
                   'failure_identities_matching_archived_baseline': len(baseline_failed),
                   'failures_without_supplied_baseline_match': len(unresolved_failed),
                   'baseline_matching_is_identity_only_not_reverification': True,
                   'failed_tests': [row['test_nodeid'] for row in subset_details
                                    if row['outcome'] in ('failed', 'errored')]},
        'pressure': {'distinct_cases': len(cases), 'rounds': rounds,
                     'distinct_pytest_outcome_counts': distinct_counts,
                     'total_pytest_outcome_counts': total_counts,
                     'total_test_executions': len(cases) * len(rounds),
                     'passed_case_count_excluding_proposal_only_characterizations':
                         distinct_counts['passed'] - len(proposal_cases),
                     'strict_semantic_desired_rule_xfails': open_cases,
                     'proposal_boundary_characterizations_not_prevention': proposal_cases,
                     'scenario_counts': report['scenario_counts'],
                     'claim_scope_counts': report['claim_scope_counts'],
                     'protection_status_counts': report['protection_status_counts']},
        'prompt_inventory': {'baseline': prompt.get('baseline'),
                             'baseline_words': prompt.get('baseline_words'),
                             'current_words': prompt.get('current_words'),
                             'change_percent': prompt.get('change_percent'),
                             'method': prompt.get('method')},
        'live_model_calls': 0, 'browser_calls': 0,
        'false_acceptance_rate': 'not_established', 'false_rejection_rate': 'not_established',
        'model_semantic_accuracy': 'not_established', 'dispatch_token_cost': 'not_established',
        'production_latency': 'not_established',
        'full_observations': {'compressed_artifact': 'artifacts/observations.json.gz',
                             'original_bytes': observation_path.stat().st_size,
                             'original_sha256': raw_digest,
                             'compressed_bytes': compressed.stat().st_size,
                             'compressed_sha256': compressed_digest},
    }
    write_json(destination / 'summary.json', summary)
    write_json(destination / 'case-manifest.json', manifest)
    write_json(destination / 'provenance.json', {
        'frozen_head': args.frozen_head, 'original_pressure_output': str(pressure_dir),
        'pressure_started_utc': report['started_utc'], 'pressure_finished_utc': report['finished_utc'],
        'production_source_hashes': report['production_source_hashes'],
        'test_source_hashes': report['test_source_hashes'],
        'selected_pressure_test_files': report['selected_test_files'],
        'additional_pinned_sources': report['additional_source_files'],
        'verified_frozen_commit_pins': pinned_count,
        'evidence_owner_sha256': report['evidence_owner_sha256'],
        'input_artifact_hashes': {str(path.resolve()): digest_file(path) for path in (
            observation_path, args.subset_modules, args.subset_nodeids, args.subset_xml,
            args.subset_log, args.subset_audit, args.prompt_inventory, args.commands_json)},
        'round_case_source_hashes': {label: {path.name: digest_file(path) for path in paths}
                                     for label, paths in round_case_files.items()},
        'packager_sha256': digest_file(Path(__file__).resolve()),
    })
    (destination / 'METHOD.md').write_text(
        '# Offline evidence method\n\n'
        'The frozen commit and every pinned source are verified against Git objects. '
        'The selected subset modules and collected nodes bind exactly to executed JUnit cases. '
        'The subset remains a focused selection; failures are reported, never hidden. '
        'An archived baseline match identifies the same test, and is not a fresh baseline verification.\n\n'
        'Pressure cases bind one-to-one to collected nodes, actual per-round JUnit outcomes '
        f'and complete paired input/output observations. {len(open_cases)} known semantic desired-rule '
        f'failures are counted separately as expected failures; {len(proposal_cases)} passing extractor '
        'characterizations document proposal boundaries, not release defects prevented. '
        'The counts are validated against configurable expected populations. '
        'Full raw observations are retained only as lossless deterministic gzip plus both SHA-256 values.\n\n'
        'All complete per-round case files, including public response/storage captures '
        'whose timestamps differ across rounds, are retained in per-round cases.tar.gz '
        'archives with individual original hashes in provenance.json.\n\n'
        'Inputs are curated repository golden passages/composites and fabricated model outputs. '
        'Typed fixture support declarations and semantic judgments are authored by tests. '
        'Repeating forward, reverse and seeded orders checks deterministic behavior/isolation, '
        'not additional scenarios. No real model or browser is called. No population false '
        'acceptance/rejection rate, semantic accuracy, dispatch tokens or production latency '
        'is established. Prompt word counts use the supplied documented static method.\n\n'
        'Exact expanded invocations and captured exit codes are in artifacts/commands.json. '
        'The full observations and every round XML/log remain available for audit. '
        'The package is temporary until archived outside /tmp; no Git commit of the raw text '
        'is required or recommended.\n')
    files = sorted(path for path in destination.rglob('*') if path.is_file())
    (destination / 'SHA256SUMS').write_text(''.join(
        digest_file(path) + '  ' + path.relative_to(destination).as_posix() + '\n' for path in files))
    print(json.dumps({'output': str(destination), 'subset_outcomes': dict(subset_counts),
                      'pressure_distinct_outcomes': distinct_counts,
                      'proposal_only_characterizations': len(proposal_cases),
                      'compressed_observations_bytes': compressed.stat().st_size}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pressure-output', 'subset-modules', 'subset-nodeids', 'subset-xml',
                 'subset-log', 'subset-audit', 'prompt-inventory', 'commands-json', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--frozen-head', required=True)
    parser.add_argument('--repo', type=Path, default=Path('/workspace/Nyaymalaw'))
    parser.add_argument('--baseline-failures-json', type=Path)
    parser.add_argument('--expected-semantic-xfails', type=int, default=4)
    parser.add_argument('--expected-proposal-characterizations', type=int, default=2)
    args = parser.parse_args()
    try:
        package(args)
    except (ValueError, KeyError, OSError, ET.ParseError, subprocess.CalledProcessError) as exc:
        print(f'Evidence packaging refused: {exc}', file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == '__main__':
    main()
