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

## Gallery 0.4 loading window and video path

Thumbnail requests now cover the visible viewport plus two viewport heights above and below. Nearby videos use a separate two-worker queue to preload at most 2 MiB per video into the existing account cache (encrypted for locked media). Viewer playback streams subsequent byte ranges instead of waiting for a whole download. The range fixture verifies that an in-prefix seek causes zero additional upstream requests and a full read reuses the prefix before requesting the remaining range. These are request-count/behavior checks, not production latency or memory benchmarks.

The packaged GTK 4.22.4 disables its GStreamer media backend, which explains the nonfunctional Gtk.Video path. Gallery 0.4 instead packages Clapper 0.10.0/ClapperGtk with GStreamer 1.26.11 and its playback plugins. Native generated-MP4 playback reached position 0.6 seconds and hid the loading spinner. This verifies the installed playback pipeline, not every codec in a user's library.

## Galeria 0.7 date views and visited pages

Date covers now request four assets for each date card within the two-screen
loading window, independently of the paginated all-photos results. Decoded date
covers (96cards), collection thumbnails (256), grid textures (768), and24visited
query results have bounded in-memory caches. Lock/sign-out/account changes clear
those caches. Re-entering a cached query issues no initial media request; active
views check remote changes every15seconds without hiding cached content.

Native synthetic checks verified30date buckets/600photos, unloaded month covers,
opening-animation intermediate frames despite a40ms data response, cached base
view reuse after a folder query, stack closure on tier changes, a successful
Trash thumbnail flight/reflow, and a new simulated phone upload appearing after
an automatic refresh. No production assets were mutated.

Tier motion matches source asset IDs with individual folder-cover quadrants.
Per-frame drawing clips to the viewport; allocation retains two screens above
and below. Animated tile imagery uses its existing texture directly, avoiding
layout of each tile widget during the tier motion. The controlled1200-image,
60-month comparison uses software GL and measures CPU allocation/snapshot time,
not production GPU frame rate; logs are /tmp/gallery-app-identification/bench-tier-{before,after}.log.

## Galeria0.8 indexed lightweight cells

The0.7 implementation still constructed a full button/overlay/picture/check tree
for every item and allowed queued image work to outlive the viewport. The new
cells create native children only in the two-screen allocation band. A10000-slot
native fixture had90live button trees after a jump to an older month, a280450px
scroll extent and no full-media search requests; recent thumbnail requests
followed that older month. Compact metadata loaded separately. A read-only
Immich3.3.3 check decoded27compact entries with valid ratios in0.232s without any
thumbnail requests. That sample is not a throughput estimate for the full library.

The same1200-photo softwareGL tier benchmark now reports allocation median1.19,
p953.24,max29.03ms; snapshot median0.75,p951.29,max21.05ms. Typical passes are
smaller than0.7, but first-layout/outlier stalls remain and no guaranteed production
frame rate is claimed. Sources/logs: /tmp/gallery-app-identification/indexed-native.py,
indexed-native.log, bench-tier-08.log. Header/sync/locked/hover and video editor
native checks pass with fatal GTK criticals;49Python tests cover compact parsing,
full placeholder range, grouped month→year destinations, dynamic job priority,
folder-album mapping/depth, and cache invalidation during in-flight writes.


## Galeria 0.8.1: profiling the real 44,854-item library

The 0.8 synthetic pass missed the user's live regression. Read-only desktop
traces used Python 3.14.7, PyGObject 3.56.3, GTK 4.22.4, Adwaita 1.9.3 and
GskVulkanRenderer on DP-2. No production media was changed.

* Disk pruning rescanned and sorted the entire cache after every write. A
  controlled fixture with 3,000 existing entries and 100 writes took
  2.9365 / 2.9411 / 2.9612 seconds and 610,100 Path.stat calls per run.
  An in-memory eviction heap took 0.0156 / 0.0162 / 0.0145 seconds and 100
  Path.stat calls, plus one initial scandir inventory. Kept. Other writers are
  reconciled every 30 seconds; a single writer enforces its budget immediately.
* Hover and selection updates now touch active cells; checks derive visibility
  from selection/hover state. Unallocated cells have no GTK parent, so hidden
  entries do not remain in the native child traversal. Cached per-month rows
  survive other months' metadata updates.
* Animation planning gathers visible photos instead of building 44,854 sprite
  records and discarding most afterward. In the same unprofiled live sequence,
  gathering photos fell from p95 83.10 ms to 1.08 / 1.13 ms. Group clips retain
  actual source IDs and final folder-cover bounds.
* A remaining visibility-index rebuild walked every stored rectangle whenever
  metadata arrived. The final layout retains complete row heights and month
  extents, but materializes rectangles only around the current scroll band.
  Select All still includes loaded matching media outside that band. Offline
  native checks compare the full scroll height with uncropped justified rows,
  bound native parentage/rendered rectangles, jump to old dates and verify
  viewport-prioritized downloads and grouped year transitions.

The same live sequence (12 tier switches, then 120 scroll increments) measured:

| Unprofiled Vulkan run | Allocation p95 | Tier frame interval p95 | Scroll frame interval p95 |
| --- | ---: | ---: | ---: |
| Before viewport-bounded rectangle construction | 37.18 ms | 33.34 ms | 116.38 ms |
| Final, first run | 8.20 ms | 17.04 ms | 33.32 ms |
| Final, repeated | 7.23 ms | 17.13 ms | 16.79 ms |

These are frame-clock intervals, not GPU presentation timestamps. The first
layout still has a roughly 74–82 ms outlier; no guaranteed frame rate under
other GPU/game loads is claimed. Network/cache state varies between live runs.
The deterministic cache benchmark and bounded native geometry checks supplement
the desktop comparison. An OpenGL renderer experiment was slower (scroll p95
283.66 ms); no renderer override ships.

Evidence: /tmp/gallery-app-identification/bench-cache.py, live-timed-indexfix.json,
live-timed-windowgeometry{,-repeat}.json and live-timed-gl-layoutfix.json.
Run the offline native regression with the packaged GI environment on a private
display: `G_DEBUG=fatal-criticals python3 checks/timeline_native.py`.


## Galeria 0.9: sustained scrolling and abandoned image work

The user reported a scrolling freeze after the 0.8.1 short-run measurements.
Longer 3,600-step runs reproduced 1.2–4.5 second frame gaps. The installed
catalog runtime is Python 3.13.15 (GTK 4.22.4, PyGObject 3.56.3, Adwaita 1.9.3),
whereas the separate upstream development flake used Python 3.14.7. Tests and
native checks were repeated in the actual catalog environment.

The pending image queue repeatedly ranked every abandoned job while draining
stale work one future at a time. With 5,000 abandoned jobs and one visible job,
three controlled runs took 1.7589 / 1.7123 / 1.6888 seconds, evaluating priorities
12,507,500 times each. A missing viewport priority now explicitly marks abandoned
work; one ranking pass retires those futures together without running their
loaders. The same fixture took 0.0167 / 0.0118 / 0.0111 seconds and 5,000 priority
evaluations. Completion callbacks still clear pending-image/cover bookkeeping.
Kept, with a deterministic regression test for linear priority evaluation.

Two subsequent runs each used a new private empty thumbnail cache, the actual
catalog Python/GI environment, the real 44,855-item read-only library on DP-2,
and the same 3,600-step forward/reverse/old-date-jump sequence. Their frame-clock
median was 16.67ms; p95 was16.75 /29.82ms; max148.74 /134.02ms. No multi-second
scrolling gap appeared. Pending queues peaked at509 /574 jobs. This is evidence
for the queue fix, not proof that every possible unresponsive-window failure is
resolved. Initial model/widget construction still pauses for roughly0.7seconds
before initial media display; it is outside the scrolling phase.

Experiments not shipped: skipping unchanged native cell allocation caused GTK
allocation warnings; retaining cached allocation arguments still did not remove
the long stalls, so the entire allocation-reuse experiment was reverted.
Suppressing repeated cover opacity calls alone did not fix them either and was
reverted. GC instrumentation measured25–55ms collections, insufficient to explain
the multi-second stalls. A native-call/system-call trace perturbed timing and did
not reproduce the long pause; it is not used as an after-fix performance claim.
No renderer, scheduler, kernel, game or monitor configuration changes ship.

The native regression now also checks the year rail's standard Gtk.Scrollbar,
top/bottom mapping, hidden hint at rest, and hint visibility during hover/hold.
All53unit tests plus native layout, cache/refresh/Trash/stack and rail checks pass.
Evidence: /tmp/gallery-app-identification/bench-stale.py,
freeze-queuefix{,-repeat}-events.jsonl, tests-09-final.log and native-09-final.log.


## Galeria 0.9.1 scrollbar interaction correction

The first 0.9 rail was a standalone scrollbar beside the grid, so it reserved
content width and never acquired the native overlay indicator states. Its
legacy event callback also received a null GdkEvent on the live Wayland backend,
preventing drag tracking. The rail now sits in a non-measuring Gtk.Overlay and
uses native overlay-indicator/hovering/dragging CSS states. Tick marks are visible
only while engaged. Captured click/unpaired-release gestures track held state
without relying on that event object; parent motion observes the actual cursor
coordinates even while dragging outside the narrow rail. The hint is anchored to
those coordinates and presented again when it moves.

A private Xvfb real-XTest pointer check (not direct method calls) verifies full
content width, collapsed/expanded track states, hidden ticks at rest, visible
ticks on hover/hold, popup position following cursor movement, native thumb drag,
tracking outside the rail and release outside returning to the collapsed state.
The native bar allocation changes21→25px with these theme metrics; screenshots
confirm the visual indicator goes from narrow to expanded. Full grid width stays
unchanged. The 10,000-slot date/priority/group test and existing cache/refresh/
Trash/stack native checks also pass with fatal GTK warnings. All53unit tests pass.
Run `checks/scrollbar_native.py` only on private DISPLAY=:91, with xdotool available
or GALERIA_XDOTOOL set. Optional GALERIA_CHECK_SHOTS writes synthetic screenshots.

## Galeria 0.10 cache-first startup and input follow-up

A native private-Xvfb integration fixture blocks session validation and confirms
that a fresh process restores all eight cached thumbnails before that HTTP call
returns, never enters the loading status page, and retains the same mosaic after
validation. A separate real-client test ages disk snapshots beyond their normal
TTL and verifies startup restoration makes zero HTTP or unlock requests. These
are behavior/request-count checks, not claims about startup latency on every
library. Startup decodes only the initial three screens; ordinary disk/RAM
budgets and locked-media separation remain intact.

The 0.9.1 GtkPopover hint still owned a native input surface despite can_target
being false. Replaced it with non-targetable widgets in the existing overlay.
The real-XTest check now enters the actual hint during a held thumb drag, then
continues moving inside it and verifies scrolling continues. No physical
Wayland input automation is claimed. The Clapper 0.10 stylesheet applied popup
backgrounds to every arrow, including modelbutton submenu chevrons; the scoped
application rule clears only those chevrons. A native video-menu screenshot
confirms the correction.

All60unit tests pass on Python3.13.15/PyGObject3.56.3/GTK4.22.4/Adwaita1.9.3.
The native integration also verifies profile photo loading/change, single Save
As and bulk chosen-folder exports, month selection scopes and sidebar sync
status. Tests use generated files and loopback/fake accounts; no production
profile, original, sync service or media mutation is performed. Existing indexed
10,000-slot and cache/refresh/Trash/stack regressions remain part of validation.
