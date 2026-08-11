use crate::cli::RunnerMode;
use crate::{FailureClass, RunnerError};
use serde::{Deserialize, Serialize};
use std::path::Path;
use std::process::Command;

pub const MINIMUM_EVIDENCE_DISK_BYTES: u64 = 16 * 1024 * 1024;
pub const MAXIMUM_ADMISSION_SWAP_BYTES: u64 = 256 * 1024 * 1024;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct HostAdmission {
    pub telemetry_source: String,
    pub physical_memory_bytes: u64,
    pub available_memory_bytes: u64,
    pub compressed_memory_bytes: u64,
    pub memory_pressure: String,
    pub swap_used_bytes: u64,
    pub checkpoint_volume_free_bytes: Option<u64>,
    pub evidence_volume_free_bytes: u64,
    pub load_averages: [f64; 3],
    pub competing_processes_clear: bool,
    pub competing_processes: Vec<String>,
    pub port_1234_listener: bool,
    pub thermal_state: String,
    pub performance_warning: bool,
}

impl HostAdmission {
    pub fn collect(
        mode: &RunnerMode,
        production: bool,
        checkpoint: Option<&Path>,
        out: &Path,
    ) -> Result<Self, RunnerError> {
        if !production || matches!(mode, RunnerMode::Fixture { .. } | RunnerMode::DryRun) {
            return Ok(Self::synthetic_fixture());
        }
        collect_macos(checkpoint, out)
    }

    pub fn validate(
        &self,
        mode: &RunnerMode,
        production: bool,
        memory_floor_bytes: u64,
    ) -> Result<(), RunnerError> {
        if !production || matches!(mode, RunnerMode::Fixture { .. } | RunnerMode::DryRun) {
            if self.telemetry_source != "synthetic_fixture" {
                return Err(admission(
                    "fixture_telemetry_source",
                    "fixture telemetry source differs",
                ));
            }
            return Ok(());
        }
        if self.telemetry_source != "measured_host" {
            return Err(admission(
                "production_telemetry_source",
                "production modes require measured host telemetry",
            ));
        }
        if memory_floor_bytes == 0 {
            return Err(admission(
                "memory_floor_zero",
                "production memory floor must be positive",
            ));
        }
        if self.physical_memory_bytes == 0 || self.available_memory_bytes < memory_floor_bytes {
            return Err(admission(
                "memory_floor",
                "available memory is below the absolute floor",
            ));
        }
        if self.swap_used_bytes > MAXIMUM_ADMISSION_SWAP_BYTES {
            return Err(admission(
                "swap_usage",
                "swap usage exceeds the reviewed negligible admission bound",
            ));
        }
        if matches!(
            self.memory_pressure.as_str(),
            "critical" | "urgent" | "unavailable"
        ) {
            return Err(admission(
                "memory_pressure",
                "memory pressure is not admissible",
            ));
        }
        if !self.competing_processes_clear || self.port_1234_listener {
            return Err(admission(
                "competing_inference",
                "competing local inference is present",
            ));
        }
        if self.evidence_volume_free_bytes < MINIMUM_EVIDENCE_DISK_BYTES {
            return Err(admission(
                "evidence_disk",
                "evidence volume has insufficient free space",
            ));
        }
        if matches!(mode, RunnerMode::CheckpointIdentity)
            && self.checkpoint_volume_free_bytes.is_none()
        {
            return Err(admission(
                "checkpoint_disk",
                "checkpoint volume telemetry is unavailable",
            ));
        }
        if self.thermal_state == "warning" || self.performance_warning {
            return Err(admission(
                "thermal_warning",
                "hard thermal or performance warning is active",
            ));
        }
        Ok(())
    }

    fn synthetic_fixture() -> Self {
        Self {
            telemetry_source: "synthetic_fixture".to_owned(),
            physical_memory_bytes: 1,
            available_memory_bytes: 1,
            compressed_memory_bytes: 0,
            memory_pressure: "synthetic".to_owned(),
            swap_used_bytes: 0,
            checkpoint_volume_free_bytes: None,
            evidence_volume_free_bytes: 1,
            load_averages: [0.0; 3],
            competing_processes_clear: true,
            competing_processes: Vec::new(),
            port_1234_listener: false,
            thermal_state: "not_applicable".to_owned(),
            performance_warning: false,
        }
    }
}

#[cfg(target_os = "macos")]
fn collect_macos(checkpoint: Option<&Path>, out: &Path) -> Result<HostAdmission, RunnerError> {
    let physical_memory_bytes = sysctl_u64("hw.memsize")?;
    let vm = command("vm_stat", &[])?;
    let page_size = parse_page_size(&vm)?;
    let free_pages = vm_pages(&vm, "Pages free")?
        .saturating_add(vm_pages(&vm, "Pages inactive")?)
        .saturating_add(vm_pages(&vm, "Pages speculative")?);
    let compressed_pages = vm_pages(&vm, "Pages occupied by compressor").unwrap_or(0);
    let pressure = command("memory_pressure", &["-Q"])?;
    let memory_pressure = parse_memory_pressure(&pressure)?;
    let swap = command("sysctl", &["-n", "vm.swapusage"])?;
    let swap_used_bytes = parse_swap_used(&swap)?;
    let mut load = [0.0; 3];
    unsafe { libc::getloadavg(load.as_mut_ptr(), 3) };
    let (competing_processes, port_1234_listener) = competing_processes()?;
    let evidence_parent = out.parent().unwrap_or_else(|| Path::new("."));
    let evidence_volume_free_bytes = disk_free(evidence_parent)?;
    let checkpoint_volume_free_bytes = checkpoint
        .and_then(Path::parent)
        .map(disk_free)
        .transpose()?;
    let thermal = command("pmset", &["-g", "therm"]).unwrap_or_default();
    let lower = thermal.to_ascii_lowercase();
    let performance_warning =
        lower.contains("performance warning") && !lower.contains("no performance warning");
    let thermal_state =
        if lower.contains("thermal warning") && !lower.contains("no thermal warning") {
            "warning"
        } else if thermal.is_empty() {
            "unavailable"
        } else {
            "normal"
        };
    Ok(HostAdmission {
        telemetry_source: "measured_host".to_owned(),
        physical_memory_bytes,
        available_memory_bytes: free_pages.saturating_mul(page_size),
        compressed_memory_bytes: compressed_pages.saturating_mul(page_size),
        memory_pressure,
        swap_used_bytes,
        checkpoint_volume_free_bytes,
        evidence_volume_free_bytes,
        load_averages: load,
        competing_processes_clear: competing_processes.is_empty() && !port_1234_listener,
        competing_processes,
        port_1234_listener,
        thermal_state: thermal_state.to_owned(),
        performance_warning,
    })
}

#[cfg(not(target_os = "macos"))]
fn collect_macos(_checkpoint: Option<&Path>, _out: &Path) -> Result<HostAdmission, RunnerError> {
    Err(admission(
        "host_telemetry_platform",
        "production telemetry requires macOS",
    ))
}

#[cfg(target_os = "macos")]
fn sysctl_u64(name: &str) -> Result<u64, RunnerError> {
    let mut value = 0_u64;
    let mut size = std::mem::size_of::<u64>();
    let name = std::ffi::CString::new(name).unwrap();
    let status = unsafe {
        libc::sysctlbyname(
            name.as_ptr(),
            (&mut value as *mut u64).cast(),
            &mut size,
            std::ptr::null_mut(),
            0,
        )
    };
    if status != 0 || size != std::mem::size_of::<u64>() {
        return Err(admission(
            "host_telemetry_sysctl",
            "required sysctl is unavailable",
        ));
    }
    Ok(value)
}

#[cfg(target_os = "macos")]
fn disk_free(path: &Path) -> Result<u64, RunnerError> {
    use std::os::unix::ffi::OsStrExt;
    let path = std::ffi::CString::new(path.as_os_str().as_bytes())
        .map_err(|_| admission("disk_path", "disk path contains NUL"))?;
    let mut stat: libc::statvfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::statvfs(path.as_ptr(), &mut stat) } != 0 {
        return Err(admission(
            "disk_telemetry",
            "cannot stat evidence/checkpoint volume",
        ));
    }
    Ok(u64::from(stat.f_bavail).saturating_mul(stat.f_frsize))
}

#[cfg(target_os = "macos")]
fn command(program: &str, args: &[&str]) -> Result<String, RunnerError> {
    let output = Command::new(program)
        .args(args)
        .output()
        .map_err(|error| admission("host_telemetry_command", error))?;
    if !output.status.success() {
        return Err(admission(
            "host_telemetry_command",
            format!("{program} failed"),
        ));
    }
    String::from_utf8(output.stdout).map_err(|error| admission("host_telemetry_utf8", error))
}

#[cfg(target_os = "macos")]
fn parse_page_size(value: &str) -> Result<u64, RunnerError> {
    value
        .lines()
        .next()
        .and_then(|line| line.split("page size of ").nth(1))
        .and_then(|part| part.split_whitespace().next())
        .and_then(|part| part.parse().ok())
        .ok_or_else(|| admission("vm_stat_parse", "vm_stat page size is unavailable"))
}

#[cfg(target_os = "macos")]
fn vm_pages(value: &str, key: &str) -> Result<u64, RunnerError> {
    value
        .lines()
        .find(|line| line.starts_with(key))
        .and_then(|line| line.split(':').nth(1))
        .map(|part| part.trim().trim_end_matches('.'))
        .and_then(|part| part.parse().ok())
        .ok_or_else(|| admission("vm_stat_parse", format!("{key} is unavailable")))
}

#[cfg(target_os = "macos")]
fn parse_memory_pressure(value: &str) -> Result<String, RunnerError> {
    let lower = value.to_ascii_lowercase();
    if lower.contains("critical") {
        Ok("critical".to_owned())
    } else if lower.contains("urgent") {
        Ok("urgent".to_owned())
    } else if lower.contains("normal") || lower.contains("system-wide memory free percentage") {
        Ok("normal".to_owned())
    } else {
        Err(admission(
            "memory_pressure_parse",
            "memory pressure state is unavailable",
        ))
    }
}

#[cfg(target_os = "macos")]
fn parse_swap_used(value: &str) -> Result<u64, RunnerError> {
    let used = value
        .split("used = ")
        .nth(1)
        .and_then(|v| v.split_whitespace().next())
        .ok_or_else(|| admission("swap_parse", "swap usage is unavailable"))?;
    parse_byte_quantity(used.trim_matches(|c: char| c == '=' || c == ','))
}

#[cfg(target_os = "macos")]
fn parse_byte_quantity(value: &str) -> Result<u64, RunnerError> {
    let split = value
        .find(|c: char| !c.is_ascii_digit() && c != '.')
        .unwrap_or(value.len());
    let number: f64 = value[..split]
        .parse()
        .map_err(|_| admission("swap_parse", "swap number is malformed"))?;
    let multiplier = match value[split..].trim().to_ascii_uppercase().as_str() {
        "B" | "" => 1.0,
        "K" | "KB" => 1024.0,
        "M" | "MB" => 1024.0 * 1024.0,
        "G" | "GB" => 1024.0 * 1024.0 * 1024.0,
        _ => return Err(admission("swap_parse", "swap unit is unsupported")),
    };
    Ok((number * multiplier) as u64)
}

#[cfg(target_os = "macos")]
fn competing_processes() -> Result<(Vec<String>, bool), RunnerError> {
    let output = command("ps", &["-axo", "pid=,comm=,args="])?;
    let self_pid = std::process::id().to_string();
    let markers = [
        "LM Studio",
        "lmstudio",
        "llama-server",
        "ollama serve",
        "mlx_lm",
        "f017-glm52-runner",
    ];
    let mut found = Vec::new();
    for line in output.lines() {
        let trimmed = line.trim();
        let mut parts = trimmed.split_whitespace();
        let pid = parts.next().unwrap_or("unknown");
        let name = parts.next().unwrap_or("unknown");
        if pid == self_pid {
            continue;
        }
        let is_runner = name.ends_with("f017-glm52-runner");
        let is_other = markers[..5].iter().any(|marker| trimmed.contains(marker));
        if is_runner || is_other {
            found.push(format!("pid={pid};process={name}"));
        }
    }
    let listener = Command::new("lsof")
        .args(["-nP", "-iTCP:1234", "-sTCP:LISTEN"])
        .output()
        .is_ok_and(|output| {
            output.status.success() && output.stdout.split(|byte| *byte == b'\n').count() > 1
        });
    Ok((found, listener))
}

fn admission(code: &'static str, message: impl std::fmt::Display) -> RunnerError {
    RunnerError::new(
        FailureClass::AdmissionEnvironment,
        code,
        message.to_string(),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn production_admission_fails_closed() {
        let mode = RunnerMode::AdapterPreflight;
        let mut value = HostAdmission::synthetic_fixture();
        assert!(value.validate(&mode, true, 1).is_err());
        value.telemetry_source = "measured_host".to_owned();
        value.physical_memory_bytes = 128;
        value.available_memory_bytes = 128;
        value.evidence_volume_free_bytes = MINIMUM_EVIDENCE_DISK_BYTES;
        value.memory_pressure = "normal".to_owned();
        value.thermal_state = "unavailable".to_owned();
        assert!(value.validate(&mode, true, 1).is_ok());
        value.available_memory_bytes = 0;
        assert!(value.validate(&mode, true, 1).is_err());
        value.available_memory_bytes = 128;
        value.competing_processes_clear = false;
        assert!(value.validate(&mode, true, 1).is_err());
        value.competing_processes_clear = true;
        value.memory_pressure = "urgent".to_owned();
        assert!(value.validate(&mode, true, 1).is_err());
    }
}
