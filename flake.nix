{
  description = "Minimal Doubao ASR voice input for NixOS";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      packages = forAllSystems (pkgs:
        let
          python = pkgs.python3.withPackages (ps: [ ps.requests ]);
        in
        {
          default = pkgs.writeShellApplication {
            name = "doubao-voice-input";
            runtimeInputs = [
              pkgs.alsa-utils
              pkgs.wtype
              python
            ];
            text = ''
              exec ${python}/bin/python ${./doubao-voice-input.py} "$@"
            '';
          };
        });

      apps = forAllSystems (pkgs: {
        default = {
          type = "app";
          program = "${self.packages.${pkgs.system}.default}/bin/doubao-voice-input";
        };
      });

      nixosModules.default = { config, lib, pkgs, ... }:
        let
          cfg = config.programs.doubao-voice-input;
        in
        {
          options.programs.doubao-voice-input = {
            enable = lib.mkEnableOption "minimal Doubao ASR voice input";
            package = lib.mkOption {
              type = lib.types.package;
              default = self.packages.${pkgs.system}.default;
            };
          };

          config = lib.mkIf cfg.enable {
            environment.systemPackages = [ cfg.package ];
          };
        };
    };
}
