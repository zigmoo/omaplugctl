"""Omarchy's installed agent choices and the CLIs' own model inventories."""
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess

LABELS = {'codex': 'Codex', 'cursor-agent': 'Cursor', 'claude': 'Claude Code', 'opencode': 'OpenCode'}


def option(agent, model='', label='', effort='default'):
    identity = agent + '\n' + model + '\n' + effort
    return {'id': 'native-' + hashlib.sha256(identity.encode()).hexdigest()[:24],
            'group': 'native:' + agent, 'agent': agent, 'agentLabel': LABELS[agent],
            'model': model, 'label': label or 'Configured default model', 'effort': effort,
            'native': True}


def discover(command):
    agents = set(LABELS)
    preferred = ''
    if shutil.which('omarchy'):
        try:
            catalog = json.loads(command(['omarchy', 'commands', '--json']))['commands']
            entry = next(e for e in catalog if e['route'] == 'omarchy default agent')
            agents &= set(entry['args'].strip('[]').split('|'))
            preferred = command(['omarchy', 'default', 'agent'])
        except (RuntimeError, ValueError, KeyError, StopIteration):
            pass  # Older Omarchy releases still work with installed adapters.
    options = []
    errors = []
    for agent in sorted(agents):
        if not shutil.which(agent):
            continue
        options.append(option(agent))
        try:
            if agent == 'codex':
                configured_home = os.environ.get('CODEX_HOME')
                if not configured_home and shutil.which('omarchy-agent-account-home'):
                    configured_home = command(['omarchy-agent-account-home', 'codex'])
                home = pathlib.Path(configured_home or pathlib.Path.home() / '.codex')
                file = home / 'models_cache.json'
                if file.exists() and file.stat().st_size <= 4_000_000:
                    for model in json.loads(file.read_text()).get('models', []):
                        if model.get('visibility') == 'list' and isinstance(model.get('slug'), str):
                            options.append(option(agent, model['slug'], model.get('display_name') or model['slug'],
                                                  model.get('default_reasoning_level') or 'default'))
            elif agent == 'cursor-agent':
                for line in command([agent, '--list-models']).splitlines():
                    match = re.fullmatch(r'([\w./:#-]+) - (.{1,200})', line.strip())
                    if match:
                        options.append(option(agent, match[1], match[2]))
            elif agent == 'opencode':
                for line in command([agent, 'models']).splitlines():
                    model = line.strip()
                    if re.fullmatch(r'[\w.-]+/[\w./:#-]+', model):
                        options.append(option(agent, model, model))
            elif agent == 'claude':
                configured_home = os.environ.get('CLAUDE_CONFIG_DIR')
                if not configured_home and shutil.which('omarchy-agent-account-home'):
                    configured_home = command(['omarchy-agent-account-home', 'claude'])
                file = pathlib.Path(configured_home or pathlib.Path.home() / '.claude') / 'settings.json'
                if file.exists() and file.stat().st_size <= 1_000_000:
                    model = json.loads(file.read_text()).get('model')
                    if isinstance(model, str) and model:
                        options.append(option(agent, model, model))
        except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as exc:
            errors.append(f'{LABELS[agent]} model discovery: {str(exc)[:160]}')
    return options, preferred, errors


def argv(route, instructions, file, result, directory):
    """Each supported CLI owns its prompt/model syntax; no shell interpolation."""
    agent, model = route['agent'], route.get('model')
    prompt = instructions + f' Read only the assigned review input file: {file}'
    if agent == 'codex':
        args = [agent, 'exec', '--sandbox', 'danger-full-access' if route['dil'] else 'read-only',
                '--skip-git-repo-check', '-C', str(directory), '-o', str(result)]
        if model: args += ['--model', model]
        if route.get('effort') not in (None, 'default'):
            args += ['-c', 'model_reasoning_effort=' + json.dumps(route['effort'])]
        return args + [prompt], True
    if agent == 'cursor-agent':
        args = [agent, '--print', '--trust'] + (['--force'] if route['dil'] else ['--mode', 'plan'])
    elif agent == 'claude':
        args = [agent, '--print', '--permission-mode', 'auto', '--output-format', 'text']
    elif agent == 'opencode':
        args = [agent, 'run', '--auto', '--format', 'default', '--file', str(file)]
    else:
        raise RuntimeError('This native agent has no supported review adapter.')
    if model: args += ['--model', model]
    return args + [prompt], False
