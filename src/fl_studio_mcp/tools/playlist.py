"""Playlist and arrangement tools for FL Studio (markers, track names and colors).

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

    @mcp.tool()
    def fl_get_markers() -> dict:
        """List the playlist markers' names, in timeline order.

        FL Studio's API doesn't expose marker positions, only their names.
        """
        result = get_connection().send_command("arrangement.getMarkers")
        if not result.get("success", False) and "error" in result:
            return {"error": result["error"]}
        return {"markers": result.get("markers", [])}

    @mcp.tool()
    def fl_add_markers(markers: list[dict], beats_per_bar: int = 4) -> str:
        """Add markers to the playlist, e.g. to lay out song sections.

        Markers can't be moved or deleted through the API, so a marker whose name
        already exists is skipped: re-running the same call adds nothing.

        Args:
            markers: List of {"bar": int, "name": str}; bars are numbered from 1
                     as in the playlist ruler
            beats_per_bar: Beats per bar of the song (default 4)
        """
        result = get_connection().send_command(
            "arrangement.addMarkers", {"markers": markers, "beats_per_bar": beats_per_bar}
        )
        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"
        added, skipped = result.get("added", []), result.get("skipped", [])
        text = f"Added {len(added)} marker(s): {', '.join(added) or '-'}"
        if skipped:
            text += f". Already present, skipped: {', '.join(skipped)}"
        return text

    @mcp.tool()
    def fl_get_playlist_tracks(count: int = 20) -> dict:
        """Get the names and colors of the first playlist tracks.

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
    def fl_set_playlist_track(index: int, name: str | None = None, color: int | None = None) -> str:
        """Rename and/or recolor a playlist track.

        Args:
            index: Playlist track number, from 1
            name: New name ("" restores "Track n")
            color: Color as 0xBBGGRR integer
        """
        params: dict = {"index": index}
        if name is not None:
            params["name"] = name
        if color is not None:
            params["color"] = color
        result = get_connection().send_command("playlist.setTrack", params)
        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"
        return f"Playlist track {index}: '{result.get('name')}'"
