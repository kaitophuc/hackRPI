# Attribution and source boundaries

Candidate upstream repositories and immutable revisions are recorded in
`dependencies.lock.json`. Fetch with `scripts/fetch-deps.ps1 -AllCandidates`.
They are kept under `third_party/`; preserve each project's license and all
embedded notices. The selected SpinalVoodoo core is integrated into the
accepted Standard board bitstream; its generated RTL and integration patch
are included here. Build caches and upstream checkouts remain excluded.

* RasterIX by ToNi3141: GPL-3.0-or-later, evaluated fallback. Tests compile its Rasterizer and
  TestFunc directly, without copying/modifying those modules. Float is pinned
  at 83485654e380392a726ee67f8e5d2f4f8f73dd32. Bundled AXI/AXIS and other
  sources retain their own notices. The root upstream LICENSE is available in
  `third_party/RasterIX/LICENSE` after fetching.
* SpinalVoodoo by fayalalebrun: integrated 3D source.
  CERN-OHL-W-2.0 repository license; its Glide/software dependencies have
  separate notices that must be retained and reviewed for distribution.
  Copies of the upstream repository and Glide licenses are in `licenses/`.
* GlandaGPU by stiangglanda: evaluated only. No root license was found; no
  GlandaGPU HDL was incorporated in this platform.
* Standard GHRD board shell, constraints and HPS system: local source
  `D:/hardwareaccel/quartus/DE10_Standard_AI`, originally Terasic/Altera.
  Original notices remain in the files. `hardware/source-provenance.json`
  records the copied source hashes. Do not replace these notices with a
  blanket license for newly written code. Generated Intel IP is governed by
  its vendor license and is regenerated using the installed Quartus tools.

Original platform code is provided under the MIT terms below. This does not
relicense upstream components or assert compatibility of a future combined
distribution; preserve GPL/CERN/vendor obligations when integrating those cores.

Copyright (c) 2026 GPU platform contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
