"""Automation clip presets (.fst) for FL Studio.

The scripting API can't create automation clips, but FL's AutoTrack.fst
channel template adds one, like the other channel templates. The preset
written here adds its points (event 234, as in project files) and the link
to the automated control (a remote control event, 227). FL reads the link's
source as a channel index, so the clip must land at the index it was written
for: the bridge checks that.
"""

from __future__ import annotations

import struct

from fl_studio_mcp.utils.channel_presets import fst_bytes, fst_events

FST_AUTOMATION = 234
FST_REMOTE_CONTROL = 227

# Default header and trailer of the points data, as FL writes them for a
# plain clip (no LFO)
POINTS_HEADER = bytes.fromhex("01000000 40000000 00 04000000 03000000")
POINTS_TRAILER = bytes.fromhex(
    "01000000ffffffffffffffffffffffffffffffff800000008000000000000000"
    "800000000500000003000000010000000000000000000000000000000000f03f"
    "00000000000000000100000000000000fffffffffffffffffffffffffbb20000"
    "00000000000000000000000000000000"
)
# Remote control flags as FL saves them for automation clip links
REMOTE_FLAGS = (8, 0x1D5)


def clip_points(points: list[dict]) -> list[tuple[float, float, float]]:
    """(bars, value, tension) tuples from {"bars", "value", "tension"} dicts.

    Sorted by position, starting at 0: a clip starts at its first point.
    Raises ValueError on a bad point.
    """
    parsed = []
    for i, point in enumerate(points):
        try:
            bars, value = float(point["bars"]), float(point["value"])
            tension = float(point.get("tension", 0.0))
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ValueError(f'Point {i} must be like {{"bars": 2, "value": 0.5}}') from None
        if bars < 0:
            raise ValueError(f"Point {i}: bars can't be negative (got {bars})")
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"Point {i}: value must be between 0.0 and 1.0 (got {value})")
        if not -1.0 <= tension <= 1.0:
            raise ValueError(f"Point {i}: tension must be between -1 and 1 (got {tension})")
        parsed.append((bars, value, tension))
    # Stable: points at the same position keep their order (a jump)
    parsed.sort(key=lambda p: p[0])
    if len(parsed) < 2 or parsed[-1][0] == 0:
        raise ValueError("Give at least two points, the last one after the clip's start")
    if parsed[0][0] > 0:
        # Hold the first value from the clip's start
        parsed.insert(0, (0.0, parsed[0][1], 0.0))
    return parsed


def _tension_byte(tension: float, first: bool) -> int:
    """Last byte of a point: FL stores the tension's sign next to it."""
    if first:
        return 0
    return 0xFF if tension < 0 else 1 if tension > 0 else 2


def points_data(points: list[tuple[float, float, float]]) -> bytes:
    """Points data from (beat, value, tension) tuples sorted by beat, the first at 0."""
    data = bytearray(POINTS_HEADER + struct.pack("<I", len(points)))
    previous = 0.0
    for i, (beat, value, tension) in enumerate(points):
        # Positions are quarter notes after the previous point
        data += struct.pack("<ddf", beat - previous, value, tension)
        data += bytes([0, 0, 0, _tension_byte(tension, i == 0)])
        previous = beat
    return bytes(data + POINTS_TRAILER)


def automation_preset(template: bytes, points: list[tuple[float, float, float]],
                      channel_index: int, event_id: int) -> bytes:
    """FL's AutoTrack.fst template with points and a link to the control `event_id`.

    `channel_index` is the global index the new clip will get.
    """
    header = template[:8 + int.from_bytes(template[4:8], "little")]
    events = [(e, v) for e, v in fst_events(template)
              if e not in (FST_AUTOMATION, FST_REMOTE_CONTROL)]
    events.append((FST_AUTOMATION, points_data(points)))
    # Source (the clip, as a channel event ID), destination (the control)
    link = struct.pack("<IIIII", channel_index << 16, 0, event_id, *REMOTE_FLAGS)
    events.append((FST_REMOTE_CONTROL, link))
    return fst_bytes(header, events)
