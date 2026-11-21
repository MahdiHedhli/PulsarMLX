// Fixed synthetic child only. Run this exact ignored test under the supervising
// watchdog/resource gate. Dynamic-library initializers precede the release gate;
// no explicit MLX call below occurs until stdin supplies the single byte G.
struct StreamReuseInput {
    cols: usize,
    bits: u32,
    x: Vec<f32>,
    packed: Vec<u8>,
    scales: Vec<u8>,
    biases: Vec<u8>,
}

impl StreamReuseInput {
    fn new(cols: usize, bits: u32) -> Self {
        // For bits=4 this is byte-for-byte the retained synthetic-stream-main.c
        // fill recipe, including unsigned LCG wrapping and little-endian words.
        let magnitude = [0x3e80u16, 0x3f00, 0x3f40, 0x3f80];
        let scale = [0x3b80u16, 0x3c00, 0x3c40, 0x3c80];
        let bias = [0xbd00u16, 0x3d00, 0xbd80, 0x3d80];
        let x = (0..cols)
            .map(|i| {
                let word = magnitude[i % 4] | if (i / 4) % 2 == 1 { 0x8000 } else { 0 };
                f32::from_bits(u32::from(word) << 16)
            })
            .collect();
        let mut state = 0x019af4c3u32 ^ cols as u32;
        let codes: Vec<u8> = (0..64 * cols)
            .map(|_| {
                state = state.wrapping_mul(1664525).wrapping_add(1013904223);
                (state >> (32 - bits)) as u8
            })
            .collect();
        let metadata = |table: &[u16; 4]| {
            (0..64 * cols / 64)
                .flat_map(|i| table[i % 4].to_le_bytes())
                .collect()
        };
        Self {
            cols,
            bits,
            x,
            packed: words(&codes, bits),
            scales: metadata(&scale),
            biases: metadata(&bias),
        }
    }

    fn run(&self, ctx: &NativeContext) -> Vec<f32> {
        copied_tile(
            ctx,
            self.cols,
            self.bits,
            64,
            &self.packed,
            &self.scales,
            &self.biases,
            Some(&self.x),
        )
        .unwrap()
    }

    fn identity(&self) -> Value {
        use mlx_native_affine::fixture::sha256_hex;
        serde_json::json!({"bits":self.bits,"rows":64,"cols":self.cols,
            "sha256":[sha256_hex(&halves(&self.x)),sha256_hex(&self.packed),
                sha256_hex(&self.scales),sha256_hex(&self.biases)]})
    }
}

#[test]
#[ignore = "admitted Studio019 stream-reuse synthetic child only; requires stdin G and exclusive output directory"]
fn affine4_caller_owned_stream_reuse() {
    use std::fs::OpenOptions;
    use std::io::{Read, Write};
    use std::os::unix::fs::OpenOptionsExt;
    use std::path::PathBuf;
    use std::time::Instant;

    unsafe extern "C" {
        fn mlx_stream_get_index(index: *mut i32, stream: crate::ffi::mlx_stream) -> i32;
    }
    fn index(ctx: &NativeContext) -> i32 {
        let mut index = -1;
        // SAFETY: read-only stream query on this thread; ctx owns the live handle.
        assert_eq!(
            unsafe { mlx_stream_get_index(&mut index, ctx.borrowed_stream()) },
            0
        );
        index
    }
    fn retain(file: &mut std::fs::File, values: &[f32]) -> Vec<u16> {
        let bits: Vec<u16> = values.iter().map(|v| (v.to_bits() >> 16) as u16).collect();
        let raw: Vec<u8> = bits.iter().flat_map(|v| v.to_le_bytes()).collect();
        file.write_all(&raw).unwrap();
        // Preserve raw output before any check that can refuse this child.
        assert_eq!(values.len(), 64);
        assert!(values
            .iter()
            .all(|v| v.is_finite() && v.to_bits() & 0xffff == 0));
        bits
    }

    let output = PathBuf::from(
        std::env::var_os("STUDIO019_STREAM_REUSE_OUTPUT_DIR")
            .expect("exact output directory env required"),
    );
    assert!(output.is_absolute() && output.is_dir());
    println!(
        "{}",
        serde_json::json!({"event":"ready","calls":1024,"interleaved_8bit_calls":16,"separate_context_calls":2,"release_byte":"G"})
    );
    std::io::stdout().flush().unwrap();
    let mut release = [0u8];
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
    let mut primary = create("outputs.u16");
    let mut interleaved = create("interleaved-8bit.u16");
    let mut separated = create("separate-context.u16");
    let inputs = [
        StreamReuseInput::new(4096, 4),
        StreamReuseInput::new(2048, 4),
    ];
    // The interleaved fixture uses the identical x/metadata recipe, with each
    // LCG output's high byte as its 8-bit code, packed four codes per U32.
    let eight = StreamReuseInput::new(4096, 8);
    // Retain actual candidate inputs, rather than relying solely on an in-child
    // hash implementation. Canonical layout: x BF16, packed U32, scales BF16,
    // biases BF16, each in little-endian byte order with no header or padding.
    for (name, input) in [
        ("inputs-4096.bin", &inputs[0]),
        ("inputs-2048.bin", &inputs[1]),
        ("inputs-8bit.bin", &eight),
    ] {
        let mut file = create(name);
        let raw_x = halves(&input.x);
        for bytes in [
            raw_x.as_slice(),
            input.packed.as_slice(),
            input.scales.as_slice(),
            input.biases.as_slice(),
        ] {
            file.write_all(bytes).unwrap();
        }
        file.sync_all().unwrap();
    }
    println!(
        "{}",
        serde_json::json!({"event":"inputs","affine4":[inputs[0].identity(),inputs[1].identity()],"interleaved_8bit":eight.identity()})
    );
    std::io::stdout().flush().unwrap();

    native::ensure_error_handler();
    assert!(native::metal_available().unwrap());
    native::set_default_device_gpu().unwrap();
    assert_eq!(unsafe { studio017_limits() }, 0);
    let ctx = NativeContext::new(DeviceKind::Gpu).unwrap();
    let main_index = index(&ctx);
    let mut first: [Option<Vec<u16>>; 2] = [None, None];
    let mut first_eight = None;
    let start = Instant::now();
    for call in 1..=1024 {
        let which = usize::from((call - 1) % 128 >= 64);
        let actual = retain(&mut primary, &inputs[which].run(&ctx));
        if let Some(expected) = &first[which] {
            assert_eq!(&actual, expected, "exact repeat at affine4 call {call}");
        } else {
            first[which] = Some(actual);
        }
        assert_eq!(index(&ctx), main_index);
        println!(
            "{}",
            serde_json::json!({"event":"call","call":call,"cols":inputs[which].cols,"stream_index":main_index,"elapsed_ms":start.elapsed().as_millis()})
        );
        if call % 64 == 0 {
            let actual = retain(&mut interleaved, &eight.run(&ctx));
            if let Some(expected) = &first_eight {
                assert_eq!(&actual, expected, "exact interleaved 8-bit repeat");
            } else {
                first_eight = Some(actual);
            }
            println!(
                "{}",
                serde_json::json!({"event":"interleaved_8bit","after_call":call,"stream_index":index(&ctx)})
            );
        }
        if call == 512 {
            // Drop only this separate owner, then continue using the original
            // owner for the remaining 512 affine4 calls and eight 8-bit calls.
            let other = NativeContext::new(DeviceKind::Gpu).unwrap();
            let other_index = index(&other);
            assert_ne!(other_index, main_index);
            for which in 0..2 {
                let actual = retain(&mut separated, &inputs[which].run(&other));
                assert_eq!(
                    Some(&actual),
                    first[which].as_ref(),
                    "independent context exact output"
                );
                println!(
                    "{}",
                    serde_json::json!({"event":"separate_context","cols":inputs[which].cols,"stream_index":index(&other)})
                );
            }
            assert_eq!(other.live_arrays(), 0);
            other.synchronize().unwrap();
            drop(other);
        }
        std::io::stdout().flush().unwrap();
    }
    assert_eq!(ctx.live_arrays(), 0);
    ctx.synchronize().unwrap();
    drop(ctx);
    native::drain_residual_error("stream reuse synthetic teardown");
    assert_eq!(native::handle_census().0, 0);
    assert_eq!(native::double_free_attempts(), 0);
    assert!(native::cleanup_errors().is_empty());
    assert_eq!(native::handler_messages(), 0);
    primary.sync_all().unwrap();
    interleaved.sync_all().unwrap();
    separated.sync_all().unwrap();
    println!(
        "{}",
        serde_json::json!({"event":"complete","calls":1024,"interleaved_8bit_calls":16,"separate_context_calls":2,"live_array_handles":0,"cleanup_errors":0,"handler_messages":0})
    );
    std::io::stdout().flush().unwrap();
}
