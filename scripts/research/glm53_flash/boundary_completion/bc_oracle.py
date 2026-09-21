"""Independent scalar equations for the successor cases (no candidate imports)."""
import math

def sigmoid(x):
    if x>=0:return 1/(1+math.exp(-x))
    z=math.exp(x);return z/(1+z)

def route(case,ids):
    values=[sigmoid(case['gates'][i]) for i in ids]
    denominator=sum(values) if case['normalize'] and case['top_k']>1 else 1.0
    return [case['scale']*v/denominator for v in values]

def kernel_one(x,weights):
    raw=[[[v*weights[c][0][0] for c,v in enumerate(row)] for row in batch] for batch in x]
    act=[[[v*sigmoid(v) for v in row] for row in batch] for batch in raw]
    return {'raw':raw,'silu':act,'state':{'shape':[len(x),0,len(weights)],'values':[[] for _ in x]}}
