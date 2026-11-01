# Timeline animation measurements

Controlled native GTK4 4.22.4 / libadwaita 1.9.3 / Python 3.13.15 run: 40 placeholder tiles, 1280×820 window, Xvfb with software GL, 18 frame-driven All Photos / Months / Years transitions. Three repetitions per variant, cProfile enabled in each run. This is not a measurement of the user's desktop compositor.

| Variant | Target-layout CPU, ms (three runs) | Median | Decision |
| --- | --- | --- | --- |
| Baseline | 55.96 / 48.98 / 49.33 | 49.33 | Repeated geometry calculation found |
| Cache target geometry by width, mode, expanded groups, density and query | 4.24 / 4.20 / 4.99 | 4.24 | Kept: ~91% less target-layout CPU |

Frame-time median and p95 were 16.67 ms before and after; the controlled run did not reproduce a sustained frame-rate drop. Total allocation CPU moved from a median 272.63 ms to 262.41 ms, too small/noisy to claim as an end-user speedup. The measured win above concerns the repeated calculation specifically.

Evidence and exact harness: `/tmp/gallery-app-identification/bench-tiers.py`, `tiers-baseline*.json`, `tiers-cache-*.json`. Every run used the same GTK runtime, renderer, display and sequence. Cache inputs include every layout-affecting value; visual selection state does not change target geometry.

Second isolated change: allocate animated child widgets at stable endpoint sizes and move/scale their render transforms rather than relaying out each button at every intermediate size. The same three-run sequence measured allocation CPU at 249.72 / 247.58 / 249.11 ms (median 249.11), versus 252.10 / 262.41 / 262.60 ms (median 262.41) with caching alone. Kept: ~5% lower allocation CPU and non-overlapping run ranges; target-layout lookup cost rose slightly (median 6.13 ms). Frame median/p95 remained 16.67 ms. This is a modest controlled CPU reduction, not a demonstrated desktop FPS improvement. Evidence: `tiers-stable-*.json`. Geometry and crop tests remain green.
