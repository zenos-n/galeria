# Shutdown checkpoint — 2026-11-02

Project directory: `/Users/doromiert/Projects/gallery`.

The user requested finishing the immediate batch, coordinating with the other active Codex session, and powering off. No new feature scope should start as part of this checkpoint.

Completed in this batch:

- Current Immich structured metadata filters; Trash uses `trashedAt`, album contents use paginated asset search rather than the metadata-only album response.
- Complete month/year bucket catalog before media search, and date-range queries when opening older folders.
- Opaque media during the grid/viewer morph, background click dismissal, native Clapper playback/loading controls, authenticated range forwarding and bounded video-prefix preloading.
- Header search toggle/Escape, narrower filter popover, signed-in account menu/sign-out, administrator-only menu entry.
- Sidebar disclosure on the right, reduced left inset, thumbnail prefetch within two screens above/below.
- Upload-only folder sync UI and packaged user service, recursion/depth controls, album destinations, checksum deduplication and persistent journal. Originals and deletions are never mirrored. The service is opt-in and was not activated against a real account during development.

Verification: 29 unit/integration tests; native GTK fixture checks for complete date catalog, header search, filter width, account menu, administrator visibility and sync dialog. Actual generated MP4 playback reached a playing position with spinner hidden. HTTP fixture checks authenticated ranges, cached prefix reuse, HEAD, and access revocation. Multipart upload fixture confirms original bytes remain untouched. Nix package builds successfully.

Remaining requested work:

- Redesign Albums, People, Tags and duplicate review layouts; the current shared card layout is still present.
- Implement album-sharing controls and real viewer sharing; the viewer Share sheet is still a preview.
- Replace search ID fields with people/album/tag pickers; broader Immich search/admin parity still needs an audit.
- Verify the new API/video/sync paths against the user's actual Immich version. Development used loopback fixtures; no production account mutation or upload was performed.
- Google Photos editor parity, actual image processing/save, graphical map and offline locked-vault browsing remain unfinished from earlier iterations.

Use `./run` after reboot to build/start the current source. The app-owned sync service starts only when Background uploads is enabled in Folder sync. Resume from the existing commits and preserve other sessions' work.

## Resumed after reboot

The user resumed work and requested a Galeria rename (`com.neg-zero.Galeria`) plus a ZenPkgs package/program module. Collection-specific layouts and real album/media sharing are now implemented. Native fixture checks cover 500 albums with bounded cover loading, circular people, compact tags, duplicate comparisons at narrow widths, link creation/password clearing, invitations and role changes. Desktop file-open and legacy keyring migration checks also pass. Remaining work listed above is historical where superseded by these changes; real-server acceptance and editor/AI parity remain pending. No further shutdown is authorized.
