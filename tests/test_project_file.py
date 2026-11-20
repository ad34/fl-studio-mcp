"""Reading automation clips from a project file (.flp)."""

import struct

import pytest

from fl_studio_mcp.utils import automation, project_file
from fl_studio_mcp.utils.channel_presets import fst_bytes


def _utf16(text: str) -> bytes:
    return (text + "\0").encode("utf-16-le")


def _playlist_item(position: int, index: int, length: int, track: int) -> bytes:
    """An 88-byte playlist record, as FL Studio 2026 saves them."""
    head = struct.pack("<IHHIHH", position, project_file.PATTERN_BASE, index, length,
                       project_file.PLAYLIST_LAST_TRACK - (track - 1), 0)
    return head + bytes(88 - len(head))


def _project(playlist: bytes | None = None) -> bytes:
    """A 3/4 project: a generator, then a clip on Pro-Q 3's param 2 placed at bar 3."""
    header = b"FLhd" + struct.pack("<IHHH", 6, 0, 2, 96)
    ticks_per_bar = 96 * 3
    if playlist is None:
        playlist = (_playlist_item(2 * ticks_per_bar, 1, 4 * ticks_per_bar, 5)
                    + _playlist_item(0, project_file.PATTERN_BASE + 1, ticks_per_bar, 1))
    events = [
        # FL 2025+ writes event 172 with 3 bytes: reading 4 would shift the rest
        (172, b"\x01\x01\x00"), (192, _utf16("FL Studio 2026")),
        (17, b"\x03"), (18, b"\x04"),
        (64, struct.pack("<H", 0)), (21, b"\x02"), (203, _utf16("Kick")),
        # Not the project's time signature: only the first one counts
        (18, b"\x38"),
        (64, struct.pack("<H", 1)), (21, b"\x05"), (203, _utf16("Cutoff sweep")),
        (234, automation.points_data([(0, 0.1, 0.0), (6, 0.9, 0.5)])),
        (227, struct.pack("<IIIII", 1 << 16, 0, 0x70008002, 8, 0x1D5)),
        # A peak controller's link: not a clip
        (227, struct.pack("<IIIII", 0x74828001, 0, 0x00020000, 8, 0x1D5)),
        (99, struct.pack("<H", 0)), (241, _utf16("Arrangement")),
        (203, _utf16("A mixer plugin")),
        (233, playlist),
    ]
    return fst_bytes(header, events)


def test_reads_clip_target_points_and_placement():
    result = project_file.read_automation_clips(_project())
    assert result["time_signature"] == "3/4"
    assert "warning" not in result
    assert result["clips"] == [{
        "channel": 1,
        "name": "Cutoff sweep",
        "targets": [{"kind": "plugin", "track": 0, "slot": 0, "param": 2}],
        "placements": [{"playlist_track": 5, "start_bar": 3.0, "length_bars": 4.0}],
        "length_bars": 2.0,
        "points": [{"bars": 0.0, "value": 0.1, "tension": 0.0},
                   {"bars": 2.0, "value": 0.9, "tension": 0.5}],
    }]


def test_unknown_playlist_format_warns():
    result = project_file.read_automation_clips(_project(playlist=bytes(50)))
    assert "placements are missing" in result["warning"]
    assert result["clips"][0]["placements"] == []


def test_rejects_other_files():
    with pytest.raises(ValueError, match="Not an FL Studio project"):
        project_file.read_automation_clips(b"RIFF....")


@pytest.mark.parametrize("event_id, expected", [
    (0x70008002, {"kind": "plugin", "track": 0, "slot": 0, "param": 2}),
    (0x72411F01, {"kind": "fx_mix", "track": 9, "slot": 1}),
    (0x70401F00, {"kind": "fx_enabled", "track": 1, "slot": 0}),
    (0x70C01FC0, {"kind": "mixer_volume", "track": 3}),
    (0x70C01FC1, {"kind": "mixer_pan", "track": 3}),
    (0x70C01FD9, {"kind": "eq_frequency", "track": 3, "band": 2}),
    (0x70C02005, {"kind": "send", "track": 3, "to_track": 5}),
    (0x004C80CD, {"kind": "plugin", "channel": 76, "param": 205}),
    (0x00020011, {"kind": "channel_volume_multiplier", "channel": 2}),
    (0x00500000, {"kind": "channel_volume", "channel": 80}),
    (0x40000005, {"kind": "tempo"}),
    # Older projects: mixer events from 0x2000 items, sends after the controls
    (0x21801FC1, {"kind": "mixer_pan", "track": 6}),
    (0x23C28004, {"kind": "plugin", "track": 15, "slot": 2, "param": 4}),
    (0x20401F45, {"kind": "send", "track": 1, "to_track": 5}),
    (0x60000000, {"kind": "other", "event_id": "0x60000000"}),
])
def test_describe_event(event_id, expected):
    assert project_file.describe_event(event_id) == expected
