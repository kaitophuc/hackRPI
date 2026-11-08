# Software checkpoint evidence

This snapshot accompanies the software-first checkpoint before any new RTL work.
The selected runtime bundle is
`c87b88edf247491677f28b8d97a2ebab1414654e0708e41be34139214a3401f1`.

* `visible-play.json`: latest 30.984-second active interval, 504 canvas ACKs,
  **16.266 displayed FPS**, fresh Arduino input throughout. Browser identifiers
  are anonymized and raw sensor measurements are omitted. Timing, frame counters,
  visibility and freshness are retained; the original recording hash is included.
* `depth-deployed-validation.json` and the two `.txt` test outputs: 360 queued
  frame comparisons against 28 pre-change FPGA references, with no added errors.
* `depth-bypass-summary.json` and `pixel-cost-summary.json`: controlled software
  A/B/A results and the separate pixel-workload diagnostic.
* `cpu-vs-existing-gpu.json`: the unresolved original CPU/FPGA image differences.
* `vertex-*.json`: the direct-storage prototype's limited throughput gain; this
  prototype was not selected for the running game.
* `depth-selected-manifest.json`, `final-state.json` and
  `software-completion-audit.json`: selected-build provenance and unmet gates.
* `rtl-readiness-precheck.json`: read-only source/tool checks; no new RTL build
  or programming was performed.

The **27 FPS minimum remains unmet**. A controlled sample's completed FPS is
not displayed FPS. Full explanations are in the [software audit](../../SOFTWARE_PROFILE.md).

Compiled outputs, full raw captures, phase-specific rollback archives and tool
caches remain in the ignored local `build/` directories. Source-file hashes in
historical manifests describe the original working-tree bytes; Git may normalize
text line endings. The imported hardware/patch files retain their exact bytes.
