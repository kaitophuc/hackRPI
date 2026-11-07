# FG-CONTRACT-1-PROPOSED

Status: **proposal, not agreed**. No GPU-team contact or authority to send messages was supplied. This document makes the required discussion concrete while desktop development proceeds.

## Sign-off checklist

| Owner / decision | Status |
| --- | --- |
| GPU team contact and approval | Pending |
| RasterIX repository commit and software/RTL/FPGA configuration | Pending |
| ARM architecture, OS, ABI, toolchain, RAM and framebuffer budget | Pending |
| Software RasterIX context/bus connector and frame readback | Pending |
| Board display/streaming delivery and timing hooks | Pending |
| Browser input session/timebase/reconnect adapter | Pending |
| Formats, filtering, culling, depth, clipping and HUD subset below | Proposed; desktop implemented |
| Resolution, geometry and texture limits below | Software guardrails; FPGA budgets unverified |

The initial target is deliberately narrow. Change this versioned contract and its validation matrix before adding a feature. Desktop success is evidence only for that desktop implementation. In particular, the proposed GL entry points and enumerants must be checked against the chosen RasterIX revision.

## Rendering interface

`IRenderer.Render(Frame)` receives a complete frame and returns opaque ARGB32 pixels for the desktop host. The native ABI uses RGBA8 bytes. Native bridge ABI 1 is in `native/flighting_bridge.h`. Gameplay only constructs frames; it does not call GL, WinForms, platform transport, or RasterIX directly.

| Property | Definition |
| --- | --- |
| World | Right-handed, metres, +Y up; default aircraft travels toward −Z |
| Camera | Right-handed look-at, 60° vertical field of view, aspect = framebuffer width/height |
| Projection | Homogeneous clip volume −w≤x,y,z≤w; visible w>0; near 0.2 m, far 2000 m (terrain 1800 m) |
| Geometry | Indexed triangle lists; 9 float native vertex stride: clip XYZW, RGB, UV |
| Winding | CCW front in bottom-left screen/clip XY; BACK culling selectable per draw |
| Depth | Cleared to 1; LESS; writes enabled for 3D; overlay test and writes disabled |
| Color | Opaque linear numeric RGB values [0,1], no gamma conversion; RGB interpolated perspective-correctly |
| Texture | One texture per draw, opaque RGBA8 upload, power-of-two dimensions 1–256; NEAREST min/mag; CLAMP_TO_EDGE; MODULATE RGB |
| UV origin | (0,0) bottom left; upload/capture byte rows run top to bottom; GL glue flips uploads |
| Output | Top-left pixel origin, rows top to bottom; opaque pixels; compare quantization with tolerance |
| HUD | Opaque triangles in clip coordinates, no depth test/write/cull; submitted last; logical 640×400, +X right/+Y down |
| Limits | Resolution 64–1920 × 64–1080; 250,000 submitted triangles, 4096 draw calls, 255 named textures, 4 MiB logical RGBA texture storage per frame |
| Debug | Software wireframe only; native bridge returns unsupported for wireframe |

No blending, alpha tests, programmable shaders, framebuffer effects, fog, dynamic lighting, multitexture, mipmaps, anisotropy or texture compression. Unknown backend/options, missing resources, invalid textures and failed native calls produce errors. C# models only these exposed states; there is no generic GL escape hatch in gameplay.

GL glue uses `glViewport`, `glMatrixMode`, `glLoadIdentity`, `glEnable`, `glDisable`, `glDepthFunc`, `glDepthMask`, `glFrontFace`, `glCullFace`, `glClearColor`, `glClear`, `glGenTextures`, `glDeleteTextures`, `glBindTexture`, `glTexParameteri`, `glTexEnvi`, `glPixelStorei`, `glTexImage2D`, `glBegin(GL_TRIANGLES)`, `glEnd`, `glColor3f`, `glTexCoord2f`, `glVertex4f`, `glFinish`, `glReadPixels` and `glGetError`. It explicitly disables blending, lighting, alpha testing and fog in a fresh, dedicated context. Default depth clear value/range must remain 1 / [0,1]. Readback is part of the validation path, not a performance-optimized board presentation path.

The GPU team must approve every call/enum, especially RGBA8 conversion, clamp-to-edge, perspective interpolation and framebuffer readback. If its transport cannot expose the GL path, implement the same C ABI against the selected RasterIX command interface and preserve scene semantics.

## Input interface v1

`InputState` is platform-independent. The Windows host maps keys into it. The included loopback UDP receiver is an integration entry point for the GPU team's browser adapter; it is not a browser or network authentication service.

Send UTF-8 JSON, at most 2048 bytes, one complete snapshot per UDP datagram, ideally at 60 Hz with heartbeats even when controls do not change:

```json
{"version":1,"session":"demo-1","sequence":120,"sender_ms":2000,"pitch":0.1,"roll":0,"yaw":0,"throttle":0.55,"buttons":0,"focused":true,"connected":true}
```

| Field | Definition |
| --- | --- |
| version | Integer 1 |
| session | Nonempty connection/session ID, ≤64 characters |
| sequence | Nonnegative signed 64-bit integer; strictly increasing within session |
| sender_ms | Nonnegative signed 64-bit integer, sender monotonic milliseconds; nondecreasing |
| pitch | −1..1; positive climbs |
| roll | −1..1; positive raises right wing / banks left |
| yaw | −1..1; positive turns right |
| vertical | Optional −1..1; positive moves upward in world space, negative downward; default 0 preserves legacy flight |
| throttle | 0..1; absolute desired throttle |
| buttons | Unsigned bitmask; bit 0 airbrake (1), bit 1 boost (2), bit 2 held fire (4), bit 3 restart after game over (8); all other bits rejected |
| focused, connected | Both true to simulate; false immediately clears held controls and pauses |

Reject NaN/infinity, out-of-range axes, invalid schema values, duplicate/out-of-order sequence numbers, backward timestamps and session changes without an explicit reset. The receiver uses its local monotonic clock: after 500 ms without accepted input it returns all-zero axes/buttons/throttle, focused=false and connected=false, pausing simulation. Input delayed more than 500 ms relative to the session's initial sender/receiver clock anchor is also rejected.

The first packet establishes that clock anchor; its absolute age cannot be inferred from unsynchronized clocks. The browser/platform adapter must flush queued packets on connection, authenticate the session where applicable, and preserve a trustworthy sender monotonic clock. Long-running clock drift/re-anchoring policy needs GPU-team agreement. The sample UDP host locks the first session ID until process restart; an embedded host can explicitly call `InputGate.Reset()` on an authenticated reconnect. It does not accept an arbitrary new session while controls are active.

The UDP socket binds **127.0.0.1 only**. Browser events go through the team's existing platform service to this local adapter; no remote listener or browser-input server is silently introduced. At most 64 queued packets are drained each rendered frame to bound input processing. The platform adapter should validate `assets/input.schema.json`; the built-in decoder requires the specified members and validates their types/ranges, but ignores extra JSON member names for forward compatibility.

Pause and single-step are host debug commands outside the flight-control packet. Board debug commands may use the team's own control channel. Desktop single step executes exactly one 1/60 s tick. The portable API is `Session.Step(InputState)` for board debugging. Bit 2 fires while held; bit 3 is only consumed at game over to reset the round. The browser adapter must explicitly support these proposed new bits before board combat is claimed as tested.

In format-6 endless-run sessions, `roll` is a leftward dodge command and `pitch` an upward dodge command. The legacy `yaw` field supplies an additional rightward dodge command; `vertical` supplies additional upward movement. Combined axes are clamped and normalized. The plane stays at local Z=130, X within ±16 metres and Y within 46–62 metres. Smoothed bank/pitch is visual; heading stays forward and the camera is fixed. W/S and A/D map to vertical/horizontal dodge, while Page Up/Down controls automatic forward speed. Formats 1–5 retain the earlier free-flight interpretation and camera. The input packet schema and button bits are unchanged.

## Time and simulation

Fixed 60 Hz simulation, at most 5 catch-up steps per rendered iteration. Incoming elapsed time is capped at 250 ms; surplus full steps beyond five are discarded and counted as dropped wall time. Physics never receives variable render or stream dt. Pausing clears the accumulator. Local inputs are sampled per rendered iteration; replay records the actual control snapshot consumed at each simulation tick.

The world seed defaults to 1337. New recordings use `FLIGHTING_REPLAY,6,<seed>,60`, followed by contiguous tick, pitch, roll, yaw, throttle, buttons and vertical records. Format 6 selects the fixed-camera endless run: distance advances a pool of 11 cached section instances drawn from one nine-section Hanoi sequence. Aircraft and combat actors remain in a local scrolling frame; source geometry and terrain queries share the same periodic phase. Format 5 retains the prior repeating-map free flight; format 4 retains fixed Hanoi; format 3 retains the original terrain and combat; formats 1/2 retain combat-free flight. Formats 1–4 retain their original terrain interpolation. Same-runtime replay reproduces distance, dodge velocities, aircraft and combat state; cross-runtime floating-point tolerances still require review.

Combat uses the same fixed step, specified xorshift32 PRNG, four-fighter/192-projectile/16-burst limits, 100 player HP, 5–10 incoming damage and one-hit enemies. Existing actors and the previous player position are first converted to the new scrolling frame; newly spawned actors are not shifted twice. Swept collision, velocity inheritance and enemy leading then use that consistent frame. Game over freezes distance and combat. Restart resets distance, pool phase, dodge velocities, RNG, timers, actors, score and HP. Rendering remains opaque triangles through the existing interface.
