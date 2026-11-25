{ pkgs ? import (builtins.getFlake "nixpkgs").outPath {
  config.allowUnfreePredicate = package: (package.pname or "") == "galeria";
} }:
let
  mediaGtk = pkgs.gtk4.overrideAttrs (old: {
    patches = (old.patches or []) ++ [ ./gtk-media-hdr.patch ];
  });
in pkgs.stdenv.mkDerivation {
  pname = "galeria";
  version = "0.14.21";
  src = pkgs.lib.cleanSource ./.;
  nativeBuildInputs = with pkgs; [ wrapGAppsHook4 gobject-introspection makeWrapper ];
  buildInputs = with pkgs; [ mediaGtk libadwaita libsecret libshumate libglycin libglycin-gtk4 libglycin.setupHook glycin-loaders shared-mime-info clapper-unwrapped.lib gst_all_1.gst-plugins-rs gst_all_1.gstreamer gst_all_1.gst-plugins-base gst_all_1.gst-libav gst_all_1.gst-plugins-good gst_all_1.gst-plugins-bad ];
  # Reuse existing GTK ABI consumers with this app-local runtime backport.
  preFixup = ''
    gappsWrapperArgs+=(--prefix GI_TYPELIB_PATH : "${mediaGtk}/lib/girepository-1.0")
    gappsWrapperArgs+=(--prefix LD_LIBRARY_PATH : "${mediaGtk}/lib")
  '';
  dontBuild = true;
  installPhase = ''
    mkdir -p $out/lib/galeria $out/bin $out/share/applications $out/share/metainfo $out/share/icons/hicolor/scalable/apps
    cp *.py style.css $out/lib/galeria/
    ${pkgs.python3}/bin/python3 -m compileall -q --invalidation-mode unchecked-hash "$out/lib/galeria"
    cp -r icons $out/lib/galeria/
    cp data/com.neg-zero.Galeria.desktop $out/share/applications/
    cp data/com.neg-zero.Galeria.metainfo.xml $out/share/metainfo/
    cp icons/hicolor/scalable/apps/com.neg-zero.Galeria.svg $out/share/icons/hicolor/scalable/apps/
    makeWrapper ${pkgs.python3.withPackages (ps: with ps; [ pygobject3 pycairo pillow cryptography ])}/bin/python3 $out/bin/galeria \
      --add-flags "$out/lib/galeria/app.py" --prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.ffmpeg-headless ]}
    makeWrapper ${pkgs.python3.withPackages (ps: with ps; [ pygobject3 pycairo pillow cryptography ])}/bin/python3 $out/bin/galeria-sync \
      --add-flags "$out/lib/galeria/sync_service.py"
  '';
  meta = {
    description = "Native photo and video library for local folders and Immich";
    mainProgram = "galeria";
    platforms = pkgs.lib.platforms.linux;
    license = { shortName = "NAPL"; fullName = "Non-Aggression License 1.1"; url = "https://github.com/zenos-n/galeria/blob/main/LICENSE"; free = false; };
  };
}
