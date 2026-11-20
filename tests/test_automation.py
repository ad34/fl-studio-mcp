"""Automation clip presets: points, shapes and the preset FL loads."""

import hashlib
import struct

import pytest

from fl_studio_mcp.utils import automation
from fl_studio_mcp.utils.channel_presets import fst_bytes, fst_events

# A minimal channel template: FLhd header, then a name and a stale link
HEADER = b"FLhd" + struct.pack("<IHHH", 6, 0, 1, 96)
TEMPLATE = fst_bytes(HEADER, [(21, b"\x05"), (192, b"Auto clip\0"), (227, b"\0" * 20)])


def test_points_data_matches_clips_checked_in_fl():
    # Both clips were loaded in FL Studio 2026 and drove Pro-Q 3 as drawn
    # (sampled during playback): any change to these bytes needs a new check
    straight = automation.points_data([(0, 0.2, 0.0), (16, 0.9, 0.0), (32, 0.2, 0.0),
                                       (40, 0.5, 0.0)])
    curved = automation.points_data([(0, 0.2, 0.0), (16, 0.8, 0.8), (32, 0.2, -0.8)])
    assert hashlib.sha256(straight).hexdigest() == (
        "31f89cd1df45844f0cd5c19763595e34620a1725b48d5eec81fb597de3acfd58")
    assert hashlib.sha256(curved).hexdigest() == (
        "a1f1685c380c9e81e102d4e10bf56c47ac18825e47dd8b302bc047d5edc216aa")


def test_fst_events_reads_event_172_as_3_bytes():
    data = fst_bytes(HEADER, [(172, b"\x01\x01\x00"), (192, b"Name\0"), (21, b"\x05")])
    assert fst_events(data) == [(172, b"\x01\x01\x00"), (192, b"Name\0"), (21, b"\x05")]


def test_points_data_layout():
    data = automation.points_data([(0, 0.25, 0.0), (4, 1.0, -0.5), (6, 0.0, 0.5), (8, 0.5, 0.0)])
    assert data.startswith(automation.POINTS_HEADER)
    assert data.endswith(automation.POINTS_TRAILER)
    assert struct.unpack_from("<I", data, 17)[0] == 4
    # Positions are deltas; the last byte carries the tension's sign
    assert struct.unpack_from("<ddf", data, 21 + 24) == (4.0, 1.0, -0.5)
    assert [data[21 + 24 * i + 23] for i in range(4)] == [0, 0xFF, 1, 2]
    assert automation.read_points(data) == [(0, 0.25, 0.0), (4, 1.0, -0.5), (6, 0.0, 0.5),
                                            (8, 0.5, 0.0)]


def test_automation_preset_replaces_link_and_adds_points():
    preset = automation.automation_preset(TEMPLATE, [(0, 0.1, 0.0), (8, 0.9, 0.0)], 6, 0x70008002)
    assert preset.startswith(HEADER)
    events = fst_events(preset)
    links = [v for e, v in events if e == automation.FST_REMOTE_CONTROL]
    assert links == [struct.pack("<IIIII", 6 << 16, 0, 0x70008002, 8, 0x1D5)]
    points = [v for e, v in events if e == automation.FST_AUTOMATION]
    assert automation.read_points(points[0]) == [(0, 0.1, 0.0), (8, 0.9, 0.0)]
    assert (192, b"Auto clip\0") in events


def test_clip_points_sorts_and_starts_at_zero():
    points = automation.clip_points([{"bars": 4, "value": 1}, {"bars": 2, "value": 0.5,
                                                               "tension": -0.3}])
    assert points == [(0.0, 0.5, 0.0), (2.0, 0.5, -0.3), (4.0, 1.0, 0.0)]


@pytest.mark.parametrize("points, message", [
    ([{"bars": 0, "value": 1.5}, {"bars": 1, "value": 0}], "value must be between"),
    ([{"bars": -1, "value": 0}, {"bars": 1, "value": 0}], "can't be negative"),
    ([{"bars": 0, "value": 0, "tension": 2}, {"bars": 1, "value": 0}], "tension"),
    ([{"bars": 0, "value": 0}], "at least two points"),
    ([{"value": 0}, {"bars": 1, "value": 0}], "must be like"),
    (["x", "y"], "must be like"),
])
def test_clip_points_rejects(points, message):
    with pytest.raises(ValueError, match=message):
        automation.clip_points(points)


def _levels(shape):
    return [(p["bars"], p["value"]) for p in automation.shape_points(shape)]


def test_ramp():
    assert automation.shape_points({"type": "ramp", "bars": 8, "from": 0.2, "to": 0.9,
                                    "tension": 0.5}) == [
        {"bars": 0.0, "value": 0.2}, {"bars": 8.0, "value": 0.9, "tension": 0.5}]


def test_periodic_shapes():
    assert _levels({"type": "triangle", "bars": 2, "low": 0.2, "high": 0.8}) == [
        (0, 0.2), (0.5, 0.8), (1, 0.2), (1.5, 0.8), (2, 0.2)]
    # The saw and the square jump back at each cycle: two points, same position
    assert _levels({"type": "saw", "bars": 2}) == [(0, 0), (1, 1), (1, 0), (2, 1)]
    assert _levels({"type": "square", "bars": 1, "period": 0.5}) == [
        (0, 1), (0.25, 1), (0.25, 0), (0.5, 0), (0.5, 1), (0.75, 1), (0.75, 0), (1, 0)]
    sine = _levels({"type": "sine", "bars": 1, "low": 0.3, "high": 0.7})
    assert len(sine) == automation.SINE_STEPS + 1
    assert sine[0] == (0, 0.5) and sine[4] == (0.25, 0.7) and sine[12] == (0.75, 0.3)
    inverted = _levels({"type": "sine", "bars": 1, "low": 0.3, "high": 0.7, "invert": True})
    assert inverted[4] == (0.25, 0.3)


def test_pump_ducks_each_period():
    points = automation.shape_points({"type": "pump", "bars": 0.5, "low": 0.2, "high": 0.8})
    assert [(p["bars"], p["value"], p["tension"]) for p in points] == [
        (0, 0.2, 0), (0.125, 0.8, 0.5), (0.25, 0.8, 0), (0.25, 0.2, 0), (0.375, 0.8, 0.5),
        (0.5, 0.8, 0)]


def test_shape_cut_mid_cycle_ends_on_the_clip_length():
    assert _levels({"type": "triangle", "bars": 1.25}) == [
        (0, 0), (0.5, 1), (1, 0), (1.25, 0.5)]


def test_shapes_make_valid_clips():
    for kind in automation.SHAPES:
        points = automation.clip_points(automation.shape_points({"type": kind, "bars": 3.3}))
        assert points[0][0] == 0 and points[-1][0] == pytest.approx(3.3)


@pytest.mark.parametrize("shape, message", [
    ({"type": "wobble", "bars": 4}, "type must be one of"),
    ({"type": "sine"}, "more than 0"),
    ({"type": "sine", "bars": 4, "period": 0}, "more than 0"),
    ({"type": "sine", "bars": 1000, "period": 0.01}, "Too many points"),
    ({"type": "ramp", "bars": 4, "to": 1.5}, "between 0 and 1"),
    ({"type": "pump", "bars": 4, "release": "fast"}, "must be a number"),
    ("sine", "must be like"),
])
def test_shape_rejects(shape, message):
    with pytest.raises(ValueError, match=message):
        automation.shape_points(shape)
