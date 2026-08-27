#!/usr/bin/env python3
"""Same-SX8100 read-pattern benchmark for one verified R001 layer."""
from __future__ import annotations
import argparse,fcntl,json,os,random,resource,statistics,time
from pathlib import Path

F_NOCACHE=48

def open_nocache(path:Path):
    fd=os.open(path,os.O_RDONLY|getattr(os,"O_CLOEXEC",0)|getattr(os,"O_NOFOLLOW",0))
    try: fcntl.fcntl(fd,F_NOCACHE,1);nocache=True
    except OSError: nocache=False
    return fd,nocache

def pread_exact(fd,offset,length):
    pos=0;checksum=0
    while pos<length:
        b=os.pread(fd,min(length-pos,8*1024*1024),offset+pos)
        if not b: raise EOFError("short benchmark read")
        checksum^=b[len(b)//2];pos+=len(b)
    return checksum

def trial(order,records,root,source_root,mode):
    source_fds={};bundle_fds={};nocache=[]
    try:
        for r in records:
            for c in r["components"]:
                name=c["source"]["shard"]
                if name not in source_fds:
                    source_fds[name],n=open_nocache(source_root/name);nocache.append(n)
            path=root/r["relative_path"]
            bundle_fds[r["expert"]],n=open_nocache(path);nocache.append(n)
        calls=bytes_requested=checksum=0;t0=time.perf_counter();cpu0=time.process_time()
        for eid in order:
            r=records[eid]
            if mode=="native_components":
                for c in r["components"]:
                    checksum^=pread_exact(source_fds[c["source"]["shard"]],c["source"]["offset"],c["source"]["length"]);calls+=1;bytes_requested+=c["source"]["length"]
            elif mode=="bundle_components":
                for c in r["components"]:
                    checksum^=pread_exact(bundle_fds[eid],c["bundle_offset"],c["length"]);calls+=1;bytes_requested+=c["length"]
            elif mode=="bundle_combined":
                comps=r["components"];start=comps[0]["bundle_offset"];end=comps[-1]["bundle_offset"]+comps[-1]["length"]
                checksum^=pread_exact(bundle_fds[eid],start,end-start);calls+=1;bytes_requested+=end-start
            else: raise ValueError(mode)
        wall=time.perf_counter()-t0;cpu=time.process_time()-cpu0
        return {"mode":mode,"wall_seconds":wall,"cpu_seconds":cpu,"read_calls":calls,"bytes_requested":bytes_requested,"effective_gib_s":bytes_requested/wall/(1024**3),"checksum":checksum,"f_nocache_all":all(nocache)}
    finally:
        for fd in list(source_fds.values())+list(bundle_fds.values()): os.close(fd)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--manifest",type=Path,required=True);p.add_argument("--source-root",type=Path,required=True);p.add_argument("--layer",type=int,default=40);p.add_argument("--count",type=int,default=64);p.add_argument("--repeats",type=int,default=3);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    lines=a.manifest.read_text().splitlines();objects=[json.loads(x) for x in lines[1:-1]]
    selected=[o for o in objects if o["layer"]==a.layer and o["expert_class"]=="routed"]
    if len(selected)!=256: raise SystemExit("benchmark requires a complete routed layer")
    byid={o["expert"]:o for o in selected};orders={"sequential":list(range(a.count)),"randomized":random.Random(17001).sample(range(256),a.count)}
    results=[]
    for pattern,order in orders.items():
        for mode in ("native_components","bundle_components","bundle_combined"):
            samples=[trial(order,byid,a.manifest.parent,a.source_root,mode) for _ in range(a.repeats)]
            results.append({"pattern":pattern,"mode":mode,"samples":samples,"median_wall_seconds":statistics.median(x["wall_seconds"] for x in samples),"median_gib_s":statistics.median(x["effective_gib_s"] for x in samples),"read_calls":samples[0]["read_calls"],"bytes_requested":samples[0]["bytes_requested"],"f_nocache_all":all(x["f_nocache_all"] for x in samples)})
    doc={"schema":"pulsarmlx.r001.same-device-benchmark.v1","status":"passed","device":"ADATA SX8100NP via OWC Envoy Express","filesystem":"APFS","thunderbolt_link":"40 Gb/s","nvme_link":"PCIe 8.0 GT/s x2","temperature":"unavailable","cache_claim":"F_NOCACHE cache-minimized where reported; not cold-cache","layer":a.layer,"expert_count":a.count,"repeats":a.repeats,"results":results,"peak_rss_bytes":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    if a.out.exists(): raise SystemExit("refuse existing output")
    with a.out.open("x") as f:json.dump(doc,f,sort_keys=True,separators=(",",":"));f.write("\n");f.flush();os.fsync(f.fileno())
    print(json.dumps(doc,sort_keys=True))
if __name__=="__main__":main()
