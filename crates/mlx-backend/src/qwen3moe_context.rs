//! The typed, source-free Qwen3MoE plugin and admitted-graph context.
//!
//! This module intentionally stops at the metadata admission boundary. A
//! context owns the descriptor that was admitted by [`crate::admit_qwen3moe_full_graph`];
//! it does not open a model, read payload bytes, reconstruct graph operations,
//! or resolve tensor names from model metadata.

use backend::{ArchitecturePlugin, ContractError, ErrorCategory};

use crate::qwen3moe::{
    Qwen3MoeFullGraphDescriptor, Qwen3MoeGraphDescriptor, Qwen3MoeLayerGraphDescriptor,
    Qwen3MoeTensorDescriptor, Qwen3MoeTensorRole, QWEN3MOE_FULL_GRAPH_CONTRACT_ID,
};

/// The already-admitted architecture identity used by the backend contract.
pub const QWEN3MOE_ARCHITECTURE_ID: &str = "qwen3moe";

/// Backend plugin identity for an admitted Qwen3MoE graph.
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct Qwen3MoePlugin;

impl ArchitecturePlugin for Qwen3MoePlugin {
    fn architecture_id(&self) -> &str {
        QWEN3MOE_ARCHITECTURE_ID
    }
}

impl Qwen3MoePlugin {
    /// Construct the stateless Qwen3MoE plugin identity.
    pub const fn new() -> Self {
        Self
    }

    /// Build a source-free context from an already-admitted full graph.
    ///
    /// The descriptor is moved into the context unchanged. In particular, this
    /// method does not call canonical graph construction or perform a payload
    /// read. The descriptor's contract ID is checked so a context cannot be
    /// accidentally attached to a different graph admission contract.
    pub fn execution_context(
        &self,
        descriptor: Qwen3MoeFullGraphDescriptor,
    ) -> Result<Qwen3MoeExecutionContext, ContractError> {
        Qwen3MoeExecutionContext::try_new(descriptor)
    }
}

/// Source-free execution context for an already-admitted Qwen3MoE graph.
///
/// This is a typed plumbing seam only. It retains the exact graph and tensor
/// catalog values from the admission result; it contains no file, file
/// descriptor, payload bytes, weights, device handle, or fallback runtime.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Qwen3MoeExecutionContext {
    descriptor: Qwen3MoeFullGraphDescriptor,
}

impl Qwen3MoeExecutionContext {
    /// Retain an already-admitted descriptor without reading any model source.
    pub fn try_new(descriptor: Qwen3MoeFullGraphDescriptor) -> Result<Self, ContractError> {
        if descriptor.contract_id != QWEN3MOE_FULL_GRAPH_CONTRACT_ID {
            return Err(ContractError::new(
                ErrorCategory::InvalidModel,
                "qwen3moe_graph_contract_mismatch",
                "the descriptor is not admitted under the Qwen3MoE full-graph contract",
            ));
        }
        Ok(Self { descriptor })
    }

    /// The exact descriptor retained from graph admission.
    pub fn descriptor(&self) -> &Qwen3MoeFullGraphDescriptor {
        &self.descriptor
    }

    /// The exact typed graph bindings retained from graph admission.
    pub fn graph(&self) -> &Qwen3MoeGraphDescriptor {
        &self.descriptor.graph
    }

    /// The exact typed tensor catalog retained from graph admission.
    pub fn tensors(&self) -> &[Qwen3MoeTensorDescriptor] {
        &self.descriptor.tensors
    }

    /// Find a catalog entry by its typed semantic role and layer.
    ///
    /// This deliberately accepts no tensor-name string or arbitrary selector;
    /// the descriptor remains the source of the admitted binding identity.
    pub fn tensor(
        &self,
        role: Qwen3MoeTensorRole,
        layer_index: Option<u32>,
    ) -> Option<&Qwen3MoeTensorDescriptor> {
        self.descriptor
            .tensors
            .iter()
            .find(|tensor| tensor.role == role && tensor.layer_index == layer_index)
    }

    /// Return one retained layer graph by its bounded typed layer index.
    pub fn layer(&self, layer_index: u32) -> Option<&Qwen3MoeLayerGraphDescriptor> {
        self.descriptor.layer(layer_index)
    }
}
