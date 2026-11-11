//! Verifier process isolation and the ABI witness for the fixed M2b ledger.
use std::{ffi::OsStr, mem::size_of, path::Path, process::Command};

pub(super) fn layout_stamp() -> &'static str {
    if cfg!(all(
        target_os = "macos",
        target_arch = "aarch64",
        target_pointer_width = "64",
        target_endian = "little"
    )) && size_of::<mlx_expert_ranges::BoundedSource>() == 368
        && size_of::<(String, serde_json::Value)>() == 56
        && size_of::<Option<std::fs::File>>() == 4
    {
        concat!(
            "pulsarmlx.resident-layout/1|aarch64-apple-darwin|",
            env!("F020_RUSTC_VERSION"),
            "|end"
        )
    } else {
        "unsupported resident accounting layout"
    }
}

fn configure(cmd: &mut Command, home: &OsStr) {
    cmd.env_clear()
        .env("HOME", home)
        .env("PATH", "/usr/bin:/bin:/usr/sbin:/sbin");
    cmd.args(["-I", "-S", "-B", "-c"]);
}

pub(super) fn verifier_command(
    script: &str,
    modules: &str,
    intent: &Path,
) -> Result<Command, String> {
    let home = std::env::var_os("HOME").ok_or("missing verifier home")?;
    if !Path::new(&home).is_absolute() {
        return Err("absolute verifier home required".into());
    }
    let mut cmd = Command::new("/usr/bin/python3");
    configure(&mut cmd, &home);
    cmd.arg(script).arg(modules).arg(intent);
    Ok(cmd)
}

#[cfg(all(test, target_os = "macos", target_arch = "aarch64"))]
mod tests {
    use super::*;
    #[test]
    fn verifier_scrubs_native_loader_python_git_and_credential_overrides() {
        assert_eq!(
            layout_stamp(),
            concat!(
                "pulsarmlx.resident-layout/1|aarch64-apple-darwin|",
                env!("F020_RUSTC_VERSION"),
                "|end"
            )
        );
        let mut cmd = Command::new("/usr/bin/python3");
        for name in [
            "DYLD_LIBRARY_PATH",
            "LD_LIBRARY_PATH",
            "PYTHONPATH",
            "GIT_CONFIG_GLOBAL",
            "GH_TOKEN",
            "MLX_C_PREFIX",
        ] {
            cmd.env(name, "synthetic-test-marker");
        }
        configure(&mut cmd, OsStr::new("/"));
        let keys: Vec<_> = cmd.get_envs().map(|(key, _)| key).collect();
        assert_eq!(keys, [OsStr::new("HOME"), OsStr::new("PATH")]);
        let out=cmd.arg("import os,sys; assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode; assert os.environ['HOME']=='/'; assert 'synthetic-test-marker' not in os.environ.values()").output().unwrap();
        assert!(out.status.success(), "{:?}", out.status);
        let script = "import os,sys; assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode; assert sys.argv[1:] == ['[]','synthetic-intent']; assert not any(k.startswith(('DYLD_', 'GIT_', 'PYTHON')) for k in os.environ)";
        let mut actual = verifier_command(script, "[]", Path::new("synthetic-intent")).unwrap();
        assert_eq!(actual.get_program(), OsStr::new("/usr/bin/python3"));
        assert_eq!(
            actual.get_envs().map(|(k, _)| k).collect::<Vec<_>>(),
            [OsStr::new("HOME"), OsStr::new("PATH")]
        );
        assert!(actual.status().unwrap().success());
    }
}
