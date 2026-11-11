# Galeria

Native GTK4/libadwaita gallery for local folders and Immich, based on the supplied lo-fi layout.

Run `./run` on this ZenOS/Nix machine. The launcher builds an isolated package; it does not change the system configuration.

The flake supports `x86_64-linux` and `aarch64-linux`: `nix run` opens Galeria,
`nix build` builds it, and `nix develop` opens its Python/GTK development shell.
`nix run .#sync -- --help` runs the folder-sync service CLI. Nixpkgs is locked;
the app's NAPL license is allowed only for Galeria inside these outputs.

The welcome dialog routes **Yes, use Immich** to server/email/password sign-in and **No, choose folders** to the native multiple-folder picker. Sign-in loads albums, media and authenticated thumbnails/previews. Passwords are cleared on submission. Remember this account stores the session in the system Secret Service keyring; server/account identity and selected local folders are saved in private app preferences. OAuth is not implemented.

Local mode recursively discovers images and videos without modifying files or following symlinks. Images render thumbnails/previews, including WebP and AVIF, decoded off the GTK thread. Dates currently use filesystem modification times; filename search is local and case-insensitive. Scrolling near the end automatically loads the next batch, preserving scroll position. Images within two viewports above/below are requested; viewer previews have a separate worker queue. Clapper/GStreamer plays local and authenticated remote videos with buffering feedback and native controls. Nearby videos preload a bounded 2 MiB prefix. The loopback range bridge keeps credentials out of player URLs and uses encrypted caching for locked videos.

Ordinary thumbnails/previews are cached on disk with a 512 MB limit, account/server/revision-separated keys and 768 in-memory textures. Video preloads have a separate 128 MB cache; existing video packets migrate without removing thumbnails. Cached thumbnails use a separate decoding queue so HTTP downloads cannot hold them up. Metadata snapshots expire after 30 seconds; Refresh bypasses them. Concurrent identical requests are coalesced. Preferences has Clear cache for both ordinary caches. This does not remove encrypted device copies. Measurements and limits are in PERF.md.

While Galeria is visible, remote changes are checked every 15 seconds. A changed
loaded month stays on screen until its replacement metadata is ready. Incoming
visible thumbnails are prepared before insertion, within the existing RAM limit.
Existing photos move into their new positions; arrivals fade in at their final
size. Selection and the visible scroll anchor are retained. Failed refreshes
leave the current photos visible and retry on the next check.

**Hamburger → Administration**, visible only to administrators, has Overview, Users, Job queues, Libraries and Settings. Click a user to edit name/email, role, quota and password, view storage/session information, or soft-delete/restore the account. Create user adds an account without sending email. Queues support Pause/Resume; older servers without `/queues` have read-only `/jobs` statistics. External libraries can be created, their server paths/exclusions edited, and scans started. Server scalar settings and string lists have native editors; nested object arrays are displayed as advanced entries, not edited. Save merges only changed fields into a fresh configuration. Server permissions remain authoritative and each section has its own error/retry state.

Albums uses virtualized square cover cards with counts and real sidebar navigation. People uses circular portraits, Tags uses compact native rows, and duplicate review compares previews side by side with a confirmed Keep this action that moves the other items to Trash. Albums/tags can be created or renamed; utility cards have action menus. People opens matching photos and supports rename/hide; Tags opens matching media and supports rename/delete; Duplicates opens groups for review/dismissal. Batch actions can favorite, add to an album, trash and restore media. Pin or unpin albums from the ellipsis or right-click menu, including sidebar albums. Pins persist per account; the Pinned section is hidden when empty. Map uses an interactive native map with photo clusters.

The HTTP adapter follows the [official Immich OpenAPI schema](https://github.com/immich-app/immich/blob/main/open-api/immich-openapi-specs.json). Current metadata search fields also support the older page-based API. Connection, authentication and permission errors are surfaced; requests run off the GTK thread, use timeouts and normal TLS verification, and do not follow redirects with credentials. Actual compatibility with the user's server still needs a live sign-in; the integration was exercised against a local HTTP fixture, not a production server.

The library uses justified thumbnail rows against the standard app background. Months and Years have real thumbnail covers and expand into full-width inline photo rows, with a pointer linking the cover to its contents. Switching tiers morphs the tiles toward or out of their date groups. Clicking a photo expands it along an arc into a viewer overlay that dims the app. The header and backdrop share one fade; closing remeasures the current tile bounds. Native stack transitions animate previous/next navigation; media geometry also animates between viewing and editing. Animations respect GTK's animation setting.

The sidebar includes a native Gtk.TreeListModel album tree with a disclosure button on the right, media types and Immich utilities. Symbolic icons are bundled from GNOME's [Icon Development Kit](https://gitlab.gnome.org/Teams/Design/icon-development-kit), the source used by Icon Library; attribution and CC0 license are in `icons/`. Non-library page titles are centered. Adw.Avatar has a square circular button. Appearance and density live only in Preferences. Upload progress is a flat sidebar row with a circular indicator, an item count and a right-side popover.

Immersive fullscreen uses a black background and fits the media to the full viewport. Controls hide and reappear on pointer motion; Esc first exits fullscreen. Details uses an Adw.OverlaySplitView with a material sidebar and a responsive overlay on narrow windows. Share creates real Immich links for the focused or selected media. Album sharing is available from the album menu and its header button; owners can invite server users, change viewer/editor roles, remove members, and create/revoke password-protected links with download/upload/metadata/expiration controls.

The native drop target accepts files and folders in both the grid and viewer. Drops and the upload picker open a review sheet; Upload scans supported media and sends originals to Immich off the GTK thread. SHA-1 preflight skips files already on the server. Transfers can be cancelled and never modify source files. A signed-in account is required.

The photo editor exposes Crop, Adjust and Markup. Light/Color/Detail controls apply distinct tonal, color and detail operations, retain independent values and snap to neutral during dragging; keyboard steps remain precise. Pen, highlighter, opaque redaction and placed text draw on the photo, with a highlighted selected color and Undo/Redo (Ctrl+Z, Ctrl+Shift+Z or Ctrl+Y). The Text tool opens an inline entry where you click; drag the caption to move it or its handles to rotate and scale. Compare shows the source and Reset clears edits. Save a copy uploads an edited PNG directly to Immich from memory, applying adjustments, markup, crop, rotation, mirror and straighten while preserving the original. Locked sources create locked copies. Unsupported remote originals use the server preview and report the lower-resolution copy. Previews run off the GTK thread, coalesce pending changes and use at most1200pixels per side. The separate video editor retains its functional trim, crop, rotation and filter export controls.

Multi-selection supports the header selection toggle, checkboxes, Ctrl-click, Shift-click ranges, Ctrl+A, Escape, and a batch-action bar. Local files remain read-only. Trash uses a confirmation and restores from the Trash page rather than deleting permanently.

Shift+D downloads the expanded media or the current selection through the
save-location picker. It is inactive while editing, typing, or using a dialog.
Copy media supplies image pixels only, with no file paths or URI formats.
Videos have no Copy action. If an Immich original cannot be decoded locally, its
rendered preview supplies the image pixels. Locked images stay in memory and
the app-owned clipboard provider is cleared when locked. Right-click Share
works for both images and videos.
Loading month metadata fills existing cells in place; it does not animate a new
upload. Pending scroll restoration yields to newer scroll input or a held year
scrollbar. The hamburger menu has no Quit item; Ctrl+Q remains available.

Search sends [Immich semantic/metadata queries](https://docs.immich.app/features/searching/) with filename, path, description, OCR, location, date, camera, exact rating and display filters. People, albums and tags currently accept IDs rather than name pickers. Active filters become removable chips. Server results are paginated; local mode hides server filters and matches real filenames. Photos, videos, favorites, archive and trash views use their corresponding server filters. Screenshots currently match the filename `Screenshot`; full screenshot detection is pending.

Locked folder authenticates through [Immich's PIN/session elevation](https://docs.immich.app/features/locked-folder/), with account-password fallback. Optional device copies require a random 256-bit key in the system keyring. Originals are streamed directly to AES-GCM ciphertext; thumbnails/previews and metadata are also authenticated ciphertext, never plaintext disk files. Lock, navigation away, source switch, expiry or shutdown cancels sync and clears access/memory state. The client locks locally after 14 minutes and requests server relocking. Device copies are retained separately from the ordinary cache; offline browsing and recovery/export of those copies are not yet implemented. Losing the keyring key loses access to the device copies; server originals remain untouched.

The welcome question has an illustration slot above the text for a user-supplied graphic. Recently added is removed. The upload button uses GNOME's cloud-deploy-symbolic. Empty upload progress is hidden.

Date folders reveal their photo rows directly downward at the media's normal size. Expanded years contain all that year's photos, without nested month folders or subgroups. Tier geometry is cached and intermediate frames reuse stable child sizes; measured CPU results and limits are in PERF.md. Fullscreen animates media bounds, the black backdrop and control visibility.

The image crop tool has draggable corners, a movable crop area, locked/free aspect ratios and guides reaching the media edges. Its bounds apply to the edited preview and PNG copy. Hover checkboxes are independent circular controls, so clicking one selects rather than opening the viewer.

Run the tests in the packaged Python environment (Pillow and cryptography required) with `python3 -m unittest -v`. They cover layout/crop geometry, discovery, HTTP requests, WebP/AVIF/JPEG decoding, cache persistence/isolation/coalescing and encrypted copy integrity. Native tests use generated media and a loopback fixture, including actual pointer album navigation, infinite scroll, account create/edit, utility results, PIN elevation and encrypted originals. No production account was mutated during verification.

Galeria 0.5 fetches the complete month/year catalog before loading the first page of media. Opening a date folder queries that date range instead of relying on the newest loaded page. Current Immich searches use structured filters, including `trashedAt` for Trash and `albumIds` for paginated album contents. Older detected servers retain the legacy search payload.

Search toggles from the sidebar and replaces the main header controls; Escape or the toggle closes it. Signed-in accounts have a context menu with sign-out and folder sync. Clicking the viewer backdrop closes focused media. Media stays opaque during its grid transition.

**Hamburger → Folder sync** configures upload-only rules per account: library or album destination, include/exclude subfolders, and an explicit unlimited-depth switch or maximum subfolder depth. Enabling uploads explicitly stores the session in the system keyring and installs/enables the app-owned `gallery-folder-sync.service` user service. It continues while the app is closed. A private SQLite journal skips unchanged files, checksum checks avoid duplicate uploads, changed files upload as new assets, and a stable-file check defers files still being written. The service never edits originals or mirrors deletions. Pausing/removing a rule stops it at file boundaries; an in-flight upload can finish. Disabling all accounts stops the service. No service was enabled against a production account during development.

Folder sync, sharing and remote playback were verified against loopback fixtures, not the user's production server. Advanced AI editing and offline locked-vault browsing remain unfinished.

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
Photos export PNG copies through the separate image editor described above.

Visited grid results, date covers and collection thumbnails stay in bounded RAM
caches. Returning to a cached grid does not replace it with the loading page.
Visible views check for remote changes every15seconds and preserve the
loaded page count and scroll position. These checks pause while viewing/editing
media. Month/year covers load separately from their complete date catalog.
Changing date tiers closes the expanded folder; transitions match asset IDs
between the actual grid images and cover quadrants. Only the viewport is drawn,
with two screens above/below allocated. Successful Trash, Archive and Move to locked folder actions animate visible
media into the invoked action icon, in selection and viewing mode, then rearrange
the remaining tiles without refetching.

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
errors. Directory scanning and duplicate checks stay quiet, including after Sync now; the indicator appears only during actual file uploads or for errors. It no longer repeats the username.

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
still pauses for hidden windows and focused-media viewing/editing. Folder sync now uses directory notifications (since0.13.0); recent or changing
files wait until stable, with an infrequent recovery scan. After validating a saved account, Galeria resumes its already
opted-in sync rules and updates an older service runtime. Installing the service
no longer immediately sends SIGUSR1 before its signal handler is ready; its first
scan starts automatically. Existing running services use the normal wake signal.

Galeria0.10.2 shows the sidebar sync indicator only for pending/active work or
errors. Successful idle completion closes its popover and hides the indicator;
background scans continue. The active indicator has10px bottom/side spacing.

Galeria0.10.3 keeps a compact justified-row index during window resizing instead
of constructing every offscreen photo rectangle for each width. Full scroll
heights and photo geometry remain exact; rectangles are produced only around the
viewport. A45,000-item private-display resize benchmark reduced frame p95 from
83ms to33ms. These are frame-clock measurements, not a universal GPU framerate
claim. Exact tests and limits are recorded in PERF.md.

Galeria0.11 restores RAM textures before building month/year-to-photo transition
sprites. Folder clipping follows logical photo membership through interrupted
closing and grid rebuilds; panels remain clipping anchors outside the viewport.
Widgets absent from both transition layouts are skipped rather than raising an
allocation exception. The compact row-index resize fix remains in place.

Selection and focused media both offer Archive (unarchive from Archive) and Trash
(restore from Trash), using the real Immich asset APIs and the existing Trash
confirmation. Right-click a grid item or focused media for Copy media, Download,
Archive and Trash; Ctrl+C copies focused images. Version0.13.0 supplies image
pixels only, without file/URI formats. Locked pixels and the app-owned private
clipboard provider are cleared on lock, sign-out, library switch or shutdown.
Other applications' clipboard histories are outside Galeria's control.

Video editing has separate trim and playback controls: two draggable start/end
handles with an accent-colored selected span, numeric times, and a playhead with
Play/Pause and seeking. Space toggles playback. Playback uses the original inside
the selected trim interval; Preview5seconds renders crop/rotation/filters, and
Save a copy exports all edits. Numeric fields and keyboard handle adjustment
remain available. Tests use generated media, local clipboard and fixture accounts.

Galeria0.11.1 retains the complete date-card starting layout during folder
opening/closing, including cards outside the viewport; native photo children
remain bounded. The panel collapses into the row gap so lower cards move with
its edge. Tier labels keep their normal size and draw above photo sprites;
interrupted tier-to-folder captions fade out instead of lingering.

Album cards use one native hover background. Owned album menus include
**Delete album…**, with confirmation. It deletes the collection, refreshes album
caches/sidebar/pins, and leaves media in the library, following
[Immich3.3.3's album deletion endpoint](https://github.com/immich-app/immich/blob/v3.3.3/server/src/services/album.service.ts#L153).
Empty cached album views remain visible after deleting the last album.

The timeline date follows the newest visible month in All Photos and visible year in the date tiers. The newest month appears only in the header, with no duplicate inline heading or reserved gap. Older month labels move vertically from their exact inline position into the header and reverse with scrolling. Both use the same left edge; fast skips exchange header labels in the actual scroll direction.

Moving assets to Locked retains other assets’ RAM textures and known disk thumbnails/previews/video prefixes. Only moved assets leave RAM cover caches; metadata snapshots and unclassified disk entries are invalidated for privacy, and pending pre-move writes are blocked. The remaining grid reflows with its scroll anchor intact.


Galeria0.13.0 adds working file/folder drop uploads, including drops onto focused
media, and event-driven folder syncing. Gio directory monitors wake the service
after a250ms debounce; a two-second stable-file check avoids uploading half-written
files. Pending files retry after2.2seconds, errors after30seconds, and a600second
recovery pass covers missed/unavailable notifications. Recursive monitors follow
the existing include-subfolders/depth rules, including new directories. Scanning,
hashing and duplicate checks do not show an upload indicator.

Photo copies now upload PNG bytes directly to Immich without a local save dialog
or plaintext staging file. Both editors have bounded Undo/Redo history; photo
markup supports inline text entry, move, rotate and scale. Focused media offers
working Favorite, Archive, Trash and Locked actions. Space toggles video playback
without leaving focus; Replay restarts ended videos and Loop repeats the item.
Mouse-wheel zoom and pinch zoom span1–8x, with drag panning and a reset control.
Zoom transforms the existing widget rather than reallocating a larger player.

Action animations target the actual toolbar icon. Moving assets to Locked also
retains currently displayed textures evicted from the LRU; metadata-only arrivals
reuse existing cells and pixels. The year-scroll hint has an explicit popover
background.78unit checks and native action-target, real cross-window drop/upload,
clipboard receiver, viewer controls, editor, Locked retention and scrolling/date
regressions pass. Pinch/pan callbacks were simulated; physical touchpad/touch
hardware and production-server mutations were not tested.


Galeria0.13.1 starts the remaining selection grid's reflow as soon as removal
snapshots begin flying to the Trash, Archive or Locked icon. The selection
toolbar stays visible until the snapshots arrive, then exits selection mode.
Native checks verify intermediate tile positions during all three flights,
empty-grid/reduced-motion completion, actual icon targets and API failure
retention. The Locked cache/privacy/scroll regression also passes.


Galeria0.14.0 asks **Save / Cancel / Discard** when leaving an editor with
unsaved changes, including Done, Back/Escape, changing media, closing the window
and quitting. Save uses the existing photo-to-Immich or video-save-copy flow
and leaves only after success; failure or a cancelled file chooser retains edits.
Cancel stays in the editor; Discard restores its last successfully saved state.
An unchanged or already saved editor leaves directly. Saved state stays separate
from the bounded Undo/Redo history and is cleared with private editor data.

Text markup now caches Pango/Cairo glyph outlines, shared by the live preview
and output renderer, rather than enlarging a small text bitmap. PNG copies draw
those outlines at final image resolution; the saved photo itself remains a PNG.
Text rotation snaps within6degrees of multiples of90degrees and remains free
between detents.80unit tests and native photo/vector/rotation, editor-exit,
video-edit/export and clipboard regressions pass. Exit checks cover Save/Cancel/
Discard, upload/export failures, chooser cancellation, clean/saved state and
window/quit guards using generated media. Large-text and prompt screenshots
were inspected; no production media was edited for tests.


Galeria0.14.1 opens desktop Open With requests in separate device-file preview
windows. Opening or refreshing these previews never changes the saved library
or replaces the main Immich client, grid, cached textures or scroll position.
Starting normally still restores the saved account, including after a cold
Open With launch. Explicit Choose folders retains its persistent behavior.
Preview windows close fully even when background mode is enabled; Quit checks
unsaved edits and cleans up every Galeria window. A private-session native
regression launches a real desktop entry through GApplication for cold/warm
images, videos, multiple files and folders. It reproduces the0.14.0 account-mode
overwrite and verifies byte-identical saved preferences with the fix.


Galeria0.14.2 opens indexed media immediately from its cached thumbnail while
fresh asset details load in the background. Full previews, video playback,
editing and data actions wait for that validation; newly private items are
rejected. Back, navigation and cached-image zoom stay responsive. Failed detail
requests retain the cached view; late responses from a closed/previous item
are ignored. Videos autoplay when delayed metadata permits playback.

The private-display click-to-paint fixture uses the same cached pixels and a
fixed1200ms details delay: median1265ms before,55ms after across three indexed
items. An already hydrated item remains about56–61ms. These are controlled
measurements, not a production-server latency claim. Native privacy/failure/
stale-response/navigation/video checks pass, along with existing viewer controls,
clipboard/editor exits, Open With account retention and selection animations.


Galeria0.14.3 installs application styles during shared startup, so cold
Open With previews have the same sidebar heading margins and dark focus
backdrop as the library. Preview account controls show the live or remembered
Immich identity and cached avatar; Open library and sidebar navigation return
to the primary library through normal session restoration. Device-file actions
remain isolated from the cloud client. Primary account changes update previews.
Focus actions sit on the left; Info and Edit remain on the right.

The private-session desktop-entry regression now exercises real application
startup and checks computed heading margins, backdrop pixels, action positions,
cached/live avatar identity, return-to-library restoration and signout updates,
as well as the existing saved-session/grid/cache/scroll preservation checks.
The80unit tests and native viewer-controls, clipboard, editor-exit, opening
latency and all six selection/focus action-target checks pass on the packaged
GTK environment. Production Immich authentication was not exercised.


Galeria0.14.4 accepts Ctrl+V image uploads in the connected gallery, selection
and focus views. Clipboard pixels become a PNG in memory and use the existing
checksum preflight, duplicate skipping, upload progress and incremental refresh.
Text fields, dialogs and editing keep their normal paste behavior; late clipboard
replies cannot upload to a newly selected account. No temporary image is written.

Move to trash now offers This device and Immich, This device only, or Immich only,
with both selected when both copies are known. Local files use the desktop Trash;
cloud items use Immich Trash. Local-only deletion leaves the cloud item visible,
and cloud-only deletion preserves local files. Sync-journal associations are
reused; manual imports and new downloads record account/asset/path/checksum
associations. Older unrecorded copies are not guessed or scanned for. Each known
original is checked before removal; changed files and symlinks are kept. A failed
cloud operation leaves local originals untouched. Local failures after a cloud
success are reported separately. Restoring Immich Trash restores the cloud copy;
local copies can be restored from the desktop Trash.

Verification uses generated media and fixture accounts: actual cross-process
clipboard pixels and real Ctrl+V, multipart uploads/alpha/checksum/duplicates,
selection/focus/text paste, failure and account-change guards; the native Trash
scope dialog and real reversible desktop Trash, local/cloud/both modes; existing
six action animation targets and actual file-drop upload regressions. No
production files or cloud assets were deleted in tests.
All85unit tests pass, along with native image-paste, Trash-scope, action-target,
file-drop upload, viewer clipboard, editor-exit and cold/warm Open With checks.


Galeria0.14.5 puts upload previews into the grid before the transfer finishes.
Paste inserts its clipboard pixels immediately; file/folder imports queue image
and video tiles before their transfers. Edited photos create a pending copy as
soon as rendering produces its PNG, while keeping the editor open.
The folder-sync service publishes per-file transfer records; file monitoring
and the fallback poll feed the same tiles without showing scan-only activity.

Each uploading tile has a circular byte-progress indicator. It remains until
Immich confirms an asset or checksum duplicate, then the tile adopts that ID
and the circle disappears. Server metadata adopts its cached pixels. Pending
IDs cannot be selected or sent to cloud actions. Failed uploads retain their
preview and a Retry control; sync retry wakes the existing service. Account
changes/window shutdown fence transient previews and queued GTK handoffs.

Upload updates retain existing cells and textures. Thumbnail and metadata work
is restricted to the visible area and one screen below; offscreen content waits
for scrolling. Completing an upload updates its tile without a full-grid refresh.
Progress changes redraw only the visible circles. In a private X11/software-GL fixture with the upload response
held until after paint,1,000cached items paint clipboard pixels/circle in about
60ms;8,000items take about102ms versus618ms before cell reuse and viewport scoping. These are controlled
fixture values, not production timing claims. The check enforces500ms and tests
real multipart byte progress, image/video batches, sync status, failure/retry,
server metadata adoption and cell/pixel retention.92unit tests pass, including
local Trash rejection of replaced FIFOs without blocking a worker.


Galeria0.14.6 opens desktop Open With files in focus over the primary library.
Cold launches restore the remembered Immich account normally and load its grid
behind the device file. Warm launches keep the existing account and browse state.
Sidebar navigation stays in the same window. Multiple files and folders queue
in that window; device paths never act as cloud asset IDs.

Leaving focus, closing the window or quitting checks the original's SHA1 against
Immich off the GTK thread. An existing asset skips the prompt. A new file offers
Save, Don’t Save and Cancel; Save uploads the unchanged original through the
existing progress flow and waits for acknowledgement. Failed checks offer Retry
or Don’t Save. A failed save leaves focus open. A disconnected library can still
preview device files; there is no upload or duplicate check without a client.

The real desktop-entry regression covers cold/warm restoration, image/video/
batch focus, same-window navigation, duplicate skip, cancel/retry/discard/save,
failed saves, background close and Save on Quit. Fixture originals and saved
preferences are byte-identical.92unit tests and native editor/viewer/clipboard/
upload/Trash/account/cache regressions pass. All upload checks use fixtures.


Version 0.14.7 adds a 50%-to-transparent black gradient behind fullscreen
viewer controls. Fullscreen, Download and Share sit immediately before Info
and Edit on the right. Archive and Trash start their icon animation before
the server response, with rollback after failures and reconciliation of partial
local Trash results. Automatic folder sync requires ten seconds of observed
size and modification-time stability and skips files open for writing on Linux.
Details shows full local paths from the account-scoped upload journal.
