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
        result = conn.send_command("transport.start")

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        is_playing = result.get("is_playing", False)
        return f"Playback {'started' if is_playing else 'paused'}"

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

        Returns information about whether FL Studio is playing, recording,
        the current position, and loop mode.
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
    def fl_set_song_position(position: float, mode: int = 2) -> str:
        """Set the playback position in FL Studio.

        Args:
            position: The position value. Interpretation depends on mode.
            mode: Position format:
                  0 = Percentage (0.0 to 1.0)
                  1 = Time in milliseconds
                  2 = Time in seconds (default)
                  3 = Position in ticks
                  4 = Position as bars:steps:ticks (encoded)
        """
        conn = get_connection()
        result = conn.send_command("transport.setPosition", {
            "position": position,
            "mode": mode,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        new_pos = result.get("position", "")
        return f"Position set to {new_pos}"

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
