"""MIT. Bounded synchronous synthetic transaction harness, not native runtime.

Only immutable tuples cross snapshots. No file I/O, model access, lease issuance,
GPU, concurrency primitive or hidden current request. Proposal handles are local
opaque monotonically increasing integers; outputs are revealed only by commit.
"""
from dataclasses import dataclass, replace
import math
from scripts.research.glm53_flash import candidate as primitive


def integer(value,lo,hi):
    if type(value) is not int or not lo<=value<=hi:
        raise ValueError('INTEGER_BOUND')


def vector(value,n):
    if type(value) is not tuple or len(value)!=n:
        raise ValueError('VECTOR_SHAPE')
    if any(type(x) not in (int,float) or not math.isfinite(x) or abs(x)>8 for x in value):
        raise ValueError('FINITE_OPERAND_BOUND')


def matrix(value,rows,cols):
    if type(value) is not tuple or len(value)!=rows:
        raise ValueError('MATRIX_SHAPE')
    for row in value: vector(row,cols)


def name(value):
    if type(value) is not str or not 1<=len(value)<=64:
        raise ValueError('IDENTITY')


@dataclass(frozen=True)
class Step:
    descriptor: tuple
    request: str
    epoch: int
    position: int
    count: int
    limit: int


@dataclass(frozen=True)
class KDA:
    epoch: int
    position: int
    recurrent: tuple
    suffix: tuple


@dataclass(frozen=True)
class Sparse:
    epoch: int
    position: int
    origin: int
    history: tuple  # entries: (position, index_key, gate, attention_key, value)


@dataclass(frozen=True)
class Context:
    descriptor: tuple
    request: str
    epoch: int
    origin: int
    position: int
    limit: int
    revision: int
    layers: tuple


def validate_token(kind,token):
    if type(token) is not tuple:
        raise ValueError('TOKEN_TYPE')
    if kind=='kda':
        if len(token)!=3: raise ValueError('KDA_TOKEN')
        vector(token[0],7); vector(token[1],2); vector((token[2],),1)
    else:
        if len(token)!=7: raise ValueError('SPARSE_TOKEN')
        for value,n in zip(token,(2,2,2,1,3,3,3)):
            vector((value,) if n==1 else value,n)


def validate_layer(state,context):
    if (type(state) not in (KDA,Sparse) or type(state.epoch) is not int or type(state.position) is not int
            or state.epoch!=context.epoch or state.position!=context.position):
        raise ValueError('STATE_COORDINATES')
    if type(state) is KDA:
        matrix(state.recurrent,2,3); matrix(state.suffix,2,7)
    else:
        if type(state.origin) is not int or state.origin!=context.origin or type(state.history) is not tuple:
            raise ValueError('SPARSE_ORIGIN')
        if len(state.history)!=context.position-context.origin:
            raise ValueError('SPARSE_HISTORY_LENGTH')
        for expected,entry in enumerate(state.history,context.origin):
            if type(entry) is not tuple or len(entry)!=5 or type(entry[0]) is not int or entry[0]!=expected:
                raise ValueError('SPARSE_HISTORY_POSITION')
            for value,n in zip(entry[1:],(2,2,3,3)): vector(value,n)


def kda_transition(state,tokens):
    kernel=tuple(((c+1)/32,-(c+2)/64,(c+3)/32) for c in range(7))
    conv=primitive.causal_conv_silu(tuple(t[0] for t in tokens),kernel,state.suffix)
    q=tuple(row[:2] for row in conv.outputs)
    k=tuple(row[2:4] for row in conv.outputs)
    v=tuple(row[4:] for row in conv.outputs)
    out=primitive.kda_sequence(q,k,v,tuple(t[1] for t in tokens),tuple(t[2] for t in tokens),
                               .125,(.0625,-.125),state=state.recurrent,position=0)
    updated=KDA(state.epoch,state.position+len(tokens),out.state,conv.suffix)
    return updated,out.outputs


def sparse_transition(state,tokens):
    history=list(state.history); outputs=[]; selections=[]
    for token in tokens:
        position=state.origin+len(history)
        history.append((position,token[0],token[1],token[5],token[6]))
        rows=history
        keys=tuple(row[1] for row in rows); gates=tuple(row[2] for row in rows)
        selected=primitive.sparse_select(keys,gates,((.125,-.25),(.375,.0625)),
                                         (token[2],),(token[3],),(True,)*len(rows),len(rows)-1,2,2,
                                         bypass_short=False)
        allowed=tuple(sorted(set(i for i in selected.indices if i>=0)))
        if not allowed: raise ValueError('EMPTY_ATTENTION')
        logits=tuple(primitive.dot(token[4],rows[i][3])/math.sqrt(3) for i in allowed)
        probs=primitive.softmax(logits)
        outputs.append(tuple(math.fsum(p*rows[i][4][d] for p,i in zip(probs,allowed)) for d in range(3)))
        selections.append(tuple(state.origin+i for i in allowed))
    return Sparse(state.epoch,state.position+len(tokens),state.origin,tuple(history)),(tuple(outputs),tuple(selections))


class Engine:
    def __init__(self,descriptor):
        if type(descriptor) is not tuple or len(descriptor)!=3:
            raise ValueError('DESCRIPTOR')
        for item in descriptor: name(item)
        self.descriptor=descriptor
        self._contexts={}; self._pending={}; self._sequence=0

    def create(self,request,layers,*,origin=0,limit=8,initial=None):
        name(request); integer(origin,0,2**31-9); integer(limit,1,8)
        if request in self._contexts or len(self._contexts)>=2:
            raise ValueError('CONTEXT_CAPACITY_OR_DUPLICATE')
        if type(layers) is not tuple or not 1<=len(layers)<=4 or any(type(i) is not int or i not in (0,3,4,7) for i in layers) or tuple(sorted(set(layers)))!=layers:
            raise ValueError('LAYER_SET')
        states=[]
        if initial is None: initial=(((0.,)*3,)*2,((0.,)*7,)*2)
        if type(initial) is not tuple or len(initial)!=2: raise ValueError('INITIAL_STATE')
        matrix(initial[0],2,3); matrix(initial[1],2,7)
        for lid in layers:
            state=Sparse(0,origin,origin,()) if lid in (3,7) else KDA(0,origin,*initial)
            states.append((lid,state))
        self._contexts[request]=Context(self.descriptor,request,0,origin,origin,limit,0,tuple(states))

    def snapshot(self,request):
        if type(request) is not str or request not in self._contexts:
            raise ValueError('UNKNOWN_CONTEXT')
        return self._contexts[request]

    def prepare(self,step,operands):
        if type(step) is not Step: raise ValueError('STEP_TYPE')
        context=self.snapshot(step.request)
        for v in (step.epoch,step.position,step.count,step.limit): integer(v,0,2**31-1)
        if (step.descriptor!=context.descriptor or step.epoch!=context.epoch or step.position!=context.position
                or step.limit!=context.limit or not 1<=step.count<=8
                or step.position+step.count>context.origin+context.limit):
            raise ValueError('STEP_IDENTITY_POSITION_OR_BOUND')
        if len(self._pending)>=8: raise ValueError('PROPOSAL_CAPACITY')
        if type(operands) is not dict or any(type(i) is not int for i in operands) or set(operands)!=set(dict(context.layers)):
            raise ValueError('OPERAND_LAYER_SET')
        # Validate the entire transaction before computing any layer.
        for lid,state in context.layers:
            if (lid in (3,7)) != (type(state) is Sparse): raise ValueError('STATE_KIND')
            validate_layer(state,context)
            tokens=operands[lid]
            if type(tokens) is not tuple or len(tokens)!=step.count: raise ValueError('TOKEN_COUNT')
            for token in tokens: validate_token('kda' if type(state) is KDA else 'sparse',token)
        layers=[]; outputs=[]
        for lid,state in context.layers:
            after,output=(kda_transition if type(state) is KDA else sparse_transition)(state,operands[lid])
            layers.append((lid,after)); outputs.append((lid,output))
        after=replace(context,position=step.position+step.count,revision=context.revision+1,layers=tuple(layers))
        for _,state in after.layers: validate_layer(state,after)
        self._sequence+=1
        self._pending[self._sequence]=(context,after,tuple(outputs))
        return self._sequence

    def commit(self,handle):
        integer(handle,1,self._sequence)
        if handle not in self._pending: raise ValueError('STALE_PROPOSAL')
        before,after,outputs=self._pending.pop(handle)
        if self.snapshot(before.request)!=before: raise ValueError('STALE_CONTEXT')
        self._contexts[before.request]=after
        return outputs

    def cancel(self,handle):
        integer(handle,1,self._sequence)
        self._pending.pop(handle,None)

    def reset(self,request,*,origin=0):
        integer(origin,0,2**31-9)
        before=self.snapshot(request)
        integer(before.epoch+1,0,2**31-1)
        epoch=before.epoch+1
        states=tuple((lid,Sparse(epoch,origin,origin,()) if type(st) is Sparse
                      else KDA(epoch,origin,((0.,)*3,)*2,((0.,)*7,)*2)) for lid,st in before.layers)
        self._contexts[request]=replace(before,epoch=epoch,origin=origin,position=origin,revision=before.revision+1,layers=states)
        for handle,(ctx,_,_) in tuple(self._pending.items()):
            if ctx.request==request: self._pending.pop(handle)
