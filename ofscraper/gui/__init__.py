r"""
 _______  _______         _______  _______  _______  _______  _______  _______  _______
(  ___  )(  ____ \       (  ____ \(  ____ \(  ____ )(  ___  )(  ____ )(  ____ \(  ____ )
| (   ) || (    \/       | (    \/| (    \/| (    )|| (   ) || (    )|| (    \/| (    )|
| |   | || (__     _____ | (_____ | |      | (____)|| (___) || (____)|| (__    | (____)|
| |   | ||  __)   (_____)(_____  )| |      |     __)|  ___  ||  _____)|  __)   |     __)
| |   | || (                   ) || |      | (\ (   | (   ) || (      | (      | (\ (
| (___) || )             /\____) || (____/\| ) \ \__| )   ( || )      | (____/\| ) \ \__
(_______)|/              \_______)(_______/|/   \__/|/     \||/       (_______/|/   \__/

GUI package (NiceGUI native window).
"""

# GUI mode never consumes CLI arguments (each screen builds its own argv via
# ofscraper.gui.argbuild), and the first lazy retriveArgs() during import
# parses the real sys.argv -- '--gui' would crash it.  Neutralize argv BEFORE
# the import chain below starts.
import sys as _sys

if any(flag in _sys.argv[1:] for flag in ("--gui", "-g")):
    _sys.argv = [_sys.argv[0]]

# The console/settings/config modules form an import cycle that only resolves
# if `ofscraper.main.close.exit` is imported first (the CLI entry does this
# implicitly through ofscraper/main/open/run.py).  Seed it here so any import
# of the gui package is safe.
import ofscraper.main.close.exit as _cycle_seed  # noqa: F401,E402
