# BuMoChi — mocap → SuperCollider → Godot

Upstream is vendored here as a submodule, so a fresh clone needs one command
before the directory has anything in it:

```
git submodule update --init --recursive
```

That fills `bumochi/BuMoChi/` from https://github.com/iani/BuMoChi. Everything
below refers to paths inside it.

Port chain: XR-Animator → 39537 → BunrakuOSCEncoder → 57130 → SC/Bmc → 39538 → BunrakuOSCDecoder → 39539 → Godot.
`Bmc.help;` prints the active port map.

Launcher: `PipelineApplications/start_bumochi_pipeline.sh` starts the encoder,
the decoder and a Godot helper service; pass `--no-godot-service` to leave the
last one out. A second, older copy of the script sits at the repo root and
starts only the encoder and decoder. Prefer the one in `PipelineApplications/`,
and note that neither is the same file, so a fix applied to one does not reach
the other.

Copy `GodotProjects/*` into your assets root first — installing doesn't. Three
projects ship: `VMC_1_Avatar_F`, `VMC_1_Avatar_M`, `VMC_2_Avatars`.

Wiki: `tool.bumochi`.

## Reaching the rest of the event

Any value inside SuperCollider can go onto the shared bus as a Wwise game
parameter:

```supercollider
NetAddr("127.0.0.1", 9000).sendMsg("/wwise/rtpc", "Energy", val);
```

Run `kitlib contract` for the other verbs, and `kitlib monitor` to confirm the
message is actually arriving. Pose data that is yours rather than shared
belongs under a track prefix, `/ch5/pose/left_hand`, so it cannot collide with
another team's addresses.
