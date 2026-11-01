//! Original-byte preflight and reader equivalence. No native code is linked.
use mlx_expert_ranges::{BoundedSource, PlaneDestination};
use mlx_native_affine::fixture::sha256_hex;
use packed_affine_adoption::cases::{confined, manifest, Case};
use serde_json::json;
use std::{fs, path::Path};
fn run() -> Result<(), String> {
    let args: Vec<_> = std::env::args().collect();
    if args.len() != 4 {
        return Err("portable-check FIXTURES MANIFEST_SHA REPORT (create-only)".into());
    }
    let root = Path::new(&args[1]);
    let manifest = manifest(root, &args[2])?;
    let mut results = Vec::new();
    let mut references = serde_json::Map::new();
    for (name, record) in manifest["files"].as_object().ok_or("files")? {
        let raw = fs::read(confined(root, name)?).map_err(|e| e.to_string())?;
        if raw.len() as u64 != record["bytes"].as_u64().ok_or("bytes")?
            || sha256_hex(&raw) != record["sha256"].as_str().ok_or("sha")?
        {
            return Err("frozen file identity".into());
        }
    }
    for value in manifest["cases"].as_array().ok_or("cases")? {
        let case: Case = serde_json::from_value(value.clone()).map_err(|e| e.to_string())?;
        let (input, original, exponent) = case.original(root)?;
        let source =
            BoundedSource::open(&confined(root, &case.source)?).map_err(|e| e.to_string())?;
        let plan = source.plan(case.request()).map_err(|e| e.to_string())?;
        let mut storage: [Vec<u8>; 3] =
            std::array::from_fn(|i| vec![0xa5; original[i].bytes.len()]);
        let [w, s, b] = &mut storage;
        let receipt = plan
            .read_plane_into(
                case.role()?,
                PlaneDestination::new(w, s, b, case.expected_hashes.clone()),
            )
            .map_err(|e| e.to_string())?
            .into_receipt();
        for i in 0..3 {
            if storage[i] != original[i].bytes {
                return Err("original byte equivalence".into());
            }
        }
        if case.d == 128 {
            use mlx_affine::reference_qmm::{qmm_reference, QmmMetadata};
            let words = |b: &[u8]| {
                b.chunks_exact(4)
                    .map(|c| u32::from_le_bytes(c.try_into().unwrap()))
                    .collect::<Vec<_>>()
            };
            let halves = |b: &[u8]| {
                b.chunks_exact(2)
                    .map(|c| u16::from_le_bytes(c.try_into().unwrap()))
                    .collect::<Vec<_>>()
            };
            let r = qmm_reference(
                &words(&input.bytes),
                &words(&original[0].bytes),
                QmmMetadata::Bf16 {
                    scales: &halves(&original[1].bytes),
                    biases: &halves(&original[2].bytes),
                },
                case.m,
                case.h as usize,
                case.d as usize,
                case.bits[case.role()?.index()],
                64,
            )
            .map_err(|e| e.to_string())?;
            references.insert(case.id.clone(),json!({"y":r.y.iter().map(|v|format!("{:016x}",v.to_bits())).collect::<Vec<_>>(),"phi":r.phi.iter().map(|v|format!("{:016x}",v.to_bits())).collect::<Vec<_>>()}));
        }
        results.push(json!({"id":case.id,"original_preflight":"PASS","bound_exponent":exponent,"receipt":receipt,"read_calls":source.payload_read_calls(),"requested_bytes":source.requested_payload_bytes()}));
    }
    let report = json!({"schema":"pulsarmlx.adoption-portable/1","contract_sha256":packed_affine_adoption::CONTRACT,"fixture_manifest_sha256":args[2],"cases":results,"rust_r1":references,"native_calls":0,"native_qualification":"PENDING","shipping_default":"copied"});
    use std::io::Write;
    let mut out = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&args[3])
        .map_err(|e| e.to_string())?;
    writeln!(out, "{}", serde_json::to_string_pretty(&report).unwrap())
        .map_err(|e| e.to_string())?;
    println!("20 original preflights and exact three-component fills passed; native qualification pending");
    Ok(())
}
fn main() {
    if let Err(e) = run() {
        eprintln!("{e}");
        std::process::exit(1);
    }
}
