"""
Scrape screen: full form for the main download/like/unlike flow.

Builds the same argv the CLI accepts (see `ofscraper --help`) — the common
controls are widgets; anything exotic goes through the "extra CLI args" box,
so every flag remains reachable.
"""

from nicegui import ui

import ofscraper.gui.screens as screens
from ofscraper.gui.state import get_state

DOWNLOAD_AREAS = [
    "Timeline",
    "Archived",
    "Messages",
    "Pinned",
    "Highlights",
    "Stories",
    "Purchased",
    "Profile",
    "Streams",
    "Labels",
    "labels+",
    "labels*",
    "all",
]
LIKE_AREAS = ["Timeline", "Archived", "Pinned", "Labels", "Streams", "all"]
MEDIA_TYPES = ["Videos", "Audios", "Images"]


def _flag(argv, flag, value):
    if value not in (None, "", [], False):
        if isinstance(value, float) and value.is_integer():
            value = int(value)  # ui.number yields floats; CLI wants integers
        if isinstance(value, (list, tuple, set)):
            value = ",".join(str(v) for v in value)
        argv += [flag, str(value)]


def _flag_if(argv, flag, condition):
    if condition:
        argv.append(flag)


@screens.register("Scrape")
def render(nav):
    state = get_state()

    ui.label("Scrape / Download").classes("text-2xl font-bold")

    # ------------------------------------------------------------------ users
    with ui.card().classes("w-full"):
        ui.label("Users").classes("text-lg font-semibold")
        run_preview = ui.label().classes("text-sm text-gray-400 wrap")
        with ui.row().classes("w-full items-center"):
            ui.button("Pick models", on_click=lambda: nav("Models")).props("outline")
            manual_users = ui.input(
                "Usernames (overrides picker; ALL = every subscription)",
                placeholder="name1,name2  or  ALL",
            ).classes("grow")
        ui.label(
            "Tip: you can also use numeric user IDs, or leave both empty to be "
            "asked by terminal selection (not recommended in GUI mode)."
        ).classes("text-xs text-gray-400")

    # ---------------------------------------------------------------- actions
    with ui.card().classes("w-full"):
        ui.label("Actions").classes("text-lg font-semibold")
        with ui.row():
            action_download = ui.checkbox("Download", value=True)
            action_like = ui.checkbox("Like", value=False)
            action_unlike = ui.checkbox("Unlike", value=False)

        def like_conflict():
            if action_unlike.value and action_like.value:
                action_like.value = False

        action_unlike.on("change", like_conflict)
        action_like.on("change", like_conflict)

        with ui.row().classes("w-full items-center"):
            download_areas = screens.check_group(
                "Download areas", DOWNLOAD_AREAS, default=["Timeline"]
            )
            like_areas = screens.check_group("Like areas", LIKE_AREAS)
        scrape_paid = ui.checkbox(
            "Scrape entire paid page (very slow)", value=False
        )

    # ----------------------------------------------------------- post filters
    with ui.expansion("Post filters", icon="filter_alt").classes("w-full"):
        with ui.row().classes("w-full items-center"):
            post_id = ui.input("Post ID filter").classes("grow")
            label_filter = ui.input("Label filter (-lb)").classes("grow")
        with ui.row().classes("w-full items-center"):
            max_post_count = ui.number("Max posts", min=0, step=1)
            post_sort = ui.select(
                {"date": "date"}, label="Post sort", value=None
            ).classes("w-40")
            post_desc = ui.checkbox("Sort posts descending", value=False)
        with ui.row().classes("w-full items-center"):
            filter_regex = ui.input("Post text regex (-ft)").classes("grow")
            neg_filter = ui.input("Exclude regex (-nf)").classes("grow")
        with ui.row().classes("w-full items-center"):
            mass = ui.toggle(
                {"": "any", "-mm": "mass only", "-ms": "mass skip"},
                value="",
            )
            timed = ui.toggle(
                {"": "any", "-ok": "timed only", "-sk": "timed skip"},
                value="",
            )
        with ui.row().classes("w-full items-center"):
            before = ui.input("Before (YYYY-MM-DD)").classes("grow")
            after = ui.input("After (YYYY-MM-DD)").classes("grow")

    # ---------------------------------------------------------- media filters
    with ui.expansion("Media filters", icon="movie").classes("w-full"):
        with ui.row().classes("w-full items-center"):
            quality = ui.select(
                {"240": "240p", "720": "720p", "source": "source"},
                label="Video quality",
                value=None,
            ).classes("w-40")
            mediatypes = ui.select(
                {m: m for m in MEDIA_TYPES},
                label="Media types",
                multiple=True,
                value=[],
            ).classes("w-64")
        with ui.row().classes("w-full items-center"):
            size_max = ui.input("Max size (e.g. 10mb)").classes("grow")
            size_min = ui.input("Min size (e.g. 1mb)").classes("grow")
            length_max = ui.input("Max length (seconds)").classes("grow")
            length_min = ui.input("Min length (seconds)").classes("grow")
        with ui.row().classes("w-full items-center"):
            media_id = ui.input("Media ID filter (-mid)").classes("grow")
            max_media_count = ui.number("Max media", min=0, step=1)
        with ui.row().classes("w-full items-center"):
            media_sort = ui.select(
                {
                    "": "default",
                    "random": "random",
                    "text": "text",
                    "date": "date",
                    "filename": "filename",
                },
                label="Media sort",
                value="",
            ).classes("w-40")
            media_desc = ui.checkbox("Sort media descending", value=False)
        with ui.row().classes("w-full"):
            protected = ui.toggle(
                {"": "all", "-to": "protected only", "-no": "normal only"},
                value="",
            )
            text = ui.checkbox("Download text files too (-t)", value=False)
            text_only = ui.checkbox("Text files ONLY (-tx)", value=False)
        with ui.row().classes("w-full"):
            force_all = ui.checkbox("Force all / dupes (-e)", value=False)
            dupe_model = ui.checkbox(
                "Only new media per model (-eq)", value=False
            )
            redownload = ui.checkbox("Redownload everything (-rd)", value=False)

    # -------------------------------------------------------- user selection
    with ui.expansion("User list filters", icon="group").classes("w-full"):
        with ui.row().classes("w-full items-center"):
            userlist = ui.input("Userlist (-ul)").classes("grow")
            blacklist = ui.input("Blacklist (-bl)").classes("grow")
            excluded = ui.input("Excluded usernames (-eu)").classes("grow")
        with ui.row().classes("w-full"):
            current_price = ui.toggle(
                {"": "any", "paid": "paid", "free": "free"}, value=""
            )
            sub_status = ui.toggle(
                {"": "any", "-ts": "active", "-es": "expired"}, value=""
            )
            renew = ui.toggle({"": "any", "-ro": "renews on", "-rf": "renews off"}, value="")
            free_trial = ui.toggle(
                {"": "any", "-fo": "trial only", "-fs": "trial skip"}, value=""
            )
            promo = ui.toggle(
                {"": "any", "-po": "promo only", "-ps": "promo skip"}, value=""
            )
            last_seen = ui.toggle(
                {"": "any", "-lo": "visible only", "-ls": "hidden"}, value=""
            )

    # ------------------------------------------------------------ advanced
    with ui.expansion("Advanced user filters (price ranges, dates)", icon="tune").classes(
        "w-full"
    ):
        with ui.row().classes("w-full items-center"):
            ppn = ui.number("Promo price min", min=0)
            ppm = ui.number("Promo price max", min=0)
            gpn = ui.number("Regular price min", min=0)
            gpm = ui.number("Regular price max", min=0)
        with ui.row().classes("w-full items-center"):
            cpn = ui.number("Current price min", min=0)
            cpm = ui.number("Current price max", min=0)
            rpn = ui.number("Renewal price min", min=0)
            rpm = ui.number("Renewal price max", min=0)
        with ui.row().classes("w-full items-center"):
            lsb = ui.input("Last seen before (YYYY-MM-DD)").classes("grow")
            lsa = ui.input("Last seen after (YYYY-MM-DD)").classes("grow")
        with ui.row().classes("w-full items-center"):
            esb = ui.input("Expires before (YYYY-MM-DD)").classes("grow")
            esa = ui.input("Expires after (YYYY-MM-DD)").classes("grow")
        with ui.row().classes("w-full items-center"):
            ssb = ui.input("Subscribed before (YYYY-MM-DD)").classes("grow")
            ssa = ui.input("Subscribed after (YYYY-MM-DD)").classes("grow")

    # ------------------------------------------------------------- run bar
    with ui.card().classes("w-full"):
        with ui.row().classes("w-full items-center"):
            extra = ui.input(
                "Extra CLI args (appended verbatim)",
                placeholder="-sd 2 -p low",
            ).classes("grow")
            screens.run_button(
                lambda: _build_argv(),
                "Scrape job",
                label="Run scrape",
            )
            ui.button("Job monitor", on_click=lambda: nav("Job")).props("outline")

    # ------------------------------------------------------------- assembly
    def _split_users() -> list:
        manual = [u.strip() for u in (manual_users.value or "").split(",") if u.strip()]
        if manual:
            return manual
        return list(state.selected_usernames)

    def _toggle_flags(toggle_value, argv):
        # toggle values carry the literal flag to append (e.g. '-mm')
        if toggle_value:
            argv.append(toggle_value)

    def _build_argv() -> list:
        argv = []
        users = _split_users()
        _flag(argv, "-u", users)

        actions = []
        if action_download.value:
            actions.append("download")
        if action_like.value:
            actions.append("like")
        if action_unlike.value:
            actions.append("unlike")
        _flag(argv, "-a", actions)

        _flag(argv, "-da", download_areas())
        _flag(argv, "-la", like_areas())
        _flag_if(argv, "-sp", scrape_paid.value)

        # post filters
        _flag(argv, "-pd", post_id.value)
        _flag(argv, "-lb", label_filter.value)
        _flag(argv, "-xc", max_post_count.value)
        if post_sort.value:
            argv += ["-pst", post_sort.value]
        _flag_if(argv, "-pdc", post_desc.value)
        _flag(argv, "-ft", filter_regex.value)
        _flag(argv, "-nf", neg_filter.value)
        _toggle_flags(mass.value, argv)
        _toggle_flags(timed.value, argv)
        _flag(argv, "-be", before.value)
        _flag(argv, "-af", after.value)

        # media filters
        if quality.value:
            argv += ["-q", quality.value]
        _flag(
            argv,
            "-mt",
            [str(v).lower() for v in (mediatypes.value or [])],
        )
        _flag(argv, "-sx", size_max.value)
        _flag(argv, "-sm", size_min.value)
        _flag(argv, "-lx", length_max.value)
        _flag(argv, "-lm", length_min.value)
        _flag(argv, "-mid", media_id.value)
        _flag(argv, "-mxc", max_media_count.value)
        if media_sort.value:
            argv += ["-mst", media_sort.value]
        _flag_if(argv, "-mdc", media_desc.value)
        _toggle_flags(protected.value, argv)
        _flag_if(argv, "-t", text.value)
        _flag_if(argv, "-tx", text_only.value)
        _flag_if(argv, "-e", force_all.value)
        _flag_if(argv, "-eq", dupe_model.value)
        _flag_if(argv, "-rd", redownload.value)

        # user list filters
        _flag(argv, "-ul", userlist.value)
        _flag(argv, "-bl", blacklist.value)
        _flag(argv, "-eu", excluded.value)
        if current_price.value:
            argv += ["-cp", current_price.value]
        _toggle_flags(sub_status.value, argv)
        _toggle_flags(renew.value, argv)
        _toggle_flags(free_trial.value, argv)
        _toggle_flags(promo.value, argv)
        _toggle_flags(last_seen.value, argv)

        # advanced user filters
        _flag(argv, "-ppn", ppn.value)
        _flag(argv, "-ppm", ppm.value)
        _flag(argv, "-gpn", gpn.value)
        _flag(argv, "-gpm", gpm.value)
        _flag(argv, "-cpn", cpn.value)
        _flag(argv, "-cpm", cpm.value)
        _flag(argv, "-rpn", rpn.value)
        _flag(argv, "-rpm", rpm.value)
        _flag(argv, "-lsb", lsb.value)
        _flag(argv, "-lsa", lsa.value)
        _flag(argv, "-esb", esb.value)
        _flag(argv, "-esa", esa.value)
        _flag(argv, "-ssb", ssb.value)
        _flag(argv, "-ssa", ssa.value)

        # extras verbatim
        argv += (extra.value or "").split()
        return argv

    # live preview of exactly who this run will process — makes the
    # manual-usernames-override-picker behavior impossible to miss
    def refresh_run_preview():
        users = _split_users()
        if (manual_users.value or "").strip():
            run_preview.text = (
                f"Will run: {', '.join(users)} — typed usernames OVERRIDE "
                "the model picker"
            )
            run_preview.classes("text-yellow-400", remove="text-gray-400")
        elif users:
            run_preview.text = f"Will run: {', '.join(users)}"
            run_preview.classes("text-gray-400", remove="text-yellow-400")
        else:
            run_preview.text = "no models selected yet"
            run_preview.classes("text-gray-400", remove="text-yellow-400")

    refresh_run_preview()
    ui.timer(0.5, refresh_run_preview)
