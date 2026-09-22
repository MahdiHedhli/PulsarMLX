//! R1 and R3 against the frozen Flash research fixture.
//!
//! The governing design note names `glm53-flash-decoder-quantized-v1` as
//! qualification material for this slice, and Round 1 never consumed it:
//! running the existing Python research tests establishes things about the
//! Python path, not about this Rust decoder. This file closes that gap.
//!
//! **The fixture is read, never written.** It lives under
//! `fixtures/research/`, which is frozen, and nothing here opens it for
//! writing, regenerates it, or depends on a tolerance other than the ones it
//! states about itself: `tolerances.dequantize_cross_check = 1e-6` for
//! agreement between the two decoders, and `tolerances.output = 1e-4` for the
//! values it expects.
//!
//! The case used is `multilinear-4bit-g64`, the one whose expectations are
//! reachable from a decoder alone: two heads of a `[48, 64]` 4-bit group-64
//! weight, with `x @ W.T` and `x @ W` outputs stored for each. The matmul is
//! done here, in the test, in binary64 and in binary32 respectively -- this
//! crate supplies the dequantization and nothing else, which is the whole of
//! what Slice 1 qualifies. The `switch-*` cases additionally need SwiGLU and
//! routing, which are out of scope, and the `predicate` case is a naming rule
//! this crate deliberately does not implement.

use mlx_affine::decode::{dequantize_rows, ScaleDtype};
use mlx_affine::reference::dequantize_rows_single;
use mlx_affine::spec::{Bits, GroupSize, Mode, QuantSpec};
use serde_json::Value;

fn fixture() -> Value {
    let path: std::path::PathBuf = [
        env!("CARGO_MANIFEST_DIR"),
        "../../fixtures/research/glm53-flash-decoder-quantized-v1/fixtures.json",
    ]
    .iter()
    .collect();
    let text = std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{}: {e}", path.display()));
    serde_json::from_str(&text).unwrap()
}

fn floats(value: &Value) -> Vec<f64> {
    value
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_f64().unwrap())
        .collect()
}

fn matrix(value: &Value) -> Vec<Vec<f64>> {
    value.as_array().unwrap().iter().map(floats).collect()
}

#[test]
fn r1_and_r3_agree_with_the_frozen_flash_fixture() {
    let fixture = fixture();
    let tolerances = &fixture["tolerances"];
    let cross_check = tolerances["dequantize_cross_check"].as_f64().unwrap();
    let output_tolerance = tolerances["output"].as_f64().unwrap();
    assert_eq!(
        cross_check, 1e-6,
        "the fixture's own dequantization tolerance"
    );
    assert_eq!(output_tolerance, 1e-4, "the fixture's own output tolerance");

    let case = fixture["cases"]
        .as_array()
        .unwrap()
        .iter()
        .find(|case| case["fixture_id"] == "multilinear-4bit-g64")
        .expect("the multilinear case");
    let config = &case["config"];
    let bits = config["bits"].as_u64().unwrap() as u32;
    let group = config["group_size"].as_u64().unwrap() as u32;
    let input_dims = config["input_dims"].as_u64().unwrap() as usize;
    let output_dims = config["output_dims"].as_u64().unwrap() as usize;
    let heads = config["num_heads"].as_u64().unwrap() as usize;
    assert_eq!((bits, group), (4, 64));

    let spec = QuantSpec::new(
        Bits::from_u32(bits).unwrap(),
        GroupSize::from_u32(group).unwrap(),
        Mode::Affine,
    );

    let x_transpose = matrix(&case["x_transpose"]);
    let x_no_transpose = matrix(&case["x_no_transpose"]);
    let expected = &fixture["expected"]["multilinear-4bit-g64"];
    let expected_transpose = expected["transpose"].as_array().unwrap();
    let expected_no_transpose = expected["no_transpose"].as_array().unwrap();

    let mut worst_cross_check = 0f64;
    let mut worst_output = 0f64;
    let mut elements = 0usize;

    for head in 0..heads {
        let block = &case["quantized"]["weight"][head];
        let words: Vec<u32> = block["words"]
            .as_array()
            .unwrap()
            .iter()
            .flat_map(|row| row.as_array().unwrap())
            .map(|w| w.as_u64().unwrap() as u32)
            .collect();
        // The fixture stores metadata as decimal floats; a checkpoint stores
        // binary32. Rounding once here is what makes the two arms see the
        // same stored value rather than two different ones.
        let scale_bits: Vec<u32> = block["scales"]
            .as_array()
            .unwrap()
            .iter()
            .flat_map(|row| row.as_array().unwrap())
            .map(|v| (v.as_f64().unwrap() as f32).to_bits())
            .collect();
        let bias_bits: Vec<u32> = block["biases"]
            .as_array()
            .unwrap()
            .iter()
            .flat_map(|row| row.as_array().unwrap())
            .map(|v| (v.as_f64().unwrap() as f32).to_bits())
            .collect();
        assert_eq!(words.len(), output_dims * input_dims * bits as usize / 32);
        assert_eq!(
            scale_bits.len(),
            output_dims * (input_dims / group as usize)
        );

        // R1: binary64 from the stored bit patterns.
        let mut r1 = vec![0f64; output_dims * input_dims];
        dequantize_rows_single(
            &words,
            &scale_bits,
            &bias_bits,
            bits,
            group,
            output_dims,
            input_dims,
            &mut r1,
        )
        .unwrap();

        // R3: binary32 from the bytes a shard would hold.
        let scale_bytes: Vec<u8> = scale_bits.iter().flat_map(|b| b.to_le_bytes()).collect();
        let bias_bytes: Vec<u8> = bias_bits.iter().flat_map(|b| b.to_le_bytes()).collect();
        let mut r3 = vec![0f32; output_dims * input_dims];
        dequantize_rows(
            "flash-multilinear",
            &words,
            &scale_bytes,
            &bias_bytes,
            ScaleDtype::F32,
            spec,
            output_dims,
            &mut r3,
        )
        .unwrap();

        // The fixture's own dequantization tolerance, between the two arms.
        for index in 0..r1.len() {
            let difference = (f64::from(r3[index]) - r1[index]).abs();
            worst_cross_check = worst_cross_check.max(difference);
            assert!(
                difference <= cross_check,
                "head {head} element {index}: R3 {} vs R1 {} exceeds {cross_check}",
                r3[index],
                r1[index]
            );
            elements += 1;
        }

        // y = x @ W.T, in binary64 from R1's weights.
        for (row, activation) in x_transpose.iter().enumerate() {
            for out in 0..output_dims {
                let mut accumulator = 0f64;
                for (k, value) in activation.iter().enumerate() {
                    accumulator += value * r1[out * input_dims + k];
                }
                let want = expected_transpose[head].as_array().unwrap()[row]
                    .as_array()
                    .unwrap()[out]
                    .as_f64()
                    .unwrap();
                let difference = (accumulator - want).abs();
                worst_output = worst_output.max(difference);
                assert!(
                    difference <= output_tolerance,
                    "transpose head {head} row {row} column {out}: {accumulator} vs {want}"
                );
            }
        }

        // y = x @ W, the untransposed direction.
        for (row, activation) in x_no_transpose.iter().enumerate() {
            for out in 0..input_dims {
                let mut accumulator = 0f64;
                for (k, value) in activation.iter().enumerate() {
                    accumulator += value * r1[k * input_dims + out];
                }
                let want = expected_no_transpose[head].as_array().unwrap()[row]
                    .as_array()
                    .unwrap()[out]
                    .as_f64()
                    .unwrap();
                let difference = (accumulator - want).abs();
                worst_output = worst_output.max(difference);
                assert!(
                    difference <= output_tolerance,
                    "no-transpose head {head} row {row} column {out}: {accumulator} vs {want}"
                );
            }
        }
    }

    assert_eq!(elements, heads * output_dims * input_dims);
    assert!(elements >= 6000, "only {elements} weights were compared");
    // Recorded so the evidence can state the observed margins rather than
    // only that the tolerances were met.
    println!(
        "flash-multilinear: elements={elements} worst_cross_check={worst_cross_check:e} \
         worst_output={worst_output:e}"
    );
}

#[test]
fn the_frozen_fixture_is_only_ever_read() {
    // A standing assertion that this adapter reads the frozen corpus and
    // nothing else about it: the file is unchanged relative to HEAD.
    let output = std::process::Command::new("git")
        .args([
            "status",
            "--porcelain",
            "--",
            "fixtures/research/glm53-flash-decoder-quantized-v1",
        ])
        .current_dir(concat!(env!("CARGO_MANIFEST_DIR"), "/../.."))
        .output();
    if let Ok(output) = output {
        let text = String::from_utf8_lossy(&output.stdout);
        assert!(
            text.trim().is_empty(),
            "the frozen Flash fixture must not be modified, saw: {text}"
        );
    }
}
