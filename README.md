# Gallery

Native GTK4/libadwaita design prototype based on the supplied lo-fi layout.

Run `./run` on this ZenOS/Nix machine. The launcher builds an isolated package; it does not change the system configuration.

The welcome dialog routes **Yes, use Immich** to a sign-in form and **No, choose folders** to the native multiple-folder picker. This is a UI preview: no server requests, authentication, directory scanning, or photo loading occur. Password fields are not stored. Selecting folders only changes the sidebar label.

The library uses neutral blocks to show justified thumbnail rows against the standard app background. Years / Months / All Photos change the grouping and scale. Clicking a block expands it along an arc into a viewer overlay that dims the app. The source tile is hidden without changing the grid's sensitivity styling. Closing remeasures its current bounds and renders the exact source snapshot for one frame before restoring the grid. Native stack transitions animate previous/next navigation. Animations respect GTK's animation setting.

The sidebar includes a native Gtk.TreeListModel/TreeExpander album tree, media types and Immich utilities. Symbolic icons are bundled from GNOME's [Icon Development Kit](https://gitlab.gnome.org/Teams/Design/icon-development-kit), the source used by Icon Library; attribution and CC0 license are in `icons/`. Non-library page titles are centered. Adw.Avatar has a square circular button. Appearance and density live only in Preferences. Upload progress is a flat sidebar row with a circular indicator, an item count and a right-side popover.

Immersive fullscreen uses a black background and fits the media to the full viewport. Controls hide and reappear on pointer motion; Esc first exits fullscreen. Details uses an Adw.OverlaySplitView with a material sidebar and a responsive overlay on narrow windows. Share opens a native sheet with recipient, shared-album, download and expiration controls.

The native drop target accepts Gdk.FileList, including both files and folders. Drops and the upload picker open an import review sheet. Only item names and file types are inspected; directory contents are not scanned, and nothing is imported or uploaded.

The editor hides unrelated viewing controls. Its tool inventory follows the categories in [Google Photos' Android editor](https://support.google.com/photos/answer/6128850?hl=en&co=GENIE.Platform%3DAndroid): Suggestions, Crop, Adjust, Filters, Markup, Actions and conversational editing. It includes crop ratios, rotate/mirror, straighten/perspective controls, tonal/color adjustments, filter previews, markup choices, and planned advanced tools such as Magic Eraser, Unblur, Portrait Light and Auto Frame. Save and Save a copy are design controls. **This is not functional Google Photos parity**: image processing, AI models/services, selection/brush engines, editing history and persistence remain unimplemented. No image is modified or saved.

Locked folder has an unlock form but does not authenticate, encrypt, cache or sync anything. Before real locked-folder sync is enabled, files **and thumbnails** must be encrypted on this device, plaintext caches must be excluded, and key storage, session locking and recovery must be designed and verified. The preview never claims that a vault has been unlocked or protected.

The welcome question will receive a user-supplied graphic in a later pass.

Check the layout geometry with `python3 -m unittest -v test_layout.py`.
