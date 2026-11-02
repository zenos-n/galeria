# Timeline animation measurements

Controlled native GTK4 4.22.4 / libadwaita 1.9.3 / Python 3.13.15 run: 40 placeholder tiles, 1280×820 window, Xvfb with software GL, 18 frame-driven All Photos / Months / Years transitions. Three repetitions per variant, cProfile enabled in each run. This is not a measurement of the user's desktop compositor.

| Variant | Target-layout CPU, ms (three runs) | Median | Decision |
| --- | --- | --- | --- |
| Baseline | 55.96 / 48.98 / 49.33 | 49.33 | Repeated geometry calculation found |
| Cache target geometry by width, mode, expanded groups, density and query | 4.24 / 4.20 / 4.99 | 4.24 | Kept: ~91% less target-layout CPU |

Frame-time median and p95 were 16.67 ms before and after; the controlled run did not reproduce a sustained frame-rate drop. Total allocation CPU moved from a median 272.63 ms to 262.41 ms, too small/noisy to claim as an end-user speedup. The measured win above concerns the repeated calculation specifically.

Evidence and exact harness: `/tmp/gallery-app-identification/bench-tiers.py`, `tiers-baseline*.json`, `tiers-cache-*.json`. Every run used the same GTK runtime, renderer, display and sequence. Cache inputs include every layout-affecting value; visual selection state does not change target geometry.

Second isolated change: allocate animated child widgets at stable endpoint sizes and move/scale their render transforms rather than relaying out each button at every intermediate size. The same three-run sequence measured allocation CPU at 249.72 / 247.58 / 249.11 ms (median 249.11), versus 252.10 / 262.41 / 262.60 ms (median 262.41) with caching alone. Kept: ~5% lower allocation CPU and non-overlapping run ranges; target-layout lookup cost rose slightly (median 6.13 ms). Frame median/p95 remained 16.67 ms. This is a modest controlled CPU reduction, not a demonstrated desktop FPS improvement. Evidence: `tiers-stable-*.json`. Geometry and crop tests remain green.

## Real media decoding and cache, Gallery 0.3

The packaged 0.2 decoder failed both real WebP and AVIF fixtures with `Unrecognized image file format`; JPEG worked. The runtime's GdkPixbuf format inventory had no WebP/AVIF loader. Pillow decoding on image workers now passes all three formats, including orientation and bounded-size RGBA output. PNG-only fixtures had missed this failure.

Controlled cache benchmark: 40 WebP images through an authenticated loopback HTTP fixture with 15 ms response delay, each decoded identically, three repetitions. Warm runs construct a new client, so reuse comes from disk rather than the old client/texture map.

| Variant | ms, three runs | Median | Image HTTP requests |
| --- | --- | --- | --- |
| Uncached | 679.2 / 657.9 / 657.9 | 657.9 | 40 |
| New cache, cold | 682.5 / 671.3 / 674.4 | 674.4 | 40 |
| New cache, warm, new client | 27.5 / 27.4 / 27.8 | 27.5 | 0 |

Kept: warm reuse removes the network requests and beats run-to-run variance. Cold writes add about 16.5 ms in this fixture. These numbers are not a measurement of the user's Immich server. Harness/log: `/tmp/gallery-app-identification/bench-cache-v3.py` and `bench-cache-v3.log`. A regression test verifies a new client does not refetch an unchanged image; another verifies concurrent misses fetch once.

Cache keys include server, account, asset ID, revision and image size. Ordinary media has a 512 MB disk budget and 256-texture memory limit; search/album metadata expires after 30 seconds and Refresh bypasses it. Locked media uses a separate authenticated encrypted store; it never enters the ordinary store. Unlock clears ordinary cached copies to remove potentially stale copies of media moved into the locked folder outside Gallery. Original encrypted device copies are retained separately rather than evicted as thumbnails. Local image keys include file path, modification nanoseconds and size.

The native 150-item fixture also checks that initial image requests stay below a full page, scrolling appends the second page without resetting position, and viewer previews use a separate worker queue. Production latency still requires user verification after signing in.
