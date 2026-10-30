//! Test/example oracle reader only. Never imported by the runtime computation.
use backend::routed_cpu::RoutedTrace;
use backend::step::CommittedStep;

pub fn compare(case: &str, result: &CommittedStep) -> Result<(), String> {
    let trace = RoutedTrace::decode(&result.bytes).map_err(|e| e.to_string())?;
    let fields = fields(&trace);
    let text = include_str!("../../fixtures/routed_cpu_v1/goldens.tsv");
    let mut observed = 0;
    for line in text.lines().filter(|l| !l.starts_with('#')) {
        let columns: Vec<_> = line.split('\t').collect();
        if columns[0] != case
            || columns[1].parse::<u64>().map_err(|e| e.to_string())? != result.previous_position
        {
            continue;
        }
        if columns[2] == "identity" {
            let expected: Vec<u64> = columns[3]
                .split_whitespace()
                .map(|s| s.parse().expect("frozen identity"))
                .collect();
            if expected
                != [
                    result.previous_position,
                    trace.input_token as u64,
                    result.token as u64,
                ]
                || result.position != result.previous_position + 1
            {
                return Err("identity/commit progression mismatch".into());
            }
        } else {
            let actual = fields
                .iter()
                .find(|(key, _)| key == columns[2])
                .ok_or_else(|| format!("unknown golden field {}", columns[2]))?;
            let expected: Vec<f64> = columns[3]
                .split_whitespace()
                .map(|s| s.parse().expect("frozen scalar"))
                .collect();
            if expected.len() != actual.1.len() {
                return Err(format!("{} cardinality", columns[2]));
            }
            for (index, (&a, &b)) in actual.1.iter().zip(&expected).enumerate() {
                let bound = if columns[2].ends_with("selected") {
                    0.0
                } else {
                    2_f64.powi(-35) * (1.0 + b.abs()) + 2_f64.powi(-180)
                };
                if !a.is_finite() || (a - b).abs() > bound {
                    return Err(format!("{}[{index}] differs: {a} vs {b}", columns[2]));
                }
            }
        }
        observed += 1;
    }
    if observed != 24 {
        return Err(format!("incomplete golden step: {observed} fields"));
    }
    Ok(())
}

fn fields(trace: &RoutedTrace) -> Vec<(String, Vec<f64>)> {
    let mut out = Vec::new();
    for (index, l) in trace.layers.iter().enumerate() {
        for (name, v) in [
            ("input", l.input.to_vec()),
            ("scores", l.scores.to_vec()),
            ("selected", l.selected.map(|id| id as f64).to_vec()),
            ("weights", l.weights.to_vec()),
            ("gate", l.gate.iter().flatten().copied().collect()),
            ("up", l.up.iter().flatten().copied().collect()),
            ("silu", l.silu.iter().flatten().copied().collect()),
            ("product", l.product.iter().flatten().copied().collect()),
            ("down", l.down.iter().flatten().copied().collect()),
            ("combined", l.combined.to_vec()),
            ("residual", l.residual.to_vec()),
        ] {
            out.push((format!("l{index}.{name}"), v));
        }
    }
    out.push(("logits".into(), trace.logits.to_vec()));
    out
}
