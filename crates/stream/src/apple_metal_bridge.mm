#import <Foundation/Foundation.h>
#import <Metal/Metal.h>

#include <stdint.h>
#include <stdio.h>
#include <string.h>

static constexpr uintptr_t kPageAlignment = 4096;

static NSString *const kChecksumSource = @R"METAL(
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
)METAL";

@interface PulsarMetalContextObject : NSObject
@property(nonatomic, strong) id<MTLDevice> device;
@property(nonatomic, strong) id<MTLCommandQueue> queue;
@property(nonatomic, strong) id<MTLComputePipelineState> checksumPipeline;
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

int pulsar_metal_context_create(
    PulsarMetalContext **out_context,
    char *error_buffer,
    size_t error_capacity) {
    if (out_context == nullptr) {
        return set_error(error_buffer, error_capacity, @"null context output");
    }
    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    if (device == nil) {
        return set_error(error_buffer, error_capacity, @"Metal device unavailable");
    }
    id<MTLCommandQueue> queue = [device newCommandQueue];
    if (queue == nil) {
        return set_error(error_buffer, error_capacity, @"Metal command queue unavailable");
    }
    NSError *library_error = nil;
    id<MTLLibrary> library = [device newLibraryWithSource:kChecksumSource options:nil error:&library_error];
    if (library == nil) {
        return set_error(
            error_buffer,
            error_capacity,
            library_error.localizedDescription ?: @"Metal checksum library compilation failed");
    }
    id<MTLFunction> function = [library newFunctionWithName:@"pulsar_checksum"];
    if (function == nil) {
        return set_error(error_buffer, error_capacity, @"Metal checksum function unavailable");
    }
    NSError *pipeline_error = nil;
    id<MTLComputePipelineState> pipeline = [device newComputePipelineStateWithFunction:function error:&pipeline_error];
    if (pipeline == nil) {
        return set_error(
            error_buffer,
            error_capacity,
            pipeline_error.localizedDescription ?: @"Metal checksum pipeline creation failed");
    }

    PulsarMetalContextObject *context = [PulsarMetalContextObject new];
    context.device = device;
    context.queue = queue;
    context.checksumPipeline = pipeline;
    *out_context = (PulsarMetalContext *)CFBridgingRetain(context);
    return 0;
}

void pulsar_metal_context_destroy(PulsarMetalContext *context) {
    if (context != nullptr) {
        CFBridgingRelease((void *)context);
    }
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
        return set_error(error_buffer, error_capacity, @"Metal checksum smoke path supports at most UINT32_MAX bytes");
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

uintptr_t pulsar_metal_registration_address(PulsarMetalRegistration *raw_registration) {
    if (raw_registration == nullptr) {
        return 0;
    }
    PulsarMetalRegistrationObject *registration = (__bridge PulsarMetalRegistrationObject *)raw_registration;
    return reinterpret_cast<uintptr_t>(registration.address);
}

}
