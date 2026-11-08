/* SPDX-License-Identifier: MIT
 * Native Glide diagnostic producer; FPGA coverage/depth/texturing only.
 * Requires GPU2 sidecar, verified Standard bitstream and reserved DDR pool.
 */
#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#include <glide.h>

extern int gpu_mmio_read32(void *, size_t, size_t, uint32_t *);
extern int gpu_mmio_write32(void *, size_t, size_t, uint32_t);
#define WIDTH 320
#define HEIGHT 240
#define FRAME_BYTES (WIDTH * HEIGHT * 2)
#define SIDECAR_SPAN 4096u
static int progress_fd = -1;
static int queued_primitives = 0;

static double now(void)
{
    struct timespec stamp;
    if (clock_gettime(CLOCK_MONOTONIC, &stamp)) return -1;
    return (double)stamp.tv_sec + stamp.tv_nsec / 1e9;
}

/* Optional crash/hang breadcrumbs stay separate from the pixel/JSON protocol. */
static int progress_mark(const char *stage)
{
    char line[160];
    size_t offset = 0;
    int length;
    if (progress_fd < 0) return 0;
    length = snprintf(line, sizeof(line), "%.9f %s\n", now(), stage);
    if (length < 0 || (size_t)length >= sizeof(line)) return -1;
    while (offset < (size_t)length) {
        ssize_t count = write(progress_fd, line + offset, (size_t)length - offset);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) return -1;
        offset += (size_t)count;
    }
    return fsync(progress_fd);
}

#define MARK(stage) do { if (progress_mark(stage)) { \
    failure = "cannot persist diagnostic progress"; goto done; } } while (0)

static uint32_t reg_read(void *map, unsigned offset)
{
    uint32_t value = 0;
    if (gpu_mmio_read32(map, SIDECAR_SPAN, offset, &value)) abort();
    return value;
}

static void reg_write(void *map, unsigned offset, uint32_t value)
{
    if (gpu_mmio_write32(map, SIDECAR_SPAN, offset, value)) abort();
}

static int wait_ready(void *map, double timeout)
{
    double start = now();
    struct timespec nap = {0, 1000000};
    if (start < 0) return -1;
    for (;;) {
        uint32_t status = reg_read(map, 8);
        double current;
        if (status & ~15u || status & 8u) {
            fprintf(stderr, "GPU2 error status 0x%08" PRIx32 "\n", status);
            return -1;
        }
        if (status & 4u) return 0;
        current = now();
        if (current < 0 || current - start >= timeout) {
            fprintf(stderr, "GPU2 fence timeout status 0x%08" PRIx32 "\n", status);
            return -1;
        }
        nanosleep(&nap, NULL);
    }
}

static GrVertex vertex(float x, float y, float depth)
{
    GrVertex value;
    memset(&value, 0, sizeof(value));
    value.x = x; value.y = y; value.ooz = depth;
    value.r = value.g = value.b = value.a = 255;
    value.oow = 1;
    value.tmuvtx[0].oow = 1;
    return value;
}

/* The current port consumes some render state live after command issue.
 * Serialize primitives before the caller changes constant color or other
 * state. Publication still requires the separate final GPU2 fence below.
 */
static void submit_triangle(const GrVertex *a, const GrVertex *b, const GrVertex *c)
{
    grDrawTriangle(a, b, c);
    if (!queued_primitives) grSstIdle();
}

static void draw_triangle(float x0, float y0, float x1, float y1,
                          float x2, float y2, float depth, FxU32 color)
{
    GrVertex a = vertex(x0, y0, depth), b = vertex(x1, y1, depth), c = vertex(x2, y2, depth);
    grConstantColorValue(color);
    submit_triangle(&a, &b, &c);
}

static void configure_state(void)
{
    grRenderBuffer(GR_BUFFER_BACKBUFFER);
    grClipWindow(0, 0, WIDTH, HEIGHT);
    grCullMode(GR_CULL_DISABLE);
    grDitherMode(GR_DITHER_DISABLE);
    grDepthBufferMode(GR_DEPTHBUFFER_ZBUFFER);
    grDepthBufferFunction(GR_CMP_GREATER);
    grDepthMask(FXTRUE);
    grColorMask(FXTRUE, FXFALSE);
    grAlphaTestFunction(GR_CMP_ALWAYS);
    grAlphaBlendFunction(GR_BLEND_ONE, GR_BLEND_ZERO, GR_BLEND_ONE, GR_BLEND_ZERO);
    grFogMode(GR_FOG_DISABLE);
    grChromakeyMode(GR_CHROMAKEY_DISABLE);
    grColorCombine(GR_COMBINE_FUNCTION_LOCAL, GR_COMBINE_FACTOR_NONE,
                   GR_COMBINE_LOCAL_CONSTANT, GR_COMBINE_OTHER_NONE, FXFALSE);
    grBufferClear(0, 0, 0);
    if (!queued_primitives) grSstIdle();
}

static void draw_depth(int near_first)
{
    if (near_first) draw_triangle(70, 50, 250, 50, 160, 210, 50000, 0xff0000ffu);
    draw_triangle(40, 180, 280, 180, 160, 25, 20000, 0xffff0000u);
    if (!near_first) draw_triangle(70, 50, 250, 50, 160, 210, 50000, 0xff0000ffu);
}

static void texture_setup(void)
{
    static FxU16 checker[64 * 64];
    GrTexInfo info;
    unsigned x, y;
    for (y = 0; y < 64; ++y) for (x = 0; x < 64; ++x)
        checker[y * 64 + x] = ((x / 8) ^ (y / 8)) & 1 ? 0xffff : 0x001f;
    memset(&info, 0, sizeof(info));
    info.smallLod = info.largeLod = GR_LOD_64;
    info.aspectRatio = GR_ASPECT_1x1;
    info.format = GR_TEXFMT_RGB_565;
    info.data = checker;
    grTexDownloadMipMap(GR_TMU0, 0, GR_MIPMAPLEVELMASK_BOTH, &info);
    grTexSource(GR_TMU0, 0, GR_MIPMAPLEVELMASK_BOTH, &info);
    grTexClampMode(GR_TMU0, GR_TEXTURECLAMP_CLAMP, GR_TEXTURECLAMP_CLAMP);
    grTexFilterMode(GR_TMU0, GR_TEXTUREFILTER_POINT_SAMPLED, GR_TEXTUREFILTER_POINT_SAMPLED);
    grTexMipMapMode(GR_TMU0, GR_MIPMAP_DISABLE, FXFALSE);
    grTexCombine(GR_TMU0, GR_COMBINE_FUNCTION_LOCAL, GR_COMBINE_FACTOR_NONE,
                 GR_COMBINE_FUNCTION_LOCAL, GR_COMBINE_FACTOR_NONE, FXFALSE, FXFALSE);
    grColorCombine(GR_COMBINE_FUNCTION_SCALE_OTHER, GR_COMBINE_FACTOR_ONE,
                   GR_COMBINE_LOCAL_NONE, GR_COMBINE_OTHER_TEXTURE, FXFALSE);
}

static void draw_cube(double degrees, int textured)
{
    static const float positions[8][3] = {
        {-1,-1,-1},{1,-1,-1},{1,1,-1},{-1,1,-1},
        {-1,-1,1},{1,-1,1},{1,1,1},{-1,1,1}
    };
    static const unsigned faces[6][4] = {
        {0,1,2,3},{5,4,7,6},{4,0,3,7},{1,5,6,2},{3,2,6,7},{4,5,1,0}
    };
    static const FxU32 colors[6] = {
        0xff0000ffu,0xff00ff00u,0xffff0000u,0xff00ffffu,0xffffff00u,0xffff00ffu
    };
    /* Glide texture coordinates span 0..255 independently of selected LOD. */
    static const float uv[4][2] = {{0,0},{255,0},{255,255},{0,255}};
    GrVertex projected[8];
    double angle = degrees * 0.017453292519943295;
    double cy = cos(angle), sy = sin(angle), cx = cos(angle * 0.6 + 0.35), sx = sin(angle * 0.6 + 0.35);
    unsigned i, face;
    for (i = 0; i < 8; ++i) {
        double x = positions[i][0] * cy + positions[i][2] * sy;
        double z = -positions[i][0] * sy + positions[i][2] * cy;
        double y = positions[i][1] * cx - z * sx;
        double camera_z = positions[i][1] * sx + z * cx + 4;
        projected[i] = vertex((float)(160 + 150 * x / camera_z),
                              (float)(120 - 150 * y / camera_z), (float)(65535 / camera_z));
        projected[i].oow = (float)(1 / camera_z);
    }
    if (textured) texture_setup();
    for (face = 0; face < 6; ++face) {
        GrVertex corners[4];
        for (i = 0; i < 4; ++i) {
            corners[i] = projected[faces[face][i]];
            corners[i].tmuvtx[0].oow = corners[i].oow;
            corners[i].tmuvtx[0].sow = uv[i][0] * corners[i].oow;
            corners[i].tmuvtx[0].tow = uv[i][1] * corners[i].oow;
        }
        if (!textured) grConstantColorValue(colors[face]);
        submit_triangle(&corners[0], &corners[1], &corners[2]);
        submit_triangle(&corners[0], &corners[2], &corners[3]);
    }
}

static int parse_address(const char *text, uint32_t *value)
{
    char *end;
    unsigned long long number;
    errno = 0;
    number = strtoull(text, &end, 0);
    if (!text[0] || text[0] == '-' || errno || *end || number > UINT32_MAX || number % 4096) return -1;
    *value = (uint32_t)number;
    return 0;
}

static void usage(const char *program)
{
    fprintf(stderr, "Usage: %s --base 0xc0000000 --sidecar-base 0xff240000\n"
            " [--scene triangle|depth|cube|textured-cube] [--angle DEGREES]\n"
            " [--depth-order near-first|far-first] [--stdout|--output FILE]\n"
            " [--timeout SECONDS] [--log FILE] [--progress FILE] [--queued-primitives] [--no-depth-test]\n", program);
}

int main(int argc, char **argv)
{
    uint32_t base = 0, sidecar_base = 0, sequence = 0, cycles = 0, busy_cycles = 0, hz = 0;
    int have_base = 0, have_sidecar = 0, binary_stdout = 0, explicit_output = 0, near_first = 0;
    int fd = -1, lock_fd = -1, saved_out = -1, saved_error = -1, redirected = 0, initialized = 0;
    int owned_ready = 0, result = 1, argument;
    int no_depth_test = 0;
    const char *scene = "triangle", *output_path = "frame.rgb565", *log_path = "/tmp/gpu-spinal-glide.log";
    const char *failure = "native renderer failed";
    const char *progress_path = NULL;
    FILE *log = NULL, *output = NULL;
    void *map = MAP_FAILED, *sst_map = MAP_FAILED;
    unsigned char *pixels = NULL;
    double angle = 0, timeout = 2, started = 0, copy_start, copy_seconds = 0, capture_seconds = 0, init_seconds = 0;
    GrHwConfiguration hardware;
    for (argument = 1; argument < argc; ++argument) {
        const char *option = argv[argument];
        char *end;
        if (!strcmp(option, "--stdout")) { binary_stdout = 1; continue; }
        if (!strcmp(option, "--queued-primitives")) { queued_primitives = 1; continue; }
        if (!strcmp(option, "--no-depth-test")) { no_depth_test = 1; continue; }
        if (!strcmp(option, "--help")) { usage(argv[0]); return 0; }
        if (argument + 1 >= argc) goto bad_arguments;
        if (!strcmp(option, "--base")) { if (parse_address(argv[++argument], &base)) goto bad_arguments; have_base = 1; }
        else if (!strcmp(option, "--sidecar-base")) { if (parse_address(argv[++argument], &sidecar_base)) goto bad_arguments; have_sidecar = 1; }
        else if (!strcmp(option, "--scene")) scene = argv[++argument];
        else if (!strcmp(option, "--output")) { output_path = argv[++argument]; explicit_output = 1; }
        else if (!strcmp(option, "--log")) log_path = argv[++argument];
        else if (!strcmp(option, "--progress")) progress_path = argv[++argument];
        else if (!strcmp(option, "--depth-order")) {
            const char *order = argv[++argument];
            if (strcmp(order, "near-first") && strcmp(order, "far-first")) goto bad_arguments;
            near_first = !strcmp(order, "near-first");
        } else if (!strcmp(option, "--angle")) {
            angle = strtod(argv[++argument], &end);
            if (*end || !isfinite(angle) || fabs(angle) > 1e9) goto bad_arguments;
        } else if (!strcmp(option, "--timeout")) {
            timeout = strtod(argv[++argument], &end);
            if (*end || !isfinite(timeout) || timeout <= 0) goto bad_arguments;
        } else goto bad_arguments;
    }
    if (!have_base || !have_sidecar || (binary_stdout && explicit_output) ||
        (strcmp(scene, "triangle") && strcmp(scene, "depth") && strcmp(scene, "cube") && strcmp(scene, "textured-cube"))) goto bad_arguments;
    if (progress_path) {
        progress_fd = open(progress_path, O_WRONLY | O_CREAT | O_APPEND, 0600);
        if (progress_fd < 0) { failure = "cannot open diagnostic progress file"; goto done; }
        MARK("capture.begin");
    }
    lock_fd = open("/run/lock/de10-gpu-platform.lock", O_RDWR | O_CREAT, 0600);
    if (lock_fd < 0 || flock(lock_fd, LOCK_EX | LOCK_NB)) { failure = "exclusive framebuffer lock unavailable"; goto done; }
    fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) { failure = "cannot open /dev/mem"; goto done; }
    map = mmap(NULL, SIDECAR_SPAN, PROT_READ | PROT_WRITE, MAP_SHARED, fd, (off_t)sidecar_base);
    if (map == MAP_FAILED) { failure = "cannot map GPU2 sidecar"; goto done; }
    MARK("sidecar.identity.before");
    if (reg_read(map, 0) != 0x47505532u || reg_read(map, 4) != 2 ||
        reg_read(map, 0x10) != WIDTH || reg_read(map, 0x14) != HEIGHT ||
        reg_read(map, 0x18) != WIDTH * 2 || reg_read(map, 0x1c) != 1) {
        failure = "GPU2 identity/ABI/geometry mismatch; refusing renderer writes"; goto done;
    }
    MARK("sidecar.identity.after");
    if (reg_read(map, 8) & 8u) { failure = "GPU2 sticky error set"; goto done; }
    if (reg_read(map, 8) & 4u) reg_write(map, 12, 2);
    if (reg_read(map, 8) & 3u) { failure = "GPU2 is already rendering/fencing"; goto done; }
    sst_map = mmap(NULL, SIDECAR_SPAN, PROT_READ | PROT_WRITE, MAP_SHARED, fd, (off_t)base);
    if (sst_map == MAP_FAILED) { failure = "cannot map SST bridge status page"; goto done; }
    MARK("sst.first_read.before");
    if (reg_read(sst_map, 0x254) & 7u) {
        failure = "SST bridge has a sticky request/response timeout; reset hardware before capture"; goto done;
    }
    MARK("sst.first_read.after");
    pixels = (unsigned char *)malloc(FRAME_BYTES);
    if (!pixels) { failure = "snapshot allocation failed"; goto done; }
    saved_out = dup(STDOUT_FILENO); saved_error = dup(STDERR_FILENO);
    /* One producer owns the device: retain the latest capture's diagnostics
     * instead of growing a log on every continuously streamed frame. */
    log = fopen(log_path, "w");
    if (saved_out < 0 || saved_error < 0 || !log) { failure = "cannot prepare isolated Glide log"; goto done; }
    fflush(stdout); fflush(stderr);
    if (dup2(fileno(log), STDOUT_FILENO) < 0 || dup2(fileno(log), STDERR_FILENO) < 0) {
        failure = "cannot redirect Glide diagnostics"; goto done;
    }
    redirected = 1;
    {
        char address[32];
        snprintf(address, sizeof(address), "0x%08" PRIx32, base);
        setenv("DE10_VOODOO_BASE", address, 1);
        setenv("DE10_VOODOO_SPAN", "0x01000000", 1);
        setenv("DE10_ADV7513_INIT", "0", 1);
        setenv("GLIDE_X11_ENABLE", "0", 1);
        setenv("SST_FBIMEM_SIZE", "4", 1);
        setenv("SST_TMUMEM_SIZE", "4", 1);
    }
    started = now();
    if (started < 0) { failure = "monotonic clock unavailable"; goto done; }
    MARK("glide.init.before");
    grGlideInit(); initialized = 1;
    MARK("glide.init.after");
    MARK("glide.query.before");
    if (!grSstQueryHardware(&hardware)) { failure = "Glide hardware query failed"; goto done; }
    MARK("glide.query.after");
    MARK("glide.select.before");
    grSstSelect(0);
    MARK("glide.select.after");
    MARK("glide.winopen.before");
    if (!grSstWinOpen(0, GR_RESOLUTION_320x240, GR_REFRESH_60Hz,
                      GR_COLORFORMAT_ABGR, GR_ORIGIN_UPPER_LEFT, 2, 1)) {
        failure = "Glide headless window initialization failed"; goto done;
    }
    MARK("glide.winopen.after");
    MARK("init.idle.before");
    grSstIdle();
    MARK("init.idle.after");
    if (reg_read(sst_map, 0x254) & 7u) { failure = "SST bridge timed out during Glide initialization"; goto done; }
    MARK("init.fence.before");
    reg_write(map, 12, 1);
    if (wait_ready(map, timeout)) { failure = "initialization flush failed"; goto done; }
    MARK("init.fence.after");
    MARK("init.release.before");
    reg_write(map, 12, 2);
    MARK("init.release.after");
    init_seconds = now() - started;
    started = now();
    MARK("render.begin.before");
    reg_write(map, 12, 4);
    MARK("render.begin.after");
    MARK("render.configure.before");
    configure_state();
    if (no_depth_test) grDepthBufferFunction(GR_CMP_ALWAYS);
    MARK("render.configure.after");
    MARK("render.draw.before");
    if (!strcmp(scene, "triangle")) draw_triangle(40, 200, 160, 30, 280, 200, 40000, 0xffffffffu);
    else if (!strcmp(scene, "depth")) draw_depth(near_first);
    else draw_cube(angle, !strcmp(scene, "textured-cube"));
    MARK("render.draw.after");
    MARK("render.idle.before");
    grSstIdle();
    MARK("render.idle.after");
    MARK("render.fence.before");
    reg_write(map, 12, 1);
    if (wait_ready(map, timeout)) { failure = "render frame fence failed"; goto done; }
    owned_ready = 1;
    MARK("render.fence.after");
    sequence = reg_read(map, 0x20); cycles = reg_read(map, 0x24);
    busy_cycles = reg_read(map, 0x2c); hz = reg_read(map, 0x28);
    if (!hz) { failure = "GPU2 reported zero clock"; goto done; }
    copy_start = now();
    MARK("readback.lfb.before");
    if (!grLfbReadRegion(GR_BUFFER_BACKBUFFER, 0, 0, WIDTH, HEIGHT, WIDTH * 2, pixels)) {
        failure = "native LFB snapshot failed"; goto done;
    }
    MARK("readback.lfb.after");
    if (reg_read(map, 0x20) != sequence || (reg_read(map, 8) & 14u) != 4u) {
        failure = "GPU2 snapshot ownership violation"; goto done;
    }
    if (reg_read(sst_map, 0x254) & 7u) { failure = "SST bridge timed out during rendering/readback"; goto done; }
    copy_seconds = now() - copy_start;
    MARK("render.release.before");
    reg_write(map, 12, 2); owned_ready = 0;
    if (reg_read(map, 8) & 14u) { failure = "GPU2 release not acknowledged"; goto done; }
    MARK("render.release.after");
    capture_seconds = now() - started;
    /* Driver shutdown may touch registers; finish while exclusive ownership held. */
    MARK("glide.shutdown.before");
    grGlideShutdown(); initialized = 0;
    MARK("glide.shutdown.after");
    munmap(sst_map, SIDECAR_SPAN); sst_map = MAP_FAILED;
    munmap(map, SIDECAR_SPAN); map = MAP_FAILED;
    close(fd); fd = -1;
    close(lock_fd); lock_fd = -1;
    fflush(stdout); fflush(stderr);
    dup2(saved_out, STDOUT_FILENO); dup2(saved_error, STDERR_FILENO); redirected = 0;
    output = binary_stdout ? stdout : fopen(output_path, "wb");
    if (!output || fwrite(pixels, 1, FRAME_BYTES, output) != FRAME_BYTES || fflush(output)) {
        failure = "cannot write captured output"; goto done;
    }
    if (!binary_stdout) { if (fclose(output)) { output = NULL; failure = "cannot close output"; goto done; } output = NULL; }
    fprintf(stderr, "{\"source\":\"hardware\",\"renderer\":\"SpinalVoodoo\",\"scene\":\"%s\","
            "\"submission_mode\":\"%s\",\"depth_test_enabled\":%s,\"angle\":%.6f,\"depth_order\":\"%s\",\"sequence\":%" PRIu32 ",\"width\":320,\"height\":240,\"bytes\":153600,"
            "\"render_cycles\":%" PRIu32 ",\"clock_hz\":%" PRIu32 ",\"render_seconds\":%.9f,"
            "\"pipeline_busy_cycles\":%" PRIu32 ",\"copy_seconds\":%.9f,\"capture_seconds\":%.9f,\"initialization_seconds\":%.9f,"
            "\"render_timing_semantics\":\"begin-to-fence including CPU submission gaps\"}\n",
            scene, queued_primitives ? "queued" : "serialized", no_depth_test ? "false" : "true", angle, near_first ? "near-first" : "far-first", sequence, cycles, hz,
            (double)cycles / hz, busy_cycles, copy_seconds, capture_seconds, init_seconds);
    result = 0;
done:
    if (owned_ready && map != MAP_FAILED) {
        (void)progress_mark("cleanup.release.before");
        reg_write(map, 12, 2);
        (void)progress_mark("cleanup.release.after");
    }
    if (initialized) {
        (void)progress_mark("cleanup.shutdown.before");
        grGlideShutdown();
        (void)progress_mark("cleanup.shutdown.after");
    }
    if (redirected) { fflush(stdout); fflush(stderr); dup2(saved_out, STDOUT_FILENO); dup2(saved_error, STDERR_FILENO); }
    if (result) fprintf(stderr, "%s (Glide log: %s)\n", failure, log_path);
    if (output && output != stdout) fclose(output);
    if (log) fclose(log);
    if (saved_out >= 0) close(saved_out);
    if (saved_error >= 0) close(saved_error);
    if (map != MAP_FAILED) munmap(map, SIDECAR_SPAN);
    if (sst_map != MAP_FAILED) munmap(sst_map, SIDECAR_SPAN);
    if (fd >= 0) close(fd);
    if (lock_fd >= 0) close(lock_fd);
    if (progress_fd >= 0) close(progress_fd);
    free(pixels);
    return result;
bad_arguments:
    usage(argv[0]); return 2;
}
