"""Plugin control tools for FL Studio.

Effects can be loaded into mixer slots, and instruments into new channels,
from FL Studio's Plugin database.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_plugin_tools(mcp: FastMCP) -> None:
    """Register plugin control tools with the MCP server."""
    from fl_studio_mcp.utils import channel_presets
    from fl_studio_mcp.utils.connection import get_connection
    from fl_studio_mcp.utils.plugin_database import find_plugins

    @mcp.tool()
    def fl_find_plugins(query: str = "", kind: str | None = None, limit: int = 30) -> list[dict]:
        """Search the plugins installed in FL Studio (its Plugin database).

        Args:
            query: Words to look for in the plugin name, e.g. "reverb",
                   "fruity limiter", "valhalla". Empty lists everything.
            kind: "effect", "generator" (instrument), or None for both
            limit: Maximum number of results (default 30)
        """
        if kind not in (None, "effect", "generator"):
            return [{"error": "kind must be 'effect', 'generator' or None"}]

        entries = find_plugins(query, kind)
        if not entries:
            return [{"error": f"No installed plugin matches '{query}'"}]

        return [
            {"name": entry.name, "kind": entry.kind, "format": entry.format}
            for entry in entries[:limit]
        ]

    @mcp.tool()
    def fl_load_effect(name: str, track: int) -> dict:
        """Load an effect plugin into the next free slot of a mixer track.

        Works with any effect FL Studio knows about (Fruity, VST, VST3...).
        FL opens the plugin's window after loading it.

        Args:
            name: Effect name as listed by fl_find_plugins, e.g. "Fruity Reeverb 2"
            track: Mixer track index (0 = Master)
        """
        matches = find_plugins(name, "effect")
        if not matches:
            return {"error": f"No installed effect matches '{name}'. Use fl_find_plugins."}
        exact = [entry for entry in matches if entry.name.lower() == name.lower().strip()]
        if not exact and len(matches) > 1:
            return {
                "error": f"'{name}' matches several effects, use the exact name",
                "candidates": [entry.name for entry in matches[:15]],
            }
        plugin = (exact or matches)[0]

        conn = get_connection()
        # Big plugins can take a few seconds to load
        result = conn.send_command(
            "mixer.loadPlugin",
            {"track": track, "preset_path": str(plugin.path)},
            timeout=30.0,
        )

        if not result.get("success", False) and "error" in result:
            return {"error": result["error"]}

        return {
            "track": result.get("track", track),
            "track_name": result.get("track_name", ""),
            "loaded": result.get("loaded", []),
        }

    @mcp.tool()
    def fl_load_instrument(
        name: str,
        channel_name: str | None = None,
        mixer_track: int | None = None,
        color: str | None = None,
    ) -> dict:
        """Add an instrument (generator) plugin to the channel rack as a new channel.

        Works with any instrument FL Studio knows about: its own (3x Osc, FLEX,
        Sytrus, FPC...) and VST/VST3 ones (Serum 2...). The channel is routed
        to a mixer track, which FL names after the channel: the first free
        insert track by default. Both get a color. Each call adds a channel.

        Args:
            name: Instrument name as listed by fl_find_plugins(kind="generator")
            channel_name: Name for the new channel (default: the plugin's name)
            mixer_track: Insert track to route the channel to (default: first free one)
            color: "#RRGGBB" for the channel and its mixer track (default: next
                color of a palette)
        """
        matches = find_plugins(name, "generator")
        if not matches:
            return {"error": f"No installed instrument matches '{name}'. Use fl_find_plugins."}
        exact = [entry for entry in matches if entry.name.lower() == name.lower().strip()]
        if not exact and len(matches) > 1:
            return {
                "error": f"'{name}' matches several instruments, use the exact name",
                "candidates": [entry.name for entry in matches[:15]],
            }
        plugin = (exact or matches)[0]
        try:
            preset_data = plugin.path.read_bytes()
        except OSError as e:
            return {"error": f"Can't read the plugin's preset {plugin.path}: {e}"}

        result = channel_presets.add_channel(
            get_connection(), preset_data, channel_name or plugin.name, mixer_track, color)
        if not result.get("success", False) and "error" in result:
            return {"error": result["error"]}
        return {
            "channel": result.get("channel"),
            "name": result.get("name"),
            "plugin": plugin.name,
            "mixer_track": result.get("mixer_track"),
            "mixer_track_name": result.get("mixer_track_name"),
            "color": result.get("color"),
        }

    @mcp.tool()
    def fl_is_plugin_valid(
        index: int,
        slot_index: int = -1,
        use_global_index: bool = True
    ) -> bool:
        """Check if a plugin exists at the given location.

        For channel rack plugins, use just index.
        For mixer effect plugins, use index as mixer track and slot_index as effect slot.

        Args:
            index: Channel index (global) or mixer track index
            slot_index: Effect slot index for mixer plugins (-1 for channel rack)
            use_global_index: Whether to use global channel indexing
        """
        conn = get_connection()
        result = conn.send_command("plugins.isValid", {
            "index": index,
            "slot_index": slot_index,
            "use_global": use_global_index,
        })

        if not result.get("success", False) and "error" in result:
            return False

        return result.get("valid", False)

    @mcp.tool()
    def fl_get_plugin_name(
        index: int,
        slot_index: int = -1,
        use_global_index: bool = True
    ) -> str:
        """Get the name of a plugin.

        Args:
            index: Channel index (global) or mixer track index
            slot_index: Effect slot index for mixer plugins (-1 for channel rack)
            use_global_index: Whether to use global channel indexing
        """
        conn = get_connection()
        result = conn.send_command("plugins.getName", {
            "index": index,
            "slot_index": slot_index,
            "use_global": use_global_index,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        return result.get("name", "")

    @mcp.tool()
    def fl_get_plugin_param_count(
        index: int,
        slot_index: int = -1,
        use_global_index: bool = True
    ) -> int:
        """Get the number of parameters a plugin has.

        Args:
            index: Channel index (global) or mixer track index
            slot_index: Effect slot index for mixer plugins (-1 for channel rack)
            use_global_index: Whether to use global channel indexing
        """
        conn = get_connection()
        result = conn.send_command("plugins.getParamCount", {
            "index": index,
            "slot_index": slot_index,
            "use_global": use_global_index,
        })

        if not result.get("success", False) and "error" in result:
            return -1

        return result.get("count", 0)

    @mcp.tool()
    def fl_get_plugin_params(
        index: int,
        slot_index: int = -1,
        use_global_index: bool = True,
        max_params: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Get the parameters of a plugin with their current values.

        Big plugins (VSTs like Serum expose thousands of slots) need paging
        with offset, or use fl_find_plugin_params to search by name.

        For a mixer effect, the first entry (index "slot_mix") is not a plugin
        parameter but the slot's Mix knob (dry/wet) in the mixer, which scales
        the whole effect. Change it with fl_set_fx_mix.

        Args:
            index: Channel index (global) or mixer track index
            slot_index: Effect slot index for mixer plugins (-1 for channel rack)
            use_global_index: Whether to use global channel indexing
            max_params: Maximum number of parameters to return (default 50)
            offset: Index of the first parameter to return (default 0)
        """
        conn = get_connection()
        result = conn.send_command("plugins.getParams", {
            "index": index,
            "slot_index": slot_index,
            "use_global": use_global_index,
            "max_params": max_params,
            "offset": offset,
        }, timeout=15.0)

        if not result.get("success", False) and "error" in result:
            return [{"error": result["error"]}]

        params = result.get("params", [])
        slot = result.get("slot")
        if slot:
            params.insert(0, {
                "index": "slot_mix",
                "name": "Mixer slot Mix (dry/wet)",
                "value": slot.get("mix"),
                "value_string": slot.get("mix_display", ""),
                "slot_enabled": slot.get("enabled", True),
            })
        return params

    @mcp.tool()
    def fl_find_plugin_params(
        index: int,
        query: str,
        slot_index: int = -1,
        use_global_index: bool = True,
        max_results: int = 40,
    ) -> list[dict]:
        """Search a plugin's parameters by name (case-insensitive substring).

        Use it on big plugins, e.g. query "env 1" or "cutoff" on Serum.

        Args:
            index: Channel index (global) or mixer track index
            query: Text to look for in parameter names
            slot_index: Effect slot index for mixer plugins (-1 for channel rack)
            use_global_index: Whether to use global channel indexing
            max_results: Maximum number of matches to return (default 40)
        """
        if not query.strip():
            return [{"error": "query must not be empty"}]

        conn = get_connection()
        result = conn.send_command("plugins.getParams", {
            "index": index,
            "slot_index": slot_index,
            "use_global": use_global_index,
            "max_params": max_results,
            "name_filter": query.strip(),
        }, timeout=15.0)

        if not result.get("success", False) and "error" in result:
            return [{"error": result["error"]}]

        matches = result.get("params", [])
        if not matches:
            return [{"error": f"No parameter name contains '{query}'"}]
        return matches

    @mcp.tool()
    def fl_get_plugin_param_value(
        param_index: int,
        plugin_index: int,
        slot_index: int = -1,
        use_global_index: bool = True
    ) -> dict:
        """Get the value of a specific plugin parameter.

        Args:
            param_index: Parameter index
            plugin_index: Channel index (global) or mixer track index
            slot_index: Effect slot index for mixer plugins (-1 for channel rack)
            use_global_index: Whether to use global channel indexing
        """
        conn = get_connection()
        result = conn.send_command("plugins.getParamValue", {
            "param_index": param_index,
            "plugin_index": plugin_index,
            "slot_index": slot_index,
            "use_global": use_global_index,
        })

        if not result.get("success", False) and "error" in result:
            return {"error": result["error"]}

        return {
            "index": result.get("index", param_index),
            "name": result.get("name", ""),
            "value": result.get("value", 0),
            "value_string": result.get("value_string", ""),
        }

    @mcp.tool()
    def fl_set_plugin_param_value(
        param_index: int,
        value: float,
        plugin_index: int,
        slot_index: int = -1,
        use_global_index: bool = True
    ) -> str:
        """Set the value of a plugin parameter.

        Args:
            param_index: Parameter index
            value: New value (typically 0.0 to 1.0, but depends on parameter)
            plugin_index: Channel index (global) or mixer track index
            slot_index: Effect slot index for mixer plugins (-1 for channel rack)
            use_global_index: Whether to use global channel indexing
        """
        conn = get_connection()
        location = {
            "param_index": param_index,
            "plugin_index": plugin_index,
            "slot_index": slot_index,
            "use_global": use_global_index,
        }

        def applied(read: dict) -> bool:
            return abs(read.get("value", -1.0) - value) < 0.002

        # FL intermittently ignores a write (VST3 effects as well as Fruity
        # ones), and the value it reports inside the same command is stale.
        # Confirm with separate reads and write again until it holds.
        attempts = 6
        for attempt in range(1, attempts + 1):
            result = conn.send_command("plugins.setParamValue", {**location, "value": value})
            if not result.get("success", False) and "error" in result:
                return f"Error: {result['error']}"
            read = conn.read_until("plugins.getParamValue", location, applied, timeout=0.5)
            if applied(read):
                break

        name = read.get("name", result.get("name", f"Parameter {param_index}"))
        value_str = read.get("value_string", "")
        if not applied(read):
            return (
                f"Parameter '{name}' did not take {value:.4f} after {attempts} writes; "
                f"it reads {read.get('value', 0):.4f} ({value_str}). An automation clip "
                "or a controller link (e.g. Fruity peak controller) may drive it: "
                "use fl_set_fx_mix on the slot instead."
            )
        retries = f" after {attempt} writes" if attempt > 1 else ""
        return f"Parameter '{name}' set to {read['value']:.4f} ({value_str}){retries}"

    @mcp.tool()
    def fl_get_preset_count(
        index: int,
        slot_index: int = -1,
        use_global_index: bool = True
    ) -> int:
        """Get the number of presets available for a plugin.

        Args:
            index: Channel index (global) or mixer track index
            slot_index: Effect slot index for mixer plugins (-1 for channel rack)
            use_global_index: Whether to use global channel indexing
        """
        conn = get_connection()
        result = conn.send_command("plugins.getPresetCount", {
            "index": index,
            "slot_index": slot_index,
            "use_global": use_global_index,
        })

        if not result.get("success", False) and "error" in result:
            return -1

        return result.get("count", 0)

    @mcp.tool()
    def fl_next_preset(
        index: int,
        slot_index: int = -1,
        use_global_index: bool = True
    ) -> str:
        """Switch to the next preset for a plugin.

        Args:
            index: Channel index (global) or mixer track index
            slot_index: Effect slot index for mixer plugins (-1 for channel rack)
            use_global_index: Whether to use global channel indexing
        """
        conn = get_connection()
        result = conn.send_command("plugins.nextPreset", {
            "index": index,
            "slot_index": slot_index,
            "use_global": use_global_index,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        plugin_name = result.get("plugin_name", "Plugin")
        return f"Switched '{plugin_name}' to next preset"

    @mcp.tool()
    def fl_prev_preset(
        index: int,
        slot_index: int = -1,
        use_global_index: bool = True
    ) -> str:
        """Switch to the previous preset for a plugin.

        Args:
            index: Channel index (global) or mixer track index
            slot_index: Effect slot index for mixer plugins (-1 for channel rack)
            use_global_index: Whether to use global channel indexing
        """
        conn = get_connection()
        result = conn.send_command("plugins.prevPreset", {
            "index": index,
            "slot_index": slot_index,
            "use_global": use_global_index,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        plugin_name = result.get("plugin_name", "Plugin")
        return f"Switched '{plugin_name}' to previous preset"

    @mcp.tool()
    def fl_get_plugin_color(
        index: int,
        slot_index: int = -1,
        use_global_index: bool = True
    ) -> str:
        """Get the color of a plugin.

        Args:
            index: Channel index (global) or mixer track index
            slot_index: Effect slot index for mixer plugins (-1 for channel rack)
            use_global_index: Whether to use global channel indexing
        """
        conn = get_connection()
        result = conn.send_command("plugins.getColor", {
            "index": index,
            "slot_index": slot_index,
            "use_global": use_global_index,
        })

        if not result.get("success", False) and "error" in result:
            return f"Error: {result['error']}"

        return result.get("color", "0x0")
