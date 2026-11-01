mod ffi;
mod inherited;
mod native;
mod provenance;
mod slab;
use mlx_expert_ranges::{BoundedSource, PlaneDestination};
use mlx_native_affine::fixture::sha256_hex;
use native::{check, Native};
use packed_affine_adoption::{
    cases::{confined, manifest, Case},
    lease::Leases,
    registration, CONTRACT, LIVE_LIMIT,
};
use serde_json::{json, Value};
use slab::Slab;
use std::{fs, io::Write, path::Path, sync::atomic::Ordering, time::Instant};
fn event(f: &mut fs::File, value: Value) -> Result<(), String> {
    writeln!(f, "{value}").map_err(|e| e.to_string())
}
fn run(config: &Value, out: &Path, events: &mut fs::File) -> Result<Value, String> {
    if config["mode"] == "inherited" {
        return inherited::run(config, out, events);
    }
    let startup = Instant::now();
    let page = unsafe { ffi::pa_page() };
    let max = unsafe { ffi::pa_max_buffer() };
    let mut ctx = Native::open()?;
    if config["mode"] == "raw-length" {
        let slab = Slab::new(page, page)?;
        event(
            events,
            json!({"phase":"before-call","control":"P-RAW-LENGTH","allocation":page,"shape":[page/4-1]}),
        )?;
        events.sync_data().map_err(|e| e.to_string())?;
        let status = ctx.register(&slab, true)?;
        let callbacks = ctx.token.completed.load(Ordering::Acquire);
        event(
            events,
            json!({"phase":"after-return","status":status,"callbacks":callbacks}),
        )?;
        // Outside-contract probing never guesses transfer ownership. Process
        // teardown is the quarantine boundary, with no QMM or next allocation.
        event(
            events,
            json!({"phase":"cleanup","quarantine":true,"deallocation":"process-exit-only"}),
        )?;
        return Ok(
            json!({"control":"P-RAW-LENGTH","outcome":match status {0=>"outside-contract-acceptance",4=>"copied-fallback",_=>"native-error"},"status":status,"callbacks":callbacks,"qmm_calls":0,"quarantine":true}),
        );
    }
    let root = Path::new(config["fixture_root"].as_str().ok_or("fixture root")?);
    let fixture_hash = config["fixture_manifest_sha256"]
        .as_str()
        .ok_or("fixture hash")?;
    let manifest = manifest(root, fixture_hash)?;
    let ids = config["sequence"].as_array().ok_or("sequence")?;
    if ids.is_empty() || ids.len() > 3 {
        return Err("bounded sequence".into());
    }
    let mut cases = Vec::new();
    let mut inputs = Vec::new();
    for id in ids {
        let entry = manifest["cases"]
            .as_array()
            .ok_or("cases")?
            .iter()
            .find(|v| v["id"] == *id)
            .ok_or("unknown case")?;
        let c: Case = serde_json::from_value(entry.clone()).map_err(|e| e.to_string())?;
        let (x, parts, bound) = c.original(root)?;
        event(
            events,
            json!({"phase":"original-preflight","id":c.id,"bound_exponent":bound,"input_sha256":sha256_hex(&x.bytes),"component_hashes":c.expected_hashes}),
        )?;
        // Drop original HostTensor parts before allocating/adopting the pool.
        drop(parts);
        inputs.push(x.bytes);
        cases.push(c);
    }
    let first = &cases[0];
    let (n, k, bits) = first.geometry()?;
    if cases.iter().any(|c| {
        c.geometry().ok() != Some((n, k, bits))
            || c.m != first.m
            || c.source != first.source
            || c.role != first.role
    }) {
        return Err("one active class/source per child".into());
    }
    let weight = n * k * bits as usize / 8;
    let meta = n * k / 32;
    let registered = registration(weight, page, max).map_err(str::to_string)?;
    let working = registered + 2 * weight + 14 * meta + 3 * first.m * k * 4 + first.m * n * 8;
    if working > LIVE_LIMIT {
        return Err("conservative live working-data bound".into());
    }
    let mut slab = Slab::new(registered, page)?;
    let mut scales = [vec![0u8; meta], vec![0u8; meta]];
    let mut biases = [vec![0u8; meta], vec![0u8; meta]];
    let adopted = match config["arm"].as_str() {
        Some("adopted") => true,
        Some("copied") => false,
        _ => return Err("arm".into()),
    };
    let diagnostic = config["mode"] == "diagnostic";
    let resident = config["mode"] == "resident";
    if !diagnostic && !resident && config["mode"] != "fill" {
        return Err("mode".into());
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
    event(
        events,
        json!({"phase":"setup","page":page,"max_buffer_length":max,"registered_bytes":registered,"stream_id":unsafe{ffi::pa_stream(ctx.ptr)},"rust_capacity":registered+4*meta,"live_bound":working,"memory":ctx.memory()?,"adopted":adopted}),
    )?;
    // Native copying detector with a live source, distinct from callback injection.
    if diagnostic {
        check(unsafe { ffi::pa_copy_control(ctx.ptr, slab.pointer(), registered) })?;
        event(
            events,
            json!({"control":"C-COPY","reached":true,"pass":true}),
        )?;
    }
    let source = BoundedSource::open(&confined(root, &first.source)?).map_err(|e| e.to_string())?;
    let mut leases = Leases::default();
    let mut generations = [None, None];
    let count = if diagnostic {
        cases.len()
    } else {
        config["operations"].as_u64().ok_or("operation count")? as usize
    };
    if !diagnostic
        && (!((resident && [4096, 16384].contains(&count))
            || (!resident && [128, 512].contains(&count)))
            || cases.len() != 1)
    {
        return Err("preregistered block count".into());
    }
    let warmups = if diagnostic { 0 } else { 4 };
    let setup_seconds = startup.elapsed().as_secs_f64();
    let start = Instant::now();
    let mut samples = Vec::new();
    let mut outputs = Vec::new();
    let mut first_operation = None;
    for iteration in 0..count + warmups {
        let ci = if diagnostic { iteration } else { 0 };
        let c = &cases[ci];
        let slot = if diagnostic { 0 } else { iteration % 2 };
        if iteration == warmups && !diagnostic {
            check(unsafe { ffi::pa_reset_peak() })?;
        }
        let mut filled_record = None;
        let mut view_setup = None;
        let op = Instant::now();
        if !resident || generations[slot].is_none() {
            // Whole resource is quiescent: synchronize then release consumers.
            check(unsafe { ffi::pa_sync(ctx.ptr) })?;
            check(unsafe { ffi::pa_drop_slot(ctx.ptr, slot) })?;
            if !leases.quiescent() {
                return Err("whole-buffer not quiescent".into());
            }
            let generation = leases.begin_fill(slot).map_err(str::to_string)?;
            let plan = source.plan(c.request()).map_err(|e| e.to_string())?;
            if config["metadata_identities"][&c.id] != plan.record().metadata_snapshot_sha256 {
                return Err("frozen source metadata identity".into());
            }
            let result = {
                let destination = unsafe { slab.destination(slot * weight, weight) }?;
                plan.read_plane_into(
                    c.role()?,
                    PlaneDestination::new(
                        destination,
                        &mut scales[slot],
                        &mut biases[slot],
                        c.expected_hashes.clone(),
                    ),
                )
            };
            let receipt = match result {
                Ok(filled) => filled.into_receipt(),
                Err(e) => {
                    leases.failed_fill(generation).map_err(str::to_string)?;
                    return Err(e.to_string());
                }
            };
            if receipt.plane.expert != c.expert || receipt.actual_sha256 != c.expected_hashes {
                return Err("receipt identity".into());
            }
            let view_started = Instant::now();
            // No payload reference survives into native preparation.
            check(unsafe {
                ffi::pa_prepare(
                    ctx.ptr,
                    slot,
                    slab.pointer().add(slot * weight),
                    scales[slot].as_ptr(),
                    biases[slot].as_ptr(),
                    slot * weight,
                    n as i32,
                    k as i32,
                    bits as i32,
                    adopted,
                    diagnostic,
                    0,
                )
            })?;
            check(unsafe {
                ffi::pa_input(ctx.ptr, slot, inputs[ci].as_ptr(), first.m as i32, k as i32)
            })?;
            view_setup = Some(view_started.elapsed().as_secs_f64());
            filled_record = Some(receipt);
            leases.publish(generation).map_err(str::to_string)?;
            generations[slot] = Some(generation);
        }
        let generation = generations[slot].ok_or("generation")?;
        leases.lease(generation).map_err(str::to_string)?;
        let before = if diagnostic {
            Some(unsafe { slab.diagnostic_hash() })
        } else {
            None
        };
        if adopted && ctx.token.completed.load(Ordering::Acquire) != 0 {
            return Err("early callback before dispatch".into());
        }
        let mut output = vec![0f32; first.m * n];
        check(unsafe {
            ffi::pa_project(
                ctx.ptr,
                slot,
                first.m as i32,
                n as i32,
                k as i32,
                bits as i32,
                output.as_mut_ptr(),
            )
        })?;
        // The operation synchronizes and destroys the output graph. Retained
        // inputs/views are quiescent and released before a following fill.
        leases.release(generation).map_err(str::to_string)?;
        if diagnostic && before != Some(unsafe { slab.diagnostic_hash() }) {
            return Err("initialized slab mutated by native dispatch".into());
        }
        if adopted && ctx.token.completed.load(Ordering::Acquire) != 0 {
            return Err("early callback after dispatch".into());
        }
        let seconds = op.elapsed().as_secs_f64();
        if first_operation.is_none() {
            first_operation = Some(seconds);
        }
        if iteration >= warmups {
            samples.push(seconds);
        }
        if let Some(receipt) = filled_record {
            event(
                events,
                json!({"phase":"verified-fill","id":c.id,"population_id":c.population_id,"M":first.m,"N":n,"K":k,"bits":bits,"group":64,"dtypes":["U32","BF16","BF16"],"slot":slot,"generation":generation.number(),"receipt":receipt,"view_setup_seconds":view_setup}),
            )?;
        }
        let raw: Vec<u8> = output.iter().flat_map(|v| v.to_le_bytes()).collect();
        if diagnostic {
            let name = format!("output-{iteration}.f32");
            fs::write(out.join(&name), &raw).map_err(|e| e.to_string())?;
            outputs.push(json!({"id":c.id,"file":name,"sha256":sha256_hex(&raw),"dtype":"F32","shape":[first.m,n],"slot":slot,"generation":generation.number(),"slab_sha256":before}));
        }
        event(
            events,
            json!({"phase":"operation","iteration":iteration,"warmup":iteration<warmups,"id":c.id,"slot":slot,"generation":generation.number(),"seconds":seconds,"memory":ctx.memory()?,"output_sha256":sha256_hex(&raw)}),
        )?;
    }
    if diagnostic
        && outputs.len() == 3
        && outputs[0]["id"] == outputs[2]["id"]
        && outputs[0]["sha256"] != outputs[2]["sha256"]
    {
        return Err("A-B-A output mismatch".into());
    }
    let memory = ctx.memory()?;
    let callbacks_expected = u64::from(adopted);
    let counts = ctx.retire(&mut slab)?;
    Ok(
        json!({"identity":{"contract_sha256":CONTRACT,"fixture_manifest_sha256":fixture_hash},"host":{"vm_page_bytes":page,"max_buffer_length":max},"outputs":outputs,"adoption":{"method":if adopted{"managed-flat-parent"}else{"copied"},"registered_bytes":if adopted{registered}else{0},"pointer_identity":adopted},"lifetime":{"created":counts[0],"freed":counts[1],"live":counts[2],"parent_counts":[counts[3],counts[4]],"view_counts":[counts[5],counts[6]],"output_counts":[counts[7],counts[8]],"retired_parents":callbacks_expected,"completed_callbacks":callbacks_expected,"early_free_count":0,"quarantine":false},"io":{"requested_bytes":source.requested_payload_bytes(),"range_attempts":source.payload_read_calls(),"read_policy":"buffered-exact","overread_bytes":0,"physical_device_bytes":null},"copies":{"packed_import_bytes":if adopted{0}else{source.payload_read_calls()/3*weight as u64},"metadata_raw_bytes":source.payload_read_calls()/3*(2*meta) as u64,"metadata_widening_bytes":source.payload_read_calls()/3*(4*meta) as u64,"layout_materialization_bytes":null,"unknown_materialization":true,"output_bytes":(count+warmups)*first.m*n*4},"memory":{"raw_mlx_active_cache_peak":memory,"mlx_memory_limit_requested":LIVE_LIMIT,"mlx_cache_limit_requested":LIVE_LIMIT,"native_limit_calls_status":0,"live_working_bound":working,"combined_reservation":packed_affine_adoption::RESERVATION,"adopted_capacity_constant_within_reset":if adopted{registered}else{0},"reset_interval":if diagnostic{"startup and post-copy-control"}else{"after four warmups"},"clear_events":if diagnostic{2}else{1},"deduplicated_physical_usage":null,"rust_capacity":registered+4*meta,"adopted_overlap":if adopted{registered}else{0},"wiring":"unknown"},"timing":{"samples":samples,"first_operation":first_operation,"setup_seconds":setup_seconds,"startup_through_first_projection":setup_seconds+first_operation.unwrap_or(0.0),"total":startup.elapsed().as_secs_f64(),"block_wall_seconds":start.elapsed().as_secs_f64()},"decision":{"mechanism":"MEASURED_PENDING_PARENT_ACCEPTANCE","correctness":"PENDING_INDEPENDENT_REFERENCE","performance_screen":"PENDING","shipping_default":"copied"}}),
    )
}
fn main() {
    let args: Vec<_> = std::env::args().collect();
    if args.len() != 3 {
        eprintln!("adoption-probe CONFIG NEW_OUTPUT_DIR");
        std::process::exit(2);
    }
    let result = (|| -> Result<(), String> {
        let out = Path::new(&args[2]);
        fs::create_dir(out).map_err(|e| e.to_string())?;
        let mut events = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(out.join("events.jsonl"))
            .map_err(|e| e.to_string())?;
        let config: Value = serde_json::from_slice(&fs::read(&args[1]).map_err(|e| e.to_string())?)
            .map_err(|e| e.to_string())?;
        let provenance = provenance::collect(&config)?;
        event(
            &mut events,
            json!({"phase":"provenance","value":provenance}),
        )?;
        let result = run(&config, out, &mut events);
        let mut report = match &result {
            Ok(v) => v.clone(),
            Err(e) => {
                json!({"error":e,"quarantine":true,"native_qualification":"FAILED","shipping_default":"copied"})
            }
        };
        report["provenance"] = provenance;
        report["frozen_host"] = config["host"].clone();
        report["source_binding"] = json!({"source_commit":config["source_commit"],"source_tree":config["source_tree"],"dependency_manifest_sha256":config["dependency_manifest_sha256"],"generator_hashes":config["generator_hashes"]});
        report["config_sha256"] =
            json!(sha256_hex(&fs::read(&args[1]).map_err(|e| e.to_string())?));
        fs::write(
            out.join("run.json"),
            serde_json::to_vec_pretty(&report).unwrap(),
        )
        .map_err(|e| e.to_string())?;
        result.map(|_| ())
    })();
    if let Err(e) = result {
        eprintln!("{e}");
        std::process::exit(1);
    }
}
