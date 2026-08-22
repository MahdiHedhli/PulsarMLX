//! Operator-only bounded-P1 entry. Normal validation exposes plan-only mode;
//! it cannot mint authorization. `execute` consumes an already-created exact
//! one-shot authority and immediately enters the shared RN1 lifecycle.

use f017_native::contract;
use f017_native::executor::{FullNativeP1Math, FullNativeP1MathV3};
use f017_native::loader::{load_plan_only, plan_summary, SecureCheckpoint};
use f017_native::model::ModelConfig;
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use stream::{
    execute_bounded_p1_once, execute_evidenced_bounded_p1_once, validate_real_p1_authority,
    P1AttemptAuthority, P1RuntimeIdentity, EVIDENCED_RECEIPT_SCHEMA,
};

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
fn git(repo: &Path, args: &[&str]) -> Result<String, String> {
    let output = Command::new("git")
        .current_dir(repo)
        .args(args)
        .output()
        .map_err(|e| e.to_string())?;
    if !output.status.success() {
        return Err("git authority command failed".into());
    }
    String::from_utf8(output.stdout)
        .map(|s| s.trim().to_owned())
        .map_err(|e| e.to_string())
}
fn repository_preflight(repo: &Path, branch: &str, authority_head: &str) -> Result<(), String> {
    if git(repo, &["branch", "--show-current"])? != branch
        || git(repo, &["rev-parse", "HEAD"])? != authority_head
        || git(repo, &["rev-parse", &format!("origin/{branch}")])? != authority_head
        || !git(repo, &["status", "--porcelain"])?.is_empty()
    {
        return Err("repository authority mismatch".into());
    }
    Ok(())
}

fn run() -> Result<(), String> {
    let a = std::env::args().collect::<Vec<_>>();
    match a.get(1).map(String::as_str){
        Some("plan-only") if a.len()==5=>{let(m,c)=load_plan_only(Path::new(&a[2]),Path::new(&a[3]))?;write_exclusive(Path::new(&a[4]),&plan_summary(&m,&c))},
        Some("validate-contract") if a.len()==4=>{let(contract,_)=contract::load(Path::new(&a[2]))?;contract::validate_static(&contract,Path::new(&a[3]))},
        Some("machine-preflight") if a.len()==4=>{let(contract,_)=contract::load(Path::new(&a[2]))?;contract::validate_static(&contract,Path::new(&a[3]))?;contract::validate_machine(&contract).map(|_|())},
        Some("execute") if a.len()==8=>{
            let manifest_path=PathBuf::from(&a[2]);let catalog_path=PathBuf::from(&a[3]);let root=PathBuf::from(&a[4]);let auth_path=PathBuf::from(&a[5]);let state=PathBuf::from(&a[6]);let contract=PathBuf::from(&a[7]);
            let repo=std::env::current_dir().map_err(|e|e.to_string())?;let(real_contract,contract_sha)=f017_native::contract::load(&contract)?;f017_native::contract::validate_static(&real_contract,&repo)?;
            let authority:P1AttemptAuthority=f017_native::json::parse_json_no_duplicates(&fs::read(&auth_path).map_err(|e|e.to_string())?)?;
            validate_real_p1_authority(&authority).map_err(|e|e.to_string())?;
            if !authority.real_event_authorized
                || authority.attempt_id!=real_contract.one_shot.attempt_id
                || authority.checkpoint_manifest_sha256!=sha(&manifest_path)?
                || authority.checkpoint_catalog_sha256!=sha(&catalog_path)?
                || authority.contract_sha256!=contract_sha
                || authority.d0_sha256!=real_contract.authorities.d0.sha256
                || authority.d1_sha256!=real_contract.authorities.d1.sha256
                || authority.d2_sha256!=real_contract.authorities.d2.sha256
                || authority.d3_5_result_sha256!=real_contract.authorities.d3_5_result.sha256
                || authority.d3_5_acceptance_sha256!=real_contract.authorities.d3_5_acceptance.sha256
                || authority.synthetic_full_graph_result_sha256!=real_contract.authorities.synthetic_full_graph_result.sha256
                || authority.historical_master_ledger_sha256!=real_contract.authorities.historical_master_ledger_sha256
                || authority.historical_master_terminal_value!=real_contract.authorities.historical_master_terminal_value
            {return Err("authority binding mismatch".into())}
            let current=std::env::current_exe().map_err(|e|e.to_string())?;if authority.executor_sha256!=sha(&current)?||authority.executor_sha256!=real_contract.executor.sha256{return Err("executor identity mismatch".into())}
            repository_preflight(&repo,&real_contract.branch,&authority.git_head)?;f017_native::contract::validate_machine(&real_contract)?;
            if state!=PathBuf::from(&real_contract.state_root){return Err("state root mismatch".into())}
            let configured=std::env::var(&real_contract.checkpoint.root_environment).map_err(|_|"checkpoint root environment missing")?;if root.canonicalize().map_err(|e|e.to_string())?!=PathBuf::from(configured).canonicalize().map_err(|e|e.to_string())?{return Err("checkpoint root mismatch".into())}
            let(m,c)=load_plan_only(&manifest_path,&catalog_path)?;if authority.checkpoint_set_sha256!=m.checkpoint_set_sha256{return Err("checkpoint set mismatch".into())}
            let checkpoint=SecureCheckpoint::open(&root,m,c)?;let mut math=FullNativeP1Math::new(checkpoint,ModelConfig::glm52());
            let runtime=P1RuntimeIdentity{mlx_version:real_contract.runtime.mlx_version,mlx_c_version:real_contract.runtime.mlx_c_version,architecture:real_contract.runtime.architecture,machine_brand:real_contract.runtime.machine_brand,stream_origin:"OWNED_DEVICE_GPU".into(),native_handle_owned:true,deallocation_responsibility:"THIS_INVOCATION".into()};
            execute_bounded_p1_once(&state,&authority,runtime,&mut math).map(|_|()).map_err(|e|e.to_string())
        },
        Some("execute-evidenced-v3") if a.len()==8=>{
            let manifest_path=PathBuf::from(&a[2]);let catalog_path=PathBuf::from(&a[3]);let root=PathBuf::from(&a[4]);let auth_path=PathBuf::from(&a[5]);let state=PathBuf::from(&a[6]);let contract=PathBuf::from(&a[7]);
            let repo=std::env::current_dir().map_err(|e|e.to_string())?;let(real_contract,contract_sha)=f017_native::contract::load(&contract)?;f017_native::contract::validate_static(&real_contract,&repo)?;
            let authority:P1AttemptAuthority=f017_native::json::parse_json_no_duplicates(&fs::read(&auth_path).map_err(|e|e.to_string())?)?;
            validate_real_p1_authority(&authority).map_err(|e|e.to_string())?;
            if real_contract.one_shot.receipt_schema != EVIDENCED_RECEIPT_SCHEMA
                || !authority.real_event_authorized
                || authority.attempt_id!=real_contract.one_shot.attempt_id
                || authority.checkpoint_manifest_sha256!=sha(&manifest_path)?
                || authority.checkpoint_catalog_sha256!=sha(&catalog_path)?
                || authority.contract_sha256!=contract_sha
                || authority.d0_sha256!=real_contract.authorities.d0.sha256
                || authority.d1_sha256!=real_contract.authorities.d1.sha256
                || authority.d2_sha256!=real_contract.authorities.d2.sha256
                || authority.d3_5_result_sha256!=real_contract.authorities.d3_5_result.sha256
                || authority.d3_5_acceptance_sha256!=real_contract.authorities.d3_5_acceptance.sha256
                || authority.synthetic_full_graph_result_sha256!=real_contract.authorities.synthetic_full_graph_result.sha256
                || authority.historical_master_ledger_sha256!=real_contract.authorities.historical_master_ledger_sha256
                || authority.historical_master_terminal_value!=real_contract.authorities.historical_master_terminal_value
            {return Err("authority binding mismatch".into())}
            let current=std::env::current_exe().map_err(|e|e.to_string())?;if authority.executor_sha256!=sha(&current)?||authority.executor_sha256!=real_contract.executor.sha256{return Err("executor identity mismatch".into())}
            repository_preflight(&repo,&real_contract.branch,&authority.git_head)?;f017_native::contract::validate_machine(&real_contract)?;
            if state!=PathBuf::from(&real_contract.state_root){return Err("state root mismatch".into())}
            let configured=std::env::var(&real_contract.checkpoint.root_environment).map_err(|_|"checkpoint root environment missing")?;if root.canonicalize().map_err(|e|e.to_string())?!=PathBuf::from(configured).canonicalize().map_err(|e|e.to_string())?{return Err("checkpoint root mismatch".into())}
            let(m,c)=load_plan_only(&manifest_path,&catalog_path)?;if authority.checkpoint_set_sha256!=m.checkpoint_set_sha256{return Err("checkpoint set mismatch".into())}
            let mut math=FullNativeP1MathV3::new(root,m,c,ModelConfig::glm52());
            let runtime=P1RuntimeIdentity{mlx_version:real_contract.runtime.mlx_version,mlx_c_version:real_contract.runtime.mlx_c_version,architecture:real_contract.runtime.architecture,machine_brand:real_contract.runtime.machine_brand,stream_origin:"OWNED_DEVICE_GPU".into(),native_handle_owned:true,deallocation_responsibility:"THIS_INVOCATION".into()};
            execute_evidenced_bounded_p1_once(&state,&authority,runtime,&mut math,false).map(|_|()).map_err(|e|e.to_string())
        },
        _=>Err("usage: f017-native-bounded-p1 plan-only MANIFEST CATALOG OUT | validate-contract CONTRACT REPO_ROOT | machine-preflight CONTRACT REPO_ROOT | execute MANIFEST CATALOG CHECKPOINT_ROOT AUTHORIZATION STATE_ROOT CONTRACT | execute-evidenced-v3 MANIFEST CATALOG CHECKPOINT_ROOT AUTHORIZATION STATE_ROOT CONTRACT".into())
    }
}
fn main() {
    if let Err(e) = run() {
        eprintln!("{e}");
        std::process::exit(2)
    }
}
