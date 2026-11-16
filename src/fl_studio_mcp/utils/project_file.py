"""Read automation clips from FL Studio project files (.flp).

The scripting API can't read an automation clip's points or where clips sit
in the playlist, but the saved project has both. PyFLP can't parse FL Studio
2026 projects, so this reads the few events it needs directly. It sees the
project as it was last saved.
"""

from __future__ import annotations

import os
import platform
import struct

from fl_studio_mcp.utils.automation import FST_AUTOMATION, FST_REMOTE_CONTROL, read_points
from fl_studio_mcp.utils.channel_presets import fst_events

# Project events (same numbering as channel presets)
EV_CHANNEL_TYPE = 21
EV_TIME_SIG_NUM = 17
EV_TIME_SIG_DEN = 18
EV_NEW_CHANNEL = 64
EV_NEW_ARRANGEMENT = 99
EV_NAME_ANSI = 192
EV_NAME = 203
EV_PLAYLIST = 233
EV_ARRANGEMENT_NAME = 241
CHANNEL_TYPE_AUTOMATION = 5

# Playlist items: one record per clip; FL 21+ uses 88 bytes, older 60 or 32
PLAYLIST_ITEM_SIZES = (88, 60, 32)
PATTERN_BASE = 0x5000
# Tracks are stored reversed: track 1 is 499
PLAYLIST_LAST_TRACK = 499

# REC event IDs (FL's midi.py): channels, then mixer effects and tracks
REC_ITEM_RANGE = 0x10000
REC_CHANNEL_LAST = 0x1000 * REC_ITEM_RANGE
REC_PLUG_FIRST = 0x7000 * REC_ITEM_RANGE
REC_PLUG_LAST = REC_PLUG_FIRST + 0x8000 * REC_ITEM_RANGE
# Older projects keep mixer events at 0x2000 items, sends right after the
# effect controls instead of at 0x2000
REC_PLUG_FIRST_OLD = 0x2000 * REC_ITEM_RANGE
REC_PLUG_LAST_OLD = REC_PLUG_FIRST_OLD + 0x2000 * REC_ITEM_RANGE
REC_PLUGIN_BASE = 0x8000
REC_GLOBAL_FIRST = 0x4000 * REC_ITEM_RANGE
SLOTS_PER_TRACK = 64
CHANNEL_CONTROLS = {0: "volume", 1: "pan", 2: "filter_cutoff", 3: "filter_resonance",
                    4: "pitch", 16: "pan_offset", 17: "volume_multiplier",
                    18: "pitch_offset", 19: "filter_cutoff_offset",
                    20: "filter_resonance_offset"}
# Offsets from the effect slot's (or the track's slot 0) event ID
MIXER_CONTROLS = {0x1F00: "fx_enabled", 0x1F01: "fx_mix", 0x1FC0: "mixer_volume",
                  0x1FC1: "mixer_pan", 0x1FC2: "stereo_separation"}
GLOBAL_CONTROLS = {0: "main_volume", 1: "main_shuffle", 2: "main_pitch", 5: "tempo"}


def describe_event(event_id: int) -> dict:
    """What a REC event ID drives, e.g. {"kind": "plugin", "track": 0, "slot": 0, "param": 2}."""
    old = REC_PLUG_FIRST_OLD <= event_id < REC_PLUG_LAST_OLD
    if old or REC_PLUG_FIRST <= event_id < REC_PLUG_LAST:
        base = REC_PLUG_FIRST_OLD if old else REC_PLUG_FIRST
        item, offset = (event_id - base) >> 16, event_id & 0xFFFF
        track, slot = divmod(item, SLOTS_PER_TRACK)
        if offset >= REC_PLUGIN_BASE:
            return {"kind": "plugin", "track": track, "slot": slot,
                    "param": offset - REC_PLUGIN_BASE}
        if offset in (0x1F00, 0x1F01):
            return {"kind": MIXER_CONTROLS[offset], "track": track, "slot": slot}
        if offset in MIXER_CONTROLS:
            return {"kind": MIXER_CONTROLS[offset], "track": track}
        if 0x1FD0 <= offset < 0x1FD0 + 24:
            band_control, band = divmod(offset - 0x1FD0, 8)
            return {"kind": f"eq_{('gain', 'frequency', 'bandwidth')[band_control]}",
                    "track": track, "band": band + 1}
        sends = 0x1F40 if old else 0x2000
        if sends <= offset < sends + (0x80 if old else 0x200):
            return {"kind": "send", "track": track, "to_track": offset - sends}
    elif 0 <= event_id < REC_CHANNEL_LAST:
        channel, offset = event_id >> 16, event_id & 0xFFFF
        if offset >= REC_PLUGIN_BASE:
            return {"kind": "plugin", "channel": channel, "param": offset - REC_PLUGIN_BASE}
        if offset in CHANNEL_CONTROLS:
            return {"kind": f"channel_{CHANNEL_CONTROLS[offset]}", "channel": channel}
    elif REC_GLOBAL_FIRST <= event_id < REC_GLOBAL_FIRST + REC_ITEM_RANGE:
        control = GLOBAL_CONTROLS.get(event_id - REC_GLOBAL_FIRST)
        if control:
            return {"kind": control}
    return {"kind": "other", "event_id": f"0x{event_id:08X}"}


def _playlist_items(data: bytes) -> tuple[int, list[bytes]]:
    """Record size and records of a playlist event, or (0, []) if the format is unknown."""
    for size in PLAYLIST_ITEM_SIZES:
        if data and len(data) % size == 0:
            items = [data[i:i + size] for i in range(0, len(data), size)]
            if all(item[4:6] == PATTERN_BASE.to_bytes(2, "little") for item in items):
                return size, items
    return 0, []


def read_automation_clips(data: bytes) -> dict:
    """Automation clips of a project: targets, points and playlist placements.

    Positions are in bars from 1 (placements) or from the clip's start
    (points), following the project's time signature.
    """
    if data[:4] != b"FLhd":
        raise ValueError("Not an FL Studio project file")
    ppq = struct.unpack_from("<H", data, 12)[0] or 96
    numerator, denominator = 4, 4
    clips: dict[int, dict] = {}
    links: list[tuple[int, int]] = []
    placements: list[tuple[str, bytes]] = []
    channel = None
    arrangement = "Arrangement"
    unknown_playlist = False
    # Only the project's own time signature, the first one in the file
    seen_numerator = seen_denominator = False

    for event_id, value in fst_events(data):
        if event_id == EV_TIME_SIG_NUM and not seen_numerator:
            seen_numerator = True
            numerator = value[0] if 1 <= value[0] <= 16 else numerator
        elif event_id == EV_TIME_SIG_DEN and not seen_denominator:
            seen_denominator = True
            denominator = value[0] if value[0] in (2, 4, 8, 16) else denominator
        elif event_id == EV_NEW_CHANNEL:
            channel = int.from_bytes(value, "little")
        elif event_id == EV_CHANNEL_TYPE and channel is not None:
            if value[0] == CHANNEL_TYPE_AUTOMATION:
                clips[channel] = {"channel": channel, "name": None, "points": []}
        elif event_id in (EV_NAME, EV_NAME_ANSI) and channel in clips:
            if clips[channel]["name"] is None:
                text = value.decode("utf-16-le" if event_id == EV_NAME else "cp1252", "replace")
                clips[channel]["name"] = text.rstrip("\0")
        elif event_id == FST_AUTOMATION and channel in clips:
            clips[channel]["points"] = read_points(value)
        elif event_id == FST_REMOTE_CONTROL and len(value) >= 12:
            source, _, destination = struct.unpack_from("<III", value)
            links.append((source, destination))
        elif event_id == EV_NEW_ARRANGEMENT:
            # Arrangements come after the channels: stop reading channel events
            channel = None
            arrangement = f"Arrangement {int.from_bytes(value, 'little') + 1}"
        elif event_id == EV_ARRANGEMENT_NAME:
            arrangement = value.decode("utf-16-le", "replace").rstrip("\0") or arrangement
        elif event_id == EV_PLAYLIST:
            size, items = _playlist_items(value)
            unknown_playlist |= bool(value) and not size
            placements += [(arrangement, item) for item in items]

    beats_per_bar = 4 * numerator / denominator
    ticks_per_bar = ppq * beats_per_bar
    arrangements = {name for name, _ in placements}
    for clip in clips.values():
        clip["targets"] = [describe_event(dest) for source, dest in links
                           if source == clip["channel"] << 16]
        clip["placements"] = []
        points = clip.pop("points")
        clip["length_bars"] = round(points[-1][0] / beats_per_bar, 4) if points else 0
        clip["points"] = [{"bars": round(beat / beats_per_bar, 4), "value": round(value, 4),
                           "tension": round(tension, 3)} for beat, value, tension in points]
    for name, item in placements:
        position, _base, index, length, reversed_track = struct.unpack_from("<IHHIH", item)
        if index < PATTERN_BASE and index in clips:
            placement = {
                "playlist_track": PLAYLIST_LAST_TRACK - reversed_track + 1,
                "start_bar": round(position / ticks_per_bar + 1, 4),
                "length_bars": round(length / ticks_per_bar, 4),
            }
            if len(arrangements) > 1:
                placement["arrangement"] = name
            clips[index]["placements"].append(placement)
    result: dict = {
        "time_signature": f"{numerator}/{denominator}",
        "clips": sorted(clips.values(), key=lambda c: c["channel"]),
    }
    if unknown_playlist:
        result["warning"] = "The playlist format is unknown: placements are missing"
    return result


def find_project_path(file_name: str) -> str | None:
    """Full path of a project FL opened, from its recent files list (Windows only).

    FL's window title only has the file name.
    """
    if platform.system() != "Windows":
        return None
    import winreg

    candidates = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Image-Line") as root:
            versions = []
            i = 0
            while True:
                try:
                    versions.append(winreg.EnumKey(root, i))
                except OSError:
                    break
                i += 1
    except OSError:
        return None
    # Newest FL Studio first ("FL Studio 26" before "FL Studio 25")
    for version in sorted((v for v in versions if v.startswith("FL Studio")), reverse=True):
        entries = []
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                rf"Software\Image-Line\{version}\MRU") as key:
                i = 0
                while True:
                    try:
                        name, value, _type = winreg.EnumValue(key, i)
                    except OSError:
                        break
                    entries.append((name, str(value)))
                    i += 1
        except OSError:
            continue
        # Values are named 0, 1, 2... from the most recent
        entries.sort(key=lambda e: int(e[0]) if e[0].isdigit() else 1 << 30)
        candidates += [value for _name, value in entries]
    for path in candidates:
        if os.path.basename(path).lower() == file_name.lower() and os.path.isfile(path):
            return path
    return None
