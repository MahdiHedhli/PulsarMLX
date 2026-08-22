//! Operator-only bounded-P1 entry. Normal validation exposes plan-only mode;
//! it cannot mint authorization. `execute` consumes an already-created exact
//! one-shot authority and immediately enters the shared RN1 lifecycle.

use f017_native::executor::FullNativeP1Math;
use f017_native::loader::{load_plan_only, plan_summary, SecureCheckpoint};
use f017_native::model::ModelConfig;
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use stream::{execute_bounded_p1_once, P1AttemptAuthority, P1RuntimeIdentity};

fn sha(path: &Path) -> Result<String, String> {
    let bytes = fs::read(path).map_err(|e| e.to_string())?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}
fn write_exclusive(path: &Path, value: &serde_json::Value) -> Result<(), String> {
    use std::io::Write;
    use std::os::unix::fs::OpenOptionsExt;
    let mut f = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o400)
        .open(path)
        .map_err(|e| e.to_string())?;
    let mut b = serde_json::to_vec(value).map_err(|e| e.to_string())?;
    b.push(b'\n');
    f.write_all(&b).map_err(|e| e.to_string())?;
    f.sync_all().map_err(|e| e.to_string())?;
    Ok(())
}
fn machine() -> Result<(), String> {
    let out = Command::new("/usr/sbin/sysctl")
        .args(["-n", "machdep.cpu.brand_string"])
        .output()
        .map_err(|e| e.to_string())?;
    if !out.status.success()
        || String::from_utf8(out.stdout)
            .map_err(|e| e.to_string())?
            .trim_end_matches(['\r', '\n'])
            != "Apple M1 Ultra"
        || std::env::consts::ARCH != "aarch64"
    {
        return Err("exact Apple M1 Ultra arm64 identity required".into());
    }
    Ok(())
}

fn run() -> Result<(), String> {
    let a = std::env::args().collect::<Vec<_>>();
    match a.get(1).map(String::as_str){
        Some("plan-only") if a.len()==5=>{let(m,c)=load_plan_only(Path::new(&a[2]),Path::new(&a[3]))?;write_exclusive(Path::new(&a[4]),&plan_summary(&m,&c))},
        Some("execute") if a.len()==8=>{
            machine()?;
            let manifest_path=PathBuf::from(&a[2]);let catalog_path=PathBuf::from(&a[3]);let root=PathBuf::from(&a[4]);let auth_path=PathBuf::from(&a[5]);let state=PathBuf::from(&a[6]);let contract=PathBuf::from(&a[7]);
            let authority:P1AttemptAuthority=f017_native::json::parse_json_no_duplicates(&fs::read(&auth_path).map_err(|e|e.to_string())?)?;
            if !authority.real_event_authorized||authority.checkpoint_manifest_sha256!=sha(&manifest_path)?||authority.contract_sha256!=sha(&contract)?{return Err("authority binding mismatch".into())}
            let current=std::env::current_exe().map_err(|e|e.to_string())?;if authority.executor_sha256!=sha(&current)?{return Err("executor identity mismatch".into())}
            let head=String::from_utf8(Command::new("git").args(["rev-parse","HEAD"]).output().map_err(|e|e.to_string())?.stdout).map_err(|e|e.to_string())?.trim().to_owned();if authority.git_head!=head{return Err("git head mismatch".into())}
            let(m,c)=load_plan_only(&manifest_path,&catalog_path)?;if authority.checkpoint_set_sha256!=m.checkpoint_set_sha256{return Err("checkpoint set mismatch".into())}
            let checkpoint=SecureCheckpoint::open(&root,m,c)?;let mut math=FullNativeP1Math::new(checkpoint,ModelConfig::glm52());
            let runtime=P1RuntimeIdentity{mlx_version:"0.31.2".into(),mlx_c_version:"0.6.0".into(),architecture:"arm64".into(),machine_brand:"Apple M1 Ultra".into(),stream_origin:"OWNED_DEVICE_GPU".into(),native_handle_owned:true,deallocation_responsibility:"THIS_INVOCATION".into()};
            execute_bounded_p1_once(&state,&authority,runtime,&mut math).map(|_|()).map_err(|e|e.to_string())
        },
        _=>Err("usage: f017-native-bounded-p1 plan-only MANIFEST CATALOG OUT | execute MANIFEST CATALOG CHECKPOINT_ROOT AUTHORIZATION STATE_ROOT CONTRACT".into())
    }
}
fn main() {
    if let Err(e) = run() {
        eprintln!("{e}");
        std::process::exit(2)
    }
}
