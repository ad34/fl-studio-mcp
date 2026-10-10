"""Piano Roll tools for FL Studio - persistent note placement.

This module provides tools for creating, editing, and deleting notes in
FL Studio's piano roll. Unlike MIDI real-time note triggering, these
tools create persistent notes by communicating with FL Studio's Piano Roll
scripting API via JSON files.

Communication flow:
1. MCP server writes requests to mcp_request.json
2. Keystroke trigger (Cmd+Opt+Y) executes FL Studio's ComposeWithLLM script
3. Script reads JSON, modifies piano roll, exports state to piano_roll_state.json
"""

from __future__ import annotations

import json
import platform
import time
from pathlib import Path
from typing import TYPE_CHECKING

from fl_studio_mcp.utils.connection import get_connection
from fl_studio_mcp.utils.fl_trigger import get_trigger, trigger_fl_studio

if TYPE_CHECKING:
    from fastmcp import FastMCP


def _get_fl_scripts_dir() -> Path:
    """Get the FL Studio Piano Roll scripts directory."""
    system = platform.system()

    if system in ("Darwin", "Windows"):
        base = Path.home() / "Documents" / "Image-Line" / "FL Studio" / "Settings"
    else:
        # Linux fallback (FL Studio doesn't officially support Linux)
        base = Path.home() / ".fl-studio" / "Settings"

    scripts_dir = base / "Piano roll scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    return scripts_dir


def _get_request_file() -> Path:
    """Get the path to the MCP request JSON file."""
    return _get_fl_scripts_dir() / "mcp_request.json"


def _get_response_file() -> Path:
    """Get the path to the MCP response JSON file."""
    return _get_fl_scripts_dir() / "mcp_response.json"


def _get_state_file() -> Path:
    """Get the path to the piano roll state JSON file."""
    return _get_fl_scripts_dir() / "piano_roll_state.json"


def _write_request(request: dict | list) -> None:
    """Write a request to the MCP request file."""
    request_file = _get_request_file()

    # Read existing requests if any
    existing = []
    if request_file.exists():
        try:
            with open(request_file) as f:
                data = json.load(f)
                if isinstance(data, list):
                    existing = data
                elif isinstance(data, dict):
                    existing = [data]
        except (json.JSONDecodeError, IOError):
            existing = []

    # Append new request(s)
    if isinstance(request, list):
        existing.extend(request)
    else:
        existing.append(request)

    # Write back
    with open(request_file, "w") as f:
        json.dump(existing, f, indent=2)


def _clear_request_file() -> None:
    """Clear the request file."""
    request_file = _get_request_file()
    if request_file.exists():
        request_file.unlink()


def _read_state() -> dict | None:
    """Read the current piano roll state."""
    state_file = _get_state_file()
    if not state_file.exists():
        return None

    try:
        with open(state_file) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def _midi_to_note_name(midi: int) -> str:
    """Convert MIDI note number to note name."""
    note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    note_name = note_names[midi % 12]
    octave = (midi // 12) - 1
    return f"{note_name}{octave}"


def _queue_is_empty() -> bool:
    """Whether the piano roll script has consumed every queued request."""
    request_file = _get_request_file()
    if not request_file.exists():
        return True
    try:
        return not json.loads(request_file.read_text() or "[]")
    except (json.JSONDecodeError, OSError):
        return False


def _wait_until(done, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while not done():
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    return True


def _open_piano_roll(channel: int | None) -> str | None:
    """Open the piano roll on `channel` (if given). Returns an error message or None."""
    if channel is None:
        return None
    result = get_connection().send_command("ui.openPianoRoll", {"channel": channel})
    if not result.get("success", False) and "error" in result:
        return f"Error: could not open the piano roll of channel {channel}: {result['error']}"
    return None


def _get_trigger_info(auto_trigger: bool) -> str:
    """Trigger FL Studio, check the script ran, and return a status suffix string."""
    if not auto_trigger:
        return ""
    trigger = get_trigger()
    if not trigger.is_supported:
        return f" Auto-trigger not supported on {trigger.platform}. Press the trigger key manually."
    if not trigger_fl_studio():
        return f" Warning: Could not trigger FL Studio. Press {trigger.keystroke} manually."
    if _wait_until(_queue_is_empty):
        return " Applied in FL Studio."
    return (
        " Warning: FL Studio did not run the piano roll script, so nothing changed yet."
        " A piano roll must be open (pass channel to open one), and ComposeWithLLM must"
        " have been run once this session from the piano roll's Tools > Scripting menu."
    )


def register_piano_roll_tools(mcp: FastMCP) -> None:
    """Register piano roll tools with the MCP server."""

    @mcp.tool()
    def fl_send_notes(
        notes: list[dict],
        mode: str = "add",
        auto_trigger: bool = True,
        channel: int | None = None,
    ) -> str:
        """Add or replace notes in the FL Studio piano roll.

        This creates persistent notes in the current pattern, for the channel
        whose piano roll is open. Pass `channel` to open that channel's piano
        roll first, so the notes (and a "replace" clear) can't land on the
        wrong instrument. Notes use quarter-note timing for simplicity.

        Args:
            notes: List of note objects with properties:
                   - midi (int): MIDI note number (60 = C4/Middle C)
                   - duration (float): Length in quarter notes (1.0 = quarter note)
                   - time (float, optional): Start position in quarter notes (default 0)
                   - velocity (float, optional): Velocity 0.0-1.0 (default 0.8)
                   - slide (bool, optional): Slide note - glides the pitch from the
                     previous note instead of retriggering (default False)
                   - porta (bool, optional): Portamento into this note (default False)
            mode: "add" to add notes, "replace" to clear existing notes first
            auto_trigger: Whether to automatically trigger FL Studio (default True)
            channel: Channel rack index whose piano roll should receive the notes
                     (default: whichever piano roll is open)

        Example notes:
            [
                {"midi": 60, "duration": 1.0, "time": 0},      # C4 quarter note at beat 0
                {"midi": 64, "duration": 1.0, "time": 0},      # E4 (chord with C4)
                {"midi": 67, "duration": 1.0, "time": 0},      # G4 (C major chord)
                {"midi": 60, "duration": 0.5, "time": 1.0},    # C4 eighth note at beat 1
            ]
        """
        if not notes:
            return "Error: No notes provided"

        # Validate notes
        for i, note in enumerate(notes):
            if "midi" not in note:
                return f"Error: Note {i} missing 'midi' field"
            if "duration" not in note:
                return f"Error: Note {i} missing 'duration' field"

            # Set defaults
            note.setdefault("time", 0)
            note.setdefault("velocity", 0.8)

        error = _open_piano_roll(channel)
        if error:
            return error

        requests = []

        # If replace mode, clear first
        if mode == "replace":
            requests.append({"action": "clear"})

        # Add notes request
        requests.append({
            "action": "add_notes",
            "notes": notes
        })

        _write_request(requests)

        trigger_info = _get_trigger_info(auto_trigger)
        note_count = len(notes)
        note_summary = ", ".join(
            f"{_midi_to_note_name(n['midi'])}@{n.get('time', 0)}"
            for n in notes[:5]
        )
        if note_count > 5:
            note_summary += f", ... ({note_count - 5} more)"

        return f"Queued {note_count} note(s): {note_summary}.{trigger_info}"

    @mcp.tool()
    def fl_send_chord(
        midi_notes: list[int],
        time: float = 0,
        duration: float = 1.0,
        velocity: float = 0.8,
        auto_trigger: bool = True,
        channel: int | None = None,
    ) -> str:
        """Add a chord (multiple simultaneous notes) to the FL Studio piano roll.

        This is a convenience function for adding multiple notes at the same time
        with the same duration. For more control, use fl_send_notes.

        Args:
            midi_notes: List of MIDI note numbers (e.g., [60, 64, 67] for C major)
            time: Start position in quarter notes (default 0)
            duration: Length in quarter notes for all notes (default 1.0)
            velocity: Velocity 0.0-1.0 for all notes (default 0.8)
            auto_trigger: Whether to automatically trigger FL Studio
            channel: Channel rack index whose piano roll should receive the chord
                     (default: whichever piano roll is open)

        Example - C major chord at beat 0:
            fl_send_chord([60, 64, 67], time=0, duration=1.0)

        Example - Am7 chord at beat 2:
            fl_send_chord([57, 60, 64, 67], time=2, duration=2.0)
        """
        if not midi_notes:
            return "Error: No MIDI notes provided"

        error = _open_piano_roll(channel)
        if error:
            return error

        # Build chord notes with velocity included
        chord_notes = [
            {"midi": midi, "velocity": velocity}
            for midi in midi_notes
        ]

        request = {
            "action": "add_chord",
            "time": time,
            "duration": duration,
            "notes": chord_notes
        }

        _write_request(request)

        trigger_info = _get_trigger_info(auto_trigger)
        note_names = ", ".join(_midi_to_note_name(n) for n in midi_notes)
        return f"Queued chord [{note_names}] at beat {time}, duration {duration}.{trigger_info}"

    @mcp.tool()
    def fl_delete_notes(
        notes: list[dict],
        auto_trigger: bool = True,
        channel: int | None = None,
    ) -> str:
        """Delete specific notes from the FL Studio piano roll.

        Args:
            notes: List of notes to delete, matching by midi and time:
                   - midi (int): MIDI note number
                   - time (float): Start position in quarter notes
            auto_trigger: Whether to automatically trigger FL Studio
            channel: Channel rack index whose piano roll to edit
                     (default: whichever piano roll is open)

        Example:
            [{"midi": 60, "time": 0}, {"midi": 64, "time": 0}]
        """
        if not notes:
            return "Error: No notes specified for deletion"

        error = _open_piano_roll(channel)
        if error:
            return error

        request = {
            "action": "delete_notes",
            "notes": notes
        }
        _write_request(request)

        trigger_info = _get_trigger_info(auto_trigger)
        return f"Queued deletion of {len(notes)} note(s).{trigger_info}"

    @mcp.tool()
    def fl_clear_piano_roll(auto_trigger: bool = True, channel: int | None = None) -> str:
        """Clear all notes from the FL Studio piano roll.

        Args:
            auto_trigger: Whether to automatically trigger FL Studio
            channel: Channel rack index whose notes to clear in the current pattern
                     (default: whichever piano roll is open)
        """
        error = _open_piano_roll(channel)
        if error:
            return error

        request = {"action": "clear"}
        _write_request(request)

        trigger_info = _get_trigger_info(auto_trigger)
        return f"Queued clear all notes.{trigger_info}"

    @mcp.tool()
    def fl_open_piano_roll(channel: int) -> str:
        """Open the piano roll on a channel (in the current pattern).

        Args:
            channel: Channel rack index
        """
        result = get_connection().send_command("ui.openPianoRoll", {"channel": channel})
        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"
        return f"Piano roll open on '{result.get('channel_name', channel)}'"

    @mcp.tool()
    def fl_get_current_pattern() -> dict:
        """Get the selected pattern - the one piano roll edits go to.

        Returns {"index", "name", "count"}; patterns are numbered from 1.
        """
        result = get_connection().send_command("patterns.getCurrent")
        if not result.get("success", False) and "error" in result:
            return {"error": result["error"]}
        return {k: result[k] for k in ("index", "name", "count")}

    @mcp.tool()
    def fl_select_pattern(index: int) -> str:
        """Select a pattern, so piano roll edits go to it.

        Args:
            index: Pattern number, from 1 (as shown in FL Studio)
        """
        result = get_connection().send_command("patterns.select", {"index": index})
        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"
        return f"Pattern {index} '{result.get('name', '')}' selected"

    @mcp.tool()
    def fl_create_pattern(name: str = "") -> str:
        """Create a new pattern (the first empty one) and select it.

        Args:
            name: Optional pattern name
        """
        result = get_connection().send_command("patterns.create", {"name": name})
        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"
        return f"Pattern {result.get('index')} '{result.get('name', '')}' created and selected"

    @mcp.tool()
    def fl_get_piano_roll_state(channel: int | None = None) -> dict:
        """Get the notes of a channel in the current pattern.

        Returns a dictionary containing:
        - ppq: Pulses per quarter note (ticks per beat)
        - notes: List of all notes with their properties

        Args:
            channel: Channel rack index to read. Its piano roll is opened and
                     the state is refreshed from FL Studio. Without it, this
                     returns the last exported state, which may be stale.
        """
        if channel is not None:
            if not _queue_is_empty():
                return {
                    "error": "Note requests are still queued; reading now would apply "
                             "them. Trigger or clear them first (fl_clear_request_queue)."
                }
            error = _open_piano_roll(channel)
            if error:
                return {"error": error}
            state_file = _get_state_file()
            before = state_file.stat().st_mtime if state_file.exists() else 0
            if not trigger_fl_studio() or not _wait_until(
                lambda: state_file.exists() and state_file.stat().st_mtime != before
            ):
                return {
                    "error": "FL Studio did not run the piano roll script. Run "
                             "ComposeWithLLM once from the piano roll's Tools > Scripting menu."
                }

        state = _read_state()

        if state is None:
            return {
                "error": "No piano roll state available. Make sure FL Studio's "
                         "ComposeWithLLM script has been run at least once."
            }

        # Add human-readable note names
        if "notes" in state:
            for note in state["notes"]:
                if "midi" in note:
                    note["note_name"] = _midi_to_note_name(note["midi"])

            if state["notes"] and all(note.get("selected") for note in state["notes"]):
                state["warning"] = (
                    "Every note listed is selected: FL Studio only shows piano roll "
                    "scripts the selected notes, so unselected ones may be missing (and "
                    "clear/delete only affect the selection). Deselect all in the piano "
                    "roll to see every note."
                )

        return state

    @mcp.tool()
    def fl_clear_request_queue() -> str:
        """Clear any pending note requests without executing them.

        Use this if you want to cancel queued changes before triggering FL Studio.
        """
        _clear_request_file()
        return "Request queue cleared."

    @mcp.tool()
    def fl_trigger_script() -> str:
        """Manually trigger FL Studio to process pending note requests.

        This sends the keystroke (Cmd+Opt+Y on macOS, Ctrl+Alt+Y on Windows)
        to FL Studio to execute the ComposeWithLLM piano roll script.
        """
        trigger = get_trigger()

        if not trigger.is_supported:
            return f"Error: Auto-trigger not supported on {trigger.platform}"

        success = trigger_fl_studio()

        if success:
            return "FL Studio triggered successfully. Notes should now appear in the piano roll."
        else:
            return f"Failed to trigger FL Studio. Try pressing {trigger.keystroke} manually."

    @mcp.tool()
    def fl_get_piano_roll_info() -> dict:
        """Get information about the Piano Roll integration status.

        Returns platform info, file paths, and whether auto-triggering is supported.
        """
        trigger = get_trigger()

        return {
            "platform": trigger.platform,
            "auto_trigger_supported": trigger.is_supported,
            "trigger_keystroke": trigger.keystroke,
            "scripts_dir": str(_get_fl_scripts_dir()),
            "request_file": str(_get_request_file()),
            "state_file": str(_get_state_file()),
            "request_file_exists": _get_request_file().exists(),
            "state_file_exists": _get_state_file().exists(),
        }
