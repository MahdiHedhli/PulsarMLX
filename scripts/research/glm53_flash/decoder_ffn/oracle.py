"""Independent scalar reference for the bounded dense FFN fixture."""
import math


def _sigmoid(x): return 1.0 / (1.0 + math.exp(-x))
def _dot(a, b): return sum(x*y for x, y in zip(a, b))
def _norm(v, eps): return [x / math.sqrt(sum(y*y for y in v)/len(v) + eps) for x in v]


def run(f):
    B,L,H,D = f['shape']; eps=f['hc_eps']; fn=f['fn']; base=f['base']; scale=f['scale']; x=f['x']; residual=x
    out=[]; boundaries=[]
    for b in range(B):
      rows=[]
      for t in range(L):
        streams=x[b][t]; z=_norm([v for s in streams for v in s], f['rms_norm_eps'])
        mixes=[_dot(row,z) for row in fn]
        pre=[_sigmoid(mixes[i]*scale[0]+base[i])+eps for i in range(H)]
        post=[2*_sigmoid(mixes[H+i]*scale[1]+base[H+i]) for i in range(H)]
        comb=[]
        for i in range(H):
          q=[mixes[2*H+i*H+j]*scale[2]+base[2*H+i*H+j] for j in range(H)]; m=max(q); e=[math.exp(v-m) for v in q]; comb.append([v/sum(e)+eps for v in e])
        for j in range(H):
          d=sum(comb[i][j] for i in range(H))+eps
          for i in range(H): comb[i][j]/=d
        for _ in range(max(f['sinkhorn_iters']-1,0)):
          for i in range(H):
            d=sum(comb[i])+eps; comb[i]=[v/d for v in comb[i]]
          for j in range(H):
            d=sum(comb[i][j] for i in range(H))+eps
            for i in range(H): comb[i][j]/=d
        xc=[sum(pre[h]*streams[h][d] for h in range(H)) for d in range(D)]
        n=_norm(xc,f['rms_norm_eps']); gate=[_dot(w,n) for w in f['gate']]; up=[_dot(w,n) for w in f['up']]
        active=[min(g,f['limit'])*_sigmoid(min(g,f['limit']))*max(-f['limit'],min(u,f['limit'])) for g,u in zip(gate,up)]
        m=[_dot(w,active) for w in f['down']]
        expanded=[]
        for j in range(H): expanded.append([post[j]*m[d]+sum(comb[i][j]*residual[b][t][i][d] for i in range(H)) for d in range(D)])
        rows.append(expanded); boundaries.append({'xc':xc,'post':post,'comb':comb,'mlp':m})
      out.append(rows)
    return {'output':out,'boundaries':boundaries}
