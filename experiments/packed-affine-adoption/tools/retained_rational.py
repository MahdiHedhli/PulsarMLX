"""Private exact-field view for the frozen experimental reference; no I/O changes."""
import copy
from fractions import Fraction
import hashlib
import json
import math
import re

REFERENCE_SHA = 'c27a9d51f7e2dee014749078ede961659a81ebe926bff644bfe62b9de058e191'
FIXTURE_SHA = '513b8c800be7f1f491d0bfa08748123066e6ef9369cc907e0a2d8475e733e597'
INTEGER = r'(?:0|-?[1-9][0-9]*)'
FRACTION = INTEGER + r'/[1-9][0-9]*'
POLICY = 'ASCII canonical integer n -> n/1; reduced positive-denominator fractions text-identical; exact fields only'


class NumericalFailure(ValueError):
    def __init__(self, case, gates):
        super().__init__('independent numerical failure: ' + case)
        self.case = case
        self.gates = gates


def normalize_token(value):
    if type(value) is not str or len(value) > 4096:
        raise ValueError('exact token must be a bounded string')
    if re.fullmatch(INTEGER, value, re.ASCII):
        normalized = value + '/1'
        if Fraction(int(value), 1) != Fraction(normalized):
            raise ValueError('lossless integer proof')
        return normalized, True
    if not re.fullmatch(FRACTION, value, re.ASCII):
        raise ValueError('noncanonical exact token')
    numerator, denominator = map(int, value.split('/'))
    if math.gcd(numerator, denominator) != 1:
        raise ValueError('unreduced fraction')
    return value, False


def normalize_exact(exact):
    result = copy.deepcopy(exact)
    counts = {}
    for field in ('y_exact', 'phi_exact'):
        if type(exact[field]) is not list:
            raise ValueError('exact vector type')
        converted = 0
        for i, value in enumerate(exact[field]):
            normalized, changed = normalize_token(value)
            result[field][i] = normalized
            converted += changed
        counts[field] = {'total': len(exact[field]), 'converted': converted,
                         'unchanged': len(exact[field]) - converted}
    return result, counts


def frozen_view(raw, manifest):
    if hashlib.sha256(raw).hexdigest() != REFERENCE_SHA:
        raise ValueError('original reference hash')
    original = json.loads(raw)
    if original['schema'] != 'pulsarmlx.adoption-original-reference/1' or original['fixture_manifest_sha256'] != FIXTURE_SHA:
        raise ValueError('original reference schema/fixture')
    cases = {c['id']: c for c in manifest['cases']}
    if len(cases) != 20 or set(cases) != set(original['cases']):
        raise ValueError('exact reference case IDs')
    view = copy.deepcopy(original)
    census = {}
    totals = {f: {'total': 0, 'converted': 0, 'unchanged': 0} for f in ('y_exact', 'phi_exact')}
    for cid, c in cases.items():
        r = original['cases'][cid]
        if r['exact']['k'] != c['D'] or any(len(r['exact'][f]) != c['M'] * c['H'] for f in totals):
            raise ValueError('exact reference geometry')
        full = c['D'] == 4096
        if (r['rust'] is None) != full:
            raise ValueError('full-K deferral identity')
        view['cases'][cid]['exact'], census[cid] = normalize_exact(r['exact'])
        want_phi = {'full-positive-A-gate': 2048, 'full-positive-A-up': 1024,
                    'full-positive-B-gate': 0, 'full-positive-B-up': 1024}
        for field, counts in census[cid].items():
            want = (2048 if field == 'y_exact' else want_phi[cid]) if full else 0
            if counts['converted'] != want:
                raise ValueError('per-case normalization census')
            for key in counts:
                totals[field][key] += counts[key]
    if totals != {'y_exact': {'total': 25088, 'converted': 8192, 'unchanged': 16896},
                  'phi_exact': {'total': 25088, 'converted': 4096, 'unchanged': 20992}}:
        raise ValueError('complete normalization census')
    # The originals remain untouched; only these two vectors differ in the view.
    restored = copy.deepcopy(view)
    for cid in cases:
        for field in totals:
            restored['cases'][cid]['exact'][field] = original['cases'][cid]['exact'][field]
    if restored != original:
        raise ValueError('non-rational reference fields changed')
    return view, {'policy': POLICY, 'original_reference_sha256': REFERENCE_SHA,
                  'cases': census, 'totals': totals, 'exact_value_proof': True,
                  'original_bytes_modified': False, 'non_rational_fields_unchanged': True}


def grade_compatible(view, report):
    # Same gate selection as reference.grade; import the unchanged implementation.
    from reference import decide_qmm
    run = json.loads(report.read_bytes())
    if run['identity']['fixture_manifest_sha256'] != view['fixture_manifest_sha256']:
        raise ValueError('reference/report identity')
    results = []
    for output in run['outputs']:
        r = view['cases'][output['id']]
        case = {'id': output['id'], 'expected': {'families_0_31_2': [{'gamma_n': r['gamma_n']}]}}
        verdict = decide_qmm(case, r['exact'], r['rust'], {'id': output['id'], 'output': output}, report.parent)
        if any(v is not None and not v['pass'] for v in verdict.values()):
            raise NumericalFailure(output['id'], verdict)
        results.append({'id': output['id'], 'gates': verdict})
    if not results:
        raise ValueError('missing numerical outputs')
    return results
