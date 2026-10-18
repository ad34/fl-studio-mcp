"""FL Studio MCP tools."""

from fl_studio_mcp.tools.automation import register_automation_tools
from fl_studio_mcp.tools.channels import register_channel_tools
from fl_studio_mcp.tools.mixer import register_mixer_tools
from fl_studio_mcp.tools.piano_roll import register_piano_roll_tools
from fl_studio_mcp.tools.playlist import register_playlist_tools
from fl_studio_mcp.tools.plugins import register_plugin_tools
from fl_studio_mcp.tools.samples import register_sample_tools
from fl_studio_mcp.tools.transport import register_transport_tools

__all__ = [
    "register_transport_tools",
    "register_mixer_tools",
    "register_channel_tools",
    "register_plugin_tools",
    "register_piano_roll_tools",
    "register_playlist_tools",
    "register_sample_tools",
    "register_automation_tools",
]
