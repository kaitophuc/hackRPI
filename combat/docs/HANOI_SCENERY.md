# Hanoi scenery — circa 1972

An original, deliberately simple interpretation of wartime Hanoi, built from opaque colored triangles. The map compresses distances and simplifies streets, buildings and landmark proportions for the existing flight game. It is not a surveyed reconstruction, an exact account of a particular air raid, or a modern city model.

## Essential visual cues

- **Hoan Kiem Lake and Turtle Tower:** green water, a small island and a light-colored three-tier tower with dark arch openings.
- **Ngoc Son and The Huc:** a small tiled-roof temple island and red arched footbridge near the lake's northeast edge.
- **Old Quarter-inspired neighbourhoods:** low-rise ochre/plaster tube houses, pitched terracotta roofs, simple shop openings, narrow streets and a few trees.
- **Red River and Long Bien Bridge:** muddy river water, sandy banks, a long steel railway bridge with repeating trusses, rails and stone piers. A simplified patched span is a general wartime cue.
- **Period atmosphere:** scattered tubular street shelters, a few roofless buildings and small rail-side crater marks; a muted sky and an explicit “HANOI / CIRCA 1972” location caption. No modern high-rise skyline is included.

The scenery is kept quiet and low-detail: there are no crowds, moving vehicles, active bombing effects or additional ground weapons. The existing WWII-inspired player/enemy aircraft remain as previously requested; their presence is an intentional game-art combination, not a claim about aircraft deployed over Hanoi in 1972.

## Reference basis

The following references informed shapes and period selection. The mesh, colors, layout and previews are original; no photographs or third-party art were imported.

1. [Hanoi Department of Culture and Sports: Hoan Kiem Lake and Ngoc Son Temple](https://sovhtt.hanoi.gov.vn/en/hoan-kiem-lake-ngoc-son-temple-special-national-monuments-famous-scenic-spots-capital/) identifies the lake, temple complex, island and The Huc Bridge.
2. [Vietnam National Authority of Tourism: Explore the Old Quarter](https://vietnam.travel/things-to-do/explore-old-quarter-your-way/) provides context for the historic quarter and the lake's associated landmarks. Contemporary tourism amenities are not modeled.
3. [Hanoi Department of Culture and Sports: Long Bien Bridge](https://sovhtt.hanoi.gov.vn/en/long-bien-bridge-symbol-historical-cultural-values-hanoi/) describes the bridge's rail/road significance and wartime damage during 1965–1972. The damaged span here is illustrative, not a dated engineering reconstruction.
4. [TIME, 23 October 1972: Living Inside a Bull's Eye](https://time.com/archive/6815755/north-viet-nam-living-inside-a-bulls-eye/) is a contemporary report describing individual tubular bomb shelters along Hanoi streets. This informs the small roadside shelter details.

## Implementation and limits

`src/HanoiCity.cs` holds one cached 1760 × 1980 metre sequence containing the same low-relief city, countryside and landmarks. New games divide it into nine 220 metre sections and recycle those sections through an 11-slot forward corridor. The plane is anchored at a constant depth, the camera stays fixed, and tilt moves the plane sideways/up/down. HP, enemy AI, firing, game over and restart remain.

Sections scroll toward and past the camera, then the pool reuses the cached sequence ahead. Only visible chunks are submitted, using conservative sphere/frustum culling and near-to-far ordering. Identical vertices share indices. `--complexity 4..48` selects one of three cached density variants; revisiting a variant does not rebuild it. No shaders, alpha blending, external textures, or new graphics API features are used.

Sequence dimensions are whole 55 metre terrain periods, with matching edge vertices. Terrain queries subtract the same scrolling phase used by the section pool. Source meshes always use unscrolled height, so first-render timing cannot deform the cached sequence. Existing enemies, projectiles and bursts are shifted into the new local frame before combat is stepped; swept collision endpoints share that frame. Distance grows separately while visible coordinates and pool size stay bounded. See [PERFORMANCE.md](PERFORMANCE.md).

The terrain height query is shared by rendering, ground clearance and projectile-ground checks. Streets and water remain low-relief; buildings and landmark structures are visual scenery and do not add building-collision damage or destructible terrain. Flying through a building is still possible at low altitude. Changing that would be a separate gameplay feature.

## Determinism and old recordings

New format-6 recordings select the endless forward run and preserve its distance, input sequence and seeded combat. Format 5 retains the repeating-map free flight; format 4 retains fixed Hanoi. Versions 1/2 retain their original terrain and combat-free flight; version 3 retains earlier terrain plus combat. Captures include an `Environment` label, runner state and frozen geometry. Older recordings keep their original movement model.

## Preview artifacts

- `captures/hanoi-desktop.png`: actual desktop host rendering with its unchanged chase camera.
- `captures/hanoi-overview.png`: scenery inspection overview.
- `captures/hanoi-lake.png`: lake, Turtle Tower, temple and red bridge inspection.
- `captures/hanoi-bridge.png`: Long Bien / Red River inspection.

Inspection cameras are used only to create preview images; the in-game camera is unchanged. The environment and extra city geometry are desktop-tested. RasterIX, ARM and FPGA execution remain untested as documented in `VALIDATION.md`.
