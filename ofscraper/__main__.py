import sys


def main():
    if "--gui" in sys.argv[1:] or "-g" in sys.argv[1:]:
        from ofscraper.gui.app import main as gui_main

        gui_main()
        return
    import ofscraper.main.open.load as load

    load.main()


if __name__ == "__main__":
    main()
