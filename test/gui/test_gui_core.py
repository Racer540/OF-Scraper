"""
GUI unit tests: argbuild, patches, bridges, state, runner.

These run without a display or network: NiceGUI rendering is covered by a
separate render test; auth/API boundaries are never hit because jobs are
never started here (argbuild only parses argv into settings).
"""

import logging
import threading
import time

import pytest

log = logging.getLogger("shared")


@pytest.fixture(scope="session", autouse=True)
def gui_bootstrapped():
    """Install patches and bootstrap settings once for the whole module."""
    import ofscraper.gui.patches as patches

    patches.install()
    from ofscraper.gui.app import _bootstrap

    _bootstrap()
    yield
    patches.uninstall()


# ---------------------------------------------------------------- argbuild
class TestArgbuild:
    def test_scrape_job_parses(self, gui_bootstrapped):
        from ofscraper.gui import argbuild

        d = argbuild.build_job(
            ["-u", "user1,user2", "-a", "download,like", "-da", "Timeline,Messages",
             "-la", "Timeline"]
        )
        assert d.usernames == ["user1", "user2"]
        assert set(d.download_area) == {"Timeline", "Messages"}
        assert d.like_area == {"Timeline"} or list(d.like_area) == ["Timeline"]
        assert "download" in d.actions and "like" in d.actions

    def test_manual_command(self, gui_bootstrapped):
        from ofscraper.gui import argbuild

        d = argbuild.build_job(["manual", "-u", "https://onlyfans.com/123"])
        assert d.command == "manual"
        assert d.url == ["https://onlyfans.com/123"]

    def test_check_commands(self, gui_bootstrapped):
        from ofscraper.gui import argbuild

        for cmd in ("msg_check", "story_check", "paid_check"):
            d = argbuild.build_job([cmd, "-u", "someone"])
            assert d.command == cmd
        d = argbuild.build_job(
            ["post_check", "-u", "https://onlyfans.com/someone", "-ca", "Timeline",
             "-fo"]
        )
        assert d.command == "post_check"
        assert "Timeline" in d.check_area
        assert d.force is True

    def test_metadata_command(self, gui_bootstrapped):
        from ofscraper.gui import argbuild

        d = argbuild.build_job(
            ["metadata", "-md", "update", "-u", "someone", "-o", "Timeline",
             "--mark-stray"]
        )
        assert d.command == "metadata"
        assert d.metadata == "update"
        assert d.mark_stray is True

    def test_metadata_requires_mode(self, gui_bootstrapped):
        import click

        from ofscraper.gui import argbuild

        with pytest.raises(click.UsageError):
            argbuild.build_job(["metadata", "-u", "someone"])

    def test_db_command(self, gui_bootstrapped):
        from ofscraper.gui import argbuild

        d = argbuild.build_job(["db", "-o", "Timeline", "-dst", "posted", "-bdc"])
        assert d.command == "db"
        assert d.db_sort == "posted"
        assert d.db_asc is True

    def test_settings_updated_globally(self, gui_bootstrapped):
        import ofscraper.utils.settings as settings
        from ofscraper.gui import argbuild

        argbuild.build_job(["-u", "syncuser"])
        assert "syncuser" in settings.get_settings().usernames


# ---------------------------------------------------------------- patches
class TestPatches:
    def test_interactive_prompt_raises(self, gui_bootstrapped):
        import ofscraper.prompts.prompts as prompts

        from ofscraper.gui.errors import GuiPromptError

        with pytest.raises(GuiPromptError):
            prompts.main_prompt()
        with pytest.raises(GuiPromptError):
            prompts.download_areas_prompt()

    def test_safe_prompt_defaults(self, gui_bootstrapped):
        import ofscraper.prompts.prompts as prompts

        assert prompts.continue_prompt() is False
        assert prompts.retry_user_scan() is False
        assert prompts.reset_username_prompt() == "Selection_Strict"
        assert prompts.reset_download_areas_prompt() == "No"

    def test_make_auth_raises_auth_required(self, gui_bootstrapped):
        import ofscraper.utils.auth.make as make

        from ofscraper.gui.errors import GuiAuthRequired

        with pytest.raises(GuiAuthRequired):
            make.make_auth()

    def test_check_shim_installed(self, gui_bootstrapped):
        import ofscraper.classes.table.app as table_app
        import ofscraper.commands.check as check

        assert check.thread_starters.__name__ == "gui_thread_starters"
        assert type(table_app.app).__name__ == "GuiCheckApp"

    def test_check_shim_handoff_and_finish(self, gui_bootstrapped):
        import ofscraper.commands.check as check
        from ofscraper.gui.state import get_state

        state = get_state()
        rows = [
            {"index": 1, "number": 1, "download_cart": "[]", "username": "u",
             "downloaded": False}
        ]
        thread = threading.Thread(target=lambda: check.thread_starters(rows), daemon=True)
        thread.start()
        for _ in range(40):
            if state.check_rows_ready.is_set():
                break
            time.sleep(0.05)
        assert state.check_rows_ready.is_set()
        assert len(state.check_rows) == 1

        import ofscraper.classes.table.app as table_app

        table_app.app.update_cell_state("1", "[downloaded]", "bold green")
        assert state.check_rows[0]["download_cart"] == "[downloaded]"
        assert state.check_rows[0]["downloaded"] is True

        state.check_finished.set()
        thread.join(timeout=5)
        assert not thread.is_alive()

    def test_consumer_started_once(self, gui_bootstrapped):
        # thread_starters blocks until check_finished (or cancel) — never
        # call it synchronously on the test thread
        import ofscraper.commands.check as check
        from ofscraper.gui.state import get_state

        state = get_state()
        thread = threading.Thread(target=lambda: check.thread_starters([]), daemon=True)
        thread.start()
        for _ in range(40):
            if state.check_rows_ready.is_set():
                break
            time.sleep(0.05)
        state.check_finished.set()
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert check.thread_starters.consumer_started is True

    def test_cancel_hooks_raise(self, gui_bootstrapped):
        import ofscraper.utils.live.updater as updater
        from ofscraper.gui.state import get_state

        state = get_state()
        state.cancel_event.set()
        try:
            with pytest.raises(KeyboardInterrupt):
                updater.api.update_job_task(0, completed=1)
        finally:
            state.cancel_event.clear()

    def test_signal_tolerance_off_main_thread(self, gui_bootstrapped):
        import ofscraper.utils.context.exit as exit_context

        result = {}

        def work():
            try:
                with exit_context.DelayedKeyboardInterrupt():
                    pass
                result["ok"] = True
            except ValueError:
                result["ok"] = False

        t = threading.Thread(target=work)
        t.start()
        t.join()
        assert result.get("ok") is True


# ---------------------------------------------------------------- bridges
class TestBridges:
    def test_log_buffer(self):
        from ofscraper.gui.bridges.logs import LogBuffer

        buf = LogBuffer()
        buf.write("line one\n")
        buf.write("line two")
        assert buf.drain() == ["line one", "line two"]
        assert buf.drain() == []

    def test_log_widget_seam_receives_records(self, gui_bootstrapped):
        import ofscraper.utils.logs.logger as logger

        from ofscraper.gui.state import get_state

        buf = get_state().log_buffer
        logger.add_widget(buf)
        log.info("seam test marker 12345")
        drained = buf.drain()
        assert any("seam test marker 12345" in line for line in drained)

    def test_progress_snapshot_shape(self, gui_bootstrapped):
        from ofscraper.gui.bridges.progress import plain, snapshot

        snap = snapshot()
        for key in ("activity_desc", "activity_counter", "api", "userlist",
                    "metadata", "download", "like"):
            assert key in snap
        for group in ("api", "userlist", "download"):
            assert set(snap[group].keys()) == {"job", "overall"}
        assert plain("[bold red]Hello[/] world") == "Hello world"
        assert plain(None) == ""


# ---------------------------------------------------------------- state
class TestState:
    def test_job_lock_single_job(self):
        from ofscraper.gui.state import GuiState

        state = GuiState()
        assert state.begin_job("first") is True
        assert state.begin_job("second") is False
        state.finish_job(result="done")
        assert state.status.value == "idle"
        assert state.job_result == "done"
        assert state.begin_job("third") is True

    def test_cancel_flow(self):
        from ofscraper.gui.state import GuiState

        state = GuiState()
        state.begin_job("job")
        state.request_cancel()
        assert state.status.value == "cancelling"
        assert state.cancel_event.is_set()
        state.finish_job()
        assert not state.cancel_event.is_set()


# ---------------------------------------------------------------- runner
class TestRunner:
    def test_refuses_second_job(self, gui_bootstrapped, monkeypatch):
        from ofscraper.gui import runner as runner_mod
        from ofscraper.gui.state import get_state

        state = get_state()
        started = threading.Event()
        release = threading.Event()

        def fake_worker(self, argv, description):
            started.set()
            release.wait(timeout=10)
            state.finish_job(result="stub")

        monkeypatch.setattr(type(runner_mod.runner), "_worker", fake_worker)
        try:
            assert runner_mod.runner.start(["-u", "x"], "stub job") is True
            assert started.wait(timeout=5)
            assert runner_mod.runner.start(["-u", "y"], "second") is False
        finally:
            release.set()

    def test_bad_argv_reports_error(self, gui_bootstrapped):
        from ofscraper.gui import runner as runner_mod
        from ofscraper.gui.state import get_state

        state = get_state()
        assert runner_mod.runner.start(["--definitely-not-a-flag"], "bad job") is True
        for _ in range(100):
            if state.status.value == "idle":
                break
            time.sleep(0.05)
        assert state.status.value == "idle"
        assert state.job_error or state.job_result
