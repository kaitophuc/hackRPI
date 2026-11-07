#ifndef FLIGHTING_BRIDGE_H
#define FLIGHTING_BRIDGE_H
#include <stdint.h>
#ifdef _WIN32
#define FG_EXPORT __declspec(dllexport)
#else
#define FG_EXPORT __attribute__((visibility("default")))
#endif
#ifdef __cplusplus
extern "C" {
#endif
/* ABI 1. C calling convention. All operations run on the context's owner thread.
 * Return 0 on success, -1 invalid arguments, -2 unsupported, -3 graphics error,
 * -4 platform/context error, -5 allocation failure. Errors are never ignored.
 * Every buffer remains owned by its caller and is valid only during the call.
 */
FG_EXPORT int fg_abi_version(void);
FG_EXPORT int fg_open(int width,int height);
FG_EXPORT const char *fg_backend_name(void);
FG_EXPORT int fg_upload(int id,int width,int height,const uint8_t *rgba_top_down);
FG_EXPORT int fg_begin(uint32_t clear_argb);
/* Vertex stride = 9 floats: clip x,y,z,w; color r,g,b; u,v.
 * Texture 0 disables texturing; positive IDs refer to fg_upload.
 * Depth=true means LESS, depth writes on. Cull=true means CCW front/BACK cull.
 * HUD depth=false means no depth writes. Triangles only. No blending.
 */
FG_EXPORT int fg_draw(const float *vertices,int vertex_count,const int32_t *indices,
                     int index_count,int texture,int depth,int cull,int wire);
/* Complete rendering; output opaque RGBA8, rows top to bottom.
 * Completion/readback is not a GPU timer. No platform present occurs here. */
FG_EXPORT int fg_end(uint8_t *rgba_top_down,int byte_count);
/* Separate frame-delivery timing boundary. */
FG_EXPORT int fg_present(const uint8_t *rgba_top_down,int byte_count);
FG_EXPORT void fg_close(void);

/* REQUIRED GPU-TEAM HOST HOOKS. Do not bind these to a desktop GL driver when
 * claiming RasterIX validation. The host must establish the selected RasterIX
 * software or board context and identify the exact revision/configuration.
 */
int fg_platform_open(int width,int height);
void *fg_platform_get_proc(const char *name);
const char *fg_platform_backend_name(void);
int fg_platform_present(const uint8_t *rgba_top_down,int width,int height);
void fg_platform_close(void);
#ifdef __cplusplus
}
#endif
#endif
