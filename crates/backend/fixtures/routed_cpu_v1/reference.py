#!/usr/bin/env python3
"""Independent stdlib Decimal oracle; no Rust import, execution or output input."""
import argparse
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parent


def fixture():
    d = Decimal
    embedding = [[d(int(j == i)) for j in range(4)] for i in range(4)]
    embedding += [[-d(int(j == i)) for j in range(4)] for i in range(3)]
    embedding += [[d(0)] * 4]
    routers = [
        [[d(v)/8 for v in row] for row in [[1,0,-1,0],[1,0,-1,0],[-1,1,1,0],[0,-1,0,1]]],
        [[d(v)/32 for v in row] for row in [[-3,-1,1,3],[-1,3,-3,1],[1,-3,3,-1],[3,1,-1,-3]]],
    ]
    layers = []
    for layer in range(2):
        banks = []
        for matrix in range(3):
            banks.append([[[d(((layer+1)*3+expert*5+matrix*7+row*3+col*11)%9-4)/32
                            for col in range(4)] for row in range(4)] for expert in range(4)])
        layers.append((routers[layer], *banks))
    head = [[d(0)] * 4 for _ in range(8)]
    for token in range(7):
        head[token+1][token%4] = d(1 if token<4 else -1)/2
    head[0][3] = -d(1)/2
    return embedding, layers, head


def flatten(value):
    if isinstance(value, list) or isinstance(value, tuple):
        return [n for child in value for n in flatten(child)]
    return [value]


def dot(matrix, vector):
    out = []
    for row in matrix:
        total = Decimal(0)
        for column in range(4):
            total += row[column] * vector[column]
        out.append(total)
    return out


def step(weights, token):
    embedding, layers, head = weights
    x = embedding[token][:]
    fields = {}
    for layer, (router, gate, up, down) in enumerate(layers):
        prefix = f'l{layer}.'
        fields[prefix+'input'] = x[:]
        scores = dot(router, x)
        ids = sorted(range(4), key=lambda expert: (-scores[expert], expert))[:2]
        exponentials = [(scores[expert]-scores[ids[0]]).exp() for expert in ids]
        denominator = sum(exponentials)
        probabilities = [e/denominator for e in exponentials]
        g = [dot(gate[e], x) for e in ids]
        u = [dot(up[e], x) for e in ids]
        activation = [[z/(1+(-z).exp()) for z in row] for row in g]
        product = [[activation[s][i]*u[s][i] for i in range(4)] for s in range(2)]
        outputs = [dot(down[ids[s]], product[s]) for s in range(2)]
        combined = [sum(probabilities[s]*outputs[s][i] for s in range(2)) for i in range(4)]
        residual = [x[i]+combined[i] for i in range(4)]
        fields.update({prefix+k: flatten(v) for k,v in [
            ('scores',scores),('selected',ids),('weights',probabilities),('gate',g),
            ('up',u),('silu',activation),('product',product),('down',outputs),
            ('combined',combined),('residual',residual)]})
        ordered = sorted(scores, reverse=True)
        for a,b in zip(ordered, ordered[1:]):
            assert a == b or a-b > Decimal(2)**-10, ('ambiguous router boundary', layer)
        x = residual
    logits = dot(head, x)
    ids = sorted(range(8), key=lambda i: (-logits[i], i))
    assert logits[ids[0]] == logits[ids[1]] or logits[ids[0]]-logits[ids[1]] > Decimal(2)**-10
    fields['logits'] = logits
    return ids[0], fields


def run(precision):
    with localcontext() as ctx:
        ctx.prec = precision
        weights = fixture()
        records = []
        for name, seed, maximum, eos in [('max',0,8,None),('eos',5,8,7)]:
            token = seed
            for position in range(1, maximum+1):
                result, fields = step(weights, token)
                records.append((name, position, token, result, fields))
                token = result
                if result == eos:
                    break
        return weights, records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    weights, records = run(80)
    _, stable = run(100)
    differences = []
    for left, right in zip(records, stable, strict=True):
        assert left[:4] == right[:4]
        for key in left[4]:
            for a,b in zip(left[4][key], right[4][key], strict=True):
                differences.append(abs(Decimal(a)-Decimal(b)))
    worst = max(differences)
    assert worst < Decimal('1e-70')
    assert [r[3] for r in records if r[0]=='max'] == [1,2,3,4,5,6,7,0]
    assert [r[3] for r in records if r[0]=='eos'] == [6,7]
    routes = {tuple(r[4]['l0.selected']) for r in records}
    assert len(routes) >= 2
    assert records[7][4]['logits'] == [0]*8
    binary = b''.join(struct.pack('<d', float(v)) for v in flatten(weights))
    lines = ['# routed_cpu_v1; 80-digit independent Decimal; exact identity/selected; abs=rel=2^-35; uncertainty=2^-180']
    for name,pos,token,result,fields in records:
        lines.append(f'{name}\t{pos}\tidentity\t{pos} {token} {result}')
        for key, values in fields.items():
            lines.append(f'{name}\t{pos}\t{key}\t'+' '.join(format(v,'.65g') if isinstance(v,Decimal) else str(v) for v in values))
    outputs = {'weights.bin':binary, 'goldens.tsv':('\n'.join(lines)+'\n').encode(),
               'reference_summary.json':(json.dumps({'reference_digits':80,'stability_digits':100,'max_reference_difference':str(worst),'stability_threshold':'1e-70','generated_tokens':{'max':[1,2,3,4,5,6,7,0],'eos':[6,7]},'distinct_layer0_routes':len(routes)},indent=2)+'\n').encode()}
    identities = {name:hashlib.sha256(content).hexdigest() for name,content in outputs.items()}
    identities.update({name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['reference.py','SPEC.md']})
    outputs['manifest.json'] = (json.dumps({'schema':'routed_cpu_v1.freeze/1','sha256':identities,'weights_bytes':len(binary),'cases':2,'steps':len(records),'comparison':{'absolute':'2^-35','relative':'2^-35','reference_uncertainty':'2^-180','identity_and_selected':'EXACT'}},indent=2)+'\n').encode()
    for name, content in outputs.items():
        if args.check:
            assert (ROOT/name).read_bytes() == content, ('frozen artifact drift',name)
        else:
            (ROOT/name).write_bytes(content)
    print(json.dumps({'reference':'PASS','check':args.check,'weights_bytes':len(binary),'steps':len(records),'max_80_100_difference':str(worst),'distinct_layer0_routes':len(routes)}))


if __name__ == '__main__':
    main()
