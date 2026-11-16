"""Automation clip tools for FL Studio."""

from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP

TARGETS = ("plugin", "fx_mix", "mixer_volume", "mixer_pan", "channel_volume", "channel_pan")


def register_automation_tools(mcp: FastMCP) -> None:
    """Register automation clip tools with the MCP server."""
    from fl_studio_mcp.utils import automation, channel_presets, project_file
    from fl_studio_mcp.utils.connection import get_connection
    from fl_studio_mcp.utils.fl_trigger import fl_project_file

    @mcp.tool()
    def fl_create_automation_clip(
        target: str,
        points: list[dict] | None = None,
        shape: dict | None = None,
        track: int | None = None,
        slot: int | None = None,
        channel: int | None = None,
        param: int | None = None,
        name: str | None = None,
        color: str | None = None,
    ) -> str:
        """Create an automation clip that drives a plugin parameter or a mixer/channel control.

        The clip is added to the channel rack, linked to its control, with
        the given points or a ready-made shape. FL's API can't place clips: it does nothing until
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

        Shapes (give shape instead of points), all with "bars" (the clip's
        length) and values 0.0-1.0:
        - {"type": "ramp", "bars": 8, "from": 0.2, "to": 0.9, "tension": 0}
        - {"type": "sine" | "triangle" | "saw" | "square", "bars": 8,
          "low": 0.3, "high": 0.7, "period": 1, "invert": false}: period is
          bars per cycle (0.25 = a beat in 4/4). The sine starts at its middle
          going up, the triangle and saw at low, the square at high; invert
          flips them
        - {"type": "pump", "bars": 8, "low": 0.2, "high": 0.8, "period": 0.25,
          "release": 0.5, "tension": 0.5}: a sidechain-like duck to low at each
          period's start, back up to high over `release` of the period

        Args:
            target: One of the targets above
            shape: A ready-made shape (see above), instead of points
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
        if (points is None) == (shape is None):
            return "Error: give either points or a shape"
        try:
            clip = automation.clip_points(
                automation.shape_points(shape) if shape is not None else points)
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

    @mcp.tool()
    def fl_get_automation_clips(project_path: str | None = None,
                                include_points: bool = True) -> dict:
        """List the project's automation clips: what each drives, its points, where it is placed.

        Read from the saved project file, since the API can't read clips: it
        shows the project as last saved, so save first (fl_save_project) to
        include recent changes. Without project_path it reads the project open
        in FL (Windows). A clip with no placements isn't in the playlist and
        does nothing; two clips on the same target fight over it.

        Targets: "plugin" (track and slot for a mixer effect, or channel for
        an instrument, plus param), "fx_mix" and "fx_enabled" (track, slot),
        "mixer_volume", "mixer_pan", "stereo_separation", "eq_gain",
        "eq_frequency", "eq_bandwidth", "send" (track), "channel_volume",
        "channel_pan", "channel_pitch"... (channel), "tempo". Points have the
        form fl_create_automation_clip takes, so a clip can be recreated with
        changes. In targets, track is a mixer track; placements give the
        playlist_track (from 1), start_bar (from 1) and length_bars.

        Args:
            project_path: A .flp file (default: the project open in FL)
            include_points: False to leave out the points (just their count)
        """
        from_fl = project_path is None
        if from_fl:
            name = fl_project_file()
            if not name:
                return {"error": "No saved project is open in FL Studio (or not on Windows): "
                                 "save it, or give project_path"}
            project_path = project_file.find_project_path(name)
            if not project_path:
                return {"error": f"Couldn't find where '{name}' is saved: give project_path"}
        try:
            data = Path(project_path).read_bytes()
            result = project_file.read_automation_clips(data)
        except (OSError, ValueError) as e:
            return {"error": f"Can't read {project_path}: {e}"}
        if not include_points:
            for clip in result["clips"]:
                clip["point_count"] = len(clip.pop("points"))
        saved = datetime.fromtimestamp(os.path.getmtime(project_path))
        response = {"project_file": project_path,
                    "saved_at": saved.isoformat(timespec="seconds"), **result}
        if from_fl:
            state = get_connection().send_command("project.getState")
            if state.get("unsaved_changes"):
                note = ("FL Studio has unsaved changes, missing here: save "
                        "(fl_save_project) and read again")
                response["warning"] = (f"{response['warning']}. {note}"
                                       if "warning" in response else note)
        return response
