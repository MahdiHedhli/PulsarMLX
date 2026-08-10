#import <Foundation/Foundation.h>
#import <Metal/Metal.h>

#include <chrono>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static constexpr uintptr_t kPageAlignment = 4096;
static constexpr NSUInteger kIQ2GridBytes = 256 * 8;
static constexpr NSUInteger kIQ2SignBytes = 128;

static NSString *const kKernelSource = @R"METAL(
#include <metal_stdlib>
using namespace metal;

kernel void pulsar_checksum(
    device const uchar *input [[buffer(0)]],
    device uint *output [[buffer(1)]],
    constant uint &length [[buffer(2)]],
    uint thread_id [[thread_position_in_grid]]) {
    if (thread_id != 0) {
        return;
    }
    uint sum = 0;
    for (uint i = 0; i < length; ++i) {
        sum += static_cast<uint>(input[i]);
    }
    output[0] = sum;
}

struct IQ2XXSParams {
    uint rows;
    uint columns;
    uint packed_row_bytes;
};

kernel void pulsar_iq2_xxs_gemv(
    device const uchar *packed [[buffer(0)]],
    device const float *activation [[buffer(1)]],
    device float *output [[buffer(2)]],
    device const uchar *grid_table [[buffer(3)]],
    device const uchar *sign_table [[buffer(4)]],
    constant IQ2XXSParams &params [[buffer(5)]],
    uint row [[thread_position_in_grid]]) {
    if (row >= params.rows) {
        return;
    }
    const uint blocks_per_row = params.columns / 256u;
    const uint row_base = row * params.packed_row_bytes;
    float sum = 0.0f;
    for (uint block_index = 0; block_index < blocks_per_row; ++block_index) {
        const uint block_base = row_base + block_index * 66u;
        const ushort scale_bits = ushort(packed[block_base]) |
            (ushort(packed[block_base + 1u]) << 8u);
        const float d = float(as_type<half>(scale_bits));
        for (uint group = 0; group < 8u; ++group) {
            const uint group_base = block_base + 2u + group * 8u;
            const uint aux1 = uint(packed[group_base + 4u]) |
                (uint(packed[group_base + 5u]) << 8u) |
                (uint(packed[group_base + 6u]) << 16u) |
                (uint(packed[group_base + 7u]) << 24u);
            const float block_scale = d * (0.5f + float(aux1 >> 28u)) * 0.25f;
            for (uint grid_lane = 0; grid_lane < 4u; ++grid_lane) {
                const uint grid_index = uint(packed[group_base + grid_lane]);
                const uint sign_index = (aux1 >> (7u * grid_lane)) & 127u;
                const uchar sign_mask = sign_table[sign_index];
                for (uint element = 0; element < 8u; ++element) {
                    const uint column = block_index * 256u + group * 32u +
                        grid_lane * 8u + element;
                    const float magnitude = float(grid_table[grid_index * 8u + element]);
                    const float sign = (sign_mask & uchar(1u << element)) != 0 ? -1.0f : 1.0f;
                    const float weight = block_scale * magnitude * sign;
                    sum += weight * activation[column];
                }
            }
        }
    }
    output[row] = sum;
}
)METAL";

@interface PulsarMetalContextObject : NSObject
@property(nonatomic, strong) id<MTLDevice> device;
@property(nonatomic, strong) id<MTLCommandQueue> queue;
@property(nonatomic, strong) id<MTLComputePipelineState> checksumPipeline;
@property(nonatomic, strong) id<MTLComputePipelineState> iq2Pipeline;
@property(nonatomic, strong) id<MTLBuffer> iq2GridBuffer;
@property(nonatomic, strong) id<MTLBuffer> iq2SignBuffer;
@property(nonatomic, assign) double compilationSeconds;
@end

@implementation PulsarMetalContextObject
@end

@interface PulsarMetalRegistrationObject : NSObject
@property(nonatomic, strong) id<MTLBuffer> buffer;
@property(nonatomic, strong) PulsarMetalContextObject *context;
@property(nonatomic, assign) const void *address;
@property(nonatomic, assign) NSUInteger length;
@end

@implementation PulsarMetalRegistrationObject
@end

extern "C" {

typedef void PulsarMetalContext;
typedef void PulsarMetalRegistration;

struct PulsarIq2XxsGemvTelemetry {
    double dispatch_seconds;
    double kernel_seconds;
    double synchronization_seconds;
    double total_seconds;
};

static double elapsed_seconds(
    const std::chrono::steady_clock::time_point &start,
    const std::chrono::steady_clock::time_point &end) {
    return std::chrono::duration<double>(end - start).count();
}

static int set_error(char *buffer, size_t capacity, NSString *message) {
    if (buffer != nullptr && capacity > 0) {
        const char *utf8 = message.UTF8String;
        if (utf8 == nullptr) {
            utf8 = "unknown Metal bridge error";
        }
        snprintf(buffer, capacity, "%s", utf8);
    }
    return -1;
}

static id<MTLComputePipelineState> build_pipeline(
    id<MTLDevice> device,
    id<MTLLibrary> library,
    NSString *name,
    NSError **error) {
    id<MTLFunction> function = [library newFunctionWithName:name];
    if (function == nil) {
        if (error != nullptr) {
            *error = [NSError errorWithDomain:@"PulsarMLXMetal"
                code:1
                userInfo:@{NSLocalizedDescriptionKey:
                    [NSString stringWithFormat:@"Metal function unavailable: %@", name]}];
        }
        return nil;
    }
    return [device newComputePipelineStateWithFunction:function error:error];
}

int pulsar_metal_context_create(
    PulsarMetalContext **out_context,
    char *error_buffer,
    size_t error_capacity) {
    if (out_context == nullptr) {
        return set_error(error_buffer, error_capacity, @"null context output");
    }
    const auto compilation_start = std::chrono::steady_clock::now();
    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    if (device == nil) {
        return set_error(error_buffer, error_capacity, @"Metal device unavailable");
    }
    id<MTLCommandQueue> queue = [device newCommandQueue];
    if (queue == nil) {
        return set_error(error_buffer, error_capacity, @"Metal command queue unavailable");
    }
    NSError *library_error = nil;
    id<MTLLibrary> library = [device newLibraryWithSource:kKernelSource options:nil error:&library_error];
    if (library == nil) {
        return set_error(
            error_buffer,
            error_capacity,
            library_error.localizedDescription ?: @"Metal library compilation failed");
    }
    NSError *pipeline_error = nil;
    id<MTLComputePipelineState> checksum_pipeline =
        build_pipeline(device, library, @"pulsar_checksum", &pipeline_error);
    if (checksum_pipeline == nil) {
        return set_error(
            error_buffer,
            error_capacity,
            pipeline_error.localizedDescription ?: @"Metal checksum pipeline creation failed");
    }
    pipeline_error = nil;
    id<MTLComputePipelineState> iq2_pipeline =
        build_pipeline(device, library, @"pulsar_iq2_xxs_gemv", &pipeline_error);
    if (iq2_pipeline == nil) {
        return set_error(
            error_buffer,
            error_capacity,
            pipeline_error.localizedDescription ?: @"Metal IQ2_XXS pipeline creation failed");
    }

    PulsarMetalContextObject *context = [PulsarMetalContextObject new];
    context.device = device;
    context.queue = queue;
    context.checksumPipeline = checksum_pipeline;
    context.iq2Pipeline = iq2_pipeline;
    context.compilationSeconds = elapsed_seconds(
        compilation_start, std::chrono::steady_clock::now());
    *out_context = (PulsarMetalContext *)CFBridgingRetain(context);
    return 0;
}

void pulsar_metal_context_destroy(PulsarMetalContext *context) {
    if (context != nullptr) {
        CFBridgingRelease((void *)context);
    }
}

int pulsar_metal_context_configure_iq2_xxs(
    PulsarMetalContext *raw_context,
    const uint8_t *grid,
    size_t grid_length,
    const uint8_t *signs,
    size_t signs_length,
    char *error_buffer,
    size_t error_capacity) {
    if (raw_context == nullptr || grid == nullptr || signs == nullptr) {
        return set_error(error_buffer, error_capacity, @"null IQ2_XXS table argument");
    }
    if (grid_length != kIQ2GridBytes || signs_length != kIQ2SignBytes) {
        return set_error(error_buffer, error_capacity, @"IQ2_XXS lookup-table length mismatch");
    }
    PulsarMetalContextObject *context = (__bridge PulsarMetalContextObject *)raw_context;
    context.iq2GridBuffer = [context.device newBufferWithBytes:grid
        length:grid_length
        options:MTLResourceStorageModeShared];
    context.iq2SignBuffer = [context.device newBufferWithBytes:signs
        length:signs_length
        options:MTLResourceStorageModeShared];
    if (context.iq2GridBuffer == nil || context.iq2SignBuffer == nil) {
        return set_error(error_buffer, error_capacity, @"IQ2_XXS lookup-buffer allocation failed");
    }
    return 0;
}

double pulsar_metal_context_compilation_seconds(PulsarMetalContext *raw_context) {
    if (raw_context == nullptr) {
        return -1.0;
    }
    PulsarMetalContextObject *context = (__bridge PulsarMetalContextObject *)raw_context;
    return context.compilationSeconds;
}

int pulsar_metal_context_device_name(
    PulsarMetalContext *raw_context,
    char *output,
    size_t output_capacity) {
    if (raw_context == nullptr || output == nullptr || output_capacity == 0) {
        return -1;
    }
    PulsarMetalContextObject *context = (__bridge PulsarMetalContextObject *)raw_context;
    snprintf(output, output_capacity, "%s", context.device.name.UTF8String ?: "Apple Metal device");
    return 0;
}

int pulsar_metal_register_no_copy(
    PulsarMetalContext *raw_context,
    const void *address,
    size_t length,
    PulsarMetalRegistration **out_registration,
    char *error_buffer,
    size_t error_capacity) {
    if (raw_context == nullptr || address == nullptr || out_registration == nullptr) {
        return set_error(error_buffer, error_capacity, @"null Metal registration argument");
    }
    if (length == 0) {
        return set_error(error_buffer, error_capacity, @"Metal registration length must be non-zero");
    }
    if (length > UINT32_MAX) {
        return set_error(error_buffer, error_capacity, @"Metal research bridge supports at most UINT32_MAX bytes per registration");
    }
    if ((reinterpret_cast<uintptr_t>(address) % kPageAlignment) != 0) {
        return set_error(error_buffer, error_capacity, @"Metal registration address is not page aligned");
    }

    PulsarMetalContextObject *context = (__bridge PulsarMetalContextObject *)raw_context;
    id<MTLBuffer> buffer = [context.device
        newBufferWithBytesNoCopy:(void *)address
        length:length
        options:MTLResourceStorageModeShared
        deallocator:nil];
    if (buffer == nil) {
        return set_error(error_buffer, error_capacity, @"newBufferWithBytesNoCopy returned nil");
    }

    PulsarMetalRegistrationObject *registration = [PulsarMetalRegistrationObject new];
    registration.buffer = buffer;
    registration.context = context;
    registration.address = address;
    registration.length = length;
    *out_registration = (PulsarMetalRegistration *)CFBridgingRetain(registration);
    return 0;
}

void pulsar_metal_registration_destroy(PulsarMetalRegistration *registration) {
    if (registration != nullptr) {
        CFBridgingRelease((void *)registration);
    }
}

int pulsar_metal_checksum(
    PulsarMetalContext *raw_context,
    PulsarMetalRegistration *raw_registration,
    uint32_t *out_checksum,
    char *error_buffer,
    size_t error_capacity) {
    if (raw_context == nullptr || raw_registration == nullptr || out_checksum == nullptr) {
        return set_error(error_buffer, error_capacity, @"null Metal checksum argument");
    }
    PulsarMetalContextObject *context = (__bridge PulsarMetalContextObject *)raw_context;
    PulsarMetalRegistrationObject *registration = (__bridge PulsarMetalRegistrationObject *)raw_registration;
    if (registration.context != context) {
        return set_error(error_buffer, error_capacity, @"Metal registration belongs to another context");
    }
    id<MTLBuffer> output = [context.device newBufferWithLength:sizeof(uint32_t)
        options:MTLResourceStorageModeShared];
    id<MTLBuffer> length_buffer = [context.device newBufferWithLength:sizeof(uint32_t)
        options:MTLResourceStorageModeShared];
    if (output == nil || length_buffer == nil) {
        return set_error(error_buffer, error_capacity, @"Metal checksum output allocation failed");
    }
    *static_cast<uint32_t *>(length_buffer.contents) = static_cast<uint32_t>(registration.length);

    id<MTLCommandBuffer> command_buffer = [context.queue commandBuffer];
    id<MTLComputeCommandEncoder> encoder = [command_buffer computeCommandEncoder];
    if (command_buffer == nil || encoder == nil) {
        return set_error(error_buffer, error_capacity, @"Metal command encoder unavailable");
    }
    [encoder setComputePipelineState:context.checksumPipeline];
    [encoder setBuffer:registration.buffer offset:0 atIndex:0];
    [encoder setBuffer:output offset:0 atIndex:1];
    [encoder setBuffer:length_buffer offset:0 atIndex:2];
    [encoder dispatchThreads:MTLSizeMake(1, 1, 1)
        threadsPerThreadgroup:MTLSizeMake(1, 1, 1)];
    [encoder endEncoding];
    [command_buffer commit];
    [command_buffer waitUntilCompleted];
    if (command_buffer.status != MTLCommandBufferStatusCompleted) {
        return set_error(error_buffer, error_capacity, command_buffer.error.localizedDescription ?: @"Metal command failed");
    }
    *out_checksum = *static_cast<const uint32_t *>(output.contents);
    return 0;
}

int pulsar_metal_iq2_xxs_gemv(
    PulsarMetalContext *raw_context,
    PulsarMetalRegistration *raw_registration,
    uint32_t rows,
    uint32_t columns,
    uint32_t packed_row_bytes,
    const float *activation,
    size_t activation_len,
    float *output_values,
    size_t output_len,
    PulsarIq2XxsGemvTelemetry *out_telemetry,
    char *error_buffer,
    size_t error_capacity) {
    if (raw_context == nullptr || raw_registration == nullptr || activation == nullptr ||
        output_values == nullptr || out_telemetry == nullptr) {
        return set_error(error_buffer, error_capacity, @"null IQ2_XXS GEMV argument");
    }
    PulsarMetalContextObject *context = (__bridge PulsarMetalContextObject *)raw_context;
    PulsarMetalRegistrationObject *registration = (__bridge PulsarMetalRegistrationObject *)raw_registration;
    if (registration.context != context) {
        return set_error(error_buffer, error_capacity, @"IQ2_XXS registration belongs to another context");
    }
    if (rows == 0 || columns == 0 || columns % 256u != 0 ||
        activation_len != columns || output_len != rows) {
        return set_error(error_buffer, error_capacity, @"invalid IQ2_XXS GEMV dimensions");
    }
    const uint64_t expected_row_bytes = (uint64_t(columns) / 256u) * 66u;
    const uint64_t expected_matrix_bytes = uint64_t(rows) * expected_row_bytes;
    if (packed_row_bytes != expected_row_bytes || registration.length != expected_matrix_bytes) {
        return set_error(error_buffer, error_capacity, @"IQ2_XXS packed byte accounting mismatch");
    }
    if (context.iq2GridBuffer == nil || context.iq2SignBuffer == nil) {
        return set_error(error_buffer, error_capacity, @"IQ2_XXS lookup buffers are unavailable");
    }

    const auto total_start = std::chrono::steady_clock::now();
    const auto dispatch_start = total_start;
    id<MTLBuffer> activation_buffer = [context.device newBufferWithBytes:activation
        length:activation_len * sizeof(float)
        options:MTLResourceStorageModeShared];
    id<MTLBuffer> output_buffer = [context.device newBufferWithLength:output_len * sizeof(float)
        options:MTLResourceStorageModeShared];
    if (activation_buffer == nil || output_buffer == nil) {
        return set_error(error_buffer, error_capacity, @"IQ2_XXS activation/output allocation failed");
    }
    memset(output_buffer.contents, 0, output_len * sizeof(float));

    struct IQ2XXSParams {
        uint32_t rows;
        uint32_t columns;
        uint32_t packed_row_bytes;
    } params = {rows, columns, packed_row_bytes};

    id<MTLCommandBuffer> command_buffer = [context.queue commandBuffer];
    id<MTLComputeCommandEncoder> encoder = [command_buffer computeCommandEncoder];
    if (command_buffer == nil || encoder == nil) {
        return set_error(error_buffer, error_capacity, @"IQ2_XXS Metal command encoder unavailable");
    }
    [encoder setComputePipelineState:context.iq2Pipeline];
    [encoder setBuffer:registration.buffer offset:0 atIndex:0];
    [encoder setBuffer:activation_buffer offset:0 atIndex:1];
    [encoder setBuffer:output_buffer offset:0 atIndex:2];
    [encoder setBuffer:context.iq2GridBuffer offset:0 atIndex:3];
    [encoder setBuffer:context.iq2SignBuffer offset:0 atIndex:4];
    [encoder setBytes:&params length:sizeof(params) atIndex:5];
    const NSUInteger width = MIN((NSUInteger)256, context.iq2Pipeline.maxTotalThreadsPerThreadgroup);
    [encoder dispatchThreads:MTLSizeMake(rows, 1, 1)
        threadsPerThreadgroup:MTLSizeMake(width, 1, 1)];
    [encoder endEncoding];
    [command_buffer commit];
    const auto dispatch_end = std::chrono::steady_clock::now();
    const auto synchronization_start = dispatch_end;
    [command_buffer waitUntilCompleted];
    const auto synchronization_end = std::chrono::steady_clock::now();
    if (command_buffer.status != MTLCommandBufferStatusCompleted) {
        return set_error(error_buffer, error_capacity,
            command_buffer.error.localizedDescription ?: @"IQ2_XXS Metal command failed");
    }
    memcpy(output_values, output_buffer.contents, output_len * sizeof(float));

    out_telemetry->dispatch_seconds = elapsed_seconds(dispatch_start, dispatch_end);
    out_telemetry->synchronization_seconds =
        elapsed_seconds(synchronization_start, synchronization_end);
    out_telemetry->total_seconds = elapsed_seconds(total_start, synchronization_end);
    if (command_buffer.GPUEndTime >= command_buffer.GPUStartTime &&
        command_buffer.GPUStartTime > 0.0) {
        out_telemetry->kernel_seconds = command_buffer.GPUEndTime - command_buffer.GPUStartTime;
    } else {
        out_telemetry->kernel_seconds = -1.0;
    }
    return 0;
}

uintptr_t pulsar_metal_registration_address(PulsarMetalRegistration *raw_registration) {
    if (raw_registration == nullptr) {
        return 0;
    }
    PulsarMetalRegistrationObject *registration = (__bridge PulsarMetalRegistrationObject *)raw_registration;
    return reinterpret_cast<uintptr_t>(registration.address);
}

}
