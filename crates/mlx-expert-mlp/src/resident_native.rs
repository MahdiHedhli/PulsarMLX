#[path = "resident_verifier.rs"]
mod verifier;
use crate::{bridge, ffi, native, provenance};
use mlx_expert_mlp::{
    resident,
    resident_fixture::{self as fixture, Arm, Population},
    resident_pipeline::*,
};
use mlx_native_affine::{
    dtype::Dtype,
    fixture::{sha256_hex, HostTensor},
    refusal::DeviceFacts,
};
use serde_json::{json, Value};
use std::{fs, path::Path};

extern "C" {
    fn pulsar_mlp_cpu_guard(fpcr: *mut u64) -> i32;
    fn pulsar_mlp_activation(
        g: *const f32,
        u: *const f32,
        m: i32,
        h: i32,
        out: *mut f32,
        gc: *mut u32,
        uc: *mut u32,
        stats: *mut u64,
        mode: i32,
    ) -> i32;
    fn mlx_set_cache_limit(old: *mut usize, limit: usize) -> i32;
    fn mlx_get_cache_memory(size: *mut usize) -> i32;
    fn mlx_clear_cache() -> i32;
}
fn status(rc: i32, op: &str) -> StageResult<()> {
    if rc == 0 {
        Ok(())
    } else {
        Err(Fault::uncertain(format!("{op} returned {rc}")))
    }
}
fn cache() -> StageResult<usize> {
    let mut size = 0;
    status(
        unsafe { mlx_get_cache_memory(&mut size) },
        "get_cache_memory",
    )?;
    Ok(size)
}
fn census() -> [u64; 3] {
    let (a, b, c) = native::result_census();
    [a, b, c]
}
pub(super) struct Copied {
    ctx: Option<native::NativeContext>,
    freed: u64,
    results: [u64; 3],
}
impl Copied {
    pub(super) fn new() -> Self {
        Self { ctx: None, freed: native::handle_census().1, results: census() }
    }
}
impl Driver for Copied {
    fn begin(&mut self) -> StageResult<DeviceFacts> {
        if self.ctx.is_some() || native::handle_census().0 != 0 {
            return Err(Fault::uncertain("existing handles"));
        }
        self.freed = native::handle_census().1;
        self.results = census();
        self.ctx =
            Some(native::NativeContext::new(native::DeviceKind::Gpu).map_err(Fault::uncertain)?);
        self.ctx
            .as_ref()
            .unwrap()
            .device_facts()
            .map_err(Fault::uncertain)
    }
    fn projection(
        &mut self,
        role: usize,
        x: &HostTensor,
        p: &[HostTensor; 3],
        bits: u32,
    ) -> StageResult<Projection> {
        let ctx = self
            .ctx
            .as_ref()
            .ok_or_else(|| Fault::uncertain("missing GPU context"))?;
        let start = ffi::call_counts();
        let mut fpcr = 0;
        status(
            unsafe { pulsar_mlp_cpu_guard(&mut fpcr) },
            "CPU guard before projection",
        )?;
        let result = bridge::quantized_matmul(ctx, x, &p[0], &p[1], &p[2], bits, 64);
        let mut after_fpcr = 0;
        status(
            unsafe { pulsar_mlp_cpu_guard(&mut after_fpcr) },
            "CPU guard after projection",
        )?;
        if fpcr != after_fpcr {
            return Err(Fault::uncertain("CPU arithmetic mode changed"));
        }
        let (_, copy, s) = result.map_err(|(e, _)| match e {
            bridge::BridgeError::Refused(id) => Fault::clean(id),
            bridge::BridgeError::Native(e) => Fault::uncertain(e),
        })?;
        let end = ffi::call_counts();
        if s.output_nbytes != Some(copy.bytes.len()) {
            return Err(Fault::uncertain("incomplete projection readback"));
        }
        Ok(Projection {
            output: HostTensor {
                name: ["gate", "up", "down"][role].into(),
                dtype: copy.dtype,
                shape: copy.shape,
                bytes: copy.bytes,
            },
            calls: end.0 - start.0,
            imports: end.1 - start.1,
            before_import: s.imports_before_decision,
            before_call: s.numerical_before_decision,
            cpu_checks: 2,
            gpu: s.device_facts == Some(DeviceFacts::GPU),
            memory: [
                s.active_before
                    .ok_or_else(|| Fault::uncertain("missing active memory"))?,
                cache()?,
                s.peak_after
                    .ok_or_else(|| Fault::uncertain("missing peak"))?,
            ],
        })
    }
    fn activation(&mut self, g: &HostTensor, u: &HostTensor) -> StageResult<Activation> {
        let values = |t: &HostTensor| -> StageResult<[f32; 64]> {
            if t.bytes.len() != 256 {
                return Err(Fault::clean("activation dimension"));
            }
            Ok(std::array::from_fn(|i| {
                f32::from_le_bytes(t.bytes[i * 4..i * 4 + 4].try_into().unwrap())
            }))
        };
        let (g, u) = (values(g)?, values(u)?);
        let (mut out, mut gc, mut uc, mut stats) = ([0f32; 64], [0; 64], [0; 64], [0u64; 8]);
        native::reset_peak_memory().map_err(Fault::uncertain)?;
        let active = native::active_memory().map_err(Fault::uncertain)?;
        let rc = unsafe {
            pulsar_mlp_activation(
                g.as_ptr(),
                u.as_ptr(),
                1,
                64,
                out.as_mut_ptr(),
                gc.as_mut_ptr(),
                uc.as_mut_ptr(),
                stats.as_mut_ptr(),
                0,
            )
        };
        if rc != 0 {
            return Err(Fault::uncertain(format!(
                "activation {rc}, ownership {stats:?}"
            )));
        }
        Ok(Activation {
            hidden: HostTensor {
                name: "hidden".into(),
                dtype: Dtype::F32,
                shape: vec![1, 64],
                bytes: out.iter().flat_map(|v| v.to_le_bytes()).collect(),
            },
            clamps: [gc, uc],
            stats,
            memory: [
                active,
                cache()?,
                native::peak_memory().map_err(Fault::uncertain)?,
            ],
        })
    }
    fn retire(&mut self) -> StageResult<Retirement> {
        let sync = self.ctx.as_ref().map(|c| c.synchronize()).transpose();
        drop(self.ctx.take());
        native::drain_residual_error("resident occurrence retirement");
        let (live, freed) = native::handle_census();
        let now = census();
        let r = Retirement {
            live,
            freed: freed - self.freed,
            double_free: native::double_free_attempts(),
            errors: native::cleanup_errors().len(),
            messages: native::handler_messages(),
            results: std::array::from_fn(|i| now[i] - self.results[i]),
        };
        if let Err(e) = sync {
            return Err(Fault::uncertain(format!(
                "synchronize: {e}; census live={live}, cleanup={}, results={:?}",
                r.errors, r.results
            )));
        }
        Ok(r)
    }
    fn finish(&mut self) -> StageResult<()> {
        status(unsafe { mlx_clear_cache() }, "clear cache at finish")?;
        if self.ctx.is_some()
            || native::handle_census().0 != 0
            || cache()? != 0
            || !native::cleanup_errors().is_empty()
            || native::handler_messages() != 0
        {
            return Err(Fault::uncertain("finish ownership/cache"));
        }
        Ok(())
    }
}
fn write(path: &Path, b: &[u8]) -> Result<(), String> {
    use std::io::Write;
    let mut f = fs::File::create_new(path).map_err(|e| e.to_string())?;
    f.write_all(b).map_err(|e| e.to_string())
}
pub fn run() -> Result<(), String> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() != 2 || args[0] != "--intent" {
        return Err("expected --intent with a supervised launch".into());
    }
    let path = Path::new(&args[1]);
    let raw = fixture::checked_file(path, 65536)?;
    let cap: Value = serde_json::from_slice(&raw).map_err(|e| e.to_string())?;
    let get = |k: &str| fixture::text(&cap[k]);
    let repo = Path::new(get("repo")?);
    let out = path.parent().ok_or("arm directory")?.join("out");
    if repo != std::env::current_dir().map_err(|e| e.to_string())?
        || cap["supervisor_pid"] != unsafe { libc::getppid() }
        || path.file_name().and_then(|s| s.to_str()) != Some("intent.json")
    {
        return Err("launch custody".into());
    }
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let binary_hash = sha256_hex(&fixture::checked_file(&exe, 128 << 20)?);
    if cap["identity"]["binary_sha256"] != binary_hash {
        return Err("child build identity".into());
    }
    // Reopen the stable exclusive claim and validate authority before the first native call.
    let modules = [
        (
            "f020_expert_mlp_r1_v1",
            sha256_hex(include_bytes!(
                "../../../scripts/research/f020_expert_mlp_r1_v1.py"
            )),
        ),
        (
            "f020_expert_mlp_qualify_v1",
            sha256_hex(include_bytes!(
                "../../../scripts/research/f020_expert_mlp_qualify_v1.py"
            )),
        ),
        (
            "f020_resident_mlp_fixtures",
            sha256_hex(include_bytes!(
                "../../../scripts/research/f020_resident_mlp_fixtures.py"
            )),
        ),
        (
            "f020_resident_mlp_runtime",
            sha256_hex(include_bytes!(
                "../../../scripts/research/f020_resident_mlp_runtime.py"
            )),
        ),
        (
            "f020_resident_mlp_check",
            sha256_hex(include_bytes!(
                "../../../scripts/research/f020_resident_mlp_check.py"
            )),
        ),
        (
            "f020_resident_mlp_supervise",
            sha256_hex(include_bytes!(
                "../../../scripts/research/f020_resident_mlp_supervise.py"
            )),
        ),
    ];
    // Run only the exact verifier and imports compiled into this binary, without
    // user-site startup, inherited Python paths or bytecode caches.
    let bootstrap = r#"import sys, types, hashlib, json, pathlib
root=pathlib.Path.cwd()/'scripts/research'
mods=json.loads(sys.argv[1])
sys.argv=['resident-verifier','verify-child',sys.argv[2]]
for name,digest in mods:
 p=root/(name+'.py')
 if p.stat().st_size>524288:raise ValueError('oversized verifier source')
 raw=p.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('verifier source identity')
 key='__main__' if name==mods[-1][0] else name
 mod=types.ModuleType(key);mod.__file__=str(p);sys.modules[key]=mod
 exec(compile(raw,str(p),'exec'),mod.__dict__)
"#;
    let compiled: std::collections::BTreeMap<_, _> = modules.iter().map(|(n, h)| (*n, h)).collect();
    if cap["identity"]["verifier_modules"] != json!(compiled)
        || cap["identity"]["accounting"]["abi_stamp"] != verifier::layout_stamp()
    {
        return Err("compiled resident verifier/accounting identity".into());
    }
    let verify = verifier::verifier_command(
        bootstrap,
        &serde_json::to_string(&modules).map_err(|e| e.to_string())?,
        path,
    )?
    .status()
    .map_err(|e| e.to_string())?;
    if !verify.success() {
        return Err("child admission".into());
    }
    fs::create_dir(&out).map_err(|e| e.to_string())?;
    let profile = get("profile")?;
    let arm = match get("arm")? {
        "allocating" => Arm::Allocating,
        "cached" => Arm::Cached,
        _ => return Err("arm".into()),
    };
    ffi::verify_abi()?;
    native::ensure_error_handler();
    native::set_default_device_gpu().map_err(|e| e.to_string())?;
    let prov = provenance::collect(&std::env::var("MLX_C_PREFIX").map_err(|e| e.to_string())?)?;
    for n in ["libmlx", "libmlxc", "metallib"] {
        if prov[n]["sha256"] != cap["identity"]["native"][n] || !prov[n]["sha256"].is_string() {
            return Err(format!("loaded installation mismatch {n}"));
        }
    }
    if prov["mlx_commit_pinned"] != cap["identity"]["native"]["mlx_commit"]
        || prov["mlx_c_commit_pinned"] != cap["identity"]["native"]["mlx_c_commit"]
        || prov["build"]["qualify_executable_sha256"] != binary_hash
        || prov["other_mlx_named_images"] != json!([])
        || prov["environment"]["DYLD_LIBRARY_PATH"] != "<native-prefix>/lib"
        || prov["environment"]["MLX_ENABLE_TF32"] != "0"
        || prov["mlx_version"] != prov["mlx_version_expected"]
    {
        return Err("loaded runtime/source identity".into());
    }
    let mut old = 0;
    status(
        unsafe { mlx_set_cache_limit(&mut old, 0) },
        "set cache limit",
    )
    .map_err(|e| e.reason)?;
    status(unsafe { mlx_clear_cache() }, "initial cache clear").map_err(|e| e.reason)?;
    let initial_cache = cache().map_err(|e| e.reason)?;
    if initial_cache != 0 {
        return Err("nonzero initial cache".into());
    }
    let (mut host, store, cp) = resident::setup(
        repo,
        profile,
        arm,
        Copied {
            ctx: None,
            freed: native::handle_census().1,
            results: census(),
        },
        None,
    )?;
    let seq = resident::run_sequence(&mut host, &store, &cp, arm);
    let mut sizes = 0;
    for (i, row) in host.backend().records.iter().enumerate() {
        sizes += row.len();
        write(&out.join(format!("occ-{i:02}.json")), row)?;
    }
    let report = json!({"schema":"resident-mlp-v1","profile":profile,"arm":arm.name(),"identity":cap["identity"],"intent_sha256":sha256_hex(&raw),"fixture":Population::load(profile)?.binding(),"allocator":{"cache_limit":0,"initial_clear":0,"initial_cache":initial_cache,"previous_limit":old},"provenance":prov,"sequence":seq.as_ref().ok(),"failure":seq.as_ref().err(),"ledger":host.backend().ledger(),"final":host.backend().snapshot(),"row_count":host.backend().records.len()});
    let result = serde_json::to_vec_pretty(&report).map_err(|e| e.to_string())?;
    if sizes + result.len() > REPORT_LIMIT {
        return Err("report size".into());
    }
    write(&out.join("report.json"), &result)?;
    seq.map(|_| ())
}
