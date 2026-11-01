{ pkgs ? import (builtins.getFlake "nixpkgs").outPath {} }:
pkgs.stdenv.mkDerivation {
  pname = "gallery";
  version = "0.3.0";
  src = pkgs.lib.cleanSource ./.;
  nativeBuildInputs = with pkgs; [ wrapGAppsHook4 gobject-introspection makeWrapper ];
  buildInputs = with pkgs; [ gtk4 libadwaita libsecret ];
  dontBuild = true;
  installPhase = ''
    mkdir -p $out/lib/gallery $out/bin
    cp *.py style.css $out/lib/gallery/
    cp -r icons $out/lib/gallery/
    makeWrapper ${pkgs.python3.withPackages (ps: with ps; [ pygobject3 pycairo pillow cryptography ])}/bin/python3 $out/bin/gallery \
      --add-flags "$out/lib/gallery/app.py"
  '';
}
