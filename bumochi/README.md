# BuMoChi — mocap → SuperCollider → Godot

Upstream: https://github.com/iani/BuMoChi (add as a submodule: `git submodule add https://github.com/iani/BuMoChi bumochi/BuMoChi`).

Port chain: XR-Animator → 39537 → BunrakuOSCEncoder → 57130 → SC/Bmc → 39538 → BunrakuOSCDecoder → 39539 → Godot.
Launcher: `./PipelineApplications/start_bumochi_pipeline.sh` (starts encoder+decoder only). `Bmc.help;` prints the active port map.
Copy `GodotProjects/*` into your assets root first — installing doesn't. Wiki: `tool.bumochi`.

To send any Bmc value on to Wwise: `NetAddr("127.0.0.1", 9000).sendMsg("/wwise/rtpc", "Energy", val)`.
