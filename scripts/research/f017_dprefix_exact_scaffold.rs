use std::collections::BTreeMap;
use std::convert::TryInto;
use std::fs::{self, File};
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};

const HIDDEN: usize = 6144;
const HEADS: usize = 64;
const VALUE: usize = 256;
const KV: usize = 512;
const FFN: usize = 12288;
const RMS_EPSILON: f64 = 9.999999747378752e-6;

#[derive(Clone)]
struct Tensor { path: PathBuf, dims: Vec<usize> }

fn die(message: &str) -> ! { eprintln!("DPREFIX-EXACT-1-B: {message}"); std::process::exit(2) }

fn manifest(path: &Path) -> BTreeMap<String, Tensor> {
    let text = fs::read_to_string(path).unwrap_or_else(|_| die("manifest read"));
    let mut result = BTreeMap::new();
    for line in text.lines() {
        let fields: Vec<_> = line.split('\t').collect();
        if fields.len() != 6 { die("manifest parse") }
        let rank: usize = fields[2].parse().unwrap_or_else(|_| die("manifest rank"));
        let all = [fields[3], fields[4], fields[5]].map(|x| x.parse::<usize>().unwrap_or_else(|_| die("manifest dimension")));
        let dims = all[..rank].to_vec();
        let expected = dims.iter().product::<usize>() * 4;
        if fs::metadata(fields[1]).map(|m| m.len() as usize).unwrap_or(0) != expected { die("tensor identity") }
        if result.insert(fields[0].to_string(), Tensor { path: fields[1].into(), dims }).is_some() { die("duplicate tensor") }
    }
    if result.len() != 40 { die("manifest count") }
    result
}

fn load(tensors: &BTreeMap<String, Tensor>, name: &str) -> Vec<f32> {
    let item = tensors.get(name).unwrap_or_else(|| die("missing tensor"));
    let raw = fs::read(&item.path).unwrap_or_else(|_| die("tensor read"));
    raw.chunks_exact(4).map(|b| f32::from_le_bytes(b.try_into().unwrap())).collect()
}

fn embedding(tensors: &BTreeMap<String, Tensor>) -> Vec<f32> {
    let item = tensors.get("token_embd.weight").unwrap_or_else(|| die("embedding absent"));
    if item.dims != [154880, HIDDEN] { die("embedding shape") }
    let mut file = File::open(&item.path).unwrap_or_else(|_| die("embedding open"));
    file.seek(SeekFrom::Start((9703 * HIDDEN * 4) as u64)).unwrap_or_else(|_| die("embedding seek"));
    let mut raw = vec![0u8; HIDDEN * 4];
    file.read_exact(&mut raw).unwrap_or_else(|_| die("embedding read"));
    raw.chunks_exact(4).map(|b| f32::from_le_bytes(b.try_into().unwrap())).collect()
}

fn matvec(matrix: &[f32], rows: usize, columns: usize, vector: &[f32]) -> Vec<f32> {
    if matrix.len() != rows * columns || vector.len() != columns { die("matvec shape") }
    let mut output = vec![0.0f32; rows];
    for row in 0..rows {
        let mut sum = 0.0f64;
        for column in 0..columns { sum += matrix[row * columns + column] as f64 * vector[column] as f64; }
        output[row] = sum as f32;
    }
    output
}

fn rms(input: &[f32], weight: &[f32]) -> Vec<f32> {
    if input.len() != weight.len() { die("rms shape") }
    let mut sum = 0.0f64;
    for &value in input { sum += value as f64 * value as f64; }
    let inverse = (1.0 / (sum / input.len() as f64 + RMS_EPSILON).sqrt()) as f32;
    input.iter().zip(weight).map(|(&x, &w)| (x * inverse) * w).collect()
}

fn write_surface(root: &Path, name: &str, values: &[f32]) {
    let mut file = File::create(root.join(format!("{name}.f32le"))).unwrap_or_else(|_| die("surface create"));
    for value in values { file.write_all(&value.to_le_bytes()).unwrap_or_else(|_| die("surface write")); }
}

fn layer(tensors: &BTreeMap<String, Tensor>, layer: usize, residual: &[f32], output: &Path) -> Vec<f32> {
    let p = format!("blk.{layer}");
    let normalized = rms(residual, &load(tensors, &format!("{p}.attn_norm.weight")));
    let kv_raw = matvec(&load(tensors, &format!("{p}.attn_kv_a_mqa.weight")), KV + 64, HIDDEN, &normalized);
    let kv = rms(&kv_raw[..KV], &load(tensors, &format!("{p}.attn_kv_a_norm.weight")));
    let value_weights = load(tensors, &format!("{p}.attn_v_b.weight"));
    let mut values = vec![0.0f32; HEADS * VALUE];
    for head in 0..HEADS {
        let begin = head * VALUE * KV;
        let result = matvec(&value_weights[begin..begin + VALUE * KV], VALUE, KV, &kv);
        values[head * VALUE..(head + 1) * VALUE].copy_from_slice(&result);
    }
    let attention = matvec(&load(tensors, &format!("{p}.attn_output.weight")), HIDDEN, HEADS * VALUE, &values);
    write_surface(output, &format!("layer_{layer}_attention"), &attention);
    let attention_residual: Vec<f32> = residual.iter().zip(&attention).map(|(&a, &b)| a + b).collect();
    let ffn_input = rms(&attention_residual, &load(tensors, &format!("{p}.ffn_norm.weight")));
    let gate = matvec(&load(tensors, &format!("{p}.ffn_gate.weight")), FFN, HIDDEN, &ffn_input);
    let up = matvec(&load(tensors, &format!("{p}.ffn_up.weight")), FFN, HIDDEN, &ffn_input);
    let activated: Vec<f32> = gate.iter().zip(&up).map(|(&g, &u)| (g / (1.0 + (-g).exp())) * u).collect();
    let down = matvec(&load(tensors, &format!("{p}.ffn_down.weight")), HIDDEN, FFN, &activated);
    let result: Vec<f32> = attention_residual.iter().zip(&down).map(|(&a, &b)| a + b).collect();
    write_surface(output, &format!("layer_{layer}_output"), &result);
    result
}

fn main() {
    let args: Vec<_> = std::env::args_os().collect();
    if args.len() != 3 { die("usage: exact-input-manifest output-directory") }
    let tensors = manifest(Path::new(&args[1]));
    let output = Path::new(&args[2]);
    fs::create_dir_all(output).unwrap_or_else(|_| die("output directory"));
    let mut hidden = embedding(&tensors);
    write_surface(output, "embedding", &hidden);
    for index in 0..3 { hidden = layer(&tensors, index, &hidden, output); }
    write_surface(output, "layer_3_entry", &hidden);
}
