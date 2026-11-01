# Gallery

Native GTK4/libadwaita gallery for local folders and Immich, based on the supplied lo-fi layout.

Run `./run` on this ZenOS/Nix machine. The launcher builds an isolated package; it does not change the system configuration.

The welcome dialog routes **Yes, use Immich** to server/email/password sign-in and **No, choose folders** to the native multiple-folder picker. Sign-in now calls Immich, loads real albums and pages of media, and fetches authenticated thumbnails and larger image previews. Passwords are cleared from the form when submitted; session tokens stay in memory. Nothing is saved to a credential file or thumbnail cache. Choose the library again after restarting. OAuth and persistent sessions are not implemented.

Local mode recursively discovers images and videos in the selected folders without modifying files or following symlinks. Images render real thumbnails and viewer previews. Dates currently use filesystem modification times; filename search is local and case-insensitive. The grid starts with 100 items and Load more adds the next batch. Video playback remains unconnected; remote videos can show their server thumbnail.

**Hamburger → Administration** opens a native panel with Overview, Users and Job queues. An administrator session loads server version, media counts, storage, users/quotas and queue statistics. Pause/Resume sends a real queue update when clicked. Refresh reloads server data. Non-admin sessions get an access-required state, and denied requests show a retryable error per section. Older servers without `/queues` fall back to read-only `/jobs` statistics. User creation/deletion, system configuration and external-library management are not implemented.

The HTTP adapter follows the [official Immich OpenAPI schema](https://github.com/immich-app/immich/blob/main/open-api/immich-openapi-specs.json). Current metadata search fields also support the older page-based API. Connection, authentication and permission errors are surfaced; requests run off the GTK thread, use timeouts and normal TLS verification, and do not follow redirects with credentials. Actual compatibility with the user's server still needs a live sign-in; the integration was exercised against a local HTTP fixture, not a production server.

The library uses justified thumbnail rows against the standard app background. Months and Years have real thumbnail covers and expand into full-width inline photo rows, with a pointer linking the cover to its contents. Switching tiers morphs the tiles toward or out of their date groups. Clicking a photo expands it along an arc into a viewer overlay that dims the app. The header and backdrop share one fade; closing remeasures the current tile bounds. Native stack transitions animate previous/next navigation; media geometry also animates between viewing and editing. Animations respect GTK's animation setting.

The sidebar includes a native Gtk.TreeListModel/TreeExpander album tree, media types and Immich utilities. Symbolic icons are bundled from GNOME's [Icon Development Kit](https://gitlab.gnome.org/Teams/Design/icon-development-kit), the source used by Icon Library; attribution and CC0 license are in `icons/`. Non-library page titles are centered. Adw.Avatar has a square circular button. Appearance and density live only in Preferences. Upload progress is a flat sidebar row with a circular indicator, an item count and a right-side popover.

Immersive fullscreen uses a black background and fits the media to the full viewport. Controls hide and reappear on pointer motion; Esc first exits fullscreen. Details uses an Adw.OverlaySplitView with a material sidebar and a responsive overlay on narrow windows. Share opens a native sheet with recipient, shared-album, download and expiration controls.

The native drop target accepts Gdk.FileList, including both files and folders. Drops and the upload picker open an import review sheet. Only item names and file types are inspected; directory contents are not scanned, and nothing is imported or uploaded.

The editor hides unrelated viewing controls. Its tool inventory follows the categories in [Google Photos' Android editor](https://support.google.com/photos/answer/6128850?hl=en&co=GENIE.Platform%3DAndroid): Suggestions, Crop, Adjust, Filters, Markup and Actions. Ask is intentionally removed. The layout uses centered wrapping choices, Light/Color/Detail adjustment groups and circular color swatches. It includes crop ratios, rotate/mirror, straighten/perspective controls, tonal/color adjustments, filter previews, markup choices, and planned advanced tools such as Magic Eraser, Unblur, Portrait Light and Auto Frame. Save and Save a copy are design controls. **This is not functional Google Photos parity**: image processing, AI models/services, brush engines, editing history and persistence remain unimplemented. No image is modified or saved.

Multi-selection supports the header selection toggle, checkboxes, Ctrl-click, Shift-click ranges, Ctrl+A, Escape, and a batch-action bar. The batch actions are UI previews.

Search sends [Immich semantic/metadata queries](https://docs.immich.app/features/searching/) with filename, path, description, OCR, location, date, camera, exact rating and display filters. People, albums and tags currently accept IDs rather than name pickers. Active filters become removable chips. Server results are paginated; local mode hides server filters and matches real filenames. Photos, videos, favorites, archive and trash views use their corresponding server filters. Screenshots currently match the filename `Screenshot`; full screenshot detection is pending.

Locked folder has an unlock form but does not authenticate, encrypt, cache or sync anything. Locked assets are excluded from loaded results. Before real locked-folder sync is enabled, files **and thumbnails** must be encrypted on this device, plaintext caches must be excluded, and key storage, session locking and recovery must be designed and verified. The app never claims that a vault has been unlocked or protected.

The welcome question has an illustration slot above the text for a user-supplied graphic. Recently added is removed. The upload button uses GNOME's cloud-deploy-symbolic. Empty upload progress is hidden.

Date folders reveal their photo rows directly downward at the media's normal size. Expanded years contain all that year's photos, without nested month folders or subgroups. Tier geometry is cached and intermediate frames reuse stable child sizes; measured CPU results and limits are in PERF.md. Fullscreen animates media bounds, the black backdrop and control visibility.

The crop tool has draggable corners, a movable crop area, locked/free aspect ratios and guides reaching the media edges. It previews crop bounds; image processing and saving remain unconnected. Hover checkboxes are independent circular controls, so clicking one selects rather than opening the viewer.

Run `python3 -m unittest -v` for layout/crop geometry, local discovery and HTTP client tests. HTTP tests use an isolated loopback server and dummy credentials; they do not contact Immich or modify user media.
