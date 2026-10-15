"""Transport control tools for FL Studio."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_transport_tools(mcp: FastMCP) -> None:
    """Register transport control tools with the MCP server."""
    from fl_studio_mcp.utils.connection import get_connection
    from fl_studio_mcp.utils.fl_trigger import fl_project_file

    @mcp.tool()
    def fl_play() -> str:
        """Start or pause FL Studio playback.

        Toggles between play and pause states. If stopped, starts playback.
        If playing, pauses playback.
        """
        conn = get_connection()
        before = conn.send_command("transport.getStatus")
        result = conn.send_command("transport.start")

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        # FL starts or pauses after the command returns
        was_playing = before.get("is_playing", False)
        status = conn.read_until("transport.getStatus", None,
                                 lambda s: s.get("is_playing") != was_playing)
        return f"Playback {'started' if status.get('is_playing') else 'paused'}"

    @mcp.tool()
    def fl_stop() -> str:
        """Stop FL Studio playback completely.

        Stops playback and resets the playback position.
        """
        conn = get_connection()
        result = conn.send_command("transport.stop")

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        return "Playback stopped"

    @mcp.tool()
    def fl_record() -> str:
        """Toggle recording mode in FL Studio.

        When enabled, incoming MIDI and audio will be recorded.
        """
        conn = get_connection()
        result = conn.send_command("transport.record")

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        is_recording = result.get("is_recording", False)
        return f"Recording {'enabled' if is_recording else 'disabled'}"

    @mcp.tool()
    def fl_get_transport_status() -> dict:
        """Get current transport status including playback and recording state.

        Returns whether FL Studio is playing or recording, the position
        (bar:step:tick), the loop mode, the tempo, the bar length in ticks
        (from the time signature) and the playlist time selection, if any
        ({"start_bar", "end_bar", ...}, end_bar excluded; song playback stays
        inside it).
        """
        conn = get_connection()
        result = conn.send_command("transport.getStatus")

        if not result.get("success", False) and "error" in result:
            return {"error": result["error"]}

        return {
            "is_playing": result.get("is_playing", False),
            "is_recording": result.get("is_recording", False),
            "position": result.get("position", ""),
            "loop_mode": result.get("loop_mode", "pattern"),
            "tempo": result.get("tempo", 0),
            "ticks_per_bar": result.get("ticks_per_bar"),
            "selection": result.get("selection"),
        }

    @mcp.tool()
    def fl_set_tempo(bpm: float) -> str:
        """Set the project tempo.

        Args:
            bpm: Tempo in beats per minute (10 to 522, FL Studio's range)
        """
        if not 10 <= bpm <= 522:
            return "Error: Tempo must be between 10 and 522 BPM"

        conn = get_connection()
        result = conn.send_command("transport.setTempo", {"bpm": bpm})

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        status = conn.read_until(
            "transport.getStatus", {}, lambda r: abs(r.get("tempo", 0) - bpm) < 0.01
        )
        tempo = status.get("tempo", 0)
        if abs(tempo - bpm) >= 0.01:
            return f"Error: tempo is still {tempo:g} BPM"
        return f"Tempo set to {tempo:g} BPM"

    @mcp.tool()
    def fl_set_song_position(bar: float | None = None, seconds: float | None = None) -> str:
        """Move the playhead to a bar or a time. Give exactly one of them.

        In pattern mode this moves within the current pattern; switch to song
        mode first (fl_set_loop_mode) to move in the song. With a playlist
        time selection active, FL keeps the playhead inside it.

        Args:
            bar: Bar number from 1, as in the playlist ruler (2.5 = middle of
                bar 2); follows the project's time signature
            seconds: Time from the song start, in seconds
        """
        if (bar is None) == (seconds is None):
            return "Error: give either bar or seconds"
        if bar is not None:
            params: dict = {"bar": bar}
        elif seconds < 0:
            return "Error: seconds can't be negative"
        else:
            # FL's SONGLENGTH_S mode
            params = {"position": seconds, "mode": 1}
        conn = get_connection()
        result = conn.send_command("transport.setPosition", params)

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        # FL moves the playhead after the command returns: read it separately
        status = conn.send_command("transport.getStatus")
        text = f"Position set to {status.get('position', '')} (bar:step:tick)"
        if status.get("loop_mode") == "pattern":
            text += "; FL is in pattern mode, so this is a position in the pattern"
        selection = status.get("selection")
        if selection:
            text += (f"; a time selection (bars {selection['start_bar']} to "
                     f"{selection['end_bar']}, end excluded) keeps the playhead inside it")
        return text

    @mcp.tool()
    def fl_get_song_length() -> dict:
        """Get the total length of the current song/pattern.

        Returns the length in multiple formats for convenience.
        """
        conn = get_connection()
        result = conn.send_command("transport.getLength")

        if not result.get("success", False) and "error" in result:
            return {"error": result["error"]}

        return {
            "bars": result.get("bars", 0),
            "ticks": result.get("ticks", 0),
            "seconds": result.get("seconds", 0),
            "milliseconds": result.get("milliseconds", 0),
        }

    @mcp.tool()
    def fl_get_project_state() -> dict:
        """Get the open project's file name and whether it has unsaved changes.

        project_file comes from FL's window title (Windows only, else None).
        changed: 0 = saved, 1 = unsaved changes, 2 = unsaved but covered by
        FL's last autosave.
        """
        conn = get_connection()
        result = conn.send_command("project.getState")
        if not result.get("success", False) and "error" in result:
            return {"error": result["error"]}
        return {
            "project_file": fl_project_file(),
            "changed": result.get("changed"),
            "unsaved_changes": result.get("unsaved_changes"),
        }

    @mcp.tool()
    def fl_save_project(new_version: bool = False) -> str:
        """Save the open project, like Ctrl+S (or Ctrl+N with new_version).

        Changes made through these tools live only in the running FL Studio
        until the project is saved: save after each significant step.
        Refuses when the open file is one of FL's autosave backups, since
        saving would write into the Backup folder: Save As a real file first.

        Args:
            new_version: True to save as a new numbered version instead of
                overwriting the project file
        """
        conn = get_connection()
        project = fl_project_file()
        if project and "autosaved" in project.lower():
            return (
                f"Not saved: the open project is an autosave backup ({project}). "
                "Ask the user to use File > Save as to a real project file first."
            )

        result = conn.send_command("project.save", {"new_version": new_version})
        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"
        # FL saves after the command returns: confirm with separate reads
        after = conn.read_until("project.getState", None,
                                lambda s: s.get("changed") == 0, timeout=5.0)
        project = fl_project_file() or "project"
        if after.get("changed") != 0:
            return (f"Save requested but FL still reports unsaved changes "
                    f"({project}); a dialog may be open in FL.")
        return f"Saved: {project}"

    @mcp.tool()
    def fl_set_time_signature(numerator: int, denominator: int) -> str:
        """Set the project's time signature, e.g. 3/4 or 6/8.

        Bar numbers in the other tools (song position, markers, sections)
        follow it. Set it before adding markers: markers and clips keep their
        position in ticks, so their bar numbers change (and can become
        fractional). Time signature markers placed in the playlist are not
        taken into account. FL doesn't record the change in its undo history.

        Args:
            numerator: Beats per bar, 1-16
            denominator: Beat value: 2, 4, 8 or 16
        """
        result = get_connection().send_command(
            "project.setTimeSignature", {"numerator": numerator, "denominator": denominator}
        )
        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"
        return (f"Time signature set to {numerator}/{denominator} "
                f"({result.get('ticks_per_bar')} ticks per bar at {result.get('ppq')} PPQ)")

    @mcp.tool()
    def fl_get_undo_history() -> dict:
        """Get the position in FL Studio's undo history.

        position: how many steps back from the latest state (0 = nothing undone).
        length: number of entries in the history. hint: FL's "position/length".
        """
        result = get_connection().send_command("undo.getState")
        if not result.get("success", False) and "error" in result:
            return {"error": result["error"]}
        return {k: result.get(k) for k in ("position", "length", "hint")}

    # History length right after the last fl_save_undo_point of this server run
    save_point: dict = {}

    def _save_undo_point(name: str) -> str | None:
        """Add the undo point and remember it; returns an error message or None."""
        conn = get_connection()
        before = conn.send_command("undo.getState")
        if not before.get("success", False) and "error" in before:
            return f"Error: {before['error']}"
        result = conn.send_command("undo.savePoint", {"name": name})
        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"
        # Like any edit, the entry drops the undone (redo) entries above the
        # current position, and shows up after the command returns
        expected = before["length"] - before["position"] + 1
        after = conn.read_until("undo.getState", None,
                                lambda s: s.get("position") == 0 and s.get("length") == expected)
        if after.get("length") != expected or after.get("position") != 0:
            return "Error: FL Studio did not add the undo point"
        save_point.update(name=name, length=expected)
        return None

    @mcp.tool()
    def fl_save_undo_point(name: str = "MCP changes") -> str:
        """Snapshot notes, steps, patterns, the playlist and markers into FL's undo history.

        Call it before every batch of changes: FL doesn't record changes made
        through these tools to notes, steps, patterns or playlist tracks, so
        without a save point fl_undo can't revert them. Mixer and plugin knob
        changes and added markers get their own entries. fl_undo(to_save_point=True)
        then returns to this state. The point is kept in the server's memory
        and lost if the server restarts.

        Args:
            name: Entry name shown in FL's Edit > History
        """
        error = _save_undo_point(name)
        if error:
            return error
        return f"Undo point '{name}' saved (history entry {save_point['length']})"

    def _move_undo(steps: int) -> str:
        conn = get_connection()
        result = conn.send_command("undo.move", {"steps": steps})
        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"
        if "from_position" not in result:
            return "Error: unexpected response from FL Studio; reload the script in FL"
        # FL moves through the history after the command returns
        target = result["from_position"] + steps
        state = conn.read_until("undo.getState", None,
                                lambda s: s.get("position") == target)
        if not state.get("success", False) and "error" in state:
            return f"Error: undo requested but reading the history failed: {state['error']}"
        if state.get("position") != target:
            return (f"Error: FL's undo position is {state.get('position')}, "
                    f"expected {target}")
        return f"Undo history at {state.get('hint')} ({target} step(s) back from latest)"

    @mcp.tool()
    def fl_undo(steps: int = 1, to_save_point: bool = False) -> str:
        """Step back through FL Studio's undo history (Edit > History).

        Each step undoes FL's newest history entry, not necessarily your last
        tool call: changes made through these tools to notes, steps, patterns
        and playlist tracks create no entry, so a plain step undoes something
        older (a mixer change, a marker, or the user's own edit). To revert
        those changes, call fl_save_undo_point before the batch and use
        to_save_point=True.

        Args:
            steps: Number of history entries to step back (default 1)
            to_save_point: Instead of steps, return to the state saved by the
                last fl_save_undo_point, undoing every entry added since. The
                point is saved again right after, so the next batch can be
                reverted the same way (and nothing is left to redo).
        """
        if not to_save_point:
            if steps < 1:
                return "Error: steps must be at least 1"
            return _move_undo(steps)

        if not save_point:
            return "Error: no undo point saved yet (fl_save_undo_point)"
        name = save_point["name"]
        state = get_connection().send_command("undo.getState")
        if not state.get("success", False) and "error" in state:
            return f"Error: {state['error']}"
        added = state["length"] - save_point["length"]
        # Stepping back past the save point's entry restores its snapshot
        steps = added + 1 - state["position"]
        if added < 0 or steps <= 0:
            return (f"Error: undo point '{name}' is no longer reachable (the history "
                    f"was undone past it or cut); save a new one with fl_save_undo_point")
        moved = _move_undo(steps)
        if moved.startswith("Error"):
            return moved
        # Snapshot the restored state again, so a revert after the next batch works
        error = _save_undo_point(name)
        if error:
            return f"Back at undo point '{name}', but saving it again failed: {error}"
        return f"Back at undo point '{name}'; it is saved again for the next batch"

    @mcp.tool()
    def fl_redo(steps: int = 1) -> str:
        """Redo changes undone with fl_undo(steps).

        There is nothing to redo after fl_undo(to_save_point=True), which saves
        the point again.

        Args:
            steps: Number of history entries to step forward (default 1)
        """
        if steps < 1:
            return "Error: steps must be at least 1"
        return _move_undo(-steps)

    @mcp.tool()
    def fl_set_loop_mode(mode: str) -> str:
        """Set the loop mode between pattern and song.

        Args:
            mode: Either "pattern" or "song"
        """
        if mode not in ("pattern", "song"):
            return "Error: mode must be 'pattern' or 'song'"

        conn = get_connection()
        result = conn.send_command("transport.setLoopMode", {"mode": mode})

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        return f"Loop mode set to {mode}"

    @mcp.tool()
    def fl_set_playback_speed(speed: float) -> str:
        """Set the playback speed multiplier.

        Args:
            speed: Speed multiplier from 0.25 (quarter speed) to 4.0 (4x speed).
                   1.0 is normal speed.
        """
        if not 0.25 <= speed <= 4.0:
            return "Error: Speed must be between 0.25 and 4.0"

        conn = get_connection()
        result = conn.send_command("transport.setPlaybackSpeed", {"speed": speed})

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        return f"Playback speed set to {speed}x"
