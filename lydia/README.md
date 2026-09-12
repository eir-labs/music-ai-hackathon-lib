# Roland Project LYDIA — DIY toolkit

Roland's `LYDIA DIY Documentation` (standalone HTML, 13 MB) is at the kit table on a USB stick and summarised on the wiki as `tool.lydia-diy`.
The toolkit repo itself (`rfdl-project-Lydia-phase2-DIY_toolkit`) is provided by Roland — ask the Ch2 mentor for access.

Quick facts: Raspberry Pi 5 · 128×64 LCD · controls `enc1`–`enc5`, `enc1_sw`, `panel_sw1/2`, `foot_sw1/2` · UI defined in `ui_config.json` via the browser UI Editor · Pure Data talks to the runtime over OSC/UDP, values normalised 0–1 · regenerate Pd receivers with `pd_osc_recive_patch_generator.py --all-pages` after every UI change · set the Pi to X11, not Wayland, for Pd.
