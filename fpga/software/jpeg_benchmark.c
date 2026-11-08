/* SPDX-License-Identifier: MIT
 * RGB565 -> JPEG benchmark and single-frame pipe encoder. No FPGA access.
 * cc -std=c99 -O2 -Wall -Wextra -Werror jpeg_benchmark.c -o jpeg_benchmark -ljpeg -lrt
 */
#define _POSIX_C_SOURCE 200809L
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <setjmp.h>
#include <time.h>
#include <jpeglib.h>
#include <jerror.h>

struct benchmark_error {
    struct jpeg_error_mgr public;
    jmp_buf jump;
};

struct memory_destination {
    struct jpeg_destination_mgr public;
    JOCTET *buffer;
    size_t capacity;
    size_t length;
};

struct encoder {
    struct jpeg_compress_struct jpeg;
    struct benchmark_error error;
    struct memory_destination destination;
    int created;
};

static void jpeg_failure(j_common_ptr jpeg)
{
    struct benchmark_error *error = (struct benchmark_error *)jpeg->err;
    (*jpeg->err->output_message)(jpeg);
    longjmp(error->jump, 1);
}

static void destination_init(j_compress_ptr jpeg)
{
    struct memory_destination *destination = (struct memory_destination *)jpeg->dest;
    destination->length = 0;
    destination->public.next_output_byte = destination->buffer;
    destination->public.free_in_buffer = destination->capacity;
}

static boolean destination_grow(j_compress_ptr jpeg)
{
    struct memory_destination *destination = (struct memory_destination *)jpeg->dest;
    size_t previous = destination->capacity;
    JOCTET *grown;
    if (previous > SIZE_MAX / 2) ERREXIT(jpeg, JERR_OUT_OF_MEMORY);
    grown = (JOCTET *)realloc(destination->buffer, previous * 2);
    if (!grown) ERREXIT(jpeg, JERR_OUT_OF_MEMORY);
    destination->buffer = grown;
    destination->capacity = previous * 2;
    destination->public.next_output_byte = grown + previous;
    destination->public.free_in_buffer = previous;
    return TRUE;
}

static void destination_finish(j_compress_ptr jpeg)
{
    struct memory_destination *destination = (struct memory_destination *)jpeg->dest;
    destination->length = destination->capacity - destination->public.free_in_buffer;
}

static double seconds(clockid_t clock)
{
    struct timespec stamp;
    if (clock_gettime(clock, &stamp) != 0) return -1;
    return (double)stamp.tv_sec + (double)stamp.tv_nsec / 1e9;
}

static int positive_integer(const char *text, long limit, int *output)
{
    char *end;
    long value;
    errno = 0;
    value = strtol(text, &end, 10);
    if (!text[0] || errno || *end || value < 1 || value > limit) return -1;
    *output = (int)value;
    return 0;
}

static void usage(const char *program)
{
    fprintf(stderr, "Usage: %s INPUT.rgb565 [--width 320] [--height 240] [--frames 30]\n"
            "       [--quality 75] [--output FIRST_FRAME.jpg]\n"
            "       %s --stdin --stdout [--width 320] [--height 240] [--quality 75]\n", program, program);
}

static int prepare_encoder(struct encoder *encoder, int width, int height, int quality)
{
    encoder->jpeg.err = jpeg_std_error(&encoder->error.public);
    encoder->error.public.error_exit = jpeg_failure;
    if (setjmp(encoder->error.jump)) return -1;
    jpeg_create_compress(&encoder->jpeg);
    encoder->created = 1;
    encoder->destination.public.init_destination = destination_init;
    encoder->destination.public.empty_output_buffer = destination_grow;
    encoder->destination.public.term_destination = destination_finish;
    encoder->jpeg.dest = &encoder->destination.public;
    encoder->jpeg.image_width = (JDIMENSION)width;
    encoder->jpeg.image_height = (JDIMENSION)height;
    encoder->jpeg.input_components = 3;
    encoder->jpeg.in_color_space = JCS_RGB;
    jpeg_set_defaults(&encoder->jpeg);
    jpeg_set_quality(&encoder->jpeg, quality, TRUE);
    encoder->jpeg.optimize_coding = FALSE;
    return 0;
}

static int encode_frame(struct encoder *encoder, unsigned char *rgb, int width)
{
    if (setjmp(encoder->error.jump)) return -1;
    jpeg_start_compress(&encoder->jpeg, TRUE);
    while (encoder->jpeg.next_scanline < encoder->jpeg.image_height) {
        JSAMPROW row = rgb + (size_t)encoder->jpeg.next_scanline * width * 3;
        if (jpeg_write_scanlines(&encoder->jpeg, &row, 1) != 1) return -1;
    }
    jpeg_finish_compress(&encoder->jpeg);
    return 0;
}

int main(int argc, char **argv)
{
    int width = 320, height = 240, frames = 30, quality = 75, argument;
    int result = 1, frame, pipe_input = 0, pipe_output = 0;
    const char *input_path = NULL, *output_path = NULL;
    unsigned char *input = NULL, *rgb = NULL;
    FILE *file = NULL;
    struct encoder *encoder = NULL;
    size_t pixel_count, input_bytes, encoded_min = SIZE_MAX, encoded_max = 0;
    double wall_sum = 0, cpu_sum = 0, conversion_sum = 0, jpeg_sum = 0, byte_sum = 0;
    if (argc < 2) { usage(argv[0]); return 2; }
    for (argument = 1; argument < argc; ++argument) {
        const char *option = argv[argument];
        if (!strcmp(option, "--help")) { usage(argv[0]); return 0; }
        if (!strcmp(option, "--stdin")) { pipe_input = 1; continue; }
        if (!strcmp(option, "--stdout")) { pipe_output = 1; continue; }
        if (option[0] != '-') {
            if (input_path) goto invalid_arguments;
            input_path = option;
            continue;
        }
        if (argument + 1 >= argc) goto invalid_arguments;
        if (!strcmp(option, "--width")) {
            if (positive_integer(argv[++argument], 2048, &width)) goto invalid_arguments;
        } else if (!strcmp(option, "--height")) {
            if (positive_integer(argv[++argument], 2048, &height)) goto invalid_arguments;
        } else if (!strcmp(option, "--frames")) {
            if (positive_integer(argv[++argument], 100000, &frames)) goto invalid_arguments;
        } else if (!strcmp(option, "--quality")) {
            if (positive_integer(argv[++argument], 100, &quality)) goto invalid_arguments;
        } else if (!strcmp(option, "--output")) {
            output_path = argv[++argument];
        } else goto invalid_arguments;
    }
    if (pipe_input != pipe_output || (pipe_input && (input_path || output_path))) goto invalid_arguments;
    if (!input_path && !pipe_input) goto invalid_arguments;
    if (pipe_input) frames = 1;
    pixel_count = (size_t)width * height;
    input_bytes = pixel_count * 2;
    input = (unsigned char *)malloc(input_bytes);
    rgb = (unsigned char *)malloc(pixel_count * 3);
    encoder = (struct encoder *)calloc(1, sizeof(*encoder));
    if (!input || !rgb || !encoder) { fprintf(stderr, "allocation failed\n"); goto done; }
    file = pipe_input ? stdin : fopen(input_path, "rb");
    if (!file) { perror("open input"); goto done; }
    if (fread(input, 1, input_bytes, file) != input_bytes || fgetc(file) != EOF || ferror(file)) {
        fprintf(stderr, "input must contain exactly %zu tightly packed RGB565 bytes\n", input_bytes);
        goto done;
    }
    if (!pipe_input) fclose(file);
    file = NULL;
    encoder->destination.capacity = 65536;
    encoder->destination.buffer = (JOCTET *)malloc(encoder->destination.capacity);
    if (!encoder->destination.buffer) { fprintf(stderr, "destination allocation failed\n"); goto done; }
    if (prepare_encoder(encoder, width, height, quality)) {
        fprintf(stderr, "JPEG initialization failed\n"); goto done;
    }

    for (frame = 0; frame < frames; ++frame) {
        size_t pixel;
        double wall_start, cpu_start, converted, wall_end, cpu_end;
        wall_start = seconds(CLOCK_MONOTONIC);
        cpu_start = seconds(CLOCK_PROCESS_CPUTIME_ID);
        if (wall_start < 0 || cpu_start < 0) { perror("clock_gettime"); goto done; }
        for (pixel = 0; pixel < pixel_count; ++pixel) {
            unsigned int word = input[pixel * 2] | ((unsigned int)input[pixel * 2 + 1] << 8);
            unsigned int red = (word >> 11) & 31, green = (word >> 5) & 63, blue = word & 31;
            rgb[pixel * 3] = (unsigned char)((red << 3) | (red >> 2));
            rgb[pixel * 3 + 1] = (unsigned char)((green << 2) | (green >> 4));
            rgb[pixel * 3 + 2] = (unsigned char)((blue << 3) | (blue >> 2));
        }
        converted = seconds(CLOCK_MONOTONIC);
        if (converted < 0) { perror("clock_gettime"); goto done; }
        if (encode_frame(encoder, rgb, width)) {
            fprintf(stderr, "JPEG encode failed\n"); goto done;
        }
        wall_end = seconds(CLOCK_MONOTONIC);
        cpu_end = seconds(CLOCK_PROCESS_CPUTIME_ID);
        if (wall_end < 0 || cpu_end < 0) { perror("clock_gettime"); goto done; }
        wall_sum += wall_end - wall_start;
        cpu_sum += cpu_end - cpu_start;
        conversion_sum += converted - wall_start;
        jpeg_sum += wall_end - converted;
        byte_sum += encoder->destination.length;
        if (encoder->destination.length < encoded_min) encoded_min = encoder->destination.length;
        if (encoder->destination.length > encoded_max) encoded_max = encoder->destination.length;
        if (frame == 0 && output_path) {
            file = fopen(output_path, "wb");
            if (!file) { perror("open JPEG output"); goto done; }
            if (fwrite(encoder->destination.buffer, 1, encoder->destination.length, file) != encoder->destination.length) {
                perror("write JPEG output"); goto done;
            }
            if (fclose(file)) { file = NULL; perror("close JPEG output"); goto done; }
            file = NULL;
        }
    }
    if (pipe_output) {
        if (fwrite(encoder->destination.buffer, 1, encoder->destination.length, stdout) != encoder->destination.length || fflush(stdout)) {
            perror("write JPEG stdout"); goto done;
        }
    }
    fprintf(pipe_output ? stderr : stdout, "{\"source\":\"%s\",\"width\":%d,\"height\":%d,"
           "\"frames\":%d,\"quality\":%d,\"input_bytes\":%zu,\"mean_encode_ms\":%.6f,"
           "\"cpu_ms\":%.6f,\"rgb_conversion_ms\":%.6f,\"jpeg_ms\":%.6f,"
           "\"bytes\":%.0f,\"min_bytes\":%zu,\"max_bytes\":%zu,\"jpeg_lib_version\":%d,"
           "\"timing_includes_rgb_conversion\":true,\"file_io_timed\":false}\n",
           pipe_output ? "native-rgb565-jpeg-encoder" : "offline-rgb565-jpeg-benchmark",
           width, height, frames, quality, input_bytes, wall_sum * 1000 / frames,
           cpu_sum * 1000 / frames, conversion_sum * 1000 / frames,
           jpeg_sum * 1000 / frames, byte_sum / frames, encoded_min, encoded_max,
           JPEG_LIB_VERSION);
    result = 0;
done:
    if (file) fclose(file);
    if (encoder) {
        if (encoder->created) jpeg_destroy_compress(&encoder->jpeg);
        free(encoder->destination.buffer);
        free(encoder);
    }
    free(rgb);
    free(input);
    return result;
invalid_arguments:
    usage(argv[0]);
    return 2;
}
