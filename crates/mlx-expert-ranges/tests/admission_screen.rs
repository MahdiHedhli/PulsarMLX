use mlx_expert_ranges::{
    admission_screen::*,
    residency::{parse_hash, ContentAuthority, CopiedResidency, TupleHashes},
    BoundedSource, ExpertRequest,
};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeSet,
    fs,
    path::{Path, PathBuf},
};

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap()
}
fn fixture(name: &str) -> Value {
    let data = fs::read(root().join("fixtures/admission-screen").join(name)).unwrap();
    assert!(data.len() <= LIMIT);
    serde_json::from_slice(&data).unwrap()
}
fn encoded(v: &Value) -> Vec<u8> {
    serde_json::to_vec(v).unwrap()
}
fn trace(template: &Value, calls: &[Vec<u16>]) -> Trace {
    let mut value = template.clone();
    value["calls"] = json!(calls);
    Trace::parse(&encoded(&value)).unwrap()
}
fn words(length: usize) -> impl Iterator<Item = Vec<u16>> {
    (0..3usize.pow(length as u32)).map(move |mut code| {
        let mut w = vec![0; length];
        for x in w.iter_mut().rev() {
            *x = (code % 3) as u16;
            code /= 3;
        }
        w
    })
}
fn partitions(w: Vec<u16>) -> [Vec<Vec<u16>>; 2] {
    let singles = w.iter().map(|&x| vec![x]).collect();
    [vec![w], singles]
}
fn domain(c: &Value) -> String {
    let mut h = Sha256::new();
    h.update(b"admission-screen.domain/1\0");
    for key in ["content", "metadata"] {
        h.update(parse_hash(c[key].as_str().unwrap()).unwrap())
    }
    for v in ["layer", "d", "h", "group"]
        .iter()
        .map(|k| &c[*k])
        .chain(c["bits"].as_array().unwrap())
    {
        h.update((v.as_u64().unwrap() as u32).to_le_bytes());
    }
    for n in c["components"].as_array().unwrap() {
        h.update(n.as_u64().unwrap().to_le_bytes())
    }
    format!("{:x}", h.finalize())
}
#[test]
fn admission_screen_exhaustive_independent_reference() {
    let template = fixture("template.json");
    let golden = fixture("expected.json");
    let mut hash = Sha256::new();
    let mut cases = 0;
    for len in 1..=6 {
        for word in words(len) {
            for calls in partitions(word) {
                let t = trace(&template, &calls);
                for policy in [Policy::AdmitAll, Policy::TwoHit] {
                    let r = screen(&t, policy, u64::MAX).unwrap();
                    for hex in [&r.input_sha256, &r.event_sha256, &r.state_sha256] {
                        hash.update(parse_hash(hex).unwrap());
                    }
                    let c = r.state.counts;
                    for n in [
                        c.r,
                        c.m,
                        c.u_r,
                        c.u_t,
                        c.admitted_fills,
                        c.persistent_evictions,
                    ] {
                        hash.update(n.to_le_bytes());
                    }
                    cases += 1;
                }
            }
        }
    }
    let observed = format!("{:x}", hash.finalize());
    assert_eq!(cases, 4368);
    assert_eq!(golden["exhaustive"]["sha256"], observed);
    println!("model/reference {cases} runs {observed}");
}
#[test]
fn admission_screen_named_journals_and_hand_computed_outcomes() {
    let schedules = fixture("schedules.json");
    let expected = fixture("expected.json");
    let template = fixture("template.json");
    for (name, v) in schedules.as_object().unwrap() {
        let calls: Vec<Vec<u16>> = serde_json::from_value(v.clone()).unwrap();
        let t = trace(&template, &calls);
        let quota = t.ledger().unwrap().logical_total;
        let mut previous = None;
        for policy in [Policy::AdmitAll, Policy::TwoHit] {
            let report = screen(&t, policy, quota).unwrap();
            let metrics = &report.metrics;
            let label = format!("{policy:?}");
            let want = &expected["case_reports"][name][&label];
            let actual = serde_json::to_value(&report).unwrap();
            for (k, v) in want.as_object().unwrap() {
                assert_eq!(&actual[k], v, "{name}/{label}/{k}")
            }
            assert!(screen(&t, policy, quota - 1).is_err());
            assert!(report.encode(7).is_err());
            let count = report.state.counts;
            assert_eq!(count.r + count.m + count.u_r + count.u_t, count.occurrences);
            assert_eq!(metrics.component_read_calls, 9 * count.m);
            assert_eq!(metrics.issued_bytes, count.m * 13824);
            assert_eq!(
                report.events.len(),
                calls.iter().map(Vec::len).sum::<usize>()
            );
            let journal: Vec<_> = report.events.iter().map(|e| e.expert).collect();
            assert_eq!(journal, calls.iter().flatten().copied().collect::<Vec<_>>());
            if policy == Policy::TwoHit {
                assert_eq!(previous.as_ref(), Some(&report.ledger));
                match name.as_str() {
                    "win" => assert_eq!(count.m, 8),
                    "tie" => assert_eq!(count.m, 2),
                    "loss" => assert_eq!(count.m, 2),
                    "same_wave" => {
                        assert_eq!((count.m, count.u_t, count.admitted_fills), (1, 2, 0));
                        assert_eq!(report.state.history, [0]);
                    }
                    "fifo65" => {
                        assert_eq!(
                            (
                                count.history_evictions,
                                count.history_insertions,
                                count.admitted_fills
                            ),
                            (2, 66, 1)
                        );
                        assert_eq!(report.state.slots[0].unwrap().expert, 64);
                    }
                    "evicted_then_first" => {
                        assert_eq!(report.events.last().unwrap().kind, Kind::Transient);
                        assert!(report.state.history.contains(&0));
                    }
                    _ => (),
                }
                let resident: BTreeSet<_> = report
                    .state
                    .slots
                    .iter()
                    .flatten()
                    .map(|s| s.expert)
                    .collect();
                assert!(report.state.history.iter().all(|s| !resident.contains(s)));
            } else {
                match name.as_str() {
                    "win" => assert_eq!(count.m, 10),
                    "loss" => assert_eq!(count.m, 1),
                    "tie" => assert_eq!(count.m, 2),
                    _ => (),
                }
            }
            previous = Some(report.ledger);
        }
    }
}
struct Real {
    root: PathBuf,
    recipe: Value,
    template: Value,
    hashes: Vec<TupleHashes>,
    req: ExpertRequest,
}
impl Real {
    fn new(profile: &str) -> Self {
        let dir = root().join("fixtures/resident-expert-mlp");
        let m: Value =
            serde_json::from_slice(&fs::read(dir.join("manifest.json")).unwrap()).unwrap();
        let recipe = m["recipes"][profile].clone();
        let r = dir.join(recipe["name"].as_str().unwrap());
        let planes = recipe["planes"][0].as_array().unwrap();
        let req = ExpertRequest {
            expert: 0,
            experts: 3,
            d: 128,
            h: 64,
            bits: std::array::from_fn(|i| planes[i]["bits"].as_u64().unwrap() as u32),
            group_size: 64,
            modules: std::array::from_fn(|i| planes[i]["module"].as_str().unwrap().into()),
        };
        let hashes = (0..3)
            .map(|e| {
                std::array::from_fn(|i| {
                    std::array::from_fn(|c| {
                        parse_hash(recipe["planes"][e][i]["sha256"][c].as_str().unwrap()).unwrap()
                    })
                })
            })
            .collect();
        let lengths: Vec<_> = planes
            .iter()
            .flat_map(|p| {
                p["ranges"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|v| v["len"].as_u64().unwrap())
            })
            .collect();
        let mut real = Self {
            root: r,
            recipe,
            req,
            hashes,
            template: Value::Null,
        };
        let c = json!({"content":real.recipe["content"],"metadata":real.recipe["metadata"],"layer":0,"d":128,"h":64,"group":64,"bits":real.req.bits,"components":lengths,"persistent_slots":2});
        let d = domain(&c);
        let cache = real.cache();
        let cat: Vec<_> = (0..3)
            .map(
                |i| json!({"expert":i,"domain":d,"binding":hex(&cache.demand(i).unwrap().binding)}),
            )
            .collect();
        real.template = json!({"schema":"pulsarmlx.admission-screen.input/1","provenance_kind":"synthetic","class":c,"catalog":cat,"calls":[[0]]});
        real
    }
    fn cache(&self) -> CopiedResidency {
        CopiedResidency::new(
            BoundedSource::open(&self.root).unwrap(),
            0,
            &self.req,
            ContentAuthority {
                checkpoint: self.recipe["name"].as_str().unwrap(),
                metadata: self.recipe["metadata"].as_str().unwrap(),
                content: parse_hash(self.recipe["content"].as_str().unwrap()).unwrap(),
                hashes: &self.hashes,
            },
            u64::MAX,
            0,
        )
        .unwrap()
    }
    fn compare(&self, calls: &[Vec<u16>], proof: &mut Sha256) -> (u64, u64, u64, u64) {
        let mut actual = self.cache();
        let t = trace(&self.template, calls);
        let report = screen(&t, Policy::AdmitAll, u64::MAX).unwrap();
        let mut pos = 0;
        for (i, call) in calls.iter().enumerate() {
            let demand: Vec<_> = call
                .iter()
                .map(|&e| actual.demand(e.into()).unwrap())
                .collect();
            actual
                .consume(
                    &demand,
                    || false,
                    |view| {
                        let event = &report.events[pos];
                        let expert = view.demand.key.expert as usize;
                        assert_eq!(
                            (
                                event.expert as usize,
                                event.call as usize,
                                event.kind,
                                event.slot as u64,
                                event.generation
                            ),
                            (expert, i, Kind::Persistent, view.slot.0, view.generation)
                        );
                        assert_eq!(report.catalog[expert], view.demand.binding);
                        assert_eq!(*view.hashes, self.hashes[expert]);
                        for r in 0..3 {
                            for c in 0..3 {
                                let b = view.components[r][c];
                                assert_eq!(b.len() as u64, report.source.components[r * 3 + c]);
                                assert_eq!(
                                    <[u8; 32]>::from(Sha256::digest(b)),
                                    self.hashes[expert][r][c]
                                );
                            }
                        }
                        pos += 1;
                        Ok(())
                    },
                )
                .unwrap();
            let events = &report.events[..pos];
            let misses = events.iter().filter(|e| e.category == Category::M).count() as u64;
            assert_eq!(actual.stats().consumed, pos as u64);
            assert_eq!(actual.stats().fills, misses);
            assert_eq!(actual.stats().hits, pos as u64 - misses);
            assert_eq!(actual.stats().evictions, misses.saturating_sub(2));
            assert_eq!(actual.read_calls(), misses * 9);
            assert_eq!(
                actual.requested_bytes(),
                misses * actual.ledger().tuple_bytes
            );
        }
        actual.finish().unwrap();
        let c = report.state.counts;
        assert_eq!(actual.stats().hits, c.r + c.u_r);
        assert_eq!(c.u_t, 0);
        assert_eq!(actual.requested_bytes(), report.metrics.issued_bytes);
        assert_eq!(report.events.len(), pos);
        proof.update(parse_hash(&report.input_sha256).unwrap());
        proof.update(parse_hash(&report.event_sha256).unwrap());
        proof.update(parse_hash(&report.state_sha256).unwrap());
        (
            actual.read_calls(),
            actual.requested_bytes(),
            actual.working_bytes(),
            report.ledger.logical_total,
        )
    }
}
fn hex(d: &[u8; 32]) -> String {
    d.iter().map(|b| format!("{b:02x}")).collect()
}
#[test]
fn admission_screen_control_matches_actual_copied_residency() {
    let mut digest = Sha256::new();
    let named = fixture("schedules.json");
    for profile in ["default", "mixed"] {
        let real = Real::new(profile);
        let mut cases = 0;
        for len in 1..=4 {
            for word in words(len) {
                for calls in partitions(word) {
                    real.compare(&calls, &mut digest);
                    cases += 1;
                }
            }
        }
        assert_eq!(cases, 240);
        for name in [
            "m2a",
            "m2b",
            "m3",
            "protect_late_hit",
            "same_wave",
            "evicted_then_first",
        ] {
            let calls: Vec<Vec<u16>> = serde_json::from_value(named[name].clone()).unwrap();
            let (reads, bytes, w, model) = real.compare(&calls, &mut digest);
            println!("actual {profile} {name} calls={} reads={reads} issued_bytes={bytes} real_W={w} model_envelope={model}",calls.len());
        }
    }
    println!(
        "real-cache differential 492 runs; cumulative trace/event/state digest {:x}",
        digest.finalize()
    );
}
#[test]
fn admission_screen_input_limits_and_refusals() {
    let base = fixture("template.json");
    let b = encoded(&base);
    let string = String::from_utf8(b.clone()).unwrap();
    for malformed in [
        b[..b.len() - 1].to_vec(),
        vec![b' '; LIMIT + 1],
        b"[]".to_vec(),
        string.replacen("{", "{\"calls\":[],", 1).into_bytes(),
        string
            .replacen("\"d\":128", "\"d\":128,\"d\":128", 1)
            .into_bytes(),
        string
            .replacen("\"expert\":0", "\"expert\":NaN", 1)
            .into_bytes(),
    ] {
        assert!(Trace::parse(&malformed).is_err());
    }
    for (pointer, bad) in [
        ("/schema", json!("old")),
        ("/provenance_kind", json!("authentic")),
        ("/class/group", json!(32)),
        ("/class/bits/0", json!(3)),
        ("/class/components/0", json!(u64::MAX)),
        ("/class/components/1", json!(0)),
        ("/catalog/0/domain", json!("0".repeat(64))),
        ("/catalog/1/expert", json!(0)),
        ("/catalog/0/binding", json!("F".repeat(64))),
        ("/catalog/1/binding", base["catalog"][0]["binding"].clone()),
        ("/calls", json!([[4096]])),
        ("/calls", json!([[]])),
        ("/calls", json!([])),
        ("/calls", json!([vec![0; 65]])),
        ("/class", json!([])),
        ("/catalog/0", json!([0, 0, 0])),
    ] {
        let mut d = base.clone();
        *d.pointer_mut(pointer).unwrap() = bad;
        assert!(Trace::parse(&encoded(&d)).is_err(), "{pointer}");
    }
    for part in ["", "/class", "/catalog/0"] {
        let mut d = base.clone();
        d.pointer_mut(part).unwrap()["unknown"] = json!(false);
        assert!(Trace::parse(&encoded(&d)).is_err());
    }
    let mut doc = base;
    let domain = doc["catalog"][0]["domain"].clone();
    doc["catalog"] = json!((0..4096u32)
        .map(|i| json!({"expert":i,"binding":format!("{i:064x}"),"domain":domain}))
        .collect::<Vec<_>>());
    doc["calls"] = json!(vec![vec![4095u16; 16]; 4096]);
    let max = Trace::parse(&encoded(&doc)).unwrap();
    let report = screen(&max, Policy::TwoHit, u64::MAX).unwrap();
    assert_eq!(report.events.len(), 65536);
    assert!(report.encode(1024).is_err());
    let full = report.encode(LIMIT).unwrap();
    assert!(full.len() <= LIMIT);
    doc["calls"][0].as_array_mut().unwrap().push(json!(0));
    assert!(Trace::parse(&encoded(&doc)).is_err());
    doc["calls"] = json!(vec![vec![0]; 4097]);
    assert!(Trace::parse(&encoded(&doc)).is_err());
    doc["calls"] = json!([[0]]);
    doc["catalog"]
        .as_array_mut()
        .unwrap()
        .push(json!({"expert":4096,"binding":format!("{:064x}",4096),"domain":domain}));
    assert!(Trace::parse(&encoded(&doc)).is_err());
    doc["catalog"].as_array_mut().unwrap().pop();
    doc["calls"] = json!([vec![0; 64]]);
    assert!(Trace::parse(&encoded(&doc)).is_ok());
    assert!("LFU".parse::<Policy>().is_err());
}
