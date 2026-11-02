{
  description = "Galeria — native GTK photo and video library for local folders and Immich";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      eachSystem = nixpkgs.lib.genAttrs systems;
      packagesFor = system: import nixpkgs {
        inherit system;
        config.allowUnfreePredicate = package: (package.pname or "") == "galeria";
      };
    in {
      packages = eachSystem (system:
        let pkgs = packagesFor system; galeria = import ./default.nix { inherit pkgs; };
        in { inherit galeria; default = galeria; });
      apps = eachSystem (system: {
        default = { type = "app"; program = "${self.packages.${system}.galeria}/bin/galeria"; };
        sync = { type = "app"; program = "${self.packages.${system}.galeria}/bin/galeria-sync"; };
      });
      devShells = eachSystem (system:
        let pkgs = packagesFor system;
        in { default = pkgs.mkShell {
          inputsFrom = [ self.packages.${system}.galeria ];
          packages = [ (pkgs.python3.withPackages (ps: with ps; [ pygobject3 pycairo pillow cryptography ])) ];
        }; });
      checks = eachSystem (system: { inherit (self.packages.${system}) galeria; });
    };
}
