# Wwise

- `osc2wwise.py` — OSC → WAAPI bridge. Anything that speaks OSC drives Wwise events/RTPCs, no game engine.
  `pip install waapi-client python-osc` · `python osc2wwise.py --map /sensor/radar=Proximity -v`
- Wwise must be running with a project open and **Project > User Preferences > Enable Wwise Authoring API** ticked.
- Authoring by prompt: [BilkentAudio/Wwise-MCP](https://github.com/BilkentAudio/Wwise-MCP) — add it to Claude Code / Cursor next to the eir wiki MCP.
- Wiki: `tool.wwise`, `tool.osc2wwise`, `tool.wwise-mcp`.
