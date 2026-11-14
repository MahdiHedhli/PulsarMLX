//! Compare all three real storage paths with the unchanged, independently frozen AdmitAll model.
use mlx_expert_ranges::{
    admission_screen::{screen, Policy, Trace},
    residency::{overlap::*, *},
    BoundedSource, ExpertRequest,
};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    cell::Cell,
    fs,
    io::Write,
    path::{Path, PathBuf},
    rc::Rc,
    thread,
};
fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap()
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
}
fn hex(d: &[u8; 32]) -> String {
    d.iter().map(|b| format!("{b:02x}")).collect()
}

enum Storage {
    Direct(CopiedResidency),
    Staged(StagedResidency),
}
impl Storage {
    fn cache(&self) -> &CopiedResidency {
        match self {
            Self::Direct(c) => c,
            Self::Staged(s) => s.cache(),
        }
    }
}
fn compare(
    real: &Real,
    profile: &str,
    name: &str,
    calls: &[Vec<u16>],
    log: &mut Option<fs::File>,
    checksum: &mut Sha256,
) {
    let mut spec = real.template.clone();
    spec["calls"] = json!(calls);
    let trace = Trace::parse(&serde_json::to_vec(&spec).unwrap()).unwrap();
    let model = screen(&trace, Policy::AdmitAll, u64::MAX).unwrap();
    let owner = thread::current().id();
    let mut arms = Vec::new();
    for arm in [None, Some(Mode::Serial), Some(Mode::Overlap)] {
        let cache = real.cache();
        let mut storage = match arm {
            None => Storage::Direct(cache),
            Some(mode) => Storage::Staged(StagedResidency::new(cache, mode, u64::MAX).unwrap()),
        };
        let mut pos = 0;
        let mut call_logs = vec![];
        let callback_count = Rc::new(Cell::new(0));
        for (i, call) in calls.iter().enumerate() {
            let demand: Vec<_> = call
                .iter()
                .map(|e| storage.cache().demand((*e).into()).unwrap())
                .collect();
            let mut consume = |v: TupleView<'_>| {
                assert_eq!(thread::current().id(), owner);
                callback_count.set(callback_count.get() + 1);
                let e = &model.events[pos];
                assert_eq!(
                    (
                        e.call as usize,
                        e.expert as u32,
                        e.slot as u64,
                        e.generation
                    ),
                    (i, v.demand.key.expert, v.slot.0, v.generation)
                );
                assert_eq!(v.demand.binding, model.catalog[e.expert as usize]);
                assert_eq!(v.hashes, &real.hashes[e.expert as usize]);
                for r in 0..3 {
                    for c in 0..3 {
                        assert_eq!(
                            v.components[r][c].len() as u64,
                            model.source.components[3 * r + c]
                        );
                        assert_eq!(
                            <[u8; 32]>::from(Sha256::digest(v.components[r][c])),
                            real.hashes[e.expert as usize][r][c]
                        );
                    }
                }
                pos += 1;
                Ok(())
            };
            match &mut storage {
                Storage::Direct(c) => c.consume(&demand, || false, &mut consume).unwrap(),
                Storage::Staged(s) => {
                    s.consume(&demand, || false, &mut consume).unwrap();
                    s.finish().unwrap();
                    let reader = s.reader_thread().unwrap();
                    assert_ne!(reader, owner);
                    let a = s.activity();
                    assert_eq!(a.spawned, i as u64 + 1);
                    assert_eq!(a.joined, a.spawned);
                    assert!(a.banks_home && !a.outstanding);
                    assert_eq!(a.copy_operations, s.cache().read_calls());
                    assert_eq!(a.copied_bytes, s.cache().requested_bytes());
                    assert_eq!(a.verified_components, a.copy_operations);
                    assert_eq!(a.verified_bytes, a.copied_bytes);
                    assert_eq!(a.discarded_issued_bytes, 0);
                    assert_eq!(a.requests, a.completions);
                    assert!(a.request_high_water <= 1 && a.completion_high_water <= 1);
                    let events = s.events();
                    assert!(events.len() <= 2048);
                    assert_eq!(
                        events.iter().filter(|e| e.phase == "submit").count(),
                        events.iter().filter(|e| e.phase == "installed").count()
                    );
                    let first = pos - call.len();
                    let first_wave = model.events[first].wave;
                    for ev in events {
                        assert!(model.events[first..pos]
                            .iter()
                            .any(|slot| slot.wave - first_wave == ev.wave as u64
                                && slot.expert as u32 == ev.expert));
                        assert_eq!(ev.binding, model.catalog[ev.expert as usize]);
                        assert_eq!(ev.invocation, i as u64 + 1);
                    }
                    if log.is_some() {
                        call_logs.push(json!({"reader":format!("{reader:?}"),"activity":a,"tickets":events.iter().map(|v|(v.phase,v.wave,v.bank,v.generation,v.expert)).collect::<Vec<_>>()}));
                    }
                }
            }
            let c = storage.cache();
            let n = model.events[..pos]
                .iter()
                .filter(|e| e.category == mlx_expert_ranges::admission_screen::Category::M)
                .count() as u64;
            assert_eq!(c.stats().fills, n);
            assert_eq!(c.stats().hits, pos as u64 - n);
            assert_eq!(c.read_calls(), 9 * n);
            assert_eq!(c.requested_bytes(), n * c.ledger().tuple_bytes);
        }
        let c = storage.cache();
        let st = c.stats();
        let mc = model.state.counts;
        assert_eq!(pos, model.events.len());
        assert_eq!(callback_count.get(), pos);
        assert_eq!(
            (st.fills, st.hits, st.evictions, st.consumed),
            (mc.m, mc.r + mc.u_r, mc.persistent_evictions, mc.occurrences)
        );
        assert_eq!(
            c.residents(),
            model
                .state
                .slots
                .map(|s| s.map(|s| (s.expert as u32, s.generation, s.recency)))
        );
        let stats = (
            st.fills,
            st.hits,
            st.evictions,
            st.consumed,
            c.read_calls(),
            c.requested_bytes(),
        );
        let (label, ledger) = match &storage {
            Storage::Direct(_) => (
                "direct",
                json!({"W_cache":c.working_bytes(),"S":c.ledger().tuple_bytes,"M":c.ledger().metadata_bytes}),
            ),
            Storage::Staged(s) => (
                if arm == Some(Mode::Serial) {
                    "serial"
                } else {
                    "overlap"
                },
                json!(s.ledger()),
            ),
        };
        arms.push(json!({"arm":label,"counts":stats,"resident":c.residents(),"ledger":ledger,"calls":call_logs}));
    }
    assert_eq!(arms[1]["ledger"], arms[2]["ledger"]);
    checksum.update(parse_hash(&model.input_sha256).unwrap());
    checksum.update(parse_hash(&model.event_sha256).unwrap());
    checksum.update(parse_hash(&model.state_sha256).unwrap());
    if let Some(file) = log {
        let value = json!({"recipe":profile,"schedule":name,"calls":calls,"model_input":model.input_sha256,"model_events":model.event_sha256,"model_state":model.state_sha256,"owner_thread":format!("{owner:?}"),"arms":arms});
        let bytes = serde_json::to_vec(&value).unwrap();
        assert!(bytes.len() < 1 << 20);
        file.write_all(&bytes).unwrap();
        file.write_all(b"\n").unwrap();
    }
}
#[test]
fn staged_three_paths_match_model_and_all_borrowed_components() {
    let mut log =
        std::env::var_os("STAGING_CORPUS_CAPTURE").map(|p| fs::File::create_new(p).unwrap());
    let mut corpus = Sha256::new();
    let mut named = Sha256::new();
    let mut count = 0;
    let mut extra = 0;
    for profile in ["default", "mixed"] {
        let real = Real::new(profile);
        for n in 1..=4 {
            for word in words(n) {
                for calls in partitions(word) {
                    compare(&real, profile, "exhaustive", &calls, &mut log, &mut corpus);
                    count += 1;
                }
            }
        }
        for (name, calls) in [
            ("six", vec![vec![0, 1, 0, 2, 1, 0]]),
            ("m2b", vec![vec![0, 1, 0, 2, 1, 0], vec![0, 1, 0]]),
            ("protected", vec![vec![0, 1], vec![2, 0]]),
            ("hits", vec![vec![0, 1], vec![1, 0, 0, 1]]),
            ("single", vec![vec![2, 2]]),
            ("long", vec![(0..64).map(|i| i % 3).collect()]),
        ] {
            compare(&real, profile, name, &calls, &mut log, &mut named);
            extra += 1;
        }
    }
    assert_eq!((count, extra), (480, 12));
    println!("staged-corpus combinations={count} arms={} named={extra} named_arms={} corpus={:x} schedules={:x}",count*3,extra*3,corpus.finalize(),named.finalize());
}
#[test]
fn staged_constant_ledger_at_short_long_and_unicode_paths() {
    let tmp = std::env::temp_dir()
        .canonicalize()
        .unwrap()
        .join(format!("stage-paths-{}", std::process::id()));
    fs::create_dir(&tmp).unwrap();
    for profile in ["default", "mixed"] {
        let mut real = Real::new(profile);
        let original = real.root.clone();
        let mut prior = None;
        for part in ["s", "longer-synthetic-checkout", "étapes-東京"] {
            real.root = tmp.join(part).join(original.file_name().unwrap());
            fs::create_dir_all(&real.root).unwrap();
            for n in [
                "config.json",
                "model.safetensors.index.json",
                "model.safetensors",
            ] {
                fs::copy(original.join(n), real.root.join(n)).unwrap();
            }
            let c = real.cache();
            let cache = c.ledger();
            let size = cache.tuple_bytes;
            let expected = cache.working_bytes + 2 * size + (4 << 20);
            let len = real.root.as_os_str().as_encoded_bytes().len() as i64;
            if let Some((prev_len, prev_m)) = prior {
                assert_eq!(cache.metadata_bytes as i64 - prev_m, len - prev_len)
            }
            prior = Some((len, cache.metadata_bytes as i64));
            let s = StagedResidency::new(c, Mode::Serial, expected).unwrap();
            let o = StagedResidency::new(real.cache(), Mode::Overlap, expected).unwrap();
            assert_eq!(json!(s.ledger()), json!(o.ledger()));
            let l = s.ledger();
            assert_eq!(s.working_bytes(), expected);
            assert!(l.control_required <= l.control_bytes);
            assert_eq!(
                l.component_capacities.iter().flatten().sum::<usize>() as u64,
                size
            );
            assert_eq!(l.staging_bytes, 2 * size);
            assert_eq!(s.activity().spawned, 0);
            println!("staged-path {profile} {part} {}", json!(l));
        }
    }
    fs::remove_dir_all(tmp).unwrap();
}
