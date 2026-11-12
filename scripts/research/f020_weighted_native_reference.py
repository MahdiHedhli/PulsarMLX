"""Compute independent weighted source enclosures from the original six synthetic cases."""
import argparse
import hashlib
import json
from fractions import Fraction
from pathlib import Path
import f020_expert_mlp_r1_v1 as r1
import f020_expert_mlp_qualify_v1 as donor
import f020_resident_mlp_fixtures as fixtures
import f020_weighted_mlp_reference as dyadic
import f020_weighted_native_rational as rational

ROOT = fixtures.ROOT
DIR = ROOT / "fixtures/weighted-native-mlp"
FILE = DIR / "source-enclosure-v1.json"
REFERENCE_LIMIT = 4 << 20
ARMS = tuple((p, a) for p in ("default", "mixed") for a in ("allocating", "cached"))
BOOKS = {"default":"02a7180617c9f3554e77b3d9bafa381dc97dfd29bc0b28d73f7c9b21a74b8497",
         "mixed":"037e3cc41a4cdf409cbe32c7a1f22d0dd3535ea706b13229e84a5e5f0543d2b0"}
Q, H, T, ONE = 0x3e800000, 0x3f000000, 0x3f400000, 0x3f800000
ROUTE = (((0,ONE),), ((0,T),(1,Q)), ((0,H),(1,Q),(2,Q)), ((0,Q),(1,H),(0,Q)), ((0,H),(2,0),(1,H)))
GAMMA = Fraction(21, (1 << 24)-21)
HELPERS = (r1, donor, fixtures, dyadic, rational)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(obj):
    return (json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False)+"\n").encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bounded(path, limit):
    return fixtures.contents(path.parent, path.name, limit)


def strict(raw):
    def invalid(value):
        raise ValueError("non-integral or nonfinite JSON number")
    return json.loads(raw,object_pairs_hook=dyadic.unique,parse_float=invalid,parse_constant=invalid)


def route_ids(profile, recipe):
    words = dyadic.words
    field = dyadic.field
    plans = [b"weighted-plan-v1\0" + words([len(p)]) + words(x for pair in p for x in pair) for p in ROUTE]
    data = (b"weighted-book-v1\0"+field(profile.encode())+field(b"binary32-rne-mul-then-add-v1")+
            bytes.fromhex(sha(bounded(fixtures.VIEW/"manifest.json",1<<20)))+
            bytes.fromhex(recipe["content"])+bytes.fromhex(fixtures.INPUT)+
            words([1,128,64,3,64,0]+[p["bits"] for p in recipe["planes"][0]]+[5])+b"".join(map(field,plans)))
    require(sha(data)==BOOKS[profile],"fixed route identity")
    return dict(book=sha(data),plans=list(map(sha,plans)))


def expert_enclosure(ref):
    require(r1.gamma_n(1,128,64)==21,"fixed down gamma")
    hmax=[max(abs(lo),abs(hi))+b for (lo,hi),b in zip(ref["h"][0],ref["bh"][0])]
    star=[GAMMA*sum(a*h for a,h in zip(row,hmax)) for row in ref["down"][1]]
    prop=ref["propagated"][0]
    intervals=[(lo-b-p,hi+b+p) for (lo,hi),b,p in zip(ref["y"][0],star,prop)]
    return intervals,dict(Hmax=list(map(rational.encode,hmax)),Bstar=list(map(rational.encode,star)),
                          P=list(map(rational.encode,prop)),I=[[rational.encode(x) for x in pair] for pair in intervals])


def endpoints(route, enclosures):
    ends=[[0,0] for _ in range(128)]
    for expert,bits in route:
        weight=r1.f32(bits)
        require(weight>=0,"negative weight")
        for j,pair in enumerate(enclosures[expert]):
            for side in (0,1):
                product=rational.rn32(weight*pair[side])
                ends[j][side]=rational.rn32(r1.f32(ends[j][side])+r1.f32(product))
    return ends


class Originals:
    def __init__(self):
        self.recipes=fixtures.prepare()["recipes"]
        raw=bounded(fixtures.ORIGINAL/"manifest.json",1<<20)
        require(sha(raw)==fixtures.MANIFEST,"original manifest binding")
        self.manifest=strict(raw)
        self.cases={}
        self.artifact=self.generate()

    def generate(self):
        profiles={}
        for profile,recipe in self.recipes.items():
            enclosures=[]; experts=[]
            for expert in range(3):
                cid=f"mlp-d128-h64-m1-e{expert}-{profile}"
                case,=[c for c in self.manifest["cases"] if c["id"]==cid]
                require(sha(bounded(fixtures.ORIGINAL/case["input"],512))==fixtures.INPUT,"input binding")
                ref=donor.refs(self.manifest,case)
                self.cases[profile,expert]=ref
                interval,row=expert_enclosure(ref)
                enclosures.append(interval)
                experts.append(dict(case=cid,components=[p["sha256"] for p in recipe["planes"][expert]],**row))
            profiles[profile]=dict(identity=route_ids(profile,recipe),content=recipe["content"],
                     bits=[p["bits"] for p in recipe["planes"][0]],experts=experts,
                     endpoints=[endpoints(plan,enclosures) for plan in ROUTE])
        return dict(schema="weighted-native-source-enclosure-v1",rounding="rational-to-binary32-rne/1",
                    arithmetic="binary32-rne-mul-then-add-v1",geometry=[1,128,64,3,64,0],route=ROUTE,
                    original_manifest=fixtures.MANIFEST,indexed_manifest=sha(bounded(fixtures.VIEW/"manifest.json",1<<20)),
                    input_sha256=fixtures.INPUT,gamma=rational.encode(GAMMA),
                    helpers={Path(m.__file__).name:sha(bounded(Path(m.__file__).resolve(),1<<20)) for m in HELPERS},
                    producer=sha(bounded(Path(__file__).resolve(),1<<20)),profiles=profiles)

    def verify(self):
        expected=canonical(self.artifact);raw=bounded(FILE,REFERENCE_LIMIT)
        require(expected==raw and canonical(strict(raw))==raw,"frozen source reference")
        return sha(raw)


def local_bits(route, down):
    require(len(route)==len(down) and 1<=len(route)<=3,"local route length")
    acc=[0]*128
    for (expert,w),(observed,words) in zip(route,down):
        require(expert==observed and len(words)==128,"local occurrence")
        acc=[dyadic.add(a,dyadic.multiply(w,x)) for a,x in zip(acc,words)]
    return acc


def weighted_gates(route,down,words,fixed):
    require(len(words)==len(fixed)==128,"weighted shape")
    expected=local_bits(route,down)
    require(words==expected,"WEIGHTED_LOCAL_BITS_V1")
    require(all(r1.f32(lo)<=r1.f32(w)<=r1.f32(hi) for (lo,hi),w in zip(fixed,words)),
            "WEIGHTED_SOURCE_ENCLOSURE_V1")
    return expected


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("action",choices=["generate","check"])
    action=p.parse_args().action
    source=Originals()
    if action=="generate":
        data=canonical(source.artifact);require(len(data)<=REFERENCE_LIMIT,"source reference size")
        with FILE.open("xb") as out:
            out.write(data)
    print(source.verify())
