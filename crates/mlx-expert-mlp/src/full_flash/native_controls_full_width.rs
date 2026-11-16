// Included only by graph::native_controls, in the explicitly sandboxed test build.
// No IO, external arguments, model, grant or reference-as-input. Five production
// copied_tile dispatches, one per frozen geometry. Stable scalar CPU FP64 expected
// outputs are generated independently by studio017_full_width_fixture.py.
type WidthObservation = (u32, usize, [String; 4], Vec<u16>);
fn full_width_observations(
    ctx: &NativeContext,
    geometries: &[(u32, usize)],
) -> R<Vec<WidthObservation>> {
    use mlx_native_affine::fixture::sha256_hex;
    const ROWS: usize = 64;
    let mut observations = Vec::new();
    for &(bits, cols) in geometries {
        let x: Vec<f32> = (0..cols)
            .map(|j| {
                let q = (j / 4) % 4;
                let a = if j % 4 == q { 1.0 } else { 1.0 / 256.0 };
                if q == 3 {
                    -a
                } else {
                    a
                }
            })
            .collect();
        let mut codes = Vec::with_capacity(ROWS * cols);
        let (mut scales, mut biases) = (Vec::new(), Vec::new());
        for row in 0..ROWS {
            for g in 0..cols / 64 {
                let sel = (row + 3 * g + g / 3) % 5;
                let center = (if bits == 4 { 5 + sel } else { 120 + 4 * sel }) as i32;
                let factor = if row == 1 && g + 1 == cols / 64 {
                    1
                } else {
                    [1, 2, -3, 3][(g + 3 * row + g / 5) % 4]
                };
                scales.push(factor as f32 / 256.0);
                biases.push((-center * factor) as f32 / 256.0);
                for t in 0..64 {
                    let j = g * 64 + t;
                    let offset: i32 = match row {
                        0 => 0,
                        1 | 2 => {
                            (if t < 32 { 2 } else { -2 }) + i32::from(row == 1 && j + 2 == cols)
                        }
                        _ => {
                            ((13 * row
                                + 5 * g
                                + 3 * t
                                + t / 4 * (1 + row % 5)
                                + row * (j % 11)
                                + g / 3)
                                % 7) as i32
                                - 3
                        }
                    };
                    codes.push((center + offset) as u8);
                }
            }
        }
        let (packed, sc, bi) = (words(&codes, bits), halves(&scales), halves(&biases));
        let binds = [
            sha256_hex(&halves(&x)),
            sha256_hex(&packed),
            sha256_hex(&sc),
            sha256_hex(&bi),
        ];
        let out = copied_tile(ctx, cols, bits, ROWS, &packed, &sc, &bi, Some(&x))?;
        if out.len() != ROWS
            || out.iter().any(|v| !v.is_finite() || v.to_bits() & 0xffff != 0)
        {
            return Err("full-width QMM output count or BF16 domain".into());
        }
        let out_bits: Vec<u16> = out.iter().map(|v| (v.to_bits() >> 16) as u16).collect();
        observations.push((bits, cols, binds, out_bits));
    }
    Ok(observations)
}

fn full_width_affine_controls(ctx: &NativeContext) -> R<()> {
    use mlx_native_affine::fixture::sha256_hex;
    const ROWS: usize = 64;
    let observations = full_width_observations(
        ctx,
        &[
            (4u32, 2048usize),
            (4, 4096),
            (8, 4096),
            (8, 12288),
            (8, 16384),
        ],
    )?;
    // All five native outputs returned before reading the independent expected values.
    let golden: Value =
        serde_json::from_str(include_str!("full-width-affine-golden.json")).unwrap();
    let cases = golden.as_array().unwrap();
    assert_eq!(cases.len(), observations.len());
    for ((bits, cols, binds, actual), g) in observations.into_iter().zip(cases) {
        assert_eq!(g["bits"], bits);
        assert_eq!(g["cols"], cols);
        assert_eq!(g["rows"], ROWS);
        assert_eq!(
            g["sha256"],
            serde_json::json!(binds),
            "packed/input identity {bits}/{cols}"
        );
        let expect = g["expected_bf16"].as_array().unwrap();
        assert_eq!(expect.len(), actual.len());
        // All correct reductions of these particular dyadic values are exact
        // in F32 until the final BF16 rounding. No candidate-dependent tolerance;
        // +zero and -zero denote the same numerical zero.
        let raw: Vec<u8> = actual.iter().flat_map(|n| n.to_le_bytes()).collect();
        eprintln!(
            "studio017_full_width_affine={}",
            serde_json::json!({"rows":ROWS,"cols":cols,
            "bits":bits,"observed_bf16_sha256":sha256_hex(&raw),"observed_bf16":actual,
            "expected_bf16":expect,"source_comparison":"synthetic dense binary64; exact BF16 after final cast"})
        );
        for (i, (word, e)) in actual.iter().zip(expect).enumerate() {
            let e = u16::try_from(e.as_u64().unwrap()).unwrap();
            assert!(
                *word == e || (*word == 0x8000 && e == 0),
                "QMM {bits}-bit 64x{cols} row {i}: got {word:#06x}, expected {e:#06x}"
            );
        }
    }
    Ok(())
}

#[test]
#[ignore = "physical Studio017 synthetic 8-bit QMM and dequantize controls"]
fn uncovered_eight_bit_dispatches() {
    use mlx_native_affine::fixture::sha256_hex;

    native::ensure_error_handler();
    assert!(native::metal_available().unwrap());
    native::set_default_device_gpu().unwrap();
    let ctx = NativeContext::new(DeviceKind::Gpu).unwrap();
    assert_eq!(unsafe { studio017_limits() }, 0);

    // Freeze the geometries separately from the oracle. The expected values never
    // supply inputs to copied_tile. The production selector owns kernel dispatch.
    let geometries = [
        (8, 128),
        (8, 256),
        (8, 512),
        (8, 1536),
        (8, 2048),
        (8, 8192),
    ];
    let mut observations: Vec<_> = full_width_observations(&ctx, &geometries)
        .unwrap()
        .into_iter()
        .map(|(_, k, binds, actual)| (64usize, k, binds.to_vec(), actual))
        .collect();

    let cols = 4096;
    let codes: Vec<u8> = (0..cols)
        .map(|j| {
            if j % 64 == 0 {
                3
            } else {
                ((37 * j + 11 * (j / 64) + 3) % 256) as u8
            }
        })
        .collect();
    let scales: Vec<f32> = (0..cols / 64)
        .map(|g| [129., -129., 130., -130.][g % 4] / 128.)
        .collect();
    let biases: Vec<f32> = (0..cols / 64)
        .map(|g| [-95., 95., -124., 124.][g % 4] / 32.)
        .collect();
    let (packed, scales, biases) = (words(&codes, 8), halves(&scales), halves(&biases));
    let binds = vec![
        sha256_hex(&packed),
        sha256_hex(&scales),
        sha256_hex(&biases),
    ];
    let decoded = copied_tile(&ctx, cols, 8, 1, &packed, &scales, &biases, None).unwrap();
    let words = decoded.iter().map(|x| (x.to_bits() >> 16) as u16).collect();
    observations.push((1, cols, binds, words));

    let golden: Value =
        serde_json::from_str(include_str!("dispatch-eight-bit-golden.json")).unwrap();
    let cases = golden.as_array().unwrap();
    assert_eq!(cases.len(), observations.len());
    let mut failures = Vec::new();
    for ((rows, k, binds, actual), expected) in observations.iter().zip(cases) {
        let words: Vec<u16> = serde_json::from_value(expected["expected_bf16"].clone()).unwrap();
        let first_difference = actual
            .iter()
            .zip(&words)
            .position(|(&a, &b)| a != b && !(*rows == 64 && a & 0x7fff == 0 && b & 0x7fff == 0));
        let identity_ok = expected["bits"] == 8
            && expected["cols"] == *k
            && expected["rows"] == *rows
            && expected["sha256"] == serde_json::json!(binds);
        let passed = identity_ok && first_difference.is_none() && words.len() == actual.len();
        let raw: Vec<u8> = actual.iter().flat_map(|w| w.to_le_bytes()).collect();
        eprintln!(
            "studio017_dispatch_eight_bit={}",
            serde_json::json!({
                "rows": rows, "cols": k, "input_sha256": binds, "observed_bf16": actual,
                "observed_bf16_sha256": sha256_hex(&raw), "expected_count": words.len(),
                "identity_ok": identity_ok, "first_difference": first_difference.map(|i|
                    serde_json::json!({"coordinate":i,"expected":words[i],"actual":actual[i]})),
                "passed":passed
            })
        );
        if !passed {
            failures.push((*rows, *k));
        }
    }
    assert!(
        failures.is_empty(),
        "8-bit production geometries refused: {failures:?}"
    );
}
