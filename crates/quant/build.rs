fn main() {
    let source = std::fs::read_to_string("../../scripts/research/iq_extra_tables.py")
        .expect("read accepted IQ2_S table source");
    let start = source.find("IQ2S_GRID = [").expect("IQ2S_GRID") + "IQ2S_GRID = [".len();
    let end = source[start..].find(']').expect("IQ2S_GRID end") + start;
    let values = source[start..end]
        .split(',')
        .filter_map(|part| {
            let value = part.trim();
            (!value.is_empty()).then_some(value)
        })
        .collect::<Vec<_>>();
    assert_eq!(values.len(), 1024, "accepted IQ2_S grid census");
    let generated = format!("const IQ2S_GRID: [u64; 1024] = [{}];\n", values.join(","));
    let out = std::path::PathBuf::from(std::env::var("OUT_DIR").unwrap());
    std::fs::write(out.join("f017_iq2s_grid.rs"), generated).expect("write IQ2_S table");
    println!("cargo:rerun-if-changed=../../scripts/research/iq_extra_tables.py");
}
