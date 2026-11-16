"""Automation clip presets (.fst) for FL Studio.

The scripting API can't create automation clips, but FL's AutoTrack.fst
channel template adds one, like the other channel templates. The preset
written here adds its points (event 234, as in project files) and the link
to the automated control (a remote control event, 227). FL reads the link's
source as a channel index, so the clip must land at the index it was written
for: the bridge checks that.
"""

from __future__ import annotations

import math
import struct

from fl_studio_mcp.utils.channel_presets import fst_bytes, fst_events

FST_AUTOMATION = 234
FST_REMOTE_CONTROL = 227

SHAPES = ("ramp", "sine", "triangle", "saw", "square", "pump")
# More points than this is a mistake (a period far too short for the length)
MAX_POINTS = 2000
# Straight segments per sine cycle: off by under 2% of the swing
SINE_STEPS = 16

# One cycle of each periodic shape: (phase 0-1, level 0-1 between low and
# high, tension). A cycle that doesn't end where the next starts jumps.
_CYCLES = {
    "sine": [(k / SINE_STEPS, 0.5 + 0.5 * math.sin(2 * math.pi * k / SINE_STEPS), 0.0)
             for k in range(SINE_STEPS + 1)],
    "triangle": [(0.0, 0.0, 0.0), (0.5, 1.0, 0.0), (1.0, 0.0, 0.0)],
    "saw": [(0.0, 0.0, 0.0), (1.0, 1.0, 0.0)],
    "square": [(0.0, 1.0, 0.0), (0.5, 1.0, 0.0), (0.5, 0.0, 0.0), (1.0, 0.0, 0.0)],
}

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


def _number(shape: dict, key: str, default: float, low: float, high: float) -> float:
    try:
        value = float(shape.get(key, default))
    except (TypeError, ValueError):
        raise ValueError(f"shape {key} must be a number") from None
    if not low <= value <= high:
        raise ValueError(f"shape {key} must be between {low:g} and {high:g} (got {value:g})")
    return value


def shape_points(shape: dict) -> list[dict]:
    """Points ({"bars", "value", "tension"}) drawing a ready-made shape.

    shape: {"type": ..., "bars": clip length, ...}; see SHAPES and the
    fl_create_automation_clip docs for each type's keys. Raises ValueError.
    """
    if not isinstance(shape, dict):
        raise ValueError('shape must be like {"type": "sine", "bars": 8}')
    kind = shape.get("type")
    if kind not in SHAPES:
        raise ValueError(f"shape type must be one of {', '.join(SHAPES)}")
    bars = _number(shape, "bars", 0.0, 0.0, 10000.0)
    if bars <= 0:
        raise ValueError("shape bars (the clip's length) must be more than 0")
    if kind == "ramp":
        start = _number(shape, "from", 0.0, 0.0, 1.0)
        end = _number(shape, "to", 1.0, 0.0, 1.0)
        tension = _number(shape, "tension", 0.0, -1.0, 1.0)
        return [{"bars": 0.0, "value": start}, {"bars": bars, "value": end, "tension": tension}]

    low = _number(shape, "low", 0.0, 0.0, 1.0)
    high = _number(shape, "high", 1.0, 0.0, 1.0)
    period = _number(shape, "period", 0.25 if kind == "pump" else 1.0, 0.0, 10000.0)
    if period <= 0:
        raise ValueError("shape period (bars per cycle) must be more than 0")
    if kind == "pump":
        # Ducks at each period's start, then comes back up: fast, then slow
        release = _number(shape, "release", 0.5, 0.01, 1.0)
        tension = _number(shape, "tension", 0.5, -1.0, 1.0)
        cycle = [(0.0, 0.0, 0.0), (release, 1.0, tension), (1.0, 1.0, 0.0)]
    else:
        cycle = _CYCLES[kind]
    invert = bool(shape.get("invert", False))
    if math.ceil(bars / period - 1e-9) * len(cycle) > MAX_POINTS:
        raise ValueError(f"Too many points (over {MAX_POINTS}): use a longer period "
                         "or a shorter clip")

    points: list[dict] = []

    def add(position: float, level: float, tension: float) -> None:
        level = 1.0 - level if invert else level
        value = round(low + (high - low) * level, 6)
        last = points[-1] if points else None
        # Skip a point that repeats the previous one (cycles that join up)
        if last and abs(last["bars"] - position) < 1e-9 and last["value"] == value:
            return
        points.append({"bars": round(position, 6), "value": value, "tension": tension})

    start = 0.0
    while start < bars - 1e-9:
        previous = None
        for phase, level, tension in cycle:
            position = start + phase * period
            if position > bars + 1e-9:
                # The clip ends mid-segment: end it there, on a straight line
                p0, l0 = previous
                fraction = (bars - start - p0 * period) / ((phase - p0) * period)
                add(bars, l0 + (level - l0) * fraction, 0.0)
                break
            add(position, level, tension)
            previous = (phase, level)
        start += period
    return points


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


def read_points(data: bytes) -> list[tuple[float, float, float]]:
    """(beat, value, tension) tuples from points data (event 234), beats from the clip's start."""
    if len(data) < len(POINTS_HEADER) + 4:
        return []
    count = struct.unpack_from("<I", data, len(POINTS_HEADER))[0]
    offset = len(POINTS_HEADER) + 4
    points, beat = [], 0.0
    for _ in range(count):
        if offset + 24 > len(data):
            break
        delta, value, tension = struct.unpack_from("<ddf", data, offset)
        beat += delta
        points.append((beat, value, tension))
        offset += 24
    return points


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
