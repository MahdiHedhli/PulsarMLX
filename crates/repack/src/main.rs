use repack::{inventory_summary, parse_scope, run_repack, verify_bundle, RepackConfig, Result};
use std::path::PathBuf;

fn need(args: &mut impl Iterator<Item = String>, name: &str) -> Result<String> {
    args.next().ok_or_else(|| format!("{name} requires a value").into())
}

fn run() -> Result<()> {
    let mut args = std::env::args().skip(1);
    let command = args.next().ok_or("missing command: inventory|dry-run|repack|verify-bundle")?;
    if command == "inventory" {
        let path = PathBuf::from(need(&mut args, "inventory path")?);
        println!("{}", serde_json::to_string(&inventory_summary(&path)?)?);
        return Ok(());
    }
    if command == "verify-bundle" {
        let path = PathBuf::from(need(&mut args, "bundle path")?);
        println!("{}", serde_json::to_string(&verify_bundle(&path)?)?);
        return Ok(());
    }
    if command != "dry-run" && command != "repack" {
        return Err(format!("unknown command {command}").into());
    }
    let mut checkpoint_dir = None;
    let mut admission_path = None;
    let mut inventory_path = None;
    let mut output_root = None;
    let mut staging_root = None;
    let mut scope = None;
    let mut summary_path = None;
    let mut shared = false;
    let mut resume = false;
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--checkpoint-dir" => checkpoint_dir = Some(PathBuf::from(need(&mut args, &arg)?)),
            "--admission" => admission_path = Some(PathBuf::from(need(&mut args, &arg)?)),
            "--inventory" => inventory_path = Some(PathBuf::from(need(&mut args, &arg)?)),
            "--output-root" => output_root = Some(PathBuf::from(need(&mut args, &arg)?)),
            "--staging-root" => staging_root = Some(PathBuf::from(need(&mut args, &arg)?)),
            "--layers" => scope = Some(need(&mut args, &arg)?),
            "--summary" => summary_path = Some(PathBuf::from(need(&mut args, &arg)?)),
            "--shared" => shared = true,
            "--resume" => resume = true,
            other => return Err(format!("unknown argument {other}").into()),
        }
    }
    let scope = parse_scope(scope.as_deref().ok_or("missing --layers")?, shared)?;
    let cfg = RepackConfig {
        checkpoint_dir: checkpoint_dir.ok_or("missing --checkpoint-dir")?,
        admission_path: admission_path.ok_or("missing --admission")?,
        inventory_path: inventory_path.ok_or("missing --inventory")?,
        output_root: output_root.ok_or("missing --output-root")?,
        staging_root: staging_root.ok_or("missing --staging-root")?,
        scope,
        summary_path: summary_path.ok_or("missing --summary")?,
        dry_run: command == "dry-run",
        resume,
    };
    println!("{}", serde_json::to_string(&run_repack(&cfg)?)?);
    Ok(())
}

fn main() {
    if let Err(e) = run() {
        eprintln!("pulsar-repack: {e}");
        std::process::exit(1);
    }
}
