#!/usr/bin/env python3
"""Deterministic scorer for the unpruned-fidelity held-out tasks (G41). Stdlib only.

A model output is scored on its CONTENT: the text after the first `</think>`; no closed think block or empty content is
UNUSABLE (a failure, reported separately). Checkers: python-asserts (the first fenced code block + the task's asserts run
under the repository's sandbox-exec fence: no network, no writes outside a temp dir, 10 s), last-number, normalized-match,
contains-all, json-object (expected keys equal), json-equals. The same scorer runs on both conditions; it never reads
hidden reasoning."""
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata

THINK_END = '</think>'


def content_of(text):
    i = text.find(THINK_END)
    if i < 0:
        return None
    return text[i + len(THINK_END):].strip()


def normalize(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9/_]+', ' ', s).strip()


def last_number(s):
    nums = re.findall(r'-?\d[\d\s,]*(?:[.,]\d+)?', s)
    if not nums:
        return None
    raw = nums[-1].replace(' ', '').replace(',', '')
    try:
        return float(raw)
    except ValueError:
        return None


def code_block(s):
    m = re.search(r'```(?:python|py)?\s*\n(.*?)```', s, re.S)
    return m.group(1) if m else None


def strip_fences(s):
    m = re.search(r'```(?:json)?\s*\n(.*?)```', s, re.S)
    return m.group(1).strip() if m else s.strip()


def first_json(s):
    s = strip_fences(s)
    for start in [i for i, ch in enumerate(s) if ch in '{[']:
        for end in range(len(s), start, -1):
            try:
                return json.loads(s[start:end])
            except ValueError:
                continue
    return None


def fence_profile(work):
    """The successor supervisor's fence shape: deny network, deny reads/writes except system python + the work dir."""
    lines = ['(version 1)', '(allow default)', '(deny network*)', '(deny file-read*)', '(deny file-write*)', '(allow file-read-metadata)', '(deny process-fork)']
    for p in ['/System', '/usr/lib', '/usr/share', '/usr/bin', '/opt/homebrew/Cellar', '/opt/homebrew/opt', '/opt/homebrew/lib', '/private/var/db/dyld', '/Library/Developer/CommandLineTools', '/Applications/Xcode.app', work]:
        lines.append('(allow file-read* (subpath ' + json.dumps(p) + '))')
    for p in ['/', '/dev/null', '/dev/random', '/dev/urandom', '/private/etc/localtime', '/usr/bin/sandbox-exec']:
        lines.append('(allow file-read* (literal ' + json.dumps(p) + '))')
    lines.append('(allow file-write* (subpath ' + json.dumps(work) + '))'); lines.append('(allow file-write* (literal "/dev/null"))')
    return '\n'.join(lines) + '\n'


def run_python_asserts(code, asserts, python=sys.executable, timeout=10):
    work = os.path.realpath(tempfile.mkdtemp(prefix='score-')); prof = os.path.join(work, 'fence.sb'); open(prof, 'w').write(fence_profile(work))
    src = os.path.join(work, 'check.py'); open(src, 'w').write(code + '\n\n' + '\n'.join(asserts) + '\nprint("ASSERTS_OK")\n')
    env = {'PATH': '/usr/bin:/bin', 'HOME': work, 'TMPDIR': work, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1', 'PYTHONHASHSEED': '0'}
    try:
        p = subprocess.run(['/usr/bin/sandbox-exec', '-f', prof, python, '-I', '-B', '-S', src], capture_output=True, text=True, timeout=timeout, env=env, cwd=work)
        return p.returncode == 0 and 'ASSERTS_OK' in p.stdout, (p.stdout + p.stderr)[-600:]
    except subprocess.TimeoutExpired:
        return False, 'TIMEOUT'


def score(task, text, python=sys.executable):
    content = content_of(text or '')
    if not content:
        return {'id': task['id'], 'domain': task['domain'], 'pass': False, 'reason': 'UNUSABLE (no closed </think> or empty content)', 'usable': False}
    c = task['check']; kind = c['type']; ok = False; reason = ''
    if kind == 'python-asserts':
        code = code_block(content)
        if code is None:
            reason = 'no code block'
        else:
            ok, reason = run_python_asserts(code, c['asserts'], python=python)
    elif kind == 'last-number':
        got = last_number(content); ok = got is not None and abs(got - c['answer']) < 1e-9; reason = f'last number {got} vs {c["answer"]}'
    elif kind == 'normalized-match':
        n = normalize(content); lines = [normalize(l) for l in content.splitlines() if l.strip()]
        ok = any(n == normalize(a) or (lines and lines[-1] == normalize(a)) for a in c['answers']); reason = f'normalized {n[:60]!r}'
    elif kind == 'contains-all':
        ok = all(n in content for n in c['needles']); reason = f'needles {c["needles"]}'
    elif kind in ('json-object', 'json-equals'):
        got = first_json(content)
        if got is None:
            reason = 'no JSON'
        elif kind == 'json-equals':
            ok = got == c['expect']; reason = f'{str(got)[:80]} vs {c["expect"]}'
        else:
            ok = isinstance(got, dict) and all(k in got and (abs(got[k] - v) < 1e-9 if isinstance(v, (int, float)) and not isinstance(v, bool) and isinstance(got.get(k), (int, float)) else got[k] == v) for k, v in c['expect'].items()); reason = f'{str(got)[:80]}'
    else:
        reason = 'unknown checker'
    return {'id': task['id'], 'domain': task['domain'], 'pass': bool(ok), 'reason': reason, 'usable': True, 'content_chars': len(content)}


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--tasks', required=True); ap.add_argument('--outputs', required=True, help='JSON {task_id: text}'); ap.add_argument('--log', required=True); ap.add_argument('--python', default=sys.executable)
    a = ap.parse_args()
    tasks = json.load(open(a.tasks))['tasks']; outputs = json.load(open(a.outputs))
    rows = [score(t, outputs.get(t['id']), python=a.python) for t in tasks]
    n = sum(r['pass'] for r in rows); json.dump({'rows': rows, 'passed': n, 'total': len(rows), 'unusable': sum(1 for r in rows if not r['usable'])}, open(a.log, 'w'), indent=1)
    print(json.dumps({'passed': n, 'total': len(rows), 'unusable': sum(1 for r in rows if not r['usable']), 'by_domain': {d: [r['pass'] for r in rows if r['domain'] == d] for d in sorted({r['domain'] for r in rows})}}))


if __name__ == '__main__':
    main()
