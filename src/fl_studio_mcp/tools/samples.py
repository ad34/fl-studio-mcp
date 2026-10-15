"""Sample tools for FL Studio: find samples and load them into new Sampler channels."""

from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP

# Windows' path length limit (long paths are off by default)
MAX_PATH = 260
WINDOWS_ONLY = "Sample folders are read from FL Studio's Windows settings: Windows only"


def register_sample_tools(mcp: FastMCP) -> None:
    """Register sample search and loading tools with the MCP server."""
    from fl_studio_mcp.utils import channel_presets, samples
    from fl_studio_mcp.utils.connection import get_connection

    @mcp.tool()
    def fl_list_sample_folders() -> dict:
        """List the sample folders FL Studio's browser searches.

        These are the browser's extra search folders (Options > File settings)
        plus FL's own Packs, with how many audio files FL's index knows in each.
        Windows only.
        """
        if platform.system() != "Windows":
            return {"error": WINDOWS_ONLY}
        files = samples.cached_samples()
        folders = []
        for folder in samples.sample_folders():
            prefix = os.path.normcase(folder).rstrip("\\/") + os.sep
            folders.append({
                "folder": folder,
                "indexed_audio_files": sum(os.path.normcase(p).startswith(prefix) for p in files),
            })
        return {"folders": folders, "index": str(samples.search_cache_file())}

    @mcp.tool()
    def fl_find_samples(query: str, folder: str | None = None, limit: int = 20) -> dict:
        """Search the sample folders for audio files whose path contains every word of query.

        Searches FL Studio's own browser index, which covers the browser's
        extra search folders and FL's Packs. Words match anywhere in the path,
        so folder names count: "kick 808", "vocal chop Fmin", "cymatics snare".
        FL saves its index when it closes, so files added since are missing:
        give their folder (it is then searched directly when the index has
        nothing). Windows only.

        Args:
            query: Words to look for, e.g. "kick 808"
            folder: Only search inside this folder
            limit: Maximum number of results (default 20, at most 200)
        """
        if platform.system() != "Windows":
            return {"error": WINDOWS_ONLY}
        if folder and not os.path.isdir(folder):
            return {"error": f"Folder not found: {folder}"}
        limit = min(max(limit, 1), 200)
        found, total = samples.search_samples(query, folder, limit)
        result: dict = {"source": "FL's browser index"}
        if not found and folder:
            found, total, truncated = samples.search_folder(folder, query, limit)
            result["source"] = "folder scan"
            if truncated:
                result["note"] = "The folder is too big: only part of it was scanned"
        elif not found and not samples.cached_samples():
            return {"error": f"FL's browser index was not found ({samples.search_cache_file()}); "
                             "give a folder to scan"}
        too_long = sum(len(p) >= MAX_PATH for p in found)
        if too_long:
            note = (f"{too_long} of these paths are {MAX_PATH} characters or longer: "
                    "fl_load_sample can't load them")
            result["note"] = f"{result['note']}. {note}" if "note" in result else note
        return {"samples": found, "count": len(found), "total_matches": total, **result}

    @mcp.tool()
    def fl_load_sample(
        path: str, mixer_track: int | None = None, color: str | None = None
    ) -> str:
        """Load an audio file into a new Sampler channel (FL Studio's stock sampler).

        The channel is named after the sample and routed to a mixer track,
        which FL names after it too: the first free insert track by default.
        Both get a color. Each call adds a channel.
        Find files with fl_find_samples. The path must be shorter than 260
        characters and use Western (cp1252) characters.

        Args:
            path: Absolute path of the audio file (.wav, .aif, .flac, .mp3, .ogg...)
            mixer_track: Insert track to route the channel to (default: first free one)
            color: "#RRGGBB" for the channel and its mixer track (default: next
                color of a palette)
        """
        if len(path) >= MAX_PATH:
            return (f"Error: the path is {len(path)} characters long, over Windows' "
                    f"{MAX_PATH}-character limit: copy or move the file to a shorter path")
        if not os.path.isfile(path):
            return f"Error: file not found: {path}"
        if not path.lower().endswith(samples.AUDIO_EXTENSIONS):
            return f"Error: not an audio file FL can load: {path}"
        conn = get_connection()
        paths = channel_presets.bridge_paths(conn)
        if not paths.get("success", False) and "error" in paths:
            return f"Error: {paths['error']}"
        try:
            # FL's channel template for a new Sampler, with the sample in it
            template = (Path(paths["data_system"]) / "SamplerTrack.fst").read_bytes()
            preset_data = samples.sampler_preset(template, os.path.abspath(path))
        except (OSError, ValueError) as e:
            return f"Error: {e}"
        result = channel_presets.add_channel(
            conn, preset_data, Path(path).stem, mixer_track, color)
        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"
        return (f"Sampler channel {result.get('channel')} '{result.get('name')}' added, "
                f"routed to mixer track {result.get('mixer_track')} "
                f"'{result.get('mixer_track_name')}', color {result.get('color')}")
