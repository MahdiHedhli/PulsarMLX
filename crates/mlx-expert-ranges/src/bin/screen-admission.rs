//! Single synthetic metadata screen. The output directory must be new.
use mlx_expert_ranges::admission_screen::{screen, Policy, Trace, LIMIT};
use std::{
    fs,
    io::{Read, Write},
    path::Path,
};
fn run() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args_os().skip(1).take(5).collect();
    if args.len() != 4 {
        return Err(
            "usage: screen-admission INPUT AdmitAll|TwoHit AVAILABLE_BYTES NEW_OUTPUT_DIR".into(),
        );
    }
    let policy: Policy = args[1].to_str().ok_or("policy encoding")?.parse()?;
    let budget: u64 = args[2].to_str().ok_or("budget encoding")?.parse()?;
    if !fs::symlink_metadata(&args[0])?.is_file() {
        return Err("regular metadata file required".into());
    }
    let mut file = fs::File::open(&args[0])?;
    let m = file.metadata()?;
    if !m.is_file() || m.len() > LIMIT as u64 {
        return Err("bounded regular metadata file required".into());
    }
    let mut raw = vec![0; m.len() as usize];
    file.read_exact(&mut raw)?;
    if file.read(&mut [0])? != 0 {
        return Err("metadata file changed size".into());
    }
    let trace = Trace::parse(&raw)?;
    drop(raw);
    let data = screen(&trace, policy, budget)?.encode(LIMIT)?;
    let dir = Path::new(&args[3]);
    fs::create_dir(dir)?;
    let mut out = fs::File::create_new(dir.join("report.json"))?;
    out.write_all(&data)?;
    out.sync_all()?;
    Ok(())
}
fn main() {
    if let Err(e) = run() {
        eprintln!("screen-admission: {e}");
        std::process::exit(1)
    }
}
