# -*- mode: python ; coding: utf-8 -*-
import os

# --- This block makes the spec file self-aware and robust ---
# SPECPATH is a variable provided by PyInstaller containing the path to the spec file's directory.
spec_dir = SPECPATH
# Calculate the project root (one level up from 'specs/')
project_root = os.path.join(spec_dir, '..')
# -----------------------------------------------------------------------

# This block finds the ffmpeg binary to bundle with your app
try:
    from pyffmpeg import FFmpeg
    ffmpeg_binary_path = FFmpeg().get_ffmpeg_bin()
    # The spec format for binaries is a list of tuples: (source_path, destination_in_bundle)
    ffmpeg_binary_tuple = (ffmpeg_binary_path, '.')
    print(f"✅ Found ffmpeg binary to bundle: {ffmpeg_binary_path}")
except Exception as e:
    print(f"⚠️ WARNING: Could not find ffmpeg binary; it will not be bundled. Error: {e}")
    ffmpeg_binary_tuple = None

# --- NiceGUI static assets (required for the GUI; PyInstaller misses them) ---
from PyInstaller.utils.hooks import collect_data_files

nicegui_datas = collect_data_files('nicegui')


def _windows_version_info():
    """Embed the build version into the exe's Windows file properties
    (Details tab in Explorer). Reads the version hatchling derived from git
    at install time, e.g. 3.14.7+g8256b6f4."""
    if os.name != 'nt':
        return None
    import re

    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    try:
        from importlib.metadata import version as pkg_version

        ver = pkg_version('ofscraper')
    except Exception:
        ver = '0.0.0'
    m = re.match(r'(\d+)\.(\d+)\.(\d+)', ver)
    quad = tuple(int(g) for g in m.groups()) + (0,) if m else (0, 0, 0, 0)
    return VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=quad,
            prodvers=quad,
            mask=0x3F,
            flags=0x0,
            OS=0x40004,
            fileType=0x1,
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        '040904B0',
                        [
                            StringStruct('CompanyName', 'OF-Scraper'),
                            StringStruct('FileDescription', 'OF-Scraper'),
                            StringStruct('FileVersion', ver),
                            StringStruct('ProductName', 'OF-Scraper'),
                            StringStruct('ProductVersion', ver),
                            StringStruct('OriginalFilename', 'ofscraper_file.exe'),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct('Translation', [1033, 1200])]),
        ],
    )

# This Analysis block contains all the necessary dependency information
a = Analysis(
    # Provide a full, unambiguous path to the main script
    [os.path.join(project_root, 'ofscraper', '__main__.py')],
    # Use the calculated project_root for the path
    pathex=[project_root],
    # Bundle the ffmpeg binary
    binaries=[ffmpeg_binary_tuple] if ffmpeg_binary_tuple else [],
    datas=nicegui_datas,
    # Include the hidden import for diskcache
    hiddenimports=['diskcache'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# --- This section defines the one-dir build ---
# The EXE object for a one-dir build includes the binaries and data directly.
# There is no final COLLECT step.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ofscraper_file', # The base name of the output executable
    version=_windows_version_info(),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)