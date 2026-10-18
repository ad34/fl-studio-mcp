"""Find samples in the folders FL Studio's browser lists.

FL keeps a text index of every browser folder (the user's extra search
folders and its own Packs) in Settings/Browser/SearchCache: searching it is
instant, where walking the folders can mean hundreds of gigabytes. FL saves it
when it closes, so files added since (or before a crash) are missing;
search_folder() walks a folder directly for those. Windows only: the folders
come from FL's registry settings.
"""

from __future__ import annotations

import os
import platform
import re
from pathlib import Path

from fl_studio_mcp.utils.channel_presets import fst_bytes, fst_events

AUDIO_EXTENSIONS = (".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg", ".wv", ".m4a", ".rx2")

_cache: dict = {"mtime": None, "files": []}


def _registry_value(key: str, name: str) -> str | None:
    """A value under HKCU\\Software\\Image-Line, or None (Windows only)."""
    if platform.system() != "Windows":
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"Software\Image-Line\{key}") as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def _registry_subkeys() -> list[str]:
    """Keys under HKCU\\Software\\Image-Line (Windows only)."""
    if platform.system() != "Windows":
        return []
    import winreg

    keys = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Image-Line") as k:
            while True:
                keys.append(winreg.EnumKey(k, len(keys)))
    except OSError:
        pass
    return keys


def _documents() -> Path:
    return Path(os.environ.get("USERPROFILE", Path.home())) / "Documents"


def fl_install_dir() -> Path | None:
    install = _registry_value("Shared\\Paths", "Install path")
    return Path(install) if install else None


def _placeholders() -> dict[str, str]:
    """What the %...% names in FL's browser files stand for."""
    shared = (_registry_value("Shared\\Paths", "Shared data")
              or str(_documents() / "Image-Line") + os.sep)
    values = {
        "%FLStudioUserData%": str(_documents() / "Image-Line" / "FL Studio"),
        "%ILSharedData%": shared,
        "%FLStudioDownloadsData%": str(_documents() / "Image-Line" / "Downloads"),
    }
    install = fl_install_dir()
    if install:
        values["%FLStudioFactoryData%"] = str(install)
    return values


def search_cache_file() -> Path:
    return _documents() / "Image-Line" / "FL Studio" / "Settings" / "Browser" / "SearchCache"


def _settings_key() -> str | None:
    """FL's settings key: "FL Studio 26" for FL Studio 2026.

    Several versions can have one, so prefer the installed one's.
    """
    versions = [m.group(1) for m in map(re.compile(r"FL Studio (\d+)").fullmatch,
                                        _registry_subkeys()) if m]
    if not versions:
        return None
    install = fl_install_dir()
    year = re.search(r"(\d{2})$", install.name) if install else None
    if year and year.group(1) in versions:
        return f"FL Studio {year.group(1)}"
    return f"FL Studio {max(versions, key=int)}"


def sample_folders() -> list[str]:
    """The browser's extra search folders (Options > File settings), plus FL's Packs."""
    folders = []
    install = fl_install_dir()
    key = _settings_key()
    for index in range(30):  # FL allows 30 extra search folders
        value = _registry_value(f"{key}\\Search paths", str(index)) if key else None
        if not value:
            break
        # Stored as "<folder>\,<second field>"; a drive keeps its "\" ("D:\")
        folder = value.rsplit(",", 1)[0]
        folders.append(folder if len(folder) <= 3 else folder.rstrip("\\"))
    if install and (install / "Data" / "Patches" / "Packs").is_dir():
        folders.append(str(install / "Data" / "Patches" / "Packs"))
    return folders


def _fields(line: str) -> list[str]:
    """Comma-separated fields of an index line; quoted ones ('it''s') unquoted."""
    fields, i = [], 0
    while True:
        if line[i:i + 1] == "'":
            out, i = [], i + 1
            while i < len(line):
                if line[i] == "'":
                    if line[i + 1:i + 2] != "'":
                        break
                    i += 1
                out.append(line[i])
                i += 1
            fields.append("".join(out))
            i = line.find(",", i)
        else:
            end = line.find(",", i)
            fields.append(line[i:] if end < 0 else line[i:end])
            i = end
        if i < 0:
            return fields
        i += 1


# Rows of folders (and plugins) in FL's index have this type
_FOLDER_TYPE = "-100"


def cached_samples() -> list[str]:
    """Absolute paths of every audio file in FL's browser index (re-read when it changes)."""
    path = search_cache_file()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return []
    if _cache["mtime"] == mtime:
        return _cache["files"]
    placeholders = _placeholders()
    files, folder = [], None
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if not line.startswith("'"):
                continue
            fields = _fields(line)
            header = re.fullmatch(r"(.*)\|\d+", fields[0]) if len(fields) == 1 else None
            if header:
                # Folder header: 'C:\Samples\Kicks\|0'
                folder = header.group(1)
                for name, value in placeholders.items():
                    folder = folder.replace(name, value)
                continue
            name = fields[0]
            is_folder = len(fields) > 4 and fields[4] == _FOLDER_TYPE
            if folder and not is_folder and name.lower().endswith(AUDIO_EXTENSIONS):
                files.append(os.path.join(folder, name))
    _cache.update(mtime=mtime, files=files)
    return files


def _matches(path: str, words: list[str]) -> bool:
    text = path.lower()
    return all(word in text for word in words)


def _rank(path: str, words: list[str]) -> tuple:
    # Words found in the file name first, then shorter paths
    name = os.path.basename(path).lower()
    return (-sum(word in name for word in words), len(path))


def search_samples(
    query: str, folder: str | None = None, limit: int = 20
) -> tuple[list[str], int]:
    """Audio files whose path contains every word of `query`, best matches
    first, and how many matched in all."""
    words = query.lower().split()
    files = cached_samples()
    if folder:
        prefix = os.path.normcase(os.path.abspath(folder)).rstrip("\\/") + os.sep
        files = [p for p in files if os.path.normcase(p).startswith(prefix)]
    found = [p for p in files if _matches(p, words)]
    return sorted(found, key=lambda p: _rank(p, words))[:limit], len(found)


def search_folder(
    folder: str, query: str = "", limit: int = 20, max_files: int = 200_000
) -> tuple[list[str], int, bool]:
    """Walk a folder for audio files, for files FL's index doesn't have yet.

    Returns the best matches, how many matched in all, and whether the walk
    stopped at `max_files` files.
    """
    words = query.lower().split()
    found, seen = [], 0
    for root, _dirs, names in os.walk(folder):
        names = names[:max_files - seen]
        seen += len(names)
        for name in names:
            if name.lower().endswith(AUDIO_EXTENSIONS):
                path = os.path.join(root, name)
                if _matches(path, words):
                    found.append(path)
        if seen >= max_files:
            break
    return sorted(found, key=lambda p: _rank(p, words))[:limit], len(found), seen >= max_files


# Event IDs in FL's state files (.fst), as in project files
FST_CHANNEL_NAME = 192
FST_SAMPLE_FILE = 196


def sampler_preset(template: bytes, sample_path: str) -> bytes:
    """FL's SamplerTrack.fst channel template with a sample file added."""
    header = template[:8 + int.from_bytes(template[4:8], "little")]
    try:
        # The template is in FL 9 format, where texts are ANSI
        path = sample_path.encode("cp1252") + b"\0"
    except UnicodeEncodeError:
        raise ValueError("FL's Sampler presets can't hold this path (non-Western "
                         "characters): copy or rename the file") from None
    events = []
    for event_id, value in fst_events(template):
        if event_id == FST_SAMPLE_FILE:
            continue
        if event_id == FST_CHANNEL_NAME:
            # Same place as in FL's factory Sampler presets
            events.append((FST_SAMPLE_FILE, path))
        events.append((event_id, value))
    return fst_bytes(header, events)
