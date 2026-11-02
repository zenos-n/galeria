# Galeria

Native GTK4/libadwaita gallery for local folders and Immich, based on the supplied lo-fi layout.

Run `./run` on this ZenOS/Nix machine. The launcher builds an isolated package; it does not change the system configuration.

The flake supports `x86_64-linux` and `aarch64-linux`: `nix run` opens Galeria,
`nix build` builds it, and `nix develop` opens its Python/GTK development shell.
`nix run .#sync -- --help` runs the folder-sync service CLI. Nixpkgs is locked;
the app's NAPL license is allowed only for Galeria inside these outputs.

The welcome dialog routes **Yes, use Immich** to server/email/password sign-in and **No, choose folders** to the native multiple-folder picker. Sign-in loads albums, media and authenticated thumbnails/previews. Passwords are cleared on submission. Remember this account stores the session in the system Secret Service keyring; server/account identity and selected local folders are saved in private app preferences. OAuth is not implemented.

Local mode recursively discovers images and videos without modifying files or following symlinks. Images render thumbnails/previews, including WebP and AVIF, decoded off the GTK thread. Dates currently use filesystem modification times; filename search is local and case-insensitive. Scrolling near the end automatically loads the next batch, preserving scroll position. Images within two viewports above/below are requested; viewer previews have a separate worker queue. Clapper/GStreamer plays local and authenticated remote videos with buffering feedback and native controls. Nearby videos preload a bounded 2 MiB prefix. The loopback range bridge keeps credentials out of player URLs and uses encrypted caching for locked videos.

Ordinary thumbnails/previews are cached on disk with a 512 MB limit, account/server/revision-separated keys and 768 in-memory textures. Metadata snapshots expire after 30 seconds; Refresh bypasses them. Concurrent identical requests are coalesced. Preferences has Clear cache. This does not remove encrypted device copies. Measurements and limits are in PERF.md.

**Hamburger → Administration**, visible only to administrators, has Overview, Users, Job queues, Libraries and Settings. Click a user to edit name/email, role, quota and password, view storage/session information, or soft-delete/restore the account. Create user adds an account without sending email. Queues support Pause/Resume; older servers without `/queues` have read-only `/jobs` statistics. External libraries can be created, their server paths/exclusions edited, and scans started. Server scalar settings and string lists have native editors; nested object arrays are displayed as advanced entries, not edited. Save merges only changed fields into a fresh configuration. Server permissions remain authoritative and each section has its own error/retry state.

Albums uses virtualized square cover cards with counts and real sidebar navigation. People uses circular portraits, Tags uses compact native rows, and duplicate review compares previews side by side with a confirmed Keep this action that moves the other items to Trash. Albums/tags can be created or renamed; utility cards have action menus. People opens matching photos and supports rename/hide; Tags opens matching media and supports rename/delete; Duplicates opens groups for review/dismissal. Batch actions can favorite, add to an album, trash and restore media. Pinned albums persist per account. Map uses an interactive native map with photo clusters.

The HTTP adapter follows the [official Immich OpenAPI schema](https://github.com/immich-app/immich/blob/main/open-api/immich-openapi-specs.json). Current metadata search fields also support the older page-based API. Connection, authentication and permission errors are surfaced; requests run off the GTK thread, use timeouts and normal TLS verification, and do not follow redirects with credentials. Actual compatibility with the user's server still needs a live sign-in; the integration was exercised against a local HTTP fixture, not a production server.

The library uses justified thumbnail rows against the standard app background. Months and Years have real thumbnail covers and expand into full-width inline photo rows, with a pointer linking the cover to its contents. Switching tiers morphs the tiles toward or out of their date groups. Clicking a photo expands it along an arc into a viewer overlay that dims the app. The header and backdrop share one fade; closing remeasures the current tile bounds. Native stack transitions animate previous/next navigation; media geometry also animates between viewing and editing. Animations respect GTK's animation setting.

The sidebar includes a native Gtk.TreeListModel album tree with a disclosure button on the right, media types and Immich utilities. Symbolic icons are bundled from GNOME's [Icon Development Kit](https://gitlab.gnome.org/Teams/Design/icon-development-kit), the source used by Icon Library; attribution and CC0 license are in `icons/`. Non-library page titles are centered. Adw.Avatar has a square circular button. Appearance and density live only in Preferences. Upload progress is a flat sidebar row with a circular indicator, an item count and a right-side popover.

Immersive fullscreen uses a black background and fits the media to the full viewport. Controls hide and reappear on pointer motion; Esc first exits fullscreen. Details uses an Adw.OverlaySplitView with a material sidebar and a responsive overlay on narrow windows. Share creates real Immich links for the focused or selected media. Album sharing is available from the album menu and its header button; owners can invite server users, change viewer/editor roles, remove members, and create/revoke password-protected links with download/upload/metadata/expiration controls.

The native drop target accepts Gdk.FileList, including both files and folders. Drops and the upload picker open an import review sheet. Only item names and file types are inspected; directory contents are not scanned, and nothing is imported or uploaded.

The editor hides unrelated viewing controls. Its tool inventory follows the categories in [Google Photos' Android editor](https://support.google.com/photos/answer/6128850?hl=en&co=GENIE.Platform%3DAndroid): Suggestions, Crop, Adjust, Filters, Markup and Actions. Ask is intentionally removed. The layout uses centered wrapping choices, Light/Color/Detail adjustment groups and circular color swatches. It includes crop ratios, rotate/mirror, straighten/perspective controls, tonal/color adjustments, filter previews, markup choices, and planned advanced tools such as Magic Eraser, Unblur, Portrait Light and Auto Frame. Save and Save a copy are design controls. **This is not functional Google Photos parity**: image processing, AI models/services, brush engines, editing history and persistence remain unimplemented. No image is modified or saved.

Multi-selection supports the header selection toggle, checkboxes, Ctrl-click, Shift-click ranges, Ctrl+A, Escape, and a batch-action bar. Local files remain read-only. Trash uses a confirmation and restores from the Trash page rather than deleting permanently.

Search sends [Immich semantic/metadata queries](https://docs.immich.app/features/searching/) with filename, path, description, OCR, location, date, camera, exact rating and display filters. People, albums and tags currently accept IDs rather than name pickers. Active filters become removable chips. Server results are paginated; local mode hides server filters and matches real filenames. Photos, videos, favorites, archive and trash views use their corresponding server filters. Screenshots currently match the filename `Screenshot`; full screenshot detection is pending.

Locked folder authenticates through [Immich's PIN/session elevation](https://docs.immich.app/features/locked-folder/), with account-password fallback. Optional device copies require a random 256-bit key in the system keyring. Originals are streamed directly to AES-GCM ciphertext; thumbnails/previews and metadata are also authenticated ciphertext, never plaintext disk files. Lock, navigation away, source switch, expiry or shutdown cancels sync and clears access/memory state. The client locks locally after 14 minutes and requests server relocking. Device copies are retained separately from the ordinary cache; offline browsing and recovery/export of those copies are not yet implemented. Losing the keyring key loses access to the device copies; server originals remain untouched.

The welcome question has an illustration slot above the text for a user-supplied graphic. Recently added is removed. The upload button uses GNOME's cloud-deploy-symbolic. Empty upload progress is hidden.

Date folders reveal their photo rows directly downward at the media's normal size. Expanded years contain all that year's photos, without nested month folders or subgroups. Tier geometry is cached and intermediate frames reuse stable child sizes; measured CPU results and limits are in PERF.md. Fullscreen animates media bounds, the black backdrop and control visibility.

The image crop tool has draggable corners, a movable crop area, locked/free aspect ratios and guides reaching the media edges. It previews crop bounds; image processing and saving remain unconnected. Hover checkboxes are independent circular controls, so clicking one selects rather than opening the viewer.

Run the tests in the packaged Python environment (Pillow and cryptography required) with `python3 -m unittest -v`. They cover layout/crop geometry, discovery, HTTP requests, WebP/AVIF/JPEG decoding, cache persistence/isolation/coalescing and encrypted copy integrity. Native tests use generated media and a loopback fixture, including actual pointer album navigation, infinite scroll, account create/edit, utility results, PIN elevation and encrypted originals. No production account was mutated during verification.

Galeria 0.5 fetches the complete month/year catalog before loading the first page of media. Opening a date folder queries that date range instead of relying on the newest loaded page. Current Immich searches use structured filters, including `trashedAt` for Trash and `albumIds` for paginated album contents. Older detected servers retain the legacy search payload.

Search toggles from the sidebar and replaces the main header controls; Escape or the toggle closes it. Signed-in accounts have a context menu with sign-out and folder sync. Clicking the viewer backdrop closes focused media. Media stays opaque during its grid transition.

**Hamburger → Folder sync** configures upload-only rules per account: library or album destination, include/exclude subfolders, and an explicit unlimited-depth switch or maximum subfolder depth. Enabling uploads explicitly stores the session in the system keyring and installs/enables the app-owned `gallery-folder-sync.service` user service. It continues while the app is closed. A private SQLite journal skips unchanged files, checksum checks avoid duplicate uploads, changed files upload as new assets, and a stable-file check defers files still being written. The service never edits originals or mirrors deletions. Pausing/removing a rule stops it at file boundaries; an in-flight upload can finish. Disabling all accounts stops the service. No service was enabled against a production account during development.

Folder sync, sharing and remote playback were verified against loopback fixtures, not the user's production server. Google Photos processing/AI parity, offline locked-vault browsing remain unfinished.

The app is now **Galeria**, application ID `com.neg-zero.Galeria`, executable `galeria`. Desktop Open With accepts supported image/video files and directories; a single file opens in the viewer. Existing `gallery` configuration/cache/state directories and the folder-sync service name are retained for compatibility. Keyring reads fall back to the old schema and migrate entries to the Galeria schema; sign-out clears both. No stored library, sync rule, or encrypted vault key is discarded.

The ZenPkgs package is `pkgs.com.neg-zero.Galeria` (category alias `pkgs.byCategories.apps.graphics.galeria`). Enable it with `users.<name>.programs.galeria.enable = true;` or the corresponding system program defaults. `defaultViewer = true` optionally assigns supported image/video MIME types; its default is false. Accounts, credentials, preferences, caches and folder-sync rules stay writable and managed by the app.

Map uses libshumate with the server's configured map style, clustering geotagged
photos as you pan and zoom. Click a cluster to zoom in or a photo to browse that
location. OpenStreetMap is the fallback when the server style is unavailable.
External map providers receive no Immich session token.

Preferences offers **Start at login** (starts without a window) and **Keep running
in the background**. Closing the window hides it when background mode is enabled;
Ctrl+Q or Quit Galeria exits. Folder uploads use their independent sync service.
The optional [GNOME helper](https://github.com/zenos-n/galeria-gnome-extension)
adds Open, Folder sync, Sync now and background controls to Quick Settings.

Video editing supports trim start/end, free or fixed-ratio crop, quarter-turn
rotation, Original/Vivid/Warm/Cool/Mono/Noir filters, and a five-second encoded
preview. Save a copy exports H.264/AAC MP4 using FFmpeg, with cancellation and
atomic replacement. It refuses to overwrite the original. Remote edits read the
original through the authenticated loopback bridge; tokens never reach FFmpeg.
The existing image editor remains a preview; this video export path is connected.

Visited grid results, date covers and collection thumbnails stay in bounded RAM
caches. Returning to a cached grid does not replace it with the loading page.
Visible views check for remote changes every15seconds and preserve the
loaded page count and scroll position. These checks pause while viewing/editing
media. Month/year covers load separately from their complete date catalog.
Changing date tiers closes the expanded folder; transitions match asset IDs
between the actual grid images and cover quadrants. Only the viewport is drawn,
with two screens above/below allocated. Successful batch Trash animates thumbnail
snapshots into the sidebar, then rearranges the remaining tiles without refetching.

Galeria0.8 uses Immich's compact timeline metadata (IDs, ratios, dates and types)
to create the library's complete scroll range before thumbnail downloads.
Unfetched months start with lightweight size estimates; their exact geometry
arrives with compact metadata. Only cells within two screens of the viewport
construct buttons/pictures. Pending image jobs follow the current viewport;
abandoned jobs are skipped, and folder covers load for the visible date tier.
The indexed library currently applies to the unfiltered Immich Library; filtered
search/other collections retain paginated results. Legacy servers retain the
previous search path. Media details are hydrated when opening an indexed item.

Folder rules use explicit Unlimited subfolder depth and Folders to albums
switches. Album mode can map every directory to its own album, use a single named
album, or target an existing album. Subfolder names use `Root / relative/path`
so identical directory names under different parents remain distinct. Existing
rules retain their destinations; originals/deletions remain untouched.
Selection also offers Move to locked folder, using PIN/password elevation when
needed and invalidating ordinary cached copies and in-flight writes on success.
The main header is46px; sidebar hover restores the actual active item on leave.
Empty video thumbnails try a preview/frame fallback instead of downloading the
whole original as an image or repeatedly displaying error toasts.

`nix run -- --monitor DP-2` opens on a chosen connector. On Wayland the initial
fullscreen placement selects the display before mapping, then restores a normal
window; if the compositor moves it elsewhere, it retains fullscreen on the chosen
monitor. It does not change monitor configuration or control other windows.


Galeria 0.8.1 keeps full-library row heights while constructing rectangles and
native children only around the viewport. Scroll position determines image-job
priority; hover and transition planning operate on visible items. Cache writes
use an eviction index instead of rescanning the directory after every image.
See [PERF.md](PERF.md) for real-library measurements and remaining outliers.


Galeria 0.9 adds a native scrollbar with equal space per year in the indexed
All Photos view. Its small track divisions mark years; the year hint appears
only during hover or dragging. The newest year is at the top. Scrolling within
each year remains proportional to that year's content. Abandoned thumbnail jobs
are retired in batches so rapid scrolling does not repeatedly rescan stale work.


The year scrollbar overlays the grid without reserving a side column. It uses
native overlay-indicator styling: a narrow indicator at rest, an expanded track
and year divisions on hover/drag, and a year hint anchored to the actual cursor.
The hint follows the pointer even when dragging outside the track; release
outside collapses the scrollbar and hides its year divisions.

Galeria 0.10 restores the saved account's ordinary date index and cached visible
thumbnail pixels before session validation or network refresh. Existing disk
snapshots are usable past their refresh age; network revalidation updates the
same grid in place when its date catalog is unchanged. It decodes the first three
screens on a worker; the existing bounded RAM cache handles navigation afterward.
Missing or evicted thumbnails still need downloading. Cold accounts and cleared
caches still show loading feedback. Locked media is excluded from this bootstrap.

The user menu loads the Immich profile photo and offers **Change profile photo…**
with a native image chooser. Photos are cached by account and profile revision.
The sidebar shows actual folder-sync activity, uploaded/already-saved counts and
errors, including immediately after Sync now. It no longer repeats the username.

The viewer's Download action uses native Save As for the original. Multi-selection
has Download selected, which chooses a destination directory and preserves name
collisions with numbered copies. Transfers stream with cancellation and atomic
completion; failure never replaces an existing destination. Grid selection offers
Select month for the current/selected month, or Select all from selected months.
The year hint is an input-transparent overlay in the same window, so dragging
through it does not cross a separate popup input surface. Playback submenu
chevrons keep their transparent background.

Galeria0.10.1 refreshes visible libraries/albums even while another application
has focus, so uploads appear when Galeria is on a secondary display. Refresh
still pauses for hidden windows and focused-media viewing/editing. Folder sync
rescans enabled rules every30seconds by default; recent or changing files wait
until stable. After validating a saved account, Galeria resumes its already
opted-in sync rules and updates an older service runtime. Installing the service
no longer immediately sends SIGUSR1 before its signal handler is ready; its first
scan starts automatically. Existing running services use the normal wake signal.

Galeria0.10.2 shows the sidebar sync indicator only for pending/active work or
errors. Successful idle completion closes its popover and hides the indicator;
background scans continue. The active indicator has10px bottom/side spacing.
