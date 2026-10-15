"""Playlist and arrangement tools for FL Studio (markers, track names, colors, mute, solo).

FL Studio's scripting API can't place or read clips in the playlist; markers are
the way to lay out a song structure for the user to fill in.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_playlist_tools(mcp: FastMCP) -> None:
    """Register playlist and arrangement tools with the MCP server."""
    from fl_studio_mcp.utils.connection import get_connection

    def _set_mode(conn, mode: str) -> bool:
        """Put FL in "song" or "pattern" mode and wait until it has switched."""
        conn.send_command("transport.setLoopMode", {"mode": mode})
        # FL switches after the command returns: confirm every switch, so no
        # pending one can land in the middle of a later command
        status = conn.read_until("transport.getStatus", None,
                                 lambda s: s.get("loop_mode") == mode)
        return status.get("loop_mode") == mode

    def _marker_names(conn) -> list | dict:
        result = conn.send_command("arrangement.getMarkers")
        if not result.get("success", False) and "error" in result:
            return {"error": result["error"]}
        return [{"index": i, "name": name, "bar": None, "end_bar": None}
                for i, name in enumerate(result.get("markers", []))]

    @mcp.tool()
    def fl_get_markers() -> dict:
        """List the playlist markers in timeline order, with their positions.

        Returns {"markers": [{"index", "name", "bar", "end_bar"}]}. A marker's
        section runs from its bar up to end_bar, the next marker's bar (None
        for the last one). Bars count from 1, follow the project's time
        signature and can be fractional. bar is None when FL can't locate the
        marker (two markers at the same position). Reading positions briefly
        switches FL to song mode and moves the playhead, then puts both back;
        while FL is playing, only the names are returned.
        """
        conn = get_connection()
        names = _marker_names(conn)
        if isinstance(names, dict) or not names:
            return names if isinstance(names, dict) else {"markers": []}
        status = conn.send_command("transport.getStatus")
        if status.get("is_playing") or status.get("is_recording"):
            return {"markers": names, "note": "Stop playback to read marker positions"}
        previous = status.get("loop_mode")
        if previous != "song" and not _set_mode(conn, "song"):
            return {"markers": names, "note": "Could not switch to song mode to read positions"}
        result = conn.send_command("arrangement.getMarkerSections")
        if previous == "pattern":
            _set_mode(conn, "pattern")
        if not result.get("success", False) and "error" in result:
            return {"markers": names, "note": f"Positions unavailable: {result['error']}"}
        return {"markers": [{k: m[k] for k in ("index", "name", "bar", "end_bar")}
                            for m in result.get("markers", [])]}

    @mcp.tool()
    def fl_loop_section(
        marker: str | None = None,
        start_bar: float | None = None,
        end_bar: float | None = None,
    ) -> str:
        """Select a section of the song to loop: switch FL to song mode, select
        the section in the playlist and move the playhead to its start.

        This doesn't start playback: fl_play then plays the section in a loop.
        The selection stays, and keeps song playback inside it, until
        fl_clear_time_selection or the next fl_loop_section.

        Give a marker name (its section runs up to the next marker), or
        start_bar and end_bar. end_bar is exclusive: start_bar=9, end_bar=17
        loops bars 9 to 16. With a marker, start_bar is ignored and end_bar
        overrides the section end; the last marker has no end, so give end_bar.

        Args:
            marker: Marker name, as listed by fl_get_markers
            start_bar: First bar of the section, from 1
            end_bar: Bar where the section ends (exclusive)
        """
        if marker is None:
            if start_bar is None or end_bar is None:
                return "Error: give a marker name, or start_bar and end_bar"
            if start_bar < 1 or end_bar <= start_bar:
                return "Error: need 1 <= start_bar < end_bar"
        conn = get_connection()
        status = conn.send_command("transport.getStatus")
        if not status.get("success", False) and "error" in status:
            return f"Error: {status['error']}"
        previous = status.get("loop_mode")
        if previous != "song" and not _set_mode(conn, "song"):
            return "Error: could not switch FL Studio to song mode"

        def fail(message: str) -> str:
            if previous == "pattern":
                _set_mode(conn, "pattern")
            return f"Error: {message}"

        ticks_per_bar = status.get("ticks_per_bar") or 384
        if marker is not None:
            sections = conn.send_command("arrangement.getMarkerSections")
            if not sections.get("success", False) and "error" in sections:
                return fail(sections["error"])
            markers = sections.get("markers", [])
            found = ([m for m in markers if m["name"] == marker]
                     or [m for m in markers if m["name"].lower() == marker.lower()])
            if not found:
                names = ", ".join(m["name"] for m in markers)
                return fail(f"no marker named '{marker}' (markers: {names or 'none'})")
            if found[0]["start_tick"] is None:
                return fail(f"FL can't locate marker '{marker}' (it probably shares its "
                            f"position with another marker); give start_bar and end_bar")
            start = found[0]["start_tick"]
            end = found[0]["end_tick"]
            if end_bar is not None:
                end = round((end_bar - 1) * ticks_per_bar)
            elif end is None:
                return fail(f"'{marker}' is the last marker; give end_bar as well")
        else:
            start = round((start_bar - 1) * ticks_per_bar)
            end = round((end_bar - 1) * ticks_per_bar)

        result = conn.send_command("arrangement.setSelection",
                                   {"start_tick": start, "end_tick": end, "move_playhead": False})
        if not result.get("success", False) and "error" in result:
            return fail(result["error"])
        selection = result.get("selection") or {}
        # Moving the playhead in the same command as the selection doesn't stick
        conn.send_command("transport.setPosition", {"position": start, "mode": 2})
        name = f"'{marker}' " if marker is not None else ""
        return (f"Selected {name}bars {selection.get('start_bar')} to "
                f"{selection.get('end_bar')} (end excluded) in song mode, playhead at its "
                f"start. fl_play plays it in a loop; fl_clear_time_selection removes it.")

    @mcp.tool()
    def fl_clear_time_selection() -> str:
        """Remove the playlist time selection, so song playback is no longer kept inside it."""
        result = get_connection().send_command("arrangement.clearSelection")
        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"
        return "Time selection cleared"

    @mcp.tool()
    def fl_delete_marker(name: str) -> str:
        """Delete a playlist marker by name.

        Briefly switches FL to song mode to locate it, then puts the mode back.

        Args:
            name: Marker name, as listed by fl_get_markers
        """
        conn = get_connection()
        status = conn.send_command("transport.getStatus")
        if not status.get("success", False) and "error" in status:
            return f"Error: {status['error']}"
        if status.get("is_playing") or status.get("is_recording"):
            return "Error: stop playback first"
        previous = status.get("loop_mode")
        if previous != "song" and not _set_mode(conn, "song"):
            return "Error: could not switch FL Studio to song mode"
        result = conn.send_command("arrangement.deleteMarker", {"name": name})
        if previous == "pattern":
            _set_mode(conn, "pattern")
        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"
        return f"Marker '{name}' at bar {result.get('bar')} deleted"

    @mcp.tool()
    def fl_add_markers(markers: list[dict], beats_per_bar: int | None = None) -> str:
        """Add markers to the playlist, e.g. to lay out song sections.

        A marker whose name already exists is skipped, so re-running the same
        call adds nothing; so is one at a position that already has a marker.
        Markers can't be moved: delete one (fl_delete_marker) and add it
        again. Each added marker is an undo entry.

        Args:
            markers: List of {"bar": int, "name": str}; bars are numbered from 1
                     as in the playlist ruler
            beats_per_bar: Quarter notes per bar; by default the project's
                time signature sets the bar length
        """
        params: dict = {"markers": markers}
        if beats_per_bar is not None:
            params["beats_per_bar"] = beats_per_bar
        result = get_connection().send_command("arrangement.addMarkers", params)
        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"
        added, skipped = result.get("added", []), result.get("skipped", [])
        text = f"Added {len(added)} marker(s): {', '.join(added) or '-'}"
        if skipped:
            text += f". Already present, skipped: {', '.join(skipped)}"
        for clash in result.get("occupied", []):
            taken_by = f" by '{clash['taken_by']}'" if clash.get("taken_by") else ""
            text += f". Bar {clash['bar']} is already taken{taken_by}: '{clash['name']}' not added"
        return text

    @mcp.tool()
    def fl_get_playlist_tracks(count: int = 20) -> dict:
        """Get the names, colors, mute and solo state of the first playlist tracks.

        Playlist tracks are numbered from 1. Unnamed tracks are called "Track n".
        The API can't tell which clips a track holds.

        Args:
            count: How many tracks to read, from track 1 (default 20)
        """
        result = get_connection().send_command("playlist.getTracks", {"count": count})
        if not result.get("success", False) and "error" in result:
            return {"error": result["error"]}
        return {"tracks": result.get("tracks", [])}

    @mcp.tool()
    def fl_set_playlist_track(
        index: int,
        name: str | None = None,
        color: int | None = None,
        muted: bool | None = None,
        solo: bool | None = None,
    ) -> str:
        """Rename, recolor, mute and/or solo a playlist track.

        Args:
            index: Playlist track number, from 1
            name: New name ("" restores "Track n")
            color: Color as 0xRRGGBB integer
            muted: True to mute the track, False to unmute it
            solo: True to solo the track (FL mutes every other track); False
                unsolos it and unmutes every track, including ones muted before
        """
        params: dict = {"index": index}
        if name is not None:
            params["name"] = name
        if color is not None:
            params["color"] = color
        if muted is not None:
            params["muted"] = muted
        if solo is not None:
            params["solo"] = solo
        conn = get_connection()
        result = conn.send_command("playlist.setTrack", params)
        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        def track_of(tracks: dict) -> dict:
            return next((t for t in tracks.get("tracks", []) if t.get("index") == index), {})

        # Mute and solo can apply after the command returns: read them back
        def applied(tracks: dict) -> bool:
            track = track_of(tracks)
            return all(track.get(f"is_{k}") == params[k] for k in ("muted", "solo") if k in params)

        tracks = conn.read_until("playlist.getTracks", {"index": index}, applied)
        if not tracks.get("success", False) and "error" in tracks:
            return f"Error: {tracks['error']}"
        track = track_of(tracks)
        text = (f"Playlist track {index}: '{track.get('name')}'"
                f"{', muted' if track.get('is_muted') else ''}"
                f"{', solo' if track.get('is_solo') else ''}")
        if not applied(tracks):
            return f"Error: FL Studio did not apply mute/solo. {text}"
        return text
