"""Add channels to FL Studio's channel rack from channel presets (.fst).

The scripting API can't add channels, but the bridge can make FL load a
channel preset, which adds a channel routed to a mixer track. FL names the
channel after the preset file, and its Python can't write binary files, so the
server writes the preset next to the bridge script under the wanted name.
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import Any

# Colors given to new channels and their mixer tracks, in turn
PALETTE = [
    "#E57373", "#F0A24B", "#E8D44D", "#8BC34A", "#4DB6AC",
    "#4FC3F7", "#7986CB", "#BA68C8", "#F06292", "#A1887F",
]

# Tools run in parallel threads, and two channels can have the same name, so
# the same preset file: one load at a time
_load_lock = threading.Lock()


def parse_color(color: str) -> tuple[int, int, int] | None:
    """(r, g, b) from "#RRGGBB" (or "RRGGBB"), or None if it isn't one."""
    match = re.fullmatch(r"#?([0-9a-fA-F]{6})", color.strip())
    if not match:
        return None
    value = int(match.group(1), 16)
    return value >> 16, (value >> 8) & 0xFF, value & 0xFF


def safe_file_stem(name: str) -> str:
    """`name` usable as a file name (it becomes the channel's name)."""
    stem = re.sub(r'[\\/:*?"<>|]+', "_", name).strip(" .")
    return stem or "Channel"


def fst_events(data: bytes) -> list[tuple[int, bytes]]:
    """(id, value) events of an FL state file: FLhd header, then FLdt events."""
    pos = 8 + int.from_bytes(data[4:8], "little") + 8  # skip FLhd, then FLdt and its size
    events = []
    while pos < len(data):
        event_id = data[pos]
        pos += 1
        if event_id < 192:
            # 1, 2 or 4 byte values below 64, 128 and 192
            size = 1 if event_id < 64 else 2 if event_id < 128 else 4
        else:
            size, shift = 0, 0
            while True:
                byte = data[pos]
                pos += 1
                size |= (byte & 0x7F) << shift
                shift += 7
                if byte < 0x80:
                    break
        events.append((event_id, data[pos:pos + size]))
        pos += size
    return events


def fst_bytes(header: bytes, events: list[tuple[int, bytes]]) -> bytes:
    """An FL state file from its FLhd header and (id, value) events."""
    body = bytearray()
    for event_id, value in events:
        body.append(event_id)
        if event_id >= 192:
            size = len(value)
            while True:
                byte = size & 0x7F
                size >>= 7
                body.append(byte | 0x80 if size else byte)
                if not size:
                    break
        body += value
    return header + b"FLdt" + len(body).to_bytes(4, "little") + bytes(body)


def bridge_paths(conn: Any) -> dict:
    """FL's Data/System folder and the bridge script's folder."""
    return conn.send_command("system.getPaths")


def load_preset(conn: Any, preset_data: bytes, stem: str, action: str,
                params: dict, timeout: float) -> dict:
    """Write `stem`.fst next to the bridge script and have the bridge load it with `action`."""
    paths = bridge_paths(conn)
    if not paths.get("success", False) and "error" in paths:
        return paths
    preset = Path(paths["script_dir"]) / f"{stem}.fst"
    with _load_lock:
        preset.write_bytes(preset_data)
        try:
            return conn.send_command(action, {**params, "preset": preset.name}, timeout=timeout)
        finally:
            preset.unlink(missing_ok=True)


def add_channel(conn: Any, preset_data: bytes, channel_name: str,
                mixer_track: int | None = None, color: str | None = None,
                timeout: float = 30.0) -> dict:
    """Add a channel from preset bytes; returns the bridge's response.

    The channel and its mixer track get `color` ("#RRGGBB"), or the next
    palette color.
    """
    rgb = parse_color(color) if color else None
    if color and rgb is None:
        return {"success": False, "error": f"color must be like #E57373 (got {color})"}
    stem = safe_file_stem(channel_name)
    params: dict = {}
    if mixer_track is not None:
        params["mixer_track"] = mixer_track
    # Big plugins can take a few seconds to load
    result = load_preset(conn, preset_data, stem, "channels.addFromPreset", params, timeout)
    if not result.get("success"):
        return result
    index, track = result["channel"], result["mixer_track"]

    # Loading also opens an empty window for the mixer track's first slot
    time.sleep(0.3)
    conn.send_command("ui.closeEmptySlotWindow",
                      {"mixer_track": track, "channel_name": result.get("name", "")})
    # FL opens the plugin window before the plugin draws in it, so it stays
    # empty: closing and reopening it shows the plugin
    conn.send_command("channels.showEditor", {"index": index, "show": False})
    conn.send_command("channels.showEditor", {"index": index, "show": True})

    if stem != channel_name and result.get("name") == stem:
        # The name had characters a file name can't hold: rename afterwards
        conn.send_command("channels.setName", {"index": index, "name": channel_name})
        result["name"] = channel_name
        if result.get("mixer_track_name") == stem:
            conn.send_command("mixer.setTrackName", {"track": track, "name": channel_name})
            result["mixer_track_name"] = channel_name

    r, g, b = rgb or parse_color(PALETTE[index % len(PALETTE)])
    conn.send_command("channels.setColor", {"index": index, "r": r, "g": g, "b": b})
    conn.send_command("mixer.setTrackColor", {"track": track, "r": r, "g": g, "b": b})
    result["color"] = f"#{r:02X}{g:02X}{b:02X}"
    return result
