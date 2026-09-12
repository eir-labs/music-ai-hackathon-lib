# Wwise

- `kitlib wwise` — OSC → WAAPI bridge. Anything that speaks OSC drives Wwise events/RTPCs, no game engine.
  `kitlib wwise --map /sensor/radar=Proximity -v` · `osc2wwise.py` still works and does the same thing.
- Wwise must be running with a project open and **Project > User Preferences > Enable Wwise Authoring API** ticked.
  If it is not, the bridge says so within a second or two rather than hanging.
- Verbs: `/wwise/event` `/wwise/rtpc` `/wwise/switch` `/wwise/state` `/wwise/pos` `/wwise/stop`. Run `kitlib contract` for the arguments.
- Authoring by prompt: [BilkentAudio/Wwise-MCP](https://github.com/BilkentAudio/Wwise-MCP) — add it to Claude Code / Cursor next to the eir wiki MCP.
- Wiki: `tool.wwise`, `tool.osc2wwise`, `tool.wwise-mcp`.
