//! Changed-import evidence only: reuse the unchanged Slice 2C loader and IDs.
use super::{
    event, ffi,
    native::{check, Native},
    slab::Slab,
};
use mlx_native_affine::{
    compose::{compose, stage, Source},
    dtype::Dtype,
    fixture::{sha256_hex, HostTensor},
    refusal::{check_qmm, DeviceFacts},
};
use serde_json::{json, Value};
use std::{collections::BTreeMap, fs, path::Path, sync::atomic::Ordering};
pub fn run(config: &Value, out: &Path, events: &mut fs::File) -> Result<Value, String> {
    let root = Path::new(config["inherited_root"].as_str().ok_or("inherited root")?);
    let raw = fs::read(root.join("manifest.json")).map_err(|e| e.to_string())?;
    if sha256_hex(&raw) != mlx_native_affine::frozen_compose::MANIFEST_SHA256 {
        return Err("frozen Slice2C manifest".into());
    }
    let manifest: Value = serde_json::from_slice(&raw).map_err(|e| e.to_string())?;
    let c = manifest["cases"]
        .as_array()
        .ok_or("cases")?
        .iter()
        .find(|v| v["id"] == config["case_id"])
        .ok_or("case id")?;
    if c["expected"]["outcome"] != "accept" {
        return Err("positive changed-import scope".into());
    }
    let dir = root.join(
        c["composition"]["checkpoint"]
            .as_str()
            .ok_or("checkpoint")?,
    );
    let cfg = fs::read_to_string(root.join(c["composition"]["config"].as_str().ok_or("config")?))
        .map_err(|e| e.to_string())?;
    let windows: BTreeMap<String, u64> =
        serde_json::from_value(c["composition"]["backing"]["windows"].clone())
            .map_err(|e| e.to_string())?;
    let source = Source::open(&dir, &cfg, &windows).map_err(|e| e.to_string())?;
    let indices: Vec<u64> = serde_json::from_value(c["composition"]["index_path"].clone())
        .map_err(|e| e.to_string())?;
    let plane = compose(
        &source,
        c["composition"]["module"].as_str().ok_or("module")?,
        &indices,
    )
    .map_err(|e| e.to_string())?;
    if plane.identity().to_json() != c["oracle"]["identity"] {
        return Err("inherited source identity".into());
    }
    let parts = stage(&plane)?;
    for (i, key) in ["w", "scales", "biases"].iter().enumerate() {
        if sha256_hex(&parts[i].bytes) != c["expected"]["staged_inputs"][key]["sha256"] {
            return Err("inherited plane bytes".into());
        }
    }
    let standalone =
        fs::read(root.join(c["file"].as_str().ok_or("input file")?)).map_err(|e| e.to_string())?;
    if sha256_hex(&standalone) != c["file_sha256"] {
        return Err("inherited standalone identity".into());
    }
    let t = c["tensors"]
        .as_array()
        .ok_or("tensors")?
        .iter()
        .find(|v| v["name"] == "x")
        .ok_or("x")?;
    let offset = t["offset"].as_u64().ok_or("offset")? as usize;
    let len = t["nbytes"].as_u64().ok_or("length")? as usize;
    let x = HostTensor {
        name: "x".into(),
        dtype: Dtype::F32,
        shape: serde_json::from_value(t["shape"].clone()).map_err(|e| e.to_string())?,
        bytes: standalone
            .get(offset..offset + len)
            .ok_or("input range")?
            .to_vec(),
    };
    let bits = c["params"]["bits"].as_u64().ok_or("bits")? as u32;
    let g = check_qmm(
        &DeviceFacts::GPU,
        true,
        &x,
        &parts[0],
        &parts[1],
        &parts[2],
        bits,
        64,
    )
    .map_err(|e| e.to_string())?;
    let page = unsafe { ffi::pa_page() };
    let size = packed_affine_adoption::registration(parts[0].bytes.len(), page, unsafe {
        ffi::pa_max_buffer()
    })
    .map_err(str::to_string)?;
    let mut slab = Slab::new(size, page)?;
    unsafe { slab.destination(0, parts[0].bytes.len()) }?.copy_from_slice(&parts[0].bytes);
    let mut ctx = Native::open()?;
    let adopted = config["arm"] == "adopted";
    if !adopted && config["arm"] != "copied" {
        return Err("arm".into());
    }
    if adopted {
        if let Err(reason) = ctx.register(&slab, false) {
            event(events, json!({"phase":"adoption-refused","reason":reason}))?;
            let retirement = ctx.retire(&mut slab);
            event(
                events,
                json!({"phase":"refusal-cleanup","retirement":retirement,"quarantine":retirement.is_err()}),
            )?;
            return Err(reason);
        }
    }
    check(unsafe {
        ffi::pa_prepare(
            ctx.ptr,
            0,
            slab.pointer(),
            parts[1].bytes.as_ptr(),
            parts[2].bytes.as_ptr(),
            0,
            g.n as i32,
            g.k as i32,
            bits as i32,
            adopted,
            true,
            0,
        )
    })?;
    check(unsafe { ffi::pa_input(ctx.ptr, 0, x.bytes.as_ptr(), g.m_eff as i32, g.k as i32) })?;
    let before = unsafe { slab.diagnostic_hash() };
    let mut output = vec![0f32; g.m_eff * g.n];
    check(unsafe {
        ffi::pa_project(
            ctx.ptr,
            0,
            g.m_eff as i32,
            g.n as i32,
            g.k as i32,
            bits as i32,
            output.as_mut_ptr(),
        )
    })?;
    if before != unsafe { slab.diagnostic_hash() }
        || ctx.token.completed.load(Ordering::Acquire) != 0
    {
        return Err("inherited changed-import mutation/early callback".into());
    }
    let raw: Vec<_> = output.iter().flat_map(|v| v.to_le_bytes()).collect();
    fs::write(out.join("output.f32"), &raw).map_err(|e| e.to_string())?;
    let memory = ctx.memory()?;
    let counts = ctx.retire(&mut slab)?;
    event(
        events,
        json!({"id":c["id"],"original_loader":"unchanged Source::open/compose/stage","slab_sha256":before,"memory":memory,"source_identity":plane.identity().to_json()}),
    )?;
    Ok(
        json!({"id":c["id"],"population":"inherited_slice2c_changed_import","original_population_unchanged":true,"output":{"file":"output.f32","dtype":"F32","sha256":sha256_hex(&raw)},"lifetime":{"created":counts[0],"freed":counts[1],"live":counts[2],"parent_counts":[counts[3],counts[4]],"view_counts":[counts[5],counts[6]],"output_counts":[counts[7],counts[8]],"completed_callbacks":u64::from(adopted),"early_free_count":0},"quarantine":false,"numerical_acceptance":"PENDING_ORIGINAL_GATES"}),
    )
}
