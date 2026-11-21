// Synthetic-only admitted child. No explicit MLX call precedes the stdin G gate.
// Aux completes successful calls before host readback. On failure, pending work
// on its borrowed stream remains possible; these prechecks never enqueue work.
#[test]
#[ignore = "admitted Studio019 auxiliary stream-reuse child only; requires stdin G and exclusive output directory"]
fn aux_caller_owned_stream_reuse() {
    use std::collections::BTreeSet;
    use std::fs::{File, OpenOptions};
    use std::io::{Read, Write};
    use std::os::unix::fs::OpenOptionsExt;
    use std::path::PathBuf;

    unsafe extern "C" {
        fn mlx_stream_get_index(index: *mut i32, stream: crate::ffi::mlx_stream) -> i32;
    }
    fn index(ctx: &NativeContext) -> i32 {
        let mut value = -1;
        // SAFETY: query the live owner stream on its owning thread.
        assert_eq!(
            unsafe { mlx_stream_get_index(&mut value, ctx.borrowed_stream()) },
            0
        );
        value
    }
    fn event(iteration: usize, operation: &str, ctx: &NativeContext) {
        println!(
            "{}",
            serde_json::json!({"event":"operation","iteration":iteration,
            "operation":operation,"stream_index":index(ctx)})
        );
        std::io::stdout().flush().unwrap();
    }
    fn retain_bf(file: &mut File, values: &[f32]) -> Vec<u8> {
        let raw = halves(values);
        file.write_all(&raw).unwrap();
        file.sync_data().unwrap();
        assert!(values
            .iter()
            .all(|v| v.is_finite() && v.to_bits() & 0xffff == 0));
        raw
    }
    fn repeat(first: &mut Option<Vec<u8>>, actual: Vec<u8>) {
        if let Some(expected) = first {
            assert_eq!(&actual, expected);
        } else {
            *first = Some(actual);
        }
    }
    fn router(ctx: &NativeContext, x: &[f32], w: &[f32], file: &mut File) -> Vec<f32> {
        let mut out = vec![0.; 288];
        // SAFETY: all buffers have the exact required geometry; the owner lives
        // on this thread throughout this synchronous borrowed-stream call.
        let rc = unsafe {
            studio017_aux(
                x.as_ptr(),
                w.as_ptr(),
                4096,
                288,
                0,
                out.as_mut_ptr(),
                std::ptr::null_mut(),
                ctx.borrowed_stream(),
            )
        };
        file.write_all(&out.iter().flat_map(|v| v.to_le_bytes()).collect::<Vec<_>>())
            .unwrap();
        file.sync_data().unwrap();
        assert_eq!(rc, 0);
        out
    }
    fn partition(ctx: &NativeContext, values: &[f32], file: &mut File) -> [u32; 8] {
        let mut out = [0; 8];
        // SAFETY: exact F32 input/u32 output geometry and live same-thread owner.
        let rc = unsafe {
            studio017_aux(
                values.as_ptr(),
                std::ptr::null(),
                288,
                8,
                1,
                std::ptr::null_mut(),
                out.as_mut_ptr(),
                ctx.borrowed_stream(),
            )
        };
        file.write_all(&out.iter().flat_map(|v| v.to_le_bytes()).collect::<Vec<_>>())
            .unwrap();
        file.sync_data().unwrap();
        assert_eq!(rc, 0);
        out
    }
    fn prechecks(geometry_stream: crate::ffi::mlx_stream) {
        // All fail before a device query; no invalid/freed non-null pointer.
        let stream = crate::ffi::mlx_stream {
            ctx: std::ptr::null_mut(),
        };
        let mut floats = [0.; 288];
        let mut ids = [0; 8];
        let x = [0.; 4096];
        let weights = [0.];
        // SAFETY: null stream and/or invalid geometry make every call return
        // before touching buffers or invoking any GPU operation.
        unsafe {
            assert_eq!(
                studio017_aux(
                    x.as_ptr(),
                    weights.as_ptr(),
                    4096,
                    288,
                    0,
                    floats.as_mut_ptr(),
                    std::ptr::null_mut(),
                    stream
                ),
                1
            );
            assert_eq!(
                studio017_aux(
                    x.as_ptr(),
                    weights.as_ptr(),
                    4095,
                    288,
                    0,
                    floats.as_mut_ptr(),
                    std::ptr::null_mut(),
                    geometry_stream
                ),
                1
            );
            assert_eq!(
                studio017_aux(
                    x.as_ptr(),
                    std::ptr::null(),
                    288,
                    7,
                    1,
                    std::ptr::null_mut(),
                    ids.as_mut_ptr(),
                    geometry_stream
                ),
                1
            );
        }
    }

    let output = PathBuf::from(
        std::env::var_os("STUDIO019_AUX_STREAM_REUSE_OUTPUT_DIR")
            .expect("exact output directory env required"),
    );
    assert!(output.is_absolute() && output.is_dir());
    println!(
        "{}",
        serde_json::json!({"event":"ready","iterations":256,
        "router_calls":257,"unique_partition_calls":257,"tie_partition_calls":16,
        "affine4_calls":256,"qmm8_calls":16,"dequantize8_calls":16,"release_byte":"G"})
    );
    std::io::stdout().flush().unwrap();
    let mut release = [0];
    std::io::stdin().read_exact(&mut release).unwrap();
    assert_eq!(release, [b'G']);
    let create = |name| {
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(output.join(name))
            .unwrap()
    };
    let x: Vec<f32> = (0..4096)
        .map(|i| ((i % 17) as i32 - 8) as f32 / 8.)
        .collect();
    let mut weights = vec![0.; 288 * 4096];
    let mut expected = Vec::new();
    for r in 0..288 {
        let col = (r * 13) % 4096;
        let weight = ((r % 4) + 1) as f32 / 4. * if r % 2 == 0 { 1. } else { -1. };
        weights[r * 4096 + col] = weight;
        // Exact numeric equality intentionally treats +0 and -0 equally.
        // Actual signed F32 output bits are retained before this comparison.
        expected.push(x[col] * weight);
    }
    let unique: Vec<f32> = (0..288).map(|i| -(((i * 73) % 288) as f32)).collect();
    let expected_ids: BTreeSet<u32> = (0..288)
        .filter(|i| (i * 73) % 288 >= 280)
        .map(|i| i as u32)
        .collect();
    let mut ties = vec![0.; 288];
    ties[..16].fill(-1.);
    let inputs = [
        StreamReuseInput::new(4096, 4),
        StreamReuseInput::new(2048, 4),
    ];
    let eight = StreamReuseInput::new(4096, 8);
    for (name, values) in [
        ("router-x.f32", &x),
        ("router-weights.f32", &weights),
        ("unique-partition.f32", &unique),
        ("tie-partition.f32", &ties),
    ] {
        let mut file = create(name);
        file.write_all(
            &values
                .iter()
                .flat_map(|v| v.to_le_bytes())
                .collect::<Vec<_>>(),
        )
        .unwrap();
        file.sync_all().unwrap();
    }
    for (name, input) in [
        ("inputs-4096.bin", &inputs[0]),
        ("inputs-2048.bin", &inputs[1]),
        ("inputs-8bit.bin", &eight),
    ] {
        let mut file = create(name);
        for bytes in [
            halves(&input.x).as_slice(),
            &input.packed,
            &input.scales,
            &input.biases,
        ] {
            file.write_all(bytes).unwrap();
        }
        file.sync_all().unwrap();
    }
    let mut router_out = create("router-output.f32");
    let mut unique_out = create("unique-output.u32");
    let mut tie_out = create("tie-output.u32");
    let mut affine_out = create("affine4-output.bf16");
    let mut qmm_out = create("qmm8-output.bf16");
    let mut deq_out = create("dequantize8-output.bf16");
    prechecks(crate::ffi::mlx_stream {
        ctx: std::ptr::null_mut(),
    });
    native::ensure_error_handler();
    assert!(native::metal_available().unwrap());
    native::set_default_device_gpu().unwrap();
    assert_eq!(unsafe { studio017_limits() }, 0);
    let ctx = NativeContext::new(DeviceKind::Gpu).unwrap();
    let main_index = index(&ctx);
    // Live stream plus invalid geometry must still reject before querying GPU.
    prechecks(unsafe { ctx.borrowed_stream() });
    let mut first_unique = None;
    let mut first_affine = [None, None];
    let mut first_qmm = None;
    let mut first_deq = None;
    for iteration in 1..=256 {
        let out = router(&ctx, &x, &weights, &mut router_out);
        assert_eq!(out, expected);
        event(iteration, "router", &ctx);
        let ids = partition(&ctx, &unique, &mut unique_out);
        assert_eq!(ids.iter().copied().collect::<BTreeSet<_>>(), expected_ids);
        let ordered_repeat = first_unique.map(|first| ids == first);
        if first_unique.is_none() {
            first_unique = Some(ids);
        }
        // Raw order is evidence only; qualification compares the exact set.
        println!(
            "{}",
            serde_json::json!({"event":"unique_order","iteration":iteration,
            "same_as_first":ordered_repeat})
        );
        event(iteration, "unique_partition", &ctx);
        let which = (iteration - 1) % 2;
        let actual = retain_bf(&mut affine_out, &inputs[which].run(&ctx));
        assert_eq!(actual.len(), 128);
        repeat(&mut first_affine[which], actual);
        event(
            iteration,
            if which == 0 {
                "affine4_4096"
            } else {
                "affine4_2048"
            },
            &ctx,
        );
        if iteration % 16 == 0 {
            let actual = retain_bf(&mut qmm_out, &eight.run(&ctx));
            assert_eq!(actual.len(), 128);
            repeat(&mut first_qmm, actual);
            event(iteration, "qmm8_4096", &ctx);
            let values = copied_tile(
                &ctx,
                4096,
                8,
                1,
                &eight.packed[..4096],
                &eight.scales[..128],
                &eight.biases[..128],
                None,
            )
            .unwrap();
            let actual = retain_bf(&mut deq_out, &values);
            assert_eq!(actual.len(), 8192);
            repeat(&mut first_deq, actual);
            event(iteration, "dequantize8_4096", &ctx);
            let ids = partition(&ctx, &ties, &mut tie_out);
            let set: BTreeSet<_> = ids.iter().copied().collect();
            assert_eq!(set.len(), 8);
            assert!(set.iter().all(|&i| i < 16));
            event(iteration, "tie_partition", &ctx);
        }
        assert_eq!(index(&ctx), main_index);
        assert_eq!(ctx.live_arrays(), 0);
        if iteration == 128 {
            let other = NativeContext::new(DeviceKind::Gpu).unwrap();
            assert_ne!(index(&other), main_index);
            assert_eq!(router(&other, &x, &weights, &mut router_out), expected);
            event(iteration, "secondary_router", &other);
            let ids = partition(&other, &unique, &mut unique_out);
            assert_eq!(ids.iter().copied().collect::<BTreeSet<_>>(), expected_ids);
            event(iteration, "secondary_unique_partition", &other);
            assert_eq!(other.live_arrays(), 0);
            other.synchronize().unwrap();
            drop(other);
            println!(
                "{}",
                serde_json::json!({"event":"secondary_dropped","after_iteration":128})
            );
        }
    }
    prechecks(unsafe { ctx.borrowed_stream() });
    ctx.synchronize().unwrap();
    assert_eq!(ctx.live_arrays(), 0);
    drop(ctx);
    native::drain_residual_error("aux stream reuse synthetic teardown");
    let (live, freed) = native::handle_census();
    assert_eq!(live, 0);
    assert_eq!(native::double_free_attempts(), 0);
    assert!(native::cleanup_errors().is_empty());
    assert_eq!(native::handler_messages(), 0);
    for file in [
        &router_out,
        &unique_out,
        &tie_out,
        &affine_out,
        &qmm_out,
        &deq_out,
    ] {
        file.sync_all().unwrap();
    }
    println!(
        "{}",
        serde_json::json!({"event":"complete","iterations":256,
        "rust_live_handles":live,"rust_handles_freed":freed,"double_free_attempts":0,
        "cleanup_errors":0,"handler_messages":0,"c_handles_in_census":false})
    );
    std::io::stdout().flush().unwrap();
}
