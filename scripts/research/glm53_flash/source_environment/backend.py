"""Admitted wheel boundaries. State and aggregation are research wrappers only."""
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import symtable
import guard

SOURCE_SHA = 'cd210c73ce3e569ab5270a47a92941cd5ec1450c6ff7b55b8be57c51263f4cb6'
CAPSULE_SHA = '4efab08404da68c50faa1f2a4ebe3235436a1b2aa09bac6e77e20dc0fba35ad9'

class DomainError(ValueError):
    pass

def flat(value):
    if isinstance(value, list):
        for item in value:
            yield from flat(item)
    else:
        yield value

def finite(value):
    vals = list(flat(value))
    if len(vals) > 65536 or any(type(x) not in (int, float) or not math.isfinite(x) for x in vals):
        raise DomainError('nonfinite, nonnumeric or oversized value')

def shape(value):
    if not isinstance(value, list):
        return ()
    if not value:
        return (0,)
    children = [shape(v) for v in value]
    if len(set(children)) != 1:
        raise DomainError('ragged shape')
    return (len(value),) + children[0]

def capsule(phase, mx, *, raw_override=None, bindings_override=None):
    manifest = guard.verify_environment(phase)
    guard.verify_origin(mx, phase, manifest)
    source = Path(phase) / 'source/mlx-vlm/mlx_vlm/models/deepseek_v32/language.py'
    raw_source = source.read_bytes()
    if hashlib.sha256(raw_source).hexdigest() != SOURCE_SHA:
        raise DomainError('upstream source hash mismatch')
    exact = b''.join(raw_source.splitlines(keepends=True)[232:265])
    raw = (Path(phase) / 'source/group_expert_select.capsule.py').read_bytes() if raw_override is None else raw_override
    if raw != exact or hashlib.sha256(raw).hexdigest() != CAPSULE_SHA:
        raise DomainError('capsule source hash mismatch')
    validate_capsule_text(raw)
    namespace = {'mx': mx} if bindings_override is None else dict(bindings_override)
    # A missing binding fails on the real exact decorator at exec time. The
    # override is only for synthetic negative controls; no alternate module runs.
    if any(name != 'mx' or value is not mx for name,value in namespace.items()):
        raise DomainError('unadmitted external binding')
    exec(compile(raw, '<verified-selector>', 'exec'), namespace)
    return namespace['group_expert_select']

def validate_capsule_text(raw):
    parsed = ast.parse(raw)
    if len(parsed.body) != 1 or not isinstance(parsed.body[0], ast.FunctionDef):
        raise DomainError('single function boundary required')
    fn = parsed.body[0]
    if fn.name != 'group_expert_select' or [ast.unparse(d) for d in fn.decorator_list] != ['mx.compile']:
        raise DomainError('function/decorator discrepancy')
    table = symtable.symtable(raw.decode(), '<verified-selector>', 'exec')
    external = {s.get_name() for child in table.get_children() for s in child.get_symbols() if s.is_global() and s.is_referenced()}
    if external != {'mx'}:
        raise DomainError('unexpected external global dependency: '+str(sorted(external)))
    return external

class Boundaries:
    def __init__(self, phase):
        self.phase = Path(phase)
        guard.verify_child_interpreter(phase)
        if os.environ.get('FLASH_ADMITTED_PHASE') != str(self.phase):
            raise DomainError('supervised admission required')
        import mlx.core as mx
        import mlx.nn as nn
        self.mx, self.nn = mx, nn
        manifest = guard.verify_environment(phase)
        guard.verify_origin(nn, phase, manifest)
        self.select = capsule(phase, mx)
        self.evaluations = 0

    def evaluate(self, *arrays):
        self.mx.eval(*arrays)
        self.mx.synchronize()
        self.evaluations += 1
        values = [v.tolist() for v in arrays]
        for value in values:
            finite(value)
        return values

    def route(self, case, *, configured=False):
        finite(case['gates']); finite(case['bias']); finite(case['scale'])
        if any(abs(v)>1000 for v in case['gates']) or any(abs(v)>16 for v in case['bias']):
            raise DomainError('FP32 conversion/corrected-score domain')
        count = len(case['gates'])
        if shape(case['gates']) != (count,) or shape(case['bias']) != (count,):
            raise DomainError('selector vector shape')
        k, groups, keep = (case[x] for x in ('top_k','n_group','topk_group'))
        if any(type(x) is not int for x in (k,groups,keep)) or type(case['normalize']) is not bool:
            raise DomainError('selector parameter types')
        if not (1 <= count <= (512 if configured else 8) and 1 <= k <= min(count,8)
                and 1 <= groups <= (count if configured else 4) and 1 <= keep <= groups
                and (groups == 1 or keep < groups)
                and count % groups == 0 and (groups == 1 or count // groups >= 2)
                and 0 < case['scale'] <= 2.5):
            raise DomainError('selector domain')
        mx = self.mx
        ids, ws = self.select(mx.array([case['gates']], dtype=mx.float32),
                              mx.array(case['bias'], dtype=mx.float32), k, groups, keep,
                              case['scale'], case['normalize'])
        a,b = self.evaluate(ids, ws)
        if shape(a) != (1,k) or shape(b) != (1,k) or len(set(a[0])) != k:
            raise DomainError('selector output shape/uniqueness')
        return a[0], b[0]

    def conv(self, x, weights, state=None, *, mutation=None):
        finite(x); finite(weights)
        dims = shape(x)
        if len(dims) != 3:
            raise DomainError('NLC input required')
        b,t,c = dims
        wd = shape(weights)
        if len(wd) != 3 or wd[0] != c or wd[2] != 1 or not (1<=b<=2 and 1<=t<=16 and 1<=c<=32 and 1<=wd[1]<=7):
            raise DomainError('bounded depthwise kernel/input required')
        k = wd[1]
        if state is None:
            state = [[[0.0]*c for _ in range(k-1)] for _ in range(b)]
        finite(state)
        expected_shape = (b,k-1,c) if k>1 else (b,0)
        if shape(state) != expected_shape:
            raise DomainError('left-state shape')
        if max(abs(v) for v in flat(x)) > 2 or max(abs(v) for v in flat(weights)) > 1 or any(abs(v)>2 for v in flat(state)):
            raise DomainError('prospective convolution value domain')
        mx = self.mx
        joined = mx.array([s+row for s,row in zip(state,x)], dtype=mx.float32)
        operator = self.nn.Conv1d(c,c,k,groups=c,bias=False,padding=0)
        kernel = mx.array(weights, dtype=mx.float32)
        if mutation == 'reversed-convolution-taps':
            kernel = kernel[:, ::-1, :]
        elif mutation == 'swapped-convolution-axes':
            kernel = mx.swapaxes(kernel,1,2)
        elif mutation is not None:
            raise DomainError('unknown synthetic control')
        operator.weight = kernel
        raw = operator(joined)
        act = self.nn.silu(raw)
        suffix = joined[:, -(k-1):, :] if k>1 else joined[:, :0, :]
        return self.evaluate(raw,act,suffix)

    def aggregate(self, ids, weights, experts, *, wrong_association=False):
        finite(weights); finite(experts)
        if not 1<=len(experts)<=8 or len(ids)!=len(weights) or shape(experts)[1:]!=(3,):
            raise DomainError('tiny aggregation domain')
        if any(type(i) is not int or not 0<=i<len(experts) for i in ids):
            raise DomainError('expert ID domain')
        paired = list(reversed(weights)) if wrong_association else weights
        mx = self.mx
        values = mx.array([experts[i] for i in ids], dtype=mx.float32)
        result = (values * mx.array(paired,dtype=mx.float32)[:,None]).sum(axis=0)
        return self.evaluate(result)[0]
