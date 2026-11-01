//! Frozen binary64 gate, applied by a host-only process to saved native outputs.
use mlx_affine::reference_qmm::{qmm_reference, QmmMetadata};
use mlx_native_affine::{
    fixture::{load_case, parse_manifest, sha256_hex},
    gates::g_qmm_rust,
};
use serde_json::{json, Value};
use std::{fs, path::Path};
fn run() -> Result<(), String> {
    let a: Vec<_> = std::env::args().collect();
    if a.len() != 5 {
        return Err("grade-rust PORTABLE INHERITED_ROOT NATIVE_REPORT NEW_RESULT".into());
    }
    let p: Value = serde_json::from_slice(&fs::read(&a[1]).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    let path = Path::new(&a[3]);
    let run: Value = serde_json::from_slice(&fs::read(path).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    let inherited = run["population"] == "inherited_slice2c_changed_import";
    let outputs = if inherited {
        vec![json!({"id":run["id"],"output":run["output"]})]
    } else {
        run["outputs"]
            .as_array()
            .ok_or("outputs")?
            .iter()
            .map(|o| json!({"id":o["id"],"output":o}))
            .collect()
    };
    if outputs.is_empty() {
        return Err("no outputs".into());
    }
    let mut rows = Vec::new();
    for record in outputs {
        let id = record["id"].as_str().ok_or("case id")?;
        let (rust, k, exponent) = if inherited {
            let dir = Path::new(&a[2]);
            let raw = fs::read(dir.join("manifest.json")).map_err(|e| e.to_string())?;
            if sha256_hex(&raw) != mlx_native_affine::frozen_compose::MANIFEST_SHA256 {
                return Err("inherited manifest".into());
            }
            let m = parse_manifest(&raw).map_err(|e| e.to_string())?;
            let spec = m
                .cases
                .iter()
                .find(|c| c.id == id && !c.is_refusal())
                .ok_or("inherited case")?;
            let c = load_case(dir, spec).map_err(|e| e.to_string())?;
            let t = |s: &str| c.tensor(s).unwrap();
            let s = t("scales").halves_u16();
            let b = t("biases").halves_u16();
            let param = |s: &str| spec.param_u64(s).unwrap() as usize;
            let r = qmm_reference(
                &t("x").words_u32(),
                &t("w").words_u32(),
                QmmMetadata::Bf16 {
                    scales: &s,
                    biases: &b,
                },
                param("M_eff"),
                param("N"),
                param("K"),
                param("bits") as u32,
                64,
            )
            .map_err(|e| e.to_string())?;
            (
                json!({"y":r.y.iter().map(|v|format!("{:016x}",v.to_bits())).collect::<Vec<_>>(),"phi":r.phi.iter().map(|v|format!("{:016x}",v.to_bits())).collect::<Vec<_>>()}),
                param("K"),
                spec.manifest_gamma_n().ok_or("family exponent")? as usize,
            )
        } else {
            if run["identity"]["fixture_manifest_sha256"] != p["fixture_manifest_sha256"] {
                return Err("portable binding".into());
            }
            let case = p["cases"]
                .as_array()
                .ok_or("portable cases")?
                .iter()
                .find(|c| c["id"] == id)
                .ok_or("unknown case")?;
            let k = case["receipt"]["plane"]["logical_shape"][1]
                .as_u64()
                .ok_or("K")? as usize;
            if k == 4096 {
                rows.push(json!({"id":id,"gate":"selected exact original-input R1 required separately","rust":null}));
                continue;
            }
            (
                p["rust_r1"][id].clone(),
                k,
                case["bound_exponent"].as_u64().ok_or("bound")? as usize,
            )
        };
        let output = &record["output"];
        let raw = fs::read(packed_affine_adoption::cases::confined(
            path.parent().ok_or("report root")?,
            output["file"].as_str().ok_or("output file")?,
        )?)
        .map_err(|e| e.to_string())?;
        if output["dtype"] != "F32"
            || sha256_hex(&raw) != output["sha256"].as_str().ok_or("output hash")?
        {
            return Err("native output binding".into());
        }
        let y = rust["y"].as_array().ok_or("Rust y")?;
        let phi = rust["phi"].as_array().ok_or("Rust phi")?;
        if raw.len() != y.len() * 4 || y.len() != phi.len() {
            return Err("output cardinality".into());
        }
        let parse = |v: &Value| {
            u64::from_str_radix(v.as_str().ok_or("reference encoding")?, 16)
                .map(f64::from_bits)
                .map_err(|_| "reference bits")
        };
        for ((v, y), ph) in raw.chunks_exact(4).zip(y).zip(phi) {
            if !g_qmm_rust(
                f32::from_le_bytes(v.try_into().unwrap()),
                parse(y)?,
                parse(ph)?,
                k,
                exponent,
            )
            .0
            {
                return Err(format!("G-QMM-RUST failed: {id}"));
            }
        }
        rows.push(json!({"id":id,"G-QMM-RUST":"PASS","rust":rust}));
    }
    use std::io::Write;
    let mut f = fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(&a[4])
        .map_err(|e| e.to_string())?;
    writeln!(
        f,
        "{}",
        serde_json::to_string_pretty(
            &json!({"report_sha256":sha256_hex(&fs::read(path).unwrap()),"cases":rows})
        )
        .unwrap()
    )
    .map_err(|e| e.to_string())?;
    Ok(())
}
fn main() {
    if let Err(e) = run() {
        eprintln!("{e}");
        std::process::exit(1);
    }
}
