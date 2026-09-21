"""Successor research state wrapper over retained, source-bound MLX machinery."""
from pathlib import Path
import bc_guard
import backend

class Boundaries(backend.Boundaries):
    def __init__(self,phase):
        if Path(phase)!=bc_guard.PHASE:raise ValueError('successor phase required')
        super().__init__(bc_guard.OLD)
    def conv_state(self,x,weights,state=None,*,retain_input_mutation=False):
        backend.finite(x);backend.finite(weights)
        dims=backend.shape(x);wd=backend.shape(weights)
        if len(dims)!=3 or len(wd)!=3:raise backend.DomainError('NLC/C-K-1 required')
        b,t,c=dims;k=wd[1]
        if not (1<=b<=2 and 1<=t<=16 and 1<=c<=32 and 1<=k<=7 and wd==(c,k,1)):raise backend.DomainError('successor convolution bounds')
        if type(retain_input_mutation) is not bool:raise backend.DomainError('mutation flag type')
        if state is None:state={'shape':[b,k-1,c],'values':[[[0.0]*c for _ in range(k-1)] for _ in range(b)]}
        if type(state) is not dict or set(state)!={'shape','values'} or state['shape']!=[b,k-1,c]:raise backend.DomainError('state metadata shape')
        values=state['values'];backend.finite(values)
        expected=(b,k-1,c) if k>1 else (b,0)
        if backend.shape(values)!=expected:raise backend.DomainError('state values shape')
        if any(abs(v)>2 for v in backend.flat(x)) or any(abs(v)>2 for v in backend.flat(values)) or any(abs(v)>1 for v in backend.flat(weights)):raise backend.DomainError('convolution value bounds')
        mx=self.mx
        joined=mx.array([s+row for s,row in zip(values,x)],dtype=mx.float32)
        conv=self.nn.Conv1d(c,c,k,groups=c,bias=False,padding=0)
        conv.weight=mx.array(weights,dtype=mx.float32)
        raw=conv(joined);act=self.nn.silu(raw)
        suffix=joined[:, -(k-1):, :] if k>1 or retain_input_mutation else joined[:, :0, :]
        suffix_shape=list(suffix.shape)
        a,bv,sv=self.evaluate(raw,act,suffix)
        return {'raw':a,'silu':bv,'state':{'shape':suffix_shape,'values':sv}}
