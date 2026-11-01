# Gallery

Native GTK4/libadwaita design prototype based on the supplied lo-fi layout.

Run `./run` on this ZenOS/Nix machine. The launcher builds an isolated package; it does not change the system configuration.

The welcome dialog routes **Yes, use Immich** to a sign-in form and **No, choose folders** to the native multiple-folder picker. This is a UI preview: no server requests, authentication, directory scanning, or photo loading occur. Password fields are not stored. Selecting folders only changes the sidebar label.

The library uses neutral blocks to show justified thumbnail rows against the standard app background. Months and Years are date-folder covers that expand into full-width inline rows, with a pointer linking the cover to its contents. Switching tiers morphs the persistent tiles toward or out of their containing date groups. Clicking a photo expands it along an arc into a viewer overlay that dims the app. The media stays invisible until its initial bounds are measured; the header and backdrop share one fade. Closing remeasures the current tile bounds and renders the thumbnail content for a frame before restoring it. Native stack transitions animate previous/next navigation; media geometry also animates between viewing and editing. Animations respect GTK's animation setting.

The sidebar includes a native Gtk.TreeListModel/TreeExpander album tree, media types and Immich utilities. Symbolic icons are bundled from GNOME's [Icon Development Kit](https://gitlab.gnome.org/Teams/Design/icon-development-kit), the source used by Icon Library; attribution and CC0 license are in `icons/`. Non-library page titles are centered. Adw.Avatar has a square circular button. Appearance and density live only in Preferences. Upload progress is a flat sidebar row with a circular indicator, an item count and a right-side popover.

Immersive fullscreen uses a black background and fits the media to the full viewport. Controls hide and reappear on pointer motion; Esc first exits fullscreen. Details uses an Adw.OverlaySplitView with a material sidebar and a responsive overlay on narrow windows. Share opens a native sheet with recipient, shared-album, download and expiration controls.

The native drop target accepts Gdk.FileList, including both files and folders. Drops and the upload picker open an import review sheet. Only item names and file types are inspected; directory contents are not scanned, and nothing is imported or uploaded.

The editor hides unrelated viewing controls. Its tool inventory follows the categories in [Google Photos' Android editor](https://support.google.com/photos/answer/6128850?hl=en&co=GENIE.Platform%3DAndroid): Suggestions, Crop, Adjust, Filters, Markup and Actions. Ask is intentionally removed. The layout uses centered wrapping choices, Light/Color/Detail adjustment groups and circular color swatches. It includes crop ratios, rotate/mirror, straighten/perspective controls, tonal/color adjustments, filter previews, markup choices, and planned advanced tools such as Magic Eraser, Unblur, Portrait Light and Auto Frame. Save and Save a copy are design controls. **This is not functional Google Photos parity**: image processing, AI models/services, brush engines, editing history and persistence remain unimplemented. No image is modified or saved.

Multi-selection supports the header selection toggle, checkboxes, Ctrl-click, Shift-click ranges, Ctrl+A, Escape, and a batch-action bar. The batch actions are UI previews.

Search exposes the [Immich search modes and metadata filters](https://docs.immich.app/features/searching/), including semantic search, filename, path, description, OCR, people, albums, tags, location, date range, camera, ratings and display options. Active filters become removable chips. Local mode hides server filters and matches only placeholder filenames. Real Immich search is not connected; no search request is sent.

Locked folder has an unlock form but does not authenticate, encrypt, cache or sync anything. Before real locked-folder sync is enabled, files **and thumbnails** must be encrypted on this device, plaintext caches must be excluded, and key storage, session locking and recovery must be designed and verified. The preview never claims that a vault has been unlocked or protected.

The welcome question has an illustration slot above the text for a user-supplied graphic. Recently added is removed. The upload button uses GNOME's cloud-deploy-symbolic. Empty upload progress is hidden.

Date folders reveal their photo rows directly downward at the media's normal size. Expanded years contain all that year's photos, without nested month folders or subgroups. Tier geometry is cached and intermediate frames reuse stable child sizes; measured CPU results and limits are in PERF.md. Fullscreen animates media bounds, the black backdrop and control visibility.

The crop tool has draggable corners, a movable crop area, locked/free aspect ratios and guides reaching the media edges. It previews crop bounds in the placeholder editor; image processing and saving remain unconnected. Hover checkboxes are independent circular controls, so clicking one selects rather than opening the viewer.

Check layout and crop geometry with `python3 -m unittest -v test_layout.py test_crop_geometry.py`.
