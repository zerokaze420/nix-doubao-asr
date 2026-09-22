# nix-asr

最小豆包语音输入：录音、调用豆包语音识别大模型、把结果输入到当前 Wayland 窗口。

## 使用

```bash
export DOUBAO_ASR_API_KEY='你的 x-api-key'
nix run path:/home/tux/code/nix-asr -- --seconds 5
```

只输出文字，不自动输入：

```bash
nix run path:/home/tux/code/nix-asr -- --seconds 5 --no-type
```

NixOS 配置：

```nix
{
  inputs.nix-asr.url = "path:/home/tux/code/nix-asr";

  outputs = { nixpkgs, nix-asr, ... }: {
    nixosConfigurations.host = nixpkgs.lib.nixosSystem {
      modules = [
        nix-asr.nixosModules.default
        { programs.doubao-voice-input.enable = true; }
      ];
    };
  };
}
```

然后把 `DOUBAO_ASR_API_KEY` 放到你的 shell、systemd user 环境或密钥管理工具里。

## 快捷键

固定录音时长，例如在 sway 里：

```text
bindsym $mod+space exec env DOUBAO_ASR_API_KEY=$DOUBAO_ASR_API_KEY doubao-voice-input --seconds 5
```

按住说话、松开输入，例如在 Hyprland 里：

```text
bind = SUPER, SPACE, exec, doubao-voice-input --start
bindr = SUPER, SPACE, exec, doubao-voice-input --stop
```

当前实现依赖 ALSA 的 `arecord` 录音和 Wayland 的 `wtype` 输入。
