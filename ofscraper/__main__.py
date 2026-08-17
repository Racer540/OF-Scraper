import multiprocessing
import sys


def _wants_gui(argv):
    if "--gui" in argv or "-g" in argv:
        return True
    # On Windows, double-clicking the exe passes no arguments: open the GUI.
    return sys.platform == "win32" and not argv


def main():
    # Frozen exe (PyInstaller): multiprocessing children re-run this script
    # with --multiprocessing-fork; freeze_support() intercepts them here so
    # they never reach the arg parsing below.
    multiprocessing.freeze_support()
    argv = sys.argv[1:]
    if _wants_gui(argv):
        forced = "--gui" in argv or "-g" in argv
        try:
            from ofscraper.gui.app import main as gui_main
        except Exception:
            if forced:
                # -g was explicit, so failing loudly beats silently downgrading
                raise
            # CLI-only build (GUI stack excluded): fall through to the menu
        else:
            gui_main()
            return
    import ofscraper.main.open.load as load

    load.main()


if __name__ == "__main__":
    main()
