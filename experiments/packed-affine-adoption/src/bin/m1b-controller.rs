use mlx_native_affine::harness::{child_env, ChildOutcome};
use packed_affine_adoption::{
    file_sha256,
    policy::{self, Screen},
};
use serde_json::{json, Value as V};
use sha2::{Digest, Sha256};
use std::{
    ffi::OsStr,
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    os::unix::{
        fs::{DirBuilderExt, MetadataExt, OpenOptionsExt},
        process::{CommandExt, ExitStatusExt},
    },
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    thread,
    time::{Duration, Instant},
};
type R<T> = Result<T, String>;
const A: &str = "full-positive-A-gate";
const B: &str = "full-positive-B-up";
const PROFILE: &[u8] = include_bytes!("../../m1b-source-profile-v1.json");
const HELPER: &[u8] = include_bytes!("../../tools/m1b_admission.py");
fn bad<T>(why: &str) -> R<T> {
    Err(why.into())
}
fn check(ok: bool, why: &str) -> R<()> {
    if ok {
        Ok(())
    } else {
        bad(why)
    }
}
fn io(e: std::io::Error) -> String {
    e.to_string()
}
fn sha(b: &[u8]) -> String {
    format!("{:x}", Sha256::digest(b))
}
fn string(v: &V) -> R<&str> {
    v.as_str().ok_or_else(|| "expected string".into())
}
fn val(b: &[u8]) -> R<V> {
    serde_json::from_slice(b).map_err(|e| e.to_string())
}
fn raw(p: &Path, limit: u64) -> R<Vec<u8>> {
    let m = p.symlink_metadata().map_err(io)?;
    check(
        m.is_file() && m.len() <= limit,
        "unbounded or nonregular file",
    )?;
    let mut b = vec![];
    File::open(p)
        .map_err(io)?
        .take(limit + 1)
        .read_to_end(&mut b)
        .map_err(io)?;
    check(b.len() as u64 <= limit, "file grew")?;
    Ok(b)
}
fn canon(p: &Path) -> R<()> {
    check(
        p.is_absolute() && p.canonicalize().map_err(io)? == p,
        "canonical original path required",
    )
}
fn write_new(p: &Path, v: &V) -> R<String> {
    let mut f = new_file(p)?;
    let b = serde_json::to_vec_pretty(v).map_err(|e| e.to_string())?;
    f.write_all(&b).map_err(io)?;
    f.sync_all().map_err(io)?;
    Ok(sha(&b))
}
fn new_file(p: &Path) -> R<File> {
    OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(p)
        .map_err(io)
}
fn pos(v: &V) -> R<f64> {
    v.as_f64()
        .filter(|n| n.is_finite() && *n > 0.)
        .ok_or_else(|| "invalid positive sample".into())
}
fn mem(v: &V) -> R<()> {
    let a = v.as_array().ok_or("memory observation missing")?;
    check(
        a.len() == 3
            && a.iter().all(V::is_u64)
            && a[0].as_u64() <= Some(32 << 20)
            && a[2].as_u64() <= Some(32 << 20),
        "observed active/peak memory limit",
    )
}
fn left(end: Instant, max: Duration) -> R<Duration> {
    end.checked_duration_since(Instant::now())
        .filter(|v| !v.is_zero())
        .map(|v| v.min(max))
        .ok_or_else(|| "DEADLINE".into())
}

#[derive(Clone, Debug)]
struct Arm {
    stage: &'static str,
    mode: &'static str,
    case: &'static str,
    method: &'static str,
    count: usize,
    pair: usize,
}
impl Arm {
    fn config(&self, qualified: &V) -> R<V> {
        check(
            matches!(
                (self.case, self.stage),
                (
                    A,
                    "baseline" | "recalibration" | "primary" | "followup" | "resident"
                ) | (B, "heldout")
            ),
            "unreleased case/stage",
        )?;
        check(
            matches!(
                (self.mode, self.count),
                ("fill", policy::FILL | policy::FILL_RETRY)
                    | ("resident", policy::RESIDENT | policy::RESIDENT_RETRY)
            ) && matches!(self.method, "adopted" | "copied"),
            "timing arm",
        )?;
        let calibrating = matches!(self.stage, "baseline" | "recalibration");
        check(
            if calibrating {
                self.method == "copied" && self.pair < 6
            } else {
                self.pair < 3 && (self.stage == "resident") == (self.mode == "resident")
            },
            "fixed schedule arm",
        )?;
        let mut c = qualified["config"].clone();
        let fields = [
            "arm",
            "binary_sha256",
            "dependency_manifest_sha256",
            "fixture_manifest_sha256",
            "fixture_root",
            "generator_hashes",
            "host",
            "metadata_identities",
            "mode",
            "native_libraries",
            "sequence",
            "source_commit",
            "source_tree",
        ];
        check(
            c.as_object().is_some_and(|m| {
                m.len() == fields.len() && fields.iter().all(|k| m.contains_key(*k))
            }),
            "closed retained timing template",
        )?;
        check(
            c["mode"] == "diagnostic" && c["sequence"] == json!([self.case]),
            "qualified case config",
        )?;
        c["mode"] = json!(self.mode);
        c["arm"] = json!(self.method);
        c["operations"] = json!(self.count);
        Ok(c)
    }
}
trait Campaign {
    fn arm(&mut self, a: Arm) -> R<f64>;
    fn record(&mut self, name: &str, v: V) -> R<()>;
}
fn schedule(c: &mut impl Campaign) -> R<&'static str> {
    let mut settings = vec![];
    for (mode, counts) in [
        ("fill", [policy::FILL, policy::FILL_RETRY]),
        ("resident", [policy::RESIDENT, policy::RESIDENT_RETRY]),
    ] {
        let mut accepted = None;
        for (try_no, count) in counts.into_iter().enumerate() {
            let mut means = [0.; 6];
            for (i, v) in means.iter_mut().enumerate() {
                *v = c.arm(Arm {
                    stage: if try_no == 0 {
                        "baseline"
                    } else {
                        "recalibration"
                    },
                    mode,
                    case: A,
                    method: "copied",
                    count,
                    pair: i,
                })?
            }
            let durations = means.map(|v| v * count as f64);
            let noise = policy::noise(means, durations);
            c.record(&format!("{mode}-calibration-{try_no}"),json!({"count":count,"means":means,"durations":durations,"noise":noise.as_ref().ok(),"refusal":noise.as_ref().err()}))?;
            match noise {
                Ok(e) => {
                    accepted = Some((count, e));
                    break;
                }
                Err("unsuitable-baseline") => {}
                Err(e) => return bad(e),
            }
        }
        if let Some(v) = accepted {
            settings.push(v)
        } else {
            return Ok("INCONCLUSIVE");
        }
    }
    let [(fill, e), (res, er)] = settings[..] else {
        return bad("missing calibration");
    };
    c.record(
        "calibration-freeze",
        json!({"fill":[fill as f64,e],"resident":[res as f64,er]}),
    )?;
    fn pairs(
        c: &mut impl Campaign,
        stage: &'static str,
        cid: &'static str,
        mode: &'static str,
        count: usize,
        reverse: bool,
    ) -> R<[f64; 3]> {
        let mut gains = [0.; 3];
        for (i, gain) in gains.iter_mut().enumerate() {
            let mut t = [0.; 2];
            let flip = (i % 2 == 1) ^ reverse;
            for j in if flip { [1, 0] } else { [0, 1] } {
                t[j] = c.arm(Arm {
                    stage,
                    case: cid,
                    method: ["copied", "adopted"][j],
                    count,
                    mode,
                    pair: i,
                })?;
            }
            *gain = 1. - t[1] / t[0];
        }
        c.record(stage, json!({"gains":gains}))?;
        Ok(gains)
    }
    let g = pairs(c, "primary", A, "fill", fill, false)?;
    match policy::primary(g, e)? {
        Screen::Pass => {}
        Screen::Stop => return Ok("NO_PROMOTION"),
        Screen::Followup => {
            let h = pairs(c, "followup", A, "fill", fill, true)?;
            if !policy::followup([g[0], g[1], g[2], h[0], h[1], h[2]], e)? {
                return Ok("NO_PROMOTION");
            }
        }
    }
    if policy::primary(pairs(c, "heldout", B, "fill", fill, false)?, e)? != Screen::Pass {
        return Ok("NO_PROMOTION");
    }
    let regressions = pairs(c, "resident", A, "resident", res, false)?.map(|x| -x);
    c.record(
        "resident-decision",
        json!({"regressions":regressions,"noise":er}),
    )?;
    Ok(if policy::resident(regressions, er)? {
        "PASS_EXPERIMENTAL_ONLY"
    } else {
        "NO_PROMOTION"
    })
}

// Timing outputs are deliberately empty. Original diagnostic receipts supply
// expected projection digests and read identities, never timing samples.
fn admit_report(a: &Arm, q: &V, c: &V, ch: &str, r: &V, events: &[V], outcome: &V) -> R<f64> {
    check(
        outcome["outcome"] == "EXIT_STATUS 0"
            && outcome["reaped"] == true
            && outcome["config_sha256"] == ch
            && outcome["binary_sha256"] == c["binary_sha256"],
        "child process binding",
    )?;
    check(
        a.config(q)? == *c
            && r["config_sha256"] == ch
            && r["outputs"] == json!([])
            && r.get("error").is_none()
            && r.get("bridge_diagnostic").is_none(),
        "timing report/config",
    )?;
    let ad = usize::from(a.method == "adopted");
    let t = a.count + policy::WARMUPS;
    let f = if a.mode == "resident" { 2 } else { t };
    let total = (6 + ad) * f + t + ad;
    let life = json!({"created":total,"freed":total,"live":0,"parent_counts":[ad,ad],"view_counts":[(1+ad)*f,(1+ad)*f],"output_counts":[t,t],"retired_parents":ad,"completed_callbacks":ad,"early_free_count":0,"quarantine":false});
    check(
        r["lifetime"] == life
            && r["adoption"]
                == json!({"method":if ad==1{"managed-flat-parent"}else{"copied"},"pointer_identity":ad==1,"registered_bytes":ad*8388608}),
        "ownership/registration",
    )?;
    check(
        r["io"]
            == json!({"requested_bytes":4718592*f,"range_attempts":3*f,"read_policy":"buffered-exact","physical_device_bytes":null,"overread_bytes":0})
            && r["copies"]
                == json!({"packed_import_bytes":(1-ad)*4194304*f,"metadata_raw_bytes":524288*f,"metadata_widening_bytes":1048576*f,"output_bytes":8192*t,"layout_materialization_bytes":null,"unknown_materialization":true}),
        "timing read/copy accounting",
    )?;
    let prov = json!({"native_libraries":c["native_libraries"],"binary_sha256":c["binary_sha256"],"source_commit":c["source_commit"],"source_tree":c["source_tree"],"native_prefix":"<NATIVE_PREFIX>","TF32":false,"loaded_images_verified":true});
    check(
        r["provenance"] == prov
            && r["source_binding"]
                == json!({"source_commit":c["source_commit"],"source_tree":c["source_tree"],"dependency_manifest_sha256":c["dependency_manifest_sha256"],"generator_hashes":c["generator_hashes"]})
            && r["frozen_host"] == c["host"]
            && r["identity"]
                == json!({"fixture_manifest_sha256":c["fixture_manifest_sha256"],"contract_sha256":packed_affine_adoption::CONTRACT}),
        "child source/native provenance",
    )?;
    check(
        events.len() == 3 + t + f
            && events[0] == json!({"phase":"provenance","value":prov})
            && events[1] == q["preflight"],
        "event population/preflight",
    )?;
    let s = &events[2];
    check(
        s["phase"] == "setup"
            && s["adopted"] == (ad == 1)
            && s["page"] == 16384
            && s["registered_bytes"] == 8388608
            && s["rust_capacity"] == 9437184
            && s["live_bound"] == 20512768
            && s["stream_id"].is_i64()
            && s["max_buffer_length"] == q["setup"]["max_buffer_length"]
            && r["host"]
                == json!({"vm_page_bytes":s["page"],"max_buffer_length":s["max_buffer_length"]}),
        "setup geometry/host",
    )?;
    mem(&s["memory"])?;
    let m = &r["memory"];
    mem(&m["raw_mlx_active_cache_peak"])?;
    check(
        m == &json!({"raw_mlx_active_cache_peak":m["raw_mlx_active_cache_peak"],"mlx_memory_limit_requested":33554432,"mlx_cache_limit_requested":33554432,"native_limit_calls_status":0,"live_working_bound":s["live_bound"],"combined_reservation":100663296,"adopted_capacity_constant_within_reset":ad*8388608,"reset_interval":"after four warmups","clear_events":1,"deduplicated_physical_usage":null,"rust_capacity":9437184,"adopted_overlap":ad*8388608,"wiring":"unknown"}),
        "memory accounting",
    )?;
    let timing = &r["timing"];
    let samples = timing["samples"].as_array().ok_or("missing samples")?;
    check(samples.len() == a.count, "sample count")?;
    let mut j = 3;
    let mut sum = 0.;
    for i in 0..t {
        let slot = i % 2;
        let generation = if a.mode == "resident" { 1 } else { i / 2 + 1 };
        if i < f {
            let v = &events[j];
            j += 1;
            let mut expected = q["fill"].clone();
            expected["slot"] = json!(slot);
            expected["generation"] = json!(generation);
            pos(&v["view_setup_seconds"])?;
            expected["view_setup_seconds"] = v["view_setup_seconds"].clone();
            check(*v == expected, "verified-fill identity/order")?;
        }
        let op = &events[j];
        j += 1;
        let secs = pos(&op["seconds"])?;
        mem(&op["memory"])?;
        check(
            op == &json!({"phase":"operation","iteration":i,"warmup":i<policy::WARMUPS,"id":a.case,"slot":slot,"generation":generation,"seconds":op["seconds"],"memory":op["memory"],"output_sha256":q["output"]}),
            "operation chronology/output",
        )?;
        if i == 0 {
            check(
                op["seconds"] == timing["first_operation"],
                "first operation",
            )?
        }
        if i >= policy::WARMUPS {
            check(
                samples[i - policy::WARMUPS] == op["seconds"],
                "ordered sample duration",
            )?;
            sum += secs;
        }
    }
    let startup = pos(&timing["setup_seconds"])? + pos(&timing["first_operation"])?;
    let recorded = pos(&timing["startup_through_first_projection"])?;
    check(
        (startup - recorded).abs() <= 4. * f64::EPSILON * startup
            && pos(&timing["total"])? >= pos(&timing["block_wall_seconds"])?
            && sum.is_finite(),
        "timing boundaries",
    )?;
    Ok(sum / a.count as f64)
}
// The group belongs only to this invocation. The handle stays owned through
// observation failures; an unconfirmed reap is never reported as a timeout pass.
fn observe(
    child: &mut Child,
    end: Instant,
    started: Instant,
    mut poll: impl FnMut(&mut Child) -> std::io::Result<Option<std::process::ExitStatus>>,
) -> V {
    let pid = child.id();
    let (reason, timed) = loop {
        match poll(child) {
            Ok(Some(s)) => {
                let o = if let Some(n) = s.code() {
                    ChildOutcome::Exited(n)
                } else {
                    ChildOutcome::Signaled(s.signal().unwrap_or(-1))
                };
                return json!({"pid":pid,"outcome":o.describe(),"reaped":true,"launch_to_reap_seconds":started.elapsed().as_secs_f64()});
            }
            Ok(None) => {}
            Err(e) => {
                if e.raw_os_error() == Some(libc::ECHILD) {
                    return json!({"pid":pid,"outcome":"WAIT_ERROR","reason":e.to_string(),"reaped":false,"effects":"unknown"});
                }
                break (e.to_string(), false);
            }
        }
        if Instant::now() >= end {
            break ("watchdog".to_owned(), true);
        }
        thread::sleep(Duration::from_millis(5).min(end.saturating_duration_since(Instant::now())));
    };
    // SAFETY: process_group(0) created this group; do not signal unrelated PIDs.
    let kill = unsafe { libc::kill(-(pid as i32), libc::SIGKILL) };
    let stop = Instant::now() + Duration::from_secs(5);
    loop {
        match child.try_wait() {
            Ok(Some(s)) => {
                let o = if timed && kill == 0 {
                    ChildOutcome::Timeout {
                        elapsed_ms: started.elapsed().as_millis(),
                        reaped_signal: s.signal(),
                    }
                    .describe()
                } else {
                    "WAIT_ERROR".into()
                };
                return json!({"pid":pid,"outcome":o,"reason":reason,"kill_status":kill,"reaped":true,"launch_to_reap_seconds":started.elapsed().as_secs_f64()});
            }
            Ok(None) => {}
            Err(e) if e.kind() == std::io::ErrorKind::Interrupted => {}
            Err(_) => break,
        }
        if Instant::now() >= stop {
            break;
        }
        thread::sleep(Duration::from_millis(10));
    }
    json!({"pid":pid,"outcome":"CLEANUP_UNCONFIRMED","reason":reason,"kill_status":kill,"reaped":false,"effects":"unknown"})
}
fn spawn(cmd: &mut Command, end: Instant, capture: bool) -> R<(V, Vec<u8>)> {
    left(end, Duration::from_secs(120))?;
    let st = Instant::now();
    cmd.process_group(0).stdin(Stdio::null());
    if capture {
        cmd.stdout(Stdio::piped());
    }
    let mut child = match cmd.spawn() {
        Ok(c) => c,
        Err(e) => {
            return Ok((
                json!({"outcome":ChildOutcome::SpawnFailed(e.to_string()).describe(),"reaped":false}),
                vec![],
            ))
        }
    };
    let pipe = child.stdout.take().map(|o| {
        thread::spawn(move || {
            let mut buf = Vec::new();
            o.take(2 * 1024 * 1024 + 1)
                .read_to_end(&mut buf)
                .map(|_| buf)
        })
    });
    let obs = observe(&mut child, end, st, Child::try_wait);
    let bytes = if obs["reaped"] == true {
        match pipe {
            Some(t) => t.join().map_err(|_| "inspector pipe")?.map_err(io)?,
            None => vec![],
        }
    } else {
        vec![]
    };
    check(bytes.len() <= 2 * 1024 * 1024, "inspector output overflow")?;
    Ok((obs, bytes))
}
struct Inspector {
    ap: PathBuf,
    digest: String,
    helper: PathBuf,
    py: PathBuf,
    exe: PathBuf,
}
impl Inspector {
    fn new(ap: &Path, digest: &str) -> R<Self> {
        check(
            std::env::var("PULSAR_ADOPTION_PHASE").as_deref() == Ok("m1b"),
            "phase=m1b required",
        )?;
        for (k, _) in std::env::vars_os() {
            let k = k.to_string_lossy();
            check(
                !k.starts_with("GIT_")
                    && !k.starts_with("DYLD_")
                    && !matches!(
                        k.as_ref(),
                        "LD_LIBRARY_PATH"
                            | "LD_PRELOAD"
                            | "PYTHONPATH"
                            | "PYTHONHOME"
                            | "MLX_PREFIX"
                            | "MLX_C_PREFIX"
                            | "PULSAR_REQUIRE_NATIVE_MLX"
                            | "PULSAR_F020_NATIVE_PREFIX"
                            | "PULSARMLX_MODEL_GGUF"
                            | "GITHUB_ACTIONS"
                            | "PULSAR_ADOPTION_HOST_ROLE"
                            | "PULSAR_ADOPTION_CAMPAIGN"
                    ),
                "unsafe controller environment",
            )?
        }
        canon(ap)?;
        let bytes = raw(ap, 2 << 20)?;
        check(sha(&bytes) == digest, "authority digest")?;
        let a = val(&bytes)?;
        let p = &a["paths"];
        let prof = val(PROFILE)?;
        let exe = std::env::current_exe()
            .map_err(io)?
            .canonicalize()
            .map_err(io)?;
        check(
            exe.as_os_str() == OsStr::new(string(&p["controller"])?),
            "controller path",
        )?;
        let x = Path::new(string(&a["sources"]["S"]["root"])?)
            .join("experiments/packed-affine-adoption");
        let helper = x.join("tools/m1b_admission.py");
        canon(&helper)?;
        canon(&x.join("m1b-source-profile-v1.json"))?;
        check(
            raw(&helper, 1 << 20)? == HELPER
                && raw(&x.join("m1b-source-profile-v1.json"), 1 << 20)? == PROFILE,
            "compiled helper/profile binding",
        )?;
        let py = PathBuf::from(string(&p["python"])?);
        canon(&py)?;
        check(
            file_sha256(&py)? == string(&prof["python"])?,
            "retained Python",
        )?;
        Ok(Self {
            ap: ap.into(),
            digest: digest.into(),
            helper,
            py,
            exe,
        })
    }
    fn admit(&self, stage: &str, end: Instant) -> R<V> {
        let again = Self::new(&self.ap, &self.digest)?;
        check(
            self.py == again.py && self.helper == again.helper,
            "inspector drift",
        )?;
        let mut cmd = Command::new(&self.py);
        cmd.env_clear()
            .env("PATH", "/usr/bin:/bin")
            .env("PULSAR_ADOPTION_PHASE", "m1b")
            .args(["-I", "-S", "-B", "-X", "pycache_prefix=/dev/null"])
            .arg(&self.helper)
            .arg(&self.ap)
            .arg(&self.digest)
            .arg(stage)
            .arg(&self.exe);
        let (o, b) = spawn(&mut cmd, end, true)?;
        check(
            o["outcome"] == "EXIT_STATUS 0" && o["reaped"] == true,
            &format!("inspector: {o}"),
        )?;
        val(&b)
    }
}
fn root_id(root: &Path) -> R<(u64, u64)> {
    canon(root)?;
    let m = fs::symlink_metadata(root).map_err(io)?;
    check(m.is_dir(), "missing owned directory")?;
    Ok((m.dev(), m.ino()))
}
fn still_owned(root: &Path, id: (u64, u64)) -> R<()> {
    check(
        root_id(root)? == id,
        "timing root replaced; use external capture",
    )
}
struct Live<'a> {
    id: (u64, u64),
    ins: &'a Inspector,
    f: V,
    root: PathBuf,
    claim: PathBuf,
    ch: String,
    start: Instant,
    end: Instant,
    seals: Vec<(PathBuf, String)>,
    arms: Vec<V>,
    steps: Vec<V>,
    attempts: usize,
}
impl Live<'_> {
    fn seal(&mut self, p: PathBuf, v: &V) -> R<String> {
        still_owned(&self.root, self.id)?;
        let h = write_new(&p, v)?;
        self.seals.push((p, h.clone()));
        Ok(h)
    }
    fn original(&self) -> R<()> {
        still_owned(&self.root, self.id)?;
        canon(&self.claim)?;
        check(file_sha256(&self.claim)? == self.ch, "claim drift")?;
        verify_seals(self.seals.get(..1).ok_or("missing timing freeze")?)?;
        check(
            self.ins.admit("live", self.end)? == self.f,
            "live bindings drift",
        )?;
        left(self.end, Duration::MAX)?;
        Ok(())
    }
    fn finish(&self) -> R<()> {
        self.original()?;
        verify_seals(&self.seals)?;
        left(self.end, Duration::MAX)?;
        Ok(())
    }
}
fn verify_seals(seals: &[(PathBuf, String)]) -> R<()> {
    for (p, h) in seals {
        canon(p)?;
        check(file_sha256(p)? == *h, "sealed evidence drift")?;
    }
    Ok(())
}
impl Campaign for Live<'_> {
    fn record(&mut self, name: &str, v: V) -> R<()> {
        self.seal(self.root.join(format!("{name}.json")), &v)?;
        self.steps.push(json!({"stage":name,"data":v}));
        Ok(())
    }
    fn arm(&mut self, a: Arm) -> R<f64> {
        check(self.attempts < 48, "fixed child limit")?;
        self.original().map_err(|e| format!("readmission: {e}"))?;
        let n = self.attempts + 1;
        let q = self.f["qualified"][a.case].clone();
        let cfg = a.config(&q)?;
        let dir = self.root.join(format!("arm-{n:02}"));
        fs::create_dir(&dir).map_err(io)?;
        let config = dir.join("config.json");
        let h = self.seal(config.clone(), &cfg)?;
        let child = PathBuf::from(string(&self.f["child"])?);
        canon(&child)?;
        check(
            file_sha256(&child)? == string(&cfg["binary_sha256"])?,
            "child binary drift",
        )?;
        let intent = json!({"ordinal":n,"stage":a.stage,"pair":a.pair,"claim_sha256":self.ch,"freeze_sha256":self.seals.first().ok_or("freeze")?.1,"authority_sha256":self.ins.digest,"binary_sha256":cfg["binary_sha256"],"config_sha256":h});
        self.seal(dir.join("intent.json"), &intent)?;
        let mut cmd = Command::new(&child);
        cmd.env_clear()
            .envs(child_env(Path::new(string(&self.f["prefix"])?), &dir))
            .arg(&config)
            .arg(dir.join("output"))
            .stdout(new_file(&dir.join("stdout"))?)
            .stderr(new_file(&dir.join("stderr"))?);
        let limit = left(self.end, Duration::from_secs(120))?;
        self.attempts = n;
        let arm_end = self.end.min(Instant::now() + limit);
        let (mut o, _) = spawn(&mut cmd, arm_end, false)?;
        o["arm_deadline_exceeded"] = json!(Instant::now() > arm_end);
        o["binary_sha256"] = cfg["binary_sha256"].clone();
        o["config_sha256"] = json!(h);
        self.seal(dir.join("outcome.json"), &o)?;
        check(
            o["outcome"] == "EXIT_STATUS 0"
                && o["reaped"] == true
                && o["arm_deadline_exceeded"] == false,
            &format!("CHILD_EXECUTION_CLEANUP: {o}"),
        )?;
        left(self.end, Duration::MAX)?;
        let parse_report = || -> R<(V, String, String, f64)> {
            check(file_sha256(&config)? == h, "config drift")?;
            let rp = dir.join("output/run.json");
            let ev = dir.join("output/events.jsonl");
            canon(&rp)?;
            canon(&ev)?;
            let bytes = raw(&rp, 8 << 20)?;
            let r = val(&bytes)?;
            let eb = raw(&ev, 64 << 20)?;
            check(eb.ends_with(b"\n"), "truncated event stream")?;
            let events = eb[..eb.len() - 1]
                .split(|&v| v == b'\n')
                .map(val)
                .collect::<R<Vec<_>>>()?;
            let mean = admit_report(&a, &q, &cfg, &h, &r, &events, &o)?;
            Ok((r, sha(&bytes), sha(&eb), mean))
        };
        let (report, rh, eh, mean) =
            parse_report().map_err(|e| format!("REPORT_CORRECTNESS_RESOURCE: {e}"))?;
        self.seals.push((dir.join("output/run.json"), rh.clone()));
        self.seals
            .push((dir.join("output/events.jsonl"), eh.clone()));
        self.arms.push(json!({"intent":intent,"outcome":o,"report":report,"report_sha256":rh,"events_sha256":eh,"mean_seconds":mean}));
        Ok(mean)
    }
}
fn claim(p: &Path, receipt: &V) -> R<(Instant, String)> {
    let mut f = new_file(p).map_err(|e| format!("PRECLAIM_REFUSAL exclusive claim: {e}"))?;
    let start = Instant::now();
    let bytes = serde_json::to_vec_pretty(receipt).map_err(|e| format!("POSTCLAIM_SETUP: {e}"))?;
    f.write_all(&bytes)
        .and_then(|_| f.sync_all())
        .map_err(|e| format!("POSTCLAIM_SETUP claim spent: {e}"))?;
    Ok((start, sha(&bytes)))
}
fn run(ap: &Path, h: &str) -> R<()> {
    let admission_start = Instant::now();
    let pre = |e: String| format!("PRECLAIM_REFUSAL: {e}");
    let ins = Inspector::new(ap, h).map_err(pre)?;
    let f = ins
        .admit("pre", admission_start + Duration::from_secs(180))
        .map_err(pre)?;
    let root = PathBuf::from(string(&f["timing"])?);
    let cp = PathBuf::from(string(&f["claim"])?);
    let admission_seconds = admission_start.elapsed().as_secs_f64();
    let receipt = json!({"schema":"pulsarmlx.m1b-claim/1","phase":"m1b","authority_sha256":h,"timing_root":root,"controller":f["identities"]["controller"],"child":f["identities"]["child"],"campaigns":1,"raw":0,"numerical":0});
    let (start, ch) = claim(&cp, &receipt)?;
    let end = start + Duration::from_secs(policy::DEADLINE_SECONDS);
    fs::DirBuilder::new()
        .mode(0o700)
        .create(&root)
        .map_err(|e| format!("POSTCLAIM_SETUP claim spent; timing root: {e}"))?;
    let id = root_id(&root).map_err(|e| format!("POSTCLAIM_SETUP: {e}"))?;
    let mut live = Live {
        id,
        ins: &ins,
        f,
        root: root.clone(),
        claim: cp,
        ch,
        start,
        end,
        seals: vec![],
        arms: vec![],
        steps: vec![],
        attempts: 0,
    };
    let work = (|| -> R<&str> {
        let freeze = json!({"schema":"pulsarmlx.m1b-freeze/1","admitted":live.f,"claim_sha256":live.ch,"policy_sha256":val(PROFILE)?["profile_pins"]["src/policy.rs"],"deadline_seconds":policy::DEADLINE_SECONDS,"per_arm_seconds":120,"children_max":48});
        live.seal(root.join("freeze.json"), &freeze)
            .map_err(|e| format!("POSTCLAIM_SETUP: {e}"))?;
        let v = schedule(&mut live)?;
        live.finish()
            .map_err(|e| format!("FINAL_BINDING_DRIFT: {e}"))?;
        Ok(v)
    })();
    let result = json!({"schema":"pulsarmlx.m1b-result/1","decision":work.as_ref().ok(),"failure":work.as_ref().err(),"claim_spent":true,"freeze_bindings":live.f,"steps":live.steps,"arms":live.arms,"children_attempted":live.attempts,"elapsed_seconds":live.start.elapsed().as_secs_f64(),"initial_admission_seconds":admission_seconds,"process_launch_to_first_projection":null,"final_readmission":work.is_ok(),"shipping_default":"copied","M2_M4_started":false,"C2_experimental_CI_acceptance":false,"exact_commit_cross_host_acceptance":false,"historical_CI_conclusion":"failure","scope":"warm buffered synthetic screen only; physical memory and wiring unobserved"});
    still_owned(&root, live.id)?;
    write_new(&root.join("result.json"), &result).map_err(|e| format!("POSTCLAIM_RESULT: {e}"))?;
    work.map(|_| ())
}
fn main() {
    let a: Vec<_> = std::env::args_os().collect();
    let res = if a.len() == 3 {
        a[2].to_str()
            .ok_or_else(|| "digest".into())
            .and_then(|h| run(Path::new(&a[1]), h))
    } else {
        bad("usage: m1b-controller ABS_AUTHORITY SHA256")
    };
    if let Err(s) = res {
        eprintln!(
            "{}",
            json!({"schema":"pulsarmlx.m1b-refusal/1","failure":s,"retry_authorized":false,"shipping_default":"copied"})
        );
        std::process::exit(1)
    }
}
#[cfg(test)]
#[path = "m1b-controller/tests.rs"]
mod tests;
