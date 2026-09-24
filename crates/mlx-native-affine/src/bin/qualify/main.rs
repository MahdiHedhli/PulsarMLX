//! `qualify` -- the F020 Slice 2B qualification child.
//!
//! ```text
//! qualify --repo <checkout> --out <dir> [--mode qualify|selftest] [--test-fault <kind>]
//! ```
//!
//! Before any MLX-C call the child asserts its start environment
//! (A-NONAX.runtime_assertion): `MLX_ENABLE_TF32` must be exactly `0` and
//! `MLX_METAL_GPU_ARCH`, `MLX_MAX_OPS_PER_BUFFER`, `MLX_MAX_MB_PER_BUFFER`
//! must be unset; otherwise it refuses with R-NAX and exits with the dedicated
//! status (78) without touching MLX.
//!
//! `--test-fault` exists only so the parent's failure paths can be exercised
//! (acceptance B9): `abort` raises SIGABRT after MLX is initialised, `hang`
//! never returns, `exit` exits 7, `no-report` exits 0 without a report, and
//! `garbage-report` writes an unparsable report and exits 0. The parent treats
//! every one of them as a failure.

use std::path::PathBuf;
use std::process::ExitCode;

use mlx_native_affine::frozen;

#[cfg(pulsar_native_mlx)]
mod bridge;
#[cfg(pulsar_native_mlx)]
mod ffi;
#[cfg(pulsar_native_mlx)]
mod native;
#[cfg(pulsar_native_mlx)]
mod provenance;
#[cfg(pulsar_native_mlx)]
mod run;

pub struct Args {
    pub repo: PathBuf,
    pub out: PathBuf,
    pub mode: String,
    pub test_fault: Option<String>,
}

fn parse_args() -> Result<Args, String> {
    let mut repo = None;
    let mut out = None;
    let mut mode = "qualify".to_string();
    let mut test_fault = None;
    let mut it = std::env::args().skip(1);
    while let Some(a) = it.next() {
        let mut val = || it.next().ok_or_else(|| format!("{a} needs a value"));
        match a.as_str() {
            "--repo" => repo = Some(PathBuf::from(val()?)),
            "--out" => out = Some(PathBuf::from(val()?)),
            "--mode" => mode = val()?,
            "--test-fault" => test_fault = Some(val()?),
            other => return Err(format!("unknown argument {other}")),
        }
    }
    if mode != "qualify" && mode != "selftest" {
        return Err(format!("unknown mode {mode}"));
    }
    Ok(Args {
        repo: repo.ok_or("--repo is required")?,
        out: out.ok_or("--out is required")?,
        mode,
        test_fault,
    })
}

/// A-NONAX runtime assertion; no MLX-C function has been called yet.
fn check_environment() -> Result<(), String> {
    for (k, v) in frozen::REQUIRED_ENV {
        match std::env::var(k) {
            Ok(got) if got == v => {}
            Ok(got) => return Err(format!("{k}={got:?}, required {v:?}")),
            Err(_) => return Err(format!("{k} unset, required {v:?}")),
        }
    }
    for k in frozen::FORBIDDEN_ENV {
        if std::env::var_os(k).is_some() {
            return Err(format!("{k} is set"));
        }
    }
    Ok(())
}

fn main() -> ExitCode {
    if let Err(detail) = check_environment() {
        eprintln!("R-NAX: {detail}");
        return ExitCode::from(frozen::R_NAX_EXIT_STATUS as u8);
    }
    let args = match parse_args() {
        Ok(a) => a,
        Err(e) => {
            eprintln!("qualify: {e}");
            return ExitCode::from(64);
        }
    };
    native_main(&args)
}

#[cfg(not(pulsar_native_mlx))]
fn native_main(_args: &Args) -> ExitCode {
    eprintln!("qualify: built without the pinned native MLX prefix (MLX_C_PREFIX/MLX_PREFIX); refusing to run");
    ExitCode::from(frozen::NATIVE_UNAVAILABLE_EXIT_STATUS as u8)
}

#[cfg(pulsar_native_mlx)]
fn native_main(args: &Args) -> ExitCode {
    if let Some(fault) = &args.test_fault {
        return test_fault(fault, args);
    }
    let r = if args.mode == "selftest" {
        run::selftest(args)
    } else {
        run::qualify(args)
    };
    match r {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("qualify: setup failure: {e}");
            ExitCode::from(frozen::SETUP_FAILURE_EXIT_STATUS as u8)
        }
    }
}

#[cfg(pulsar_native_mlx)]
fn test_fault(kind: &str, args: &Args) -> ExitCode {
    // Initialise MLX exactly as a qualification does, then fail.
    native::ensure_error_handler();
    let _ = native::set_default_device_gpu();
    match kind {
        "abort" => std::process::abort(),
        "hang" => loop {
            std::thread::sleep(std::time::Duration::from_secs(3600));
        },
        "exit" => ExitCode::from(7),
        "no-report" => ExitCode::SUCCESS,
        "garbage-report" => {
            let _ = std::fs::create_dir_all(&args.out);
            let _ = std::fs::write(args.out.join("report.json"), b"{ this is not json");
            ExitCode::SUCCESS
        }
        _ => ExitCode::from(64),
    }
}
