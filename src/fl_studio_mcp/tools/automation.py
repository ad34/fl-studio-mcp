"""Automation clip tools for FL Studio."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP

TARGETS = ("plugin", "fx_mix", "mixer_volume", "mixer_pan", "channel_volume", "channel_pan")


def register_automation_tools(mcp: FastMCP) -> None:
    """Register automation clip tools with the MCP server."""
    from fl_studio_mcp.utils import automation, channel_presets
    from fl_studio_mcp.utils.connection import get_connection

    @mcp.tool()
    def fl_create_automation_clip(
        target: str,
        points: list[dict],
        track: int | None = None,
        slot: int | None = None,
        channel: int | None = None,
        param: int | None = None,
        name: str | None = None,
        color: str | None = None,
    ) -> str:
        """Create an automation clip that drives a plugin parameter or a mixer/channel control.

        The clip is added to the channel rack, linked to its control, with
        the given points. FL's API can't place clips: it does nothing until
        the user drags it from the channel rack onto a playlist track, at the
        bar where it should start. A control driven by two clips jumps between
        them: mute or delete the other one.

        Targets:
        - "plugin": a plugin parameter, of a mixer effect (track and slot) or
          of a channel's instrument (channel); param is its index
          (fl_find_plugin_params)
        - "fx_mix": an effect slot's Mix knob (track and slot)
        - "mixer_volume", "mixer_pan": a mixer track (track)
        - "channel_volume", "channel_pan": a channel (channel)

        Args:
            target: One of the targets above
            points: List of {"bars": float, "value": float, "tension": float}.
                bars: from the clip's start (0 = its first beat, 2.5 = two
                and a half bars in). value: 0.0-1.0 on the control's own scale,
                as fl_get_plugin_params shows it (mixer volume 0.8 = 0 dB, pan
                0.5 = center). tension (optional, -1 to 1): bends the segment
                that ends at this point; 0 (default) is a straight line, above
                0 the change comes early (fast, then slow), below 0 late;
                +-0.8 is already a strong curve. Two points at the same
                position make a jump.
            track: Mixer track (0 = Master) for mixer targets and mixer effects
            slot: Effect slot (0-9) for "fx_mix" and "plugin" on a mixer effect
            channel: Channel index (global) for channel targets and instruments
            param: Plugin parameter index for "plugin"
            name: Clip name (default: FL's, e.g. "Pro-Q 3 - Master - Band 1 Frequency")
            color: "#RRGGBB" for the clip (default: FL's)
        """
        if target not in TARGETS:
            return f"Error: target must be one of {', '.join(TARGETS)}"
        try:
            clip = automation.clip_points(points)
        except ValueError as e:
            return f"Error: {e}"
        rgb = channel_presets.parse_color(color) if color else None
        if color and rgb is None:
            return f"Error: color must be like #E57373 (got {color})"

        conn = get_connection()
        params = {"target": target, "track": track, "slot": slot, "channel": channel,
                  "param": param}
        info = conn.send_command(
            "automation.getTarget", {k: v for k, v in params.items() if v is not None})
        if not info.get("success", False) and "error" in info:
            return f"Error: {info['error']}"
        paths = channel_presets.bridge_paths(conn)
        if not paths.get("success", False) and "error" in paths:
            return f"Error: {paths['error']}"
        try:
            # FL's channel template for a new automation clip
            template = (Path(paths["data_system"]) / "AutoTrack.fst").read_bytes()
        except OSError as e:
            return f"Error: FL Studio's automation clip template is missing: {e}"
        beats_per_bar = info["beats_per_bar"]
        preset = automation.automation_preset(
            template, [(bars * beats_per_bar, value, tension) for bars, value, tension in clip],
            info["next_channel"], info["event_id"])

        clip_name = name or info["name"]
        result = channel_presets.load_preset(
            conn, preset, channel_presets.safe_file_stem(clip_name),
            "channels.addAutomationClip", {"expected_index": info["next_channel"]}, timeout=10.0)
        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"
        index = result["channel"]

        # Loading also opens an empty window for the mixer track's first slot
        time.sleep(0.3)
        conn.send_command("ui.closeEmptySlotWindow",
                          {"mixer_track": result["mixer_track"], "channel_name": result["name"]})
        if result["name"] != clip_name:
            # FL names the clip after the preset file
            conn.send_command("channels.setName", {"index": index, "name": clip_name})
        if rgb:
            r, g, b = rgb
            conn.send_command("channels.setColor", {"index": index, "r": r, "g": g, "b": b})
        return (f"Automation clip {index} '{clip_name}' created: {len(clip)} points over "
                f"{clip[-1][0]:g} bars, linked to {info['name']} (now {info['value_display']}). "
                "The API can't place clips: ask the user to drag it from the channel rack "
                "onto a playlist track, at the bar where it should start")
