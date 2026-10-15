# name=FL Studio MCP Controller
# url=https://github.com/karl-andres/fl-studio-mcp
# supportedDevices=FL Studio MCP

"""
FL Studio MIDI Controller Script for MCP Integration.

This script runs inside FL Studio and receives MIDI trigger messages from the
MCP server. When triggered, it reads a command from a JSON file, executes the
corresponding FL Studio API function, and writes the response to another JSON file.

Communication flow:
1. MCP server writes command to mcp_command.json
2. MCP server sends MIDI note 127 (trigger)
3. This script receives the trigger via OnMidiMsg()
4. Script reads command JSON, executes FL Studio API
5. Script writes response to mcp_response.json
6. MCP server reads response
"""

import json
import os
import sys
from pathlib import Path

# FL Studio API modules (available when running inside FL Studio)
import arrangement
import channels
import device
import general
import midi
import mixer
import patterns
import playlist
import plugins
import transport
import ui


def _get_script_dir() -> Path:
    """Get the script directory path.

    FL Studio's Python environment doesn't support __file__, so we construct
    the path based on the platform's standard FL Studio settings location.
    """
    if sys.platform == "darwin":
        # macOS
        base = Path.home() / "Documents" / "Image-Line" / "FL Studio" / "Settings"
    elif sys.platform == "win32":
        # Windows
        userprofile = os.environ.get("USERPROFILE", "~")
        base = Path(userprofile) / "Documents" / "Image-Line" / "FL Studio" / "Settings"
    else:
        # Linux (unlikely but handle it)
        base = Path.home() / "Documents" / "Image-Line" / "FL Studio" / "Settings"

    return base / "Hardware" / "FLStudioMCP"


# File paths for JSON communication
SCRIPT_DIR = _get_script_dir()
COMMAND_FILE = SCRIPT_DIR / "mcp_command.json"
RESPONSE_FILE = SCRIPT_DIR / "mcp_response.json"

# MIDI trigger note
TRIGGER_NOTE = 127


def OnInit():
    """Called when the script is loaded."""
    print("FL Studio MCP Controller initialized")
    print(f"Command file: {COMMAND_FILE}")
    print(f"Response file: {RESPONSE_FILE}")


def OnDeInit():
    """Called when the script is unloaded."""
    print("FL Studio MCP Controller deinitialized")


def OnMidiMsg(event):
    """Called when a MIDI message is received."""
    # Check for trigger note (Note On, note 127)
    if event.midiId == 0x90 and event.data1 == TRIGGER_NOTE and event.data2 > 0:
        execute_pending_command()
        event.handled = True


def OnIdle():
    """Called periodically when FL Studio is idle."""
    pass  # Required FL Studio API hook; no polling needed


def execute_pending_command():
    """Read command from JSON file, execute it, and write response."""
    response = {"success": False, "error": None}

    try:
        # Read command file
        if not COMMAND_FILE.exists():
            response["error"] = "No command file found"
            write_response(response)
            return

        command_text = COMMAND_FILE.read_text()
        command = json.loads(command_text)

        action = command.get("action", "")
        params = command.get("params", {})

        # Execute command and get result
        result = dispatch_command(action, params)
        response = {"success": True, **result}

    except json.JSONDecodeError as e:
        response["error"] = f"Invalid JSON in command file: {e}"
    except Exception as e:
        response["error"] = f"Error executing command: {e}"

    write_response(response)


def write_response(response: dict):
    """Write response to JSON file."""
    try:
        RESPONSE_FILE.write_text(json.dumps(response, indent=2))
    except Exception as e:
        print(f"Error writing response: {e}")


def dispatch_command(action: str, params: dict) -> dict:
    """Route command to appropriate handler and return result."""

    # Transport commands
    if action == "transport.start":
        return handle_transport_start()
    elif action == "transport.stop":
        return handle_transport_stop()
    elif action == "transport.record":
        return handle_transport_record()
    elif action == "transport.getStatus":
        return handle_transport_get_status()
    elif action == "transport.setPosition":
        return handle_transport_set_position(params)
    elif action == "transport.getLength":
        return handle_transport_get_length()
    elif action == "transport.setLoopMode":
        return handle_transport_set_loop_mode(params)
    elif action == "transport.setPlaybackSpeed":
        return handle_transport_set_playback_speed(params)
    elif action == "transport.setTempo":
        return handle_transport_set_tempo(params)

    # Project commands
    elif action == "project.getState":
        return handle_project_get_state()
    elif action == "project.save":
        return handle_project_save(params)
    elif action == "project.setTimeSignature":
        return handle_project_set_time_signature(params)

    # Undo history
    elif action == "undo.getState":
        return handle_undo_get_state()
    elif action == "undo.savePoint":
        return handle_undo_save_point(params)
    elif action == "undo.move":
        return handle_undo_move(params)

    # UI commands
    elif action == "ui.openPianoRoll":
        return handle_ui_open_piano_roll(params)
    elif action == "ui.closePianoRoll":
        return handle_ui_close_piano_roll()

    # Pattern commands
    elif action == "patterns.getCurrent":
        return handle_patterns_get_current()
    elif action == "patterns.select":
        return handle_patterns_select(params)
    elif action == "patterns.create":
        return handle_patterns_create(params)
    elif action == "patterns.getAll":
        return handle_patterns_get_all()
    elif action == "patterns.getInfo":
        return handle_patterns_get_info(params)
    elif action == "patterns.set":
        return handle_patterns_set(params)
    elif action == "patterns.clone":
        return handle_patterns_clone(params)

    # Arrangement / playlist commands
    elif action == "arrangement.getMarkers":
        return handle_arrangement_get_markers()
    elif action == "arrangement.addMarkers":
        return handle_arrangement_add_markers(params)
    elif action == "arrangement.getMarkerSections":
        return handle_arrangement_get_marker_sections()
    elif action == "arrangement.setSelection":
        return handle_arrangement_set_selection(params)
    elif action == "arrangement.clearSelection":
        return handle_arrangement_clear_selection()
    elif action == "arrangement.deleteMarker":
        return handle_arrangement_delete_marker(params)
    elif action == "playlist.getTracks":
        return handle_playlist_get_tracks(params)
    elif action == "playlist.setTrack":
        return handle_playlist_set_track(params)

    # Mixer commands
    elif action == "mixer.getTrackCount":
        return handle_mixer_get_track_count()
    elif action == "mixer.getTrackInfo":
        return handle_mixer_get_track_info(params)
    elif action == "mixer.getAllTracks":
        return handle_mixer_get_all_tracks(params)
    elif action == "mixer.setTrackVolume":
        return handle_mixer_set_track_volume(params)
    elif action == "mixer.setTrackPan":
        return handle_mixer_set_track_pan(params)
    elif action == "mixer.muteTrack":
        return handle_mixer_mute_track(params)
    elif action == "mixer.soloTrack":
        return handle_mixer_solo_track(params)
    elif action == "mixer.armTrack":
        return handle_mixer_arm_track(params)
    elif action == "mixer.setTrackName":
        return handle_mixer_set_track_name(params)
    elif action == "mixer.setTrackColor":
        return handle_mixer_set_track_color(params)
    elif action == "mixer.setStereoSep":
        return handle_mixer_set_stereo_sep(params)
    elif action == "mixer.getTrackFx":
        return handle_mixer_get_track_fx(params)
    elif action == "mixer.setSlotMix":
        return handle_mixer_set_slot_mix(params)
    elif action == "mixer.setSlotEnabled":
        return handle_mixer_set_slot_enabled(params)
    elif action == "mixer.getRouting":
        return handle_mixer_get_routing(params)
    elif action == "mixer.setRoute":
        return handle_mixer_set_route(params)
    elif action == "mixer.loadPlugin":
        return handle_mixer_load_plugin(params)
    elif action == "mixer.getPeaks":
        return handle_mixer_get_peaks()

    # Channel commands
    elif action == "channels.getCount":
        return handle_channels_get_count(params)
    elif action == "channels.getInfo":
        return handle_channels_get_info(params)
    elif action == "channels.getAll":
        return handle_channels_get_all()
    elif action == "channels.getSelected":
        return handle_channels_get_selected()
    elif action == "channels.select":
        return handle_channels_select(params)
    elif action == "channels.selectOne":
        return handle_channels_select_one(params)
    elif action == "channels.triggerNote":
        return handle_channels_trigger_note(params)
    elif action == "channels.setVolume":
        return handle_channels_set_volume(params)
    elif action == "channels.setPan":
        return handle_channels_set_pan(params)
    elif action == "channels.mute":
        return handle_channels_mute(params)
    elif action == "channels.solo":
        return handle_channels_solo(params)
    elif action == "channels.setName":
        return handle_channels_set_name(params)
    elif action == "channels.setColor":
        return handle_channels_set_color(params)
    elif action == "channels.routeToMixer":
        return handle_channels_route_to_mixer(params)
    elif action == "channels.addFromPreset":
        return handle_channels_add_from_preset(params)
    elif action == "channels.showEditor":
        return handle_channels_show_editor(params)
    elif action == "ui.closeEmptySlotWindow":
        return handle_ui_close_empty_slot_window(params)
    elif action == "system.getPaths":
        return handle_system_get_paths()

    # Step sequencer commands
    elif action == "channels.getGridBit":
        return handle_channels_get_grid_bit(params)
    elif action == "channels.setGridBit":
        return handle_channels_set_grid_bit(params)
    elif action == "channels.getStepSequence":
        return handle_channels_get_step_sequence(params)
    elif action == "channels.setStepSequence":
        return handle_channels_set_step_sequence(params)

    # Plugin commands
    elif action == "plugins.isValid":
        return handle_plugins_is_valid(params)
    elif action == "plugins.getName":
        return handle_plugins_get_name(params)
    elif action == "plugins.getParamCount":
        return handle_plugins_get_param_count(params)
    elif action == "plugins.getParams":
        return handle_plugins_get_params(params)
    elif action == "plugins.getParamValue":
        return handle_plugins_get_param_value(params)
    elif action == "plugins.setParamValue":
        return handle_plugins_set_param_value(params)
    elif action == "plugins.getPresetCount":
        return handle_plugins_get_preset_count(params)
    elif action == "plugins.nextPreset":
        return handle_plugins_next_preset(params)
    elif action == "plugins.prevPreset":
        return handle_plugins_prev_preset(params)
    elif action == "plugins.getColor":
        return handle_plugins_get_color(params)

    else:
        # Raise so the response has success False: a server newer than this
        # script must not mistake a missing action for a successful one
        raise ValueError(f"Unknown action: {action} (reload the script in FL Studio)")


# =============================================================================
# Transport Handlers
# =============================================================================


def handle_transport_start() -> dict:
    """Toggle play/pause."""
    transport.start()
    return {"is_playing": transport.isPlaying() == 1}


def handle_transport_stop() -> dict:
    """Stop playback."""
    transport.stop()
    return {"stopped": True}


def handle_transport_record() -> dict:
    """Toggle recording."""
    transport.record()
    return {"is_recording": transport.isRecording() == 1}


def handle_transport_get_status() -> dict:
    """Get transport status."""
    loop_mode = transport.getLoopMode()
    # getCurrentTempo() has been seen returning both BPM and thousandths of a
    # BPM; FL's tempo never goes above 522 BPM, so the magnitude tells them apart
    tempo = mixer.getCurrentTempo()
    return {
        "is_playing": transport.isPlaying() == 1,
        "is_recording": transport.isRecording() == 1,
        "position": transport.getSongPosHint(),
        "loop_mode": "song" if loop_mode == 1 else "pattern",
        "tempo": tempo / 1000 if tempo > 1000 else tempo,
        "ticks_per_bar": _ticks_per_bar(),
        "selection": _selection(),
    }


def handle_transport_set_position(params: dict) -> dict:
    """Set playback position."""
    if "bar" in params:
        # Bar numbers start at 1, as in the playlist ruler
        if params["bar"] < 1:
            raise ValueError(f"Bar numbers start at 1 (got {params['bar']})")
        ticks = (params["bar"] - 1) * _ticks_per_bar()
        transport.setSongPos(round(ticks), midi.SONGLENGTH_ABSTICKS)
        return {"position": transport.getSongPosHint()}
    position = params.get("position", 0)
    mode = params.get("mode", midi.SONGLENGTH_S)
    transport.setSongPos(position, mode)
    return {"position": transport.getSongPosHint()}


def handle_transport_get_length() -> dict:
    """Get song length."""
    # Modes: 0 = ms, 1 = seconds, 2 = absolute ticks, 3 = bars
    return {
        "bars": transport.getSongLength(3),
        "ticks": transport.getSongLength(2),
        "seconds": transport.getSongLength(1),
        "milliseconds": transport.getSongLength(0),
    }


def handle_project_get_state() -> dict:
    """Unsaved-changes flag (the API doesn't expose the project file name)."""
    changed = general.getChangedFlag()
    return {
        # 0 = saved, 1 = unsaved changes, 2 = unsaved but covered by an autosave
        "changed": changed,
        "unsaved_changes": changed != 0,
    }


def handle_project_save(params: dict) -> dict:
    """Save the project like Ctrl+S, or as a new version like Ctrl+N."""
    command = midi.FPT_SaveNew if params.get("new_version", False) else midi.FPT_Save
    transport.globalTransport(command, 1)
    return {"saved": True, "new_version": command == midi.FPT_SaveNew}


def handle_project_set_time_signature(params: dict) -> dict:
    """Set the project's time signature (not a playlist time signature marker)."""
    if not hasattr(general, "setNumerator"):
        raise ValueError("Setting the time signature needs a newer FL Studio (2025 or later)")
    numerator, denominator = params["numerator"], params["denominator"]
    # FL rejects other values, and silently ignores a denominator like 3
    if not 1 <= numerator <= 16 or denominator not in (2, 4, 8, 16):
        raise ValueError("Numerator must be 1-16 and denominator 2, 4, 8 or 16")
    general.setNumerator(numerator)
    general.setDenominator(denominator)
    return {"ticks_per_bar": _ticks_per_bar(), "ppq": general.getRecPPQ()}


# =============================================================================
# Undo Handlers
# =============================================================================


def handle_undo_get_state() -> dict:
    """Position in FL's undo history (0 = latest state) and its length."""
    return {
        "position": general.getUndoHistoryLast(),
        "length": general.getUndoHistoryPos(),
        "hint": general.getUndoLevelHint(),
    }


# What a save point snapshots: pattern data (notes, steps), the playlist and
# its markers. Mixer and plugin knob changes get their own history entries.
UNDO_POINT_FLAGS = midi.UF_PR | midi.UF_PL | midi.UF_PRMarker | midi.UF_PLMarker


def handle_undo_save_point(params: dict) -> dict:
    """Snapshot the project into a named undo entry, before making changes."""
    name = params.get("name") or "MCP changes"
    general.saveUndo(name, params.get("flags", UNDO_POINT_FLAGS))
    return {"name": name}


def handle_undo_move(params: dict) -> dict:
    """Undo (steps > 0) or redo (steps < 0) through FL's undo history."""
    steps = params.get("steps", 1)
    position = general.getUndoHistoryLast()
    length = general.getUndoHistoryPos()
    if steps > 0 and position + steps > length - 1:
        raise ValueError(f"Only {max(length - 1 - position, 0)} step(s) left to undo")
    if steps < 0 and position + steps < 0:
        raise ValueError(f"Only {position} step(s) left to redo")
    for _ in range(abs(steps)):
        if steps > 0:
            general.undoUp()
        else:
            general.undoDown()
    # FL moves through the history after this callback returns: read the new
    # position with a separate command (undo.getState)
    return {"from_position": position}


def handle_transport_set_loop_mode(params: dict) -> dict:
    """Set loop mode."""
    mode = params.get("mode", "pattern")
    current_mode = transport.getLoopMode()
    target_mode = 1 if mode.lower() == "song" else 0

    if current_mode != target_mode:
        transport.setLoopMode()

    return {"mode": mode}


def handle_transport_set_playback_speed(params: dict) -> dict:
    """Set playback speed."""
    speed = params.get("speed", 1.0)
    transport.setPlaybackSpeed(speed)
    return {"speed": speed}


def handle_transport_set_tempo(params: dict) -> dict:
    """Set the project tempo in BPM."""
    bpm = params.get("bpm", 120.0)
    # The tempo REC event takes thousandths of a BPM
    general.processRECEvent(
        midi.REC_Tempo, round(bpm * 1000), midi.REC_Control | midi.REC_UpdateControl
    )
    return {"bpm": bpm}


# =============================================================================
# UI Handlers
# =============================================================================


def handle_ui_open_piano_roll(params: dict) -> dict:
    """Open the piano roll on a channel so piano roll scripts act on it."""
    index = params.get("channel", 0)
    if not 0 <= index < channels.channelCount(True):
        raise ValueError(f"Channel {index} does not exist")
    # A channel hidden by the channel rack's group filter can't get the piano
    # roll: FL opens it on a visible channel instead, and notes land there
    visible = {channels.getChannelIndex(i) for i in range(channels.channelCount())}
    if index not in visible:
        raise ValueError(
            f"Channel {index} is hidden by the channel rack filter; set the filter to All"
        )
    channels.selectOneChannel(index, True)
    # The piano roll opens on the selected channel, but an open one stays on
    # its channel, so close it first
    if ui.getVisible(midi.widPianoRoll):
        ui.hideWindow(midi.widPianoRoll)
    ui.showWindow(midi.widPianoRoll)
    ui.setFocused(midi.widPianoRoll)
    return {"channel_name": channels.getChannelName(index, True)}


def handle_ui_close_piano_roll() -> dict:
    """Close the piano roll."""
    ui.hideWindow(midi.widPianoRoll)
    return {"closed": True}


# =============================================================================
# Pattern Handlers
# =============================================================================


def handle_patterns_get_current() -> dict:
    """Get the selected pattern (patterns are numbered from 1)."""
    index = patterns.patternNumber()
    return {
        "index": index,
        "name": patterns.getPatternName(index),
        "count": patterns.patternCount(),
    }


def handle_patterns_select(params: dict) -> dict:
    """Select a pattern by number."""
    index = params.get("index", 1)
    _check_pattern(index)
    patterns.jumpToPattern(index)
    return {"index": index, "name": patterns.getPatternName(index)}


def _check_pattern(index: int) -> None:
    """Raise if the pattern number is out of range (patterns are numbered from 1)."""
    # Every number up to patternMax() is a usable pattern, even an empty one
    if not 1 <= index <= patterns.patternMax():
        raise ValueError(f"Pattern {index} does not exist (1 to {patterns.patternMax()})")


def _pattern_info(index: int) -> dict:
    color = patterns.getPatternColor(index) & 0xFFFFFF  # 0xRRGGBB
    info = {
        "index": index,
        "name": patterns.getPatternName(index),
        "color": {"r": color >> 16, "g": (color >> 8) & 0xFF, "b": color & 0xFF},
        "length_steps": patterns.getPatternLength(index),
    }
    if hasattr(patterns, "isPatternDefault"):  # API 23+
        info["empty"] = patterns.isPatternDefault(index) == 1
    return info


def handle_patterns_get_all() -> dict:
    """Name, color and length of every used pattern, plus the selected one."""
    # patternCount() only counts the patterns changed from their default
    # state, and they need not be adjacent: scan until all of them are found
    remaining = patterns.patternCount()
    current = patterns.patternNumber()
    if not hasattr(patterns, "isPatternDefault"):  # API < 23: assume no gaps
        indexes = sorted(set(range(1, remaining + 1)) | {current})
        return {"patterns": [_pattern_info(i) for i in indexes], "current": current}
    found = []
    for index in range(1, patterns.patternMax() + 1):
        if remaining == 0 and index > current:
            break
        used = not patterns.isPatternDefault(index)
        remaining -= used
        if used or index == current:
            found.append(_pattern_info(index))
    return {"patterns": found, "current": current}


def handle_patterns_get_info(params: dict) -> dict:
    """Name, color and length of one pattern."""
    index = params.get("index", 1)
    _check_pattern(index)
    return _pattern_info(index)


def handle_patterns_set(params: dict) -> dict:
    """Rename, recolor and/or resize a pattern."""
    index = params.get("index", 1)
    _check_pattern(index)
    if "length_steps" in params and not hasattr(patterns, "setPatternLength"):
        raise ValueError("Setting a pattern length needs FL Studio 2025 or newer")
    if "name" in params:
        patterns.setPatternName(index, params["name"])
    if "color" in params:
        r, g, b = (params["color"][k] for k in ("r", "g", "b"))
        patterns.setPatternColor(index, (r << 16) | (g << 8) | b)
    if "length_steps" in params:
        # 0 makes the length automatic again (getPatternLength then returns
        # the computed length, not 0)
        patterns.setPatternLength(index, params["length_steps"])
    # Read the result back with a separate command (patterns.getInfo): FL can
    # apply changes after this callback returns
    return {"index": index}


def handle_patterns_clone(params: dict) -> dict:
    """Clone a pattern (default: the selected one); FL selects the copy.

    The copy is inserted right after the source: later patterns move up by one.
    """
    if not hasattr(patterns, "clonePattern"):  # API 25+
        raise ValueError("Cloning patterns needs a newer FL Studio (API 25)")
    index = params["index"] if params.get("index") is not None else patterns.patternNumber()
    _check_pattern(index)
    patterns.clonePattern(index)
    clone = patterns.patternNumber()
    if clone == index:
        raise ValueError(f"FL Studio did not clone pattern {index}")
    if params.get("name"):
        patterns.setPatternName(clone, params["name"])
    return {"source": index, "index": clone, "name": patterns.getPatternName(clone)}


# =============================================================================
# Arrangement / Playlist Handlers
# =============================================================================


def _marker_names() -> list:
    names = []
    while len(names) < 999:
        name = arrangement.getMarkerName(len(names))
        if not name:
            break
        names.append(name)
    return names


def _ticks_per_bar() -> int:
    """Bar length from the project's time signature (PPQ * 4 * num / den).

    Time signature markers in the playlist are not taken into account.
    """
    return general.getRecPPB()


def _bar_of(ticks: int) -> float:
    """Bar number (from 1) of a tick position; fractional between bar lines."""
    bar = ticks / _ticks_per_bar() + 1
    return int(bar) if bar == int(bar) else round(bar, 4)


def _has_selection_api() -> bool:
    return hasattr(arrangement, "selectionSet")  # FL Studio 2025+


def _check_selection_api() -> None:
    if not _has_selection_api():
        raise ValueError("Time selections and marker positions need a newer FL Studio")


def _selection():
    """The playlist time selection in ticks and bars, or None."""
    if not _has_selection_api() or not arrangement.selectionIsActive():
        return None
    start, end = arrangement.selectionStart(), arrangement.selectionEnd()
    return {"start_tick": start, "end_tick": end,
            "start_bar": _bar_of(start), "end_bar": _bar_of(end)}


def _marker_sections() -> tuple:
    """Start and end ticks of each marker (by index), read in song mode, and
    the playhead position (ticks) from before the scan.

    FL only gives marker names, but jumping to a marker selects its section,
    up to the next marker (no end for the last one). A marker sharing its
    position with another one is never landed on, so it is missing. The
    playhead is moved back here, but that doesn't stick when a selection is
    restored in the same callback: callers move it again in a new command.
    """
    position = transport.getSongPos(midi.SONGLENGTH_ABSTICKS)
    count = len(_marker_names())
    if not count:
        return {}, position
    _check_selection_api()
    if transport.getLoopMode() != 1:
        raise ValueError("Marker positions can only be read in song mode")
    selection = _selection()

    sections = {}
    try:
        transport.setSongPos(0, midi.SONGLENGTH_ABSTICKS)
        # Past the last marker a jump wraps around to the first, so count
        # jumps from the song start visit every marker, even one at bar 1
        for _ in range(count):
            index = arrangement.jumpToMarker(1, True)
            end = arrangement.selectionEnd()
            sections[index] = (arrangement.selectionStart(), end if end >= 0 else None)
    finally:
        # The last jump leaves its marker section looping inside FL, and only
        # selectionClear ends that: selectionSet alone would keep positions
        # wrapping inside that section
        arrangement.selectionClear()
        if selection:
            arrangement.selectionSet(selection["start_tick"], selection["end_tick"])
        transport.setSongPos(position, midi.SONGLENGTH_ABSTICKS)
    return sections, position


def handle_arrangement_get_markers() -> dict:
    """Names of the playlist markers, in timeline order."""
    return {"markers": _marker_names()}


def handle_arrangement_get_marker_sections() -> dict:
    """Name, start and end (the next marker's position) of every marker."""
    sections, position = _marker_sections()
    markers = []
    for index, name in enumerate(_marker_names()):
        start, end = sections.get(index, (None, None))
        markers.append({
            "index": index,
            "name": name,
            "bar": None if start is None else _bar_of(start),
            "end_bar": None if end is None else _bar_of(end),
            "start_tick": start,
            "end_tick": end,
        })
    return {"markers": markers, "restore_position": position}


def handle_arrangement_set_selection(params: dict) -> dict:
    """Select a section (song mode only).

    Takes start_tick/end_tick, or start_bar/end_bar (end exclusive). Move the
    playhead with a separate transport.setPosition: setSongPos in the same
    callback as selectionSet doesn't stick.
    """
    _check_selection_api()
    if transport.getLoopMode() != 1:
        raise ValueError("Switch FL Studio to song mode first")
    if "start_tick" in params:
        start, end = params["start_tick"], params["end_tick"]
    else:
        start_bar, end_bar = params["start_bar"], params["end_bar"]
        if start_bar < 1:
            raise ValueError(f"Bar numbers start at 1 (got {start_bar})")
        start = round((start_bar - 1) * _ticks_per_bar())
        end = round((end_bar - 1) * _ticks_per_bar())
    if start < 0 or end <= start:
        raise ValueError("The section must end after it starts")
    arrangement.selectionClear()  # also ends a marker section loop
    arrangement.selectionSet(start, end)
    return {"selection": _selection()}


def handle_arrangement_clear_selection() -> dict:
    """Remove the playlist time selection."""
    _check_selection_api()
    arrangement.selectionClear()
    return {"cleared": True}


def _dropped_marker(before: list, after: list):
    """Index in `before` of the one marker missing from `after`, or None.

    Compares positions rather than names: projects can have several markers
    with the same name.
    """
    if len(after) != len(before) - 1:
        return None
    for index, name in enumerate(after):
        if before[index] != name:
            return index
    return len(after)


def handle_arrangement_add_markers(params: dict) -> dict:
    """Add markers at bar numbers (from 1); names already present are skipped."""
    if params.get("beats_per_bar"):
        ticks_per_bar = general.getRecPPQ() * params["beats_per_bar"]
    else:
        ticks_per_bar = _ticks_per_bar()
    existing = _marker_names()
    added, skipped, occupied = [], [], []
    for marker in params.get("markers", []):
        bar, name = marker["bar"], marker["name"]
        if bar < 1:
            raise ValueError(f"Bar numbers start at 1 (got {bar})")
        if name in existing:
            skipped.append(name)
            continue
        tick = round((bar - 1) * ticks_per_bar)
        arrangement.addAutoTimeMarker(tick, name)
        after = _marker_names()
        if len(after) == len(existing) + 1:
            added.append(name)
        else:
            # FL toggles markers: at a position that already has one, adding
            # removes that marker instead. Put it back (FL records both steps
            # in the undo history) and report the clash.
            dropped = _dropped_marker(existing, after)
            taken_by = None if dropped is None else existing[dropped]
            if taken_by is not None:
                arrangement.addAutoTimeMarker(tick, taken_by)
                after = _marker_names()
            occupied.append({"name": name, "bar": bar, "taken_by": taken_by})
        existing = after
    return {"added": added, "skipped": skipped, "occupied": occupied}


def handle_arrangement_delete_marker(params: dict) -> dict:
    """Delete a marker by name (song mode only)."""
    name = params["name"]
    names = _marker_names()
    if name not in names:
        raise ValueError(f"No marker named '{name}'")
    sections, position = _marker_sections()
    start = sections.get(names.index(name), (None, None))[0]
    if start is None:
        raise ValueError(f"FL can't locate marker '{name}'")
    # Adding a marker where one already is removes that marker instead
    arrangement.addAutoTimeMarker(start, name)
    dropped = _dropped_marker(names, _marker_names())
    if dropped is None:
        raise ValueError(f"FL Studio did not delete marker '{name}'")
    if names[dropped] != name:
        # Another marker at the same position went instead: put it back
        arrangement.addAutoTimeMarker(start, names[dropped])
        raise ValueError(f"FL Studio removed '{names[dropped]}' instead of '{name}' "
                         f"(same position); it was put back")
    return {"deleted": name, "bar": _bar_of(start), "restore_position": position}


def _check_playlist_track(index: int) -> None:
    """Raise if the playlist track doesn't exist (tracks are numbered from 1)."""
    if not 1 <= index <= playlist.trackCount():
        raise ValueError(f"Playlist track {index} does not exist")


def _playlist_track_info(index: int) -> dict:
    return {
        "index": index,
        "name": playlist.getTrackName(index),
        "color": playlist.getTrackColor(index),
        "is_muted": playlist.isTrackMuted(index) == 1,
        "is_solo": playlist.isTrackSolo(index) == 1,
    }


def handle_playlist_get_tracks(params: dict) -> dict:
    """Name, color, mute and solo state of the first playlist tracks (from 1)."""
    if "index" in params:
        _check_playlist_track(params["index"])
        return {"tracks": [_playlist_track_info(params["index"])]}
    count = min(params.get("count", 20), playlist.trackCount())
    return {"tracks": [_playlist_track_info(i) for i in range(1, count + 1)]}


def handle_playlist_set_track(params: dict) -> dict:
    """Rename, recolor, mute and/or solo a playlist track (numbered from 1)."""
    index = params.get("index", 1)
    _check_playlist_track(index)
    if "name" in params:
        playlist.setTrackName(index, params["name"])
    if "color" in params:
        playlist.setTrackColor(index, params["color"])
    # muteTrack/soloTrack only take a target value since API 30: toggle when
    # the state differs instead. Solo goes first, since unsolo unmutes every
    # track and would undo a mute made before it.
    if "solo" in params and (playlist.isTrackSolo(index) == 1) != params["solo"]:
        playlist.soloTrack(index)
    if "muted" in params and (playlist.isTrackMuted(index) == 1) != params["muted"]:
        playlist.muteTrack(index)
    # Mute/solo can apply after this callback returns: read them back with a
    # separate command (playlist.getTracks)
    return {"index": index, "name": playlist.getTrackName(index)}


def handle_patterns_create(params: dict) -> dict:
    """Select the first empty pattern, optionally naming it."""
    name = params.get("name", "")
    patterns.findFirstNextEmptyPat(midi.FFNEP_DontPromptName)
    index = patterns.patternNumber()
    if name:
        patterns.setPatternName(index, name)
    return {"index": index, "name": patterns.getPatternName(index)}


# =============================================================================
# Mixer Handlers
# =============================================================================


def handle_mixer_get_peaks() -> dict:
    """Current peak meter of every mixer track (1.0 = 0 dBFS), for level sampling."""
    return {"peaks": [mixer.getTrackPeaks(t, 2) for t in range(mixer.trackCount() - 1)]}


def handle_mixer_get_track_count() -> dict:
    """Get number of mixer tracks."""
    return {"count": mixer.trackCount()}


def handle_mixer_get_track_info(params: dict) -> dict:
    """Get info about a mixer track."""
    track = params.get("track", 0)
    _check_track(track)
    return {
        "index": track,
        "name": mixer.getTrackName(track),
        "volume": mixer.getTrackVolume(track),
        "volume_db": mixer.getTrackVolume(track, 1),
        "pan": mixer.getTrackPan(track),
        "stereo_separation": mixer.getTrackStereoSep(track),
        "stereo_separation_display": _rec_display(_track_event(track, midi.REC_Mixer_SS)),
        "is_muted": mixer.isTrackMuted(track) == 1,
        "is_solo": mixer.isTrackSolo(track) == 1,
        "is_armed": mixer.isTrackArmed(track) == 1,
        "color": hex(mixer.getTrackColor(track)),
        "fx_slots": _loaded_slots(track),
        "sends_to": _routes_from(track),
    }


def handle_mixer_get_all_tracks(params: dict) -> dict:
    """Get info about all mixer tracks."""
    include_empty = params.get("include_empty", False)
    tracks = []
    # trackCount() also counts the hidden "Current" track at the end
    track_count = mixer.trackCount() - 1

    for i in range(track_count):
        name = mixer.getTrackName(i)

        # Skip empty tracks if requested
        if not include_empty and (not name or name.startswith("Insert ")):
            if i != 0:  # Always include master
                continue

        tracks.append({
            "index": i,
            "name": name if name else ("Master" if i == 0 else f"Insert {i}"),
            "volume": mixer.getTrackVolume(i),
            "pan": mixer.getTrackPan(i),
            "is_muted": mixer.isTrackMuted(i) == 1,
            "is_solo": mixer.isTrackSolo(i) == 1,
        })

    return {"tracks": tracks}


def handle_mixer_set_track_volume(params: dict) -> dict:
    """Set mixer track volume."""
    track = params.get("track", 0)
    volume = params.get("volume", 0.8)
    mixer.setTrackVolume(track, volume)
    return {
        "volume": mixer.getTrackVolume(track),
        "volume_db": mixer.getTrackVolume(track, 1),
    }


def handle_mixer_set_track_pan(params: dict) -> dict:
    """Set mixer track pan."""
    track = params.get("track", 0)
    pan = params.get("pan", 0.0)
    mixer.setTrackPan(track, pan)
    return {"pan": mixer.getTrackPan(track)}


def handle_mixer_mute_track(params: dict) -> dict:
    """Mute/unmute mixer track."""
    track = params.get("track", 0)
    muted = params.get("muted")  # None = toggle

    if muted is None:
        mixer.muteTrack(track, -1)
    else:
        mixer.muteTrack(track, 1 if muted else 0)

    return {
        "is_muted": mixer.isTrackMuted(track) == 1,
        "track_name": mixer.getTrackName(track),
    }


def handle_mixer_solo_track(params: dict) -> dict:
    """Solo/unsolo mixer track."""
    track = params.get("track", 0)
    solo = params.get("solo")  # None = toggle
    mode = params.get("mode", 3)

    if solo is None:
        mixer.soloTrack(track, -1, mode)
    else:
        mixer.soloTrack(track, 1 if solo else 0, mode)

    return {
        "is_solo": mixer.isTrackSolo(track) == 1,
        "track_name": mixer.getTrackName(track),
    }


def handle_mixer_arm_track(params: dict) -> dict:
    """Toggle arm state of mixer track."""
    track = params.get("track", 0)
    mixer.armTrack(track)
    return {
        "is_armed": mixer.isTrackArmed(track) == 1,
        "track_name": mixer.getTrackName(track),
    }


def handle_mixer_set_track_name(params: dict) -> dict:
    """Set mixer track name."""
    track = params.get("track", 0)
    name = params.get("name", "")
    mixer.setTrackName(track, name)
    return {"name": name}


def handle_mixer_set_track_color(params: dict) -> dict:
    """Set mixer track color."""
    track = params.get("track", 0)
    r = params.get("r", 0)
    g = params.get("g", 0)
    b = params.get("b", 0)
    # FL Studio's scripting API takes 0xRRGGBB
    color = (r << 16) | (g << 8) | b
    mixer.setTrackColor(track, color)
    return {"color": f"RGB({r}, {g}, {b})"}


def handle_mixer_set_stereo_sep(params: dict) -> dict:
    """Set mixer track stereo separation."""
    track = params.get("track", 0)
    separation = params.get("separation", 0.0)
    _check_track(track)
    mixer.setTrackStereoSep(track, separation, midi.PIM_None)
    # Like slot changes, this can show up only after the callback returns:
    # read it back with a separate command (mixer.getTrackInfo).
    return {"track": track}


# =============================================================================
# Mixer FX Slot & Routing Handlers
# =============================================================================

# Every mixer track has 10 effect slots
MIXER_SLOT_COUNT = 10


def _check_track(track: int) -> None:
    """Raise if the mixer track doesn't exist."""
    # trackCount() also counts the hidden "Current" track at the end
    if not 0 <= track < mixer.trackCount() - 1:
        raise ValueError(f"Mixer track {track} does not exist")


def _check_slot(track: int, slot: int) -> None:
    """Raise if the effect slot is out of range or empty."""
    _check_track(track)
    if not 0 <= slot < MIXER_SLOT_COUNT:
        raise ValueError(f"Slot must be between 0 and {MIXER_SLOT_COUNT - 1}")
    if not mixer.isTrackPluginValid(track, slot):
        raise ValueError(f"No plugin loaded in slot {slot} of mixer track {track}")


def _track_event(track: int, offset: int) -> int:
    """REC event ID of a track-level control (stereo sep, sends...)."""
    return mixer.getTrackPluginId(track, 0) + offset


def _slot_event(track: int, slot: int, offset: int) -> int:
    """REC event ID of an effect slot control (mix level, on/off)."""
    return mixer.getTrackPluginId(track, slot) + offset


def _rec_display(event_id: int) -> str:
    """Value of a REC event formatted the way FL displays it (e.g. '15%')."""
    return device.getLinkedValueString(event_id)


def _set_rec_value(event_id: int, value: float) -> None:
    """Set the control behind a REC event from a 0.0-1.0 value."""
    # REC_MIDIController makes FL read the value on the 0..FromMIDI_Max scale
    scaled = round(min(max(value, 0.0), 1.0) * midi.FromMIDI_Max)
    general.processRECEvent(event_id, scaled, midi.REC_MIDIController)


def _slot_info(track: int, slot: int) -> dict:
    """Describe a loaded effect slot, including its Mix (dry/wet) knob."""
    mix_event = _slot_event(track, slot, midi.REC_Plug_MixLevel)
    if hasattr(mixer, "getPluginMixLevel"):  # API 37+
        mix = mixer.getPluginMixLevel(track, slot)
    else:
        mix = device.getLinkedValue(mix_event)
    return {
        "slot": slot,
        "name": plugins.getPluginName(track, slot),
        "enabled": device.getLinkedValue(_slot_event(track, slot, midi.REC_Plug_Mute)) >= 0.5,
        "mix": mix,
        "mix_display": _rec_display(mix_event),
    }


def _loaded_slots(track: int) -> list:
    return [
        _slot_info(track, slot)
        for slot in range(MIXER_SLOT_COUNT)
        if mixer.isTrackPluginValid(track, slot)
    ]


def _route_info(src: int, dst: int) -> dict:
    """Describe the route from src to dst, including its send level."""
    send_event = _track_event(src, midi.REC_Mixer_Send_First + dst)
    if hasattr(mixer, "getRouteToLevel"):  # API 36+
        level = mixer.getRouteToLevel(src, dst)
    else:
        level = device.getLinkedValue(send_event)
    return {
        "track": dst,
        "name": mixer.getTrackName(dst),
        "level": level,
        "level_display": _rec_display(send_event),
    }


def _routes_from(track: int) -> list:
    return [
        _route_info(track, dst)
        for dst in range(mixer.trackCount() - 1)
        if dst != track and mixer.getRouteSendActive(track, dst)
    ]


def handle_mixer_get_track_fx(params: dict) -> dict:
    """List the effects loaded on a mixer track with their mix levels."""
    track = params.get("track", 0)
    _check_track(track)
    slots_enabled = True
    if hasattr(mixer, "isTrackSlotsEnabled"):  # API 19+
        slots_enabled = mixer.isTrackSlotsEnabled(track) == 1
    return {
        "track": track,
        "track_name": mixer.getTrackName(track),
        "slots_enabled": slots_enabled,
        "slots": _loaded_slots(track),
    }


def handle_mixer_set_slot_mix(params: dict) -> dict:
    """Set the Mix (dry/wet) knob of an effect slot."""
    track = params.get("track", 0)
    slot = params.get("slot", 0)
    mix = params.get("mix", 1.0)
    _check_slot(track, slot)
    if hasattr(mixer, "setPluginMixLevel"):  # API 37+
        mixer.setPluginMixLevel(track, slot, mix, midi.PIM_None)
    else:
        _set_rec_value(_slot_event(track, slot, midi.REC_Plug_MixLevel), mix)
    # FL applies slot changes after this callback returns: read them back with
    # a separate command (mixer.getTrackFx) rather than here.
    return {"name": plugins.getPluginName(track, slot)}


def handle_mixer_set_slot_enabled(params: dict) -> dict:
    """Turn an effect slot on or off (bypass)."""
    track = params.get("track", 0)
    slot = params.get("slot", 0)
    enabled = params.get("enabled", True)
    _check_slot(track, slot)
    _set_rec_value(_slot_event(track, slot, midi.REC_Plug_Mute), 1.0 if enabled else 0.0)
    return {"name": plugins.getPluginName(track, slot)}


def handle_mixer_get_routing(params: dict) -> dict:
    """List where a mixer track sends to and which tracks feed into it."""
    track = params.get("track", 0)
    _check_track(track)
    receives_from = [
        {"track": src, "name": mixer.getTrackName(src)}
        for src in range(mixer.trackCount() - 1)
        if src != track and mixer.getRouteSendActive(src, track)
    ]
    return {
        "track": track,
        "track_name": mixer.getTrackName(track),
        "sends_to": _routes_from(track),
        "receives_from": receives_from,
    }


def handle_mixer_set_route(params: dict) -> dict:
    """Create, remove or adjust the route from one mixer track to another."""
    src = params.get("src", 0)
    dst = params.get("dst", 0)
    enabled = params.get("enabled", True)
    level = params.get("level")  # None = leave the send level unchanged
    exclusive = params.get("exclusive", False)
    _check_track(src)
    _check_track(dst)
    if src == dst:
        raise ValueError("A mixer track cannot be routed to itself")

    if enabled and exclusive:
        # Like FL's "Route to this track only": drop every other output
        for other in range(mixer.trackCount() - 1):
            if other not in (src, dst) and mixer.getRouteSendActive(src, other):
                mixer.setRouteTo(src, other, False)

    mixer.setRouteTo(src, dst, enabled)
    if enabled and level is not None:
        if hasattr(mixer, "setRouteToLevel"):  # API 36+
            mixer.setRouteToLevel(src, dst, level)
        else:
            _set_rec_value(_track_event(src, midi.REC_Mixer_Send_First + dst), level)
    mixer.afterRoutingChanged()

    return {
        "src": src,
        "src_name": mixer.getTrackName(src),
        "dst": dst,
        "active": mixer.getRouteSendActive(src, dst) == 1,
        "sends_to": _routes_from(src),
    }


def _slot_names(track: int) -> dict:
    return {
        slot: plugins.getPluginName(track, slot)
        for slot in range(MIXER_SLOT_COUNT)
        if mixer.isTrackPluginValid(track, slot)
    }


def handle_mixer_load_plugin(params: dict) -> dict:
    """Load an effect into the next free slot of a mixer track from a .fst preset."""
    track = params.get("track", 0)
    preset_path = params.get("preset_path", "")
    _check_track(track)
    if not os.path.isfile(preset_path):
        raise ValueError(f"Preset file not found: {preset_path}")
    before = _slot_names(track)
    if len(before) == MIXER_SLOT_COUNT:
        raise ValueError(f"All {MIXER_SLOT_COUNT} effect slots of mixer track {track} are full")

    # The scripting API has no "load plugin" call, but the audio editor launcher
    # (what the Mackie script uses to drop Edison on a track) loads any .fst
    # preset into the track's next free slot. It only takes paths relative to
    # FL's Data/System folder, and native plugins need the exact relative path.
    try:
        relative_preset = os.path.relpath(preset_path, _fl_data_system_dir())
    except ValueError:
        raise ValueError("The preset must be on the same drive as FL Studio") from None
    ui.launchAudioEditor(False, "", track, relative_preset, "")

    after = _slot_names(track)
    loaded = [_slot_info(track, slot) for slot, name in after.items() if before.get(slot) != name]
    if not loaded:
        raise ValueError(f"FL Studio did not load the preset {preset_path}")
    return {"track": track, "track_name": mixer.getTrackName(track), "loaded": loaded}


def _fl_data_system_dir() -> str:
    """FL Studio's Data/System folder, the base for launchAudioEditor presets."""
    # midi.py ships in <FL Studio>/Shared/Python/Lib
    fl_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(midi.__file__))))
    return os.path.join(fl_dir, "Data", "System")


# =============================================================================
# Channel Handlers
# =============================================================================


def handle_channels_get_count(params: dict) -> dict:
    """Get number of channels."""
    global_count = params.get("global_count", True)
    return {"count": channels.channelCount(global_count)}


def handle_channels_get_info(params: dict) -> dict:
    """Get info about a channel."""
    index = params.get("index", 0)
    use_global = params.get("use_global", True)

    return {
        "index": index,
        "name": channels.getChannelName(index, use_global),
        "color": hex(channels.getChannelColor(index, use_global)),
        # getChannelVolume's 2nd argument is mode (dB), NOT useGlobalIndex:
        # passed positionally, the index is read in the displayed channel group
        "volume": channels.getChannelVolume(index, useGlobalIndex=use_global),
        "pan": channels.getChannelPan(index, use_global),
        "pitch": channels.getChannelPitch(index, useGlobalIndex=use_global),
        "is_muted": channels.isChannelMuted(index, use_global) == 1,
        "is_solo": channels.isChannelSolo(index, use_global) == 1,
        "is_selected": channels.isChannelSelected(index, use_global) == 1,
        "target_fx_track": channels.getTargetFxTrack(index, use_global),
    }


def handle_channels_get_all() -> dict:
    """Get info about all channels."""
    channels_list = []
    count = channels.channelCount(True)

    for i in range(count):
        channels_list.append({
            "index": i,
            "name": channels.getChannelName(i, True),
            "is_muted": channels.isChannelMuted(i, True) == 1,
            "is_selected": channels.isChannelSelected(i, True) == 1,
            "target_fx_track": channels.getTargetFxTrack(i, True),
        })

    return {"channels": channels_list}


def handle_channels_get_selected() -> dict:
    """Get currently selected channel."""
    index = channels.selectedChannel(canBeNone=True, indexGlobal=True)

    if index is None or index < 0:
        return {"channel": None}

    return {
        "channel": {
            "index": index,
            "name": channels.getChannelName(index, True),
            "volume": channels.getChannelVolume(index, useGlobalIndex=True),
            "pan": channels.getChannelPan(index, True),
            "is_muted": channels.isChannelMuted(index, True) == 1,
            "is_solo": channels.isChannelSolo(index, True) == 1,
        }
    }


def handle_channels_select(params: dict) -> dict:
    """Select/deselect a channel."""
    index = params.get("index", 0)
    select = params.get("select", True)
    channels.selectChannel(index, 1 if select else 0, True)
    return {
        "selected": select,
        "channel_name": channels.getChannelName(index, True),
    }


def handle_channels_select_one(params: dict) -> dict:
    """Select only one channel, deselecting others."""
    index = params.get("index", 0)
    channels.selectOneChannel(index, True)
    return {"channel_name": channels.getChannelName(index, True)}


def handle_channels_trigger_note(params: dict) -> dict:
    """Trigger a MIDI note on a channel."""
    channel = params.get("channel", 0)
    note = params.get("note", 60)
    velocity = params.get("velocity", 100)
    midi_channel = params.get("midi_channel", -1)
    channels.midiNoteOn(channel, note, velocity, midi_channel)
    return {"triggered": True, "note": note, "velocity": velocity}


def handle_channels_set_volume(params: dict) -> dict:
    """Set channel volume."""
    index = params.get("index", 0)
    volume = params.get("volume", 0.8)
    # The 3rd positional argument is pickupMode, NOT useGlobalIndex
    channels.setChannelVolume(index, volume, useGlobalIndex=True)
    return {
        "volume": channels.getChannelVolume(index, useGlobalIndex=True),
        "channel_name": channels.getChannelName(index, True),
    }


def handle_channels_set_pan(params: dict) -> dict:
    """Set channel pan."""
    index = params.get("index", 0)
    pan = params.get("pan", 0.0)
    channels.setChannelPan(index, pan, useGlobalIndex=True)
    return {
        "pan": channels.getChannelPan(index, True),
        "channel_name": channels.getChannelName(index, True),
    }


def handle_channels_mute(params: dict) -> dict:
    """Mute/unmute channel."""
    index = params.get("index", 0)
    muted = params.get("muted")  # None = toggle

    if muted is None:
        channels.muteChannel(index, -1, True)
    else:
        channels.muteChannel(index, 1 if muted else 0, True)

    return {
        "is_muted": channels.isChannelMuted(index, True) == 1,
        "channel_name": channels.getChannelName(index, True),
    }


def handle_channels_solo(params: dict) -> dict:
    """Solo/unsolo channel."""
    index = params.get("index", 0)
    solo = params.get("solo")  # None = toggle

    if solo is None:
        channels.soloChannel(index, -1, True)
    else:
        channels.soloChannel(index, 1 if solo else 0, True)

    return {
        "is_solo": channels.isChannelSolo(index, True) == 1,
        "channel_name": channels.getChannelName(index, True),
    }


def handle_channels_set_name(params: dict) -> dict:
    """Set channel name."""
    index = params.get("index", 0)
    name = params.get("name", "")
    channels.setChannelName(index, name, True)
    return {"name": name}


def handle_channels_set_color(params: dict) -> dict:
    """Set channel color."""
    index = params.get("index", 0)
    r = params.get("r", 0)
    g = params.get("g", 0)
    b = params.get("b", 0)
    # FL Studio's scripting API takes 0xRRGGBB
    color = (r << 16) | (g << 8) | b
    channels.setChannelColor(index, color, True)
    return {"color": f"RGB({r}, {g}, {b})"}


def handle_system_get_paths() -> dict:
    """FL's Data/System folder (channel templates) and this script's folder."""
    return {"data_system": _fl_data_system_dir(), "script_dir": str(SCRIPT_DIR)}


def _free_mixer_track() -> int:
    """First insert track with its default name, no effect, and nothing routed to it.

    Neither a channel nor another track (a bus) may send to it.
    """
    used = {channels.getTargetFxTrack(i, True) for i in range(channels.channelCount(True))}
    inserts = range(1, mixer.trackCount() - 1)
    for track in inserts:
        name = mixer.getTrackName(track)
        if (track not in used and name in ("", f"Insert {track}")
                and not any(mixer.isTrackPluginValid(track, s) for s in range(MIXER_SLOT_COUNT))
                and not any(mixer.getRouteSendActive(src, track)
                            for src in inserts if src != track)):
            return track
    raise ValueError("No free mixer track: give one")


def handle_ui_close_empty_slot_window(params: dict) -> dict:
    """Close the empty "Slot 1 (<track>)" window that adding a channel opens.

    Only when it is the focused window and its slot is really empty.
    """
    track = params.get("mixer_track", 0)
    _check_track(track)
    caption = ui.getFocusedFormCaption()
    # The caption has the track's name, which FL set to the new channel's
    # name (the bridge may have restored a custom one since)
    names = {mixer.getTrackName(track), params.get("channel_name", "")} - {""}
    empty_slot_focused = (
        ui.getFocused(midi.widPluginEffect)
        and caption.startswith("Slot ")
        and any(f"({name})" in caption for name in names)
        and not any(mixer.isTrackPluginValid(track, s) for s in range(MIXER_SLOT_COUNT))
    )
    if empty_slot_focused:
        ui.escape()
    return {"closed": bool(empty_slot_focused)}


def handle_channels_show_editor(params: dict) -> dict:
    """Show (True), hide (False) or toggle (None) a channel's plugin window."""
    index = params.get("index", 0)
    show = params.get("show")
    channels.showEditor(index, -1 if show is None else int(show), True)
    return {"index": index}


def handle_channels_add_from_preset(params: dict) -> dict:
    """Add a channel from a channel preset next to this script.

    The server writes the preset (a plugin from the Plugin database, or FL's
    SamplerTrack.fst template with a sample in it), named as the channel
    should be: FL's Python fails at writing binary files.
    """
    preset = params.get("preset", "")
    if os.path.basename(preset) != preset or not preset.endswith(".fst"):
        raise ValueError("preset must be a .fst file name in the script folder")
    track = params.get("mixer_track")
    if track is None:
        track = _free_mixer_track()
    elif track < 1:
        raise ValueError("Route the channel to an insert track (1 or more), not the master")
    _check_track(track)
    track_name = mixer.getTrackName(track)
    custom_track_name = track_name not in ("", f"Insert {track}")

    # The scripting API can't add channels, but the audio editor launcher
    # creates one from a generator preset, routed to the track. FL names the
    # channel after the preset file. It only takes paths relative to FL's
    # Data/System folder.
    try:
        relative = os.path.relpath(str(SCRIPT_DIR / preset), _fl_data_system_dir())
    except ValueError:
        raise ValueError("FL Studio's settings folder must be on FL Studio's drive") from None
    before = [channels.getChannelName(i, True) for i in range(channels.channelCount(True))]
    ui.launchAudioEditor(False, "", track, relative, "")
    after = [channels.getChannelName(i, True) for i in range(channels.channelCount(True))]
    if len(after) != len(before) + 1:
        raise ValueError("FL Studio did not add the channel")
    index = next((i for i, n in enumerate(before) if after[i] != n), len(before))
    if custom_track_name:
        # FL renames the track after the channel: keep the user's name
        mixer.setTrackName(track, track_name)
    return {
        "channel": index,
        "name": channels.getChannelName(index, True),
        "mixer_track": track,
        "mixer_track_name": mixer.getTrackName(track),
    }


def handle_channels_route_to_mixer(params: dict) -> dict:
    """Route channel to mixer track."""
    channel_index = params.get("channel_index", 0)
    mixer_track = params.get("mixer_track", 0)
    channels.setTargetFxTrack(channel_index, mixer_track, True)
    return {
        "channel_name": channels.getChannelName(channel_index, True),
        "mixer_track": mixer_track,
    }


# =============================================================================
# Step Sequencer Handlers
# =============================================================================


def handle_channels_get_grid_bit(params: dict) -> dict:
    """Get whether a step is active."""
    channel = params.get("channel", 0)
    position = params.get("position", 0)
    return {"value": channels.getGridBit(channel, position, True) == 1}


def handle_channels_set_grid_bit(params: dict) -> dict:
    """Set a step on or off."""
    channel = params.get("channel", 0)
    position = params.get("position", 0)
    value = params.get("value", False)
    channels.setGridBit(channel, position, 1 if value else 0, True)
    return {
        "value": value,
        "channel_name": channels.getChannelName(channel, True),
    }


def handle_channels_get_step_sequence(params: dict) -> dict:
    """Get step sequence for a channel."""
    channel = params.get("channel", 0)
    steps = params.get("steps", 16)
    sequence = []

    for i in range(steps):
        sequence.append(channels.getGridBit(channel, i, True) == 1)

    return {"sequence": sequence}


def handle_channels_set_step_sequence(params: dict) -> dict:
    """Set complete step sequence for a channel."""
    channel = params.get("channel", 0)
    pattern = params.get("pattern", [])

    for i, value in enumerate(pattern):
        channels.setGridBit(channel, i, 1 if value else 0, True)

    active_steps = sum(pattern)
    return {
        "active_steps": active_steps,
        "total_steps": len(pattern),
        "channel_name": channels.getChannelName(channel, True),
    }


# =============================================================================
# Plugin Handlers
# =============================================================================


def handle_plugins_is_valid(params: dict) -> dict:
    """Check if plugin exists at location."""
    index = params.get("index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    if slot_index >= 0:
        valid = plugins.isValid(index, slot_index, True)
    else:
        valid = plugins.isValid(index, -1, use_global)

    return {"valid": valid == 1}


def handle_plugins_get_name(params: dict) -> dict:
    """Get plugin name."""
    index = params.get("index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    if slot_index >= 0:
        name = plugins.getPluginName(index, slot_index, True)
    else:
        # The 3rd argument is userName, not useGlobalIndex
        name = plugins.getPluginName(index, -1, False, use_global)

    try:
        preset = plugins.getName(index, slot_index, midi.FPN_Preset, 0, use_global)
    except Exception:
        preset = ""
    return {"name": name, "preset": preset}


def handle_plugins_get_param_count(params: dict) -> dict:
    """Get number of plugin parameters."""
    index = params.get("index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    if slot_index >= 0:
        count = plugins.getParamCount(index, slot_index, True)
    else:
        count = plugins.getParamCount(index, -1, use_global)

    return {"count": count}


def handle_plugins_get_params(params: dict) -> dict:
    """Get plugin parameters, optionally from an offset or filtered by name."""
    index = params.get("index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)
    max_params = params.get("max_params", 50)
    offset = params.get("offset", 0)
    name_filter = params.get("name_filter", "").lower()

    if slot_index >= 0:
        param_count = plugins.getParamCount(index, slot_index, True)
    else:
        param_count = plugins.getParamCount(index, -1, use_global)

    param_list = []
    for i in range(offset, param_count):
        if len(param_list) >= max_params:
            break
        try:
            if slot_index >= 0:
                name = plugins.getParamName(i, index, slot_index, True)
            else:
                name = plugins.getParamName(i, index, -1, use_global)
            if name_filter and name_filter not in name.lower():
                continue

            if slot_index >= 0:
                value = plugins.getParamValue(i, index, slot_index, True)
                value_str = plugins.getParamValueString(i, index, slot_index, True)
            else:
                value = plugins.getParamValue(i, index, -1, use_global)
                value_str = plugins.getParamValueString(i, index, -1, use_global)

            param_list.append({
                "index": i,
                "name": name,
                "value": value,
                "value_string": value_str,
            })
        except Exception as e:
            print(f"Warning: could not read param {i}: {e}")
            continue

    response = {"params": param_list, "param_count": param_count}
    if slot_index >= 0 and mixer.isTrackPluginValid(index, slot_index):
        # The slot's Mix knob scales the whole effect but isn't a plugin param
        response["slot"] = _slot_info(index, slot_index)
    return response


def handle_plugins_get_param_value(params: dict) -> dict:
    """Get specific parameter value."""
    param_index = params.get("param_index", 0)
    plugin_index = params.get("plugin_index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    if slot_index >= 0:
        name = plugins.getParamName(param_index, plugin_index, slot_index, True)
        value = plugins.getParamValue(param_index, plugin_index, slot_index, True)
        value_str = plugins.getParamValueString(param_index, plugin_index, slot_index, True)
    else:
        name = plugins.getParamName(param_index, plugin_index, -1, use_global)
        value = plugins.getParamValue(param_index, plugin_index, -1, use_global)
        value_str = plugins.getParamValueString(param_index, plugin_index, -1, use_global)

    return {
        "index": param_index,
        "name": name,
        "value": value,
        "value_string": value_str,
    }


def handle_plugins_set_param_value(params: dict) -> dict:
    """Set plugin parameter value."""
    param_index = params.get("param_index", 0)
    value = params.get("value", 0.0)
    plugin_index = params.get("plugin_index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    # setParamValue's 5th argument is pickupMode, NOT useGlobalIndex:
    # setParamValue(value, paramIndex, index, slotIndex, pickupMode, useGlobalIndex).
    # Passing True there enables pickup mode and the value is silently ignored.
    pim_none = midi.PIM_None
    if slot_index >= 0:
        name = plugins.getParamName(param_index, plugin_index, slot_index, True)
        plugins.setParamValue(value, param_index, plugin_index, slot_index, pim_none, True)
        new_value = plugins.getParamValue(param_index, plugin_index, slot_index, True)
        value_str = plugins.getParamValueString(param_index, plugin_index, slot_index, True)
    else:
        name = plugins.getParamName(param_index, plugin_index, -1, use_global)
        plugins.setParamValue(value, param_index, plugin_index, -1, pim_none, use_global)
        new_value = plugins.getParamValue(param_index, plugin_index, -1, use_global)
        value_str = plugins.getParamValueString(param_index, plugin_index, -1, use_global)

    return {
        "name": name,
        "value": new_value,
        "value_string": value_str,
    }


def handle_plugins_get_preset_count(params: dict) -> dict:
    """Get number of plugin presets."""
    index = params.get("index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    if slot_index >= 0:
        count = plugins.getPresetCount(index, slot_index, True)
    else:
        count = plugins.getPresetCount(index, -1, use_global)

    return {"count": count}


def handle_plugins_next_preset(params: dict) -> dict:
    """Switch to next preset."""
    index = params.get("index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    if slot_index >= 0:
        plugin_name = plugins.getPluginName(index, slot_index, True)
        plugins.nextPreset(index, slot_index, True)
    else:
        plugin_name = plugins.getPluginName(index, -1, False, use_global)
        plugins.nextPreset(index, -1, use_global)

    return {"plugin_name": plugin_name}


def handle_plugins_prev_preset(params: dict) -> dict:
    """Switch to previous preset."""
    index = params.get("index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    if slot_index >= 0:
        plugin_name = plugins.getPluginName(index, slot_index, True)
        plugins.prevPreset(index, slot_index, True)
    else:
        plugin_name = plugins.getPluginName(index, -1, False, use_global)
        plugins.prevPreset(index, -1, use_global)

    return {"plugin_name": plugin_name}


def handle_plugins_get_color(params: dict) -> dict:
    """Get plugin color."""
    index = params.get("index", 0)
    slot_index = params.get("slot_index", -1)
    use_global = params.get("use_global", True)

    if slot_index >= 0:
        color = plugins.getColor(index, slot_index, True)
    else:
        color = plugins.getColor(index, -1, use_global)

    return {"color": hex(color)}
