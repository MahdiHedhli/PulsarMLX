use backend::{CancellationToken, ContractError};
use mlx_backend::{
    read_admitted_layer0_expert_gate_rows_0_to_16, ExternalModelInspection, Qwen3MoEDecodedTensor,
    QWEN_DECODED_SLICE_BYTES, QWEN_ENCODED_SLICE_BYTES,
};

#[test]
fn public_storage_surface_is_the_bounded_typed_slice_operation() {
    let _: fn(
        &ExternalModelInspection,
        String,
        CancellationToken,
    ) -> Result<Qwen3MoEDecodedTensor, ContractError> =
        read_admitted_layer0_expert_gate_rows_0_to_16;
    assert_eq!(QWEN_ENCODED_SLICE_BYTES, 34_816);
    assert_eq!(QWEN_DECODED_SLICE_BYTES, 131_072);
}
