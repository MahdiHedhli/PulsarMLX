"""Independent serial metadata reference. Reads synthetic policy metadata only."""
import hashlib
import itertools
import json
import re
import struct
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures/admission-screen"
LIMIT = 8 << 20
F = "pulsarmlx.admission-screen.input/1"
POLICIES = ("AdmitAll", "TwoHit")
COUNT_KEYS = ("occurrences", "waves", "r", "m", "u_r", "u_t", "admitted_fills", "bypasses",
              "persistent_evictions", "history_insertions", "history_evictions", "peak_persistent",
              "peak_transient", "peak_history")


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def pairs(items):
    out = {}
    for key, value in items:
        require(key not in out, "duplicate field")
        out[key] = value
    return out


def invalid(_):
    raise ValueError("non-integer numeric field")


def json_bytes(obj):
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_fixture(name):
    require(Path(name).name == name, "metadata fixture name")
    path = FIXTURES / name
    require(path.resolve(strict=True) == path and path.is_file() and path.stat().st_size <= LIMIT,
            "bounded metadata fixture")
    with path.open("rb") as source:
        raw = source.read(LIMIT + 1)
    require(len(raw) <= LIMIT, "input size")
    return raw


def integer(n, maximum=2**32-1):
    require(type(n) is int and 0 <= n <= maximum, "unsigned integer")
    return n


def hexdigest(s):
    require(type(s) is str and re.fullmatch("[a-f0-9]{64}", s), "canonical hash")
    return bytes.fromhex(s)


def domain(c):
    raw = b"admission-screen.domain/1\0" + hexdigest(c["content"]) + hexdigest(c["metadata"])
    raw += struct.pack("<7I", c["layer"],c["d"],c["h"],c["group"],*c["bits"])
    return sha(raw + struct.pack("<9Q", *c["components"]))


def parse(raw):
    require(type(raw) is bytes and len(raw) <= LIMIT, "input size")
    doc = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_float=invalid, parse_constant=invalid)
    require(type(doc) is dict and set(doc)=={"provenance_kind","schema","class","catalog","calls"}, "trace fields")
    require(doc["schema"] == F and doc["provenance_kind"] == "synthetic", "schema/provenance")
    c = doc["class"]
    require(type(c) is dict and set(c)==set("content metadata layer d h group bits components persistent_slots".split()), "class fields")
    require(integer(c["persistent_slots"])==2 and integer(c["group"])==64, "geometry")
    integer(c["layer"])
    d,h = map(integer,(c["d"],c["h"]))
    require(min(d,h)>0 and d%64==h%64==0 and type(c["bits"]) is list and len(c["bits"])==3, "shape")
    expected=[]
    for bits,k in zip(c["bits"],(d,d,h)):
        require(integer(bits) in (4,8),"recipe")
        count=d*h;expected.extend((count*bits//8,count//32,count//32))
    require(type(c["components"]) is list and [integer(n,2**64-1) for n in c["components"]]==expected
            and sum(expected)<=32<<20, "tuple capacity")
    tag=domain(c)
    catalog=doc["catalog"]
    require(type(catalog) is list and 1<=len(catalog)<=4096, "catalog size")
    seen=set()
    for i, item in enumerate(catalog):
        require(type(item) is dict and set(item)=={"expert","domain","binding"}, "catalog fields")
        require(integer(item["expert"])==i and item["domain"]==tag, "catalog domain")
        binding=hexdigest(item["binding"]);require(binding not in seen,"catalog binding");seen.add(binding)
    calls=doc["calls"]
    require(type(calls) is list and 1<=len(calls)<=4096,"call count")
    count=0
    for call in calls:
        require(type(call) is list and 1<=len(call)<=64, "call size");count+=len(call)
        require(count<=65536 and all(integer(n)<len(catalog) for n in call), "call identity or total")
    return doc


def waves(call):
    current=[]
    for key in call:
        if key not in current and len(set(current))==2:
            yield current
            current=[]
        current.append(key)
    yield current


def simulate(raw, policy):
    doc=parse(raw);require(policy in POLICIES,"policy")
    size=sum(doc["class"]["components"])
    counts=dict.fromkeys(COUNT_KEYS,0);slots=[None,None];history=[];events=[]
    tag=domain(doc["class"]);input_sha=sha(raw)
    suffix=bytes.fromhex(input_sha+tag)+bytes([POLICIES.index(policy)])
    digest=hashlib.sha256(b"admission-screen.events/1\0"+suffix)
    for call_index,call in enumerate(doc["calls"]):
        for wave in waves(call):
            counts["waves"]+=1
            idx=list(dict.fromkeys(wave))
            old={s["expert"]:i for i,s in enumerate(slots) if s is not None}
            protected={old[k] for k in idx if k in old}
            before=tuple(history)
            new_residents=[];temporary=[]
            tickets={}
            for k in idx:
                if k in old:
                    s=old[k];tickets[k]=("Persistent",s,slots[s]["generation"])
                elif policy=="AdmitAll" or k in before:
                    s=min(set(range(2))-protected,key=lambda i:((-1 if slots[i] is None else slots[i]["recency"]),i))
                    generation=1 if slots[s] is None else slots[s]["generation"]+1
                    if slots[s] is not None:counts["persistent_evictions"]+=1
                    slots[s]=dict(expert=k,generation=generation,recency=0)
                    tickets[k]=("Persistent",s,generation);protected.add(s);new_residents.append(k)
                else:
                    tickets[k]=("Transient",len(temporary),counts["waves"]);temporary.append(k)
            visited=set()
            for k in wave:
                kind,slot,gen=tickets[k]
                if k in old:cat="R"
                elif k not in visited:cat="M"
                else:cat="U_R" if kind=="Persistent" else "U_T"
                visited.add(k);counts[cat.lower()]+=1;counts["occurrences"]+=1
                if kind=="Persistent":slots[slot]["recency"]=counts["occurrences"]
                events.append(dict(call=call_index,wave=counts["waves"],expert=k,category=cat,kind=kind,slot=slot,generation=gen))
                digest.update(struct.pack("<HQHBBBQ",call_index,counts["waves"],k,("R","M","U_R","U_T").index(cat),int(kind=="Transient"),slot,gen))
            counts["admitted_fills"]+=len(new_residents);counts["bypasses"]+=len(temporary)
            history=[k for k in history if k not in new_residents]+temporary
            counts["history_insertions"]+=len(temporary);counts["history_evictions"]+=max(0,len(history)-64)
            history=history[-64:]
            for name,n in (("persistent",sum(v is not None for v in slots)),("history",len(history)),("transient",len(temporary))):
                counts["peak_"+name]=max(counts["peak_"+name],n)
            require(not set(history).intersection(s["expert"] for s in slots if s), "history invariant")
    c=counts;hits=c["r"]+c["u_r"]+c["u_t"];n=c["occurrences"]
    require(c["m"]+hits==n and c["m"]==c["admitted_fills"]+c["bypasses"],"accounting partition")
    state=dict(slots=slots,history=history,counts=counts)
    metrics=dict(materializations=c["m"],demanded_bytes=size*n,component_read_calls=9*c["m"],issued_bytes=size*c["m"],
                 persistent_hit_bytes=size*c["r"],retained_reuse_bytes=size*c["u_r"],transient_reuse_bytes=size*c["u_t"],
                 read_avoidance_hits=hits,read_avoidance_bytes=size*hits,persistent_hit_ratio=[c["r"],n],read_avoidance_ratio=[hits,n],
                 final_persistent=sum(v is not None for v in slots),final_transient=0,final_history=len(history))
    return dict(input_sha256=input_sha,domain_sha256=tag,event_sha256=digest.hexdigest(),
                state_sha256=sha(b"admission-screen.state/1\0"+suffix+json_bytes(state)),events=events,state=state,metrics=metrics)


def verify_report(raw, policy, encoded):
    """Check an observed synthetic report against an independent whole-trace replay."""
    require(type(encoded) is bytes and len(encoded)<=LIMIT, "report size")
    report=json.loads(encoded.decode("utf-8"),object_pairs_hook=pairs,parse_constant=invalid,parse_float=invalid)
    expected=simulate(raw,policy)
    doc=parse(raw)
    require(type(report) is dict and set(report)==set(expected)|{"schema","provenance_kind","policy","source","catalog","ledger"}, "report fields")
    identity={"schema":"pulsarmlx.admission-screen.report/1","provenance_kind":"synthetic","policy":policy,
              "source":doc["class"],"catalog":[entry["binding"] for entry in doc["catalog"]]}
    for field,value in dict(expected,**identity).items():
        require(json.dumps(report[field],sort_keys=True)==json.dumps(value,sort_keys=True), "report mismatch: "+field)
    ledger=report["ledger"]
    fields=("modeled_persistent_payload_bound","modeled_transient_payload_bound","catalog_bytes","parsed_input_bytes",
            "history_capacity_bytes","state_and_tickets_bytes","event_capacity_bytes","scratch_capacity_bytes","report_capacity_bytes")
    require(type(ledger) is dict and set(ledger)==set(fields)|{"logical_total"}, "ledger fields")
    for n in ledger.values():integer(n,2**64-1)
    size=sum(doc["class"]["components"])
    require(ledger["modeled_persistent_payload_bound"]==ledger["modeled_transient_payload_bound"]==2*size
            and ledger["history_capacity_bytes"]==128 and ledger["catalog_bytes"]==32*len(doc["catalog"])
            and ledger["report_capacity_bytes"]==LIMIT and sum(ledger[k] for k in fields)==ledger["logical_total"], "comparison envelope")
    return report


def corpus():
    base=parse(read_fixture("template.json")); digest=hashlib.sha256();n=0
    for length in range(1,7):
        for word in itertools.product(range(3),repeat=length):
            for calls in ([list(word)],[[k] for k in word]):
                doc=dict(base,calls=calls)
                raw=json.dumps(doc,sort_keys=True,separators=(",",":")).encode()
                for policy in POLICIES:
                    result=simulate(raw,policy)
                    for key in ("input_sha256","event_sha256","state_sha256"):
                        digest.update(bytes.fromhex(result[key]))
                    digest.update(struct.pack("<6Q",*(result["state"]["counts"][k] for k in ("r","m","u_r","u_t","admitted_fills","persistent_evictions"))))
                    n+=1
    return dict(policy_runs=n,words=1092,partitions_per_word=2,sha256=digest.hexdigest())


def golden():
    named=json.loads(read_fixture("schedules.json"),object_pairs_hook=pairs)
    doc=parse(read_fixture("template.json"));out={}
    for name,calls in named.items():
        raw=json.dumps(dict(doc,calls=calls),sort_keys=True,separators=(",",":")).encode()
        out[name]={p:simulate(raw,p) for p in POLICIES}
    return dict(schema="pulsarmlx.admission-screen.synthetic-reference/1",case_reports=out,exhaustive=corpus())


if __name__=="__main__":
    import sys
    data=json_bytes(golden())+b"\n";require(len(data)<=LIMIT,"expected journal size")
    if sys.argv[1:]==["--check"]:require(data==read_fixture("expected.json"),"reference parity")
    elif sys.argv[1:]==["--emit"]:sys.stdout.buffer.write(data)
    else:raise SystemExit("use --check or --emit")
