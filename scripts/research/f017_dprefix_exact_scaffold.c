#include <errno.h>
#include <fcntl.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

/* DPREFIX-EXACT-1 implementation A.
 *
 * Every reduction is a single, increasing-index binary64 accumulator.  The
 * reviewed build disables contraction and vectorization.  Position-zero
 * attention has exactly one visible token, so q/k cannot affect the value
 * path and are analytically eliminated; all value-path and FFN contractions
 * remain explicit.
 */

enum { HIDDEN = 6144, HEADS = 64, VALUE = 256, KV = 512, FFN = 12288 };
static const double RMS_EPSILON = 9.999999747378752e-6;

typedef struct {
    char name[96];
    char path[1024];
    size_t dims[3];
    int rank;
    size_t bytes;
    const float *data;
} Tensor;

static Tensor tensors[40];
static size_t tensor_count = 0;

static void fail(const char *message) {
    fprintf(stderr, "DPREFIX-EXACT-1-A: %s\n", message);
    exit(2);
}

static Tensor *tensor(const char *name) {
    for (size_t i = 0; i < tensor_count; ++i) {
        if (strcmp(tensors[i].name, name) == 0) return &tensors[i];
    }
    fail("missing tensor");
    return NULL;
}

static void load_manifest(const char *path) {
    FILE *source = fopen(path, "r");
    if (!source) fail("manifest open");
    char line[1400];
    while (fgets(line, sizeof line, source)) {
        if (tensor_count == 40) fail("manifest overflow");
        Tensor *item = &tensors[tensor_count];
        unsigned long long d0 = 0, d1 = 0, d2 = 0;
        int fields = sscanf(line, "%95s\t%1023s\t%d\t%llu\t%llu\t%llu",
                            item->name, item->path, &item->rank, &d0, &d1, &d2);
        if (fields != 6 || item->rank < 1 || item->rank > 3) fail("manifest parse");
        item->dims[0] = (size_t)d0; item->dims[1] = (size_t)d1; item->dims[2] = (size_t)d2;
        size_t count = item->dims[0];
        for (int i = 1; i < item->rank; ++i) count *= item->dims[i];
        item->bytes = count * sizeof(float);
        int fd = open(item->path, O_RDONLY | O_NOFOLLOW);
        if (fd < 0) fail("tensor open");
        struct stat status;
        if (fstat(fd, &status) || !S_ISREG(status.st_mode) || (size_t)status.st_size != item->bytes)
            fail("tensor identity");
        void *mapped = mmap(NULL, item->bytes, PROT_READ, MAP_PRIVATE, fd, 0);
        close(fd);
        if (mapped == MAP_FAILED) fail("tensor mmap");
        item->data = (const float *)mapped;
        ++tensor_count;
    }
    fclose(source);
    if (tensor_count != 40) fail("manifest count");
}

static float *allocate(size_t count) {
    float *value = calloc(count, sizeof(float));
    if (!value) fail("allocation");
    return value;
}

static void matvec(const float *matrix, size_t rows, size_t columns,
                   const float *vector, float *output) {
    for (size_t row = 0; row < rows; ++row) {
        double sum = 0.0;
        const float *weights = matrix + row * columns;
        for (size_t column = 0; column < columns; ++column)
            sum += (double)weights[column] * (double)vector[column];
        output[row] = (float)sum;
    }
}

static void rms_norm(const float *input, const float *weight, size_t count, float *output) {
    double square_sum = 0.0;
    for (size_t i = 0; i < count; ++i) square_sum += (double)input[i] * (double)input[i];
    float inverse = (float)(1.0 / sqrt(square_sum / (double)count + RMS_EPSILON));
    for (size_t i = 0; i < count; ++i) output[i] = (input[i] * inverse) * weight[i];
}

static void write_surface(const char *directory, const char *name, const float *values, size_t count) {
    char path[1200];
    snprintf(path, sizeof path, "%s/%s.f32le", directory, name);
    FILE *target = fopen(path, "wb");
    if (!target || fwrite(values, sizeof(float), count, target) != count || fclose(target))
        fail("surface write");
}

static float *run_layer(int layer, const float *residual, const char *output_dir) {
    char name[96];
    float *normalized = allocate(HIDDEN);
    snprintf(name, sizeof name, "blk.%d.attn_norm.weight", layer);
    rms_norm(residual, tensor(name)->data, HIDDEN, normalized);

    float *kv_raw = allocate(KV + 64);
    snprintf(name, sizeof name, "blk.%d.attn_kv_a_mqa.weight", layer);
    matvec(tensor(name)->data, KV + 64, HIDDEN, normalized, kv_raw);
    free(normalized);
    float *kv = allocate(KV);
    snprintf(name, sizeof name, "blk.%d.attn_kv_a_norm.weight", layer);
    rms_norm(kv_raw, tensor(name)->data, KV, kv);
    free(kv_raw);

    float *values = allocate(HEADS * VALUE);
    snprintf(name, sizeof name, "blk.%d.attn_v_b.weight", layer);
    const float *value_weights = tensor(name)->data;
    for (size_t head = 0; head < HEADS; ++head)
        matvec(value_weights + head * VALUE * KV, VALUE, KV, kv, values + head * VALUE);
    free(kv);

    float *attention = allocate(HIDDEN);
    snprintf(name, sizeof name, "blk.%d.attn_output.weight", layer);
    matvec(tensor(name)->data, HIDDEN, HEADS * VALUE, values, attention);
    free(values);
    char surface[64];
    snprintf(surface, sizeof surface, "layer_%d_attention", layer);
    write_surface(output_dir, surface, attention, HIDDEN);

    float *attention_residual = allocate(HIDDEN);
    for (size_t i = 0; i < HIDDEN; ++i) attention_residual[i] = residual[i] + attention[i];
    free(attention);
    float *ffn_input = allocate(HIDDEN);
    snprintf(name, sizeof name, "blk.%d.ffn_norm.weight", layer);
    rms_norm(attention_residual, tensor(name)->data, HIDDEN, ffn_input);

    float *gate = allocate(FFN), *up = allocate(FFN), *activated = allocate(FFN);
    snprintf(name, sizeof name, "blk.%d.ffn_gate.weight", layer);
    matvec(tensor(name)->data, FFN, HIDDEN, ffn_input, gate);
    snprintf(name, sizeof name, "blk.%d.ffn_up.weight", layer);
    matvec(tensor(name)->data, FFN, HIDDEN, ffn_input, up);
    free(ffn_input);
    for (size_t i = 0; i < FFN; ++i)
        activated[i] = (gate[i] / (1.0f + expf(-gate[i]))) * up[i];
    free(gate); free(up);
    float *down = allocate(HIDDEN);
    snprintf(name, sizeof name, "blk.%d.ffn_down.weight", layer);
    matvec(tensor(name)->data, HIDDEN, FFN, activated, down);
    free(activated);
    float *output = allocate(HIDDEN);
    for (size_t i = 0; i < HIDDEN; ++i) output[i] = attention_residual[i] + down[i];
    free(attention_residual); free(down);
    snprintf(surface, sizeof surface, "layer_%d_output", layer);
    write_surface(output_dir, surface, output, HIDDEN);
    return output;
}

int main(int argc, char **argv) {
    if (argc != 3) fail("usage: exact-input-manifest output-directory");
    load_manifest(argv[1]);
    Tensor *embedding = tensor("token_embd.weight");
    if (embedding->rank != 2 || embedding->dims[0] != 154880 || embedding->dims[1] != HIDDEN)
        fail("embedding shape");
    float *hidden = allocate(HIDDEN);
    memcpy(hidden, embedding->data + (size_t)9703 * HIDDEN, HIDDEN * sizeof(float));
    write_surface(argv[2], "embedding", hidden, HIDDEN);
    for (int layer = 0; layer < 3; ++layer) {
        float *next = run_layer(layer, hidden, argv[2]);
        free(hidden); hidden = next;
    }
    write_surface(argv[2], "layer_3_entry", hidden, HIDDEN);
    free(hidden);
    return 0;
}
