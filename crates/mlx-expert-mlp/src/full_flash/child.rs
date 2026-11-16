use crate::{ffi, graph, provider};
use mlx_native_affine::fixture::sha256_hex;
use serde_json::{json, Value};
use std::{
    collections::BTreeSet,
    fs,
    io::Write,
    os::unix::fs::{MetadataExt, OpenOptionsExt},
    path::{Path, PathBuf},
    process::Command,
};
type R<T> = Result<T, String>;
fn err(e: impl std::fmt::Display) -> String {
    e.to_string()
}
fn field<'a>(v: &'a Value, k: &str) -> R<&'a str> {
    v[k].as_str()
        .ok_or_else(|| format!("missing admission field {k}"))
}
fn read_json(p: &Path, limit: u64) -> R<Value> {
    let m = p.symlink_metadata().map_err(err)?;
    if !m.is_file() || m.len() > limit {
        return Err("unbounded private JSON".into());
    }
    serde_json::from_slice(&fs::read(p).map_err(err)?).map_err(err)
}
fn images(info: &Value) -> R<BTreeSet<String>> {
    let lib = Path::new(field(info, "prefix")?).join("lib");
    let mut seen = BTreeSet::new();
    let count = unsafe { libc::_dyld_image_count() };
    if count > 4096 {
        return Err("image census".into());
    }
    for i in 0..count {
        let p = unsafe { libc::_dyld_get_image_name(i) };
        if p.is_null() {
            return Err("image path".into());
        }
        let im = Path::new(
            unsafe { std::ffi::CStr::from_ptr(p) }
                .to_str()
                .map_err(err)?,
        );
        let n = im.file_name().and_then(|s| s.to_str()).unwrap_or("");
        if n.ends_with(".dylib")
            && (n.to_ascii_lowercase().contains("mlx") || n == "libjaccl.dylib")
        {
            if !matches!(n, "libmlx.dylib" | "libmlxc.dylib" | "libjaccl.dylib")
                || im.canonicalize().map_err(err)? != lib.join(n)
                || im.metadata().map_err(err)?.len() > 32 << 20
                || sha256_hex(&fs::read(im).map_err(err)?) != info["libs"][n]
                || !seen.insert(n.to_string())
            {
                return Err("loaded image binding".into());
            }
        }
    }
    if seen.len() != 3 {
        return Err("missing MLX image".into());
    }
    Ok(seen)
}
struct Sink {
    out: PathBuf,
    files: serde_json::Map<String, Value>,
    routes: Vec<Value>,
    bytes: usize,
}
impl Sink {
    fn file(&mut self, name: &str, b: &[u8]) -> R<()> {
        if b.is_empty()
            || b.len() > 8 << 20
            || self.bytes + b.len() > 256 << 20
            || name.contains('/')
            || self.files.contains_key(name)
        {
            return Err("duplicate/oversized output".into());
        }
        let mut f = fs::OpenOptions::new()
            .create_new(true)
            .write(true)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW)
            .open(self.out.join(name))
            .map_err(err)?;
        f.write_all(b).and_then(|_| f.sync_all()).map_err(err)?;
        self.bytes += b.len();
        self.files
            .insert(name.into(), json!({"bytes":b.len(),"sha256":sha256_hex(b)}));
        Ok(())
    }
    fn floats(&mut self, name: &str, x: &[f32]) -> R<()> {
        if x.iter().any(|v| !v.is_finite()) {
            return Err("nonfinite output".into());
        }
        self.file(
            name,
            &x.iter().flat_map(|v| v.to_le_bytes()).collect::<Vec<_>>(),
        )
    }
}
impl graph::Witness for Sink {
    fn vector(&mut self, l: usize, n: &str, x: &[f32]) -> R<()> {
        self.floats(&format!("{l:02}.{n}.f32"), x)
    }
    fn route(&mut self, l: usize, ids: &[usize], w: &[f32], gap: f32) -> R<()> {
        if l != self.routes.len() + 3
            || ids.len() != 8
            || w.len() != 8
            || !gap.is_finite()
            || gap <= 0.
        {
            return Err("ambiguous or missing route".into());
        }
        self.routes
            .push(json!({"layer":l,"ids":ids,"weights":w,"cutoff_gap":gap}));
        Ok(())
    }
}
pub fn run() -> R<()> {
    let a: Vec<_> = std::env::args_os().skip(1).collect();
    if a.len() != 2 {
        return Err("expected stage capability and fresh output directory".into());
    }
    let out = PathBuf::from(&a[1]);
    let cap = PathBuf::from(&a[0]);
    if !cap.is_absolute() || out.canonicalize().map_err(err)? != out {
        return Err("noncanonical stage paths".into());
    }
    let verify = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../scripts/research/studio017_supervise.py")
        .canonicalize()
        .map_err(err)?;
    if fs::read(&verify).map_err(err)?
        != include_bytes!("../../../../scripts/research/studio017_supervise.py")
    {
        return Err("supervisor source changed".into());
    }
    let gate = verify.with_file_name("studio017_py_gate.py");
    if fs::read(&gate).map_err(err)? != include_bytes!("../../../../scripts/research/studio017_py_gate.py") {
        return Err("Python gate source changed".into());
    }
    let cap_doc = read_json(&cap, 64 << 10)?;
    let py = &cap_doc["python_gate"];
    let parent = cap.parent().ok_or("missing cap parent")?;
    let interpreter = Path::new("/opt/homebrew/bin/python3").canonicalize().map_err(err)?;
    if interpreter != Path::new(field(py,"interpreter")?) {
        return Err("pinned physical interpreter mismatch".into());
    }
    let v = Command::new(interpreter)
        .env_remove("DYLD_LIBRARY_PATH")
        .args(["-I","-B","-S","-X"])
        .arg(format!("pycache_prefix={}",parent.join("cache-helper").display()))
        .arg(&gate)
        .arg("helper")
        .arg(field(py,"policy")?)
        .arg(field(py,"sha256")?)
        .arg(parent.join("python-helper.json"))
        .arg(field(&cap_doc,"operation")?)
        .arg(&cap)
        .output()
        .map_err(err)?;
    if !v.status.success() || v.stdout.len() > 32768 {
        return Err(format!(
            "child admission refused: {}",
            String::from_utf8_lossy(&v.stderr)
        ));
    }
    let info: Value = serde_json::from_slice(&v.stdout).map_err(err)?;
    if field(&info, "stage")? != "native"
        || Path::new(field(&info, "output")?) != out
        || out.symlink_metadata().map_err(err)?.mode() & 0o077 != 0
        || out.read_dir().map_err(err)?.next().is_some()
    {
        return Err("stage/output custody".into());
    }
    let loaded = images(&info)?;
    let source = Path::new(field(&info, "model_root")?);
    let witness = read_json(Path::new(field(&info, "witnesses")?), 64 << 10)?;
    let orig = read_json(Path::new(field(&info, "input")?), 65536)?;
    if orig["id"] != 154820
        || orig["position"] != 0
        || orig["batch"] != 1
        || orig["max_new_tokens"] != 1
        || orig["sampling"] != false
        || orig["empty_state"] != true
    {
        return Err("wrong frozen input".into());
    }
    ffi::verify_abi()?;
    let mut device = provider::Metal::open(
        source,
        "a2b1a6822bf21b8459952e1a0124d00b44f8008167c09f3dbf5099eb4d98deea",
        &witness,
    )?;
    let mut w = Sink {
        out: out.clone(),
        files: Default::default(),
        routes: vec![],
        bytes: 0,
    };
    let (logits, id) = graph::forward(&mut device, &mut w, 154820)?;
    let cleanup = device.finish()?;
    if logits.len() != 154880 || w.routes.len() != 42 {
        return Err("incomplete full model".into());
    }
    w.floats("logits.f32", &logits)?;
    let runner =
        (0..logits.len())
            .filter(|i| *i != id)
            .fold(if id == 0 { 1 } else { 0 }, |j, i| {
                if logits[i] > logits[j] {
                    i
                } else {
                    j
                }
            });
    let report = json!({"schema":"studio017-native/1","layer_count":45,"position":0,"generated_token_count":1,"input_id":154820,"token_id":id,"runner_up":runner,"margin":logits[id] as f64-logits[runner] as f64,"routes":w.routes,"files":w.files,"native":cleanup,"libraries":loaded});
    w.file("report.json", &serde_json::to_vec(&report).map_err(err)?)?;
    fs::File::open(out)
        .and_then(|f| f.sync_all())
        .map_err(err)?;
    Ok(())
}
